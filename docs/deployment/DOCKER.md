# KATO Docker Deployment Guide

This guide covers Docker-based deployment and management of KATO using the kato-manager.sh script.

## Prerequisites

- Docker Desktop or Docker Engine installed
- Docker Compose (optional, for multi-container deployments)
- Bash shell (macOS/Linux) or WSL (Windows)
- curl (for health checks)
- 4GB+ available RAM

## Quick Start

### Make Script Executable
```bash
chmod +x kato-manager.sh
```

### Basic Commands
```bash
# Build Docker image
./kato-manager.sh build

# Start KATO system
./kato-manager.sh start

# Check status
./kato-manager.sh status

# View logs
./kato-manager.sh logs

# Stop system
./kato-manager.sh stop
```

## Docker Architecture

KATO creates the following Docker resources:

1. **Network**: `kato-network` - Isolated network for containers
2. **MongoDB Container**: `mongo-kb-${USER}-1` - Persistent data storage
3. **KATO API Container**: `kato-api-${USER}-1` - Main processor
4. **Volume**: `kato-mongo-data` - MongoDB data persistence

### Container Naming

Containers are named with user prefix to allow multiple users on the same system:
- KATO API: `kato-api-${USER}-1`
- MongoDB: `mongo-kb-${USER}-1`

## Management Commands

### System Management

#### start
Start KATO system with MongoDB backend.

```bash
./kato-manager.sh start

# With custom parameters
./kato-manager.sh start --name "MyProcessor" --port 9000
```

#### stop
Stop KATO system and cleanup containers.

```bash
./kato-manager.sh stop
```

#### restart
Restart KATO system (stop + start).

```bash
./kato-manager.sh restart
```

#### build
Build or rebuild KATO Docker image.

```bash
./kato-manager.sh build

# Force rebuild with no cache
./kato-manager.sh build --no-cache
```

#### clean
Complete cleanup of containers, images, and volumes.

```bash
./kato-manager.sh clean
```

### Monitoring & Debugging

#### status
Show status of all KATO containers and services.

```bash
./kato-manager.sh status
```

Output shows:
- Container status (running/stopped)
- Port mappings
- Health check results
- Resource usage

#### logs
View container logs.

```bash
# KATO API logs
./kato-manager.sh logs kato

# MongoDB logs
./kato-manager.sh logs mongo

# All logs
./kato-manager.sh logs all

# Follow logs (real-time)
./kato-manager.sh logs kato -f
```

#### shell
Open interactive shell in running container.

```bash
./kato-manager.sh shell

# Execute specific command
./kato-manager.sh shell ls -la /app
```

## Docker Compose

### Basic docker-compose.yml

```yaml
version: '3.8'

services:
  mongodb:
    image: mongo:4.4
    container_name: mongo-kb
    volumes:
      - kato-mongo-data:/data/db
    networks:
      - kato-network

  kato-api:
    image: kato:latest
    container_name: kato-api
    ports:
      - "8000:8000"
    environment:
      - MONGO_BASE_URL=mongodb://mongodb:27017
      - LOG_LEVEL=INFO
      - PROCESSOR_ID=p46b6b076c
      - PROCESSOR_NAME=P1
    depends_on:
      - mongodb
    networks:
      - kato-network

networks:
  kato-network:
    driver: bridge

volumes:
  kato-mongo-data:
```

### Multi-Instance Deployment

```yaml
version: '3.8'

services:
  mongodb:
    image: mongo:4.4
    container_name: mongo-kb
    networks:
      - kato-network

  kato-1:
    image: kato:latest
    container_name: kato-instance-1
    environment:
      - PROCESSOR_ID=p001
      - PROCESSOR_NAME=Processor1
      - MONGO_BASE_URL=mongodb://mongodb:27017
    networks:
      - kato-network

  kato-2:
    image: kato:latest
    container_name: kato-instance-2
    environment:
      - PROCESSOR_ID=p002
      - PROCESSOR_NAME=Processor2
      - MONGO_BASE_URL=mongodb://mongodb:27017
    networks:
      - kato-network

  gateway:
    image: kato-gateway:latest
    container_name: kato-gateway
    ports:
      - "8000:8000"
    environment:
      - KATO_P001=kato-1:5555
      - KATO_P002=kato-2:5555
    networks:
      - kato-network

networks:
  kato-network:
    driver: bridge
```

## Dockerfile

The main KATO Dockerfile:

```dockerfile
FROM python:3.9-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY kato/ ./kato/
COPY setup.py .

# Install KATO package
RUN pip install -e .

# Expose ports
EXPOSE 8000 5555

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV LOG_LEVEL=INFO

# Entry point
CMD ["python", "-m", "kato.scripts.kato_engine"]
```

## Environment Variables

### Required Variables
- `PROCESSOR_ID`: Unique processor identifier
- `PROCESSOR_NAME`: Human-readable processor name

