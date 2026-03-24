"""
KATO Performance Bottleneck Runner

Orchestrates all benchmark suites and produces a unified JSON report
with per-operation timing, bottleneck ranking, and scaling analysis.

Usage:
    # Run full suite (100, 1K, 10K patterns)
    python -m benchmarks.bottleneck_runner

    # Run specific tiers
    python -m benchmarks.bottleneck_runner --tiers 100,1000

    # Run specific path only
    python -m benchmarks.bottleneck_runner --path database
    python -m benchmarks.bottleneck_runner --path learning
    python -m benchmarks.bottleneck_runner --path prediction

    # Run all paths
    python -m benchmarks.bottleneck_runner --path all

    # Quick mode (100 patterns only)
    python -m benchmarks.bottleneck_runner --quick
"""

import argparse
import json
import platform
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from benchmarks.profiler import (
    TimingCollector,
    compute_bottleneck_ranking,
    compute_scaling_analysis,
)


def get_system_info() -> dict:
    """Collect system information for the report."""
    info = {
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "cpu_count": platform.os.cpu_count(),
        "cpu_model": platform.processor(),
        "timestamp": datetime.now().isoformat(),
    }
    try:
        import psutil
        info["memory_gb"] = round(psutil.virtual_memory().total / 1e9, 2)
    except ImportError:
        info["memory_gb"] = "unknown (psutil not installed)"
    return info


def check_services() -> bool:
    """Verify KATO services are running."""
    print("Checking services...")
    errors = []

    # Check ClickHouse
    try:
        from kato.storage.connection_manager import OptimizedConnectionManager
        conn = OptimizedConnectionManager()
        ch = conn.clickhouse
        ch.query("SELECT 1")
        print("  ClickHouse: OK")
    except Exception as e:
        errors.append(f"  ClickHouse: FAILED ({e})")

    # Check Redis
    try:
        r = conn.redis
        r.ping()
        print("  Redis: OK")
    except Exception as e:
        errors.append(f"  Redis: FAILED ({e})")

    if errors:
        for err in errors:
            print(err)
        print("\nPlease start services with: ./start.sh")
        return False

    return True


def run_database_benchmarks() -> TimingCollector:
    """Run database isolation benchmarks."""
    from benchmarks.test_database_latency import run_all
    return run_all()


def run_learning_benchmarks(tiers: list[int]) -> TimingCollector:
    """Run learning path benchmarks."""
    from benchmarks.test_learning_path import run_all
    return run_all(tiers=tiers)


def run_prediction_benchmarks(tiers: list[int]) -> TimingCollector:
    """Run prediction path benchmarks."""
    from benchmarks.test_prediction_path import run_all
    return run_all(tiers=tiers)


def generate_report(collectors: dict[str, TimingCollector],
                    tiers: list[int],
                    system_info: dict) -> dict:
    """
    Generate unified JSON report from all collectors.

    Args:
        collectors: Dict mapping path_name -> TimingCollector
        tiers: Scale tiers used
        system_info: System information dict

    Returns:
        Report dictionary ready for JSON serialization
    """
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    report = {
        "benchmark_id": f"bottleneck_{timestamp}",
        "timestamp": datetime.now().isoformat(),
        "system_info": system_info,
        "tiers": tiers,
        "results": {},
        "summary": {},
    }

    # Merge all collector stats
    all_stats = {}
    for path_name, collector in collectors.items():
        stats = collector.get_all_stats()
        report["results"][path_name] = stats
        all_stats.update(stats)

    # Bottleneck ranking for learning path
    if 'learn.total' in all_stats:
        report["summary"]["learning_bottlenecks"] = compute_bottleneck_ranking(
            all_stats, 'learn.total'
        )[:10]

    # Bottleneck ranking for fast prediction path
    if 'predict.fast.total' in all_stats:
        report["summary"]["prediction_fast_bottlenecks"] = compute_bottleneck_ranking(
            all_stats, 'predict.fast.total'
        )[:10]

    # Bottleneck ranking for full prediction path
    if 'predict.full.total' in all_stats:
        report["summary"]["prediction_full_bottlenecks"] = compute_bottleneck_ranking(
            all_stats, 'predict.full.total'
        )[:10]

    # I/O vs computation breakdown
    io_labels = [l for l in all_stats if '.ch.' in l or '.redis.' in l or '.clickhouse.' in l]
    compute_labels = [l for l in all_stats if '.minhash' in l or '.rapidfuzz' in l or '.pattern_init' in l or '.lcs' in l]

    io_total = sum(all_stats[l].get('sum', 0) for l in io_labels if all_stats[l].get('samples', 0) > 0)
    compute_total = sum(all_stats[l].get('sum', 0) for l in compute_labels if all_stats[l].get('samples', 0) > 0)

    report["summary"]["io_vs_compute"] = {
        "io_total_ms": round(io_total, 2),
        "compute_total_ms": round(compute_total, 2),
        "io_labels": io_labels,
        "compute_labels": compute_labels,
    }

    return report


