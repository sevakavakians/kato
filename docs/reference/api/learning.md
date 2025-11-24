# Learning API

Endpoints for learning patterns from observations and managing memory.

## Overview

Learning converts sequences in short-term memory (STM) into persistent patterns in long-term memory (LTM).

**Key Concepts**:
- **Manual Learning**: Explicit `learn` endpoint call
- **Auto-Learning**: Automatic when STM reaches `max_pattern_length`
- **Pattern Persistence**: Patterns stored permanently in ClickHouse
- **Pattern Frequency**: Incremented when same pattern re-learned

## Endpoints

### Learn Pattern from STM

Learn a pattern from the session's current STM.

```http
POST /sessions/{session_id}/learn
```

**Request**: No body required

**Response** (`200 OK`):

```json
{
  "status": "learned",
  "pattern_name": "PTRN|abc123def456...",
  "session_id": "session-abc123...",
  "message": "Learned pattern PTRN|abc123... from 5 events"
}
```

**Errors**:

- `404 Not Found`: Session not found or expired
- `400 Bad Request`: Cannot learn from empty STM

**Example**:

```bash
# 1. Build up STM with observations
curl -X POST http://localhost:8000/sessions/$SESSION_ID/observe-sequence \
  -H "Content-Type: application/json" \
  -d '{
    "observations": [
      {"strings": ["login"]},
      {"strings": ["view_dashboard"]},
      {"strings": ["edit_profile"]},
      {"strings": ["logout"]}
    ]
  }'

# 2. Learn pattern
curl -X POST http://localhost:8000/sessions/$SESSION_ID/learn
```

**Response**:

```json
{
  "status": "learned",
  "pattern_name": "PTRN|a1b2c3d4...",
  "session_id": "session-xyz...",
  "message": "Learned pattern PTRN|a1b2c3d4... from 4 events"
}
```

---

### Clear Short-Term Memory

Clear the STM for a specific session.

```http
POST /sessions/{session_id}/clear-stm
```

**Request**: No body required

**Response** (`200 OK`):

```json
{
  "status": "cleared",
  "session_id": "session-abc123..."
}
```

**Errors**:

- `404 Not Found`: Session not found

**Example**:

```bash
curl -X POST http://localhost:8000/sessions/$SESSION_ID/clear-stm
```

**Use Cases**:
- Start fresh sequence
- Reset after learning
- Clear failed observations

**Note**: Clearing STM does NOT delete learned patterns.

---

### Clear All Memory

Clear all memory (STM + learned patterns) for a specific session's node.

```http
POST /sessions/{session_id}/clear-all
```

**Request**: No body required

**Response** (`200 OK`):

```json
{
  "status": "cleared",
  "session_id": "session-abc123...",
  "scope": "all"
}
```

**Errors**:

- `404 Not Found`: Session not found

**Example**:

```bash
curl -X POST http://localhost:8000/sessions/$SESSION_ID/clear-all
```

**⚠️ WARNING**: This deletes ALL learned patterns for the session's `kb_id`. This affects:
- All sessions with the same `kb_id`
- All learned patterns in ClickHouse
- All vector embeddings in Qdrant

**Use Cases**:
- Complete system reset
- Starting over with training data
- Development/testing cleanup

**Production Note**: Use with extreme caution in production. Consider using separate `kb_id` values for isolation instead.

---

## Learning Behavior

### STM to Pattern Conversion

When you call `learn`:

1. **STM Capture**: Current STM state captured as sequence
2. **Hash Generation**: SHA1 hash computed from sequence
3. **Pattern Lookup**: Check if pattern already exists
4. **Pattern Storage**:
   - **New pattern**: Create with frequency=1
   - **Existing pattern**: Increment frequency
5. **Emotives/Metadata**: Append to rolling windows
6. **STM Handling**: STM cleared or rolled based on `stm_mode`

**Example**:

```python
STM: [["a", "b"], ["c"]]
↓
Pattern: {
  "name": "PTRN|abc123...",
  "data": [["a", "b"], ["c"]],
  "frequency": 1,
  "emotives": {...},
  "metadata": {...}
}
```

### Pattern Frequency

When the same pattern is learned multiple times:

