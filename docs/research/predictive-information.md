# Excess Entropy / Predictive Information in KATO

## Executive Summary

**Predictive Information** (also called **Excess Entropy**) measures how much information the past of a sequence contains about its future. In KATO, this metric quantifies the hidden structure and long-range correlations within learned patterns, and is available as one of the ranking metrics alongside other measures.

**Current Potential Calculation:**
```
potential = (evidence + confidence) * snr + itfdf_similarity + (1/(fragmentation + 1))
```

Where:
- `evidence`: Proportion of the pattern that has been observed
- `confidence`: Ratio of matched symbols to total present symbols
- `snr`: Signal-to-noise ratio (matches vs extras)
- `itfdf_similarity`: Inverse term frequency-document frequency similarity
- `fragmentation`: Pattern cohesion measure (number of blocks - 1)

**Predictive Information**: Calculated separately and available as `predictive_information` field and as an alternative ranking metric via `rank_sort_algo` configuration

## 1. Theoretical Foundation

### 1.1 Information-Theoretic Definition

Excess Entropy (EE) is formally defined as the mutual information between the semi-infinite past and semi-infinite future of a stochastic process:

```
E = I(Past; Future) = Σ P(past, future) log₂[P(past, future)/(P(past)·P(future))]
```

This captures the **complexity of structure** in sequences—not just randomness (entropy rate) but the predictive relationships between different parts of the sequence.

### 1.2 Intuitive Understanding

- **Entropy rate** (h_μ): How unpredictable each next symbol is
- **Excess entropy**: How much "hidden structure" exists—the reduction in uncertainty about the future by knowing the past
- **High EE**: Strong correlations between past and future (reliable predictions)
- **Low EE**: Either nearly random (white noise) or trivially repetitive

## 2. KATO's Temporal Segmentation Mapping

### 2.1 Conceptual Alignment

The critical insight is that KATO's temporal segmentation differs from traditional excess entropy formulations:

**Traditional EE:**
- Past: Everything before current observation
- Future: Everything after current observation

**KATO's Implementation:**
- **Past**: Events BEFORE the first matching event
- **Present**: ALL events containing matching symbols (the observed overlap)
- **Future**: Events AFTER the last matching event

### 2.2 Mapping to Predictive Information

For predictive information calculation in KATO:
- **EE "Past"** → KATO's **"Present"** (the matched segment)
- **EE "Future"** → KATO's **"Future"** (predicted subsequences)

This mapping makes sense because:
1. KATO's "present" represents what we know (the matched portion)
2. KATO's "future" represents what we want to predict
3. The mutual information between these segments measures predictive power

## 3. Mathematical Formulation for KATO

### 3.1 Empirical Probability Estimation

Given KATO's pattern storage in MongoDB with frequency counters:

```python
# Joint probability of present-future pair
P(present, future) = f(present, future) / Σ f(all_present_future_pairs)

# Marginal probabilities
P(present) = Σ_future f(present, future) / Σ f(all_present_future_pairs)
P(future) = Σ_present f(present, future) / Σ f(all_present_future_pairs)
```

Where `f(x, y)` denotes the frequency count of the pair (x, y) across all patterns in the KB.

### 3.2 Predictive Information Calculation

```python
def calculate_predictive_information(present, future, kb):
    """
    Calculate mutual information between present (matched) and future segments.
    
    Args:
        present: List of events in the present segment
        future: List of events in the future segment
        kb: Knowledge base with pattern frequencies
        
    Returns:
        Predictive information value (bits)
    """
    # Get co-occurrence statistics from KB
    joint_freq = get_present_future_frequency(present, future, kb)
    present_freq = get_present_frequency(present, kb)
    future_freq = get_future_frequency(future, kb)
    total_freq = get_total_pair_frequency(kb)
    
    # Calculate probabilities
    p_joint = joint_freq / total_freq if total_freq > 0 else 0
    p_present = present_freq / total_freq if total_freq > 0 else 0
    p_future = future_freq / total_freq if total_freq > 0 else 0
    
    # Calculate mutual information term
    if p_joint > 0 and p_present > 0 and p_future > 0:
        return p_joint * log2(p_joint / (p_present * p_future))
    else:
        return 0.0
```

### 3.3 Aggregate Predictive Information

