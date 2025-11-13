# Performance Profiling and Optimization

Comprehensive guide to profiling and optimizing KATO performance.

## Overview

Performance optimization areas in KATO:
1. **Pattern Matching** - Most CPU-intensive operation
2. **Database Queries** - Main I/O bottleneck
3. **Vector Operations** - Memory and computation intensive
4. **Session Management** - Concurrent request handling
5. **Memory Usage** - STM and cache management

## Performance Targets

### Expected Performance Metrics

```
Operation              Target Latency    Throughput
----------------------------------------------------
Observation            < 10ms            > 500 req/s
Pattern Learning       < 100ms           > 50 req/s
Pattern Matching       < 200ms           > 25 req/s
Vector Processing      < 50ms/vector     > 100 vectors/s
Session Creation       < 20ms            > 200 req/s
```

## Profiling Tools

### 1. cProfile (Built-in Profiler)

**Basic Profiling**:
```python
import cProfile
import pstats
from pstats import SortKey

# Profile a function
profiler = cProfile.Profile()
profiler.enable()

# Code to profile
processor.get_predictions()

profiler.disable()

# Print results
stats = pstats.Stats(profiler)
stats.strip_dirs()
stats.sort_stats(SortKey.CUMULATIVE)
stats.print_stats(20)  # Top 20 functions
```

**Output**:
```
   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
        1    0.000    0.000    2.450    2.450 pattern_processor.py:123(get_predictions)
      145    0.023    0.000    2.120    0.015 pattern_search.py:67(search_patterns)
     1450    1.890    0.001    1.890    0.001 {built-in method _rapidfuzz.fuzz.ratio}
      145    0.087    0.001    0.210    0.001 super_knowledge_base.py:89(find_patterns)
```

**Profile Entire Script**:
```bash
python -m cProfile -o profile.stats kato/api/main.py

# Analyze results
python -c "import pstats; p = pstats.Stats('profile.stats'); p.sort_stats('cumulative').print_stats(30)"
```

### 2. line_profiler (Line-by-Line Profiling)

**Installation**:
```bash
pip install line_profiler
```

**Usage**:
```python
# Add @profile decorator
from line_profiler import LineProfiler

@profile
def search_patterns(self, query_stm, threshold):
    """Search patterns matching query."""
    candidates = self._get_candidates(query_stm)  # Line-by-line timing
    scored = []
    for pattern in candidates:
        similarity = self._calculate_similarity(pattern, query_stm)
        if similarity >= threshold:
            scored.append((pattern, similarity))
    return self._rank_patterns(scored)

# Run profiler
profiler = LineProfiler()
profiler.add_function(search_patterns)
profiler.enable()

# Execute code
searcher.search_patterns(stm, 0.3)

profiler.disable()
profiler.print_stats()
```

**Output**:
```
Line #      Hits         Time  Per Hit   % Time  Line Contents
==============================================================
    45         1       1250.0   1250.0      0.1  candidates = self._get_candidates(query_stm)
    46         1          5.0      5.0      0.0  scored = []
    47       145        120.0      0.8      0.0  for pattern in candidates:
    48       145    1890500.0  13038.0     95.2      similarity = self._calculate_similarity(pattern, query_stm)
    49       145       2300.0     15.9      0.1      if similarity >= threshold:
    50        42        850.0     20.2      0.0          scored.append((pattern, similarity))
    51         1      85000.0  85000.0      4.3  return self._rank_patterns(scored)
```

### 3. memory_profiler (Memory Usage)

**Installation**:
```bash
pip install memory_profiler
```

**Usage**:
```python
from memory_profiler import profile

@profile
def learn_pattern(self, stm, emotives):
    """Learn pattern with memory tracking."""
    pattern_hash = self._hash_pattern(stm)  # Memory allocation
    pattern = Pattern(
        pattern_name=f"PTN|{pattern_hash}",
        events=stm,
        emotive_profile=emotives
    )
    self.storage.store_pattern(pattern)
    return pattern

# Run
python -m memory_profiler kato/workers/pattern_processor.py
```

