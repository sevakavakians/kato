#!/usr/bin/env python3
"""
Hybrid Architecture Performance Benchmark

Compares MongoDB-only pattern matching performance vs ClickHouse/Redis hybrid architecture
across various dataset sizes and filter pipeline configurations.

Usage:
    python scripts/benchmark_hybrid_architecture.py [options]

Options:
    --dataset-sizes     Comma-separated list of pattern counts to test (default: "100,1000,10000")
    --num-queries       Number of query iterations per test (default: 10)
    --output-dir        Directory for benchmark results (default: benchmarks/)
    --skip-mongodb      Skip MongoDB-only benchmarks (only test hybrid)
    --skip-hybrid       Skip hybrid benchmarks (only test MongoDB)
    --verbose           Verbose logging

Examples:
    # Quick benchmark with small datasets
    python scripts/benchmark_hybrid_architecture.py --dataset-sizes "100,1000"

    # Full benchmark with multiple scales
    python scripts/benchmark_hybrid_architecture.py --dataset-sizes "100,1000,10000,50000"

    # Test only hybrid architecture
    python scripts/benchmark_hybrid_architecture.py --skip-mongodb
"""

import argparse
import json
import os
import random
import statistics
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Tuple

from pymongo import MongoClient
import clickhouse_connect
import redis

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from kato.config.session_config import SessionConfiguration
from kato.storage.connection_manager import (
    get_connection_manager,
    get_clickhouse_client,
    get_redis_client
)
from kato.searches.pattern_search import PatternSearcher

# ANSI color codes
GREEN = '\033[0;32m'
YELLOW = '\033[1;33m'
RED = '\033[0;31m'
BLUE = '\033[0;34m'
CYAN = '\033[0;36m'
BOLD = '\033[1m'
NC = '\033[0m'


def print_header(title: str):
    """Print a section header."""
    print(f"\n{BLUE}{BOLD}{'=' * 70}{NC}")
    print(f"{BLUE}{BOLD}{title:^70}{NC}")
    print(f"{BLUE}{BOLD}{'=' * 70}{NC}")


def print_subheader(title: str):
    """Print a subsection header."""
    print(f"\n{CYAN}{'-' * 70}{NC}")
    print(f"{CYAN}{title}{NC}")
    print(f"{CYAN}{'-' * 70}{NC}")


def print_success(message: str):
    """Print a success message."""
    print(f"{GREEN}✓ {message}{NC}")


def print_warning(message: str):
    """Print a warning message."""
    print(f"{YELLOW}⚠ {message}{NC}")


def print_error(message: str):
    """Print an error message."""
    print(f"{RED}✗ {message}{NC}")


def generate_random_pattern(length: int = 5) -> List[List[str]]:
    """Generate a random pattern for training."""
    pattern = []
    for i in range(length):
        event_size = random.randint(1, 3)
        event = [f"word_{random.randint(0, 1000)}" for _ in range(event_size)]
        pattern.append(event)
    return pattern


def generate_query_state(pattern_pool: List[List[List[str]]], overlap_ratio: float = 0.7) -> List[List[str]]:
    """
    Generate a query state based on existing patterns.

    Args:
        pattern_pool: Pool of learned patterns
        overlap_ratio: How much of a random pattern to use (0.0-1.0)

    Returns:
        Query state (partial pattern)
    """
    if not pattern_pool:
        return [["query_word"]]

    # Pick a random pattern
    pattern = random.choice(pattern_pool)

    # Take first N events (based on overlap ratio)
    overlap_length = max(1, int(len(pattern) * overlap_ratio))
    return pattern[:overlap_length]


