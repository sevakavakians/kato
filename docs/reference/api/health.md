# Health & Status API

System health checks and status monitoring endpoints.

## Endpoints

### Health Check

Enhanced health check with metrics integration.

```http
GET /health
```

**Response** (`200 OK`):

```json
{
  "status": "healthy",
  "processor_status": "healthy",
  "service_name": "kato",
  "uptime_seconds": 3600.5,
  "issues": [],
  "metrics_collected": 1234,
  "last_collection": 1699900000.0,
  "active_sessions": 42,
  "timestamp": "2025-11-13T12:00:00Z"
}
```

**Status Values**:
- `healthy`: All systems operational
- `degraded`: Some issues detected
- `unhealthy`: Critical issues present

**Example**:

```bash
curl http://localhost:8000/health
```

**Use Cases**:
- Load balancer health checks
- Monitoring system integration
- Kubernetes liveness/readiness probes

---

### System Status

Detailed system status with session and processor statistics.

```http
GET /status
```

**Response** (`200 OK`):

```json
{
  "status": "healthy",
  "base_processor_id": "kato_primary",
  "uptime_seconds": 3600.5,
  "sessions": {
    "active": 42,
    "total_created": 1234,
    "total_deleted": 1192
  },
  "processors": {
    "active_processors": 3,
    "patterns_count": 5678
  },
  "version": "1.0.0"
}
```

**Example**:

```bash
curl http://localhost:8000/status
```

---

## Kubernetes Integration

### Liveness Probe

```yaml
livenessProbe:
  httpGet:
    path: /health
    port: 8000
  initialDelaySeconds: 30
  periodSeconds: 10
```

### Readiness Probe

```yaml
readinessProbe:
  httpGet:
    path: /health
    port: 8000
  initialDelaySeconds: 5
  periodSeconds: 5
```

---

## Monitoring Integration

### Prometheus

```python
import requests

response = requests.get("http://localhost:8000/health")
health = response.json()

# Expose as Prometheus metrics
kato_up = 1 if health["status"] == "healthy" else 0
kato_uptime_seconds = health["uptime_seconds"]
kato_active_sessions = health["active_sessions"]
```

### Datadog

```python
from datadog import statsd

response = requests.get("http://localhost:8000/health")
health = response.json()

statsd.gauge('kato.uptime', health["uptime_seconds"])
statsd.gauge('kato.active_sessions', health["active_sessions"])
statsd.gauge('kato.metrics_collected', health["metrics_collected"])
```

---

## See Also

- [Monitoring API](monitoring.md) - Detailed metrics and performance data
- [Configuration Guide](../../operations/configuration.md)
- [Monitoring Guide](../../operations/monitoring.md)

---

**Last Updated**: November 2025
**KATO Version**: 3.0+
