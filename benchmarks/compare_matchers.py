#!/usr/bin/env python3
"""
Compare RapidFuzz vs difflib matcher performance.

Measures performance difference between fast matching (RapidFuzz) and
original matching (difflib) for pattern matching operations.

Usage:
    # Run comparison benchmarks
    python benchmarks/compare_matchers.py

    # Quick comparison (skip large datasets)
    python benchmarks/compare_matchers.py --quick

Results saved to: benchmarks/results/comparison_YYYYMMDD_HHMMSS.json
"""

import argparse
import json
import os
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


class MatcherComparison:
    """Compare performance of different matching implementations."""

    def __init__(self, processor_id: str = "benchmark_compare"):
        """
        Initialize benchmark comparison.

        Args:
            processor_id: Unique identifier for database isolation
        """
        self.processor_id = processor_id
        self.results = {
            "benchmark_id": f"comparison_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "processor_id": processor_id,
            "timestamp": datetime.now().isoformat(),
            "system_info": self._get_system_info(),
            "comparisons": []
        }

    def _get_system_info(self) -> Dict[str, Any]:
        """Collect system information."""
        import platform
        import psutil

        # Check RapidFuzz availability
        try:
            import rapidfuzz
            rapidfuzz_version = rapidfuzz.__version__
            rapidfuzz_available = True
        except ImportError:
            rapidfuzz_version = None
            rapidfuzz_available = False

        return {
            "platform": platform.platform(),
            "python_version": platform.python_version(),
            "cpu_count": psutil.cpu_count(),
            "cpu_count_physical": psutil.cpu_count(logical=False),
            "memory_gb": round(psutil.virtual_memory().total / 1e9, 2),
            "cpu_model": platform.processor(),
            "rapidfuzz_available": rapidfuzz_available,
            "rapidfuzz_version": rapidfuzz_version
        }

    def generate_test_patterns(
        self,
        count: int,
        min_events: int = 2,
        max_events: int = 5,
        min_symbols_per_event: int = 5,
        max_symbols_per_event: int = 20
    ) -> List[Pattern]:
        """Generate random test patterns (same as baseline.py)."""
        patterns = []
        vocab = [f"sym{i}" for i in range(100)]
        vocab += [f"VCTR|{i:04x}" for i in range(50)]

        for i in range(count):
            num_events = np.random.randint(min_events, max_events + 1)
            events = []
            for _ in range(num_events):
                event_length = np.random.randint(min_symbols_per_event, max_symbols_per_event + 1)
                event = sorted(list(np.random.choice(vocab, event_length, replace=False)))
                events.append(event)

            pattern = Pattern(events)
            patterns.append(pattern)

        return patterns

    def setup_patterns(self, pattern_count: int) -> tuple:
        """
        Set up MongoDB with test patterns.

        Args:
            pattern_count: Number of patterns to create

        Returns:
            Tuple of (mongo_client, kb, patterns, query_state)
        """
        print(f"Generating {pattern_count:,} test patterns...")
        patterns = self.generate_test_patterns(pattern_count)

        # Store in MongoDB
        print("Storing patterns in MongoDB...")
        mongo_client = MongoClient("mongodb://localhost:27017")
        kb = mongo_client[self.processor_id]

        # Clear existing
        kb.patterns_kb.delete_many({})
        kb.symbols_kb.delete_many({})
        kb.metadata.delete_many({})

        # Insert patterns
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

        # Generate query
        vocab = [f"sym{i}" for i in range(100)]
        query_state = sorted(list(np.random.choice(vocab, 10, replace=False)))

        return mongo_client, kb, patterns, query_state

    def benchmark_matcher(
        self,
        pattern_count: int,
        use_fast_matching: bool,
        iterations: int = 10
    ) -> Dict[str, Any]:
        """
        Benchmark a specific matcher implementation.

        Args:
            pattern_count: Number of patterns to match against
            use_fast_matching: If True, use RapidFuzz; if False, use difflib
            iterations: Number of iterations to run

        Returns:
            Benchmark results dict
        """
        matcher_name = "RapidFuzz" if use_fast_matching else "difflib"
        print(f"\n{'='*60}")
        print(f"Benchmarking: {matcher_name} with {pattern_count:,} patterns")
        print(f"{'='*60}")

        # Setup patterns
        mongo_client, kb, patterns, query_state = self.setup_patterns(pattern_count)

        # Set environment variable to control matcher
        original_env = os.environ.get('KATO_USE_FAST_MATCHING')
        os.environ['KATO_USE_FAST_MATCHING'] = str(use_fast_matching).lower()

        try:
            # Create searcher
            print(f"Initializing PatternSearcher with fast_matching={use_fast_matching}...")
            searcher = PatternSearcher(
                kb_id=self.processor_id,
                max_predictions=100,
                recall_threshold=0.1
            )

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
            result_counts = []

            for i in range(iterations):
                start = time.perf_counter()
                results = searcher.causalBelief(query_state, stm_events=None)
                latency = (time.perf_counter() - start) * 1000  # Convert to ms
                latencies.append(latency)
                result_counts.append(len(results))

                print(f"  Iteration {i+1}/{iterations}: {latency:.2f}ms ({len(results)} matches)")

            # Calculate statistics
            latencies_np = np.array(latencies)
            result = {
                "matcher": matcher_name,
                "pattern_count": pattern_count,
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
                "results": {
                    "mean_count": float(np.mean(result_counts)),
                    "consistent": len(set(result_counts)) == 1  # All iterations same count
                }
            }

            print(f"\n{'─'*60}")
            print(f"Results ({matcher_name}):")
            print(f"  Mean latency:   {result['latency_ms']['mean']:.2f}ms")
            print(f"  Median latency: {result['latency_ms']['median']:.2f}ms")
            print(f"  P95 latency:    {result['latency_ms']['p95']:.2f}ms")
            print(f"  Throughput:     {result['throughput']['patterns_per_second']:.0f} patterns/sec")
            print(f"  Result count:   {result['results']['mean_count']:.0f} (consistent: {result['results']['consistent']})")
            print(f"{'─'*60}")

            return result

        finally:
            # Cleanup
            kb.patterns_kb.delete_many({})
            mongo_client.close()

            # Restore original environment
            if original_env is not None:
                os.environ['KATO_USE_FAST_MATCHING'] = original_env
            elif 'KATO_USE_FAST_MATCHING' in os.environ:
                del os.environ['KATO_USE_FAST_MATCHING']

    def compare_matchers(
        self,
        pattern_count: int,
        iterations: int = 10
    ) -> Dict[str, Any]:
        """
        Compare RapidFuzz vs difflib for same pattern count.

        Args:
            pattern_count: Number of patterns to test
            iterations: Number of iterations per matcher

        Returns:
            Comparison results dict
        """
        print(f"\n{'='*60}")
        print(f"COMPARISON: {pattern_count:,} patterns")
        print(f"{'='*60}")

        # Benchmark difflib
        difflib_result = self.benchmark_matcher(pattern_count, use_fast_matching=False, iterations=iterations)

        # Benchmark RapidFuzz
        rapidfuzz_result = self.benchmark_matcher(pattern_count, use_fast_matching=True, iterations=iterations)

        # Calculate speedup
        speedup = difflib_result['latency_ms']['mean'] / rapidfuzz_result['latency_ms']['mean']

        comparison = {
            "pattern_count": pattern_count,
            "difflib": difflib_result,
            "rapidfuzz": rapidfuzz_result,
            "speedup": {
                "ratio": float(speedup),
                "percentage": float((speedup - 1) * 100)
            }
        }

        # Print comparison summary
        print(f"\n{'='*60}")
        print(f"COMPARISON SUMMARY ({pattern_count:,} patterns)")
        print(f"{'='*60}")
        print(f"difflib mean:     {difflib_result['latency_ms']['mean']:>10.2f}ms")
        print(f"RapidFuzz mean:   {rapidfuzz_result['latency_ms']['mean']:>10.2f}ms")
        print(f"Speedup:          {speedup:>10.2f}x")
        print(f"Improvement:      {(speedup - 1) * 100:>10.1f}%")
        print(f"{'='*60}\n")

        return comparison

    def run_all_comparisons(self, quick: bool = False):
        """
        Run complete comparison suite.

        Args:
            quick: If True, skip 1M pattern comparison
        """
        print("="*60)
        print("KATO Matcher Performance Comparison")
        print("RapidFuzz vs difflib")
        print("="*60)
        print(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Processor ID: {self.processor_id}")
        print("")

        # Check RapidFuzz availability
        if not self.results["system_info"]["rapidfuzz_available"]:
            print("⚠️  WARNING: RapidFuzz not installed!")
            print("   Install with: pip install rapidfuzz>=3.0.0")
            print("   Comparison will show fallback behavior.\n")

        # Comparison configurations
        test_configs = [
            (1_000, 10),     # 1K patterns, 10 iterations
            (10_000, 10),    # 10K patterns, 10 iterations
            (100_000, 5),    # 100K patterns, 5 iterations
        ]

        if not quick:
            test_configs.append((1_000_000, 3))  # 1M patterns, 3 iterations

        for pattern_count, iterations in test_configs:
            try:
                comparison = self.compare_matchers(pattern_count, iterations=iterations)
                self.results["comparisons"].append(comparison)
            except Exception as e:
                print(f"\n❌ ERROR in comparison ({pattern_count:,} patterns): {e}")
                self.results["comparisons"].append({
                    "pattern_count": pattern_count,
                    "error": str(e)
                })

        # Save results
        output_dir = Path("benchmarks/results")
        output_dir.mkdir(parents=True, exist_ok=True)

        output_file = output_dir / f"comparison_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(output_file, 'w') as f:
            json.dump(self.results, f, indent=2)

        print(f"\n{'='*60}")
        print(f"✅ Comparisons complete!")
        print(f"Results saved to: {output_file}")
        print(f"End time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}")

        return self.results

    def print_summary(self):
        """Print summary of comparison results."""
        print("\n" + "="*60)
        print("COMPARISON SUMMARY")
        print("="*60)

        for comp in self.results["comparisons"]:
            if "error" in comp:
                print(f"\n❌ {comp['pattern_count']:,} patterns - ERROR")
                print(f"   {comp.get('error', 'Unknown error')}")
                continue

            print(f"\n{comp['pattern_count']:,} patterns:")
            print(f"  difflib:      {comp['difflib']['latency_ms']['mean']:>8.2f}ms")
            print(f"  RapidFuzz:    {comp['rapidfuzz']['latency_ms']['mean']:>8.2f}ms")
            print(f"  Speedup:      {comp['speedup']['ratio']:>8.2f}x ({comp['speedup']['percentage']:>6.1f}%)")

        print("\n" + "="*60)


def main():
    """Run matcher comparison suite."""
    parser = argparse.ArgumentParser(description="Compare KATO matcher implementations")
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Skip 1M pattern comparison for faster testing"
    )
    parser.add_argument(
        "--processor-id",
        default="benchmark_compare",
        help="Processor ID for database isolation (default: benchmark_compare)"
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

    # Run comparisons
    comparator = MatcherComparison(processor_id=args.processor_id)

    try:
        results = comparator.run_all_comparisons(quick=args.quick)
        comparator.print_summary()
        sys.exit(0)
    except KeyboardInterrupt:
        print("\n\n⚠️  Comparison interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ ERROR: Comparison failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
