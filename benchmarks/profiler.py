"""
Non-invasive performance profiling infrastructure for KATO benchmarks.

Provides timing utilities that wrap existing methods via monkey-patching
at benchmark runtime — zero changes to production code under kato/.

Usage:
    from benchmarks.profiler import TimingCollector, instrument_class

    collector = TimingCollector()
    uninstrument = instrument_class(ClickHouseWriter, {
        '_prepare_row': 'learn.ch.prepare_row',
        'flush': 'learn.ch.flush',
    }, collector)

    # ... run benchmarks ...

    collector.print_summary()
    uninstrument()
"""

import asyncio
import functools
import statistics
import time
from collections import defaultdict
from contextlib import contextmanager
from typing import Any, Callable, Optional


class TimingCollector:
    """Accumulates raw timing samples keyed by label, computes stats on demand."""

    def __init__(self):
        self.samples: dict[str, list[float]] = defaultdict(list)

    def record(self, label: str, elapsed_ms: float) -> None:
        """Record a timing sample in milliseconds."""
        self.samples[label].append(elapsed_ms)

    def clear(self) -> None:
        """Clear all collected samples."""
        self.samples.clear()

    def get_stats(self, label: str) -> dict[str, Any]:
        """Compute statistics for a given label."""
        data = self.samples.get(label, [])
        if not data:
            return {"samples": 0}

        sorted_data = sorted(data)
        n = len(sorted_data)

        return {
            "samples": n,
            "mean": statistics.mean(data),
            "median": statistics.median(data),
            "min": min(data),
            "max": max(data),
            "p95": sorted_data[int(n * 0.95)] if n >= 20 else sorted_data[-1],
            "p99": sorted_data[int(n * 0.99)] if n >= 100 else sorted_data[-1],
            "stddev": statistics.stdev(data) if n > 1 else 0.0,
            "sum": sum(data),
            "unit": "ms",
        }

    def get_all_stats(self) -> dict[str, dict[str, Any]]:
        """Compute statistics for all labels."""
        return {label: self.get_stats(label) for label in sorted(self.samples.keys())}

    def print_summary(self, title: str = "Timing Summary") -> None:
        """Print a human-readable summary table."""
        all_stats = self.get_all_stats()
        if not all_stats:
            print(f"\n{title}: No timing data collected.")
            return

        print(f"\n{'=' * 90}")
        print(f"  {title}")
        print(f"{'=' * 90}")
        print(f"  {'Label':<40} {'Mean':>8} {'Median':>8} {'P95':>8} {'P99':>8} {'Samples':>8}")
        print(f"  {'-' * 40} {'-' * 8} {'-' * 8} {'-' * 8} {'-' * 8} {'-' * 8}")

        for label, stats in all_stats.items():
            if stats["samples"] == 0:
                continue
            print(
                f"  {label:<40} "
                f"{stats['mean']:>7.2f}ms "
                f"{stats['median']:>7.2f}ms "
                f"{stats['p95']:>7.2f}ms "
                f"{stats['p99']:>7.2f}ms "
                f"{stats['samples']:>8d}"
            )

        print(f"{'=' * 90}")

    def to_dict(self) -> dict[str, dict[str, Any]]:
        """Export all stats as a serializable dictionary."""
        return self.get_all_stats()


@contextmanager
def perf_timer(label: str, collector: TimingCollector):
    """Context manager that records elapsed time to a collector.

    Usage:
        with perf_timer('learn.ch.flush', collector):
            writer.flush()
    """
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed_ms = (time.perf_counter() - start) * 1000
        collector.record(label, elapsed_ms)


def timed_method(label: str, collector: TimingCollector) -> Callable:
    """Decorator factory that wraps a sync method with timing instrumentation.

    Args:
        label: Hierarchical timing label (e.g., 'learn.ch.prepare_row')
        collector: TimingCollector to record samples to
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                return func(*args, **kwargs)
            finally:
                elapsed_ms = (time.perf_counter() - start) * 1000
                collector.record(label, elapsed_ms)
        return wrapper
    return decorator


def timed_async_method(label: str, collector: TimingCollector) -> Callable:
    """Decorator factory that wraps an async method with timing instrumentation.

    Args:
        label: Hierarchical timing label
        collector: TimingCollector to record samples to
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                return await func(*args, **kwargs)
            finally:
                elapsed_ms = (time.perf_counter() - start) * 1000
                collector.record(label, elapsed_ms)
        return wrapper
    return decorator


