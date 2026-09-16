"""Ranking must not depend on the order predictions arrive in.

KATO guarantees that the same inputs produce the same outputs. Predictions
reach the ranking step in an unstable order: candidates come out of a `set`
(string hashing is randomised per process, so each uvicorn worker iterates them
differently) and batch results are gathered with `as_completed`. Ranking on the
configured metric alone therefore let arrival order settle ties -- `nlargest`
keeps the first of equal keys and `sorted` is stable -- so tied predictions came
back in a different order per request, and once `max_predictions` truncated the
list, as a different *set*.

Measured against the running service before the fix: 40 identical requests over
10 tied patterns with max_predictions=3 gave 7 distinct orderings and 5 distinct
sets.

These tests pin the invariant directly, which an end-to-end test cannot do
reliably -- the test fixture reuses one HTTP connection and so stays pinned to a
single uvicorn worker, where set iteration order happens to be stable.
"""

import random

import pytest

from kato.representations.prediction import rank_predictions


def _preds(scores):
    return [{'name': f'pattern{i:03d}', 'potential': s} for i, s in enumerate(scores)]


def test_all_ties_rank_identically_regardless_of_input_order():
    predictions = _preds([1.0] * 10)

    results = set()
    for _ in range(200):
        shuffled = predictions[:]
        random.shuffle(shuffled)
        results.add(tuple(p['name'] for p in rank_predictions(shuffled, 'potential', 3)))

    assert len(results) == 1, f"ranking depended on input order: {results}"


def test_partial_ties_rank_identically_regardless_of_input_order():
    """A realistic mix: a clear winner, a tied band, and some also-rans."""
    predictions = _preds([9.0, 5.0, 5.0, 5.0, 5.0, 1.0, 1.0])

    results = set()
    for _ in range(200):
        shuffled = predictions[:]
        random.shuffle(shuffled)
        results.add(tuple(p['name'] for p in rank_predictions(shuffled, 'potential', 4)))

    assert len(results) == 1, f"ranking depended on input order: {results}"
    best = next(iter(results))
    assert best[0] == 'pattern000', "the highest-scoring prediction must still rank first"


def test_ranking_is_descending_by_metric():
    predictions = _preds([0.1, 0.9, 0.5, 0.7])
    ranked = rank_predictions(predictions, 'potential', 4)
    assert [p['potential'] for p in ranked] == [0.9, 0.7, 0.5, 0.1]


def test_limit_is_honoured():
    predictions = _preds([float(i) for i in range(20)])
    assert len(rank_predictions(predictions, 'potential', 5)) == 5
    # A limit above the population returns everything, not padding.
    assert len(rank_predictions(predictions, 'potential', 50)) == 20


def test_empty_input_returns_empty():
    assert rank_predictions([], 'potential', 5) == []


def test_alternate_metric_is_used():
    predictions = [
        {'name': 'a', 'potential': 1.0, 'confidence': 0.1},
        {'name': 'b', 'potential': 0.1, 'confidence': 1.0},
    ]
    assert [p['name'] for p in rank_predictions(predictions, 'confidence', 2)] == ['b', 'a']


def test_missing_metric_raises_keyerror():
    """predictPattern relies on this to report an invalid rank_sort_algo."""
    with pytest.raises(KeyError):
        rank_predictions(_preds([1.0]), 'no_such_metric', 1)
