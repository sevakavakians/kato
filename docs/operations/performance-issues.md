# Performance Issues Troubleshooting Guide

Comprehensive guide to diagnosing and resolving KATO performance issues in production.

## Overview

This guide helps identify, diagnose, and resolve common performance issues in KATO deployments. Each section includes symptoms, diagnosis steps, and solutions.

## Quick Diagnosis Decision Tree

```
Performance Issue?
├─ High Latency (>100ms)
│  ├─ Application slow? → See "High Latency"
│  ├─ Database slow? → See "Database Performance"
│  └─ Network slow? → See "Network Issues"
│
├─ High CPU Usage (>80%)
│  ├─ KATO process? → See "High CPU Usage"
│  ├─ Database process? → See "Database CPU"
│  └─ Multiple processes? → See "Resource Contention"
│
├─ High Memory Usage (>80%)
│  ├─ Memory leak? → See "Memory Leaks"
│  ├─ Large dataset? → See "Memory Optimization"
│  └─ Too many sessions? → See "Session Management"
│
├─ Low Throughput (<100 req/s)
│  ├─ Connection limits? → See "Connection Pool Issues"
│  ├─ Rate limiting? → See "Rate Limiting"
│  └─ Queuing delays? → See "Queue Backlog"
│
└─ Intermittent Issues
   ├─ Spikes/drops? → See "Intermittent Performance"
   ├─ Time-based? → See "Periodic Performance Issues"
   └─ Random? → See "Race Conditions"
```

## High Latency Issues

### Symptom: P95 Latency >100ms

**Diagnosis**:
```bash
# Check current latency
curl -w "@curl-format.txt" -o /dev/null -s http://localhost:8000/health

# curl-format.txt content:
# time_namelookup: %{time_namelookup}s
# time_connect: %{time_connect}s
# time_appconnect: %{time_appconnect}s
# time_pretransfer: %{time_pretransfer}s
# time_starttransfer: %{time_starttransfer}s
# time_total: %{time_total}s

# Check Prometheus metrics
curl http://localhost:8000/metrics | grep kato_request_duration

# Check specific endpoint latency
kubectl logs -f deployment/kato -n kato | grep -E "duration_ms|latency"
```

**Common Causes**:

#### 1. High Recall Threshold Too Low

**Symptoms**:
- Latency spikes during predictions
- High CPU during prediction requests
- Many predictions returned

**Solution**:
```bash
# Increase recall threshold
RECALL_THRESHOLD=0.5  # from 0.1

# Limit predictions
MAX_PREDICTIONS=50  # from 500

# Restart KATO
docker-compose restart kato
```

**Verify**:
```bash
# Check prediction count
curl http://localhost:8000/sessions/{session_id}/predictions | jq '.present | length'

# Should be <100 predictions
```

#### 2. Unoptimized Database Queries

**Symptoms**:
- Slow database operations in logs
- High ClickHouse CPU
- Missing indexes or inefficient queries

**Diagnosis**:
```bash
# Check slow queries in ClickHouse
curl "http://kato-clickhouse:8123/" --data "
  SELECT query, elapsed, read_rows, read_bytes
  FROM system.query_log
  WHERE type = 'QueryFinish'
    AND elapsed > 0.1
  ORDER BY event_time DESC
  LIMIT 10
"

# Check table structure and indexes
curl "http://kato-clickhouse:8123/" --data "
  SHOW CREATE TABLE kato.patterns
"
```

**Solution**:
```bash
# Optimize table structure with proper indexes
curl "http://kato-clickhouse:8123/" --data "
  OPTIMIZE TABLE kato.patterns FINAL
"

# Check if indexes are being used
curl "http://kato-clickhouse:8123/" --data "
  EXPLAIN indexes = 1
  SELECT * FROM kato.patterns
  WHERE kb_id = 'kato-1'
    AND frequency > 10
"
```

#### 3. Slow Vector Search

**Symptoms**:
- Slow predictions with vectors
- High Qdrant CPU
- Large vector collections

