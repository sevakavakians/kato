#!/usr/bin/env python3
"""
Rehydrate Redis metadata from ClickHouse patterns.

When Redis loses data (no persistence enabled), pattern metadata (frequency,
symbol stats, global counters, pre-computed metrics) is lost while ClickHouse
retains the actual pattern data. This script rebuilds all Redis metadata by
reading patterns from ClickHouse.

Usage:
    # Rehydrate specific kb_ids
    python scripts/rehydrate_redis.py --kb-ids node0_kato,node1_kato,node2_kato,node3_kato

    # Rehydrate ALL kb_ids found in ClickHouse
    python scripts/rehydrate_redis.py --all

    # Dry run (report what would be done without writing)
    python scripts/rehydrate_redis.py --kb-ids node0_kato --dry-run

    # Custom batch size and connections
    python scripts/rehydrate_redis.py --kb-ids node0_kato --batch-size 10000 \
        --clickhouse-host localhost --redis-url redis://localhost:6379

Limitations:
    - All frequencies default to 1 (historical frequency data is unrecoverable)
    - Emotives and per-pattern metadata are unrecoverable
    - Symbol affinity data is unrecoverable
"""

import argparse
import json
import sys
import time
from collections import Counter
from math import log, log2

import clickhouse_connect
import redis


def get_clickhouse_client(host: str, port: int, db: str,
                          user: str, password: str) -> clickhouse_connect.driver.Client:
    """Create ClickHouse client connection."""
    return clickhouse_connect.get_client(
        host=host,
        port=port,
        database=db,
        username=user,
        password=password
    )


def get_redis_client(redis_url: str) -> redis.Redis:
    """Create Redis client connection."""
    return redis.from_url(
        redis_url,
        decode_responses=True,
        encoding='utf-8'
    )


def discover_kb_ids(ch_client) -> list[str]:
    """Discover all kb_ids in ClickHouse."""
    result = ch_client.query(
        "SELECT kb_id, COUNT(*) as cnt FROM kato.patterns_data GROUP BY kb_id ORDER BY cnt DESC"
    )
    kb_ids = []
    for row in result.result_rows:
        kb_ids.append(row[0])
        print(f"  Found: {row[0]} ({row[1]:,} patterns)")
    return kb_ids


