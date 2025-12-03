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

### PROCESSOR_ID
- **Type**: String
- **Default**: Auto-generated `kato-<uuid>-<timestamp>`
- **Description**: Unique identifier for the processor instance
- **Example**: `primary`, `test_processor_123`
- **Notes**: Critical for database isolation - each instance MUST have unique ID

### PROCESSOR_NAME
- **Type**: String
- **Default**: `KatoProcessor`
- **Description**: Human-readable display name for the processor
- **Example**: `PrimaryProcessor`, `TestingInstance`

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

### QDRANT_COLLECTION_PREFIX
- **Type**: String
- **Default**: `vectors`
- **Description**: Prefix for Qdrant collection names
- **Example**: `vectors`, `embeddings`
- **Notes**: Full collection name becomes `{prefix}_{session_id}`

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

### AUTO_LEARN_ENABLED
- **Type**: Boolean
- **Default**: `false`
- **Description**: Enable automatic pattern learning
- **Options**: `true`, `false`
- **Notes**: Works in conjunction with AUTO_LEARN_THRESHOLD

### AUTO_LEARN_THRESHOLD
- **Type**: Integer
- **Default**: `50`
- **Range**: `1` to unlimited
- **Description**: Number of observations before auto-learning triggers
- **Example**: `10`, `50`, `100`
- **Notes**: Only applies when AUTO_LEARN_ENABLED is true

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

### SORT
- **Type**: Boolean
- **Default**: `true`
- **Description**: Sort symbols alphabetically within events
- **Options**: `true`, `false`
- **Notes**: Enable for deterministic pattern matching

### PROCESS_PREDICTIONS
- **Type**: Boolean
- **Default**: `true`
- **Description**: Enable prediction processing
- **Options**: `true`, `false`
- **Notes**: Can be disabled for observation-only mode

### KATO_USE_TOKEN_MATCHING
- **Type**: Boolean
- **Default**: `false`
- **Description**: Use token-level (vs character-level) pattern matching
- **Options**:
  - `false` (default): Character-level matching - Faster (75x speedup), ~0.03 score difference
  - `true`: Token-level matching - Slower (9x speedup), EXACT difflib compatibility
- **Performance Trade-off**:
  - Character-level: Best for production, high throughput
  - Token-level: Best for testing, exact similarity requirements
- **Notes**:
  - Token mode provides EXACT difflib.SequenceMatcher compatibility
  - Character mode is recommended for most use cases
  - See [Pattern Matching Documentation](PATTERN_MATCHING.md) for details

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

### KATO_USE_FAST_MATCHING
- **Type**: Boolean
- **Default**: `true`
- **Description**: Use optimized fast matching algorithms
- **Options**: `true`, `false`
- **Notes**: Significantly improves pattern matching speed

### KATO_USE_INDEXING
- **Type**: Boolean
- **Default**: `true`
- **Description**: Use pattern indexing for faster lookups
- **Options**: `true`, `false`
- **Notes**: Creates indexes for common query patterns

### KATO_USE_OPTIMIZED
- **Type**: Boolean
- **Default**: `true`
- **Description**: Enable general performance optimizations
- **Options**: `true`, `false`
- **Notes**: Applies various optimization strategies

### KATO_BATCH_SIZE
- **Type**: Integer
- **Default**: `1000`
- **Range**: `1` to `100000`
- **Description**: Batch size for bulk database operations
- **Example**: `100`, `1000`, `10000`
- **Notes**: Larger batches improve throughput but use more memory

### KATO_VECTOR_BATCH_SIZE
- **Type**: Integer
- **Default**: `1000`
- **Range**: `1` to `100000`
- **Description**: Batch size for vector operations
- **Example**: `100`, `1000`, `5000`
- **Notes**: Optimize based on vector dimension and available memory

### KATO_VECTOR_SEARCH_LIMIT
- **Type**: Integer
- **Default**: `100`
- **Range**: `1` to `10000`
- **Description**: Maximum vector search results
- **Example**: `50`, `100`, `500`
- **Notes**: Limits vector similarity search results

