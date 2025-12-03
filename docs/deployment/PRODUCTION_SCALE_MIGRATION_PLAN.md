# Production Scale Migration Plan (PSMP)

**Status:** Planning Document - Future Implementation
**Created:** 2025-11-03
**Purpose:** Document production-scale deployment architecture for when scaling needs arise
**Short Name:** PSMP

## Executive Summary

This guide documents industry best practices for deploying FastAPI applications at production scale. KATO currently uses single-worker Uvicorn, which is appropriate for development and testing. When production scaling is needed, this guide provides the migration path.

## Current State Analysis

### KATO's Current Setup

```dockerfile
# Current Dockerfile configuration (Dockerfile:59-67)
CMD ["uvicorn", "kato.services.kato_fastapi:app",
     "--host", "0.0.0.0", "--port", "8000",
     "--workers", "1",                    # Single worker
     "--limit-concurrency", "100",        # 100 concurrent connections per worker
     "--limit-max-requests", "10000"]     # Auto-restart after 10k requests
```

### Current Limitations

| Aspect | Current State | Impact |
|--------|---------------|--------|
| **Parallelism** | Single worker = 1 CPU core | Cannot utilize multi-core CPUs |
| **Fault Tolerance** | Worker crash = service down | No isolation between requests |
| **Worker Restarts** | Restart after 10k requests | Training sessions interrupted |
| **Load Balancing** | No internal load balancing | All requests to single worker |
| **Concurrency** | 100 connections per worker | Limited for high-traffic scenarios |

### When Current Setup is Sufficient

✅ Development and testing environments
✅ Single-user scenarios
✅ Low-to-medium traffic (<100 requests/sec)
✅ Training workloads with batch sizes <10k observations
✅ Prototyping and proof-of-concept deployments

## Industry Best Practices (2025)

Based on FastAPI documentation and industry standards, production deployments use one of two approaches:

### Approach 1: Gunicorn + Uvicorn Workers (Traditional/VM Deployment)

**Architecture:**
```
Client Request → Gunicorn (Process Manager)
                    ↓
    ┌───────────────┼───────────────┐
    ↓               ↓               ↓
Uvicorn Worker  Uvicorn Worker  Uvicorn Worker
(CPU Core 1)    (CPU Core 2)    (CPU Core 3)
    ↓               ↓               ↓
FastAPI App     FastAPI App     FastAPI App
    ↓               ↓               ↓
ClickHouse, Redis, Qdrant (Shared Resources)
```

**Why This Works:**
- **Gunicorn manages processes**: Spawns workers, distributes load, handles restarts
- **Uvicorn handles async**: Each worker runs async event loop for concurrency
- **Combined power**: Multi-process parallelism + async concurrency

### Approach 2: Kubernetes + Single Uvicorn per Pod (Cloud-Native)

**Architecture:**
```
Client Request → Kubernetes Service (Load Balancer)
                    ↓
    ┌───────────────┼───────────────┐
    ↓               ↓               ↓
Pod 1           Pod 2           Pod 3
(Uvicorn)       (Uvicorn)       (Uvicorn)
    ↓               ↓               ↓
FastAPI App     FastAPI App     FastAPI App
    ↓               ↓               ↓
ClickHouse, Redis, Qdrant (Shared Resources)
```

**Why This Works:**
- **Kubernetes manages processes**: Pod orchestration, health checks, auto-scaling
- **Uvicorn handles async**: Single worker per pod, K8s handles parallelism
- **Cloud-native**: Horizontal Pod Autoscaler (HPA) scales based on load

## Detailed Implementation Options

### Option 1: Gunicorn + Uvicorn Workers

#### Configuration

