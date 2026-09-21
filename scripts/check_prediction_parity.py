#!/usr/bin/env python3
"""Capture and compare full prediction payloads, to prove a change is behaviour-preserving.

KATO guarantees identical outputs for identical inputs. Several planned changes
to the prediction path touch code that feeds `past`/`present`/`missing`/`extras`
and the per-pattern metrics, so "the tests still pass" is not a strong enough
gate — the suite pins particular shapes, not every field of every prediction.

Usage:
    ./start.sh
    python scripts/check_prediction_parity.py --capture before.json
    # ... make a change, rebuild, redeploy ...
    python scripts/check_prediction_parity.py --compare before.json

The corpus is built to exercise the paths a change could plausibly disturb:

  * multi-symbol events and ragged event widths (segmentation)
  * symbols repeated across events (forces refine_alignment_by_events past its
    early-out, which is where alignment ambiguity is resolved)
  * patterns learned more than once, so `frequency > 1`
  * non-empty `emotives` and `metadata`

Those last two matter more than they look. Metadata reaches a prediction only
through `frequency` and `emotives`; if every pattern had frequency 1 and no
emotives, a regression that dropped metadata entirely would produce identical
output and this tool would pass vacuously. The corpus is built so that cannot
happen — `--self-check` asserts it.
"""

import argparse
import json
import sys
from pathlib import Path

import requests

BASE = "http://localhost:8000"
NODE = "parity_check_node"

# One keep-alive connection for the whole run, which pins every request to a
# single uvicorn worker.
#
# This is deliberate and load-bearing. Each worker memoises the node's symbol
# statistics and global counters (OptimizedQueryManager._symbol_cache and
# PatternProcessor._global_metadata_cache) and invalidates them only when *it*
# serves a learn. A worker that did not serve the learn keeps answering from
# stale statistics, so the metrics derived from them -- confluence,
# normalized_entropy, global_normalized_entropy, itfdf_similarity -- come back
# with materially different values depending on which worker answered
# (confluence 0.49 vs 0.20 for the same query, observed).
#
# That is a real cross-worker coherence problem, but it is NOT what this tool is
# for. Mixing it in would make the gate flap and hide the thing we are actually
# checking: whether a code change altered the computation. Pinning removes that
# variable. Run against KATO_WORKERS=1 if you want to rule it out entirely.
SESSION = requests.Session()

# (events, times_to_learn, emotives, metadata)
CORPUS = [
    # ragged widths, no repeats
    ([["alpha", "beta"], ["gamma"], ["delta", "epsilon", "zeta"]], 1,
     {"joy": 0.8, "trust": 0.3}, {"kind": "ragged"}),
    # repeated symbols across events -> exercises alignment refinement
    ([["x", "y"], ["y", "z"], ["x"], ["w", "y", "z"]], 3,
     {"joy": -0.4}, {"kind": "repeats"}),
    # long single-symbol chain
    ([["s1"], ["s2"], ["s3"], ["s4"], ["s5"], ["s6"]], 2,
     {"arousal": 0.55, "valence": -0.65}, {"kind": "chain"}),
    # wide events
    ([["m1", "m2", "m3", "m4"], ["n1", "n2"]], 1,
     {}, {"kind": "wide"}),
    # shares a prefix with the ragged pattern -> near-twin disambiguation
    ([["alpha", "beta"], ["gamma"], ["other"]], 5,
     {"joy": 0.1}, {"kind": "near_twin"}),
    # single event
    ([["solo"]], 1, {"calm": 0.9}, {"kind": "solo"}),
]

# A block of patterns that all match one probe, so a low max_predictions makes
# the top-K prune actually fire. Without this the corpus is far below
# max_predictions * 3 and the pruned path -- where metadata is attached only to
# the survivors -- is never exercised, so a gate built on the corpus above would
# pass while testing nothing.
CROWD_SIZE = 14
CROWD = [
    ([["crowd", "head"], [f"tail{i:02d}"]], 1 + (i % 4),
     {"joy": round(0.1 * (i % 7), 3)}, {"kind": "crowd", "i": str(i)})
    for i in range(CROWD_SIZE)
]
CORPUS = CORPUS + CROWD

