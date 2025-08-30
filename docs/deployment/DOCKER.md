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
2. **MongoDB Container**: `mongo-kb-${USER}-1` - Shared persistent data storage
3. **KATO Processor Containers**: Named by processor ID - Individual processors
4. **Volume**: `kato-mongo-data` - MongoDB data persistence

### Container Naming

#### Single Instance Mode (Default)
When started without specifying an ID, containers use default naming:
- KATO API: `kato-api-${USER}-1`
- MongoDB: `mongo-kb-${USER}-1`

#### Multi-Instance Mode
When started with `--id` flag, containers are named by processor ID:
- KATO Processor: `kato-${PROCESSOR_ID}`
- MongoDB: `mongo-kb-${USER}-1` (shared across all instances)

Examples:
```bash
./kato-manager.sh start --id processor-1  # Creates: kato-processor-1
./kato-manager.sh start --id nlp-engine   # Creates: kato-nlp-engine
```

## Management Commands

### System Management

#### start
Start KATO processor instance(s) with MongoDB backend.

```bash
# Start default instance
./kato-manager.sh start

# Start with custom parameters
./kato-manager.sh start --name "MyProcessor" --port 9000

# Start multiple instances
./kato-manager.sh start --id processor-1 --name "Main" --port 8001
./kato-manager.sh start --id processor-2 --name "Secondary" --port 8002
```

#### stop
Stop KATO instance(s) and automatically remove containers.

```bash
# Stop all instances (prompts for MongoDB removal)
./kato-manager.sh stop

# Stop specific instance by ID or name
./kato-manager.sh stop processor-1         # By ID
./kato-manager.sh stop "Main"              # By name

# Stop with explicit options
./kato-manager.sh stop --id processor-1    # Specific ID
./kato-manager.sh stop --name "Main"       # Specific name
./kato-manager.sh stop --all               # All instances
./kato-manager.sh stop --all --with-mongo  # All + MongoDB
./kato-manager.sh stop --all --no-mongo    # All, keep MongoDB
```

**Note**: Containers are automatically removed after stopping to prevent accumulation.

#### list
Show all registered KATO instances.

```bash
./kato-manager.sh list
```

Output:
```
KATO Instances:
===============
ID                   Name                 Status     API Port   ZMQ Port   Container
----------------------------------------------------------------------------------------------------
processor-1          Main                 running    8001       5556       kato-processor-1
processor-2          Secondary            running    8002       5557       kato-processor-2
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
./kato-manager.sh stop processor-1
docker ps -a | grep processor-1  # No results - container removed
```

### MongoDB Container

MongoDB container is shared across all instances and handled separately:

- **Preserved by default**: Stop commands don't remove MongoDB unless specified
- **Explicit removal**: Use `--with-mongo` flag to also stop and remove MongoDB
- **Manual removal**: `docker rm mongo-kb-${USER}-1`

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

#### Using kato-manager.sh (Recommended)

The easiest way to deploy multiple instances:

```bash
# Start multiple instances with different configurations
./kato-manager.sh start --id sentiment --name "Sentiment Analysis" --port 8001
./kato-manager.sh start --id classifier --name "Text Classifier" --port 8002 --indexer-type VI
./kato-manager.sh start --id learner --name "Sequence Learner" --port 8003 --max-seq-length 10

# View all instances
./kato-manager.sh list

# Each instance has its own API endpoint
curl http://localhost:8001/sentiment/ping
curl http://localhost:8002/classifier/ping
curl http://localhost:8003/learner/ping
```

#### Using docker-compose-multi.yml

For production deployments with predefined instances:

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

  kato-sentiment:
    image: kato:latest
    container_name: kato-sentiment
    ports:
      - "8001:8000"
    environment:
      - PROCESSOR_ID=sentiment
      - PROCESSOR_NAME=Sentiment
      - MONGO_BASE_URL=mongodb://mongodb:27017
      - MAX_PREDICTIONS=50
    networks:
      - kato-network
    depends_on:
      - mongodb

  kato-classifier:
    image: kato:latest
    container_name: kato-classifier
    ports:
      - "8002:8000"
    environment:
      - PROCESSOR_ID=classifier
      - PROCESSOR_NAME=Classifier
      - INDEXER_TYPE=VI
      - MONGO_BASE_URL=mongodb://mongodb:27017
    networks:
      - kato-network
    depends_on:
      - mongodb

volumes:
  kato-mongo-data:

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
          ./test-harness.sh build
          ./kato-manager.sh test
      
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