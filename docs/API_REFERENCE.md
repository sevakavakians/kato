# KATO API Reference

Complete reference for all KATO REST API endpoints.

## Base URL

```
http://localhost:8000
```

## Multi-Instance Support

When running multiple KATO instances, each has its own base URL:
- Instance 1: `http://localhost:8001`
- Instance 2: `http://localhost:8002`
- etc.

Each instance requires its processor ID in the API path:
```
http://localhost:{port}/{processor_id}/{endpoint}
```

## Authentication

Currently, KATO API does not require authentication. Future versions may support API key authentication via the `--api-key` parameter.

## Response Format

All responses are JSON with the following structure:

```json
{
  "status": "okay" | "error",
  "message": "response message",
  // Additional endpoint-specific data
}
```

## Endpoints

### System Health

#### GET /kato-api/ping
Check if the KATO API is running.

**Response:**
```json
{
  "status": "healthy",
  "message": "KATO API is running"
}
```

### Connection Management

#### POST /connect
Establish connection with KATO system.

**Request Body:**
```json
{
  "processor_id": "p46b6b076c"
}
```

**Response:**
```json
{
  "status": "okay",
  "message": "connected",
  "processor_id": "p46b6b076c"
}
```

### Processor Operations

#### GET /{processor_id}/ping
Check if a specific processor is responsive.

**Parameters:**
- `processor_id` (path): Processor identifier

**Response:**
```json
{
  "status": "okay",
  "message": "pong",
  "processor_id": "p46b6b076c"
}
```

#### GET /{processor_id}/status
Get detailed processor status.

**Parameters:**
- `processor_id` (path): Processor identifier

**Response:**
```json
{
  "status": "okay",
  "id": "p46b6b076c",  // The processor's unique identifier
  "processor": "P1",
  "time_stamp": 1234567890.123,
  "interval": 0,
  "message": {...}  // Full processor information
}
```

### Observation and Learning

#### POST /{processor_id}/observe
Send an observation to the processor.

**Parameters:**
- `processor_id` (path): Processor identifier

**Request Body:**
```json
{
  "strings": ["hello", "world"],
  "vectors": [[1.0, 2.0, 3.0]],
  "emotives": {
    "joy": 0.8,
    "confidence": 0.6
  }
}
```

**Response:**
```json
{
  "status": "observed",
  "processor_id": "p46b6b076c",
  "short_term_memory": [["hello", "world"]]
}
```

**Notes:**
- Strings are automatically sorted alphanumerically within each event
- Empty observations are ignored
- Vectors are optional; when provided, they generate vector name strings for STM
- Emotives are optional key-value pairs (0.0-1.0)

#### POST /{processor_id}/learn
Trigger learning from current short-term memory.

**Parameters:**
- `processor_id` (path): Processor identifier

**Response:**
```json
{
  "status": "learned",
  "processor_id": "p46b6b076c",
  "pattern_name": "PTRN|a5b9c3d7e1f2..."
}
```

**Behavior:**
- Creates pattern from current STM content
- Pattern identified by SHA1 hash: `PTRN|<sha1_hash>`
- Frequency tracking:
  - New patterns start with frequency = 1
  - Re-learning identical pattern increments frequency
  - No patterns exist with frequency = 0
- STM clearing:
  - Regular learn(): STM completely cleared
  - Auto-learn (max_pattern_length reached): Last event preserved
- Returns empty string if STM has < 2 strings (no pattern created)

### Short-Term Memory

#### GET /{processor_id}/short-term-memory
Get current short-term memory contents.

**Parameters:**
- `processor_id` (path): Processor identifier

**Response:**
```json
{
  "message": [
    ["first", "event"],
    ["second"],
    ["third", "event", "here"]
  ],
  "time_stamp": 1234567890.123,
  "interval": 0
}
```

#### POST /{processor_id}/short-term-memory/clear
Clear short-term memory (preserves learned patterns).

**Parameters:**
- `processor_id` (path): Processor identifier

**Response:**
```json
{
  "status": "okay",
  "processor_id": "p46b6b076c",
  "message": "short-term memory cleared"
}
```

### Memory Management

#### POST /{processor_id}/memory/clear-all
Clear all memory (short-term memory and learned patterns).

**Parameters:**
- `processor_id` (path): Processor identifier

**Response:**
```json
{
  "status": "okay",
  "processor_id": "p46b6b076c",
  "message": "all memory cleared"
}
```

### Predictions

#### GET /{processor_id}/predictions
Get current predictions based on short-term memory.

**Important**: KATO requires at least 2 strings total in short-term memory to generate predictions. Vectors contribute their own string representations (e.g., 'VECTOR|<hash>'), so a single user string with vectors meets this requirement. With fewer than 2 strings total, this endpoint will return an empty predictions array.

**Parameters:**
- `processor_id` (path): Processor identifier

**Query Parameters:**
- `unique_id` (optional): Filter predictions by unique identifier