# Observations to probe with. Each is a list of events.
PROBES = [
    [["alpha", "beta"], ["gamma"], ["delta", "epsilon", "zeta"]],   # exact, full
    [["alpha", "beta"]],                                            # prefix only
    [["alpha", "beta"], ["gamma"]],                                 # near-twin ambiguity
    [["gamma"], ["delta", "epsilon", "zeta"]],                      # suffix
    [["x", "y"], ["y", "z"]],                                       # repeats, partial
    [["y", "z"], ["x"]],                                            # repeats, mid-start
    [["x"]],                                                        # lone repeated symbol
    [["s2"], ["s3"], ["s4"]],                                       # middle of the chain
    [["s1"], ["s3"]],                                               # gap
    [["m1", "m2", "m3", "m4"], ["n1", "n2"]],                       # wide, exact
    [["m1", "m4"], ["n2"]],                                         # wide, dropped symbols
    [["alpha", "beta", "UNEXPECTED"], ["gamma"]],                   # extras
    [["solo"]],                                                     # single symbol fast path
    [["nothing", "matches", "here"]],                               # no match
]

# ---------------------------------------------------------------------------
# Boundary corpus (--boundary)
#
# The corpus above cannot test the recall-safe candidate bound
# (kato/filters/recall_bounds.py). Its patterns top out around 9 tokens and it
# is probed at the default recall_threshold, where the bound's length window is
# [1, ~190] -- every pattern sits far inside it, so the bound never makes a
# decision and a gate built on it would pass while testing nothing.
#
# These patterns are placed exactly ON the boundary, and one token either side
# of it, using the scorer's own identity:
#
#     similarity = 2M/(P+L) = r   <=>   P = 2M/r - L
#
# where M is the LCS length, P the pattern's token count and L the probe's.
# The "exactly r" rows are the ones that matter: they are what an off-by-one or
# a float-truncation in the bound would wrongly discard. Computing
# int(6 * 1.9 / 0.1) in floats yields 113, not 114, and would drop BOUND_M6_AT.
BOUNDARY_L = 6
BOUNDARY_Q = [f"q{i}" for i in range(1, BOUNDARY_L + 1)]
BOUNDARY_PROBE = [[q] for q in BOUNDARY_Q]   # L = 6 flattened tokens


