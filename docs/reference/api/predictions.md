# Predictions API

Retrieve predictions based on learned patterns and current short-term memory.

## Overview

Predictions represent KATO's forecasts based on pattern matching between current observations (STM) and learned patterns (LTM).

Each prediction contains:
- **Temporal segmentation**: past/present/future
- **Match analysis**: matches/missing/extras
- **Information metrics**: confidence, evidence, similarity, SNR, entropy, potential
- **Pattern metadata**: frequency, emotives, metadata

## Endpoints

### Get Predictions

Get predictions based on the session's current STM.

```http
GET /sessions/{session_id}/predictions
```

**Response** (`200 OK`):

```json
{
  "predictions": [
    {
      "name": "PTRN|abc123def456...",
      "type": "prototypical",
      "frequency": 42,
      "matches": ["hello", "world"],
      "missing": ["goodbye"],
      "extras": ["unexpected"],
      "past": [["start"]],
      "present": [["hello", "world", "goodbye"]],
      "future": [["end"]],
      "confidence": 0.67,
      "evidence": 0.40,
      "similarity": 0.85,
      "snr": 0.33,
      "fragmentation": 0.0,
      "entropy": 1.58,
      "global_normalized_entropy": 0.72,
      "potential": 2.45
    }
  ],
  "future_potentials": [
    {
      "symbol": "end",
      "total_potential": 2.45,
      "prediction_count": 1,
      "patterns": ["PTRN|abc123..."]
    }
  ],
  "session_id": "session-abc123...",
  "count": 1
}
```

**Parameters**:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `session_id` | string (path) | Yes | Session identifier |

**Errors**:

- `404 Not Found`: Session not found or expired

**Example**:

```bash
curl http://localhost:8000/sessions/session-abc123.../predictions
```

---

## Prediction Object Structure

### Core Fields

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Pattern ID (PTRN\|hash) |
| `type` | string | Prediction type (always "prototypical") |
| `frequency` | integer | Number of times pattern was learned |

### Temporal Segmentation

| Field | Type | Description |
|-------|------|-------------|
| `past` | array[array[string]] | Events before first observed event |
| `present` | array[array[string]] | ALL events containing observed symbols (complete events) |
| `future` | array[array[string]] | Events after last observed event |

**Example**:

```python
Pattern: [["start"], ["hello", "world"], ["middle"], ["end"]]
Observing: ["hello", "end"]

past: [["start"]]                     # Before first match
present: [["hello", "world"], ["end"]]  # ALL events with matches (complete)
future: [["middle"]]                  # After last match (nothing after "end")
```

### Match Analysis

| Field | Type | Description |
|-------|------|-------------|
| `matches` | array[string] | Symbols present in both observation and pattern |
| `missing` | array[string] | Pattern symbols NOT observed (from present events) |
| `extras` | array[string] | Observed symbols NOT in pattern |

**Example**:

```python
Pattern present: [["a", "b"], ["c", "d"]]
Observing: ["a", "c", "x"]

matches: ["a", "c"]      # In both
missing: ["b", "d"]      # In pattern, not observed
extras: ["x"]            # Observed, not in pattern
```

### Information Metrics

| Field | Range | Description |
|-------|-------|-------------|
| `confidence` | 0.0-1.0 | Ratio of matches to total present symbols |
| `evidence` | 0.0-1.0 | Proportion of pattern observed |
| `similarity` | 0.0-1.0 | Base similarity score |
| `snr` | -1.0-1.0 | Signal-to-noise ratio (matches vs extras) |
| `fragmentation` | 0.0-n | Degree of match discontinuity |
| `entropy` | 0.0-n | Pattern complexity measure |
| `global_normalized_entropy` | 0.0-1.0 | Normalized entropy score |
| `potential` | 0.0-n | Prediction ranking score (default sort) |

**Formulas**:

```python
confidence = len(matches) / total_present_length
evidence = len(matches) / pattern_length
snr = (2 * len(matches) - len(extras)) / (2 * len(matches) + len(extras))
```

**See**: [../../research/predictive-information.md](../../research/predictive-information.md)

---

## Future Potentials

Aggregated predictions for future symbols.

```json
{
  "future_potentials": [
    {
      "symbol": "end",
      "total_potential": 5.67,
      "prediction_count": 3,
      "patterns": [
        "PTRN|abc123...",
        "PTRN|def456...",
        "PTRN|ghi789..."
      ]
    },
    {
      "symbol": "logout",
      "total_potential": 2.45,
      "prediction_count": 1,
      "patterns": ["PTRN|xyz999..."]
    }
  ]
}
```

**Use Cases**:
- Next symbol prediction
- Multi-pattern aggregation
- Confidence weighting

**Calculation**:

1. Extract all symbols from `future` events across all predictions
2. Sum `potential` for each unique symbol
3. Track which patterns contribute to each symbol
4. Sort by `total_potential` (descending)

---

## Prediction Filtering

Predictions are filtered by `recall_threshold` configuration:

```json
{
  "config": {
    "recall_threshold": 0.5
  }
}
```

| Threshold | Effect | Use Case |
|-----------|--------|----------|
| 0.0 | All patterns (no filtering) | Exploratory analysis |
| 0.1 | Very permissive (default) | General use |
| 0.5 | Moderate filtering | High-quality predictions |
| 1.0 | Exact matches only | Precise matching |

**Filtering Logic**:

```python
if similarity >= recall_threshold:
    include_prediction()
```

---

## Prediction Limiting

Limit number of predictions with `max_predictions` configuration:

