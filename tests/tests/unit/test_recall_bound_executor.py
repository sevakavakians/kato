"""
Executor-level tests for the recall-safe candidate bound.

Covers the three behaviours that the pure-arithmetic tests in
test_recall_bounds.py cannot reach, because they live in the executor:

  1. the bound is actually applied to the query that runs
  2. a bounded-query failure FAILS OPEN to the unbounded query
  3. the audit mode actually detects a violation (a clean audit report from a
     broken audit is indistinguishable from a clean one from a working audit,
     so this is tested with a deliberately over-aggressive bound)

Uses stub clients -- no database, no services.
"""

import logging
from types import SimpleNamespace

import pytest

from kato.filters import recall_bounds
from kato.filters.executor import FilterPipelineExecutor


class StubResult:
    """Mimics a clickhouse-connect query result."""

    def __init__(self, rows):
        self.column_names = ['name', 'pattern_data', 'length']
        self.result_rows = rows


class StubClickHouse:
    """Records the queries it is asked to run and replays canned rows."""

    def __init__(self, rows, fail_on_bounded=False):
        self.rows = rows
        self.fail_on_bounded = fail_on_bounded
        self.queries = []

    def query(self, query, parameters=None):
        self.queries.append((query, parameters or {}))
        is_bounded = 'hasAny' in query or 'BETWEEN' in query
        if is_bounded and self.fail_on_bounded:
            raise RuntimeError("simulated ClickHouse failure on the bounded query")
        if is_bounded:
            # Crude stand-in for the server-side predicate: keep only patterns
            # sharing a token with the STM.
            tokens = set(parameters.get('state_tokens', []))
            kept = [r for r in self.rows if tokens & {t for ev in r[1] for t in ev}]
            return StubResult(kept)
        return StubResult(self.rows)


def make_executor(rows, *, threshold=0.3, token_matching=True, fail_on_bounded=False,
                  audit=False, enabled=True):
    config = SimpleNamespace(filter_pipeline=[], enable_filter_metrics=False)
    ch = StubClickHouse(rows, fail_on_bounded=fail_on_bounded)
    ex = FilterPipelineExecutor(
        config=config,
        state=['alpha', 'beta'],
        clickhouse_client=ch,
        redis_client=None,
        kb_id='test_kb',
        recall_threshold=threshold,
        use_token_matching=token_matching,
    )
    # Set explicitly rather than via env so the test does not depend on the
    # ambient environment.
    ex.recall_bound_enabled = enabled
    ex.recall_bound_audit = audit
    return ex, ch


# Two patterns share the STM's tokens; two are entirely disjoint from it.
ROWS = [
    ('p_match_1', [['alpha'], ['beta'], ['gamma']], 3),
    ('p_match_2', [['alpha'], ['beta'], ['delta']], 3),
    ('p_other_1', [['zzz1'], ['zzz2'], ['zzz3']], 3),
    ('p_other_2', [['yyy1'], ['yyy2'], ['yyy3']], 3),
]


class TestBoundIsApplied:
    def test_bounded_query_is_used_and_prunes(self):
        ex, ch = make_executor(ROWS)
        candidates = ex._get_all_patterns()
        assert candidates == {'p_match_1', 'p_match_2'}
        assert len(ch.queries) == 1
        assert 'hasAny' in ch.queries[0][0]

    def test_kill_switch_emits_the_unbounded_query(self):
        ex, ch = make_executor(ROWS, enabled=False)
        candidates = ex._get_all_patterns()
        assert candidates == {r[0] for r in ROWS}
        assert 'hasAny' not in ch.queries[0][0]
        assert 'BETWEEN' not in ch.queries[0][0]

    def test_character_mode_emits_the_unbounded_query(self):
        """A token bound is invalid against a character-level scorer."""
        ex, ch = make_executor(ROWS, token_matching=False)
        candidates = ex._get_all_patterns()
        assert candidates == {r[0] for r in ROWS}
        assert 'hasAny' not in ch.queries[0][0]

    def test_stage_metrics_record_the_reduction(self):
        ex, _ = make_executor(ROWS)
        ex._get_all_patterns()
        stage = ex.stage_metrics[-1]
        assert stage['filter'] == 'recall_bound'
        assert stage['candidates_after'] == 2
        assert stage['applied'] is True


