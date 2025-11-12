#!/usr/bin/env python3
"""
Migration Verification Script

Verifies that MongoDB data has been correctly migrated to ClickHouse and Redis
by comparing pattern counts, sampling data, and checking data integrity.

Usage:
    python scripts/verify_migration.py [--nodes "node0 node1"] [--sample-size 10]

Options:
    --nodes         Space-separated list of node names (default: "node0 node1 node2 node3")
    --sample-size   Number of patterns to sample for integrity check (default: 10)
    --mongo-host    MongoDB host (default: localhost)
    --mongo-port    MongoDB port (default: 27017)
    --clickhouse-host  ClickHouse host (default: localhost)
    --clickhouse-port  ClickHouse port (default: 8123)
    --redis-host    Redis host (default: localhost)
    --redis-port    Redis port (default: 6379)
"""

import argparse
import sys
import random
from typing import List, Dict, Any, Tuple
from pymongo import MongoClient
import clickhouse_connect
import redis

# ANSI color codes
GREEN = '\033[0;32m'
YELLOW = '\033[1;33m'
RED = '\033[0;31m'
BLUE = '\033[0;34m'
NC = '\033[0m'


def print_section(title: str):
    """Print a section header."""
    print(f"\n{BLUE}{'=' * 60}{NC}")
    print(f"{BLUE}{title}{NC}")
    print(f"{BLUE}{'=' * 60}{NC}")


def print_success(message: str):
    """Print a success message."""
    print(f"{GREEN}✓ {message}{NC}")


def print_error(message: str):
    """Print an error message."""
    print(f"{RED}✗ {message}{NC}")


def print_warning(message: str):
    """Print a warning message."""
    print(f"{YELLOW}⚠ {message}{NC}")


def get_mongodb_counts(mongo_client: MongoClient, nodes: List[str]) -> Dict[str, Dict[str, int]]:
    """Get pattern and metadata counts from MongoDB for each node."""
    print_section("MongoDB Pattern Counts")

    counts = {}
    total_patterns = 0
    total_metadata = 0

    for node in nodes:
        try:
            db = mongo_client[node]
            patterns_count = db.patterns_kb.count_documents({})
            metadata_count = db.metadata.count_documents({})

            counts[node] = {
                'patterns': patterns_count,
                'metadata': metadata_count
            }

            total_patterns += patterns_count
            total_metadata += metadata_count

            print(f"  {node}:")
            print(f"    Patterns:  {patterns_count:,}")
            print(f"    Metadata:  {metadata_count:,}")

        except Exception as e:
            print_error(f"Failed to query {node}: {e}")
            counts[node] = {'patterns': 0, 'metadata': 0}

    print(f"\n  {BLUE}Total across all nodes:{NC}")
    print(f"    Patterns:  {total_patterns:,}")
    print(f"    Metadata:  {total_metadata:,}")

    return counts


def get_clickhouse_count(clickhouse_client) -> int:
    """Get total pattern count from ClickHouse."""
    print_section("ClickHouse Pattern Count")

    try:
        result = clickhouse_client.query("SELECT COUNT(*) FROM kato.patterns_data")
        count = result.result_rows[0][0]
        print_success(f"ClickHouse patterns: {count:,}")
        return count
    except Exception as e:
        print_error(f"Failed to query ClickHouse: {e}")
        return 0


def get_redis_counts(redis_client) -> Dict[str, int]:
    """Get key counts from Redis by prefix."""
    print_section("Redis Key Counts")

    try:
        total_keys = redis_client.dbsize()

        # Count keys by prefix (all kb_ids)
        frequency_keys = len(redis_client.keys('*:frequency:*'))
        emotives_keys = len(redis_client.keys('*:emotives:*'))
        metadata_keys = len(redis_client.keys('*:metadata:*'))

        print(f"  Total keys:       {total_keys:,}")
        print(f"  Frequency keys:   {frequency_keys:,}")
        print(f"  Emotives keys:    {emotives_keys:,}")
        print(f"  Metadata keys:    {metadata_keys:,}")

        return {
            'total': total_keys,
            'frequency': frequency_keys,
            'emotives': emotives_keys,
            'metadata': metadata_keys
        }
    except Exception as e:
        print_error(f"Failed to query Redis: {e}")
        return {'total': 0, 'frequency': 0, 'emotives': 0, 'metadata': 0}


