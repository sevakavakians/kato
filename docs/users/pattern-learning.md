# Pattern Learning Guide

Complete guide to learning patterns in KATO, including temporal sequences, non-temporal profiles, and advanced learning strategies.

## What is a Pattern?

A **pattern** in KATO is a learned sequence of observations that represents knowledge. Patterns can be:

1. **Temporal Sequences**: Time-ordered events (e.g., morning routine, error-fix sequences)
2. **Non-Temporal Profiles**: Unordered associations (e.g., user preferences, feature bundles)
3. **Hybrid**: Both temporal and associative elements

### Pattern Structure

```json
{
  "pattern_name": "PTN|a1b2c3d4e5f6",
  "length": 3,
  "events": [
    ["coffee", "morning"],
    ["commute", "train"],
    ["arrive", "work"]
  ],
  "emotive_profile": {
    "energy": [[-0.2], [0.0], [0.5]],
    "focus": [[null], [0.3], [0.8]]
  },
  "metadata": {
    "location": [["home"], ["transit"], ["office"]]
  }
}
```

**Components**:
- **pattern_name**: Unique hash identifier (`PTN|{hash}`)
- **length**: Number of events in pattern
- **events**: Time-ordered list of symbol sets (sorted within each event)
- **emotive_profile**: Rolling window of emotive values per event
- **metadata**: Accumulated metadata per event

## Learning Workflow

### Manual Learning (Default)

```
Observations → STM → Learn Command → LTM Pattern
```

**Step 1: Send Observations**
```bash
curl -X POST http://localhost:8000/sessions/{session_id}/observe \
  -d '{"strings": ["morning", "coffee"], "vectors": [], "emotives": {"energy": -0.2}}'

curl -X POST http://localhost:8000/sessions/{session_id}/observe \
  -d '{"strings": ["train", "commute"], "vectors": [], "emotives": {"energy": 0.0}}'

curl -X POST http://localhost:8000/sessions/{session_id}/observe \
  -d '{"strings": ["work", "arrive"], "vectors": [], "emotives": {"energy": 0.5}}'
```

**Step 2: Trigger Learning**
```bash
curl -X POST http://localhost:8000/sessions/{session_id}/learn
```

**Response**:
```json
{
  "pattern_name": "PTN|a1b2c3",
  "length": 3,
  "events": [
    ["coffee", "morning"],
    ["commute", "train"],
    ["arrive", "work"]
  ],
  "emotive_profile": {
    "energy": [[-0.2], [0.0], [0.5]]
  },
  "message": "Pattern learned successfully",
  "stored_in": "node_my_app_kato"
}
```

### Auto-Learning (Optional)

Enable automatic learning when STM reaches threshold.

**Configuration** (.env):
```bash
MAX_PATTERN_LENGTH=10  # Auto-learn at 10 events
STM_MODE=CLEAR         # Clear STM after learning
```

**Behavior**:
1. STM grows: 1 → 2 → ... → 9 events
2. 10th observation arrives
3. **Automatic learning triggered**
4. Pattern stored in LTM
5. STM cleared (or rolled, depending on `STM_MODE`)

**Use Cases**:
- **Streaming data**: Continuous event processing
- **Real-time analytics**: Pattern discovery
- **Background workers**: Autonomous learning

## Pattern Types

### 1. Temporal Sequences

Time-ordered patterns where order matters.

**Example: User Journey**
```python
# Event 1: Landing
kato.observe(["page:home", "source:google"], emotives={"interest": 0.3})

# Event 2: Browse
kato.observe(["page:products", "action:scroll"], emotives={"interest": 0.6})

# Event 3: Convert
kato.observe(["page:checkout", "action:purchase"], emotives={"interest": 0.9})

# Learn journey pattern
pattern = kato.learn()
# Pattern captures: home → products → checkout sequence
```

**Properties**:
- Order is significant
- Temporal relationships preserved
- Future events predictable from past
- Emotive progression tracked

### 2. Non-Temporal Profiles

Unordered associations where co-occurrence matters, not order.

**Example: User Preferences**
```python
# Single event with all preferences
kato.observe([
    "user:alice",
    "theme:dark",
    "language:python",
    "editor:vim",
    "notifications:off"
])

# Learn preference profile
pattern = kato.learn()
# Pattern represents user:alice's complete profile
```

**Properties**:
- Order irrelevant (symbols sorted)
- Associations captured
- No temporal prediction
- Used for lookups/retrieval

**Later: Retrieve by Partial Input**
```python
kato.clear_stm()
kato.observe(["user:alice"])
predictions = kato.get_predictions()
# Returns: theme:dark, language:python, editor:vim, notifications:off
```

