"""
predictPattern scores every candidate, then ranks, then cuts.

The posterior, `future_potentials` and `predictive_information` are sums over
every candidate above the recall threshold, and `potential` and the prior need
each pattern's frequency. If the candidates were cut before they were scored,
every one of those values would depend on the cut -- on `max_predictions`, and on
whatever provisional score chose the survivors -- and a session ranking by
`frequency` would get the most frequent of a pre-selected few, not of the
candidates.

These tests drive the real predictPattern in process. Storage is replaced by
dictionaries; the candidates are built by KATO's own extraction
(InformationExtractor and Prediction), exactly as the searcher builds them, so
every match field is the real one. The end-to-end tests cover the same path
through the API.
"""

import asyncio
import math
import os
import sys
from collections import Counter
from itertools import chain
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from kato.config.session_config import VALID_RANK_SORT_ALGORITHMS
from kato.informatics.prediction_metrics import POTENTIAL_WEIGHTS
from kato.representations.prediction import Prediction
from kato.searches.pattern_search import InformationExtractor
from kato.workers import pattern_processor as pattern_processor_module
from kato.workers.pattern_processor import PATTERN_METRICS, PatternProcessor, PredictionSettings

EXACT = {'rel': 1e-12, 'abs': 1e-12}


class Node:
    """Patterns, frequencies and the counters a learn would have written."""

    def __init__(self, learned, *, pattern_total=None, arrival=sorted, recall_threshold=0.1):
        self.patterns = {name: [sorted(event) for event in events] for name, events, _ in learned}
        self.frequency = {name: times for name, _, times in learned}
        self.arrival = arrival
        self.recall_threshold = recall_threshold
        self.frequency_reads = []
        self.metadata_reads = []
        self.affinity_weights = None

        occurrences, holding = Counter(), Counter()
        for name, events in self.patterns.items():
            symbols = list(chain(*events))
            for symbol in symbols:
                occurrences[symbol] += self.frequency[name]
            for symbol in set(symbols):
                holding[symbol] += 1
        self.symbol_table = {
            symbol: {'name': symbol, 'frequency': occurrences[symbol], 'pattern_member_frequency': holding[symbol]}
            for symbol in occurrences
        }
        self.totals = {
            'total_symbols_in_patterns_frequencies': sum(occurrences.values()),
            'total_pattern_frequencies': (
                sum(self.frequency.values()) if pattern_total is None else pattern_total),
            'total_unique_patterns': len(self.patterns),
            'stats_version': 1,
        }

    # -- the searcher's part ---------------------------------------------
    async def causalBeliefAsync(self, state, target_class_candidates, stm_events, max_workers, batch_size):
        extractor = InformationExtractor(use_fast_matcher=True, use_token_matching=True)
        candidates = []
        for name in self.arrival(self.patterns):
            events = self.patterns[name]
            info = extractor.extract_prediction_info(list(chain(*events)), state, cutoff=self.recall_threshold)
            if not info:
                continue
            (_pattern, matches, past, present, missing, extras, similarity, blocks,
             anomalies, weighted_similarity, alignment) = info[:11]
            candidates.append(Prediction(
                {'name': name, 'pattern_data': events, 'length': sum(map(len, events)),
                 'frequency': 1, 'emotives': {}},
                matches, past, present, missing, extras, similarity, blocks,
                fuzzy_matches=anomalies, stm_events=stm_events,
                weighted_similarity=weighted_similarity, alignment=alignment,
            ))
        return candidates

    def attach_pattern_metadata(self, predictions):
        self.metadata_reads.append([prediction['name'] for prediction in predictions])
        return {}

    # -- the Redis writer's part -----------------------------------------
    def get_frequency_batch(self, names):
        self.frequency_reads.append(list(names))
        return {name: self.frequency.get(name, 0) for name in names}

    def processor(self):
        processor = object.__new__(PatternProcessor)
        processor.name = processor.kb_id = 'scoring_order_test_kato'
        processor.target_class_candidates = None
        processor.superkb = SimpleNamespace(
            symbols_kb=None,
            clickhouse_writer=SimpleNamespace(ensure_visible=lambda version: None),
            redis_writer=SimpleNamespace(
                get_global_metadata=lambda: self.totals,
                get_retired_pattern_ids=lambda names: set(),
                get_frequency_batch=self.get_frequency_batch,
            ),
        )
        processor.query_manager = SimpleNamespace(
            get_all_symbols_optimized=lambda collection, stats_version=None: self.symbol_table)
        processor._compute_affinity_weights = lambda *args, **kwargs: None
        return processor

    def predict(self, stm, rank_sort_algo='potential', max_predictions=100):
        stm = [sorted(event) for event in stm]
        settings = PredictionSettings(self, max_predictions, rank_sort_algo, True)
        return asyncio.run(self.processor().predictPattern(
            list(chain(*stm)), stm_events=stm, settings=settings))


