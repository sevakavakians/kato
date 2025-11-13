# Monitoring and Alerting Guide

Comprehensive guide to monitoring KATO in production with Prometheus, Grafana, logging, and alerting.

## Overview

Production monitoring for KATO includes:
- **Metrics Collection**: Prometheus for time-series metrics
- **Visualization**: Grafana dashboards
- **Logging**: Centralized log aggregation (ELK, Loki, CloudWatch)
- **Alerting**: PagerDuty, Slack, email notifications
- **Distributed Tracing**: Request flow tracking

## Architecture

```
┌─────────────────────────────────────────┐
│            KATO Instances               │
│  - Expose /metrics endpoint             │
│  - JSON structured logs to stdout       │
│  - Trace ID propagation                 │
└──────────────┬──────────────────────────┘
               │
    ┌──────────┴──────────┐
    │                     │
┌───▼─────────┐    ┌──────▼──────┐
│ Prometheus  │    │  Log Agent  │
│  - Scrape   │    │  (Filebeat/ │
│  - Store    │    │   Promtail) │
│  - Alert    │    └──────┬──────┘
└───┬─────────┘           │
    │              ┌──────▼──────────┐
    │              │  Log Aggregator │
    │              │  (Elasticsearch │
    │              │   /Loki)        │
    │              └──────┬──────────┘
    │                     │
┌───▼─────────────────────▼───────┐
│         Grafana                  │
│  - Dashboards                    │
│  - Queries                       │
│  - Visualizations                │
└──────────────┬───────────────────┘
               │
    ┌──────────┴──────────┐
    │                     │
┌───▼────────┐    ┌───────▼────────┐
│ AlertManager│    │ Grafana Alerts │
│ (Prometheus)│    │                │
└───┬────────┘    └───┬────────────┘
    │                 │
    └────────┬────────┘
             │
    ┌────────▼─────────────┐
    │  Notification        │
    │  - PagerDuty         │
    │  - Slack             │
    │  - Email             │
    └──────────────────────┘
```

## Prometheus Setup

### Install Prometheus

**Docker Compose**:
```yaml
# docker-compose.yml
version: '3.8'

services:
  prometheus:
    image: prom/prometheus:latest
    container_name: prometheus
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - prometheus-data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--storage.tsdb.retention.time=30d'
    networks:
      - kato-network
    restart: unless-stopped

volumes:
  prometheus-data:
```

**Kubernetes**:
```bash
# Install with Helm
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

helm install prometheus prometheus-community/prometheus \
  --namespace monitoring \
  --create-namespace \
  --set server.persistentVolume.size=50Gi \
  --set server.retention=30d
```

### Prometheus Configuration

**prometheus.yml**:
```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s
  external_labels:
    cluster: 'kato-production'
    environment: 'production'

# Alerting configuration
alerting:
  alertmanagers:
    - static_configs:
        - targets:
            - 'alertmanager:9093'

# Load alert rules
rule_files:
  - '/etc/prometheus/alerts/*.yml'

# Scrape configurations
scrape_configs:
  # KATO API metrics
  - job_name: 'kato'
    static_configs:
      - targets:
          - 'kato-1:8000'
          - 'kato-2:8000'
          - 'kato-3:8000'
    metrics_path: '/metrics'
    scrape_interval: 10s

  # MongoDB exporter
  - job_name: 'mongodb'
    static_configs:
      - targets:
          - 'mongodb-exporter:9216'

  # Redis exporter
  - job_name: 'redis'
    static_configs:
      - targets:
          - 'redis-exporter:9121'

  # Node exporter (system metrics)
  - job_name: 'node'
    static_configs:
      - targets:
          - 'node-exporter:9100'

  # Kubernetes service discovery (if using K8s)
  - job_name: 'kubernetes-pods'
    kubernetes_sd_configs:
      - role: pod
    relabel_configs:
      - source_labels: [__meta_kubernetes_pod_annotation_prometheus_io_scrape]
        action: keep
        regex: true
      - source_labels: [__meta_kubernetes_pod_annotation_prometheus_io_path]
        action: replace
        target_label: __metrics_path__
        regex: (.+)
      - source_labels: [__address__, __meta_kubernetes_pod_annotation_prometheus_io_port]
        action: replace
        regex: ([^:]+)(?::\d+)?;(\d+)
        replacement: $1:$2
        target_label: __address__
```