**Diagnosis**:
```bash
# Check Qdrant collection size
curl http://localhost:6333/collections/vectors_kato-1

# Check search performance
time curl -X POST http://localhost:6333/collections/vectors_kato-1/points/search \
  -H "Content-Type: application/json" \
  -d '{
    "vector": [...],
    "limit": 10
  }'
```

**Solution**:
```python
# Update HNSW parameters for faster search
from qdrant_client import QdrantClient
from qdrant_client.models import HnswConfigDiff

client = QdrantClient(host="qdrant-kb", port=6333)

client.update_collection(
    collection_name="vectors_kato-1",
    hnsw_config=HnswConfigDiff(
        m=16,  # Reduce from 32
        ef_construct=100  # Reduce from 200
    )
)

# Enable quantization
from qdrant_client.models import ScalarQuantization, ScalarType

client.update_collection(
    collection_name="vectors_kato-1",
    quantization_config=ScalarQuantization(
        type=ScalarType.INT8,
        quantile=0.99
    )
)
```

## High CPU Usage

### Symptom: CPU >80% for Extended Period

**Diagnosis**:
```bash
# Check process CPU
docker stats kato

# Check CPU breakdown
kubectl top pods -n kato

# Profile CPU usage (if Python debugging enabled)
docker exec -it kato python -m cProfile -o profile.stats \
  -m kato.api.main

# View profile
python -c "
import pstats
p = pstats.Stats('profile.stats')
p.strip_dirs().sort_stats('cumulative').print_stats(20)
"
```

**Common Causes**:

#### 1. Too Many Pattern Matches

**Symptoms**:
- High CPU during predictions
- Low recall threshold (0.1-0.2)
- Large pattern database (>100k patterns)

**Solution**:
```bash
# Increase recall threshold
RECALL_THRESHOLD=0.5

# Add pattern frequency filtering
MIN_PATTERN_FREQUENCY=3  # Only match patterns seen 3+ times

# Limit pattern length
MAX_PATTERN_LENGTH_MATCH=50  # Don't match patterns >50 elements
```

**Implement frequency filtering** (`kato/searches/pattern_search.py`):
```python
def search_patterns(self, stm: List[str], threshold: float, min_frequency: int = 3):
    """Search patterns with frequency filtering."""
    patterns = self.kb.get_patterns(
        processor_id=self.processor_id,
        min_frequency=min_frequency  # Add frequency filter
    )
    # ... rest of search logic
```

#### 2. Inefficient Matching Algorithm

**Symptoms**:
- High CPU on string matching
- Slow prediction generation
- Character-level matching being used

**Solution**:
```bash
# Enable fast matching (if not already)
KATO_USE_FAST_MATCHING=true

# Use token-level matching (not character-level)
KATO_USE_TOKEN_MATCHING=true

# Restart KATO
docker-compose restart kato
```

#### 3. Excessive Logging

**Symptoms**:
- High CPU during all operations
- Large log files
- DEBUG log level in production

**Solution**:
```bash
# Reduce log level
LOG_LEVEL=INFO  # from DEBUG

# Disable verbose logging
LOG_VERBOSE=false

# Use log sampling (log 1 in 10 requests)
LOG_SAMPLE_RATE=0.1
```

## High Memory Usage

### Symptom: Memory >80% or OOM Errors

**Diagnosis**:
```bash
# Check memory usage
docker stats kato
kubectl top pods -n kato

# Check for memory leaks
docker exec -it kato python -c "
import gc
import sys
gc.collect()
print(f'Objects: {len(gc.get_objects())}')
print(f'Memory: {sys.getsizeof(gc.get_objects()) / 1024 / 1024:.2f} MB')
"

# Monitor memory over time
watch -n 5 'docker stats kato --no-stream'
```

**Common Causes**:

#### 1. Memory Leak in Sessions

**Symptoms**:
- Memory grows over time
- Many inactive sessions
- Sessions not being cleaned up

