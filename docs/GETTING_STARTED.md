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

### 2. Start KATO

```bash
# Start all services (MongoDB, Qdrant, Redis, KATO)
./start.sh
```

### 3. Verify Installation

```bash
# Check system status
docker-compose ps

# Test the API
curl http://localhost:8000/health
```

You should see:
```json
{"status": "healthy", "message": "KATO API is running"}
```

## Your First KATO Session

### 1. Create a Session

First, create a session with a `node_id` to identify your workspace:

```bash
# Create session
SESSION=$(curl -s -X POST http://localhost:8000/sessions \
  -H "Content-Type: application/json" \
  -d '{"node_id": "my_first_kato"}' | jq -r '.session_id')

echo "Session ID: $SESSION"
```

**Important**: The `node_id` ("my_first_kato") is your **persistent identifier**. Using the same `node_id` later will reconnect to all trained patterns!

### 2. Send an Observation

```bash
curl -X POST http://localhost:8000/sessions/$SESSION/observe \
  -H "Content-Type: application/json" \
  -d '{
    "strings": ["hello", "world"],
    "vectors": [],
    "emotives": {"joy": 0.8}
  }'
```

### 3. Check Short-Term Memory

```bash
curl http://localhost:8000/sessions/$SESSION/stm
```

Response shows the sorted observation:
```json
{
  "stm": [["hello", "world"]],
  "session_id": "session-abc123..."
}
```

### 4. Learn a Pattern

```bash
# Add more observations
curl -X POST http://localhost:8000/sessions/$SESSION/observe \
  -H "Content-Type: application/json" \
  -d '{"strings": ["how"], "vectors": [], "emotives": {}}'

curl -X POST http://localhost:8000/sessions/$SESSION/observe \
  -H "Content-Type: application/json" \
  -d '{"strings": ["are", "you"], "vectors": [], "emotives": {}}'

# Trigger learning
curl -X POST http://localhost:8000/sessions/$SESSION/learn
```

### 5. Get Predictions

```bash
# Clear short-term memory (patterns remain in long-term memory)
curl -X POST http://localhost:8000/sessions/$SESSION/clear-stm

# Observe the start of the learned pattern
curl -X POST http://localhost:8000/sessions/$SESSION/observe \
  -H "Content-Type: application/json" \
  -d '{"strings": ["hello"], "vectors": [], "emotives": {}}'

# Get predictions
curl http://localhost:8000/sessions/$SESSION/predictions
```

KATO will predict the rest of the pattern!

### 6. Understanding Data Persistence

**What just happened?**
- Your **session** (STM, emotives) is temporary - expires after 1 hour by default
- Your **learned patterns** are permanent - stored in MongoDB forever
- Your `node_id` ("my_first_kato") links to a specific MongoDB database

**Reconnecting Later:**

```bash
# Day 1: You trained patterns (above)
# Session expires...

# Day 7: Reconnect to same training
NEW_SESSION=$(curl -s -X POST http://localhost:8000/sessions \
  -H "Content-Type: application/json" \
  -d '{"node_id": "my_first_kato"}' | jq -r '.session_id')

# Different session ID, but SAME trained patterns!
curl -X POST http://localhost:8000/sessions/$NEW_SESSION/observe \
  -H "Content-Type: application/json" \
  -d '{"strings": ["hello"], "vectors": [], "emotives": {}}'

curl http://localhost:8000/sessions/$NEW_SESSION/predictions
# Returns predictions from Day 1 training!
```

**Key Takeaway:** Same `node_id` = Same trained database (always)

For complete details, see [Database Persistence Guide](DATABASE_PERSISTENCE.md).

## Understanding KATO's Behavior

### Key Concepts

1. **Alphanumeric Sorting**: Strings within events are automatically sorted
   - Input: `["zebra", "apple"]` → Stored: `["apple", "zebra"]`

2. **Pattern Learning**: KATO learns patterns from observations
   - Builds patterns from short-term memory
   - Each pattern gets a unique hash identifier

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
./start.sh \
  --name "MyProcessor" \
  --max-predictions 200 \
  --recall-threshold 0.1
