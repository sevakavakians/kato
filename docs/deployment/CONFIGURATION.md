# KATO Configuration Guide

Complete guide to configuring KATO processors and system parameters.

## Configuration Methods

KATO supports multiple configuration methods:

1. **Command-line parameters** - Direct parameter specification
2. **Environment variables** - System-wide defaults
3. **JSON manifest** - Complete configuration object
4. **Instance registry** - Automatic tracking in `~/.kato/instances.json`

## Command-Line Parameters

All parameters can be specified directly when starting KATO:

```bash
./kato-manager.sh start [OPTIONS]
```

### Core Identity Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `--id` | string | auto-generated | **Unique processor identifier** - Used for API routing and container naming |
| `--name` | string | "KatoProcessor" | Human-readable processor name for display |
| `--port` | integer | 8000 | REST API port (auto-finds next available if in use) |
| `--log-level` | string | INFO | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `--api-key` | string | none | API key for authentication |

**Multi-Instance Notes:**
- Each instance must have a unique `--id` 
- Container names are derived from the ID: `kato-${PROCESSOR_ID}`
- Ports are automatically allocated if defaults are in use
- All instances share the same MongoDB but maintain separate memory

### Machine Learning Parameters

| Parameter | Type | Default | Range | Description |
|-----------|------|---------|-------|-------------|
| `--indexer-type` | string | "VI" | VI only | Vector indexer type (only VI supported) |
| `--max-predictions` | integer | 100 | 1-1000 | Maximum predictions to generate |
| `--recall-threshold` | float | 0.1 | 0.0-1.0 | Minimum similarity for recall |

### Memory and Learning Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `--max-seq-length` | integer | 0 | **Auto-learning threshold**: When short-term memory reaches this length, automatically learn pattern and reset (0=disabled) |
| `--persistence` | integer | 5 | Emotive persistence duration |
| `--smoothness` | integer | 3 | Learning smoothness parameter |
| `--quiescence` | integer | 3 | Quiescence period |

#### Auto-Learning Feature (`max_pattern_length`)

When `max_pattern_length` is set to a value greater than 0, KATO automatically learns patterns when short-term memory reaches the threshold:

**Behavior:**
1. **Accumulation**: Short-term memory accumulates observations normally
2. **Trigger**: When length reaches `max_pattern_length`, auto-learning activates  
3. **Learning**: The entire short-term memory pattern is learned as a pattern
4. **Reset**: Short-term memory is cleared, keeping only the last observation
5. **Continuation**: System continues processing with learned pattern available

**Example:**
```bash
# Set auto-learning at 3 observations
./kato-manager.sh start --max-seq-length 3

# Or update dynamically via API
curl -X POST http://localhost:8000/p46b6b076c/genes/change \
  -d '{"data": {"max_pattern_length": 3}}'
```

**Use Cases:**
- **Streaming data**: Continuous learning from data streams
- **Memory management**: Prevent short-term memory overflow
- **Pattern recognition**: Automatic detection of recurring patterns  
- **Real-time systems**: Background learning without manual intervention

### Behavior Control Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `--auto-act-method` | string | "none" | Auto-action method |
| `--auto-act-threshold` | float | 0.8 | Auto-action threshold (0.0-1.0) |
| `--update-frequencies` | flag | false | Always update pattern frequencies |
| `--no-sort` | flag | false | Disable alphanumeric sorting |
| `--no-predictions` | flag | false | Disable prediction processing |

### ZeroMQ Configuration

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `KATO_ZMQ_IMPLEMENTATION` | string | "improved" | **ZMQ implementation**: "improved" (ROUTER/DEALER - recommended) or "legacy" (REQ/REP) |
| `ZMQ_PORT` | integer | 5555 | ZeroMQ server port |
| `REST_PORT` | integer | 8000 | REST gateway port |

**Important**: The "improved" ROUTER/DEALER implementation is strongly recommended for production use as it provides:
- Non-blocking communication (no deadlocks under load)
- Better timeout handling (graceful timeout without socket corruption)
- Connection health monitoring (30-second heartbeats)
- Concurrent request support (handles multiple clients efficiently)

Example:
```bash
# Use improved ROUTER/DEALER implementation (default and recommended)
export KATO_ZMQ_IMPLEMENTATION=improved
./kato-manager.sh start

# Only use legacy if you have specific compatibility requirements
export KATO_ZMQ_IMPLEMENTATION=legacy
./kato-manager.sh start
```

## Usage Examples

### Basic Configuration

```bash
# Start with all defaults
./kato-manager.sh start

# Custom name and port
./kato-manager.sh start --name "ProductionKATO" --port 9000
```

### Development Configuration

```bash
./kato-manager.sh start \
  --name "DevProcessor" \
  --indexer-type VI \
  --max-predictions 50 \
  --recall-threshold 0.2 \
  --log-level DEBUG \
  --port 8080
```

