"""Run the ranking benchmark against a live KATO instance.

For each node of a suite: learn its sequences through the REST API, ask the
held-out queries at each recall threshold, record what every ranking key would
have put on top, time a few requests, and clear the node again.

    ./start.sh start                                      # KATO must be running

    python -m benchmarks.ranking.run --suite smoke        # two minutes, no downloads
    python -m benchmarks.ranking.run                      # the guide suite
    python -m benchmarks.ranking.run --only gen_base hdfs # some of its nodes
    python -m benchmarks.ranking.run --check-data         # fetch and read every data set, then stop
    python -m benchmarks.ranking.report                   # tables and charts from the results

Results go to benchmarks/results/ranking/<name>/. A run that is interrupted, or
asked for more queries later, continues from what is stored: completed queries
are never asked twice. Only nodes whose id starts with the node prefix are
written, and each is cleared when its queries are done.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
import threading
import time
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from benchmarks.ranking import datasets, scoring
from benchmarks.ranking import suite as suites
from benchmarks.ranking.client import Kato, KatoError

FORMAT = 1
THRESHOLDS = (0.1, 0.3, 0.5)
DEPTH = 100                    # predictions read per key when a response cannot hold every candidate
LATENCY_QUERIES = 20
LATENCY_KEY_QUERIES = 5
LATENCY_MAX_PREDICTIONS = 100  # KATO's default
TIME_KEYS_ON = ("gen_base", "gen_smallvocab", "gen_small")

RESULTS_DIR = Path(__file__).resolve().parent.parent / "results" / "ranking"
DATA_DIR = Path(__file__).resolve().parent / "data"

# Pinned for every session, so two instances are compared on the same footing
# whatever their own defaults: token-level matching, fuzzy matching off, no
# filter pipeline (every pattern above the recall threshold is a candidate),
# and learning only when asked.
MATCHING = {
    "use_token_matching": True,
    "fuzzy_token_threshold": 0.0,
    "filter_pipeline": [],
    "max_pattern_length": 0,
    "stm_mode": "CLEAR",
    "process_predictions": False,
}


class BenchmarkError(RuntimeError):
    """The run cannot go on as asked; the message says what to do."""


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def digest_of(value) -> str:
    text = json.dumps(value, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _pretty(value, indent: int = 0) -> str:
    """JSON with one key per line and lists of plain values on one line."""
    pad = " " * (indent + 1)
    if isinstance(value, dict) and value:
        rows = [f"{pad}{json.dumps(key)}: {_pretty(value[key], indent + 1)}" for key in sorted(value)]
        return "{\n" + ",\n".join(rows) + "\n" + " " * indent + "}"
    if isinstance(value, list) and any(isinstance(item, (dict, list)) for item in value):
        return "[\n" + ",\n".join(pad + _pretty(item, indent + 1) for item in value) + "\n" + " " * indent + "]"
    return json.dumps(value)


def write_json(path: Path, value) -> None:
    partial = path.with_name(path.name + ".part")
    partial.write_text(_pretty(value) + "\n")
    partial.replace(path)


def _transient(error: Exception) -> bool:
    if isinstance(error, KatoError):
        return error.status >= 500 or error.status == 404
    return isinstance(error, (urllib.error.URLError, OSError))


# ----------------------------------------------------------------------------
# loading a node

def load_node(kato: Kato, node_id: str, sequences: list, workers: int, log=print) -> dict:
    """Clear the node, learn `sequences`, check what KATO stored, and finalize training.

    Every learn is checked: the pattern name KATO returns must be the SHA-1 the
    client computes for the sequence. A learn is never retried, because a
    repeated learn would raise a pattern's frequency unnoticed.
    """
    started = time.perf_counter()
    keeper = kato.new_session(node_id, MATCHING)
    try:
        kato.clear_node(keeper)
        shares = [[] for _ in range(max(1, workers))]
        for index, sequence in enumerate(sequences):
            shares[index % len(shares)].append(sequence)
        done = [0]
        lock = threading.Lock()
        stop = threading.Event()

        def learn(share: list) -> None:
            session = kato.new_session(node_id, MATCHING)
            try:
                for sequence in share:
                    if stop.is_set():
                        return
                    result = kato.observe(session, sequence, learn=True)
                    learned = (result.get("final_learned_pattern") or "").replace("PTRN|", "")
                    if learned != scoring.pattern_name(sequence):
                        raise BenchmarkError(
                            f"{node_id}: KATO learned pattern '{learned}' where "
                            f"'{scoring.pattern_name(sequence)}' was expected. The node is not usable.")
                    if result.get("final_stm_length"):
                        kato.clear_stm(session)
                    with lock:
                        done[0] += 1
                        if done[0] % 2000 == 0:
                            rate = done[0] / (time.perf_counter() - started)
                            log(f"      learned {done[0]:,} of {len(sequences):,} sequences ({rate:.0f} per second)")
            except BaseException:
                stop.set()                                  # the other sessions stop at their next sequence
                raise
            finally:
                _quietly(kato.delete_session, session)

        with ThreadPoolExecutor(max_workers=len(shares)) as pool:
            list(pool.map(learn, [share for share in shares if share]))

        expected = suites.distinct_patterns(sequences)
        reported = kato.pattern_count(node_id)
        if reported != expected:
            raise BenchmarkError(
                f"{node_id}: KATO reports {reported} patterns, the data has {expected}. The node is not usable.")
        finalized = kato.finalize_training(keeper)
    finally:
        _quietly(kato.delete_session, keeper)
    return {
        "load_seconds": round(time.perf_counter() - started, 1),
        "pattern_count": reported,
        "finalize_ms": finalized.get("time_ms"),
    }


def clear_node(kato: Kato, node_id: str) -> None:
    session = kato.new_session(node_id, MATCHING)
    try:
        kato.clear_node(session)
    finally:
        _quietly(kato.delete_session, session)


def _quietly(call, *arguments) -> None:
    try:
        call(*arguments)
    except (KatoError, OSError):
        pass


# ----------------------------------------------------------------------------
# asking queries

class Asker:
    """Asks queries of one node. Each thread has its own session: one writer per session."""

    def __init__(self, kato: Kato, node_id: str, thresholds: tuple, cap: int, depth: int):
        self.kato, self.node_id = kato, node_id
        self.thresholds, self.cap, self.depth = thresholds, cap, depth
        self._local = threading.local()
        self._sessions = []
        self._lock = threading.Lock()

    def _session(self, fresh: bool = False) -> str:
        if fresh or not getattr(self._local, "session", None):
            self._local.session = self.kato.new_session(self.node_id, MATCHING)
            with self._lock:
                self._sessions.append(self._local.session)
        return self._local.session

    def close(self) -> None:
        for session in self._sessions:
            _quietly(self.kato.delete_session, session)
        self._sessions = []

    def ask(self, query: tuple) -> dict:
        """One query at every threshold. Retried from the start on a transient failure."""
        fresh = False
        for pause in (1, 5, 20, 60, None):
            try:
                return self._ask(query, self._session(fresh))
            except Exception as error:
                if pause is None or not _transient(error):
                    raise
                fresh = isinstance(error, KatoError) and error.status == 404
                time.sleep(pause)
        raise AssertionError("unreachable")

    def _ask(self, query: tuple, session: str) -> dict:
        stm, answer = query
        kato = self.kato
        kato.clear_stm(session)
        observed = kato.observe(session, stm)
        if observed.get("initial_stm_length") != 0 or observed.get("final_stm_length") != len(stm):
            raise BenchmarkError(f"{self.node_id}: the STM does not hold the query: {observed}")
        by_threshold = {}
        for threshold in self.thresholds:
            kato.configure(session, {"recall_threshold": threshold, "max_predictions": self.cap,
                                     "rank_sort_algo": "potential"})
            started = time.perf_counter()
            response = kato.predictions(session)
            entry = {"n": response["count"], "ms": round((time.perf_counter() - started) * 1000, 1)}
            entry.update(scoring.read_ensemble(response, answer))
            if response["count"] < self.cap:
                entry.update(scoring.read_ranked(response["predictions"], answer))
                entry["digest"] = scoring.response_digest(response)
            else:
                # More candidates than one response carries: ask KATO for each key's own top.
                entry.update({"capped": self.depth, "top": [], "future": [], "rank": [], "tied": []})
                for key in scoring.KEYS:
                    kato.configure(session, {"rank_sort_algo": key, "max_predictions": self.depth})
                    read = scoring.read_top_ranked(kato.predictions(session)["predictions"], answer)
                    entry["top"].append(read["top"])
                    entry["future"].append(read["future"])
                    entry["rank"].append(read["rank"])
                    entry["tied"].append(0)
            by_threshold[str(threshold)] = entry
        return by_threshold


def describe(query: tuple) -> dict:
    stm, answer = query
    return {
        "q": digest_of([stm, answer]),
        "stm_events": len(stm),
        "stm_symbols": sum(len(event) for event in stm),
        "answer_symbols": 0 if answer is None else len(answer),
    }


def stored_records(path: Path, queries: list, thresholds: tuple) -> list:
    """The records already in a set's file that belong to these queries, in order.

    Stops at the first line that is cut short, out of order, or about a
    different query; the caller rewrites the file to what is returned.
    """
    records = []
    if not path.exists():
        return records
    wanted = {str(threshold) for threshold in thresholds}
    for line in path.read_text().splitlines():
        try:
            record = json.loads(line)
        except ValueError:
            break
        index = len(records)
        if index >= len(queries) or record.get("i") != index or set(record.get("t", {})) != wanted:
            break
        if record.get("q") != describe(queries[index])["q"]:
            raise BenchmarkError(
                f"{path}: stored query {index} is not the query this suite draws now. "
                f"Use --fresh to start the run again, or --name for a separate one.")
        records.append(record)
    return records


def run_set(asker: Asker, query_set, path: Path, workers: int, log=print) -> dict:
    queries = query_set.queries
    records = stored_records(path, queries, asker.thresholds)
    path.write_text("".join(json.dumps(r, separators=(",", ":")) + "\n" for r in records))
    todo = range(len(records), len(queries))
    started = time.perf_counter()
    if todo:
        pool = ThreadPoolExecutor(max_workers=max(1, workers))
        try:
            with path.open("a") as out:
                # map() yields in query order, so the file is always a prefix of the set.
                for index, by_threshold in zip(todo, pool.map(lambda i: asker.ask(queries[i]), todo)):
                    record = {"i": index, **describe(queries[index]), "t": by_threshold}
                    out.write(json.dumps(record, separators=(",", ":")) + "\n")
                    out.flush()
        finally:
            pool.shutdown(wait=True, cancel_futures=True)   # on a failure, do not ask the rest
    seconds = time.perf_counter() - started
    log(f"      {query_set.key}: {len(queries)} queries"
        + (f", {len(todo)} asked in {seconds:.0f}s" if todo else ", all stored already"))
    return {"label": query_set.label, "group": query_set.group, "queries": len(queries)}


# ----------------------------------------------------------------------------
# timing

def probe_latency(kato: Kato, node_id: str, queries: list, time_keys: bool) -> dict:
    """Request times, one request at a time, with KATO's default `max_predictions`.

    The accuracy pass asks for every candidate and runs several queries at once,
    so its times are not what a client sees. These are.
    """
    config = {**MATCHING, "recall_threshold": THRESHOLDS[0], "max_predictions": LATENCY_MAX_PREDICTIONS,
              "rank_sort_algo": "potential"}
    session = kato.new_session(node_id, config)
    result = {"recall_threshold": THRESHOLDS[0], "max_predictions": LATENCY_MAX_PREDICTIONS, "ms": []}
    try:
        chosen = queries[:LATENCY_QUERIES]
        if chosen:
            kato.clear_stm(session)
            kato.observe(session, chosen[0][0])
            kato.predictions(session)                       # warm-up, not recorded
        for stm, _ in chosen:
            kato.clear_stm(session)
            kato.observe(session, stm)
            started = time.perf_counter()
            kato.predictions(session)
            result["ms"].append(round((time.perf_counter() - started) * 1000, 1))
        if time_keys:
            by_key = {key: [] for key in scoring.KEYS}
            for stm, _ in queries[:LATENCY_KEY_QUERIES]:
                kato.clear_stm(session)
                kato.observe(session, stm)
                for key in scoring.KEYS:
                    kato.configure(session, {"rank_sort_algo": key})
                    started = time.perf_counter()
                    kato.predictions(session)
                    by_key[key].append(round((time.perf_counter() - started) * 1000, 1))
            result["by_key_ms"] = by_key
    finally:
        _quietly(kato.delete_session, session)
    return result


# ----------------------------------------------------------------------------
# the run

def source_record(dataset: datasets.Dataset) -> dict:
    return {
        "title": dataset.title, "kind": dataset.kind, "what": dataset.what, "licence": dataset.licence,
        "page": dataset.page, "cite": dataset.cite,
        "files": [{"url": d.url, "sha256": d.sha256, "members": dict(d.members)} for d in dataset.downloads],
    }


def node_summary(node) -> dict:
    return {
        "label": node.label, "kind": node.kind, "dataset": node.dataset, "in_fit": node.in_fit,
        "learned_sequences": len(node.sequences),
        "events": sum(len(sequence) for sequence in node.sequences),
        "symbols": sum(len(event) for sequence in node.sequences for event in sequence),
        "vocabulary": len({name for sequence in node.sequences for event in sequence for name in event}),
        "patterns": suites.distinct_patterns(node.sequences),
        "data_digest": digest_of(node.sequences),
    }


def check_data(plans: list, data_dir: Path, count: int, log=print) -> int:
    """Fetch, verify and read every data set of the suite, and print what each node would hold."""
    failures = 0
    for plan in plans:
        try:
            node = plan.build(data_dir, count, log)
        except Exception as error:                              # report every data set, not only the first
            failures += 1
            log(f"  {plan.key}: FAILED: {error}")
            continue
        summary = node_summary(node)
        log(f"  {plan.key}: {summary['learned_sequences']:,} sequences, {summary['events']:,} events, "
            f"{summary['patterns']:,} patterns, {summary['vocabulary']:,} symbols; "
            + ", ".join(f"{len(s.queries)} {s.key.split('.', 1)[1]}" for s in node.query_sets) + " queries")
        if summary["patterns"] >= suites.RESPONSE_CAP:
            log(f"      note: more than {suites.RESPONSE_CAP - 1:,} patterns; queries with that many candidates "
                f"are read per key, {DEPTH} predictions deep")
    return failures


def run(args, log=print, kato: Kato = None) -> int:
    """Run the suite. `kato` replaces the instance at `args.url` (tests pass one with their own transport)."""
    plans = suites.SUITES[args.suite]()
    node_order = [plan.key for plan in plans]
    if args.only:
        unknown = sorted(set(args.only) - {plan.key for plan in plans})
        if unknown:
            raise BenchmarkError(f"no such node in suite '{args.suite}': {', '.join(unknown)}")
        plans = [plan for plan in plans if plan.key in args.only]
    count = args.queries or suites.SUITE_QUERIES[args.suite]
    data_dir = Path(args.data_dir)

    if args.check_data:
        return 1 if check_data(plans, data_dir, count, log) else 0

    kato = kato or Kato(args.url)
    if not kato.healthy():
        raise BenchmarkError(f"KATO is not reachable at {args.url}. Start it with ./start.sh start")
    service = kato.info()

    out_dir = Path(args.results_dir) / (args.name or args.suite)
    sets_dir = out_dir / "sets"
    if args.fresh and out_dir.exists():
        for path in sorted(sets_dir.glob("*.jsonl")) + [out_dir / "run.json"]:
            if path.exists():
                path.unlink()
    sets_dir.mkdir(parents=True, exist_ok=True)

    settings = {"format": FORMAT, "suite": args.suite, "thresholds": list(THRESHOLDS), "keys": list(scoring.KEYS),
                "matching": MATCHING, "response_cap": args.response_cap, "depth": DEPTH}
    run_path = out_dir / "run.json"
    record = json.loads(run_path.read_text()) if run_path.exists() else {}
    if record:
        if record.get("settings") != settings:
            raise BenchmarkError(f"{run_path} was made with other settings. Use --fresh, or --name for a separate run.")
        if record["kato"].get("version") != service.get("version"):
            raise BenchmarkError(
                f"{run_path} was measured on KATO {record['kato'].get('version')}; this instance is "
                f"{service.get('version')}. Use --fresh, or --name for a separate run.")
    else:
        record = {"benchmark": "ranking", "settings": settings, "started": now(), "nodes": {}, "sources": {},
                  "kato": {"version": service.get("version"), "service": service.get("service"), "url": args.url}}
    record["client"] = {"python": platform.python_version(), "platform": platform.platform(),
                        "concurrency": args.concurrency}
    record["queries_per_set"] = max(count, record.get("queries_per_set", 0))
    record["node_order"] = node_order
    write_json(run_path, record)

    log(f"KATO {service.get('version')} at {args.url}; suite '{args.suite}', {len(plans)} nodes, "
        f"{count} queries per set, results in {out_dir}")
    failed = []
    for number, plan in enumerate(plans, 1):
        node_id = f"{args.node_prefix}_{args.suite}_{plan.key}"
        log(f"[{number}/{len(plans)}] {plan.key}: {plan.label}")
        try:
            _run_node(kato, plan, node_id, count, data_dir, sets_dir, record, run_path, args, log)
        except KeyboardInterrupt:
            raise
        except Exception as error:                              # one node failing must not lose the others
            failed.append(plan.key)
            record["nodes"].setdefault(plan.key, {})["error"] = f"{type(error).__name__}: {error}"
            write_json(run_path, record)
            log(f"      FAILED: {type(error).__name__}: {error}")
    record["finished"] = now()
    write_json(run_path, record)
    if failed:
        log(f"Not complete: {', '.join(failed)}. Run the same command again to continue.")
        return 1
    log(f"Complete. Build the report with: python -m benchmarks.ranking.report --run {out_dir}")
    return 0


def _run_node(kato, plan, node_id, count, data_dir, sets_dir, record, run_path, args, log) -> None:
    node = plan.build(data_dir, count, log)
    summary = node_summary(node)
    known = record["nodes"].get(plan.key, {})
    if known.get("data_digest") not in (None, summary["data_digest"]):
        raise BenchmarkError(f"{plan.key}: the data is not what the stored results were measured on. Use --fresh.")

    done = all(
        len(stored_records(sets_dir / f"{s.key}.jsonl", s.queries, THRESHOLDS)) == len(s.queries)
        for s in node.query_sets)
    if done and "latency" in known and "error" not in known:
        log("      complete already")
        return

    if node.dataset:
        record["sources"][node.dataset] = source_record(datasets.DATASETS[node.dataset])
    log(f"      learning {summary['learned_sequences']:,} sequences ({summary['events']:,} events, "
        f"{summary['patterns']:,} patterns)")
    asker = Asker(kato, node_id, THRESHOLDS, args.response_cap, DEPTH)
    try:
        summary.update(load_node(kato, node_id, node.sequences, args.concurrency, log))
        log(f"      learned in {summary['load_seconds']:.0f}s")
        summary["sets"] = {}
        summary["set_order"] = [query_set.key for query_set in node.query_sets]
        for query_set in node.query_sets:
            summary["sets"][query_set.key] = run_set(
                asker, query_set, sets_dir / f"{query_set.key}.jsonl", args.concurrency, log)
        summary["latency"] = probe_latency(kato, node_id, node.query_sets[0].queries, plan.key in TIME_KEYS_ON)
    finally:
        asker.close()
        if not args.keep_nodes:
            _quietly(clear_node, kato, node_id)
    record["nodes"][plan.key] = summary
    write_json(run_path, record)
    if args.discard_data and node.dataset:
        datasets.discard(datasets.DATASETS[node.dataset], data_dir)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--url", default="http://localhost:8000", help="the KATO instance (default: %(default)s)")
    p.add_argument("--suite", default="guide", choices=sorted(suites.SUITES), help="default: %(default)s")
    p.add_argument("--only", nargs="+", metavar="NODE", help="run only these nodes of the suite")
    p.add_argument("--queries", type=int, help="queries per set (default: 200 for guide, 12 for smoke)")
    p.add_argument("--concurrency", type=int, default=4,
                   help="sessions used at once for learning and for queries (default: %(default)s)")
    p.add_argument("--name", help="folder under the results directory (default: the suite's name)")
    p.add_argument("--results-dir", default=str(RESULTS_DIR), help="default: %(default)s")
    p.add_argument("--data-dir", default=str(DATA_DIR), help="where downloads are kept (default: %(default)s)")
    p.add_argument("--node-prefix", default="rankbench",
                   help="node ids are <prefix>_<suite>_<node>; only these nodes are written (default: %(default)s)")
    p.add_argument("--response-cap", type=int, default=suites.RESPONSE_CAP,
                   help="predictions asked for per response; at or above this many, each key is asked "
                        "separately (default: %(default)s, KATO's maximum)")
    p.add_argument("--check-data", action="store_true",
                   help="fetch, verify and read every data set of the suite, then stop; KATO is not needed")
    p.add_argument("--discard-data", action="store_true",
                   help="delete each download from the data directory once its node is done")
    p.add_argument("--keep-nodes", action="store_true", help="leave the nodes in KATO afterwards")
    p.add_argument("--fresh", action="store_true", help="delete this run's stored results first")
    return p


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    try:
        return run(args)
    except BenchmarkError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("interrupted; run the same command again to continue", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
