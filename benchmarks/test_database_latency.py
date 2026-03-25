"""
Raw database latency benchmarks for KATO infrastructure.

Measures baseline latency for ClickHouse, Redis, and CPU-bound computation
independent of KATO application logic. Establishes latency floors to help
distinguish I/O bottlenecks from computation bottlenecks.

Usage:
    python -m benchmarks.test_database_latency
    # Or via pytest:
    pytest benchmarks/test_database_latency.py -v -s
"""

import sys
import time
from itertools import chain
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from typing import Optional

from benchmarks.profiler import TimingCollector, perf_timer

# Lazy imports for optional dependencies
_clickhouse_client = None
_redis_client = None


def _get_clickhouse():
    global _clickhouse_client
    if _clickhouse_client is None:
        from kato.storage.connection_manager import OptimizedConnectionManager
        _clickhouse_client = OptimizedConnectionManager().clickhouse
    return _clickhouse_client


def _get_redis():
    global _redis_client
    if _redis_client is None:
        from kato.storage.connection_manager import OptimizedConnectionManager
        _redis_client = OptimizedConnectionManager().redis
    return _redis_client


def benchmark_clickhouse_queries(collector: TimingCollector, iterations: int = 50) -> None:
    """Benchmark raw ClickHouse query latency."""
    ch = _get_clickhouse()
    print("\n--- ClickHouse Query Latency ---")

    # SELECT 1 (connection round-trip)
    for _ in range(iterations):
        with perf_timer("db.ch.select_1", collector):
            ch.query("SELECT 1")

    # COUNT(*) on patterns_data
    for _ in range(iterations):
        with perf_timer("db.ch.count_all", collector):
            ch.query("SELECT COUNT(*) FROM kato.patterns_data")

    print(f"  SELECT 1: {collector.get_stats('db.ch.select_1')['mean']:.2f}ms mean ({iterations} samples)")
    print(f"  COUNT(*): {collector.get_stats('db.ch.count_all')['mean']:.2f}ms mean ({iterations} samples)")


def benchmark_clickhouse_in_clause(collector: TimingCollector,
                                    kb_id: str = "__bench_db_latency__",
                                    iterations: int = 20) -> None:
    """Benchmark ClickHouse SELECT with varying IN-clause sizes."""
    ch = _get_clickhouse()
    print("\n--- ClickHouse IN-Clause Scaling ---")

    # Generate fake pattern names
    fake_names = [f"fake_pattern_{i:06d}" for i in range(10_000)]

    for in_size in [10, 100, 1_000, 10_000]:
        label = f"db.ch.select_in_{in_size}"
        names_subset = fake_names[:in_size]
        names_str = ", ".join(f"'{n}'" for n in names_subset)

        for _ in range(iterations):
            with perf_timer(label, collector):
                ch.query(
                    f"SELECT name, pattern_data, length FROM kato.patterns_data "
                    f"WHERE kb_id = '{kb_id}' AND name IN ({names_str})"
                )

        stats = collector.get_stats(label)
        print(f"  IN({in_size:>5}): {stats['mean']:.2f}ms mean")