def print_bottleneck_summary(report: dict) -> None:
    """Print a concise bottleneck summary to console."""
    print(f"\n{'=' * 70}")
    print(f"  BOTTLENECK SUMMARY")
    print(f"{'=' * 70}")

    for section, title in [
        ("learning_bottlenecks", "Learning Path (top 5)"),
        ("prediction_fast_bottlenecks", "Prediction Fast Path (top 5)"),
        ("prediction_full_bottlenecks", "Prediction Full Path (top 5)"),
    ]:
        bottlenecks = report.get("summary", {}).get(section, [])
        if bottlenecks:
            print(f"\n  {title}:")
            print(f"  {'Operation':<40} {'Mean':>10} {'% of Total':>12}")
            print(f"  {'-' * 40} {'-' * 10} {'-' * 12}")
            for b in bottlenecks[:5]:
                print(f"  {b['operation']:<40} {b['mean_ms']:>8.2f}ms {b['pct_of_total']:>10.1f}%")

    io_compute = report.get("summary", {}).get("io_vs_compute", {})
    if io_compute:
        io = io_compute.get("io_total_ms", 0)
        comp = io_compute.get("compute_total_ms", 0)
        total = io + comp
        if total > 0:
            print(f"\n  I/O vs Computation:")
            print(f"    Database I/O: {io:>10.0f}ms ({io/total*100:.1f}%)")
            print(f"    Computation:  {comp:>10.0f}ms ({comp/total*100:.1f}%)")

    print(f"\n{'=' * 70}")


def main():
    parser = argparse.ArgumentParser(description="KATO Performance Bottleneck Runner")
    parser.add_argument(
        "--tiers", type=str, default="100,1000,10000",
        help="Comma-separated scale tiers (default: 100,1000,10000)"
    )
    parser.add_argument(
        "--path", type=str, default="all",
        choices=["all", "database", "learning", "prediction"],
        help="Which benchmark path to run (default: all)"
    )
    parser.add_argument(
        "--quick", action="store_true",
        help="Quick mode: only 100 patterns"
    )
    parser.add_argument(
        "--output-dir", type=str, default="benchmarks/results",
        help="Output directory for JSON report"
    )
    args = parser.parse_args()

    # Parse tiers
    if args.quick:
        tiers = [100]
    else:
        tiers = [int(t.strip()) for t in args.tiers.split(",")]

    print("=" * 70)
    print("  KATO Performance Bottleneck Profiling")
    print(f"  Tiers: {tiers}")
    print(f"  Path: {args.path}")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    # Check services
    if not check_services():
        sys.exit(1)

    system_info = get_system_info()
    collectors = {}
    overall_start = time.perf_counter()

    try:
        # Run benchmarks
        if args.path in ("all", "database"):
            print("\n" + "=" * 70)
            print("  Phase 1: Database Latency Benchmarks")
            print("=" * 70)
            collectors["database"] = run_database_benchmarks()

        if args.path in ("all", "learning"):
            print("\n" + "=" * 70)
            print("  Phase 2: Learning Path Benchmarks")
            print("=" * 70)
            collectors["learning"] = run_learning_benchmarks(tiers)

        if args.path in ("all", "prediction"):
            print("\n" + "=" * 70)
            print("  Phase 3: Prediction Path Benchmarks")
            print("=" * 70)
            collectors["prediction"] = run_prediction_benchmarks(tiers)

    except KeyboardInterrupt:
        print("\n\nBenchmark interrupted by user.")
    except Exception as e:
        print(f"\nBenchmark failed: {e}")
        import traceback
        traceback.print_exc()

    total_ms = (time.perf_counter() - overall_start) * 1000

    # Generate report
    report = generate_report(collectors, tiers, system_info)
    report["total_benchmark_time_ms"] = round(total_ms, 0)

    # Save JSON report
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_file = output_dir / f"bottleneck_{timestamp}.json"

    with open(output_file, 'w') as f:
        json.dump(report, f, indent=2, default=str)

    print(f"\nReport saved to: {output_file}")

    # Print summary
    print_bottleneck_summary(report)

    print(f"\nTotal benchmark time: {total_ms/1000:.1f}s")
    print(f"Finished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    main()
