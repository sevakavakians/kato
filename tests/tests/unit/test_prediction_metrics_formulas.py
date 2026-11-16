"""
The formulas of kato.informatics.prediction_metrics, against values worked by hand.

These are pure functions of a prediction's match fields and the node's counts,
so the tests build both by hand and need no running service. Every expected
value is written out from the formula in the docs, not read back from the code.

The node used throughout holds two patterns:

    a b c    learned once
    a x y    learned three times

so the symbol occurrences are a 4, b 1, c 1, x 3, y 3 (12 in all), four pattern
occurrences were learned in all, and `a` is held by both patterns.
"""

import itertools
import math

import pytest

from kato.informatics.prediction_metrics import (
    NOISE,
    PENALTY_BITS,
    POTENTIAL_WEIGHTS,
    NodeStatistics,
    Observation,
    bayesian_posteriors,
    confluence,
    future_potentials,
    good_odds,
    itfdf_similarity,
    potential,
    potential_terms,
    predictive_information,
    score_ensemble,
    tfidf_score,
    weight_of_evidence,
)

W = POTENTIAL_WEIGHTS
EXACT = {'rel': 1e-12, 'abs': 1e-12}

SYMBOL_TABLE = {
    'a': {'name': 'a', 'frequency': 4, 'pattern_member_frequency': 2},
    'b': {'name': 'b', 'frequency': 1, 'pattern_member_frequency': 1},
    'c': {'name': 'c', 'frequency': 1, 'pattern_member_frequency': 1},
    'x': {'name': 'x', 'frequency': 3, 'pattern_member_frequency': 1},
    'y': {'name': 'y', 'frequency': 3, 'pattern_member_frequency': 1},
}
STM = [['a'], ['b']]


def node():
    return NodeStatistics(SYMBOL_TABLE, total_symbol_occurrences=12, total_pattern_frequency=4, pattern_count=2)


def abc(**overrides):
    """`a b c` against the STM `a b`: both symbols matched, `c` still to come."""
    prediction = {
        'name': 'abc', 'frequency': 1,
        'matches': ['a', 'b'], 'missing': [[], []], 'extras': [[], []],
        'past': [], 'present': [['a'], ['b']], 'future': [['c']],
        'fragmentation': 0.0, 'snr': 1.0, 'fuzzy_matches': [],
    }
    prediction.update(overrides)
    return prediction


def axy(**overrides):
    """`a x y` against the STM `a b`: `a` matched, `b` an extra."""
    prediction = {
        'name': 'axy', 'frequency': 3,
        'matches': ['a'], 'missing': [[]], 'extras': [[], ['b']],
        'past': [], 'present': [['a']], 'future': [['x'], ['y']],
        'fragmentation': 0.0, 'snr': 1 / 3, 'fuzzy_matches': [],
    }
    prediction.update(overrides)
    return prediction


# ── node counts ────────────────────────────────────────────────────────

def test_the_constant_and_the_penalty():
    assert NOISE == 0.05
    assert math.log2(20) == PENALTY_BITS


def test_per_symbol_bits_come_from_the_share_of_learned_occurrences():
    stats = node()
    # q(a) = 4/12, q(b) = 1/12
    assert stats.match_bits['a'] == pytest.approx(math.log2(0.95 * 3), **EXACT)
    assert stats.match_bits['b'] == pytest.approx(math.log2(0.95 * 12), **EXACT)
    assert stats.rarity_bits['a'] == pytest.approx(math.log2(3), **EXACT)
    assert stats.rarity_bits['x'] == pytest.approx(2.0, **EXACT)
    assert stats.match_bits['b'] > stats.match_bits['a'], "a rarer symbol is worth more bits"