def benchmark_clickhouse_inserts(collector: TimingCollector,
                                  kb_id: str = "__bench_db_latency__") -> None:
    """Benchmark ClickHouse INSERT with varying batch sizes."""
    ch = _get_clickhouse()
    print("\n--- ClickHouse INSERT Batch Scaling ---")

    from datetime import datetime
    from datasketch import MinHash

    def make_row(i):
        tokens = [f"tok_{j}" for j in range(10)]
        mh = MinHash(num_perm=100)
        for t in tokens:
            mh.update(t.encode('utf8'))
        lsh_bands = [abs(hash(tuple(list(mh.hashvalues)[b*5:(b+1)*5]))) for b in range(20)]
        now = datetime.now()
        return [
            kb_id, f"bench_insert_{i}", [tokens], len(tokens),
            tokens, len(tokens), list(mh.hashvalues), lsh_bands,
            tokens[0], tokens[-1], now, now
        ]

    columns = [
        'kb_id', 'name', 'pattern_data', 'length',
        'token_set', 'token_count', 'minhash_sig', 'lsh_bands',
        'first_token', 'last_token', 'created_at', 'updated_at'
    ]

    for batch_size in [1, 10, 50, 100, 500]:
        label = f"db.ch.insert_batch_{batch_size}"
        rows = [make_row(i) for i in range(batch_size)]

        iterations = max(5, 50 // batch_size)
        for _ in range(iterations):
            with perf_timer(label, collector):
                ch.insert('kato.patterns_data', rows, column_names=columns)

        stats = collector.get_stats(label)
        print(f"  INSERT({batch_size:>3}): {stats['mean']:.2f}ms mean ({stats['mean']/batch_size:.3f}ms/row)")

    # Cleanup
    try:
        ch.command(f"ALTER TABLE kato.patterns_data DROP PARTITION '{kb_id}'")
    except Exception:
        pass


def benchmark_redis_operations(collector: TimingCollector, iterations: int = 100) -> None:
    """Benchmark raw Redis operation latency."""
    r = _get_redis()
    print("\n--- Redis Operation Latency ---")

    # PING
    for _ in range(iterations):
        with perf_timer("db.redis.ping", collector):
            r.ping()

    # SET + GET
    for i in range(iterations):
        key = f"__bench__:test:{i}"
        with perf_timer("db.redis.set", collector):
            r.set(key, f"value_{i}")
        with perf_timer("db.redis.get", collector):
            r.get(key)

    # Cleanup
    keys = list(r.scan_iter(match="__bench__:*", count=1000))
    if keys:
        r.delete(*keys)

    print(f"  PING: {collector.get_stats('db.redis.ping')['mean']:.3f}ms mean")
    print(f"  SET:  {collector.get_stats('db.redis.set')['mean']:.3f}ms mean")
    print(f"  GET:  {collector.get_stats('db.redis.get')['mean']:.3f}ms mean")


def benchmark_redis_batch(collector: TimingCollector, iterations: int = 20) -> None:
    """Benchmark Redis batch operations (MGET, pipeline) at varying sizes."""
    r = _get_redis()
    print("\n--- Redis Batch Scaling ---")

    # Seed some keys
    max_keys = 1000
    pipe = r.pipeline(transaction=False)
    for i in range(max_keys):
        pipe.set(f"__bench_batch__:{i}", f"value_{i}")
    pipe.execute()

    for batch_size in [1, 10, 100, 1_000]:
        keys = [f"__bench_batch__:{i}" for i in range(batch_size)]

        # MGET
        label_mget = f"db.redis.mget_{batch_size}"
        for _ in range(iterations):
            with perf_timer(label_mget, collector):
                r.mget(*keys)

        # Pipeline GET
        label_pipe = f"db.redis.pipeline_get_{batch_size}"
        for _ in range(iterations):
            with perf_timer(label_pipe, collector):
                p = r.pipeline(transaction=False)
                for k in keys:
                    p.get(k)
                p.execute()

        mget_stats = collector.get_stats(label_mget)
        pipe_stats = collector.get_stats(label_pipe)
        print(f"  MGET({batch_size:>4}):     {mget_stats['mean']:.3f}ms mean ({mget_stats['mean']/batch_size:.4f}ms/key)")
        print(f"  PIPELINE({batch_size:>4}): {pipe_stats['mean']:.3f}ms mean ({pipe_stats['mean']/batch_size:.4f}ms/key)")

    # Cleanup
    keys = list(r.scan_iter(match="__bench_batch__:*", count=1000))
    if keys:
        r.delete(*keys)


def benchmark_computation(collector: TimingCollector, iterations: int = 50) -> None:
    """Benchmark CPU-bound operations used in KATO."""
    print("\n--- Computation Baselines ---")

    from datasketch import MinHash
    from kato.representations.pattern import Pattern

    # MinHash computation at varying token counts
    for token_count in [10, 50, 200, 1_000]:
        label = f"compute.minhash_{token_count}"
        tokens = [f"tok_{i}".encode('utf8') for i in range(token_count)]

        for _ in range(iterations):
            with perf_timer(label, collector):
                mh = MinHash(num_perm=100)
                for t in tokens:
                    mh.update(t)
                _ = list(mh.hashvalues)

        stats = collector.get_stats(label)
        print(f"  MinHash({token_count:>4} tokens): {stats['mean']:.3f}ms mean")

    # Pattern construction
    for event_count in [2, 5, 10]:
        label = f"compute.pattern_init_{event_count}e"
        events = [[f"tok_{j}" for j in range(10)] for _ in range(event_count)]

        for _ in range(iterations):
            with perf_timer(label, collector):
                Pattern(events)

        stats = collector.get_stats(label)
        print(f"  Pattern({event_count} events): {stats['mean']:.4f}ms mean")

    # RapidFuzz similarity
    try:
        from rapidfuzz import fuzz, process
        from rapidfuzz.distance import LCSseq

        for seq_len in [10, 50, 200]:
            label = f"compute.rapidfuzz_lcs_{seq_len}"
            seq_a = " ".join(f"tok_{i}" for i in range(seq_len))
            seq_b = " ".join(f"tok_{i+5}" for i in range(seq_len))

            for _ in range(iterations):
                with perf_timer(label, collector):
                    LCSseq.similarity(seq_a, seq_b)

            stats = collector.get_stats(label)
            print(f"  RapidFuzz LCS({seq_len:>3} tokens): {stats['mean']:.4f}ms mean")

        # Batch extract (simulates matching against N candidates)
        for candidate_count in [10, 100, 1_000]:
            label = f"compute.rapidfuzz_extract_{candidate_count}"
            query = " ".join(f"tok_{i}" for i in range(20))
            candidates = [" ".join(f"tok_{i+j}" for i in range(20)) for j in range(candidate_count)]

            iters = max(5, iterations // (candidate_count // 10 + 1))
            for _ in range(iters):
                with perf_timer(label, collector):
                    process.extract(query, candidates, limit=candidate_count, score_cutoff=10.0)

            stats = collector.get_stats(label)
            print(f"  RapidFuzz extract({candidate_count:>4} candidates): {stats['mean']:.2f}ms mean")

    except ImportError:
        print("  (RapidFuzz not available, skipping)")


def run_all(collector: Optional[TimingCollector] = None) -> TimingCollector:
    """Run all database latency benchmarks."""
    if collector is None:
        collector = TimingCollector()

    print("=" * 70)
    print("  KATO Database Latency Benchmarks")
    print("=" * 70)

    benchmark_clickhouse_queries(collector)
    benchmark_clickhouse_in_clause(collector)
    benchmark_clickhouse_inserts(collector)
    benchmark_redis_operations(collector)
    benchmark_redis_batch(collector)
    benchmark_computation(collector)

    collector.print_summary("Database Latency Summary")
    return collector


if __name__ == "__main__":
    run_all()
