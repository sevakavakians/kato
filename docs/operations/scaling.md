# Scaling Guide

Comprehensive guide to scaling KATO for production workloads with horizontal and vertical scaling strategies.

## Overview

KATO supports multiple scaling approaches:
- **Horizontal Scaling**: Add more KATO instances
- **Vertical Scaling**: Increase resources per instance
- **Database Scaling**: Scale ClickHouse, Qdrant, Redis
- **Auto-Scaling**: Dynamic scaling based on load

## Scaling Architecture

```
                    ┌─────────────────┐
                    │  Load Balancer  │
                    │  (Nginx/K8s)    │
                    └────────┬────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
  ┌─────▼─────┐       ┌──────▼──────┐     ┌──────▼──────┐
  │  KATO-1   │       │   KATO-2    │     │   KATO-3    │
  │ (Primary) │       │  (Worker)   │     │  (Worker)   │
  └─────┬─────┘       └──────┬──────┘     └──────┬──────┘
        │                    │                    │
        └────────────────────┼────────────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
  ┌─────▼─────┐       ┌──────▼──────┐     ┌──────▼──────┐
  │ ClickHouse│       │   Qdrant    │     │   Redis     │
  │  Cluster  │       │   Cluster   │     │  Sentinel   │
  └───────────┘       └─────────────┘     └─────────────┘
```

## Horizontal Scaling

### Docker Compose Multi-Instance

**docker compose.yml**:
```yaml
version: '3.8'

services:
  # Load Balancer
  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
      - ./certs:/etc/nginx/certs:ro
    depends_on:
      - kato-1
      - kato-2
      - kato-3
    networks:
      - kato-network

  # KATO Instances
  kato-1:
    image: ghcr.io/your-org/kato:latest
    container_name: kato-1
    environment:
      - PROCESSOR_ID=kato-1
      - CLICKHOUSE_HOST=kato-clickhouse
      - CLICKHOUSE_PORT=8123
      - CLICKHOUSE_DB=kato
      - QDRANT_HOST=qdrant-kb
      - REDIS_URL=redis://redis-kb:6379/0
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 4G
        reservations:
          cpus: '1.0'
          memory: 2G
    networks:
      - kato-network

  kato-2:
    image: ghcr.io/your-org/kato:latest
    container_name: kato-2
    environment:
      - PROCESSOR_ID=kato-2
      - CLICKHOUSE_HOST=kato-clickhouse
      - CLICKHOUSE_PORT=8123
      - CLICKHOUSE_DB=kato
      - QDRANT_HOST=qdrant-kb
      - REDIS_URL=redis://redis-kb:6379/0
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 4G
        reservations:
          cpus: '1.0'
          memory: 2G
    networks:
      - kato-network

  kato-3:
    image: ghcr.io/your-org/kato:latest
    container_name: kato-3
    environment:
      - PROCESSOR_ID=kato-3
      - CLICKHOUSE_HOST=kato-clickhouse
      - CLICKHOUSE_PORT=8123
      - CLICKHOUSE_DB=kato
      - QDRANT_HOST=qdrant-kb
      - REDIS_URL=redis://redis-kb:6379/0
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 4G
        reservations:
          cpus: '1.0'
          memory: 2G
    networks:
      - kato-network

  # Shared databases
  kato-clickhouse:
    image: clickhouse/clickhouse-server:latest
    # ... ClickHouse configuration

  qdrant-kb:
    image: qdrant/qdrant:latest
    # ... Qdrant configuration

  redis-kb:
    image: redis:7-alpine
    # ... Redis configuration

networks:
  kato-network:
    driver: bridge
```