def test_idf_counts_patterns_not_occurrences():
    stats = node()
    assert stats.idf['a'] == 1.0            # held by both patterns: log2(2/2) + 1
    assert stats.idf['b'] == 2.0            # held by one of two: log2(2/1) + 1
    assert stats.idf['never_learned'] == 0.0
    assert stats.pattern_share('a') == 1.0
    assert stats.pattern_share('x') == 0.5
    assert stats.pattern_share('never_learned') == 0.0


def test_counts_read_mid_write_stay_inside_their_bounds():
    """q(s) stays in (0, 1] when a count is missing or ahead of the node total."""
    stats = NodeStatistics({'a': {'frequency': 50, 'pattern_member_frequency': 1}}, 10, 1, 1)
    assert stats.occurrences('a') == 10                       # never above the total
    assert stats.occurrences('unrecorded') == 1               # never below one
    assert stats.rarity_bits['a'] == 0.0
    assert math.isfinite(stats.match_bits['unrecorded'])
    empty = NodeStatistics({}, 0, 0, 0)                       # every counter lost
    assert math.isfinite(empty.match_bits['a']) and empty.idf['a'] == 0.0


# ── bayesian_likelihood, bayesian_prior, good_odds ─────────────────────

def test_weight_of_evidence_adds_matches_and_subtracts_penalties():
    stats = node()
    # log2(0.95 / (4/12)) + log2(0.95 / (1/12))
    assert weight_of_evidence(abc(), stats) == pytest.approx(math.log2(2.85) + math.log2(11.4), **EXACT)
    # one match on `a`, one extra symbol
    assert weight_of_evidence(axy(), stats) == pytest.approx(math.log2(2.85) - math.log2(20), **EXACT)


def test_missing_and_extra_symbols_cost_the_same():
    stats = node()
    clean = weight_of_evidence(abc(), stats)
    one_missing = weight_of_evidence(abc(missing=[[], ['m']]), stats)
    one_extra = weight_of_evidence(abc(extras=[['e'], []]), stats)
    assert clean - one_missing == pytest.approx(PENALTY_BITS, **EXACT)
    assert one_missing == one_extra


def test_the_unobserved_past_and_future_are_not_evidence():
    stats = node()
    short = abc()
    long = abc(past=[['p1'], ['p2']], future=[['c'], ['d'], ['e'], ['f']])
    assert weight_of_evidence(short, stats) == weight_of_evidence(long, stats)


def test_good_odds_is_the_log_prior_plus_the_weight_of_evidence():
    stats = node()
    evidence = weight_of_evidence(abc(), stats)
    assert good_odds(1 / 4, evidence) == math.log2(1 / 4) + evidence
    # 2^G is prior x likelihood ratio: 1/4 x 2.85 x 11.4
    assert 2 ** good_odds(1 / 4, evidence) == pytest.approx(0.25 * 2.85 * 11.4, **EXACT)


def test_a_fuzzy_matched_token_takes_the_count_of_the_pattern_token():
    """`bb` was never learned; it matched the pattern's `b`, so it is worth b's bits."""
    stats = node()
    fuzzy = abc(matches=['a', 'bb'],
                fuzzy_matches=[{'observed': 'bb', 'expected': 'b', 'similarity': 0.8}])
    assert weight_of_evidence(fuzzy, stats) == weight_of_evidence(abc(), stats)


def test_flat_missing_and_extras_are_counted_too():
    stats = node()
    structured = abc(missing=[['m'], []], extras=[[], ['e']])
    flat = abc(missing=['m'], extras=['e'])
    assert weight_of_evidence(flat, stats) == weight_of_evidence(structured, stats)


# ── potential ──────────────────────────────────────────────────────────

