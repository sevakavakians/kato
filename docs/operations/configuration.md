# KATO Configuration Guide

Complete reference for all KATO configuration options and environment variables.

## Table of Contents
- [Environment Variables Overview](#environment-variables-overview)
- [Core Configuration](#core-configuration)
- [Database Configuration](#database-configuration)
- [Learning Configuration](#learning-configuration)
- [Processing Configuration](#processing-configuration)
- [Performance Configuration](#performance-configuration)
- [API Configuration](#api-configuration)
- [Logging Configuration](#logging-configuration)
- [Session Configuration](#session-configuration)
- [Environment & Deployment](#environment--deployment)
- [Docker Compose Examples](#docker compose-configuration-examples)
- [Configuration Profiles](#configuration-profiles)
- [Runtime Configuration Updates](#runtime-configuration-updates)
- [Best Practices](#configuration-best-practices)
- [Troubleshooting](#troubleshooting-configuration-issues)

## Environment Variables Overview

KATO uses environment variables for configuration. These can be set in:
- Docker Compose files
- Shell environment
- `.env` files
- Container runtime parameters
- Configuration files (JSON/YAML via KATO_CONFIG_FILE)

## Core Configuration

### SERVICE_NAME
- **Type**: String
- **Default**: `kato`
- **Description**: Service name identifier, used as the base processor id and in logs
- **Example**: `kato`, `kato-production`

**Processor identity**: there is no `PROCESSOR_ID` or `PROCESSOR_NAME`
environment variable. A processor's id is the session's `node_id`, supplied per
request; database isolation follows from that, not from configuration.

## Database Configuration

### CLICKHOUSE_HOST
- **Type**: String
- **Default**: `localhost`
- **Description**: ClickHouse database host for pattern storage
- **Example**: `kato-clickhouse`, `192.168.1.100`

### CLICKHOUSE_PORT
- **Type**: Integer
- **Default**: `8123`
- **Range**: `1` to `65535`
- **Description**: ClickHouse HTTP port
- **Example**: `8123`

### CLICKHOUSE_DB
- **Type**: String
- **Default**: `kato`
- **Description**: ClickHouse database name
- **Example**: `kato`, `kato_production`

### QDRANT_HOST
- **Type**: String
- **Default**: `localhost`
- **Description**: Qdrant vector database host
- **Example**: `qdrant`, `192.168.1.100`

### QDRANT_PORT
- **Type**: Integer
- **Default**: `6333`
- **Range**: `1` to `65535`
- **Description**: Qdrant vector database HTTP port
- **Example**: `6333`

### QDRANT_GRPC_PORT
- **Type**: Integer
- **Default**: `6334`
- **Range**: `1` to `65535`
- **Description**: Qdrant vector database gRPC port
- **Example**: `6334`
- **Notes**: Used for high-performance vector operations

### REDIS_HOST
- **Type**: String
- **Default**: `None` (optional)
- **Description**: Redis host for caching and session storage
- **Example**: `redis`, `localhost`, `192.168.1.101`

### REDIS_PORT
- **Type**: Integer
- **Default**: `6379`
- **Range**: `1` to `65535`
- **Description**: Redis port number
- **Example**: `6379`

### REDIS_ENABLED
- **Type**: Boolean
- **Default**: `false`
- **Description**: Enable Redis caching layer
- **Options**: `true`, `false`
- **Notes**: Improves performance for frequently accessed patterns

### REDIS_URL
- **Type**: String (Redis connection URL)
- **Default**: Constructed from REDIS_HOST and REDIS_PORT
- **Description**: Full Redis connection URL (alternative to HOST/PORT)
- **Example**: `redis://redis:6379`, `redis://localhost:6379/0`
- **Notes**: Used in docker compose for session management

## Learning Configuration

### MAX_PATTERN_LENGTH
- **Type**: Integer
- **Default**: `0`
- **Range**: `0` to unlimited
- **Description**: Auto-learn after N observations (0 = manual learning only)
- **Example**: `0` (manual), `10` (auto-learn after 10), `50`
- **Notes**: When reached, triggers automatic pattern learning. STM behavior depends on STM_MODE

### STM_MODE
- **Type**: String (Literal)
- **Default**: `CLEAR`
- **Options**: `CLEAR`, `ROLLING`
- **Description**: Short-term memory mode after auto-learning
- **Example**: `CLEAR`, `ROLLING`
- **Notes**: 
  - `CLEAR`: Traditional behavior - STM completely cleared after auto-learn
  - `ROLLING`: STM maintained as sliding window for continuous learning

**STM_MODE Behavior Details:**
- **CLEAR Mode**: When MAX_PATTERN_LENGTH is reached, the pattern is learned and STM is emptied
- **ROLLING Mode**: When MAX_PATTERN_LENGTH is reached, the pattern is learned but STM is maintained as a sliding window of size (MAX_PATTERN_LENGTH - 1), enabling continuous learning of overlapping patterns

### PERSISTENCE
- **Type**: Integer
- **Default**: `5`
- **Range**: `1` to `100`
- **Description**: Rolling window size for emotive value history per pattern
- **Example**: `5`, `10`, `20`
- **Notes**: Controls adaptive learning and memory for emotional/utility values

**How PERSISTENCE Works:**
- Each pattern maintains arrays of emotive values (one array per emotive type)
- Arrays are limited to PERSISTENCE length using a rolling window
- When a pattern is re-learned with new emotive values, oldest values drop off
- This creates a rolling window that adapts to changing contexts

**Configuration Impact:**
- **Low values (1-5)**: Fast adaptation, quick forgetting of old emotives
- **Medium values (5-10)**: Balanced memory and adaptation (default range)
- **High values (10-20)**: Longer memory, slower adaptation to changes
- **Very high (20+)**: Extended historical context, resistant to change

### RECALL_THRESHOLD
- **Type**: Float
- **Default**: `0.1`
- **Range**: `0.0` to `1.0`
- **Description**: Pattern matching sensitivity threshold
- **Examples**:
  - `0.0-0.1`: Very permissive (include most partial matches)
  - `0.3`: Permissive
  - `0.5`: Moderate filtering
  - `0.7`: Strict
  - `0.9`: Very strict
  - `1.0`: Exact matches only
- **Notes**:
  - Acts as rough filter, not exact decimal precision
  - **Avoid exact boundaries**: Similarity scores may vary slightly depending on whether RapidFuzz is installed
    - With RapidFuzz (faster): Character-level Levenshtein distance on joined strings
    - Without RapidFuzz (fallback): Token-level matching on list elements
    - Typical difference: < 0.03 (e.g., 0.5714 vs 0.6000)
    - **Recommendation**: Use thresholds with safety margins (e.g., 0.5 instead of 0.6) to ensure consistent behavior

## Processing Configuration

### INDEXER_TYPE
- **Type**: String
- **Default**: `VI`
- **Description**: Type of vector indexing to use
- **Options**: `VI` (Vector Indexing)
- **Notes**: Controls vector storage and retrieval strategy

### MAX_PREDICTIONS
- **Type**: Integer
- **Default**: `100`
- **Range**: `1` to `10000`
- **Description**: Maximum number of predictions to return
- **Example**: `10`, `50`, `100`, `1000`
- **Notes**: Limits response payload size

### SORT_SYMBOLS
- **Type**: Boolean
- **Default**: `true`
- **Description**: Sort symbols alphabetically within events
- **Options**: `true`, `false`
- **Notes**: Enable for deterministic pattern matching. The variable is named
  `SORT_SYMBOLS`; a bare `SORT` is not accepted.

### PROCESS_PREDICTIONS
- **Type**: Boolean
- **Default**: `true`
- **Description**: Enable prediction processing
- **Options**: `true`, `false`
- **Notes**: Can be disabled for observation-only mode

### USE_TOKEN_MATCHING / KATO_USE_TOKEN_MATCHING
- **Type**: Boolean
- **Default**: `true`
- **Description**: Use token-level (vs character-level) pattern matching
- **Options**:
  - `true` (default): Token-level matching - EXACT difflib compatibility, 9x speedup
  - `false`: Character-level matching - 75x speedup, ~0.03 score difference
- **Performance Trade-off**:
  - Token-level: correct for tokenized text, exact similarity requirements
  - Character-level: document chunks only, where fuzzy matching is acceptable
- **Notes**:
  - Both spellings are accepted; prefer `KATO_USE_TOKEN_MATCHING`, which the
    pattern search hot path reads directly from the environment
  - `sort_symbols` is auto-toggled to match when set per session

### FUZZY_TOKEN_THRESHOLD / KATO_FUZZY_TOKEN_THRESHOLD
- **Type**: Float
- **Default**: `0.0`
- **Range**: `0.0` to `1.0`
- **Description**: Fuzzy token matching threshold (`0.0` disables fuzzy matching)
- **Notes**: Both spellings are accepted

### RANK_SORT_ALGO
- **Type**: String
- **Default**: `potential`
- **Description**: Metric to use for ranking predictions
- **Options**:
  - `potential`: Primary composite ranking metric (default)
  - `similarity`: Base pattern similarity score
  - `evidence`: Proportion of pattern observed
  - `confidence`: Match quality in current context
  - `snr`: Signal-to-noise ratio
  - `frequency`: Pattern occurrence count
  - `fragmentation`: Pattern cohesion measure
  - `normalized_entropy`: Local information content
  - `global_normalized_entropy`: Global information content
  - `itfdf_similarity`: Frequency-weighted importance
  - `confluence`: Probability vs random occurrence
  - `predictive_information`: Future prediction reliability
- **Example**: `potential`, `similarity`, `evidence`
- **Notes**:
  - Controls how predictions are sorted in the response
  - Can be changed at runtime via `/sessions/{session_id}/config` endpoint
  - Different metrics optimize for different use cases (match quality vs predictive power vs frequency)

## Performance Configuration

### USE_FAST_MATCHING / KATO_USE_FAST_MATCHING
- **Type**: Boolean
- **Default**: `true`
- **Description**: Use optimized fast matching algorithms
- **Options**: `true`, `false`
- **Notes**: Significantly improves pattern matching speed

### USE_INDEXING / KATO_USE_INDEXING
- **Type**: Boolean
- **Default**: `true`
- **Description**: Use pattern indexing for faster lookups
- **Options**: `true`, `false`
- **Notes**: Creates indexes for common query patterns

### KATO_USE_BLOOM_FILTER
- **Type**: Boolean
- **Default**: `true`
- **Description**: Bloom filter pre-screening in pattern search
- **Options**: `true`, `false`

### KATO_USE_REDIS_CACHE
- **Type**: Boolean
- **Default**: `true`
- **Description**: Redis-backed pattern cache in pattern search
- **Options**: `true`, `false`

### MINHASH_HASH_FUNC
- **Type**: String
- **Default**: `sha1`
- **Options**: `sha1`, `xxhash`
- **Description**: Hash function used for MinHash signatures
- **Notes**: `xxhash` is faster but changes the signatures — existing patterns
  must be reindexed. Falls back to SHA-1 with a warning if `xxhash` is not
  installed.

### CONNECTION_POOL_SIZE
- **Type**: Integer
- **Default**: `200`
- **Range**: `1` to `1000`
- **Description**: Maximum Redis connections **per worker**
- **Notes**: Total connections ≈ `CONNECTION_POOL_SIZE × KATO_WORKERS`

### REQUEST_TIMEOUT
- **Type**: Float
- **Default**: `30.0`
- **Range**: `1.0` to `300.0`
- **Description**: ClickHouse send/receive timeout in seconds
- **Notes**: Does not affect Qdrant or Redis, which have their own timeouts

### Batching

There is no batch-size variable. ClickHouse batching is server-side via
`async_insert` (`async_insert=1`, `wait_for_async_insert=0`), which batches
across all uvicorn workers; the client-side write buffer is deliberately
disabled because per-worker buffers orphaned rows across workers.

## API Configuration

The HTTP server is not configured through environment variables. Host, port and
worker count come from the `uvicorn` command line in the Dockerfile, CORS is
applied unconditionally with `allow_origins=["*"]`, the `/docs` and `/redoc`
endpoints are always enabled, and there is no request-size limit setting. There
are no `HOST`, `PORT`, `WORKERS`, `CORS_ENABLED`, `CORS_ORIGINS`,
`DOCS_ENABLED` or `MAX_REQUEST_SIZE` variables.

The two knobs that do exist are expanded by the Dockerfile `CMD`:

### KATO_WORKERS
- **Type**: Integer
- **Default**: `4`
- **Description**: Number of uvicorn worker processes
- **Notes**: Also read by `/concurrency` when reporting real capacity

### KATO_LIMIT_CONCURRENCY
- **Type**: Integer
- **Default**: `100`
- **Description**: Maximum concurrent connections per worker
- **Notes**: `/concurrency` reports total capacity as
  `KATO_LIMIT_CONCURRENCY × KATO_WORKERS`

## Logging Configuration

### LOG_LEVEL
- **Type**: String (enum)
- **Default**: `INFO`
- **Options**: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`
- **Description**: Controls logging verbosity
- **Notes**: Use `DEBUG` for development, `INFO` or `WARNING` for production

### LOG_FORMAT
- **Type**: String (enum)
- **Default**: `human`
- **Options**: `json`, `human`
- **Description**: Log output format
- **Notes**: Use `json` for log aggregation systems; JSON records include
  `trace_id` and `duration_ms`

### LOG_OUTPUT
- **Type**: String
- **Default**: `stdout`
- **Description**: Log output destination
- **Example**: `stdout`, `stderr`, `/var/log/kato.log`
- **Notes**: Defaults to stdout. Earlier versions logged to stderr through
  `logging.basicConfig`; set `LOG_OUTPUT=stderr` to restore that.

## Session Configuration

### SESSION_TTL
- **Type**: Integer
- **Default**: `3600`
- **Description**: Session time-to-live in seconds
- **Example**: `1800` (30 min), `3600` (1 hour), `7200` (2 hours)
- **Notes**: Controls how long user sessions remain active

### SESSION_AUTO_EXTEND
- **Type**: Boolean
- **Default**: `true`
- **Description**: Extend the session TTL on each access (sliding window)

### SESSION_COUNT_CACHE_TTL_SECONDS
- **Type**: Float
- **Default**: `5`
- **Description**: Cache TTL for the session-count endpoint

### METRICS_CACHE_TTL_SECONDS
- **Type**: Float
- **Default**: `5`
- **Description**: Cache TTL for the metrics endpoint

## Environment & Deployment

### ENVIRONMENT
- **Type**: String (enum)
- **Default**: `development`
- **Options**: `development`, `testing`, `production`
- **Description**: Deployment environment
- **Notes**: Affects default settings and behavior

### DEBUG
- **Type**: Boolean
- **Default**: `false` (true in development)
- **Description**: Enable debug mode
- **Options**: `true`, `false`
- **Notes**: Automatically true when ENVIRONMENT=development

### KATO_CONFIG_FILE
- **Type**: String (file path)
- **Default**: `None`
- **Description**: Path to configuration file (YAML or JSON)
- **Example**: `/etc/kato/config.yaml`, `./config.json`
- **Notes**: File settings are overridden by environment variables. Unknown
  keys cause startup to fail.

### KATO_ENV_FILE
- **Type**: String (file path)
- **Default**: `None`
- **Description**: Explicit `.env` file to load instead of the discovered one

### KATO_SKIP_DOTENV
- **Type**: String
- **Default**: unset
- **Description**: Set to `1` to disable `.env` loading entirely

### Vector Database Variables

Read by `kato/config/vectordb_config.py`: `KATO_VECTOR_DB_BACKEND`,
`KATO_VECTOR_DIM`, `KATO_SIMILARITY_METRIC`, `KATO_QUANTIZATION_ENABLED`,
`KATO_QUANTIZATION_TYPE`, `KATO_CACHE_ENABLED`, and `KATO_VECTOR_CONFIG_FILE`
(a JSON/YAML file that overrides the env-derived vector config).

## Docker Compose Configuration Examples

### Primary Instance (Manual Learning)
```yaml
environment:
  - SERVICE_NAME=kato-primary
  - CLICKHOUSE_HOST=kato-clickhouse
  - CLICKHOUSE_PORT=8123
  - CLICKHOUSE_DB=kato
  - QDRANT_HOST=qdrant
  - QDRANT_PORT=6333
  - REDIS_URL=redis://redis:6379
  - SESSION_TTL=3600
  - MAX_PATTERN_LENGTH=0  # Manual learning only
  - PERSISTENCE=5
  - RECALL_THRESHOLD=0.1
  - LOG_LEVEL=INFO
```

### Testing Instance (Debug Mode)
```yaml
environment:
  - SERVICE_NAME=kato-testing
  - CLICKHOUSE_HOST=kato-clickhouse
  - CLICKHOUSE_PORT=8123
  - CLICKHOUSE_DB=kato
  - QDRANT_HOST=qdrant
  - QDRANT_PORT=6333
  - REDIS_URL=redis://redis:6379
  - SESSION_TTL=1800
  - MAX_PATTERN_LENGTH=10  # Auto-learn after 10
  - PERSISTENCE=5
  - RECALL_THRESHOLD=0.1
  - LOG_LEVEL=DEBUG
```

### Analytics Instance (Auto-Learning)
```yaml
environment:
  - SERVICE_NAME=kato-analytics
  - CLICKHOUSE_HOST=kato-clickhouse
  - CLICKHOUSE_PORT=8123
  - CLICKHOUSE_DB=kato
  - QDRANT_HOST=qdrant
  - QDRANT_PORT=6333
  - REDIS_URL=redis://redis:6379
  - SESSION_TTL=7200
  - MAX_PATTERN_LENGTH=50  # Auto-learn after 50
  - PERSISTENCE=10
  - RECALL_THRESHOLD=0.5
  - LOG_LEVEL=INFO
  - MAX_PREDICTIONS=200
```

## Configuration Profiles

### Development Profile
```bash
export SERVICE_NAME=kato-dev
export ENVIRONMENT=development
export LOG_LEVEL=DEBUG
export LOG_FORMAT=human
export MAX_PATTERN_LENGTH=5
export RECALL_THRESHOLD=0.1
```

### Production Profile
```bash
export SERVICE_NAME=kato-prod
export ENVIRONMENT=production
export LOG_LEVEL=WARNING
export LOG_FORMAT=json
export MAX_PATTERN_LENGTH=0
export RECALL_THRESHOLD=0.3
export MAX_PREDICTIONS=50
export REDIS_ENABLED=true
```

### Testing Profile
```bash
export SERVICE_NAME=kato-test
export ENVIRONMENT=testing
export LOG_LEVEL=INFO
export MAX_PATTERN_LENGTH=10
export RECALL_THRESHOLD=0.1
export PERSISTENCE=5
export KATO_USE_FAST_MATCHING=true
```

## Runtime Configuration Updates

Configuration can be updated at runtime using session-based endpoints:

### Updatable Parameters
- `recall_threshold` - Pattern matching sensitivity
- `max_predictions` - Maximum number of predictions returned
- `persistence` - Emotive value rolling window size
- `stm_mode` - Short-term memory mode (CLEAR/ROLLING)
- `process_predictions` - Enable/disable prediction processing
- `rank_sort_algo` - Prediction ranking metric
- `use_token_matching` - Pattern matching mode (token vs character level)
- `sort_symbols` - Sort symbols alphabetically within events
- `fuzzy_token_threshold` - Fuzzy token matching threshold
- `affinity_emotive` - Emotive used for affinity-weighted matching (session-only; there is no `AFFINITY_EMOTIVE` environment variable)

### Example Update Request
```bash
curl -X POST http://localhost:8000/sessions/{session_id}/config \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "recall_threshold": 0.5,
      "max_predictions": 50,
      "persistence": 10,
      "rank_sort_algo": "similarity"
    }
  }'
```

**Note**: Configuration changes only affect the specific session. Each session maintains independent configuration.

### Ranking Algorithm Selection

The `rank_sort_algo` parameter allows you to optimize predictions for different use cases:

```bash
# Prioritize overall potential (default - balanced approach)
curl -X POST http://localhost:8000/sessions/{session_id}/config \
  -H "Content-Type: application/json" \
  -d '{"config": {"rank_sort_algo": "potential"}}'

# Prioritize pattern similarity (best matches)
curl -X POST http://localhost:8000/sessions/{session_id}/config \
  -H "Content-Type: application/json" \
  -d '{"config": {"rank_sort_algo": "similarity"}}'

# Prioritize frequent patterns (most common)
curl -X POST http://localhost:8000/sessions/{session_id}/config \
  -H "Content-Type: application/json" \
  -d '{"config": {"rank_sort_algo": "frequency"}}'

# Prioritize predictive reliability
curl -X POST http://localhost:8000/sessions/{session_id}/config \
  -H "Content-Type: application/json" \
  -d '{"config": {"rank_sort_algo": "predictive_information"}}'
```

## Configuration Best Practices

### 1. Node Isolation
Isolation is per `node_id`, supplied when a session is created — not through
configuration:
```bash
# Each tenant/test run gets its own node_id
curl -X POST http://localhost:8000/sessions \
  -H "Content-Type: application/json" \
  -d '{"node_id": "test_'"$(uuidgen)"'"}'
```

### 2. Environment-Specific Settings
Adjust configuration based on deployment environment:

**Development**:
- LOG_LEVEL=DEBUG
- LOG_FORMAT=human
- MAX_PATTERN_LENGTH=5-10 (quick learning)
- RECALL_THRESHOLD=0.1 (see all matches)

**Production**:
- LOG_LEVEL=WARNING or ERROR
- LOG_FORMAT=json
- MAX_PATTERN_LENGTH=0 or high value
- RECALL_THRESHOLD=0.3-0.5 (filter noise)

### 3. Performance Tuning
For high-throughput scenarios:
- MAX_PREDICTIONS=20-50 (limit response size)
- KATO_WORKERS / KATO_LIMIT_CONCURRENCY sized to the host
- CONNECTION_POOL_SIZE tuned against Redis `maxclients` (per worker)
- KATO_USE_BLOOM_FILTER=true and KATO_USE_REDIS_CACHE=true
- REDIS_ENABLED=true (enable caching)

### 4. Memory Management
For long-running instances:
- MAX_PATTERN_LENGTH > 0 (prevent unbounded STM growth)
- PERSISTENCE=5-10 (limit emotives history)
- MAX_PREDICTIONS sized to the response payload you can afford

## Troubleshooting Configuration Issues

### Issue: Database Conflicts
**Symptom**: Unexpected patterns appearing, test contamination
**Solution**: Ensure each instance or test run uses a unique `node_id`

### Issue: No Predictions Generated
**Symptom**: Empty prediction lists
**Causes**:
- RECALL_THRESHOLD too high (try 0.1)
- PROCESS_PREDICTIONS=false
- STM has < 2 strings

### Issue: Too Many Predictions
**Symptom**: Large response payloads, slow API
**Solution**: 
- Reduce MAX_PREDICTIONS
- Increase RECALL_THRESHOLD
- Tighten the session's filter pipeline thresholds

### Issue: Auto-Learning Not Triggering
**Symptom**: STM grows unbounded
**Solution**: 
- Set MAX_PATTERN_LENGTH > 0 — it is the only auto-learn trigger

### Issue: Patterns Not Matching
**Symptom**: Known patterns not found
**Causes**:
- SORT_SYMBOLS differs between learning and matching
- RECALL_THRESHOLD too high
- Different `node_id` (different knowledge base)

### Issue: Poor Performance
**Symptom**: Slow responses, high latency
**Solution**:
- Enable KATO_USE_FAST_MATCHING=true
- Enable KATO_USE_INDEXING=true
- Enable REDIS_ENABLED=true
- Increase CONNECTION_POOL_SIZE (per worker)
- Increase KATO_WORKERS / KATO_LIMIT_CONCURRENCY

## Validation Rules

1. **RECALL_THRESHOLD**: Must be greater than 0.0 and at most 1.0
2. **MAX_PATTERN_LENGTH**: Must be >= 0
3. **PERSISTENCE**: Must be between 1 and 100
4. **MAX_PREDICTIONS**: Must be between 1 and 10000
5. **SESSION_TTL**: Must be between 60 and 86400
6. **CONNECTION_POOL_SIZE**: Must be between 1 and 1000
7. **REQUEST_TIMEOUT**: Must be between 1.0 and 300.0
8. **ENVIRONMENT**: Must be `development`, `testing` or `production`
9. **ENVIRONMENT**: Must be valid option (development/testing/production)