### 3. Hybrid Patterns

Combine temporal sequences with rich per-event attributes.

**Example: Error Diagnosis**
```python
# Event 1: Error context
kato.observe([
    "error:timeout",
    "service:api",
    "region:us-east",
    "load:high"
], emotives={"urgency": 0.8})

# Event 2: Diagnostic steps
kato.observe([
    "action:check_logs",
    "result:connection_pool_exhausted"
], emotives={"urgency": 0.9})

# Event 3: Resolution
kato.observe([
    "action:scale_instances",
    "result:resolved",
    "duration:5min"
], emotives={"urgency": 0.2})

pattern = kato.learn()
# Pattern captures: error context → diagnosis → resolution
```

## Pattern Naming

### Hash-Based Naming

KATO generates unique names from pattern content:

```
Pattern Content → Hash → PTN|a1b2c3d4e5f6
```

**Properties**:
- **Deterministic**: Same pattern always gets same name
- **Collision-resistant**: Different patterns get different names
- **Content-addressable**: Name derived from content

### Pattern Name Format

```
PTN|{hash}
```

**Examples**:
- `PTN|a1b2c3d4e5f6`
- `PTN|9f8e7d6c5b4a`
- `VCTR|x1y2z3w4v5u6` (vector-derived pattern)

### Pattern Deduplication

KATO automatically deduplicates patterns:

```python
# Learn same pattern twice
kato.observe(["hello", "world"])
kato.learn()  # Creates PTN|abc123

kato.clear_stm()
kato.observe(["hello", "world"])
kato.learn()  # Returns existing PTN|abc123 (not duplicate)
```

**Benefit**: Natural deduplication - identical patterns share storage.

## Emotive Profiles

### Rolling Window Storage

Emotives stored as rolling windows (default: 5 values per pattern).

**Configuration**:
```bash
# .env
PERSISTENCE=5  # Store 5 most recent values
```

**Example**:
```python
# First time learning pattern
kato.observe(["morning"], emotives={"energy": 0.3})
kato.learn()
# Stored: energy: [[0.3]]

# Learn same pattern again later
kato.observe(["morning"], emotives={"energy": 0.5})
kato.learn()
# Stored: energy: [[0.3, 0.5]]

# Third time
kato.observe(["morning"], emotives={"energy": 0.4})
kato.learn()
# Stored: energy: [[0.3, 0.5, 0.4]]

# ... after 6 learnings
# Stored: energy: [[0.5, 0.4, 0.6, 0.3, 0.5]]  # Oldest (0.3) dropped
```

### Null Values

`null` indicates emotive not observed for that event.

```python
kato.observe(["event1"], emotives={"joy": 0.8})
kato.observe(["event2"], emotives={})  # No emotives
kato.observe(["event3"], emotives={"joy": 0.6})
kato.learn()

# Stored:
# joy: [[0.8], [null], [0.6]]
```

### Prediction Statistics

KATO computes statistics from rolling windows:

```json
"emotive_predictions": {
  "energy": {
    "mean": 0.43,
    "std": 0.15,
    "min": 0.2,
    "max": 0.6,
    "count": 5
  }
}
```

## Metadata Handling

### Set-Union Accumulation

Metadata values accumulated as sets across observations.

```python
# First learning
kato.observe(["action:login"], metadata={"device": "mobile", "location": "NYC"})
kato.learn()
# Stored: metadata: {"device": ["mobile"], "location": ["NYC"]}

# Second learning
kato.observe(["action:login"], metadata={"device": "desktop", "location": "SF"})
kato.learn()
# Stored: metadata: {"device": ["mobile", "desktop"], "location": ["NYC", "SF"]}

# Predictions include all accumulated values
```

**Use Cases**:
- Track all devices user logged in from
- Accumulate error contexts
- Collect feature usage patterns

## Learning Strategies

### Strategy 1: Fixed-Length Windows

Learn patterns of fixed size.

```python
# Auto-learn every 10 events
# .env: MAX_PATTERN_LENGTH=10

# Events 1-10 → Pattern A
# Events 11-20 → Pattern B
# Events 21-30 → Pattern C
```

**Use Cases**:
- Streaming analytics
- Time-series segmentation
- Batched processing

### Strategy 2: Sliding Windows

Use `STM_MODE=ROLLING` to create overlapping patterns.

```python
# .env:
# MAX_PATTERN_LENGTH=5
# STM_MODE=ROLLING

# Events: A B C D E F G H
# Pattern 1: A B C D E  (auto-learn, keep E)
# Pattern 2: E F G H I  (auto-learn, keep I)
# Overlapping windows capture transitions
```

**Use Cases**:
- Continuous streams
- Pattern transitions
- Anomaly detection