def test_the_terms_of_an_exact_contiguous_match():
    stats = node()
    terms = potential_terms(abc(), Observation(STM, stats), stats)
    assert list(terms) == list(POTENTIAL_WEIGHTS), "the terms come in the order they are added"
    assert terms == pytest.approx({
        'snr': 1.0,
        'fragmentation': 0.0,
        'inverse_fragmentation': 1.0,
        'last_event_matched': 1.0,
        'last_event_share': 1.0,
        'recency_07': 0.7 + 1.0,            # `a` one event back, `b` in the newest
        'recency_09': 0.9 + 1.0,
        'tversky': 1.0,
        'cosine_idf_present': 1.0,          # the STM and `present` are the same bag
        'evidence_to_end': 1.0,             # 2 matches of the 2 symbols up to the end of present
        'log_frequency': 0.0,
    }, **EXACT)


def test_the_terms_of_a_match_that_misses_the_newest_event():
    stats = node()
    terms = potential_terms(axy(), Observation(STM, stats), stats)
    assert terms == pytest.approx({
        'snr': 1 / 3,                       # (2 x 1 - 1) / (2 x 1 + 1)
        'fragmentation': 0.0,
        'inverse_fragmentation': 1.0,
        'last_event_matched': 0.0,          # `b` is an extra
        'last_event_share': 0.0,
        'recency_07': 0.7,                  # only `a`, one event back
        'recency_09': 0.9,
        'tversky': 1 / 3,                   # 1 / (1 + 2 x 0 + 2 x 1)
        # STM weights a 1, b 2 (norm sqrt 5); present holds `a` alone (norm 1); dot 1
        'cosine_idf_present': 1 / math.sqrt(5),
        'evidence_to_end': 1.0,
        'log_frequency': math.log(3),
    }, **EXACT)


def test_potential_is_the_weighted_sum_of_its_terms():
    stats = node()
    observation = Observation(STM, stats)
    expected_abc = (
        W['snr'] + W['inverse_fragmentation'] + W['last_event_matched'] + W['last_event_share']
        + 1.7 * W['recency_07'] + 1.9 * W['recency_09'] + W['tversky']
        + W['cosine_idf_present'] + W['evidence_to_end']
    )
    assert potential(abc(), observation, stats) == pytest.approx(expected_abc, **EXACT)
    assert expected_abc == pytest.approx(16.10272848, abs=1e-8)

    expected_axy = (
        W['snr'] / 3 + W['inverse_fragmentation']
        + 0.7 * W['recency_07'] + 0.9 * W['recency_09'] + W['tversky'] / 3
        + W['cosine_idf_present'] / math.sqrt(5) + W['evidence_to_end']
        + W['log_frequency'] * math.log(3)
    )
    assert potential(axy(), observation, stats) == pytest.approx(expected_axy, **EXACT)


def test_the_weights_are_the_fitted_constants():
    assert POTENTIAL_WEIGHTS == {
        'snr': 0.5843639561444975,
        'fragmentation': -0.7701727284444962,
        'inverse_fragmentation': 0.3874235103814889,
        'last_event_matched': 2.7551983021381603,
        'last_event_share': 0.022364665110185304,
        'recency_07': 1.7897143000355997,
        'recency_09': 0.0632088710855439,
        'tversky': 0.947709643038957,
        'cosine_idf_present': 6.037962738972206,
        'evidence_to_end': 2.2050945031820732,
        'log_frequency': 0.6797831284041117,
    }


def test_potential_does_not_fall_as_the_unobserved_future_grows():
    stats = node()
    observation = Observation(STM, stats)
    longer = abc(future=[['c'], ['d'], ['e'], ['f'], ['g']])
    assert potential(longer, observation, stats) == potential(abc(), observation, stats)


def test_each_term_moves_potential_in_its_own_direction():
    stats = node()
    observation = Observation(STM, stats)
    base = potential(abc(), observation, stats)
    assert potential(abc(frequency=2), observation, stats) - base == pytest.approx(
        W['log_frequency'] * math.log(2), **EXACT)
    # One more matched block: fragmentation 1, inverse 1/2.
    assert potential(abc(fragmentation=1.0), observation, stats) - base == pytest.approx(
        W['fragmentation'] - W['inverse_fragmentation'] / 2, **EXACT)
    # A pattern event before the match: evidence_to_end falls from 2/2 to 2/3.
    assert potential(abc(past=[['p']]), observation, stats) - base == pytest.approx(
        -W['evidence_to_end'] / 3, **EXACT)


