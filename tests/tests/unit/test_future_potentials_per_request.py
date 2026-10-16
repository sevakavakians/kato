"""
A request's future_potentials come back with its own predictions.

future_potentials aggregates the futures of a request's scored candidates. It
used to be kept on the PatternProcessor, which every session on a node shares,
and the predictions endpoint read it back off the processor after predicting. A
request that computed none -- an empty STM returns before predicting -- then
served the previous request's value, which could be another session's: one
session's learned futures appeared in a different session's response.

predictPattern now returns a PredictionResult carrying both lists, and the
endpoint builds its response from that. Ties on aggregate_potential are settled
by the future's hash, so the order no longer follows database arrival order.
"""

import os
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from fixtures.kato_fixtures import kato_fixture as kato_fixture

from kato.informatics.predictive_information import calculate_ensemble_predictive_information
from kato.workers.pattern_processor import PatternProcessor, PredictionResult

# ── in-process ─────────────────────────────────────────────────────────

def test_the_processor_keeps_no_future_potentials():
    """Nothing about a request's ensemble is left where another can read it."""
    assert not hasattr(PatternProcessor, 'future_potentials')


@pytest.mark.asyncio
async def test_an_empty_stm_returns_empty_lists_without_predicting():
    processor = object.__new__(PatternProcessor)
    assert await processor.get_predictions_async([], None) == PredictionResult([], [])
    assert await processor.get_predictions_async([[]], None) == PredictionResult([], [])


@pytest.mark.asyncio
async def test_the_result_is_returned_as_predicted(monkeypatch):
    processor = object.__new__(PatternProcessor)
    expected = PredictionResult([{'name': 'p'}], [{'future': [['f']]}])

    async def fake_predict(state, stm_events, config):
        return expected

    monkeypatch.setattr(processor, '_predict_with_config', fake_predict)
    assert await processor.get_predictions_async([['a']], None) is expected


def test_the_sync_wrapper_still_returns_only_the_predictions(monkeypatch):
    processor = object.__new__(PatternProcessor)

    async def fake_async(stm, config=None):
        return PredictionResult([{'name': 'p'}], [{'future': [['f']]}])

    monkeypatch.setattr(processor, 'get_predictions_async', fake_async)
    assert processor.get_predictions([['a']]) == [{'name': 'p'}]


def _tied_predictions():
    """Two patterns of equal weight with different futures."""
    return [
        {'name': name, 'frequency': 1, 'similarity': 1.0, 'future': future}
        for name, future in (('p1', [['zeta']]), ('p2', [['alpha']]))
    ]


def test_tied_futures_come_out_in_one_order_whatever_the_arrival_order():
    forward = _tied_predictions()
    _, forward_potentials = calculate_ensemble_predictive_information(forward)
    _, reverse_potentials = calculate_ensemble_predictive_information(
        list(reversed(_tied_predictions())))

    assert forward_potentials[0]['aggregate_potential'] == forward_potentials[1]['aggregate_potential']
    assert [fp['future'] for fp in forward_potentials] == [fp['future'] for fp in reverse_potentials]


def test_a_higher_potential_still_ranks_first():
    predictions = _tied_predictions()
    predictions[1]['frequency'] = 3
    _, potentials = calculate_ensemble_predictive_information(predictions)
    assert [fp['future'] for fp in potentials] == [[['alpha']], [['zeta']]]


# ── end to end ─────────────────────────────────────────────────────────

X = [['fp_x1'], ['fp_x2'], ['fp_x3']]
Y = [['fp_y1'], ['fp_y2'], ['fp_y3']]


def _learn(fixture, events):
    fixture.clear_short_term_memory()
    for event in events:
        fixture.observe({'strings': event, 'vectors': [], 'emotives': {}})
    fixture.learn()


class _Session:
    """A session on the fixture's node, read through the raw endpoint."""

    def __init__(self, fixture):
        self.fixture = fixture
        response = fixture.requests_session.post(
            f"{fixture.base_url}/sessions", json={'node_id': fixture.processor_id})
        response.raise_for_status()
        self.url = f"{fixture.base_url}/sessions/{response.json()['session_id']}"

    def observe(self, events):
        self.fixture.requests_session.post(f"{self.url}/clear-stm").raise_for_status()
        for event in events:
            self.fixture.requests_session.post(
                f"{self.url}/observe",
                json={'strings': event, 'vectors': [], 'emotives': {}},
            ).raise_for_status()

    def predictions(self):
        response = self.fixture.requests_session.get(f"{self.url}/predictions")
        response.raise_for_status()
        return response.json()

    def close(self):
        self.fixture.requests_session.delete(self.url)


@pytest.fixture
def two_sessions(kato_fixture):
    kato_fixture.clear_all_memory()
    _learn(kato_fixture, X)
    _learn(kato_fixture, Y)
    first, second = _Session(kato_fixture), _Session(kato_fixture)
    try:
        yield first, second
    finally:
        first.close()
        second.close()


def test_an_empty_stm_does_not_receive_another_sessions_future_potentials(two_sessions):
    first, second = two_sessions
    first.observe(X[:2])
    for _ in range(10):
        assert first.predictions()['future_potentials']
        response = second.predictions()
        assert response['count'] == 0
        assert response['future_potentials'] == []


def test_concurrent_sessions_get_the_future_potentials_of_their_own_predictions(two_sessions):
    first, second = two_sessions
    first.observe(X[:2])
    second.observe(Y[:2])

    with ThreadPoolExecutor(max_workers=8) as pool:
        jobs = [(expected, pool.submit(session.predictions))
                for _ in range(20) for session, expected in ((first, X[2:]), (second, Y[2:]))]
        for expected, job in jobs:
            response = job.result()
            assert [p['future'] for p in response['predictions']] == [expected]
            assert [fp['future'] for fp in response['future_potentials']] == [expected]