**Output**:
```
Line #    Mem usage    Increment  Occurrences   Line Contents
=============================================================
    45    125.5 MiB    125.5 MiB           1   @profile
    46                                         def learn_pattern(self, stm, emotives):
    47    125.8 MiB      0.3 MiB           1       pattern_hash = self._hash_pattern(stm)
    48    128.2 MiB      2.4 MiB           1       pattern = Pattern(...)
    49    130.5 MiB      2.3 MiB           1       self.storage.store_pattern(pattern)
    50    130.5 MiB      0.0 MiB           1       return pattern
```

### 4. py-spy (Sampling Profiler)

**Installation**:
```bash
pip install py-spy
```

**Live Profiling** (no code changes):
```bash
# Profile running process
py-spy top --pid $(pgrep -f kato)

# Generate flame graph
py-spy record -o profile.svg --pid $(pgrep -f kato)

# Profile for 30 seconds
py-spy record -o profile.svg --duration 30 -- python -m kato.api.main
```

**Flame Graph**:
- Wide bars = more time spent
- Depth = call stack depth
- Interactive SVG for drilling down

### 5. pytest-benchmark (Performance Tests)

**Installation**:
```bash
pip install pytest-benchmark
```

**Usage**:
```python
def test_pattern_matching_benchmark(benchmark, kato_fixture):
    """Benchmark pattern matching performance."""
    # Setup
    for i in range(100):
        kato_fixture.observe({'strings': [f'token_{i}'], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()

    kato_fixture.clear_stm()
    kato_fixture.observe({'strings': ['token_0'], 'vectors': [], 'emotives': {}})

    # Benchmark
    result = benchmark(kato_fixture.get_predictions)

    # Assertions
    assert len(result['predictions']) > 0

# Run benchmarks
pytest tests/test_performance.py --benchmark-only

# Compare with previous runs
pytest tests/test_performance.py --benchmark-autosave
pytest tests/test_performance.py --benchmark-compare
```

**Output**:
```
---------------------------- benchmark: 1 tests ----------------------------
Name (time in ms)                    Min      Max     Mean  StdDev  Median
---------------------------------------------------------------------------
test_pattern_matching_benchmark    145.2    198.5    165.3    12.4   163.8
---------------------------------------------------------------------------
```

## Database Optimization

### MongoDB Indexing

**Check Current Indices**:
```javascript
// Connect to MongoDB
docker exec -it kato-mongodb mongosh

use node_my_app_kato
db.patterns.getIndexes()
```

**Create Optimal Indices**:
```javascript
// Pattern ID (created automatically)
db.patterns.createIndex({"_id": 1})

// Length-based queries
db.patterns.createIndex({"length": 1})

// Temporal queries
db.patterns.createIndex({"created_at": -1})
db.patterns.createIndex({"updated_at": -1})

// Observation count (for ranking)
db.patterns.createIndex({"observation_count": -1})

// Compound index for common query patterns
db.patterns.createIndex({"length": 1, "observation_count": -1})

// Event-based queries (first event)
db.patterns.createIndex({"events.0": 1})

// Text search (if needed)
db.patterns.createIndex({"events": "text"})
```

**Analyze Query Performance**:
```javascript
// Explain query plan
db.patterns.find({"length": 3}).explain("executionStats")

// Look for:
// - "stage": "IXSCAN" (good - using index)
// - "stage": "COLLSCAN" (bad - full collection scan)
// - "executionTimeMillis": < 100ms (target)
```

**Enable Query Profiling**:
```javascript
// Profile slow queries (>100ms)
db.setProfilingLevel(1, {slowms: 100})

// View slow queries
db.system.profile.find().sort({ts: -1}).limit(10).pretty()

// Disable profiling
db.setProfilingLevel(0)
```