**Diagnosis**:
```bash
# Check session count
redis-cli KEYS "session:*" | wc -l

# Check session sizes
redis-cli --bigkeys

# Check expired sessions
redis-cli KEYS "session:*" | while read key; do
  ttl=$(redis-cli TTL "$key")
  if [ $ttl -eq -1 ]; then
    echo "$key has no TTL"
  fi
done
```

**Solution**:
```bash
# Enable session cleanup
SESSION_TTL=3600  # 1 hour
SESSION_AUTO_EXTEND=true  # Extend active sessions

# Add cleanup cron job
*/15 * * * * curl -X POST http://localhost:8000/admin/cleanup-sessions

# Manual cleanup
redis-cli KEYS "session:*" | xargs redis-cli DEL
```

**Implement cleanup endpoint** (`kato/api/endpoints/admin.py`):
```python
@app.post("/admin/cleanup-sessions")
async def cleanup_sessions():
    """Remove expired sessions."""
    count = 0
    for key in await redis.keys("session:*"):
        ttl = await redis.ttl(key)
        if ttl == -1 or ttl <= 0:
            await redis.delete(key)
            count += 1
    return {"deleted": count}
```

#### 2. Large STM Accumulation

**Symptoms**:
- Memory grows with observations
- STM not being cleared
- ROLLING mode with high observation rate

**Solution**:
```bash
# Use CLEAR mode
STM_MODE=CLEAR

# Trigger learning more frequently
MAX_PATTERN_LENGTH=25  # from 100

# Manually clear STM periodically
curl -X POST http://localhost:8000/sessions/{session_id}/clear-stm
```

#### 3. Pattern Cache Overflow

**Symptoms**:
- Memory grows with learned patterns
- Large pattern database
- No cache eviction

**Solution**:
```python
# Implement LRU cache with size limit
from cachetools import LRUCache

class PatternCache:
    def __init__(self, maxsize=1000):
        self.cache = LRUCache(maxsize=maxsize)

    def get(self, key):
        return self.cache.get(key)

    def set(self, key, value):
        self.cache[key] = value
```

## Database Performance Issues

### ClickHouse Performance

**Symptoms**:
- Slow queries (>100ms)
- High ClickHouse CPU
- High memory usage

**Diagnosis**:
```bash
# Check current operations
curl "http://kato-clickhouse:8123/" --data "
  SELECT query, elapsed, memory_usage
  FROM system.processes
  WHERE elapsed > 1
"

# Check slow queries
curl "http://kato-clickhouse:8123/" --data "
  SELECT query, query_duration_ms, read_rows
  FROM system.query_log
  WHERE type = 'QueryFinish'
    AND query_duration_ms > 100
  ORDER BY event_time DESC
  LIMIT 10
"

# Check table sizes
curl "http://kato-clickhouse:8123/" --data "
  SELECT
    table,
    formatReadableSize(sum(bytes)) as size,
    sum(rows) as rows
  FROM system.parts
  WHERE database = 'kato'
  GROUP BY table
"
```

**Solutions**:

#### 1. Optimize Table Structure

```bash
# Use appropriate engine and partitioning
curl "http://kato-clickhouse:8123/" --data "
  ALTER TABLE kato.patterns
  MODIFY SETTING parts_to_throw_insert = 300
"

# Optimize table (merge parts)
curl "http://kato-clickhouse:8123/" --data "
  OPTIMIZE TABLE kato.patterns FINAL
"
```

#### 2. Add Materialized Views for Common Queries

```bash
# Create materialized view for frequency aggregations
curl "http://kato-clickhouse:8123/" --data "
  CREATE MATERIALIZED VIEW IF NOT EXISTS kato.pattern_frequencies
  ENGINE = SummingMergeTree()
  ORDER BY (kb_id, pattern_name)
  AS SELECT
    kb_id,
    pattern_name,
    count() as frequency
  FROM kato.patterns
  GROUP BY kb_id, pattern_name
"
```

### Qdrant Performance

