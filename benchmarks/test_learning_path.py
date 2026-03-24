"""
Learning path benchmarks for KATO.

Instruments the full observe→learn pipeline with per-operation timing:
- Pattern construction (SHA1 hash)
- ClickHouse row preparation (MinHash, LSH bands, token_set)
- ClickHouse batch INSERT (flush)
- Redis metadata writes (frequency, emotives, metadata)
- Redis symbol stats updates (batch pipeline)
- Searcher index update
- Cache invalidation

Usage:
    python -m benchmarks.test_learning_path
    # Or via pytest:
    pytest benchmarks/test_learning_path.py -v -s
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from benchmarks.profiler import (
    TimingCollector,
    instrument_instance,
    perf_timer,
)
from benchmarks.data_generator import BenchmarkDataGenerator


def run_learning_benchmark(tier_size: int, collector: TimingCollector,
                           generator: BenchmarkDataGenerator) -> dict:
    """
    Run learning path benchmark for a given tier size.

    Instruments actual KATO components via monkey-patching and measures
    per-operation timing as patterns are learned.

    Args:
        tier_size: Number of patterns to learn
        collector: TimingCollector to record timings to
        generator: Data generator instance

    Returns:
        Dict with tier results and processor_id for cleanup
    """
    from kato.workers.pattern_processor import PatternProcessor
    from kato.storage.clickhouse_writer import ClickHouseWriter
    from kato.storage.redis_writer import RedisWriter
    from kato.representations.pattern import Pattern
    from kato.config.settings import get_settings

    processor_id = BenchmarkDataGenerator.make_processor_id(tier_size)
    print(f"\n--- Learning Path Benchmark: {tier_size:,} patterns (kb_id={processor_id}) ---")

    # Generate patterns
    print(f"  Generating {tier_size:,} patterns...")
    patterns = generator.generate_patterns(tier_size)

    # Create PatternProcessor (this sets up all connections)
    settings = get_settings()
    pp = PatternProcessor(
        settings=settings,
        name=processor_id,
        kb_id=processor_id,
        max_pattern_length=0,
        persistence=7,
        max_predictions=100,
        recall_threshold=0.1,
        use_token_matching=True,
    )

    # Instrument components with timing labels prefixed by tier
    uninstrument_fns = []

    # Instrument ClickHouseWriter instance
    ch_writer = pp.superkb.clickhouse_writer
    uninstrument_fns.append(instrument_instance(ch_writer, {
        '_prepare_row': f'learn.ch.prepare_row',
        'flush': f'learn.ch.flush',
        'write_pattern': f'learn.ch.write_pattern',
    }, collector))

    # Instrument RedisWriter instance
    redis_writer = pp.superkb.redis_writer
    uninstrument_fns.append(instrument_instance(redis_writer, {
        'write_metadata': f'learn.redis.write_metadata',
        'get_frequency': f'learn.redis.get_frequency',
        'increment_frequency': f'learn.redis.incr_frequency',
        'get_metadata': f'learn.redis.get_metadata_single',
        'batch_update_symbol_stats': f'learn.redis.batch_symbol_stats',
    }, collector))

    # Instrument PatternSearcher
    searcher = pp.patterns_searcher
    uninstrument_fns.append(instrument_instance(searcher, {
        'assignNewlyLearnedToWorkers': f'learn.searcher.assign',
    }, collector))

    # Learn patterns
    print(f"  Learning {tier_size:,} patterns...")
    learn_start = time.perf_counter()

    for i, pattern in enumerate(patterns):
        # Simulate the learn path: load STM, call learn()
        with perf_timer('learn.total', collector):
            # Set STM to pattern data (this is what observe does before learn)
            pp.setSTM(pattern.pattern_data)
            pp.emotives = []
            pp.metadata = []
            pp.learn()

        if (i + 1) % max(1, tier_size // 10) == 0:
            elapsed = (time.perf_counter() - learn_start) * 1000
            rate = (i + 1) / (elapsed / 1000)
            print(f"    {i+1:>6,}/{tier_size:,} ({rate:.0f} patterns/sec)")

    total_elapsed = (time.perf_counter() - learn_start) * 1000
    print(f"  Total: {total_elapsed:.0f}ms ({tier_size / (total_elapsed / 1000):.0f} patterns/sec)")

    # Verify correctness
    actual_count = ch_writer.count_patterns()
    # Some patterns may have identical hashes (duplicates), so actual <= tier_size
    print(f"  Verification: {actual_count} patterns in ClickHouse (expected ~{tier_size})")

    # Restore original methods
    for uninstrument in uninstrument_fns:
        uninstrument()

    # Cleanup database
    try:
        ch_writer.delete_all_patterns()
        redis_writer.delete_all_metadata()
    except Exception as e:
        print(f"  Warning: cleanup failed: {e}")

    return {
        'tier_size': tier_size,
        'processor_id': processor_id,
        'total_ms': total_elapsed,
        'patterns_per_sec': tier_size / (total_elapsed / 1000),
        'actual_pattern_count': actual_count,
    }


def run_all(collector: TimingCollector = None,
            tiers: list[int] = None) -> TimingCollector:
    """Run learning path benchmarks across scale tiers."""
    if collector is None:
        collector = TimingCollector()
    if tiers is None:
        tiers = [100, 1_000, 10_000]

    generator = BenchmarkDataGenerator(seed=42)

    print("=" * 70)
    print("  KATO Learning Path Benchmarks")
    print("=" * 70)

    tier_results = []
    for tier in tiers:
        result = run_learning_benchmark(tier, collector, generator)
        tier_results.append(result)

    collector.print_summary("Learning Path Timing Summary")

    # Print per-tier throughput
    print(f"\n{'=' * 70}")
    print(f"  Learning Throughput by Tier")
    print(f"{'=' * 70}")
    print(f"  {'Tier':>10} {'Total (ms)':>12} {'Rate (p/s)':>12} {'Verified':>10}")
    print(f"  {'-' * 10} {'-' * 12} {'-' * 12} {'-' * 10}")
    for r in tier_results:
        print(f"  {r['tier_size']:>10,} {r['total_ms']:>11.0f}ms {r['patterns_per_sec']:>11.0f} {r['actual_pattern_count']:>10,}")
    print(f"{'=' * 70}")

    return collector


if __name__ == "__main__":
    run_all()