def seq(text):
    """'a b c' -> [['a'], ['b'], ['c']]; 'a,b c' -> [['a', 'b'], ['c']]."""
    return [event.split(',') for event in text.split()]


# Six patterns that all match the STM `a b`, with different frequencies, lengths
# and futures, plus one that does not match at all.
LEARNED = [
    ('p_abc', seq('a b c'), 1),
    ('p_abd', seq('a b d'), 4),
    ('p_abce', seq('a b c e'), 2),
    ('p_xab', seq('x a b'), 9),
    ('p_amb', seq('a m b d'), 3),
    ('p_ab', seq('a b'), 1),
    ('p_qrs', seq('q r s'), 20),
]
STM = seq('a b')
CANDIDATES = 6
VALUE_FIELDS = (
    'frequency', 'potential', 'good_odds', 'bayesian_prior', 'bayesian_likelihood',
    'bayesian_posterior', 'predictive_information', 'confluence', 'itfdf_similarity',
    'tfidf_score', 'entropy', 'normalized_entropy', 'global_normalized_entropy',
)


def _values(result):
    return {p['name']: tuple(p[field] for field in VALUE_FIELDS) for p in result.predictions}


# ── every candidate is scored ──────────────────────────────────────────

def test_frequency_is_read_for_every_candidate_and_metadata_for_what_is_returned():
    node = Node(LEARNED)
    result = node.predict(STM, max_predictions=2)

    assert len(result.predictions) == 2
    assert sorted(chain(*node.frequency_reads)) == sorted(
        name for name, _, _ in LEARNED if name != 'p_qrs')
    assert node.metadata_reads == [[p['name'] for p in result.predictions]]


def test_returned_values_do_not_depend_on_max_predictions():
    everything = Node(LEARNED).predict(STM)
    assert len(everything.predictions) == CANDIDATES
    full = _values(everything)

    for limit in (1, 2, 3, 5):
        cut = Node(LEARNED).predict(STM, max_predictions=limit)
        assert [p['name'] for p in cut.predictions] == [p['name'] for p in everything.predictions[:limit]]
        for name, values in _values(cut).items():
            assert values == full[name]
        assert cut.future_potentials == everything.future_potentials
        assert cut.chance_posterior == everything.chance_posterior
        assert cut.ends_here == everything.ends_here


def test_the_posteriors_of_every_candidate_and_chance_add_up_to_one():
    result = Node(LEARNED).predict(STM)
    total = sum(p['bayesian_posterior'] for p in result.predictions) + result.chance_posterior
    assert total == pytest.approx(1.0, **EXACT)

    # Returning fewer predictions returns fewer posteriors, not rescaled ones.
    cut = Node(LEARNED).predict(STM, max_predictions=2)
    assert sum(p['bayesian_posterior'] for p in cut.predictions) + cut.chance_posterior < 1.0


def test_future_potentials_count_candidates_that_are_not_returned():
    result = Node(LEARNED).predict(STM, max_predictions=1)
    assert len(result.predictions) == 1
    supporters = sum(entry['supporting_patterns'] for entry in result.future_potentials)
    assert supporters == 4, "p_abc, p_abd, p_abce and p_amb have a future; p_xab and p_ab end with the STM"
    assert {tuple(entry['next_event']) for entry in result.future_potentials} == {('c',), ('d',)}
    # p_xab and p_ab end with the STM: their weight is the probability that nothing follows.
    weights = {p['name']: math.exp(p['potential']) for p in Node(LEARNED).predict(STM).predictions}
    ended = (weights['p_xab'] + weights['p_ab']) / sum(weights.values())
    assert result.ends_here == pytest.approx(ended, rel=1e-9)
    assert 0.0 < result.ends_here < 1.0
    assert (sum(entry['probability'] for entry in result.future_potentials) + result.ends_here
            == pytest.approx(1.0, **EXACT))