def rehydrate_kb_id(kb_id: str, ch_client, redis_client: redis.Redis,
                    batch_size: int, dry_run: bool) -> dict:
    """
    Rehydrate all Redis metadata for a single kb_id.

    Returns summary dict with counts and timing.
    """
    start = time.perf_counter()
    print(f"\n{'='*70}")
    print(f"Rehydrating: {kb_id}")
    print(f"{'='*70}")

    # Check existing Redis state
    existing_freq_count = sum(1 for _ in redis_client.scan_iter(
        match=f"{kb_id}:frequency:*", count=1000
    ))
    if existing_freq_count > 0:
        print(f"  WARNING: {existing_freq_count} frequency keys already exist for {kb_id}")
        print(f"  These will be overwritten with frequency=1")

    # Step 1: Query all patterns from ClickHouse
    print(f"\n  [1/5] Querying patterns from ClickHouse...")
    result = ch_client.query(
        f"SELECT name, pattern_data FROM kato.patterns_data WHERE kb_id = %(kb_id)s",
        parameters={'kb_id': kb_id}
    )

    patterns = result.result_rows
    pattern_count = len(patterns)
    print(f"         Found {pattern_count:,} patterns")

    if pattern_count == 0:
        print(f"  SKIP: No patterns found for {kb_id}")
        return {'kb_id': kb_id, 'patterns': 0, 'status': 'skipped'}

    if dry_run:
        print(f"  DRY RUN: Would rehydrate {pattern_count:,} patterns")
        elapsed = round((time.perf_counter() - start) * 1000, 2)
        return {
            'kb_id': kb_id, 'patterns': pattern_count,
            'status': 'dry_run', 'time_ms': elapsed
        }

    # Step 2: Write frequency metadata + accumulate symbol stats
    print(f"\n  [2/5] Writing frequency metadata and accumulating symbol stats...")
    total_symbol_occurrences = 0
    # Global accumulators
    symbol_freq = Counter()       # symbol -> total occurrences across all patterns
    symbol_pmf = Counter()        # symbol -> count of patterns containing this symbol
    symbol_to_patterns = {}       # symbol -> set of pattern names

    for batch_start in range(0, pattern_count, batch_size):
        batch_end = min(batch_start + batch_size, pattern_count)
        batch = patterns[batch_start:batch_end]

        pipe = redis_client.pipeline(transaction=False)

        for pattern_name, pattern_data in batch:
            # Write frequency = 1
            pipe.set(f"{kb_id}:frequency:{pattern_name}", 1)

            # Accumulate symbol stats
            all_symbols = [s for event in pattern_data for s in event]
            symbol_counts = Counter(all_symbols)
            total_symbol_occurrences += len(all_symbols)

            for symbol, count in symbol_counts.items():
                symbol_freq[symbol] += count
                if symbol not in symbol_to_patterns:
                    symbol_to_patterns[symbol] = set()
                symbol_to_patterns[symbol].add(pattern_name)

            # Count unique symbols per pattern (for pmf)
            for symbol in symbol_counts:
                symbol_pmf[symbol] += 1

        pipe.execute()
        progress = min(batch_end, pattern_count)
        print(f"         {progress:,}/{pattern_count:,} patterns processed", end='\r')

    print(f"         {pattern_count:,}/{pattern_count:,} patterns processed")
    unique_symbols = len(symbol_freq)
    print(f"         {unique_symbols:,} unique symbols found")

    # Step 3: Write symbol stats to Redis
    print(f"\n  [3/5] Writing symbol stats...")
    symbol_list = list(symbol_freq.keys())
    for batch_start in range(0, len(symbol_list), batch_size):
        batch_end = min(batch_start + batch_size, len(symbol_list))
        batch_symbols = symbol_list[batch_start:batch_end]

        pipe = redis_client.pipeline(transaction=False)
        for symbol in batch_symbols:
            # Symbol frequency (total occurrences)
            pipe.hset(f"{kb_id}:symbols:freq", symbol, symbol_freq[symbol])
            # Pattern member frequency (how many patterns contain this symbol)
            pipe.hset(f"{kb_id}:symbols:pmf", symbol, symbol_pmf[symbol])
            # Symbol-to-patterns mapping
            if symbol in symbol_to_patterns:
                members = list(symbol_to_patterns[symbol])
                # Write in sub-batches to avoid huge SADD commands
                for i in range(0, len(members), 1000):
                    pipe.sadd(f"{kb_id}:symbol_to_patterns:{symbol}", *members[i:i+1000])

        pipe.execute()
        progress = min(batch_end, len(symbol_list))
        print(f"         {progress:,}/{len(symbol_list):,} symbols written", end='\r')

    print(f"         {len(symbol_list):,}/{len(symbol_list):,} symbols written")

    # Step 4: Write global metadata
    print(f"\n  [4/5] Writing global metadata...")
    pipe = redis_client.pipeline(transaction=False)
    pipe.set(f"{kb_id}:global:total_unique_patterns", pattern_count)
    pipe.set(f"{kb_id}:global:total_pattern_frequencies", pattern_count)
    pipe.set(f"{kb_id}:global:total_symbols_in_patterns_frequencies", total_symbol_occurrences)
    pipe.execute()
    print(f"         total_unique_patterns = {pattern_count:,}")
    print(f"         total_pattern_frequencies = {pattern_count:,}")
    print(f"         total_symbols_in_patterns_frequencies = {total_symbol_occurrences:,}")

    # Step 5: Compute and write pre-computed metrics (entropy, TF vectors)
    print(f"\n  [5/5] Computing pre-computed metrics (entropy, TF vectors)...")

    # Build symbol probability cache: P(symbol) = pmf / total_unique_patterns
    symbol_probability_cache = {}
    for symbol, pmf_count in symbol_pmf.items():
        symbol_probability_cache[symbol] = pmf_count / pattern_count if pattern_count > 0 else 0.0

    total_symbols = unique_symbols
    metrics_written = 0

    for batch_start in range(0, pattern_count, batch_size):
        batch_end = min(batch_start + batch_size, pattern_count)
        batch = patterns[batch_start:batch_end]

        pipe = redis_client.pipeline(transaction=False)

        for pattern_name, pattern_data in batch:
            # Flatten pattern_data to symbol list
            pattern_symbols = [s for event in pattern_data for s in event]
            pattern_length = len(pattern_symbols)

            if pattern_length == 0:
                continue

            symbol_counts = Counter(pattern_symbols)

            # Shannon entropy: H = -sum(p_i * log2(p_i))
            entropy_val = 0.0
            for count in symbol_counts.values():
                if count > 0:
                    p = count / pattern_length
                    entropy_val -= p * log2(p)

            # Normalized entropy: uses log base = total_symbols
            normalized_entropy_val = 0.0
            if total_symbols > 1:
                for count in symbol_counts.values():
                    if count > 0:
                        p = count / pattern_length
                        normalized_entropy_val -= p * log(p, total_symbols)

            # Global normalized entropy: uses symbol probabilities from corpus
            global_normalized_entropy_val = 0.0
            if total_symbols > 1:
                for symbol in set(pattern_symbols):
                    prob = symbol_probability_cache.get(symbol, 0)
                    if prob > 0:
                        global_normalized_entropy_val -= prob * log(prob, total_symbols)

            # TF vector: {symbol: count / pattern_length}
            tf_vector = {
                symbol: count / pattern_length
                for symbol, count in symbol_counts.items()
            }

            # Write to Redis
            pipe.set(f"{kb_id}:entropy:{pattern_name}", str(entropy_val))
            pipe.set(f"{kb_id}:normalized_entropy:{pattern_name}", str(normalized_entropy_val))
            pipe.set(f"{kb_id}:global_normalized_entropy:{pattern_name}", str(global_normalized_entropy_val))
            pipe.set(f"{kb_id}:tf_vector:{pattern_name}", json.dumps(tf_vector))
            metrics_written += 1

        pipe.execute()
        progress = min(batch_end, pattern_count)
        print(f"         {progress:,}/{pattern_count:,} metrics computed", end='\r')

    print(f"         {metrics_written:,}/{pattern_count:,} metrics computed and written")

    elapsed = round((time.perf_counter() - start) * 1000, 2)
    elapsed_sec = elapsed / 1000

    print(f"\n  DONE: {kb_id}")
    print(f"    Patterns:  {pattern_count:,}")
    print(f"    Symbols:   {unique_symbols:,}")
    print(f"    Metrics:   {metrics_written:,}")
    print(f"    Time:      {elapsed_sec:.1f}s")

    return {
        'kb_id': kb_id,
        'patterns': pattern_count,
        'symbols': unique_symbols,
        'metrics': metrics_written,
        'status': 'completed',
        'time_ms': elapsed
    }