### KATO Metrics Endpoint

**Add Prometheus metrics** (`kato/api/main.py`):
```python
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from fastapi import Response

# Define metrics
request_count = Counter(
    'kato_requests_total',
    'Total number of requests',
    ['method', 'endpoint', 'status']
)

request_duration = Histogram(
    'kato_request_duration_seconds',
    'Request duration in seconds',
    ['method', 'endpoint']
)

observation_count = Counter(
    'kato_observations_total',
    'Total number of observations processed',
    ['processor_id']
)

prediction_count = Counter(
    'kato_predictions_total',
    'Total number of predictions generated',
    ['processor_id']
)

pattern_count = Gauge(
    'kato_patterns_stored',
    'Number of patterns stored in LTM',
    ['processor_id']
)

stm_size = Gauge(
    'kato_stm_size',
    'Current short-term memory size',
    ['processor_id', 'session_id']
)

# Metrics endpoint
@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST
    )
```

**Instrument endpoints**:
```python
@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    """Track request metrics."""
    start_time = time.time()

    response = await call_next(request)

    duration = time.time() - start_time
    request_count.labels(
        method=request.method,
        endpoint=request.url.path,
        status=response.status_code
    ).inc()

    request_duration.labels(
        method=request.method,
        endpoint=request.url.path
    ).observe(duration)

    return response
```

### Database Exporters

**MongoDB Exporter**:
```yaml
# docker-compose.yml
services:
  mongodb-exporter:
    image: percona/mongodb_exporter:latest
    container_name: mongodb-exporter
    ports:
      - "9216:9216"
    environment:
      MONGODB_URI: mongodb://mongo-kb:27017
    command:
      - '--collect-all'
      - '--mongodb.direct-connect=true'
    networks:
      - kato-network
```

**Redis Exporter**:
```yaml
services:
  redis-exporter:
    image: oliver006/redis_exporter:latest
    container_name: redis-exporter
    ports:
      - "9121:9121"
    environment:
      REDIS_ADDR: redis://redis-kb:6379
    networks:
      - kato-network
```

## Grafana Setup

### Install Grafana

**Docker Compose**:
```yaml
services:
  grafana:
    image: grafana/grafana:latest
    container_name: grafana
    ports:
      - "3000:3000"
    environment:
      GF_SECURITY_ADMIN_USER: admin
      GF_SECURITY_ADMIN_PASSWORD: secure_password_here
      GF_INSTALL_PLUGINS: grafana-piechart-panel
    volumes:
      - grafana-data:/var/lib/grafana
      - ./grafana/dashboards:/etc/grafana/provisioning/dashboards:ro
      - ./grafana/datasources:/etc/grafana/provisioning/datasources:ro
    networks:
      - kato-network
    restart: unless-stopped

volumes:
  grafana-data:
```

**Kubernetes**:
```bash
helm install grafana grafana/grafana \
  --namespace monitoring \
  --set persistence.enabled=true \
  --set persistence.size=10Gi \
  --set adminPassword=secure_password_here
```

### Configure Datasources

**grafana/datasources/prometheus.yml**:
```yaml
apiVersion: 1

datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
    editable: false

  - name: Loki
    type: loki
    access: proxy
    url: http://loki:3100
    editable: false
```

### KATO Dashboard

**grafana/dashboards/kato-overview.json**:
```json
{
  "dashboard": {
    "title": "KATO Overview",
    "panels": [
      {
        "title": "Request Rate",
        "targets": [
          {
            "expr": "rate(kato_requests_total[5m])"
          }
        ],
        "type": "graph"
      },
      {
        "title": "Request Duration (p95)",
        "targets": [
          {
            "expr": "histogram_quantile(0.95, rate(kato_request_duration_seconds_bucket[5m]))"
          }
        ],
        "type": "graph"
      },
      {
        "title": "Active Sessions",
        "targets": [
          {
            "expr": "sum(kato_stm_size) by (processor_id)"
          }
        ],
        "type": "stat"
      },
      {
        "title": "Patterns Stored",
        "targets": [
          {
            "expr": "kato_patterns_stored"
          }
        ],
        "type": "stat"
      }
    ]
  }
}
```

