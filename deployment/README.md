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
- Ports available: 8000, 27017, 6333, 6379

### Installation

1. **Download this deployment directory** or clone the repository:
   ```bash
   # Option 1: Download deployment files only
   curl -L https://github.com/sevakavakians/kato/archive/main.tar.gz | tar xz
   cd kato-main/deployment

   # Option 2: Clone entire repository
   git clone https://github.com/sevakavakians/kato.git
   cd kato/deployment
   ```

2. **Start all services:**
   ```bash
   ./start.sh start
   ```

3. **Verify installation:**
   ```bash
   ./start.sh status
   ```

4. **Access KATO:**
   - API: http://localhost:8000
   - Interactive Docs: http://localhost:8000/docs
   - Health Check: http://localhost:8000/health

That's it! KATO is now running with all required infrastructure.

## Usage

### Service Management

```bash
# Start all services
./start.sh start

# Stop all services
./start.sh stop

# Restart all services
./start.sh restart

# Check service status
./start.sh status
```

### Individual Services

```bash
# Start/stop/restart individual services
./start.sh start mongodb
./start.sh restart kato
./start.sh stop redis
```

### Updates

```bash
# Update KATO to latest version
./start.sh update

# Or manually pull and restart
./start.sh pull
./start.sh restart kato
```

### Logs

```bash
# View recent logs (default: 50 lines)
./start.sh logs kato

# View more lines
./start.sh logs kato 200

# Follow logs in real-time
./start.sh follow kato
```

### Data Management

```bash
# Clear all data (keeps services running)
./start.sh clean-data

# Remove all containers and volumes
./start.sh clean
```

## Configuration

### Basic Configuration

Create a `.env` file to customize settings:

```bash
cp .env.example .env
# Edit .env with your preferred settings
./start.sh restart
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

KATO deployment includes four services:

1. **KATO Service** (Port 8000)
   - FastAPI application serving the AI engine
   - Processes observations and generates predictions
   - Uses pre-built image from `ghcr.io/sevakavakians/kato:latest`

2. **MongoDB** (Port 27017)
   - Persistent pattern storage
   - Session-isolated databases
   - 2GB WiredTiger cache

3. **Qdrant** (Port 6333)
   - Vector database for semantic search
   - HNSW indexing for fast similarity matching

4. **Redis** (Port 6379)
   - Session state management
   - High-speed caching

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

## Monitoring

### Health Checks

```bash
# KATO health
curl http://localhost:8000/health

# Detailed status
./start.sh status
```

### Service Logs

```bash
# All services
./start.sh logs

# Specific service
./start.sh logs mongodb

# Real-time logs
./start.sh follow kato
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
   lsof -i :8000 -i :27017 -i :6333 -i :6379
   ```

2. **Check Docker resources:**
   - Ensure Docker has at least 4GB RAM allocated
   - Check available disk space

3. **View logs for errors:**
   ```bash
   ./start.sh logs
   ```

### KATO Not Responding

1. **Check service status:**
   ```bash
   ./start.sh status
   docker logs kato --tail 50
   ```

2. **Verify dependencies:**
   ```bash
   docker exec kato-mongodb mongo --eval "db.adminCommand('ping')"
   curl http://localhost:6333/health
   docker exec kato-redis redis-cli ping
   ```

3. **Restart services:**
   ```bash
   ./start.sh restart
   ```

### Out of Memory

1. **Reduce MongoDB cache:**
   Edit `docker-compose.yml`:
   ```yaml
   command: mongod --wiredTigerCacheSizeGB 1
   ```

2. **Reduce batch size:**
   Edit `.env`:
   ```bash
   KATO_BATCH_SIZE=1000
   ```

### Data Corruption

```bash
# Clear all data and restart
./start.sh clean-data
./start.sh restart
```

## Production Considerations

### Security

1. **Network Isolation:**
   - Remove port exposures in `docker-compose.yml`
   - Use reverse proxy (nginx, Traefik) for public access
   - Enable TLS/SSL certificates

2. **Database Security:**
   - Configure MongoDB authentication
   - Use strong passwords
   - Enable access control

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
   # MongoDB
   docker exec kato-mongodb mongodump --out /data/backup

   # Qdrant
   docker exec kato-qdrant sh -c 'tar -czf /qdrant/backup.tar.gz /qdrant/storage'
   ```

2. **Volume Backups:**
   ```bash
   docker run --rm -v kato_mongo-data:/data -v $(pwd):/backup \
     alpine tar -czf /backup/mongo-backup.tar.gz /data
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

## Version

This deployment uses the latest KATO image from GitHub Container Registry:
- Image: `ghcr.io/sevakavakians/kato:latest`
- Registry: https://github.com/sevakavakians/kato/pkgs/container/kato

To use a specific version:
```yaml
# In docker-compose.yml
image: ghcr.io/sevakavakians/kato:v1.2.3
```
