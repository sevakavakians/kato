"""End-to-end prediction scaling over the HTTP API.

The other benchmarks in this directory drive `PatternProcessor` in-process. This
one goes through the running service, so it measures what a client actually
waits for — uvicorn, the session layer, the filter pipeline, matching, metrics
and ranking — and it is the harness the 2026-09-16 investigation used to find
that the per-request `ProcessPoolExecutor` was costing 3378 ms where the thread
pool cost 1231 ms.

It reports three numbers per corpus tier so a change can be attributed:

    scan      the exact `SELECT name, pattern_data, length ... WHERE kb_id = ?`
              that `FilterPipelineExecutor._get_all_patterns` issues when
              `filter_pipeline` is empty (the default)
    metadata  one `patterns_metadata` lookup of METADATA_CHUNK_SIZE names, the
              unit the prediction path repeats per chunk
    predict   GET /sessions/{id}/predictions, end to end

Measured 2026-09-16 (6000 patterns, all matching): scan ~12 ms (1%), metadata
~430 ms over 12 chunks (35%), matching and metrics the rest. The full-corpus
scan is not the bottleneck — that is the main thing this benchmark exists to
keep honest.

Loading uses `process_predictions: false`. With predictions on, every observe
runs a full-corpus prediction, so building a corpus is O(N^2): at ~700 patterns
it had collapsed to ~8 patterns/min against 8 concurrent writers, versus ~428
patterns/min per worker with them off. That is why the older benchmark results
in this directory stop at 100 patterns.

Usage:
    ./start.sh                                   # service must be running
    python -m benchmarks.test_service_scaling
    python -m benchmarks.test_service_scaling --tiers 500,2000
    python -m benchmarks.test_service_scaling --baseline benchmarks/results/service_scaling_<id>.json
    python -m benchmarks.test_service_scaling --keep   # leave the corpus for the next run
"""

import argparse
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from benchmarks.profiler import TimingCollector  # noqa: E402

KATO_URL = os.environ.get("KATO_BENCH_URL", "http://localhost:8000")
CLICKHOUSE_URL = os.environ.get("KATO_BENCH_CLICKHOUSE_URL", "http://localhost:8123")
NODE_ID = os.environ.get("KATO_BENCH_NODE", "bench_service_scaling")
KB_ID = f"{NODE_ID}_kato"

DEFAULT_TIERS = [500, 2000, 6000]
PROBE_EVENT = ["alpha", "beta"]   # every pattern starts with this, so all match
SAMPLES = 12
LOAD_WORKERS = 8
RESULTS_DIR = Path(__file__).resolve().parent / "results"


# --------------------------------------------------------------------------- IO

def call(method: str, path: str, payload=None, timeout: int = 120):
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        KATO_URL + path, data=data, method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def clickhouse(sql: str, timeout: int = 120) -> str:
    url = CLICKHOUSE_URL + "/?" + urllib.parse.urlencode({"query": sql})
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return response.read().decode().strip()


def new_session(config: dict = None) -> str:
    return call("POST", "/sessions", {"node_id": NODE_ID, "config": config or {}})["session_id"]


def corpus_size() -> int:
    return int(clickhouse(
        f"SELECT count() FROM kato.patterns_data WHERE kb_id = '{KB_ID}'"
    ) or 0)


# ---------------------------------------------------------------------- loading

def _load_chunk(args) -> int:
    """Learn `count` patterns. One session per worker: one writer per session."""
    start, count = args
    # process_predictions=False keeps loading linear; see the module docstring.
    session = new_session({"process_predictions": False})
    for i in range(start, start + count):
        call("POST", f"/sessions/{session}/clear-stm", {})
        call("POST", f"/sessions/{session}/observe", {"strings": sorted(PROBE_EVENT)})
        call("POST", f"/sessions/{session}/observe",
             {"strings": sorted([f"mid{i % 37:02d}", f"tag{i % 53:02d}"])})
        call("POST", f"/sessions/{session}/observe", {"strings": [f"tail{i:06d}"]})
        call("POST", f"/sessions/{session}/learn", {})
    call("DELETE", f"/sessions/{session}")
    return count


