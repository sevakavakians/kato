# KATO Performance Benchmarks

This directory contains performance benchmarking tools for KATO pattern matching.

---

## Available Benchmarks

1. **test_service_scaling.py** - End-to-end prediction latency over the HTTP API, by corpus size. **Start here when judging a change to the prediction path.**
2. **bottleneck_runner.py** - In-process timing breakdown of the learn and predict paths
3. **baseline.py** - Baseline pattern-matching measurement (pre-optimization)
4. **compare_matchers.py** - Compare RapidFuzz vs difflib performance (Phase 2)

---

## Service Scaling (end to end)

`test_service_scaling.py` measures what a client actually waits for — uvicorn,
the session layer, the filter pipeline, matching, metrics and ranking — rather
than driving `PatternProcessor` in-process like the other benchmarks. It is the
harness that showed the per-request `ProcessPoolExecutor` cost 3378 ms where the
thread pool cost 1231 ms, for byte-identical output.

```bash
./start.sh                                    # the service must be running

python -m benchmarks.test_service_scaling                      # default tiers 500/2000/6000
python -m benchmarks.test_service_scaling --tiers 500,2000     # smaller/faster
python -m benchmarks.test_service_scaling --keep               # leave the corpus for the next run
python -m benchmarks.test_service_scaling --rebuild            # clear first

# Compare against a previous run — this is the point of the tool
python -m benchmarks.test_service_scaling \
    --baseline benchmarks/results/service_scaling_<id>.json
```

Each run writes `benchmarks/results/service_scaling_<timestamp>.json` and, by
default, clears the corpus it built. `--keep` makes a repeat run much faster,
since the loader only tops the corpus up to the requested tier.

### What it reports, and why those three numbers

| column | what it times |
|---|---|
| `scan` | the exact unfiltered `SELECT` that `FilterPipelineExecutor._get_all_patterns` issues, which is the default path because `filter_pipeline` defaults to `[]` |
| `meta/chunk` | one `patterns_metadata` lookup of `METADATA_CHUNK_SIZE` names — the prediction path issues one per chunk of matched patterns, so multiply, don't read it as a total |
| `predict` | `GET /sessions/{id}/predictions`, end to end, median of 12 samples after a warm-up |

Splitting them out settles where the time goes. Measured 2026-09-16 at 6000
patterns with everything matching: scan ~12 ms (1%), metadata ~430 ms across 12
chunks (35%), matching and metrics the remaining ~57%. **The full-corpus scan is
not the bottleneck**, which is the assumption this benchmark exists to keep
honest.

### Reference numbers

Committed baseline: `benchmarks/results/service_scaling_baseline.json` (KATO
5.1.2, local Docker stack). Hardware varies — compare a run against a run you
took yourself on the same machine, not against these absolutes.

### Why loading uses `process_predictions: false`

With predictions on (the default), every observe runs a full-corpus prediction,
so building a corpus is O(N²). At ~700 patterns that had collapsed to roughly 8
patterns/min across 8 concurrent writers; with predictions off it is ~950/min.
That is why the older `bottleneck_*` results in this directory stop at 100
patterns — larger tiers were impractical to build, not uninteresting.

---

## Baseline Benchmarks

Measures current pattern matching performance without optimizations.

### Running Benchmarks

```bash
# Ensure KATO services are running
./start.sh

# Run all benchmarks (includes 1M patterns - may take 5-10 minutes)
python benchmarks/baseline.py

# Run quick benchmarks (skip 1M patterns - faster)
python benchmarks/baseline.py --quick
```

### What Gets Measured

**Query Performance:**
- 1,000 patterns with 10-symbol query
- 10,000 patterns with 10-symbol query
- 100,000 patterns with 10-symbol query
- 1,000,000 patterns with 10-symbol query (skipped with --quick)

**Learning Performance:**
- Time to learn 1,000 new patterns
- Pattern insertion throughput

**Metrics:**
- Latency: min, max, mean, median, P95, P99, std dev
- Throughput: patterns/sec, queries/sec
- System info: CPU, memory, platform

### Results

Results are saved to `benchmarks/results/baseline_YYYYMMDD_HHMMSS.json` with:
- Timestamp and system information
- Detailed metrics for each test
- Generation and insertion timing

Example results structure:
```json
{
  "benchmark_id": "baseline_20251020_143022",
  "processor_id": "benchmark_baseline",
  "timestamp": "2025-10-20T14:30:22.123456",
  "system_info": {
    "platform": "Darwin-24.6.0-arm64-arm-64bit",
    "python_version": "3.13.7",
    "cpu_count": 8,
    "memory_gb": 16.0
  },
  "tests": [
    {
      "test_type": "query",
      "result": {
        "pattern_count": 1000,
        "query_length": 10,
        "iterations": 10,
        "latency_ms": {
          "mean": 123.45,
          "median": 120.00,
          "p95": 145.67,
          "p99": 150.23
        },
        "throughput": {
          "patterns_per_second": 8100,
          "queries_per_second": 8.1
        }
      }
    }
  ]
}
```