**nginx.conf**:
```nginx
upstream kato_backend {
    # Load balancing method
    least_conn;  # Route to least busy instance

    # KATO instances
    server kato-1:8000 max_fails=3 fail_timeout=30s;
    server kato-2:8000 max_fails=3 fail_timeout=30s;
    server kato-3:8000 max_fails=3 fail_timeout=30s;

    # Health check
    keepalive 32;
}

server {
    listen 80;
    server_name kato.yourdomain.com;

    # Health check endpoint (bypass load balancing)
    location /health {
        access_log off;
        proxy_pass http://kato-1:8000/health;
    }

    # Main application
    location / {
        proxy_pass http://kato_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;

        # Buffering
        proxy_buffering on;
        proxy_buffer_size 4k;
        proxy_buffers 8 4k;

        # Keep-alive
        proxy_http_version 1.1;
        proxy_set_header Connection "";
    }

    # WebSocket support
    location /ws {
        proxy_pass http://kato_backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 86400;
    }
}
```

**Deploy**:
```bash
docker compose up -d --scale kato-1=1 --scale kato-2=1 --scale kato-3=1
```

### Kubernetes Horizontal Scaling

**Deployment with HPA**:
```yaml
# kato-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: kato
  namespace: kato
spec:
  replicas: 3  # Initial replicas
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: kato
  template:
    metadata:
      labels:
        app: kato
    spec:
      containers:
      - name: kato
        image: ghcr.io/your-org/kato:latest
        ports:
        - containerPort: 8000
        env:
        - name: PROCESSOR_ID
          valueFrom:
            fieldRef:
              fieldPath: metadata.name
        resources:
          requests:
            memory: "2Gi"
            cpu: "1"
          limits:
            memory: "4Gi"
            cpu: "2"
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 5
---
# Horizontal Pod Autoscaler
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: kato-hpa
  namespace: kato
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: kato
  minReplicas: 3
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
  # Custom metrics from Prometheus
  - type: Pods
    pods:
      metric:
        name: kato_requests_per_second
      target:
        type: AverageValue
        averageValue: "1000"
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
      - type: Percent
        value: 50
        periodSeconds: 60
      - type: Pods
        value: 1
        periodSeconds: 60
      selectPolicy: Min
    scaleUp:
      stabilizationWindowSeconds: 60
      policies:
      - type: Percent
        value: 100
        periodSeconds: 30
      - type: Pods
        value: 2
        periodSeconds: 30
      selectPolicy: Max
```

**Deploy**:
```bash
kubectl apply -f kato-deployment.yaml

# Monitor scaling
kubectl get hpa -n kato -w
kubectl get pods -n kato -w
```

### Custom Metrics Autoscaling

**Prometheus Adapter**:
```bash
# Install Prometheus Adapter
helm install prometheus-adapter prometheus-community/prometheus-adapter \
  --namespace monitoring \
  --set prometheus.url=http://prometheus-server.monitoring.svc.cluster.local
```

**Configure custom metrics** (`prometheus-adapter-values.yaml`):
```yaml
rules:
  custom:
    - seriesQuery: 'kato_requests_total{namespace="kato"}'
      resources:
        overrides:
          namespace: {resource: "namespace"}
          pod: {resource: "pod"}
      name:
        matches: "^kato_requests_total"
        as: "kato_requests_per_second"
      metricsQuery: 'rate(<<.Series>>{<<.LabelMatchers>>}[1m])'
```

## Vertical Scaling

### Resource Allocation Guidelines

**Development**:
```yaml
resources:
  requests:
    memory: "512Mi"
    cpu: "250m"
  limits:
    memory: "1Gi"
    cpu: "500m"
```

**Staging**:
```yaml
resources:
  requests:
    memory: "1Gi"
    cpu: "500m"
  limits:
    memory: "2Gi"
    cpu: "1"
```

**Production (Standard)**:
```yaml
resources:
  requests:
    memory: "2Gi"
    cpu: "1"
  limits:
    memory: "4Gi"
    cpu: "2"
```

**Production (High Load)**:
```yaml
resources:
  requests:
    memory: "4Gi"
    cpu: "2"
  limits:
    memory: "8Gi"
    cpu: "4"
```

### When to Vertically Scale

