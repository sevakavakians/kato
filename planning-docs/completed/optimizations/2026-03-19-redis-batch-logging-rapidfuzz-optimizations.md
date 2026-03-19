# Performance Optimization: Redis Batching, Logging, RapidFuzz, and Import Cleanup

**Completed**: 2026-03-19
**Type**: Optimization (multi-phase performance improvement)
**Impact**: Significant reduction in Redis round-trips on hot paths; lower CPU overhead per learn/predict cycle

---

## Summary

A multi-phase performance optimization pass across the core processing pipeline. The work targeted four independent bottleneck categories: Redis network round-trips (Phases 1A-1C), log-level noise (Phase 2A), redundant Python object construction (Phases 2B-2C), fuzzy-match algorithmic complexity (Phase 3A), and module-load overhead (Phase 4A).

---

## Phase 1A: Redis Batch Methods (redis_writer.py)

**Problem**: Pattern metadata loading and symbol-stat updates issued individual Redis commands in loops — N patterns required 3N sequential GET round-trips; a 50-symbol pattern triggered 150+ individual Redis calls.

**Solution**:
- Added `get_metadata_batch()` — pre-loads metadata for multiple patterns using a single Redis pipeline, collapsing 3N GETs into 1 pipeline call.
- Added `batch_update_symbol_stats()` — consolidates all per-symbol Redis writes (frequency increments, PMF increments, SADD mappings, global counters) from `learnPattern()` into a single pipeline.
- Updated `get_global_metadata()` — replaced 3 sequential GETs with a single `mget()` call.

**Files Modified**: `kato/storage/redis_writer.py`

---

## Phase 1B: Batched Redis in learnPattern() (knowledge_base.py)

**Problem**: Both the new-pattern and re-learned-pattern paths in `learnPattern()` looped over symbols and fired individual Redis commands per symbol.

**Solution**: Both code paths now call `batch_update_symbol_stats()`, reducing the Redis call count from O(symbols) to O(1) pipeline per learn operation. A 50-symbol pattern drops from 150+ Redis calls to 1.

**Files Modified**: `kato/storage/knowledge_base.py`

---

## Phase 1C: Batch Metadata Loading in Prediction Path

**Problem**: Prediction generation loaded pattern metadata one-at-a-time during candidate evaluation.

**Solution**:
- `_build_predictions_batch()` in `pattern_search.py` now pre-loads all candidate pattern metadata in a single batch call before iterating.
- `_predict_single_symbol_fast()` in `pattern_processor.py` pre-loads metadata for all candidate patterns in a single batch call before scoring.

**Files Modified**: `kato/searches/pattern_search.py`, `kato/workers/pattern_processor.py`

---

## Phase 2A: Logging Level Optimization (knowledge_base.py)

**Problem**: `learnPattern()` issued 10+ `logger.info()` calls per invocation — in high-frequency training these flushed to log sinks on every pattern, adding measurable overhead.

**Solution**: Downgraded 10+ mid-function `logger.info()` calls to `logger.debug()`. Entry-point and final-success messages remain at INFO to preserve operational visibility.

**Files Modified**: `kato/storage/knowledge_base.py`

---

## Phase 2B: Cached Property (pattern.py)

**Problem**: `flat_data` was recomputed on every access inside the `learn()` method's hot loop.

**Solution**: Applied `@functools.cached_property` to `flat_data` in the `Pattern` class. Updated `pattern_processor.py` `learn()` method to use the cached property.

**Files Modified**: `kato/models/pattern.py`, `kato/workers/pattern_processor.py`

---

## Phase 2C: Removed Duplicate Imports (knowledge_base.py)

**Problem**: `learnPattern()` contained duplicate `from itertools import chain` and `from collections import Counter` import statements inside the function body, evaluated on every call.

**Solution**: Removed the redundant in-function imports. Module-level imports already covered these.

**Files Modified**: `kato/storage/knowledge_base.py`

---

## Phase 3A: RapidFuzz Batch API (pattern_search.py)

**Problem**: Fuzzy string matching used a manual O(n×m) nested loop over state tokens and candidates.

**Solution**: Replaced with `process.extractOne()` per state token from the RapidFuzz batch API, which internally uses optimized C extensions. A manual fallback loop is retained for environments where RapidFuzz is unavailable.

**Files Modified**: `kato/searches/pattern_search.py`

---

## Phase 4A: Module-Level Imports (clickhouse_writer.py)

**Problem**: `from datasketch import MinHash` and `from datetime import datetime` were imported inside functions, re-executing the import machinery on every call.

**Solution**: Moved both imports to module level.

**Files Modified**: `kato/storage/clickhouse_writer.py`

---

## Test Results

- **445 passed**, 2 failed (pre-existing performance/stress test issues unrelated to this work), 2 skipped
- Zero correctness regressions introduced

---

## Files Modified

| File | Change |
|------|--------|
| `kato/storage/redis_writer.py` | Added `get_metadata_batch()`, `batch_update_symbol_stats()`, updated `get_global_metadata()` |
| `kato/storage/knowledge_base.py` | Batched Redis calls in `learnPattern()`, downgraded log levels, removed duplicate imports |
| `kato/searches/pattern_search.py` | `_build_predictions_batch()` batch metadata load, RapidFuzz batch API |
| `kato/workers/pattern_processor.py` | `_predict_single_symbol_fast()` batch metadata load, cached property usage |
| `kato/models/pattern.py` | `@functools.cached_property` on `flat_data` |
| `kato/storage/clickhouse_writer.py` | Moved `MinHash` and `datetime` imports to module level |
