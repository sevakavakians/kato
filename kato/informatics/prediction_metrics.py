"""
Prediction metrics that read the node's counts.

`good_odds`, `bayesian_prior`, `bayesian_likelihood`, `bayesian_posterior`,
`potential`, `future_potentials`, `ends_here`, `predictive_information`,
`confluence`, `tfidf_score` and `itfdf_similarity` are computed here, as pure
functions of

- a prediction's own match fields (`matches`, `missing`, `extras`, `past`,
  `present`, `future`, `fragmentation`, `snr`, `frequency`),
- the short-term memory, and
- counts the node keeps (NodeStatistics).

Nothing is aligned or matched here and nothing is read from storage: the match
fields are taken exactly as the extraction returns them.

The model behind good-odds and the Bayesian fields
--------------------------------------------------
Two hypotheses are compared for each candidate pattern.

    chance        every observed symbol was drawn independently with
                  probability q(s), the symbol's share of all learned symbol
                  occurrences
    the pattern   a pattern that is occurring shows each symbol of `present`
                  with probability 1 - e and drops it with probability e
                  (`missing`); an observed symbol the pattern does not account
                  for is an intrusion, with probability e x q(s) (`extras`)

Which stretch of the pattern is in view is taken as given, so an unobserved
past or future is not evidence against a pattern. `e` is NOISE, the one constant.

    bayesian_likelihood   W = sum over matches of log2((1 - e) / q(s))
                              - log2(1 / e) x (missing + extras)          bits
    bayesian_prior        f / F
    good_odds             G = log2(f / F) + W                              bits
    bayesian_posterior    2^G / (1 + sum of 2^G over the candidates)

W is I. J. Good's weight of evidence: the base-2 logarithm of
P(STM | pattern) / P(STM | chance). Adding the logarithm of the prior gives the
logarithm of the posterior odds of the pattern against chance, which is why the
field carries his name, and `log2(bayesian_prior) + bayesian_likelihood ==
good_odds` holds exactly. Odds against a common reference turn into
probabilities as odds / (1 + total odds); the 1 is the reference itself, so what
the candidates leave over, 1 / (1 + sum of 2^G), is the probability that no
learned pattern explains the STM better than chance (`chance_posterior`).

Determinism
-----------
Floating-point addition is not associative, so every sum here has a stated
order: a prediction's own terms in the order written, symbols in sorted order,
and anything summed over the ensemble in pattern-name order. Sums are plain
left-to-right additions, not the builtin `sum`, whose rounding of floats
differs between Python versions. The same candidates therefore give the same
bits whatever order they arrive in.
"""

import math
from collections import Counter
from collections.abc import Mapping, Sequence
from itertools import chain
from typing import Any, NamedTuple, Optional

# The assumed chance that a symbol is dropped from, or intrudes into, an
# observation of a pattern. The only constant of good-odds.
NOISE = 0.05

_SHOWN = 1.0 - NOISE
# What each missing or extra symbol costs, in bits.
PENALTY_BITS = math.log2(1.0 / NOISE)

