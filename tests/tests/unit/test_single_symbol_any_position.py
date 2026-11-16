"""
A single symbol matches a pattern wherever it occurs (issue #15).

Single-symbol candidate selection used to read only patterns whose first stored
token was the symbol. Events are sorted, so of [['A','B','C'], ['marker']] a lone
'A' matched while a lone 'B' or 'C' did not: alphabetical order decided
eligibility. Selection now takes every pattern containing the symbol, and the
preference for patterns that start with the observed symbols is left to ranking:
`potential` scores a pattern higher the less of it lies before the match (its
`evidence_to_end` term), and `onset_alignment` reports the position, alongside
the position-free `event_cohesion`.
"""

import math
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from fixtures.kato_fixtures import kato_fixture as kato_fixture

from kato.informatics.prediction_metrics import POTENTIAL_WEIGHTS as W
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
    # Same shape and length, so the match is the same and only its position
    # differs: nothing precedes it in one pattern, two events do in the other.
    starts = _learn(kato_fixture, [['B', 'k1'], ['k2'], ['k3']])
    late = _learn(kato_fixture, [['k4'], ['k5'], ['B', 'k6']])

    predictions = _predict(kato_fixture, [['B']])
    first, last = _by_name(predictions, starts), _by_name(predictions, late)
    assert first is not None and last is not None
    assert first['onset_alignment'] == 1.0
    assert last['onset_alignment'] == pytest.approx(1 / 3)
    # evidence_to_end: one match over the two symbols up to the end of present,
    # against one match over four.
    assert first['potential'] - last['potential'] == pytest.approx(
        W['evidence_to_end'] * (1 / 2 - 1 / 4), rel=1e-9)
    assert predictions.index(first) < predictions.index(last)


def test_single_event_potential_is_the_weighted_sum_of_its_terms(kato_fixture):
    """The lone `B` against [['B','k1'], ['k2'], ['k3']], in a node of two patterns.

    One match, `k1` missing from the matched event, nothing extra. `B` is held
    by both patterns (weight 1 in the cosine), `k1` by one (weight 2).
    """
    kato_fixture.clear_all_memory()
    starts = _learn(kato_fixture, [['B', 'k1'], ['k2'], ['k3']])
    _learn(kato_fixture, [['k4'], ['k5'], ['B', 'k6']])

    prediction = _by_name(_predict(kato_fixture, [['B']]), starts)
    assert prediction is not None
    expected = (
        W['snr']                                  # snr 1: no extras
        + W['inverse_fragmentation']              # one block
        + W['last_event_matched'] + W['last_event_share']
        + W['recency_07'] + W['recency_09']       # one matched symbol, in the newest event
        + W['tversky'] / 3                        # 1 / (1 + 2 x 1 missing)
        + W['cosine_idf_present'] / math.sqrt(5)  # STM {B}; present {B: 1, k1: 2}
        + W['evidence_to_end'] / 2                # 1 match of 2 symbols up to the end of present
    )                                             # frequency 1: log_frequency adds nothing
    assert prediction['potential'] == pytest.approx(expected, rel=1e-9)


def test_multi_symbol_single_event_uses_cohesion_and_onset(kato_fixture):
    kato_fixture.clear_all_memory()
    together = _learn(kato_fixture, [['A', 'B', 'C'], ['m']])
    split = _learn(kato_fixture, [['A'], ['C'], ['m']])

    predictions = _predict(kato_fixture, [['A', 'C']])
    p_together, p_split = _by_name(predictions, together), _by_name(predictions, split)
    assert p_together is not None and p_split is not None
    assert (p_together['event_cohesion'], p_together['onset_alignment']) == (1.0, 1.0)
    assert (p_split['event_cohesion'], p_split['onset_alignment']) == (0.5, 0.5)


def test_multi_event_stm_potential_is_the_weighted_sum_of_its_terms(kato_fixture):
    """[['A'], ['marker']] against [['A','B','C'], ['marker'], ['tail']], the node's only pattern.

    Two matches in two blocks, `B` and `C` missing, nothing extra. Every symbol
    is held by the one pattern, so each weighs 1 in the cosine. onset_alignment
    is reported and is not a term.
    """
    kato_fixture.clear_all_memory()
    name = _learn(kato_fixture, [['A', 'B', 'C'], ['marker'], ['tail']])

    prediction = _by_name(_predict(kato_fixture, [['A'], ['marker']]), name)
    assert prediction is not None
    assert prediction['onset_alignment'] > 0
    assert prediction['fragmentation'] == 1.0
    expected = (
        W['snr']                                  # snr 1: no extras
        + W['fragmentation']                      # one break between the two blocks
        + W['inverse_fragmentation'] / 2
        + W['last_event_matched'] + W['last_event_share']
        + 1.7 * W['recency_07']                   # `A` one event back (0.7), `marker` newest (1)
        + 1.9 * W['recency_09']
        + W['tversky'] / 3                        # 2 / (2 + 2 x 2 missing)
        + W['cosine_idf_present'] / math.sqrt(2)  # 2 / (sqrt 2 x sqrt 4)
        + W['evidence_to_end'] / 2                # 2 matches of 4 symbols up to the end of present
    )                                             # frequency 1: log_frequency adds nothing
    assert prediction['potential'] == pytest.approx(expected, rel=1e-9)