### Production Configuration

```bash
./kato-manager.sh start \
  --name "ProdProcessor" \
  --indexer-type VI \
  --max-predictions 200 \
  --recall-threshold 0.05 \
  --persistence 10 \
  --max-seq-length 1000 \
  --update-frequencies \
  --api-key "your-secret-key"
```

### Research Configuration

```bash
./kato-manager.sh start \
  --name "ResearchProcessor" \
  --max-seq-length 5000 \
  --persistence 20 \
  --smoothness 5 \
  --quiescence 5 \
  --log-level DEBUG
```

### Minimal Predictions

```bash
./kato-manager.sh start \
  --name "MinimalProcessor" \
  --max-predictions 10 \
  --recall-threshold 0.5 \
  --no-predictions  # Disable automatic predictions
```

## Environment Variables

Set defaults using environment variables:

```bash
# Export individual variables
export KATO_PROCESSOR_NAME="MyProcessor"
export KATO_MAX_PREDICTIONS=150
export KATO_LOG_LEVEL=DEBUG
export KATO_API_PORT=9000

# Or use .env file
cat > .env << EOF
KATO_PROCESSOR_NAME=MyProcessor
KATO_MAX_PREDICTIONS=150
KATO_RECALL_THRESHOLD=0.15
KATO_PERSISTENCE=10
KATO_LOG_LEVEL=INFO
EOF

# Start with environment defaults
./kato-manager.sh start
```

### Available Environment Variables

| Variable | Maps to Parameter |
|----------|-------------------|
| `KATO_PROCESSOR_ID` | `--id` |
| `KATO_PROCESSOR_NAME` | `--name` |
| `KATO_API_PORT` | `--port` |
| `KATO_LOG_LEVEL` | `--log-level` |
| `KATO_INDEXER_TYPE` | `--indexer-type` |
| `KATO_MAX_PREDICTIONS` | `--max-predictions` |
| `KATO_RECALL_THRESHOLD` | `--recall-threshold` |
| `KATO_MAX_SEQ_LENGTH` | `--max-seq-length` |
| `KATO_PERSISTENCE` | `--persistence` |
| `KATO_SMOOTHNESS` | `--smoothness` |
| `KATO_QUIESCENCE` | `--quiescence` |

## JSON Manifest

KATO internally uses a JSON manifest for configuration:

```json
{
  "id": "p46b6b076c",
  "name": "KatoProcessor",
  "indexer_type": "VI",
  "max_pattern_length": 0,
  "persistence": 5,
  "smoothness": 3,
  "auto_act_method": "none",
  "auto_act_threshold": 0.8,
  "always_update_frequencies": false,
  "max_predictions": 100,
  "recall_threshold": 0.1,
  "quiescence": 3,
  "sort": true,
  "process_predictions": true
}
```

This manifest is automatically generated from command-line parameters.

## Parameter Details

### Recall Threshold

Controls prediction sensitivity:
- `0.0`: Return all possible matches (many false positives)
- `0.1`: Default, balanced sensitivity
- `0.5`: Only high-confidence matches
- `1.0`: Only exact matches

### Max Predictions

Limits the number of predictions returned:
- Lower values (10-50): Faster response, less noise
- Default (100): Good balance
- Higher values (200+): Complete results, slower

### Persistence

How long emotives are retained:
- `1-5`: Short-term emotional context
- `5-10`: Default range
- `10-20`: Extended emotional memory
- `20+`: Long-term emotional tracking

### Max Pattern Length

Controls auto-learning trigger:
- `0`: No limit (manual learning only)
- `10-50`: Frequent learning cycles
- `100-500`: Moderate cycles
- `1000+`: Rare auto-learning

## Multi-Instance Configuration

### Instance Registry

KATO automatically maintains an instance registry at `~/.kato/instances.json`:

```json
{
  "instances": {
    "processor-1": {
      "name": "Main Processor",
      "container": "kato-processor-1",
      "api_port": 8001,
      "zmq_port": 5556,
      "status": "running",
      "updated": "2024-01-01T12:00:00"
    },
    "processor-2": {
      "name": "Secondary",
      "container": "kato-processor-2",
      "api_port": 8002,
      "zmq_port": 5557,
      "status": "running",
      "updated": "2024-01-01T12:05:00"
    }
  }
}
```

### Multi-Instance Examples

```bash
# Development setup - Different configurations
./kato-manager.sh start --id test-1 --name "Test High Recall" --port 8001 --recall-threshold 0.05
./kato-manager.sh start --id test-2 --name "Test Low Recall" --port 8002 --recall-threshold 0.5

# Production setup - Task-specific processors
./kato-manager.sh start --id nlp --name "NLP Engine" --port 8001 \
  --max-seq-length 20 --recall-threshold 0.2

./kato-manager.sh start --id stream --name "Stream Processor" --port 8002 \
  --max-predictions 50 --persistence 10

./kato-manager.sh start --id realtime --name "Real-time Stream" --port 8003 \
  --max-seq-length 5 --max-predictions 10

# View all instances
./kato-manager.sh list
```