def sample_data_integrity(
    mongo_client: MongoClient,
    clickhouse_client,
    redis_client,
    nodes: List[str],
    sample_size: int
) -> Tuple[int, int]:
    """Sample random patterns and verify data integrity."""
    print_section(f"Data Integrity Check (sampling {sample_size} patterns)")

    success_count = 0
    failure_count = 0

    for node in nodes:
        db = mongo_client[node]
        patterns = list(db.patterns_kb.find({}, {'name': 1, 'pattern_data': 1, 'frequency': 1}).limit(sample_size))

        if not patterns:
            print_warning(f"No patterns found in {node}")
            continue

        print(f"\n  {node}:")

        for pattern in patterns[:min(sample_size, len(patterns))]:
            pattern_name = pattern.get('name', '')

            try:
                # Check ClickHouse
                ch_result = clickhouse_client.query(
                    f"SELECT name, pattern_data FROM kato.patterns_data WHERE kb_id = '{node}' AND name = '{pattern_name}'"
                )

                if not ch_result.result_rows:
                    print_error(f"    Pattern {pattern_name} not found in ClickHouse")
                    failure_count += 1
                    continue

                # Check Redis frequency (with kb_id namespace)
                redis_freq = redis_client.get(f'{node}:frequency:{pattern_name}')

                if redis_freq is None:
                    print_error(f"    Pattern {pattern_name} frequency not found in Redis")
                    failure_count += 1
                    continue

                # Verify frequency matches
                mongo_freq = pattern.get('frequency', 1)
                redis_freq_int = int(redis_freq)

                if mongo_freq != redis_freq_int:
                    print_warning(f"    Pattern {pattern_name} frequency mismatch: "
                                f"MongoDB={mongo_freq}, Redis={redis_freq_int}")
                    failure_count += 1
                    continue

                success_count += 1

            except Exception as e:
                print_error(f"    Pattern {pattern_name} check failed: {e}")
                failure_count += 1

        print(f"    Checked: {min(sample_size, len(patterns))} patterns")

    print(f"\n  {BLUE}Integrity Check Results:{NC}")
    print(f"    Passed: {success_count}")
    print(f"    Failed: {failure_count}")

    return success_count, failure_count


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Verify MongoDB → ClickHouse/Redis migration'
    )
    parser.add_argument(
        '--nodes',
        nargs='+',
        default=['node0', 'node1', 'node2', 'node3'],
        help='List of node names to verify (default: node0 node1 node2 node3)'
    )
    parser.add_argument(
        '--sample-size',
        type=int,
        default=10,
        help='Number of patterns to sample for integrity check (default: 10)'
    )
    parser.add_argument(
        '--mongo-host',
        default='localhost',
        help='MongoDB host (default: localhost)'
    )
    parser.add_argument(
        '--mongo-port',
        type=int,
        default=27017,
        help='MongoDB port (default: 27017)'
    )
    parser.add_argument(
        '--clickhouse-host',
        default='localhost',
        help='ClickHouse host (default: localhost)'
    )
    parser.add_argument(
        '--clickhouse-port',
        type=int,
        default=8123,
        help='ClickHouse port (default: 8123)'
    )
    parser.add_argument(
        '--redis-host',
        default='localhost',
        help='Redis host (default: localhost)'
    )
    parser.add_argument(
        '--redis-port',
        type=int,
        default=6379,
        help='Redis port (default: 6379)'
    )

    args = parser.parse_args()

    print(f"{BLUE}{'=' * 60}{NC}")
    print(f"{BLUE}Migration Verification Tool{NC}")
    print(f"{BLUE}{'=' * 60}{NC}")
    print(f"Nodes:      {', '.join(args.nodes)}")
    print(f"MongoDB:    {args.mongo_host}:{args.mongo_port}")
    print(f"ClickHouse: {args.clickhouse_host}:{args.clickhouse_port}")
    print(f"Redis:      {args.redis_host}:{args.redis_port}")

    # Connect to databases
    try:
        print("\nConnecting to databases...")
        mongo_client = MongoClient(f"mongodb://{args.mongo_host}:{args.mongo_port}")
        clickhouse_client = clickhouse_connect.get_client(
            host=args.clickhouse_host,
            port=args.clickhouse_port,
            database='kato'
        )
        redis_client = redis.Redis(
            host=args.redis_host,
            port=args.redis_port,
            decode_responses=True
        )

        # Test connections
        mongo_client.admin.command('ping')
        clickhouse_client.query("SELECT 1")
        redis_client.ping()

        print_success("All database connections established")

    except Exception as e:
        print_error(f"Failed to connect to databases: {e}")
        sys.exit(1)

    # Get counts
    mongo_counts = get_mongodb_counts(mongo_client, args.nodes)
    clickhouse_count = get_clickhouse_count(clickhouse_client)
    redis_counts = get_redis_counts(redis_client)

    # Calculate totals
    total_mongo_patterns = sum(node['patterns'] for node in mongo_counts.values())
    total_mongo_metadata = sum(node['metadata'] for node in mongo_counts.values())

    # Verification
    print_section("Verification Results")

    all_checks_passed = True

    # Check pattern counts
    if clickhouse_count == total_mongo_patterns:
        print_success(f"Pattern count matches: {clickhouse_count:,}")
    else:
        print_error(f"Pattern count mismatch: MongoDB={total_mongo_patterns:,}, "
                   f"ClickHouse={clickhouse_count:,} (diff: {abs(clickhouse_count - total_mongo_patterns)})")
        all_checks_passed = False

    # Check Redis frequency keys (should match pattern count)
    if redis_counts['frequency'] == total_mongo_patterns:
        print_success(f"Frequency keys match: {redis_counts['frequency']:,}")
    elif redis_counts['frequency'] == 0:
        print_warning("No frequency keys found in Redis (migration may have failed)")
        all_checks_passed = False
    else:
        print_warning(f"Frequency key count mismatch: Expected={total_mongo_patterns:,}, "
                     f"Found={redis_counts['frequency']:,} (diff: {abs(redis_counts['frequency'] - total_mongo_patterns)})")

    # Sample data integrity
    success, failure = sample_data_integrity(
        mongo_client, clickhouse_client, redis_client, args.nodes, args.sample_size
    )

    if failure > 0:
        all_checks_passed = False

    # Final summary
    print_section("Final Summary")

    if all_checks_passed and failure == 0:
        print_success("✓ All verification checks passed!")
        print_success("Migration appears to be successful and data integrity is intact")
        sys.exit(0)
    else:
        print_error("✗ Some verification checks failed")
        print_error("Review the errors above and consider re-running the migration")
        sys.exit(1)


if __name__ == '__main__':
    main()