### Optional Variables
- `MONGO_BASE_URL`: MongoDB connection string (default: mongodb://localhost:27017)
- `LOG_LEVEL`: Logging level (DEBUG, INFO, WARNING, ERROR)
- `REST_PORT`: REST API port (default: 8000)
- `ZMQ_PORT`: ZeroMQ server port (default: 5555)

### Configuration Example

```bash
# .env file
PROCESSOR_ID=p46b6b076c
PROCESSOR_NAME=MainProcessor
MONGO_BASE_URL=mongodb://mongodb:27017
LOG_LEVEL=INFO
REST_PORT=8000
ZMQ_PORT=5555
MAX_PREDICTIONS=100
RECALL_THRESHOLD=0.1
```

## Health Checks

### Docker Health Check

Add to Dockerfile or docker-compose.yml:

```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8000/kato-api/ping"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 40s
```

### Manual Health Check

```bash
# Check KATO API
curl http://localhost:8000/kato-api/ping

# Check specific processor
curl http://localhost:8000/p46b6b076c/ping

# Check MongoDB connection
docker exec mongo-kb mongo --eval "db.adminCommand('ping')"
```

## Resource Management

### Memory Limits

```yaml
# docker-compose.yml
services:
  kato-api:
    mem_limit: 2g
    memswap_limit: 2g
```

### CPU Limits

```yaml
services:
  kato-api:
    cpus: '2.0'
    cpu_shares: 1024
```

## Logging

### Log Configuration

```bash
# Set log level via environment
LOG_LEVEL=DEBUG ./kato-manager.sh start

# Or in docker-compose.yml
environment:
  - LOG_LEVEL=DEBUG
```

### Log Files

Logs are stored in:
- Container logs: `docker logs kato-api-${USER}-1`
- Manager logs: `logs/kato-manager.log`
- Test logs: `logs/test-results.log`

### Log Rotation

```yaml
# docker-compose.yml
logging:
  driver: "json-file"
  options:
    max-size: "10m"
    max-file: "3"
```

## Troubleshooting

### Common Issues

#### Container Won't Start
```bash
# Check logs
docker logs kato-api-${USER}-1

# Rebuild image
./kato-manager.sh build --no-cache
./kato-manager.sh start
```

#### Port Already in Use
```bash
# Use different port
./kato-manager.sh start --port 9000

# Or find and kill process using port
lsof -i :8000
kill -9 <PID>
```

#### MongoDB Connection Issues
```bash
# Check MongoDB status
docker ps | grep mongo

# Restart MongoDB
docker restart mongo-kb-${USER}-1

# Check MongoDB logs
docker logs mongo-kb-${USER}-1
```

#### Permission Denied
```bash
# Fix script permissions
chmod +x kato-manager.sh

# Fix Docker socket permissions (Linux)
sudo usermod -aG docker $USER
newgrp docker
```

### Debug Commands

```bash
# List all KATO containers
docker ps -a | grep kato

# Inspect container
docker inspect kato-api-${USER}-1

# Check network
docker network inspect kato-network

# Check volumes
docker volume ls | grep kato

# Clean everything
docker system prune -a --volumes
```

## Production Deployment

### Security Considerations

1. **Use secrets management** for sensitive data
2. **Enable TLS** for external connections
3. **Set resource limits** to prevent resource exhaustion
4. **Use non-root user** in containers
5. **Regular security updates** of base images

### Monitoring

1. **Prometheus metrics** export (planned)
2. **Health check endpoints** for monitoring systems
3. **Log aggregation** with ELK stack or similar
4. **Performance metrics** via Docker stats

### Backup Strategy

```bash
# Backup MongoDB data
docker exec mongo-kb-${USER}-1 mongodump --out /backup
docker cp mongo-kb-${USER}-1:/backup ./mongo-backup

# Restore MongoDB data
docker cp ./mongo-backup mongo-kb-${USER}-1:/restore
docker exec mongo-kb-${USER}-1 mongorestore /restore
```

## CI/CD Integration

### GitHub Actions Example

```yaml
name: KATO CI/CD

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      
      - name: Build KATO
        run: ./kato-manager.sh build
      
      - name: Start KATO
        run: ./kato-manager.sh start
      
      - name: Run Tests
        run: |
          cd tests
          ./run_tests.sh
      
      - name: Stop KATO
        run: ./kato-manager.sh stop
```

### Docker Hub Publishing

```bash
# Tag image
docker tag kato:latest yourusername/kato:latest

# Push to registry
docker push yourusername/kato:latest
```

## Advanced Configuration

### Custom Network Configuration

```yaml
networks:
  kato-network:
    driver: bridge
    ipam:
      config:
        - subnet: 172.28.0.0/16
          gateway: 172.28.0.1
```

### Volume Mounts for Development

```yaml
services:
  kato-api:
    volumes:
      - ./kato:/app/kato  # Hot reload for development
      - ./tests:/app/tests
```

### Multi-Stage Build

```dockerfile
# Build stage
FROM python:3.9-slim as builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --user -r requirements.txt

# Runtime stage
FROM python:3.9-slim
WORKDIR /app
COPY --from=builder /root/.local /root/.local
COPY . .
ENV PATH=/root/.local/bin:$PATH
CMD ["python", "-m", "kato.scripts.kato_engine"]
```

## Support

For Docker-specific issues:
- Check [Docker documentation](https://docs.docker.com)
- Review [Troubleshooting Guide](../technical/TROUBLESHOOTING.md)
- Open an issue on GitHub