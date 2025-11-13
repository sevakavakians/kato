# Configuration API

Update session-specific configuration to customize KATO's behavior per session.

## Overview

Session configuration allows dynamic runtime adjustment of:
- Pattern matching thresholds
- Learning parameters
- Processing modes
- Filter pipeline settings

Configuration is **per-session**, meaning each session can have different behavior while sharing learned patterns (LTM) via `node_id`.

## Endpoints

### Update Session Configuration

Update configuration parameters for a specific session.

```http
POST /sessions/{session_id}/config
```

**Request Body**:

```json
{
  "config": {
    "recall_threshold": 0.5,
    "max_predictions": 100,
    "use_token_matching": true,
    "sort_symbols": true,
    "max_pattern_length": 10,
    "stm_mode": "CLEAR",
    "persistence": 20
  }
}
```

**Response** (`200 OK`):

```json
{
  "status": "okay",
  "message": "Configuration updated",
  "session_id": "session-abc123..."
}
```

**Errors**:

- `404 Not Found`: Session not found

**Example**:

```bash
curl -X POST http://localhost:8000/sessions/$SESSION_ID/config \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "recall_threshold": 0.7,
      "max_predictions": 50
    }
  }'
```

---

## Configuration Parameters

### Learning Configuration

| Parameter | Type | Range | Default | Description |
|-----------|------|-------|---------|-------------|
| `max_pattern_length` | integer | 0+ | 0 | Auto-learn when STM reaches this length (0=manual) |
| `persistence` | integer | 1-100 | 20 | Emotive rolling window size |
| `recall_threshold` | float | 0.0-1.0 | 0.1 | Pattern matching sensitivity |
| `stm_mode` | string | CLEAR\|ROLLING | CLEAR | STM mode after auto-learning |

### Processing Configuration

| Parameter | Type | Range | Default | Description |
|-----------|------|-------|---------|-------------|
| `max_predictions` | integer | 1-10000 | 10000 | Maximum predictions to return |
| `sort_symbols` | boolean | true\|false | true | Sort symbols alphanumerically |
| `use_token_matching` | boolean | true\|false | true | Token-level (true) vs character-level (false) |
| `process_predictions` | boolean | true\|false | true | Whether to process predictions |

### Filter Pipeline Configuration

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `filter_pipeline` | array[string] | ["length", "jaccard", "bloom", "minhash", "rapidfuzz"] | Ordered filter stages |
| `length_min_ratio` | float | 0.5 | Min pattern length as ratio of STM |
| `length_max_ratio` | float | 2.0 | Max pattern length as ratio of STM |
| `jaccard_threshold` | float | 0.3 | Minimum Jaccard similarity |
| `jaccard_min_overlap` | integer | 2 | Minimum token overlap count |
| `minhash_threshold` | float | 0.7 | LSH Jaccard threshold |
| `bloom_false_positive_rate` | float | 0.01 | Bloom filter FPR |
| `max_candidates_per_stage` | integer | 100000 | Safety limit per filter stage |
| `enable_filter_metrics` | boolean | true | Log filter timing/counts |

**See**: [../session-configuration.md](../session-configuration.md) for complete reference.

---

## Configuration at Session Creation

Set configuration when creating a session:

```bash
curl -X POST http://localhost:8000/sessions \
  -H "Content-Type: application/json" \
  -d '{
    "node_id": "user_alice",
    "config": {
      "recall_threshold": 0.5,
      "max_pattern_length": 5,
      "use_token_matching": true
    }
  }'
```

**Response**:

```json
{
  "session_id": "session-abc123...",
  "node_id": "user_alice",
  "session_config": {
    "recall_threshold": 0.5,
    "max_pattern_length": 5,
    "use_token_matching": true,
    "sort_symbols": true
  }
}
```

---

## Auto-Toggling: sort_symbols and use_token_matching

KATO automatically syncs `sort_symbols` with `use_token_matching` for correct behavior:

**Token-level matching** requires sorted symbols:
```json
{
  "use_token_matching": true  // Auto-sets sort_symbols=true
}
```

**Character-level matching** requires unsorted symbols:
```json
{
  "use_token_matching": false  // Auto-sets sort_symbols=false
}
```

**Warning**: If you manually set conflicting values, KATO logs a warning but uses your values:

