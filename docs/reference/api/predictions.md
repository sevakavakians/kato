# Predictions API

Retrieve predictions based on learned patterns and current short-term memory.

## Overview

Predictions represent KATO's forecasts based on pattern matching between current observations (STM) and learned patterns (LTM).

Each prediction contains:
- **Temporal segmentation**: past/present/future
- **Match analysis**: matches/missing/extras/anomalies/fuzzy_matches
- **Information metrics**: confidence, evidence, similarity, SNR, entropy, potential, good-odds, Bayesian posteriors
- **Pattern metadata**: frequency, emotives

Beside the predictions, the response carries two figures computed over the whole set of candidates:
- **`future_potentials`**: the probability of each next event
- **`chance_posterior`**: the probability that no learned pattern explains the observation better than chance

## Endpoints

### Get Predictions

Get predictions based on the session's current STM.

```http
GET /sessions/{session_id}/predictions
```

**Response** (`200 OK`):

The example is a node that has learned three patterns: `login, browse, checkout` five times, `login, browse, logout` three times and `login, reset_password, logout` twice. The session then observes `login` and `browse`. The first of the three predictions is shown; values are rounded to four decimals.

```json
{
  "predictions": [
    {
      "name": "a629167ef78bdb4dee0784c40fe2b39a4ffd207d",
      "type": "prototypical",
      "frequency": 5,
      "matches": ["login", "browse"],
      "missing": [[], []],
      "extras": [[], []],
      "anomalies": [],
      "fuzzy_matches": [],
      "past": [],
      "present": [["login"], ["browse"]],
      "future": [["checkout"]],
      "sequence": [["login"], ["browse"], ["checkout"]],
      "evidence": 0.6667,
      "confidence": 1.0,
      "similarity": 0.8,
      "snr": 1.0,
      "fragmentation": 0.0,
      "event_cohesion": 1.0,
      "onset_alignment": 1.0,
      "potential": 17.1968,
      "good_odds": 2.3439,
      "bayesian_prior": 0.5,
      "bayesian_likelihood": 3.3439,
      "bayesian_posterior": 0.5548,
      "predictive_information": 1.0627,
      "confluence": 5.0768,
      "entropy": 1.585,
      "normalized_entropy": 0.6826,
      "global_normalized_entropy": 0.3955,
      "itfdf_similarity": 1.0,
      "tfidf_score": 0.5744,
      "emotives": {},
      "weighted_similarity": null,
      "weighted_evidence": null,
      "weighted_confidence": null,
      "weighted_snr": null
    }
  ],
  "future_potentials": [
    {"next_event": ["checkout"], "probability": 0.5859, "supporting_patterns": 1},
    {"next_event": ["logout"], "probability": 0.414, "supporting_patterns": 1},
    {"next_event": ["reset_password"], "probability": 0.0001, "supporting_patterns": 1}
  ],
  "chance_posterior": 0.1093,
  "session_id": "session-abc123...",
  "count": 3
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
| `name` | string | Pattern ID (plain SHA1 hash) |
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

past: [["start"]]                                        # Before first match
present: [["hello", "world"], ["middle"], ["end"]]       # ALL events from first to last match (inclusive)
future: []                                               # Nothing after last match
```

**Important**: `present` includes ALL events from first match to last match, including intervening events that contain no matches (like `["middle"]` above).

### Match Analysis

| Field | Type | Description |
|-------|------|-------------|
| `matches` | array[string] | Symbols present in both observation and pattern |
| `missing` | array[array[string]] | Pattern symbols NOT observed, event-aligned with `present` |
| `extras` | array[array[string]] | Observed symbols NOT in pattern, event-aligned with STM |
| `anomalies` | array[string] | Every deviating symbol in one flat list: missing, then extras, then fuzzy-observed tokens |
| `fuzzy_matches` | array[object] | Fuzzy token matches with similarity scores (when fuzzy matching enabled) |

**Example**:

```python
Pattern present: [["a", "b"], ["c", "d"]]
STM: [["a", "c", "x"]]

matches: ["a", "c"]           # In both
missing: [["b"], ["d"]]       # Per-present-event: symbols in pattern not observed
extras: [["x"]]               # Per-STM-event: symbols in STM not in pattern
anomalies: ["b", "d", "x"]    # Missing, then extras, in one flat list
fuzzy_matches: []             # No fuzzy matches (exact matching only)
```

**Fuzzy Matches Field**:

When fuzzy token matching is enabled (`fuzzy_token_threshold` > 0.0), the `fuzzy_matches` array documents non-exact matches:

```json
{
  "fuzzy_matches": [
    {
      "observed": "bannana",
      "expected": "banana",
      "similarity": 0.93
    },
    {
      "observed": "chery",
      "expected": "cherry",
      "similarity": 0.91
    }
  ]
}
```

