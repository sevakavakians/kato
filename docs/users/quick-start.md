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
# Start all services (ClickHouse, Qdrant, Redis, KATO)
./start.sh
```

### 3. Verify Installation

```bash
# Check system status
docker compose ps

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
- Your **learned patterns** are permanent - stored in the database forever
- Your `node_id` ("my_first_kato") is your persistent identifier linking to your trained patterns

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

For complete details, see [Database Persistence Guide](database-persistence.md).

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

### View Logs

```bash
# Follow KATO logs
docker compose logs -f kato

# Check all service logs
docker compose logs
```

### Stop KATO

```bash
# Stop all services
docker compose down

# Stop and remove volumes (WARNING: deletes all data)
docker compose down -v
```

## Python Client Example

```python
import requests

class KATOClient:
    def __init__(self, base_url="http://localhost:8000"):
        self.base_url = base_url
        self.session_id = None

    def create_session(self, node_id, config=None):
        """Create a new session"""
        response = requests.post(
            f"{self.base_url}/sessions",
            json={"node_id": node_id, "config": config or {}}
        )
        self.session_id = response.json()['session_id']
        return self.session_id

    def observe(self, strings, vectors=None, emotives=None):
        """Send an observation to KATO"""
        response = requests.post(
            f"{self.base_url}/sessions/{self.session_id}/observe",
            json={
                "strings": strings,
                "vectors": vectors or [],
                "emotives": emotives or {}
            }
        )
        return response.json()

    def learn(self):
        """Trigger learning from short-term memory"""
        response = requests.post(
            f"{self.base_url}/sessions/{self.session_id}/learn"
        )
        return response.json()

    def get_predictions(self):
        """Get current predictions"""
        response = requests.get(
            f"{self.base_url}/sessions/{self.session_id}/predictions"
        )
        return response.json()

    def clear_stm(self):
        """Clear short-term memory"""
        response = requests.post(
            f"{self.base_url}/sessions/{self.session_id}/clear-stm"
        )
        return response.json()

# Example usage
kato = KATOClient()

# Create session
kato.create_session("my_first_kato")

# Learn a pattern
kato.observe(["morning"])
kato.observe(["coffee"])
kato.observe(["work"])
pattern = kato.learn()
print(f"Learned pattern: {pattern}")

# Test recall
kato.clear_stm()
kato.observe(["morning"])
predictions = kato.get_predictions()
print(f"KATO predicts: {predictions}")
```

## Running Tests

```bash
# Ensure services are running
./start.sh

# Run all tests (recommended)
./run_tests.sh --no-start --no-stop

# Run specific test suites
python -m pytest tests/tests/unit/ -v
python -m pytest tests/tests/integration/ -v
python -m pytest tests/tests/api/ -v
```

For detailed testing information, see the [Testing Guide](../developers/testing.md).

## Troubleshooting

### Docker Not Running
Start Docker Desktop, then run `./start.sh`

### Container Won't Start
```bash
# Check logs
docker compose logs kato

# Rebuild if needed
docker compose build --no-cache kato
./start.sh
```

## Next Steps

- **Important**: Read [Database Persistence Guide](database-persistence.md) to understand data persistence
- Read [Core Concepts](CONCEPTS.md) to understand KATO's behavior
- Explore the [API Reference](api-reference.md) for all endpoints
- See [Configuration Guide](deployment/CONFIGURATION.md) for parameters

## Getting Help

- Check the [Troubleshooting Guide](technical/TROUBLESHOOTING.md)
- Open an issue on GitHub for bugs or questions