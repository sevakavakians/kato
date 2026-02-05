# KATO Performance Bottleneck Investigation

## Executive Summary

This investigation analyzed KATO's learning process during active training to identify performance bottlenecks. The analysis covered three critical areas: service request processing, storage layer operations, and pattern matching algorithms.

**Key Finding**: KATO has several significant bottlenecks that impact training throughput, particularly related to lock contention, filter pipeline configuration, and matching algorithm selection.

---

## Critical Bottlenecks Identified

### 1. Processing Lock Serialization (CRITICAL)
**Location**: `kato/workers/observation_processor.py:346`

**Issue**: A `multiprocessing.Lock` serializes ALL observations per processor instance:
```python
self.processing_lock = Lock()  # Serializes all observations

with self.processing_lock:
    # Observation processing happens here
```

**Impact**:
- Concurrent training sessions on same processor must wait
- Lock contention increases with concurrent sessions
- Despite "stateless" processor design, observations are still serialized
- Bottleneck scales poorly with multiple training jobs

**Severity**: HIGH - Directly limits concurrent training throughput

---

### 2. Empty Filter Pipeline = Full Table Scan (CRITICAL)
**Location**: `kato/filters/executor.py:132-240`

**Issue**: When `filter_pipeline=[]` (default), system performs full table scan:
- Query: `SELECT name, pattern_data, length FROM patterns_data WHERE kb_id = '{kb_id}'`
- Loads ALL patterns from ClickHouse into memory
- No filtering before detailed matching
- With billion-scale patterns, this causes memory explosion

**Impact**:
```
Empty Pipeline:  1B patterns → Load ALL → Match ALL → O(n) memory + time
With MinHash:    1B patterns → 10M candidates → 100 matches → O(log n) with pruning
```

**Severity**: CRITICAL - Makes billion-scale deployments impossible without configuration

---

### 3. Session Lock Serialization (HIGH)
**Location**: `kato/api/endpoints/sessions.py:299-392`

**Issue**: Redis-based session lock serializes entire request lifecycle:
```python
async with lock:
    session = await app_state.session_manager.get_session(session_id)
    processor = await app_state.processor_manager.get_processor(...)
    result = await processor.observe(observation, session_state=session, ...)
    await app_state.session_manager.update_session(session)
```

**Impact**:
- All observations to same session are sequential (no parallelism)
- Lock held during: Redis fetch → observe → predict → Redis update
- Training throughput limited by lock duration per request

**Severity**: HIGH - Limits single-session training throughput

---

### 4. Filter Pipeline Overhead (MAJOR)
**Location**: `kato/filters/executor.py`

**Issue**: Multi-stage filtering is dominant cost (60-70% of prediction time):
1. ClickHouse queries for each database-side filter stage
2. Pattern data retrieval and caching
3. Candidate set reduction across stages
4. Early exit if candidates → 0

**Performance Path**:
```
Stage 1 (MinHash DB):      1B → 10M patterns (30ms)
Stage 2 (MinHash Python):  10M → 5M patterns (20ms)
Stage 3 (Jaccard DB):      5M → 100 patterns (15ms)
Stage 4 (RapidFuzz):       100 → 10 matches (25ms)
Total:                     90ms per prediction
```

**Severity**: MEDIUM - Optimized but still dominant cost at scale

---

### 5. MinHash False Negatives at Low Thresholds (HIGH)
**Location**: `kato/filters/minhash_filter.py`

**Issue**: Default MinHash parameters (bands=20, rows=5) optimize for J ≥ 0.7:
- At threshold 0.7: 95% recall (excellent)
- At threshold 0.4: <40% recall (missing patterns)
- False negatives propagate through sequential pipeline

**Impact**:
- Patterns missed by MinHash never reach downstream filters
- Training with low thresholds produces incomplete results
- No warnings when threshold mismatches band/row configuration

**Severity**: HIGH - Silent correctness issue, not just performance

**Documented**: `docs/reference/filter-pipeline-guide.md`

---

## Performance Characteristics Observed

