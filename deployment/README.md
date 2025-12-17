# KATO Production Deployment

This directory contains everything needed to deploy KATO using pre-built container images from GitHub Container Registry.

**No source code required** - just these deployment files!

## What is KATO?

KATO (Knowledge Abstraction for Traceable Outcomes) is a deterministic memory and prediction system for transparent, explainable AI. It processes multi-modal observations and makes temporal predictions while maintaining complete transparency and traceability.

## Quick Start

### Prerequisites

- Docker Engine 20.10+ or Docker Desktop
- Docker Compose 2.0+
- 4GB+ available RAM
- Ports available: 8000, 8123, 9000, 6333, 6379, 3001 (optional)

### Fastest Setup

```bash
# Download deployment files
curl -L https://github.com/sevakavakians/kato/archive/main.tar.gz | tar xz
cd kato-main/deployment

# Start all services
./kato-manager.sh start

# Verify
./kato-manager.sh status
```

**Access KATO:**
- API: http://localhost:8000
- Interactive Docs: http://localhost:8000/docs
- Health Check: http://localhost:8000/health
- Dashboard UI: http://localhost:3001 (optional monitoring interface)

**See [Deployment Options](#deployment-options) below for alternative installation methods.**

## Deployment Options

Choose the deployment method that best fits your needs:

### Option 1: Copy Deployment Directory (Recommended for Production)

**Best for:** Remote servers, production deployments, minimal footprint

**What you need:** Just the 4 files in this `deployment/` directory

**Steps:**

1. **Copy deployment files to your remote machine:**
   ```bash
   # From your local machine
   scp -r deployment/ user@remote-machine:/opt/kato/

   # Or use rsync
   rsync -av deployment/ user@remote-machine:/opt/kato/
   ```

2. **On the remote machine:**
   ```bash
   cd /opt/kato
   ./kato-manager.sh start
   ```

3. **Verify installation:**
   ```bash
   ./kato-manager.sh status
   ```

**Advantages:**
- ✅ Minimal footprint (only 4 small files needed)
- ✅ No source code required
- ✅ Easy to manage with included `kato-manager.sh` script
- ✅ Simple updates: `./kato-manager.sh update`
- ✅ Clean separation from development environment

**Files included:**
- `docker-compose.yml` - Service orchestration
- `kato-manager.sh` - Management script
- `.env.example` - Configuration template
- `README.md` - This documentation

### Option 2: Download from GitHub

**Best for:** Quick setup, trying KATO, automated deployments

**Steps:**

```bash
# Using curl
curl -L https://github.com/sevakavakians/kato/archive/main.tar.gz | tar xz
cd kato-main/deployment
./kato-manager.sh start

# Using wget
wget -O- https://github.com/sevakavakians/kato/archive/main.tar.gz | tar xz
cd kato-main/deployment
./kato-manager.sh start

# Download specific version
curl -L https://github.com/sevakavakians/kato/archive/v1.2.3.tar.gz | tar xz
cd kato-1.2.3/deployment
./kato-manager.sh start

# Clone entire repository
git clone https://github.com/sevakavakians/kato.git
cd kato/deployment
./kato-manager.sh start
```

**Advantages:**
- ✅ Always get latest version
- ✅ Can specify exact version tags
- ✅ No manual file transfers
- ✅ Good for CI/CD pipelines

### Option 3: Manual Docker Commands

**Best for:** Custom setups, testing, environments without docker compose

**No files required** - just run these commands:

```bash
# 1. Create network
docker network create kato-network --subnet 172.28.0.0/16

# 2. Start ClickHouse
docker run -d \
  --name kato-clickhouse \
  --network kato-network \
  -p 8123:8123 \
  -p 9000:9000 \
  -v kato-clickhouse-data:/var/lib/clickhouse \
  --restart unless-stopped \
  --ulimit nofile=262144:262144 \
  clickhouse/clickhouse-server:latest

# 3. Start Qdrant
docker run -d \
  --name kato-qdrant \
  --network kato-network \
  -p 6333:6333 \
  -v kato-qdrant-data:/qdrant/storage \
  --restart unless-stopped \
  qdrant/qdrant:latest

# 4. Start Redis
docker run -d \
  --name kato-redis \
  --network kato-network \
  -p 6379:6379 \
  -v kato-redis-data:/data \
  --restart unless-stopped \
  redis:7-alpine \
  redis-server --save "" --appendonly no

# 5. Wait for databases to be ready
sleep 10

# 6. Start KATO
docker run -d \
  --name kato \
  --network kato-network \
  -p 8000:8000 \
  --restart unless-stopped \
  -e SERVICE_NAME=kato \
  -e CLICKHOUSE_HOST=kato-clickhouse \
  -e CLICKHOUSE_PORT=9000 \
  -e CLICKHOUSE_DB=kato \
  -e QDRANT_HOST=kato-qdrant \
  -e QDRANT_PORT=6333 \
  -e REDIS_URL=redis://kato-redis:6379 \
  -e LOG_LEVEL=INFO \
  -e SESSION_TTL=3600 \
  -e SESSION_AUTO_EXTEND=true \
  -e KATO_BATCH_SIZE=10000 \
  -e CONNECTION_POOL_SIZE=50 \
  -e REQUEST_TIMEOUT=120.0 \
  ghcr.io/sevakavakians/kato:latest

# 7. Start Dashboard (Optional)
docker run -d \
  --name kato-dashboard \
  --network kato-network \
  -p 3001:3001 \
  --restart unless-stopped \
  -e KATO_API_URL=http://kato:8000 \
  -e CLICKHOUSE_HOST=kato-clickhouse \
  -e CLICKHOUSE_HTTP_PORT=8123 \
  -e CLICKHOUSE_DB=kato \
  -e QDRANT_URL=http://kato-qdrant:6333 \
  -e REDIS_URL=redis://kato-redis:6379 \
  -e USE_HYBRID_PATTERNS=true \
  -e ADMIN_USERNAME=admin \
  -e ADMIN_PASSWORD=changeme \
  -e SECRET_KEY=change-this-in-production \
  -v /var/run/docker.sock:/var/run/docker.sock:rw \
  ghcr.io/sevakavakians/kato-dashboard:latest

# 8. Check health
sleep 5
curl http://localhost:8000/health
curl http://localhost:3001/health  # Dashboard health (if started)
```

**Management commands:**
```bash
# View logs
docker logs kato --tail 50
docker logs kato -f
docker logs kato-dashboard --tail 50  # Dashboard logs

# Restart services
docker restart kato
docker restart kato-dashboard
docker restart kato-clickhouse kato-qdrant kato-redis

# Stop all services
docker stop kato kato-dashboard kato-clickhouse kato-qdrant kato-redis

# Start all services
docker start kato-clickhouse kato-qdrant kato-redis kato kato-dashboard

# Update KATO
docker pull ghcr.io/sevakavakians/kato:latest
docker stop kato
docker rm kato
# Then run the KATO docker run command again (step 6 above)

# Update Dashboard
docker pull ghcr.io/sevakavakians/kato-dashboard:latest
docker stop kato-dashboard
docker rm kato-dashboard
# Then run the Dashboard docker run command again (step 7 above)

# Clean up everything
docker stop kato kato-dashboard kato-clickhouse kato-qdrant kato-redis
docker rm kato kato-dashboard kato-clickhouse kato-qdrant kato-redis
docker network rm kato-network
docker volume rm kato-clickhouse-data kato-qdrant-data kato-redis-data
```

**Advantages:**
- ✅ No files required at all
- ✅ Works without docker compose
- ✅ Full control over every parameter
- ✅ Easy to customize and modify
- ✅ Good for scripting and automation

**Disadvantages:**
- ❌ More verbose commands
- ❌ Manual service orchestration
- ❌ No built-in management scripts

### Comparison Table

| Feature | Copy Directory | Download from GitHub | Manual Docker |
|---------|---------------|---------------------|---------------|
| **Files needed** | 4 files | Internet access | None |
| **Setup complexity** | Low | Low | Medium |
| **Management ease** | Excellent (`kato-manager.sh`) | Excellent (`kato-manager.sh`) | Manual |
| **Customization** | Easy (edit files) | Easy (edit files) | Very Easy (modify commands) |
| **Updates** | `./kato-manager.sh update` | `./kato-manager.sh update` | Manual pull & restart |
| **Best for** | Production servers | Quick testing | Custom setups |
| **Version control** | Manual | Easy (git tags) | Manual |

### Recommendation

- **Production deployments**: Use **Option 1** (Copy Directory) for minimal footprint and easy management
- **Quick testing/evaluation**: Use **Option 2** (Download from GitHub) for fastest setup
- **Custom configurations**: Use **Option 3** (Manual Docker) for full control without files

## Usage

### Service Management

```bash
# Start all services
./kato-manager.sh start

# Stop all services
./kato-manager.sh stop

# Restart all services
./kato-manager.sh restart

# Check service status
./kato-manager.sh status
```

### Individual Services

```bash
# Start/stop/restart individual services
./kato-manager.sh start clickhouse
./kato-manager.sh restart kato
./kato-manager.sh stop redis
```

### Updates

```bash
# Update KATO to latest version
./kato-manager.sh update

# Or manually pull and restart
./kato-manager.sh pull
./kato-manager.sh restart kato
```

### Logs

```bash
# View recent logs (default: 50 lines)
./kato-manager.sh logs kato

# View more lines
./kato-manager.sh logs kato 200

# Follow logs in real-time
./kato-manager.sh follow kato
```

### Data Management

```bash
# Clear all data (keeps services running)
./kato-manager.sh clean-data

# Remove all containers and volumes
./kato-manager.sh clean
```

## Configuration

### Basic Configuration

Create a `.env` file to customize settings:

```bash
cp .env.example .env
# Edit .env with your preferred settings
./kato-manager.sh restart
```

### Available Settings

See `.env.example` for all configurable options including:

- **Session Management**: TTL, auto-extension
- **Performance**: Batch sizes, connection pools, timeouts
- **Logging**: Log levels
- **Learning**: Auto-learning, pattern matching thresholds
- **Database**: Connection URLs

### Port Customization

To use different ports, edit `docker-compose.yml`:

```yaml
ports:
  - "YOUR_PORT:8000"  # Change YOUR_PORT to desired port
```

## Architecture

KATO deployment includes five services:

1. **KATO Service** (Port 8000)
   - FastAPI application serving the AI engine
   - Processes observations and generates predictions
   - Uses pre-built image from `ghcr.io/sevakavakians/kato:latest`

2. **ClickHouse** (Ports 8123 HTTP, 9000 Native)
   - High-performance columnar pattern data storage
   - Multi-stage filter pipeline for billion-scale performance
   - kb_id partitioning for node isolation

3. **Qdrant** (Port 6333)
   - Vector database for semantic search
   - HNSW indexing for fast similarity matching

4. **Redis** (Port 6379)
   - Session state management
   - Pattern metadata (frequency, emotives)
   - High-speed caching

5. **Dashboard** (Port 3001) - Optional
   - Web-based monitoring and management interface
   - Real-time metrics visualization
   - Session and database management
   - Uses pre-built image from `ghcr.io/sevakavakians/kato-dashboard:latest`

All services communicate via a private Docker network (`kato-network`) and persist data in Docker volumes.

## API Usage

### Basic Example

```bash
# Create a session
curl -X POST http://localhost:8000/sessions/create \
  -H "Content-Type: application/json"

# Response: {"session_id": "sess_abc123..."}

# Make observations
curl -X POST http://localhost:8000/sessions/sess_abc123/observe \
  -H "Content-Type: application/json" \
  -d '{"strings": ["hello", "world"]}'

# Learn patterns
curl -X POST http://localhost:8000/sessions/sess_abc123/learn

# Get predictions
curl http://localhost:8000/sessions/sess_abc123/predictions
```

### Interactive API Documentation

Visit http://localhost:8000/docs for:
- Full API reference
- Interactive request testing
- Request/response schemas
- Authentication details

## Dashboard (Optional)

KATO Dashboard provides a web-based monitoring and management interface for comprehensive system oversight.

### Features

- **Real-Time Monitoring**: Live system metrics, performance stats, and resource usage
- **Session Management**: View and manage active KATO sessions with detailed insights
- **Database Analytics**: Browse and analyze ClickHouse patterns, Qdrant vectors, and Redis cache
- **Performance Insights**: Detailed charts and visualizations for system performance
- **Pattern Analysis**: Explore learned patterns, frequencies, and emotive data
- **Container Monitoring**: Real-time Docker container stats and health checks

### Access

- **Dashboard UI**: http://localhost:3001
- **Default Login**: `admin` / `changeme` (⚠️ **CHANGE IN PRODUCTION!**)

### Managing Dashboard

The dashboard starts automatically with other services:

```bash
# Start all services (including dashboard)
./kato-manager.sh start

# Start dashboard separately
./kato-manager.sh start dashboard

# Check dashboard status
./kato-manager.sh status

# View dashboard logs
./kato-manager.sh logs dashboard

# Stop dashboard (keeps KATO running)
./kato-manager.sh stop dashboard
```

### Security

⚠️ **IMPORTANT**: Change default credentials before production deployment!

Edit `.env` file:
```env
DASHBOARD_ADMIN_USERNAME=your-username
DASHBOARD_ADMIN_PASSWORD=your-secure-password
DASHBOARD_SECRET_KEY=your-random-secret-key
```

Then restart:
```bash
./kato-manager.sh restart dashboard
```

### Features Overview

| Feature | Description |
|---------|-------------|
| **System Metrics** | CPU, memory, disk usage for all containers |
| **Session Browser** | View active sessions, STM contents, and configurations |
| **Pattern Explorer** | Search and analyze patterns across all knowledgebases |
| **Database Tools** | Direct access to ClickHouse, Qdrant, and Redis data |
| **Performance Charts** | Historical trends and real-time performance graphs |
| **Container Stats** | Per-container resource monitoring via Docker API |

### Optional Service

The dashboard is **completely optional**. KATO functions normally without it:
- Dashboard provides monitoring/management UI only
- Stopping the dashboard doesn't affect KATO operations
- Can be started/stopped independently: `./kato-manager.sh stop dashboard`

### Docker Socket Access

The dashboard requires access to the Docker socket (`/var/run/docker.sock`) for container monitoring:
- **Security Note**: This grants the dashboard access to the Docker daemon
- **Production**: Consider using a Docker socket proxy for restricted access
- **Alternative**: Remove volume mount in `docker-compose.yml` to disable container stats

## Monitoring

### Health Checks

```bash
# KATO health
curl http://localhost:8000/health

# Detailed status
./kato-manager.sh status
```

### Service Logs

```bash
# All services
./kato-manager.sh logs

# Specific service
./kato-manager.sh logs clickhouse

# Real-time logs
./kato-manager.sh follow kato
```

### Metrics

Access system metrics via API:
```bash
curl http://localhost:8000/metrics
```

## Troubleshooting

### Services Won't Start

1. **Check if ports are available:**
   ```bash
   lsof -i :8000 -i :8123 -i :9000 -i :6333 -i :6379
   ```

2. **Check Docker resources:**
   - Ensure Docker has at least 4GB RAM allocated
   - Check available disk space

3. **View logs for errors:**
   ```bash
   ./kato-manager.sh logs
   ```

### KATO Not Responding

1. **Check service status:**
   ```bash
   ./kato-manager.sh status
   docker logs kato --tail 50
   ```

2. **Verify dependencies:**
   ```bash
   docker exec kato-clickhouse clickhouse-client --query "SELECT 1"
   curl http://localhost:6333/health
   docker exec kato-redis redis-cli ping
   ```

3. **Restart services:**
   ```bash
   ./kato-manager.sh restart
   ```

### Out of Memory

1. **Adjust ClickHouse memory settings:**
   Edit `docker-compose.yml`:
   ```yaml
   environment:
     - CLICKHOUSE_MAX_MEMORY_USAGE=4000000000  # 4GB
   ```

2. **Reduce batch size:**
   Edit `.env`:
   ```bash
   KATO_BATCH_SIZE=1000
   ```

### Data Corruption

```bash
# Clear all data and restart
./kato-manager.sh clean-data
./kato-manager.sh restart
```

## Production Considerations

### Security

1. **Network Isolation:**
   - Remove port exposures in `docker-compose.yml`
   - Use reverse proxy (nginx, Traefik) for public access
   - Enable TLS/SSL certificates

2. **Database Security:**
   - Configure ClickHouse authentication and user permissions
   - Use strong passwords
   - Enable access control and network restrictions

3. **API Security:**
   - Implement authentication middleware
   - Use API keys or JWT tokens
   - Rate limiting

### Scalability

1. **Horizontal Scaling:**
   - Multiple KATO instances with load balancer
   - Shared database infrastructure
   - Session affinity/sticky sessions

2. **Resource Limits:**
   Add to `docker-compose.yml`:
   ```yaml
   deploy:
     resources:
       limits:
         cpus: '2.0'
         memory: 4G
   ```

### Backup

1. **Database Backups:**
   ```bash
   # ClickHouse (use backup command or freeze tables)
   docker exec kato-clickhouse clickhouse-client --query "BACKUP DATABASE kato TO Disk('backups', 'backup.zip')"

   # Qdrant
   docker exec kato-qdrant sh -c 'tar -czf /qdrant/backup.tar.gz /qdrant/storage'
   ```

2. **Volume Backups:**
   ```bash
   docker run --rm -v kato-clickhouse-data:/data -v $(pwd):/backup \
     alpine tar -czf /backup/clickhouse-backup.tar.gz /data
   ```

### Monitoring

1. **Prometheus Integration:**
   - Expose metrics endpoint
   - Configure Prometheus scraping
   - Set up Grafana dashboards

2. **Health Monitoring:**
   - Regular health check pings
   - Alert on service failures
   - Log aggregation (ELK, Loki)

## Development vs Production

This deployment package is suitable for both:

- **Development:** Quick local testing and experimentation
- **Staging:** Pre-production validation
- **Production:** Small-to-medium scale deployments

For large-scale production deployments, consider:
- Kubernetes orchestration
- Managed database services
- Load balancing
- Auto-scaling
- Multi-region deployment

## Support

- **Documentation:** http://localhost:8000/docs (when running)
- **GitHub:** https://github.com/sevakavakians/kato
- **Issues:** https://github.com/sevakavakians/kato/issues

## License

See LICENSE file in the main repository.

## Version Management

KATO follows [Semantic Versioning 2.0.0](https://semver.org/) with multiple tag options for different use cases.

### Available Image Tags

| Tag Format | Example | Description | Updates | Use Case |
|------------|---------|-------------|---------|----------|
| `MAJOR.MINOR.PATCH` | `2.0.0` | Specific version (immutable) | Never | **Production** - Pin to exact version |
| `MAJOR.MINOR` | `2.0` | Latest patch for minor | Patches only | Auto-receive bug/security fixes |
| `MAJOR` | `2` | Latest minor for major | Minor + Patches | Track major version line |
| `latest` | `latest` | Latest stable release | All updates | Development/testing only |

### Choosing the Right Tag

**For Production (Recommended):**
```yaml
# Pin to specific version for stability
image: ghcr.io/sevakavakians/kato:2.0.0
```

**For Auto-Patching (Security/Bug Fixes):**
```yaml
# Automatically get patches (2.0.1, 2.0.2, etc.)
image: ghcr.io/sevakavakians/kato:2.0
```

**For Development:**
```yaml
# Always use latest (not recommended for production)
image: ghcr.io/sevakavakians/kato:latest
```

### Updating KATO

#### Method 1: Using start.sh (Recommended)

```bash
# Update to latest version of current tag
./kato-manager.sh update

# This will:
# - Pull latest image for your configured tag
# - Gracefully stop KATO service
# - Remove old container
# - Start with new image
# - Preserve all data (ClickHouse, Qdrant, Redis)
```

#### Method 2: Change Version in docker-compose.yml

```bash
# 1. Edit docker-compose.yml
vim docker-compose.yml

# Change:
#   image: ghcr.io/sevakavakians/kato:2.0.0
# To:
#   image: ghcr.io/sevakavakians/kato:2.1.0

# 2. Pull and restart
./kato-manager.sh pull
./kato-manager.sh restart kato
```

#### Method 3: Manual Docker Commands

```bash
# Pull new version
docker pull ghcr.io/sevakavakians/kato:2.1.0

# Stop and remove old container
docker stop kato
docker rm kato

# Start with new version (use your existing docker run command)
docker run -d \
  --name kato \
  --network kato-network \
  -p 8000:8000 \
  --restart unless-stopped \
  -e SERVICE_NAME=kato \
  -e CLICKHOUSE_HOST=kato-clickhouse \
  -e CLICKHOUSE_PORT=9000 \
  -e CLICKHOUSE_DB=kato \
  -e QDRANT_HOST=kato-qdrant \
  -e QDRANT_PORT=6333 \
  -e REDIS_URL=redis://kato-redis:6379 \
  -e LOG_LEVEL=INFO \
  ghcr.io/sevakavakians/kato:2.1.0
```

### Version Verification

```bash
# Check running version
docker inspect kato | grep -A 5 "Labels"

# View version metadata
docker inspect ghcr.io/sevakavakians/kato:2.0.0 | jq '.[0].Config.Labels'

# Test version in container
docker exec kato python -c "import kato; print(kato.__version__)"
```

### Version Compatibility

- **Major versions** (e.g., 1.x → 2.x): May include breaking changes, review changelog
- **Minor versions** (e.g., 2.0.x → 2.1.x): New features, backward compatible
- **Patch versions** (e.g., 2.0.0 → 2.0.1): Bug fixes, fully compatible

### Registry Information

- **Registry**: GitHub Container Registry (ghcr.io)
- **Repository**: `ghcr.io/sevakavakians/kato`
- **Packages Page**: https://github.com/sevakavakians/kato/pkgs/container/kato
- **Release Notes**: https://github.com/sevakavakians/kato/releases

### Rollback

If you need to rollback to a previous version:

```bash
# 1. Stop current version
docker stop kato
docker rm kato

# 2. Start previous version
# (Update version number in docker-compose.yml or docker run command)
./kato-manager.sh start

# Or with docker compose
docker compose up -d kato
```

Data in ClickHouse, Qdrant, and Redis volumes is preserved during version changes.

### Pre-Release Versions

Pre-release versions (alpha, beta, rc) are available with special tags:

```yaml
# Use pre-release version
image: ghcr.io/sevakavakians/kato:2.1.0-beta.1
```

**Note:** Pre-releases do NOT update `latest`, `2.1`, or `2` tags. Use only for testing.
