"""
End-to-end tests for `potential`, `future_potentials` and `predictive_information`.

    potential                the weighted sum of eleven terms (POTENTIAL_WEIGHTS)
    future_potentials        P(E | STM) = sum of e^potential over the predictions whose
                             next event is E / the same sum over every prediction
    ends_here                the share of that sum held by predictions with no future
    predictive_information   share x log2(P(E | STM) / q(E)), in bits; share is the
                             prediction's own part of P(E | STM), q(E) the product of q(s)
                             over the next event's symbols

Each test learns into a node of its own, so every count in the expected values is
exactly what the test learned.
"""

import math

import pytest

from kato.informatics.prediction_metrics import POTENTIAL_WEIGHTS as W

CLOSE = {'rel': 1e-9, 'abs': 1e-12}


def _learn(fixture, events, times=1):
    name = None
    for _ in range(times):
        fixture.clear_stm()
        for event in events:
            fixture.observe({"strings": event, "vectors": [], "emotives": {}})
        name = fixture.learn()
    return name[5:] if name.startswith('PTRN|') else name


def _predict(fixture, events):
    fixture.clear_stm()
    for event in events:
        fixture.observe({"strings": event, "vectors": [], "emotives": {}})
    response = fixture.get_predictions_response()
    return {p['name']: p for p in response['predictions']}, response


