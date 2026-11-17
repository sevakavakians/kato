"""The suites: which nodes are built, and which held-out queries are asked of each.

A node is a list of sequences to learn. A query set is a list of queries on one
node; a query is an STM and the event that followed it, or None when the
sequence had ended. Everything is built deterministically from fixed seeds, so
query i of a set is the same on every machine, and asking for more queries
extends a set without changing the ones already drawn.
"""

from __future__ import annotations

import bisect
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from benchmarks.ranking import datasets
from benchmarks.ranking.generated import Library, Rng

# A full response holds at most this many predictions (KATO caps `max_predictions`).
# A guide node is kept below it, so one response per query holds every candidate.
RESPONSE_CAP = 10000
STM_EVENTS = 5


@dataclass(frozen=True)
class QuerySet:
    key: str
    node: str
    label: str            # how the report names the condition
    group: str            # 'situation' (generated), 'data' (a public data set) or 'ending'
    queries: list         # [(stm_events, answer_event or None), ...]


@dataclass(frozen=True)
class Node:
    key: str
    label: str
    kind: str             # how the report groups it: 'Generated', 'System logs', ...
    dataset: str          # key in datasets.DATASETS, or '' for generated data
    in_fit: bool          # whether the weights of `potential` were fitted on this kind of data
    sequences: list       # what the node learns, in order
    query_sets: list


@dataclass(frozen=True)
class NodePlan:
    """A node that has not been built yet. `build` may download a data set."""
    key: str
    label: str
    kind: str
    dataset: str
    in_fit: bool
    set_keys: tuple
    build: Callable[[Path, int, Callable], Node] = field(repr=False, compare=False, default=None)


def seed_for(*parts: str) -> int:
    """A fixed 64-bit seed for a named thing."""
    return int.from_bytes(hashlib.sha256("/".join(parts).encode()).digest()[:8], "big")


def pattern_key(sequence: list) -> tuple:
    """What makes two learned sequences the same pattern: their events, symbols sorted."""
    return tuple(tuple(sorted(event)) for event in sequence)


def distinct_patterns(sequences: list) -> int:
    return len({pattern_key(sequence) for sequence in sequences})


# ----------------------------------------------------------------------------
# queries on held-out sequences of a public data set

def next_event_queries(held_out: list, seed: int, count: int, stm_events: int = STM_EVENTS,
                       skip_answers: frozenset = frozenset()) -> list:
    """Positions drawn uniformly, without repeats, from every position of the held-out sequences
    that has two or more events before it and lies in the first MAX_EVENTS.

    The STM is the `stm_events` events before the position, or all of them when
    fewer came before; the answer is the event at the position.
    """
    offsets, total = [], 0
    for sequence in held_out:
        offsets.append(total)
        total += max(0, min(len(sequence), datasets.MAX_EVENTS) - 2)
    rng, taken, out = Rng(seed), set(), []
    while len(out) < count and len(taken) < total:
        x = rng.below(total)
        if x in taken:
            continue
        taken.add(x)
        sequence = held_out[bisect.bisect_right(offsets, x) - 1]
        at = 2 + x - offsets[bisect.bisect_right(offsets, x) - 1]
        answer = sequence[at]
        if len(answer) == 1 and answer[0] in skip_answers:
            continue
        out.append((sequence[max(0, at - stm_events):at], answer))
    return out


def ending_queries(held_out: list, seed: int, count: int, stm_events: int = STM_EVENTS) -> list:
    """Held-out sequences that are complete within MAX_EVENTS, observed to their last event."""
    complete = [sequence for sequence in held_out if 2 <= len(sequence) <= datasets.MAX_EVENTS]
    rng, taken, out = Rng(seed), set(), []
    while len(out) < count and len(taken) < len(complete):
        x = rng.below(len(complete))
        if x in taken:
            continue
        taken.add(x)
        out.append((complete[x][-stm_events:], None))
    return out


# ----------------------------------------------------------------------------
# plans