```python
# First learning
learn() → PTRN|abc123... (frequency=1)

# Second learning (same sequence)
learn() → PTRN|abc123... (frequency=2)

# Third learning
learn() → PTRN|abc123... (frequency=3)
```

**Use Case**: Pattern frequency indicates how often a sequence occurs in your data.

---

## Auto-Learning

Configure automatic learning when STM reaches a specific length:

```json
{
  "config": {
    "max_pattern_length": 5,  // Auto-learn at 5 events
    "stm_mode": "CLEAR"       // Clear STM after learning
  }
}
```

**Auto-Learning Behavior**:

```python
# With max_pattern_length=5
observe() → STM length = 1
observe() → STM length = 2
observe() → STM length = 3
observe() → STM length = 4
observe() → STM length = 5  # AUTO-LEARN TRIGGERED
# Pattern learned, STM cleared (if CLEAR mode)
observe() → STM length = 1  # Fresh start
```

### STM Modes

| Mode | Behavior After Auto-Learning |
|------|------------------------------|
| `CLEAR` | STM completely cleared |
| `ROLLING` | First event removed, rest kept |

**Example - CLEAR**:

```python
STM: [["a"], ["b"], ["c"], ["d"], ["e"]]  # Length = 5
↓ Auto-learn triggered
Pattern: PTRN|abc123... (contains all 5 events)
STM: []  # Cleared
```

**Example - ROLLING**:

```python
STM: [["a"], ["b"], ["c"], ["d"], ["e"]]  # Length = 5
↓ Auto-learn triggered
Pattern: PTRN|abc123... (contains all 5 events)
STM: [["b"], ["c"], ["d"], ["e"]]  # First event removed
```

**Configuration**:

```bash
curl -X POST http://localhost:8000/sessions/$SESSION_ID/config \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "max_pattern_length": 10,
      "stm_mode": "ROLLING"
    }
  }'
```

---

## Learning Strategies

### 1. Manual Learning (Explicit Control)

```json
{
  "config": {
    "max_pattern_length": 0  // Disable auto-learning
  }
}
```

**Workflow**:

```bash
# Build sequence
observe-sequence → STM accumulates
observe-sequence → STM accumulates

# Explicit learn when ready
learn → Pattern created
```

**Use Cases**:
- Custom sequence boundaries
- User-triggered learning
- Complex sequences with varying lengths

### 2. Auto-Learning (Automatic)

```json
{
  "config": {
    "max_pattern_length": 5,
    "stm_mode": "CLEAR"
  }
}
```

**Workflow**:

```bash
observe → STM: 1 event
observe → STM: 2 events
observe → STM: 3 events
observe → STM: 4 events
observe → STM: 5 events → AUTO-LEARN → STM: 0 events
```

**Use Cases**:
- Fixed-length sequences
- Sliding window patterns
- Continuous learning

### 3. Batch Learning (Bulk Processing)

```bash
curl -X POST http://localhost:8000/sessions/$SESSION_ID/observe-sequence \
  -H "Content-Type: application/json" \
  -d '{
    "observations": [...],  // Many observations
    "learn_at_end": true    // Learn from final STM
  }'
```

**Use Cases**:
- Importing historical data
- Processing logs
- Training from datasets

### 4. Incremental Learning

```bash
curl -X POST http://localhost:8000/sessions/$SESSION_ID/observe-sequence \
  -H "Content-Type: application/json" \
  -d '{
    "observations": [...],     // Multiple observations
    "learn_after_each": true   // Learn after each observation
  }'
```

**Use Cases**:
- Online learning
- Streaming data
- Real-time adaptation

---

## Learning Workflow Examples

### Example 1: User Session Pattern

```bash
# Create session
SESSION_ID=$(curl -X POST http://localhost:8000/sessions \
  -d '{"node_id": "app_user_sessions"}' | jq -r '.session_id')

# Observe user actions
curl -X POST http://localhost:8000/sessions/$SESSION_ID/observe-sequence \
  -d '{
    "observations": [
      {"strings": ["login"], "metadata": {"page": "auth"}},
      {"strings": ["view_dashboard"], "metadata": {"page": "home"}},
      {"strings": ["click_settings"], "metadata": {"page": "home"}},
      {"strings": ["update_profile"], "metadata": {"page": "settings"}},
      {"strings": ["logout"], "metadata": {"page": "settings"}}
    ],
    "learn_at_end": true
  }'

# Pattern learned: login → dashboard → settings → profile → logout
```

