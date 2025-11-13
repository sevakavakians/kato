# Docker Deployment Guide

Complete guide to deploying KATO with Docker and Docker Compose.

## Overview

KATO uses Docker Compose for orchestrating multiple services:
- **KATO API**: FastAPI application
- **MongoDB**: Pattern and symbol storage
- **Qdrant**: Vector similarity search
- **Redis**: Session and cache management

## Quick Start

### Prerequisites

- Docker Desktop 20.10+
- Docker Compose 2.0+
- 4GB+ available RAM
- 10GB+ disk space

### Basic Deployment

```bash
# Clone repository
git clone https://github.com/your-org/kato.git
cd kato

# Start all services
./start.sh

# Verify deployment
curl http://localhost:8000/health
```

## Docker Compose Configuration

### docker-compose.yml

```yaml
version: '3.8'

services:
  # KATO API Service
  kato:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: kato
    ports:
      - "8000:8000"
    environment:
      - MONGO_BASE_URL=mongodb://mongo-kb:27017
      - QDRANT_HOST=qdrant-kb
      - REDIS_URL=redis://redis-kb:6379/0
      - LOG_LEVEL=INFO
      - ENVIRONMENT=production
    depends_on:
      - mongo-kb
      - qdrant-kb
      - redis-kb
    restart: unless-stopped
    networks:
      - kato-network
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

  # MongoDB Service
  mongo-kb:
    image: mongo:6.0
    container_name: mongo-kb
    ports:
      - "27017:27017"
    volumes:
      - kato-mongo-data:/data/db
    restart: unless-stopped
    networks:
      - kato-network
    command: --wiredTigerCacheSizeGB 2

  # Qdrant Service
  qdrant-kb:
    image: qdrant/qdrant:latest
    container_name: qdrant-kb
    ports:
      - "6333:6333"
      - "6334:6334"
    volumes:
      - kato-qdrant-data:/qdrant/storage
    restart: unless-stopped
    networks:
      - kato-network

  # Redis Service
  redis-kb:
    image: redis:7-alpine
    container_name: redis-kb
    ports:
      - "6379:6379"
    volumes:
      - kato-redis-data:/data
    restart: unless-stopped
    networks:
      - kato-network
    command: redis-server --appendonly yes

volumes:
  kato-mongo-data:
  kato-qdrant-data:
  kato-redis-data:

networks:
  kato-network:
    driver: bridge
```

## Dockerfile

### Production Dockerfile

```dockerfile
# Multi-stage build for optimized image size
FROM python:3.10-slim as builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt requirements.lock ./
RUN pip install --no-cache-dir --user -r requirements.lock

# Production stage
FROM python:3.10-slim

WORKDIR /app

# Copy Python packages from builder
COPY --from=builder /root/.local /root/.local

# Copy application code
COPY kato/ ./kato/
COPY start.sh ./

# Set Python path
ENV PATH=/root/.local/bin:$PATH
ENV PYTHONPATH=/app

# Create non-root user
RUN useradd -m -u 1000 kato && chown -R kato:kato /app
USER kato

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

# Start KATO
CMD ["uvicorn", "kato.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

## Environment Configuration

### Production .env

```bash
# Service Configuration
SERVICE_NAME=kato
SERVICE_VERSION=3.0
ENVIRONMENT=production

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json
LOG_OUTPUT=stdout

# API Configuration
HOST=0.0.0.0
PORT=8000
WORKERS=4
CORS_ENABLED=true
CORS_ORIGINS=https://yourdomain.com

# Database Configuration
MONGO_BASE_URL=mongodb://mongo-kb:27017
MONGO_TIMEOUT=5000
QDRANT_HOST=qdrant-kb
QDRANT_PORT=6333
REDIS_URL=redis://redis-kb:6379/0

# Learning Configuration
MAX_PATTERN_LENGTH=0
RECALL_THRESHOLD=0.3
STM_MODE=CLEAR
PERSISTENCE=5

# Session Configuration
SESSION_TTL=7200
SESSION_AUTO_EXTEND=true

# Performance Configuration
KATO_USE_FAST_MATCHING=true
KATO_USE_INDEXING=true
KATO_BATCH_SIZE=1000
CONNECTION_POOL_SIZE=50
```

## Deployment Scenarios

### Single Instance Deployment

```bash
# Start services
docker-compose up -d

# View logs
docker-compose logs -f

# Check status
docker-compose ps
```

### Multi-Instance Deployment

```yaml
# docker-compose.yml with multiple KATO instances
services:
  kato-1:
    <<: *kato-service
    container_name: kato-1
    ports:
      - "8001:8000"
    environment:
      - PROCESSOR_ID=kato-1

  kato-2:
    <<: *kato-service
    container_name: kato-2
    ports:
      - "8002:8000"
    environment:
      - PROCESSOR_ID=kato-2

  kato-3:
    <<: *kato-service
    container_name: kato-3
    ports:
      - "8003:8000"
    environment:
      - PROCESSOR_ID=kato-3

  # Nginx load balancer
  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
    depends_on:
      - kato-1
      - kato-2
      - kato-3