**Scale UP when**:
- CPU utilization consistently >80%
- Memory utilization consistently >80%
- P95 latency >1 second
- OOM (Out of Memory) errors occurring
- Garbage collection taking >10% CPU time

**Scale DOWN when**:
- CPU utilization consistently <30%
- Memory utilization consistently <30%
- Cost optimization needed
- Over-provisioned resources evident

### Vertical Scaling Process

**Kubernetes**:
```bash
# Update resource limits
kubectl set resources deployment/kato \
  --namespace=kato \
  --limits=cpu=4,memory=8Gi \
  --requests=cpu=2,memory=4Gi

# Or edit deployment
kubectl edit deployment/kato -n kato
```

**Docker Compose**:
```yaml
# Update docker compose.yml
services:
  kato:
    deploy:
      resources:
        limits:
          cpus: '4.0'
          memory: 8G
        reservations:
          cpus: '2.0'
          memory: 4G

# Restart service
docker compose up -d kato
```

## Database Scaling

### ClickHouse Scaling

#### Vertical Scaling (Single Node)

**docker compose.yml**:
```yaml
services:
  kato-clickhouse:
    image: clickhouse/clickhouse-server:latest
    volumes:
      - kato-clickhouse-data:/var/lib/clickhouse
    environment:
      - CLICKHOUSE_DEFAULT_ACCESS_MANAGEMENT=1
    deploy:
      resources:
        limits:
          cpus: '8.0'
          memory: 16G
        reservations:
          cpus: '4.0'
          memory: 8G
    ulimits:
      nofile:
        soft: 262144
        hard: 262144
```

**When to use**:
- Datasets < 1TB
- Single region deployment
- Simplified operations
- Cost optimization

#### Cluster Mode (Horizontal Scaling)

**For datasets >1TB or high availability**:

**docker compose.yml**:
```yaml
services:
  # ClickHouse cluster with 2 shards, 2 replicas each
  clickhouse-01:
    image: clickhouse/clickhouse-server:latest
    volumes:
      - ./clickhouse-config/config.xml:/etc/clickhouse-server/config.d/cluster.xml
      - clickhouse-01-data:/var/lib/clickhouse
    networks:
      - kato-network

  clickhouse-02:
    image: clickhouse/clickhouse-server:latest
    volumes:
      - ./clickhouse-config/config.xml:/etc/clickhouse-server/config.d/cluster.xml
      - clickhouse-02-data:/var/lib/clickhouse
    networks:
      - kato-network

  clickhouse-03:
    image: clickhouse/clickhouse-server:latest
    volumes:
      - ./clickhouse-config/config.xml:/etc/clickhouse-server/config.d/cluster.xml
      - clickhouse-03-data:/var/lib/clickhouse
    networks:
      - kato-network

  clickhouse-04:
    image: clickhouse/clickhouse-server:latest
    volumes:
      - ./clickhouse-config/config.xml:/etc/clickhouse-server/config.d/cluster.xml
      - clickhouse-04-data:/var/lib/clickhouse
    networks:
      - kato-network

  # ClickHouse Keeper for coordination
  clickhouse-keeper:
    image: clickhouse/clickhouse-keeper:latest
    volumes:
      - clickhouse-keeper-data:/var/lib/clickhouse-keeper
    networks:
      - kato-network
```

**cluster.xml configuration**:
```xml
<clickhouse>
    <remote_servers>
        <kato_cluster>
            <shard>
                <replica>
                    <host>clickhouse-01</host>
                    <port>9000</port>
                </replica>
                <replica>
                    <host>clickhouse-02</host>
                    <port>9000</port>
                </replica>
            </shard>
            <shard>
                <replica>
                    <host>clickhouse-03</host>
                    <port>9000</port>
                </replica>
                <replica>
                    <host>clickhouse-04</host>
                    <port>9000</port>
                </replica>
            </shard>
        </kato_cluster>
    </remote_servers>
</clickhouse>
```

