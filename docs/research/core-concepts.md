# KATO Core Concepts

## Table of Contents
1. [Overview](#overview)
2. [Patterns](#patterns)
3. [Memory Architecture](#memory-architecture)
4. [Determinism](#determinism)
5. [Transparency](#transparency)
6. [Temporal Processing](#temporal-processing)
7. [Multi-Modal Observations](#multi-modal-observations)
8. [Prediction Philosophy](#prediction-philosophy)

## Overview

KATO (Knowledge Abstraction for Traceable Outcomes) is built on foundational concepts from information theory, computational mechanics, and deterministic machine learning. This document explains the core theoretical concepts that underpin KATO's design and behavior.

### Guiding Principles

1. **Deterministic Learning**: Same inputs always produce same outputs
2. **Complete Transparency**: All predictions traceable to learned patterns
3. **Information-Theoretic**: Based on entropy, mutual information, and predictive information
4. **Temporal Awareness**: Understanding of sequence order and timing
5. **Multi-Modal Integration**: Unified processing of discrete symbols, vectors, and continuous values

## Patterns

### Definition

A **pattern** is KATO's fundamental unit of knowledge. It represents a learned sequence of events or a profile of co-occurring symbols.

**Formal Definition**:
```
Pattern P = (E, F, M, C)

Where:
  E = [e₁, e₂, ..., eₙ]  - Sequence of events
  F = frequency count      - Number of observations
  M = emotive profile      - Emotional/utility values
  C = metadata             - Contextual information
```

**Event Structure**:
```python
# Each event is a set of co-occurring symbols
event = ["symbol_1", "symbol_2", "symbol_3"]

# Pattern is sequence of events
pattern = [
    ["coffee", "morning"],      # Event 1
    ["commute", "train"],       # Event 2
    ["arrive", "work"]          # Event 3
]
```

### Pattern Types

#### Temporal Patterns (Sequences)
- **Definition**: Ordered sequences where event position matters
- **Length**: 2+ events
- **Use Case**: Predicting future states based on observed sequences
- **Example**: Weather patterns, user workflows, system state transitions

#### Non-Temporal Patterns (Profiles)
- **Definition**: Single-event patterns capturing co-occurrence
- **Length**: 1 event
- **Use Case**: Clustering, classification, association
- **Example**: User profiles, document categories, sensor readings

### Pattern Identity

Patterns are identified by deterministic SHA-1 hashing:

```python
# Pattern hash calculation
pattern_string = str(sorted_events)
pattern_hash = hashlib.sha1(pattern_string.encode()).hexdigest()
pattern_name = f"PTN|{pattern_hash[:12]}"

# Example: PTN|a1b2c3d4e5f6
```

**Properties**:
- Identical patterns always have identical hashes
- Hash serves as unique identifier in storage
- Deterministic across all KATO instances

## Memory Architecture

### Two-Memory Model

KATO implements a classic two-stage memory architecture inspired by cognitive science:

```
┌─────────────────────────────────────┐
│   Short-Term Memory (STM)           │
│   • Temporary buffer                │
│   • Recent observations             │
│   • Limited capacity                │
│   • Source for learning             │
└──────────────┬──────────────────────┘
               │ Learn
               ▼
┌─────────────────────────────────────┐
│   Long-Term Memory (LTM)            │
│   • Persistent storage              │
│   • Learned patterns                │
│   • Unlimited capacity              │
│   • Source for predictions          │
└─────────────────────────────────────┘
```

### Short-Term Memory (STM)

**Purpose**: Accumulate recent observations before pattern formation

**Implementation**:
```python
# Python deque for efficient FIFO operations
stm = deque([
    ["event1_sym1", "event1_sym2"],
    ["event2_sym1"],
    ["event3_sym1", "event3_sym2", "event3_sym3"]
])
```

**Properties**:
- Events added sequentially
- FIFO (First In, First Out) structure
- Can be cleared manually or automatically (STM_MODE)
- Minimum 2 strings required for predictions

**STM Modes**:

1. **CLEAR Mode** (default):
   ```python
   # STM cleared after learning
   observe() → observe() → learn() → STM=[empty]
   ```

2. **ROLLING Mode**:
   ```python
   # STM maintains sliding window
   observe() → observe() → learn() → STM=[recent events]
   ```

### Long-Term Memory (LTM)

**Purpose**: Persistent storage of learned patterns

**Storage**: ClickHouse (pattern data) + Redis (metadata/cache)

**Structure**:
```python
pattern = {
  "name": "PTN|a1b2c3d4e5f6",
  "length": 3,
  "events": [
    ["morning", "coffee"],
    ["commute", "train"],
    ["work", "arrive"]
  ],
  "emotive_profile": {
    "energy": [[-0.2], [0.0], [0.5]]
  },
  "metadata": {},
  "frequency": 42,
  "created_at": "2025-11-13T00:00:00Z",
  "updated_at": "2025-11-13T00:00:00Z"
}
```

**Operations**:
- **Store**: Add new patterns (ClickHouse)
- **Update**: Increment frequency counters (Redis)
- **Query**: Retrieve matching patterns (multi-stage filter)
- **Search**: Find similar patterns (hybrid search)

## Determinism

### Deterministic Guarantee

**Promise**: Given identical inputs and configuration, KATO produces identical outputs

**Implementation Requirements**:
1. **Sorted Events**: Symbols within events sorted alphabetically
2. **Consistent Hashing**: SHA-1 for reproducible identifiers
3. **Fixed Algorithms**: No randomness in core processing
4. **Stateless Processing**: No hidden state between operations

### Deterministic Operations

#### Observation Processing
```python
# Input order doesn't matter
observe(["zebra", "apple"])  # Stored as ["apple", "zebra"]
observe(["apple", "zebra"])  # Stored as ["apple", "zebra"]
# Both produce identical pattern
```

#### Pattern Matching
```python
# Always produces same similarity scores
stm = [["A", "B"], ["C", "D"]]
pattern = [["A", "B"], ["C", "D"], ["E", "F"]]
similarity = calculate_similarity(stm, pattern)  # Always 0.667
```

#### Prediction Ranking
```python
# Consistent ordering by potential
predictions = get_predictions()
# Sorted by: potential = (evidence + confidence) * snr + itfdf + (1/(frag+1))
# Same inputs → same ordering
```

### Testing Determinism

```python
# Test: Run twice, compare outputs
def test_determinism():
    # First run
    session1 = create_session("test_node")
    observe(session1, ["A", "B"])
    observe(session1, ["C", "D"])
    learn(session1)
    predictions1 = get_predictions(session1)

    # Second run (fresh session, same data)
    session2 = create_session("test_node")
    observe(session2, ["A", "B"])
    observe(session2, ["C", "D"])
    learn(session2)
    predictions2 = get_predictions(session2)

    # Assert identical
    assert predictions1 == predictions2
```

## Transparency

### Traceable Predictions

Every prediction in KATO can be traced back to:
1. **Source Pattern**: Which learned pattern generated it
2. **Matching Blocks**: Exact symbols that matched
3. **Temporal Alignment**: Past, present, future segmentation
4. **Confidence Metrics**: How similar and reliable

### Prediction Object Transparency

```python
prediction = {
    "pattern_name": "PTN|a1b2c3d4e5f6",  # Source pattern ID
    "past": [["morning", "coffee"]],      # Events before match
    "present": [["commute", "train"]],    # Matched events
    "future": [["work", "arrive"]],       # Predicted events
    "missing": [["train"]],               # Expected but not observed
    "extras": [["bus"]],                  # Observed but not expected
    "confidence": 0.85,                   # Match quality
    "potential": 2.3,                     # Overall score
    "similarity": 0.67,                   # Sequence similarity
    "frequency": 42,                      # Pattern reliability
    "evidence": 0.67,                     # Proportion observed
    "snr": 0.9,                           # Signal to noise
    "fragmentation": 0                    # Match cohesion
}
```

### Explainable Scoring

Each metric in predictions is calculable:

**Evidence**:
```
evidence = matched_events / total_pattern_events
```

**Confidence**:
```
confidence = matched_symbols / present_symbols
```

**Signal-to-Noise Ratio**:
```
snr = matched_symbols / (matched_symbols + extra_symbols)
```

**Potential** (composite score):
```
potential = (evidence + confidence) * snr + itfdf_similarity + (1/(fragmentation + 1))
```

## Temporal Processing

### Time as Sequence Order

KATO treats time as **ordinal** (event order) rather than **cardinal** (clock time):

```python
# Events have order, not timestamps
[event₁, event₂, event₃]  # t=1, t=2, t=3

# Not: [(event₁, 10:00), (event₂, 10:05), (event₃, 10:10)]
```

**Benefits**:
- Clock time irrelevant
- Works with irregular intervals
- Focus on causal sequence

### Temporal Segmentation

Predictions segmented into three temporal regions:

```
Past           Present              Future
[e₁, e₂]      [e₃, e₄, e₅]        [e₆, e₇]
                   ↑
            Matched region
```

**Definitions**:
- **Past**: Events in pattern BEFORE first matched event
- **Present**: ALL events containing matched symbols
- **Future**: Events in pattern AFTER last matched event

**Example**:
```python
# Learned pattern
pattern = [["A"], ["B"], ["C"], ["D"], ["E"]]

# Observation (STM)
stm = [["B"], ["C"], ["D"]]

# Segmentation
past = [["A"]]                # Before match
present = [["B"], ["C"], ["D"]]  # Matched region
future = [["E"]]              # After match
```

## Multi-Modal Observations

### Symbol Types

KATO processes three types of symbols:

#### 1. Discrete Strings
```python
strings = ["user_login", "page_view", "checkout"]
```
- Direct symbolic representation
- Sorted alphabetically within events
- Most common observation type

#### 2. Vector Embeddings
```python
vectors = [
    [0.1, 0.2, ..., 0.768],  # 768-dimensional embedding
    [0.3, 0.1, ..., 0.421]
]
```
- Converted to hash-based names: `VCTR|a1b2c3`
- Stored in Qdrant for similarity search
- Enables semantic matching

#### 3. Emotives (Continuous Values)
```python
emotives = {
    "happiness": 0.8,
    "arousal": -0.3,
    "confidence": 0.6
}
```
- Emotional or utility metadata
- Averaged across observations
- Stored in pattern emotive profiles

### Unified Processing

All modalities combined into single event:

```python
observation = {
    "strings": ["login", "success"],
    "vectors": [[0.1, ..., 0.768]],
    "emotives": {"confidence": 0.9}
}

# Becomes event:
["login", "success", "VCTR|a1b2c3"]  # + emotives stored separately
```

## Prediction Philosophy

### Information-Theoretic Foundation

KATO's predictions based on **predictive information** - mutual information between observed past and predicted future:

```
I(Past; Future) = Σ P(past, future) log₂[P(past, future) / (P(past)·P(future))]
```

**Interpretation**: How much does knowing the past reduce uncertainty about the future?

### Ensemble Predictions

KATO returns **multiple predictions**, not single answer:

```python
predictions = [
    {"future": [["E"]], "potential": 2.3, "frequency": 42},
    {"future": [["F"]], "potential": 1.8, "frequency": 15},
    {"future": [["G"]], "potential": 1.2, "frequency": 8}
]
```

**Benefits**:
- Shows alternative possibilities
- Weighted by reliability (frequency, potential)
- Enables probabilistic reasoning
- Supports decision-making under uncertainty

### Prediction Filtering

**Recall Threshold**:
```python
RECALL_THRESHOLD = 0.3  # Minimum similarity

# Only patterns with similarity ≥ 0.3 returned
```

**Max Predictions**:
```python
MAX_PREDICTIONS = 100  # Limit result set

# Return top 100 by potential
```

## Theoretical Foundations

### Computational Mechanics

KATO inspired by **computational mechanics** framework:
- Causal states represent predictive equivalence classes
- Patterns as compressed representations of causal structure
- Excess entropy measures hidden temporal structure

### Information Theory

Core metrics from information theory:
- **Entropy**: H(X) = -Σ P(x) log₂ P(x)
- **Mutual Information**: I(X;Y) = H(X) + H(Y) - H(X,Y)
- **Predictive Information**: I(Past; Future)

### Machine Learning

KATO as deterministic ML:
- Supervised learning from sequences
- Non-parametric (instance-based)
- Lazy learning (computation at prediction time)
- Explainable (traceable to training data)

## Comparison to Other Approaches

### vs. Neural Networks
| KATO | Neural Networks |
|------|-----------------|
| Deterministic | Stochastic (random initialization) |
| Exact pattern recall | Approximate pattern recognition |
| Fully explainable | Black box (generally) |
| No training phase | Requires training |

### vs. Markov Models
| KATO | Markov Models |
|------|---------------|
| Variable-length patterns | Fixed-order context |
| Multi-modal | Typically single modality |
| Exact storage | Probability matrices |
| Event-based | State-based |

### vs. RNNs/LSTMs
| KATO | RNNs/LSTMs |
|------|------------|
| Explicit memory | Learned hidden states |
| Deterministic | Training randomness |
| Interpretable | Opaque internal representations |
| No gradient descent | Backpropagation through time |

## Use Cases

### Ideal Applications

1. **Regulatory Compliance**: Where explainability required
2. **Safety-Critical Systems**: Where determinism essential
3. **Temporal Prediction**: Sequential decision-making
4. **Anomaly Detection**: Detecting missing/extra symbols
5. **Multi-Modal Learning**: Combining text, vectors, values

### Not Ideal For

1. **Unstructured Generation**: Free-form text/image generation
2. **Continuous Control**: Real-time robotics/control systems
3. **High-Dimensional Regression**: Complex function approximation
4. **Transfer Learning**: Cross-domain generalization

## Related Documentation

- [Pattern Matching](pattern-matching.md) - Similarity algorithms
- [Predictive Information](predictive-information.md) - Information theory details
- [Vector Embeddings](vector-embeddings.md) - Vector processing
- [Emotives Processing](emotives-processing.md) - Continuous values
- [Metadata Processing](metadata-processing.md) - Contextual information

---

**Last Updated**: November 2025
**KATO Version**: 3.0+
