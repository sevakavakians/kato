# Environment Variables - Operations Guide

Comprehensive operational guide for KATO environment variables with production context, troubleshooting, and best practices.

## Overview

KATO uses environment variables for runtime configuration. This guide provides operational context beyond the reference documentation, including production recommendations, troubleshooting, and real-world scenarios.

## Quick Reference

For a complete list of all environment variables and their types, see [Configuration Variables Reference](../reference/configuration-vars.md).

## Service Configuration

### SERVICE_NAME
**Type**: string | **Default**: `kato` | **Required**: No

```bash
SERVICE_NAME=kato-production
```

**Operational Context**:
- Appears in logs and metrics for identification
- Useful for distinguishing multiple KATO deployments
- Include environment suffix: `kato-prod`, `kato-staging`

**Troubleshooting**:
- If metrics appear under wrong service name, verify this variable
- Check Prometheus/Grafana service label matches

### SERVICE_VERSION
**Type**: string | **Default**: `3.0` | **Required**: No

```bash
SERVICE_VERSION=3.0.1
```

**Operational Context**:
- Used for version tracking in logs and metrics
- Update during deployments for rollback tracking
- Semver format recommended: MAJOR.MINOR.PATCH

**Production Best Practice**:
```bash
# Tag with git commit for traceability
SERVICE_VERSION=3.0.1-${GIT_COMMIT_SHA}
```

## Logging Configuration

### LOG_LEVEL
**Type**: string | **Default**: `INFO` | **Required**: No
**Values**: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`

```bash
LOG_LEVEL=INFO  # Production
LOG_LEVEL=DEBUG # Development/Troubleshooting
```

**Operational Context**:
- **DEBUG**: Detailed logs, high volume, use only for troubleshooting
- **INFO**: Standard production logging, balanced verbosity
- **WARNING**: Minimal logging, production with strict log quotas
- **ERROR**: Only errors and critical issues

**Performance Impact**:
| Level | Volume | Performance | Use Case |
|-------|--------|-------------|----------|
| DEBUG | Very High | -10-20% | Development, debugging |
| INFO | Moderate | -2-5% | Production standard |
| WARNING | Low | <1% | High-volume production |
| ERROR | Very Low | Negligible | Critical alerts only |

**Troubleshooting**:
```bash
# Temporarily increase log level without restart
curl -X POST http://localhost:8000/admin/log-level \
  -H "Content-Type: application/json" \
  -d '{"level": "DEBUG"}'
```

### LOG_FORMAT
**Type**: string | **Default**: `human` | **Required**: No
**Values**: `json`, `human`

```bash
LOG_FORMAT=json   # Production (structured logging)
LOG_FORMAT=human  # Development (readable console)
```

**Operational Context**:
- **json**: Machine-readable, required for log aggregation (ELK, Loki)
- **human**: Human-readable, best for local development

**Example Output**:
```json
// LOG_FORMAT=json
{
  "timestamp": "2025-11-13T10:30:45.123Z",
  "level": "INFO",
  "service": "kato",
  "trace_id": "abc123",
  "message": "Observation processed",
  "duration_ms": 5.2
}
```

```
// LOG_FORMAT=human
2025-11-13 10:30:45 INFO [kato] Observation processed (5.2ms) trace_id=abc123
```

### LOG_OUTPUT
**Type**: string | **Default**: `stdout` | **Required**: No
**Values**: `stdout`, `stderr`, file path

```bash
LOG_OUTPUT=stdout                    # Standard (Docker/K8s)
LOG_OUTPUT=/var/log/kato/app.log    # File-based
```

**Operational Context**:
- **stdout**: Recommended for containers (captured by Docker/Kubernetes)
- **stderr**: Error stream only
- **File path**: Legacy systems, requires volume mount

**Production Recommendation**: Always use `stdout` for containerized deployments.

## Database Configuration

### ClickHouse (Hybrid Architecture)

#### CLICKHOUSE_HOST
**Type**: string | **Default**: `localhost` | **Required**: Yes

```bash
# Standard connection
CLICKHOUSE_HOST=kato-clickhouse