### Qdrant Optimization

**HNSW Configuration**:
```python
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, HnswConfigDiff

# Optimize for speed
client.create_collection(
    collection_name="vectors_fast",
    vectors_config=VectorParams(
        size=768,
        distance=Distance.COSINE
    ),
    hnsw_config=HnswConfigDiff(
        m=16,              # Links per layer (higher = more accurate, slower)
        ef_construct=100,  # Construction parameter (higher = better quality)
        ef=128            # Search parameter (higher = more accurate, slower)
    )
)

# Optimize for memory
client.create_collection(
    collection_name="vectors_memory_efficient",
    vectors_config=VectorParams(size=768, distance=Distance.COSINE),
    hnsw_config=HnswConfigDiff(
        m=8,               # Fewer links = less memory
        ef_construct=50,
        ef=64
    )
)
```

**Benchmarking**:
```python
import time
import numpy as np

def benchmark_vector_search(collection_name, num_queries=100):
    """Benchmark vector search performance."""
    timings = []

    for _ in range(num_queries):
        query_vector = np.random.rand(768).tolist()

        start = time.time()
        results = client.search(
            collection_name=collection_name,
            query_vector=query_vector,
            limit=100
        )
        timings.append(time.time() - start)

    print(f"Collection: {collection_name}")
    print(f"  Mean: {np.mean(timings)*1000:.2f}ms")
    print(f"  Median: {np.median(timings)*1000:.2f}ms")
    print(f"  P95: {np.percentile(timings, 95)*1000:.2f}ms")
    print(f"  P99: {np.percentile(timings, 99)*1000:.2f}ms")
```

### Redis Optimization

**Connection Pooling**:
```python
from redis import ConnectionPool, Redis

# Create pool once
pool = ConnectionPool(
    host='localhost',
    port=6379,
    max_connections=50,  # Tune based on concurrency
    decode_responses=True
)

# Reuse connections
redis_client = Redis(connection_pool=pool)
```

**Pipeline Operations**:
```python
# Bad: Multiple round trips
redis_client.set('session:abc:stm', json.dumps(stm))
redis_client.set('session:abc:emotives', json.dumps(emotives))
redis_client.expire('session:abc:stm', 3600)
redis_client.expire('session:abc:emotives', 3600)

# Good: Single round trip
pipe = redis_client.pipeline()
pipe.set('session:abc:stm', json.dumps(stm))
pipe.set('session:abc:emotives', json.dumps(emotives))
pipe.expire('session:abc:stm', 3600)
pipe.expire('session:abc:emotives', 3600)
pipe.execute()
```

## Code Optimization

### 1. Pattern Matching Optimization

**Use Token-Level Matching** (9x faster):
```python
# config/settings.py
USE_TOKEN_MATCHING=true  # Default: token-level (faster)

# Token-level: O(n) set operations
def token_similarity(pattern_event, query_event):
    return len(set(pattern_event) & set(query_event)) / len(set(pattern_event) | set(query_event))

# Character-level: O(n*m) string comparison
def character_similarity(pattern_str, query_str):
    from rapidfuzz import fuzz
    return fuzz.ratio(pattern_str, query_str) / 100.0
```

**Benchmark Results**:
```
Token-level:      15.2ms (✓ Default)
Character-level: 138.5ms (9x slower, only for fuzzy text)
```

### 2. RapidFuzz Optimization

**Use RapidFuzz** (10x faster than difflib):
```python
# Install
pip install rapidfuzz>=3.0.0

# searches/pattern_search.py
RAPIDFUZZ_AVAILABLE = True
try:
    from rapidfuzz import fuzz, process
except ImportError:
    RAPIDFUZZ_AVAILABLE = False
    # Fallback to difflib (much slower)

# Benchmark
import time
from rapidfuzz import fuzz
from difflib import SequenceMatcher

s1 = "the quick brown fox jumps over the lazy dog"
s2 = "the quack brown fox jumped over the lazy cat"

# RapidFuzz
start = time.time()
for _ in range(10000):
    score = fuzz.ratio(s1, s2)
print(f"RapidFuzz: {time.time() - start:.3f}s")  # ~0.05s

# difflib
start = time.time()
for _ in range(10000):
    score = SequenceMatcher(None, s1, s2).ratio()
print(f"difflib: {time.time() - start:.3f}s")  # ~0.50s (10x slower)
```

