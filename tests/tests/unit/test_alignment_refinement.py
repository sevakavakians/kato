"""
Pure-function tests for refine_alignment_by_events / segment_by_alignment.

The matcher aligns flattened sequences; these tests feed difflib's own
alignment (exactly as kato/searches/pattern_search.py derives it) through the
refinement and check the event-aware attribution, plus the invariants the
refinement must never break: same number of matches, same symbols, strictly
increasing positions, and idempotence.
"""

import difflib
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))

from kato.representations.prediction import refine_alignment_by_events, segment_by_alignment  # noqa: E402

REPEATS = [['x', 'y'], ['y', 'z'], ['x'], ['w', 'y', 'z']]
RAGGED = [['a', 'b', 'c'], ['d'], ['e', 'f'], ['g', 'h', 'i', 'j'], ['k'], ['l', 'm']]


def flat(events):
    return [s for e in events for s in e]


def difflib_alignment(pattern, stm):
    """Matched flat positions the way extract_prediction_info builds them."""
    m = difflib.SequenceMatcher(None, flat(pattern), flat(stm))
    pp, sp = [], []
    for i, j, n in m.get_matching_blocks()[:-1]:
        pp.extend(range(i, i + n))
        sp.extend(range(j, j + n))
    return pp, sp


def segment(pattern, stm):
    pp, sp = difflib_alignment(pattern, stm)
    return segment_by_alignment(pattern, stm, pp, sp)


def assert_valid_refinement(pattern, stm, before, after):
    (pb, sb), (pa, sa) = before, after
    assert len(pa) == len(pb) == len(sa) == len(sb), "match count must not change"
    assert [flat(pattern)[q] for q in pa] == [flat(pattern)[q] for q in pb], "matched symbols must not change"
    assert [flat(stm)[j] for j in sa] == [flat(stm)[j] for j in sb]
    assert all(x < y for x, y in zip(pa, pa[1:])) and all(x < y for x, y in zip(sa, sa[1:])), "must stay monotone"
    assert len(set(pa)) == len(pa) and len(set(sa)) == len(sa)


@pytest.mark.parametrize("stm,expected_missing", [
    ([['x', 'y'], ['z'], ['x'], ['w', 'y', 'z']], [[], ['y'], [], []]),   # 'y' of event 1 omitted
    ([['x'], ['y', 'z'], ['x'], ['w', 'y', 'z']], [['y'], [], [], []]),   # 'y' of event 0 omitted
    ([['x', 'y'], ['y', 'z'], ['x'], ['w', 'z']], [[], [], [], ['y']]),   # 'y' of event 3 omitted
], ids=["drop-event1", "drop-event0", "drop-event3"])
def test_dropped_repeated_symbol_is_attributed_to_its_event(stm, expected_missing):
    past, present, future, missing, extras = segment(REPEATS, stm)
    assert (past, present, future) == ([], REPEATS, [])
    assert missing == expected_missing
    assert extras == [[], [], [], []]


def test_lone_symbol_prefers_the_exact_event():
    """['x'] alone matches pattern event ['x'] exactly, not the 'x' of ['x','y']."""
    past, present, future, missing, extras = segment(REPEATS, [['x']])
    assert past == REPEATS[:2] and present == [['x']] and future == [REPEATS[3]]
    assert missing == [[]] and extras == [[]]


def test_lone_symbol_tightness_general():
    pattern = [['a', 'b', 'c', 'd'], ['b']]
    past, present, future, missing, extras = segment(pattern, [['b']])
    assert present == [['b']] and past == [['a', 'b', 'c', 'd']] and missing == [[]]


def test_repeated_observed_symbol_extra_attributed_to_its_event():
    """Observed-side mirror: the extra 'b' belongs to the observed event whose mates didn't match."""
    pattern = [['a'], ['b', 'c']]
    past, present, future, missing, extras = segment(pattern, [['a', 'b'], ['b', 'c']])
    assert present == pattern and missing == [[], []]
    assert extras == [['b'], []]


@pytest.mark.parametrize("stm,present,missing,extras", [
    ([['y', 'z'], ['x']], REPEATS[1:3], [[], []], [[], []]),
    ([['y'], ['y'], ['y']], REPEATS, [['x'], ['z'], ['x'], ['w', 'z']], [[], [], []]),
    ([['x', 'y']], [REPEATS[0]], [[]], [[]]),
    ([['w', 'y', 'z']], [REPEATS[3]], [[]], [[]]),
], ids=["middle-two", "lone-y-x3", "first-event", "last-event"])
def test_repeats_shapes_unchanged_by_refinement(stm, present, missing, extras):
    got = segment(REPEATS, stm)
    assert (got[1], got[3], got[4]) == (present, missing, extras)


@pytest.mark.parametrize("stm,present,missing,extras", [
    ([['a'], ['b', 'c'], ['d']], RAGGED[:2], [[], []], [[], [], []]),          # split event
    ([['d', 'e', 'f']], RAGGED[1:3], [[], []], [[]]),                          # merged events
    ([['a', 'a', 'b', 'c'], ['d']], RAGGED[:2], [[], []], [['a'], []]),        # duplicate in event
    ([['e', 'f'], ['d']], [RAGGED[2]], [[]], [[], ['d']]),                     # out of order
    ([['b', 'c'], ['d']], RAGGED[:2], [['a'], []], [[], []]),                  # mid-event start
], ids=["split", "merged", "duplicate", "out-of-order", "mid-event-start"])
def test_ragged_shapes_unchanged_by_refinement(stm, present, missing, extras):
    got = segment(RAGGED, stm)
    assert (got[1], got[3], got[4]) == (present, missing, extras)


@pytest.mark.parametrize("pattern,stm", [
    (REPEATS, [['x', 'y'], ['z'], ['x'], ['w', 'y', 'z']]),
    (REPEATS, [['x']]),
    (REPEATS, [['y'], ['y'], ['y']]),
    (RAGGED, [['a'], ['b', 'c'], ['d']]),
    ([['a'], ['b', 'c']], [['a', 'b'], ['b', 'c']]),
    ([['a', 'b', 'c', 'd'], ['b']], [['b']]),
])
def test_refinement_invariants_and_idempotence(pattern, stm):
    before = difflib_alignment(pattern, stm)
    once = refine_alignment_by_events(pattern, stm, *before)
    assert_valid_refinement(pattern, stm, before, once)
    twice = refine_alignment_by_events(pattern, stm, *once)
    assert tuple(map(list, twice)) == tuple(map(list, once)), "refinement must be idempotent"


def test_short_circuit_when_no_symbol_repeats():
    before = difflib_alignment(RAGGED, [['a', 'c'], ['d', 'q'], ['f']])
    after = refine_alignment_by_events(RAGGED, [['a', 'c'], ['d', 'q'], ['f']], *before)
    assert tuple(map(list, after)) == tuple(map(list, before))


def test_empty_alignment_passes_through():
    assert refine_alignment_by_events(RAGGED, [['zz']], [], []) == ([], [])
