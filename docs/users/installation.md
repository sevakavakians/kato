# Installation Guide

Complete installation instructions for KATO on various platforms.

## System Requirements

### Minimum Requirements

- **CPU**: 2+ cores
- **RAM**: 4GB available
- **Disk**: 10GB free space
- **OS**: macOS, Linux, or Windows with WSL2
- **Docker Desktop**: Latest stable version

### Recommended Requirements

- **CPU**: 4+ cores
- **RAM**: 8GB available
- **Disk**: 20GB free space (for larger datasets)
- **OS**: macOS 12+, Ubuntu 20.04+, or Windows 11 with WSL2
- **Docker Desktop**: Latest version with Kubernetes support (optional)

### Network Requirements

KATO requires the following ports to be available:
- **8000**: KATO API (default, configurable)
- **8123**: ClickHouse HTTP
- **9000**: ClickHouse Native (optional)
- **6333**: Qdrant HTTP
- **6334**: Qdrant gRPC
- **6379**: Redis

## Installation Methods

### Method 1: Docker Compose (Recommended)

Docker Compose is the simplest way to get KATO running with all dependencies.

#### 1. Install Docker Desktop

**macOS**:
```bash
# Download from https://www.docker.com/products/docker-desktop
# Or using Homebrew:
brew install --cask docker
```

**Ubuntu/Debian**:
```bash
# Install Docker Engine
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Install Docker Compose
sudo apt-get update
sudo apt-get install docker compose-plugin

# Add user to docker group
sudo usermod -aG docker $USER
newgrp docker
```

**Windows (WSL2)**:
```powershell
# Download from https://www.docker.com/products/docker-desktop
# Ensure WSL2 backend is enabled in Docker Desktop settings
```

#### 2. Clone KATO Repository

```bash
git clone https://github.com/your-org/kato.git
cd kato
```

#### 3. Start KATO

```bash
# Start all services (KATO, ClickHouse, Qdrant, Redis)
./start.sh
```

The startup script will:
- Pull/build Docker images
- Start all required services
- Initialize databases
- Display service URLs

#### 4. Verify Installation

```bash
# Check service status
docker compose ps

# Test KATO API
curl http://localhost:8000/health

# Expected response:
# {"status": "healthy", "message": "KATO API is running"}
```

### Method 2: Manual Docker Setup

For more control over the deployment:

```bash
# Start ClickHouse
docker run -d --name kato-clickhouse \
  -p 8123:8123 -p 9000:9000 \
  -v kato-clickhouse-data:/var/lib/clickhouse \
  clickhouse/clickhouse-server:latest

# Start Qdrant
docker run -d --name kato-qdrant \
  -p 6333:6333 -p 6334:6334 \
  -v kato-qdrant-data:/qdrant/storage \
  qdrant/qdrant:latest

# Start Redis
docker run -d --name kato-redis \
  -p 6379:6379 \
  redis:7-alpine

# Build KATO image
docker build -t kato:latest .

# Start KATO
docker run -d --name kato \
  -p 8000:8000 \
  -e CLICKHOUSE_HOST=host.docker.internal \
  -e CLICKHOUSE_PORT=8123 \
  -e CLICKHOUSE_DB=kato \
  -e QDRANT_HOST=host.docker.internal \
  -e REDIS_URL=redis://host.docker.internal:6379 \
  kato:latest
```

**Note**: On Linux, replace `host.docker.internal` with your machine's IP address.

### Method 3: Kubernetes Deployment

For production deployments, see [Kubernetes Deployment Guide](../operations/kubernetes-deployment.md).

## Configuration

### Environment Variables

Create a `.env` file in the KATO directory:

```bash
# Service Configuration
LOG_LEVEL=INFO
LOG_FORMAT=human

# Database Configuration
CLICKHOUSE_HOST=localhost
CLICKHOUSE_PORT=8123
CLICKHOUSE_DB=kato
QDRANT_HOST=localhost
QDRANT_PORT=6333
REDIS_URL=redis://localhost:6379

# Learning Configuration
MAX_PATTERN_LENGTH=0
RECALL_THRESHOLD=0.1
STM_MODE=CLEAR

# Session Configuration
SESSION_TTL=3600
SESSION_AUTO_EXTEND=true
```

For complete configuration options, see [Configuration Guide](configuration.md) and [Environment Variables Reference](../reference/configuration-vars.md).

### Custom Port Configuration