# `potential` is the sum of these terms, each times its weight, added in this
# order. The weights are constants: they were fitted once, on held-out queries
# of synthetic sequences, system logs, click streams and text, to make the
# event that followed an STM as probable as possible under a softmax of
# `potential` over the candidates. Nothing is fitted at prediction time.
POTENTIAL_WEIGHTS = {
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
_POTENTIAL_WEIGHT_VALUES = tuple(POTENTIAL_WEIGHTS.values())


class _PerSymbol(dict):
    """symbol -> value, worked out on first use and kept for the rest of the request."""

    def __init__(self, compute) -> None:
        super().__init__()
        self._compute = compute

    def __missing__(self, symbol: str) -> float:
        value = self[symbol] = self._compute(symbol)
        return value


class NodeStatistics:
    """The node's counts, as the metrics read them.

    Built once per request from the symbol table and the global counters. The
    per-symbol logarithms are worked out on first use and kept for the rest of
    the request; an instance is never shared between requests.

    Args:
        symbol_table: symbol -> {'frequency': learned occurrences,
            'pattern_member_frequency': patterns that hold the symbol}.
        total_symbol_occurrences: sum of `frequency` over every symbol
            (`total_symbols_in_patterns_frequencies`).
        total_pattern_frequency: sum of every pattern's frequency
            (`total_pattern_frequencies`).
        pattern_count: number of patterns in the node (`total_unique_patterns`).

    Attributes, each a table indexed by symbol:
        match_bits: log2((1 - e) / q(s)), what one matched occurrence is worth.
        rarity_bits: log2(1 / q(s)), how surprising one occurrence is by chance.
        idf: log2(patterns / patterns holding s) + 1; 0 for a symbol never learned.
    """

    def __init__(
        self,
        symbol_table: Mapping[str, Mapping[str, Any]],
        total_symbol_occurrences: int,
        total_pattern_frequency: int,
        pattern_count: int,
    ) -> None:
        self._table = symbol_table
        self.total_symbol_occurrences = max(int(total_symbol_occurrences), 1)
        self.total_pattern_frequency = max(int(total_pattern_frequency), 0)
        self.pattern_count = max(int(pattern_count), 1)
        self.match_bits = _PerSymbol(self._match_bits)
        self.rarity_bits = _PerSymbol(self._rarity_bits)
        self.idf = _PerSymbol(self._idf)

    def __len__(self) -> int:
        """Number of distinct symbols in the node."""
        return len(self._table)

    def knows(self, symbol: str) -> bool:
        """Whether the node has learned `symbol`."""
        return symbol in self._table

    def occurrences(self, symbol: str) -> int:
        """Learned occurrences of `symbol`, held between 1 and the node total.

        A symbol of a learned pattern has occurred at least once and at most as
        often as every symbol together. The bounds only take effect when the
        counts are read while a learn or a purge is in flight, and keep q(s)
        inside (0, 1] there.
        """
        entry = self._table.get(symbol)
        count = int(entry.get('frequency', 0)) if entry else 0
        return min(max(count, 1), self.total_symbol_occurrences)

    def patterns_holding(self, symbol: str) -> int:
        """Number of patterns that hold `symbol`; 0 for a symbol never learned."""
        entry = self._table.get(symbol)
        return int(entry.get('pattern_member_frequency', 0)) if entry else 0

    def pattern_share(self, symbol: str) -> float:
        """Share of the node's patterns that hold `symbol`."""
        return self.patterns_holding(symbol) / self.pattern_count

    def _match_bits(self, symbol: str) -> float:
        return math.log2(_SHOWN * self.total_symbol_occurrences / self.occurrences(symbol))

    def _rarity_bits(self, symbol: str) -> float:
        return math.log2(self.total_symbol_occurrences / self.occurrences(symbol))

    def _idf(self, symbol: str) -> float:
        holding = self.patterns_holding(symbol)
        return math.log2(self.pattern_count / holding) + 1.0 if holding else 0.0


class Observation:
    """The short-term memory, as the terms of `potential` read it.

    Built once per request. `events` is the STM as KATO holds it: a list of
    events, each a list of symbols.
    """

    def __init__(self, events: Sequence[Sequence[str]], node: NodeStatistics) -> None:
        self.event_sizes = [len(event) for event in events]
        newest = len(self.event_sizes) - 1
        # How much a symbol counts by how many events back from the newest it is.
        self.decay_07 = [0.7 ** (newest - index) for index in range(newest + 1)]
        self.decay_09 = [0.9 ** (newest - index) for index in range(newest + 1)]
        self.counts = Counter(chain.from_iterable(events))
        self.size = sum(self.event_sizes)
        self.symbols = sorted(self.counts)
        self.idf = {symbol: node.idf[symbol] for symbol in self.symbols}
        squares = 0.0
        for symbol in self.symbols:
            squares += (self.idf[symbol] * self.counts[symbol]) ** 2
        self.idf_norm = math.sqrt(squares)


def _count(events: Any) -> int:
    """Number of symbols in an event-structured list, or in a flat one."""
    if not events:
        return 0
    if isinstance(events[0], list):
        return sum(map(len, events))
    return len(events)


def _extras_by_event(prediction: Mapping[str, Any], observation: Observation) -> tuple[list[int], list[int]]:
    """(symbols per STM event, extras per STM event), index for index.

    `extras` is aligned with the STM events. Where it is not (a prediction
    built without the STM's event structure carries a flat list), the STM is
    read as a single event, so every term below stays defined.
    """
    extras = prediction['extras']
    if extras and isinstance(extras[0], list) and len(extras) == len(observation.event_sizes):
        return observation.event_sizes, list(map(len, extras))
    return [observation.size], [_count(extras)]


def weight_of_evidence(prediction: Mapping[str, Any], node: NodeStatistics) -> float:
    """`bayesian_likelihood`: Good's weight of evidence for the pattern, in bits.

        W = sum over matches of log2((1 - e) / q(s)) - log2(1 / e) x (missing + extras)

    The base-2 logarithm of P(STM | the pattern) / P(STM | chance). Each match
    adds bits, more for a rarer symbol; each missing or extra symbol costs
    log2(1 / e) = 4.32 bits. Positive when the pattern explains the STM better
    than chance does, negative when worse.

    Matches are added in list order, then the penalty is subtracted. With fuzzy
    token matching, a matched STM token the node has never learned takes the
    count of the pattern token it was matched to.
    """
    expected: dict[str, str] = {}
    for fuzzy in prediction.get('fuzzy_matches') or ():
        expected.setdefault(fuzzy['observed'], fuzzy['expected'])

    match_bits = node.match_bits
    bits = 0.0
    for symbol in prediction['matches']:
        if expected and not node.knows(symbol):
            symbol = expected.get(symbol, symbol)
        bits += match_bits[symbol]
    return bits - PENALTY_BITS * (_count(prediction['missing']) + _count(prediction['extras']))


def good_odds(prior: float, evidence_bits: float) -> float:
    """`good_odds`: log2 of the posterior odds of the pattern against chance, in bits.

        G = log2(bayesian_prior) + bayesian_likelihood

    Named for I. J. Good, whose weight of evidence is the second term. It is a
    property of one prediction and the node: it does not depend on which other
    candidates matched, on their order, or on `max_predictions`.
    """
    return math.log2(prior) + evidence_bits


def _potential_term_values(
    prediction: Mapping[str, Any],
    observation: Observation,
    node: NodeStatistics,
) -> tuple[float, ...]:
    """The terms of `potential` for one prediction, in POTENTIAL_WEIGHTS order."""
    matches = len(prediction['matches'])
    missing = _count(prediction['missing'])
    sizes, extras_here = _extras_by_event(prediction, observation)
    extras = sum(extras_here)
    newest = len(sizes) - 1
    if len(sizes) == len(observation.event_sizes):
        decay_07, decay_09 = observation.decay_07, observation.decay_09
    else:
        decay_07 = decay_09 = [1.0]
    recency_07 = 0.0
    recency_09 = 0.0
    for index, size in enumerate(sizes):
        matched_here = size - extras_here[index]
        recency_07 += matched_here * decay_07[index]
        recency_09 += matched_here * decay_09[index]
    last_matched = sizes[newest] - extras_here[newest] if sizes else 0
    last_size = sizes[newest] if sizes else 0

    here = Counter(chain.from_iterable(prediction['present']))
    state_counts, state_idf = observation.counts, observation.idf
    dot = 0.0
    for symbol in observation.symbols:
        if symbol in here:
            idf = state_idf[symbol]
            dot += idf * state_counts[symbol] * idf * here[symbol]
    node_idf = node.idf
    squares = 0.0
    for symbol in sorted(here):
        squares += (node_idf[symbol] * here[symbol]) ** 2
    norm_here = math.sqrt(squares)
    norm_state = observation.idf_norm

    fragmentation = prediction['fragmentation']
    up_to_end = _count(prediction['past']) + _count(prediction['present'])
    tversky_denominator = matches + 2.0 * missing + 2.0 * extras
    return (
        prediction['snr'],
        fragmentation if fragmentation > 0 else 0.0,
        1.0 / (fragmentation + 1) if fragmentation >= 0 else 0.0,
        1.0 if last_matched > 0 else 0.0,
        last_matched / last_size if last_size else 0.0,
        recency_07,
        recency_09,
        matches / tversky_denominator if tversky_denominator else 0.0,
        dot / (norm_state * norm_here) if norm_state and norm_here else 0.0,
        matches / up_to_end if up_to_end else 0.0,
        math.log(prediction['frequency']),
    )


def potential_terms(
    prediction: Mapping[str, Any],
    observation: Observation,
    node: NodeStatistics,
) -> dict[str, float]:
    """The eleven terms of `potential` for one prediction, by name.

    snr                    the prediction's `snr`
    fragmentation          the prediction's `fragmentation` (matched blocks - 1)
    inverse_fragmentation  1 / (fragmentation + 1)
    last_event_matched     1 if the newest STM event has a matched symbol, else 0
    last_event_share       matched share of the newest STM event's symbols
    recency_07             matched STM symbols, each counted 0.7^(events back from the newest)
    recency_09             the same with 0.9
    tversky                matches / (matches + 2 x missing + 2 x extras)
    cosine_idf_present     cosine between the STM and `present` as bags of symbols,
                           each symbol weighted by log2(patterns / patterns holding it) + 1
    evidence_to_end        matches / symbols of `past` and `present`
    log_frequency          natural logarithm of the pattern's frequency

    A match with no exact block (possible only with fuzzy token matching) has
    `fragmentation` -1; it counts as 0 blocks broken and earns no
    inverse_fragmentation.
    """
    return dict(zip(POTENTIAL_WEIGHTS, _potential_term_values(prediction, observation, node)))


def potential(prediction: Mapping[str, Any], observation: Observation, node: NodeStatistics) -> float:
    """`potential`: the weighted sum of potential_terms, added in POTENTIAL_WEIGHTS order.

    The default ranking key. It is computed from the prediction's own fields
    and the node's counts, so it does not depend on which other candidates
    matched, on their order, or on `max_predictions`, and no term falls as the
    unobserved future of a pattern grows.
    """
    score = 0.0
    for weight, term in zip(_POTENTIAL_WEIGHT_VALUES, _potential_term_values(prediction, observation, node)):
        score += weight * term
    return score


def _name_order(predictions: Sequence[Mapping[str, Any]]) -> list[int]:
    """Indices of `predictions` in pattern-name order: the order of every ensemble sum."""
    return sorted(range(len(predictions)), key=lambda i: predictions[i]['name'])


def _posteriors(odds_bits: Sequence[float], order: Sequence[int]) -> tuple[list[float], float]:
    """(posterior of every candidate, chance posterior); see bayesian_posteriors."""
    top = 0.0                                             # the chance hypothesis sits at 0 bits
    for i in order:
        if odds_bits[i] > top:
            top = odds_bits[i]
    total = 2.0 ** (0.0 - top)
    for i in order:
        total += 2.0 ** (odds_bits[i] - top)
    posteriors = [0.0] * len(odds_bits)
    for i in order:
        posteriors[i] = 2.0 ** (odds_bits[i] - top) / total
    return posteriors, 2.0 ** (0.0 - top) / total


def bayesian_posteriors(names: Sequence[str], odds_bits: Sequence[float]) -> tuple[dict[str, float], float]:
    """`bayesian_posterior` for every candidate, and the chance posterior.

        posterior = 2^G / (1 + sum of 2^G over the candidates)
        chance    = 1   / (1 + sum of 2^G over the candidates)

    `names` and `odds_bits` are parallel: pattern name and good-odds of every
    candidate above the recall threshold. The posteriors and the chance
    posterior add up to 1. A lone candidate gets 2^G / (1 + 2^G), and with no
    candidate at all the chance posterior is 1.

    The sum runs in pattern-name order, with every power taken relative to the
    largest exponent so that nothing overflows.
    """
    order = sorted(range(len(names)), key=lambda i: names[i])
    posteriors, chance = _posteriors(odds_bits, order)
    return {names[i]: posteriors[i] for i in order}, chance


def _next_events(
    predictions: Sequence[Mapping[str, Any]],
    order: Sequence[int],
) -> tuple[list[float], dict[tuple, list], Optional[float]]:
    """(share of every prediction, {next event: [probability, supporting patterns]}, ends_here).

    share = e^potential / sum of e^potential over every prediction. A prediction
    with a future adds its share to the probability of its next event; a
    prediction without one adds it to `ends_here`, the probability that nothing
    follows, and its own entry in the returned shares is 0.0. The probabilities
    and `ends_here` add up to 1. `ends_here` is None when there is no
    prediction. `order` is the pattern-name order: every sum runs in it. Every
    exponential is taken relative to the largest potential.
    """
    shares = [0.0] * len(predictions)
    events: dict[tuple, list] = {}
    if not predictions:
        return shares, events, None
    top = max(prediction['potential'] for prediction in predictions)
    total = 0.0
    for i in order:
        total += math.exp(predictions[i]['potential'] - top)
    ends_here = 0.0
    for i in order:
        share = math.exp(predictions[i]['potential'] - top) / total
        if predictions[i]['future']:
            shares[i] = share
            entry = events.setdefault(tuple(predictions[i]['future'][0]), [0.0, 0])
            entry[0] += share
            entry[1] += 1
        else:
            ends_here += share
    return shares, events, ends_here


def _future_potentials(events: Mapping[tuple, Sequence]) -> list[dict[str, Any]]:
    return [
        {'next_event': list(event), 'probability': probability, 'supporting_patterns': supporters}
        for event, (probability, supporters) in sorted(events.items(), key=lambda item: (-item[1][0], item[0]))
    ]


def _predictive_information(
    predictions: Sequence[Mapping[str, Any]],
    shares: Sequence[float],
    events: Mapping[tuple, Sequence],
    node: NodeStatistics,
) -> list[float]:
    information = [0.0] * len(predictions)
    for i, prediction in enumerate(predictions):
        if shares[i] > 0.0:          # no future, or a share that underflowed: nothing to add
            event = tuple(prediction['future'][0])
            chance_bits = 0.0
            for symbol in event:
                chance_bits += node.rarity_bits[symbol]
            information[i] = shares[i] * (math.log2(events[event][0]) + chance_bits)
    return information


def future_potentials(predictions: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """`future_potentials`: the probability of each next event the ensemble proposes.

        P(E | STM) = sum of e^potential over the predictions whose next event is E
                     / sum of e^potential over every prediction

    The next event of a prediction is the first event of its `future`. Returns
    [{'next_event': [...], 'probability': P, 'supporting_patterns': n}], most
    probable first; equal probabilities go to the event that sorts first. A
    prediction with no future proposes no event: its weight goes to `ends_here`,
    and the probabilities add up to 1 - ends_here. Empty when no prediction has
    a future.

    `predictions` are every candidate above the recall threshold, each with its
    `potential` already set.
    """
    _, events, _ = _next_events(predictions, _name_order(predictions))
    return _future_potentials(events)


def ends_here(predictions: Sequence[Mapping[str, Any]]) -> Optional[float]:
    """`ends_here`: the probability that no event follows the STM.

        sum of e^potential over the predictions that have no future
        / sum of e^potential over every prediction

    A prediction has no future when its pattern ends where the observation
    ends. With the probabilities of `future_potentials` it adds up to 1. None
    when there is no prediction.

    `predictions` are every candidate above the recall threshold, each with its
    `potential` already set.
    """
    _, _, share = _next_events(predictions, _name_order(predictions))
    return share


def predictive_information(
    predictions: Sequence[Mapping[str, Any]],
    node: NodeStatistics,
) -> dict[str, float]:
    """`predictive_information` of every prediction, in bits, by pattern name.

        share x log2(P(E | STM) / q(E))

    E is the prediction's next event, P(E | STM) its probability in
    `future_potentials`, `share` the prediction's own part of that probability
    (e^potential over its sum across every prediction), and q(E) the chance
    probability of the event: the product of q(s) over its symbols. Over the
    predictions the values add up to the sum, over the events proposed, of
    P(E | STM) x log2(P(E | STM) / q(E)): the information the STM carries about
    which event follows, measured against chance. A prediction with no future
    proposes no event and carries none: 0.0.
    """
    shares, events, _ = _next_events(predictions, _name_order(predictions))
    information = _predictive_information(predictions, shares, events, node)
    return {prediction['name']: information[i] for i, prediction in enumerate(predictions)}


def confluence(
    pattern_events: Sequence[Sequence[str]],
    frequency: int,
    total_pattern_frequency: int,
    node: NodeStatistics,
) -> float:
    """`confluence`: how far the pattern is from a chance co-occurrence, in bits.

        log2(f / F) + sum over the pattern's symbols of log2(1 / q(s))

    The base-2 logarithm of how many times more often the pattern was learned
    than chance alone would have produced it. It is a property of the pattern
    and the node, the same for every prediction of the pattern, and it is the
    ceiling of good-odds: an exact, complete observation of the pattern scores
    `confluence` less log2(1 / (1 - e)) = 0.074 bits per symbol.

    Symbols are added in pattern order.
    """
    bits = math.log2(frequency / total_pattern_frequency)
    for event in pattern_events:
        for symbol in event:
            bits += node.rarity_bits[symbol]
    return bits


def tfidf_score(symbol_shares: Mapping[str, float], node: NodeStatistics) -> float:
    """`tfidf_score`: mean of TF x IDF over the pattern's distinct symbols.

    `symbol_shares` is the pattern's TF vector: symbol -> its share of the
    pattern's symbols. IDF(s) = log2(patterns / patterns holding s) + 1, with a
    symbol the node does not hold counted as held by one pattern. Symbols are
    added in sorted order.
    """
    if not symbol_shares:
        return 0.0
    total = 0.0
    for symbol in sorted(symbol_shares):
        holding = node.patterns_holding(symbol) or 1
        total += symbol_shares[symbol] * (math.log2(node.pattern_count / holding) + 1)
    return total / len(symbol_shares)


def itfdf_similarity(
    observation: Observation,
    present: Sequence[Sequence[str]],
    frequency: int,
    candidate_frequency: int,
    node: NodeStatistics,
) -> float:
    """`itfdf_similarity`: 1 - distance x frequency / candidate_frequency.

    `distance` is 1 minus the cosine between the STM and `present` as bags of
    symbols, each symbol weighted by the share of the node's patterns that hold
    it. `candidate_frequency` is the sum of the frequencies of every candidate
    above the recall threshold. The cosine is held to [0, 1], so an STM that
    equals `present` scores exactly 1.0. Symbols are added in sorted order.
    """
    if candidate_frequency <= 0:
        return 0.0
    here = Counter(chain.from_iterable(present))
    dot = 0.0
    state_squares = 0.0
    for symbol in observation.symbols:
        weight = node.pattern_share(symbol)
        state_squares += (weight * observation.counts[symbol]) ** 2
        if symbol in here:
            dot += weight * observation.counts[symbol] * weight * here[symbol]
    here_squares = 0.0
    for symbol in sorted(here):
        here_squares += (node.pattern_share(symbol) * here[symbol]) ** 2
    denominator = math.sqrt(state_squares * here_squares)
    cosine = min(dot / denominator, 1.0) if denominator > 0.0 else 0.0
    return 1.0 - (1.0 - cosine) * frequency / candidate_frequency


class EnsembleScores(NamedTuple):
    """What score_ensemble returns beside the fields it sets on each prediction."""
    future_potentials: list[dict[str, Any]]
    chance_posterior: float
    # Probability that no event follows; None when there is no candidate.
    ends_here: Optional[float]
    # Sum of the candidates' frequencies, and the node total the priors were
    # taken against. The second is the larger of the node's counter and the
    # first, so a prior never exceeds 1.
    candidate_frequency: int
    total_pattern_frequency: int


def score_ensemble(
    predictions: Sequence[dict[str, Any]],
    observation: Observation,
    node: NodeStatistics,
) -> EnsembleScores:
    """Set the scores that need every candidate, and return the ensemble's own.

    `predictions` are every candidate above the recall threshold, each with its
    `frequency` already read; `observation` is the STM they were matched
    against. Sets `bayesian_prior`, `bayesian_likelihood`, `good_odds`,
    `potential`, `bayesian_posterior` and `predictive_information` on each, in
    place, and returns `future_potentials`, the chance posterior, `ends_here`
    and the totals used.

    Ranking and cutting to `max_predictions` come after this, never before: the
    posterior, `future_potentials` and `predictive_information` are sums over
    the candidates, and cutting first would make them depend on the cut.
    """
    candidate_frequency = 0
    for prediction in predictions:
        candidate_frequency += prediction['frequency']
    total_pattern_frequency = max(node.total_pattern_frequency, candidate_frequency)

    odds_bits = []
    for prediction in predictions:
        prior = prediction['frequency'] / total_pattern_frequency
        evidence_bits = weight_of_evidence(prediction, node)
        prediction['bayesian_prior'] = prior
        prediction['bayesian_likelihood'] = evidence_bits
        prediction['good_odds'] = good_odds(prior, evidence_bits)
        prediction['potential'] = potential(prediction, observation, node)
        odds_bits.append(prediction['good_odds'])

    order = _name_order(predictions)
    posteriors, chance_posterior = _posteriors(odds_bits, order)
    shares, events, ends_here = _next_events(predictions, order)
    information = _predictive_information(predictions, shares, events, node)
    for i, prediction in enumerate(predictions):
        prediction['bayesian_posterior'] = posteriors[i]
        prediction['predictive_information'] = information[i]

    return EnsembleScores(
        _future_potentials(events),
        chance_posterior,
        ends_here,
        candidate_frequency,
        total_pattern_frequency,
    )