```dockerfile
# Dockerfile.production
FROM python:3.10-slim

# Build arguments for version metadata
ARG VERSION=dev
ARG GIT_COMMIT=unknown
ARG BUILD_DATE=unknown

# OCI-compliant image labels
LABEL org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.revision="${GIT_COMMIT}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.title="KATO" \
      org.opencontainers.image.description="Knowledge Abstraction for Traceable Outcomes - Production" \
      org.opencontainers.image.vendor="Intelligent Artifacts"

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.lock .

# Install all dependencies from locked requirements
RUN pip install --no-cache-dir -r requirements.lock

# Install gunicorn for production
RUN pip install --no-cache-dir gunicorn==21.2.0

# Cache bust for code changes
ARG CACHE_BUST=7
RUN echo "Cache bust: $CACHE_BUST"

# Copy the KATO package
COPY kato/ ./kato/

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PORT=8000

# Expose the port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health').raise_for_status()" || exit 1

# Production command with Gunicorn + Uvicorn workers
CMD ["gunicorn", "kato.services.kato_fastapi:app", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--workers", "4", \
     "--bind", "0.0.0.0:8000", \
     "--worker-connections", "1000", \
     "--max-requests", "50000", \
     "--max-requests-jitter", "5000", \
     "--timeout", "120", \
     "--graceful-timeout", "30", \
     "--keepalive", "5", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "--log-level", "info"]
```

#### Worker Calculation

```bash
# Recommended: 2-4x the number of CPU cores
# For a 4-core machine:
--workers 4   # Conservative (1x cores)
--workers 8   # Moderate (2x cores)
--workers 16  # Aggressive (4x cores)

# Dynamic calculation in docker compose:
environment:
  - GUNICORN_WORKERS=${GUNICORN_WORKERS:-4}
```

#### Key Parameters Explained

| Parameter | Value | Purpose |
|-----------|-------|---------|
| `--worker-class` | `uvicorn.workers.UvicornWorker` | Use Uvicorn's async capabilities |
| `--workers` | `4` | Number of worker processes (2-4x CPU cores) |
| `--worker-connections` | `1000` | Max concurrent connections per worker |
| `--max-requests` | `50000` | Worker restart after N requests (prevents memory leaks) |
| `--max-requests-jitter` | `5000` | Randomize restart timing (prevents simultaneous restarts) |
| `--timeout` | `120` | Kill workers that don't respond in 120s |
| `--graceful-timeout` | `30` | Time for worker to finish in-flight requests before force kill |
| `--keepalive` | `5` | Keep-alive timeout for persistent connections |

#### Production docker compose.yml

```yaml
# docker compose.production.yml
version: '3.8'

services:
  # ClickHouse shared by all sessions
  clickhouse:
    image: clickhouse/clickhouse-server:latest
    container_name: clickhouse
    ports:
      - "8123:8123"
      - "9000:9000"
    volumes:
      - clickhouse-data:/var/lib/clickhouse
    networks:
      - kato-network
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "clickhouse-client", "--query", "SELECT 1"]
      interval: 15s
      timeout: 10s
      retries: 20
      start_period: 180s

  # Qdrant vector database
  qdrant:
    image: qdrant/qdrant:latest
    container_name: kato-qdrant
    ports:
      - "6333:6333"
    volumes:
      - qdrant-data:/qdrant/storage
    networks:
      - kato-network
    restart: unless-stopped

  # Redis for session storage
  redis:
    image: redis:7-alpine
    container_name: kato-redis
    command: redis-server --save "" --appendonly no
    ports:
      - "6379:6379"
    volumes:
      - redis-data:/data
    networks:
      - kato-network
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  # KATO Service with Gunicorn + Uvicorn
  kato:
    build:
      context: .
      dockerfile: Dockerfile.production
      args:
        VERSION: ${VERSION:-dev}
        GIT_COMMIT: ${GIT_COMMIT:-unknown}
        BUILD_DATE: ${BUILD_DATE:-unknown}
    image: kato:production
    container_name: kato
    environment:
      - SERVICE_NAME=kato
      - CLICKHOUSE_HOST=clickhouse
      - CLICKHOUSE_PORT=8123
      - CLICKHOUSE_DB=kato
      - REDIS_HOST=redis
      - REDIS_PORT=6379
      - QDRANT_HOST=qdrant
      - QDRANT_PORT=6333
      - LOG_LEVEL=INFO
      - SESSION_TTL=3600
      - SESSION_AUTO_EXTEND=true
      # Gunicorn configuration
      - GUNICORN_WORKERS=${GUNICORN_WORKERS:-4}
      # Performance optimizations
      - KATO_BATCH_SIZE=10000
      - CONNECTION_POOL_SIZE=50
      - REQUEST_TIMEOUT=120.0
    ports:
      - "8000:8000"
    networks:
      - kato-network
    depends_on:
      clickhouse:
        condition: service_healthy
      redis:
        condition: service_healthy
      qdrant:
        condition: service_started
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=5).read()"]
      interval: 30s
      timeout: 10s
      retries: 3

networks:
  kato-network:
    driver: bridge
    ipam:
      config:
        - subnet: 172.28.0.0/16

volumes:
  clickhouse-data:
  redis-data:
  qdrant-data:
```