### Expected Baseline Performance

Current sequential Python implementation (before GPU optimization):

| Pattern Count | Query Latency | Notes |
|---------------|---------------|-------|
| 1K | ~100ms | Fast enough |
| 10K | ~1,000ms (1s) | Noticeable delay |
| 100K | ~10,000ms (10s) | Very slow |
| 1M | ~100,000ms (100s) | Unusable for real-time |

**Learning:** ~0.1ms per pattern (fast - no optimization needed)

### GPU Performance Targets

After GPU optimization (Phase 3):

| Pattern Count | Current | Target | Speedup |
|---------------|---------|--------|---------|
| 1K | 100ms | 5ms | 20x |
| 10K | 1,000ms | 20ms | 50x |
| 100K | 10,000ms | 50ms | 200x |
| 1M | 100,000ms | 100ms | 1000x |
| 10M | N/A | 100ms | N/A |

---

## CPU Optimization Comparison (Phase 2)

Compare RapidFuzz vs difflib performance.

### Running Comparisons

```bash
# Ensure services running
./start.sh

# Quick comparison (recommended - skip 1M patterns)
python benchmarks/compare_matchers.py --quick

# Full comparison (includes 1M patterns - may take 10+ minutes)
python benchmarks/compare_matchers.py

# Results saved to: benchmarks/results/comparison_YYYYMMDD_HHMMSS.json
```

### What Gets Measured

For each pattern count (1K, 10K, 100K, 1M):
- Run benchmark with RapidFuzz enabled
- Run benchmark with difflib (RapidFuzz disabled)
- Calculate speedup ratio
- Compare result consistency

### Expected Results

**CPU Optimization (RapidFuzz):**
```
Pattern Count | difflib | RapidFuzz | Speedup
1K            | 100ms   | 20ms      | 5.0x
10K           | 1,000ms | 150ms     | 6.7x
100K          | 10,000ms| 1,200ms   | 8.3x
1M            | 100,000ms|12,000ms  | 8.3x
```

**Speedup increases with pattern count** due to better batch optimization.

### Results Format

```json
{
  "comparisons": [
    {
      "pattern_count": 10000,
      "difflib": {
        "matcher": "difflib",
        "latency_ms": {"mean": 1234.56, "p95": 1456.78},
        "throughput": {"patterns_per_second": 8100}
      },
      "rapidfuzz": {
        "matcher": "RapidFuzz",
        "latency_ms": {"mean": 185.23, "p95": 201.45},
        "throughput": {"patterns_per_second": 54000}
      },
      "speedup": {
        "ratio": 6.67,
        "percentage": 566.7
      }
    }
  ]
}
```

---

## Comparing All Results

To compare baseline, CPU-optimized, and GPU performance:

```bash
# 1. Run baseline (pre-optimization)
python benchmarks/baseline.py --quick

# 2. Run CPU optimization comparison (Phase 2)
python benchmarks/compare_matchers.py --quick

# 3. After GPU implementation (Phase 3 - future)
python benchmarks/gpu_benchmarks.py --quick

# All results in benchmarks/results/ directory
```

## Troubleshooting

**ClickHouse connection errors:**
```bash
# Check services
docker ps | grep clickhouse

# Start services
./start.sh
```

**Out of memory:**
```bash
# Run quick benchmarks (skip 1M patterns)
python benchmarks/baseline.py --quick
```

**Slow performance:**
- Normal for large datasets (100K+ patterns)
- This establishes the baseline for measuring GPU improvements
- Use `--quick` flag for faster testing

## Development

### Adding New Benchmarks

1. Create new benchmark file: `benchmarks/my_benchmark.py`
2. Inherit from `BenchmarkRunner` or create custom class
3. Save results to `benchmarks/results/` with timestamps
4. Update this README

### Pattern Generation

Test patterns are randomly generated with:
- 2-5 events per pattern
- 5-20 symbols per event
- Vocabulary: 100 regular symbols + 50 vector symbols

Patterns are realistic representations of KATO data.

## Notes

- Benchmarks use isolated `benchmark_baseline` processor ID
- All test data is cleaned up after benchmarks
- No interference with production KATO data
- Results are deterministic (seeded random generation coming soon)

## See Also

- `docs/developers/gpu/IMPLEMENTATION_PLAN.md` - GPU optimization roadmap
- `docs/developers/gpu/PHASE1_GUIDE.md` - Phase 1 details
- `CLAUDE.md` - KATO project documentation