def test_a_match_with_no_exact_block_earns_no_cohesion():
    """fragmentation is -1 when fuzzy matching finds tokens and no exact block."""
    stats = node()
    terms = potential_terms(abc(fragmentation=-1.0), Observation(STM, stats), stats)
    assert terms['fragmentation'] == 0.0
    assert terms['inverse_fragmentation'] == 0.0


def test_extras_without_event_structure_read_the_stm_as_one_event():
    stats = node()
    terms = potential_terms(axy(extras=['b']), Observation(STM, stats), stats)
    assert terms['recency_07'] == 1.0 and terms['recency_09'] == 1.0     # one matched symbol, no decay
    assert terms['last_event_matched'] == 1.0
    assert terms['last_event_share'] == 0.5
    assert terms['tversky'] == pytest.approx(1 / 3, **EXACT)


# ── bayesian_posterior ─────────────────────────────────────────────────

def test_posteriors_are_odds_over_one_plus_total_odds():
    odds_abc = 0.25 * 2.85 * 11.4            # 2^G of `a b c`
    odds_axy = 0.75 * 2.85 / 20              # 2^G of `a x y`
    posteriors, chance = bayesian_posteriors(['abc', 'axy'], [math.log2(odds_abc), math.log2(odds_axy)])
    total = 1 + odds_abc + odds_axy
    assert posteriors['abc'] == pytest.approx(odds_abc / total, **EXACT)
    assert posteriors['axy'] == pytest.approx(odds_axy / total, **EXACT)
    assert chance == pytest.approx(1 / total, **EXACT)
    assert posteriors['abc'] == pytest.approx(0.88007, abs=1e-5)
    assert posteriors['axy'] == pytest.approx(0.01158, abs=1e-5)
    assert chance == pytest.approx(0.10835, abs=1e-5)
    assert sum(posteriors.values()) + chance == pytest.approx(1.0, **EXACT)


def test_a_lone_candidate_is_weighed_against_chance():
    posteriors, chance = bayesian_posteriors(['only'], [3.0])
    assert posteriors['only'] == pytest.approx(8 / 9, **EXACT)
    assert chance == pytest.approx(1 / 9, **EXACT)
    # A lone candidate that explains the STM worse than chance is not believed.
    posteriors, chance = bayesian_posteriors(['only'], [-10.0])
    assert posteriors['only'] == pytest.approx(1 / 1025, **EXACT)
    assert chance == pytest.approx(1024 / 1025, **EXACT)


def test_no_candidate_leaves_everything_to_chance():
    assert bayesian_posteriors([], []) == ({}, 1.0)


def test_posteriors_survive_exponents_no_float_can_hold():
    posteriors, chance = bayesian_posteriors(['strong', 'weak'], [5000.0, -5000.0])
    assert posteriors == {'strong': 1.0, 'weak': 0.0}
    assert chance == 0.0
    posteriors, chance = bayesian_posteriors(['weak'], [-5000.0])
    assert posteriors == {'weak': 0.0} and chance == 1.0


def test_posteriors_do_not_depend_on_the_order_candidates_arrive_in():
    names = ['p3', 'p1', 'p4', 'p2', 'p5']
    odds = [0.1, 7.3, -2.2, 7.3000001, 3.9]
    reference = bayesian_posteriors(names, odds)
    for order in itertools.permutations(range(5)):
        shuffled = bayesian_posteriors([names[i] for i in order], [odds[i] for i in order])
        assert shuffled == reference


# ── future_potentials ──────────────────────────────────────────────────

def _with_potential(name, future, value):
    return {'name': name, 'future': future, 'potential': value}