**Update KATO configuration**:
```bash
CLICKHOUSE_HOST=clickhouse-01,clickhouse-02,clickhouse-03,clickhouse-04
CLICKHOUSE_PORT=8123
CLICKHOUSE_CLUSTER=kato_cluster
```

**When to use**:
- Datasets > 1TB
- High availability requirements
- Multi-region deployment
- Need for read scaling

### Qdrant Scaling

#### Cluster Mode

**docker compose.yml**:
```yaml
services:
  qdrant-node-1:
    image: qdrant/qdrant:latest
    environment:
      QDRANT__CLUSTER__ENABLED: "true"
      QDRANT__CLUSTER__P2P__PORT: 6335
    ports:
      - "6333:6333"

  qdrant-node-2:
    image: qdrant/qdrant:latest
    environment:
      QDRANT__CLUSTER__ENABLED: "true"
      QDRANT__CLUSTER__P2P__PORT: 6335
      QDRANT__CLUSTER__BOOTSTRAP: "http://qdrant-node-1:6335"
    ports:
      - "6334:6333"

  qdrant-node-3:
    image: qdrant/qdrant:latest
    environment:
      QDRANT__CLUSTER__ENABLED: "true"
      QDRANT__CLUSTER__P2P__PORT: 6335
      QDRANT__CLUSTER__BOOTSTRAP: "http://qdrant-node-1:6335"
    ports:
      - "6336:6333"
```

### Redis Scaling

#### Sentinel (High Availability)

**docker compose.yml**:
```yaml
services:
  redis-master:
    image: redis:7-alpine
    command: redis-server --appendonly yes

  redis-replica-1:
    image: redis:7-alpine
    command: redis-server --slaveof redis-master 6379 --appendonly yes

  redis-replica-2:
    image: redis:7-alpine
    command: redis-server --slaveof redis-master 6379 --appendonly yes

  redis-sentinel-1:
    image: redis:7-alpine
    command: redis-sentinel /etc/redis/sentinel.conf
    volumes:
      - ./sentinel.conf:/etc/redis/sentinel.conf

  redis-sentinel-2:
    image: redis:7-alpine
    command: redis-sentinel /etc/redis/sentinel.conf
    volumes:
      - ./sentinel.conf:/etc/redis/sentinel.conf

  redis-sentinel-3:
    image: redis:7-alpine
    command: redis-sentinel /etc/redis/sentinel.conf
    volumes:
      - ./sentinel.conf:/etc/redis/sentinel.conf
```

**sentinel.conf**:
```
sentinel monitor mymaster redis-master 6379 2
sentinel down-after-milliseconds mymaster 5000
sentinel parallel-syncs mymaster 1
sentinel failover-timeout mymaster 10000
```

**Update KATO configuration**:
```bash
REDIS_URL=redis-sentinel://redis-sentinel-1:26379,redis-sentinel-2:26379,redis-sentinel-3:26379/mymaster/0
```

## Capacity Planning

### Load Calculations

**Concurrent Users**:
```
Requests per second = Concurrent Users × Requests per User per Second

Example:
- 10,000 concurrent users
- 2 requests/user/second
= 20,000 requests/second

KATO instances needed:
- Each instance handles ~2,000 req/s (optimized)
= 10 instances minimum (with 50% headroom)
= 15 instances recommended
```

**Storage Requirements**:
```
Pattern storage = Patterns × Average Size

Example:
- 1M patterns
- 2KB average size per pattern
= 2GB storage

ClickHouse scaling:
- <100GB: Single instance
- 100GB-1TB: Vertical scaling (more CPU/RAM)
- >1TB: Cluster with sharding
```

**Memory Requirements**:
```
Per-instance memory = Base + (Sessions × STM Size)

Example:
- Base: 500MB
- 1,000 active sessions
- 100KB average STM size
= 500MB + 100MB = 600MB
= 2GB allocated (with headroom)
```

### Scaling Decision Matrix

