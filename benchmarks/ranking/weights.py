"""`future_potentials` rebuilt with other candidate weights.

KATO weights every candidate by e^potential when it builds `future_potentials`
and `ends_here`, whatever `rank_sort_algo` is. This asks the guide suite's
queries once, at recall_threshold 0.1, and rebuilds both figures from every
candidate of each response under other weightings: e^key for each ranking key,
2^good_odds, frequency taken linearly, and every candidate counting equally.
Each is scored as the benchmark scores the real figures: how often the top
entry names the event that followed, how well its stated probability matches
that, and how well `ends_here` tells ended sequences from continuing ones.

The rebuild with e^potential must equal what KATO returned, to the last bit, on
every query; the run stops if it does not.

    python -m benchmarks.ranking.weights                 # the guide suite, about an hour
    python -m benchmarks.ranking.weights --summarize     # the summary again, from the stored rows

Standard library only. It writes to nodes named `<prefix>_<node>` and clears
each when its queries are done.
"""
import argparse
import gzip
import json
import math
import sys
import time
from pathlib import Path

from . import run, stats, suite
from .client import Kato
from .scoring import same_event

THRESHOLD = 0.1
KINDS = ("Generated", "System logs", "Click streams", "Text", "Finance", "Healthcare", "Music", "Computing")
KEYS = (
    "potential", "good_odds", "similarity", "evidence", "confidence", "snr", "fragmentation", "frequency",
    "bayesian_posterior", "bayesian_prior", "bayesian_likelihood", "predictive_information", "confluence",
    "entropy", "normalized_entropy", "global_normalized_entropy", "tfidf_score", "itfdf_similarity",
    "event_cohesion", "onset_alignment",
)
BASE = "e^potential"
_LN2 = math.log(2.0)


def _exp_of(key):
    return lambda p: float(p[key])


def _linear_frequency(p):
    return math.log(p["frequency"]) if p["frequency"] > 0 else -math.inf


WEIGHTS = {f"e^{key}": _exp_of(key) for key in KEYS}
"""Name -> the natural logarithm of a candidate's weight."""
WEIGHTS["2^good_odds"] = lambda p: p["good_odds"] * _LN2   # the shares are bayesian_posterior
WEIGHTS["frequency, linear"] = _linear_frequency
WEIGHTS["uniform"] = lambda p: 0.0


def rebuild(predictions: list, log_weight) -> tuple:
    """(entries, ends_here) as KATO builds future_potentials, with another weight.

    Entries are (probability, next event as a tuple), most probable first, equal
    probabilities to the event that sorts first. Every sum runs one candidate at
    a time in pattern-name order, with each weight taken relative to the
    largest, as `kato.informatics.prediction_metrics` sums them, so that the
    rebuild with e^potential is the same bits as KATO's own figures.
    ends_here is None when there is no candidate or no candidate has weight.
    """
    if not predictions:
        return [], None
    order = sorted(range(len(predictions)), key=lambda i: predictions[i]["name"])
    logs = [log_weight(p) for p in predictions]
    top = max(logs)
    if top == -math.inf:
        return [], None
    weights = [math.exp(x - top) if x != -math.inf else 0.0 for x in logs]
    total = 0.0
    for i in order:
        total += weights[i]
    events, ends_here = {}, 0.0
    for i in order:
        share = weights[i] / total
        if predictions[i]["future"]:
            event = tuple(predictions[i]["future"][0])
            events[event] = events.get(event, 0.0) + share
        else:
            ends_here += share
    entries = sorted(((p, e) for e, p in events.items()), key=lambda t: (-t[0], t[1]))
    return entries, ends_here


def score(predictions: list, answer, log_weight) -> dict:
    """What one query says about one weighting."""
    entries, ends_here = rebuild(predictions, log_weight)
    p_answer = 0.0
    if answer is not None:
        for probability, event in entries:
            if same_event(list(event), answer):
                p_answer = probability
                break
    top = entries[0] if entries else None
    return {
        "top_p": top[0] if top else None,
        "right": bool(top is not None and answer is not None and same_event(list(top[1]), answer)),
        "p_answer": p_answer,
        "ends_here": ends_here,
    }