### Request Processing Pipeline
**Location**: `kato/workers/kato_processor.py`

**Timing Breakdown** (typical prediction request):
- Filter Pipeline Execution: 60-70% of time
- Pattern Similarity Matching: 15-25% of time
- Observation Processing: 5-10% of time
- Session Serialization: 5% of time

### Storage Layer Performance
**ClickHouse** (observed query times):
- Billion-scale patterns: ~1s
- 100M patterns: ~500ms
- 10M patterns: ~300ms
- 1M patterns: ~200ms

**Redis** (session operations):
- `get_session()`: JSON deserialization + TTL update
- `update_session()`: Full serialization + SETEX
- `get_metadata()`: 3 separate Redis calls per pattern

### Pattern Matching Performance
**Two matching modes available**:
- **Token-level** (default): Exact difflib compatibility, 9x faster than difflib
- **Character-level**: 75x faster than difflib, ~0.03 score difference

**Location**: `kato/searches/pattern_search.py:821-900`

---

## Optimization Opportunities

### 1. Configure Filter Pipeline (CRITICAL ACTION)
**Current Issue**: Empty pipeline loads all patterns

**Fix**: Always configure non-empty filter pipeline for training:
```python
config = {
    "filter_pipeline": ["length", "minhash", "jaccard"],
    "recall_threshold": 0.6
}
```

**Expected Impact**: 100-1000x reduction in patterns loaded into memory

**Files to Update**:
- Training notebook configuration
- Session config in `kato/config/session_config.py`

---

### 2. Use Character-Level Matching for Training (HIGH IMPACT)
**Current**: Token-level matching (slower, exact)

**Fix**: Enable character-level for training workloads:
```python
config = {
    "use_token_matching": false  # 75x faster, slight accuracy trade-off
}
```

**Expected Impact**: 10x speedup in similarity calculations (15-25% of total time)

**Trade-off**: ~0.03 score difference from exact difflib

**Files**:
- `kato/config/settings.py`: Set `KATO_USE_TOKEN_MATCHING=false`
- Training notebook: Configure per-session

---

### 3. Tune MinHash Parameters for Threshold (HIGH PRIORITY)
**Current Issue**: Default bands=20, rows=5 optimized for J ≥ 0.7

**Fix**: Adjust based on training threshold:
- Threshold 0.7+: bands=20, rows=5 (default)
- Threshold 0.4-0.7: bands=40, rows=3 (higher recall)
- Threshold <0.4: Use JaccardFilter instead of MinHash

**Expected Impact**: Eliminate false negatives at lower thresholds

**Files**:
- `kato/filters/minhash_filter.py`: Add threshold validation
- `docs/reference/filter-pipeline-guide.md`: Document band/row selection

---

### 4. Remove Debug Logging in Production (MEDIUM IMPACT)
**Current**: Debug logging in hot paths increases I/O overhead

**Locations**:
- `kato/searches/pattern_search.py`: Lines 240-246, 268-282 (stderr prints)
- `kato/filters/executor.py`: Detailed per-stage logging
- `kato/workers/pattern_processor.py`: Verbose debugging

**Fix**: Set `LOG_LEVEL=INFO` in production, remove stderr prints

**Expected Impact**: 5-10% reduction in I/O overhead

---

### 5. Batch Redis Metadata Lookups (MEDIUM IMPACT)
**Current**: 3 Redis calls per pattern for metadata

**Location**: `kato/storage/redis_writer.py`

**Fix**: Implement Redis pipelining:
```python
# Current: 3 separate calls
frequency = redis.get(f"{kb_id}:frequency:{pattern}")
emotives = redis.get(f"{kb_id}:emotives:{pattern}")
metadata = redis.get(f"{kb_id}:metadata:{pattern}")

# Optimized: Single pipeline
pipe = redis.pipeline()
pipe.get(f"{kb_id}:frequency:{pattern}")
pipe.get(f"{kb_id}:emotives:{pattern}")
pipe.get(f"{kb_id}:metadata:{pattern}")
results = pipe.execute()
```

