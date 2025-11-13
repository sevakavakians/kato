# Environment Variables Reference

Complete reference for all KATO environment variables.

## Service Configuration

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `SERVICE_NAME` | string | `kato` | Service name identifier |
| `SERVICE_VERSION` | string | `2.0` | Service version |

## Logging Configuration

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `LOG_LEVEL` | string | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL) |
| `LOG_FORMAT` | string | `human` | Log output format (json, human) |
| `LOG_OUTPUT` | string | `stdout` | Log destination (stdout, stderr, or file path) |

## Database Configuration

### MongoDB

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `MONGO_BASE_URL` | string | `mongodb://localhost:27017` | MongoDB connection URL |
| `MONGO_TIMEOUT` | integer | `5000` | Connection timeout in milliseconds (1000-30000) |

### Qdrant

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `QDRANT_HOST` | string | `localhost` | Qdrant host address |
| `QDRANT_PORT` | integer | `6333` | Qdrant HTTP port (1-65535) |
| `QDRANT_GRPC_PORT` | integer | `6334` | Qdrant gRPC port (1-65535) |
| `QDRANT_COLLECTION_PREFIX` | string | `vectors` | Prefix for collection names |

### Redis

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `REDIS_URL` | string | None | Redis connection URL (preferred) |
| `REDIS_HOST` | string | None | Redis host (deprecated, use REDIS_URL) |
| `REDIS_PORT` | integer | `6379` | Redis port (deprecated) |
| `REDIS_ENABLED` | boolean | `false` | Enable Redis caching |

### ClickHouse (Hybrid Architecture)

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `CLICKHOUSE_HOST` | string | `localhost` | ClickHouse host address |
| `CLICKHOUSE_PORT` | integer | `8123` | ClickHouse HTTP port |
| `CLICKHOUSE_DB` | string | `kato` | ClickHouse database name |

## Learning Configuration

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `MAX_PATTERN_LENGTH` | integer | `0` | Auto-learn when STM reaches this length (0 = manual) |
| `PERSISTENCE` | integer | `5` | Emotive rolling window size (1-100) |
| `RECALL_THRESHOLD` | float | `0.1` | Pattern matching sensitivity (0.0-1.0) |
| `AUTO_LEARN_ENABLED` | boolean | `false` | Enable automatic pattern learning |
| `AUTO_LEARN_THRESHOLD` | integer | `50` | Observations before auto-learning |
| `STM_MODE` | string | `CLEAR` | STM mode after auto-learn (CLEAR or ROLLING) |

## Processing Configuration

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `INDEXER_TYPE` | string | `VI` | Vector indexer type |
| `MAX_PREDICTIONS` | integer | `100` | Maximum predictions to return (1-10000) |
| `SORT` | boolean | `true` | Sort symbols alphabetically |
| `PROCESS_PREDICTIONS` | boolean | `true` | Enable prediction processing |
| `KATO_USE_TOKEN_MATCHING` | boolean | `true` | Token-level (true) vs character-level (false) |
| `RANK_SORT_ALGO` | string | `potential` | Prediction ranking metric |

## Performance Configuration

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `KATO_USE_FAST_MATCHING` | boolean | `true` | Use optimized matching algorithms |
| `KATO_USE_INDEXING` | boolean | `true` | Use pattern indexing |
| `KATO_USE_OPTIMIZED` | boolean | `true` | Use optimized code paths |

## Session Configuration

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `SESSION_TTL` | integer | `3600` | Default session TTL in seconds |
| `SESSION_AUTO_EXTEND` | boolean | `true` | Auto-extend session TTL on access |

## Example Configuration

### Development

```bash
# .env.development
LOG_LEVEL=DEBUG
LOG_FORMAT=human
MONGO_BASE_URL=mongodb://localhost:27017
QDRANT_HOST=localhost
REDIS_URL=redis://localhost:6379/0
MAX_PATTERN_LENGTH=0
RECALL_THRESHOLD=0.1
```

### Production

```bash
# .env.production
LOG_LEVEL=INFO
LOG_FORMAT=json
MONGO_BASE_URL=mongodb://mongo-cluster:27017
QDRANT_HOST=qdrant-cluster
REDIS_URL=redis://redis-cluster:6379/0
MAX_PATTERN_LENGTH=10
RECALL_THRESHOLD=0.3
SESSION_TTL=7200
```

---

**Last Updated**: November 2025
**KATO Version**: 3.0+
