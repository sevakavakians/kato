# Predictions Guide

Complete guide to understanding and working with KATO predictions.

## What are Predictions?

**Predictions** are KATO's way of completing patterns based on partial input. Given current observations in STM, KATO finds matching patterns from LTM and returns structured information about what came before, what matches now, and what's expected next.

### Prediction Structure

```json
{
  "predictions": [
    {
      "name": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
      "type": "prototypical",
      "frequency": 5,
      "past": [["event1"], ["event2"]],
      "present": [["current_event"]],
      "future": [["next_event"], ["final_event"]],
      "matches": ["current_event"],
      "missing": [[]],
      "extras": [[]],
      "anomalies": [],
      "similarity": 0.85,
      "confidence": 0.88,
      "evidence": 0.90,
      "snr": 0.75,
      "potential": 2.45,
      "fragmentation": 0.0,
      "emotives": {"joy": 0.7, "energy": 0.6}
    }
  ],
  "count": 1
}
```

## Prediction Components

### past

**Events that came before the first match in the pattern.**

```python
# Learned pattern: A → B → C → D

# STM: [C]
# past: [A, B]  ← What happened before C in the pattern
# present: [C]
# future: [D]
```

**Use Cases**:
- **Context reconstruction**: "How did we get here?"
- **Root cause analysis**: "What led to this error?"
- **Conversation history**: "What was discussed before?"

**Example**:
```python
# Pattern: greet → introduce → discuss → conclude

kato.clear_stm()
kato.observe(["discuss", "topic_AI"])
predictions = kato.get_predictions()

# predictions[0]['past']:
# [["greet", "hello"], ["introduce", "name"]]
# Shows what typically comes before discussion
```

### present

**Complete events from the pattern that match current STM.**

**Important**: Returns **complete events**, not just matched symbols.

```python
# Pattern event: ["coffee", "morning", "routine"]
# STM: [["coffee"]]  ← Partial match

# present: [["coffee", "morning", "routine"]]  ← Complete event
# missing: [["morning", "routine"]]  ← Expected but not in STM
```

**Use Cases**:
- **Completion suggestions**: "You said X, pattern includes X+Y+Z"
- **Context expansion**: "Based on X, you probably mean X+Y"
- **Disambiguation**: "X could mean X+A or X+B (two patterns)"

**Example**:
```python
# Pattern: [["login", "user:alice", "device:mobile"]]

kato.observe(["login", "user:alice"])
predictions = kato.get_predictions()

# predictions[0]['present']:
# [["login", "user:alice", "device:mobile"]]
# ↑ Complete event including "device:mobile"

# predictions[0]['missing']:
# [["device:mobile"]]
# ↑ Expected but not observed
```

### future

**Events expected after the last match in the pattern.**

```python
# Pattern: A → B → C → D

# STM: [A]
# past: []
# present: [A]
# future: [B, C, D]  ← What comes next
```

**Use Cases**:
- **Next-step prediction**: "What should happen next?"
- **Autocomplete**: "You started X, next is probably Y"
- **Proactive suggestions**: "After X, users typically do Y"
- **Anomaly detection**: "X happened but Y didn't (expected)"

**Example**:
```python
# Pattern: checkout → payment → confirmation → email

kato.clear_stm()
kato.observe(["checkout", "cart"])
predictions = kato.get_predictions()

# predictions[0]['future']:
# [
#   ["payment", "process"],
#   ["confirmation", "order_id"],
#   ["email", "receipt"]
# ]
# Predicts remaining 3 steps
```

### missing

**Expected symbols not observed in current STM.**

**Alignment**: Parallel to `present` - same number of events.

```python
# Pattern: [["A", "B", "C"], ["D", "E"]]
# STM:     [["A"],           ["D"]]

# present: [["A", "B", "C"], ["D", "E"]]
# missing: [["B", "C"],      ["E"]]
#           ↑                 ↑
#       Event 1           Event 2
```

**Use Cases**:
- **Completion**: "You're missing B and C"
- **Validation**: "Expected X but didn't see it"
- **Error detection**: "Pattern requires Y, not present"

**Example**:
```python
# Pattern: [["error:timeout", "service:api", "severity:high"]]

kato.observe(["error:timeout"])
predictions = kato.get_predictions()

# predictions[0]['missing']:
# [["service:api", "severity:high"]]
# Shows what additional context is expected
```

### extras

**Observed symbols not expected in the pattern.**

**Alignment**: Parallel to STM - same number of events.

```python
# Pattern: [["A"], ["B"]]
# STM:     [["A", "X"], ["B", "Y", "Z"]]

# present: [["A"], ["B"]]
# extras:  [["X"], ["Y", "Z"]]
#          ↑       ↑
#       Event 1  Event 2
```

