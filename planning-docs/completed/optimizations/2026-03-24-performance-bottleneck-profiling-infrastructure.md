# Performance Bottleneck Profiling Infrastructure - COMPLETE

**Completion Date**: 2026-03-24
**Branch**: `perf/bottleneck-profiling`
**Status**: Implementation complete, ready for test execution (no commit yet)
**Category**: Optimization - Profiling Infrastructure
**Time Taken**: Not yet measured (implementation session)

---

## Summary

Created a complete, zero-invasive profiling infrastructure under `benchmarks/` for identifying
performance bottlenecks in the KATO learning and prediction paths. The implementation uses
monkey-patching so zero changes to `kato/` source code are required.

---

## Files Created

### 1. `benchmarks/profiler.py`
Core instrumentation primitives:
- `TimingCollector` — thread-safe dict-of-lists for accumulating per-operation timing samples
- `PerfTimer` — context manager using `time.perf_counter()` for nanosecond precision
- `instrument_class()` — monkey-patches every public method on a class with timing wrappers
- `instrument_instance()` — patches a specific live instance (useful for processor instances)

### 2. `benchmarks/data_generator.py`
Realistic synthetic workload generation:
- Zipf-distributed vocabulary for realistic symbol frequency skew
- Four scale tiers: 100 / 1K / 10K / 100K patterns
- Each tier gets a unique `processor_id` for full ClickHouse + Redis isolation
- Configurable sequence lengths and observation depth

### 3. `benchmarks/test_database_latency.py`
Baseline latency characterization:
- Raw ClickHouse read/write round-trip timing
- Raw Redis read/write round-trip timing
- Pure computation baselines (MinHash, SHA1, LCS)
- Establishes I/O floor before higher-level benchmarks run

### 4. `benchmarks/test_learning_path.py`
Instrumented `observe → learn` path:
- Wraps `KatoProcessor.observe()` and `KatoProcessor.learn()` with per-operation timing
- Breaks down time into: observation_processing, stm_update, pattern_hashing,
  clickhouse_write, redis_metadata_write, minhash_computation
- Runs at each of the four scale tiers to reveal scaling behavior

### 5. `benchmarks/test_prediction_path.py`
Instrumented prediction path — two sub-paths:
- **Single-symbol fast path**: `_predict_single_symbol_fast()` breakdown
- **Multi-symbol filter pipeline**: per-stage timing for length filter → Jaccard →
  RapidFuzz → MinHash/LSH → similarity computation
- Reports I/O time vs. CPU time ratio per stage

### 6. `benchmarks/bottleneck_runner.py`
Main orchestrator:
- Runs all benchmark modules in sequence
- Aggregates results into structured JSON report
- Ranks operations by total wall-clock contribution (bottleneck ranking)
- Includes scaling analysis: reports how time grows from 100 → 100K patterns
- Outputs `benchmarks/results/bottleneck_report_YYYYMMDD_HHMMSS.json`

---

## Key Design Decisions

### Zero Source-Code Intrusion
Instrumentation uses monkey-patching exclusively. No `kato/` files are modified.
This means the benchmarks measure production code behavior exactly as deployed,
and the profiling infrastructure can be removed without any cleanup.

### Precision Timing
All measurements use `time.perf_counter()` (monotonic, sub-microsecond resolution)
rather than `time.time()` to avoid wall-clock skew from NTP adjustments.

### Database Isolation Per Tier
Each scale tier uses a unique `processor_id` (format: `bench_{tier}_{uuid}`),
ensuring ClickHouse partition pruning and Redis key namespacing are exercised
correctly and tiers do not bleed into each other.

### I/O vs. Computation Breakdown
Every benchmark separates I/O wait time from CPU-bound computation time.
This distinction drives actionable optimization choices:
- I/O-bound hotspots → batching, pipelining, caching
- CPU-bound hotspots → algorithmic improvement, parallelism, native extensions

### Scaling Analysis
Results include a scaling coefficient for each operation (time at 100K / time at 100).
Linear scaling (100x) is expected; super-linear scaling (>100x) flags algorithmic issues;
sub-linear scaling (<100x) confirms caching or batch-write effectiveness.

---

## Next Steps

1. **Commit the implementation** on branch `perf/bottleneck-profiling`
2. **Execute benchmarks** against running services: `python benchmarks/bottleneck_runner.py`
3. **Analyze JSON report** — identify top-3 bottlenecks by wall-clock contribution
4. **File targeted optimization tasks** based on findings (add to SPRINT_BACKLOG or SESSION_STATE)
5. **Establish baseline** so future optimizations can be measured against it

---

## Related Work

- `planning-docs/completed/optimizations/2026-03-19-performance-optimization-phase-5-optimizations.md`
- `planning-docs/completed/optimizations/2026-03-19-redis-batch-logging-rapidfuzz-optimizations.md`
- `docs/reference/filter-pipeline-guide.md` — filter pipeline stages being profiled
