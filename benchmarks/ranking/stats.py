"""The figures of the ranking benchmark, computed from a run's result files.

Everything here is arithmetic on the stored outcomes; nothing is re-asked of
KATO. A share is a count over a count. An interval is a 95% interval: Wilson
for one share, normal for a mean of shares and for a paired difference.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from benchmarks.ranking import store
from benchmarks.ranking.scoring import KEYS, NO_EVENT, RIGHT

Z = 1.959963984540054          # the 97.5th percentile of the standard normal
GUIDE_THRESHOLD = "0.1"        # the recall threshold the guidance table is read at


# ----------------------------------------------------------------------------
# loading

def load_run(run_dir: Path) -> dict:
    """A run's record and every query set it completed, in the suite's order."""
    run_dir = Path(run_dir)
    record = json.loads((run_dir / "run.json").read_text())
    sets = {}
    for node_key in record.get("node_order") or sorted(record["nodes"]):
        node = record["nodes"].get(node_key)
        if not node or "sets" not in node:
            continue
        for set_key in node.get("set_order") or sorted(node["sets"]):
            info = node["sets"][set_key]
            rows = [json.loads(line) for line in store.read_lines(run_dir / "sets", set_key)]
            if rows:
                sets[set_key] = {
                    "key": set_key, "node": node_key, "label": info["label"], "group": info["group"],
                    "kind": node["kind"], "in_fit": node["in_fit"], "dataset": node["dataset"], "rows": rows,
                }
    return {"dir": str(run_dir), "record": record, "sets": sets,
            "keys": record["settings"]["keys"], "thresholds": [str(t) for t in record["settings"]["thresholds"]]}


# ----------------------------------------------------------------------------
# shares and intervals

def wilson(successes: int, n: int) -> tuple:
    """(share, low, high) of the Wilson 95% interval; (None, None, None) for n = 0."""
    if n == 0:
        return (None, None, None)
    p = successes / n
    centre = (p + Z * Z / (2 * n)) / (1 + Z * Z / n)
    half = Z * math.sqrt(p * (1 - p) / n + Z * Z / (4 * n * n)) / (1 + Z * Z / n)
    return (p, max(0.0, centre - half), min(1.0, centre + half))


def share(flags: list) -> dict:
    """A share with its interval: {'p', 'lo', 'hi', 'n'}."""
    n = len(flags)
    p, lo, hi = wilson(sum(1 for flag in flags if flag), n)
    return {"p": p, "lo": lo, "hi": hi, "n": n}


def mean_of_shares(shares: list) -> dict:
    """The mean of several sets' shares, each set counting the same, with a normal interval
    that adds the sets' variances."""
    shares = [s for s in shares if s["p"] is not None]
    if not shares:
        return {"p": None, "lo": None, "hi": None, "n": 0}
    m = len(shares)
    p = sum(s["p"] for s in shares) / m
    se = math.sqrt(sum(s["p"] * (1 - s["p"]) / s["n"] for s in shares)) / m
    return {"p": p, "lo": max(0.0, p - Z * se), "hi": min(1.0, p + Z * se), "n": sum(s["n"] for s in shares)}


def paired(a: list, b: list) -> dict:
    """The difference of two shares measured on the same queries: mean of a_i - b_i and its
    standard error. `a` and `b` are lists of 0 and 1."""
    n = len(a)
    if n == 0:
        return {"d": None, "se": None, "n": 0}
    diffs = [x - y for x, y in zip(a, b)]
    d = sum(diffs) / n
    variance = sum((x - d) ** 2 for x in diffs) / (n - 1) if n > 1 else 0.0
    return {"d": d, "se": math.sqrt(variance / n), "n": n}


def mean_of_paired(pairs: list) -> dict:
    """The mean over sets of paired differences, with the sets' variances added."""
    pairs = [p for p in pairs if p["d"] is not None]
    if not pairs:
        return {"d": None, "se": None, "n": 0}
    m = len(pairs)
    return {"d": sum(p["d"] for p in pairs) / m, "se": math.sqrt(sum(p["se"] ** 2 for p in pairs)) / m,
            "n": sum(p["n"] for p in pairs)}


def interval(difference: dict) -> tuple:
    """(low, high) of a paired difference's 95% interval."""
    return (difference["d"] - Z * difference["se"], difference["d"] + Z * difference["se"])


def level(difference: dict) -> bool:
    """Whether a paired difference's 95% interval includes zero."""
    if difference["d"] is None:
        return False
    low, high = interval(difference)
    return low <= 0.0 <= high