**Response:**
```json
{
  "status": "okay",
  "processor_id": "p46b6b076c",
  "predictions": [
    {
      "name": "PTRN|abc123...",
      "past": [["previous", "events"]],
      "present": [["current", "matching"]],
      "future": [["expected", "next"]],
      "missing": ["symbol1"],
      "extras": ["unexpected"],
      "confidence": 0.85,
      "similarity": 0.92,
      "frequency": 3,
      "matches": ["current"],
      "emotives": {"joy": 0.7},
      "hamiltonian": -2.5,
      "grand_hamiltonian": -3.2,
      "entropy": 0.15
    }
  ]
}
```

**Prediction Fields:**
- `past`: Events before current match position
- `present`: Current matching events (may be partial)
- `future`: Events expected after current position
- `missing`: Expected symbols not observed in present
- `extras`: Observed symbols not expected in present
- `confidence`: Prediction confidence (0-1)
- `similarity`: Match quality measure
- `frequency`: Times this pattern was learned
- `emotives`: Emotional context if learned with pattern

### Data Retrieval

#### GET /{processor_id}/percept-data
Get perceptual data from the processor.

**Parameters:**
- `processor_id` (path): Processor identifier

**Response:**
```json
{
  "status": "okay",
  "processor_id": "p46b6b076c",
  "percept_data": {
    "observations": [...],
    "timestamp": "2024-01-01T12:00:00Z"
  }
}
```

#### GET /{processor_id}/cognition-data
Get cognitive processing data.

**Parameters:**
- `processor_id` (path): Processor identifier

**Note**: The predictions field will be empty unless short-term memory contains at least 2 strings total (including vector-contributed strings like 'VECTOR|<hash>').

**Response:**
```json
{
  "status": "okay",
  "processor_id": "p46b6b076c",
  "short_term_memory": [...],
  "predictions": [...],
  "emotives": {...},
  "symbols": [...],
  "command": null
}
```

### Gene/Parameter Management

#### GET /{processor_id}/gene/{gene_name}
Get a specific gene/parameter value.

**Parameters:**
- `processor_id` (path): Processor identifier
- `gene_name` (path): Gene/parameter name

**Available Genes:**
- `indexer_type`: Vector indexer type (VI only)
- `max_predictions`: Maximum predictions to generate
- `recall_threshold`: Minimum similarity score required for predictions (0.0-1.0)
  - **Purpose**: Controls the quality gate for pattern matching predictions
  - **Default**: 0.1 (permissive, allows weak matches)
  - **Impact**:
    - `0.0-0.3`: Very permissive, generates many predictions including partial matches
    - `0.3-0.5`: Balanced filtering, moderate quality threshold
    - `0.5-0.7`: Restrictive, only strong pattern matches
    - `0.7-1.0`: Very restrictive, requires near-perfect similarity
  - **How it works**: Filters predictions by comparing pattern similarity ratios against this threshold
- `persistence`: Emotive persistence duration
- `max_pattern_length`: Maximum pattern length
- `quiescence`: Quiescence period

**Response:**
```json
{
  "gene_name": "max_predictions",
  "gene_value": 100,
  "message": 100  // The gene value for backward compatibility
}
```

#### POST /{processor_id}/gene/{gene_name}/change
Update a gene/parameter value.

**Parameters:**
- `processor_id` (path): Processor identifier
- `gene_name` (path): Gene/parameter name

**Request Body:**
```json
{
  "value": 150
}
```

**Response:**
```json
{
  "id": "p46b6b076c",  // The processor's unique identifier
  "status": "okay",
  "message": "updated-genes"
}
```

#### POST /{processor_id}/genes/change
Update multiple genes at once (primary gene update endpoint).

**Parameters:**
- `processor_id` (path): Processor identifier

**Request Body:**
```json
{
  "data": {
    "max_predictions": 200,
    "recall_threshold": 0.15, 
    "persistence": 10,
    "max_pattern_length": 3
  }
}
```

**Response:**
```json
{
  "id": "p46b6b076c",  // The processor's unique identifier
  "status": "okay",
  "message": "updated-genes"
}
```

#### POST /{processor_id}/genes/update
Update multiple genes at once (alternative endpoint).

**Parameters:**
- `processor_id` (path): Processor identifier

**Request Body:**
```json
{
  "genes": {
    "max_predictions": 200,
    "recall_threshold": 0.15,
    "persistence": 10
  }
}
```

**Response:**
```json
{
  "status": "okay",
  "processor_id": "p46b6b076c",
  "updated_genes": ["max_predictions", "recall_threshold", "persistence"]
}
```

#### POST /{processor_id}/recall-threshold/increment
Increment the recall threshold.

**Parameters:**
- `processor_id` (path): Processor identifier

**Request Body:**
```json
{
  "increment": 0.05
}
```

**Response:**
```json
{
  "status": "okay",
  "processor_id": "p46b6b076c",
  "old_value": 0.1,
  "new_value": 0.15
}
```

## Error Responses

### 404 Not Found
```json
{
  "status": "error",
  "message": "Processor p123 not found",
  "error_code": "PROCESSOR_NOT_FOUND"
}
```

