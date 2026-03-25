"""
Prediction path benchmarks for KATO.

Instruments both prediction paths:
1. Single-symbol fast path (Redis index → ClickHouse batch → similarity)
2. Multi-symbol full path (filter pipeline → RapidFuzz → metrics)

Usage:
    python -m benchmarks.test_prediction_path
    # Or via pytest:
    pytest benchmarks/test_prediction_path.py -v -s
"""

import asyncio
import sys
import time
from itertools import chain
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from benchmarks.profiler import (
    TimingCollector,
    instrument_instance,
    perf_timer,
)
from benchmarks.data_generator import BenchmarkDataGenerator


def _setup_processor(processor_id: str):
    """Create a PatternProcessor with given kb_id."""
    from kato.workers.pattern_processor import PatternProcessor
    from kato.config.settings import get_settings

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
    return pp


def _load_patterns(pp, patterns):
    """Learn patterns into the processor's storage."""
    # Ensure patterns_kb is accessible (learn() references self.patterns_kb)
    if not hasattr(pp, 'patterns_kb') or pp.patterns_kb is None:
        pp.patterns_kb = pp.superkb.patterns_kb
    for pattern in patterns:
        pp.setSTM(pattern.pattern_data)
        pp.emotives = []
        pp.metadata = []
        pp.learn()


def run_prediction_benchmark(tier_size: int, collector: TimingCollector,
                              generator: BenchmarkDataGenerator,
                              num_queries: int = 50) -> dict:
    """
    Run prediction path benchmark for a given tier size.

    Loads patterns, then runs both single-symbol and multi-symbol predictions
    with per-operation timing.

    Args:
        tier_size: Number of patterns to preload
        collector: TimingCollector to record timings to
        generator: Data generator instance
        num_queries: Number of prediction queries to run per path

    Returns:
        Dict with tier results
    """
    from kato.storage.clickhouse_writer import ClickHouseWriter
    from kato.storage.redis_writer import RedisWriter
    from kato.searches.pattern_search import PatternSearcher, InformationExtractor
    from kato.filters.executor import FilterPipelineExecutor

    processor_id = BenchmarkDataGenerator.make_processor_id(tier_size)
    print(f"\n--- Prediction Path Benchmark: {tier_size:,} patterns (kb_id={processor_id}) ---")

    # Generate and load patterns
    print(f"  Generating {tier_size:,} patterns...")
    patterns = generator.generate_patterns(tier_size)

    print(f"  Loading {tier_size:,} patterns into storage...")
    pp = _setup_processor(processor_id)
    load_start = time.perf_counter()
    _load_patterns(pp, patterns)
    load_ms = (time.perf_counter() - load_start) * 1000
    print(f"  Loaded in {load_ms:.0f}ms")

    # Generate queries
    single_queries = generator.generate_single_symbol_queries(patterns, count=num_queries)
    multi_queries = generator.generate_observations(patterns, count=num_queries,
                                                     min_stm_events=2, max_stm_events=5)

    # Instrument components for prediction path
    uninstrument_fns = []

    # Instrument RedisWriter for prediction reads
    redis_writer = pp.superkb.redis_writer
    uninstrument_fns.append(instrument_instance(redis_writer, {
        'get_patterns_for_symbol': 'predict.redis.get_patterns_for_symbol',
        'get_metadata_batch': 'predict.redis.get_metadata_batch',
        'get_global_metadata': 'predict.redis.get_global_metadata',
        'get_all_symbols_batch': 'predict.redis.get_all_symbols_batch',
    }, collector))

    # Instrument PatternSearcher
    searcher = pp.patterns_searcher
    uninstrument_fns.append(instrument_instance(searcher, {
        'causalBelief': 'predict.searcher.causalBelief',
    }, collector))

    # Instrument the async method
    uninstrument_fns.append(instrument_instance(searcher, {
        'causalBeliefAsync': 'predict.searcher.causalBeliefAsync',
    }, collector, async_methods={'causalBeliefAsync'}))

    # --- Single-Symbol Fast Path ---
    print(f"\n  Single-symbol fast path ({len(single_queries)} queries)...")
    single_start = time.perf_counter()

    loop = asyncio.new_event_loop()
    for i, query in enumerate(single_queries):
        with perf_timer('predict.fast.total', collector):
            result = loop.run_until_complete(
                pp._predict_single_symbol_fast(query['symbol'], stm_events=query['stm'])
            )
        if i == 0:
            print(f"    First query: {len(result)} predictions for symbol '{query['symbol']}'")

    single_ms = (time.perf_counter() - single_start) * 1000
    print(f"  Single-symbol total: {single_ms:.0f}ms ({single_ms/max(1,len(single_queries)):.1f}ms avg)")

    # --- Multi-Symbol Full Path ---
    print(f"\n  Multi-symbol full path ({len(multi_queries)} queries)...")
    multi_start = time.perf_counter()

    for i, query in enumerate(multi_queries):
        # Set STM and run predictions
        pp.setSTM(query['stm'])
        pp.trigger_predictions = True

        with perf_timer('predict.full.total', collector):
            result = loop.run_until_complete(
                pp.predictPattern(query['stm_flat'], stm_events=list(pp.STM))
            )
        if i == 0:
            print(f"    First query: {len(result)} predictions for {len(query['stm_flat'])} symbols")

    multi_ms = (time.perf_counter() - multi_start) * 1000
    print(f"  Multi-symbol total: {multi_ms:.0f}ms ({multi_ms/max(1,len(multi_queries)):.1f}ms avg)")

    loop.close()

    # Collect filter pipeline stage metrics from searcher
    if hasattr(searcher, 'filter_executor') and searcher.filter_executor:
        fe = searcher.filter_executor
        if hasattr(fe, 'stage_metrics') and fe.stage_metrics:
            print(f"\n  Filter pipeline stage metrics (last run):")
            for sm in fe.stage_metrics:
                stage_name = sm.get('filter', 'unknown')
                stage_ms = sm.get('duration_ms', 0)
                in_count = sm.get('candidates_in', 0)
                out_count = sm.get('candidates_out', 0)
                print(f"    {stage_name:<20}: {stage_ms:.1f}ms ({in_count} -> {out_count} candidates)")

    # Restore original methods
    for uninstrument in uninstrument_fns:
        uninstrument()

    # Cleanup database
    try:
        pp.superkb.clickhouse_writer.delete_all_patterns()
        pp.superkb.redis_writer.delete_all_metadata()
    except Exception as e:
        print(f"  Warning: cleanup failed: {e}")

    return {
        'tier_size': tier_size,
        'processor_id': processor_id,
        'single_symbol_queries': len(single_queries),
        'single_symbol_total_ms': single_ms,
        'single_symbol_avg_ms': single_ms / max(1, len(single_queries)),
        'multi_symbol_queries': len(multi_queries),
        'multi_symbol_total_ms': multi_ms,
        'multi_symbol_avg_ms': multi_ms / max(1, len(multi_queries)),
    }


