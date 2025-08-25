# KATO Configuration Guide

Complete guide to configuring KATO processors and system parameters.

## Configuration Methods

KATO supports three configuration methods:

1. **Command-line parameters** - Direct parameter specification
2. **Environment variables** - System-wide defaults
3. **JSON manifest** - Complete configuration object

## Command-Line Parameters

All parameters can be specified directly when starting KATO:

```bash
./kato-manager.sh start [OPTIONS]
```

### Core Identity Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `--id` | string | auto-generated | Unique processor identifier |
| `--name` | string | "KatoProcessor" | Human-readable processor name |
| `--port` | integer | 8000 | REST API port |
| `--log-level` | string | INFO | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `--api-key` | string | none | API key for authentication |

### Machine Learning Parameters

| Parameter | Type | Default | Range | Description |
|-----------|------|---------|-------|-------------|
| `--classifier` | string | "CVC" | CVC, DVC | Classifier type |
| `--max-predictions` | integer | 100 | 1-1000 | Maximum predictions to generate |
| `--recall-threshold` | float | 0.1 | 0.0-1.0 | Minimum similarity for recall |
| `--search-depth` | integer | 10 | 1-100 | Vector search depth |

### Memory and Learning Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `--max-seq-length` | integer | 0 | **Auto-learning threshold**: When working memory reaches this length, automatically learn sequence and reset (0=disabled) |
| `--persistence` | integer | 5 | Emotive persistence duration |
| `--smoothness` | integer | 3 | Learning smoothness parameter |
| `--quiescence` | integer | 3 | Quiescence period |

#### Auto-Learning Feature (`max_sequence_length`)

When `max_sequence_length` is set to a value greater than 0, KATO automatically learns sequences when working memory reaches the threshold:

**Behavior:**
1. **Accumulation**: Working memory accumulates observations normally
2. **Trigger**: When length reaches `max_sequence_length`, auto-learning activates  
3. **Learning**: The entire working memory sequence is learned as a model
4. **Reset**: Working memory is cleared, keeping only the last observation
5. **Continuation**: System continues processing with learned model available

**Example:**
```bash
# Set auto-learning at 3 observations
./kato-manager.sh start --max-seq-length 3

# Or update dynamically via API
curl -X POST http://localhost:8000/p46b6b076c/genes/change \
  -d '{"data": {"max_sequence_length": 3}}'
```

**Use Cases:**
- **Streaming data**: Continuous learning from data streams
- **Memory management**: Prevent working memory overflow
- **Pattern recognition**: Automatic detection of recurring sequences  
- **Real-time systems**: Background learning without manual intervention

### Behavior Control Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `--auto-act-method` | string | "none" | Auto-action method |
| `--auto-act-threshold` | float | 0.8 | Auto-action threshold (0.0-1.0) |
| `--update-frequencies` | flag | false | Always update model frequencies |
| `--no-sort` | flag | false | Disable alphanumeric sorting |
| `--no-predictions` | flag | false | Disable prediction processing |

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
  --classifier CVC \
  --max-predictions 50 \
  --recall-threshold 0.2 \
  --log-level DEBUG \
  --port 8080
```

### Production Configuration

```bash
./kato-manager.sh start \
  --name "ProdProcessor" \
  --classifier DVC \
  --max-predictions 200 \
  --recall-threshold 0.05 \
  --persistence 10 \
  --search-depth 15 \
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
  --search-depth 25 \
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
| `KATO_CLASSIFIER` | `--classifier` |
| `KATO_MAX_PREDICTIONS` | `--max-predictions` |
| `KATO_RECALL_THRESHOLD` | `--recall-threshold` |
| `KATO_SEARCH_DEPTH` | `--search-depth` |
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
  "classifier": "CVC",
  "max_sequence_length": 0,
  "persistence": 5,
  "smoothness": 3,
  "auto_act_method": "none",
  "auto_act_threshold": 0.8,
  "always_update_frequencies": false,
  "max_predictions": 100,
  "recall_threshold": 0.1,
  "quiescence": 3,
  "search_depth": 10,
  "sort": true,
  "process_predictions": true
}
```

This manifest is automatically generated from command-line parameters.

## Parameter Details

### Classifier Types

**CVC (Contiguous Vector Classifier)**
- Best for sequential data
- Lower memory usage
- Faster processing
- Suitable for most use cases

**DVC (Distributed Vector Classifier)**
- Better for complex patterns
- Higher memory usage
- More sophisticated matching
- Suitable for research/advanced use

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

### Max Sequence Length

Controls auto-learning trigger:
- `0`: No limit (manual learning only)
- `10-50`: Frequent learning cycles
- `100-500`: Moderate cycles
- `1000+`: Rare auto-learning

## Configuration Profiles

### Speed-Optimized
```bash
./kato-manager.sh start \
  --classifier CVC \
  --max-predictions 20 \
  --recall-threshold 0.3 \
  --search-depth 5 \
  --no-predictions
```

### Accuracy-Optimized
```bash
./kato-manager.sh start \
  --classifier DVC \
  --max-predictions 500 \
  --recall-threshold 0.01 \
  --search-depth 50 \
  --update-frequencies
```

### Memory-Optimized
```bash
./kato-manager.sh start \
  --classifier CVC \
  --max-predictions 50 \
  --max-seq-length 100 \
  --persistence 3 \
  --search-depth 5
```

### Real-Time Processing
```bash
./kato-manager.sh start \
  --classifier CVC \
  --max-predictions 10 \
  --recall-threshold 0.5 \
  --search-depth 3 \
  --max-seq-length 50
```

## Validation Rules

The manager script validates all parameters:

| Parameter | Validation |
|-----------|------------|
| `classifier` | Must be "CVC" or "DVC" |
| `max_predictions` | Integer, 1-1000 |
| `recall_threshold` | Float, 0.0-1.0 |
| `auto_act_threshold` | Float, 0.0-1.0 |
| `persistence` | Integer, >= 1 |
| `search_depth` | Integer, >= 1 |
| `port` | Integer, 1024-65535 |

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

## Configuration Best Practices

### 1. Start Simple
Begin with defaults and adjust based on performance:
```bash
./kato-manager.sh start --name "Test"
```

### 2. Profile Your Use Case
- High-volume: Optimize for speed
- Research: Optimize for accuracy
- Production: Balance all factors

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

## Migration from Genome Files

Previously, KATO used genome files for configuration. To migrate:

### Old Genome Format
```json
{
  "elements": {
    "nodes": [{
      "data": {
        "id": "p46b6b076c",
        "name": "P1",
        "classifier": "CVC",
        "max_predictions": 100
      }
    }]
  }
}
```

### New Parameter Format
```bash
./kato-manager.sh start \
  --id p46b6b076c \
  --name P1 \
  --classifier CVC \
  --max-predictions 100
```

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