# KATO Parameter-Based Configuration

The KATO management system now supports direct parameter-based configuration instead of requiring genome files. This provides more flexibility and easier integration with deployment scripts.

## Migration from Genome Files

Previously, KATO required genome files (`.genome` or `.json`) containing complex nested structures. Now you can specify processor parameters directly as command-line arguments.

### Before (Genome File):
```json
{
  "elements": {
    "nodes": [{
      "data": {
        "id": "p46b6b076c",
        "name": "P1", 
        "classifier": "CVC",
        "max_predictions": 100,
        "recall_threshold": 0.1,
        "persistence": 5
        // ... many more parameters
      }
    }]
  }
}
```

### After (Direct Parameters):
```bash
./kato-manager.sh start --name P1 --classifier CVC --max-predictions 100 --recall-threshold 0.1
```

## Available Parameters

All parameters that were previously defined in genome files can now be specified as command-line arguments:

### Core Identity
- `--id ID` - Unique processor identifier (default: auto-generated)
- `--name NAME` - Human-readable processor name (default: "KatoProcessor")

### Machine Learning Configuration
- `--classifier TYPE` - Classifier type: CVC or DVC (default: "CVC")
- `--max-predictions N` - Maximum number of predictions (default: 100)
- `--recall-threshold T` - Recall threshold 0.0-1.0 (default: 0.1)
- `--search-depth N` - Vector search depth (default: 10)

### Memory and Learning
- `--max-seq-length N` - Maximum sequence length, 0=unlimited (default: 0)
- `--persistence N` - How long to remember emotives (default: 5)
- `--smoothness N` - Smoothness parameter for learning (default: 3)
- `--quiescence N` - Quiescence parameter (default: 3)

### Behavior Control
- `--auto-act-method M` - Auto-action method (default: "none")
- `--auto-act-threshold T` - Auto-action threshold 0.0-1.0 (default: 0.8)
- `--update-frequencies` - Always update frequencies flag (default: false)
- `--no-sort` - Disable symbol sorting (default: enabled)
- `--no-predictions` - Disable prediction processing (default: enabled)

## Usage Examples

### Basic Usage
```bash
# Start with all defaults
./kato-manager.sh start

# Start with custom name and port
./kato-manager.sh start --name "ProductionProcessor" --port 9000
```

### Development Configuration
```bash
# Development setup with debug logging
./kato-manager.sh start \
  --name "DevProcessor" \
  --classifier CVC \
  --max-predictions 50 \
  --recall-threshold 0.2 \
  --log-level DEBUG
```

### Production Configuration
```bash
# Production setup with optimized parameters
./kato-manager.sh start \
  --name "ProdProcessor" \
  --classifier DVC \
  --max-predictions 200 \
  --recall-threshold 0.05 \
  --persistence 10 \
  --search-depth 15 \
  --port 8080
```

### Research Configuration
```bash
# Research setup with extended memory
./kato-manager.sh start \
  --name "ResearchProcessor" \
  --max-seq-length 1000 \
  --persistence 20 \
  --smoothness 5 \
  --update-frequencies
```

## Parameter Validation

The management script validates all parameters:

- **Classifier**: Must be "CVC" or "DVC"
- **Numeric values**: Must be valid integers (max-predictions, persistence, etc.)
- **Thresholds**: Must be between 0.0 and 1.0 (recall-threshold, auto-act-threshold)
- **Boolean flags**: Automatically handled for --no-sort, --no-predictions, --update-frequencies

## Generated Manifest

Parameters are automatically converted to a JSON manifest that KatoProcessor expects:

```json
{
  "id": "kato-processor-1234567890",
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

## Docker Integration

The Docker containers receive the generated manifest via environment variables:

```bash
docker run -e "MANIFEST={...generated_json...}" kato:latest
```

## Environment Variables

You can also use environment variables to set defaults:

```bash
export KATO_PROCESSOR_NAME="MyProcessor"
export KATO_MAX_PREDICTIONS=150
./kato-manager.sh start
```

## Migration Guide

To migrate from genome files:

1. **Identify your current genome parameters**:
   ```bash
   # Extract parameters from genome file
   cat kato-tests/test-genomes/your-genome.genome | jq '.elements.nodes[0].data'
   ```

2. **Convert to command-line arguments**:
   - `"name": "P1"` → `--name P1`
   - `"classifier": "DVC"` → `--classifier DVC`
   - `"max_predictions": 50` → `--max-predictions 50`

3. **Test the new configuration**:
   ```bash
   ./kato-manager.sh start --name P1 --classifier DVC --max-predictions 50
   ```

4. **Verify the generated manifest**:
   ```bash
   ./kato-manager.sh config
   ```

## Benefits

- **Simpler deployment**: No need to manage genome files
- **Better CI/CD integration**: Direct parameter passing
- **Easier configuration management**: Standard command-line interface
- **Dynamic configuration**: Parameters can be computed at runtime
- **Better documentation**: Self-documenting via --help

## Backwards Compatibility

Genome files are no longer required or supported. All configuration is now done via direct parameters, making the system more straightforward and maintainable.