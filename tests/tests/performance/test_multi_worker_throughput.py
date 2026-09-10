"""
Multi-worker throughput and concurrent-training integrity.

Opt-in (set KATO_PERF=1): launches its own throwaway kato:latest containers at
KATO_WORKERS=1 and KATO_WORKERS=4 and runs the parallel-training shape —
N client threads, one session each, all on one node_id — against both.

It asserts two things the "Multi-Worker Uvicorn + Concurrent Training Safety"
initiative promised:

1. Throughput: the 4-worker run completes the same workload faster than the
   single-worker run (the exact ratio is machine-dependent and is reported,
   not asserted beyond "faster").
2. Integrity under contention, which is where the SETNX new-pattern gate and
   server-side async_insert matter:
   - every distinct pattern learned appears exactly once in ClickHouse;
   - a pattern that every thread learns every round ends with frequency
     exactly threads × rounds (no lost INCRs, no SET clobbers);
   - Redis and ClickHouse agree on the pattern count for the node;
   - clear-all afterwards leaves nothing in either store.

Requires the docker CLI, the kato:latest image, and the compose `kato`
container (its config is copied), like test_worker_topology.py.
"""

import concurrent.futures
import os
import sys
import time
import uuid

import pytest
import redis
import requests

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from integration.test_worker_topology import KatoTopology  # noqa: E402

from kato.storage.redis_writer import escape_glob  # noqa: E402

pytestmark = pytest.mark.skipif(
    not os.environ.get("KATO_PERF"),
    reason="opt-in performance test: set KATO_PERF=1 (launches two containers, ~1-2 min)",
)

THREADS = int(os.environ.get("KATO_PERF_THREADS", "8"))
ROUNDS = int(os.environ.get("KATO_PERF_ROUNDS", "10"))
SYMBOLS_PER_PATTERN = 4
# A request that takes this long means a worker has stalled; fail instead of hanging the run.
REQUEST_TIMEOUT = float(os.environ.get("KATO_PERF_REQUEST_TIMEOUT", "60"))
WORKER_COUNTS = (1, 4)

CLICKHOUSE_URL = os.environ.get("KATO_TEST_CLICKHOUSE_URL", "http://localhost:8123")
REDIS_URL = os.environ.get("KATO_TEST_REDIS_URL", "redis://localhost:6379/0")


def _ch(query: str, **params) -> str:
    resp = requests.post(CLICKHOUSE_URL, params={"query": query, **{f"param_{k}": v for k, v in params.items()}}, timeout=30)
    resp.raise_for_status()
    return resp.text.strip()


def _kb_id(node_id: str) -> str:
    # ProcessorManager builds kb_id as "<node_id>_<SERVICE_NAME>" for short, clean node_ids.
    return f"{node_id}_kato"