**Expected Impact**: 50-70% reduction in Redis latency for metadata-heavy workloads

---

### 6. Session Caching Layer (MEDIUM IMPACT)
**Current**: Session deserialized from Redis on every request

**Fix**: Add in-memory session cache with TTL:
- Cache deserialized sessions in memory
- Invalidate on session update
- Reduce Redis round-trips by 50%

**Location**: `kato/sessions/redis_session_manager.py`

**Expected Impact**: 10-20% reduction in request latency

---

## Configuration Recommendations for Training

Based on investigation findings, optimal training configuration:

```python
training_config = {
    # CRITICAL: Enable filter pipeline
    "filter_pipeline": ["length", "minhash", "jaccard"],

    # HIGH IMPACT: Use faster matching mode
    "use_token_matching": false,

    # Tune for training workload
    "recall_threshold": 0.6,
    "max_predictions": 100,
    "max_pattern_length": 0,  # Manual learning only
    "stm_mode": "CLEAR",

    # Disable expensive features during training
    "fuzzy_token_threshold": 0.0,  # Disable fuzzy matching
    "enable_filter_metrics": false,  # Reduce logging overhead

    # MinHash tuning (match threshold)
    "minhash_bands": 20,
    "minhash_rows": 5
}
```

**Environment Variables**:
```bash
LOG_LEVEL=INFO  # Reduce debug logging overhead
KATO_USE_TOKEN_MATCHING=false
KATO_USE_FAST_MATCHING=true
KATO_USE_INDEXING=true
KATO_USE_BLOOM_FILTER=true
```

---

## Instrumentation and Monitoring

### Available Performance Metrics

**Filter Pipeline Metrics** (`filters/executor.py`):
- Per-stage candidate counts
- Per-stage execution time (milliseconds)
- Early exit detection

**Metrics Cache** (`storage/metrics_cache.py`):
- Cache hit rate statistics
- Calculation time tracking (avg of last 100)
- Redis-backed caching

**Request Logging** (`config/logging_config.py`):
- Structured JSON logging with trace IDs
- Request duration tracking
- Async context variables for trace propagation

### Recommended Monitoring During Training

1. **Enable filter metrics temporarily** to identify bottlenecks:
   ```python
   config = {"enable_filter_metrics": true}
   ```

2. **Monitor ClickHouse query times**:
   ```bash
   docker logs clickhouse | grep "QueryFinish"
   ```

3. **Track Redis memory usage**:
   ```bash
   docker exec -it redis redis-cli INFO memory
   ```

4. **Profile lock contention** (requires instrumentation):
   - Add timing around lock acquisition in `observation_processor.py`
   - Measure wait time vs hold time

---

## Files Referenced in Investigation

### Core Processing
- `kato/workers/kato_processor.py` - Main processing engine
- `kato/workers/pattern_processor.py` - Pattern learning/matching (lines 354-397)
- `kato/workers/observation_processor.py` - Input processing (line 346: processing lock)

### Storage & Search
- `kato/storage/clickhouse_writer.py` - Pattern storage
- `kato/storage/redis_writer.py` - Metadata storage
- `kato/storage/qdrant_manager.py` - Vector operations
- `kato/searches/pattern_search.py` - Pattern matching (lines 821-900: matching modes)
- `kato/filters/executor.py` - Filter pipeline (lines 132-240)
- `kato/filters/minhash_filter.py` - MinHash/LSH filtering

### API Layer
- `kato/api/endpoints/sessions.py` - Session API (lines 299-392: session lock)

### Configuration
- `kato/config/settings.py` - Environment-based configuration
- `kato/config/session_config.py` - Per-session configuration

### Documentation
- `docs/HYBRID_ARCHITECTURE.md` - Storage architecture
- `docs/reference/filter-pipeline-guide.md` - Filter tuning guide
- `docs/research/pattern-matching.md` - Matching performance
- `docs/maintenance/known-issues.md` - Known issues

---

## Verification Plan

### 1. Validate Filter Pipeline Impact
**Test**: Compare empty vs configured pipeline