def test_values_do_not_depend_on_the_order_candidates_arrive_in():
    reference = Node(LEARNED).predict(STM)
    backward = Node(LEARNED, arrival=lambda names: sorted(names, reverse=True)).predict(STM)
    scrambled = Node(LEARNED, arrival=lambda names: sorted(names, key=lambda n: n[::-1])).predict(STM)
    for other in (backward, scrambled):
        assert [p['name'] for p in other.predictions] == [p['name'] for p in reference.predictions]
        assert _values(other) == _values(reference)
        assert other.future_potentials == reference.future_potentials
        assert other.chance_posterior == reference.chance_posterior
        assert other.ends_here == reference.ends_here


# ── ranking ────────────────────────────────────────────────────────────

@pytest.mark.parametrize('metric', VALID_RANK_SORT_ALGORITHMS)
def test_every_metric_ranks_every_candidate(metric):
    everything = Node(LEARNED).predict(STM, rank_sort_algo=metric)
    assert len(everything.predictions) == CANDIDATES

    keys = [(p[metric] is not None, p[metric] if p[metric] is not None else 0.0, p['name'])
            for p in everything.predictions]
    assert keys == sorted(keys, reverse=True), f"{metric}: highest first, ties by name"

    # The top two of a cut are the top two of all the candidates.
    cut = Node(LEARNED).predict(STM, rank_sort_algo=metric, max_predictions=2)
    assert [p['name'] for p in cut.predictions] == [p['name'] for p in everything.predictions[:2]]


@pytest.mark.parametrize('metric', VALID_RANK_SORT_ALGORITHMS)
def test_the_ranking_key_does_not_change_any_value(metric):
    reference = _values(Node(LEARNED).predict(STM))
    assert _values(Node(LEARNED).predict(STM, rank_sort_algo=metric)) == reference


def test_ranking_by_frequency_finds_the_most_frequent_candidate():
    result = Node(LEARNED).predict(STM, rank_sort_algo='frequency', max_predictions=1)
    assert [(p['name'], p['frequency']) for p in result.predictions] == [('p_xab', 9)]


def test_a_pattern_metric_as_the_key_is_worked_out_for_every_candidate_first():
    for metric in sorted(PATTERN_METRICS):
        node = Node(LEARNED)
        result = node.predict(STM, rank_sort_algo=metric, max_predictions=1)
        assert len(result.predictions) == 1
        assert len(node.metadata_reads[0]) == CANDIDATES, metric


def test_an_unknown_ranking_key_is_reported():
    with pytest.raises(Exception, match="Invalid rank_sort_algo 'no_such_metric'"):
        Node(LEARNED).predict(STM, rank_sort_algo='no_such_metric')


def test_nothing_private_is_left_in_a_prediction():
    for prediction in Node(LEARNED).predict(STM).predictions:
        assert not [key for key in prediction if key.startswith('_')]
        assert 'pattern_data' not in prediction
        assert 'good_odds' in prediction


# ── values ─────────────────────────────────────────────────────────────

def test_the_prior_is_the_share_of_every_learn_in_the_node():
    """Not of the candidates: p_qrs was learned 20 times and matches nothing here."""
    result = Node(LEARNED).predict(STM)
    by_name = {p['name']: p for p in result.predictions}
    assert by_name['p_xab']['bayesian_prior'] == pytest.approx(9 / 40, **EXACT)
    assert by_name['p_abc']['bayesian_prior'] == pytest.approx(1 / 40, **EXACT)
    assert sum(p['bayesian_prior'] for p in result.predictions) == pytest.approx(20 / 40, **EXACT)


def test_goods_identity_holds_to_the_last_bit():
    for prediction in Node(LEARNED).predict(STM).predictions:
        assert (math.log2(prediction['bayesian_prior']) + prediction['bayesian_likelihood']
                == prediction['good_odds'])


def test_patterns_that_match_alike_differ_in_potential_by_log_frequency_alone():
    """a b c and a b d match the STM identically; only their frequencies differ."""
    by_name = {p['name']: p for p in Node(LEARNED).predict(STM).predictions}
    difference = by_name['p_abd']['potential'] - by_name['p_abc']['potential']
    assert difference == pytest.approx(POTENTIAL_WEIGHTS['log_frequency'] * math.log(4), rel=1e-9)


