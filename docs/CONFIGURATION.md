# KATO Configuration Guide

Complete reference for all KATO configuration options and environment variables.

## Environment Variables

KATO uses environment variables for configuration. These can be set in:
- Docker Compose files
- Shell environment
- `.env` files
- Container runtime parameters

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

### LOG_LEVEL
- **Type**: String (enum)
- **Default**: `INFO`
- **Options**: `DEBUG`, `INFO`, `WARNING`, `ERROR`
- **Description**: Controls logging verbosity
- **Notes**: Use `DEBUG` for troubleshooting, `INFO` for production

### PORT
- **Type**: Integer
- **Default**: `8000`
- **Description**: Port number for FastAPI service
- **Example**: `8001`, `8002`, `8003`

## Database Configuration

### MONGO_BASE_URL
- **Type**: String (MongoDB connection string)
- **Default**: `mongodb://localhost:27017`
- **Description**: MongoDB connection string
- **Example**: `mongodb://mongo:27017`, `mongodb://user:pass@host:27017`
- **Notes**: Each processor creates its own database named after PROCESSOR_ID

### QDRANT_HOST
- **Type**: String
- **Default**: `localhost`
- **Description**: Qdrant vector database host
- **Example**: `qdrant`, `192.168.1.100`

### QDRANT_PORT
- **Type**: Integer
- **Default**: `6333`
- **Description**: Qdrant vector database port
- **Example**: `6333`, `6334`

## Learning Configuration

### MAX_PATTERN_LENGTH
- **Type**: Integer
- **Default**: `0`
- **Description**: Auto-learn after N observations (0 = manual learning only)
- **Example**: `0` (manual), `10` (auto-learn after 10 observations), `50`
- **Notes**: When reached, triggers automatic pattern learning and STM clearing

### PERSISTENCE
- **Type**: Integer
- **Default**: `5`
- **Range**: `1` to unlimited (practical max: 100)
- **Description**: Rolling window size for emotive value history per pattern
- **Example**: `5`, `10`, `20`
- **Notes**: Controls adaptive learning and memory for emotional/utility values

**How PERSISTENCE Works:**
- Each pattern maintains arrays of emotive values (one array per emotive type)
- Arrays are limited to PERSISTENCE length using MongoDB's `$slice` operator
- When a pattern is re-learned with new emotive values, oldest values drop off
- This creates a rolling window that adapts to changing contexts

**Configuration Impact:**
- **Low values (1-5)**: Fast adaptation, quick forgetting of old emotives
- **Medium values (5-10)**: Balanced memory and adaptation (default range)
- **High values (10-20)**: Longer memory, slower adaptation to changes
- **Very high (20+)**: Extended historical context, resistant to change

**Use Cases by PERSISTENCE Value:**
- `1`: Only most recent emotive matters (instant adaptation)
- `3-5`: Quick response to emotional changes (chatbots, real-time systems)
- `5-10`: Standard applications with moderate memory needs
- `10-20`: Systems requiring emotional trend analysis
- `20+`: Long-term emotional profiling or sentiment tracking

### RECALL_THRESHOLD
- **Type**: Float
- **Default**: `0.1`
- **Range**: `0.0` to `1.0`
- **Description**: Pattern matching sensitivity threshold
- **Examples**:
  - `0.0`: Include all patterns (even non-matching)
  - `0.1`: Very permissive (default)
  - `0.3`: Permissive
  - `0.5`: Moderate filtering
  - `0.7`: Strict
  - `0.9`: Very strict
  - `1.0`: Exact matches only
- **Notes**: Lower values return more predictions with partial matches

### SMOOTHNESS
- **Type**: Integer
- **Default**: `3`
- **Description**: Smoothing factor for pattern matching
- **Example**: `1` (no smoothing), `3` (moderate), `5` (high smoothing)
- **Notes**: Higher values provide more lenient matching

## Processing Configuration

### INDEXER_TYPE
- **Type**: String
- **Default**: `VI`
- **Description**: Type of vector indexing
- **Options**: `VI` (Vector Indexing)
- **Notes**: Controls vector storage and retrieval strategy

### AUTO_ACT_METHOD
- **Type**: String
- **Default**: `none`
- **Description**: Method for automatic actions
- **Options**: `none`, `threshold`, `pattern`
- **Notes**: Enables automated responses based on patterns

### AUTO_ACT_THRESHOLD
- **Type**: Float
- **Default**: `0.8`
- **Range**: `0.0` to `1.0`
- **Description**: Threshold for triggering automatic actions
- **Notes**: Only used when AUTO_ACT_METHOD is not `none`

### ALWAYS_UPDATE_FREQUENCIES
- **Type**: Boolean
- **Default**: `false`
- **Description**: Update pattern frequencies on re-observation
- **Options**: `true`, `false`
- **Notes**: When true, re-observing a pattern increments its frequency

