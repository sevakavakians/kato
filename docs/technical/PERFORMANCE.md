# KATO Performance Guide

Comprehensive guide to KATO's performance characteristics, optimization strategies, and benchmarks.

## Performance Characteristics

### Latency Metrics

| Operation | Typical Latency | Optimized | Notes |
|-----------|----------------|-----------|-------|
| Observation | 1-5ms | <1ms | Depends on event size |
| Prediction | 5-20ms | 2-10ms | Scales with model count |
| Learning | 10-100ms | 5-50ms | Depends on sequence length |
| Memory Clear | <1ms | <0.5ms | Short-term memory only |
| API Round-trip | 5-10ms | 2-5ms | Including network overhead |

### Throughput Metrics

| Metric | Standard | Optimized | Maximum |
|--------|----------|-----------|---------|
| Requests/sec | 1,000 | 5,000 | 10,000+ |
| Observations/sec | 500 | 2,000 | 5,000 |
| Predictions/sec | 200 | 1,000 | 2,500 |
| Learning ops/sec | 50 | 200 | 500 |

### Resource Usage

| Resource | Idle | Normal Load | Peak Load |
|----------|------|-------------|-----------|
| Memory | 200MB | 500MB-1GB | 2GB+ |
| CPU | <5% | 20-40% | 80-100% |
| Network | <1Mbps | 10-50Mbps | 100Mbps+ |
| Disk I/O | Minimal | 10MB/s | 50MB/s |

## ZeroMQ Performance

### Connection Pool Benefits

```
Without Pool:
- Connection setup: 5-10ms per request
- Total latency: 10-20ms
- Max throughput: 100 req/s

With Pool:
- Connection reuse: 0ms overhead
- Total latency: 0.5-2ms
- Max throughput: 10,000+ req/s
```

### MessagePack Advantages

```
JSON Serialization:
- Size: 100%
- Encode time: 1.0ms
- Decode time: 0.8ms

MessagePack:
- Size: 60-70%
- Encode time: 0.5ms
- Decode time: 0.4ms
```

## Optimization Strategies

### 1. Configuration Optimization

#### For Speed
```bash
./kato-manager.sh start \
  --indexer-type VI \
  --max-predictions 20 \
  --recall-threshold 0.3 \
  --max-seq-length 100
```

#### For Accuracy
```bash
./kato-manager.sh start \
  --indexer-type VI \
  --max-predictions 500 \
  --recall-threshold 0.01 \
  --update-frequencies
```

#### For Memory Efficiency
```bash
./kato-manager.sh start \
  --max-predictions 50 \
  --max-seq-length 50 \
  --persistence 3
```

### 2. Batch Operations

```python
# Inefficient: Individual requests
for observation in observations:
    kato.observe(observation)

# Efficient: Batch processing
def batch_observe(observations, batch_size=100):
    for i in range(0, len(observations), batch_size):
        batch = observations[i:i+batch_size]
        for obs in batch:
            kato.observe(obs)
        # Process predictions after batch
        predictions = kato.get_predictions()
```

### 3. Connection Reuse

```python
# Bad: New connection per request
def make_request(data):
    response = requests.post(url, json=data)
    return response.json()

# Good: Session reuse
session = requests.Session()
def make_request(data):
    response = session.post(url, json=data)
    return response.json()
```

### 4. Async Processing

```python
import asyncio
import aiohttp

async def async_observe(session, url, data):
    async with session.post(url, json=data) as response:
        return await response.json()

async def batch_async_observe(observations):
    async with aiohttp.ClientSession() as session:
        tasks = [async_observe(session, url, obs) for obs in observations]
        return await asyncio.gather(*tasks)
```

## Benchmarking

### Performance Test Script

```python
import time
import requests
from statistics import mean, stdev

def benchmark_operation(operation, iterations=100):
    """Benchmark a KATO operation"""
    times = []
    
    for _ in range(iterations):
        start = time.perf_counter()
        operation()
        end = time.perf_counter()
        times.append((end - start) * 1000)  # Convert to ms
    
    return {
        'mean': mean(times),
        'stdev': stdev(times),
        'min': min(times),
        'max': max(times),
        'throughput': 1000 / mean(times)  # ops/sec
    }

# Example benchmarks
def observe_benchmark():
    return requests.post(f"{BASE_URL}/observe", 
                         json={"strings": ["test"], "vectors": [], "emotives": {}})

def prediction_benchmark():
    return requests.get(f"{BASE_URL}/predictions")

# Run benchmarks
observe_stats = benchmark_operation(observe_benchmark)
prediction_stats = benchmark_operation(prediction_benchmark)

print(f"Observation: {observe_stats['mean']:.2f}ms ± {observe_stats['stdev']:.2f}ms")
print(f"Prediction: {prediction_stats['mean']:.2f}ms ± {prediction_stats['stdev']:.2f}ms")
```

