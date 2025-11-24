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
docker-compose build

# Start KATO system
./start.sh

# Check status
docker-compose ps

# View logs
docker-compose logs

# Stop system
docker-compose down
```

## Docker Architecture

KATO creates the following Docker resources:

1. **Network**: `kato-network` - Isolated network for containers
2. **ClickHouse Container**: `clickhouse` - Pattern data storage with multi-stage filter pipeline
3. **Redis Container**: `redis` - Session management and pattern metadata
4. **Qdrant Container**: `qdrant` - Vector embeddings storage
5. **KATO Processor Containers**: Named by processor ID - Individual processors
6. **Volumes**:
   - `clickhouse-data` - ClickHouse data persistence
   - `redis-data` - Redis data persistence
   - `qdrant-data` - Qdrant data persistence

### Container Naming

#### Single Instance Mode (Default)
When started without specifying an ID, containers use default naming:
- KATO API: `kato-api-${USER}-1`
- ClickHouse: `clickhouse` (shared across all instances)
- Redis: `redis` (shared across all instances)
- Qdrant: `qdrant` (shared across all instances)

#### Multi-Instance Mode
When started with `--id` flag, containers are named by processor ID:
- KATO Processor: `kato-${PROCESSOR_ID}`
- ClickHouse: `clickhouse` (shared across all instances)
- Redis: `redis` (shared across all instances)
- Qdrant: `qdrant` (shared across all instances)

Examples:
```bash
./start.sh --id processor-1  # Creates: kato-processor-1
./start.sh --id nlp-engine   # Creates: kato-nlp-engine
```

## Management Commands

### System Management

#### start
Start KATO processor instance(s) with ClickHouse/Redis/Qdrant backend.

```bash
# Start default instance
./start.sh

# Start with custom parameters
./start.sh --name "MyProcessor" --port 9000

# Start multiple instances
./start.sh --id processor-1 --name "Main" --port 8001
./start.sh --id processor-2 --name "Secondary" --port 8002
```

#### stop
Stop KATO instance(s) and automatically remove containers.

```bash
# Stop all instances
docker-compose down

# Stop specific instance by ID or name
docker-compose down processor-1         # By ID
docker-compose down "Main"              # By name

# Stop with explicit options
docker-compose down --id processor-1    # Specific ID
docker-compose down --name "Main"       # Specific name
docker-compose down --all               # All instances
```

**Note**: Containers are automatically removed after stopping to prevent accumulation. Storage services (ClickHouse, Redis, Qdrant) are shared and persist.

#### list
Show all registered KATO instances.

```bash
./kato-manager.sh list
```

Output:
```
KATO FastAPI Services Status:

NAME           IMAGE               COMMAND                  SERVICE        STATUS    PORTS
kato           kato:latest         "uvicorn kato.servic…"   kato           healthy   0.0.0.0:8001->8000/tcp
kato-testing   kato:latest         "uvicorn kato.servic…"   kato-testing   healthy   0.0.0.0:8002->8000/tcp
clickhouse     clickhouse/clickhouse-server   clickhouse         healthy   0.0.0.0:8123->8123/tcp
redis          redis:7-alpine      redis-server             redis          healthy   0.0.0.0:6379->6379/tcp
qdrant         qdrant/qdrant       entrypoint.sh            qdrant         running   0.0.0.0:6333->6333/tcp
```

#### restart
Restart KATO system (stop + start).

```bash
docker-compose restart
```

#### build
Build or rebuild KATO Docker image.

```bash
docker-compose build

# Force rebuild with no cache
docker-compose build --no-cache
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
docker-compose ps
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
docker-compose logs kato

# ClickHouse logs
docker-compose logs clickhouse

# Redis logs
docker-compose logs redis

# All logs
docker-compose logs all

# Follow logs (real-time)
docker-compose logs kato -f
```

#### shell
Open interactive shell in running container.

```bash
./kato-manager.sh shell

# Execute specific command
./kato-manager.sh shell ls -la /app
```

## Container Lifecycle Management

### Automatic Container Removal

KATO now implements automatic container cleanup to prevent Docker resource accumulation:

1. **On Stop**: When you stop an instance, the container is automatically removed
2. **Registry Sync**: The instance registry is updated to reflect container removal
3. **No Orphans**: Prevents accumulation of stopped containers

### Container States

```bash
# Check all KATO containers (running and stopped)
docker ps -a | grep kato

# After using stop command - container is removed
docker-compose down processor-1
docker ps -a | grep processor-1  # No results - container removed
```

### Storage Containers

Storage containers (ClickHouse, Redis, Qdrant) are shared across all instances and persist:

- **Preserved by default**: Stop commands don't remove storage containers
- **Data persistence**: Volume data persists across container restarts
- **Manual removal**: `docker-compose down -v` (removes volumes - use with caution)

## Docker Compose

### Basic docker-compose.yml

```yaml
version: '3.8'