#### Benefits

✅ **Parallelism**: Utilize all CPU cores (4 workers = ~4x throughput)
✅ **Fault Tolerance**: Worker crash doesn't kill service
✅ **Load Balancing**: Gunicorn distributes requests across healthy workers
✅ **Graceful Restarts**: In-flight requests complete before worker dies
✅ **Higher Limits**: 50k requests vs 10k reduces restart frequency
✅ **Easy Setup**: Works on any VM/server without Kubernetes

#### Drawbacks

⚠️ Manual scaling (need to restart with different worker count)
⚠️ No auto-scaling based on load
⚠️ Limited to single machine resources

### Option 2: Kubernetes Deployment

#### Deployment Manifest

```yaml
# kubernetes/kato-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: kato
  namespace: production
  labels:
    app: kato
    component: api
spec:
  replicas: 4
  selector:
    matchLabels:
      app: kato
      component: api
  template:
    metadata:
      labels:
        app: kato
        component: api
    spec:
      containers:
      - name: kato
        image: ghcr.io/sevakavakians/kato:latest
        command:
          - "uvicorn"
          - "kato.services.kato_fastapi:app"
          - "--host=0.0.0.0"
          - "--port=8000"
          - "--workers=1"
          - "--limit-concurrency=1000"
        ports:
        - containerPort: 8000
          name: http
          protocol: TCP
        env:
        - name: SERVICE_NAME
          value: "kato"
        - name: CLICKHOUSE_HOST
          value: "clickhouse"
        - name: CLICKHOUSE_PORT
          value: "8123"
        - name: CLICKHOUSE_DB
          value: "kato"
        - name: REDIS_HOST
          value: "redis"
        - name: REDIS_PORT
          value: "6379"
        - name: QDRANT_HOST
          value: "qdrant"
        - name: QDRANT_PORT
          value: "6333"
        - name: LOG_LEVEL
          value: "INFO"
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
          timeoutSeconds: 5
          failureThreshold: 3
        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 5
          timeoutSeconds: 3
          failureThreshold: 3
        startupProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 0
          periodSeconds: 5
          timeoutSeconds: 3
          failureThreshold: 30

---
apiVersion: v1
kind: Service
metadata:
  name: kato-service
  namespace: production
spec:
  selector:
    app: kato
    component: api
  ports:
  - protocol: TCP
    port: 80
    targetPort: 8000
    name: http
  type: LoadBalancer

---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: kato-hpa
  namespace: production
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: kato
  minReplicas: 2
  maxReplicas: 20
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
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
      - type: Percent
        value: 50
        periodSeconds: 60
    scaleUp:
      stabilizationWindowSeconds: 0
      policies:
      - type: Percent
        value: 100
        periodSeconds: 30
```

#### Benefits

✅ **Auto-scaling**: HPA automatically adds/removes pods based on CPU/memory
✅ **Rolling Updates**: Zero-downtime deployments
✅ **Cloud-native**: Works with any cloud provider (AWS EKS, GCP GKE, Azure AKS)
✅ **Observability**: Integrates with Prometheus, Grafana, Jaeger
✅ **Resource Management**: CPU/memory requests and limits per pod
✅ **Self-healing**: Automatically restarts failed pods

#### Drawbacks

⚠️ Complex infrastructure setup required
⚠️ Steep learning curve for Kubernetes
⚠️ Higher operational overhead
⚠️ Overkill for small deployments