| Metric | Current | Threshold | Action |
|--------|---------|-----------|--------|
| CPU Usage | >80% | 70% | Add instances or increase CPU |
| Memory Usage | >80% | 70% | Add instances or increase memory |
| Request Rate | >2000/s per instance | 1500/s | Add instances |
| P95 Latency | >1s | 100ms | Add instances or optimize |
| Error Rate | >1% | 0.1% | Investigate, then scale if needed |
| Database CPU | >80% | 70% | Scale database |
| Database Storage | >80% | 70% | Add storage or shard |

## Auto-Scaling Configuration

### KEDA (Kubernetes Event-Driven Autoscaling)

**Install KEDA**:
```bash
helm repo add kedacore https://kedacore.github.io/charts
helm install keda kedacore/keda --namespace keda --create-namespace
```

**ScaledObject**:
```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: kato-scaler
  namespace: kato
spec:
  scaleTargetRef:
    name: kato
  minReplicaCount: 3
  maxReplicaCount: 20
  cooldownPeriod: 300
  triggers:
    # Scale based on Prometheus metrics
    - type: prometheus
      metadata:
        serverAddress: http://prometheus-server.monitoring:9090
        metricName: kato_requests_per_second
        threshold: '1000'
        query: sum(rate(kato_requests_total[1m]))

    # Scale based on CPU
    - type: cpu
      metricType: Utilization
      metadata:
        value: '70'

    # Scale based on memory
    - type: memory
      metricType: Utilization
      metadata:
        value: '80'
```

## Testing Scaling

### Load Testing Script

```bash
#!/bin/bash
# load-test.sh - Gradually increase load to test scaling

BASE_URL="https://kato.yourdomain.com"
DURATION=300  # 5 minutes

# Start with 10 concurrent users
echo "Starting load test with 10 concurrent users..."
ab -n 10000 -c 10 -t $DURATION "${BASE_URL}/health"

# Increase to 50
echo "Increasing to 50 concurrent users..."
ab -n 50000 -c 50 -t $DURATION "${BASE_URL}/health"

# Increase to 100
echo "Increasing to 100 concurrent users..."
ab -n 100000 -c 100 -t $DURATION "${BASE_URL}/health"

# Monitor scaling
echo "Monitoring pod count..."
kubectl get pods -n kato -w
```

### Scaling Verification

```bash
# Monitor HPA
kubectl get hpa -n kato -w

# Check pod resource usage
kubectl top pods -n kato

# View scaling events
kubectl describe hpa kato-hpa -n kato

# Check logs for errors during scaling
kubectl logs -f deployment/kato -n kato
```

## Best Practices

1. **Start with horizontal scaling** - Easier to manage than vertical
2. **Use odd numbers for HA** - 3, 5, 7 instances for consensus
3. **Set resource limits** - Prevent resource starvation
4. **Monitor before scaling** - Understand bottlenecks first
5. **Scale databases independently** - Don't wait for app issues
6. **Test failover** - Ensure high availability works
7. **Use connection pooling** - Maximize database efficiency
8. **Implement circuit breakers** - Protect against cascading failures
9. **Cache aggressively** - Reduce database load
10. **Regular load testing** - Validate scaling behavior

## Scaling Checklist

### Pre-Scaling
- [ ] Baseline metrics established
- [ ] Bottlenecks identified
- [ ] Scaling strategy decided (horizontal vs vertical)
- [ ] Load testing completed
- [ ] Monitoring dashboards ready

### During Scaling
- [ ] Traffic gradually increased
- [ ] Metrics monitored in real-time
- [ ] Error rates tracked
- [ ] Performance verified
- [ ] Database health checked

### Post-Scaling
- [ ] Performance meets SLA
- [ ] Cost analyzed
- [ ] Documentation updated
- [ ] Team trained on new scale
- [ ] Rollback plan verified

## Related Documentation

- [Performance Tuning](performance-tuning.md)
- [Monitoring](monitoring.md)
- [Kubernetes Deployment](kubernetes-deployment.md)
- [Production Checklist](production-checklist.md)

---

**Last Updated**: November 2025
**KATO Version**: 3.0+