services:
  clickhouse:
    image: clickhouse/clickhouse-server:latest
    container_name: clickhouse
    volumes:
      - clickhouse-data:/var/lib/clickhouse
    networks:
      - kato-network

  redis:
    image: redis:7-alpine
    container_name: redis
    volumes:
      - redis-data:/data
    networks:
      - kato-network

  qdrant:
    image: qdrant/qdrant:latest
    container_name: qdrant
    volumes:
      - qdrant-data:/qdrant/storage
    networks:
      - kato-network

  kato-api:
    image: kato:latest
    container_name: kato-api
    ports:
      - "8000:8000"
    environment:
      - CLICKHOUSE_HOST=clickhouse
      - CLICKHOUSE_PORT=8123
      - CLICKHOUSE_DB=kato
      - REDIS_HOST=redis
      - REDIS_PORT=6379
      - QDRANT_HOST=qdrant
      - QDRANT_PORT=6333
      - LOG_LEVEL=INFO
      - PROCESSOR_ID=p46b6b076c
      - PROCESSOR_NAME=P1
    depends_on:
      - clickhouse
      - redis
      - qdrant
    networks:
      - kato-network

networks:
  kato-network:
    driver: bridge

volumes:
  clickhouse-data:
  redis-data:
  qdrant-data:
```

### Multi-Instance Deployment

#### Using kato-manager.sh (Recommended)

The easiest way to deploy multiple instances:

```bash
# Start multiple instances with different configurations
./start.sh --id sentiment --name "Sentiment Analysis" --port 8001
./start.sh --id classifier --name "Text Classifier" --port 8002 --indexer-type VI
./start.sh --id learner --name "Pattern Learner" --port 8003 --max-seq-length 10

# View all instances
./kato-manager.sh list

# Each instance has its own API endpoint
curl http://localhost:8000/sentiment/ping
curl http://localhost:8000/classifier/ping
curl http://localhost:8000/learner/ping
```

#### Using docker-compose-multi.yml

For production deployments with predefined instances:

```yaml
version: '3.8'

services:
  clickhouse:
    image: clickhouse/clickhouse-server:latest
    volumes:
      - clickhouse-data:/var/lib/clickhouse
    networks:
      - kato-network

  redis:
    image: redis:7-alpine
    volumes:
      - redis-data:/data
    networks:
      - kato-network

  qdrant:
    image: qdrant/qdrant:latest
    volumes:
      - qdrant-data:/qdrant/storage
    networks:
      - kato-network

  kato-sentiment:
    image: kato:latest
    container_name: kato-sentiment
    ports:
      - "8001:8000"
    environment:
      - PROCESSOR_ID=sentiment
      - PROCESSOR_NAME=Sentiment
      - CLICKHOUSE_HOST=clickhouse
      - CLICKHOUSE_PORT=8123
      - REDIS_HOST=redis
      - QDRANT_HOST=qdrant
      - MAX_PREDICTIONS=50
    networks:
      - kato-network
    depends_on:
      - clickhouse
      - redis
      - qdrant

  kato-classifier:
    image: kato:latest
    container_name: kato-classifier
    ports:
      - "8002:8000"
    environment:
      - PROCESSOR_ID=classifier
      - PROCESSOR_NAME=Classifier
      - INDEXER_TYPE=VI
      - CLICKHOUSE_HOST=clickhouse
      - REDIS_HOST=redis
      - QDRANT_HOST=qdrant
    networks:
      - kato-network
    depends_on:
      - clickhouse
      - redis
      - qdrant

volumes:
  clickhouse-data:
  redis-data:
  qdrant-data:

networks:
  kato-network:
    driver: bridge
```

Deploy with:
```bash
docker-compose -f docker-compose-multi.yml up -d
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
- `CLICKHOUSE_HOST`: ClickHouse host (default: localhost)
- `CLICKHOUSE_PORT`: ClickHouse HTTP port (default: 8123)
- `CLICKHOUSE_DB`: ClickHouse database name (default: kato)
- `REDIS_HOST`: Redis host (default: localhost)
- `REDIS_PORT`: Redis port (default: 6379)
- `QDRANT_HOST`: Qdrant host (default: localhost)
- `QDRANT_PORT`: Qdrant port (default: 6333)
- `LOG_LEVEL`: Logging level (DEBUG, INFO, WARNING, ERROR)

### Configuration Example