# IP address
CLICKHOUSE_HOST=192.168.1.100
```

**Operational Context**:
- Used for billion-scale pattern storage
- Part of hybrid architecture (ClickHouse + Redis)
- Provides high-performance read path for pattern queries

#### CLICKHOUSE_PORT
**Type**: integer | **Default**: `8123` | **Required**: Yes

```bash
CLICKHOUSE_PORT=8123  # HTTP interface (default)
CLICKHOUSE_PORT=9000  # Native interface (for higher performance)
```

**Operational Context**:
- Port 8123: HTTP interface (standard, easier debugging)
- Port 9000: Native protocol (faster, use for production)
- Ensure firewall allows chosen port

#### CLICKHOUSE_DB
**Type**: string | **Default**: `kato` | **Required**: Yes

```bash
CLICKHOUSE_DB=kato             # Development
CLICKHOUSE_DB=kato_production  # Production
CLICKHOUSE_DB=kato_staging     # Staging
```

**Operational Context**:
- Database name for pattern storage
- Use environment-specific names for isolation
- Must exist before KATO starts (created by migrations)

**Troubleshooting**:
```bash
# Test connection
curl "http://kato-clickhouse:8123/?query=SELECT%201"

# Check database exists
curl "http://kato-clickhouse:8123/" \
  --data "SHOW DATABASES"

# Check table stats
curl "http://kato-clickhouse:8123/" \
  --data "SELECT count() FROM kato.patterns"
```

### Qdrant

#### QDRANT_HOST / QDRANT_PORT
**Type**: string, integer | **Default**: `localhost`, `6333` | **Required**: Yes

```bash
QDRANT_HOST=qdrant-kb
QDRANT_PORT=6333        # HTTP API
QDRANT_GRPC_PORT=6334   # gRPC (faster)
```

**Operational Context**:
- Use gRPC port for better performance (10-20% faster)
- HTTP port for debugging and manual queries
- Cloud deployments may use different ports

**High-Performance Configuration**:
```bash
QDRANT_HOST=qdrant-kb
QDRANT_PORT=6334  # Use gRPC port
QDRANT_USE_GRPC=true
```

**Troubleshooting**:
```bash
# Test HTTP endpoint
curl http://qdrant-kb:6333/

# Test gRPC endpoint (requires grpcurl)
grpcurl -plaintext qdrant-kb:6334 list

# Check collection status
curl http://qdrant-kb:6333/collections/vectors_<processor_id>
```

### Redis

#### REDIS_URL
**Type**: string | **Default**: None | **Required**: Yes (if Redis enabled)

```bash
# Standard connection
REDIS_URL=redis://redis-kb:6379/0

# With password
REDIS_URL=redis://:password@redis-kb:6379/0

# Sentinel (high availability)
REDIS_URL=redis-sentinel://sentinel1:26379,sentinel2:26379/mymaster/0

# Cluster
REDIS_URL=redis://redis-cluster-1:6379,redis-cluster-2:6379,redis-cluster-3:6379/0
```

**Operational Context**:
- Database number (0-15) for logical separation
- Use Sentinel for production high availability
- Use Cluster for massive scale (>100GB data)

**Connection String Parameters**:
```bash
REDIS_URL=redis://redis-kb:6379/0?\
  socket_timeout=5&\
  socket_connect_timeout=5&\
  socket_keepalive=true&\
  health_check_interval=30&\
  max_connections=50&\
  retry_on_timeout=true
```

**Troubleshooting**:
```bash
# Test connection
docker exec kato python -c "
import redis
r = redis.from_url('$REDIS_URL')
print(r.ping())
"

# Check Redis memory
docker exec redis-kb redis-cli INFO memory