### Load Testing

```bash
# Using Apache Bench
ab -n 1000 -c 10 -p observation.json -T application/json \
   http://localhost:8000/p46b6b076c/observe

# Using wrk
wrk -t4 -c100 -d30s --script=kato_load.lua \
    http://localhost:8000/p46b6b076c/observe
```

## Memory Optimization

### Memory Profiling

```python
import tracemalloc
import gc

# Start tracing
tracemalloc.start()

# Your KATO operations
kato.observe(...)
kato.learn()

# Get memory usage
current, peak = tracemalloc.get_traced_memory()
print(f"Current memory: {current / 1024 / 1024:.2f} MB")
print(f"Peak memory: {peak / 1024 / 1024:.2f} MB")

# Stop tracing
tracemalloc.stop()

# Force garbage collection
gc.collect()
```

### Memory Management Tips

1. **Clear Short-Term Memory Regularly**
```python
# After learning
kato.learn()
kato.clear_short_term_memory()
```

2. **Limit Model Count**
```python
# Periodically clean old models
if model_count > MAX_MODELS:
    cleanup_old_models()
```

3. **Optimize Data Structures**
```python
# Use numpy arrays for vectors
vectors = np.array(vectors, dtype=np.float32)  # Use float32 instead of float64
```

## CPU Optimization

### Profiling CPU Usage

```python
import cProfile
import pstats
from pstats import SortKey

profiler = cProfile.Profile()
profiler.enable()

# KATO operations
for _ in range(100):
    kato.observe({"strings": ["test"]})
    kato.get_predictions()

profiler.disable()
stats = pstats.Stats(profiler)
stats.sort_stats(SortKey.CUMULATIVE)
stats.print_stats(10)
```

### CPU Optimization Strategies

1. **Use VI Indexer (Optimized)**
   - High performance vector indexing
   - Efficient CPU usage
   - Suitable for all use cases

2. **Limit Max Predictions**
```bash
--max-predictions 50  # Reduce from default 100
```

3. **Increase Recall Threshold**
```bash
--recall-threshold 0.5  # Filter more aggressively
```

## Network Optimization

### Compression

```python
import gzip
import json

def compress_request(data):
    """Compress JSON data for transmission"""
    json_str = json.dumps(data)
    compressed = gzip.compress(json_str.encode())
    return compressed

def decompress_response(compressed_data):
    """Decompress response data"""
    decompressed = gzip.decompress(compressed_data)
    return json.loads(decompressed.decode())
```

### Keep-Alive Connections

```python
# Enable keep-alive
session = requests.Session()
session.headers.update({'Connection': 'keep-alive'})
adapter = requests.adapters.HTTPAdapter(
    pool_connections=10,
    pool_maxsize=100,
    max_retries=3
)
session.mount('http://', adapter)
```

## Database Optimization

### MongoDB Indexes

```javascript
// Create indexes for faster queries
db.models.createIndex({"processor_id": 1, "name": 1})
db.models.createIndex({"frequency": -1})
db.models.createIndex({"created_at": -1})
```

### Connection Pooling

```python
# MongoDB connection pool
from pymongo import MongoClient

client = MongoClient(
    'mongodb://localhost:27017/',
    maxPoolSize=50,
    minPoolSize=10,
    maxIdleTimeMS=30000
)
```

## Docker Optimization

### Resource Limits

```yaml
# docker-compose.yml
services:
  kato:
    mem_limit: 2g
    memswap_limit: 2g
    cpus: '2.0'
    cpu_shares: 1024
```

### Multi-Stage Build

```dockerfile
# Smaller image size
FROM python:3.9-slim as builder
# Build dependencies
RUN pip install --user -r requirements.txt

FROM python:3.9-slim
# Copy only runtime dependencies
COPY --from=builder /root/.local /root/.local
```

## Monitoring Performance

### Metrics Collection

```python
import time
from collections import deque

class PerformanceMonitor:
    def __init__(self, window_size=100):
        self.latencies = deque(maxlen=window_size)
        self.throughput = deque(maxlen=window_size)
        
    def record_operation(self, duration):
        self.latencies.append(duration)
        self.throughput.append(1.0 / duration if duration > 0 else 0)
    
    def get_stats(self):
        return {
            'avg_latency': mean(self.latencies),
            'p95_latency': sorted(self.latencies)[int(len(self.latencies) * 0.95)],
            'throughput': sum(self.throughput)
        }
```

### Real-time Monitoring

```bash
# Monitor Docker stats
docker stats kato-api --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}"

# Monitor network traffic
netstat -i 1  # Update every second

# Monitor disk I/O
iostat -x 1
```

## recall_threshold Performance Impact