```bash
# .env file
PROCESSOR_ID=primary
PROCESSOR_NAME=PrimaryProcessor
CLICKHOUSE_HOST=clickhouse
CLICKHOUSE_PORT=8123
CLICKHOUSE_DB=kato
REDIS_HOST=redis
REDIS_PORT=6379
QDRANT_HOST=qdrant
QDRANT_PORT=6333
LOG_LEVEL=INFO
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

# Check ClickHouse connection
docker exec clickhouse clickhouse-client --query "SELECT 1"

# Check Redis connection
docker exec redis redis-cli ping
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
LOG_LEVEL=DEBUG ./start.sh

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
docker-compose build --no-cache
./start.sh
```

#### Port Already in Use
```bash
# Use different port
./start.sh --port 9000

# Or find and kill process using port
lsof -i :8000
kill -9 <PID>
```

#### Storage Connection Issues
```bash
# Check ClickHouse status
docker ps | grep clickhouse
docker restart clickhouse
docker logs clickhouse

# Check Redis status
docker ps | grep redis
docker restart redis
docker logs redis

# Check Qdrant status
docker ps | grep qdrant
docker restart qdrant
docker logs qdrant
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
# Backup ClickHouse data
docker exec clickhouse clickhouse-client --query "BACKUP DATABASE kato TO Disk('backups', 'backup.zip')"
docker cp clickhouse:/var/lib/clickhouse/backups/backup.zip ./clickhouse-backup.zip

# Backup Redis data
docker exec redis redis-cli SAVE
docker cp redis:/data/dump.rdb ./redis-backup.rdb

# Backup Qdrant data
docker cp qdrant:/qdrant/storage ./qdrant-backup
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
        run: docker-compose build
      
      - name: Start KATO
        run: ./start.sh
      
      - name: Run Tests
        run: |
          ./test-harness.sh build
          ./kato-manager.sh test
      
      - name: Stop KATO
        run: docker-compose down
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

## Test Container Architecture

KATO uses a sophisticated clustered test harness with containerized testing:

### Test Harness Container

The test harness runs tests in isolated containers with complete database separation:

```dockerfile
# Dockerfile.test
FROM python:3.9-slim
WORKDIR /tests
COPY requirements-test.txt .
RUN pip install -r requirements-test.txt
COPY tests/ /tests/
CMD ["python", "-m", "pytest"]
```

### Clustered Test Execution

Each test cluster gets its own isolated environment:

```bash
# Build test harness container
./test-harness.sh build

# Run tests with automatic clustering
./test-harness.sh test
```

**Architecture Overview:**
```
Test Harness Container
    ↓
Cluster Orchestrator (on host)
    ↓
For each cluster:
    ├── KATO Instance (kato-cluster_<name>_<id>)
    ├── ClickHouse (clickhouse-cluster_<name>_<id>)
    ├── Redis (redis-cluster_<name>_<id>)
    ├── Qdrant (qdrant-cluster_<name>_<id>)
```

### Key Features

1. **Complete Isolation**: Each cluster runs with dedicated databases
2. **Unique Processor IDs**: Format: `cluster_<name>_<timestamp>_<uuid>`
3. **Network Isolation**: All containers on `kato-network`
4. **Automatic Cleanup**: Containers removed after tests complete
5. **Configuration Flexibility**: Different clusters can have different settings

### Test Container Environment Variables

```bash
# Set by cluster orchestrator
KATO_CLUSTER_MODE=true
KATO_TEST_MODE=container
KATO_PROCESSOR_ID=cluster_default_123456_abc
KATO_API_URL=http://kato-cluster_default_123456_abc:8000
CLICKHOUSE_HOST=clickhouse-cluster_default_123456_abc
CLICKHOUSE_PORT=8123
REDIS_URL=redis://redis-cluster_default_123456_abc:6379
QDRANT_URL=http://qdrant-cluster_default_123456_abc:6333
```

### Running Tests in CI/CD

```yaml
# Example GitHub Actions
- name: Build test harness
  run: ./test-harness.sh build

- name: Run clustered tests
  run: ./test-harness.sh test

- name: Upload results
  uses: actions/upload-artifact@v2
  with:
    name: test-results
    path: logs/test-runs/
```

### Debugging Test Containers

```bash
# Get shell in test container
./test-harness.sh shell

# View running test containers
docker ps | grep cluster_

# Check logs for specific cluster
docker logs kato-cluster_default_<id>

# Inspect test network
docker network inspect kato-network
```

## Support

For Docker-specific issues:
- Check [Docker documentation](https://docs.docker.com)
- Review [Troubleshooting Guide](../technical/TROUBLESHOOTING.md)
- See [Testing Guide](../developers/testing.md) for test-specific help
- Open an issue on GitHub