def main():
    parser = argparse.ArgumentParser(
        description='Rehydrate Redis metadata from ClickHouse patterns'
    )
    parser.add_argument(
        '--kb-ids',
        help='Comma-separated list of kb_ids to rehydrate (e.g., node0_kato,node1_kato)'
    )
    parser.add_argument(
        '--all', action='store_true',
        help='Rehydrate ALL kb_ids found in ClickHouse'
    )
    parser.add_argument(
        '--dry-run', action='store_true',
        help='Report what would be done without writing to Redis'
    )
    parser.add_argument(
        '--batch-size', type=int, default=5000,
        help='Number of patterns per Redis pipeline batch (default: 5000)'
    )
    parser.add_argument(
        '--clickhouse-host', default='localhost',
        help='ClickHouse host (default: localhost)'
    )
    parser.add_argument(
        '--clickhouse-port', type=int, default=8123,
        help='ClickHouse HTTP port (default: 8123)'
    )
    parser.add_argument(
        '--clickhouse-db', default='kato',
        help='ClickHouse database (default: kato)'
    )
    parser.add_argument(
        '--clickhouse-user', default='default',
        help='ClickHouse user (default: default)'
    )
    parser.add_argument(
        '--clickhouse-password', default='',
        help='ClickHouse password (default: empty)'
    )
    parser.add_argument(
        '--redis-url', default='redis://localhost:6379',
        help='Redis URL (default: redis://localhost:6379)'
    )

    args = parser.parse_args()

    if not args.kb_ids and not args.all:
        parser.error("Must specify --kb-ids or --all")

    print("=" * 70)
    print("KATO Redis Rehydration Tool")
    print("=" * 70)

    # Connect to ClickHouse
    print(f"\nConnecting to ClickHouse at {args.clickhouse_host}:{args.clickhouse_port}...")
    ch_client = get_clickhouse_client(
        host=args.clickhouse_host,
        port=args.clickhouse_port,
        db=args.clickhouse_db,
        user=args.clickhouse_user,
        password=args.clickhouse_password
    )
    print("  Connected")

    # Connect to Redis
    print(f"Connecting to Redis at {args.redis_url}...")
    redis_client = get_redis_client(args.redis_url)
    redis_client.ping()
    print("  Connected")

    # Determine kb_ids to process
    if args.all:
        print("\nDiscovering kb_ids in ClickHouse...")
        kb_ids = discover_kb_ids(ch_client)
    else:
        kb_ids = [k.strip() for k in args.kb_ids.split(',')]
        print(f"\nTarget kb_ids: {kb_ids}")

    if not kb_ids:
        print("No kb_ids to process. Exiting.")
        sys.exit(0)

    if args.dry_run:
        print("\n*** DRY RUN MODE - No data will be written ***")

    # Process each kb_id
    total_start = time.perf_counter()
    results = []
    for kb_id in kb_ids:
        result = rehydrate_kb_id(
            kb_id=kb_id,
            ch_client=ch_client,
            redis_client=redis_client,
            batch_size=args.batch_size,
            dry_run=args.dry_run
        )
        results.append(result)

    total_elapsed = time.perf_counter() - total_start

    # Summary
    print(f"\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}")
    total_patterns = sum(r.get('patterns', 0) for r in results)
    total_symbols = sum(r.get('symbols', 0) for r in results)
    total_metrics = sum(r.get('metrics', 0) for r in results)
    print(f"  kb_ids processed:  {len(results)}")
    print(f"  Total patterns:    {total_patterns:,}")
    print(f"  Total symbols:     {total_symbols:,}")
    print(f"  Total metrics:     {total_metrics:,}")
    print(f"  Total time:        {total_elapsed:.1f}s")

    for r in results:
        status = r.get('status', 'unknown')
        print(f"  {r['kb_id']}: {status} ({r.get('patterns', 0):,} patterns)")

    if not args.dry_run:
        print(f"\nRedis metadata successfully rehydrated.")
        print(f"NOTE: All frequencies set to 1 (historical frequency data is unrecoverable).")
        print(f"NOTE: Emotives and per-pattern metadata are unrecoverable.")


if __name__ == '__main__':
    main()