# Monitor commands
docker exec redis-kb redis-cli MONITOR
```

#### REDIS_ENABLED
**Type**: boolean | **Default**: `false` | **Required**: No

```bash
REDIS_ENABLED=true   # Enable session caching
REDIS_ENABLED=false  # Disable (testing/minimal setup)
```

**Operational Context**:
- **Enabled**: Sessions persist across restarts, better performance
- **Disabled**: Simpler setup, sessions lost on restart

**When to Enable**:
- Production deployments (always)
- Multi-instance deployments (required)
- High session throughput (recommended)

**When to Disable**:
- Single-user development
- Minimal testing environments
- Cost-sensitive deployments


## Learning Configuration

### MAX_PATTERN_LENGTH
**Type**: integer | **Default**: `0` (manual) | **Range**: 0-1000

```bash
MAX_PATTERN_LENGTH=0   # Manual learning (explicit /learn calls)
MAX_PATTERN_LENGTH=10  # Auto-learn at 10 observations
MAX_PATTERN_LENGTH=50  # Auto-learn at 50 observations
```

**Operational Context**:
- **0**: Manual control, recommended for production
- **10-20**: Aggressive learning, good for rapid pattern discovery
- **50-100**: Conservative learning, reduces noise

**Performance Impact**:
| Value | Learning Frequency | Memory Usage | Pattern Quality |
|-------|-------------------|--------------|-----------------|
| 0 | Manual | Low | High (curated) |
| 10 | Very High | Moderate | Variable |
| 50 | Moderate | High | Good |
| 100 | Low | Very High | Best |

**Production Recommendation**:
```bash
# Recommendation: Manual learning for production
MAX_PATTERN_LENGTH=0

# Use auto-learn in development/testing
MAX_PATTERN_LENGTH=20
```

### RECALL_THRESHOLD
**Type**: float | **Default**: `0.1` | **Range**: 0.0-1.0

```bash
RECALL_THRESHOLD=0.1  # High recall, more predictions
RECALL_THRESHOLD=0.5  # Balanced
RECALL_THRESHOLD=0.9  # High precision, fewer predictions
```

**Operational Context**:
- Lower = More predictions, higher latency, lower precision
- Higher = Fewer predictions, lower latency, higher precision

**Performance vs Accuracy**:
| Threshold | Predictions | Latency | CPU | Memory | Precision |
|-----------|------------|---------|-----|--------|-----------|
| 0.1 | 500+ | 200ms | High | High | Low |
| 0.3 | 100-200 | 75ms | Moderate | Moderate | Moderate |
| 0.5 | 20-50 | 30ms | Low | Low | High |
| 0.7 | 5-15 | 15ms | Very Low | Very Low | Very High |

**Production Tuning**:
```bash
# Discovery phase (initial learning)
RECALL_THRESHOLD=0.2

# Production phase (known patterns)
RECALL_THRESHOLD=0.4

# High-speed production (low latency required)
RECALL_THRESHOLD=0.6
```

**Adaptive Threshold Script**:
```python
# Adjust threshold based on load
import psutil

cpu_usage = psutil.cpu_percent()
if cpu_usage > 80:
    RECALL_THRESHOLD = 0.6  # Reduce load
elif cpu_usage < 30:
    RECALL_THRESHOLD = 0.3  # Increase recall