For a complete prediction ensemble:

```python
def calculate_ensemble_predictive_information(predictions, kb):
    """
    Calculate total predictive information across all predictions.
    """
    total_pi = 0.0
    
    for prediction in predictions:
        present = prediction['present']
        future = prediction['future']
        
        # Calculate PI for this specific prediction
        pi = calculate_predictive_information(present, future, kb)
        
        # Weight by pattern frequency (reliability)
        weighted_pi = pi * prediction['frequency'] / total_pattern_frequencies
        
        total_pi += weighted_pi
    
    return total_pi
```

## 4. Implementation in KATO

### 4.1 Data Structure Requirements

To efficiently calculate predictive information, KATO needs to track:

1. **Present-Future Co-occurrence Matrix**
   ```python
   {
     "present_hash": "hash_of_present_segment",
     "future_hash": "hash_of_future_segment",
     "frequency": 127,
     "patterns": ["PTRN|abc123", "PTRN|def456", ...]
   }
   ```

2. **Marginal Frequency Caches**
   ```python
   {
     "present_frequencies": {"hash1": 250, "hash2": 189, ...},
     "future_frequencies": {"hash3": 312, "hash4": 98, ...},
     "total_pair_frequency": 15678
   }
   ```

### 4.2 Integration Points

1. **Pattern Learning** (`learnPattern`):
   - Extract present-future segments from pattern
   - Update co-occurrence statistics
   - Increment marginal frequencies

2. **Prediction Generation** (`predictPattern`):
   - Calculate predictive_information for each prediction
   - Calculate potential using standard formula: `(evidence + confidence) * snr + itfdf_similarity + (1/(fragmentation + 1))`
   - Sort by configurable ranking metric (default: `potential`; alternative: `predictive_information`)

### 4.3 Algorithm Pseudocode

```python
# During pattern learning
def update_predictive_information_stats(pattern):
    # Segment pattern into past, present, future
    segments = segment_pattern(pattern)
    
    # Hash segments for efficient storage
    present_hash = hash(segments.present)
    future_hash = hash(segments.future)
    
    # Update co-occurrence
    increment_cooccurrence(present_hash, future_hash)
    
    # Update marginals
    increment_present_frequency(present_hash)
    increment_future_frequency(future_hash)
    increment_total_pairs()

# During prediction
def calculate_prediction_potential(prediction):
    # Calculate predictive information (for metrics)
    pi = calculate_predictive_information(
        prediction['present'],
        prediction['future'],
        kb
    )

    # Store in prediction object
    prediction['predictive_information'] = pi

    # Calculate potential using standard formula
    prediction['potential'] = (
        (prediction['evidence'] + prediction['confidence']) * prediction['snr']
        + prediction['itfdf_similarity']
        + (1 / (prediction['fragmentation'] + 1))
    )

    return prediction
```

## 5. Example Calculation

### 5.1 Scenario Setup

**Learned Pattern** (frequency = 127):
```python
[["A1","A2"], ["B1","B2","B3"], ["C1"], ["D1","D2","D3","D4"], ["E1","E2","E3"]]
```

**STM Observation**:
```python
[["B2","B4"], ["D1","D3","D5"], ["E1","E2"], ["C1"]]
```

**Segmentation Result**:
- Past: `[["A1","A2"]]`
- Present: `[["B1","B2","B3"], ["C1"], ["D1","D2","D3","D4"]]`
- Future: `[["E1","E2","E3"]]`

### 5.2 Predictive Information Calculation

Assume from KB statistics:
- This present→future pair occurs 95 times
- This present occurs with any future 120 times  
- This future occurs with any present 150 times
- Total present-future pairs in KB: 10,000

```python
p_joint = 95/10000 = 0.0095
p_present = 120/10000 = 0.012
p_future = 150/10000 = 0.015

PI = 0.0095 * log2(0.0095/(0.012*0.015))
   = 0.0095 * log2(0.0095/0.00018)
   = 0.0095 * log2(52.78)
   = 0.0095 * 5.72
   = 0.054 bits
```

### 5.3 Potential Calculation

With the following metrics:
- evidence = 0.6 (60% of pattern observed)
- confidence = 0.8 (80% match quality in present)
- snr = 0.7 (good signal-to-noise)
- itfdf_similarity = 0.65
- fragmentation = 2 (3 blocks)