```

**nginx.conf**:
```nginx
upstream kato_backend {
    least_conn;
    server kato-1:8000;
    server kato-2:8000;
    server kato-3:8000;
}

server {
    listen 80;

    location / {
        proxy_pass http://kato_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## Volume Management

### Backup Volumes

```bash
# Backup MongoDB
docker run --rm \
  -v kato-mongo-data:/data \
  -v $(pwd)/backups:/backup \
  alpine tar czf /backup/mongo-$(date +%Y%m%d).tar.gz /data

# Backup Qdrant
docker run --rm \
  -v kato-qdrant-data:/data \
  -v $(pwd)/backups:/backup \
  alpine tar czf /backup/qdrant-$(date +%Y%m%d).tar.gz /data

# Backup Redis
docker run --rm \
  -v kato-redis-data:/data \
  -v $(pwd)/backups:/backup \
  alpine tar czf /backup/redis-$(date +%Y%m%d).tar.gz /data
```

### Restore Volumes

```bash
# Restore MongoDB
docker run --rm \
  -v kato-mongo-data:/data \
  -v $(pwd)/backups:/backup \
  alpine tar xzf /backup/mongo-20251113.tar.gz -C /

# Restart services
docker-compose restart mongo-kb
```

## Resource Limits

### docker-compose.yml with limits

```yaml
services:
  kato:
    # ... other config
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 4G
        reservations:
          cpus: '1.0'
          memory: 2G

  mongo-kb:
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 4G
        reservations:
          cpus: '1.0'
          memory: 2G

  qdrant-kb:
    deploy:
      resources:
        limits:
          cpus: '1.0'
          memory: 2G
        reservations:
          cpus: '0.5'
          memory: 1G
```

## Health Checks and Monitoring

### Health Check Script

```bash
#!/bin/bash
# health-check.sh

# Check KATO health
KATO_HEALTH=$(curl -s http://localhost:8000/health | jq -r '.status')
if [ "$KATO_HEALTH" != "healthy" ]; then
    echo "KATO unhealthy"
    exit 1
fi

# Check MongoDB
if ! docker exec mongo-kb mongo --eval "db.adminCommand('ping')" > /dev/null 2>&1; then
    echo "MongoDB unhealthy"
    exit 1
fi

# Check Qdrant
QDRANT_HEALTH=$(curl -s http://localhost:6333/ | jq -r '.title')
if [ -z "$QDRANT_HEALTH" ]; then
    echo "Qdrant unhealthy"
    exit 1
fi

# Check Redis
if ! docker exec redis-kb redis-cli ping > /dev/null 2>&1; then
    echo "Redis unhealthy"
    exit 1
fi

echo "All services healthy"
```

## Logging Configuration

### Centralized Logging

```yaml
# docker-compose.yml with logging
services:
  kato:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

### Log Aggregation

```bash
# View all logs
docker-compose logs

# Follow specific service
docker-compose logs -f kato

# Export logs
docker-compose logs --no-color > kato-logs-$(date +%Y%m%d).log
```

## Updates and Maintenance

### Update KATO

```bash
# Pull latest code
git pull origin main

# Rebuild image
docker-compose build --no-cache kato

# Restart with zero downtime (if using multiple instances)
docker-compose up -d --no-deps --scale kato=2 kato

# Or simple restart
docker-compose restart kato
```

### Update Dependencies

```bash
# Update requirements
pip-compile --output-file=requirements.lock requirements.txt

# Rebuild image
docker-compose build --no-cache kato
docker-compose up -d
```

## Troubleshooting

### Container Won't Start

```bash
# Check logs
docker-compose logs kato

# Check resource usage
docker stats

# Verify configuration
docker-compose config
```

### Network Issues

```bash
# Inspect network
docker network inspect kato-network

# Test connectivity
docker exec kato ping mongo-kb
docker exec kato ping qdrant-kb
```

### Database Connection Issues

```bash
# Test MongoDB connection
docker exec mongo-kb mongo --eval "db.adminCommand('ping')"

# Test Qdrant connection
curl http://localhost:6333/

# Test Redis connection
docker exec redis-kb redis-cli ping
```

## Security Best Practices

1. **Use secrets management**: Docker secrets or external vault
2. **Non-root user**: Run containers as non-root (already configured)
3. **Network isolation**: Use custom networks
4. **Resource limits**: Set CPU and memory limits
5. **Regular updates**: Keep base images updated
6. **Environment variables**: Never commit secrets to git

## Production Checklist

- [ ] Set ENVIRONMENT=production
- [ ] Configure proper CORS_ORIGINS
- [ ] Set strong MongoDB authentication
- [ ] Enable Redis persistence (AOF)
- [ ] Configure backup strategy
- [ ] Set up log aggregation
- [ ] Configure health checks
- [ ] Set resource limits
- [ ] Enable HTTPS (via reverse proxy)
- [ ] Configure monitoring

## Related Documentation

- [Kubernetes Deployment](kubernetes-deployment.md)
- [Production Checklist](production-checklist.md)
- [Security Configuration](security-configuration.md)
- [Monitoring](monitoring.md)
- [Scaling](scaling.md)

---

**Last Updated**: November 2025
**KATO Version**: 3.0+
