# KATO Pattern Matching System

## Table of Contents
1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Algorithms](#algorithms)
4. [Configuration](#configuration)
5. [Performance](#performance)
6. [Implementation Flow](#implementation-flow)
7. [Examples](#examples)
8. [Troubleshooting](#troubleshooting)

## Overview

KATO uses a sophisticated multi-layered pattern matching system to identify and compare sequences of symbols. The system is designed to be both fast and accurate, with configurable trade-offs between performance and precision.

### Key Characteristics
- **Deterministic**: Same inputs always produce same outputs
- **Scalable**: ~300x performance improvement over naive approaches
- **Configurable**: Multiple optimization levels can be enabled/disabled
- **Graceful Degradation**: System maintains functionality even with optimizations disabled

## Architecture

KATO's pattern matching uses a **layered architecture** where each layer can be independently enabled or disabled:

```
┌─────────────────────────────────────────────┐
│           Application Layer                 │
│         (PatternSearcher API)               │
└─────────────────┬───────────────────────────┘
                  │
┌─────────────────▼───────────────────────────┐
│          Indexing Layer                     │
│   (Optional - KATO_USE_INDEXING=true)       │
│   • Inverted Index                          │
│   • Bloom Filter                            │
│   • Length Partitioning                     │
└─────────────────┬───────────────────────────┘
                  │
┌─────────────────▼───────────────────────────┐
│       Fast Matching Layer                   │
│  (Optional - KATO_USE_FAST_MATCHING=true)   │
│   • Rabin-Karp Rolling Hash                 │
│   • N-gram Indexing                         │
│   • RapidFuzz (if installed)                │
└─────────────────┬───────────────────────────┘
                  │
┌─────────────────▼───────────────────────────┐
│         Core Algorithm Layer                │
│     (Always Active - SequenceMatcher)       │
│   • Longest Common Subsequence              │
│   • Detailed Match Extraction               │
└─────────────────────────────────────────────┘
```

## Algorithms

### 1. Core Algorithm: SequenceMatcher

**Location**: `kato/informatics/extractor.py`

The foundation of KATO's pattern matching is the SequenceMatcher algorithm, based on Python's difflib. This algorithm is **always active** and provides the final detailed matching information.

**How it works**:
- Finds the longest contiguous matching subsequence between two sequences
- Recursively applies to remaining segments
- Produces "human-friendly" matches rather than minimal edit sequences

**Capabilities**:
- Exact matching block identification
- Temporal region extraction (past/present/future)
- Missing and extra symbol detection
- Similarity ratio calculation

**Example**:
```python
# Comparing sequences ['A', 'B', 'C', 'D'] and ['B', 'C', 'E']
# Produces:
# - Matching blocks: [(1, 0, 2)] meaning indices 1-2 of first match 0-1 of second
# - Similarity: 0.57 (4 matches out of 7 total elements)
```

### 2. Fast Matching Layer

**Location**: `kato/searches/fast_matcher.py`

This optional layer provides rapid filtering and similarity calculations.

#### 2.1 Rabin-Karp Rolling Hash
- **Purpose**: Quick equality checking and sliding window search
- **Complexity**: O(1) for window updates
- **Use Case**: Fast filtering of exact matches or fixed-length patterns

**Algorithm**:
```
hash(sequence) = (s[0]*p^(n-1) + s[1]*p^(n-2) + ... + s[n-1]) mod m
where p = prime number (101), m = large prime (2^31 - 1)
```

#### 2.2 N-gram Indexing
- **Purpose**: Similarity search based on subsequence overlap
- **Default**: 3-grams (trigrams)
- **Metric**: Jaccard similarity between n-gram sets

**Example**:
```python
# Sequence: ['A', 'B', 'C', 'D']
# 3-grams: {('A','B','C'), ('B','C','D')}
# Similarity calculated as: |intersection| / |union|
```

#### 2.3 RapidFuzz Integration (Optional)
- **Purpose**: ~10x faster similarity calculations
- **Installation**: `pip install rapidfuzz`
- **Fallback**: Automatically uses SequenceMatcher if not available
- **Algorithm**: Optimized Levenshtein distance calculations

### 3. Indexing Layer

**Location**: `kato/searches/index_manager.py`

This layer dramatically reduces the search space before detailed matching.

#### 3.1 Inverted Index
- **Structure**: Maps each symbol to patterns containing it
- **Purpose**: Fast candidate filtering
- **Modes**: AND (all symbols must be present) or OR (any symbol)

**Example**:
```python
# Index structure:
{
    'A': {'pattern1', 'pattern3'},
    'B': {'pattern1', 'pattern2'},
    'C': {'pattern2', 'pattern3'}
}
# Query ['A', 'B'] with AND mode returns: {'pattern1'}
```

#### 3.2 Bloom Filter
- **Purpose**: Probabilistic data structure for fast negative lookups
- **Guarantee**: If bloom filter says "not present", it's definitely not there
- **Trade-off**: May have false positives but never false negatives
- **Size**: 10,000 bits with 3 hash functions by default

#### 3.3 Length-Partitioned Index
- **Purpose**: Groups patterns by length for faster search
- **Partition Size**: 10 symbols by default
- **Tolerance**: Configurable search range around target length

**Example**:
```python
# Patterns of length 0-9 in partition 0
# Patterns of length 10-19 in partition 1
# Searching for length 15 primarily checks partition 1
```

## Configuration

### Environment Variables

| Variable | Default | Description | Impact |
|----------|---------|-------------|--------|
| `KATO_USE_FAST_MATCHING` | `true` | Enable fast matching algorithms | ~10x performance improvement |
| `KATO_USE_INDEXING` | `true` | Enable pattern indexing | Reduces candidates from O(n) to O(log n) |
| `RECALL_THRESHOLD` | `0.1` | Minimum similarity for matches (0.0-1.0) | Lower = more results, Higher = stricter |
| `MAX_PREDICTIONS` | `100` | Maximum predictions to return | Limits result set size |

### Configuration Examples

#### Maximum Performance (Default)
```bash
export KATO_USE_FAST_MATCHING=true
export KATO_USE_INDEXING=true
export RECALL_THRESHOLD=0.1
```

#### Maximum Accuracy (Slower)
```bash
export KATO_USE_FAST_MATCHING=false  # Use only SequenceMatcher
export KATO_USE_INDEXING=false       # Check all patterns
export RECALL_THRESHOLD=0.01         # Very permissive matching
```

#### Balanced Configuration
```bash
export KATO_USE_FAST_MATCHING=true
export KATO_USE_INDEXING=true
export RECALL_THRESHOLD=0.5          # Moderate filtering
```

## Performance

### Benchmarks

| Configuration | Patterns | Query Time | Relative Speed |
|--------------|----------|------------|----------------|
| Naive (no optimizations) | 10,000 | ~3000ms | 1x |
| With Indexing | 10,000 | ~300ms | 10x |
| With Fast Matching | 10,000 | ~100ms | 30x |
| Full Optimizations | 10,000 | ~10ms | 300x |
| + RapidFuzz | 10,000 | ~3ms | 1000x |

### Memory Usage

| Component | Memory Overhead | When to Use |
|-----------|----------------|-------------|
| Base SequenceMatcher | Minimal | Always active |
| Inverted Index | O(unique_symbols × patterns) | Default on |
| Bloom Filter | 10KB fixed | Default on |
| N-gram Index | O(patterns × n-grams) | Default on |
| Suffix Arrays | O(pattern_length²) | Disabled by default (memory intensive) |

## Implementation Flow

### Pattern Matching Process

```python
def match_patterns(query, patterns):
    # 1. INDEXING LAYER (if enabled)
    if KATO_USE_INDEXING:
        # Quick negative check
        if not bloom_filter.possibly_contains(query):
            return []
        
        # Filter by length
        candidates = length_index.get_candidates(len(query))
        
        # Filter by symbol presence
        candidates &= inverted_index.search(query)
    else:
        candidates = all_patterns
    
    # 2. FAST MATCHING LAYER (if enabled)
    if KATO_USE_FAST_MATCHING:
        if rapidfuzz_available:
            # Use RapidFuzz for batch similarity
            similarities = rapidfuzz.process.extract(query, candidates)
        else:
            # Use n-gram similarity
            similarities = ngram_index.calculate_similarities(query, candidates)
        
        # Filter by recall threshold
        candidates = filter(lambda p: similarity(p) >= RECALL_THRESHOLD, candidates)
    
    # 3. CORE ALGORITHM LAYER (always active)
    results = []
    for pattern in candidates:
        # Detailed extraction using SequenceMatcher
        matcher = SequenceMatcher(pattern, query)
        
        if matcher.ratio() >= RECALL_THRESHOLD:
            # Extract temporal regions
            matching_blocks = matcher.get_matching_blocks()
            past, present, future = extract_temporal_regions(matching_blocks)
            missing, extras = extract_anomalies(pattern, query)
            
            results.append({
                'pattern': pattern,
                'similarity': matcher.ratio(),
                'past': past,
                'present': present,
                'future': future,
                'missing': missing,
                'extras': extras
            })
    
    return results
```

## Examples

### Example 1: Basic Pattern Matching

```python
# Learned pattern
pattern = [['A'], ['B'], ['C'], ['D']]

# Observation
observation = [['B'], ['C']]

# Matching process:
# 1. Index lookup finds pattern contains 'B' and 'C'
# 2. Fast matching calculates rough similarity: 0.5
# 3. SequenceMatcher extracts:
#    - past: [['A']]
#    - present: [['B'], ['C']]
#    - future: [['D']]
#    - similarity: 0.5
```

### Example 2: Partial Matching with Extras

```python
# Learned pattern
pattern = [['apple', 'banana'], ['cherry']]

# Observation (sorted automatically)
observation = [['banana', 'apple', 'date'], ['cherry', 'elderberry']]

# Result:
# - matches: ['apple', 'banana', 'cherry']
# - extras: ['date', 'elderberry']
# - missing: []
# - similarity: 0.6
```

### Example 3: Configuration Impact

```python
# Pattern database: 50,000 patterns
# Query: ['sensor_1', 'sensor_2', 'alert']

# Configuration 1: All optimizations
KATO_USE_INDEXING=true
KATO_USE_FAST_MATCHING=true
# Result: 15 matches in 12ms

# Configuration 2: No optimizations
KATO_USE_INDEXING=false
KATO_USE_FAST_MATCHING=false
# Result: 15 matches in 3500ms

# Configuration 3: Stricter threshold
RECALL_THRESHOLD=0.8
# Result: 3 matches in 8ms (fewer results to process)
```

## Troubleshooting

### Issue: Too Many Predictions

**Symptom**: Receiving hundreds of low-quality predictions

**Solution**: Increase `RECALL_THRESHOLD`
```bash
export RECALL_THRESHOLD=0.5  # Default is 0.1
```

### Issue: Missing Expected Matches

**Symptom**: Known patterns not appearing in predictions

**Possible Causes**:
1. Threshold too high - reduce `RECALL_THRESHOLD`
2. Pattern not learned - check with `/patterns` endpoint
3. Insufficient STM content - need at least 2 strings

### Issue: Slow Performance

**Symptom**: Pattern matching takes >100ms

**Solutions**:
1. Enable optimizations:
   ```bash
   export KATO_USE_FAST_MATCHING=true
   export KATO_USE_INDEXING=true
   ```

2. Install RapidFuzz:
   ```bash
   pip install rapidfuzz
   ```

3. Reduce `MAX_PREDICTIONS` to limit result processing

### Issue: High Memory Usage

**Symptom**: Container using excessive memory

**Solutions**:
1. Disable suffix arrays (already off by default)
2. Increase bloom filter size for better filtering:
   ```python
   # In code: BloomFilter(size=50000)  # Larger but more accurate
   ```

### Issue: Non-Deterministic Results

**Symptom**: Same query produces different results

**This should never happen** - KATO is fully deterministic. If observed:
1. Check for concurrent modifications to pattern database
2. Verify `session_id` isolation
3. Report as bug with reproduction steps

## Advanced Topics

### Custom Similarity Metrics

While KATO uses ratio-based similarity by default, the system calculates multiple metrics:

- **Ratio**: 2.0 * matches / (len(seq1) + len(seq2))
- **Quick Ratio**: Upper bound estimate (faster)
- **Real Quick Ratio**: Very rough upper bound (fastest)

### Parallel Processing

PatternSearcher uses multiprocessing for parallel pattern evaluation:
```python
self.procs = multiprocessing.cpu_count()
```

### Database Considerations

- Patterns are indexed by SHA1 hash for O(1) lookup
- MongoDB queries use indexed fields
- Qdrant uses HNSW algorithm for vector similarity

## See Also

- [Configuration Management](CONFIGURATION_MANAGEMENT.md)
- [System Overview](SYSTEM_OVERVIEW.md)
- [API Reference](API_REFERENCE.md)
- [Performance Tuning](deployment/PERFORMANCE_TUNING.md)