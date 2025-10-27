#!/usr/bin/env python3
"""
Baseline performance benchmarks for KATO pattern matching.

Measures current performance before GPU optimization.
Results stored in benchmarks/results/baseline_YYYYMMDD_HHMMSS.json

Usage:
    # Run all benchmarks (may take several minutes for large datasets)
    python benchmarks/baseline.py

    # Run quick benchmarks (skip 1M patterns)
    python benchmarks/baseline.py --quick

Requirements:
    - KATO services running (./start.sh)
    - MongoDB accessible at localhost:27017
"""

import argparse
import json
import sys
import time
from datetime import datetime
from itertools import chain
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
from pymongo import MongoClient

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from kato.searches.pattern_search import PatternSearcher
from kato.representations.pattern import Pattern


class BenchmarkRunner:
    """Run pattern matching benchmarks."""

    def __init__(self, processor_id: str = "benchmark"):
        """
        Initialize benchmark runner.

        Args:
            processor_id: Unique identifier for database isolation
        """
        self.processor_id = processor_id
        self.results = {
            "benchmark_id": f"baseline_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "processor_id": processor_id,
            "timestamp": datetime.now().isoformat(),
            "system_info": self._get_system_info(),
            "tests": []
        }

    def _get_system_info(self) -> Dict[str, Any]:
        """Collect system information."""
        import platform
        import psutil

        return {
            "platform": platform.platform(),
            "python_version": platform.python_version(),
            "cpu_count": psutil.cpu_count(),
            "cpu_count_physical": psutil.cpu_count(logical=False),
            "memory_gb": round(psutil.virtual_memory().total / 1e9, 2),
            "cpu_model": platform.processor()
        }

    def generate_test_patterns(
        self,
        count: int,
        min_events: int = 2,
        max_events: int = 5,
        min_symbols_per_event: int = 5,
        max_symbols_per_event: int = 20
    ) -> List[Pattern]:
        """
        Generate random test patterns.

        Args:
            count: Number of patterns to generate
            min_events: Minimum number of events per pattern
            max_events: Maximum number of events per pattern
            min_symbols_per_event: Minimum symbols per event
            max_symbols_per_event: Maximum symbols per event

        Returns:
            List of Pattern objects
        """
        patterns = []

        # Vocabulary of test symbols
        vocab = [f"sym{i}" for i in range(100)]
        vocab += [f"VCTR|{i:04x}" for i in range(50)]

        for i in range(count):
            # Random number of events (2-5)
            num_events = np.random.randint(min_events, max_events + 1)

            # Random symbols per event
            events = []
            for _ in range(num_events):
                event_length = np.random.randint(min_symbols_per_event, max_symbols_per_event + 1)
                event = sorted(list(np.random.choice(vocab, event_length, replace=False)))
                events.append(event)

            pattern = Pattern(events)
            patterns.append(pattern)

        return patterns

    def benchmark_query(
        self,
        pattern_count: int,
        query_length: int,
        iterations: int = 10
    ) -> Dict[str, Any]:
        """
        Benchmark pattern matching query performance.

        Args:
            pattern_count: Number of patterns to match against
            query_length: Length of query sequence
            iterations: Number of test iterations

        Returns:
            Benchmark results dict
        """
        print(f"\n{'='*60}")
        print(f"Benchmarking: {pattern_count:,} patterns, query length {query_length}")
        print(f"{'='*60}")

        # Generate test patterns
        print(f"Generating {pattern_count:,} test patterns...")
        start_gen = time.time()
        patterns = self.generate_test_patterns(pattern_count)
        gen_time = time.time() - start_gen
        print(f"  Generation time: {gen_time:.2f}s")

        # Store in MongoDB
        print("Storing patterns in MongoDB...")
        mongo_client = MongoClient("mongodb://localhost:27017")
        kb = mongo_client[self.processor_id]

        # Clear existing
        kb.patterns_kb.delete_many({})
        kb.symbols_kb.delete_many({})
        kb.metadata.delete_many({})

        # Insert patterns
        start_insert = time.time()
        pattern_docs = []
        for pattern in patterns:
            pattern_docs.append({
                "name": pattern.name,
                "pattern_data": pattern.pattern_data,
                "frequency": 1,
                "length": len(list(chain(*pattern.pattern_data)))
            })

        if pattern_docs:
            kb.patterns_kb.insert_many(pattern_docs)

        insert_time = time.time() - start_insert
        print(f"  Insertion time: {insert_time:.2f}s")

        # Create searcher
        print("Initializing pattern searcher...")
        searcher = PatternSearcher(
            kb_id=self.processor_id,
            max_predictions=100,
            recall_threshold=0.1
        )

        # Generate query
        vocab = [f"sym{i}" for i in range(100)]
        query_state = sorted(list(np.random.choice(vocab, query_length, replace=False)))

        print(f"Query ({len(query_state)} symbols): {query_state[:5]}{'...' if len(query_state) > 5 else ''}")

        # Warmup
        print("Warming up (3 iterations)...")
        for i in range(3):
            start = time.time()
            searcher.causalBelief(query_state, stm_events=None)
            warmup_time = (time.time() - start) * 1000
            print(f"  Warmup {i+1}: {warmup_time:.2f}ms")

        # Benchmark
        print(f"\nRunning {iterations} benchmark iterations...")
        latencies = []

        for i in range(iterations):
            start = time.perf_counter()
            results = searcher.causalBelief(query_state, stm_events=None)
            latency = (time.perf_counter() - start) * 1000  # Convert to ms
            latencies.append(latency)

            print(f"  Iteration {i+1}/{iterations}: {latency:.2f}ms ({len(results)} matches)")

        # Calculate statistics
        latencies_np = np.array(latencies)
        result = {
            "pattern_count": pattern_count,
            "query_length": query_length,
            "iterations": iterations,
            "latency_ms": {
                "min": float(latencies_np.min()),
                "max": float(latencies_np.max()),
                "mean": float(latencies_np.mean()),
                "median": float(np.median(latencies_np)),
                "p95": float(np.percentile(latencies_np, 95)),
                "p99": float(np.percentile(latencies_np, 99)),
                "std": float(latencies_np.std())
            },
            "throughput": {
                "patterns_per_second": pattern_count / (latencies_np.mean() / 1000),
                "queries_per_second": 1000 / latencies_np.mean()
            },
            "generation_time_s": gen_time,
            "insertion_time_s": insert_time
        }

        print(f"\n{'─'*60}")
        print(f"Results:")
        print(f"  Mean latency:   {result['latency_ms']['mean']:.2f}ms")
        print(f"  Median latency: {result['latency_ms']['median']:.2f}ms")
        print(f"  P95 latency:    {result['latency_ms']['p95']:.2f}ms")
        print(f"  P99 latency:    {result['latency_ms']['p99']:.2f}ms")
        print(f"  Throughput:     {result['throughput']['patterns_per_second']:.0f} patterns/sec")
        print(f"{'─'*60}")

        # Cleanup
        kb.patterns_kb.delete_many({})
        mongo_client.close()

        return result

    def benchmark_learning(self, count: int = 1000) -> Dict[str, Any]:
        """
        Benchmark pattern learning performance.

        Args:
            count: Number of patterns to learn

        Returns:
            Benchmark results dict
        """
        print(f"\n{'='*60}")
        print(f"Benchmarking: Learning {count:,} patterns")
        print(f"{'='*60}")

        # Generate patterns
        print(f"Generating {count:,} test patterns...")
        patterns = self.generate_test_patterns(count)

        # Setup MongoDB
        mongo_client = MongoClient("mongodb://localhost:27017")
        kb = mongo_client[self.processor_id]
        kb.patterns_kb.delete_many({})

        # Create searcher
        searcher = PatternSearcher(
            kb_id=self.processor_id,
            max_predictions=100,
            recall_threshold=0.1
        )

        # Benchmark learning
        print(f"Learning {count:,} patterns...")
        latencies = []

        for i, pattern in enumerate(patterns):
            start = time.perf_counter()

            # Store in MongoDB
            kb.patterns_kb.insert_one({
                "name": pattern.name,
                "pattern_data": pattern.pattern_data,
                "frequency": 1,
                "length": len(list(chain(*pattern.pattern_data)))
            })

            # Add to searcher indices
            flattened = list(chain(*pattern.pattern_data))
            searcher.assignNewlyLearnedToWorkers(0, pattern.name, flattened)

            latency = (time.perf_counter() - start) * 1000
            latencies.append(latency)

            if (i + 1) % 100 == 0:
                avg_last_100 = np.mean(latencies[-100:])
                print(f"  Learned {i+1:,}/{count:,} patterns (avg last 100: {avg_last_100:.3f}ms)")

        latencies_np = np.array(latencies)
        result = {
            "pattern_count": count,
            "latency_ms": {
                "min": float(latencies_np.min()),
                "max": float(latencies_np.max()),
                "mean": float(latencies_np.mean()),
                "median": float(np.median(latencies_np)),
                "p95": float(np.percentile(latencies_np, 95)),
                "p99": float(np.percentile(latencies_np, 99))
            },
            "throughput": {
                "patterns_per_second": 1000 / latencies_np.mean()
            }
        }

        print(f"\n{'─'*60}")
        print(f"Results:")
        print(f"  Mean latency:   {result['latency_ms']['mean']:.3f}ms per pattern")
        print(f"  Median latency: {result['latency_ms']['median']:.3f}ms per pattern")
        print(f"  P95 latency:    {result['latency_ms']['p95']:.3f}ms per pattern")
        print(f"  Throughput:     {result['throughput']['patterns_per_second']:.0f} patterns/sec")
        print(f"{'─'*60}")

        # Cleanup
        kb.patterns_kb.delete_many({})
        mongo_client.close()

        return result

    def run_all_benchmarks(self, quick: bool = False):
        """
        Run complete benchmark suite.

        Args:
            quick: If True, skip 1M pattern benchmark (faster but less complete)
        """
        print("="*60)
        print("KATO Pattern Matching Baseline Benchmarks")
        print("="*60)
        print(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Processor ID: {self.processor_id}")
        print("")

        # Query benchmarks - various pattern counts
        test_configs = [
            (1_000, 10, 10),     # 1K patterns, 10 iterations
            (10_000, 10, 10),    # 10K patterns, 10 iterations
            (100_000, 10, 5),    # 100K patterns, 5 iterations (slower)
        ]

        if not quick:
            test_configs.append((1_000_000, 10, 3))  # 1M patterns, 3 iterations (very slow!)

        for pattern_count, query_length, iterations in test_configs:
            try:
                result = self.benchmark_query(pattern_count, query_length, iterations=iterations)
                self.results["tests"].append({
                    "test_type": "query",
                    "result": result
                })
            except Exception as e:
                print(f"\n❌ ERROR in query benchmark ({pattern_count:,} patterns): {e}")
                self.results["tests"].append({
                    "test_type": "query",
                    "error": str(e),
                    "pattern_count": pattern_count
                })

        # Learning benchmark
        try:
            learning_result = self.benchmark_learning(count=1000)
            self.results["tests"].append({
                "test_type": "learning",
                "result": learning_result
            })
        except Exception as e:
            print(f"\n❌ ERROR in learning benchmark: {e}")
            self.results["tests"].append({
                "test_type": "learning",
                "error": str(e)
            })

        # Save results
        output_dir = Path("benchmarks/results")
        output_dir.mkdir(parents=True, exist_ok=True)

        output_file = output_dir / f"baseline_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(output_file, 'w') as f:
            json.dump(self.results, f, indent=2)

        print(f"\n{'='*60}")
        print(f"✅ Benchmarks complete!")
        print(f"Results saved to: {output_file}")
        print(f"End time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}")

        return self.results

    def print_summary(self):
        """Print summary of benchmark results."""
        print("\n" + "="*60)
        print("BENCHMARK SUMMARY")
        print("="*60)

        for test in self.results["tests"]:
            if "error" in test:
                print(f"\n❌ {test['test_type'].upper()} - ERROR")
                print(f"   {test.get('error', 'Unknown error')}")
                continue

            if test["test_type"] == "query":
                r = test["result"]
                print(f"\nQuery Benchmark ({r['pattern_count']:,} patterns):")
                print(f"  Mean:   {r['latency_ms']['mean']:>10.2f}ms")
                print(f"  Median: {r['latency_ms']['median']:>10.2f}ms")
                print(f"  P95:    {r['latency_ms']['p95']:>10.2f}ms")
                print(f"  P99:    {r['latency_ms']['p99']:>10.2f}ms")
                print(f"  Throughput: {r['throughput']['patterns_per_second']:>8.0f} patterns/sec")
            elif test["test_type"] == "learning":
                r = test["result"]
                print(f"\nLearning Benchmark ({r['pattern_count']:,} patterns):")
                print(f"  Mean:   {r['latency_ms']['mean']:>10.3f}ms per pattern")
                print(f"  Median: {r['latency_ms']['median']:>10.3f}ms per pattern")
                print(f"  P95:    {r['latency_ms']['p95']:>10.3f}ms per pattern")
                print(f"  Throughput: {r['throughput']['patterns_per_second']:>8.0f} patterns/sec")

        print("\n" + "="*60)


def main():
    """Run benchmark suite."""
    parser = argparse.ArgumentParser(description="Run KATO baseline benchmarks")
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Skip 1M pattern benchmark for faster testing"
    )
    parser.add_argument(
        "--processor-id",
        default="benchmark_baseline",
        help="Processor ID for database isolation (default: benchmark_baseline)"
    )
    args = parser.parse_args()

    # Check MongoDB availability
    try:
        client = MongoClient("mongodb://localhost:27017", serverSelectionTimeoutMS=2000)
        client.admin.command('ping')
        client.close()
    except Exception as e:
        print("❌ ERROR: Cannot connect to MongoDB at localhost:27017")
        print(f"   {e}")
        print("\nPlease start KATO services:")
        print("  ./start.sh")
        sys.exit(1)

    # Run benchmarks
    runner = BenchmarkRunner(processor_id=args.processor_id)

    try:
        results = runner.run_all_benchmarks(quick=args.quick)
        runner.print_summary()
        sys.exit(0)
    except KeyboardInterrupt:
        print("\n\n⚠️  Benchmark interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ ERROR: Benchmark failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