### 3. Caching

**Pattern Cache**:
```python
from functools import lru_cache

class PatternProcessor:
    @lru_cache(maxsize=1000)
    def _hash_pattern(self, events_tuple: tuple) -> str:
        """Cache pattern hashes."""
        import hashlib
        events_str = json.dumps(list(events_tuple))
        return hashlib.sha1(events_str.encode()).hexdigest()[:16]

    def learn_pattern(self, stm: list[list[str]], emotives: dict):
        # Convert to tuple for caching
        events_tuple = tuple(tuple(event) for event in stm)
        pattern_hash = self._hash_pattern(events_tuple)
        # ...
```

**Redis Cache for Predictions**:
```python
def get_predictions(self, threshold: float) -> list[dict]:
    """Get predictions with caching."""
    # Generate cache key
    stm_hash = self._hash_stm(self.memory_manager.get_stm())
    cache_key = f"predictions:{self.node_id}:{stm_hash}:{threshold}"

    # Check cache
    cached = self.redis.get(cache_key)
    if cached:
        return json.loads(cached)

    # Calculate predictions
    predictions = self._calculate_predictions(threshold)

    # Store in cache (5 minute TTL)
    self.redis.setex(cache_key, 300, json.dumps(predictions))

    return predictions
```

### 4. Async Operations

**Parallelize I/O Operations**:
```python
import asyncio

async def observe(self, data: dict) -> dict:
    """Process observation with async I/O."""
    # Process vectors and store in parallel
    tasks = []

    if data.get('vectors'):
        tasks.append(self.vector_processor.process_vectors_async(data['vectors']))

    if data.get('emotives'):
        tasks.append(self.memory_manager.update_emotives_async(data['emotives']))

    # Wait for all parallel operations
    if tasks:
        await asyncio.gather(*tasks)

    # Sequential operations
    self.memory_manager.add_to_stm(data['strings'])

    return {"observed": True}
```

### 5. Batch Processing

**Batch Database Writes**:
```python
def store_patterns_batch(self, patterns: list[Pattern]):
    """Store multiple patterns efficiently."""
    # Batch MongoDB write
    docs = [pattern.to_dict() for pattern in patterns]
    self.patterns_kb.insert_many(docs, ordered=False)

    # Batch ClickHouse write
    if self.clickhouse_client:
        self.clickhouse_client.insert_batch(patterns)

# Usage
patterns = []
for i in range(100):
    pattern = self.learn_pattern(stm, emotives)
    patterns.append(pattern)

# Single batch write (much faster than 100 individual writes)
self.store_patterns_batch(patterns)
```

## Memory Optimization

### Monitor Memory Usage

```python
import psutil
import tracemalloc

def log_memory_usage():
    """Log current memory usage."""
    process = psutil.Process()
    mem_info = process.memory_info()

    logger.info(
        "Memory usage",
        extra={
            "rss_mb": mem_info.rss / 1024 / 1024,
            "vms_mb": mem_info.vms / 1024 / 1024,
            "percent": process.memory_percent()
        }
    )

# Track allocations
tracemalloc.start()

# ... run code ...

snapshot = tracemalloc.take_snapshot()
top_stats = snapshot.statistics('lineno')

for stat in top_stats[:10]:
    print(f"{stat.filename}:{stat.lineno}: {stat.size / 1024:.1f} KB")
```

### STM Management