**Import via API**:
```bash
curl -X POST http://localhost:3000/api/dashboards/db \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d @kato-overview.json
```

### Key Metrics to Monitor

#### Application Metrics
- **Request rate**: `rate(kato_requests_total[5m])`
- **Error rate**: `rate(kato_requests_total{status=~"5.."}[5m])`
- **Request duration (p50)**: `histogram_quantile(0.50, rate(kato_request_duration_seconds_bucket[5m]))`
- **Request duration (p95)**: `histogram_quantile(0.95, rate(kato_request_duration_seconds_bucket[5m]))`
- **Request duration (p99)**: `histogram_quantile(0.99, rate(kato_request_duration_seconds_bucket[5m]))`
- **Observation rate**: `rate(kato_observations_total[5m])`
- **Prediction rate**: `rate(kato_predictions_total[5m])`

#### System Metrics
- **CPU usage**: `rate(process_cpu_seconds_total[1m]) * 100`
- **Memory usage**: `process_resident_memory_bytes`
- **Open file descriptors**: `process_open_fds`
- **Goroutines/Threads**: `process_threads_total`

#### Database Metrics
- **MongoDB connections**: `mongodb_connections{state="current"}`
- **MongoDB operations**: `rate(mongodb_op_counters_total[1m])`
- **Redis memory**: `redis_memory_used_bytes`
- **Redis commands**: `rate(redis_commands_processed_total[1m])`

## Logging

### Centralized Logging with Loki

**Docker Compose**:
```yaml
services:
  loki:
    image: grafana/loki:latest
    container_name: loki
    ports:
      - "3100:3100"
    volumes:
      - ./loki-config.yaml:/etc/loki/local-config.yaml:ro
      - loki-data:/loki
    command: -config.file=/etc/loki/local-config.yaml
    networks:
      - kato-network

  promtail:
    image: grafana/promtail:latest
    container_name: promtail
    volumes:
      - /var/log:/var/log:ro
      - /var/lib/docker/containers:/var/lib/docker/containers:ro
      - ./promtail-config.yaml:/etc/promtail/config.yaml:ro
    command: -config.file=/etc/promtail/config.yaml
    networks:
      - kato-network

volumes:
  loki-data:
```

**loki-config.yaml**:
```yaml
auth_enabled: false

server:
  http_listen_port: 3100

ingester:
  lifecycler:
    ring:
      kvstore:
        store: inmemory
      replication_factor: 1
  chunk_idle_period: 5m
  chunk_retain_period: 30s

schema_config:
  configs:
    - from: 2020-10-24
      store: boltdb
      object_store: filesystem
      schema: v11
      index:
        prefix: index_
        period: 168h

storage_config:
  boltdb:
    directory: /loki/index
  filesystem:
    directory: /loki/chunks

limits_config:
  enforce_metric_name: false
  reject_old_samples: true
  reject_old_samples_max_age: 168h

chunk_store_config:
  max_look_back_period: 0s

table_manager:
  retention_deletes_enabled: true
  retention_period: 720h  # 30 days
```

**promtail-config.yaml**:
```yaml
server:
  http_listen_port: 9080

positions:
  filename: /tmp/positions.yaml

clients:
  - url: http://loki:3100/loki/api/v1/push

scrape_configs:
  # Docker container logs
  - job_name: docker
    docker_sd_configs:
      - host: unix:///var/run/docker.sock
        refresh_interval: 5s
    relabel_configs:
      - source_labels: ['__meta_docker_container_name']
        regex: '/(.*)'
        target_label: 'container'
      - source_labels: ['__meta_docker_container_log_stream']
        target_label: 'stream'
```

### ELK Stack (Elasticsearch, Logstash, Kibana)

