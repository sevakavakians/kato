"""
The Bayesian fields and good-odds of a prediction, end to end.

    bayesian_prior        f / F: the pattern's share of every learn the node has seen
    bayesian_likelihood   Good's weight of evidence, in bits:
                          sum over matches of log2(0.95 / q(s)) - log2(20) x (missing + extras)
    good_odds             log2(bayesian_prior) + bayesian_likelihood
    bayesian_posterior    2^good_odds / (1 + sum of 2^good_odds over every candidate)
    chance_posterior      1 / (1 + the same sum), returned beside the predictions

q(s) is the symbol's share of all learned symbol occurrences. Each test learns
into a node of its own, so every count in the expected values below is exactly
what the test learned.
"""

import math
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from fixtures.kato_fixtures import kato_fixture as kato_fixture

CLOSE = {'rel': 1e-9, 'abs': 1e-12}


def _learn(fixture, symbols, times=1):
    """Learn one symbol per event, `times` times. Returns the pattern's bare name."""
    name = None
    for _ in range(times):
        fixture.clear_short_term_memory()
        for symbol in symbols:
            fixture.observe({'strings': [symbol], 'vectors': [], 'emotives': {}})
        name = fixture.learn()
    return name[5:] if name.startswith('PTRN|') else name


def _predict(fixture, symbols):
    """Observe one symbol per event and return the whole predictions response."""
    fixture.clear_short_term_memory()
    for symbol in symbols:
        fixture.observe({'strings': [symbol], 'vectors': [], 'emotives': {}})
    response = fixture.get_predictions_response()
    return {p['name']: p for p in response['predictions']}, response


def test_bayesian_fields_are_present_and_numeric(kato_fixture):
    kato_fixture.clear_all_memory()
    kato_fixture.set_recall_threshold(0.2)
    _learn(kato_fixture, ['a', 'b', 'c'])

    predictions, response = _predict(kato_fixture, ['a', 'b'])

    assert len(predictions) == 1
    for prediction in predictions.values():
        for field in ('bayesian_posterior', 'bayesian_prior', 'bayesian_likelihood', 'good_odds'):
            assert isinstance(prediction[field], float), f"{field} should be a float"
    assert isinstance(response['chance_posterior'], float)


def test_the_prior_is_the_share_of_every_learn_in_the_node(kato_fixture):
    """f / F, with F counting each learn: two of x y z, one of x y w, three of q r s."""
    kato_fixture.clear_all_memory()
    kato_fixture.set_recall_threshold(0.2)
    twice = _learn(kato_fixture, ['x', 'y', 'z'], times=2)
    once = _learn(kato_fixture, ['x', 'y', 'w'])
    _learn(kato_fixture, ['q', 'r', 's'], times=3)

    predictions, _ = _predict(kato_fixture, ['x', 'y'])

    assert set(predictions) == {twice, once}, "q r s shares nothing with the STM"
    assert predictions[twice]['frequency'] == 2
    assert predictions[twice]['bayesian_prior'] == pytest.approx(2 / 6, **CLOSE)
    assert predictions[once]['bayesian_prior'] == pytest.approx(1 / 6, **CLOSE)
    # The base rate does not depend on what was observed: the two candidates
    # hold half of the node's learns, so their priors add up to a half.
    assert sum(p['bayesian_prior'] for p in predictions.values()) == pytest.approx(0.5, **CLOSE)


def test_the_likelihood_is_the_weight_of_evidence_in_bits(kato_fixture):
    """Two matches, each on a symbol that is one of three learned occurrences."""
    kato_fixture.clear_all_memory()
    kato_fixture.set_recall_threshold(0.2)
    name = _learn(kato_fixture, ['p', 'q', 'r'])

    predictions, _ = _predict(kato_fixture, ['p', 'q'])

    assert predictions[name]['matches'] == ['p', 'q']
    assert predictions[name]['bayesian_likelihood'] == pytest.approx(2 * math.log2(0.95 * 3), **CLOSE)


