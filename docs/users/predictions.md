# Predictions Guide

Complete guide to understanding and working with KATO predictions.

## What are Predictions?

**Predictions** are KATO's way of completing patterns based on partial input. Given current observations in STM, KATO finds matching patterns from LTM and returns structured information about what came before, what matches now, and what's expected next.

### Prediction Structure

```json
{
  "predictions": [
    {
      "past": [["event1"], ["event2"]],
      "present": [["current_event"]],
      "future": [["next_event"], ["final_event"]],
      "missing": [["expected_but_not_seen"]],
      "extras": [["seen_but_not_expected"]],
      "pattern_name": "PTN|a1b2c3d4e5f6",
      "similarity": 0.85,
      "metrics": {
        "potential": 0.72,
        "evidence": 0.90,
        "confidence": 0.88,
        "snr": 1.45
      },
      "emotive_predictions": {
        "joy": {"mean": 0.7, "std": 0.15, "min": 0.5, "max": 0.9},
        "energy": {"mean": 0.6, "std": 0.20, "min": 0.3, "max": 0.8}
      }
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

**Information-theoretic value of the prediction.**

**Higher = More useful** for reducing uncertainty about future.

**Calculation**: Based on entropy, evidence, and future information.

**Use Cases**:
- **Ranking**: Default sort order
- **Filtering**: Keep only high-value predictions
- **Prioritization**: Focus on most informative patterns

```python
predictions = kato.get_predictions()

# Sorted by potential (highest first)
# predictions[0]['metrics']['potential']: 0.95  ← Most informative
# predictions[1]['metrics']['potential']: 0.72
# predictions[2]['metrics']['potential']: 0.45
```

### evidence

**Amount of training data supporting the prediction.**

**Higher = More observations** of this pattern.

```python
# Pattern learned 100 times:
# evidence: 0.99 (high confidence)

# Pattern learned 2 times:
# evidence: 0.20 (low confidence)
```

**Use Cases**:
- **Reliability**: Prefer well-established patterns
- **Cold-start detection**: Identify undertrained patterns
- **A/B testing**: Track pattern observation counts

### confidence

**Bayesian confidence in the prediction.**

**Combined measure** of similarity, evidence, and pattern quality.

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

# Prediction:
"emotive_predictions": {
  "joy": {
    "mean": 0.70,
    "std": 0.14,
    "min": 0.5,
    "max": 0.9,
    "count": 5
  }
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
    print(f"Pattern: {top['pattern_name']}")
    print(f"Confidence: {top['metrics']['confidence']}")
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
        if p['metrics']['confidence'] >= min_confidence
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
confidence = top['metrics']['confidence']

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
        pattern = fetch_pattern_metadata(pred['pattern_name'])
        updated_at = pattern['updated_at'].timestamp()

        # Decay factor (newer = higher weight)
        age_days = (now - updated_at) / 86400
        decay = math.exp(-age_days / 30)  # 30-day half-life

        # Adjust confidence
        pred['metrics']['confidence'] *= decay

    # Re-sort by adjusted confidence
    return sorted(
        predictions['predictions'],
        key=lambda p: p['metrics']['confidence'],
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