def auroc(scores: list, positives: list):
    """Area under the ROC curve of `scores` for the flags `positives`; ties count half.
    None when one of the two classes is empty."""
    pairs = sorted(zip(scores, positives))
    n_pos = sum(1 for _, flag in pairs if flag)
    n_neg = len(pairs) - n_pos
    if n_pos == 0 or n_neg == 0:
        return None
    rank_sum, i = 0.0, 0
    while i < len(pairs):
        j = i
        while j < len(pairs) and pairs[j][0] == pairs[i][0]:
            j += 1
        mid_rank = (i + 1 + j) / 2
        rank_sum += mid_rank * sum(1 for k in range(i, j) if pairs[k][1])
        i = j
    return (rank_sum - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)


def median(values: list):
    values = sorted(values)
    if not values:
        return None
    mid = len(values) // 2
    return values[mid] if len(values) % 2 else (values[mid - 1] + values[mid]) / 2


def percentile(values: list, q: float):
    """The value at fraction q of the sorted list (nearest rank)."""
    values = sorted(values)
    if not values:
        return None
    return values[min(len(values) - 1, max(0, math.ceil(q * len(values)) - 1))]


# ----------------------------------------------------------------------------
# reading a query set

def column(query_set: dict, threshold: str, field: str) -> list:
    return [row["t"][threshold][field] for row in query_set["rows"]]


def flags(query_set: dict, threshold: str, measure: str, k: int) -> list:
    """Per query, 1 when ranking key `k` succeeds on `measure`, else 0.

    future   the top prediction that has a future names the right event
    top      the top prediction names the right event
    named    the top prediction names an event
    hit5     a prediction among the first five names the right event
    """
    rows = query_set["rows"]
    if measure == "future":
        return [int(row["t"][threshold]["future"][k] == RIGHT) for row in rows]
    if measure == "top":
        return [int(row["t"][threshold]["top"][k] == RIGHT) for row in rows]
    if measure == "named":
        return [int(row["t"][threshold]["top"][k] != NO_EVENT) for row in rows]
    if measure == "hit5":
        return [int(0 < row["t"][threshold]["rank"][k] <= 5) for row in rows]
    raise ValueError(measure)


def reciprocal_rank(query_set: dict, threshold: str, k: int) -> float:
    ranks = [row["t"][threshold]["rank"][k] for row in query_set["rows"]]
    return sum(1 / r for r in ranks if r) / len(ranks) if ranks else 0.0


def entry_flags(query_set: dict, threshold: str) -> list:
    """Per query, 1 when the top entry of `future_potentials` is the right event."""
    return [int(bool(row["t"][threshold]["fp_right"])) for row in query_set["rows"]]


def key_figures(query_set: dict, threshold: str, k: int) -> dict:
    """Everything the report shows for one ranking key on one query set."""
    top = flags(query_set, threshold, "top", k)
    named = flags(query_set, threshold, "named", k)
    answered = [row["t"][threshold] for row in query_set["rows"] if row["t"][threshold]["n"] > 0]
    return {
        "future": share(flags(query_set, threshold, "future", k)),
        "top": share(top),
        "named": share(named),
        "precision": share([t for t, n in zip(top, named) if n]),
        "hit5": share(flags(query_set, threshold, "hit5", k)),
        "mrr": reciprocal_rank(query_set, threshold, k),
        "tied": share([entry["tied"][k] > 1 for entry in answered]),
    }


def set_figures(query_set: dict, threshold: str) -> dict:
    """Figures of a query set that do not depend on the ranking key."""
    entries = [row["t"][threshold] for row in query_set["rows"]]
    return {
        "queries": len(entries),
        "empty": share([entry["n"] == 0 for entry in entries]),
        "oracle": share([entry["rank"][0] > 0 for entry in entries]),
        "candidates": sum(entry["n"] for entry in entries) / len(entries) if entries else None,
        "candidates_max": max((entry["n"] for entry in entries), default=None),
        "entry": share(entry_flags(query_set, threshold)),
        "capped": sum(1 for entry in entries if "capped" in entry),
    }


# ----------------------------------------------------------------------------
# cases: the conditions the guidance table has a row for

def cases(run: dict) -> list:
    """Each next-event query set is one case; four groups of sets come after them."""
    sets = run["sets"]
    out = []
    for query_set in sets.values():
        if query_set["group"] == "data":
            out.append({"key": query_set["key"], "label": query_set["label"], "kind": query_set["kind"],
                        "group": "data", "in_fit": query_set["in_fit"], "sets": [query_set["key"]]})
    for query_set in sets.values():
        if query_set["group"] == "situation":
            out.append({"key": query_set["key"], "label": query_set["label"], "kind": "Generated",
                        "group": "situation", "in_fit": True, "sets": [query_set["key"]]})
    return out