### MAX_PREDICTIONS
- **Type**: Integer
- **Default**: `100`
- **Description**: Maximum number of predictions to return
- **Example**: `10`, `50`, `100`, `1000`
- **Notes**: Limits prediction response size for performance

### QUIESCENCE
- **Type**: Integer
- **Default**: `3`
- **Description**: Quiescence period for pattern stabilization
- **Example**: `1`, `3`, `5`
- **Notes**: Number of observations before certain operations trigger

### SEARCH_DEPTH
- **Type**: Integer
- **Default**: `10`
- **Description**: Maximum depth for pattern search operations
- **Example**: `5`, `10`, `20`
- **Notes**: Controls search exhaustiveness vs performance

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

## Docker Compose Configuration Examples

### Primary Instance (Manual Learning)
```yaml
environment:
  - PROCESSOR_ID=primary
  - PROCESSOR_NAME=PrimaryProcessor
  - LOG_LEVEL=INFO
  - MAX_PATTERN_LENGTH=0  # Manual learning only
  - PERSISTENCE=5
  - RECALL_THRESHOLD=0.1
  - PORT=8001
```

### Testing Instance (Debug Mode)
```yaml
environment:
  - PROCESSOR_ID=testing
  - PROCESSOR_NAME=TestingProcessor
  - LOG_LEVEL=DEBUG
  - MAX_PATTERN_LENGTH=10  # Auto-learn after 10
  - PERSISTENCE=10
  - RECALL_THRESHOLD=0.3
  - PORT=8002
```

### Analytics Instance (Auto-Learning)
```yaml
environment:
  - PROCESSOR_ID=analytics
  - PROCESSOR_NAME=AnalyticsProcessor
  - LOG_LEVEL=WARNING
  - MAX_PATTERN_LENGTH=50  # Auto-learn after 50
  - PERSISTENCE=20
  - RECALL_THRESHOLD=0.5  # Stricter matching
  - MAX_PREDICTIONS=200
  - PORT=8003
```

## Configuration Profiles

### Development Profile
```bash
export PROCESSOR_ID=dev
export LOG_LEVEL=DEBUG
export MAX_PATTERN_LENGTH=5
export RECALL_THRESHOLD=0.1
export SORT=true
export PROCESS_PREDICTIONS=true
```

### Production Profile
```bash
export PROCESSOR_ID=prod
export LOG_LEVEL=WARNING
export MAX_PATTERN_LENGTH=0
export RECALL_THRESHOLD=0.3
export MAX_PREDICTIONS=50
export ALWAYS_UPDATE_FREQUENCIES=true
```

### Testing Profile
```bash
export PROCESSOR_ID=test_$(date +%s)
export LOG_LEVEL=INFO
export MAX_PATTERN_LENGTH=10
export RECALL_THRESHOLD=0.1
export PERSISTENCE=5
```

## Runtime Configuration Updates

Some configuration can be updated at runtime using the `/genes/update` endpoint:

### Updatable Genes
- `recall_threshold`
- `max_predictions`
- `persistence`
- `smoothness`
- `quiescence`
- `always_update_frequencies`

### Example Update Request
```bash
curl -X POST http://localhost:8001/genes/update \
  -H "Content-Type: application/json" \
  -d '{
    "genes": {
      "recall_threshold": 0.5,
      "max_predictions": 50
    }
  }'
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

**Production**:
- LOG_LEVEL=WARNING or ERROR
- MAX_PATTERN_LENGTH=0 or high value
- RECALL_THRESHOLD=0.3-0.5 (filter noise)

### 3. Performance Tuning
For high-throughput scenarios:
- MAX_PREDICTIONS=20-50 (limit response size)
- SEARCH_DEPTH=5-10 (balance accuracy/speed)
- PROCESS_PREDICTIONS=false (observation-only mode)

### 4. Memory Management
For long-running instances:
- MAX_PATTERN_LENGTH > 0 (prevent unbounded STM growth)
- PERSISTENCE=5-10 (limit emotives history)

## Validation Rules

1. **PROCESSOR_ID**: Must be unique across all instances
2. **RECALL_THRESHOLD**: Must be between 0.0 and 1.0
3. **MAX_PATTERN_LENGTH**: Must be >= 0
4. **PERSISTENCE**: Must be > 0
5. **MAX_PREDICTIONS**: Must be > 0
6. **PORT**: Must be available and >= 1024 for non-root

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
**Solution**: Reduce MAX_PREDICTIONS or increase RECALL_THRESHOLD

### Issue: Auto-Learning Not Triggering
**Symptom**: STM grows unbounded
**Solution**: Set MAX_PATTERN_LENGTH > 0 (e.g., 10, 50)

### Issue: Patterns Not Matching
**Symptom**: Known patterns not found
**Causes**:
- SORT setting differs between learning and matching
- RECALL_THRESHOLD too high
- Different PROCESSOR_ID (different database)