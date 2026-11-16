# Predictions Guide

Complete guide to understanding and working with KATO predictions.

## What are Predictions?

**Predictions** are KATO's way of completing patterns based on partial input. Given current observations in STM, KATO finds matching patterns from LTM and returns structured information about what came before, what matches now, and what's expected next.

### Prediction Structure

The example is a node that has learned three patterns: `login, browse, checkout` five times, `login, browse, logout` three times and `login, reset_password, logout` twice. The session then observes `browse`. The first of the two predictions is shown; values are rounded to four decimals.

```json
{
  "predictions": [
    {
      "name": "a629167ef78bdb4dee0784c40fe2b39a4ffd207d",
      "type": "prototypical",
      "frequency": 5,
      "past": [["login"]],
      "present": [["browse"]],
      "future": [["checkout"]],
      "sequence": [["login"], ["browse"], ["checkout"]],
      "matches": ["browse"],
      "missing": [[]],
      "extras": [[]],
      "anomalies": [],
      "fuzzy_matches": [],
      "similarity": 0.5,
      "confidence": 1.0,
      "evidence": 0.3333,
      "snr": 1.0,
      "fragmentation": 0.0,
      "event_cohesion": 1.0,
      "onset_alignment": 0.5,
      "entropy": 1.585,
      "normalized_entropy": 0.6826,
      "global_normalized_entropy": 0.3955,
      "itfdf_similarity": 1.0,
      "tfidf_score": 0.5744,
      "confluence": 5.0768,
      "predictive_information": 1.0628,
      "bayesian_posterior": 0.4627,
      "bayesian_prior": 0.5,
      "bayesian_likelihood": 1.8329,
      "good_odds": 0.8329,
      "potential": 14.7846,
      "weighted_similarity": null,
      "weighted_evidence": null,
      "weighted_confidence": null,
      "weighted_snr": null,
      "emotives": {}
    }
  ],
  "future_potentials": [
    {"next_event": ["checkout"], "probability": 0.586, "supporting_patterns": 1},
    {"next_event": ["logout"], "probability": 0.414, "supporting_patterns": 1}
  ],
  "ends_here": 0.0,
  "chance_posterior": 0.2597,
  "count": 2
}
```