def test_a_lone_weak_candidate_is_not_believed():
    """One pattern shares one symbol with a four-symbol STM, in a node of eleven learns."""
    node = Node([('p_abcd', seq('a b c d'), 1), ('p_qrst', seq('q r s t'), 10)])
    result = node.predict(seq('a z w v'))
    (prediction,) = result.predictions

    assert prediction['bayesian_prior'] == pytest.approx(1 / 11, **EXACT)
    # one match on `a` (1 of 44 learned symbol occurrences), three extras
    evidence = math.log2(0.95 * 44) - 3 * math.log2(20)
    assert prediction['bayesian_likelihood'] == pytest.approx(evidence, **EXACT)
    odds = (1 / 11) * 0.95 * 44 / 20 ** 3
    assert prediction['bayesian_posterior'] == pytest.approx(odds / (1 + odds), **EXACT)
    assert result.chance_posterior == pytest.approx(1 / (1 + odds), **EXACT)
    assert result.chance_posterior > 0.999
    # future_potentials and ends_here share the candidates' weight between
    # them; whether to believe the candidates at all is the chance posterior.
    assert result.future_potentials == [
        {'next_event': ['b'], 'probability': 1.0, 'supporting_patterns': 1}]
    assert result.ends_here == 0.0


def test_a_pattern_that_has_ended_keeps_a_weak_candidate_from_the_whole_probability():
    """a b c and a b d, learned once each; a, b, c is observed.

    a b c matches in full and has ended. a b d misses the newest symbol and
    proposes d. Left to the candidates that have a future, d would be certain.
    """
    node = Node([('p_abc', seq('a b c'), 1), ('p_abd', seq('a b d'), 1)])
    result = node.predict(seq('a b c'))
    by_name = {p['name']: p for p in result.predictions}

    assert by_name['p_abc']['future'] == [] and by_name['p_abd']['future'] == [['d']]
    assert by_name['p_abd']['good_odds'] < 0 < by_name['p_abc']['good_odds']
    ratio = math.exp(by_name['p_abd']['potential'] - by_name['p_abc']['potential'])
    assert result.future_potentials == [
        {'next_event': ['d'], 'probability': pytest.approx(ratio / (1 + ratio), **EXACT),
         'supporting_patterns': 1}]
    assert result.future_potentials[0]['probability'] < 0.001
    assert result.ends_here == pytest.approx(1 / (1 + ratio), **EXACT)
    assert result.ends_here > 0.999
    assert by_name['p_abc']['predictive_information'] == 0.0


def test_no_candidate_means_chance_explains_everything():
    result = Node(LEARNED).predict(seq('never seen'))
    assert result.predictions == [] and result.future_potentials == []
    assert result.chance_posterior == 1.0
    assert result.ends_here is None, "no candidate: nothing to take a share of"


def test_a_node_total_that_missed_re_learns_cannot_push_a_prior_above_one(caplog):
    """The counter holds the number of patterns (7) where the learns number 40."""
    node = Node(LEARNED, pattern_total=7)
    with caplog.at_level('WARNING', logger=pattern_processor_module.logger.name):
        result = node.predict(STM)
    assert all(0 < p['bayesian_prior'] <= 1 for p in result.predictions)
    assert sum(p['bayesian_prior'] for p in result.predictions) == pytest.approx(1.0, **EXACT)
    assert 'recount_pattern_frequencies' in caplog.text


def test_a_pattern_with_no_frequency_recorded_counts_as_learned_once(caplog):
    node = Node(LEARNED)
    del node.frequency['p_abc']
    with caplog.at_level('WARNING', logger=pattern_processor_module.logger.name):
        by_name = {p['name']: p for p in node.predict(STM).predictions}
    assert by_name['p_abc']['frequency'] == 1
    assert 'no frequency in Redis' in caplog.text


def test_frequencies_are_read_in_batches(monkeypatch):
    monkeypatch.setattr(pattern_processor_module, 'FREQUENCY_BATCH_SIZE', 4)
    node = Node(LEARNED)
    result = node.predict(STM)
    assert [len(batch) for batch in node.frequency_reads] == [4, 2]
    assert _values(result) == _values(Node(LEARNED).predict(STM))


def test_an_stm_without_event_structure_is_read_as_one_event():
    node = Node(LEARNED)
    settings = PredictionSettings(node, 100, 'potential', True)
    result = asyncio.run(node.processor().predictPattern(['a', 'b'], stm_events=None, settings=settings))
    assert len(result.predictions) == CANDIDATES
    assert all(math.isfinite(p['potential']) for p in result.predictions)
