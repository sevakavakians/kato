# Utility Operations API

Endpoints for pattern retrieval and processor data access.

## Endpoints

### Get Pattern by ID

Retrieve a specific learned pattern by its identifier.

```http
GET /pattern/{pattern_id}?node_id={node_id}
```

**Parameters**:
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `pattern_id` | string (path) | Yes | Pattern ID (PTRN\|hash) |
| `node_id` | string (query) | No | Node identifier |

**Response** (`200 OK`):

```json
{
  "pattern": {
    "name": "PTRN|abc123def456...",
    "data": [
      ["login"],
      ["view_dashboard"],
      ["logout"]
    ],
    "frequency": 5,
    "emotives": {
      "confidence": [0.8, 0.9, 0.7, 0.85, 0.82]
    },
    "metadata": {
      "source": ["web", "mobile"],
      "version": ["1.0"]
    }
  },
  "node_id": "user_alice"
}
```

**Errors**:
- `404 Not Found`: Pattern not found

**Example**:

```bash
curl "http://localhost:8000/pattern/PTRN|abc123def456...?node_id=user_alice"
```

---

### Get Percept Data (Node-Level)

Get current percept data from a processor.

```http
GET /percept-data?node_id={node_id}
```

**Parameters**:
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `node_id` | string (query) | No | Node identifier |

**Response** (`200 OK`):

```json
{
  "percept_data": {
    "strings": ["hello", "world"],
    "vectors": [...],
    "emotives": {"happiness": 0.8},
    "metadata": {"source": "input"}
  },
  "node_id": "user_alice"
}
```

**Note**: For session-specific percept data, use `/sessions/{session_id}/percept-data`.

---

### Get Cognition Data (Node-Level)

Get current cognition data from a processor.

```http
GET /cognition-data?node_id={node_id}
```

**Parameters**:
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `node_id` | string (query) | No | Node identifier |

**Response** (`200 OK`):

```json
{
  "cognition_data": {
    "predictions": [...],
    "symbols": ["hello", "world"],
    "emotives": {"happiness": 0.8},
    "time": 42
  },
  "node_id": "user_alice"
}
```

**Note**: For session-specific cognition data, use `/sessions/{session_id}/cognition-data`.

---

### Get Session Percept Data

Get percept data for a specific session.

```http
GET /sessions/{session_id}/percept-data
```

**Response** (`200 OK`):

```json
{
  "percept_data": {
    "strings": ["login"],
    "vectors": [],
    "emotives": {},
    "metadata": {"page": "auth"}
  },
  "session_id": "session-abc123...",
  "node_id": "user_alice"
}
```

**Use Cases**:
- Debugging observations
- Verifying input processing
- Auditing data flow

---

### Get Session Cognition Data

Get cognition data for a specific session.

```http
GET /sessions/{session_id}/cognition-data
```

**Response** (`200 OK`):

```json
{
  "cognition_data": {
    "predictions": [
      {
        "name": "PTRN|abc123...",
        "matches": ["login"],
        "future": [["dashboard"]],
        ...
      }
    ],
    "emotives": {},
    "symbols": ["login"],
    "time": 1
  },
  "session_id": "session-abc123...",
  "node_id": "user_alice"
}
```

**Use Cases**:
- Analyzing predictions
- Understanding cognitive state
- Debugging pattern matching

---

## Data Concepts

### Percept Data

**Definition**: Raw input perception before processing

**Contains**:
- Last observation received
- Unprocessed strings, vectors, emotives
- Metadata as provided

**Example**:

```json
{
  "strings": ["user_input"],
  "vectors": [[0.1, 0.2, ..., 0.768]],
  "emotives": {"urgency": 0.5},
  "metadata": {"timestamp": "2025-11-13T12:00:00Z"}
}
```

### Cognition Data

**Definition**: Cognitive state after processing

**Contains**:
- Current predictions
- Active symbols (after vector conversion)
- Averaged emotives
- Time counter
- Processing metadata

**Example**:

```json
{
  "predictions": [...],
  "symbols": ["user_input", "VCTR|abc123..."],
  "emotives": {"urgency": 0.5},
  "time": 42
}
```

