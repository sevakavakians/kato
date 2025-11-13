# Monitoring & Metrics API

Performance monitoring, metrics collection, and operational insights.

## Endpoints

### Concurrency Metrics

Real-time concurrency metrics for load monitoring.

```http
GET /concurrency
```

**Response** (`200 OK`):

```json
{
  "status": "healthy",
  "current": {
    "concurrent_requests": 45,
    "utilization_percent": 4
  },
  "peak": {
    "concurrent_requests": 250,
    "utilization_percent": 25
  },
  "limits": {
    "per_worker": 1000,
    "warning_threshold": 800,
    "critical_threshold": 950,
    "total_capacity": 4000
  },
  "configuration": {
    "workers": 4,
    "backlog": 2048,
    "max_requests": "unlimited"
  },
  "recommendations": [
    {
      "level": "info",
      "message": "Concurrency is healthy. Peak 250/1000 (25%)."
    }
  ],
  "timestamp": "2025-11-13T12:00:00Z"
}
```

**Status Levels**:
- `healthy`: < 80% capacity
- `warning`: 80-95% capacity
- `critical`: > 95% capacity

---

### Cache Statistics

Redis pattern cache performance statistics.

```http
GET /cache/stats
```

**Response** (`200 OK`):

```json
{
  "cache_performance": {
    "hit_rate": 0.85,
    "total_hits": 12345,
    "total_misses": 2000,
    "total_requests": 14345,
    "avg_hit_time_ms": 2.5,
    "avg_miss_time_ms": 15.3
  },
  "cache_health": {
    "status": "healthy",
    "redis_connected": true,
    "memory_usage_mb": 128.5
  },
  "timestamp": "2025-11-13T12:00:00Z"
}
```

---

### Invalidate Cache

Invalidate pattern cache (optionally for specific session).

```http
POST /cache/invalidate?session_id={session_id}
```

**Parameters**:
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `session_id` | string (query) | No | Session ID (if omitted, invalidates all) |

**Response** (`200 OK`):

```json
{
  "status": "success",
  "patterns_invalidated": 1234,
  "symbols_invalidated": 5678,
  "session_id": "session-abc123...",
  "timestamp": "2025-11-13T12:00:00Z"
}
```

---

### Distributed STM Statistics

Get distributed STM performance statistics.

```http
GET /distributed-stm/stats
```

**Response** (`200 OK`):

```json
{
  "status": "active",
  "distributed_stm_enabled": true,
  "performance_stats": {
    "avg_read_latency_ms": 1.2,
    "avg_write_latency_ms": 2.5,
    "total_operations": 10000
  },
  "processor_info": {
    "sample_processor_id": "user_alice",
    "total_active_processors": 5
  },
  "timestamp": "2025-11-13T12:00:00Z"
}
```

---

### Comprehensive Metrics

Get comprehensive system metrics.

```http
GET /metrics
```

**Response** (`200 OK`):

```json
{
  "timestamp": 1699900000.0,
  "sessions": {
    "total_created": 1234,
    "total_deleted": 1192,
    "active": 42,
    "operations_total": 5678
  },
  "performance": {
    "total_requests": 10000,
    "total_errors": 5,
    "error_rate": 0.0005,
    "average_response_time": 25.3
  },
  "resources": {
    "cpu_percent": 45.2,
    "memory_percent": 62.8,
    "disk_percent": 35.1
  },
  "databases": {
    "mongodb": {
      "operations": 5000,
      "errors": 0,
      "avg_response_time": 5.2
    },
    "qdrant": {
      "operations": 3000,
      "errors": 0,
      "avg_response_time": 3.1
    },
    "redis": {
      "operations": 8000,
      "errors": 0,
      "avg_response_time": 1.5
    }
  },
  "processor_manager": {
    "active_processors": 3,
    "patterns_count": 5678
  },
  "uptime_seconds": 3600.5,
  "active_sessions": 42
}
```

---