**Docker Compose**:
```yaml
services:
  elasticsearch:
    image: docker.elastic.co/elasticsearch/elasticsearch:8.10.0
    environment:
      - discovery.type=single-node
      - "ES_JAVA_OPTS=-Xms2g -Xmx2g"
      - xpack.security.enabled=false
    ports:
      - "9200:9200"
    volumes:
      - elasticsearch-data:/usr/share/elasticsearch/data

  logstash:
    image: docker.elastic.co/logstash/logstash:8.10.0
    volumes:
      - ./logstash.conf:/usr/share/logstash/pipeline/logstash.conf:ro
    ports:
      - "5044:5044"
    depends_on:
      - elasticsearch

  kibana:
    image: docker.elastic.co/kibana/kibana:8.10.0
    ports:
      - "5601:5601"
    environment:
      - ELASTICSEARCH_HOSTS=http://elasticsearch:9200
    depends_on:
      - elasticsearch

  filebeat:
    image: docker.elastic.co/beats/filebeat:8.10.0
    user: root
    volumes:
      - ./filebeat.yml:/usr/share/filebeat/filebeat.yml:ro
      - /var/lib/docker/containers:/var/lib/docker/containers:ro
      - /var/run/docker.sock:/var/run/docker.sock:ro
    depends_on:
      - logstash
```

**logstash.conf**:
```
input {
  beats {
    port => 5044
  }
}

filter {
  # Parse JSON logs from KATO
  if [container][name] =~ "kato" {
    json {
      source => "message"
      target => "kato"
    }

    # Extract fields
    mutate {
      add_field => {
        "trace_id" => "%{[kato][trace_id]}"
        "level" => "%{[kato][level]}"
        "service" => "%{[kato][service]}"
      }
    }
  }
}

output {
  elasticsearch {
    hosts => ["elasticsearch:9200"]
    index => "kato-%{+YYYY.MM.dd}"
  }
}
```

### Query Logs

**Loki with Grafana**:
```
{container="kato"} |= "ERROR"
{container="kato"} | json | level="ERROR"
{container="kato"} | json | trace_id="abc123"
```

**Elasticsearch with Kibana**:
```
container.name: kato AND level: ERROR
trace_id: "abc123"
level: ERROR AND NOT status_code: [200 TO 299]
```

## Alerting

### Prometheus AlertManager

**Install AlertManager**:
```yaml
services:
  alertmanager:
    image: prom/alertmanager:latest
    ports:
      - "9093:9093"
    volumes:
      - ./alertmanager.yml:/etc/alertmanager/alertmanager.yml:ro
    command:
      - '--config.file=/etc/alertmanager/alertmanager.yml'
    networks:
      - kato-network
```

**alertmanager.yml**:
```yaml
global:
  resolve_timeout: 5m
  slack_api_url: 'https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK'

route:
  group_by: ['alertname', 'cluster', 'service']
  group_wait: 10s
  group_interval: 10s
  repeat_interval: 12h
  receiver: 'default'
  routes:
    - match:
        severity: critical
      receiver: 'pagerduty'
    - match:
        severity: warning
      receiver: 'slack'

receivers:
  - name: 'default'
    email_configs:
      - to: 'alerts@yourdomain.com'
        from: 'alertmanager@yourdomain.com'
        smarthost: smtp.gmail.com:587
        auth_username: 'your-email@gmail.com'
        auth_password: 'your-app-password'

  - name: 'slack'
    slack_configs:
      - channel: '#kato-alerts'
        title: 'KATO Alert'
        text: '{{ range .Alerts }}{{ .Annotations.description }}{{ end }}'

  - name: 'pagerduty'
    pagerduty_configs:
      - service_key: 'YOUR_PAGERDUTY_SERVICE_KEY'
```

### Alert Rules

**alerts/kato-alerts.yml**:
```yaml
groups:
  - name: kato_alerts
    interval: 30s
    rules:
      # High error rate
      - alert: HighErrorRate
        expr: rate(kato_requests_total{status=~"5.."}[5m]) > 0.05
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "High error rate detected"
          description: "Error rate is {{ $value }} (threshold: 0.05)"

      # High latency
      - alert: HighLatency
        expr: histogram_quantile(0.95, rate(kato_request_duration_seconds_bucket[5m])) > 1.0
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High request latency detected"
          description: "P95 latency is {{ $value }}s (threshold: 1.0s)"

      # Service down
      - alert: ServiceDown
        expr: up{job="kato"} == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "KATO service is down"
          description: "{{ $labels.instance }} has been down for more than 1 minute"

      # High memory usage
      - alert: HighMemoryUsage
        expr: process_resident_memory_bytes{job="kato"} > 4e9
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "High memory usage"
          description: "Memory usage is {{ $value | humanize }}B (threshold: 4GB)"

      # MongoDB connection issues
      - alert: MongoDBConnectionPoolExhausted
        expr: mongodb_connections{state="current"} > mongodb_connections{state="available"} * 0.9
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "MongoDB connection pool near exhaustion"
          description: "Current: {{ $value }}, Available: {{ .available }}"

      # Redis memory
      - alert: RedisHighMemory
        expr: redis_memory_used_bytes > 1e9
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Redis memory usage is high"
          description: "Redis using {{ $value | humanize }}B (threshold: 1GB)"

      # Disk space
      - alert: LowDiskSpace
        expr: node_filesystem_avail_bytes{mountpoint="/"} / node_filesystem_size_bytes{mountpoint="/"} < 0.1
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Low disk space"
          description: "Only {{ $value | humanizePercentage }} disk space remaining"
```

