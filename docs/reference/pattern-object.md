# Pattern Object Specification

Complete specification for KATO pattern data structures.

## Overview

Patterns are learned sequences stored in ClickHouse as long-term memory (LTM). Each pattern represents knowledge extracted from observations.

## Pattern Structure

```json
{
  "name": "PTRN|abc123def456...",
  "data": [
    ["event1_symbol1", "event1_symbol2"],
    ["event2_symbol1"],
    ["event3_symbol1", "event3_symbol2"]
  ],
  "frequency": 5,
  "emotives": {
    "happiness": [0.8, 0.9, 0.7, 0.85, 0.82],
    "urgency": [-0.3, -0.2, -0.4, -0.1, -0.25]
  },
  "metadata": {
    "source": ["web", "mobile", "api"],
    "version": ["1.0", "1.1"],
    "category": ["user_action"]
  }
}
```

## Fields

### name (string)

**Format**: `PTRN|<sha1_hash>`

**Description**: Unique pattern identifier computed via SHA1 hash of pattern data.

**Example**: `PTRN|a1b2c3d4e5f6789012345678901234567890`

**Hash Computation**:

```python
import hashlib

pattern_string = str(pattern_data)
hash_value = hashlib.sha1(pattern_string.encode()).hexdigest()
pattern_name = f"PTRN|{hash_value}"
```

### data (array[array[string]])

**Description**: Sequence of events, where each event is a list of strings.

**Structure**:

```python
[
  ["symbol1", "symbol2"],  # Event 1
  ["symbol3"],             # Event 2
  ["symbol4", "symbol5"]   # Event 3
]
```

**Rules**:
- Outer array: Temporal sequence of events
- Inner arrays: Symbols within each event
- Symbols may be sorted if `sort_symbols=true`
- Minimum pattern length: 1 event with 2+ total symbols

### frequency (integer)

**Description**: Number of times this pattern was learned.

**Range**: 1 to n

**Behavior**:
- Starts at 1 when first learned
- Increments each time same pattern re-learned
- Used in prediction weighting

**Example**:

```python
frequency=1   # Learned once (rare)
frequency=10  # Learned 10 times (common)
frequency=100 # Learned 100 times (very common)
```

### emotives (object)

**Description**: Rolling window arrays of emotive values.

**Structure**:

```json
{
  "emotive_name": [value1, value2, ..., valueN],
  "another_emotive": [value1, value2, ..., valueN]
}
```

**Rules**:
- Window size controlled by `persistence` parameter (default: 5)
- Values can be positive, negative, integer, or float
- Arrays grow to `persistence` size, then oldest values removed
- Retrieved as averages in predictions

**Example**:

```json
{
  "confidence": [0.8, 0.9, 0.7, 0.85, 0.82],
  "urgency": [-0.3, -0.2, -0.4, -0.1, -0.25]
}
```

### metadata (object)

**Description**: Unique string lists (set-union accumulation).

**Structure**:

```json
{
  "key": ["unique", "values", "list"],
  "another_key": ["more", "values"]
}
```

**Rules**:
- Values stored as arrays of unique strings
- Set-union accumulation on re-learning
- No duplicates within each key

**Example**:

```json
{
  "source": ["web", "mobile", "api"],
  "version": ["1.0", "1.1", "2.0"],
  "category": ["user_action"]
}
```

## Pattern Lifecycle

### 1. Learning

```python
# STM state
STM: [["login"], ["dashboard"], ["logout"]]

# Learn pattern
pattern_name = learn()
→ "PTRN|abc123..."
→ Pattern stored with frequency=1
```

### 2. Re-Learning

```python
# Same STM sequence observed again
STM: [["login"], ["dashboard"], ["logout"]]

# Learn again
pattern_name = learn()
→ "PTRN|abc123..."  # Same hash
→ Pattern frequency incremented to 2
→ Emotives appended to rolling window
→ Metadata merged via set-union
```

### 3. Retrieval

```bash
GET /pattern/PTRN|abc123...?kb_id=user_alice
```

**Response**:

```json
{
  "pattern": {
    "name": "PTRN|abc123...",
    "data": [["login"], ["dashboard"], ["logout"]],
    "frequency": 2,
    "emotives": {...},
    "metadata": {...}
  },
  "kb_id": "user_alice"
}
```

## Storage

### ClickHouse

**Database**: Shared `kato` database

**Table**: `patterns` (partitioned by `kb_id`)

**Index**: Primary key on `(kb_id, name)` with Bloom filter

**Row**:

```sql
SELECT * FROM patterns WHERE kb_id='user_alice' AND name='abc123...'

-- Returns:
-- name: "abc123..."
-- kb_id: "user_alice"
-- data: [["login"],["dashboard"],["logout"]]
-- frequency: 5
-- emotives: '{"confidence":[0.8,0.9,0.7]}'
-- metadata: '{"source":["web","mobile"]}'
-- created_at: "2025-11-13 12:00:00"
-- updated_at: "2025-11-13 14:30:00"
```

### Qdrant (Vectors)

If pattern contains vector-derived symbols (`VCTR|hash`):

**Collection**: `vectors_<kb_id>`

**Vector Storage**: 768-dimensional embeddings

**Payload**: Links back to pattern via `VCTR|hash` name

## See Also

- [Prediction Object](prediction-object.md) - How patterns generate predictions
- [Observation Object](observation-object.md) - How observations become patterns
- [Learning API](api/learning.md) - Pattern learning endpoints

---

**Last Updated**: November 2025
**KATO Version**: 3.0+
