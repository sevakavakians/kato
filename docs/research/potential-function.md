# Predictive Potential Function in KATO

## Table of Contents
1. [Overview](#overview)
2. [Potential Function Definition](#potential-function-definition)
3. [Component Metrics](#component-metrics)
4. [Mathematical Properties](#mathematical-properties)
5. [Alternative Ranking Functions](#alternative-ranking-functions)
6. [Tuning and Optimization](#tuning-and-optimization)
7. [Examples](#examples)
8. [Comparison to Other Approaches](#comparison-to-other-approaches)

## Overview

The **potential function** is KATO's composite score for ranking predictions. It combines multiple information-theoretic and statistical metrics into a single value that represents the overall quality and reliability of a prediction.

### Purpose

- Rank predictions by likelihood and quality
- Balance multiple factors (similarity, frequency, structure)
- Provide interpretable scoring
- Enable configurable weighting

## Potential Function Definition

### Standard Formula

```
potential = (evidence + confidence) × snr + itfdf_similarity + (1/(fragmentation + 1))
```

### Components

| Component | Range | Description |
|-----------|-------|-------------|
| evidence | [0, 1] | Proportion of pattern observed |
| confidence | [0, 1] | Match quality in present |
| snr | [0, 1] | Signal-to-noise ratio |
| itfdf_similarity | [0, 1] | Weighted symbol similarity |
| fragmentation | [0, ∞) | Pattern cohesion (0 = contiguous) |

### Interpretation

**High potential** (> 2.0):
- Most of pattern observed (high evidence)
- Good match quality (high confidence)
- Few extra symbols (high SNR)
- Rare symbols matched (high ITFDF)
- Contiguous match (low fragmentation)

**Low potential** (< 1.0):
- Little of pattern observed
- Poor match quality
- Many extra symbols
- Common symbols only
- Fragmented match

## Component Metrics

### Evidence

**Definition**: Fraction of pattern actually observed

```python
def calculate_evidence(pattern, matching_events):
    """
    Evidence = observed_events / total_pattern_events

    Measures how much of the pattern has been seen.
    """
    observed = len(matching_events)
    total = len(pattern.events)

    return observed / total if total > 0 else 0.0
```

**Example**:
```python
pattern = [["A"], ["B"], ["C"], ["D"], ["E"]]  # 5 events
matching = [["B"], ["C"], ["D"]]  # 3 events matched

evidence = 3 / 5 = 0.6
```

**Properties**:
- Always in [0, 1]
- 1.0 = entire pattern observed
- 0.0 = no pattern observed

### Confidence

**Definition**: Quality of symbol matching within observed events

```python
def calculate_confidence(pattern_present, stm_present):
    """
    Confidence = matched_symbols / total_present_symbols

    Measures match quality in the present region.
    """
    pattern_symbols = set(flatten(pattern_present))
    stm_symbols = set(flatten(stm_present))

    matched = pattern_symbols & stm_symbols
    total = pattern_symbols | stm_symbols

    return len(matched) / len(total) if total > 0 else 0.0
```

**Example**:
```python
pattern_present = [["A", "B", "C"], ["D"]]
stm_present = [["A", "B", "X"], ["D", "Y"]]

matched = {"A", "B", "D"}  # 3 symbols
total = {"A", "B", "C", "D", "X", "Y"}  # 6 symbols

confidence = 3 / 6 = 0.5
```

**Properties**:
- Range [0, 1]
- 1.0 = perfect match
- 0.5 = half matched, half extras/missing
- 0.0 = no overlap

### Signal-to-Noise Ratio (SNR)

**Definition**: Proportion of signal (matches) vs. noise (extras)

```python
def calculate_snr(matched_symbols, extra_symbols):
    """
    SNR = signal / (signal + noise)

    Measures match purity.
    """
    signal = len(matched_symbols)
    noise = len(extra_symbols)

    if signal + noise > 0:
        return signal / (signal + noise)
    return 0.0
```

**Example**:
```python
matched = ["A", "B", "C"]  # 3 matches
extras = ["X"]  # 1 extra

snr = 3 / (3 + 1) = 0.75
```

**Properties**:
- Range [0, 1]
- 1.0 = no noise (perfect match)
- 0.5 = equal signal and noise
- 0.0 = all noise (no matches)

### ITFDF Similarity

**Definition**: Inverse term frequency-document frequency weighted similarity

```python
def calculate_itfdf(pattern, stm, kb):
    """
    ITFDF = Σ (weight × match) / max_symbols

    Rare symbols weighted higher than common.
    """
    similarity = 0.0

    pattern_symbols = get_all_symbols(pattern)
    stm_symbols = get_all_symbols(stm)

    for symbol in pattern_symbols:
        if symbol in stm_symbols:
            # Get symbol frequency in knowledge base
            freq = kb.get_symbol_frequency(symbol)
            total_patterns = kb.get_total_patterns()

            # Inverse frequency weight
            weight = 1.0 / (1.0 + np.log2(1.0 + freq / total_patterns))

            similarity += weight

    # Normalize
    max_size = max(len(pattern_symbols), len(stm_symbols))
    return similarity / max_size if max_size > 0 else 0.0
```

**Example**:
```python
# Rare symbol "error" (freq=5 in 1000 patterns)
weight_rare = 1.0 / (1.0 + log₂(1.0 + 5/1000)) ≈ 0.993

# Common symbol "login" (freq=800 in 1000 patterns)
weight_common = 1.0 / (1.0 + log₂(1.0 + 800/1000)) ≈ 0.527

# Rare symbol matches contribute more to similarity
```

**Properties**:
- Range [0, 1]
- Rewards rare symbol matches
- Penalizes common symbol matches
- Context-aware (uses KB statistics)

### Fragmentation

**Definition**: Number of disjoint matching blocks minus one

```python
def calculate_fragmentation(matching_blocks):
    """
    Fragmentation = num_blocks - 1

    Measures match cohesion.
    0 = contiguous match (single block)
    N = N+1 disjoint blocks
    """
    return max(0, len(matching_blocks) - 1)
```

**Example**:
```python
# Contiguous match
blocks = [(1, 0, 3)]  # Single block
fragmentation = 0

# Fragmented match
blocks = [(1, 0, 2), (4, 3, 1)]  # Two blocks
fragmentation = 1
```

**In Potential**:
```python
cohesion_term = 1 / (fragmentation + 1)

# Contiguous (frag=0): 1/1 = 1.0
# Two blocks (frag=1): 1/2 = 0.5
# Three blocks (frag=2): 1/3 = 0.33
```

## Mathematical Properties

### Bounds

**Theoretical Range**: [0, ~4.0]

**Component Contributions**:
```
(evidence + confidence) × snr:  [0, 2.0]
itfdf_similarity:              [0, 1.0]
1/(fragmentation + 1):         [0, 1.0]
```

**Typical Ranges**:
- Excellent predictions: 2.0 - 3.0
- Good predictions: 1.5 - 2.0
- Moderate predictions: 1.0 - 1.5
- Poor predictions: 0.0 - 1.0

### Sensitivity Analysis

**Evidence sensitivity**:
```python
# High evidence (0.8) vs low evidence (0.2)
# With confidence=0.8, snr=0.9, itfdf=0.7, frag=0

potential_high = (0.8 + 0.8) × 0.9 + 0.7 + 1.0 = 3.14
potential_low = (0.2 + 0.8) × 0.9 + 0.7 + 1.0 = 2.60

# Difference: 0.54 (significant)
```

**Fragmentation sensitivity**:
```python
# Contiguous (frag=0) vs fragmented (frag=3)
# With evidence=0.7, confidence=0.8, snr=0.9, itfdf=0.7

potential_cont = (0.7 + 0.8) × 0.9 + 0.7 + 1.0 = 3.05
potential_frag = (0.7 + 0.8) × 0.9 + 0.7 + 0.25 = 2.30

# Difference: 0.75 (significant)
```

### Monotonicity

**Theorem**: Potential is monotonic in each component (holding others constant).

**Proof**: Each component appears with positive coefficient or in denominator with positive contribution.

## Alternative Ranking Functions

### Predictive Information Ranking

```python
rank_sort_algo = "predictive_information"

# Sort by I(Present; Future) instead of potential
predictions.sort(key=lambda p: p["predictive_information"], reverse=True)
```

**When to use**: Pure information-theoretic ranking

### Frequency Ranking

```python
rank_sort_algo = "frequency"

# Sort by observation count
predictions.sort(key=lambda p: p["frequency"], reverse=True)
```

**When to use**: Popularity-based recommendations

### Similarity Ranking

```python
rank_sort_algo = "similarity"

# Sort by sequence similarity only
predictions.sort(key=lambda p: p["similarity"], reverse=True)
```

**When to use**: Structural pattern matching

### Custom Composite

```python
def custom_potential(pred, weights):
    """
    Custom weighted potential function.

    Args:
        pred: Prediction dictionary
        weights: Dictionary of component weights

    Returns:
        Custom potential score
    """
    return (
        weights["evidence"] * pred["evidence"] +
        weights["confidence"] * pred["confidence"] +
        weights["snr"] * pred["snr"] +
        weights["itfdf"] * pred["itfdf_similarity"] +
        weights["freq"] * np.log(1 + pred["frequency"]) +
        weights["cohesion"] / (pred["fragmentation"] + 1)
    )
```

## Tuning and Optimization

### Component Weights

Modify standard formula with configurable weights:

```python
def weighted_potential(pred, weights):
    """
    Weighted potential with configurable contributions.
    """
    # Default weights
    default_weights = {
        "evidence": 1.0,
        "confidence": 1.0,
        "snr": 1.0,
        "itfdf": 1.0,
        "cohesion": 1.0
    }

    w = {**default_weights, **weights}

    return (
        w["evidence"] * pred["evidence"] +
        w["confidence"] * pred["confidence"]
    ) * w["snr"] * pred["snr"] + \
    w["itfdf"] * pred["itfdf_similarity"] + \
    w["cohesion"] / (pred["fragmentation"] + 1)
```

### Application-Specific Tuning

**High Precision Application** (prefer quality over recall):
```python
weights = {
    "confidence": 2.0,  # Double-weight confidence
    "snr": 2.0,         # Double-weight SNR
    "evidence": 0.5     # De-emphasize evidence
}
```

**High Recall Application** (prefer coverage):
```python
weights = {
    "evidence": 2.0,    # Double-weight evidence
    "confidence": 0.5,  # De-emphasize confidence
    "snr": 0.5          # Allow some noise
}
```

**Rare Event Detection**:
```python
weights = {
    "itfdf": 3.0,       # Emphasize rare symbols
    "frequency": 0.1    # De-emphasize common patterns
}
```

## Examples

### Example 1: High-Quality Prediction

```python
prediction = {
    "evidence": 0.8,
    "confidence": 0.9,
    "snr": 0.95,
    "itfdf_similarity": 0.75,
    "fragmentation": 0,
    "frequency": 100
}

potential = (0.8 + 0.9) × 0.95 + 0.75 + 1.0
         = 1.7 × 0.95 + 0.75 + 1.0
         = 1.615 + 0.75 + 1.0
         = 3.365

# Excellent prediction (> 3.0)
```

### Example 2: Moderate Prediction

```python
prediction = {
    "evidence": 0.5,
    "confidence": 0.6,
    "snr": 0.7,
    "itfdf_similarity": 0.5,
    "fragmentation": 2,
    "frequency": 15
}

potential = (0.5 + 0.6) × 0.7 + 0.5 + (1/3)
         = 1.1 × 0.7 + 0.5 + 0.333
         = 0.77 + 0.5 + 0.333
         = 1.603

# Moderate prediction (1.5 - 2.0)
```

### Example 3: Poor Prediction

```python
prediction = {
    "evidence": 0.2,
    "confidence": 0.3,
    "snr": 0.4,
    "itfdf_similarity": 0.3,
    "fragmentation": 5,
    "frequency": 3
}

potential = (0.2 + 0.3) × 0.4 + 0.3 + (1/6)
         = 0.5 × 0.4 + 0.3 + 0.167
         = 0.2 + 0.3 + 0.167
         = 0.667

# Poor prediction (< 1.0)
```

## Comparison to Other Approaches

### vs. Simple Similarity

**KATO Potential**: Multifaceted quality metric
**Simple Similarity**: Single-dimension comparison

**Advantage**: Captures reliability, structure, rarity

### vs. Frequency-Only

**KATO Potential**: Balances popularity with match quality
**Frequency-Only**: Pure popularity contest

**Advantage**: Handles rare but relevant patterns

### vs. Neural Network Confidence

**KATO Potential**: Deterministic, interpretable, traceable
**NN Confidence**: Probabilistic, opaque

**Advantage**: Explainable, reproducible

## Related Documentation

- [Predictive Information](predictive-information.md) - Alternative ranking metric
- [Information Theory](information-theory.md) - Theoretical foundations
- [Entropy Calculations](entropy-calculations.md) - Component calculations
- [Core Concepts](core-concepts.md) - KATO fundamentals

---

**Last Updated**: November 2025
**KATO Version**: 3.0+
