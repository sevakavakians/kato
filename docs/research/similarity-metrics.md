# Similarity Metrics in KATO

## Table of Contents
1. [Overview](#overview)
2. [Token-Level Similarity](#token-level-similarity)
3. [Character-Level Similarity](#character-level-similarity)
4. [Cosine Similarity](#cosine-similarity)
5. [Composite Metrics](#composite-metrics)
6. [Performance Comparison](#performance-comparison)
7. [Selection Guidelines](#selection-guidelines)
8. [Implementation Details](#implementation-details)

## Overview

KATO implements multiple similarity metrics to compare sequences, each optimized for different use cases. This document provides theoretical foundations and practical guidance for similarity calculations.

### Similarity Metric Requirements

A valid similarity metric must satisfy:

1. **Bounded**: sim(x, y) ∈ [0, 1]
2. **Symmetric**: sim(x, y) = sim(y, x)
3. **Maximum self-similarity**: sim(x, x) = 1
4. **Minimum dissimilarity**: sim(x, y) = 0 when completely different

### KATO's Metrics

| Metric | Use Case | Speed | Accuracy |
|--------|----------|-------|----------|
| Token-Level | Discrete symbols, exact matching | 9x faster | Exact (difflib compatible) |
| Character-Level | Text chunks, fuzzy matching | 75x faster | ~0.03 difference |
| Cosine | Vector embeddings | Very fast | Semantic similarity |

## Token-Level Similarity

### Algorithm: Longest Common Subsequence (LCS)

Token-level matching uses **LCSseq** - the length of the longest common subsequence:

```
sim_token(A, B) = 2 × LCS(A, B) / (|A| + |B|)
```

### Implementation

```python
def token_similarity(seq1, seq2):
    """
    Calculate token-level similarity using LCS.

    Exactly matches difflib.SequenceMatcher behavior.
    """
    from difflib import SequenceMatcher

    # Compare token sequences directly
    matcher = SequenceMatcher(None, seq1, seq2)
    return matcher.ratio()
```

### Example

```python
# Token sequences
A = ["the", "quick", "brown", "fox"]
B = ["the", "slow", "brown", "dog"]

# Find LCS
LCS = ["the", "brown"]  # Length = 2

# Calculate similarity
sim = 2 × 2 / (4 + 4) = 0.50
```

### Properties

**Advantages**:
- Exact difflib compatibility
- Order-sensitive (respects sequence)
- Gap-aware (handles insertions/deletions)

**Disadvantages**:
- Slower than character-level (9x vs 75x speedup)
- Requires tokenized input

### When to Use

Use token-level similarity when:
- Working with pre-tokenized data
- Exact difflib compatibility required
- Regulatory/compliance needs demand identical behavior
- Testing and validation scenarios

**Configuration**:
```bash
export KATO_USE_TOKEN_MATCHING=true
```

## Character-Level Similarity

### Algorithm: Levenshtein-Based Fuzzy Matching

Character-level uses **RapidFuzz** with Levenshtein distance:

```
sim_char(A, B) = 1 - (Levenshtein(A, B) / max(|A|, |B|))
```

### Implementation

```python
def character_similarity(seq1, seq2):
    """
    Calculate character-level similarity using Levenshtein.

    Joins sequences to strings, then compares.
    """
    from rapidfuzz import fuzz

    # Join tokens to strings
    str1 = " ".join(seq1)
    str2 = " ".join(seq2)

    # Fuzzy ratio
    return fuzz.ratio(str1, str2) / 100.0
```

### Levenshtein Distance

Edit distance - minimum operations to transform string A to B:

**Operations**:
1. **Insert** a character
2. **Delete** a character
3. **Substitute** a character

**Dynamic Programming**:
```python
def levenshtein(str1, str2):
    """
    Calculate edit distance.
    """
    m, n = len(str1), len(str2)
    dp = [[0] * (n + 1) for _ in range(m + 1)]

    # Initialize
    for i in range(m + 1):
        dp[i][0] = i
    for j in range(n + 1):
        dp[0][j] = j

    # Fill matrix
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if str1[i-1] == str2[j-1]:
                cost = 0
            else:
                cost = 1

            dp[i][j] = min(
                dp[i-1][j] + 1,      # Delete
                dp[i][j-1] + 1,      # Insert
                dp[i-1][j-1] + cost  # Substitute
            )

    return dp[m][n]
```

### Example

```python
# After joining to strings
str1 = "the quick brown fox"
str2 = "the slow brown dog"

# Levenshtein distance = 8
# (substitute: quick→slow, fox→dog, etc.)

# Max length = 19
sim = 1 - (8 / 19) = 0.58
```

### Properties

**Advantages**:
- 75x faster than difflib baseline
- Works well for text chunks
- Handles typos and variations

**Disadvantages**:
- ~0.03 score difference vs difflib
- Less precise for discrete tokens
- Joins tokens (loses some structure)

### When to Use

Use character-level similarity when:
- Production deployment (speed critical)
- Processing text documents/chunks
- Approximate matching sufficient
- High throughput required

**Configuration**:
```bash
export KATO_USE_TOKEN_MATCHING=false  # Default
```

## Cosine Similarity

### Algorithm: Vector Dot Product

For vector embeddings, cosine similarity measures angle:

```
sim_cosine(u, v) = (u · v) / (‖u‖ × ‖v‖)
```

### Implementation

```python
def cosine_similarity(vec1, vec2):
    """
    Calculate cosine similarity between vectors.

    Returns value in [-1, 1], typically normalized to [0, 1].
    """
    import numpy as np

    # Dot product
    dot_product = np.dot(vec1, vec2)

    # Norms
    norm1 = np.linalg.norm(vec1)
    norm2 = np.linalg.norm(vec2)

    # Cosine
    if norm1 > 0 and norm2 > 0:
        cosine = dot_product / (norm1 * norm2)
    else:
        cosine = 0.0

    # Normalize to [0, 1]
    return (cosine + 1) / 2
```

### Geometric Interpretation

Cosine similarity measures the angle θ between vectors:

```
cos(θ) = 1.0  → θ = 0°    (identical direction)
cos(θ) = 0.0  → θ = 90°   (orthogonal)
cos(θ) = -1.0 → θ = 180°  (opposite direction)
```

### Properties

**Advantages**:
- Magnitude-invariant (only direction matters)
- Very fast computation (single dot product)
- Semantic similarity for embeddings
- Efficient indexing (HNSW)

**Disadvantages**:
- Only for vector data
- Requires pre-computed embeddings

### When to Use

Use cosine similarity for:
- Vector embeddings (768-dim)
- Semantic text similarity
- Image/audio embeddings
- Cross-modal matching

**Implementation**:
```python
# Qdrant automatically uses cosine
results = qdrant.search(
    collection_name="vectors",
    query_vector=query_vector,
    limit=100
)
```

## Composite Metrics

### ITFDF Similarity

**Inverse Term Frequency - Document Frequency**:

```python
def itfdf_similarity(pattern, query, kb):
    """
    TF-IDF-inspired metric for patterns.

    Rare symbols weighted higher than common symbols.
    """
    similarity = 0.0

    pattern_symbols = get_all_symbols(pattern)
    query_symbols = get_all_symbols(query)

    for symbol in pattern_symbols:
        if symbol in query_symbols:
            # Get symbol frequency across all patterns
            freq = kb.get_symbol_frequency(symbol)
            total_patterns = kb.get_total_patterns()

            # Inverse frequency weight
            weight = 1.0 / (1.0 + np.log2(1.0 + freq / total_patterns))

            similarity += weight

    # Normalize
    max_symbols = max(len(pattern_symbols), len(query_symbols))
    return similarity / max_symbols if max_symbols > 0 else 0.0
```

**Properties**:
- Rewards rare symbol matches
- Penalizes common symbol matches
- Contextually aware (uses KB statistics)

### Jaccard Similarity

Set-based similarity:

```python
def jaccard_similarity(set1, set2):
    """
    Jaccard index: intersection / union.
    """
    intersection = set1 & set2
    union = set1 | set2

    if len(union) > 0:
        return len(intersection) / len(union)
    return 0.0
```

**Use Case**: Event-level similarity (sets of symbols)

### N-gram Similarity

Subsequence-based matching:

```python
def ngram_similarity(seq1, seq2, n=3):
    """
    Similarity based on n-gram overlap.
    """
    # Generate n-grams
    ngrams1 = set(tuple(seq1[i:i+n]) for i in range(len(seq1)-n+1))
    ngrams2 = set(tuple(seq2[i:i+n]) for i in range(len(seq2)-n+1))

    # Jaccard on n-grams
    return jaccard_similarity(ngrams1, ngrams2)
```

**Properties**:
- Captures local structure
- Robust to small variations
- Configurable granularity (n parameter)

## Performance Comparison

### Benchmark Setup

```python
# Test data
patterns = 10000
stm_length = 7
pattern_length = 10

# Baseline: difflib.SequenceMatcher
baseline_time = 1000  # ms (normalized to 1x)
```

### Results

| Method | Time (ms) | Speedup | Accuracy vs. Difflib |
|--------|-----------|---------|---------------------|
| difflib (baseline) | 1000 | 1x | 1.000 (exact) |
| Token-level (LCSseq) | 111 | 9x | 1.000 (exact) |
| Character-level (RapidFuzz) | 13 | 75x | 0.970 (~0.03 diff) |
| Cosine (vectors) | 3 | 333x | N/A (semantic) |

### Accuracy Comparison

```python
# Sample comparison
state = [["m1"], ["m2"], ["m3"]]
pattern = [["m1"], ["m2"], ["m3"], ["m4"], ["m5"], ["m6"], ["m7"]]

# Scores
difflib_score = 0.6000
token_score = 0.6000  # Exact match
character_score = 0.5714  # ~0.03 difference
```

## Selection Guidelines

### Decision Tree

```
Is data vectorized?
├─ Yes → Use Cosine Similarity
└─ No → Is data pre-tokenized?
    ├─ Yes → Need exact difflib compatibility?
    │   ├─ Yes → Use Token-Level
    │   └─ No → Use Character-Level (faster)
    └─ No → Use Character-Level
```

### Production Recommendations

**High-Throughput Systems**:
```bash
# Use character-level for speed
export KATO_USE_TOKEN_MATCHING=false
export KATO_USE_FAST_MATCHING=true
```

**Regulatory/Compliance Systems**:
```bash
# Use token-level for exactness
export KATO_USE_TOKEN_MATCHING=true
```

**Hybrid Systems**:
```python
# Use different metrics for different phases
# Phase 1: Character-level for filtering (fast)
candidates = fast_filter(patterns, threshold=0.3)

# Phase 2: Token-level for ranking (accurate)
ranked = [token_similarity(c, query) for c in candidates]
```

### Cost-Accuracy Tradeoff

```python
def select_similarity_metric(accuracy_required, performance_budget):
    """
    Select metric based on requirements.
    """
    if accuracy_required == "exact":
        return TokenSimilarity()
    elif performance_budget == "low":
        return CharacterSimilarity()
    elif data_type == "vectors":
        return CosineSimilarity()
    else:
        # Balanced
        return CharacterSimilarity()
```

## Implementation Details

### Caching Strategies

```python
from functools import lru_cache

@lru_cache(maxsize=10000)
def cached_similarity(pattern_id, query_hash):
    """
    Cache similarity calculations.

    Speeds up repeated queries.
    """
    pattern = kb.get_pattern(pattern_id)
    query = deserialize_query(query_hash)
    return calculate_similarity(pattern, query)
```

### Batch Processing

```python
def batch_similarity(patterns, query, metric="character"):
    """
    Calculate similarities in batch for efficiency.
    """
    if metric == "character":
        from rapidfuzz import process

        # Batch processing in RapidFuzz
        query_str = " ".join(query)
        pattern_strs = [" ".join(p.events) for p in patterns]

        results = process.extract(query_str, pattern_strs, limit=len(patterns))
        return [(score/100.0, idx) for _, score, idx in results]

    else:
        # Sequential processing
        return [(calculate_similarity(p, query), i) for i, p in enumerate(patterns)]
```

### Optimization Techniques

**Early Termination**:
```python
def quick_reject(pattern, query, threshold):
    """
    Fast rejection without full calculation.
    """
    # Length-based bound
    len_ratio = min(len(pattern), len(query)) / max(len(pattern), len(query))
    if len_ratio < threshold:
        return True  # Reject

    # Symbol overlap bound
    pattern_symbols = set(get_all_symbols(pattern))
    query_symbols = set(get_all_symbols(query))
    overlap = len(pattern_symbols & query_symbols)
    max_possible_sim = overlap / len(pattern_symbols | query_symbols)

    if max_possible_sim < threshold:
        return True  # Reject

    return False  # Cannot reject, must calculate
```

## Related Documentation

- [Pattern Matching](pattern-matching.md) - Complete matching system
- [Vector Processing](vector-processing.md) - Vector operations
- [Core Concepts](core-concepts.md) - KATO fundamentals
- [Performance Tuning](../operations/performance-tuning.md) - Optimization

---

**Last Updated**: November 2025
**KATO Version**: 3.0+