def agrees_with_kato(response: dict) -> bool:
    """True when the rebuild with e^potential is KATO's own future_potentials and ends_here."""
    entries, ends_here = rebuild(response["predictions"], WEIGHTS[BASE])
    returned = response.get("future_potentials") or []
    if len(returned) != len(entries) or response.get("ends_here") != ends_here:
        return False
    return all(a["probability"] == p and a["next_event"] == list(e) for a, (p, e) in zip(returned, entries))


def ask_node(kato: Kato, plan, node_id: str, data_dir: Path, count: int, log=print) -> list:
    """Load one node, ask every query of every set, and return one row per query."""
    node = plan.build(data_dir, count, log)
    run.load_node(kato, node_id, node.sequences, 1, log=log)
    session = kato.new_session(node_id, run.MATCHING)
    rows = []
    try:
        kato.configure(session, {"recall_threshold": THRESHOLD, "max_predictions": suite.RESPONSE_CAP,
                                 "rank_sort_algo": "potential"})
        for query_set in node.query_sets:
            for i, (stm, answer) in enumerate(query_set.queries):
                kato.clear_stm(session)
                kato.observe(session, stm)
                response = kato.predictions(session)
                predictions = response["predictions"]
                if len(predictions) >= suite.RESPONSE_CAP:
                    raise run.BenchmarkError(f"{node_id}: a response reached max_predictions; not every candidate is in it")
                if not agrees_with_kato(response):
                    raise run.BenchmarkError(f"{node_id}, {query_set.key} query {i}: the rebuild with e^potential "
                                             "is not what KATO returned")
                rows.append({
                    "node": plan.key, "kind": node.kind, "set": query_set.key, "group": query_set.group, "i": i,
                    "n": len(predictions),
                    "w": {name: (score(predictions, answer, w) if predictions else None) for name, w in WEIGHTS.items()},
                })
    finally:
        kato.delete_session(session)
        run.clear_node(kato, node_id)
    return rows


# ── summary ────────────────────────────────────────────────────────────

def _set_means(rows: list, value) -> dict:
    """kind -> list of (mean, variance of the mean) per query set."""
    by_set = {}
    for r in rows:
        by_set.setdefault((r["kind"], r["set"]), []).append(value(r))
    out = {}
    for (kind, _), values in sorted(by_set.items()):
        m = stats.mean(values)
        var = stats.total((x - m) ** 2 for x in values) / max(1, len(values) - 1) / len(values)
        out.setdefault(kind, []).append((m, var))
    return out


def _mean_of_kinds(rows: list, value) -> tuple:
    """(mean over the kinds of the mean over each kind's sets, its standard error)."""
    per_kind = _set_means(rows, value)
    kinds = [k for k in KINDS if k in per_kind]
    means = [stats.mean([m for m, _ in per_kind[k]]) for k in kinds]
    variances = [stats.total(v for _, v in per_kind[k]) / len(per_kind[k]) ** 2 for k in kinds]
    return stats.mean(means), math.sqrt(stats.total(variances)) / len(kinds), dict(zip(kinds, means))


def _auroc(positives: list, negatives: list) -> float:
    wins = stats.total((p > q) + 0.5 * (p == q) for p in positives for q in negatives)
    return wins / (len(positives) * len(negatives))


