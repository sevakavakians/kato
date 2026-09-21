"""
Proof tests for the recall-safe candidate bound.

The bound in :mod:`kato.filters.recall_bounds` lets ClickHouse discard patterns
that cannot possibly clear ``recall_threshold``. Its ONLY safety requirement is:

    whenever the real scorer accepts a candidate, the bound must also accept it.

The converse is not required -- the bound is allowed to pass candidates the
scorer later rejects, because the scorer still runs on every survivor. So every
assertion here tests that one direction. Extra candidates are fine; a missing
candidate is a silent recall loss and a correctness bug.

These tests need no database and no services.
"""

import random
from fractions import Fraction

import pytest

from kato.filters.recall_bounds import (
    DEN,
    MAX_STATE_TOKENS,
    RecallBound,
    build_pattern_query,
    compute_recall_bound,
    similarity_upper_bound,
    weakened_threshold,
)
from kato.searches.pattern_search import _lcs_ratio_scorer

# 1/3 is deliberate: it has no exact decimal form, so it exercises the
# Fraction -> floor(num/DEN) path rather than a value that happens to be clean.
THRESHOLDS = [0.01, 0.1, 1 / 3, 0.5, 2 / 3, 0.9, 0.99]


def scorer_accepts(lcs_len: int, pattern_len: int, stm_len: int, threshold: float) -> bool:
    """Reproduce the scorer's acceptance test, including its float round trip.

    ``_lcs_ratio_scorer`` returns a 0-100 score which the caller divides by 100
    again (pattern_search.py:1007-1008). That ``*100.0`` then ``/100.0`` is not
    an identity in floating point, so the bound must be safe against this exact
    form, not against the algebraically equivalent one.
    """
    total = pattern_len + stm_len
    if total == 0:
        return False
    score = 2.0 * lcs_len / total * 100.0
    return (score / 100.0) >= threshold


def bound_accepts(bound: RecallBound, pattern_len: int, common: int) -> bool:
    """Apply the bound's predicates exactly as the SQL does."""
    if not bound.applied:
        return True  # no bound established -> everything is queried
    if not (bound.min_length <= pattern_len <= bound.max_length):
        return False
    if bound.use_token_overlap:
        if 2 * common * bound.den < bound.num * (pattern_len + bound.stm_len):
            return False
    return True


def make_bound(threshold, stm_len=1):
    """A bound for a synthetic STM of ``stm_len`` distinct tokens."""
    state = [f"t{i}" for i in range(stm_len)]
    return compute_recall_bound(state, threshold, use_token_matching=True)


