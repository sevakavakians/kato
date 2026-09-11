"""
Prediction segmentation over patterns whose events hold several symbols.

Two learned patterns drive these tests:

RAGGED — six events of varying width (3, 1, 2, 4, 1, 2 symbols):
    [['a','b','c'], ['d'], ['e','f'], ['g','h','i','j'], ['k'], ['l','m']]
REPEATS — symbols that recur across events:
    [['x','y'], ['y','z'], ['x'], ['w','y','z']]

Each test observes some shape — the full pattern, a slice (first half,
second half, middle, single event), a perturbed slice (symbols dropped,
symbols added, whole events added, events split, merged or reordered) — and
asserts the complete top prediction:

- `past`    pattern events before the first matched event
- `present` every pattern event from the first to the last matched event, whole
- `future`  pattern events after the last matched event
- `missing` one list per PRESENT event: its symbols that were not observed
- `extras`  one list per OBSERVED (STM) event: its symbols not expected there
- `anomalies` missing symbols, then extras, flat

Symbols are sorted within an event (token matching is on), so observations
are passed sorted and expectations are written sorted.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from fixtures.kato_fixtures import kato_fixture as kato_fixture  # noqa: F401

RAGGED = [['a', 'b', 'c'], ['d'], ['e', 'f'], ['g', 'h', 'i', 'j'], ['k'], ['l', 'm']]
REPEATS = [['x', 'y'], ['y', 'z'], ['x'], ['w', 'y', 'z']]

FIELDS = ('past', 'present', 'future', 'missing', 'extras', 'anomalies')


def _learn(fixture, pattern):
    fixture.clear_all_memory()
    fixture.clear_short_term_memory()
    for event in pattern:
        fixture.observe({'strings': sorted(event), 'vectors': [], 'emotives': {}})
    name = fixture.learn()
    assert name, "pattern should have been learned"
    return name


def _observe(fixture, events):
    fixture.clear_short_term_memory()
    for event in events:
        fixture.observe({'strings': sorted(event), 'vectors': [], 'emotives': {}})
    return fixture.get_predictions()


def _top(fixture, events):
    predictions = _observe(fixture, events)
    assert predictions, f"expected a prediction for {events}"
    return predictions[0]


def _assert_segmentation(pred, **expected):
    """Compare every segmentation field at once so a failure shows the whole picture."""
    actual = {k: pred.get(k) for k in FIELDS}
    assert actual == expected, "\n".join(
        f"  {k:10s} got {actual[k]!r}\n{'':13s}want {expected[k]!r}" for k in FIELDS if actual[k] != expected[k]
    )


def _no_gaps(n):
    return [[] for _ in range(n)]


# ---------------------------------------------------------------------------
# Slices of the ragged pattern: whole, halves, middle, single events
# ---------------------------------------------------------------------------

def test_full_pattern_observed(kato_fixture):
    _learn(kato_fixture, RAGGED)
    pred = _top(kato_fixture, RAGGED)
    _assert_segmentation(pred, past=[], present=RAGGED, future=[],
                         missing=_no_gaps(6), extras=_no_gaps(6), anomalies=[])
    assert pred['similarity'] == 1.0 and pred['confidence'] == 1.0


def test_first_half(kato_fixture):
    _learn(kato_fixture, RAGGED)
    _assert_segmentation(_top(kato_fixture, RAGGED[:3]),
                         past=[], present=RAGGED[:3], future=RAGGED[3:],
                         missing=_no_gaps(3), extras=_no_gaps(3), anomalies=[])


def test_second_half(kato_fixture):
    _learn(kato_fixture, RAGGED)
    _assert_segmentation(_top(kato_fixture, RAGGED[3:]),
                         past=RAGGED[:3], present=RAGGED[3:], future=[],
                         missing=_no_gaps(3), extras=_no_gaps(3), anomalies=[])


def test_middle_third(kato_fixture):
    _learn(kato_fixture, RAGGED)
    _assert_segmentation(_top(kato_fixture, RAGGED[2:4]),
                         past=RAGGED[:2], present=RAGGED[2:4], future=RAGGED[4:],
                         missing=_no_gaps(2), extras=_no_gaps(2), anomalies=[])


def test_single_wide_event(kato_fixture):
    """One four-symbol event pins present to exactly that event."""
    _learn(kato_fixture, RAGGED)
    pred = _top(kato_fixture, [RAGGED[3]])
    _assert_segmentation(pred, past=RAGGED[:3], present=[RAGGED[3]], future=RAGGED[4:],
                         missing=[[]], extras=[[]], anomalies=[])
    assert pred['confidence'] == 1.0


# ---------------------------------------------------------------------------
# Perturbed slices: symbols dropped, symbols added, both
# ---------------------------------------------------------------------------

def test_symbol_dropped_from_an_event(kato_fixture):
    """Observing ['a','c'] for the event ['a','b','c'] reports 'b' missing in that event."""
    _learn(kato_fixture, RAGGED)
    pred = _top(kato_fixture, [['a', 'c'], ['d']])
    _assert_segmentation(pred, past=[], present=RAGGED[:2], future=RAGGED[2:],
                         missing=[['b'], []], extras=[[], []], anomalies=['b'])
    assert pred['matches'] == ['a', 'c', 'd']


def test_symbol_added_to_an_event(kato_fixture):
    """An unexpected symbol inside an otherwise-complete event is an extra for that STM event."""
    _learn(kato_fixture, RAGGED)
    _assert_segmentation(_top(kato_fixture, [['a', 'b', 'c', 'z'], ['d']]),
                         past=[], present=RAGGED[:2], future=RAGGED[2:],
                         missing=[[], []], extras=[['z'], []], anomalies=['z'])


def test_missing_and_extra_symbols_across_events(kato_fixture):
    """Drops in two events plus an addition in another: missing aligns with present, extras with STM."""
    _learn(kato_fixture, RAGGED)
    pred = _top(kato_fixture, [['a', 'c'], ['d', 'q'], ['f']])
    _assert_segmentation(pred, past=[], present=RAGGED[:3], future=RAGGED[3:],
                         missing=[['b'], [], ['e']], extras=[[], ['q'], []],
                         anomalies=['b', 'e', 'q'])
    assert pred['matches'] == ['a', 'c', 'd', 'f']


def test_unexpected_whole_event_between_matches(kato_fixture):
    """An event the pattern doesn't have sits in extras at its STM position; present skips nothing."""
    _learn(kato_fixture, RAGGED)
    _assert_segmentation(_top(kato_fixture, [['d'], ['zz'], ['e', 'f']]),
                         past=[RAGGED[0]], present=RAGGED[1:3], future=RAGGED[3:],
                         missing=[[], []], extras=[[], ['zz'], []], anomalies=['zz'])


