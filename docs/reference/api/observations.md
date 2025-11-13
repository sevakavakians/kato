# Observations API

Endpoints for processing observations and managing short-term memory.

## Overview

Observations are multi-modal inputs to KATO containing:
- **Strings**: Discrete symbols
- **Vectors**: 768-dimensional embeddings
- **Emotives**: Emotional/utility values
- **Metadata**: Contextual tags

## Endpoints

### Process Single Observation

Process a single observation in a session context.

```http
POST /sessions/{session_id}/observe
```

**Request Body**:

```json
{
  "strings": ["hello", "world"],
  "vectors": [[0.1, 0.2, ..., 0.768]],  // Optional: 768-dim vectors
  "emotives": {                          // Optional: emotional values
    "happiness": 0.8,
    "urgency": -0.3
  },
  "metadata": {                          // Optional: contextual tags
    "source": "user_input",
    "timestamp": "2025-11-13T12:00:00Z"
  }
}
```

**Response** (`200 OK`):

```json
{
  "status": "okay",
  "session_id": "session-abc123...",
  "processor_id": "user_alice",
  "stm_length": 3,
  "time": 42,
  "unique_id": "obs-def456...",
  "auto_learned_pattern": "PTRN|abc123..."  // If auto-learning triggered
}
```

**Fields**:

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `strings` | array[string] | No | [] | String symbols to observe |
| `vectors` | array[array[float]] | No | [] | 768-dimensional embeddings |
| `emotives` | object | No | {} | Emotional values (-∞ to +∞) |
| `metadata` | object | No | {} | Contextual tags (stored as unique lists) |

**Errors**:

- `404 Not Found`: Session not found or expired
- `400 Bad Request`: Vector dimension mismatch

**Vector Dimension Error**:

```json
{
  "detail": {
    "error": "VectorDimensionError",
    "message": "Vector dimension mismatch",
    "expected_dimension": 768,
    "actual_dimension": 512,
    "vector_name": "VCTR|abc123..."
  }
}
```

**Example**:

```bash
curl -X POST http://localhost:8000/sessions/session-abc123.../observe \
  -H "Content-Type: application/json" \
  -d '{
    "strings": ["user", "login", "successful"],
    "emotives": {"confidence": 0.95}
  }'
```

---

### Process Observation Sequence

Process multiple observations in sequence with bulk processing options.

```http
POST /sessions/{session_id}/observe-sequence
```

**Request Body**:

```json
{
  "observations": [
    {
      "strings": ["hello"],
      "unique_id": "obs_1"
    },
    {
      "strings": ["world"],
      "unique_id": "obs_2"
    },
    {
      "strings": ["goodbye"],
      "unique_id": "obs_3"
    }
  ],
  "learn_after_each": false,    // Learn after each observation
  "learn_at_end": true,          // Learn from final STM state
  "clear_stm_between": false     // Clear STM between observations (isolation)
}
```

**Response** (`200 OK`):

```json
{
  "status": "completed",
  "processor_id": "user_alice",
  "observations_processed": 3,
  "initial_stm_length": 0,
  "final_stm_length": 3,
  "results": [
    {
      "status": "okay",
      "sequence_position": 0,
      "stm_length": 1,
      "time": 1,
      "unique_id": "obs_1",
      "auto_learned_pattern": null
    },
    {
      "status": "okay",
      "sequence_position": 1,
      "stm_length": 2,
      "time": 2,
      "unique_id": "obs_2",
      "auto_learned_pattern": null
    },
    {
      "status": "okay",
      "sequence_position": 2,
      "stm_length": 3,
      "time": 3,
      "unique_id": "obs_3",
      "auto_learned_pattern": null
    }
  ],
  "auto_learned_patterns": [],
  "final_learned_pattern": "PTRN|def456...",
  "isolated": false
}
```

**Fields**:

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `observations` | array | Yes | - | List of observation objects |
| `learn_after_each` | boolean | No | false | Learn pattern after each observation |
| `learn_at_end` | boolean | No | false | Learn pattern from final STM state |
| `clear_stm_between` | boolean | No | false | Clear STM between observations (isolation mode) |