class TestRecallSafety:
    """The core guarantee, swept exhaustively."""

    def test_bound_never_rejects_what_the_scorer_accepts(self):
        """Exhaustive sweep over (threshold, stm_len, pattern_len, lcs_len).

        ``common >= lcs_len`` always, so testing with ``common == lcs_len`` is
        the tightest -- and therefore worst -- case for the overlap predicate.
        """
        failures = []
        guarded = 0
        for threshold in THRESHOLDS:
            for stm_len in range(1, 41):
                bound = make_bound(threshold, stm_len)
                assert bound.applied, f"bound should apply for r={threshold}, L={stm_len}"
                for pattern_len in range(2, 201):
                    for lcs_len in range(0, min(pattern_len, stm_len) + 1):
                        if not scorer_accepts(lcs_len, pattern_len, stm_len, threshold):
                            continue
                        guarded += 1
                        if not bound_accepts(bound, pattern_len, common=lcs_len):
                            failures.append((threshold, stm_len, pattern_len, lcs_len))
        assert not failures, (
            f"{len(failures)} candidates accepted by the scorer were rejected by the "
            f"bound (silent recall loss). First 5: {failures[:5]}"
        )
        # Non-vacuity: an assertion that guards nothing proves nothing. If the
        # sweep or the scorer changes such that few cases are accepted, this
        # test would pass while testing almost nothing -- fail loudly instead.
        assert guarded > 300_000, (
            f"sweep only guarded {guarded} accepted candidates; it should guard "
            f"~324k. The test has gone vacuous."
        )

    def test_bound_agrees_with_the_real_scorer_on_random_sequences(self):
        """Same guarantee, but driving the actual RapidFuzz scorer end to end."""
        rng = random.Random(20260921)
        vocab = [f"s{i}" for i in range(25)]
        failures = []
        guarded = 0
        for _ in range(20000):
            threshold = rng.choice(THRESHOLDS)
            state = [rng.choice(vocab) for _ in range(rng.randint(1, 15))]
            pattern = [rng.choice(vocab) for _ in range(rng.randint(2, 40))]

            similarity = _lcs_ratio_scorer(state, pattern) / 100.0
            if similarity < threshold:
                continue

            guarded += 1
            bound = compute_recall_bound(state, threshold, use_token_matching=True)
            state_set = set(state)
            common = sum(1 for token in pattern if token in state_set)
            if not bound_accepts(bound, len(pattern), common):
                failures.append((threshold, state, pattern, similarity))
        assert not failures, (
            f"{len(failures)} real-scorer matches were rejected by the bound. "
            f"First: {failures[:1]}"
        )
        # Non-vacuity guard -- see the sweep test above.
        assert guarded > 1000, (
            f"only {guarded} random pairs cleared their threshold; this test is "
            f"no longer exercising the bound meaningfully."
        )

    def test_exact_rational_arithmetic_would_have_been_unsafe(self):
        """Pin the reason this module uses weakened integers, not Fractions.

        float(0.1) > 1/10, so an exact comparison is stricter than the scorer and
        loses genuine matches. If someone 'cleans this up' to use Fraction(r)
        directly, this test documents what breaks.
        """
        threshold, stm_len, pattern_len, lcs_len = 0.1, 1, 19, 1

        assert scorer_accepts(lcs_len, pattern_len, stm_len, threshold)
        # The naive exact form rejects it...
        assert not (Fraction(2 * lcs_len, pattern_len + stm_len) >= Fraction(threshold))
        assert Fraction(0.1) > Fraction(1, 10)
        # ...but the shipped bound keeps it.
        bound = make_bound(threshold, stm_len)
        assert bound_accepts(bound, pattern_len, common=lcs_len)


class TestLengthWindow:
    def test_upper_bound_float_error_case(self):
        """r=0.1, L=21: float gives 398.99999999999994, so int() would say 398.

        The true bound is exactly 399, and a 399-token pattern with a full LCS
        scores exactly 0.1 and must be kept.
        """
        bound = make_bound(0.1, stm_len=21)
        assert bound.max_length == 399

    def test_window_is_not_clamped_to_minimum_pattern_length(self):
        """Patterns are always >= 2 symbols, but the bound must not rely on it.

        Encoding that guarantee here would convert a documentation assumption
        into a correctness dependency for no selectivity gain.
        """
        bound = make_bound(0.1, stm_len=1)
        assert bound.min_length <= 1

    def test_max_length_is_clamped_to_uint32(self):
        """The length column is UInt32; a bound above that is meaningless."""
        bound = make_bound(1e-6, stm_len=40)
        assert bound.max_length <= 2**32 - 1


class TestTokenOverlap:
    def test_common_counts_multiplicity(self):
        """A pattern repeating one STM token has common == its repeat count.

        Counting distinct symbols instead would under-count and could reject a
        genuine match.
        """
        state = ['q1', 'q2']
        pattern = ['q1'] * 10
        assert similarity_upper_bound(pattern, set(state), len(state)) == Fraction(2 * 10, 12)

    def test_upper_bound_is_never_below_true_similarity(self):
        rng = random.Random(7)
        vocab = [f"v{i}" for i in range(15)]
        for _ in range(5000):
            state = [rng.choice(vocab) for _ in range(rng.randint(1, 12))]
            pattern = [rng.choice(vocab) for _ in range(rng.randint(2, 25))]
            true_similarity = _lcs_ratio_scorer(state, pattern) / 100.0
            upper = similarity_upper_bound(pattern, set(state), len(state))
            assert float(upper) >= true_similarity - 1e-12, (
                f"upper bound {float(upper)} below true similarity {true_similarity}"
            )


