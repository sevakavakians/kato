"""
A single symbol matches a pattern wherever it occurs (issue #15).

Single-symbol candidate selection used to read only patterns whose first stored
token was the symbol. Events are sorted, so of [['A','B','C'], ['marker']] a lone
'A' matched while a lone 'B' or 'C' did not: alphabetical order decided
eligibility. Selection now takes every pattern containing the symbol, and the
preference for patterns that start with the observed symbols moved into ranking
as `onset_alignment`, alongside the position-free `event_cohesion`.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from fixtures.kato_fixtures import kato_fixture as kato_fixture

from kato.representations.prediction import event_overlap_metrics


def _learn(fixture, events):
    fixture.clear_short_term_memory()
    for event in events:
        fixture.observe({'strings': event, 'vectors': [], 'emotives': {}})
    return fixture.learn()


def _predict(fixture, events):
    fixture.clear_short_term_memory()
    for event in events:
        fixture.observe({'strings': event, 'vectors': [], 'emotives': {}})
    return fixture.get_predictions()


def _by_name(predictions, name):
    clean = name[5:] if name.startswith('PTRN|') else name
    for prediction in predictions:
        if prediction['name'] in (name, clean, f'PTRN|{clean}'):
            return prediction
    return None


# ── event_overlap_metrics ──────────────────────────────────────────────

def test_overlap_metrics_single_symbol_first_event():
    assert event_overlap_metrics([['A', 'B', 'C'], ['marker']], [['B']]) == (1.0, 1.0)


def test_overlap_metrics_onset_decays_with_position():
    cohesion, onset = event_overlap_metrics([['x'], ['y'], ['B', 'z']], [['B']])
    assert cohesion == 1.0
    assert onset == pytest.approx(1 / 3)


def test_overlap_metrics_partial_overlap():
    # [['A','C']] against a pattern that splits A and C across two events: flat
    # matching calls this complete, cohesion does not.
    cohesion, onset = event_overlap_metrics([['A'], ['C'], ['m']], [['A', 'C']])
    assert cohesion == 0.5
    assert onset == 0.5


def test_overlap_metrics_repeated_symbol_prefers_earliest():
    cohesion, onset = event_overlap_metrics([['x'], ['B'], ['B']], [['B']])
    assert (cohesion, onset) == (1.0, 0.5)


def test_overlap_metrics_multi_event_stm():
    # Cohesion averages over STM events; onset reads the first one.
    cohesion, onset = event_overlap_metrics([['A', 'B'], ['C']], [['A', 'C'], ['C']])
    assert cohesion == pytest.approx((0.5 + 1.0) / 2)
    assert onset == 0.5


def test_overlap_metrics_without_stm():
    assert event_overlap_metrics([['A']], None) == (0.0, 0.0)
    assert event_overlap_metrics([['A']], []) == (0.0, 0.0)
    assert event_overlap_metrics([['A']], [[]]) == (0.0, 0.0)


def test_overlap_metrics_absent_symbol():
    assert event_overlap_metrics([['A'], ['B']], [['Z']]) == (0.0, 0.0)


# ── end to end ─────────────────────────────────────────────────────────

@pytest.mark.parametrize('symbol', ['A', 'B', 'C'])
def test_any_member_of_the_first_event_selects_the_pattern(kato_fixture, symbol):
    kato_fixture.clear_all_memory()
    name = _learn(kato_fixture, [['A', 'B', 'C'], ['marker']])

    prediction = _by_name(_predict(kato_fixture, [[symbol]]), name)
    assert prediction is not None, f"lone {symbol!r} should select the pattern"
    assert prediction['past'] == []
    assert prediction['present'] == [['A', 'B', 'C']]
    assert prediction['missing'] == [[s for s in ['A', 'B', 'C'] if s != symbol]]
    assert prediction['future'] == [['marker']]
    assert prediction['onset_alignment'] == 1.0
    assert prediction['event_cohesion'] == 1.0


def test_absent_symbol_selects_nothing(kato_fixture):
    kato_fixture.clear_all_memory()
    _learn(kato_fixture, [['A', 'B', 'C'], ['marker']])
    assert _predict(kato_fixture, [['Z']]) == []


def test_symbol_in_a_later_event_selects_the_pattern(kato_fixture):
    kato_fixture.clear_all_memory()
    name = _learn(kato_fixture, [['A', 'B', 'C'], ['marker']])

    prediction = _by_name(_predict(kato_fixture, [['marker']]), name)
    assert prediction is not None
    assert prediction['past'] == [['A', 'B', 'C']]
    assert prediction['present'] == [['marker']]
    assert prediction['onset_alignment'] == 0.5


def test_single_event_ranking_prefers_patterns_that_start_with_the_symbol(kato_fixture):
    kato_fixture.clear_all_memory()
    # Same shape and length, so every other metric is equal and onset decides.
    starts = _learn(kato_fixture, [['B', 'k1'], ['k2'], ['k3']])
    late = _learn(kato_fixture, [['k4'], ['k5'], ['B', 'k6']])

    predictions = _predict(kato_fixture, [['B']])
    first, last = _by_name(predictions, starts), _by_name(predictions, late)
    assert first is not None and last is not None
    assert first['onset_alignment'] == 1.0
    assert last['onset_alignment'] == pytest.approx(1 / 3)
    assert first['potential'] - last['potential'] == pytest.approx(2 / 3)
    assert predictions.index(first) < predictions.index(last)


def test_multi_symbol_single_event_uses_cohesion_and_onset(kato_fixture):
    kato_fixture.clear_all_memory()
    together = _learn(kato_fixture, [['A', 'B', 'C'], ['m']])
    split = _learn(kato_fixture, [['A'], ['C'], ['m']])

    predictions = _predict(kato_fixture, [['A', 'C']])
    p_together, p_split = _by_name(predictions, together), _by_name(predictions, split)
    assert p_together is not None and p_split is not None
    assert (p_together['event_cohesion'], p_together['onset_alignment']) == (1.0, 1.0)
    assert (p_split['event_cohesion'], p_split['onset_alignment']) == (0.5, 0.5)


def test_multi_event_stm_potential_excludes_onset(kato_fixture):
    kato_fixture.clear_all_memory()
    name = _learn(kato_fixture, [['A', 'B', 'C'], ['marker'], ['tail']])

    prediction = _by_name(_predict(kato_fixture, [['A'], ['marker']]), name)
    assert prediction is not None
    assert prediction['onset_alignment'] > 0
    frag = prediction['fragmentation']
    expected = (
        (prediction['evidence'] + prediction['confidence']) * prediction['snr']
        + prediction['itfdf_similarity']
        + (0.0 if frag == -1 else 1.0 / (frag + 1))
    )
    assert prediction['potential'] == pytest.approx(expected, rel=1e-9, abs=1e-12)