def test_future_potentials_add_up_the_patterns_that_agree_on_the_next_event():
    """a b c d x5, a b c e x4, a b x y x6, observed `a b`.

    The three match alike, so their potentials differ only by
    log_frequency: e^potential is proportional to frequency^weight. `c` follows
    in two patterns and `x` in one.
    """
    weight = W['log_frequency']
    predictions = [
        _with_potential('abcd', [['c'], ['d']], 10.0 + weight * math.log(5)),
        _with_potential('abce', [['c'], ['e']], 10.0 + weight * math.log(4)),
        _with_potential('abxy', [['x'], ['y']], 10.0 + weight * math.log(6)),
    ]
    total = 5 ** weight + 4 ** weight + 6 ** weight
    result = future_potentials(predictions)
    assert [entry['next_event'] for entry in result] == [['c'], ['x']]
    assert result[0]['probability'] == pytest.approx((5 ** weight + 4 ** weight) / total, **EXACT)
    assert result[1]['probability'] == pytest.approx(6 ** weight / total, **EXACT)
    assert [entry['supporting_patterns'] for entry in result] == [2, 1]
    assert result[0]['probability'] == pytest.approx(0.6216, abs=1e-4)
    assert set(result[0]) == {'next_event', 'probability', 'supporting_patterns'}


def test_a_prediction_with_no_future_proposes_nothing():
    predictions = [
        _with_potential('ends_here', [], 50.0),
        _with_potential('goes_on', [['next']], 1.0),
    ]
    assert future_potentials(predictions) == [
        {'next_event': ['next'], 'probability': 1.0, 'supporting_patterns': 1}]
    assert future_potentials([_with_potential('ends_here', [], 50.0)]) == []
    assert future_potentials([]) == []


def test_equal_probabilities_go_to_the_event_that_sorts_first():
    predictions = [
        _with_potential('p1', [['zeta']], 2.0),
        _with_potential('p2', [['alpha']], 2.0),
    ]
    forward = future_potentials(predictions)
    backward = future_potentials(list(reversed(predictions)))
    assert forward[0]['probability'] == forward[1]['probability'] == 0.5
    assert [entry['next_event'] for entry in forward] == [['alpha'], ['zeta']]
    assert forward == backward


def test_a_multi_symbol_next_event_is_one_event():
    predictions = [
        _with_potential('p1', [['m', 'n'], ['z']], 1.0),
        _with_potential('p2', [['m', 'n']], 1.0),
        _with_potential('p3', [['m']], 1.0),
    ]
    result = future_potentials(predictions)
    assert result[0] == {'next_event': ['m', 'n'], 'probability': pytest.approx(2 / 3, **EXACT),
                         'supporting_patterns': 2}
    assert result[1]['next_event'] == ['m']


def test_future_potentials_survive_potentials_no_exponential_can_hold():
    predictions = [
        _with_potential('p1', [['a']], 5000.0),
        _with_potential('p2', [['b']], -5000.0),
    ]
    result = future_potentials(predictions)
    assert [(entry['next_event'], entry['probability']) for entry in result] == [(['a'], 1.0), (['b'], 0.0)]


# ── predictive_information ─────────────────────────────────────────────

def test_predictive_information_is_the_share_times_the_bits_over_chance():
    stats = node()
    predictions = [
        _with_potential('abc', [['c']], math.log(3)),             # share 3/4
        _with_potential('axy', [['x'], ['y']], 0.0),              # share 1/4
        _with_potential('ended', [], 9.0),
    ]
    information = predictive_information(predictions, stats)
    # P(c) = 3/4 against q(c) = 1/12; P(x) = 1/4 against q(x) = 3/12
    assert information['abc'] == pytest.approx(0.75 * math.log2(0.75 * 12), **EXACT)
    assert information['axy'] == pytest.approx(0.25 * math.log2(0.25 * 4), **EXACT)
    assert information['axy'] == pytest.approx(0.0, abs=1e-12), "as probable as chance makes it: no information"
    assert information['ended'] == 0.0