def _dataset_plan(suite: str, key: str) -> NodePlan:
    dataset = datasets.DATASETS[key]
    skip = frozenset({datasets.symbol("<unk>")}) if key == "wikitext" else frozenset()

    def build(data_dir: Path, count: int, log=print) -> Node:
        split = dataset.read(data_dir, log)
        return Node(
            key=key, label=dataset.title, kind=dataset.kind, dataset=key, in_fit=dataset.in_fit,
            sequences=split.learn,
            query_sets=[
                QuerySet(f"{key}.next", key, dataset.title, "data",
                         next_event_queries(split.held_out, seed_for(suite, key, "next"), count,
                                            skip_answers=skip)),
                QuerySet(f"{key}.end", key, dataset.title, "ending",
                         ending_queries(split.held_out, seed_for(suite, key, "end"), max(1, count // 2))),
            ],
        )

    return NodePlan(key=key, label=dataset.title, kind=dataset.kind, dataset=key, in_fit=dataset.in_fit,
                    set_keys=(f"{key}.next", f"{key}.end"), build=build)


def _generated_plan(suite: str, key: str, label: str, library: dict, sets: tuple, windows: int = 0) -> NodePlan:
    """`sets` is ((set name, report label, group, query arguments), ...)."""

    def build(data_dir: Path, count: int, log=print) -> Node:
        made = Library(seed=seed_for(suite, library.get("shares_library", key), "library"),
                       **{k: v for k, v in library.items() if k != "shares_library"})
        sequences = made.learned_as_windows(windows) if windows else made.learned_as_units()
        query_sets = []
        for name, set_label, group, arguments in sets:
            wanted = max(1, count // 2) if group == "ending" else count
            query_sets.append(QuerySet(
                f"{key}.{name}", key, set_label, group,
                made.queries(seed_for(suite, library.get("shares_library", key), name), wanted, **arguments)))
        return Node(key=key, label=label, kind="Generated", dataset="", in_fit=True,
                    sequences=sequences, query_sets=query_sets)

    return NodePlan(key=key, label=label, kind="Generated", dataset="", in_fit=True,
                    set_keys=tuple(f"{key}.{name}" for name, _, _, _ in sets), build=build)


_BASE = {"vocabulary": 1000, "symbol_skew": 2, "patterns": 3000, "pattern_skew": 2, "occurrences_per_pattern": 4}
_MID = {"kind": "mid", "stm_events": STM_EVENTS, "noise": 5}
_STREAM = {"vocabulary": 1000, "symbol_skew": 2, "patterns": 400, "pattern_skew": 2,
           "occurrences_per_pattern": 4, "shares_library": "gen_stream"}


def guide_plans() -> list:
    """The guide suite: generated data that changes one condition at a time, and seven public
    data sets. The weights of `potential` were fitted on generated data, system logs, click
    streams and text; the other four kinds of data it has never seen."""
    suite = "guide"
    plans = [
        _generated_plan(suite, "gen_base", "Generated: the base setting", _BASE, (
            ("mid5", "STM of 5 events, mid-pattern", "situation", _MID),
            ("mid2", "STM of 2 events", "situation", {**_MID, "stm_events": 2}),
            ("mid10", "STM of 10 events", "situation", {**_MID, "stm_events": 10}),
            ("first5", "First 5 events of a pattern", "situation", {**_MID, "kind": "first"}),
            ("share25", "First quarter of a pattern", "situation",
             {"kind": "share", "share": 25, "events_between": (16, 60), "noise": 5}),
            ("share75", "First three quarters of a pattern", "situation",
             {"kind": "share", "share": 75, "events_between": (16, 60), "noise": 5}),
            ("noise0", "No noise", "situation", {**_MID, "noise": 0}),
            ("noise20", "20% noise", "situation", {**_MID, "noise": 20}),
            ("span", "STM across two patterns", "situation", {**_MID, "kind": "span"}),
            ("end", "Generated: the base setting", "ending", {**_MID, "kind": "end"}),
        )),
    ]
    plans += [_dataset_plan(suite, key) for key in ("hdfs", "msnbc", "wikitext", "bpi2012", "sepsis", "bach", "unix")]
    plans += [
        _generated_plan(suite, "gen_flat", "Generated: patterns learned equally often",
                        {**_BASE, "pattern_skew": 0},
                        (("mid5", "Patterns learned equally often", "situation", _MID),)),
        _generated_plan(suite, "gen_skewed", "Generated: strongly skewed pattern frequencies",
                        {**_BASE, "pattern_skew": 3},
                        (("mid5", "Strongly skewed frequencies", "situation", _MID),)),
        _generated_plan(suite, "gen_multi", "Generated: events of 1 to 5 symbols",
                        {**_BASE, "per_event": (1, 2, 3, 4, 5)},
                        (("mid5", "Events of 1 to 5 symbols", "situation", _MID),)),
        _generated_plan(suite, "gen_smallvocab", "Generated: a vocabulary of 50 symbols",
                        {**_BASE, "vocabulary": 50},
                        (("mid5", "Vocabulary of 50 symbols", "situation", _MID),)),
        _generated_plan(suite, "gen_stream_units", "Generated: a stream, pattern boundaries given", _STREAM,
                        (("stream", "Stream, boundaries given", "situation",
                          {**_MID, "kind": "stream"}),)),
        _generated_plan(suite, "gen_stream_windows", "Generated: a stream, pattern boundaries not given", _STREAM,
                        (("stream", "Stream, boundaries not given", "situation",
                          {**_MID, "kind": "stream"}),), windows=10),
    ]
    return plans


def smoke_plans() -> list:
    """A two-minute check of the whole path: one small generated node, no downloads."""
    suite = "smoke"
    library = {"vocabulary": 200, "symbol_skew": 2, "patterns": 80, "pattern_skew": 2,
               "occurrences_per_pattern": 3, "max_events": 30}
    return [
        _generated_plan(suite, "gen_small", "Generated: a small library", library, (
            ("mid5", "STM of 5 events, mid-pattern", "situation", _MID),
            ("end", "Generated: a small library", "ending", {**_MID, "kind": "end"}),
        )),
        _generated_plan(suite, "gen_small_multi", "Generated: a small library, events of 1 to 3 symbols",
                        {**library, "per_event": (1, 2, 3)},
                        (("mid5", "Events of 1 to 3 symbols", "situation", _MID),)),
    ]


SUITES = {"guide": guide_plans, "smoke": smoke_plans}
SUITE_QUERIES = {"guide": 200, "smoke": 12}