```python
# config/settings.py
STM_MODE=CLEAR  # Clear STM after learning (reduce memory)
# STM_MODE=ROLLING  # Keep rolling window (constant memory)

# workers/memory_manager.py
class MemoryManager:
    def __init__(self, stm_mode: str = "CLEAR", max_stm_length: int = 1000):
        self.stm = deque(maxlen=max_stm_length if stm_mode == "ROLLING" else None)
        self.stm_mode = stm_mode

    def add_to_stm(self, event: list[str]):
        self.stm.append(event)

        # Rolling mode: automatic cleanup
        if self.stm_mode == "ROLLING":
            # deque handles this automatically with maxlen

        # Clear mode: manual cleanup after learning
        # (handled in KatoProcessor.learn())
```

### Cache Size Limits

```python
from cachetools import LRUCache, TTLCache

class PatternCache:
    def __init__(self, max_size: int = 10000, ttl: int = 3600):
        # LRU cache with size limit
        self.pattern_cache = LRUCache(maxsize=max_size)

        # TTL cache for predictions
        self.prediction_cache = TTLCache(maxsize=1000, ttl=ttl)

    def get_pattern(self, pattern_name: str) -> Optional[Pattern]:
        if pattern_name in self.pattern_cache:
            return self.pattern_cache[pattern_name]

        # Fetch from database
        pattern = self.storage.get_pattern(pattern_name)
        if pattern:
            self.pattern_cache[pattern_name] = pattern

        return pattern
```

## Load Testing

### Using Locust

**Installation**:
```bash
pip install locust
```

**Load Test Script** (`locustfile.py`):
```python
from locust import HttpUser, task, between
import random

class KatoUser(HttpUser):
    wait_time = between(1, 3)  # Wait 1-3 seconds between requests

    def on_start(self):
        """Create session on start."""
        response = self.client.post("/sessions", json={
            "node_id": f"load_test_user_{self.user_id}"
        })
        self.session_id = response.json()['session_id']

    @task(3)  # Weight: 3x more observations than learning
    def observe(self):
        """Observe data."""
        self.client.post(
            f"/sessions/{self.session_id}/observe",
            json={
                "strings": [f"token_{random.randint(0, 100)}"],
                "vectors": [],
                "emotives": {}
            }
        )

    @task(1)
    def learn(self):
        """Learn pattern."""
        self.client.post(f"/sessions/{self.session_id}/learn")

    @task(2)
    def predict(self):
        """Get predictions."""
        self.client.get(f"/sessions/{self.session_id}/predictions")

# Run load test
# locust -f locustfile.py --host=http://localhost:8000
```

**Run Load Test**:
```bash
# Command line
locust -f locustfile.py --host=http://localhost:8000 --users 100 --spawn-rate 10

# Web UI (better visualization)
locust -f locustfile.py --host=http://localhost:8000
# Open http://localhost:8089
```

## Performance Monitoring

### Prometheus Metrics

```python
from prometheus_client import Counter, Histogram, Gauge

# Define metrics
observation_counter = Counter('kato_observations_total', 'Total observations')
prediction_latency = Histogram('kato_prediction_latency_seconds', 'Prediction latency')
active_sessions = Gauge('kato_active_sessions', 'Number of active sessions')

# Use in code
@prediction_latency.time()
def get_predictions(self):
    """Get predictions with timing."""
    # ... logic ...
    observation_counter.inc()
    return predictions

# Expose metrics endpoint
from prometheus_client import make_asgi_app

app.mount("/metrics", make_asgi_app())
```

### Grafana Dashboard

Query Prometheus metrics and visualize:
- Request rate (req/s)
- Latency percentiles (p50, p95, p99)
- Error rate
- Active sessions
- Memory usage
- Database query times

## Related Documentation

- [Debugging Guide](debugging.md)
- [Architecture Overview](architecture.md)
- [Database Management](database-management.md)
- [Testing Guide](testing.md)

---

**Last Updated**: November 2025
**KATO Version**: 3.0+