### CONNECTION_POOL_SIZE
- **Type**: Integer
- **Default**: `10`
- **Range**: `1` to `100`
- **Description**: Database connection pool size
- **Example**: `5`, `10`, `20`
- **Notes**: Balance between resource usage and concurrency

### REQUEST_TIMEOUT
- **Type**: Float
- **Default**: `30.0`
- **Range**: `1.0` to `300.0`
- **Description**: Request timeout in seconds
- **Example**: `10.0`, `30.0`, `60.0`
- **Notes**: Prevents hanging requests

## API Configuration

### HOST
- **Type**: String
- **Default**: `0.0.0.0`
- **Description**: API host address to bind to
- **Example**: `0.0.0.0`, `localhost`, `127.0.0.1`
- **Notes**: Use `0.0.0.0` for Docker containers

### PORT
- **Type**: Integer
- **Default**: `8000`
- **Range**: `1` to `65535`
- **Description**: API port number
- **Example**: `8000`, `8001`, `8002`
- **Notes**: Must be available and >= 1024 for non-root

### WORKERS
- **Type**: Integer
- **Default**: `1`
- **Range**: `1` to `16`
- **Description**: Number of worker processes
- **Example**: `1`, `4`, `8`
- **Notes**: Set based on CPU cores available

### CORS_ENABLED
- **Type**: Boolean
- **Default**: `true`
- **Description**: Enable CORS support
- **Options**: `true`, `false`
- **Notes**: Required for browser-based clients

### CORS_ORIGINS
- **Type**: String (comma-separated) or List
- **Default**: `*`
- **Description**: Allowed CORS origins
- **Example**: `*`, `http://localhost:3000,http://example.com`
- **Notes**: Use specific origins in production

### DOCS_ENABLED
- **Type**: Boolean
- **Default**: `true`
- **Description**: Enable API documentation endpoints (/docs, /redoc)
- **Options**: `true`, `false`
- **Notes**: Consider disabling in production

### MAX_REQUEST_SIZE
- **Type**: Integer
- **Default**: `104857600` (100MB)
- **Range**: `1024` to unlimited
- **Description**: Maximum request size in bytes
- **Example**: `1048576` (1MB), `10485760` (10MB)
- **Notes**: Protects against memory exhaustion

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
- **Notes**: Use `json` for log aggregation systems

### LOG_OUTPUT
- **Type**: String
- **Default**: `stdout`
- **Description**: Log output destination
- **Example**: `stdout`, `stderr`, `/var/log/kato.log`
- **Notes**: File paths create rotating log files

## Session Configuration

### SESSION_TTL
- **Type**: Integer
- **Default**: `3600`
- **Description**: Session time-to-live in seconds
- **Example**: `1800` (30 min), `3600` (1 hour), `7200` (2 hours)
- **Notes**: Controls how long user sessions remain active

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
- **Notes**: File settings are overridden by environment variables

## Docker Compose Configuration Examples

### Primary Instance (Manual Learning)
```yaml
environment:
  - PROCESSOR_ID=primary
  - PROCESSOR_NAME=PrimaryProcessor
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
  - PORT=8001
```

### Testing Instance (Debug Mode)
```yaml
environment:
  - PROCESSOR_ID=testing
  - PROCESSOR_NAME=TestingProcessor
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
  - PORT=8002
```

### Analytics Instance (Auto-Learning)
```yaml
environment:
  - PROCESSOR_ID=analytics
  - PROCESSOR_NAME=AnalyticsProcessor
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
  - PORT=8003
```

## Configuration Profiles

### Development Profile
```bash
export PROCESSOR_ID=dev
export ENVIRONMENT=development
export LOG_LEVEL=DEBUG
export LOG_FORMAT=human
export MAX_PATTERN_LENGTH=5
export RECALL_THRESHOLD=0.1
export DOCS_ENABLED=true
export CORS_ORIGINS="*"
```