### Option 3: Nginx Reverse Proxy (Complementary to Both)

```nginx
# nginx/nginx.conf
upstream kato_backend {
    least_conn;
    server kato-1:8000 max_fails=3 fail_timeout=30s;
    server kato-2:8000 max_fails=3 fail_timeout=30s;
    server kato-3:8000 max_fails=3 fail_timeout=30s;
    server kato-4:8000 max_fails=3 fail_timeout=30s;
}

server {
    listen 80;
    server_name api.kato.example.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name api.kato.example.com;

    ssl_certificate /etc/nginx/ssl/cert.pem;
    ssl_certificate_key /etc/nginx/ssl/key.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    limit_req_zone $binary_remote_addr zone=kato_limit:10m rate=100r/s;
    limit_req zone=kato_limit burst=200 nodelay;

    client_max_body_size 100M;
    client_body_buffer_size 1M;

    proxy_connect_timeout 120s;
    proxy_send_timeout 120s;
    proxy_read_timeout 120s;
    send_timeout 120s;

    location / {
        proxy_pass http://kato_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    location /health {
        proxy_pass http://kato_backend/health;
        access_log off;
        limit_req off;
    }
}
```

## Comparison Matrix

| Approach | Best For | Pros | Cons | Complexity | Cost |
|----------|----------|------|------|------------|------|
| **Current (Uvicorn only)** | Development, Testing, Low traffic | Simple, Fast startup, Easy debugging | No parallelism, Single point of failure | Low | Low |
| **Gunicorn + Uvicorn** | Traditional VMs, Single server, Medium traffic | Multi-process, Fault tolerance, Easy setup | Limited horizontal scaling, Manual scaling | Medium | Low |
| **Kubernetes** | Cloud-native, High scale, Multi-region | Auto-scaling, High availability, Observability | Steep learning curve, Complex debugging | High | Medium-High |
| **Nginx + Gunicorn** | Production VMs, SSL required | SSL termination, Rate limiting, Load balancing | Manual scaling | Medium-High | Low-Medium |

## Migration Path (Phased Approach)

### Phase 0: Immediate Fix (0-1 Day)

**Goal:** Stop training interruptions without architectural changes

**Changes:**
```dockerfile
# Dockerfile - Line 64
# Change from:
     "--limit-max-requests", "10000", \

# Change to:
     "--limit-max-requests", "50000", \
     "--limit-max-requests-jitter", "5000", \
```

**Impact:**
- 5x higher restart threshold
- Random jitter prevents simultaneous restarts
- Training sessions with <50k requests complete without interruption

**Testing:**
```bash
docker compose build --no-cache kato
./start.sh restart
# Monitor: docker logs kato -f | grep "Shutting down"
```

**Rollback:**
```bash
git checkout HEAD -- Dockerfile
docker compose build --no-cache
docker compose restart
```

### Phase 1: Production Multi-Worker (1-2 Weeks)

**Goal:** Implement Gunicorn + Uvicorn for parallel processing

**Changes:**

1. Add gunicorn to requirements:
```bash
echo "gunicorn==21.2.0" >> requirements.txt
pip-compile --output-file=requirements.lock requirements.txt
```

2. Create `Dockerfile.production` (see Option 1 above)

3. Create `docker compose.production.yml` (see Option 1 above)

**Testing:**
```bash
docker compose -f docker compose.production.yml build
docker compose -f docker compose.production.yml up -d
docker logs kato | grep "Booting worker"  # Should show 4 workers
```

**Rollback:**
```bash
docker compose -f docker compose.yml up -d
```

### Phase 2: Reverse Proxy & SSL (2-4 Weeks)

**Goal:** Add Nginx for SSL termination and rate limiting

**Changes:**

1. Create `nginx/nginx.conf` (see Option 3 above)

2. Add Nginx to `docker compose.production.yml`:
```yaml
services:
  nginx:
    image: nginx:1.25-alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./ssl:/etc/nginx/ssl:ro
    depends_on:
      - kato
    networks:
      - kato-network
    restart: unless-stopped
```

3. Generate SSL certificates:
```bash
# Self-signed for testing
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout ssl/key.pem -out ssl/cert.pem
```