```

### View Logs

```bash
# Follow KATO logs
docker-compose logs kato

# Check all logs
docker-compose logs all
```

### Stop KATO

```bash
# Stop and remove all instances (asks about MongoDB)
docker-compose down

# Stop specific instance by name or ID
docker-compose down "My KATO"           # By name
docker-compose down my-processor        # By ID

# Stop all instances and MongoDB
docker-compose down --all --with-mongo

# Stop all instances but keep MongoDB
docker-compose down --all --no-mongo
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
    def __init__(self, base_url="http://localhost:8000", session_id="p46b6b076c"):
        self.base_url = base_url
        self.session_id = session_id
    
    def observe(self, strings, vectors=None, emotives=None):
        """Send an observation to KATO"""
        url = f"{self.base_url}/{self.session_id}/observe"
        data = {
            "strings": strings,
            "vectors": vectors or [],
            "emotives": emotives or {}
        }
        response = requests.post(url, json=data)
        return response.json()
    
    def learn(self):
        """Trigger learning from short-term memory"""
        url = f"{self.base_url}/{self.session_id}/learn"
        response = requests.post(url)
        return response.json()
    
    def get_predictions(self):
        """Get current predictions"""
        url = f"{self.base_url}/{self.session_id}/predictions"
        response = requests.get(url)
        return response.json()
    
    def clear_short_term_memory(self):
        """Clear short-term memory"""
        url = f"{self.base_url}/{self.session_id}/short-term-memory/clear"
        response = requests.post(url)
        return response.json()

# Example usage
kato = KATOClient()

# Learn a pattern
kato.observe(["morning"])
kato.observe(["coffee"])
kato.observe(["work"])
pattern = kato.learn()
print(f"Learned pattern: {pattern}")

# Test recall
kato.clear_short_term_memory()
kato.observe(["morning"])
predictions = kato.get_predictions()
print(f"KATO predicts: {predictions}")
```

## Running Tests

KATO uses a simple local Python testing approach with pytest:

```bash
# Set up virtual environment (first time only)
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -r tests/requirements.txt

# Run all tests
./tests/run_tests.sh

# Run specific test suites
./tests/run_tests.sh tests/tests/unit/          # Unit tests only
./tests/run_tests.sh tests/tests/integration/   # Integration tests
./tests/run_tests.sh tests/tests/api/          # API tests
./tests/run_tests.sh tests/tests/performance/  # Performance tests

# Run with pytest directly
python -m pytest tests/tests/ -v       # Verbose output
python -m pytest tests/tests/ -s       # Show print statements
python -m pytest tests/tests/ --pdb    # Drop into debugger on failure

# Run tests without starting/stopping KATO
./tests/run_tests.sh --no-start --no-stop tests/
```

**Key Features:**
- Each test gets a unique processor ID for database isolation
- Simple debugging with standard Python tools
- Fast iteration without container rebuilds
- Full IDE and debugger support

For detailed testing information, see the [Testing Guide](development/TESTING.md).

## Troubleshooting

### Port Already in Use
```bash
# Use a different port
./start.sh --port 9000
```

### Docker Not Running
```bash
# Start Docker Desktop, then retry
./start.sh
```

### Container Won't Start
```bash
# Check logs and rebuild
docker-compose logs kato
./kato-manager.sh clean
docker-compose build
./start.sh
```

## Next Steps

- **Important**: Read [Database Persistence Guide](DATABASE_PERSISTENCE.md) to understand how data persists
- Read [Core Concepts](CONCEPTS.md) to understand KATO's behavior
- Learn [Multi-Instance Management](MULTI_INSTANCE_GUIDE.md) to run multiple processors
- Explore the [API Reference](API_REFERENCE.md) for all endpoints
- Check [System Overview](SYSTEM_OVERVIEW.md) for architecture details
- See [Configuration Guide](deployment/CONFIGURATION.md) for all parameters

## Getting Help

- Check the [Troubleshooting Guide](technical/TROUBLESHOOTING.md)
- Review [test examples](development/TESTING.md) for usage patterns
- Open an issue on GitHub for bugs or questions