def test_first_and_last_events_only(kato_fixture):
    """Matching both ends spans present over the whole pattern; every event between is missing."""
    _learn(kato_fixture, RAGGED)
    pred = _top(kato_fixture, [RAGGED[0], RAGGED[5]])
    _assert_segmentation(pred, past=[], present=RAGGED, future=[],
                         missing=[[], ['d'], ['e', 'f'], ['g', 'h', 'i', 'j'], ['k'], []],
                         extras=[[], []],
                         anomalies=['d', 'e', 'f', 'g', 'h', 'i', 'j', 'k'])
    assert pred['matches'] == ['a', 'b', 'c', 'l', 'm']


def test_one_symbol_from_each_of_two_events(kato_fixture):
    """'h' then 'm': present spans events 3..5; the unobserved symbols of each are missing."""
    _learn(kato_fixture, RAGGED)
    _assert_segmentation(_top(kato_fixture, [['h'], ['m']]),
                         past=RAGGED[:3], present=RAGGED[3:], future=[],
                         missing=[['g', 'i', 'j'], ['k'], ['l']], extras=[[], []],
                         anomalies=['g', 'i', 'j', 'k', 'l'])


# ---------------------------------------------------------------------------
# Event-boundary mismatches: split, merged, reordered, duplicated
# ---------------------------------------------------------------------------

def test_event_split_across_two_observations(kato_fixture):
    """['a'] then ['b','c'] still fully matches the single event ['a','b','c'].

    missing aligns with the two present events; extras with the three STM events.
    """
    _learn(kato_fixture, RAGGED)
    pred = _top(kato_fixture, [['a'], ['b', 'c'], ['d']])
    _assert_segmentation(pred, past=[], present=RAGGED[:2], future=RAGGED[2:],
                         missing=[[], []], extras=[[], [], []], anomalies=[])
    assert pred['confidence'] == 1.0


def test_two_events_merged_into_one_observation(kato_fixture):
    """['d','e','f'] as one event matches the pattern's ['d'] and ['e','f']; extras has one STM slot."""
    _learn(kato_fixture, RAGGED)
    _assert_segmentation(_top(kato_fixture, [['d', 'e', 'f']]),
                         past=[RAGGED[0]], present=RAGGED[1:3], future=RAGGED[3:],
                         missing=[[], []], extras=[[]], anomalies=[])


def test_events_out_of_order(kato_fixture):
    """['e','f'] then ['d']: the later 'd' cannot match after 'e','f', so it is an extra."""
    _learn(kato_fixture, RAGGED)
    pred = _top(kato_fixture, [['e', 'f'], ['d']])
    _assert_segmentation(pred, past=RAGGED[:2], present=[RAGGED[2]], future=RAGGED[3:],
                         missing=[[]], extras=[[], ['d']], anomalies=['d'])
    assert pred['matches'] == ['e', 'f']