### Time-Series Statistics

Get time-series statistics for the last N minutes.

```http
GET /stats?minutes=10
```

**Parameters**:
| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `minutes` | integer (query) | 10 | Time window in minutes |

**Response** (`200 OK`):

```json
{
  "time_range_minutes": 10,
  "timestamp": 1699900000.0,
  "time_series": {
    "kato_cpu_usage_percent": [
      {"timestamp": 1699899400.0, "value": 45.2},
      {"timestamp": 1699899460.0, "value": 47.1},
      ...
    ],
    "kato_memory_usage_percent": [...],
    "sessions_created": [...],
    "mongodb_operations": [...]
  },
  "summary": {
    "sessions": {...},
    "performance": {...},
    "resources": {...},
    "databases": {...}
  }
}
```

---

### Specific Metric History

Get time series for a specific metric.

```http
GET /metrics/{metric_name}?minutes=10
```

**Example**:

```bash
curl "http://localhost:8000/metrics/kato_cpu_usage_percent?minutes=30"
```

**Response** (`200 OK`):

```json
{
  "metric_name": "kato_cpu_usage_percent",
  "time_range_minutes": 30,
  "timestamp": 1699900000.0,
  "statistics": {
    "count": 30,
    "min": 35.2,
    "max": 78.5,
    "avg": 52.3
  },
  "data_points": [
    {"timestamp": 1699898200.0, "value": 45.2},
    {"timestamp": 1699898260.0, "value": 47.1},
    ...
  ]
}
```

**Available Metrics**:
- `kato_cpu_usage_percent`
- `kato_memory_usage_percent`
- `kato_memory_usage_bytes`
- `kato_disk_usage_percent`
- `sessions_created`
- `sessions_deleted`
- `mongodb_operations`
- `qdrant_operations`
- `redis_operations`

---

### Connection Pool Status

Get connection pool health and statistics.

```http
GET /connection-pools
```

**Response** (`200 OK`):

```json
{
  "status": "healthy",
  "health": {
    "mongodb": {
      "healthy": true,
      "active_connections": 5,
      "available_connections": 45
    },
    "redis": {
      "healthy": true,
      "active_connections": 2,
      "available_connections": 48
    },
    "qdrant": {
      "healthy": true,
      "active_connections": 1,
      "available_connections": 9
    }
  },
  "pool_statistics": {
    "mongodb": {
      "total_created": 50,
      "total_destroyed": 0,
      "peak_usage": 12
    },
    "redis": {...},
    "qdrant": {...}
  },
  "timestamp": "2025-11-13T12:00:00Z"
}
```

---

## Monitoring Best Practices

### 1. Set Up Alerts

```python
# Example: Alert on high concurrency
response = requests.get("http://localhost:8000/concurrency")
metrics = response.json()

if metrics["current"]["utilization_percent"] > 80:
    send_alert("KATO concurrency > 80%")
```

### 2. Track Cache Performance

```python
response = requests.get("http://localhost:8000/cache/stats")
cache = response.json()["cache_performance"]

# Alert on low hit rate
if cache["hit_rate"] < 0.5:
    send_alert(f"Cache hit rate low: {cache['hit_rate']}")
```

### 3. Monitor Resource Usage

```python
response = requests.get("http://localhost:8000/metrics")
resources = response.json()["resources"]

if resources["memory_percent"] > 90:
    send_alert("High memory usage")
```

### 4. Track Error Rates

```python
response = requests.get("http://localhost:8000/metrics")
perf = response.json()["performance"]

if perf["error_rate"] > 0.01:  # 1% error rate
    send_alert(f"Error rate: {perf['error_rate']}")
```

---

## See Also

- [Health API](health.md) - Basic health checks
- [Monitoring Guide](../../operations/monitoring.md) - Complete monitoring setup
- [Performance Tuning](../../operations/performance-tuning.md)

---

**Last Updated**: November 2025
**KATO Version**: 3.0+