class TestDegradationLadder:
    """Every rung must be a superset of the one below, so all are recall-safe."""

    def test_kill_switch_disables(self):
        bound = compute_recall_bound(['a'], 0.5, use_token_matching=True, enabled=False)
        assert not bound.applied and bound.reason == 'kill_switch'

    def test_character_mode_disables(self):
        """Character mode scores a CHARACTER metric; a token bound is invalid."""
        bound = compute_recall_bound(['a'], 0.5, use_token_matching=False)
        assert not bound.applied and bound.reason == 'character_mode'

    @pytest.mark.parametrize("threshold", [0.0, None, 1e-9])
    def test_non_positive_or_subgrid_threshold_disables(self, threshold):
        """At r=0 every pattern qualifies, so no filter is valid.

        Below 1/DEN the weakened threshold floors to 0, which is the same case.
        """
        bound = compute_recall_bound(['a', 'b'], threshold, use_token_matching=True)
        assert not bound.applied

    def test_empty_state_disables(self):
        bound = compute_recall_bound([], 0.5, use_token_matching=True)
        assert not bound.applied and bound.reason == 'empty_state'

    def test_oversized_token_list_falls_back_to_length_window(self):
        """Never truncate the token list -- a partial list under-counts common.

        Degrade to the length window, which is still applied and still safe.
        """
        state = [f"token{i}" for i in range(MAX_STATE_TOKENS + 1)]
        bound = compute_recall_bound(state, 0.5, use_token_matching=True)
        assert bound.applied
        assert not bound.use_token_overlap
        assert bound.reason == 'token_payload_too_large'
        assert bound.max_length > 0

    def test_oversized_fallback_is_still_recall_safe(self):
        """The degraded rung must still never reject a genuine match."""
        state = [f"token{i}" for i in range(MAX_STATE_TOKENS + 1)]
        threshold = 0.5
        bound = compute_recall_bound(state, threshold, use_token_matching=True)
        stm_len = len(state)
        for pattern_len in range(2, 400):
            for lcs_len in range(0, min(pattern_len, stm_len) + 1, 37):
                if scorer_accepts(lcs_len, pattern_len, stm_len, threshold):
                    assert bound_accepts(bound, pattern_len, common=lcs_len)


class TestDeterminism:
    def test_state_tokens_are_order_independent_and_sorted(self):
        """Query text must be reproducible: set order varies with PYTHONHASHSEED."""
        a = compute_recall_bound(['c', 'a', 'b', 'a'], 0.5, use_token_matching=True)
        b = compute_recall_bound(['b', 'c', 'a'], 0.5, use_token_matching=True)
        assert a.state_tokens == b.state_tokens == ('a', 'b', 'c')


class TestQueryConstruction:
    def test_unapplied_bound_yields_the_unbounded_query(self):
        """The disabled path must emit exactly the pre-bound behaviour."""
        bound = compute_recall_bound(['a'], 0.5, use_token_matching=True, enabled=False)
        query, params = build_pattern_query(bound)
        assert 'hasAny' not in query and 'BETWEEN' not in query
        assert '%(kb_id)s' in query
        assert params == {}

    def test_bounded_query_binds_every_placeholder_except_kb_id(self):
        """kb_id is the executor's reserved parameter; everything else is ours."""
        bound = make_bound(0.1, stm_len=3)
        query, params = build_pattern_query(bound)
        assert 'hasAny(token_set' in query
        assert 'arrayFlatten(pattern_data)' in query
        assert set(params) == {'min_length', 'max_length', 'state_tokens', 'num', 'den', 'stm_len'}
        assert 'kb_id' not in params
        # A list, not a tuple: has()/hasAny() need ClickHouse array syntax.
        assert isinstance(params['state_tokens'], list)

    def test_length_only_query_omits_token_clauses(self):
        bound = RecallBound(
            applied=True, reason='token_payload_too_large', use_token_overlap=False,
            min_length=2, max_length=40, num=weakened_threshold(0.5), stm_len=5,
        )
        query, params = build_pattern_query(bound)
        assert 'hasAny' not in query and 'BETWEEN' in query
        assert set(params) == {'min_length', 'max_length'}

    def test_no_float_literals_reach_the_sql(self):
        """Float in SQL would reintroduce the rounding hazard server-side."""
        bound = make_bound(1 / 3, stm_len=4)
        _, params = build_pattern_query(bound)
        for key in ('min_length', 'max_length', 'num', 'den', 'stm_len'):
            assert isinstance(params[key], int), f"{key} must be int, got {type(params[key])}"


class TestWeakenedThreshold:
    def test_is_never_above_the_requested_threshold(self):
        """This is what makes the derived predicates permissive rather than strict."""
        for threshold in THRESHOLDS + [0.123456789, 0.999999, 1.0]:
            assert Fraction(weakened_threshold(threshold), DEN) <= Fraction(threshold)