def test_duplicate_symbol_within_an_observed_event(kato_fixture):
    """A symbol given twice in one event matches once; the duplicate is an extra."""
    _learn(kato_fixture, RAGGED)
    _assert_segmentation(_top(kato_fixture, [['a', 'a', 'b', 'c'], ['d']]),
                         past=[], present=RAGGED[:2], future=RAGGED[2:],
                         missing=[[], []], extras=[['a'], []], anomalies=['a'])


def test_nothing_in_common_yields_no_prediction(kato_fixture):
    _learn(kato_fixture, RAGGED)
    assert _observe(kato_fixture, [['zz'], ['yy']]) == []


# ---------------------------------------------------------------------------
# Repeated symbols across events (multiset accounting)
# ---------------------------------------------------------------------------

def test_repeats_full_pattern(kato_fixture):
    _learn(kato_fixture, REPEATS)
    pred = _top(kato_fixture, REPEATS)
    _assert_segmentation(pred, past=[], present=REPEATS, future=[],
                         missing=_no_gaps(4), extras=_no_gaps(4), anomalies=[])
    assert pred['matches'] == ['x', 'y', 'y', 'z', 'x', 'w', 'y', 'z']


@pytest.mark.parametrize("dropped_from_event", [0, 1], ids=["drop-event0-y", "drop-event1-y"])
def test_repeated_symbol_dropped_once(kato_fixture, dropped_from_event):
    """Dropping one 'y' of three: exactly one 'y' is missing, attributed by the flat alignment.

    Matching runs on the flattened sequence, so dropping the 'y' of event 0 or
    of event 1 yields the same observed symbols (x y z x w y z) and the same
    prediction. The matcher keeps the longest contiguous run (y z x w y z ->
    pattern events 1..3), so the unmatched 'y' is always the earlier one - the
    one in event 0 - whichever event the observation actually omitted it from.
    Total accounting is exact either way: 7 matches, one missing 'y'.
    """
    _learn(kato_fixture, REPEATS)
    observed = [list(e) for e in REPEATS]
    observed[dropped_from_event].remove('y')
    pred = _top(kato_fixture, observed)
    _assert_segmentation(pred, past=[], present=REPEATS, future=[],
                         missing=[['y'], [], [], []], extras=_no_gaps(4), anomalies=['y'])
    assert pred['matches'] == ['x', 'y', 'z', 'x', 'w', 'y', 'z']


def test_repeated_symbol_dropped_from_last_event(kato_fixture):
    """Dropping the 'y' that has no equal-cost alternative is attributed exactly."""
    _learn(kato_fixture, REPEATS)
    pred = _top(kato_fixture, [['x', 'y'], ['y', 'z'], ['x'], ['w', 'z']])
    _assert_segmentation(pred, past=[], present=REPEATS, future=[],
                         missing=[[], [], [], ['y']], extras=_no_gaps(4), anomalies=['y'])
    assert pred['matches'] == ['x', 'y', 'y', 'z', 'x', 'w', 'z']


def test_repeats_middle_two_events(kato_fixture):
    """['y','z'] then ['x'] is exactly pattern events 1..2: nothing missing, no bleed into event 0.

    Event 0 also contains a 'y'; segmentation by matched position (not symbol
    identity) keeps it in past.
    """
    _learn(kato_fixture, REPEATS)
    pred = _top(kato_fixture, REPEATS[1:3])
    _assert_segmentation(pred, past=[REPEATS[0]], present=REPEATS[1:3], future=[REPEATS[3]],
                         missing=[[], []], extras=[[], []], anomalies=[])
    assert pred['confidence'] == 1.0


@pytest.mark.parametrize("index", [0, 3], ids=["first-event", "last-event"])
def test_repeats_single_full_event(kato_fixture, index):
    _learn(kato_fixture, REPEATS)
    pred = _top(kato_fixture, [REPEATS[index]])
    _assert_segmentation(pred, past=REPEATS[:index], present=[REPEATS[index]], future=REPEATS[index + 1:],
                         missing=[[]], extras=[[]], anomalies=[])


def test_repeated_symbol_observed_alone_three_times(kato_fixture):
    """Three lone 'y' events match the three 'y' occurrences; everything else is missing."""
    _learn(kato_fixture, REPEATS)
    pred = _top(kato_fixture, [['y'], ['y'], ['y']])
    _assert_segmentation(pred, past=[], present=REPEATS, future=[],
                         missing=[['x'], ['z'], ['x'], ['w', 'z']], extras=[[], [], []],
                         anomalies=['x', 'z', 'x', 'w', 'z'])