def groups(run: dict) -> list:
    data = [s for s in run["sets"].values() if s["group"] == "data"]
    situations = [s["key"] for s in run["sets"].values() if s["group"] == "situation"]
    out = []
    if situations:
        out.append({"key": "group.generated", "label": "Generated data, every situation", "sets": situations})
    if data:
        out.append({"key": "group.data", "label": "The public data sets", "sets": [s["key"] for s in data]})
    fitted = [s["key"] for s in data if s["in_fit"]]
    unseen = [s["key"] for s in data if not s["in_fit"]]
    if fitted:
        out.append({"key": "group.fitted", "label": "Kinds of data `potential` was fitted on", "sets": fitted})
    if unseen:
        out.append({"key": "group.unseen", "label": "Kinds of data `potential` never saw", "sets": unseen})
    return out


def case_share(run: dict, case: dict, threshold: str, measure: str, k: int) -> dict:
    return mean_of_shares([share(flags(run["sets"][key], threshold, measure, k)) for key in case["sets"]])


def case_difference(run: dict, case: dict, threshold: str, measure: str, a: int, b: int) -> dict:
    return mean_of_paired([
        paired(flags(run["sets"][key], threshold, measure, a), flags(run["sets"][key], threshold, measure, b))
        for key in case["sets"]])


def verdict(run: dict, case: dict, threshold: str = GUIDE_THRESHOLD, measure: str = "future") -> dict:
    """The rule of the guidance table: the key with the highest share is the best, and a key is
    level with it when the 95% interval of its paired difference to the best includes zero."""
    keys = run["keys"]
    shares = [case_share(run, case, threshold, measure, k) for k in range(len(keys))]
    top_share = max(s["p"] for s in shares)
    best = [k for k, s in enumerate(shares) if s["p"] == top_share]
    level_with = []
    for k in range(len(keys)):
        if k in best:
            continue
        if level(case_difference(run, case, threshold, measure, best[0], k)):
            level_with.append(k)
    level_with.sort(key=lambda k: -shares[k]["p"])
    return {"shares": shares, "best": best, "level": level_with}


# ----------------------------------------------------------------------------
# the ensemble figures