class Trainer:
    """One client thread: its own session, its own HTTP connection."""

    def __init__(self, base_url: str, node_id: str, index: int):
        self.base_url = base_url
        self.node_id = node_id
        self.index = index
        self.http = requests.Session()
        self.session_id = None
        self.unique_patterns: set[str] = set()
        self.shared_pattern: str | None = None

    def open(self) -> None:
        resp = self.http.post(f"{self.base_url}/sessions", json={"node_id": self.node_id, "ttl_seconds": 600}, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        self.session_id = resp.json()["session_id"]

    def _observe(self, symbol: str) -> None:
        resp = self.http.post(f"{self.base_url}/sessions/{self.session_id}/observe",
                              json={"strings": [symbol], "vectors": [], "emotives": {}}, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()

    def _learn(self) -> str:
        resp = self.http.post(f"{self.base_url}/sessions/{self.session_id}/learn", timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        name = resp.json()["pattern_name"]
        assert name, resp.text
        # The API returns the display form "PTRN|<sha1>"; stores key on the bare hash.
        return name.removeprefix("PTRN|")

    def run(self) -> None:
        for r in range(ROUNDS):
            # A pattern unique to this thread and round.
            for s in range(SYMBOLS_PER_PATTERN):
                self._observe(f"t{self.index}_r{r}_s{s}")
            self.unique_patterns.add(self._learn())
            # A pattern every thread learns every round: exercises the
            # new-pattern SETNX claim and the concurrent INCR path.
            for s in range(SYMBOLS_PER_PATTERN):
                self._observe(f"shared_s{s}")
            self.shared_pattern = self._learn()

    def clear_all(self) -> None:
        self.http.post(f"{self.base_url}/sessions/{self.session_id}/clear-all", timeout=REQUEST_TIMEOUT).raise_for_status()

    def close(self) -> None:
        if self.session_id:
            self.http.delete(f"{self.base_url}/sessions/{self.session_id}", timeout=REQUEST_TIMEOUT)
        self.http.close()


def run_workload(topology: KatoTopology) -> dict:
    node_id = f"perf_{topology.workers}w_{uuid.uuid4().hex[:8]}"
    kb_id = _kb_id(node_id)
    trainers = [Trainer(topology.base_url, node_id, i) for i in range(THREADS)]
    for t in trainers:
        t.open()
    try:
        started = time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=THREADS) as pool:
            for fut in [pool.submit(t.run) for t in trainers]:
                fut.result()
        elapsed = time.perf_counter() - started

        # Learns are the unit of work; each round does 2 per thread.
        learns = THREADS * ROUNDS * 2
        requests_made = THREADS * ROUNDS * (2 * SYMBOLS_PER_PATTERN + 2)

        # --- integrity, read after draining the async_insert queue ---
        _ch("SYSTEM FLUSH ASYNC INSERT QUEUE")
        unique = set().union(*(t.unique_patterns for t in trainers))
        shared = {t.shared_pattern for t in trainers}
        assert len(shared) == 1, f"threads disagree on the shared pattern's name: {shared}"
        shared_name = shared.pop()
        expected_patterns = len(unique) + 1

        rows = int(_ch("SELECT count() FROM kato.patterns_data WHERE kb_id = {kb:String}", kb=kb_id))
        distinct = int(_ch("SELECT uniqExact(name) FROM kato.patterns_data WHERE kb_id = {kb:String}", kb=kb_id))
        r = redis.Redis.from_url(REDIS_URL, decode_responses=True)
        redis_patterns = sum(1 for _ in r.scan_iter(match=f"{escape_glob(kb_id)}:frequency:*", count=5000))
        shared_freq = int(r.get(f"{kb_id}:frequency:{shared_name}") or 0)

        integrity = {
            "expected_patterns": expected_patterns, "clickhouse_rows": rows,
            "clickhouse_distinct": distinct, "redis_patterns": redis_patterns,
            "shared_frequency": shared_freq, "expected_shared_frequency": THREADS * ROUNDS,
        }
        assert len(unique) == THREADS * ROUNDS, f"unique patterns collided: {len(unique)} != {THREADS * ROUNDS}"
        assert rows == distinct == expected_patterns, f"duplicate or missing ClickHouse rows: {integrity}"
        assert redis_patterns == expected_patterns, f"Redis/ClickHouse pattern-count disagreement: {integrity}"
        assert shared_freq == THREADS * ROUNDS, f"shared pattern frequency lost updates: {integrity}"

        # --- every worker survived the contention (a deadlocked worker stops answering) ---
        alive = topology.health_pids(samples=32 * topology.workers)
        assert alive == topology.worker_pids, \
            f"workers no longer answering /health after the workload: {sorted(topology.worker_pids - alive)}"

        # --- cleanup leaves nothing ---
        trainers[0].clear_all()
        _ch("SYSTEM FLUSH ASYNC INSERT QUEUE")
        assert int(_ch("SELECT count() FROM kato.patterns_data WHERE kb_id = {kb:String}", kb=kb_id)) == 0
        assert int(_ch("SELECT count() FROM kato.patterns_metadata WHERE kb_id = {kb:String}", kb=kb_id)) == 0
        assert not list(r.scan_iter(match=f"{escape_glob(kb_id)}:*", count=5000)), "Redis keys survived clear-all"

        return {"workers": topology.workers, "elapsed_s": round(elapsed, 2),
                "learns_per_s": round(learns / elapsed, 1), "requests_per_s": round(requests_made / elapsed, 1),
                **integrity}
    finally:
        for t in trainers:
            t.close()


def test_multi_worker_throughput_and_integrity():
    results = {}
    for workers in WORKER_COUNTS:
        topo = KatoTopology(workers)
        topo.start()
        try:
            results[workers] = run_workload(topo)
        finally:
            topo.stop()

    one, four = results[1], results[4]
    speedup = four["learns_per_s"] / one["learns_per_s"]
    print(f"\nthreads={THREADS} rounds={ROUNDS}")
    for w in WORKER_COUNTS:
        print(f"  workers={w}: {results[w]['elapsed_s']}s  {results[w]['learns_per_s']} learns/s  "
              f"{results[w]['requests_per_s']} req/s")
    print(f"  speedup workers=4 vs 1: {speedup:.2f}x")

    assert speedup > 1.0, f"4 workers were not faster than 1: {results}"