class HybridBenchmark:
    """Benchmark runner for MongoDB vs Hybrid architecture comparison."""

    def __init__(self, output_dir: str = "benchmarks", verbose: bool = False):
        """
        Initialize benchmark runner.

        Args:
            output_dir: Directory for benchmark results
            verbose: Enable verbose logging
        """
        self.output_dir = output_dir
        self.verbose = verbose

        # Create output directory
        os.makedirs(output_dir, exist_ok=True)

        # Get database clients
        self.clickhouse_client = get_clickhouse_client()
        self.redis_client = get_redis_client()

        # Results storage
        self.results = {
            'metadata': {
                'timestamp': datetime.now().isoformat(),
                'environment': {
                    'mongodb_host': 'localhost:27017',
                    'clickhouse_host': 'localhost:8123',
                    'redis_host': 'localhost:6379'
                }
            },
            'mongodb_benchmarks': [],
            'hybrid_benchmarks': []
        }

    def setup_mongodb_kb(self, kb_id: str):
        """Set up MongoDB-only knowledge base."""
        mongo_client = MongoClient('mongodb://localhost:27017/')
        db = mongo_client[kb_id]

        # Clear existing data
        db.patterns_kb.delete_many({})
        db.symbols_kb.delete_many({})
        db.metadata.delete_many({})

        return db

    def setup_hybrid_infrastructure(self, kb_id: str):
        """Set up hybrid architecture (ClickHouse + Redis)."""
        # Clear ClickHouse
        if self.clickhouse_client:
            try:
                self.clickhouse_client.command(f"TRUNCATE TABLE IF EXISTS default.patterns_data")
            except Exception as e:
                if self.verbose:
                    print_warning(f"Could not truncate ClickHouse table: {e}")

        # Clear Redis
        if self.redis_client:
            try:
                # Clear only keys for this kb_id
                keys = self.redis_client.keys(f'*{kb_id}*')
                if keys:
                    self.redis_client.delete(*keys)
            except Exception as e:
                if self.verbose:
                    print_warning(f"Could not clear Redis keys: {e}")

    def load_training_data(self, db, num_patterns: int) -> List[List[List[str]]]:
        """
        Load training data into MongoDB knowledge base.

        Args:
            db: MongoDB database instance
            num_patterns: Number of patterns to generate and load

        Returns:
            List of generated patterns
        """
        patterns = []

        print(f"  Generating {num_patterns:,} random patterns...")
        for i in range(num_patterns):
            pattern = generate_random_pattern(length=random.randint(3, 8))
            patterns.append(pattern)

            if (i + 1) % 1000 == 0 and self.verbose:
                print(f"    Generated {i+1:,}/{num_patterns:,} patterns...")

        print(f"  Loading patterns into MongoDB...")
        start_time = time.time()

        for i, pattern in enumerate(patterns):
            # Flatten pattern to pattern_data format
            pattern_data = []
            for event in pattern:
                pattern_data.extend(event)

            # Create pattern document
            pattern_name = f"PTRN|benchmark_{i}_{hash(tuple(pattern_data))}"

            db.patterns_kb.update_one(
                {'name': pattern_name},
                {
                    '$set': {
                        'name': pattern_name,
                        'pattern_data': pattern_data,
                        'frequency': 1,
                        'length': len(pattern_data)
                    },
                    '$setOnInsert': {
                        'created_at': datetime.now()
                    }
                },
                upsert=True
            )

            if (i + 1) % 1000 == 0 and self.verbose:
                print(f"    Loaded {i+1:,}/{num_patterns:,} patterns...")

        load_time = time.time() - start_time
        print_success(f"Loaded {num_patterns:,} patterns in {load_time:.2f}s ({num_patterns/load_time:.0f} patterns/sec)")

        return patterns

    def migrate_to_hybrid(self, kb_id: str):
        """Migrate MongoDB data to ClickHouse and Redis."""
        print(f"  Migrating {kb_id} to ClickHouse and Redis...")

        start_time = time.time()

        # Run migration scripts
        import subprocess

        # Migrate to ClickHouse
        clickhouse_cmd = [
            'python', 'scripts/migrate_mongodb_to_clickhouse.py',
            '--mongo-url', f'mongodb://localhost:27017/{kb_id}',
            '--clickhouse-host', 'localhost',
            '--clickhouse-port', '8123',
            '--batch-size', '1000'
        ]

        result = subprocess.run(clickhouse_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print_error(f"ClickHouse migration failed: {result.stderr}")
            return False

        # Migrate to Redis
        redis_cmd = [
            'python', 'scripts/migrate_mongodb_to_redis.py',
            '--mongo-url', f'mongodb://localhost:27017/{kb_id}',
            '--redis-host', 'localhost',
            '--redis-port', '6379',
            '--batch-size', '1000'
        ]

        result = subprocess.run(redis_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print_error(f"Redis migration failed: {result.stderr}")
            return False

        migration_time = time.time() - start_time
        print_success(f"Migration completed in {migration_time:.2f}s")

        return True

    def benchmark_mongodb_queries(
        self,
        kb_id: str,
        pattern_pool: List[List[List[str]]],
        num_queries: int
    ) -> Dict[str, Any]:
        """
        Benchmark MongoDB-only pattern matching queries.

        Args:
            kb_id: Knowledge base ID
            pattern_pool: Pool of learned patterns
            num_queries: Number of query iterations

        Returns:
            Benchmark results
        """
        print_subheader(f"MongoDB Queries ({num_queries} iterations)")

        # Create PatternSearcher (MongoDB-only mode)
        searcher = PatternSearcher(
            kb_id=kb_id,
            max_predictions=100,
            recall_threshold=0.1,
            session_config=None,  # No config = MongoDB-only mode
            clickhouse_client=None,
            redis_client=None
        )

        query_times = []
        successful_queries = 0

        for i in range(num_queries):
            # Generate query state
            state = generate_query_state(pattern_pool, overlap_ratio=0.6)

            # Flatten state for token list
            state_tokens = []
            for event in state:
                state_tokens.extend(event)

            # Time the query
            start_time = time.time()
            try:
                predictions = searcher.causalBelief(state_tokens)
                query_time_ms = (time.time() - start_time) * 1000
                query_times.append(query_time_ms)
                successful_queries += 1

                if self.verbose and (i + 1) % 10 == 0:
                    print(f"    Query {i+1}/{num_queries}: {query_time_ms:.2f}ms ({len(predictions)} predictions)")

            except Exception as e:
                print_warning(f"Query {i+1} failed: {e}")

        # Calculate statistics
        if query_times:
            results = {
                'num_queries': num_queries,
                'successful_queries': successful_queries,
                'mean_latency_ms': statistics.mean(query_times),
                'median_latency_ms': statistics.median(query_times),
                'min_latency_ms': min(query_times),
                'max_latency_ms': max(query_times),
                'stdev_latency_ms': statistics.stdev(query_times) if len(query_times) > 1 else 0,
                'p95_latency_ms': sorted(query_times)[int(len(query_times) * 0.95)] if query_times else 0,
                'p99_latency_ms': sorted(query_times)[int(len(query_times) * 0.99)] if query_times else 0,
                'all_latencies_ms': query_times
            }

            print(f"  Mean latency:   {results['mean_latency_ms']:.2f}ms")
            print(f"  Median latency: {results['median_latency_ms']:.2f}ms")
            print(f"  P95 latency:    {results['p95_latency_ms']:.2f}ms")
            print(f"  P99 latency:    {results['p99_latency_ms']:.2f}ms")

            return results
        else:
            print_error("All queries failed")
            return {'error': 'all_queries_failed'}

    def benchmark_hybrid_queries(
        self,
        kb_id: str,
        pattern_pool: List[List[List[str]]],
        num_queries: int,
        filter_pipeline: List[str],
        pipeline_name: str
    ) -> Dict[str, Any]:
        """
        Benchmark hybrid architecture pattern matching queries.

        Args:
            kb_id: Knowledge base ID
            pattern_pool: Pool of learned patterns
            num_queries: Number of query iterations
            filter_pipeline: Filter pipeline configuration
            pipeline_name: Name of the pipeline (for reporting)

        Returns:
            Benchmark results
        """
        print_subheader(f"Hybrid Queries - {pipeline_name} ({num_queries} iterations)")

        # Create session config with filter pipeline
        session_config = SessionConfiguration(
            filter_pipeline=filter_pipeline,
            minhash_threshold=0.7,
            minhash_bands=20,
            minhash_rows=5,
            minhash_num_hashes=100,
            length_min_ratio=0.5,
            length_max_ratio=2.0,
            jaccard_threshold=0.3,
            jaccard_min_overlap=2,
            enable_filter_metrics=self.verbose
        )

        # Create PatternSearcher with hybrid architecture
        searcher = PatternSearcher(
            kb_id=kb_id,
            max_predictions=100,
            recall_threshold=0.1,
            session_config=session_config,
            clickhouse_client=self.clickhouse_client,
            redis_client=self.redis_client
        )

        query_times = []
        successful_queries = 0
        filter_metrics_list = []

        for i in range(num_queries):
            # Generate query state
            state = generate_query_state(pattern_pool, overlap_ratio=0.6)

            # Flatten state for token list
            state_tokens = []
            for event in state:
                state_tokens.extend(event)

            # Time the query
            start_time = time.time()
            try:
                predictions = searcher.causalBelief(state_tokens)
                query_time_ms = (time.time() - start_time) * 1000
                query_times.append(query_time_ms)
                successful_queries += 1

                # Collect filter metrics
                if searcher.filter_executor and self.verbose:
                    metrics = searcher.filter_executor.get_metrics()
                    filter_metrics_list.append(metrics)

                if self.verbose and (i + 1) % 10 == 0:
                    print(f"    Query {i+1}/{num_queries}: {query_time_ms:.2f}ms ({len(predictions)} predictions)")

            except Exception as e:
                print_warning(f"Query {i+1} failed: {e}")

        # Calculate statistics
        if query_times:
            results = {
                'pipeline_name': pipeline_name,
                'filter_pipeline': filter_pipeline,
                'num_queries': num_queries,
                'successful_queries': successful_queries,
                'mean_latency_ms': statistics.mean(query_times),
                'median_latency_ms': statistics.median(query_times),
                'min_latency_ms': min(query_times),
                'max_latency_ms': max(query_times),
                'stdev_latency_ms': statistics.stdev(query_times) if len(query_times) > 1 else 0,
                'p95_latency_ms': sorted(query_times)[int(len(query_times) * 0.95)] if query_times else 0,
                'p99_latency_ms': sorted(query_times)[int(len(query_times) * 0.99)] if query_times else 0,
                'all_latencies_ms': query_times,
                'filter_metrics': filter_metrics_list
            }

            print(f"  Mean latency:   {results['mean_latency_ms']:.2f}ms")
            print(f"  Median latency: {results['median_latency_ms']:.2f}ms")
            print(f"  P95 latency:    {results['p95_latency_ms']:.2f}ms")
            print(f"  P99 latency:    {results['p99_latency_ms']:.2f}ms")

            return results
        else:
            print_error("All queries failed")
            return {'error': 'all_queries_failed', 'pipeline_name': pipeline_name}

    def run_benchmark_suite(
        self,
        dataset_size: int,
        num_queries: int,
        skip_mongodb: bool = False,
        skip_hybrid: bool = False
    ) -> Dict[str, Any]:
        """
        Run complete benchmark suite for a given dataset size.

        Args:
            dataset_size: Number of patterns to test with
            num_queries: Number of query iterations per test
            skip_mongodb: Skip MongoDB benchmarks
            skip_hybrid: Skip hybrid benchmarks

        Returns:
            Benchmark results
        """
        print_header(f"Benchmarking with {dataset_size:,} patterns")

        kb_id = f"benchmark_{dataset_size}_{int(time.time())}"

        # Setup MongoDB knowledge base
        kb = self.setup_mongodb_kb(kb_id)

        # Load training data
        pattern_pool = self.load_training_data(kb, dataset_size)

        suite_results = {
            'dataset_size': dataset_size,
            'num_queries': num_queries,
            'mongodb_results': None,
            'hybrid_results': []
        }

        # Benchmark MongoDB-only queries
        if not skip_mongodb:
            print_subheader("MongoDB-Only Mode")
            mongodb_results = self.benchmark_mongodb_queries(kb_id, pattern_pool, num_queries)
            suite_results['mongodb_results'] = mongodb_results

        # Migrate to hybrid architecture
        if not skip_hybrid:
            print_subheader("Hybrid Architecture Migration")
            self.setup_hybrid_infrastructure(kb_id)

            if not self.migrate_to_hybrid(kb_id):
                print_error("Migration failed, skipping hybrid benchmarks")
                return suite_results

            # Test different filter pipelines
            pipelines = [
                (['length', 'jaccard', 'rapidfuzz'], 'Million-scale (no MinHash)'),
                (['minhash', 'length', 'jaccard', 'rapidfuzz'], 'Billion-scale (full pipeline)'),
                (['length', 'rapidfuzz'], 'Fast (minimal filtering)'),
            ]

            for filter_pipeline, pipeline_name in pipelines:
                hybrid_results = self.benchmark_hybrid_queries(
                    kb_id, pattern_pool, num_queries, filter_pipeline, pipeline_name
                )
                suite_results['hybrid_results'].append(hybrid_results)

        return suite_results

    def generate_report(self, all_results: List[Dict[str, Any]]):
        """Generate comprehensive benchmark report."""
        print_header("BENCHMARK REPORT")

        # Summary table
        print("\n{:<15} {:<20} {:<15} {:<15} {:<15}".format(
            "Dataset Size", "Mode", "Mean (ms)", "P95 (ms)", "P99 (ms)"
        ))
        print("-" * 80)

        for result in all_results:
            dataset_size = result['dataset_size']

            # MongoDB row
            if result['mongodb_results'] and 'error' not in result['mongodb_results']:
                mongo = result['mongodb_results']
                print("{:<15} {:<20} {:<15.2f} {:<15.2f} {:<15.2f}".format(
                    f"{dataset_size:,}",
                    "MongoDB",
                    mongo['mean_latency_ms'],
                    mongo['p95_latency_ms'],
                    mongo['p99_latency_ms']
                ))

            # Hybrid rows
            for hybrid in result['hybrid_results']:
                if 'error' not in hybrid:
                    print("{:<15} {:<20} {:<15.2f} {:<15.2f} {:<15.2f}".format(
                        "",
                        f"Hybrid-{hybrid['pipeline_name'][:12]}",
                        hybrid['mean_latency_ms'],
                        hybrid['p95_latency_ms'],
                        hybrid['p99_latency_ms']
                    ))

        print("\n" + "=" * 80)

        # Speedup analysis
        print_header("SPEEDUP ANALYSIS")

        for result in all_results:
            dataset_size = result['dataset_size']

            if result['mongodb_results'] and result['hybrid_results']:
                mongo_mean = result['mongodb_results'].get('mean_latency_ms', 0)

                print(f"\nDataset: {dataset_size:,} patterns")
                print(f"  MongoDB baseline: {mongo_mean:.2f}ms")

                for hybrid in result['hybrid_results']:
                    if 'error' not in hybrid:
                        hybrid_mean = hybrid['mean_latency_ms']
                        speedup = mongo_mean / hybrid_mean if hybrid_mean > 0 else 0

                        print(f"  {hybrid['pipeline_name']}: {hybrid_mean:.2f}ms ({speedup:.1f}x speedup)")

        # Save detailed results
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = os.path.join(self.output_dir, f'benchmark_results_{timestamp}.json')

        with open(output_file, 'w') as f:
            json.dump({
                'metadata': self.results['metadata'],
                'results': all_results
            }, f, indent=2, default=str)

        print_success(f"\nDetailed results saved to: {output_file}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Benchmark MongoDB vs ClickHouse/Redis hybrid architecture'
    )
    parser.add_argument(
        '--dataset-sizes',
        default='100,1000,10000',
        help='Comma-separated list of pattern counts (default: "100,1000,10000")'
    )
    parser.add_argument(
        '--num-queries',
        type=int,
        default=10,
        help='Number of query iterations per test (default: 10)'
    )
    parser.add_argument(
        '--output-dir',
        default='benchmarks',
        help='Directory for benchmark results (default: benchmarks/)'
    )
    parser.add_argument(
        '--skip-mongodb',
        action='store_true',
        help='Skip MongoDB-only benchmarks'
    )
    parser.add_argument(
        '--skip-hybrid',
        action='store_true',
        help='Skip hybrid architecture benchmarks'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )

    args = parser.parse_args()

    # Parse dataset sizes
    dataset_sizes = [int(x.strip()) for x in args.dataset_sizes.split(',')]

    print_header("HYBRID ARCHITECTURE BENCHMARK SUITE")
    print(f"Dataset sizes: {', '.join([f'{x:,}' for x in dataset_sizes])}")
    print(f"Queries per test: {args.num_queries}")
    print(f"Output directory: {args.output_dir}")

    # Create benchmark runner
    benchmark = HybridBenchmark(output_dir=args.output_dir, verbose=args.verbose)

    # Run benchmarks for each dataset size
    all_results = []

    for dataset_size in dataset_sizes:
        try:
            result = benchmark.run_benchmark_suite(
                dataset_size=dataset_size,
                num_queries=args.num_queries,
                skip_mongodb=args.skip_mongodb,
                skip_hybrid=args.skip_hybrid
            )
            all_results.append(result)

        except Exception as e:
            print_error(f"Benchmark failed for dataset size {dataset_size:,}: {e}")
            import traceback
            traceback.print_exc()

    # Generate report
    if all_results:
        benchmark.generate_report(all_results)
    else:
        print_error("No benchmark results to report")


if __name__ == '__main__':
    main()