**Processing Modes**:

1. **Sequential (default)**: Observations accumulate in STM
2. **Isolated** (`clear_stm_between=true`): Each observation starts with fresh STM
3. **Learn After Each** (`learn_after_each=true`): Creates pattern after each observation
4. **Learn At End** (`learn_at_end=true`): Creates pattern from final sequence

**Session Heartbeat**:

For large batches (>50 observations), KATO automatically extends the session TTL every 30 seconds to prevent expiration during processing.

**Example - Sequential Learning**:

```bash
curl -X POST http://localhost:8000/sessions/session-abc123.../observe-sequence \
  -H "Content-Type: application/json" \
  -d '{
    "observations": [
      {"strings": ["login"]},
      {"strings": ["view_dashboard"]},
      {"strings": ["logout"]}
    ],
    "learn_at_end": true
  }'
```

**Example - Isolated Processing**:

```bash
curl -X POST http://localhost:8000/sessions/session-abc123.../observe-sequence \
  -H "Content-Type: application/json" \
  -d '{
    "observations": [
      {"strings": ["document_1"]},
      {"strings": ["document_2"]},
      {"strings": ["document_3"]}
    ],
    "clear_stm_between": true,
    "learn_after_each": true
  }'
```

---

### Get Short-Term Memory

Retrieve the current STM state for a session.

```http
GET /sessions/{session_id}/stm
```

**Response** (`200 OK`):

```json
{
  "stm": [
    ["hello", "world"],
    ["foo", "bar"],
    ["goodbye"]
  ],
  "session_id": "session-abc123...",
  "length": 3
}
```

**STM Structure**:

STM is a list of events, where each event is a list of strings:

```python
[
  ["symbol1", "symbol2"],  # Event 1
  ["symbol3"],             # Event 2
  ["symbol4", "symbol5"]   # Event 3
]
```

**Example**:

```bash
curl http://localhost:8000/sessions/session-abc123.../stm
```

**Use Cases**:
- Debugging observation processing
- Verifying STM state before learning
- Monitoring sequence accumulation

---

## Multi-Modal Processing

### String Symbols

Direct string observations (most common):

```json
{
  "strings": ["login", "user_alice", "successful"]
}
```

**Behavior**:
- Sorted alphanumerically if `sort_symbols=true` (default with token matching)
- Exact string matching in pattern recognition

### Vector Embeddings

768-dimensional vector embeddings:

```json
{
  "vectors": [
    [0.1, 0.2, ..., 0.768],  // Vector 1
    [0.3, 0.4, ..., 0.768]   // Vector 2
  ]
}
```

**Behavior**:
- Converted to symbolic names: `VCTR|<hash>`
- Hash computed from vector values
- Stored in Qdrant for similarity search
- Treated as symbols in pattern matching

**See**: [../vector-embeddings.md](../../research/vector-embeddings.md)

### Emotives

Emotional or utility values:

```json
{
  "emotives": {
    "happiness": 0.8,
    "urgency": -0.3,
    "confidence": 0.95
  }
}
```

**Behavior**:
- Stored in rolling window (size = `persistence` parameter)
- Averaged when retrieved in predictions
- Accumulated across observations

**See**: [../emotives-processing.md](../../research/emotives-processing.md)

### Metadata

Contextual tags:

```json
{
  "metadata": {
    "source": "user_input",
    "timestamp": "2025-11-13T12:00:00Z",
    "location": "login_page"
  }
}
```

**Behavior**:
- Stored as unique string lists
- Set-union accumulation
- Associated with patterns

**See**: [../metadata-processing.md](../../research/metadata-processing.md)

## Auto-Learning

If `max_pattern_length > 0`, KATO automatically learns when STM reaches that length.

**Configuration**:

```json
{
  "config": {
    "max_pattern_length": 5,  // Auto-learn at 5 events
    "stm_mode": "CLEAR"       // Clear STM after learning
  }
}
```

**Auto-Learning Modes**:

| `stm_mode` | Behavior After Auto-Learning |
|------------|------------------------------|
| `CLEAR` | STM is cleared completely |
| `ROLLING` | First event removed, rest kept |