**Testing:**
```bash
curl -k https://localhost/health
ab -n 1000 -c 100 https://localhost/health  # Test rate limiting
```

**Rollback:**
```bash
docker compose -f docker compose.production.yml down nginx
# Re-expose KATO ports directly
```

### Phase 3: Monitoring & Observability (1 Month)

**Goal:** Add Prometheus, Grafana, and structured logging

**Services to Add:**
- Prometheus for metrics collection
- Grafana for dashboards
- Loki for log aggregation (optional)

**Key Metrics:**
- Request rate, latency, error rate
- CPU and memory utilization
- Database connection pool usage
- Session counts and durations

### Phase 4: Kubernetes Migration (3+ Months)

**Goal:** Migrate to Kubernetes for cloud-native deployment

**Prerequisites:**
- Kubernetes cluster (EKS, GKE, AKS, or self-hosted)
- kubectl and helm installed
- Container registry configured

**Migration Steps:**
1. Create Kubernetes manifests (see Option 2 above)
2. Deploy supporting services as StatefulSets
3. Deploy KATO as Deployment with HPA
4. Configure Ingress controller
5. Set up monitoring (Prometheus Operator)

## Testing Strategy

### Phase 0 Testing
```bash
# Test training without restart (40k observations)
python test_large_training.py --observations 40000 --batch-size 5000
docker logs kato -f | grep -E "(Finished|Shutting down)"  # Should not appear
```

### Phase 1 Testing
```bash
# Test multi-worker load handling
ab -n 10000 -c 100 http://localhost:8000/health

# Verify worker distribution
docker logs kato | grep "worker" | sort | uniq -c

# Test graceful worker restart
docker exec kato pkill -f "gunicorn: worker"
# Service should continue without errors
```

### Phase 2 Testing
```bash
# Test SSL
curl https://localhost/health

# Test rate limiting (should get 429 errors)
ab -n 10000 -c 200 https://localhost/health
```

## Cost Analysis

| Phase | Infrastructure | Monthly Cost | Capacity |
|-------|----------------|--------------|----------|
| **Current** | Single VM/container | $50-100 | <100 req/sec |
| **Phase 1** | Larger VM | $100-200 | 500-1000 req/sec |
| **Phase 2** | Same + Nginx | $120-220 | Same + SSL |
| **Phase 4** | K8s cluster (3 nodes) | $300-1000 | 5000+ req/sec, auto-scales |

## Decision Framework

```
Need better performance/reliability?
  ↓
  Yes → What's your constraint?
    ↓
    ├─ Time/Complexity → Phase 0 (increase request limit)
    ├─ Single VM Budget → Phase 1 (Gunicorn + Uvicorn)
    ├─ Need SSL/Security → Phase 2 (+ Nginx)
    └─ Need Auto-scaling → Phase 4 (Kubernetes)
```

## Conclusion

**Current Status:** KATO's single-worker Uvicorn setup is appropriate for development and testing.

**Future Scaling Path:**
1. **Short-term**: Increase `--limit-max-requests` to prevent training interruptions
2. **Medium-term**: Implement Gunicorn + Uvicorn for multi-core utilization
3. **Long-term**: Migrate to Kubernetes for cloud-native auto-scaling

**Key Takeaway:** Choose the simplest solution that meets your current needs. Scale up only when necessary.

## References

- [FastAPI Deployment Documentation](https://fastapi.tiangolo.com/deployment/)
- [Uvicorn Deployment Guide](https://www.uvicorn.org/deployment/)
- [Gunicorn Configuration](https://docs.gunicorn.org/en/stable/configure.html)
- [Kubernetes FastAPI Example](https://kubernetes.io/docs/tutorials/stateless-application/)
- [Nginx Reverse Proxy Configuration](https://docs.nginx.com/nginx/admin-guide/web-server/reverse-proxy/)

## Document Maintenance

- **Review Frequency**: Quarterly or when scaling requirements change
- **Owner**: Infrastructure/DevOps Team
- **Last Updated**: 2025-11-03
- **Next Review**: 2026-02-03