`future_potentials`, `ends_here` and `chance_posterior` describe the whole set of candidates, not one prediction: the probability of each next event, the probability that no event follows, and the probability that no learned pattern explains the observation better than chance. See [What Comes Next](#what-comes-next).

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

**Every symbol that deviates from the pattern**, as one flat list.

**Structure**: Missing symbols (in pattern order), then extras (in observation
order), then the observed token of each fuzzy match. Repeated symbols are
counted per occurrence.

```python
# Learned "hello world" one character per event, observed "o wxld"
# predictions[0]:
{
  "missing": [[], [], [], ["o"], ["r"], [], []],
  "extras":  [[], [], [], ["x"], [], []],
  "anomalies": ["o", "r", "x"]
}
```

**When Present**:
- Empty array `[]` when the observation matches the pattern exactly
- Non-empty whenever `missing`, `extras`, or `fuzzy_matches` has content

### fuzzy_matches

**Fuzzy token matches with similarity scores** (when fuzzy matching is enabled).

**Structure**: Array of objects documenting non-exact matches.

```json
{
  "fuzzy_matches": [
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
  "fuzzy_matches": [
    {"observed": "bannana", "expected": "banana", "similarity": 0.93},
    {"observed": "chery", "expected": "cherry", "similarity": 0.91}
  ],
  "anomalies": ["bannana", "chery"]  # Observed tokens surface here too
}
# ↑ fuzzy_matches highlight the fuzzy matches for review
```

**Example - Data Quality Alert**:
```python
# Check for data quality issues
predictions = kato.get_predictions()
for pred in predictions:
    if pred['fuzzy_matches']:
        print(f"⚠️ Data quality alert!")
        for fuzzy_match in pred['fuzzy_matches']:
            print(f"  Found '{fuzzy_match['observed']}' "
                  f"(expected '{fuzzy_match['expected']}', "
                  f"similarity: {fuzzy_match['similarity']:.2f})")
```

**Configuration**:
```python
# Enable fuzzy matching and fuzzy_matches tracking
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

**The default ranking score: a weighted sum of eleven terms that describe the match.**

**Higher = more likely to be the pattern that continues the observation.**

**Formula**: `potential = Σ weight * term`, with fixed weights:

| Term | Weight |
|---|---|
| Cosine between the STM and `present`, rare symbols counting more | +6.038 |
| The newest STM event has a matched symbol (1 or 0) | +2.755 |
| `matches / symbols of past and present` | +2.205 |
| Matched STM symbols, each counted `0.7^n` for an event `n` back from the newest | +1.790 |
| `matches / (matches + 2 * missing + 2 * extras)` | +0.948 |
| `fragmentation` | -0.770 |
| Natural logarithm of `frequency` | +0.680 |
| `snr` | +0.584 |
| `1 / (fragmentation + 1)` | +0.387 |
| The recency count again, with `0.9^n` | +0.063 |
| Matched share of the newest STM event | +0.022 |

**Range**: Unbounded. In the example above the two predictions score 14.78 and 14.44; they match alike and differ only in how often each pattern was learned.

**What it does not depend on**: the other candidates, their order, and `max_predictions`. A long pattern is not penalised for the future it has yet to predict.

**Use Cases**:
- **Ranking**: Default sort order
- **Next-event probabilities**: `future_potentials` weights each candidate by `e^potential`
- **Comparing two matches of one observation**: a difference of 1.0 is a factor of `e` in weight

```python
predictions = kato.get_predictions()

# Sorted by potential (highest first)
# predictions[0]['potential']: 14.78  ← login, browse, checkout (learned 5 times)
# predictions[1]['potential']: 14.44  ← login, browse, logout (learned 3 times)
```

Full definition of each term: [Prediction Object Reference](../reference/prediction-object.md#25-potential-float).

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

### fragmentation

**Number of discontinuous match blocks minus 1.**

**Range**: 0 to n (0 = perfectly cohesive match)

```python
# Pattern: A B C D E
# STM:     A B C D E  → fragmentation = 0 (one contiguous block)
# STM:     A C E      → fragmentation = 2 (three separate blocks)
```

**Use Cases**:
- **Match quality**: Lower fragmentation = more cohesive match
- **Filtering**: Prefer contiguous matches over scattered ones

### Information-Theoretic Metrics

#### entropy

**Shannon entropy of the pattern's symbols.**

**Formula**: `entropy = Σ(-p(symbol) * log2(p(symbol)))`

**Range**: 0.0 to log2(n) where n is vocabulary size

**Use Cases**:
- **Complexity assessment**: Higher entropy = more diverse symbols
- **Pattern characterization**: Distinguish simple vs complex patterns

#### normalized_entropy

**Entropy normalized to local symbol distribution within the pattern.**

**Range**: 0.0 to 1.0 (theoretical maximum depends on symbol distribution)

**Use Cases**:
- **Cross-pattern comparison**: Comparable entropy across patterns of different sizes
- **Information density**: How much information per symbol

#### global_normalized_entropy

**Entropy using global symbol probabilities across the entire knowledge base.**

**Range**: 0.0 to theoretical maximum

**Use Cases**:
- **Rarity assessment**: Patterns with rare symbols score differently than common ones
- **Cross-domain comparison**: Context-aware entropy relative to the full corpus

#### predictive_information

**This prediction's part of the information the STM carries about the next event, in bits.**

**Formula**: `share * log2(P(E | STM) / q(E))`, where `E` is the prediction's next event, `P(E | STM)` its probability in `future_potentials`, `share` the prediction's own part of that probability, and `q(E)` the probability of the event by chance.

**Range**: Unbounded, in bits. 0.0 for a prediction with no `future`; negative when the event is less probable than chance.

**Use Cases**:
- **How informative is this context**: the values of a request add up to the bits the STM tells about the next event
- **Which patterns carry it**: each prediction's value is its part of that total

### Frequency/Relevance Metrics

#### itfdf_similarity

**One minus the distance between the observation and the matched part of the pattern, with the distance scaled by the pattern's share of the candidates' frequency.**

**Formula**: `itfdf_similarity = 1 - (distance * frequency / candidate_frequency)`, with `distance` one minus the cosine between the STM and `present`, each symbol weighted by the share of patterns that hold it, and `candidate_frequency` the summed frequency of every candidate.

**Range**: 0.0 to 1.0. Exactly 1.0 when the STM and `present` hold the same symbols.

**Use Cases**:
- **Symbol overlap**: How close the observation is to the matched events, on the symbols patterns share

#### tfidf_score

**TF-IDF score measuring pattern distinctiveness.**

**Formula**: Mean of `TF(symbol) * IDF(symbol)` for all unique symbols in the pattern.

**Range**: Typically 0.0 to ~2.0

**Use Cases**:
- **Distinctive patterns**: High scores indicate patterns with rare, informative symbols
- **Filtering generic patterns**: Low scores indicate patterns with only common symbols

#### confluence

**How far the pattern is from a chance co-occurrence of its symbols, in bits.**

**Formula**: `confluence = log2(frequency / F) + Σ log2(1 / q(s))` over the pattern's symbols, with `F` the node's total of pattern frequencies and `q(s)` a symbol's share of all learned symbol occurrences.

**Range**: Unbounded, in bits. Longer patterns and rarer symbols score higher.

**Use Cases**:
- **Signal vs noise**: Identifies patterns that are both common and non-coincidental
- **Describing a pattern**: It is the same for every prediction of the pattern, whatever was observed

### Bayesian Metrics

The four fields below come from one model. A pattern that is occurring shows each of its symbols with probability 0.95; a symbol it does not account for is an intrusion; and the alternative to every pattern is chance, where symbols are drawn by how often they were learned.

#### bayesian_prior

**The pattern's share of everything the node has learned.**

**Formula**: `frequency / total_pattern_frequencies`. Every learn counts once in the total.

**Range**: Above 0.0, up to 1.0

**Use Cases**:
- **Base rates**: How common is this pattern, before any observation
- **Frequency-based ranking**: It orders predictions as `frequency` does

#### bayesian_likelihood

**How strongly the observation supports this pattern over chance, in bits. This is I. J. Good's weight of evidence.**

**Formula**: `Σ log2(0.95 / q(s))` over the matched symbols, less `log2(20)` = 4.32 bits for each missing or extra symbol.

**Range**: Unbounded, in bits. Positive when the pattern explains the observation better than chance.

**Use Cases**:
- **Match strength alone**: Compare matches without counting how often each pattern was learned
- **Rare symbols count more**: A match on a symbol seen once in a thousand is worth about 10 bits; on one seen every other time, 1 bit

#### good_odds

**The posterior odds of this pattern against chance, as a base-2 logarithm. Named for I. J. Good.**

**Formula**: `good_odds = log2(bayesian_prior) + bayesian_likelihood`

**Range**: Unbounded, in bits. Above 0 the pattern beats chance; each bit doubles the odds.

**Use Cases**:
- **Explainable ranking**: Every term is a count of bits with a stated cause
- **Comparable across requests**: The value does not depend on the other candidates or on `max_predictions`

#### bayesian_posterior

**Posterior probability that this pattern, and not another candidate or chance, produced the observation.**

**Formula**: `2^good_odds / (1 + Σ 2^good_odds)`, summed over every candidate.

**Range**: 0.0 to 1.0. **With `chance_posterior`, sums to 1.0 over every candidate.**

**Use Cases**:
- **Pattern identification**: "Which learned pattern is this, and how probable"
- **Uncertainty quantification**: A lone weak match gets a low posterior, because chance is always the other hypothesis

**Caution**: Where symbols travel together (phrases, fixed motifs), the posterior is surer than it should be. For the probability of what comes next, use `future_potentials`.

### Affinity-Weighted Metrics

When emotive affinity is configured (`affinity_emotive`), these metrics weight the base metrics by emotive similarity between the current observation and the pattern's historical emotive profile.

- **weighted_similarity**: Similarity weighted by emotive affinity
- **weighted_evidence**: Evidence weighted by emotive affinity
- **weighted_confidence**: Confidence weighted by emotive affinity
- **weighted_snr**: SNR weighted by emotive affinity

**Values**: `None` when no affinity emotive is configured; otherwise same range as their base metric.

**Use Cases**:
- **Emotionally-relevant matching**: Prioritize patterns with similar emotional context
- **Personalization**: Weight predictions by user sentiment or mood

For complete mathematical details on all metrics, see the [Prediction Object Reference](../reference/prediction-object.md).

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

**Options**: every numeric metric of a prediction. Predictions are ranked highest value first.

*Core metrics:*
- **potential** (default): Weighted sum of eleven match terms (recommended)
- **good_odds**: Posterior log-odds against chance, in bits
- **similarity**: Pattern match score
- **evidence**: Share of the pattern observed
- **confidence**: Share of the matched events observed
- **snr**: Signal-to-noise ratio
- **fragmentation**: Pattern fragmentation score (the most fragmented first)
- **frequency**: Pattern frequency count

*Bayesian:*
- **bayesian_posterior**: Probability of the pattern (ranks as `good_odds` does)
- **bayesian_prior**: Share of the node's learns (ranks as `frequency` does)
- **bayesian_likelihood**: Weight of evidence, in bits

*Information-theoretic:*
- **predictive_information**: Part of the STM's information about the next event
- **confluence**: Distance of the pattern from chance, in bits
- **entropy**: Shannon entropy of the pattern's symbols
- **normalized_entropy**: Entropy over the node's maximum
- **global_normalized_entropy**: Entropy from node-wide symbol probabilities

*TF-IDF:*
- **itfdf_similarity**: Closeness on shared symbols, scaled by frequency share
- **tfidf_score**: TF-IDF score

*Position:*
- **event_cohesion**: Observed events sitting together in pattern events
- **onset_alignment**: How early in the pattern the observation lands

*Affinity-weighted (emotive-weighted variants):*
- **weighted_similarity**: Emotive-weighted similarity
- **weighted_evidence**: Emotive-weighted evidence
- **weighted_confidence**: Emotive-weighted confidence
- **weighted_snr**: Emotive-weighted SNR

Every candidate above the recall threshold is ranked, then the list is cut to `max_predictions`. Which key suits which data: [Metrics at a Glance](../reference/prediction-object.md#metrics-at-a-glance).

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

## What Comes Next

Two figures come back beside the predictions and describe the whole set of candidates.

### future_potentials

**The probability of each next event the candidates propose, most probable first.**

```json
"future_potentials": [
  {"next_event": ["checkout"], "probability": 0.586, "supporting_patterns": 1},
  {"next_event": ["logout"], "probability": 0.414, "supporting_patterns": 1}
]
```

Each candidate votes with weight `e^potential`. A candidate that has a `future` votes for its next event; patterns that agree on the next event add up, even when they differ later. A candidate whose pattern has ended votes for `ends_here`. Each sum is divided by the total, so the probabilities and `ends_here` add up to 1.0. It is computed over every candidate, including those `max_predictions` leaves out.

**Use Cases**:
- **Next-event prediction**: `future_potentials[0]['next_event']`
- **Confidence**: `probability` is a usable confidence in that event
- **Alternatives**: the full list is the distribution over what may follow

### ends_here

**The probability that no event follows the observation.**

It is the share of the candidates' weight held by patterns that end where the observation ends. Such a pattern is often the best match there is, and it has no next event to propose. `0.0` when every candidate goes on; `1.0` when every candidate has ended; `null` when there is no candidate.

When `ends_here` is larger than the top `probability`, the most probable reading is that nothing follows. It reports where the learned patterns end, not whether the session is over.

### chance_posterior

**The probability that no learned pattern explains the observation better than chance.**

It is what the `bayesian_posterior` values of every candidate leave over. `1.0` when nothing matched; near `1.0` when something matched and none of it should be trusted; `null` when the STM was empty.

```python
data = kato.get_predictions()

if not data['predictions'] or data['chance_posterior'] > 0.5:
    print("I don't know")
elif not data['future_potentials'] or data['ends_here'] > data['future_potentials'][0]['probability']:
    print("Nothing follows")
else:
    best = data['future_potentials'][0]
    print(f"Next: {best['next_event']} ({best['probability']:.0%})")
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
if top['anomalies']:
    print(f"Warning: deviating symbols {top['anomalies']}")
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
# Different actions based on the probability of the next event
best = predictions['future_potentials'][0] if predictions['future_potentials'] else None

if best is None or predictions['chance_posterior'] > 0.5:
    # Nothing learned explains this observation: do not act
    pass
elif predictions['ends_here'] > best['probability']:
    # The patterns that fit have ended: no next event to act on
    pass
elif best['probability'] > 0.9:
    # Auto-execute
    execute(best['next_event'])
elif best['probability'] > 0.7:
    # Suggest to user
    suggest(best['next_event'])
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

- [Prediction Object Reference](../reference/prediction-object.md) - Complete field reference with mathematical formulas
- [First Session Tutorial](first-session.md)
- [Pattern Learning](pattern-learning.md)
- [Configuration Guide](configuration.md)
- [Python Client](python-client.md)