### Strategy 3: Semantic Boundaries

Learn when logical boundaries occur.

```python
# Learn when conversation topic changes
def should_learn(new_observation, current_stm):
    # Detect topic shift
    if topic_changed(new_observation, current_stm):
        kato.learn()
        kato.clear_stm()
    kato.observe(new_observation)
```

**Use Cases**:
- Conversation turns
- Session boundaries
- Task completion

### Strategy 4: Hierarchical Learning

Learn at multiple granularities.

```python
# Low-level: individual steps
kato_micro.observe(["click", "button_submit"])
kato_micro.learn()

# High-level: macro actions
kato_macro.observe(["task_login"])
kato_macro.learn()

# Different nodes, different granularity
```

**Use Cases**:
- Multi-scale analysis
- Abstraction hierarchies
- Drill-down exploration

## Advanced Patterns

### Multi-Modal Patterns

Combine strings, vectors, and emotives.

```python
# Text + embeddings + emotions
kato.observe(
    strings=["product:shoes", "brand:nike"],
    vectors=[[0.1, 0.2, ..., 0.768]],  # Image embedding
    emotives={"desire": 0.7, "confidence": 0.8},
    metadata={"price_range": "high", "category": "athletic"}
)
kato.learn()
```

### Conditional Patterns

Learn different patterns based on context.

```python
# Morning routine - weekday
if is_weekday():
    kato_weekday.observe(["alarm", "rush", "commute"])
else:
    kato_weekend.observe(["sleep_in", "relax", "brunch"])
```

**Alternative: Single node with context strings**
```python
context = "weekday" if is_weekday() else "weekend"
kato.observe([context, "morning", "routine"])
# Different patterns learned for weekday vs weekend
```

## Pattern Storage

### Vector Storage (Qdrant)

If pattern contains vectors, stored in Qdrant with pattern_name as payload:

```python
# Qdrant collection: vectors_{node_id}
{
  "id": "uuid-...",
  "vector": [0.1, 0.2, ..., 0.768],
  "payload": {
    "pattern_name": "PTN|a1b2c3d4e5f6",
    "event_index": 0,
    "vector_name": "VCTR|x1y2z3"
  }
}
```

## Pattern Inspection

### List Patterns

```python
# Pattern inspection not directly exposed via API
# Use internal storage queries for administrative access
# Contact system administrator for pattern statistics
```

## Best Practices

### When to Learn

1. **Learn frequently** for fast adaptation (auto-learn)
2. **Learn at boundaries** for discrete tasks (manual)
3. **Learn on demand** for controlled training
4. **Learn continuously** for streaming data

### Pattern Granularity

1. **Fine-grained**: More patterns, precise matching
2. **Coarse-grained**: Fewer patterns, generalization
3. **Multi-level**: Learn at multiple scales

### Memory Management

1. **Clear STM** after learning for clean boundaries
2. **Rolling STM** for overlapping patterns
3. **Monitor pattern count** - pattern storage grows with patterns
4. **Periodic cleanup** for obsolete patterns

### Performance

1. **Batch observations** before learning when possible
2. **Avoid learning after every observation** (use auto-learn)
3. **Index pattern storage** for faster retrieval
4. **Monitor learning latency** - increases with pattern count

## Troubleshooting

### Pattern Not Created

**Symptom**: `/learn` endpoint returns error

**Causes**:
- STM is empty
- STM has only 1 event (minimum: 2)
- Database connection failed

**Solution**:
```python
# Check STM before learning
stm = kato.get_stm()
if stm['length'] < 2:
    print("Need at least 2 events to learn")
else:
    kato.learn()
```

### Pattern Not Recalled

**Symptom**: No predictions returned

**Causes**:
- `recall_threshold` too high
- No matching patterns in LTM
- Wrong `node_id` (different database)

**Solution**:
```python
# Lower threshold
kato.create_session("my_app", config={"recall_threshold": 0.1})

# Verify patterns exist
# Contact system administrator for pattern verification

# Verify correct node_id
info = kato.get_session_info()
print(f"Connected to: {info['node_id']}")
```

### Duplicate Patterns

**Symptom**: Same pattern appearing multiple times

**Expected**: KATO automatically deduplicates by hash

**If happening**:
- Check if patterns are truly identical
- Verify emotive values (patterns with different emotives have same name but accumulated values)
- Check observation count in pattern metadata

## Related Documentation

- [First Session Tutorial](first-session.md)
- [Predictions Guide](predictions.md)
- [Core Concepts](concepts.md)
- [API Reference](../reference/api/)

---

**Last Updated**: November 2025
**KATO Version**: 3.0+