## Configuration Profiles

### Speed-Optimized
```bash
./kato-manager.sh start \
  --id speed-opt \
  --indexer-type VI \
  --max-predictions 20 \
  --recall-threshold 0.3 \
  --no-predictions
```

### Accuracy-Optimized
```bash
./kato-manager.sh start \
  --indexer-type VI \
  --max-predictions 500 \
  --recall-threshold 0.01 \
  --update-frequencies
```

### Memory-Optimized
```bash
./kato-manager.sh start \
  --indexer-type VI \
  --max-predictions 50 \
  --max-seq-length 100 \
  --persistence 3
```

### Real-Time Processing
```bash
./kato-manager.sh start \
  --indexer-type VI \
  --max-predictions 10 \
  --recall-threshold 0.5 \
  --max-seq-length 50
```

## Validation Rules

The manager script validates all parameters:

| Parameter | Validation | Default | Description |
|-----------|------------|---------|-------------|
| `indexer_type` | Must be "VI" | "VI" | Vector indexer type (only VI supported) |
| `max_predictions` | Integer, 1-1000 | 100 | Maximum predictions to generate |
| `recall_threshold` | Float, 0.0-1.0 | 0.1 | Minimum similarity for predictions (see tuning guide below) |
| `auto_act_threshold` | Float, 0.0-1.0 | 0.8 | Threshold for automatic actions |
| `persistence` | Integer, >= 1 | 5 | Emotive persistence duration |
| `quiescence` | Integer, >= 1 | 3 | Quiescence period |
| `port` | Integer, 1024-65535 | 8000 | REST API port |

## Dynamic Reconfiguration

Some parameters can be changed at runtime via the API:

```bash
# Change recall threshold
curl -X POST http://localhost:8000/p46b6b076c/gene/recall_threshold/change \
  -d '{"value": 0.2}'

# Update multiple parameters
curl -X POST http://localhost:8000/p46b6b076c/genes/update \
  -d '{
    "genes": {
      "max_predictions": 150,
      "persistence": 8
    }
  }'
```

## recall_threshold Tuning Guide

The `recall_threshold` parameter is critical for controlling prediction quality and quantity. It acts as a similarity filter, determining which pattern matches are returned as predictions.

### How It Works
1. KATO compares observed patterns against learned patterns
2. Each comparison generates a similarity score (0.0 to 1.0)
3. Only matches with similarity >= recall_threshold become predictions
4. Lower thresholds = more predictions (including weak matches)
5. Higher thresholds = fewer predictions (only strong matches)

### Recommended Values by Use Case

| Use Case | Threshold | Description |
|----------|-----------|-------------|
| **Pattern Discovery** | 0.05-0.15 | Find all possible patterns, including weak associations |
| **Development/Testing** | 0.1-0.3 | Default range, good for exploring system behavior |
| **Balanced Production** | 0.3-0.5 | Moderate filtering, reliable predictions |
| **High Precision** | 0.5-0.7 | Strong matches only, fewer false positives |
| **Exact Matching** | 0.8-1.0 | Near-perfect or perfect matches only |

### Impact on Different Pattern Types

#### Short Patterns (2-5 elements)
- **Low threshold (0.1)**: May match many unrelated patterns
- **Recommended**: 0.3-0.5 for meaningful matches
- **High threshold (0.7+)**: May miss valid variations

#### Medium Patterns (5-15 elements)
- **Low threshold (0.1)**: Good for finding partial matches
- **Recommended**: 0.2-0.4 for balanced results
- **High threshold (0.7+)**: Only very similar patterns

#### Long Patterns (15+ elements)
- **Low threshold (0.1)**: Captures distant relationships
- **Recommended**: 0.1-0.3 (similarity naturally decreases with length)
- **High threshold (0.7+)**: May produce no matches

### Performance Considerations
- **Lower thresholds** (< 0.3): More predictions to process, higher memory/CPU usage
- **Higher thresholds** (> 0.5): Faster processing, fewer predictions to evaluate
- **Optimization tip**: Start with higher threshold and decrease if needed

### Dynamic Adjustment Examples

```bash
# For initial pattern exploration
curl -X POST http://localhost:8000/{processor_id}/gene/recall_threshold/change \
  -d '{"value": 0.1}'

# For production with known patterns
curl -X POST http://localhost:8000/{processor_id}/gene/recall_threshold/change \
  -d '{"value": 0.4}'

# For high-precision matching
curl -X POST http://localhost:8000/{processor_id}/gene/recall_threshold/change \
  -d '{"value": 0.6}'
```