# ---------------------------------------------------------------------------
# Matches that begin or end inside an event
# ---------------------------------------------------------------------------

def test_match_starting_mid_event(kato_fixture):
    """['b','c'] then ['d']: present starts at the whole event ['a','b','c'], with 'a' missing."""
    _learn(kato_fixture, RAGGED)
    pred = _top(kato_fixture, [['b', 'c'], ['d']])
    _assert_segmentation(pred, past=[], present=RAGGED[:2], future=RAGGED[2:],
                         missing=[['a'], []], extras=[[], []], anomalies=['a'])
    assert pred['matches'] == ['b', 'c', 'd']


def test_match_ending_mid_event(kato_fixture):
    """['d'] then ['g','h']: present runs to the whole event ['g','h','i','j']; 'e','f','i','j' missing."""
    _learn(kato_fixture, RAGGED)
    pred = _top(kato_fixture, [['d'], ['g', 'h']])
    _assert_segmentation(pred, past=[RAGGED[0]], present=RAGGED[1:4], future=RAGGED[4:],
                         missing=[[], ['e', 'f'], ['i', 'j']], extras=[[], []],
                         anomalies=['e', 'f', 'i', 'j'])


# ---------------------------------------------------------------------------
# Single-symbol observations (fast path)
# ---------------------------------------------------------------------------

def test_single_symbol_that_starts_the_pattern(kato_fixture):
    """A lone first symbol predicts the pattern: present is its whole first event, rest missing."""
    _learn(kato_fixture, RAGGED)
    pred = _top(kato_fixture, [['a']])
    _assert_segmentation(pred, past=[], present=[RAGGED[0]], future=RAGGED[1:],
                         missing=[['b', 'c']], extras=[[]], anomalies=['b', 'c'])
    assert pred['matches'] == ['a']


def test_single_symbol_that_starts_the_pattern_with_repeats(kato_fixture):
    _learn(kato_fixture, REPEATS)
    _assert_segmentation(_top(kato_fixture, [['x']]),
                         past=[], present=[REPEATS[0]], future=REPEATS[1:],
                         missing=[['y']], extras=[[]], anomalies=['y'])


@pytest.mark.parametrize("symbol", ['d', 'g', 'k', 'm'])
def test_single_symbol_from_mid_pattern_is_not_predicted(kato_fixture, symbol):
    """The single-symbol fast path only considers patterns whose FIRST token is the symbol.

    So a lone symbol from anywhere else in the pattern yields no prediction, even
    though the same symbol as part of a two-symbol observation would. This pins
    the fast path's documented first-token filter (PatternProcessor.
    _predict_single_symbol_fast); change this test if that semantic changes.
    """
    _learn(kato_fixture, RAGGED)
    assert _observe(kato_fixture, [[symbol]]) == []


# ---------------------------------------------------------------------------
# Two similar patterns: ranking and per-pattern segmentation
# ---------------------------------------------------------------------------

VARIANT = [['a', 'b', 'c'], ['d'], ['e', 'f'], ['g', 'h', 'i', 'j'], ['k'], ['l', 'n']]


def _learn_both(fixture):
    _learn(fixture, RAGGED)
    fixture.clear_short_term_memory()
    for event in VARIANT:
        fixture.observe({'strings': sorted(event), 'vectors': [], 'emotives': {}})
    assert fixture.learn()


def test_exact_match_outranks_near_twin(kato_fixture):
    """With RAGGED and a one-symbol variant learned, observing RAGGED ranks it first, complete."""
    _learn_both(kato_fixture)
    predictions = _observe(kato_fixture, RAGGED)
    assert len(predictions) == 2
    exact, twin = predictions
    _assert_segmentation(exact, past=[], present=RAGGED, future=[],
                         missing=_no_gaps(6), extras=_no_gaps(6), anomalies=[])
    assert exact['similarity'] == 1.0
    _assert_segmentation(twin, past=[], present=VARIANT, future=[],
                         missing=[[], [], [], [], [], ['n']], extras=[[], [], [], [], [], ['m']],
                         anomalies=['n', 'm'])
    assert twin['similarity'] < 1.0


def test_shared_prefix_predicts_both_futures(kato_fixture):
    """A prefix common to both patterns yields one prediction per pattern, differing only in future."""
    _learn_both(kato_fixture)
    predictions = _observe(kato_fixture, RAGGED[:2])
    assert len(predictions) == 2
    futures = sorted(p['future'][-1] for p in predictions)
    assert futures == [['l', 'm'], ['l', 'n']]
    for pred in predictions:
        _assert_segmentation(pred, past=[], present=RAGGED[:2], future=pred['future'],
                             missing=[[], []], extras=[[], []], anomalies=[])
        assert pred['confidence'] == 1.0