def grow_corpus_to(target: int) -> int:
    """Add patterns until the corpus reaches `target`. Reuses what is there."""
    current = corpus_size()
    todo = target - current
    if todo <= 0:
        print(f"    corpus already at {current}, reusing")
        return current

    per_worker, remainder = divmod(todo, LOAD_WORKERS)
    chunks, offset = [], current
    for worker in range(LOAD_WORKERS):
        size = per_worker + (1 if worker < remainder else 0)
        if size:
            chunks.append((offset, size))
            offset += size

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=LOAD_WORKERS) as pool:
        list(pool.map(_load_chunk, chunks))
    elapsed = time.perf_counter() - started
    print(f"    loaded {todo} patterns in {elapsed:.1f}s ({todo / elapsed * 60:.0f}/min)")
    return corpus_size()


# ------------------------------------------------------------------- measuring

def measure_scan(collector: TimingCollector, tier: int) -> int:
    """Time the unfiltered full-corpus SELECT the executor issues."""
    sql = (f"SELECT name, pattern_data, length FROM kato.patterns_data "
           f"WHERE kb_id = '{KB_ID}' FORMAT JSONCompact")
    payload_bytes = 0
    for _ in range(5):
        url = CLICKHOUSE_URL + "/?" + urllib.parse.urlencode({"query": sql})
        started = time.perf_counter()
        with urllib.request.urlopen(url, timeout=120) as response:
            body = response.read()
        collector.record(f"scan.tier{tier}", (time.perf_counter() - started) * 1000)
        payload_bytes = len(body)
    return payload_bytes


def measure_metadata_chunk(collector: TimingCollector, tier: int) -> int:
    """Time one metadata lookup of METADATA_CHUNK_SIZE names.

    The prediction path issues ceil(matched / METADATA_CHUNK_SIZE) of these, so
    this is the unit to multiply, not a whole-corpus figure.
    """
    from kato.searches.pattern_search import METADATA_CHUNK_SIZE

    names = clickhouse(
        f"SELECT name FROM kato.patterns_data WHERE kb_id = '{KB_ID}' "
        f"LIMIT {METADATA_CHUNK_SIZE}"
    ).split("\n")
    names = [n for n in names if n]
    if not names:
        return 0

    name_list = ", ".join(f"'{n}'" for n in names)
    sql = (f"SELECT name, argMax(emotives, version), argMax(metadata, version) "
           f"FROM kato.patterns_metadata "
           f"WHERE kb_id = '{KB_ID}' AND name IN ({name_list}) "
           f"GROUP BY name FORMAT JSONCompact")
    for _ in range(5):
        url = CLICKHOUSE_URL + "/?" + urllib.parse.urlencode({"query": sql})
        started = time.perf_counter()
        with urllib.request.urlopen(url, timeout=120) as response:
            response.read()
        collector.record(f"metadata_chunk.tier{tier}", (time.perf_counter() - started) * 1000)
    return len(names)


def measure_predict(collector: TimingCollector, tier: int) -> int:
    """Time GET /predictions end to end, after a warm-up request."""
    session = new_session()
    call("POST", f"/sessions/{session}/observe", {"strings": sorted(PROBE_EVENT)})
    result = call("GET", f"/sessions/{session}/predictions")  # warm caches
    for _ in range(SAMPLES):
        started = time.perf_counter()
        result = call("GET", f"/sessions/{session}/predictions")
        collector.record(f"predict.tier{tier}", (time.perf_counter() - started) * 1000)
    call("DELETE", f"/sessions/{session}")
    return result["count"]


# -------------------------------------------------------------------- reporting

def print_table(rows: list[dict]) -> None:
    print()
    print(f"{'patterns':>9} {'scan ms':>9} {'scan KB':>9} "
          f"{'meta/chunk':>11} {'predict ms':>11} {'preds':>6}")
    print("-" * 62)
    for row in rows:
        print(f"{row['patterns']:>9} {row['scan_ms']:>9.1f} {row['scan_kb']:>9.1f} "
              f"{row['metadata_chunk_ms']:>11.1f} {row['predict_ms']:>11.1f} "
              f"{row['predictions']:>6}")


