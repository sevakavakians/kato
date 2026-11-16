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

In KATO, `predictive_information` is computed per request, between the **short-term memory** (what has been observed) and the **next event** (the first event of each prediction's `future`).

The candidates of a request give the distribution of the next event, `P(E | STM)`, returned as `future_potentials`. With nothing known, an event is as probable as its symbols are common: `q(E)` is the product, over the event's symbols, of each symbol's share of all learned symbol occurrences. The information the STM carries about the next event is the divergence between the two:

```
D = Σ P(E | STM) × log2( P(E | STM) / q(E) )
    E
```

Each prediction's `predictive_information` is its part of that sum:

```python
def predictive_information(prediction, future_potentials, share, q):
    """
    share: the prediction's part of its next event's probability
           (e^potential over the sum of e^potential across the predictions that have a future)
    q:     symbol -> share of all learned symbol occurrences
    """
    if not prediction['future']:
        return 0.0                                   # proposes no next event
    event = prediction['future'][0]
    p_event = next(e['probability'] for e in future_potentials if e['next_event'] == event)
    chance_bits = sum(log2(1 / q[s]) for s in event)
    return share * (log2(p_event) + chance_bits)
```

Averaged over the STMs a node sees, `D` is the mutual information `I(Past; Future)` defined above.

**Usage in Predictions**:
```python
# Learned: login, browse, checkout (5 times); login, browse, logout (3 times);
#          login, reset_password, logout (2 times). Observed: login, browse.
prediction = {
    "present": [["login"], ["browse"]],
    "future": [["checkout"]],
    "predictive_information": 1.063,  # bits
    "potential": 17.197               # ranking score
}
# The three predictions of this request carry 1.063 + 0.544 - 0.001 = 1.606 bits
# about the next event.
```

**Details**: [Predictive Information](predictive-information.md)

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

### Weight of Evidence and Good-Odds

The logarithm of a likelihood ratio is a quantity of information. KATO measures each candidate pattern against chance, in bits:

```python
def weight_of_evidence(matches, n_missing, n_extras, q, e=0.05):
    """
    bayesian_likelihood: log2 of P(STM | pattern) / P(STM | chance).

    q: symbol -> share of all learned symbol occurrences
    e: assumed chance that a symbol is dropped from, or intrudes into, an observation
    """
    bits = sum(log2((1 - e) / q[s]) for s in matches)        # rarer symbols earn more
    return bits - log2(1 / e) * (n_missing + n_extras)       # 4.32 bits per symbol explained away


def good_odds(frequency, total_pattern_frequencies, evidence_bits):
    """Prior log-odds plus weight of evidence: posterior log-odds against chance."""
    return log2(frequency / total_pattern_frequencies) + evidence_bits
```

A matched symbol that makes up a thousandth of the node's symbol occurrences is worth `log2(0.95 × 1000)` = 9.9 bits: it is 950 times more probable under the pattern than under chance. `good_odds` above 0 means the pattern explains the observation better than chance does.

**Details**: [Bayesian Framework](bayesian-framework-for-kato.md)

### Confluence

How far a pattern is from a chance co-occurrence of its symbols, in bits:

```python
def confluence(pattern_symbols, frequency, total_pattern_frequencies, q):
    """log2 of how often the pattern was learned over how often chance would produce it."""
    return log2(frequency / total_pattern_frequencies) + sum(log2(1 / q[s]) for s in pattern_symbols)
```

It is a property of the pattern and the node, and it is the ceiling of `good_odds`: an exact, complete observation of the pattern scores `confluence` less 0.074 bits per symbol.

### ITFDF Similarity

**Inverse Term Frequency - Document Frequency** similarity in KATO:

```python
def itfdf_similarity(stm_counts, present_counts, frequency, candidate_frequency, pattern_share):
    """
    1 - distance × frequency / candidate_frequency

    stm_counts, present_counts: symbol -> number of occurrences in the STM / in `present`
    pattern_share:              symbol -> share of the node's patterns that hold it
    candidate_frequency:        summed frequency of every candidate of the request
    """
    dot = sum(pattern_share[s] ** 2 * stm_counts[s] * present_counts[s]
              for s in stm_counts if s in present_counts)
    norm_stm = sqrt(sum((pattern_share[s] * n) ** 2 for s, n in stm_counts.items()))
    norm_present = sqrt(sum((pattern_share[s] * n) ** 2 for s, n in present_counts.items()))
    cosine = min(dot / (norm_stm * norm_present), 1.0) if norm_stm and norm_present else 0.0
    return 1.0 - (1.0 - cosine) * frequency / candidate_frequency
```

The distance between the observation and the matched events counts in proportion to the pattern's share of the candidates' frequency. An STM that holds exactly the symbols of `present` scores 1.0.

### Signal-to-Noise Ratio

Information-theoretic view of SNR:

```python
def calculate_snr(matched_symbols, extra_symbols):
    """
    Calculate signal-to-noise ratio.

    SNR = (2 × Signal - Noise) / (2 × Signal + Noise)
    """
    signal = len(matched_symbols)
    noise = len(extra_symbols)

    if signal + noise > 0:
        snr = (2 * signal - noise) / (2 * signal + noise)
    else:
        snr = 0.0

    return snr
```

**Information interpretation**: How far the matched symbols outweigh the unexpected ones, from 1.0 (no extras) down to -1.0 (extras only).

## Practical Applications

### Pattern Ranking

Using information-theoretic metrics to rank predictions:

```python
def rank_by_bits(predictions):
    """
    Rank predictions by good-odds: the bits by which each pattern
    explains the observation better than chance.
    """
    return sorted(predictions, key=lambda p: (p['good_odds'], p['name']), reverse=True)


def informative_context(predictions, min_bits=1.0):
    """
    True when the observation tells at least `min_bits` about the next event.
    """
    return sum(p['predictive_information'] for p in predictions) >= min_bits
```

The same ranking is available from KATO directly with `rank_sort_algo: "good_odds"`. The sum in `informative_context` covers every candidate only when `max_predictions` returns them all.

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
