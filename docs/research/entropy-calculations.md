# Entropy Calculations in KATO

## Table of Contents
1. [Overview](#overview)
2. [Shannon Entropy](#shannon-entropy)
3. [Conditional Entropy](#conditional-entropy)
4. [Normalized Entropy](#normalized-entropy)
5. [Entropy Rate](#entropy-rate)
6. [Practical Calculations](#practical-calculations)
7. [Use Cases](#use-cases)
8. [Implementation](#implementation)

## Overview

**Entropy** quantifies uncertainty or information content in KATO's patterns and predictions. This document covers entropy calculations, interpretations, and applications.

### Information-Theoretic Foundation

Entropy measures average surprise in bits:
- **High entropy**: Unpredictable, many equally likely outcomes
- **Low entropy**: Predictable, few likely outcomes
- **Zero entropy**: Deterministic, one certain outcome

## Shannon Entropy

### Definition

For discrete random variable X with probability distribution P:

```
H(X) = -Σ P(x) log₂ P(x)
```

**Units**: bits (using log₂)

### Properties

1. **Non-negative**: H(X) ≥ 0
2. **Maximum**: H(X) ≤ log₂(|X|)
3. **Zero**: H(X) = 0 iff X deterministic
4. **Concave**: H is concave function of P

### Implementation

```python
def shannon_entropy(probabilities):
    """
    Calculate Shannon entropy from probability distribution.

    Args:
        probabilities: List or array of probabilities (must sum to 1)

    Returns:
        Entropy in bits
    """
    import numpy as np

    # Remove zero probabilities
    probs = np.array([p for p in probabilities if p > 0])

    if len(probs) == 0:
        return 0.0

    # Calculate entropy
    return -np.sum(probs * np.log2(probs))
```

### Example: Coin Flip

```python
# Fair coin
P_fair = [0.5, 0.5]
H_fair = shannon_entropy(P_fair)
# H = -(0.5*log₂(0.5) + 0.5*log₂(0.5)) = 1.0 bits

# Biased coin
P_biased = [0.9, 0.1]
H_biased = shannon_entropy(P_biased)
# H = -(0.9*log₂(0.9) + 0.1*log₂(0.1)) = 0.47 bits

# Deterministic
P_certain = [1.0, 0.0]
H_certain = shannon_entropy(P_certain)
# H = -(1.0*log₂(1.0)) = 0.0 bits
```

## Conditional Entropy

### Definition

Entropy of Y given X:

```
H(Y|X) = -Σ P(x,y) log₂ P(y|x)
```

Alternative:
```
H(Y|X) = H(X,Y) - H(X)
```

### Implementation

```python
def conditional_entropy(joint_probs, marginal_x):
    """
    Calculate H(Y|X).

    Args:
        joint_probs: 2D array of P(x,y)
        marginal_x: Array of P(x)

    Returns:
        Conditional entropy in bits
    """
    import numpy as np

    h_xy = 0.0  # Joint entropy
    h_x = shannon_entropy(marginal_x)  # Marginal entropy

    # Calculate joint entropy
    for p_xy in joint_probs.flatten():
        if p_xy > 0:
            h_xy -= p_xy * np.log2(p_xy)

    # H(Y|X) = H(X,Y) - H(X)
    return h_xy - h_x
```

### Example: Weather and Clothing

```python
# Joint distribution
#           Coat  No Coat
# Cold      0.35   0.05
# Warm      0.10   0.50

joint = np.array([[0.35, 0.05],
                  [0.10, 0.50]])

marginal_weather = [0.40, 0.60]  # P(cold), P(warm)

H_clothing_given_weather = conditional_entropy(joint, marginal_weather)
# H(Clothing|Weather) ≈ 0.52 bits

# Interpretation: Knowing weather reduces uncertainty
# about clothing by H(Clothing) - H(Clothing|Weather) bits
```

## Normalized Entropy

### Definition

Entropy normalized by maximum possible:

```
H_normalized(X) = H(X) / log₂(|X|)
```

**Range**: [0, 1]

### Implementation

```python
def normalized_entropy(probabilities):
    """
    Calculate normalized entropy in [0, 1].

    Returns:
        0 = deterministic, 1 = uniform distribution
    """
    h = shannon_entropy(probabilities)
    n = len(probabilities)

    if n <= 1:
        return 0.0

    max_entropy = np.log2(n)
    return h / max_entropy
```

### Example: Pattern Distribution

```python
# Pattern frequencies
patterns = [
    {"freq": 100},  # Dominant pattern
    {"freq": 10},
    {"freq": 5},
    {"freq": 5}
]

total = sum(p["freq"] for p in patterns)
probs = [p["freq"]/total for p in patterns]

H_norm = normalized_entropy(probs)
# H_norm ≈ 0.45

# Interpretation: Distribution is moderately skewed
# (0 = one pattern dominates, 1 = all equally frequent)
```

## Entropy Rate

### Definition

Per-symbol entropy of a stochastic process:

```
h_μ = lim[n→∞] H(Xₙ | X₁...Xₙ₋₁)
```

For stationary process:
```
h_μ = lim[n→∞] H(X₁...Xₙ) / n
```

### Implementation

```python
def estimate_entropy_rate(sequence, order=3):
    """
    Estimate entropy rate using n-gram model.

    Args:
        sequence: List of symbols
        order: Markov order (context length)

    Returns:
        Estimated entropy rate in bits/symbol
    """
    from collections import defaultdict, Counter

    # Count n-grams and (n+1)-grams
    context_counts = defaultdict(Counter)

    for i in range(len(sequence) - order):
        context = tuple(sequence[i:i+order])
        next_symbol = sequence[i+order]
        context_counts[context][next_symbol] += 1

    # Calculate entropy rate
    h_rate = 0.0
    total_contexts = sum(sum(counts.values()) for counts in context_counts.values())

    for context, next_symbol_counts in context_counts.items():
        context_prob = sum(next_symbol_counts.values()) / total_contexts

        # Entropy of next symbol given context
        total_next = sum(next_symbol_counts.values())
        for count in next_symbol_counts.values():
            prob = count / total_next
            h_rate -= context_prob * prob * np.log2(prob)

    return h_rate
```

### Example: Text Entropy

```python
text = "the quick brown fox jumps over the lazy dog"
symbols = text.split()

h_rate = estimate_entropy_rate(symbols, order=2)
# h_rate ≈ 2.5 bits/word

# Interpretation: On average, 2.5 bits needed to encode
# next word given previous 2 words
```

## Practical Calculations

### Pattern Entropy

Entropy of pattern frequency distribution:

```python
def calculate_pattern_entropy(knowledge_base):
    """
    Calculate entropy of learned patterns.

    High entropy → diverse knowledge
    Low entropy → specialized knowledge
    """
    patterns = knowledge_base.get_all_patterns()

    # Extract frequencies
    frequencies = [p.frequency for p in patterns]
    total = sum(frequencies)

    # Probabilities
    probs = [f / total for f in frequencies]

    # Entropy
    h = shannon_entropy(probs)

    # Normalized
    h_norm = normalized_entropy(probs)

    return {
        "entropy": h,
        "normalized": h_norm,
        "max_entropy": np.log2(len(patterns)),
        "num_patterns": len(patterns)
    }
```

### Symbol Entropy

Entropy of symbol usage:

```python
def calculate_symbol_entropy(knowledge_base):
    """
    Calculate entropy of symbol distribution.

    High entropy → diverse vocabulary
    Low entropy → repetitive symbols
    """
    symbol_freqs = knowledge_base.get_symbol_frequencies()

    frequencies = list(symbol_freqs.values())
    total = sum(frequencies)
    probs = [f / total for f in frequencies]

    return {
        "entropy": shannon_entropy(probs),
        "normalized": normalized_entropy(probs),
        "vocabulary_size": len(symbol_freqs)
    }
```

### Prediction Entropy

Uncertainty in predictions:

```python
def calculate_prediction_entropy(predictions):
    """
    Calculate entropy of prediction distribution.

    High entropy → uncertain predictions
    Low entropy → confident predictions
    """
    if not predictions:
        return 0.0

    # Use frequencies as proxy for probabilities
    frequencies = [p["frequency"] for p in predictions]
    total = sum(frequencies)

    if total == 0:
        return 0.0

    probs = [f / total for f in frequencies]

    return {
        "entropy": shannon_entropy(probs),
        "normalized": normalized_entropy(probs),
        "num_predictions": len(predictions)
    }
```

## Use Cases

### Anomaly Detection

Detect anomalies using entropy:

```python
def detect_entropy_anomaly(observation, expected_entropy, threshold=2.0):
    """
    Detect if observation entropy is anomalous.

    Args:
        observation: Current observation
        expected_entropy: Expected entropy from historical data
        threshold: Standard deviations for anomaly

    Returns:
        True if anomalous, False otherwise
    """
    # Calculate observation entropy
    obs_entropy = calculate_observation_entropy(observation)

    # Z-score
    z_score = abs(obs_entropy - expected_entropy["mean"]) / expected_entropy["std"]

    return z_score > threshold
```

### Information Gain

Measure learning progress:

```python
def calculate_information_gain(kb_before, kb_after):
    """
    Calculate reduction in entropy from learning.

    Positive gain → more structured knowledge
    Negative gain → more diverse knowledge
    """
    entropy_before = calculate_pattern_entropy(kb_before)
    entropy_after = calculate_pattern_entropy(kb_after)

    gain = entropy_before["entropy"] - entropy_after["entropy"]

    return {
        "gain": gain,
        "percent_reduction": (gain / entropy_before["entropy"]) * 100
    }
```

### Diversity Metrics

Measure knowledge diversity:

```python
def calculate_diversity(knowledge_base):
    """
    Calculate diversity using normalized entropy.

    Returns value in [0, 1]:
    - 0: All patterns identical (no diversity)
    - 1: All patterns equally frequent (maximum diversity)
    """
    pattern_entropy = calculate_pattern_entropy(knowledge_base)
    return pattern_entropy["normalized"]
```

### Confidence Estimation

Estimate prediction confidence from entropy:

```python
def estimate_confidence(predictions):
    """
    Estimate confidence as inverse of entropy.

    Low entropy → high confidence
    High entropy → low confidence
    """
    pred_entropy = calculate_prediction_entropy(predictions)

    # Normalize to [0, 1]
    h = pred_entropy["entropy"]
    h_max = pred_entropy.get("max_entropy", np.log2(len(predictions)))

    if h_max > 0:
        confidence = 1.0 - (h / h_max)
    else:
        confidence = 1.0

    return confidence
```

## Implementation

### Efficient Computation

```python
class EntropyCalculator:
    """Efficient entropy calculations with caching."""

    def __init__(self):
        self.cache = {}

    def entropy(self, distribution_key):
        """Calculate entropy with caching."""
        if distribution_key in self.cache:
            return self.cache[distribution_key]

        probs = self.get_distribution(distribution_key)
        h = shannon_entropy(probs)

        self.cache[distribution_key] = h
        return h

    def clear_cache(self):
        """Clear entropy cache."""
        self.cache.clear()
```

### Incremental Updates

```python
def incremental_entropy_update(old_entropy, old_probs, new_observation):
    """
    Update entropy incrementally without recomputing from scratch.

    More efficient for streaming data.
    """
    # Update probability distribution
    new_probs = update_distribution(old_probs, new_observation)

    # Calculate new entropy
    new_entropy = shannon_entropy(new_probs)

    return new_entropy, new_probs
```

### Numerical Stability

```python
def stable_entropy(probabilities, epsilon=1e-10):
    """
    Numerically stable entropy calculation.

    Handles near-zero probabilities gracefully.
    """
    import numpy as np

    probs = np.array(probabilities)

    # Remove zeros
    probs = probs[probs > epsilon]

    if len(probs) == 0:
        return 0.0

    # Renormalize
    probs = probs / np.sum(probs)

    # Calculate entropy with clipping
    return -np.sum(probs * np.log2(np.maximum(probs, epsilon)))
```

## Related Documentation

- [Information Theory](information-theory.md) - Theoretical foundations
- [Predictive Information](predictive-information.md) - Predictive information theory
- [Core Concepts](core-concepts.md) - KATO fundamentals
- [Potential Function](potential-function.md) - Prediction scoring

---

**Last Updated**: November 2025
**KATO Version**: 3.0+