```python
# Baseline: Empty pipeline
config_empty = {"filter_pipeline": []}
time_empty = measure_prediction_time()

# Optimized: Full pipeline
config_full = {"filter_pipeline": ["length", "minhash", "jaccard"]}
time_full = measure_prediction_time()

assert time_full < time_empty / 10  # Expect 10x+ speedup
```

### 2. Measure Character-Level vs Token-Level
**Test**: Compare matching modes

```python
# Token-level (slower, exact)
config_token = {"use_token_matching": true}
time_token = measure_prediction_time()

# Character-level (faster)
config_char = {"use_token_matching": false}
time_char = measure_prediction_time()

assert time_char < time_token / 5  # Expect 5x+ speedup
```

### 3. Verify MinHash Recall at Different Thresholds
**Test**: Check pattern recall rates

```python
thresholds = [0.3, 0.5, 0.7, 0.9]
for threshold in thresholds:
    config = {
        "recall_threshold": threshold,
        "filter_pipeline": ["minhash"]
    }
    recall_rate = measure_recall_rate(config)
    print(f"Threshold {threshold}: {recall_rate}% recall")

    # Expect: 0.7+ → 95%+, 0.3-0.5 → <50% with default bands/rows
```

### 4. Profile Lock Contention
**Test**: Measure lock wait times

```bash
# Add timing instrumentation to observation_processor.py:
lock_wait_start = time.time()
with self.processing_lock:
    lock_wait_time = time.time() - lock_wait_start
    # Log wait time if > 100ms

# Run concurrent training sessions
# Monitor for lock contention warnings
```

### 5. Monitor Training Throughput
**Metrics to track**:
- Samples processed per second
- Average request latency
- Filter pipeline stage times
- Redis/ClickHouse query times

**Expected improvements**:
- Empty → Configured pipeline: 10-100x throughput increase
- Token → Character matching: 5-10x throughput increase
- Combined optimizations: 50-1000x improvement depending on scale

---

## Summary

### Bottlenecks by Severity

| Bottleneck | Severity | Impact | Action Required |
|-----------|----------|--------|----------------|
| Empty filter pipeline | CRITICAL | 100-1000x slowdown | Configure pipeline |
| Processing lock serialization | CRITICAL | Limits concurrency | Code refactor (future) |
| MinHash false negatives | HIGH | Silent correctness issue | Tune parameters |
| Session lock serialization | HIGH | Limits throughput | Code refactor (future) |
| Token-level matching | MEDIUM | 10x slower | Use character-level |
| Debug logging | MEDIUM | 5-10% overhead | Set LOG_LEVEL=INFO |
| Redis metadata lookups | MEDIUM | 3N calls | Batch with pipelining |

### Immediate Actions (No Code Changes Required)

1. **Configure filter pipeline in training notebook**
2. **Enable character-level matching** (`use_token_matching=false`)
3. **Set LOG_LEVEL=INFO** in environment
4. **Tune MinHash parameters** for training threshold
5. **Monitor with filter metrics** to validate improvements

### Future Improvements (Code Changes Required)

1. **Remove processing lock** - Redesign for true stateless concurrency
2. **Optimize session locking** - Reduce lock scope or use optimistic locking
3. **Batch Redis operations** - Implement pipelining for metadata
4. **In-memory session cache** - Reduce Redis round-trips
5. **Adaptive filter pipeline** - Auto-tune based on pattern count

---

## Next Steps

1. **Apply immediate optimizations**: Update training notebook configuration based on recommendations
2. **Monitor improvements**: Use verification plan to validate optimizations
3. **Plan future improvements**: Schedule code refactoring for processing lock and session lock issues

---

## References

- **Architecture**: `docs/developers/architecture.md`, `ARCHITECTURE_DIAGRAM.md`
- **Hybrid Architecture**: `docs/HYBRID_ARCHITECTURE.md`
- **Filter Pipeline**: `docs/reference/filter-pipeline-guide.md`
- **Pattern Matching**: `docs/research/pattern-matching.md`
- **Configuration**: `docs/reference/configuration-vars.md`
