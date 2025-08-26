# Getting Started with KATO

This guide will help you get KATO up and running in 5 minutes.

## Prerequisites

- Docker Desktop installed and running
- Bash shell (macOS/Linux) or WSL (Windows)
- 4GB+ available RAM
- Port 8000 available (or specify custom ports)

## Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/your-org/kato.git
cd kato
```

### 2. Make the Manager Script Executable

```bash
chmod +x kato-manager.sh
```

### 3. Build and Start KATO

```bash
# Build the Docker image
./kato-manager.sh build

# Start KATO with default settings (single instance)
./kato-manager.sh start

# Or start with custom processor ID and port
./kato-manager.sh start --id my-processor --name "My KATO" --port 8001
```

### 4. Verify Installation

```bash
# Check system status
./kato-manager.sh status

# Test the API
curl http://localhost:8000/kato-api/ping
```

You should see:
```json
{"status": "healthy", "message": "KATO API is running"}
```

## Your First KATO Session

### 1. Send an Observation

```bash
curl -X POST http://localhost:8000/p46b6b076c/observe \
  -H "Content-Type: application/json" \
  -d '{
    "strings": ["hello", "world"],
    "vectors": [],
    "emotives": {"joy": 0.8}
  }'
```

### 2. Check Working Memory

```bash
curl http://localhost:8000/p46b6b076c/working-memory
```

Response shows the sorted observation:
```json
{
  "working_memory": [["hello", "world"]]
}
```

### 3. Learn a Sequence

```bash
# Add more observations
curl -X POST http://localhost:8000/p46b6b076c/observe \
  -d '{"strings": ["how"], "vectors": [], "emotives": {}}'

curl -X POST http://localhost:8000/p46b6b076c/observe \
  -d '{"strings": ["are", "you"], "vectors": [], "emotives": {}}'

# Trigger learning
curl -X POST http://localhost:8000/p46b6b076c/learn
```

### 4. Get Predictions

```bash
# Clear working memory
curl -X POST http://localhost:8000/p46b6b076c/working-memory/clear

# Observe the start of the learned sequence
curl -X POST http://localhost:8000/p46b6b076c/observe \
  -d '{"strings": ["hello"], "vectors": [], "emotives": {}}'

# Get predictions
curl http://localhost:8000/p46b6b076c/predictions
```

KATO will predict the rest of the sequence!

## Understanding KATO's Behavior

### Key Concepts

1. **Alphanumeric Sorting**: Strings within events are automatically sorted
   - Input: `["zebra", "apple"]` → Stored: `["apple", "zebra"]`

2. **Sequence Learning**: KATO learns patterns from observations
   - Builds models from working memory
   - Each model gets a unique hash identifier

3. **Temporal Predictions**: KATO segments predictions into:
   - `past`: What came before
   - `present`: Current matching events
   - `future`: What's expected next
   - `missing`: Expected but not observed
   - `extras`: Observed but not expected

## Common Operations

### Start with Custom Parameters

```bash
# Start with specific configuration
./kato-manager.sh start \
  --name "MyProcessor" \
  --max-predictions 200 \
  --recall-threshold 0.1
```

### View Logs

```bash
# Follow KATO logs
./kato-manager.sh logs kato

# Check all logs
./kato-manager.sh logs all
```

### Stop KATO

```bash
# Stop and remove all instances (asks about MongoDB)
./kato-manager.sh stop

# Stop specific instance by name or ID
./kato-manager.sh stop "My KATO"           # By name
./kato-manager.sh stop my-processor        # By ID

# Stop all instances and MongoDB
./kato-manager.sh stop --all --with-mongo

# Stop all instances but keep MongoDB
./kato-manager.sh stop --all --no-mongo
```

### Clean Up Everything

```bash
# Remove all containers, images, and volumes
./kato-manager.sh clean
```

## Python Client Example

```python
import requests
import json

class KATOClient:
    def __init__(self, base_url="http://localhost:8000", processor_id="p46b6b076c"):
        self.base_url = base_url
        self.processor_id = processor_id
    
    def observe(self, strings, vectors=None, emotives=None):
        """Send an observation to KATO"""
        url = f"{self.base_url}/{self.processor_id}/observe"
        data = {
            "strings": strings,
            "vectors": vectors or [],
            "emotives": emotives or {}
        }
        response = requests.post(url, json=data)
        return response.json()
    
    def learn(self):
        """Trigger learning from working memory"""
        url = f"{self.base_url}/{self.processor_id}/learn"
        response = requests.post(url)
        return response.json()
    
    def get_predictions(self):
        """Get current predictions"""
        url = f"{self.base_url}/{self.processor_id}/predictions"
        response = requests.get(url)
        return response.json()
    
    def clear_working_memory(self):
        """Clear working memory"""
        url = f"{self.base_url}/{self.processor_id}/working-memory/clear"
        response = requests.post(url)
        return response.json()

# Example usage
kato = KATOClient()

# Learn a pattern
kato.observe(["morning"])
kato.observe(["coffee"])
kato.observe(["work"])
model = kato.learn()
print(f"Learned model: {model}")

# Test recall
kato.clear_working_memory()
kato.observe(["morning"])
predictions = kato.get_predictions()
print(f"KATO predicts: {predictions}")
```

## Running Tests

KATO includes a comprehensive test suite:

```bash
# Run all tests
cd tests
./run_tests.sh

# Run specific test categories
./run_tests.sh --unit          # Unit tests only
./run_tests.sh --integration   # Integration tests
./run_tests.sh --api           # API tests
```

## Troubleshooting

### Port Already in Use
```bash
# Use a different port
./kato-manager.sh start --port 9000
```

### Docker Not Running
```bash
# Start Docker Desktop, then retry
./kato-manager.sh start
```

### Container Won't Start
```bash
# Check logs and rebuild
./kato-manager.sh logs kato
./kato-manager.sh clean
./kato-manager.sh build
./kato-manager.sh start
```

## Next Steps

- Read [Core Concepts](CONCEPTS.md) to understand KATO's behavior
- Learn [Multi-Instance Management](MULTI_INSTANCE_GUIDE.md) to run multiple processors
- Explore the [API Reference](API_REFERENCE.md) for all endpoints
- Check [System Overview](SYSTEM_OVERVIEW.md) for architecture details
- See [Configuration Guide](deployment/CONFIGURATION.md) for all parameters

## Getting Help

- Check the [Troubleshooting Guide](technical/TROUBLESHOOTING.md)
- Review [test examples](development/TESTING.md) for usage patterns
- Open an issue on GitHub for bugs or questions