class TestPredictiveInformationE2E:
    """End-to-end tests for predictive information in predictions."""

    def test_a_certain_next_event_carries_its_whole_surprise(self, kato_fixture):
        """One pattern, one future: P(E | STM) is 1, so the information is log2(1 / q(E)).

        The node holds four symbol occurrences, one each, and the next event is
        [C, D]: q(E) = 1/4 x 1/4, which is 4 bits.
        """
        name = _learn(kato_fixture, [["A", "B"], ["C", "D"]])

        predictions, response = _predict(kato_fixture, [["A", "B"]])

        assert list(predictions) == [name]
        assert predictions[name]['future'] == [["C", "D"]]
        assert predictions[name]['predictive_information'] == pytest.approx(4.0, **CLOSE)
        assert response['future_potentials'] == [
            {'next_event': ["C", "D"], 'probability': 1.0, 'supporting_patterns': 1}]
        assert response['ends_here'] == 0.0

    def test_a_prediction_with_no_future_carries_no_information(self, kato_fixture):
        name = _learn(kato_fixture, [["A"], ["B"]])

        predictions, response = _predict(kato_fixture, [["A"], ["B"]])

        assert predictions[name]['future'] == []
        assert predictions[name]['predictive_information'] == 0.0
        assert response['future_potentials'] == []
        assert response['ends_here'] == 1.0

    def test_a_pattern_that_has_ended_keeps_a_weak_candidate_from_the_whole_probability(self, kato_fixture):
        """a b c and a b d, learned once each; a, b, c is observed.

        a b c matches in full and has ended. a b d matches two of three symbols
        and proposes d. The candidates share the probability by e^potential, so
        d gets what a b d holds of the two, and the rest says nothing follows.
        """
        ended = _learn(kato_fixture, [["a"], ["b"], ["c"]])
        goes_on = _learn(kato_fixture, [["a"], ["b"], ["d"]])

        predictions, response = _predict(kato_fixture, [["a"], ["b"], ["c"]])

        assert set(predictions) == {ended, goes_on}
        assert predictions[ended]['future'] == [] and predictions[goes_on]['future'] == [["d"]]
        ratio = math.exp(predictions[goes_on]['potential'] - predictions[ended]['potential'])
        assert response['future_potentials'] == [
            {'next_event': ["d"], 'probability': pytest.approx(ratio / (1 + ratio), rel=1e-9),
             'supporting_patterns': 1}]
        assert response['ends_here'] == pytest.approx(1 / (1 + ratio), rel=1e-9)
        assert response['future_potentials'][0]['probability'] < 0.001
        assert response['ends_here'] > 0.999
        assert predictions[ended]['predictive_information'] == 0.0

    def test_potential_is_the_weighted_sum_of_its_terms(self, kato_fixture):
        """[X, Y] in one event against [[X, Y, Z], [V, W]], the node's only pattern.

        Two matches in one block, Z missing from the matched event, nothing
        extra. Every symbol is held by the one pattern, so each weighs 1 in the
        cosine.
        """
        name = _learn(kato_fixture, [["X", "Y", "Z"], ["W", "V"]])

        predictions, _ = _predict(kato_fixture, [["X", "Y"]])

        prediction = predictions[name]
        assert prediction['matches'] == ["X", "Y"]
        assert prediction['missing'] == [["Z"]]
        expected = (
            W['snr']                                      # snr 1: no extras
            + W['inverse_fragmentation']                  # one block
            + W['last_event_matched'] + W['last_event_share']
            + 2 * W['recency_07'] + 2 * W['recency_09']   # two matched symbols, both in the newest event
            + W['tversky'] / 2                            # 2 / (2 + 2 x 1 missing)
            + W['cosine_idf_present'] * 2 / math.sqrt(6)  # dot 2, norms sqrt 2 and sqrt 3
            + W['evidence_to_end'] * 2 / 3                # 2 matches of 3 symbols up to the end of present
        )                                                 # frequency 1: log_frequency adds nothing
        assert prediction['potential'] == pytest.approx(expected, **CLOSE)

    def test_learning_a_pattern_again_raises_its_potential_by_log_frequency(self, kato_fixture):
        events = [["START"], ["MIDDLE"], ["END"]]
        name = _learn(kato_fixture, events)
        once, _ = _predict(kato_fixture, [["START"], ["MIDDLE"]])

        _learn(kato_fixture, events, times=2)
        thrice, _ = _predict(kato_fixture, [["START"], ["MIDDLE"]])

        assert thrice[name]['frequency'] == 3
        assert thrice[name]['potential'] - once[name]['potential'] == pytest.approx(
            W['log_frequency'] * math.log(3), rel=1e-9)

    def test_patterns_that_match_alike_share_the_next_event_by_frequency(self, kato_fixture):
        """A1 B1 learned five times and X9 Y9 once; one event [A1, X9] is observed.

        Each pattern matches one symbol and has the other as an extra, so their
        potentials differ by log_frequency alone and e^potential is in the ratio
        5^weight to 1. Twelve symbol occurrences are learned: B1 five times, Y9
        once.
        """
        often = _learn(kato_fixture, [["A1"], ["B1"]], times=5)
        seldom = _learn(kato_fixture, [["X9"], ["Y9"]])

        predictions, response = _predict(kato_fixture, [["A1", "X9"]])

        assert set(predictions) == {often, seldom}
        weight = 5 ** W['log_frequency']
        p_b1, p_y9 = weight / (weight + 1), 1 / (weight + 1)
        assert response['future_potentials'] == [
            {'next_event': ["B1"], 'probability': pytest.approx(p_b1, **CLOSE), 'supporting_patterns': 1},
            {'next_event': ["Y9"], 'probability': pytest.approx(p_y9, **CLOSE), 'supporting_patterns': 1},
        ]
        assert predictions[often]['predictive_information'] == pytest.approx(
            p_b1 * math.log2(p_b1 / (5 / 12)), **CLOSE)
        assert predictions[seldom]['predictive_information'] == pytest.approx(
            p_y9 * math.log2(p_y9 / (1 / 12)), **CLOSE)

    def test_predictive_information_adds_up_over_the_predictions(self, kato_fixture):
        """The values add up to the divergence of the next-event probabilities from chance."""
        _learn(kato_fixture, [["a"], ["b"], ["c"]], times=2)
        _learn(kato_fixture, [["a"], ["b"], ["d"]])
        _learn(kato_fixture, [["a"], ["b"], ["c"], ["e"]])

        predictions, response = _predict(kato_fixture, [["a"], ["b"]])

        assert len(predictions) == 3
        # 13 symbol occurrences: c is 3 of them (twice in one pattern's learns, once in another), d is 1.
        chance = {'c': 3 / 13, 'd': 1 / 13}
        divergence = sum(
            entry['probability'] * math.log2(entry['probability'] / chance[entry['next_event'][0]])
            for entry in response['future_potentials']
        )
        assert sum(p['predictive_information'] for p in predictions.values()) == pytest.approx(divergence, **CLOSE)
        assert [entry['next_event'] for entry in response['future_potentials']] == [["c"], ["d"]]
        assert response['future_potentials'][0]['supporting_patterns'] == 2
        assert response['ends_here'] == 0.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