```bash
# Start KATO on custom port
PORT=9000 ./start.sh

# Or set in .env file
echo "PORT=9000" >> .env
./start.sh
```

## Post-Installation

### Verify All Services

```bash
# Check all services are running
docker compose ps

# Expected output:
# NAME                STATUS
# kato                Up (healthy)
# kato-clickhouse     Up
# kato-qdrant         Up
# kato-redis          Up
```

### Access API Documentation

Open in browser:
- **API Docs**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### Run Test Suite

```bash
# Ensure services are running first
./start.sh

# Run all tests
./run_tests.sh --no-start --no-stop

# Expected output should show passing tests
```

For detailed testing information, see [Testing Guide](../developers/testing.md).

### Create Your First Session

```bash
# Create session
SESSION=$(curl -s -X POST http://localhost:8000/sessions \
  -H "Content-Type: application/json" \
  -d '{"node_id": "my_first_kato"}' | jq -r '.session_id')

echo "Session created: $SESSION"

# Send first observation
curl -X POST http://localhost:8000/sessions/$SESSION/observe \
  -H "Content-Type: application/json" \
  -d '{"strings": ["hello", "world"], "vectors": [], "emotives": {}}'
```

For complete walkthrough, see [First Session Guide](first-session.md).

## Upgrading KATO

### From Docker Compose

```bash
# Stop KATO
docker compose down

# Pull latest changes
git pull

# Rebuild images
docker compose build --no-cache

# Restart KATO
./start.sh
```

**Important**: Data in ClickHouse, Redis, and Qdrant persists across upgrades via Docker volumes.

### Backup Before Upgrade

```bash
# Backup ClickHouse data
docker exec kato-clickhouse clickhouse-client --query "BACKUP DATABASE kato TO Disk('backups', 'backup-$(date +%Y%m%d)')"

# Backup Qdrant (optional - can recreate from ClickHouse)
docker cp kato-qdrant:/qdrant/storage ./qdrant-backup-$(date +%Y%m%d)
```

## Uninstalling KATO

### Remove Containers Only (Keep Data)

```bash
# Stop and remove containers
docker compose down
```

Data persists in Docker volumes and can be restored by running `./start.sh` again.

### Complete Removal (Including Data)

```bash
# Stop and remove everything
docker compose down -v

# Remove Docker images
docker rmi kato:latest
docker rmi clickhouse/clickhouse-server:latest
docker rmi qdrant/qdrant:latest
docker rmi redis:7-alpine
```

**Warning**: This permanently deletes all patterns, sessions, and training data.

## Troubleshooting Installation

### Docker Not Found

**Error**: `docker: command not found`

**Solution**:
1. Install Docker Desktop from https://www.docker.com/products/docker-desktop
2. Start Docker Desktop
3. Verify installation: `docker --version`

### Port Already in Use

**Error**: `Error starting userland proxy: listen tcp4 0.0.0.0:8000: bind: address already in use`

**Solution**:
```bash
# Find what's using the port
lsof -i :8000  # macOS/Linux
netstat -ano | findstr :8000  # Windows

# Kill the process or use different port
PORT=9000 ./start.sh
```

### Permission Denied

**Error**: `permission denied while trying to connect to the Docker daemon socket`

**Solution**:
```bash
# Add user to docker group (Linux)
sudo usermod -aG docker $USER
newgrp docker

# Or run with sudo (not recommended)
sudo ./start.sh
```

### Container Fails to Start

**Error**: Container exits immediately after starting

**Solution**:
```bash
# Check logs
docker compose logs kato

# Common fixes:
# 1. Ensure ClickHouse/Qdrant/Redis are running first
docker compose up -d clickhouse qdrant redis
docker compose up -d kato

# 2. Rebuild without cache
docker compose build --no-cache kato
./start.sh
```

For more troubleshooting, see [Troubleshooting Guide](troubleshooting.md).

## Getting Help

- **Documentation**: [docs/00-START-HERE.md](../00-START-HERE.md)
- **Quick Start**: [quick-start.md](quick-start.md)
- **Configuration**: [configuration.md](configuration.md)
- **Troubleshooting**: [troubleshooting.md](troubleshooting.md)
- **GitHub Issues**: https://github.com/your-org/kato/issues

## Next Steps

1. Complete [First Session Tutorial](first-session.md)
2. Read [Core Concepts](concepts.md)
3. Explore [API Reference](../reference/api/)
4. Try [Example Applications](examples/)

---

**Last Updated**: November 2025
**KATO Version**: 3.0+
