"""Generated sequence libraries: one condition changed at a time.

A library is `patterns` distinct sequences of 2 to 100 events. Each is a chain
of motifs (short sub-sequences shared between patterns) and freshly drawn
symbols, so different patterns share stretches and one STM can match several of
them. Symbols and patterns are drawn with Zipf-distributed probabilities. The
node learns a number of occurrences drawn by pattern weight; a pattern never
drawn is unknown to it. A query draws a pattern by weight again, takes part of
it as the STM, and passes the STM through a noise channel. The answer is the
event that follows.

Everything here is integer arithmetic on a SplitMix64 stream: no floating
point, no `random` module, no NumPy. The same arguments give the same bytes on
any platform and any Python, which is what lets two runs of the benchmark be
compared query for query. KATO itself uses no random numbers.
"""

from __future__ import annotations

import bisect
import math

MASK64 = (1 << 64) - 1
NOISE_KINDS = ("drop", "insert", "substitute")


class Rng:
    """SplitMix64 (Steele, Lea and Flood, 2014). Integers only."""

    def __init__(self, seed: int):
        self.state = seed & MASK64

    def next(self) -> int:
        self.state = (self.state + 0x9E3779B97F4A7C15) & MASK64
        z = self.state
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & MASK64
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & MASK64
        return z ^ (z >> 31)

    def below(self, n: int) -> int:
        """An integer in [0, n). The bias of the multiply-shift is below n / 2**64."""
        return (self.next() * n) >> 64

    def percent(self, p: int) -> bool:
        """True with probability p / 100."""
        return self.below(100) < p