class TestFailOpen:
    def test_bounded_query_failure_retries_unbounded(self):
        """A bound failure must never reduce the candidate set to nothing.

        Before the bound, an exception here returned an empty set behind an
        HTTP 200 -- zero predictions with no error surfaced. The bound must not
        add a second route to that state.
        """
        ex, ch = make_executor(ROWS, fail_on_bounded=True)
        candidates = ex._get_all_patterns()
        assert candidates == {r[0] for r in ROWS}, "should have fallen back to the full corpus"
        assert len(ch.queries) == 2, "expected a bounded attempt then an unbounded retry"
        assert 'hasAny' in ch.queries[0][0]
        assert 'hasAny' not in ch.queries[1][0]

    def test_total_failure_returns_empty_without_raising(self):
        class AlwaysFails:
            def query(self, *a, **k):
                raise RuntimeError("clickhouse is down")

        config = SimpleNamespace(filter_pipeline=[], enable_filter_metrics=False)
        ex = FilterPipelineExecutor(
            config=config, state=['alpha'], clickhouse_client=AlwaysFails(),
            redis_client=None, kb_id='k', recall_threshold=0.3, use_token_matching=True,
        )
        assert ex._get_all_patterns() == set()


class TestAuditHasTeeth:
    def test_audit_reports_clean_when_the_bound_is_correct(self, caplog):
        ex, _ = make_executor(ROWS, audit=True)
        with caplog.at_level(logging.INFO, logger='kato.filters.executor'):
            ex._get_all_patterns()
        assert any('audit clean' in r.message.lower() or 'audit clean' in r.getMessage().lower()
                   for r in caplog.records)
        assert not any(r.levelno >= logging.ERROR for r in caplog.records)

    def test_audit_detects_an_over_aggressive_bound(self, caplog, monkeypatch):
        """Deliberately break the bound and confirm the audit catches it.

        Without this, a clean audit proves nothing -- an audit that never fires
        reports exactly the same thing as one that works.
        """
        real_compute = recall_bounds.compute_recall_bound

        def over_aggressive(state, recall_threshold, use_token_matching, enabled=True):
            bound = real_compute(state, recall_threshold, use_token_matching, enabled)
            if not bound.applied:
                return bound
            # Drop everything by demanding an impossible pattern length.
            return recall_bounds.RecallBound(
                applied=True, reason='deliberately_broken', use_token_overlap=False,
                min_length=10**9, max_length=10**9, num=bound.num, stm_len=bound.stm_len,
            )

        monkeypatch.setattr('kato.filters.executor.compute_recall_bound', over_aggressive)

        class DropEverything(StubClickHouse):
            def query(self, query, parameters=None):
                self.queries.append((query, parameters or {}))
                if 'BETWEEN' in query or 'hasAny' in query:
                    return StubResult([])  # the broken bound drops all of them
                return StubResult(self.rows)

        config = SimpleNamespace(filter_pipeline=[], enable_filter_metrics=False)
        ch = DropEverything(ROWS)
        ex = FilterPipelineExecutor(
            config=config, state=['alpha', 'beta'], clickhouse_client=ch,
            redis_client=None, kb_id='k', recall_threshold=0.3, use_token_matching=True,
        )
        ex.recall_bound_enabled = True
        ex.recall_bound_audit = True

        with caplog.at_level(logging.INFO, logger='kato.filters.executor'):
            ex._get_all_patterns()

        errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert errors, "audit failed to flag a bound that dropped reachable patterns"
        assert any('RECALL BOUND VIOLATION' in r.getMessage() for r in errors)

    def test_audit_does_not_leak_extra_patterns_into_the_request_cache(self):
        """The audit loads the full corpus; that must not reach the scorer."""
        ex, _ = make_executor(ROWS, audit=True)
        candidates = ex._get_all_patterns()
        assert candidates == {'p_match_1', 'p_match_2'}
        assert set(ex.patterns_cache) == {'p_match_1', 'p_match_2'}, (
            f"audit leaked patterns into the cache: {set(ex.patterns_cache)}"
        )


@pytest.mark.parametrize("threshold", [0.1, 0.5, 0.9])
def test_bound_never_drops_a_pattern_the_scorer_would_keep(threshold):
    """End-to-end at the executor level, against the real scorer."""
    from kato.searches.pattern_search import _lcs_ratio_scorer

    state = ['alpha', 'beta']
    ex, _ = make_executor(ROWS, threshold=threshold)
    candidates = ex._get_all_patterns()

    for name, pattern_data, _length in ROWS:
        flat = [t for ev in pattern_data for t in ev]
        if _lcs_ratio_scorer(state, flat) / 100.0 >= threshold:
            assert name in candidates, (
                f"{name} clears threshold {threshold} but the bound dropped it"
            )