```json
{
  "use_token_matching": true,
  "sort_symbols": false  // ⚠️ MISMATCH WARNING
}
```

---

## Configuration Examples

### High-Precision Mode

For applications requiring exact matches:

```json
{
  "config": {
    "recall_threshold": 0.9,
    "use_token_matching": true,
    "max_predictions": 10
  }
}
```

**Use Cases**:
- Security pattern matching
- Exact sequence detection
- High-confidence predictions

### Exploratory Mode

For discovering patterns with loose matching:

```json
{
  "config": {
    "recall_threshold": 0.1,
    "max_predictions": 1000,
    "use_token_matching": false  // Fuzzy matching
  }
}
```

**Use Cases**:
- Pattern discovery
- Research and analysis
- Exploring large datasets

### Auto-Learning Mode

For continuous learning from streaming data:

```json
{
  "config": {
    "max_pattern_length": 10,
    "stm_mode": "ROLLING",
    "recall_threshold": 0.3
  }
}
```

**Use Cases**:
- Real-time learning
- Streaming data processing
- Sliding window patterns

### Document Analysis Mode

For character-level similarity on text chunks:

```json
{
  "config": {
    "use_token_matching": false,  // Character-level
    "sort_symbols": false,         // Preserve order
    "recall_threshold": 0.5,
    "max_predictions": 100
  }
}
```

**Use Cases**:
- Document similarity
- Natural language processing
- Fuzzy text matching

---

## Dynamic Configuration Updates

Update configuration mid-session:

```bash
# Start with default config
SESSION_ID=$(curl -X POST http://localhost:8000/sessions \
  -d '{"node_id": "user_alice"}' | jq -r '.session_id')

# Process some observations
curl -X POST http://localhost:8000/sessions/$SESSION_ID/observe-sequence \
  -d '{"observations": [...]}'

# Update config for stricter matching
curl -X POST http://localhost:8000/sessions/$SESSION_ID/config \
  -d '{"config": {"recall_threshold": 0.8}}'

# Future predictions use new threshold
curl http://localhost:8000/sessions/$SESSION_ID/predictions
```

---

## Validation

KATO validates all configuration parameters:

| Parameter | Validation | Error |
|-----------|------------|-------|
| `recall_threshold` | 0.0 ≤ x ≤ 1.0 | Invalid recall_threshold |
| `persistence` | 1 ≤ x ≤ 100 | Invalid persistence |
| `max_pattern_length` | x ≥ 0 | Invalid max_pattern_length |
| `max_predictions` | 1 ≤ x ≤ 10000 | Invalid max_predictions |

**Example Error**:

```bash
curl -X POST http://localhost:8000/sessions/$SESSION_ID/config \
  -d '{"config": {"recall_threshold": 1.5}}'

# Error: Invalid recall_threshold: 1.5 (must be 0.0-1.0)
```

---

## Best Practices

### 1. Choose Matching Mode Appropriately

```python
# Token-level: Discrete events, exact matching
{
  "use_token_matching": True,
  "sort_symbols": True
}

# Character-level: Text similarity, fuzzy matching
{
  "use_token_matching": False,
  "sort_symbols": False
}
```

### 2. Tune recall_threshold for Use Case

```python
# Permissive (more predictions, lower quality)
{"recall_threshold": 0.1}

# Balanced (default)
{"recall_threshold": 0.3}

# Strict (fewer predictions, higher quality)
{"recall_threshold": 0.8}
```

### 3. Set max_predictions for Performance

```python
# Fast response, top predictions only
{"max_predictions": 10}

# Moderate
{"max_predictions": 100}

# Comprehensive analysis
{"max_predictions": 1000}
```

### 4. Use persistence for Emotive Windows

```python
# Short-term emotives
{"persistence": 5}

# Medium-term (default)
{"persistence": 20}

# Long-term history
{"persistence": 100}
```

---

## See Also

- [Session Configuration Reference](../session-configuration.md) - Complete parameter documentation
- [Session Management API](sessions.md) - Create and manage sessions
- [Pattern Matching Research](../../research/pattern-matching.md) - Matching algorithms
- [Filter Pipeline Configuration](../../research/pattern-matching.md#filter-pipeline)

---

**Last Updated**: November 2025
**KATO Version**: 3.0+