def calibration(query_sets: list, threshold: str, bins: int = 10) -> dict:
    """Stated probability of the top entry of `future_potentials` against how often it is right.

    Only queries where an entry exists count. `gap` is the mean distance between
    stated and observed over the bins, weighted by the answers in each.
    """
    stated, right = [], []
    for query_set in query_sets:
        for row in query_set["rows"]:
            entry = row["t"][threshold]
            if entry["fp_p"] is not None:
                stated.append(entry["fp_p"])
                right.append(int(bool(entry["fp_right"])))
    table = []
    for b in range(bins):
        low, high = b / bins, (b + 1) / bins
        members = [i for i, p in enumerate(stated) if low <= p < high or (b == bins - 1 and p == 1.0)]
        if members:
            table.append({"low": low, "high": high, "n": len(members),
                          "stated": sum(stated[i] for i in members) / len(members),
                          "right": sum(right[i] for i in members) / len(members)})
        else:
            table.append({"low": low, "high": high, "n": 0, "stated": None, "right": None})
    n = len(stated)
    at = {}
    for floor in (0.5, 0.9):
        members = [i for i, p in enumerate(stated) if p >= floor]
        at[str(floor)] = {"share": len(members) / n if n else None,
                          "right": share([right[i] for i in members])}
    quarter = sorted(range(n), key=lambda i: -stated[i])[:max(1, n // 4)] if n else []
    return {
        "answers": n,
        "stated": sum(stated) / n if n else None,
        "right": sum(right) / n if n else None,
        "gap": sum(row["n"] * abs(row["stated"] - row["right"]) for row in table if row["n"]) / n if n else None,
        "auroc": auroc(stated, right),
        "at": at,
        "top_quarter_right": sum(right[i] for i in quarter) / len(quarter) if quarter else None,
        "bins": table,
    }


def endings(run: dict, threshold: str, bins: int = 10) -> list:
    """`ends_here` where a sequence ended against where it went on, node by node.

    A node's ending set is compared with its first next-event set.
    """
    out = []
    by_node = {}
    for query_set in run["sets"].values():
        by_node.setdefault(query_set["node"], []).append(query_set)
    for node, node_sets in by_node.items():
        ended = [s for s in node_sets if s["group"] == "ending"]
        went_on = [s for s in node_sets if s["group"] != "ending"]
        if not ended or not went_on:
            continue
        ended, went_on = ended[0], went_on[0]

        def read(query_set):
            values, says_end = [], []
            for row in query_set["rows"]:
                entry = row["t"][threshold]
                if entry["ends_here"] is None:
                    continue
                values.append(entry["ends_here"])
                says_end.append(int(entry["fp_p"] is None or entry["ends_here"] > entry["fp_p"]))
            return values, says_end

        e_values, e_says = read(ended)
        w_values, w_says = read(went_on)
        histogram = lambda values: [  # noqa: E731
            sum(1 for v in values if b / bins <= v < (b + 1) / bins or (b == bins - 1 and v == 1.0))
            for b in range(bins)]
        out.append({
            "node": node, "label": ended["label"], "kind": ended["kind"],
            "ended": {"n": len(e_values), "mean": sum(e_values) / len(e_values) if e_values else None,
                      "above_half": share([v > 0.5 for v in e_values]), "says_end": share(e_says),
                      "histogram": histogram(e_values)},
            "went_on": {"n": len(w_values), "mean": sum(w_values) / len(w_values) if w_values else None,
                        "above_half": share([v > 0.5 for v in w_values]), "says_end": share(w_says),
                        "histogram": histogram(w_values)},
            "auroc": auroc(e_values + w_values, [1] * len(e_values) + [0] * len(w_values)),
            "ended_set": ended["key"], "went_on_set": went_on["key"],
        })
    return out


def no_future_shares(run: dict, threshold: str) -> list:
    """Per ranking key: how often its top prediction has no future, where the sequence ended and
    where it went on. Means over the nodes that have an ending set."""
    rows = []
    pairs = endings(run, threshold)
    for k, key in enumerate(run["keys"]):
        ended, went_on = [], []
        for pair in pairs:
            for target, set_key in ((ended, pair["ended_set"]), (went_on, pair["went_on_set"])):
                entries = [row["t"][threshold] for row in run["sets"][set_key]["rows"] if row["t"][threshold]["n"] > 0]
                target.append(share([entry["top"][k] == NO_EVENT for entry in entries]))
        rows.append({"key": key, "ended": mean_of_shares(ended), "went_on": mean_of_shares(went_on)})
    return rows


def chance(query_sets: list, threshold: str) -> dict:
    """Queries with `chance_posterior` above 0.5, and the top entry's accuracy inside and outside."""
    inside, outside = [], []
    for query_set in query_sets:
        for row in query_set["rows"]:
            entry = row["t"][threshold]
            if entry["chance"] is None or entry["n"] == 0:
                continue
            (inside if entry["chance"] > 0.5 else outside).append(int(bool(entry["fp_right"])))
    total = len(inside) + len(outside)
    return {"share": len(inside) / total if total else None, "n": total,
            "right_inside": share(inside), "right_outside": share(outside)}


# ----------------------------------------------------------------------------
# request time

def latency(run: dict) -> dict:
    """Request times from the one-at-a-time probe, with the candidates each request had."""
    nodes, points = [], []
    for node_key in run["record"].get("node_order") or sorted(run["record"]["nodes"]):
        node = run["record"]["nodes"].get(node_key) or {}
        probe = node.get("latency")
        if not probe or not probe.get("ms"):
            continue
        first_set = (node.get("set_order") or sorted(node["sets"]))[0]
        rows = run["sets"].get(first_set, {}).get("rows", [])
        threshold = str(probe["recall_threshold"])
        candidates = [row["t"][threshold]["n"] for row in rows[:len(probe["ms"])] if threshold in row["t"]]
        for n, ms in zip(candidates, probe["ms"]):
            points.append({"node": node_key, "candidates": n, "ms": ms})
        nodes.append({
            "node": node_key, "label": node["label"], "patterns": node["patterns"],
            "candidates": median(candidates), "ms": median(probe["ms"]), "ms_p90": percentile(probe["ms"], 0.9),
            "requests": len(probe["ms"]),
            "by_key": {key: median(values) for key, values in probe.get("by_key_ms", {}).items()},
        })
    return {"nodes": nodes, "points": points}


# ----------------------------------------------------------------------------
# two runs

def compare(run_a: dict, run_b: dict) -> dict:
    """Response by response: do two runs hold the same fingerprints?"""
    same = different = only_a = only_b = 0
    examples = []
    for set_key, set_a in run_a["sets"].items():
        set_b = run_b["sets"].get(set_key)
        if set_b is None:
            only_a += sum(len(row["t"]) for row in set_a["rows"])
            continue
        rows_b = {row["q"]: row for row in set_b["rows"]}
        for row in set_a["rows"]:
            other = rows_b.get(row["q"])
            for threshold, entry in row["t"].items():
                if other is None or threshold not in other["t"]:
                    only_a += 1
                elif entry.get("digest") == other["t"][threshold].get("digest") and entry["top"] == other["t"][threshold]["top"]:
                    same += 1
                else:
                    different += 1
                    if len(examples) < 10:
                        examples.append({"set": set_key, "query": row["i"], "threshold": threshold})
    for set_key, set_b in run_b["sets"].items():
        if set_key not in run_a["sets"]:
            only_b += sum(len(row["t"]) for row in set_b["rows"])
    return {"same": same, "different": different, "only_first": only_a, "only_second": only_b, "examples": examples}


__all__ = ["KEYS", "load_run", "wilson", "share", "paired", "verdict", "cases", "groups", "compare"]