def instrument_class(cls, method_map: dict[str, str],
                     collector: TimingCollector,
                     async_methods: Optional[set[str]] = None) -> Callable:
    """Monkey-patch class methods with timing instrumentation.

    Applied at benchmark runtime only — no changes to source files.

    Args:
        cls: The class to instrument
        method_map: Dict mapping method_name -> timing_label
        collector: TimingCollector to record to
        async_methods: Set of method names that are async (use timed_async_method)

    Returns:
        uninstrument() callable that restores original methods
    """
    async_methods = async_methods or set()
    originals = {}

    for method_name, label in method_map.items():
        original = getattr(cls, method_name)
        originals[method_name] = original

        if method_name in async_methods:
            wrapped = timed_async_method(label, collector)(original)
        else:
            wrapped = timed_method(label, collector)(original)

        setattr(cls, method_name, wrapped)

    def uninstrument():
        for method_name, original in originals.items():
            setattr(cls, method_name, original)

    return uninstrument


def instrument_instance(instance, method_map: dict[str, str],
                        collector: TimingCollector,
                        async_methods: Optional[set[str]] = None) -> Callable:
    """Monkey-patch instance methods with timing instrumentation.

    Like instrument_class but patches a specific instance, not the class.

    Args:
        instance: The object instance to instrument
        method_map: Dict mapping method_name -> timing_label
        collector: TimingCollector to record to
        async_methods: Set of method names that are async

    Returns:
        uninstrument() callable that restores original methods
    """
    async_methods = async_methods or set()
    originals = {}

    for method_name, label in method_map.items():
        original = getattr(instance, method_name)
        originals[method_name] = original

        if method_name in async_methods:
            wrapped = timed_async_method(label, collector)(original)
        else:
            wrapped = timed_method(label, collector)(original)

        setattr(instance, method_name, wrapped)

    def uninstrument():
        for method_name, original in originals.items():
            setattr(instance, method_name, original)

    return uninstrument


def compute_bottleneck_ranking(stats: dict[str, dict], total_label: str) -> list[dict]:
    """Rank operations by percentage of total time.

    Args:
        stats: Output of TimingCollector.get_all_stats()
        total_label: The label representing total end-to-end time

    Returns:
        List of dicts sorted by pct_of_total descending
    """
    total_mean = stats.get(total_label, {}).get("mean", 0)
    if total_mean == 0:
        return []

    ranking = []
    for label, stat in stats.items():
        if label == total_label or stat.get("samples", 0) == 0:
            continue
        pct = (stat["mean"] / total_mean) * 100
        ranking.append({
            "operation": label,
            "mean_ms": round(stat["mean"], 3),
            "pct_of_total": round(pct, 1),
            "samples": stat["samples"],
        })

    ranking.sort(key=lambda x: x["pct_of_total"], reverse=True)
    return ranking


def compute_scaling_analysis(tier_stats: dict[int, dict[str, dict]]) -> dict[str, dict]:
    """Analyze how each operation scales across dataset tiers.

    Args:
        tier_stats: Dict mapping tier_size -> label_stats (from TimingCollector.get_all_stats())

    Returns:
        Dict mapping label -> {tier_size: mean_ms, ..., scaling_hint: str}
    """
    tiers = sorted(tier_stats.keys())
    if len(tiers) < 2:
        return {}

    all_labels = set()
    for stats in tier_stats.values():
        all_labels.update(stats.keys())

    analysis = {}
    for label in sorted(all_labels):
        tier_means = {}
        for tier in tiers:
            stat = tier_stats[tier].get(label, {})
            if stat.get("samples", 0) > 0:
                tier_means[tier] = round(stat["mean"], 3)

        if len(tier_means) < 2:
            continue

        # Simple scaling hint based on growth ratio
        sizes = sorted(tier_means.keys())
        first_val = tier_means[sizes[0]]
        last_val = tier_means[sizes[-1]]
        size_ratio = sizes[-1] / sizes[0]

        if first_val > 0:
            time_ratio = last_val / first_val
            if time_ratio < 1.5:
                hint = "O(1)"
            elif time_ratio < size_ratio * 0.3:
                hint = "O(log n)"
            elif time_ratio < size_ratio * 1.5:
                hint = "O(n)"
            else:
                hint = "O(n^2) or worse"
        else:
            hint = "unknown"

        analysis[label] = {**tier_means, "scaling_hint": hint}

    return analysis