The `recall_threshold` parameter significantly affects KATO's performance characteristics:

### Processing Time vs Threshold

| Threshold | Candidates Processed | Processing Time | Memory Usage |
|-----------|---------------------|-----------------|--------------|
| 0.0-0.1 | 100% (all models) | Highest | Maximum |
| 0.2-0.3 | 60-80% | High | High |
| 0.4-0.5 | 30-50% | Moderate | Moderate |
| 0.6-0.7 | 10-25% | Low | Low |
| 0.8-1.0 | 1-10% | Minimal | Minimal |

### Performance Characteristics

#### Low Thresholds (0.0-0.3)
- **CPU Impact**: High - processes many candidates
- **Memory Impact**: High - stores many predictions
- **Network Impact**: High - larger response payloads
- **Latency**: 100-500ms typical for moderate datasets
- **Use When**: Pattern discovery is priority over speed

#### Medium Thresholds (0.3-0.6)
- **CPU Impact**: Moderate - balanced processing
- **Memory Impact**: Moderate - reasonable prediction count
- **Network Impact**: Moderate - manageable payloads
- **Latency**: 50-200ms typical
- **Use When**: Production systems with known patterns

#### High Thresholds (0.6-1.0)
- **CPU Impact**: Low - few candidates processed
- **Memory Impact**: Low - minimal predictions stored
- **Network Impact**: Low - small response payloads
- **Latency**: 10-100ms typical
- **Use When**: Speed is critical, exact matches needed

### Optimization Strategies

1. **Dynamic Threshold Adjustment**
   ```python
   # Start with higher threshold for speed
   initial_threshold = 0.5
   
   # If too few predictions, gradually decrease
   if prediction_count < min_required:
       new_threshold = max(0.1, current_threshold - 0.1)
   ```

2. **Sequence Length Adaptive Thresholds**
   - Short sequences (2-5): Use 0.4-0.6
   - Medium sequences (5-15): Use 0.3-0.5
   - Long sequences (15+): Use 0.1-0.3

3. **Load-Based Tuning**
   - High load: Increase threshold to 0.5+
   - Low load: Decrease to 0.2-0.3 for better recall

### Benchmarks

Testing with 10,000 learned models, observing 10-element sequence:

| Threshold | Predictions Generated | Time (ms) | Memory (MB) |
|-----------|----------------------|-----------|-------------|
| 0.1 | 847 | 412 | 23.4 |
| 0.3 | 234 | 156 | 8.7 |
| 0.5 | 67 | 73 | 3.2 |
| 0.7 | 12 | 31 | 0.8 |
| 0.9 | 2 | 18 | 0.2 |

## Performance Tuning Checklist

### Initial Setup
- [ ] Configure VI indexer for vector processing
- [ ] Set reasonable max_predictions limit
- [ ] Configure appropriate recall_threshold (see Performance Impact section)
- [ ] Set max_sequence_length if needed

### Runtime Optimization
- [ ] Use connection pooling
- [ ] Implement batch processing
- [ ] Enable keep-alive connections
- [ ] Clear short-term memory regularly

### Monitoring
- [ ] Track response times
- [ ] Monitor memory usage
- [ ] Watch CPU utilization
- [ ] Check network bandwidth

### Scaling
- [ ] Add more KATO instances
- [ ] Implement load balancing
- [ ] Use caching where appropriate
- [ ] Consider horizontal scaling

## Troubleshooting Performance Issues

### High Latency
1. Check network connectivity
2. Verify connection pool is working
3. Reduce max_predictions
4. Check for memory pressure

### High Memory Usage
1. Clear short-term memory more frequently
2. Reduce max_sequence_length
3. Limit model count
4. Check for memory leaks

### High CPU Usage
1. Use VI indexer (optimized)
2. Lower max_predictions
3. Increase recall_threshold
4. Check for infinite loops

## Performance Targets

### SLA Guidelines

| Service Level | Response Time | Availability |
|---------------|---------------|--------------|
| Critical | <10ms | 99.99% |
| Standard | <50ms | 99.9% |
| Batch | <200ms | 99% |

### Capacity Planning

| Users | KATO Instances | Memory | CPU Cores |
|-------|----------------|--------|-----------|
| 100 | 1 | 2GB | 2 |
| 1,000 | 2-3 | 4GB | 4 |
| 10,000 | 5-10 | 8GB | 8 |
| 100,000 | 20-50 | 32GB | 32 |

## Related Documentation

- [Architecture](../deployment/ARCHITECTURE.md) - System design
- [Configuration](../deployment/CONFIGURATION.md) - Performance parameters
- [Troubleshooting](TROUBLESHOOTING.md) - Performance issues
- [ZeroMQ Architecture](ZEROMQ_ARCHITECTURE.md) - Protocol performance