def print_comparison(rows: list[dict], baseline_path: Path) -> None:
    baseline = {r["patterns"]: r for r in json.loads(baseline_path.read_text())["tiers"]}
    print(f"\nagainst {baseline_path.name}:")
    print(f"{'patterns':>9} {'predict ms':>24} {'scan ms':>22}")
    print("-" * 58)
    for row in rows:
        previous = baseline.get(row["patterns"])
        if not previous:
            print(f"{row['patterns']:>9} {'(not in baseline)':>24}")
            continue
        print(f"{row['patterns']:>9} "
              f"{previous['predict_ms']:>8.1f} -> {row['predict_ms']:>8.1f} "
              f"{_delta(previous['predict_ms'], row['predict_ms']):>6} "
              f"{previous['scan_ms']:>8.1f} -> {row['scan_ms']:>6.1f} "
              f"{_delta(previous['scan_ms'], row['scan_ms']):>6}")


def _delta(before: float, after: float) -> str:
    if before <= 0:
        return "n/a"
    change = (after - before) / before * 100
    return f"{change:+.0f}%"


def cleanup() -> None:
    session = new_session()
    call("POST", f"/sessions/{session}/clear-all", {}, timeout=300)
    print(f"  cleared corpus for node {NODE_ID}")


# ------------------------------------------------------------------------- main

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tiers", default=",".join(str(t) for t in DEFAULT_TIERS),
                        help=f"comma-separated corpus sizes (default: {DEFAULT_TIERS})")
    parser.add_argument("--baseline", type=Path,
                        help="a previous results JSON to compare against")
    parser.add_argument("--keep", action="store_true",
                        help="leave the corpus in place for the next run")
    parser.add_argument("--rebuild", action="store_true",
                        help="clear any existing corpus before loading")
    args = parser.parse_args()

    tiers = sorted(int(t) for t in args.tiers.split(","))

    try:
        call("GET", "/health", timeout=10)
    except (urllib.error.URLError, OSError) as error:
        print(f"KATO is not reachable at {KATO_URL}: {error}\nStart it with ./start.sh")
        return 1

    if args.rebuild:
        cleanup()

    collector = TimingCollector()
    rows = []
    started = time.perf_counter()

    for tier in tiers:
        print(f"\n  tier {tier}:")
        actual = grow_corpus_to(tier)
        scan_bytes = measure_scan(collector, tier)
        measure_metadata_chunk(collector, tier)
        predictions = measure_predict(collector, tier)
        rows.append({
            "patterns": actual,
            "scan_ms": collector.get_stats(f"scan.tier{tier}")["median"],
            "scan_kb": scan_bytes / 1024,
            "metadata_chunk_ms": collector.get_stats(f"metadata_chunk.tier{tier}")["median"],
            "predict_ms": collector.get_stats(f"predict.tier{tier}")["median"],
            "predict_min_ms": collector.get_stats(f"predict.tier{tier}")["min"],
            "predictions": predictions,
        })

    print_table(rows)
    if args.baseline:
        print_comparison(rows, args.baseline)

    benchmark_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    RESULTS_DIR.mkdir(exist_ok=True)
    output = RESULTS_DIR / f"service_scaling_{benchmark_id}.json"
    output.write_text(json.dumps({
        "benchmark_id": benchmark_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "kato_url": KATO_URL,
        "node_id": NODE_ID,
        "samples_per_tier": SAMPLES,
        "tiers": rows,
        "raw_timings": collector.to_dict(),
        "total_benchmark_time_ms": (time.perf_counter() - started) * 1000,
    }, indent=2))
    print(f"\n  wrote {output.relative_to(Path.cwd()) if output.is_relative_to(Path.cwd()) else output}")

    if not args.keep:
        cleanup()
    else:
        print(f"  corpus kept ({rows[-1]['patterns']} patterns); rerun is faster, "
              f"or use --rebuild to start clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
