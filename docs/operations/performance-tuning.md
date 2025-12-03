# Performance Tuning Guide

Comprehensive operations-focused guide to optimizing KATO performance for production workloads.

## Overview

This guide focuses on practical performance tuning for production KATO deployments. For technical performance details, see [docs/technical/PERFORMANCE.md](../technical/PERFORMANCE.md).

## Performance Targets

### SLA Guidelines

| Service Level | Response Time (P95) | Throughput | Availability | Use Case |
|---------------|---------------------|------------|--------------|----------|
| Critical | <10ms | 10,000+ req/s | 99.99% | Real-time systems |
| Standard | <50ms | 2,000 req/s | 99.9% | Production web apps |
| Batch | <200ms | 500 req/s | 99% | Analytics, reporting |

### Baseline Metrics

**Fresh Installation** (3 instances, default config):
- Requests/sec: 1,000
- P50 latency: 5ms
- P95 latency: 20ms
- P99 latency: 50ms
- CPU usage: 20-40%
- Memory usage: 500MB-1GB per instance

## Configuration Tuning

### Recall Threshold Optimization

The `RECALL_THRESHOLD` parameter has the most significant performance impact.

**Performance vs Accuracy Trade-off**:

| Threshold | Latency (P95) | CPU Usage | Memory | Predictions | Precision | Use Case |
|-----------|---------------|-----------|--------|-------------|-----------|----------|
| 0.1 | 200ms | High (70%) | High | 500+ | Low | Pattern discovery |
| 0.3 | 75ms | Moderate (40%) | Moderate | 100-200 | Moderate | Balanced |
| 0.5 | 30ms | Low (20%) | Low | 20-50 | High | Production |
| 0.7 | 15ms | Very Low (10%) | Very Low | 5-15 | Very High | Real-time |
| 0.9 | 10ms | Minimal (5%) | Minimal | 1-5 | Exact | High-speed |

**Tuning Strategy**:

```bash
# Phase 1: Discovery (weeks 1-2)
RECALL_THRESHOLD=0.2
# Goal: Learn patterns, discover relationships

# Phase 2: Refinement (weeks 3-4)
RECALL_THRESHOLD=0.3
# Goal: Balance accuracy and performance

# Phase 3: Production (ongoing)
RECALL_THRESHOLD=0.5
# Goal: Optimize for speed with good accuracy

# Phase 4: High-Speed (if needed)
RECALL_THRESHOLD=0.7
# Goal: Maximum throughput, high precision
```

**Dynamic Threshold Adjustment** (Advanced):

```python
# kato/workers/adaptive_threshold.py
import psutil
from typing import Dict

class AdaptiveThresholdManager:
    """Adjust recall threshold based on system load."""

    def __init__(self):
        self.base_threshold = 0.4
        self.min_threshold = 0.3
        self.max_threshold = 0.7

    def get_threshold(self) -> float:
        """Calculate threshold based on current load."""
        cpu_usage = psutil.cpu_percent(interval=1)
        memory_percent = psutil.virtual_memory().percent

        # High load - increase threshold (fewer predictions)
        if cpu_usage > 80 or memory_percent > 80:
            return min(self.base_threshold + 0.2, self.max_threshold)

        # Medium load - normal threshold
        elif cpu_usage > 50 or memory_percent > 50:
            return self.base_threshold

        # Low load - decrease threshold (more predictions)
        else:
            return max(self.base_threshold - 0.1, self.min_threshold)
```

### Pattern Length Optimization

**MAX_PATTERN_LENGTH** controls auto-learning:

```bash
# Manual learning (recommended for production)
MAX_PATTERN_LENGTH=0
# Pros: Full control, predictable behavior
# Cons: Requires explicit learn() calls

# Aggressive auto-learning
MAX_PATTERN_LENGTH=10
# Pros: Rapid pattern discovery
# Cons: High CPU, memory usage, noise

# Balanced auto-learning
MAX_PATTERN_LENGTH=25
# Pros: Good balance of discovery and performance
# Cons: Moderate overhead

# Conservative auto-learning
MAX_PATTERN_LENGTH=50
# Pros: Low overhead, high-quality patterns
# Cons: Slower discovery
```

**Production Recommendation**:
```bash
# Use manual learning with scheduled batch learning
MAX_PATTERN_LENGTH=0

# Batch learning cron job (every hour)
0 * * * * curl -X POST http://localhost:8000/sessions/{session_id}/learn
```