**Use Cases**:
- **Novelty detection**: "X is new/unexpected"
- **Anomaly alerts**: "Y wasn't in training data"
- **Pattern drift**: "Behavior changing from baseline"

**Example**:
```python
# Learned pattern: [["login", "success"]]

kato.observe(["login", "success", "2fa_required"])
predictions = kato.get_predictions()

# predictions[0]['extras']:
# [["2fa_required"]]
# Flags new behavior not in original pattern
```

### anomalies

**Fuzzy token matches with similarity scores** (when fuzzy matching is enabled).

**Structure**: Array of objects documenting non-exact matches.

```json
{
  "anomalies": [
    {
      "observed": "bannana",
      "expected": "banana",
      "similarity": 0.93
    }
  ]
}
```

**When Present**:
- Empty array `[]` when fuzzy matching is disabled (`fuzzy_token_threshold=0.0`)
- Empty array `[]` when all matches are exact
- Contains entries for tokens that were fuzzy-matched (not exact)

**Use Cases**:
- **Data quality monitoring**: Detect typos in user input
- **OCR error detection**: Identify recognition mistakes
- **Spelling correction**: Flag misspelled terms
- **Anomaly tracking**: Monitor data consistency issues

**Example - Typo Detection**:
```python
# Enable fuzzy matching
kato.update_config({'fuzzy_token_threshold': 0.85})

# Learn correct spelling
kato.observe(['apple', 'banana', 'cherry'])
kato.learn()

# User enters with typos
kato.clear_stm()
kato.observe(['apple', 'bannana', 'chery'])
predictions = kato.get_predictions()

# predictions[0]:
{
  "matches": ["apple", "bannana", "chery"],  # All matched (exact + fuzzy)
  "missing": [],  # Nothing missing (fuzzy matches count)
  "extras": [],   # Nothing extra
  "anomalies": [
    {"observed": "bannana", "expected": "banana", "similarity": 0.93},
    {"observed": "chery", "expected": "cherry", "similarity": 0.91}
  ]
}
# ↑ Anomalies highlight the fuzzy matches for review
```

**Example - Data Quality Alert**:
```python
# Check for data quality issues
predictions = kato.get_predictions()
for pred in predictions:
    if pred['anomalies']:
        print(f"⚠️ Data quality alert!")
        for anomaly in pred['anomalies']:
            print(f"  Found '{anomaly['observed']}' "
                  f"(expected '{anomaly['expected']}', "
                  f"similarity: {anomaly['similarity']:.2f})")
```

**Configuration**:
```python
# Enable fuzzy matching and anomaly tracking
kato.update_config({
    'fuzzy_token_threshold': 0.85,  # 0.0 = disabled, 0.85 = recommended
    'recall_threshold': 0.3          # Pattern matching threshold
})
```