```json
{
  "config": {
    "max_predictions": 100
  }
}
```

**Default**: 10000

**Behavior**:
- Predictions sorted by `potential` (descending)
- Top N predictions returned
- `future_potentials` computed from all matching patterns

---

## Empty STM Behavior

If STM is empty, predictions will be empty:

```json
{
  "predictions": [],
  "future_potentials": [],
  "session_id": "session-abc123...",
  "count": 0
}
```

**Solution**: Process observations first

```bash
# 1. Observe
curl -X POST http://localhost:8000/sessions/session-abc123.../observe \
  -d '{"strings": ["hello", "world"]}'

# 2. Get predictions
curl http://localhost:8000/sessions/session-abc123.../predictions
```

---

## Pattern Matching Modes

### Token-Level Matching (default)

**Configuration**:
```json
{"use_token_matching": true, "sort_symbols": true}
```

**Behavior**:
- Exact symbol matching
- 9x faster than character-level
- Symbols must match exactly
- Best for: Tokenized text, discrete events

**Performance**: ~11ms for 1000 patterns

### Character-Level Matching

**Configuration**:
```json
{"use_token_matching": false, "sort_symbols": false}
```

**Behavior**:
- Fuzzy string matching (RapidFuzz)
- Character-level similarity
- Best for: Document chunks, natural language

**Performance**: ~1000ms for 1000 patterns

**See**: [../../research/pattern-matching.md](../../research/pattern-matching.md)

---

## Example Workflows

### 1. Basic Prediction Workflow

```bash
# Create session
SESSION_ID=$(curl -X POST http://localhost:8000/sessions \
  -H "Content-Type: application/json" \
  -d '{"node_id": "user_alice"}' | jq -r '.session_id')

# Observe sequence
curl -X POST http://localhost:8000/sessions/$SESSION_ID/observe-sequence \
  -H "Content-Type: application/json" \
  -d '{
    "observations": [
      {"strings": ["login"]},
      {"strings": ["view_dashboard"]},
      {"strings": ["logout"]}
    ],
    "learn_at_end": true
  }'

# Observe again (partial match)
curl -X POST http://localhost:8000/sessions/$SESSION_ID/observe \
  -H "Content-Type: application/json" \
  -d '{"strings": ["login"]}'

# Get predictions
curl http://localhost:8000/sessions/$SESSION_ID/predictions
```

### 2. Using Future Potentials

```python
import requests

# Get predictions
response = requests.get(f"http://localhost:8000/sessions/{session_id}/predictions")
data = response.json()

# Get most likely next symbol
if data["future_potentials"]:
    next_symbol = data["future_potentials"][0]["symbol"]
    confidence = data["future_potentials"][0]["total_potential"]
    print(f"Most likely next: {next_symbol} (potential: {confidence})")
```

### 3. Custom Filtering

```python
# Set custom recall threshold
requests.post(
    f"http://localhost:8000/sessions/{session_id}/config",
    json={"config": {"recall_threshold": 0.7}}
)

# Get high-quality predictions
predictions = requests.get(
    f"http://localhost:8000/sessions/{session_id}/predictions"
).json()

# Only predictions with similarity >= 0.7
```

---

## Prediction Analysis

### High-Quality Predictions

```python
def is_high_quality(prediction):
    return (
        prediction["confidence"] > 0.8 and
        prediction["snr"] > 0.5 and
        prediction["fragmentation"] == 0
    )

high_quality = [p for p in predictions if is_high_quality(p)]
```

### Most Likely Future

```python
def get_most_likely_future(data):
    if not data["future_potentials"]:
        return None

    return {
        "symbol": data["future_potentials"][0]["symbol"],
        "potential": data["future_potentials"][0]["total_potential"],
        "supporting_patterns": data["future_potentials"][0]["prediction_count"]
    }
```

### Pattern Frequency Analysis

```python
def analyze_patterns(predictions):
    total_observations = sum(p["frequency"] for p in predictions)

    return {
        "total_patterns": len(predictions),
        "total_observations": total_observations,
        "avg_frequency": total_observations / len(predictions) if predictions else 0,
        "max_frequency": max((p["frequency"] for p in predictions), default=0)
    }
```

---

## Performance Considerations

### Prediction Count

- **< 100 predictions**: Fast (<10ms)
- **100-1000 predictions**: Moderate (10-50ms)
- **> 1000 predictions**: Slower (50-200ms)

**Optimization**: Set `max_predictions` to limit results

### Pattern Database Size

- **< 1000 patterns**: Fast pattern matching
- **1000-10000 patterns**: Moderate performance
- **> 10000 patterns**: Consider hybrid architecture

**See**: [../../docs/HYBRID_ARCHITECTURE.md](../../HYBRID_ARCHITECTURE.md)

### Filtering Pipeline

KATO uses multi-stage filtering for efficiency:

1. Length filter (fast)
2. Jaccard filter (moderate)
3. Bloom filter (fast)
4. MinHash/LSH (moderate)
5. Final similarity calculation (expensive)

**See**: [../../research/pattern-matching.md](../../research/pattern-matching.md)

---

## See Also

- [Observations API](observations.md) - Process observations for predictions
- [Learning API](learning.md) - Learn patterns that generate predictions
- [Prediction Object Reference](../prediction-object.md) - Complete field documentation
- [Predictive Information Theory](../../research/predictive-information.md)
- [Pattern Matching Algorithms](../../research/pattern-matching.md)

---

**Last Updated**: November 2025
**KATO Version**: 3.0+