def test_an_extra_symbol_costs_the_penalty(kato_fixture):
    """Observing p, then q with an unknown symbol beside it: one extra, log2(20) bits."""
    kato_fixture.clear_all_memory()
    kato_fixture.set_recall_threshold(0.2)
    name = _learn(kato_fixture, ['p', 'q', 'r'])

    kato_fixture.clear_short_term_memory()
    kato_fixture.observe({'strings': ['p'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['q', 'unknown'], 'vectors': [], 'emotives': {}})
    prediction = {p['name']: p for p in kato_fixture.get_predictions()}[name]

    assert prediction['extras'] == [[], ['unknown']]
    assert prediction['bayesian_likelihood'] == pytest.approx(
        2 * math.log2(0.95 * 3) - math.log2(20), **CLOSE)


def test_good_odds_is_the_log_prior_plus_the_likelihood(kato_fixture):
    kato_fixture.clear_all_memory()
    kato_fixture.set_recall_threshold(0.2)
    _learn(kato_fixture, ['alpha', 'beta', 'gamma'], times=3)
    _learn(kato_fixture, ['alpha', 'beta', 'delta'])

    predictions, _ = _predict(kato_fixture, ['alpha', 'beta'])

    assert len(predictions) == 2
    for prediction in predictions.values():
        assert prediction['good_odds'] == pytest.approx(
            math.log2(prediction['bayesian_prior']) + prediction['bayesian_likelihood'], **CLOSE)


def test_the_posterior_is_the_odds_over_one_plus_the_total_odds(kato_fixture):
    kato_fixture.clear_all_memory()
    kato_fixture.set_recall_threshold(0.2)
    for tail in ('c', 'd', 'e'):
        _learn(kato_fixture, ['a', 'b', tail])

    predictions, response = _predict(kato_fixture, ['a', 'b'])

    assert len(predictions) == 3
    total_odds = sum(2 ** p['good_odds'] for p in predictions.values())
    for prediction in predictions.values():
        assert prediction['bayesian_posterior'] == pytest.approx(
            2 ** prediction['good_odds'] / (1 + total_odds), **CLOSE)
    assert response['chance_posterior'] == pytest.approx(1 / (1 + total_odds), **CLOSE)


def test_the_posteriors_and_the_chance_posterior_add_up_to_one(kato_fixture):
    kato_fixture.clear_all_memory()
    kato_fixture.set_recall_threshold(0.2)
    for tail in ('c', 'd', 'e'):
        _learn(kato_fixture, ['a', 'b', tail])

    predictions, response = _predict(kato_fixture, ['a', 'b'])

    posteriors = [p['bayesian_posterior'] for p in predictions.values()]
    assert sum(posteriors) + response['chance_posterior'] == pytest.approx(1.0, **CLOSE)
    assert all(0.0 < posterior < 1.0 for posterior in posteriors)
    assert 0.0 < response['chance_posterior'] < 1.0


def test_equal_matches_are_told_apart_by_how_often_each_was_learned(kato_fixture):
    """m n o learned three times and m n p once match the STM alike: the odds are 3 to 1."""
    kato_fixture.clear_all_memory()
    kato_fixture.set_recall_threshold(0.1)
    often = _learn(kato_fixture, ['m', 'n', 'o'], times=3)
    seldom = _learn(kato_fixture, ['m', 'n', 'p'])

    predictions, _ = _predict(kato_fixture, ['m', 'n'])

    assert predictions[often]['bayesian_likelihood'] == pytest.approx(
        predictions[seldom]['bayesian_likelihood'], **CLOSE)
    assert predictions[often]['bayesian_posterior'] / predictions[seldom]['bayesian_posterior'] == pytest.approx(
        3.0, **CLOSE)


def test_a_better_match_outweighs_a_pattern_learned_more_often(kato_fixture):
    """a b c learned once explains `a b` far better than a x y learned three times.

    Twelve symbol occurrences are learned: a 4, b 1, c 1, x 3, y 3, and four
    patterns occurrences. a b c matches both symbols; a x y matches `a` and has
    `b` as an extra.
    """
    kato_fixture.clear_all_memory()
    kato_fixture.set_recall_threshold(0.1)
    exact = _learn(kato_fixture, ['a', 'b', 'c'])
    frequent = _learn(kato_fixture, ['a', 'x', 'y'], times=3)

    predictions, response = _predict(kato_fixture, ['a', 'b'])

    odds_exact = (1 / 4) * (0.95 * 12 / 4) * (0.95 * 12 / 1)
    odds_frequent = (3 / 4) * (0.95 * 12 / 4) / 20
    total = 1 + odds_exact + odds_frequent
    assert predictions[exact]['bayesian_posterior'] == pytest.approx(odds_exact / total, **CLOSE)
    assert predictions[frequent]['bayesian_posterior'] == pytest.approx(odds_frequent / total, **CLOSE)
    assert response['chance_posterior'] == pytest.approx(1 / total, **CLOSE)
    assert predictions[exact]['bayesian_posterior'] == pytest.approx(0.880, abs=5e-4)
    assert predictions[frequent]['bayesian_posterior'] == pytest.approx(0.012, abs=5e-4)
    assert response['chance_posterior'] == pytest.approx(0.108, abs=5e-4)


def test_a_lone_pattern_is_weighed_against_chance(kato_fixture):
    """The only candidate does not get a posterior of 1: chance is always the other hypothesis."""
    kato_fixture.clear_all_memory()
    kato_fixture.set_recall_threshold(0.2)
    name = _learn(kato_fixture, ['one', 'pattern', 'only'])

    predictions, response = _predict(kato_fixture, ['one', 'pattern'])

    assert list(predictions) == [name]
    odds = (0.95 * 3) ** 2                      # prior 1, two matches at q = 1/3
    assert predictions[name]['bayesian_prior'] == 1.0
    assert predictions[name]['bayesian_posterior'] == pytest.approx(odds / (1 + odds), **CLOSE)
    assert response['chance_posterior'] == pytest.approx(1 / (1 + odds), **CLOSE)


def test_no_prediction_leaves_everything_to_chance(kato_fixture):
    kato_fixture.clear_all_memory()
    kato_fixture.set_recall_threshold(0.2)
    _learn(kato_fixture, ['a', 'b', 'c'])

    predictions, response = _predict(kato_fixture, ['never', 'seen'])

    assert predictions == {}
    assert response['chance_posterior'] == 1.0
    assert response['future_potentials'] == []
    assert response['ends_here'] is None


def test_an_empty_stm_computes_no_posterior(kato_fixture):
    kato_fixture.clear_all_memory()
    _learn(kato_fixture, ['a', 'b', 'c'])
    kato_fixture.clear_short_term_memory()

    response = kato_fixture.get_predictions_response()

    assert response['predictions'] == []
    assert response['chance_posterior'] is None
    assert response['ends_here'] is None


@pytest.mark.parametrize('metric', ['bayesian_posterior', 'good_odds', 'bayesian_prior', 'bayesian_likelihood'])
def test_the_bayesian_fields_rank_predictions(kato_fixture, metric):
    kato_fixture.clear_all_memory()
    kato_fixture.set_recall_threshold(0.1)
    kato_fixture.update_config({'rank_sort_algo': metric})
    _learn(kato_fixture, ['rank', 'test', 'a'], times=2)
    _learn(kato_fixture, ['rank', 'test', 'b'])
    _learn(kato_fixture, ['rank', 'other', 'c'], times=3)

    kato_fixture.clear_short_term_memory()
    for symbol in ('rank', 'test'):
        kato_fixture.observe({'strings': [symbol], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()

    assert len(predictions) == 3
    values = [p[metric] for p in predictions]
    assert values == sorted(values, reverse=True), f"predictions should be ranked by {metric}, highest first"


def test_good_odds_and_the_posterior_rank_alike(kato_fixture):
    """The posterior is a rising function of good-odds, so the two orders are the same."""
    kato_fixture.clear_all_memory()
    kato_fixture.set_recall_threshold(0.1)
    _learn(kato_fixture, ['rank', 'test', 'a'], times=2)
    _learn(kato_fixture, ['rank', 'test', 'b'])
    _learn(kato_fixture, ['rank', 'other', 'c'], times=3)

    orders = {}
    for metric in ('good_odds', 'bayesian_posterior'):
        kato_fixture.update_config({'rank_sort_algo': metric})
        kato_fixture.clear_short_term_memory()
        for symbol in ('rank', 'test'):
            kato_fixture.observe({'strings': [symbol], 'vectors': [], 'emotives': {}})
        orders[metric] = [p['name'] for p in kato_fixture.get_predictions()]

    assert orders['good_odds'] == orders['bayesian_posterior']