**Symptoms**:
- Slow vector searches (>100ms)
- High Qdrant memory
- Indexing taking too long

**Diagnosis**:
```bash
# Check collection stats
curl http://localhost:6333/collections/vectors_kato-1

# Check memory usage
docker stats qdrant-kb

# Test search performance
time curl -X POST http://localhost:6333/collections/vectors_kato-1/points/search \
  -H "Content-Type: application/json" \
  -d '{
    "vector": [0.1, 0.2, ...],
    "limit": 10
  }'
```

**Solutions**:

#### 1. Too Many Vectors

```bash
# Implement vector deduplication
curl -X POST http://localhost:8000/admin/deduplicate-vectors

# Remove old vectors
curl -X POST http://localhost:8000/admin/cleanup-vectors?days=90
```

#### 2. Unoptimized HNSW Parameters

```python
# Tune for speed (lower accuracy)
client.update_collection(
    collection_name="vectors_kato-1",
    hnsw_config=HnswConfigDiff(
        m=8,  # from 16
        ef_construct=50  # from 100
    )
)
```

## Network Issues

### Symptom: High Network Latency

**Diagnosis**:
```bash
# Test internal network
docker exec kato ping kato-clickhouse
docker exec kato ping qdrant-kb
docker exec kato ping redis-kb

# Test external latency
curl -w "@curl-format.txt" -o /dev/null -s https://kato.yourdomain.com/health

# Check network bandwidth
iftop -i eth0
```

**Common Causes**:

#### 1. Large Response Payloads

**Symptoms**:
- Slow prediction responses
- High network bandwidth
- Many predictions returned

**Solution**:
```bash
# Limit predictions
MAX_PREDICTIONS=20  # from 100

# Enable compression
# nginx.conf
gzip on;
gzip_types application/json;
```

#### 2. Connection Overhead

**Symptoms**:
- Many short-lived connections
- High connection establishment time
- No keep-alive

**Solution**:
```nginx
# Enable keep-alive
upstream kato_backend {
    server kato:8000;
    keepalive 32;
}

server {
    location / {
        proxy_pass http://kato_backend;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
    }
}
```

## Intermittent Performance Issues

### Symptom: Performance Degrades Periodically

**Diagnosis**:
```bash
# Monitor CPU over time
sar -u 1 60  # 60 seconds

# Monitor memory over time
sar -r 1 60

# Check for cron jobs
crontab -l

# Check for scheduled tasks
kubectl get cronjobs -n kato
```

**Common Causes**:

#### 1. Garbage Collection Pauses

**Symptoms**:
- Periodic latency spikes
- Python GC running frequently
- Large heaps

**Solution**:
```python
# Tune garbage collection
import gc

# Disable automatic GC
gc.disable()

# Manual GC during idle periods
def scheduled_gc():
    """Run GC during low-traffic periods."""
    import schedule
    import time

    def run_gc():
        gc.collect()
        print(f"GC collected {gc.get_count()} objects")

    # Run GC every 5 minutes at :00, :05, etc.
    schedule.every(5).minutes.do(run_gc)

    while True:
        schedule.run_pending()
        time.sleep(60)
```

#### 2. Background Tasks Interfering

**Symptoms**:
- Performance drops at scheduled times
- Backup or cleanup jobs running
- High I/O during certain hours

**Solution**:
```bash
# Schedule resource-intensive tasks during off-peak hours
# Backup job at 2 AM
0 2 * * * /scripts/backup.sh

# Cleanup job at 3 AM
0 3 * * * /scripts/cleanup.sh

# Use nice/ionice for background tasks
nice -n 19 ionice -c3 /scripts/maintenance.sh
```

## Connection Pool Issues

### Symptom: Connection Pool Exhausted

**Diagnosis**:
```bash
# Check ClickHouse connections
curl "http://kato-clickhouse:8123/" --data "
  SELECT count() FROM system.processes
"

# Check Redis connections
docker exec redis-kb redis-cli CLIENT LIST | wc -l

# Check KATO connection usage
docker logs kato | grep -i "connection"
```