### Prediction Limits

**MAX_PREDICTIONS** limits result set size:

```bash
# High recall, high latency
MAX_PREDICTIONS=500
# Use: Pattern discovery, analysis

# Balanced
MAX_PREDICTIONS=100
# Use: Production standard

# Fast response
MAX_PREDICTIONS=20
# Use: Real-time applications
```

**Performance Impact** (10,000 patterns stored):

| MAX_PREDICTIONS | Latency | Memory | Network Payload |
|-----------------|---------|--------|-----------------|
| 500 | 150ms | 45MB | 2.5MB |
| 100 | 50ms | 12MB | 600KB |
| 20 | 20ms | 3MB | 150KB |
| 5 | 10ms | 1MB | 50KB |

### STM Mode Selection

```bash
# CLEAR mode (recommended)
STM_MODE=CLEAR
# Pros: Predictable, lower memory
# Cons: Context lost after learning

# ROLLING mode
STM_MODE=ROLLING
# Pros: Maintains context
# Cons: Higher memory, complexity
```

**Memory Usage Comparison** (1,000 sessions):

| Mode | STM Size | Memory per Session | Total Memory |
|------|----------|-------------------|--------------|
| CLEAR | 0-50 | 0-5KB | 0-5MB |
| ROLLING | 50-100 | 5-10KB | 5-10MB |

## Database Optimization

### ClickHouse Tuning

#### Connection Pool Configuration

```bash
# Default (small deployments)
CLICKHOUSE_POOL_SIZE=50

# Medium deployments (5-10 KATO instances)
CLICKHOUSE_POOL_SIZE=100

# Large deployments (10+ instances)
CLICKHOUSE_POOL_SIZE=200
```

**Calculate Pool Size**:
```
Pool Size = (KATO instances × concurrent requests) + buffer

Example:
- 10 KATO instances
- 10 concurrent requests per instance
- 20% buffer
= 10 × 10 × 1.2 = 120
```

#### Query Optimization

**Table Structure** (KATO uses optimized MergeTree tables):
```sql
-- Pattern table with optimal partitioning and indexing
CREATE TABLE kato.patterns (
    kb_id String,
    name String,
    data String,
    frequency UInt32,
    created_at DateTime,
    INDEX kb_name_idx (kb_id, name) TYPE bloom_filter GRANULARITY 1
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(created_at)
ORDER BY (kb_id, name, created_at);
```

**Verify Query Performance**:
```sql
-- Explain query plan
EXPLAIN SELECT * FROM kato.patterns
WHERE kb_id = 'kato-1' AND frequency > 10;

-- Check query statistics
SELECT
    query,
    query_duration_ms,
    read_rows,
    memory_usage
FROM system.query_log
WHERE type = 'QueryFinish'
ORDER BY event_time DESC
LIMIT 10;
```

#### Memory Configuration

```xml
<!-- clickhouse-config/config.xml -->
<clickhouse>
    <max_memory_usage>8589934592</max_memory_usage> <!-- 8GB -->
    <max_bytes_before_external_group_by>4294967296</max_bytes_before_external_group_by> <!-- 4GB -->
    <max_bytes_before_external_sort>4294967296</max_bytes_before_external_sort> <!-- 4GB -->
</clickhouse>
```

**Memory Guidelines**:
```
ClickHouse Memory = Total RAM × 0.7

Example:
- 16GB RAM available
= 16GB × 0.7 = ~11GB for ClickHouse
```

#### Resource Limits

```yaml
# docker compose.yml
services:
  kato-clickhouse:
    image: clickhouse/clickhouse-server:latest
    deploy:
      resources:
        limits:
          cpus: '4.0'
          memory: 8G
        reservations:
          cpus: '2.0'
          memory: 4G
    ulimits:
      nofile:
        soft: 262144
        hard: 262144
```

### Qdrant Optimization

#### HNSW Configuration

**Update collection settings**:
```python
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, HnswConfigDiff

client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

client.recreate_collection(
    collection_name=f"vectors_{processor_id}",
    vectors_config=VectorParams(
        size=768,
        distance="Cosine"
    ),
    hnsw_config=HnswConfigDiff(
        m=16,  # Number of edges per node (default: 16)
        ef_construct=100,  # Construction time accuracy (default: 100)
        full_scan_threshold=10000,  # Switch to full scan below this (default: 10000)
        max_indexing_threads=0,  # 0 = auto (use all cores)
    ),
    optimizers_config={
        "indexing_threshold": 20000,  # Start indexing after this many vectors
        "memmap_threshold": 50000  # Use memory mapping above this
    }
)
```