### Production Profile
```bash
export PROCESSOR_ID=prod_$(hostname)_$(date +%s)
export ENVIRONMENT=production
export LOG_LEVEL=WARNING
export LOG_FORMAT=json
export MAX_PATTERN_LENGTH=0
export RECALL_THRESHOLD=0.3
export MAX_PREDICTIONS=50
export DOCS_ENABLED=false
export CORS_ORIGINS="https://app.example.com"
export REDIS_ENABLED=true
```

### Testing Profile
```bash
export PROCESSOR_ID=test_$(date +%s)_$(uuidgen)
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

### 1. Processor Isolation
Always use unique PROCESSOR_ID values to ensure complete database isolation:
```bash
# Good - unique IDs
PROCESSOR_ID=prod_api_$(hostname)_$(date +%s)
PROCESSOR_ID=test_$(uuidgen)

# Bad - shared IDs
PROCESSOR_ID=kato  # Multiple instances will conflict
```

### 2. Environment-Specific Settings
Adjust configuration based on deployment environment:

**Development**:
- LOG_LEVEL=DEBUG
- MAX_PATTERN_LENGTH=5-10 (quick learning)
- RECALL_THRESHOLD=0.1 (see all matches)
- DOCS_ENABLED=true

**Production**:
- LOG_LEVEL=WARNING or ERROR
- MAX_PATTERN_LENGTH=0 or high value
- RECALL_THRESHOLD=0.3-0.5 (filter noise)
- DOCS_ENABLED=false
- CORS_ORIGINS=specific domains

### 3. Performance Tuning
For high-throughput scenarios:
- MAX_PREDICTIONS=20-50 (limit response size)
- KATO_BATCH_SIZE=5000-10000 (larger batches)
- KATO_VECTOR_SEARCH_LIMIT=50 (faster searches)
- CONNECTION_POOL_SIZE=20-50 (more connections)
- REDIS_ENABLED=true (enable caching)

### 4. Memory Management
For long-running instances:
- MAX_PATTERN_LENGTH > 0 (prevent unbounded STM growth)
- PERSISTENCE=5-10 (limit emotives history)
- KATO_BATCH_SIZE=appropriate for memory
- MAX_REQUEST_SIZE=reasonable limit

## Troubleshooting Configuration Issues

### Issue: Database Conflicts
**Symptom**: Unexpected patterns appearing, test contamination
**Solution**: Ensure unique PROCESSOR_ID for each instance

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
- Enable KATO_VECTOR_SEARCH_LIMIT

### Issue: Auto-Learning Not Triggering
**Symptom**: STM grows unbounded
**Solution**: 
- Set MAX_PATTERN_LENGTH > 0
- Or enable AUTO_LEARN_ENABLED=true with AUTO_LEARN_THRESHOLD

### Issue: Patterns Not Matching
**Symptom**: Known patterns not found
**Causes**:
- SORT setting differs between learning and matching
- RECALL_THRESHOLD too high
- Different PROCESSOR_ID (different database)

### Issue: Poor Performance
**Symptom**: Slow responses, high latency
**Solution**:
- Enable KATO_USE_FAST_MATCHING=true
- Enable KATO_USE_INDEXING=true
- Enable REDIS_ENABLED=true
- Increase CONNECTION_POOL_SIZE
- Tune batch sizes appropriately

## Validation Rules

1. **PROCESSOR_ID**: Must be unique across all instances
2. **RECALL_THRESHOLD**: Must be between 0.0 and 1.0
3. **MAX_PATTERN_LENGTH**: Must be >= 0
4. **PERSISTENCE**: Must be >= 1
5. **MAX_PREDICTIONS**: Must be > 0
6. **PORT**: Must be available and >= 1024 for non-root
7. **Batch sizes**: Must be > 0 and reasonable for memory
8. **Timeouts**: Must be positive numbers
9. **ENVIRONMENT**: Must be valid option (development/testing/production)