def test_predictive_information_adds_up_to_the_divergence_from_chance():
    stats = node()
    predictions = [
        _with_potential('p1', [['c']], 1.3),
        _with_potential('p2', [['c'], ['y']], 0.2),
        _with_potential('p3', [['x']], 0.9),
        _with_potential('p4', [['x', 'y']], -0.4),
    ]
    information = predictive_information(predictions, stats)
    divergence = 0.0
    for entry in future_potentials(predictions):
        chance_bits = sum(stats.rarity_bits[symbol] for symbol in entry['next_event'])
        divergence += entry['probability'] * (math.log2(entry['probability']) + chance_bits)
    assert sum(information.values()) == pytest.approx(divergence, **EXACT)
    assert divergence > 0


def test_an_event_less_probable_than_chance_carries_negative_information():
    stats = node()
    predictions = [
        _with_potential('likely', [['c']], 10.0),
        _with_potential('unlikely', [['x']], 0.0),               # q(x) = 1/4, P(x) far below it
    ]
    information = predictive_information(predictions, stats)
    assert information['unlikely'] < 0 < information['likely']


# ── confluence ─────────────────────────────────────────────────────────

def test_confluence_is_how_often_learned_over_how_often_by_chance():
    stats = node()
    # log2((1/4) / ((4/12) x (1/12) x (1/12)))
    assert confluence([['a'], ['b'], ['c']], 1, 4, stats) == pytest.approx(
        math.log2(1 / 4) + math.log2(3) + 2 * math.log2(12), **EXACT)
    assert confluence([['a'], ['x'], ['y']], 3, 4, stats) == pytest.approx(
        math.log2(3 / 4) + math.log2(3) + 2 * math.log2(4), **EXACT)


def test_confluence_is_the_ceiling_of_good_odds():
    """An exact, complete observation scores confluence less log2(1/0.95) per symbol."""
    stats = node()
    complete = abc(matches=['a', 'b', 'c'], missing=[[], [], []], extras=[[], [], []],
                   present=[['a'], ['b'], ['c']], future=[])
    odds = good_odds(1 / 4, weight_of_evidence(complete, stats))
    ceiling = confluence([['a'], ['b'], ['c']], 1, 4, stats)
    assert ceiling - odds == pytest.approx(3 * math.log2(1 / 0.95), **EXACT)
    partial = good_odds(1 / 4, weight_of_evidence(abc(), stats))
    assert partial < odds < ceiling


# ── tfidf_score, itfdf_similarity ──────────────────────────────────────

def test_tfidf_score_is_the_mean_over_distinct_symbols():
    stats = node()
    # a b c: each a third of the pattern; idf a 1, b 2, c 2
    assert tfidf_score({'a': 1 / 3, 'b': 1 / 3, 'c': 1 / 3}, stats) == pytest.approx((1 + 2 + 2) / 9, **EXACT)
    # A symbol the node does not hold counts as held by one pattern.
    assert tfidf_score({'unseen': 1.0}, stats) == pytest.approx(2.0, **EXACT)
    assert tfidf_score({}, stats) == 0.0
    shares = {'c': 0.2, 'a': 0.5, 'b': 0.3}
    assert tfidf_score(shares, stats) == tfidf_score(dict(sorted(shares.items())), stats)


def test_itfdf_similarity_of_an_exact_match_is_exactly_one():
    stats = node()
    observation = Observation(STM, stats)
    for frequency in (1, 3, 50):
        assert itfdf_similarity(observation, [['a'], ['b']], frequency, 50, stats) == 1.0


