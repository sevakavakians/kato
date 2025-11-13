# Observation Object Specification

Complete specification for KATO observation input format.

## Overview

Observations are multi-modal inputs to KATO containing strings, vectors, emotives, and metadata.

## Observation Structure

```json
{
  "strings": ["symbol1", "symbol2", "symbol3"],
  "vectors": [
    [0.1, 0.2, ..., 0.768],
    [0.3, 0.4, ..., 0.768]
  ],
  "emotives": {
    "happiness": 0.8,
    "urgency": -0.3,
    "confidence": 0.95
  },
  "metadata": {
    "source": "user_input",
    "timestamp": "2025-11-13T12:00:00Z",
    "page": "dashboard"
  },
  "unique_id": "obs_12345"
}
```

## Fields

### strings (array[string])

**Required**: No (but at least one of strings/vectors should be present)

**Description**: String symbols to observe.

**Example**:

```json
{
  "strings": ["login", "user_alice", "successful"]
}
```

**Behavior**:
- Sorted alphanumerically if `sort_symbols=true`
- Used directly in pattern matching
- No length limit (practical consideration: pattern complexity)

### vectors (array[array[float]])

**Required**: No

**Description**: 768-dimensional vector embeddings.

**Structure**:

```json
{
  "vectors": [
    [0.1, 0.2, ..., 0.768],  // Vector 1
    [0.3, 0.4, ..., 0.768]   // Vector 2
  ]
}
```

**Requirements**:
- Each vector MUST be exactly 768 dimensions
- Values: floating-point numbers
- No limit on number of vectors

**Processing**:
1. Hash computed from vector values
2. Symbolic name created: `VCTR|<hash>`
3. Vector stored in Qdrant
4. Symbol used in pattern matching

**Example**:

```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer('all-mpnet-base-v2')
embedding = model.encode("hello world")

observation = {
    "vectors": [embedding.tolist()]  # Convert to list
}
```

**Error**: Vector dimension mismatch (400)

```json
{
  "detail": {
    "error": "VectorDimensionError",
    "expected_dimension": 768,
    "actual_dimension": 512
  }
}
```

### emotives (object)

**Required**: No

**Description**: Emotional or utility values.

**Structure**:

```json
{
  "emotive_name": float_value,
  "another_emotive": float_value
}
```

**Rules**:
- Keys: String emotive names
- Values: Numeric (positive, negative, integer, or float)
- No range restrictions (can be < -1 or > 1)
- Accumulated across observations
- Stored in pattern's rolling window

**Examples**:

```json
// Simple emotives
{
  "happiness": 0.8,
  "sadness": -0.3
}

// Utility values
{
  "importance": 100,
  "urgency": -50,
  "confidence": 0.95
}

// Custom metrics
{
  "user_satisfaction": 4.5,
  "conversion_probability": 0.67
}
```

### metadata (object)

**Required**: No

**Description**: Contextual tags.

**Structure**:

```json
{
  "key": "value",
  "another_key": "another_value"
}
```

**Rules**:
- Keys: String metadata names
- Values: Any JSON-serializable value (converted to string)
- Stored as unique string lists in patterns
- Set-union accumulation

**Examples**:

```json
// Simple metadata
{
  "source": "web_app",
  "user_id": "alice",
  "page": "dashboard"
}

// Structured metadata
{
  "timestamp": "2025-11-13T12:00:00Z",
  "session_id": "session_123",
  "user_agent": "Mozilla/5.0...",
  "location": {
    "country": "US",
    "state": "CA"
  }
}
```

### unique_id (string)

**Required**: No (auto-generated if not provided)

**Description**: Tracking identifier for this observation.

**Usage**:
- Returned in observation response
- Useful for correlating observations with external systems
- Auto-generated format: `obs-<uuid>`

**Example**:

```json
{
  "strings": ["event"],
  "unique_id": "user_action_12345"
}
```

## Processing Flow

### 1. Input

```json
{
  "strings": ["hello"],
  "vectors": [[0.1, ..., 0.768]],
  "emotives": {"happiness": 0.8},
  "metadata": {"source": "chat"}
}
```

### 2. Vector Processing

```python
# Vector converted to symbol
vector → hash → "VCTR|abc123..."
# Stored in Qdrant
```

### 3. Symbol Formation

```python
# Final symbols
symbols = ["hello", "VCTR|abc123..."]

# Sorted if sort_symbols=true
symbols = ["VCTR|abc123...", "hello"]
```

### 4. STM Update

```python
# Added to STM as event
STM.append(["VCTR|abc123...", "hello"])
```

### 5. Emotive/Metadata Accumulation

```python
# Emotives accumulated
emotives_accumulator["happiness"].append(0.8)

# Metadata accumulated
metadata_accumulator["source"].add("chat")
```

## Validation Rules

### Minimum Requirements

At least one of the following must be present:
- Non-empty `strings` array
- Non-empty `vectors` array

**Valid**:

```json
{"strings": ["hello"]}
{"vectors": [[...]]}
{"strings": ["hello"], "vectors": [[...]]}
```

**Invalid**:

```json
{}  // No data
{"strings": []}  // Empty
{"emotives": {"x": 1}}  // Only emotives
```

### Vector Dimensions

All vectors must be exactly 768 dimensions:

**Valid**:

```python
vector = model.encode("text")  # Returns 768-dim
assert len(vector) == 768
```

**Invalid**:

```python
vector = [0.1, 0.2]  # Only 2 dimensions
# → VectorDimensionError
```

## Use Cases

### Simple String Observation

```json
{
  "strings": ["login", "successful"]
}
```

### Vector Embedding

```json
{
  "vectors": [[0.1, 0.2, ..., 0.768]]
}
```

### Mixed Observation

```json
{
  "strings": ["document_title"],
  "vectors": [[...]],  // Document embedding
  "emotives": {"relevance": 0.9},
  "metadata": {
    "doc_id": "123",
    "category": "technical"
  }
}
```

### Tracked Observation

```json
{
  "strings": ["user_action"],
  "unique_id": "action_12345",
  "metadata": {"timestamp": "2025-11-13T12:00:00Z"}
}
```

## See Also

- [Observations API](api/observations.md) - Send observations
- [Pattern Object](pattern-object.md) - How observations become patterns
- [Vector Embeddings](../research/vector-embeddings.md) - Vector processing details

---

**Last Updated**: November 2025
**KATO Version**: 3.0+
