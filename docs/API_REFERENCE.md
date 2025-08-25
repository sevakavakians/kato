# KATO API Reference

Complete reference for all KATO REST API endpoints.

## Base URL

```
http://localhost:8000
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
  "processor_id": "p46b6b076c",
  "name": "P1",
  "working_memory_size": 3,
  "model_count": 5,
  "predictions_available": true
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
  "working_memory": [["hello", "world"]]
}
```

**Notes:**
- Strings are automatically sorted alphanumerically within each event
- Empty observations are ignored
- Vectors are optional and processed through classifiers
- Emotives are optional key-value pairs (0.0-1.0)

#### POST /{processor_id}/learn
Trigger learning from current working memory.

**Parameters:**
- `processor_id` (path): Processor identifier

**Response:**
```json
{
  "status": "learned",
  "processor_id": "p46b6b076c",
  "model_name": "MODEL|a5b9c3d7e1f2..."
}
```

### Working Memory

#### GET /{processor_id}/working-memory
Get current working memory contents.

**Parameters:**
- `processor_id` (path): Processor identifier

**Response:**
```json
{
  "status": "okay",
  "processor_id": "p46b6b076c",
  "working_memory": [
    ["first", "event"],
    ["second"],
    ["third", "event", "here"]
  ]
}
```

#### POST /{processor_id}/working-memory/clear
Clear working memory (preserves learned models).

**Parameters:**
- `processor_id` (path): Processor identifier

**Response:**
```json
{
  "status": "okay",
  "processor_id": "p46b6b076c",
  "message": "working memory cleared"
}
```

### Memory Management

#### POST /{processor_id}/memory/clear-all
Clear all memory (working memory and learned models).

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
Get current predictions based on working memory.

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
      "name": "MODEL|abc123...",
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
- `emotives`: Emotional context if learned with model

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

**Response:**
```json
{
  "status": "okay",
  "processor_id": "p46b6b076c",
  "working_memory": [...],
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
- `classifier`: Classifier type (CVC/DVC)
- `max_predictions`: Maximum predictions to generate
- `recall_threshold`: Recall threshold (0-1)
- `persistence`: Emotive persistence duration
- `max_sequence_length`: Maximum sequence length
- `search_depth`: Vector search depth

**Response:**
```json
{
  "status": "okay",
  "processor_id": "p46b6b076c",
  "gene": "max_predictions",
  "value": 100
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
  "status": "okay",
  "processor_id": "p46b6b076c",
  "gene": "max_predictions",
  "old_value": 100,
  "new_value": 150
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
    "max_sequence_length": 3
  }
}
```

**Response:**
```json
{
  "status": "okay",
  "message": "genes-updated",
  "processor_id": "p46b6b076c",
  "updated_genes": ["max_predictions", "recall_threshold", "persistence", "max_sequence_length"]
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

### Model Information

#### GET /{processor_id}/models
Get information about learned models.

**Parameters:**
- `processor_id` (path): Processor identifier

**Response:**
```json
{
  "status": "okay",
  "processor_id": "p46b6b076c",
  "models": [
    {
      "name": "MODEL|abc123...",
      "frequency": 3,
      "sequence_length": 5,
      "contains_emotives": true,
      "contains_vectors": false
    }
  ],
  "total_models": 10
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

# 4. Learn the sequence
response = requests.post(f"{BASE_URL}/{PROCESSOR_ID}/learn")
model = response.json()
print("Learned model:", model)

# 5. Clear and test recall
requests.post(f"{BASE_URL}/{PROCESSOR_ID}/working-memory/clear")

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
      "max_sequence_length": 3
    }
  }'

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

## Support

For issues or questions:
- Check the [Troubleshooting Guide](technical/TROUBLESHOOTING.md)
- Review the [System Overview](SYSTEM_OVERVIEW.md)
- Open an issue on GitHub