---

## Pattern Structure

### Pattern Object

```json
{
  "name": "PTRN|<sha1_hash>",
  "data": [
    ["event1_symbol1", "event1_symbol2"],
    ["event2_symbol1"],
    ["event3_symbol1", "event3_symbol2", "event3_symbol3"]
  ],
  "frequency": 5,
  "emotives": {
    "emotive_name": [value1, value2, ..., valueN]
  },
  "metadata": {
    "key": ["unique", "values", "list"]
  }
}
```

### Pattern Name

Format: `PTRN|<sha1_hash>`

**Example**: `PTRN|a1b2c3d4e5f6...`

**Hash Computation**:
```python
import hashlib

pattern_string = str(pattern_data)
hash_value = hashlib.sha1(pattern_string.encode()).hexdigest()
pattern_name = f"PTRN|{hash_value}"
```

### Pattern Data

List of events, where each event is a list of strings:

```python
[
  ["symbol1", "symbol2"],  # Event 1
  ["symbol3"],             # Event 2
  ["symbol4", "symbol5"]   # Event 3
]
```

### Pattern Frequency

Number of times the pattern was learned:

```python
frequency=1  # Learned once
frequency=5  # Learned 5 times (common pattern)
frequency=100 # Learned 100 times (very common)
```

### Pattern Emotives

Rolling window of emotive values:

```json
{
  "happiness": [0.8, 0.9, 0.7, 0.85, 0.82],
  "urgency": [-0.3, -0.2, -0.4, -0.1, -0.25]
}
```

Window size controlled by `persistence` parameter (default: 5).

### Pattern Metadata

Unique string lists (set-union accumulation):

```json
{
  "source": ["web", "mobile", "api"],
  "version": ["1.0", "1.1"],
  "category": ["user_action"]
}
```

---

## Use Cases

### 1. Pattern Analysis

```python
import requests

# Get all patterns for a node
# (Requires iterating through known pattern IDs)

pattern_id = "PTRN|abc123..."
response = requests.get(
    f"http://localhost:8000/pattern/{pattern_id}",
    params={"node_id": "user_alice"}
)

pattern = response.json()["pattern"]
print(f"Frequency: {pattern['frequency']}")
print(f"Events: {len(pattern['data'])}")
```

### 2. Debugging Observations

```python
# Check what was observed
response = requests.get(
    f"http://localhost:8000/sessions/{session_id}/percept-data"
)

percept = response.json()["percept_data"]
print(f"Observed strings: {percept['strings']}")
print(f"Emotives: {percept['emotives']}")
```

### 3. Analyzing Predictions

```python
# Check cognitive state
response = requests.get(
    f"http://localhost:8000/sessions/{session_id}/cognition-data"
)

cognition = response.json()["cognition_data"]
print(f"Predictions: {len(cognition['predictions'])}")
print(f"Active symbols: {cognition['symbols']}")
```

---

## Best Practices

### 1. Use Session-Specific Endpoints

For session-isolated data, prefer session endpoints:

```bash
# ✅ Session-specific
GET /sessions/{session_id}/percept-data

# ❌ Node-level (not session-isolated)
GET /percept-data?node_id=...
```

### 2. Pattern Retrieval Optimization

Cache frequently accessed patterns:

```python
pattern_cache = {}

def get_pattern(pattern_id, node_id):
    key = (pattern_id, node_id)
    if key not in pattern_cache:
        response = requests.get(
            f"http://localhost:8000/pattern/{pattern_id}",
            params={"node_id": node_id}
        )
        pattern_cache[key] = response.json()["pattern"]
    return pattern_cache[key]
```

### 3. Percept vs Cognition

- **Percept**: "What did I just observe?"
- **Cognition**: "What do I think about it?"

Use percept for input validation, cognition for output analysis.

---

## See Also

- [Observations API](observations.md) - Create percept data
- [Predictions API](predictions.md) - Generate cognition data
- [Pattern Object Reference](../pattern-object.md)
- [Core Concepts](../../users/concepts.md)

---

**Last Updated**: November 2025
**KATO Version**: 3.0+
