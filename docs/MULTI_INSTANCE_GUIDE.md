# KATO Multi-Instance Management Guide

## Overview

KATO now supports running multiple independent processor instances simultaneously, each with unique IDs, names, and configurations. This guide explains how to create, manage, and configure multiple KATO instances.

## Key Features

- **Dynamic Instance Creation**: Create multiple KATO processors with unique IDs
- **Instance Registry**: Automatic tracking of all instances in `~/.kato/instances.json`
- **Port Management**: Automatic port allocation to avoid conflicts
- **Individual Control**: Start, stop, and restart specific instances
- **Configuration Files**: Support for YAML/JSON configuration files

## Quick Start

### Starting Multiple Instances

```bash
# Start first instance with custom ID and name
./kato-manager.sh start --id processor-1 --name "Main Processor" --port 8001

# Start second instance with different configuration
./kato-manager.sh start --id processor-2 --name "Secondary" --port 8002 --max-predictions 200

# Start third instance with auto-learning enabled
./kato-manager.sh start --id processor-3 --name "Auto Learner" --port 8003 --max-seq-length 10
```

### Managing Instances

```bash
# List all instances
./kato-manager.sh list

# Stop specific instance by ID or name (removes container)
./kato-manager.sh stop processor-1         # By ID
./kato-manager.sh stop "Main Processor"    # By name
./kato-manager.sh stop --id processor-1    # Explicit ID
./kato-manager.sh stop --name "Main"       # Explicit name

# Stop all instances
./kato-manager.sh stop                     # Asks about MongoDB
./kato-manager.sh stop --all               # Same as above
./kato-manager.sh stop --all --with-mongo  # Also stops MongoDB
./kato-manager.sh stop --all --no-mongo    # Keeps MongoDB running

# Check system status
./kato-manager.sh status
```

**Important**: The `stop` command now automatically removes containers after stopping them, preventing container accumulation. Instances are also removed from the registry.

## Instance Naming

Each KATO instance has:
- **ID**: Unique identifier used in API calls (e.g., `processor-1`)
- **Name**: Human-readable name for display (e.g., `"Main Processor"`)
- **Container Name**: Docker container name based on ID (e.g., `kato-processor-1`)

### Naming Rules
- IDs should contain only alphanumeric characters, hyphens, and underscores
- IDs are automatically sanitized for Docker compatibility
- If no ID is provided, one is auto-generated with timestamp and PID

## Port Management

Each instance requires two ports:
- **REST API Port**: For HTTP API access (default: 8000)
- **ZMQ Port**: For internal communication (default: 5555)

### Automatic Port Allocation
If the requested port is in use, KATO automatically finds the next available port:

```bash
# If port 8000 is busy, will use 8001, 8002, etc.
./kato-manager.sh start --id my-processor
```

### Manual Port Assignment
```bash
./kato-manager.sh start --id my-processor --port 9000
```

## Instance Registry

All instances are tracked in `~/.kato/instances.json`:

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

## Configuration Options

### Command Line Parameters

All standard KATO parameters can be set per instance:

```bash
./kato-manager.sh start \
  --id my-processor \
  --name "Custom Processor" \
  --port 8001 \
  --indexer-type VI \
  --max-predictions 50 \
  --recall-threshold 0.2 \
  --max-seq-length 10 \
  --persistence 5
```

### Available Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `--id` | Processor ID | auto-generated |
| `--name` | Processor name | KatoProcessor |
| `--port` | REST API port | 8000 |
| `--indexer-type` | Vector indexer type (VI only) | VI |
| `--max-predictions` | Maximum predictions | 100 |
| `--recall-threshold` | Recall threshold (0-1) | 0.1 |
| `--max-seq-length` | Max pattern length | 0 (unlimited) |
| `--persistence` | Persistence value | 5 |
| `--quiescence` | Quiescence period | 3 |

## Configuration Files

For complex multi-instance setups, use configuration files:

### YAML Configuration
```yaml
# multi-instance.yaml
instances:
  - id: sentiment-analyzer
    name: "Sentiment Analysis"
    port: 8001
    indexer_type: VI
    max_predictions: 50
    
  - id: pattern-matcher
    name: "Pattern Matching"
    port: 8002
    indexer_type: VI
    max_predictions: 100
```

*(Note: Full configuration file support is planned for future releases)*

## API Access

Each instance has its own API endpoint based on its processor ID:

```bash
# Instance 1: processor-1 on port 8001
curl http://localhost:8001/processor-1/ping

# Instance 2: processor-2 on port 8002
curl http://localhost:8002/processor-2/observe \
  -d '{"strings": ["hello"], "vectors": [], "emotives": {}}'

# Instance 3: processor-3 on port 8003
curl http://localhost:8003/processor-3/predictions
```

## Docker Networking

All instances share:
- **MongoDB**: Single MongoDB instance for all processors
- **Docker Network**: `kato-network` for inter-container communication

Each instance has:
- **Unique Container**: Named after processor ID
- **Isolated Memory**: Independent short-term memory and models
- **Separate Ports**: No port conflicts between instances

## Use Cases

### 1. Different Recall Thresholds
Run instances with different similarity thresholds:
```bash
./kato-manager.sh start --id high-recall --recall-threshold 0.05 --port 8001
./kato-manager.sh start --id low-recall --recall-threshold 0.5 --port 8002
```

### 2. Different Configurations
Test different parameter settings:
```bash
./kato-manager.sh start --id conservative --recall-threshold 0.3 --port 8001
./kato-manager.sh start --id aggressive --recall-threshold 0.05 --port 8002
```

### 3. Specialized Processors
Create task-specific processors:
```bash
./kato-manager.sh start --id nlp-processor --name "NLP" --max-seq-length 20 --port 8001
./kato-manager.sh start --id stream-processor --name "Stream" --max-predictions 50 --port 8002
```

## Container Management

### Automatic Cleanup
The `stop` command now automatically:
- Stops the running container
- Removes the container completely
- Cleans up the instance from the registry

This prevents accumulation of stopped containers and keeps your system clean.

### Stop Command Options

```bash
# Stop by ID or name
./kato-manager.sh stop processor-1        # Stops and removes container
./kato-manager.sh stop "My Processor"     # Find by name, then remove

# Stop all with options
./kato-manager.sh stop --all              # Stop all, prompt for MongoDB
./kato-manager.sh stop --all --with-mongo # Stop everything
./kato-manager.sh stop --all --no-mongo   # Keep MongoDB running

# Legacy commands still work
./kato-manager.sh stop                    # Same as --all
```

## Troubleshooting

### Port Conflicts
If you see "Port already in use":
- KATO will automatically try the next available port
- Or manually specify a different port with `--port`

### Instance Not Found
If an instance isn't listed:
- Check `~/.kato/instances.json`
- Verify the container exists: `docker ps -a | grep kato`
- The registry auto-cleans when containers are removed

### Cleanup
The stop command handles cleanup automatically, but if needed:
```bash
# Manual cleanup of orphaned containers
docker rm $(docker ps -a -q -f name=kato-)

# Reset instance registry
rm ~/.kato/instances.json
./kato-manager.sh list  # Recreates clean registry
```

## Best Practices

1. **Use Descriptive IDs**: Choose meaningful processor IDs (e.g., `sentiment-analyzer` not `p1`)
2. **Document Configurations**: Keep track of what each instance is configured for
3. **Monitor Resources**: Multiple instances consume more memory and CPU
4. **Use Port Ranges**: Assign instances to port ranges (e.g., 8001-8010 for production)
5. **Regular Cleanup**: Remove unused instances to free resources

## Examples

### Example 1: A/B Testing
```bash
# Version A with current settings
./kato-manager.sh start --id version-a --name "Version A" --port 8001

# Version B with experimental settings
./kato-manager.sh start --id version-b --name "Version B" \
  --port 8002 --max-predictions 200 --recall-threshold 0.05
```

### Example 2: Multi-Modal Processing
```bash
# Text processor
./kato-manager.sh start --id text-proc --name "Text" --port 8001

# High-performance processor
./kato-manager.sh start --id high-perf --name "Performance" \
  --port 8002 --max-predictions 20 --recall-threshold 0.3

# Combined processor
./kato-manager.sh start --id combined-proc --name "Combined" \
  --port 8003 --max-seq-length 15
```

## Future Enhancements

Planned features for future releases:
- Full configuration file support (YAML/JSON)
- Batch operations from config files
- Instance templates
- Load balancing between instances
- Instance groups and orchestration
- Metrics per instance
- Web UI for instance management

## Summary

The multi-instance capability allows KATO to:
- Run multiple independent processors simultaneously
- Test different configurations in parallel
- Scale processing capacity horizontally
- Isolate workloads for different use cases
- Facilitate A/B testing and experimentation

For more information, see the main [KATO documentation](../README.md).