```

### STM_MODE
**Type**: string | **Default**: `CLEAR` | **Values**: `CLEAR`, `ROLLING`

```bash
STM_MODE=CLEAR    # Clear STM after learning (recommended)
STM_MODE=ROLLING  # Keep last N observations in STM
```

**Operational Context**:
- **CLEAR**: Clean slate after learning, predictable behavior
- **ROLLING**: Continuous context, useful for streaming data

**When to Use**:
| Mode | Use Case | Memory | Complexity |
|------|----------|--------|------------|
| CLEAR | Discrete tasks/sessions | Low | Simple |
| ROLLING | Continuous streams | Higher | Complex |

## Performance Configuration

### KATO_USE_FAST_MATCHING
**Type**: boolean | **Default**: `true` | **Required**: No

```bash
KATO_USE_FAST_MATCHING=true   # Use optimized algorithms
KATO_USE_FAST_MATCHING=false  # Use legacy algorithms
```

**Operational Context**:
- **true**: 9x faster token matching, 75x faster string matching
- **false**: Legacy behavior, debugging only

**Performance Comparison**:
```
Fast Matching OFF: 450ms average
Fast Matching ON:  50ms average (9x improvement)
```

**Production Recommendation**: Always `true` unless debugging specific issues.

### KATO_USE_INDEXING
**Type**: boolean | **Default**: `true` | **Required**: No

```bash
KATO_USE_INDEXING=true   # Use pattern indexing
KATO_USE_INDEXING=false  # Sequential search
```

**Operational Context**:
- **true**: O(log n) search with indexes
- **false**: O(n) sequential search, testing only

**Performance Impact** (10,000 patterns):
```
Indexing OFF: 1200ms search time
Indexing ON:  45ms search time (26x improvement)
```

### KATO_BATCH_SIZE
**Type**: integer | **Default**: `1000` | **Range**: 100-10000

```bash
KATO_BATCH_SIZE=1000   # Standard batch size
KATO_BATCH_SIZE=5000   # Large batches (more memory, faster)
```

**Operational Context**:
- Larger batches = Better throughput, more memory
- Smaller batches = Lower memory, more overhead

**Tuning Guidelines**:
```bash
# Memory-constrained environments
KATO_BATCH_SIZE=500

# High-throughput environments
KATO_BATCH_SIZE=5000

# Balanced
KATO_BATCH_SIZE=1000
```

## Session Configuration

### SESSION_TTL
**Type**: integer | **Default**: `3600` (seconds) | **Range**: 60-86400

```bash
SESSION_TTL=3600   # 1 hour (standard)
SESSION_TTL=7200   # 2 hours (extended)
SESSION_TTL=1800   # 30 minutes (short)
```

**Operational Context**:
- Balance between user convenience and resource usage
- Longer TTL = More memory usage (cached sessions)
- Shorter TTL = Better cleanup, less memory

**Production Recommendations**:
```bash
# Interactive applications
SESSION_TTL=7200  # 2 hours

# Batch processing
SESSION_TTL=1800  # 30 minutes

# Long-running analysis
SESSION_TTL=14400 # 4 hours
```

### SESSION_AUTO_EXTEND
**Type**: boolean | **Default**: `true` | **Required**: No

```bash
SESSION_AUTO_EXTEND=true   # Extend TTL on each access
SESSION_AUTO_EXTEND=false  # Fixed TTL from creation
```

**Operational Context**:
- **true**: Sessions stay alive while active (recommended)
- **false**: Hard timeout regardless of activity

## Environment Templates

### Development
```bash
# .env.development
ENVIRONMENT=development
LOG_LEVEL=DEBUG
LOG_FORMAT=human
LOG_OUTPUT=stdout

CLICKHOUSE_HOST=localhost
CLICKHOUSE_PORT=8123
CLICKHOUSE_DB=kato
QDRANT_HOST=localhost
QDRANT_PORT=6333
REDIS_URL=redis://localhost:6379/0
REDIS_ENABLED=true

MAX_PATTERN_LENGTH=0
RECALL_THRESHOLD=0.1
STM_MODE=CLEAR
SESSION_TTL=3600

KATO_USE_FAST_MATCHING=true
KATO_USE_INDEXING=true
```

### Staging
```bash
# .env.staging
ENVIRONMENT=staging
LOG_LEVEL=INFO
LOG_FORMAT=json
LOG_OUTPUT=stdout

CLICKHOUSE_HOST=kato-clickhouse-staging
CLICKHOUSE_PORT=8123
CLICKHOUSE_DB=kato_staging
QDRANT_HOST=qdrant-staging
QDRANT_PORT=6333
REDIS_URL=redis://redis-staging:6379/0
REDIS_ENABLED=true