## Distributed Tracing

### OpenTelemetry Integration

**Install dependencies**:
```bash
pip install opentelemetry-api opentelemetry-sdk opentelemetry-instrumentation-fastapi
```

**Configure tracing** (`kato/api/main.py`):
```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

# Configure tracer
trace.set_tracer_provider(TracerProvider())
tracer = trace.get_tracer(__name__)

# Configure Jaeger exporter
jaeger_exporter = JaegerExporter(
    agent_host_name="jaeger",
    agent_port=6831,
)
trace.get_tracer_provider().add_span_processor(
    BatchSpanProcessor(jaeger_exporter)
)

# Instrument FastAPI
FastAPIInstrumentor.instrument_app(app)
```

**Jaeger deployment**:
```yaml
services:
  jaeger:
    image: jaegertracing/all-in-one:latest
    ports:
      - "16686:16686"  # UI
      - "6831:6831/udp"  # Agent
    environment:
      - COLLECTOR_ZIPKIN_HOST_PORT=:9411
    networks:
      - kato-network
```

## Health Checks

**Comprehensive health endpoint** (`kato/api/endpoints/health.py`):
```python
@app.get("/health")
async def health_check():
    """Comprehensive health check."""
    health_status = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "checks": {}
    }

    # Check MongoDB
    try:
        await kb.client.admin.command('ping')
        health_status["checks"]["mongodb"] = "healthy"
    except Exception as e:
        health_status["checks"]["mongodb"] = f"unhealthy: {str(e)}"
        health_status["status"] = "unhealthy"

    # Check Qdrant
    try:
        response = await qdrant_client.get_collections()
        health_status["checks"]["qdrant"] = "healthy"
    except Exception as e:
        health_status["checks"]["qdrant"] = f"unhealthy: {str(e)}"
        health_status["status"] = "unhealthy"

    # Check Redis
    try:
        await redis.ping()
        health_status["checks"]["redis"] = "healthy"
    except Exception as e:
        health_status["checks"]["redis"] = f"unhealthy: {str(e)}"
        health_status["status"] = "unhealthy"

    # Return appropriate status code
    status_code = 200 if health_status["status"] == "healthy" else 503
    return JSONResponse(content=health_status, status_code=status_code)
```

## Monitoring Checklist

### Infrastructure
- [ ] Prometheus scraping all services
- [ ] Grafana dashboards configured
- [ ] AlertManager rules defined
- [ ] Log aggregation working
- [ ] Distributed tracing enabled

### Metrics
- [ ] Request rate tracked
- [ ] Error rate tracked
- [ ] Latency percentiles tracked (p50, p95, p99)
- [ ] Database metrics collected
- [ ] System metrics collected

### Alerting
- [ ] Critical alerts configured (service down, high error rate)
- [ ] Warning alerts configured (high latency, high memory)
- [ ] Alert routing configured (PagerDuty, Slack, email)
- [ ] On-call rotation defined
- [ ] Runbooks linked to alerts

### Dashboards
- [ ] Overview dashboard
- [ ] Application metrics dashboard
- [ ] Database metrics dashboard
- [ ] System metrics dashboard
- [ ] SLA compliance dashboard

## Related Documentation

- [Performance Tuning](performance-tuning.md)
- [Security Configuration](security-configuration.md)
- [Scaling](scaling.md)
- [Production Checklist](production-checklist.md)

---

**Last Updated**: November 2025
**KATO Version**: 3.0+