def zipf_weights(n: int, halves: int) -> list:
    """Integer weights proportional to 1 / rank ** (halves / 2), for rank 1 to n.

    `halves` 0 is uniform, 2 is the classic Zipf law, 3 is strongly skewed. The
    exponent is given in halves so the weights need only an integer square root.
    """
    if halves == 0:
        return [1] * n
    return [(1 << 60) // math.isqrt((rank ** halves) << 40) for rank in range(1, n + 1)]


class Sampler:
    """Draws an index with probability proportional to its integer weight."""

    def __init__(self, weights: list):
        self.cumulative = []
        total = 0
        for weight in weights:
            total += weight
            self.cumulative.append(total)
        self.total = total

    def draw(self, rng: Rng) -> int:
        return bisect.bisect_right(self.cumulative, rng.below(self.total))


def symbol_name(index: int) -> str:
    return f"s{index:05d}"


class Library:
    """A generated library, the occurrences a node learns from it, and queries on it.

    Args:
        seed: start of the SplitMix64 stream.
        vocabulary: number of symbols.
        symbol_skew: Zipf exponent of the symbols, in halves.
        patterns: number of distinct sequences in the library.
        pattern_skew: Zipf exponent of the patterns' probabilities, in halves.
        per_event: the event sizes to choose from, uniformly.
        occurrences_per_pattern: the node learns this many occurrences per library pattern.
    """

    def __init__(self, seed: int, vocabulary: int = 1000, symbol_skew: int = 2, patterns: int = 3000,
                 pattern_skew: int = 2, per_event: tuple = (1,), occurrences_per_pattern: int = 4,
                 min_events: int = 2, max_events: int = 100):
        rng = Rng(seed)
        self.vocabulary = vocabulary
        self.per_event = tuple(per_event)
        self.symbols = Sampler(zipf_weights(vocabulary, symbol_skew))
        motif_count = max(20, patterns // 20)
        self.motifs = [[self._event(rng) for _ in range(2 + rng.below(5))] for _ in range(motif_count)]
        # Log-uniform lengths: a length n is drawn with weight 1 / n.
        lengths = Sampler([(1 << 40) // n for n in range(min_events, max_events + 1)])
        seen, self.patterns = set(), []
        while len(self.patterns) < patterns:
            n = min_events + lengths.draw(rng)
            events = []
            while len(events) < n:
                if rng.below(2):
                    events.extend(self.motifs[rng.below(motif_count)])
                else:
                    events.append(self._event(rng))
            events = tuple(events[:n])
            if events not in seen:
                seen.add(events)
                self.patterns.append(events)
        # A pattern's rank is independent of its length: shuffle the weights (Fisher-Yates).
        weights = zipf_weights(patterns, pattern_skew)
        for i in range(patterns - 1, 0, -1):
            j = rng.below(i + 1)
            weights[i], weights[j] = weights[j], weights[i]
        self.by_weight = Sampler(weights)
        self.occurrences = [self.by_weight.draw(rng) for _ in range(occurrences_per_pattern * patterns)]

    def _event(self, rng: Rng) -> tuple:
        """One event: a sorted tuple of distinct symbols."""
        size = self.per_event[rng.below(len(self.per_event))]
        chosen = []
        while len(chosen) < size:
            name = symbol_name(self.symbols.draw(rng))
            if name not in chosen:
                chosen.append(name)
        return tuple(sorted(chosen))

    # ------------------------------------------------------------------ what the node learns

    def learned_as_units(self) -> list:
        """Each occurrence as one sequence: the node is told where a pattern starts and ends."""
        return [[list(event) for event in self.patterns[i]] for i in self.occurrences]

    def learned_as_windows(self, size: int) -> list:
        """The occurrences as one stream, cut every `size` events: boundaries unknown to the node.

        This is the node KATO's auto-learning builds with `max_pattern_length`
        set to `size` and `stm_mode` CLEAR. A trailing stretch shorter than
        `size` is not learned.
        """
        stream = [event for i in self.occurrences for event in self.patterns[i]]
        return [[list(event) for event in stream[start:start + size]]
                for start in range(0, len(stream) - size + 1, size)]

    # ------------------------------------------------------------------ queries

    def _noise(self, rng: Rng, events: list, percent: int) -> list:
        """The noise channel: with probability `percent`, a symbol is dropped, gains a random
        neighbour before it, or is replaced by a random symbol. Single-symbol events are
        dropped, preceded by a random event, or replaced as a whole."""
        out = []
        single = self.per_event == (1,)
        for event in events:
            if single:
                if rng.percent(percent):
                    kind = NOISE_KINDS[rng.below(3)]
                    if kind == "drop":
                        continue
                    out.append((symbol_name(self.symbols.draw(rng)),))
                    if kind == "insert":
                        out.append(event)
                    continue
                out.append(event)
                continue
            kept = []
            for name in event:
                if rng.percent(percent):
                    kind = NOISE_KINDS[rng.below(3)]
                    if kind == "drop":
                        continue
                    kept.append(symbol_name(self.symbols.draw(rng)))
                    if kind == "insert":
                        kept.append(name)
                    continue
                kept.append(name)
            if kept:
                out.append(tuple(sorted(set(kept))))
        return out

    def queries(self, seed: int, count: int, kind: str = "mid", stm_events: int = 5, noise: int = 5,
                share: int = 0, events_between: tuple = (0, 0)) -> list:
        """`count` queries as (STM events, answer). The answer is the next event, or None when the
        sequence has ended.

        kind  'mid'     the `stm_events` events before a position drawn uniformly inside a pattern
              'first'   a pattern's first `stm_events` events
              'share'   the first `share` percent of a pattern whose length in events lies in
                        `events_between`
              'span'    the end of one occurrence followed by the start of the next
              'stream'  the `stm_events` events before a position in a stream of occurrences,
                        wherever the boundaries fall
              'end'     a pattern's last `stm_events` events; nothing follows
        """
        rng = Rng(seed)
        out = []
        attempts = 0
        while len(out) < count:
            attempts += 1
            if attempts > 400 * count + 10000:
                raise RuntimeError(f"cannot draw {count} '{kind}' queries from this library")
            pattern = self.patterns[self.by_weight.draw(rng)]
            n, k = len(pattern), stm_events
            if kind == "mid":
                if n < k + 1:
                    continue
                at = k + rng.below(n - k)
                stm, answer = list(pattern[at - k:at]), pattern[at]
            elif kind == "first":
                if n < k + 1:
                    continue
                stm, answer = list(pattern[:k]), pattern[k]
            elif kind == "share":
                if not events_between[0] <= n <= events_between[1]:
                    continue
                at = max(1, (n * share + 50) // 100)
                if at >= n:
                    continue
                stm, answer = list(pattern[:at]), pattern[at]
            elif kind == "span":
                taken = 1 + rng.below(k - 1)             # events from the previous occurrence
                at = k - taken
                previous = self.patterns[self.by_weight.draw(rng)]
                if n < at + 1 or len(previous) < taken:
                    continue
                stm, answer = list(previous[-taken:]) + list(pattern[:at]), pattern[at]
            elif kind == "stream":
                stream = list(pattern)
                first = len(stream)
                for _ in range(2):
                    stream.extend(self.patterns[self.by_weight.draw(rng)])
                if first < k or len(stream) - first < 1:
                    continue
                at = first + rng.below(len(stream) - first)
                stm, answer = stream[at - k:at], stream[at]
            elif kind == "end":
                stm, answer = list(pattern[-k:]), None
            else:
                raise ValueError(f"unknown kind of query: {kind}")
            stm = self._noise(rng, stm, noise)
            if sum(len(event) for event in stm) < 2:
                continue
            out.append(([list(event) for event in stm], None if answer is None else list(answer)))
        return out