**Response with Auto-Learning**:

```json
{
  "status": "okay",
  "auto_learned_pattern": "PTRN|abc123...",
  "stm_length": 0  // If CLEAR mode
}
```

## Symbol Sorting

KATO can sort symbols within each event for deterministic pattern matching.

**Token-Level Matching** (`use_token_matching=true`):
- Requires `sort_symbols=true`
- Symbols sorted alphanumerically
- Fast exact matching (9x faster than character-level)

**Character-Level Matching** (`use_token_matching=false`):
- Requires `sort_symbols=false`
- Symbols unsorted (preserves order)
- Fuzzy string matching (for document chunks)

**Example - Sorted**:

```json
Input: {"strings": ["world", "hello"]}
Stored: ["hello", "world"]  // Alphanumerically sorted
```

**Example - Unsorted**:

```json
Input: {"strings": ["world", "hello"]}
Stored: ["world", "hello"]  // Order preserved
```

## Best Practices

### 1. Batch with observe-sequence

For multiple observations, use `observe-sequence` instead of multiple `observe` calls:

```javascript
// ❌ Inefficient
for (const obs of observations) {
  await fetch(`/sessions/${sessionId}/observe`, {
    method: 'POST',
    body: JSON.stringify({strings: obs})
  });
}

// ✅ Efficient
await fetch(`/sessions/${sessionId}/observe-sequence`, {
  method: 'POST',
  body: JSON.stringify({
    observations: observations.map(obs => ({strings: obs}))
  })
});
```

### 2. Use Unique IDs for Tracking

```json
{
  "observations": [
    {"strings": ["event1"], "unique_id": "user_action_123"},
    {"strings": ["event2"], "unique_id": "user_action_124"}
  ]
}
```

### 3. Choose Appropriate Processing Mode

- **Sequential**: Learning user workflows, conversation flows
- **Isolated**: Processing independent documents, batch classification
- **Learn After Each**: Online learning, immediate feedback
- **Learn At End**: Sequence learning, complete pattern capture

### 4. Handle Vector Dimensions

Always use 768-dimensional vectors (KATO standard):

```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer('all-mpnet-base-v2')  # 768 dimensions
embedding = model.encode("hello world")

assert len(embedding) == 768  # Verify dimension
```

## Error Handling

### Session Not Found (404)

```python
try:
    response = await observe(session_id, data)
except SessionNotFoundError:
    # Create new session
    session = await create_session(node_id)
    response = await observe(session.session_id, data)
```

### Vector Dimension Mismatch (400)

```python
try:
    response = await observe(session_id, {
        "vectors": [[0.1, 0.2]]  # Wrong dimension!
    })
except VectorDimensionError as e:
    print(f"Expected: {e.expected_dimension}")
    print(f"Got: {e.actual_dimension}")
    # Fix vector dimension
```

### Empty Observations

```python
# Valid but does nothing
await observe(session_id, {"strings": []})

# Better: skip empty observations
if has_data:
    await observe(session_id, data)
```

## Performance Considerations

### Observation Size

- **Strings**: No practical limit, but consider pattern complexity
- **Vectors**: Each vector adds ~6KB storage
- **Emotives**: Lightweight (<1KB per observation)
- **Metadata**: Lightweight, stored as unique lists

### Sequence Size

- **< 50 observations**: Normal processing
- **50-1000 observations**: Heartbeat enabled automatically
- **> 1000 observations**: Consider batching into multiple sequences

### Network Efficiency

```python
# ❌ Many small requests (high overhead)
for i in range(1000):
    await observe(session_id, small_observation)

# ✅ Fewer large requests (low overhead)
await observe_sequence(session_id, {
    "observations": all_observations,
    "learn_at_end": true
})
```

## See Also

- [Predictions API](predictions.md) - Get predictions from observations
- [Learning API](learning.md) - Learn patterns from STM
- [Session Management](sessions.md) - Create and manage sessions
- [Observation Object Specification](../observation-object.md)
- [Pattern Matching Research](../../research/pattern-matching.md)

---

**Last Updated**: November 2025
**KATO Version**: 3.0+