### Example 2: Document Classification

```bash
# Isolated document processing
curl -X POST http://localhost:8000/sessions/$SESSION_ID/observe-sequence \
  -d '{
    "observations": [
      {"strings": ["doc1_content"], "metadata": {"label": "category_A"}},
      {"strings": ["doc2_content"], "metadata": {"label": "category_A"}},
      {"strings": ["doc3_content"], "metadata": {"label": "category_B"}}
    ],
    "clear_stm_between": true,   // Each doc independent
    "learn_after_each": true      // Learn each doc as pattern
  }'
```

### Example 3: Sequence with Emotives

```bash
curl -X POST http://localhost:8000/sessions/$SESSION_ID/observe-sequence \
  -d '{
    "observations": [
      {"strings": ["task_start"], "emotives": {"motivation": 0.8}},
      {"strings": ["task_progress"], "emotives": {"motivation": 0.6}},
      {"strings": ["task_blocked"], "emotives": {"motivation": -0.3}},
      {"strings": ["task_unblocked"], "emotives": {"motivation": 0.4}},
      {"strings": ["task_complete"], "emotives": {"motivation": 0.9}}
    ],
    "learn_at_end": true
  }'

# Pattern includes averaged emotives
```

---

## Pattern Retrieval

After learning, retrieve patterns via utility endpoints:

```bash
# Get specific pattern
curl http://localhost:8000/pattern/PTRN|abc123...

# Response
{
  "pattern": {
    "name": "PTRN|abc123...",
    "data": [["login"], ["dashboard"], ["logout"]],
    "frequency": 5,
    "emotives": {"confidence": [0.8, 0.9, 0.7, 0.85, 0.82]},
    "metadata": {"source": ["web", "mobile"]}
  },
  "node_id": "user_alice"
}
```

---

## Best Practices

### 1. Choose Appropriate Learning Mode

- **Manual**: Variable-length sequences, user control
- **Auto-learning**: Fixed-length patterns, continuous processing
- **Batch**: Historical data, bulk import
- **Incremental**: Streaming data, online learning

### 2. Set Meaningful max_pattern_length

```json
{
  "max_pattern_length": 5   // Short sequences (e.g., user actions)
  "max_pattern_length": 20  // Medium sequences (e.g., conversation flows)
  "max_pattern_length": 100 // Long sequences (e.g., document sections)
  "max_pattern_length": 0   // Manual control
}
```

### 3. Monitor Pattern Growth

```python
# Check learned pattern count
response = requests.get(f"http://localhost:8000/status")
patterns_count = response.json()["processors"]["patterns_count"]
```

### 4. Use Metadata for Pattern Organization

```json
{
  "metadata": {
    "category": "user_workflow",
    "version": "1.0",
    "source": "production"
  }
}
```

---

## Error Handling

### Empty STM Error

```bash
curl -X POST http://localhost:8000/sessions/$SESSION_ID/learn
# Error: Cannot learn from empty STM
```

**Solution**: Process observations first

```bash
curl -X POST http://localhost:8000/sessions/$SESSION_ID/observe \
  -d '{"strings": ["event1"]}'

curl -X POST http://localhost:8000/sessions/$SESSION_ID/learn
```

### Minimum Sequence Length

KATO requires at least 2 events total across STM for learning:

```python
STM: [["a"]]  # Only 1 event → Cannot learn
STM: [["a"], ["b"]]  # 2 events → Can learn
STM: [["a", "b"]]  # 1 event with 2 symbols → Can learn
```

---

## See Also

- [Observations API](observations.md) - Create sequences for learning
- [Predictions API](predictions.md) - Use learned patterns
- [Session Configuration](../session-configuration.md) - Configure learning behavior
- [Pattern Object Reference](../pattern-object.md)

---

**Last Updated**: November 2025
**KATO Version**: 3.0+
