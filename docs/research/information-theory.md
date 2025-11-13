# Information Theory Foundations in KATO

## Table of Contents
1. [Overview](#overview)
2. [Entropy](#entropy)
3. [Mutual Information](#mutual-information)
4. [Predictive Information](#predictive-information)
5. [Conditional Entropy](#conditional-entropy)
6. [Information-Theoretic Metrics](#information-theoretic-metrics)
7. [Practical Applications](#practical-applications)
8. [Examples](#examples)

## Overview

KATO's design is grounded in **information theory** - the mathematical study of information quantification, storage, and communication. This foundation provides rigorous, interpretable metrics for pattern evaluation and prediction ranking.

### Why Information Theory?

1. **Quantitative**: Precise mathematical definitions
2. **Universal**: Applies across all data modalities
3. **Interpretable**: Direct connection to uncertainty and prediction
4. **Principled**: Based on fundamental limits of information processing

### Core Concepts

- **Entropy**: Measures uncertainty or information content
- **Mutual Information**: Measures statistical dependence between variables
- **Predictive Information**: Measures how much past predicts future
- **Conditional Entropy**: Uncertainty remaining after conditioning

## Entropy

### Definition

**Entropy** H(X) measures the average uncertainty in a random variable X:

```
H(X) = -Σ P(x) log₂ P(x)
```

**Units**: bits (when using log₂)

### Intuition

- **High entropy**: Variable is unpredictable (many possible values)
- **Low entropy**: Variable is predictable (few likely values)
- **Zero entropy**: Variable is deterministic (one certain value)

### Example: Binary Variable

```python
# Fair coin (maximum entropy)
P(heads) = 0.5
P(tails) = 0.5
H = -(0.5 * log₂(0.5) + 0.5 * log₂(0.5))
H = -(0.5 * -1 + 0.5 * -1) = 1.0 bits

# Biased coin (lower entropy)
P(heads) = 0.9
P(tails) = 0.1
H = -(0.9 * log₂(0.9) + 0.1 * log₂(0.1))
H = -(0.9 * -0.152 + 0.1 * -3.322) = 0.469 bits

# Deterministic (zero entropy)
P(heads) = 1.0
P(tails) = 0.0
H = -(1.0 * log₂(1.0)) = 0 bits
```

### KATO Implementation

#### Pattern Entropy

Entropy of pattern distribution in LTM:

```python
def calculate_pattern_entropy(patterns):
    """Calculate entropy of pattern frequency distribution."""
    total_freq = sum(p.frequency for p in patterns)

    entropy = 0.0
    for pattern in patterns:
        prob = pattern.frequency / total_freq
        if prob > 0:
            entropy -= prob * log2(prob)

    return entropy
```

**Interpretation**:
- High entropy → Many patterns with similar frequencies (diverse knowledge)
- Low entropy → Few dominant patterns (specialized knowledge)

#### Symbol Entropy

Entropy of symbol distribution:

```python
def calculate_symbol_entropy(symbol_frequencies):
    """Calculate entropy of symbol usage."""
    total = sum(symbol_frequencies.values())

    entropy = 0.0
    for freq in symbol_frequencies.values():
        prob = freq / total
        if prob > 0:
            entropy -= prob * log2(prob)

    return entropy
```

### Properties

1. **Non-negativity**: H(X) ≥ 0
2. **Maximum**: H(X) ≤ log₂(|X|) where |X| is number of possible values
3. **Uniformity**: Maximized when all outcomes equally likely
4. **Additivity**: H(X,Y) = H(X) + H(Y|X) = H(Y) + H(X|Y)

## Mutual Information

### Definition

**Mutual Information** I(X;Y) measures the information shared between two random variables:

```
I(X;Y) = Σ P(x,y) log₂[P(x,y) / (P(x)·P(y))]
```

Alternative form:
```
I(X;Y) = H(X) + H(Y) - H(X,Y)
```

### Intuition

- **I(X;Y) = 0**: X and Y are independent (knowing X tells nothing about Y)
- **I(X;Y) > 0**: X and Y are dependent (knowing X reduces uncertainty about Y)
- **I(X;Y) = H(X)**: Y completely determines X

### Example: Weather and Clothing

```python
# Joint probabilities P(weather, clothing)
#              Coat    No Coat
# Cold         0.35    0.05
# Warm         0.10    0.50

# Marginals
P(cold) = 0.40, P(warm) = 0.60
P(coat) = 0.45, P(no_coat) = 0.55

# Entropies
H(weather) = -(0.4*log₂(0.4) + 0.6*log₂(0.6)) = 0.971 bits
H(clothing) = -(0.45*log₂(0.45) + 0.55*log₂(0.55)) = 0.993 bits
H(weather, clothing) = -(0.35*log₂(0.35) + 0.05*log₂(0.05) +
                         0.10*log₂(0.10) + 0.50*log₂(0.50)) = 1.486 bits

# Mutual Information
I(weather; clothing) = 0.971 + 0.993 - 1.486 = 0.478 bits
```

**Interpretation**: Knowing weather reduces uncertainty about clothing by 0.478 bits.

### KATO Implementation

#### Present-Future Mutual Information

```python
def calculate_mutual_information(present, future, kb):
    """
    Calculate mutual information between present and future segments.

    I(Present; Future) = H(Present) + H(Future) - H(Present, Future)
    """
    # Get frequency counts from knowledge base
    present_future_freqs = get_present_future_frequencies(kb)
    present_freqs = get_present_frequencies(kb)
    future_freqs = get_future_frequencies(kb)
    total = get_total_frequencies(kb)

    # Calculate H(Present, Future)
    h_joint = 0.0
    for (pres, fut), freq in present_future_freqs.items():
        prob = freq / total
        if prob > 0:
            h_joint -= prob * log2(prob)

    # Calculate H(Present)
    h_present = 0.0
    for freq in present_freqs.values():
        prob = freq / total
        if prob > 0:
            h_present -= prob * log2(prob)

    # Calculate H(Future)
    h_future = 0.0
    for freq in future_freqs.values():
        prob = freq / total
        if prob > 0:
            h_future -= prob * log2(prob)

    # Mutual Information
    return h_present + h_future - h_joint
```

### Properties

1. **Symmetry**: I(X;Y) = I(Y;X)
2. **Non-negativity**: I(X;Y) ≥ 0
3. **Bounded**: I(X;Y) ≤ min(H(X), H(Y))
4. **Chain Rule**: I(X₁,X₂;Y) = I(X₁;Y) + I(X₂;Y|X₁)

## Predictive Information

### Definition

**Predictive Information** (also Excess Entropy) measures how much the past of a sequence predicts its future:

```
I(Past; Future) = lim[n→∞] I(X₁...Xₙ; Xₙ₊₁...X₂ₙ)
```

For finite sequences in KATO:
```
I(Past; Future) = Σ P(past, future) log₂[P(past, future) / (P(past)·P(future))]
```

### Intuition

Predictive information captures **temporal structure**:
- **High PI**: Strong correlations between past and future (reliable predictions)
- **Low PI**: Weak correlations (unpredictable or trivial)
- **Zero PI**: Past doesn't help predict future (memoryless process)

### Example: Coin Flips vs. Weather

```python
# Independent coin flips
# Past: HT, Future: TH
# P(HT, TH) = P(HT)·P(TH) = 0.25 * 0.25 = 0.0625
# I(Past; Future) = 0 bits (no predictive power)

# Weather patterns
# Past: Cold-Cold, Future: Cold (autocorrelation)
# P(Cold-Cold, Cold) = 0.35 (observed)
# P(Cold-Cold) = 0.16, P(Cold) = 0.40
# If independent: 0.16 * 0.40 = 0.064
# Actual: 0.35 >> 0.064
# I(Past; Future) > 0 bits (predictive power!)
```

### KATO Implementation

In KATO, predictive information calculated between **present** (matched portion) and **future** (predicted portion):

```python
def calculate_predictive_information(prediction, kb):
    """
    Calculate predictive information for a prediction.

    Maps to: I(Present; Future) where:
    - Present = matched segment of pattern
    - Future = predicted segment of pattern
    """
    present = prediction['present']
    future = prediction['future']

    # Hash segments for lookup
    present_hash = hash_segment(present)
    future_hash = hash_segment(future)

    # Get co-occurrence statistics
    joint_freq = kb.get_cooccurrence_count(present_hash, future_hash)
    present_freq = kb.get_present_count(present_hash)
    future_freq = kb.get_future_count(future_hash)
    total_freq = kb.get_total_count()

    # Calculate probabilities
    p_joint = joint_freq / total_freq
    p_present = present_freq / total_freq
    p_future = future_freq / total_freq

    # Calculate predictive information
    if p_joint > 0 and p_present > 0 and p_future > 0:
        pi = p_joint * log2(p_joint / (p_present * p_future))
    else:
        pi = 0.0

    return pi
```

**Usage in Predictions**:
```python
prediction = {
    "present": [["commute", "train"]],
    "future": [["arrive", "work"]],
    "predictive_information": 0.342,  # bits
    "potential": 2.1  # composite score
}
```

### Relationship to Entropy Rate

For stationary processes:
```
E = H - h_μ

Where:
  E = Excess entropy (predictive information)
  H = Total entropy
  h_μ = Entropy rate (per-symbol entropy)
```

**Interpretation**: Predictive information is the "excess" entropy beyond the entropy rate - the structured, predictable component.

## Conditional Entropy

### Definition

**Conditional Entropy** H(Y|X) measures remaining uncertainty in Y after observing X:

```
H(Y|X) = -Σ P(x,y) log₂ P(y|x)
```

Alternative form:
```
H(Y|X) = H(X,Y) - H(X)
```

### Intuition

- **H(Y|X) = H(Y)**: X provides no information about Y (independent)
- **H(Y|X) < H(Y)**: X reduces uncertainty about Y (dependent)
- **H(Y|X) = 0**: X completely determines Y

### KATO Implementation

#### Prediction Uncertainty

```python
def calculate_prediction_uncertainty(stm, predictions):
    """
    Calculate remaining uncertainty about future given STM.

    H(Future|STM) = H(Future, STM) - H(STM)
    """
    # H(STM) - entropy of current observation
    h_stm = calculate_segment_entropy(stm)

    # H(Future, STM) - joint entropy across all predictions
    h_joint = 0.0
    total_freq = sum(p['frequency'] for p in predictions)
    for pred in predictions:
        prob = pred['frequency'] / total_freq
        if prob > 0:
            h_joint -= prob * log2(prob)

    # Conditional entropy
    h_conditional = h_joint - h_stm

    return max(0.0, h_conditional)  # Non-negative
```

**Interpretation**: Lower conditional entropy → More certain predictions

## Information-Theoretic Metrics

### ITFDF Similarity

**Inverse Term Frequency - Document Frequency** similarity in KATO:

```python
def calculate_itfdf_similarity(pattern_symbols, stm_symbols, kb):
    """
    Calculate ITFDF similarity between pattern and STM.

    Similar to TF-IDF but for pattern matching:
    - Common symbols (high frequency) weighted less
    - Rare symbols (low frequency) weighted more
    """
    similarity = 0.0

    for symbol in pattern_symbols:
        if symbol in stm_symbols:
            # Inverse frequency weighting
            symbol_freq = kb.get_symbol_frequency(symbol)
            total_patterns = kb.get_total_patterns()

            # ITFDF score
            itfdf = 1.0 / (1.0 + log2(1.0 + symbol_freq / total_patterns))
            similarity += itfdf

    # Normalize
    return similarity / max(len(pattern_symbols), len(stm_symbols))
```

### Signal-to-Noise Ratio

Information-theoretic view of SNR:

```python
def calculate_snr(matched_symbols, extra_symbols):
    """
    Calculate signal-to-noise ratio.

    SNR = Signal / (Signal + Noise)
    """
    signal = len(matched_symbols)
    noise = len(extra_symbols)

    if signal + noise > 0:
        snr = signal / (signal + noise)
    else:
        snr = 0.0

    return snr
```

**Information interpretation**: Proportion of information that is signal vs. noise.

## Practical Applications

### Pattern Ranking

Using information-theoretic metrics to rank predictions:

```python
def rank_predictions(predictions):
    """
    Rank predictions by information-theoretic criteria.
    """
    for pred in predictions:
        # Predictive information (main signal)
        pi = pred['predictive_information']

        # Evidence (proportion observed)
        evidence = pred['evidence']

        # Confidence (match quality)
        confidence = pred['confidence']

        # Composite score
        score = pi * evidence * confidence
        pred['info_score'] = score

    # Sort by information score
    return sorted(predictions, key=lambda p: p['info_score'], reverse=True)
```

### Anomaly Detection

Using entropy for anomaly detection:

```python
def detect_anomalies(observation, expected_patterns):
    """
    Detect anomalies using entropy-based measures.
    """
    # Calculate entropy of observation
    obs_entropy = calculate_segment_entropy(observation)

    # Calculate expected entropy from patterns
    expected_entropy = calculate_pattern_entropy(expected_patterns)

    # Anomaly score
    anomaly_score = abs(obs_entropy - expected_entropy)

    return anomaly_score
```

### Information Gain

Measuring learning progress:

```python
def calculate_information_gain(kb_before, kb_after):
    """
    Calculate information gain from learning.

    Gain = H(before) - H(after)
    """
    h_before = calculate_pattern_entropy(kb_before.patterns)
    h_after = calculate_pattern_entropy(kb_after.patterns)

    # Reduction in entropy (increased structure)
    gain = h_before - h_after

    return gain
```

## Examples

### Example 1: Weather Prediction

```python
# Historical data
patterns = [
    {"present": ["cold"], "future": ["cold"], "freq": 35},
    {"present": ["cold"], "future": ["warm"], "freq": 5},
    {"present": ["warm"], "future": ["warm"], "freq": 50},
    {"present": ["warm"], "future": ["cold"], "freq": 10}
]

# Calculate predictive information
total = 100
p_cold_cold = 35/100 * log2(35/100 / (40/100 * 40/100))
p_cold_warm = 5/100 * log2(5/100 / (40/100 * 60/100))
p_warm_warm = 50/100 * log2(50/100 / (60/100 * 60/100))
p_warm_cold = 10/100 * log2(10/100 / (60/100 * 40/100))

I = p_cold_cold + p_cold_warm + p_warm_warm + p_warm_cold
# I ≈ 0.142 bits

# Interpretation: Yesterday's weather reduces uncertainty
# about today's weather by 0.142 bits
```

### Example 2: User Behavior

```python
# User action patterns
patterns = [
    {"present": ["login", "browse"], "future": ["purchase"], "freq": 120},
    {"present": ["login", "browse"], "future": ["logout"], "freq": 880},
    {"present": ["login"], "future": ["browse"], "freq": 1000}
]

# High-PI patterns: login → browse (certain)
# Low-PI patterns: browse → ? (uncertain)

# Use PI to prioritize predictions:
# - High PI → Reliable, use for planning
# - Low PI → Uncertain, gather more data
```

## Related Documentation

- [Core Concepts](core-concepts.md) - Foundational KATO concepts
- [Predictive Information](predictive-information.md) - Detailed predictive information
- [Pattern Theory](pattern-theory.md) - Pattern representation theory
- [Entropy Calculations](entropy-calculations.md) - Entropy algorithms

---

**Last Updated**: November 2025
**KATO Version**: 3.0+