## Configuration Best Practices

### 1. Start Simple
Begin with defaults and adjust based on performance:
```bash
./kato-manager.sh start --name "Test"
```

### 2. Profile Your Use Case
- High-volume: Optimize for speed (higher recall_threshold)
- Research: Optimize for discovery (lower recall_threshold)
- Production: Balance all factors (moderate recall_threshold)

### 3. Monitor and Adjust
Use logs and metrics to fine-tune:
```bash
./kato-manager.sh start --log-level DEBUG
./kato-manager.sh logs kato -f
```

### 4. Document Your Configuration
Keep track of successful configurations:
```bash
# Save configuration
./kato-manager.sh config > config-production.json

# Document in version control
git add config-production.json
git commit -m "Production configuration baseline"
```

## Vector Database Configuration

KATO uses Qdrant as its vector database for high-performance similarity search.

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `KATO_VECTOR_DB_BACKEND` | qdrant | Vector database backend (currently only qdrant) |
| `KATO_SIMILARITY_METRIC` | cosine | Distance metric: cosine, euclidean, dot, manhattan |
| `QDRANT_HOST` | localhost | Qdrant server host |
| `QDRANT_PORT` | 6333 | Qdrant REST API port |
| `QDRANT_COLLECTION` | kato_vectors | Collection name for vectors |
| `KATO_VECTOR_DIM` | 768 | Vector dimension size |
| `KATO_VECTOR_BATCH_SIZE` | 100 | Batch size for vector operations |
| `KATO_VECTOR_SEARCH_LIMIT` | 100 | Maximum search results |

### Advanced Vector Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `KATO_GPU_ENABLED` | false | Enable GPU acceleration if available |
| `KATO_GPU_DEVICES` | 0 | Comma-separated GPU device IDs |
| `KATO_QUANTIZATION_ENABLED` | false | Enable vector quantization |
| `KATO_QUANTIZATION_TYPE` | scalar | Type: scalar, product, or binary |
| `KATO_CACHE_ENABLED` | false | Enable Redis caching layer |
| `REDIS_HOST` | localhost | Redis server host |
| `REDIS_PORT` | 6379 | Redis server port |

### HNSW Index Parameters

The Hierarchical Navigable Small World (HNSW) algorithm parameters can be tuned for performance:

| Parameter | Default | Description | Impact |
|-----------|---------|-------------|---------|
| `m` | 16 | Number of bi-directional links | Higher = better recall, more memory |
| `ef_construct` | 128 | Size of dynamic list during construction | Higher = better index quality, slower build |
| `ef` | 128 | Size of dynamic list during search | Higher = better recall, slower search |

Example configuration:
```bash
# High performance configuration
export KATO_SIMILARITY_METRIC=cosine
export KATO_VECTOR_BATCH_SIZE=200
export KATO_VECTOR_SEARCH_LIMIT=50

# GPU-accelerated configuration  
export KATO_GPU_ENABLED=true
export KATO_GPU_DEVICES=0,1

# Quantization for memory optimization
export KATO_QUANTIZATION_ENABLED=true
export KATO_QUANTIZATION_TYPE=scalar
```

## Configuration Reference

### Currently Used Parameters
These parameters are actively used by KATO:

| Parameter | Usage | Default |
|-----------|-------|----------|
| `id` | Unique processor identifier | auto-generated |
| `name` | Processor display name | "KatoProcessor" |
| `indexer_type` | Vector indexer (VI only) | "VI" |
| `max_pattern_length` | Auto-learning threshold | 0 (disabled) |
| `persistence` | Emotive persistence | 5 |
| `smoothness` | Learning smoothness | 3 |
| `auto_act_method` | Auto-action method | "none" |
| `auto_act_threshold` | Auto-action threshold | 0.8 |
| `always_update_frequencies` | Update pattern frequencies | false |
| `max_predictions` | Maximum predictions | 100 |
| `recall_threshold` | Similarity threshold | 0.1 |
| `quiescence` | Quiescence period | 3 |
| `sort` | Alphanumeric sorting | true |
| `process_predictions` | Process predictions | true |

## Troubleshooting Configuration

### Parameter Not Taking Effect
- Check parameter spelling (use hyphens, not underscores)
- Verify parameter is valid for your KATO version
- Check logs for validation errors

### Conflicts Between Sources
Priority order (highest to lowest):
1. Command-line parameters
2. Environment variables
3. Default values

### Performance Issues
- Start with conservative values
- Gradually increase limits
- Monitor resource usage

## Support

For configuration help:
- Review [API Reference](../API_REFERENCE.md) for runtime changes
- Check [Troubleshooting Guide](../technical/TROUBLESHOOTING.md)
- Open an issue on GitHub