**Solutions**:

#### 1. Increase Pool Size

```bash
# ClickHouse max connections (in config.xml)
# <max_connections>1000</max_connections>

# Redis
REDIS_MAX_CONNECTIONS=100  # from 50
```

#### 2. Fix Connection Leaks

**Check for leaks**:
```python
# Add connection tracking
class ConnectionTracker:
    def __init__(self):
        self.active_connections = {}

    def track(self, conn_id: str):
        self.active_connections[conn_id] = time.time()

    def release(self, conn_id: str):
        if conn_id in self.active_connections:
            duration = time.time() - self.active_connections[conn_id]
            if duration > 60:  # Connection held >60s
                logger.warning(f"Long-lived connection: {conn_id} ({duration}s)")
            del self.active_connections[conn_id]
```

## Performance Monitoring

### Set Up Continuous Monitoring

**Prometheus Alerts**:
```yaml
# alerts/performance-alerts.yml
groups:
  - name: performance
    rules:
      # High latency
      - alert: HighLatency
        expr: histogram_quantile(0.95, rate(kato_request_duration_seconds_bucket[5m])) > 0.1
        for: 5m
        annotations:
          summary: "High P95 latency: {{ $value }}s"

      # High CPU
      - alert: HighCPU
        expr: rate(process_cpu_seconds_total[1m]) * 100 > 80
        for: 5m
        annotations:
          summary: "High CPU usage: {{ $value }}%"

      # High memory
      - alert: HighMemory
        expr: process_resident_memory_bytes / 1e9 > 3
        for: 10m
        annotations:
          summary: "High memory usage: {{ $value }}GB"

      # Slow database queries
      - alert: SlowDatabaseQueries
        expr: rate(clickhouse_query_duration_seconds[5m]) > 0.1
        for: 5m
        annotations:
          summary: "Slow ClickHouse queries: {{ $value }}s"
```

### Performance Regression Testing

```bash
#!/bin/bash
# regression-test.sh - Detect performance regressions

BASELINE_P95=50  # 50ms baseline
THRESHOLD=1.5    # 50% degradation threshold

# Run benchmark
CURRENT_P95=$(ab -n 1000 -c 10 http://localhost:8000/health | grep "95%" | awk '{print $2}')

# Compare
if (( $(echo "$CURRENT_P95 > $BASELINE_P95 * $THRESHOLD" | bc -l) )); then
    echo "Performance regression detected!"
    echo "Baseline: ${BASELINE_P95}ms"
    echo "Current: ${CURRENT_P95}ms"
    exit 1
else
    echo "Performance within acceptable range"
    exit 0
fi
```

## Performance Issue Checklist

### Immediate Actions
- [ ] Check Prometheus dashboards for anomalies
- [ ] Review recent changes/deployments
- [ ] Check resource usage (CPU, memory, disk, network)
- [ ] Review logs for errors
- [ ] Check database performance

### Short-Term Fixes
- [ ] Increase `RECALL_THRESHOLD` (0.5+)
- [ ] Limit `MAX_PREDICTIONS` (20-50)
- [ ] Clear unnecessary sessions
- [ ] Restart services if needed
- [ ] Scale horizontally (add instances)

### Long-Term Solutions
- [ ] Optimize database indexes
- [ ] Implement caching
- [ ] Tune database parameters
- [ ] Set up auto-scaling
- [ ] Review and optimize code

### Prevention
- [ ] Regular load testing
- [ ] Performance monitoring
- [ ] Capacity planning
- [ ] Code reviews for performance
- [ ] Document performance baselines

## Related Documentation

- [Performance Tuning](performance-tuning.md) - Optimization strategies
- [Monitoring](monitoring.md) - Metrics and dashboards
- [Scaling](scaling.md) - Horizontal and vertical scaling
- [Environment Variables](environment-variables.md) - Configuration options

---

**Last Updated**: November 2025
**KATO Version**: 3.0+