MAX_PATTERN_LENGTH=0
RECALL_THRESHOLD=0.3
STM_MODE=CLEAR
SESSION_TTL=7200
SESSION_AUTO_EXTEND=true

KATO_USE_FAST_MATCHING=true
KATO_USE_INDEXING=true
KATO_BATCH_SIZE=1000
```

### Production
```bash
# .env.production
ENVIRONMENT=production
SERVICE_NAME=kato-production
SERVICE_VERSION=3.0.1
LOG_LEVEL=INFO
LOG_FORMAT=json
LOG_OUTPUT=stdout

# ClickHouse cluster
CLICKHOUSE_HOST=kato-clickhouse-cluster
CLICKHOUSE_PORT=9000  # Native protocol for production
CLICKHOUSE_DB=kato_production
CLICKHOUSE_USER=kato_user
CLICKHOUSE_PASSWORD=${CLICKHOUSE_PASSWORD}  # From secrets

# Qdrant cluster
QDRANT_HOST=qdrant-cluster
QDRANT_PORT=6334  # gRPC for performance
QDRANT_USE_GRPC=true

# Redis Sentinel
REDIS_URL=redis-sentinel://sentinel1:26379,sentinel2:26379/mymaster/0
REDIS_ENABLED=true

# Learning configuration
MAX_PATTERN_LENGTH=0  # Manual learning only
RECALL_THRESHOLD=0.4
STM_MODE=CLEAR
PERSISTENCE=5

# Session management
SESSION_TTL=7200
SESSION_AUTO_EXTEND=true

# Performance
KATO_USE_FAST_MATCHING=true
KATO_USE_INDEXING=true
KATO_USE_OPTIMIZED=true
KATO_BATCH_SIZE=1000
CONNECTION_POOL_SIZE=100

# API Configuration
WORKERS=4
CORS_ENABLED=true
CORS_ORIGINS=https://yourdomain.com
```

## Troubleshooting

### Configuration Not Applied
```bash
# Verify environment variables are loaded
docker exec kato env | grep KATO

# Check FastAPI settings
curl http://localhost:8000/admin/config

# Restart to apply changes
docker compose restart kato
```

### Database Connection Errors
```bash
# Test ClickHouse
curl "http://${CLICKHOUSE_HOST}:${CLICKHOUSE_PORT}/?query=SELECT%201"

# Test Qdrant
curl http://${QDRANT_HOST}:${QDRANT_PORT}/

# Test Redis
docker exec kato python -c "import redis; print(redis.from_url(os.environ['REDIS_URL']).ping())"
```

### Performance Issues
```bash
# Check if optimizations are enabled
curl http://localhost:8000/metrics | grep -E "(fast_matching|indexing)"

# Verify batch size
docker exec kato env | grep BATCH_SIZE

# Check recall threshold impact
curl http://localhost:8000/metrics | grep prediction_count
```

## Best Practices

1. **Use environment-specific files**: `.env.development`, `.env.staging`, `.env.production`
2. **Never commit secrets**: Use `.gitignore` for `.env` files
3. **Use secret management**: Kubernetes secrets, Vault, AWS Secrets Manager
4. **Validate on startup**: Fail fast if critical variables are missing
5. **Document deviations**: If using non-default values, document why
6. **Monitor configuration**: Track which configuration is active in metrics
7. **Test in staging**: Always validate configuration changes in staging first
8. **Use configuration management**: Ansible, Terraform, Helm for consistency

## Related Documentation

- [Configuration Variables Reference](../reference/configuration-vars.md) - Complete variable reference
- [Security Configuration](security-configuration.md) - Security-related variables
- [Performance Tuning](performance-tuning.md) - Performance optimization
- [Docker Deployment](docker-deployment.md) - Docker-specific configuration
- [Kubernetes Deployment](kubernetes-deployment.md) - Kubernetes configuration

---

**Last Updated**: November 2025
**KATO Version**: 3.0+