def test_itfdf_similarity_discounts_distance_by_the_share_of_frequency():
    stats = node()
    observation = Observation(STM, stats)
    # STM weights: a 1.0, b 0.5 (norm^2 1.25). present `a` alone: norm^2 1, dot 1.
    cosine = 1 / math.sqrt(1.25)
    assert itfdf_similarity(observation, [['a']], 3, 4, stats) == pytest.approx(
        1 - (1 - cosine) * 3 / 4, **EXACT)
    # Nothing in common: distance 1, so the value is 1 - frequency share.
    assert itfdf_similarity(observation, [['x']], 3, 4, stats) == pytest.approx(0.25, **EXACT)
    assert itfdf_similarity(observation, [['a']], 3, 0, stats) == 0.0
    for present in ([['a']], [['a'], ['b']], [['x'], ['y']], [['a', 'x']]):
        assert 0.0 <= itfdf_similarity(observation, present, 1, 4, stats) <= 1.0


# ── score_ensemble ─────────────────────────────────────────────────────

def _scored(predictions):
    stats = node()
    scores = score_ensemble(predictions, Observation(STM, stats), stats)
    return predictions, scores


def test_score_ensemble_sets_the_fields_and_returns_the_ensemble_figures():
    (first, second), scores = _scored([abc(), axy()])

    assert first['bayesian_prior'] == 0.25 and second['bayesian_prior'] == 0.75
    assert first['bayesian_likelihood'] == pytest.approx(math.log2(2.85) + math.log2(11.4), **EXACT)
    for prediction in (first, second):
        # Good's identity holds to the last bit, not approximately.
        assert math.log2(prediction['bayesian_prior']) + prediction['bayesian_likelihood'] == prediction['good_odds']

    total = 1 + 0.25 * 2.85 * 11.4 + 0.75 * 2.85 / 20
    assert first['bayesian_posterior'] == pytest.approx(0.25 * 2.85 * 11.4 / total, **EXACT)
    assert second['bayesian_posterior'] == pytest.approx(0.75 * 2.85 / 20 / total, **EXACT)
    assert scores.chance_posterior == pytest.approx(1 / total, **EXACT)

    share_abc = 1 / (1 + math.exp(second['potential'] - first['potential']))
    assert scores.future_potentials == [
        {'next_event': ['c'], 'probability': pytest.approx(share_abc, **EXACT), 'supporting_patterns': 1},
        {'next_event': ['x'], 'probability': pytest.approx(1 - share_abc, **EXACT), 'supporting_patterns': 1},
    ]
    assert first['predictive_information'] == pytest.approx(
        share_abc * (math.log2(share_abc) + math.log2(12)), **EXACT)
    assert scores.candidate_frequency == 4
    assert scores.total_pattern_frequency == 4


def test_score_ensemble_gives_the_same_bits_in_any_arrival_order():
    def build():
        return [
            abc(), axy(),
            abc(name='abd', future=[['d']], frequency=7),
            axy(name='axz', frequency=2, future=[['x'], ['z']]),
            abc(name='ab', future=[]),
        ]

    def snapshot(predictions, scores):
        fields = ('bayesian_prior', 'bayesian_likelihood', 'good_odds', 'potential',
                  'bayesian_posterior', 'predictive_information')
        return ({p['name']: tuple(p[f] for f in fields) for p in predictions},
                scores.future_potentials, scores.chance_posterior)

    reference = snapshot(*_scored(build()))
    for order in itertools.permutations(range(5)):
        candidates = build()
        assert snapshot(*_scored([candidates[i] for i in order])) == reference


def test_a_prior_never_exceeds_one_when_the_node_total_is_behind():
    """A node whose counter missed re-learns: the candidates' own total stands in."""
    stats = NodeStatistics(SYMBOL_TABLE, 12, total_pattern_frequency=2, pattern_count=2)
    predictions = [abc(), axy()]
    scores = score_ensemble(predictions, Observation(STM, stats), stats)
    assert scores.candidate_frequency == 4 and scores.total_pattern_frequency == 4
    assert [p['bayesian_prior'] for p in predictions] == [0.25, 0.75]