**HNSW Parameter Trade-offs**:

| Parameter | Lower Value | Higher Value |
|-----------|-------------|--------------|
| `m` | Faster search, less memory | Slower search, more memory, better accuracy |
| `ef_construct` | Faster indexing, lower accuracy | Slower indexing, higher accuracy |
| `full_scan_threshold` | More HNSW searches | More brute-force searches |

**Production Recommendations**:
```python
# Standard (balanced)
m=16
ef_construct=100

# High accuracy (slower)
m=32
ef_construct=200

# High speed (less accurate)
m=8
ef_construct=50
```

#### Quantization (Memory Reduction)

```python
from qdrant_client.models import ScalarQuantization, ScalarType

# Enable scalar quantization (4x memory reduction)
client.update_collection(
    collection_name=f"vectors_{processor_id}",
    quantization_config=ScalarQuantization(
        type=ScalarType.INT8,
        quantile=0.99,
        always_ram=True
    )
)
```

**Quantization Impact**:
- Memory: 4x reduction (768 floats → 768 int8)
- Speed: 1.5-2x faster
- Accuracy: ~1-2% loss in recall

### Redis Optimization

#### Persistence Configuration

```bash
# Append-Only File (recommended for production)
docker run -d redis:7-alpine redis-server \
  --appendonly yes \
  --appendfsync everysec \
  --auto-aof-rewrite-percentage 100 \
  --auto-aof-rewrite-min-size 64mb

# RDB Snapshots (alternative)
docker run -d redis:7-alpine redis-server \
  --save 900 1 \
  --save 300 10 \
  --save 60 10000
```

**Trade-offs**:

| Method | Performance | Durability | Disk Usage |
|--------|-------------|------------|------------|
| AOF (everysec) | Moderate | High | High |
| AOF (always) | Low | Highest | Highest |
| RDB | High | Moderate | Low |
| None | Highest | None | None |

#### Memory Management

```bash
# Set max memory
docker run -d redis:7-alpine redis-server \
  --maxmemory 2gb \
  --maxmemory-policy allkeys-lru

# Check memory usage
docker exec redis-kb redis-cli INFO memory
```

**Eviction Policies**:
- `allkeys-lru`: Evict any key, LRU (recommended)
- `volatile-lru`: Evict keys with TTL, LRU
- `allkeys-lfu`: Evict any key, LFU (least frequently used)
- `volatile-ttl`: Evict keys with shortest TTL

## Application Optimization

### FastAPI Worker Configuration

```bash
# Single instance (development)
uvicorn kato.api.main:app --host 0.0.0.0 --port 8000

# Multiple workers (production)
gunicorn kato.api.main:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --timeout 120 \
  --keepalive 5 \
  --max-requests 1000 \
  --max-requests-jitter 100
```

**Worker Count Calculation**:
```
Workers = (2 × CPU cores) + 1

Example:
- 4 CPU cores
= (2 × 4) + 1 = 9 workers
```

### Connection Pooling

**ClickHouse Connection Pool**:
```python
from clickhouse_driver import Client
from urllib.parse import urlparse

client = Client(
    host=CLICKHOUSE_HOST,
    port=CLICKHOUSE_PORT,
    database=CLICKHOUSE_DB,
    user=CLICKHOUSE_USER,
    password=CLICKHOUSE_PASSWORD,
    settings={
        'max_execution_time': 60,
        'send_timeout': 300,
        'receive_timeout': 300,
        'max_query_size': 262144,
        'max_ast_elements': 200000,
    },
    compression=True  # Enable compression for better network performance
)
```

**Redis Connection Pool**:
```python
import redis

pool = redis.ConnectionPool(
    host=REDIS_HOST,
    port=REDIS_PORT,
    max_connections=50,
    socket_timeout=5,
    socket_connect_timeout=5,
    socket_keepalive=True,
    health_check_interval=30,
    retry_on_timeout=True
)

redis_client = redis.Redis(connection_pool=pool)
```

### Caching Strategy