**Key Points**:
- Empty array `[]` when fuzzy matching disabled (default)
- Empty array `[]` when all matches are exact
- Fuzzy-matched tokens appear in `matches`, not in `missing` or `extras`; their `observed` token is also listed in `anomalies`
- Only non-exact matches generate entries
- Similarity scores range from 0.0 (no match) to 1.0 (exact match)

**See**: [Configuration API](configuration.md#fuzzy-matching-mode) for fuzzy matching setup

### Information Metrics

| Field | Range | Description |
|-------|-------|-------------|
| `confidence` | 0.0-1.0 | Ratio of matches to total present symbols |
| `evidence` | 0.0-1.0 | Proportion of pattern observed |
| `similarity` | 0.0-1.0 | Base similarity score (unweighted) |
| `snr` | -1.0-1.0 | Signal-to-noise ratio (matches vs extras) |
| `fragmentation` | 0.0-n | Degree of match discontinuity |
| `event_cohesion` | 0.0-1.0 | How much of each observed event sits together in one pattern event |
| `onset_alignment` | 0.0-1.0 | How early in the pattern the observed symbols occur |
| `entropy` | 0.0-n | Shannon entropy of the pattern's symbols |
| `normalized_entropy` | 0.0-1.0 | The pattern's entropy over the largest entropy the node's vocabulary allows |
| `global_normalized_entropy` | 0.0-n | Entropy using global symbol probability distributions |
| `confluence` | bits, unbounded | How far the pattern is from a chance co-occurrence of its symbols |
| `itfdf_similarity` | 0.0-1.0 | One minus the distance between the STM and `present`, the distance scaled by the pattern's share of the candidates' frequency |
| `tfidf_score` | 0.0-~2.0 | TF-IDF measure of pattern distinctiveness |
| `potential` | unbounded | Weighted sum of eleven match terms (default sort) |
| `good_odds` | bits, unbounded | Posterior log-odds of the pattern against chance; above 0 beats chance |
| `bayesian_prior` | 0.0-1.0 | The pattern's share of every learn in the node |
| `bayesian_likelihood` | bits, unbounded | Weight of evidence the observation gives for the pattern over chance |
| `bayesian_posterior` | 0.0-1.0 | P(pattern\|observation); with `chance_posterior`, sums to 1.0 over every candidate |
| `predictive_information` | bits, unbounded | The prediction's part of what the STM tells about the next event |
| `weighted_similarity` | 0.0-1.0 or null | Affinity-weighted similarity (null when `affinity_emotive` not set) |
| `weighted_evidence` | 0.0-1.0 or null | Affinity-weighted evidence |
| `weighted_confidence` | 0.0-1.0 or null | Affinity-weighted confidence |
| `weighted_snr` | 0.0-1.0 or null | Affinity-weighted signal-to-noise ratio |

**Formulas**:

```python
confidence = len(matches) / total_present_length
evidence = len(matches) / pattern_length
snr = (2 * len(matches) - len(extras)) / (2 * len(matches) + len(extras))

# q(s): the symbol's share of all learned symbol occurrences in the node
# F:    the node's total of pattern frequencies (every learn counts once)
# e:    0.05
bayesian_prior      = frequency / F
bayesian_likelihood = sum(log2((1 - e) / q(s)) for s in matches) - log2(1 / e) * (n_missing + n_extras)
good_odds           = log2(bayesian_prior) + bayesian_likelihood
bayesian_posterior  = 2**good_odds / (1 + sum(2**good_odds over every candidate))
confluence          = log2(frequency / F) + sum(log2(1 / q(s)) for s in pattern)

# potential: eleven terms, each times a fixed weight
potential = (6.038 * cosine_idf(stm, present)
             + 2.755 * last_event_matched
             + 2.205 * len(matches) / n_symbols(past + present)
             + 1.790 * recency(0.7) + 0.063 * recency(0.9)
             + 0.948 * len(matches) / (len(matches) + 2 * n_missing + 2 * n_extras)
             - 0.770 * fragmentation + 0.387 / (fragmentation + 1)
             + 0.680 * ln(frequency)
             + 0.584 * snr
             + 0.022 * last_event_share)
```

Every term and the full-precision weights are in the [Prediction Object Reference](../prediction-object.md#25-potential-float).

**Weighted formulas** (when `affinity_emotive` is set):

```python
# w(t) = |affinity(t, emotive)| / frequency(t) + epsilon
weighted_similarity = 2 * sum(w(t) for t in matches) / (sum(w(t) for t in state) + sum(w(t) for t in pattern))
weighted_evidence   = sum(w(t) for t in matches) / sum(w(t) for t in pattern)
weighted_confidence = sum(w(t) for t in matches) / sum(w(t) for t in present)
weighted_snr        = sum(w(t) for t in matches) / (sum(w(t) for t in matches) + sum(w(t) for t in extras))
```

**See**: [Prediction Object Reference](../prediction-object.md) for every field, and its [Metrics at a Glance](../prediction-object.md#metrics-at-a-glance) table for what each metric is for.

---

## Future Potentials

The probability of each next event the candidates propose. Patterns that predict
the same next event pool their support into one entry, even when they differ
after it.

```json
{
  "future_potentials": [
    {"next_event": ["checkout"], "probability": 0.5859, "supporting_patterns": 1},
    {"next_event": ["logout"], "probability": 0.414, "supporting_patterns": 1},
    {"next_event": ["reset_password"], "probability": 0.0001, "supporting_patterns": 1}
  ]
}
```

| Field | Meaning |
|-------|---------|
| `next_event` | The event, as the patterns store it: a list of symbols. |
| `probability` | The probability that this event comes next. The entries sum to 1. |
| `supporting_patterns` | Number of candidates whose next event this is. |

**Use Cases**:
- Next-event prediction
- Pooling evidence from several patterns that predict the same thing
- A confidence value for the next event

**Calculation**:

1. Take every candidate above the recall threshold. The list includes patterns
   that `max_predictions` leaves out of the returned predictions.
2. Skip candidates with an empty `future`: a pattern that ends where the
   observation ends proposes nothing.
3. Give each remaining candidate the weight `e^potential`.
4. Group the candidates by the first event of their `future`, summing the weights
   of each group.
5. Divide each group's sum by the total over all groups to get `probability`.
6. Sort by `probability`, descending. Equal values go to the event that sorts
   first, so the order is the same on every request.

Each response's `future_potentials` is computed from that request's own
candidates. An empty STM, an STM that matches nothing, or a set of candidates
with no future among them returns an empty list.

The probabilities are shares among the next events the candidates propose.
They do not say how well those candidates explain the STM, so two cases need a
second look:

- A lone candidate with a future gets a probability of 1.0, however weak its
  match. Whether to believe the candidates at all is what `chance_posterior`
  says.
- When the pattern that best explains the STM ends where the STM ends, it
  proposes nothing, and the entries come from the remaining candidates. The
  `good_odds` of the predictions that propose an event says how well they
  explain the STM: below 0, worse than chance.

---

## Chance Posterior

`chance_posterior` is the probability that no learned pattern explains the
observation better than chance: `1 / (1 + sum of 2^good_odds over every
candidate)`. With the `bayesian_posterior` of every candidate it sums to 1.

| Value | Reading |
|-------|---------|
| near 0 | Some learned pattern explains the observation far better than chance. |
| near 1 | Predictions were returned, and none of them should be trusted. |
| `1.0` | Nothing matched: `predictions` is empty. |
| `null` | No prediction was computed: the STM is empty. |

```python
data = requests.get(f"http://localhost:8000/sessions/{session_id}/predictions").json()

if not data["predictions"] or data["chance_posterior"] > 0.5:
    answer = None                      # "I don't know"
else:
    answer = data["future_potentials"][0]["next_event"] if data["future_potentials"] else None
```

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
- Every candidate above the recall threshold is scored first
- The candidates are sorted by the session's `rank_sort_algo` (`potential` by default), descending
- Top N predictions returned
- `future_potentials`, `chance_posterior` and each returned prediction's metrics are computed over every candidate, so they do not change with N; see [Future Potentials](#future-potentials)

---

## Empty STM Behavior

If STM is empty, predictions will be empty:

```json
{
  "predictions": [],
  "future_potentials": [],
  "chance_posterior": null,
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

# Get the most likely next event
if data["future_potentials"]:
    best = data["future_potentials"][0]
    print(f"Most likely next: {best['next_event']} (probability: {best['probability']:.2f})")
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

    best = data["future_potentials"][0]
    return {
        "next_event": best["next_event"],
        "probability": best["probability"],
        "supporting_patterns": best["supporting_patterns"]
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

### Candidate Count

The cost of a request grows with the number of candidates above the recall
threshold: each one is matched against the STM and scored. `max_predictions`
limits how many are returned and how many get the pattern metrics (the entropy
family, `tfidf_score`, `itfdf_similarity`, `confluence`) and their emotives; it
does not limit how many are scored.

**Optimization**: Raise `recall_threshold`, or configure a `filter_pipeline`, to
cut the candidates. Set `max_predictions` to limit the size of the response.

### Pattern Database Size

- **< 1000 patterns**: Fast pattern matching
- **1000-10000 patterns**: Moderate performance
- **> 10000 patterns**: Consider hybrid architecture

**See**: [Hybrid Architecture](../../developers/hybrid-architecture.md)

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
