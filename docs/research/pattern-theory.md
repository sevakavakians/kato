# Pattern Theory in KATO

## Table of Contents
1. [Overview](#overview)
2. [Mathematical Foundation](#mathematical-foundation)
3. [Pattern Representation](#pattern-representation)
4. [Pattern Spaces](#pattern-spaces)
5. [Pattern Operations](#pattern-operations)
6. [Pattern Similarity](#pattern-similarity)
7. [Pattern Evolution](#pattern-evolution)
8. [Theoretical Properties](#theoretical-properties)

## Overview

Pattern theory provides the mathematical framework for KATO's knowledge representation. This document explores the theoretical foundations of patterns as abstract structures that capture regularities in sequential data.

### Definition

A **pattern** in KATO is a formal structure representing learned regularities:

```
P = (Σ, E, F, M, C)

Where:
  Σ = Alphabet (set of possible symbols)
  E = Event sequence [e₁, e₂, ..., eₙ]
  F = Frequency (observation count)
  M = Emotive profile (utility values)
  C = Context (metadata)
```

### Pattern Theory Foundations

KATO's pattern theory draws from:
1. **Formal Language Theory**: Sequences over alphabets
2. **Computational Mechanics**: Causal states and statistical complexity
3. **Information Theory**: Entropy and mutual information
4. **Graph Theory**: Pattern relationships and similarity networks

## Mathematical Foundation

### Alphabet and Symbols

**Definition**: The alphabet Σ is the set of all possible symbols.

```
Σ = {s₁, s₂, ..., sₙ} where sᵢ are atomic symbols
```

**Properties**:
- Finite or countably infinite
- Discrete symbols
- No inherent ordering (unless specified)

**Examples**:
```python
# Simple alphabet
Σ = {"A", "B", "C", "D"}

# Real-world alphabet
Σ = {"login", "logout", "purchase", "browse", ...}

# Vector symbols (hash-based)
Σ = {"VCTR|a1b2c3", "VCTR|d4e5f6", ...}
```

### Events

**Definition**: An event e is a multiset (unordered collection) of symbols from Σ.

```
e ⊆ Σ (allowing multiplicities)
```

**Representation**: Events stored as sorted lists for determinism:

```python
# Event as set (conceptual)
e = {"login", "success", "user_1"}

# Event as sorted list (implementation)
e = ["login", "success", "user_1"]
```

**Properties**:
- Symbols co-occurring at same "time"
- Order within event is normalized (sorted)
- Empty events possible (though rarely useful)

### Event Sequences

**Definition**: A pattern's event sequence is an ordered list of events:

```
E = [e₁, e₂, ..., eₙ] where eᵢ are events
```

**Properties**:
- Order matters (temporal sequence)
- Length n ≥ 1 (non-empty)
- For predictions: n ≥ 2 (minimum context)

**Example**:
```python
E = [
    ["morning", "coffee"],       # Event 1 (t=1)
    ["commute", "train"],        # Event 2 (t=2)
    ["arrive", "office"]         # Event 3 (t=3)
]
```

### Pattern Language

The set of all possible patterns forms a **pattern language**:

```
L(Σ) = {P | P is valid pattern over Σ}
```

**Cardinality**:
```
|L(Σ)| = Σ[n=1 to ∞] (2^|Σ|)^n

# For alphabet size |Σ| = 10, length n = 3:
# |L| ≈ (2^10)^3 = 1,073,741,824 possible patterns
```

## Pattern Representation

### Canonical Form

Every pattern has a **canonical representation** for deterministic hashing:

```python
def canonicalize(pattern):
    """Convert pattern to canonical form."""
    # 1. Sort symbols within each event
    sorted_events = [sorted(event) for event in pattern.events]

    # 2. Create string representation
    canonical_str = str(sorted_events)

    # 3. Generate deterministic hash
    pattern_hash = hashlib.sha1(canonical_str.encode()).hexdigest()

    return f"PTN|{pattern_hash[:12]}"
```

**Properties**:
- Two identical patterns have identical canonical forms
- Enables efficient equality checking
- Supports pattern deduplication

### Pattern Identity

**Definition**: Two patterns P₁ and P₂ are identical if:

```
P₁ ≡ P₂ ⟺ canonical(P₁) = canonical(P₂)
```

**Example**:
```python
# These are identical
P₁ = [["B", "A"], ["C"]]
P₂ = [["A", "B"], ["C"]]

# Both canonicalize to:
canonical = [["A", "B"], ["C"]]
hash = "PTN|abc123def456"
```

### Pattern Equivalence Classes

Patterns can be grouped into equivalence classes:

**Syntactic Equivalence**: Same structure
```python
P₁ = [["A"], ["B"]]
P₂ = [["A"], ["B"]]
# P₁ ≡_syntactic P₂
```

**Semantic Equivalence**: Same predictive power
```python
P₁ = [["cold"], ["cold"]]  # freq = 100
P₂ = [["cold"], ["cold"]]  # freq = 100
# P₁ ≡_semantic P₂ (same predictions)
```

**Statistical Equivalence**: Same frequency distribution
```python
# Patterns with same relative frequencies
# form statistical equivalence class
```

## Pattern Spaces

### Event Space

The space of all possible events:

```
ℰ(Σ) = P(Σ) = {e | e ⊆ Σ}

# Power set of alphabet
# Size: 2^|Σ|
```

### Pattern Space

The space of all patterns of length n:

```
𝒫ₙ(Σ) = ℰ(Σ)^n

# Cartesian product of event space with itself n times
# Size: (2^|Σ|)^n
```

### Learned Pattern Space

The subspace of patterns actually learned:

```
𝒫_learned ⊂ 𝒫(Σ)

# Typically |𝒫_learned| << |𝒫(Σ)|
# Real data exhibits structure, not all combinations occur
```

### Metric Space Structure

Patterns form a metric space with distance function:

```python
def pattern_distance(P₁, P₂):
    """
    Distance between two patterns.

    Uses edit distance on event sequences.
    """
    # Levenshtein distance on events
    n, m = len(P₁.events), len(P₂.events)

    # Dynamic programming
    dp = [[0] * (m + 1) for _ in range(n + 1)]

    for i in range(n + 1):
        dp[i][0] = i
    for j in range(m + 1):
        dp[0][j] = j

    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if P₁.events[i-1] == P₂.events[j-1]:
                cost = 0
            else:
                cost = 1
            dp[i][j] = min(
                dp[i-1][j] + 1,      # deletion
                dp[i][j-1] + 1,      # insertion
                dp[i-1][j-1] + cost  # substitution
            )

    return dp[n][m]
```

**Properties**:
- Non-negative: d(P₁, P₂) ≥ 0
- Identity: d(P, P) = 0
- Symmetry: d(P₁, P₂) = d(P₂, P₁)
- Triangle inequality: d(P₁, P₃) ≤ d(P₁, P₂) + d(P₂, P₃)

## Pattern Operations

### Pattern Concatenation

Joining two patterns:

```python
def concatenate(P₁, P₂):
    """
    Concatenate two patterns.

    P₁ ∘ P₂ = [e₁, ..., eₙ, f₁, ..., fₘ]
    """
    return Pattern(
        events=P₁.events + P₂.events,
        frequency=min(P₁.frequency, P₂.frequency)
    )
```

**Properties**:
- Associative: (P₁ ∘ P₂) ∘ P₃ = P₁ ∘ (P₂ ∘ P₃)
- Identity: P ∘ [] = [] ∘ P = P
- Non-commutative: P₁ ∘ P₂ ≠ P₂ ∘ P₁ (usually)

### Pattern Slicing

Extracting subsequences:

```python
def slice_pattern(P, start, end):
    """
    Extract subsequence P[start:end].
    """
    return Pattern(
        events=P.events[start:end],
        frequency=P.frequency
    )
```

**Temporal Segmentation** uses slicing:
```python
past = slice_pattern(P, 0, first_match)
present = slice_pattern(P, first_match, last_match+1)
future = slice_pattern(P, last_match+1, len(P))
```

### Pattern Projection

Projecting onto symbol subset:

```python
def project(P, symbol_set):
    """
    Project pattern onto subset of symbols.

    Keeps only events containing symbols from symbol_set.
    """
    projected_events = []
    for event in P.events:
        projected_event = [s for s in event if s in symbol_set]
        if projected_event:  # Non-empty
            projected_events.append(projected_event)

    return Pattern(events=projected_events)
```

**Use Case**: Focus on specific symbols (e.g., errors, purchases)

### Pattern Alignment

Aligning two patterns for comparison:

```python
def align_patterns(P₁, P₂):
    """
    Find optimal alignment using dynamic programming.

    Returns alignment showing correspondences.
    """
    n, m = len(P₁.events), len(P₂.events)

    # Alignment score matrix
    score = [[0] * (m + 1) for _ in range(n + 1)]

    for i in range(1, n + 1):
        for j in range(1, m + 1):
            match = event_similarity(P₁.events[i-1], P₂.events[j-1])
            score[i][j] = max(
                score[i-1][j-1] + match,  # Match/mismatch
                score[i-1][j] - 1,        # Gap in P₂
                score[i][j-1] - 1         # Gap in P₁
            )

    return traceback_alignment(score, P₁, P₂)
```

## Pattern Similarity

### Syntactic Similarity

Based on structure:

```python
def syntactic_similarity(P₁, P₂):
    """
    Structural similarity using sequence matching.

    Returns value in [0, 1].
    """
    from difflib import SequenceMatcher

    matcher = SequenceMatcher(None, P₁.events, P₂.events)
    return matcher.ratio()
```

### Semantic Similarity

Based on predictive equivalence:

```python
def semantic_similarity(P₁, P₂, test_sequences):
    """
    Measure similarity of predictions on test sequences.
    """
    predictions₁ = [predict(P₁, seq) for seq in test_sequences]
    predictions₂ = [predict(P₂, seq) for seq in test_sequences]

    # Agreement rate
    agreement = sum(p₁ == p₂ for p₁, p₂ in zip(predictions₁, predictions₂))
    return agreement / len(test_sequences)
```

### Statistical Similarity

Based on frequency distribution:

```python
def statistical_similarity(P₁, P₂, kb):
    """
    Similarity based on co-occurrence statistics.
    """
    # Symbol overlap
    symbols₁ = get_all_symbols(P₁)
    symbols₂ = get_all_symbols(P₂)

    # Jaccard similarity
    intersection = symbols₁ & symbols₂
    union = symbols₁ | symbols₂

    return len(intersection) / len(union) if union else 0
```

## Pattern Evolution

### Pattern Growth

Patterns evolve through observations:

```python
class PatternEvolution:
    def __init__(self, pattern):
        self.pattern = pattern
        self.frequency = 1
        self.first_seen = datetime.now()
        self.last_seen = datetime.now()

    def observe(self):
        """Update pattern on observation."""
        self.frequency += 1
        self.last_seen = datetime.now()

    def decay(self, decay_rate):
        """Temporal decay of pattern importance."""
        time_since = (datetime.now() - self.last_seen).total_seconds()
        self.effective_frequency = self.frequency * exp(-decay_rate * time_since)
```

### Pattern Merging

Combining similar patterns:

```python
def merge_patterns(P₁, P₂, similarity_threshold=0.9):
    """
    Merge patterns if sufficiently similar.

    Returns merged pattern or None if not similar enough.
    """
    similarity = syntactic_similarity(P₁, P₂)

    if similarity >= similarity_threshold:
        # Combine frequencies
        merged_freq = P₁.frequency + P₂.frequency

        # Use longer pattern as base
        base_pattern = P₁ if len(P₁.events) >= len(P₂.events) else P₂

        return Pattern(
            events=base_pattern.events,
            frequency=merged_freq
        )
    else:
        return None
```

### Pattern Specialization

Creating more specific patterns:

```python
def specialize_pattern(P, additional_context):
    """
    Create specialized pattern with additional constraints.
    """
    specialized_events = []
    for event in P.events:
        # Add context symbols
        specialized_event = sorted(event + additional_context)
        specialized_events.append(specialized_event)

    return Pattern(
        events=specialized_events,
        frequency=1  # New specialized pattern
    )
```

## Theoretical Properties

### Completeness

**Definition**: Pattern representation is complete if any sequence can be represented.

**Theorem**: KATO's pattern representation is complete over any finite alphabet Σ.

**Proof**: For any sequence S = [e₁, ..., eₙ], we can construct pattern P with events [e₁, ..., eₙ]. ∎

### Consistency

**Definition**: Pattern system is consistent if predictions are deterministic.

**Theorem**: KATO's pattern system is consistent - same inputs always yield same predictions.

**Proof**:
1. Pattern storage uses deterministic hashing
2. Pattern matching uses deterministic algorithms (SequenceMatcher)
3. Ranking uses deterministic scoring (potential function)
4. No random components in prediction generation
Therefore, consistency holds. ∎

### Expressiveness

**Definition**: Measure of patterns that can be distinguished.

**KATO's Expressiveness**:
- Temporal order: ✓ (sequences)
- Co-occurrence: ✓ (events)
- Frequency: ✓ (observation counts)
- Context: ✓ (emotives, metadata)
- Continuous values: ✓ (emotives)
- Hierarchical structure: ✗ (flat sequences only)

### Computational Complexity

**Pattern Learning**: O(n) where n is STM length
- Single scan of STM
- Hash computation: O(n)
- Database insert: O(log N) where N is total patterns

**Pattern Matching**: O(N × m × n) naïve
- N patterns in database
- m = STM length
- n = average pattern length

**Optimized Matching**: O(log N × m × n)
- With indexing layer
- Candidate filtering reduces N effectively

**Space Complexity**: O(N × n_avg)
- N patterns
- n_avg = average pattern length

## Use Cases

### Sequence Prediction

```python
# Learn patterns
patterns = [
    Pattern([["A"], ["B"], ["C"]], freq=10),
    Pattern([["A"], ["B"], ["D"]], freq=5)
]

# Given observation ["A"], ["B"]
# Predict: ["C"] (potential = 2.0) or ["D"] (potential = 1.0)
```

### Anomaly Detection

```python
# Expected pattern
expected = Pattern([["login"], ["browse"], ["logout"]], freq=1000)

# Observed sequence
observed = [["login"], ["admin_access"], ["logout"]]

# Anomaly: "admin_access" unexpected
```

### Clustering

```python
# Group patterns by similarity
clusters = cluster_patterns(patterns, similarity_threshold=0.8)

# Each cluster represents behavioral mode
```

## Related Documentation

- [Core Concepts](core-concepts.md) - KATO fundamentals
- [Information Theory](information-theory.md) - Information-theoretic foundations
- [Pattern Matching](pattern-matching.md) - Matching algorithms
- [Similarity Metrics](similarity-metrics.md) - Similarity calculations