**Pattern Cache** (LRU):
```python
from functools import lru_cache

class PatternCache:
    @lru_cache(maxsize=1000)
    def get_pattern(self, pattern_hash: str) -> Pattern:
        """Cache frequently accessed patterns."""
        return self.kb.get_pattern(pattern_hash)

    def invalidate_pattern(self, pattern_hash: str):
        """Invalidate cache entry."""
        self.get_pattern.cache_clear()
```

**Prediction Cache**:
```python
from cachetools import TTLCache
import hashlib

class PredictionCache:
    def __init__(self):
        self.cache = TTLCache(maxsize=500, ttl=300)  # 5 minutes

    def get_predictions(self, stm_hash: str, config_hash: str):
        """Cache predictions for STM state."""
        cache_key = f"{stm_hash}:{config_hash}"
        if cache_key in self.cache:
            return self.cache[cache_key]

        predictions = self._compute_predictions()
        self.cache[cache_key] = predictions
        return predictions
```

## Network Optimization

### HTTP/2 and Keep-Alive

**Nginx Configuration**:
```nginx
server {
    listen 443 ssl http2;  # Enable HTTP/2

    # Keep-alive settings
    keepalive_timeout 65;
    keepalive_requests 100;

    # Connection limits
    limit_conn_zone $binary_remote_addr zone=addr:10m;
    limit_conn addr 10;

    # Buffer sizes
    client_body_buffer_size 16K;
    client_max_body_size 10M;
    large_client_header_buffers 2 1k;

    # Compression
    gzip on;
    gzip_vary on;
    gzip_min_length 1000;
    gzip_types text/plain application/json;

    location / {
        proxy_pass http://kato_backend;

        # Proxy buffering
        proxy_buffering on;
        proxy_buffer_size 4k;
        proxy_buffers 8 4k;

        # Proxy timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;

        # Keep-alive to backend
        proxy_http_version 1.1;
        proxy_set_header Connection "";
    }
}
```

### Request Compression

**Client-side** (Python):
```python
import gzip
import json
import requests

def send_compressed_request(url: str, data: dict):
    """Send gzip-compressed request."""
    json_data = json.dumps(data).encode('utf-8')
    compressed_data = gzip.compress(json_data)

    response = requests.post(
        url,
        data=compressed_data,
        headers={
            'Content-Type': 'application/json',
            'Content-Encoding': 'gzip'
        }
    )
    return response.json()
```

**Server-side** (FastAPI middleware):
```python
from fastapi import Request
import gzip

@app.middleware("http")
async def decompress_request(request: Request, call_next):
    """Decompress gzip requests."""
    if request.headers.get("content-encoding") == "gzip":
        body = await request.body()
        decompressed = gzip.decompress(body)
        request._body = decompressed

    response = await call_next(request)
    return response
```

## Monitoring Performance

### Key Metrics to Track

**Application Metrics**:
```python
# Prometheus metrics
from prometheus_client import Counter, Histogram, Gauge

# Request metrics
request_duration = Histogram(
    'kato_request_duration_seconds',
    'Request duration',
    ['endpoint', 'method'],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0]
)

# Operation metrics
observation_duration = Histogram(
    'kato_observation_duration_seconds',
    'Observation processing time',
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1]
)

prediction_duration = Histogram(
    'kato_prediction_duration_seconds',
    'Prediction generation time',
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0]
)

# Resource metrics
pattern_count = Gauge(
    'kato_patterns_total',
    'Total patterns in LTM',
    ['processor_id']
)
```

### Performance Dashboard Queries

**Grafana Queries**:
```
# Average request duration
avg(rate(kato_request_duration_seconds_sum[5m])) /
avg(rate(kato_request_duration_seconds_count[5m]))

# P95 latency
histogram_quantile(0.95,
  rate(kato_request_duration_seconds_bucket[5m])
)

# Error rate
sum(rate(kato_requests_total{status=~"5.."}[5m])) /
sum(rate(kato_requests_total[5m]))

# Throughput
sum(rate(kato_requests_total[1m]))

# Pattern growth rate
rate(kato_patterns_total[1h])
```

## Performance Testing

### Benchmark Script