**Key Points**:
- Fuzzy-matched tokens appear in `matches` (treated as valid matches)
- Only non-exact matches generate anomaly entries (exact matches don't)
- Tokens below fuzzy threshold appear in `missing`/`extras` (not fuzzy-matched)
- The `similarity` score shows how similar observed vs expected (0.0-1.0)
- Higher threshold = stricter matching (fewer fuzzy matches)

**Recommended Thresholds**:
- **0.80**: Moderate (handles 1-2 character typos)
- **0.85**: Balanced (recommended default)
- **0.90**: Conservative (single character variations)
- **0.95**: Strict (capitalization/punctuation only)

## Prediction Metrics

### similarity

**How well STM matches the pattern** (0.0 - 1.0).

**Calculation**: Fuzzy string matching or token overlap.

**Values**:
- **1.0**: Perfect match (all symbols match)
- **0.7-0.9**: Strong match (most symbols match)
- **0.3-0.7**: Partial match (some symbols match)
- **< 0.3**: Weak match (few symbols match)

**Threshold**: Patterns below `recall_threshold` are filtered out.

```python
# recall_threshold = 0.3

# Pattern: ["coffee", "morning"]
# STM:     ["coffee", "morning"]  → similarity = 1.0 ✓
# STM:     ["coffee"]             → similarity = 0.5 ✓
# STM:     ["tea"]                → similarity = 0.0 ✗ (filtered)
```

### potential

**Composite ranking metric combining match quality, signal strength, frequency-weighted similarity, and pattern cohesion.**

**Higher = More useful** for reducing uncertainty about future.

**Formula**: `(evidence + confidence) * snr + itfdf_similarity + (1/(fragmentation + 1))`

**Range**: Unbounded (typically 0.0 to ~3.0, can be negative with poor SNR).

**Use Cases**:
- **Ranking**: Default sort order
- **Filtering**: Keep only high-value predictions
- **Prioritization**: Focus on most informative patterns

```python
predictions = kato.get_predictions()

# Sorted by potential (highest first)
# predictions[0]['potential']: 2.95  ← Most informative
# predictions[1]['potential']: 1.72
# predictions[2]['potential']: 0.45
```

### evidence

**Proportion of the total pattern that has been observed.**

**Formula**: `len(matches) / pattern_length`

**Range**: 0.0 to 1.0

```python
# Pattern has 5 symbols, 4 matched:
# evidence: 0.80 (most of pattern observed)

# Pattern has 10 symbols, 2 matched:
# evidence: 0.20 (small portion observed)
```

**Use Cases**:
- **Match completeness**: How much of the pattern is confirmed
- **Partial match detection**: Low evidence = only a fragment matched
- **Filtering**: Require minimum evidence for actions

### confidence

**Ratio of matched symbols to total symbols in the present events.**

**Formula**: `len(matches) / total_present_length`

**Values**:
- **0.9+**: Very confident
- **0.7-0.9**: Confident
- **0.5-0.7**: Moderate
- **< 0.5**: Low confidence

**Use Cases**:
- **Decision thresholds**: Only act on high-confidence predictions
- **User feedback**: "I'm 85% confident the next step is X"
- **Filtering**: Remove low-confidence noise

### snr (Signal-to-Noise Ratio)

**Ratio of signal (pattern strength) to noise (variability).**

**Higher = More reliable** pattern with less variance.

**Use Cases**:
- **Pattern quality**: Identify consistent vs noisy patterns
- **Anomaly detection**: Low SNR indicates unusual behavior

## Emotive Predictions

### Statistics from Rolling Windows

KATO aggregates emotives across all observations of a pattern.

```python
# Pattern learned 5 times with emotives:
# Observation 1: joy=0.8
# Observation 2: joy=0.6
# Observation 3: joy=0.9
# Observation 4: joy=0.7
# Observation 5: joy=0.5

# Prediction emotives (averaged from rolling window):
"emotives": {
  "joy": 0.70
}
```

**Use Cases**:
- **Mood prediction**: "This conversation typically has joy=0.7±0.14"
- **Emotional context**: "Users are usually frustrated at this step"
- **Personalization**: "Alice's energy is typically higher in mornings"

## Ranking and Filtering

### Default Ranking

Predictions sorted by `rank_sort_algo` (default: `potential`).

```bash
# Configure ranking metric
curl -X POST http://localhost:8000/sessions \
  -d '{
    "node_id": "my_app",
    "config": {"rank_sort_algo": "potential"}
  }'
```

**Options**:
- `potential`: Information value (default)
- `similarity`: Match quality
- `evidence`: Observation count
- `confidence`: Bayesian confidence
- `snr`: Signal-to-noise ratio

### Max Predictions

Limit number of results.

```bash
# Return top 10 predictions only
curl -X POST http://localhost:8000/sessions \
  -d '{
    "node_id": "my_app",
    "config": {"max_predictions": 10}
  }'
```

### Threshold Filtering

Only return predictions above similarity threshold.

```bash
# Require 50% similarity minimum
curl -X POST http://localhost:8000/sessions \
  -d '{
    "node_id": "my_app",
    "config": {"recall_threshold": 0.5}
  }'
```

## Prediction Patterns

### Pattern 1: Next-Step Prediction

**Use Case**: "What should I do next?"

```python
# Learn workflow
kato.observe(["step1_prepare"])
kato.observe(["step2_process"])
kato.observe(["step3_finalize"])
kato.learn()

# At step1, predict next steps
kato.clear_stm()
kato.observe(["step1_prepare"])
predictions = kato.get_predictions()

# future: [["step2_process"], ["step3_finalize"]]
next_step = predictions[0]['future'][0]
print(f"Next: {next_step}")  # step2_process
```

### Pattern 2: Context Reconstruction

**Use Case**: "How did I get here?"

```python
# Learn error sequence
kato.observe(["high_load"])
kato.observe(["slow_response"])
kato.observe(["timeout_error"])
kato.learn()

# See timeout, reconstruct context
kato.clear_stm()
kato.observe(["timeout_error"])
predictions = kato.get_predictions()

# past: [["high_load"], ["slow_response"]]
root_cause = predictions[0]['past']
print(f"Root cause chain: {root_cause}")
```

### Pattern 3: Completion Suggestions

**Use Case**: "You started X, did you mean X+Y+Z?"

```python
# Learn full command
kato.observe(["git", "commit", "message:feat", "push"])
kato.learn()

# User types partial
kato.clear_stm()
kato.observe(["git", "commit"])
predictions = kato.get_predictions()

# present: [["git", "commit", "message:feat", "push"]]
# missing: [["message:feat", "push"]]
completion = predictions[0]['missing'][0]
print(f"Suggest adding: {completion}")
```

### Pattern 4: Anomaly Detection

**Use Case**: "X is unusual/unexpected"

```python
# Learn normal pattern
kato.observe(["login", "success"])
kato.learn()

# Observe anomaly
kato.observe(["login", "success", "unusual_location"])
predictions = kato.get_predictions()

# extras: [["unusual_location"]]
anomaly = predictions[0]['extras'][0]
if anomaly:
    print(f"Alert: Unexpected behavior {anomaly}")
```

### Pattern 5: Multi-Step Planning

**Use Case**: "Show me the full path"

```python
# Learn recipe
kato.observe(["prep_ingredients"])
kato.observe(["heat_pan"])
kato.observe(["cook"])
kato.observe(["plate"])
kato.observe(["serve"])
kato.learn()

# At any step, see full plan
kato.clear_stm()
kato.observe(["heat_pan"])
predictions = kato.get_predictions()

# past: [["prep_ingredients"]]
# present: [["heat_pan"]]
# future: [["cook"], ["plate"], ["serve"]]

full_plan = (
    predictions[0]['past'] +
    predictions[0]['present'] +
    predictions[0]['future']
)
```

## Working with Predictions

### Extract Top Prediction

```python
def get_top_prediction(predictions):
    """Get highest-ranked prediction."""
    preds = predictions.get('predictions', [])
    return preds[0] if preds else None

top = get_top_prediction(predictions)
if top:
    print(f"Pattern: {top['name']}")
    print(f"Confidence: {top['confidence']}")
```

### Get Next Event

```python
def get_next_event(prediction):
    """Get immediate next event."""
    future = prediction.get('future', [])
    return future[0] if future else None

next_event = get_next_event(top)
if next_event:
    print(f"Next step: {next_event}")
```

### Check for Anomalies

```python
def has_anomalies(prediction):
    """Check if extras exist."""
    extras = prediction.get('extras', [])
    return any(event for event in extras)

if has_anomalies(top):
    print(f"Warning: Unexpected symbols {top['extras']}")
```

### Filter by Confidence

```python
def get_confident_predictions(predictions, min_confidence=0.7):
    """Return only high-confidence predictions."""
    return [
        p for p in predictions['predictions']
        if p['confidence'] >= min_confidence
    ]

confident = get_confident_predictions(predictions, 0.8)
print(f"Found {len(confident)} high-confidence predictions")
```

## Advanced Topics

### Combining Multiple Predictions

```python
# Multiple patterns may match - aggregate them
predictions = kato.get_predictions()

all_next_steps = set()
for pred in predictions['predictions']:
    next_event = pred['future'][0] if pred['future'] else []
    all_next_steps.update(next_event)

print(f"Possible next steps: {all_next_steps}")
```

### Prediction Confidence Thresholds

```python
# Different actions based on confidence
top = predictions['predictions'][0]
confidence = top['confidence']

if confidence > 0.9:
    # Auto-execute
    execute(top['future'][0])
elif confidence > 0.7:
    # Suggest to user
    suggest(top['future'][0])
else:
    # Ignore low-confidence
    pass
```

### Time-Decay Weighting

```python
# Weight recent patterns higher (application-level)
import time

def get_weighted_predictions(predictions):
    """Weight by pattern recency."""
    now = time.time()

    for pred in predictions['predictions']:
        # Fetch pattern metadata from storage
        pattern = fetch_pattern_metadata(pred['name'])
        updated_at = pattern['updated_at'].timestamp()

        # Decay factor (newer = higher weight)
        age_days = (now - updated_at) / 86400
        decay = math.exp(-age_days / 30)  # 30-day half-life

        # Adjust confidence
        pred['confidence'] *= decay

    # Re-sort by adjusted confidence
    return sorted(
        predictions['predictions'],
        key=lambda p: p['confidence'],
        reverse=True
    )
```

## Best Practices

1. **Check prediction count** before accessing
2. **Use confidence thresholds** for automated actions
3. **Handle missing predictions** gracefully
4. **Log prediction quality** for monitoring
5. **Combine multiple predictions** for robustness
6. **Validate future events** before execution
7. **Track prediction accuracy** over time
8. **Adjust recall_threshold** based on precision/recall needs

## Related Documentation

- [First Session Tutorial](first-session.md)
- [Pattern Learning](pattern-learning.md)
- [Configuration Guide](configuration.md)
- [Python Client](python-client.md)

---

**Last Updated**: November 2025
**KATO Version**: 3.0+