```python
potential = (evidence + confidence) * snr + itfdf_similarity + (1/(fragmentation + 1))
         = (0.6 + 0.8) * 0.7 + 0.65 + (1/3)
         = 1.4 * 0.7 + 0.65 + 0.333
         = 0.98 + 0.65 + 0.333
         = 1.963
```

The predictive_information value (0.054) is available separately for analysis or as an alternative ranking metric.

## 6. Benefits and Implications

### 6.1 Theoretical Advantages

1. **Information-Theoretic Foundation**: Grounded in established theory from computational mechanics
2. **Captures Hidden Structure**: Identifies patterns with strong temporal dependencies
3. **Interpretable Metric**: Direct measure of how informative the past is about the future

### 6.2 Practical Benefits

1. **Complementary Metrics**: Provides information-theoretic ranking option alongside composite potential
2. **Flexible Ranking**: Can prioritize patterns based on predictive information via `rank_sort_algo` configuration
3. **Adaptive Learning**: Naturally adapts as co-occurrence statistics evolve
4. **Multiple Perspectives**: Potential uses composite metrics for balanced ranking, predictive_information provides pure information-theoretic view

### 6.3 Decision-Making Implications

Agents using KATO should:
- **Prioritize high-PI patterns**: These have the strongest past-future correlations
- **Trust stable predictions**: High PI with high frequency indicates reliable patterns
- **Explore low-PI areas**: May indicate novel or changing dynamics

## 7. Edge Cases and Considerations

### 7.1 Empty Segments

- Empty future → PI = 0 (no prediction possible)
- Empty present → PI = 0 (no basis for prediction)
- Handle gracefully without errors

### 7.2 Novel Patterns

- New patterns have no co-occurrence history
- Use Laplace smoothing or default small PI value
- Allow rapid adaptation as statistics accumulate

### 7.3 Computational Efficiency

- Cache marginal probabilities per session
- Use incremental updates where possible
- Consider approximations for very large KBs

## 8. Testing Strategy

### 8.1 Unit Tests

1. **Basic Calculation**: Verify PI formula with known values
2. **Edge Cases**: Empty segments, single symbols, novel patterns
3. **Probability Consistency**: Ensure probabilities sum to 1

### 8.2 Integration Tests

1. **Learning-Prediction Cycle**: Verify PI updates affect predictions
2. **Sorting Correctness**: Ensure predictions sort by new potential
3. **Performance**: Measure calculation overhead

### 8.3 Validation Tests

1. **Information-Theoretic Properties**:
   - PI ≥ 0 (non-negativity)
   - PI ≤ min(H(present), H(future)) (upper bound)
   - PI = 0 for independent segments

2. **Behavioral Validation**:
   - High PI for strongly coupled sequences
   - Low PI for random or trivial patterns

## 9. Configuration and Tuning

### 9.1 Parameters

```python
# In configuration
PREDICTIVE_INFORMATION_CONFIG = {
    "enable_caching": True,
    "cache_ttl_seconds": 300,
    "smoothing_factor": 0.001,  # Laplace smoothing
    "min_frequency_threshold": 1,  # Minimum pattern frequency to consider
    "approximation_enabled": False,  # Use exact calculation by default
}
```

### 9.2 Performance Tuning

- **Small KB** (< 1000 patterns): Calculate exactly, no caching needed
- **Medium KB** (1000-10000 patterns): Enable caching, exact calculation
- **Large KB** (> 10000 patterns): Enable caching and approximations

## 10. Future Extensions

### 10.1 Multi-Scale Analysis

Calculate PI at different temporal scales:
- Event-level PI
- Symbol-level PI  
- Pattern-level PI

### 10.2 Conditional Predictive Information

Extend to conditional PI given context:
```
I(Past; Future | Context)
```

### 10.3 Real-Time Adaptation

Implement online learning algorithms for incremental PI updates without full recalculation.

## Conclusion

The integration of Predictive Information into KATO provides a theoretically grounded, interpretable, and efficient method for ranking predictions based on the fundamental information-theoretic relationships between temporal segments. This approach simplifies the potential calculation while capturing the essential predictive structure in learned patterns, making KATO's predictions more reliable and its behavior more transparent.