def run_all(collector: TimingCollector = None,
            tiers: list[int] = None) -> TimingCollector:
    """Run prediction path benchmarks across scale tiers."""
    if collector is None:
        collector = TimingCollector()
    if tiers is None:
        tiers = [100, 1_000, 10_000]

    generator = BenchmarkDataGenerator(seed=42)

    print("=" * 70)
    print("  KATO Prediction Path Benchmarks")
    print("=" * 70)

    tier_results = []
    for tier in tiers:
        result = run_prediction_benchmark(tier, collector, generator)
        tier_results.append(result)

    collector.print_summary("Prediction Path Timing Summary")

    # Print per-tier summary
    print(f"\n{'=' * 70}")
    print(f"  Prediction Latency by Tier")
    print(f"{'=' * 70}")
    print(f"  {'Tier':>10} {'Fast Avg':>12} {'Full Avg':>12} {'Fast Queries':>14} {'Full Queries':>14}")
    print(f"  {'-' * 10} {'-' * 12} {'-' * 12} {'-' * 14} {'-' * 14}")
    for r in tier_results:
        print(
            f"  {r['tier_size']:>10,} "
            f"{r['single_symbol_avg_ms']:>10.1f}ms "
            f"{r['multi_symbol_avg_ms']:>10.1f}ms "
            f"{r['single_symbol_queries']:>14d} "
            f"{r['multi_symbol_queries']:>14d}"
        )
    print(f"{'=' * 70}")

    return collector


if __name__ == "__main__":
    run_all()