def _boundary_pattern(shared, total, tag):
    """Build a pattern with LCS=`shared` against BOUNDARY_PROBE and `total` tokens.

    The `shared` probe tokens go one per event in probe order, so sorting within
    an event cannot disturb their relative order and the LCS is exactly
    `shared`. Filler tokens are unique to this pattern, so they add length
    without adding matches. Patterns need at least two events to be learnable.
    """
    events, used = [], 0
    filler = 0
    per_event = max(1, (total - shared) // max(shared, 2))
    for i in range(shared):
        event = [BOUNDARY_Q[i]]
        for _ in range(per_event):
            if used + len(event) + (shared - i - 1) < total:
                event.append(f"{tag}f{filler}")
                filler += 1
        used += len(event)
        events.append(event)
    while used < total:                      # top up, keeping >= 2 events
        event = []
        for _ in range(min(per_event or 1, total - used)):
            event.append(f"{tag}f{filler}")
            filler += 1
        used += len(event)
        events.append(event)
    if len(events) < 2:
        events.append([f"{tag}f{filler}"])
        used += 1
    assert sum(len(e) for e in events) == used
    return events


def _make_boundary_corpus():
    """(events, times, emotives, metadata) rows straddling the bound."""
    rows = []
    # (shared M, total P, label). P chosen so similarity is exactly / just off r.
    specs = [
        (6, 114, "m6_at_010"),    # 12/120 = 0.100000 -> kept at r=0.1
        (6, 115, "m6_below010"),  # 12/121 = 0.099174 -> below r=0.1
        (6, 113, "m6_above010"),  # 12/119 = 0.100840 -> above r=0.1
        (1, 14,  "m1_at_010"),    #  2/20  = 0.100000 -> kept at r=0.1
        (1, 15,  "m1_below010"),  #  2/21  = 0.095238 -> below r=0.1
        (6, 18,  "m6_at_050"),    # 12/24  = 0.500000 -> kept at r=0.5
        (6, 19,  "m6_below050"),  # 12/25  = 0.480000 -> below r=0.5
    ]
    for i, (shared, total, label) in enumerate(specs):
        events = _boundary_pattern(shared, total, label)
        assert sum(len(e) for e in events) == total, (label, sum(len(e) for e in events))
        rows.append((events, 1 + (i % 3), {"joy": round(0.05 * i, 3)},
                     {"kind": "boundary", "label": label}))
    # A pattern repeating one probe token: token-overlap counts 20 (multiplicity)
    # but the LCS is 1, so the bound keeps it and the scorer rejects it. Proves
    # the bound is permissive where it must be, and that the scorer still decides.
    rows.append(([[BOUNDARY_Q[0]] * 10, [BOUNDARY_Q[0]] * 10], 2,
                 {"joy": 0.4}, {"kind": "boundary", "label": "repeat_x20"}))
    return rows


BOUNDARY_CORPUS = _make_boundary_corpus()

# (probe, recall_threshold). Each threshold puts a different set of the rows
# above exactly on the edge.
BOUNDARY_PROBES = [
    (BOUNDARY_PROBE, 0.1),
    (BOUNDARY_PROBE, 0.5),
    (BOUNDARY_PROBE, 0.01),
    (BOUNDARY_PROBE[:3], 0.1),
    (BOUNDARY_PROBE[:3], 0.5),
]


# Probes run with a low max_predictions so max_predictions * 3 falls below the
# number of matching patterns and the top-K prune fires.
PRUNED_PROBES = [
    ([["crowd", "head"]], 2),          # 14 candidates -> prune to 6 -> return 2
    ([["crowd", "head"], ["tail03"]], 3),
    ([["crowd", "head"]], 1),
]


def call(method, path, payload=None, timeout=180):
    response = SESSION.request(method, BASE + path, json=payload, timeout=timeout)
    response.raise_for_status()
    return response.json()


def new_session(config=None):
    return call("POST", "/sessions", {"node_id": NODE, "config": config or {}})["session_id"]


def build_corpus(rows=None):
    """Clear the node and rebuild it deterministically."""
    session = new_session()
    call("POST", f"/sessions/{session}/clear-all", {})
    call("DELETE", f"/sessions/{session}")

    session = new_session()
    learned = []
    for events, times, emotives, metadata in (CORPUS if rows is None else rows):
        for _ in range(times):
            call("POST", f"/sessions/{session}/clear-stm", {})
            for i, event in enumerate(events):
                # emotives/metadata on the last event of each pattern
                body = {"strings": sorted(event)}
                if i == len(events) - 1:
                    body["emotives"] = emotives
                    body["metadata"] = metadata
                call("POST", f"/sessions/{session}/observe", body)
            result = call("POST", f"/sessions/{session}/learn", {})
            learned.append(result.get("pattern_name"))
    call("DELETE", f"/sessions/{session}")
    return learned


def _run_probe(probe, max_predictions=None, recall_threshold=None):
    config = {}
    if max_predictions:
        config["max_predictions"] = max_predictions
    if recall_threshold is not None:
        config["recall_threshold"] = recall_threshold
    session = new_session(config)
    for event in probe:
        call("POST", f"/sessions/{session}/observe", {"strings": sorted(event)})
    predictions = call("GET", f"/sessions/{session}/predictions")
    call("DELETE", f"/sessions/{session}")
    return {
        "probe": probe,
        "max_predictions": max_predictions,
        "recall_threshold": recall_threshold,
        # order is part of the contract, so it is NOT sorted here
        "predictions": predictions["predictions"],
        "future_potentials": predictions.get("future_potentials"),
        "count": predictions["count"],
    }


def capture(boundary=False):
    """Return the full prediction payload for every probe, in order."""
    if boundary:
        return [_run_probe(probe, recall_threshold=r) for probe, r in BOUNDARY_PROBES]
    snapshot = [_run_probe(probe) for probe in PROBES]
    snapshot += [_run_probe(probe, mp) for probe, mp in PRUNED_PROBES]
    return snapshot


def boundary_self_check(snapshot):
    """Fail loudly if the boundary corpus is not actually on the boundary.

    The whole point of these probes is that some prediction sits EXACTLY at
    recall_threshold -- that is the case an off-by-one or a float truncation in
    the candidate bound would wrongly discard. If none does, the gate proves
    nothing, which is exactly how the main corpus fails to test the bound.
    """
    problems = []
    at_boundary = 0
    for entry in snapshot:
        threshold = entry.get("recall_threshold")
        if threshold is None:
            continue
        for prediction in entry["predictions"]:
            similarity = prediction.get("similarity")
            if similarity is not None and abs(similarity - threshold) < 1e-9:
                at_boundary += 1
            if similarity is not None and similarity < threshold - 1e-9:
                problems.append(
                    f"probe at recall_threshold={threshold} returned a prediction with "
                    f"similarity={similarity!r}, below the threshold")
    if not at_boundary:
        problems.append(
            "no prediction sits exactly at its recall_threshold — the boundary corpus "
            "has drifted and this gate is vacuous")
    if not any(e["count"] for e in snapshot):
        problems.append("no boundary probe produced any prediction at all")
    return problems, at_boundary


def self_check(snapshot):
    """Fail loudly if the corpus cannot detect a metadata regression."""
    freqs, emotive_sets = set(), 0
    for entry in snapshot:
        for prediction in entry["predictions"]:
            freqs.add(prediction.get("frequency"))
            if prediction.get("emotives"):
                emotive_sets += 1
    problems = []
    if not any(f and f > 1 for f in freqs):
        problems.append(
            f"no prediction has frequency > 1 (saw {sorted(freqs)}) — a regression that "
            f"dropped metadata would be invisible")
    if emotive_sets == 0:
        problems.append(
            "no prediction carries non-empty emotives — a regression that dropped "
            "metadata would be invisible")
    if not any(e["count"] for e in snapshot):
        problems.append("no probe produced any prediction at all")

    # The pruned probes must actually have pruned, or the path where metadata is
    # attached to survivors only is untested.
    pruned = [e for e in snapshot if e.get("max_predictions")]
    if not pruned:
        problems.append("no pruned probes ran")
    elif not all(e["count"] == e["max_predictions"] for e in pruned):
        problems.append(
            "a pruned probe returned fewer predictions than max_predictions, so "
            "the corpus no longer forces the top-K prune to fire")
    elif not any(p.get("emotives") for e in pruned for p in e["predictions"]):
        problems.append(
            "pruned probes returned no emotives — metadata attachment after the "
            "prune would be untested")
    return problems, sorted(f for f in freqs if f is not None), emotive_sets


def diff(before, after):
    """Return a list of human-readable differences."""
    problems = []
    if len(before) != len(after):
        return [f"probe count changed: {len(before)} -> {len(after)}"]
    for i, (b, a) in enumerate(zip(before, after)):
        label = f"probe[{i}] {b['probe']}"
        if b["count"] != a["count"]:
            problems.append(f"{label}: count {b['count']} -> {a['count']}")
        if b.get("future_potentials") != a.get("future_potentials"):
            problems.append(f"{label}: future_potentials differ")
        bp, ap = b["predictions"], a["predictions"]
        if len(bp) != len(ap):
            problems.append(f"{label}: {len(bp)} -> {len(ap)} predictions")
            continue
        for j, (pb, pa) in enumerate(zip(bp, ap)):
            if pb == pa:
                continue
            keys = sorted(set(pb) | set(pa))
            for key in keys:
                if pb.get(key) != pa.get(key):
                    problems.append(
                        f"{label} pred[{j}] {pb.get('name', '?')[:12]} "
                        f"field '{key}': {pb.get(key)!r} -> {pa.get(key)!r}")
    return problems


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--capture", type=Path, help="build the corpus and write a snapshot")
    group.add_argument("--compare", type=Path, help="rebuild and diff against a snapshot")
    parser.add_argument("--keep", action="store_true", help="leave the corpus in place")
    parser.add_argument("--boundary", action="store_true",
                        help="use the boundary corpus, which places patterns exactly on "
                             "the recall-safe candidate bound's edge (and one token either "
                             "side of it). The default corpus sits far inside the bound, "
                             "so it cannot detect an off-by-one there.")
    parser.add_argument("--reuse", action="store_true",
                        help="query the existing corpus instead of rebuilding it "
                             "(isolates query-path determinism from learn-path determinism)")
    args = parser.parse_args()

    try:
        health = call("GET", "/health", timeout=10)
    except requests.RequestException as error:
        print(f"KATO unreachable at {BASE}: {error}\nStart it with ./start.sh")
        return 2
    worker_at_start = health.get("worker_pid")
    print(f"pinned to uvicorn worker pid {worker_at_start} (keep-alive)")

    corpus_label = "boundary" if args.boundary else "default"
    if args.reuse:
        print(f"reusing existing {corpus_label} corpus on node {NODE} ...")
    else:
        print(f"building {corpus_label} corpus on node {NODE} ...")
        build_corpus(BOUNDARY_CORPUS if args.boundary else None)
    snapshot = capture(boundary=args.boundary)

    if args.boundary:
        problems, at_boundary = boundary_self_check(snapshot)
        print(f"  {len(BOUNDARY_PROBES)} boundary probes, "
              f"{sum(e['count'] for e in snapshot)} predictions total")
        print(f"  predictions sitting exactly at recall_threshold: {at_boundary}")
    else:
        problems, freqs, emotive_count = self_check(snapshot)
        print(f"  {len(PROBES)} probes + {len(PRUNED_PROBES)} pruned probes, "
              f"{sum(e['count'] for e in snapshot)} predictions total")
        print(f"  frequencies seen: {freqs}; predictions carrying emotives: {emotive_count}")
    if problems:
        # In --capture mode this means the baseline would not be able to detect
        # a regression. In --compare mode it usually means the change under test
        # IS the regression -- a change that stops metadata reaching predictions
        # removes the very signal the corpus was built to carry.
        if args.compare:
            print("\nFAILED — the corpus no longer carries the signals a gate needs.")
            print("On a comparison run this usually means the change under test removed them:")
        else:
            print("\nCORPUS IS NOT A VALID GATE:")
        for problem in problems:
            print(f"  - {problem}")
        return 1 if args.compare else 2

    if not args.keep and not args.reuse:
        session = new_session()
        call("POST", f"/sessions/{session}/clear-all", {})
        call("DELETE", f"/sessions/{session}")

    if args.capture:
        args.capture.write_text(json.dumps(snapshot, indent=1, sort_keys=True))
        print(f"\n  wrote {args.capture}")
        return 0

    # If the keep-alive connection was re-established mid-run the requests moved
    # to another worker, whose cached symbol statistics may differ -- that shows
    # up as metric differences which are not a regression. Say so rather than
    # reporting a false failure.
    worker_at_end = call("GET", "/health", timeout=10).get("worker_pid")
    if worker_at_end != worker_at_start:
        print(f"\n  WARNING: served by worker {worker_at_start} then {worker_at_end}. "
              f"Cross-worker symbol-statistics staleness can make metrics differ for "
              f"reasons unrelated to any code change. Re-run before believing a failure.")

    baseline = json.loads(args.compare.read_text())
    problems = diff(baseline, snapshot)
    if problems:
        print(f"\nPREDICTIONS CHANGED — {len(problems)} difference(s):\n")
        for problem in problems[:40]:
            print(f"  {problem}")
        if len(problems) > 40:
            print(f"  ... and {len(problems) - 40} more")
        return 1
    print("\n  IDENTICAL — prediction output is unchanged")
    return 0


if __name__ == "__main__":
    sys.exit(main())