### 400 Bad Request
```json
{
  "status": "error",
  "message": "Invalid observation format",
  "error_code": "INVALID_FORMAT"
}
```

### 500 Internal Server Error
```json
{
  "status": "error",
  "message": "Internal processing error",
  "error_code": "INTERNAL_ERROR"
}
```

## Rate Limiting

Currently no rate limiting is implemented. The system can handle:
- 10,000+ requests/second per processor
- Sustained high-volume operations
- Concurrent requests from multiple clients

## WebSocket Support

WebSocket support for real-time predictions is planned for future versions.

## Examples

### Complete Session Example

```python
import requests
import json

BASE_URL = "http://localhost:8000"
PROCESSOR_ID = "p46b6b076c"

# 1. Check health
response = requests.get(f"{BASE_URL}/kato-api/ping")
print("Health:", response.json())

# 2. Connect
response = requests.post(f"{BASE_URL}/connect", 
                        json={"processor_id": PROCESSOR_ID})
print("Connected:", response.json())

# 3. Send observations
observations = [
    ["morning", "routine"],
    ["coffee", "breakfast"],
    ["work", "email"]
]

for obs in observations:
    response = requests.post(
        f"{BASE_URL}/{PROCESSOR_ID}/observe",
        json={"strings": obs, "vectors": [], "emotives": {}}
    )
    print(f"Observed {obs}:", response.status_code)

# 4. Learn the pattern
response = requests.post(f"{BASE_URL}/{PROCESSOR_ID}/learn")
pattern = response.json()
print("Learned pattern:", pattern)

# 5. Clear and test recall
requests.post(f"{BASE_URL}/{PROCESSOR_ID}/short-term-memory/clear")

response = requests.post(
    f"{BASE_URL}/{PROCESSOR_ID}/observe",
    json={"strings": ["morning"], "vectors": [], "emotives": {}}
)

# 6. Get predictions
response = requests.get(f"{BASE_URL}/{PROCESSOR_ID}/predictions")
predictions = response.json()
print("Predictions:", json.dumps(predictions, indent=2))
```

### cURL Examples

```bash
# Observe with emotives
curl -X POST http://localhost:8000/p46b6b076c/observe \
  -H "Content-Type: application/json" \
  -d '{
    "strings": ["happy", "day"],
    "vectors": [],
    "emotives": {"joy": 0.9, "energy": 0.7}
  }'

# Get cognition data
curl http://localhost:8000/p46b6b076c/cognition-data

# Update multiple genes (primary endpoint)
curl -X POST http://localhost:8000/p46b6b076c/genes/change \
  -H "Content-Type: application/json" \
  -d '{
    "data": {
      "max_predictions": 50,
      "recall_threshold": 0.2,
      "max_pattern_length": 3
    }
  }'

# Set recall_threshold for different use cases
# High precision (few, high-quality predictions)
curl -X POST http://localhost:8000/p46b6b076c/gene/recall_threshold/change \
  -H "Content-Type: application/json" \
  -d '{"value": 0.7}'

# Balanced (moderate filtering)
curl -X POST http://localhost:8000/p46b6b076c/gene/recall_threshold/change \
  -H "Content-Type: application/json" \
  -d '{"value": 0.4}'

# Pattern discovery (many predictions, including weak matches)
curl -X POST http://localhost:8000/p46b6b076c/gene/recall_threshold/change \
  -H "Content-Type: application/json" \
  -d '{"value": 0.1}'

# Update multiple genes (alternative endpoint)
curl -X POST http://localhost:8000/p46b6b076c/genes/update \
  -H "Content-Type: application/json" \
  -d '{
    "genes": {
      "max_predictions": 50,
      "recall_threshold": 0.2
    }
  }'
```

## Version History

- **v2.0.0**: Migration to ZeroMQ, improved performance
- **v1.0.0**: Initial REST API implementation

## Management Commands

While not part of the REST API, KATO provides CLI management commands:

### Instance Management
```bash
# Start instances
./kato-manager.sh start --id processor-1 --name "Main" --port 8001
./kato-manager.sh start --id processor-2 --name "Secondary" --port 8002

# List all instances
./kato-manager.sh list

# Stop instances (automatically removes containers)
./kato-manager.sh stop processor-1         # By ID
./kato-manager.sh stop "Main"              # By name
./kato-manager.sh stop --all               # All instances
./kato-manager.sh stop --all --with-mongo  # Including MongoDB
```

### Container Lifecycle
- **Automatic Cleanup**: The `stop` command removes containers to prevent accumulation
- **Registry Sync**: Instance registry (`~/.kato/instances.json`) stays synchronized
- **MongoDB Persistence**: MongoDB container is preserved unless explicitly removed

## Support

For issues or questions:
- Check the [Troubleshooting Guide](technical/TROUBLESHOOTING.md)
- Review the [System Overview](SYSTEM_OVERVIEW.md)
- See [Multi-Instance Guide](MULTI_INSTANCE_GUIDE.md) for advanced usage
- Open an issue on GitHub