```bash
#!/bin/bash
# benchmark.sh - Comprehensive performance testing

BASE_URL="http://localhost:8000"
SESSION_ID="perf-test-$(date +%s)"

# Create session
curl -X POST "${BASE_URL}/sessions" \
  -H "Content-Type: application/json" \
  -d "{\"node_id\": \"${SESSION_ID}\", \"config\": {}}"

# Warm-up (100 requests)
echo "Warming up..."
ab -n 100 -c 10 -p observe.json -T application/json \
   "${BASE_URL}/sessions/${SESSION_ID}/observe"

# Observation benchmark
echo "Benchmarking observations..."
ab -n 10000 -c 50 -p observe.json -T application/json \
   "${BASE_URL}/sessions/${SESSION_ID}/observe"

# Prediction benchmark
echo "Benchmarking predictions..."
ab -n 10000 -c 50 \
   "${BASE_URL}/sessions/${SESSION_ID}/predictions"

# Learning benchmark
echo "Benchmarking learning..."
ab -n 100 -c 10 -p learn.json -T application/json \
   "${BASE_URL}/sessions/${SESSION_ID}/learn"

# Cleanup
curl -X DELETE "${BASE_URL}/sessions/${SESSION_ID}"

echo "Benchmark complete!"
```

### Load Testing with k6

```javascript
// load-test.js
import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  stages: [
    { duration: '2m', target: 100 },  // Ramp up
    { duration: '5m', target: 100 },  // Steady state
    { duration: '2m', target: 200 },  // Peak load
    { duration: '5m', target: 200 },  // Sustained peak
    { duration: '2m', target: 0 },    // Ramp down
  ],
  thresholds: {
    http_req_duration: ['p(95)<100'],  // 95% under 100ms
    http_req_failed: ['rate<0.01'],    // Less than 1% errors
  },
};

export default function () {
  const sessionId = 'perf-test-session';

  // Observe
  const observeRes = http.post(
    `http://localhost:8000/sessions/${sessionId}/observe`,
    JSON.stringify({
      strings: ['test', 'data'],
      vectors: [],
      emotives: {}
    }),
    { headers: { 'Content-Type': 'application/json' } }
  );

  check(observeRes, {
    'observe status 200': (r) => r.status === 200,
    'observe duration < 50ms': (r) => r.timings.duration < 50,
  });

  // Predict
  const predictRes = http.get(
    `http://localhost:8000/sessions/${sessionId}/predictions`
  );

  check(predictRes, {
    'predict status 200': (r) => r.status === 200,
    'predict duration < 100ms': (r) => r.timings.duration < 100,
  });

  sleep(1);
}
```

**Run test**:
```bash
k6 run load-test.js
```

## Optimization Checklist

### Configuration
- [ ] `RECALL_THRESHOLD` tuned for workload (0.3-0.5 for production)
- [ ] `MAX_PREDICTIONS` limited to necessary amount (20-100)
- [ ] `MAX_PATTERN_LENGTH` set to 0 (manual learning)
- [ ] `STM_MODE` set to CLEAR
- [ ] `KATO_USE_FAST_MATCHING` enabled
- [ ] `KATO_USE_INDEXING` enabled

### Database
- [ ] ClickHouse tables optimized (MergeTree with proper ORDER BY)
- [ ] ClickHouse connection pool sized appropriately
- [ ] ClickHouse memory limits configured (70% of RAM)
- [ ] Qdrant HNSW parameters tuned
- [ ] Qdrant quantization enabled (if memory-constrained)
- [ ] Redis persistence configured
- [ ] Redis max memory and eviction policy set

### Application
- [ ] Multiple Gunicorn workers configured
- [ ] Connection pooling enabled
- [ ] Caching implemented for hot paths
- [ ] Async operations used throughout

### Network
- [ ] HTTP/2 enabled
- [ ] Keep-alive configured
- [ ] Compression enabled (gzip)
- [ ] Request/response sizes minimized

### Monitoring
- [ ] Prometheus metrics exposed
- [ ] Grafana dashboards configured
- [ ] Performance alerts set up
- [ ] Regular load testing scheduled

## Related Documentation

- [Performance Reference](../technical/PERFORMANCE.md) - Technical details
- [Performance Issues](performance-issues.md) - Troubleshooting
- [Monitoring](monitoring.md) - Metrics and dashboards
- [Scaling](scaling.md) - Horizontal and vertical scaling
- [Environment Variables](environment-variables.md) - Configuration reference

---

**Last Updated**: November 2025
**KATO Version**: 3.0+