def summarize(rows: list) -> list:
    """One entry per weighting, best first by the share right on the mean of the kinds."""
    nexts = [r for r in rows if r["group"] != "ending"]
    endings = [r for r in rows if r["group"] == "ending"]

    def right(r, name):
        w = r["w"][name]
        return 1.0 if w and w["right"] else 0.0

    out = []
    for name in WEIGHTS:
        share, _, by_kind = _mean_of_kinds(nexts, lambda r, n=name: right(r, n))
        diff, se, _ = _mean_of_kinds(nexts, lambda r, n=name: right(r, n) - right(r, BASE))
        answered = [r for r in nexts if r["w"][name] and r["w"][name]["top_p"] is not None]
        stated = stats.mean([r["w"][name]["top_p"] for r in answered])
        right_answered = stats.mean([right(r, name) for r in answered])
        bins = {}
        for r in answered:
            bins.setdefault(min(9, int(r["w"][name]["top_p"] * 10)), []).append(r)
        calibration = stats.total(
            abs(stats.mean([r["w"][name]["top_p"] for r in b]) - stats.mean([right(r, name) for r in b])) * len(b)
            for _, b in sorted(bins.items())) / len(answered)
        aurocs = []
        for kind in KINDS:
            ended = [r["w"][name]["ends_here"] for r in endings if r["kind"] == kind and r["w"][name]]
            went_on = [r["w"][name]["ends_here"] for r in nexts if r["kind"] == kind and r["w"][name]]
            if len(ended) >= 5 and went_on:
                aurocs.append(_auroc(ended, went_on))
        out.append({
            "weight": name, "right": share, "difference": diff,
            "low": diff - 1.96 * se, "high": diff + 1.96 * se,
            "stated": stated, "right_when_answered": right_answered, "calibration_error": calibration,
            "ends_here_auroc": stats.mean(aurocs), "by_kind": by_kind,
        })
    out.sort(key=lambda e: (-e["right"], e["weight"]))
    return out


def table(summary: list) -> str:
    lines = ["| Weight | Top entry right | Difference from `e^potential` (95% interval) | Probability stated "
             "| Share right when answered | Calibration error | `ends_here` AUROC |",
             "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for e in summary:
        diff = "" if e["weight"] == BASE else (
            f"{e['difference'] * 100:+.1f} ({e['low'] * 100:+.1f} to {e['high'] * 100:+.1f})")
        lines.append(f"| `{e['weight']}` | {e['right']:.3f} | {diff} | {e['stated']:.3f} | "
                     f"{e['right_when_answered']:.3f} | {e['calibration_error']:.3f} | {e['ends_here_auroc']:.3f} |")
    return "\n".join(lines) + "\n"


# ── command line ───────────────────────────────────────────────────────

def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m benchmarks.ranking.weights", description=__doc__.split("\n\n")[0])
    p.add_argument("--url", default="http://localhost:8000", help="the KATO instance (default: %(default)s)")
    p.add_argument("--only", nargs="+", metavar="NODE", help="ask only these nodes of the guide suite")
    p.add_argument("--queries", type=int, default=200, help="queries per set (default: %(default)s)")
    p.add_argument("--results-dir", default=str(run.RESULTS_DIR / "weights"), help="default: %(default)s")
    p.add_argument("--data-dir", default=str(run.DATA_DIR), help="where downloads are kept (default: %(default)s)")
    p.add_argument("--node-prefix", default="rankweights", help="start of the node ids (default: %(default)s)")
    p.add_argument("--summarize", action="store_true", help="only rebuild the summary from the stored rows")
    return p


def main(argv=None, kato: Kato = None, log=print) -> int:
    args = parser().parse_args(argv)
    out_dir = Path(args.results_dir)
    rows_dir = out_dir / "rows"
    rows_dir.mkdir(parents=True, exist_ok=True)
    if not args.summarize:
        kato = kato or Kato(args.url)
        for plan in suite.guide_plans():
            if args.only and plan.key not in args.only:
                continue
            path = rows_dir / f"{plan.key}.jsonl.gz"
            if path.exists():
                log(f"{plan.key}: stored already")
                continue
            started = time.perf_counter()
            rows = ask_node(kato, plan, f"{args.node_prefix}_{plan.key}", Path(args.data_dir), args.queries, log)
            path.write_bytes(gzip.compress("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows).encode(),
                                           compresslevel=9, mtime=0))
            log(f"{plan.key}: {len(rows)} queries, every rebuild with e^potential equal to KATO's, "
                f"{time.perf_counter() - started:.0f} s")
    rows = [json.loads(line) for path in sorted(rows_dir.glob("*.jsonl.gz"))
            for line in gzip.decompress(path.read_bytes()).decode().splitlines()]
    if not rows:
        log("no stored rows")
        return 1
    summary = summarize(rows)
    (out_dir / "summary.json").write_text(json.dumps(
        {"recall_threshold": THRESHOLD, "queries": len(rows), "weights": summary}, indent=1, sort_keys=True) + "\n")
    log(table(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
