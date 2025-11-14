# KATO Filter Pipeline Configuration Guide

## Table of Contents
1. [Overview](#overview)
2. [Filter Types](#filter-types)
3. [MinHash & LSH Deep Dive](#minhash--lsh-deep-dive)
4. [Filter Selection Guide](#filter-selection-guide)
5. [Pipeline Design Patterns](#pipeline-design-patterns)
6. [Common Pitfalls & Solutions](#common-pitfalls--solutions)
7. [Examples & Case Studies](#examples--case-studies)

## Overview

KATO's filter pipeline is a multi-stage system that efficiently reduces billions of candidate patterns to a manageable set for final matching. The pipeline operates in two phases:

1. **Filtering Phase**: Database and Python-side filters reduce candidates (billions → hundreds)
2. **Matching Phase**: RapidFuzz performs final similarity calculation on filtered candidates

### Why Filtering is Critical

Without filtering, pattern matching would require:
- Loading all patterns into memory (GB-TB scale)
- O(n) comparisons where n = total patterns
- Minutes to hours for large datasets

With filtering:
- Only filtered candidates loaded into memory (MB scale)
- O(log n) or O(1) candidate retrieval
- Milliseconds to seconds for billion-scale datasets

## Filter Types

### Database Filters (ClickHouse-side)

These filters run as SQL queries, leveraging ClickHouse's columnar storage and indexed fields.

#### 1. LengthFilter
**Type**: Database-side
**Complexity**: O(log n) with indexing
**Purpose**: Filter by pattern length relative to STM length

```python
config = SessionConfiguration(
    filter_pipeline=['length'],
    length_min_ratio=0.5,    # Min pattern length = 50% of STM
    length_max_ratio=2.0     # Max pattern length = 200% of STM
)
```

**When to use:**
- First stage in pipeline (very fast elimination)
- When most patterns have similar length (less effective)
- As sanity check to prevent absurd matches

**Performance:**
- 1M patterns → <10ms (indexed field scan)
- 1B patterns → <100ms (partition pruning + index)

---

#### 2. JaccardFilter
**Type**: Database-side
**Complexity**: O(n) but fast with ClickHouse array functions
**Purpose**: Exact token set overlap calculation

```python
config = SessionConfiguration(
    filter_pipeline=['jaccard'],
    jaccard_threshold=0.3,       # Min Jaccard similarity (0.0-1.0)
    jaccard_min_overlap=2        # Min absolute token overlap count
)
```

**Mathematics:**
```
Jaccard Similarity = |A ∩ B| / |A ∪ B|

Example:
STM tokens:     {A, B, C, D}
Pattern tokens: {B, C, E, F}
Intersection:   {B, C} → size = 2
Union:          {A, B, C, D, E, F} → size = 6
Jaccard = 2/6 = 0.333
```

**When to use:**
- **Best for 100K-10M patterns** (exact, fast, scalable)
- Early prediction with partial token matches
- When you need exact similarity (not approximate)

**Performance:**
- 1M patterns → 50-200ms (depends on token set sizes)
- 10M patterns → 500ms-2s (still very fast!)

**Why it's better than MinHash for most cases:**
- ✅ **Exact calculation** (no false negatives)
- ✅ **Works at any similarity threshold** (0.0-1.0)
- ✅ **No parameter tuning required**
- ✅ **Faster than MinHash for <10M patterns**

---

### Hybrid Filters (Database + Python)

#### 3. MinHashFilter
**Type**: Hybrid (Database stage + Python verification)
**Complexity**: O(1) database lookup, O(k) Python verification
**Purpose**: Approximate Jaccard similarity for billion-scale datasets

```python
config = SessionConfiguration(
    filter_pipeline=['minhash'],
    minhash_threshold=0.7,       # Estimated Jaccard threshold
    minhash_bands=20,            # Number of LSH bands
    minhash_rows=5,              # Rows per band
    minhash_num_hashes=100       # Total hash functions (bands × rows)
)
```

**⚠️ CRITICAL: MinHash has strict parameter requirements. See [MinHash & LSH Deep Dive](#minhash--lsh-deep-dive) before using.**

**When to use:**
- **ONLY for >10M patterns** (billion-scale)
- High-similarity matching (threshold ≥ 0.7)
- When performance is critical and approximate matching is acceptable

**When NOT to use:**
- <10M patterns → Use JaccardFilter instead (faster + exact)
- Low similarity thresholds (<0.4) → Use JaccardFilter or tune LSH parameters
- Need exact matching → Use JaccardFilter

---

### Python-side Filters

#### 4. BloomFilterStage
**Type**: Python-side
**Complexity**: O(1) per pattern
**Purpose**: Fast token presence checking

```python
config = SessionConfiguration(
    filter_pipeline=['bloom'],
    bloom_false_positive_rate=0.01  # 1% false positive rate
)
```

**When to use:**
- After database filters (operates on candidates in memory)
- Quick elimination of patterns with zero token overlap
- When memory allows (requires pre-built Bloom filter)

**Note**: Requires Bloom filter instance to be built and passed to executor.

---

#### 5. RapidFuzzFilter
**Type**: Python-side
**Complexity**: O(n × m) per pattern (optimized)
**Purpose**: Fast similarity calculation using RapidFuzz library

```python
config = SessionConfiguration(
    filter_pipeline=['rapidfuzz'],
    recall_threshold=0.3,          # Min similarity (0.0-1.0)
    use_token_matching=True        # Token-level vs character-level
)
```

**When to use:**
- **Final stage only** (after aggressive pre-filtering)
- On small candidate sets (<1000 patterns)
- When you need sequence similarity (not just set overlap)

**When NOT to use:**
- First stage (too slow for large candidate sets)
- Without prior filtering (will timeout)

---

## MinHash & LSH Deep Dive

### What is MinHash?

MinHash is an **approximate algorithm** for estimating Jaccard similarity between sets using **Locality-Sensitive Hashing (LSH)**.

**Key Insight**: If two sets have high Jaccard similarity, their MinHash signatures will likely match in at least one LSH band.

### LSH Mathematical Foundation

#### Core Probability Formula

```
P(collision) ≈ 1 - (1 - J^r)^b

Where:
  J = Jaccard similarity (0.0 to 1.0)
  r = rows per band
  b = number of bands

Constraint: b × r = num_hashes (total signature size)
```

#### What This Means

- **P(collision)**: Probability that two patterns share at least one matching LSH band
- **If P(collision) is high**: Patterns likely to be retrieved by database query (good recall)
- **If P(collision) is low**: Patterns likely to be missed (false negative)

### Probability Curves

For **default parameters** (bands=20, rows=5):

| Jaccard | P(collision) | Recall Rate | Interpretation |
|---------|--------------|-------------|----------------|
| 0.9     | ~99.9%       | Excellent   | Almost always found |
| 0.8     | ~98%         | Excellent   | Very reliable |
| **0.7** | **~95%**     | **Good**    | **Design target** |
| 0.6     | ~70%         | Moderate    | Significant false negatives |
| 0.5     | ~40%         | Poor        | Most patterns missed |
| 0.4     | ~15%         | Very Poor   | Rarely found |
| 0.3     | ~5%          | Terrible    | Almost never found |
| 0.2     | ~1%          | Unusable    | Effectively zero recall |
| **0.1** | **~0%**      | **Unusable**| **Won't work at all** |

**This explains why `minhash_threshold=0.1` with default LSH parameters fails!**

### Tuning LSH Parameters

#### Target: High Similarity (J ≥ 0.7) ✅ Default Works

```python
config = SessionConfiguration(
    minhash_bands=20,
    minhash_rows=5,
    minhash_num_hashes=100,  # 20 × 5 = 100
    minhash_threshold=0.7
)
```

**Probability curve peaks at J=0.7 with ~95% recall.**

---

#### Target: Medium Similarity (J ≥ 0.4)

```python
config = SessionConfiguration(
    minhash_bands=40,          # Increase bands
    minhash_rows=3,            # Decrease rows
    minhash_num_hashes=120,    # 40 × 3 = 120
    minhash_threshold=0.4
)
```

**Probability table:**

| Jaccard | P(collision) | Notes |
|---------|--------------|-------|
| 0.7     | ~99.9%       | Still excellent for high similarity |
| 0.6     | ~95%         | Good recall |
| 0.5     | ~70%         | Acceptable |
| **0.4** | **~40%**     | **Target threshold** (moderate recall) |
| 0.3     | ~15%         | Poor |

**Trade-off**: More bands = more database rows = slower query, but better recall at lower thresholds.

---

#### Target: Low Similarity (J ≥ 0.2) ⚠️ Not Recommended

```python
config = SessionConfiguration(
    minhash_bands=100,         # Many bands
    minhash_rows=2,            # Very few rows
    minhash_num_hashes=200,    # 100 × 2 = 200
    minhash_threshold=0.2
)
```

**Why this is problematic:**
- ❌ 100 bands = 100x database storage
- ❌ Query still has <50% recall at J=0.2
- ❌ ClickHouse query becomes slow (scanning 100 band arrays)
- ✅ **Better solution**: Use JaccardFilter (exact, faster, simpler)

---

### How to Calculate Optimal Parameters

**Given**: Target similarity threshold `t` and desired recall rate `p`

**Steps**:

1. **Choose total hash functions** (`num_hashes`):
   - Start with 100 (standard)
   - Increase for better precision (120, 150, 200)

2. **Choose rows per band** (`r`):
   - Lower threshold → smaller `r` (more bands)
   - Rule of thumb: `r ≈ -log(t) / log(2)` (heuristic)

3. **Calculate bands** (`b`):
   - `b = num_hashes / r`

4. **Verify probability**:
   - `P(collision) ≈ 1 - (1 - t^r)^b`
   - Adjust `r` until `P(collision) ≈ p` (desired recall)

**Example**: Target J=0.5 with 90% recall

```python
# Try r=3
r = 3
num_hashes = 120
b = 120 / 3 = 40

# Calculate P(collision)
J = 0.5
P = 1 - (1 - J**r)**b
P = 1 - (1 - 0.125)**40
P ≈ 0.995  # Too high! Over-filtered

# Try r=4
r = 4
b = 120 / 4 = 30
P = 1 - (1 - 0.5**4)**30
P = 1 - (1 - 0.0625)**30
P ≈ 0.85  # Close to 90% target!

# Final configuration:
minhash_bands = 30
minhash_rows = 4
minhash_num_hashes = 120
```

---

### MinHash Limitations Summary

| Limitation | Impact | Solution |
|------------|--------|----------|
| **Approximate** | False negatives possible | Use Jaccard for exact matching |
| **Parameter-dependent** | Wrong params = no results | Tune bands/rows for your threshold |
| **High-similarity bias** | Default tuned for J≥0.7 | Recalculate for lower thresholds |
| **Storage overhead** | Each band = array in DB | Use only for billion-scale |
| **Query complexity** | More bands = slower query | Limit bands to <50 |

---

## Filter Selection Guide

### By Dataset Size

```
Pattern Count Decision Tree:

< 100,000
  └─> ['jaccard', 'rapidfuzz']
      • Jaccard handles 100K easily (50-100ms)
      • No need for length or MinHash
      • Simple, exact, fast

100,000 - 1,000,000
  └─> ['length', 'jaccard', 'rapidfuzz']
      • Length pre-filter (10ms)
      • Jaccard main filter (100-500ms)
      • Still fast enough without MinHash

1,000,000 - 10,000,000
  └─> ['length', 'jaccard', 'rapidfuzz']
      • Jaccard can handle 10M in 1-2s
      • Consider MinHash only if Jaccard too slow
      • Test both to see which is faster for your data

> 10,000,000 (billion-scale)
  └─> ['minhash', 'jaccard', 'rapidfuzz']
      • MinHash essential for performance
      • Tune LSH parameters for your threshold!
      • Jaccard refines MinHash candidates
```

---

### By Similarity Threshold

```
Threshold Decision Tree:

High Similarity (threshold ≥ 0.7)
  ├─ <10M patterns → ['jaccard']
  └─ >10M patterns → ['minhash'] with default params

Medium Similarity (0.4 ≤ threshold < 0.7)
  ├─ <10M patterns → ['jaccard']
  └─ >10M patterns → ['minhash'] with tuned params
                      (bands=40, rows=3)

Low Similarity (threshold < 0.4)
  └─ Use ['jaccard'] regardless of size
      • MinHash recall too poor at low thresholds
      • Jaccard is exact and faster for this case
```

---

### By Performance Requirements

```
Latency Budget Decision Tree:

< 10ms (real-time)
  └─> Reduce candidates first:
      • Use aggressive filters: ['length', 'jaccard']
      • High thresholds (jaccard ≥ 0.5)
      • Pre-compute indexes

10-100ms (interactive)
  └─> Balanced approach:
      • ['length', 'jaccard', 'rapidfuzz']
      • Moderate thresholds

100-1000ms (batch)
  └─> Can use slower filters:
      • ['minhash', 'jaccard', 'bloom', 'rapidfuzz']
      • Lower thresholds for better recall

> 1000ms (background)
  └─> Optimize for recall, not speed:
      • Lower thresholds
      • More comprehensive filtering
      • Consider removing MinHash (exact Jaccard)
```

---

## Pipeline Design Patterns

### Pattern 1: Sequential Refinement (Default)

**How it works**: Each filter refines the previous filter's candidates.

```python
filter_pipeline = ['minhash', 'jaccard', 'rapidfuzz']

# Execution flow:
# MinHash:    1,000,000,000 → 10,000 candidates (DB query)
# Jaccard:    10,000 → 100 candidates (refined DB query on MinHash results)
# RapidFuzz:  100 → 10 final matches (Python in-memory)
```

**Advantages:**
- ✅ Maximum reduction (billions → tens)
- ✅ Each stage operates on smaller set
- ✅ Very fast overall

**Disadvantages:**
- ❌ **False negatives propagate**: If MinHash misses a pattern, Jaccard never sees it
- ❌ Order matters critically
- ❌ Approximate filters hurt exact filters downstream

**When to use**: When filters are **compatible** (all high-threshold or all exact)

---

### Pattern 2: Database-Only Refinement

**How it works**: Only database filters refine each other; Python filters see all database results.

```python
filter_pipeline = ['length', 'jaccard']

# Execution flow:
# Length:     1,000,000 → 500,000 candidates (DB query)
# Jaccard:    500,000 → 1,000 candidates (refined DB query)
# (RapidFuzz runs separately in matching phase)
```

**Advantages:**
- ✅ All database filters are exact (no false negatives)
- ✅ Fast database-side reduction
- ✅ Python matching sees all valid candidates

**Disadvantages:**
- ❌ More candidates reach Python stage
- ❌ Missing MinHash (if billion-scale)

**When to use:**
- **Most recommended for <10M patterns**
- When you need exact matching
- When you can tolerate longer runtime

---

### Pattern 3: Parallel Union (Future Enhancement)

**How it works**: Filters run independently, results are unioned.

```python
# Not yet implemented - future feature
filter_pipeline_mode = 'union'
filter_pipeline = ['minhash', 'jaccard']

# Execution flow:
# MinHash:  1,000,000,000 → 10,000 candidates (independent query)
# Jaccard:  1,000,000,000 → 5,000 candidates (independent query)
# Union:    10,000 ∪ 5,000 → 12,000 candidates (de-duplicated)
```

**Advantages:**
- ✅ No false negative propagation
- ✅ Each filter sees all patterns
- ✅ Combines strengths of multiple approaches

**Disadvantages:**
- ❌ More database queries
- ❌ Higher total candidate count
- ❌ Not yet implemented

---

## Common Pitfalls & Solutions

### Pitfall 1: Using MinHash with Low Threshold

**Symptom**: No predictions returned with `minhash_threshold=0.1`

**Why it fails:**
```python
# Your configuration
config = SessionConfiguration(
    filter_pipeline=['minhash'],
    minhash_threshold=0.1,       # LOW threshold
    minhash_bands=20,            # DEFAULT parameters
    minhash_rows=5
)

# Actual behavior
# STM tokens: {A, B, C} (3 tokens)
# Pattern tokens: {A, B, C, D, E, F, G, H} (8 tokens)
# Jaccard = 3/8 = 0.375
# LSH P(collision) with J=0.375 and (b=20, r=5) ≈ 5%
# Result: 95% chance pattern is missed! ❌
```

**Solution 1: Use JaccardFilter instead**
```python
config = SessionConfiguration(
    filter_pipeline=['jaccard'],  # Exact matching
    jaccard_threshold=0.2,         # Works at any threshold
    jaccard_min_overlap=2
)
```

**Solution 2: Tune MinHash parameters**
```python
config = SessionConfiguration(
    filter_pipeline=['minhash'],
    minhash_threshold=0.3,
    minhash_bands=50,      # More bands
    minhash_rows=2,        # Fewer rows
    minhash_num_hashes=100
)
# Now P(collision) at J=0.375 ≈ 40% (better, but still lossy)
```

---

### Pitfall 2: MinHash → Jaccard Pipeline Order

**Symptom**: `filter_pipeline=['minhash', 'jaccard']` returns fewer results than `['jaccard']` alone

**Why it fails:**
```python
# Pattern exists in database: Jaccard = 0.35
# MinHash threshold: 0.1 (very permissive)

# What you expect:
# - MinHash passes everything ≥0.1 → includes pattern at 0.35
# - Jaccard refines to ≥0.3 → includes pattern at 0.35 ✅

# What actually happens:
# - MinHash LSH bands don't match (P(collision) ≈ 5% at J=0.35)
# - MinHash returns 0 candidates (probabilistic miss)
# - Jaccard only queries MinHash's 0 candidates
# - Pattern never found, even though it passes both thresholds! ❌
```

**Root cause**: MinHash's false negatives prevent Jaccard from seeing valid patterns.

**Solution 1: Use Jaccard alone**
```python
config = SessionConfiguration(
    filter_pipeline=['jaccard'],  # No false negatives
    jaccard_threshold=0.3
)
```

**Solution 2: Reverse order (if MinHash properly tuned)**
```python
config = SessionConfiguration(
    filter_pipeline=['jaccard', 'bloom'],  # Exact filter first
    jaccard_threshold=0.3
)
# MinHash not needed for <10M patterns
```

---

### Pitfall 3: Using RapidFuzz as First Filter

**Symptom**: Requests timeout or take minutes

**Why it fails:**
```python
config = SessionConfiguration(
    filter_pipeline=['rapidfuzz'],
    recall_threshold=0.3
)

# With 1M patterns:
# RapidFuzz runs on ALL 1M patterns (no pre-filtering)
# O(n × m) similarity calculation × 1M
# Result: 30-60 seconds per query ❌
```

**Solution: Use database filters first**
```python
config = SessionConfiguration(
    filter_pipeline=['jaccard', 'rapidfuzz'],
    jaccard_threshold=0.25,
    recall_threshold=0.3
)

# Now:
# Jaccard: 1M → 100 candidates (200ms)
# RapidFuzz: 100 candidates (10ms)
# Total: 210ms ✅
```

---

### Pitfall 4: Threshold Confusion

**Symptom**: Different thresholds for different filters, unclear behavior

**Why it's confusing:**
```python
config = SessionConfiguration(
    filter_pipeline=['minhash', 'jaccard'],
    minhash_threshold=0.5,    # Applies to MinHash Jaccard estimation
    jaccard_threshold=0.3,    # Applies to exact Jaccard calculation
    recall_threshold=0.2      # Applies to final RapidFuzz matching
)

# Three different thresholds! Which one matters?
```

**Understanding:**
- **minhash_threshold**: Filters MinHash's Python verification stage (after LSH bands)
- **jaccard_threshold**: Filters Jaccard's database query
- **recall_threshold**: Filters final RapidFuzz matching

**Solution: Keep thresholds aligned**
```python
# Recommended: Consistent thresholds
config = SessionConfiguration(
    filter_pipeline=['jaccard'],
    jaccard_threshold=0.3,
    recall_threshold=0.3       # Same threshold
)

# Or: Progressive tightening
config = SessionConfiguration(
    filter_pipeline=['minhash', 'jaccard'],
    minhash_threshold=0.2,     # Loose filter (high recall)
    jaccard_threshold=0.3,     # Medium filter
    recall_threshold=0.5       # Strict filter (high precision)
)
```

---

### Pitfall 5: Empty Filter Pipeline

**Symptom**: Setting `filter_pipeline=[]` causes no predictions

**Why it fails (before fix):**
```python
# Old behavior (bug):
config = SessionConfiguration(
    filter_pipeline=[]  # Empty pipeline
)
# Executor returned 0 candidates (no filtering = no patterns!)
```

**Current behavior (after fix):**
```python
# New behavior:
config = SessionConfiguration(
    filter_pipeline=[]  # Empty pipeline
)
# Executor queries ALL patterns from database
# With 1.2M patterns → TIMEOUT (not practical)
```

**Solution: Use minimal filter**
```python
config = SessionConfiguration(
    filter_pipeline=['jaccard'],
    jaccard_threshold=0.1  # Very permissive
)
# Fast, exact, scalable
```

---

## Examples & Case Studies

### Case Study 1: Early Prediction with Partial Matches

**Scenario**: Predict next token after observing only 3 tokens from an 8-token pattern.

**Pattern in database:**
```python
pattern = ['Ġinfect', 's', 'Ġsmall', 'Ġrodents', 'Ġand', 'Ġamphib', 'ians', 'Ġthat']
# 8 unique tokens
```

**Observed STM:**
```python
stm = ['Ġinfect', 's', 'Ġsmall']
# 3 unique tokens
```

**Jaccard calculation:**
```
Intersection: {Ġinfect, s, Ġsmall} = 3 tokens
Union: {Ġinfect, s, Ġsmall, Ġrodents, Ġand, Ġamphib, ians, Ġthat} = 8 tokens
Jaccard = 3/8 = 0.375
```

**Configuration that works:**
```python
config = SessionConfiguration(
    filter_pipeline=['jaccard'],
    jaccard_threshold=0.25,      # Below 0.375 ✅
    jaccard_min_overlap=3,       # Exactly 3 tokens ✅
    recall_threshold=0.3         # Final matching threshold
)

# Result:
# - Jaccard finds pattern (0.375 > 0.25)
# - RapidFuzz validates sequence similarity
# - Prediction: future=['Ġrodents', 'Ġand', 'Ġamphib', 'ians', 'Ġthat']
```

**Configuration that fails:**
```python
config = SessionConfiguration(
    filter_pipeline=['minhash'],
    minhash_threshold=0.1,        # LOW threshold
    minhash_bands=20,             # DEFAULT parameters
    minhash_rows=5
)

# Result:
# - MinHash LSH: P(collision) at J=0.375 ≈ 5%
# - Pattern likely missed by LSH bands
# - No predictions returned ❌
```

---

### Case Study 2: Billion-Scale Pattern Database

**Scenario**: 1 billion patterns, need to find matches in <100ms.

**Configuration:**
```python
config = SessionConfiguration(
    filter_pipeline=['minhash', 'jaccard'],

    # MinHash stage (billion → thousands)
    minhash_threshold=0.6,
    minhash_bands=20,
    minhash_rows=5,

    # Jaccard stage (thousands → hundreds)
    jaccard_threshold=0.7,
    jaccard_min_overlap=5,

    # Final matching
    recall_threshold=0.7
)
```

**Performance breakdown:**
```
Stage 1 (MinHash DB):  1,000,000,000 → 10,000 patterns  (30ms)
Stage 2 (MinHash Python): 10,000 → 5,000 patterns     (20ms)
Stage 3 (Jaccard DB):     5,000 → 100 patterns         (15ms)
Stage 4 (RapidFuzz):      100 → 10 final matches       (25ms)
Total:                                                   90ms ✅
```

**Why this works:**
- MinHash tuned for J≥0.6 (within optimal range)
- Sequential refinement reduces candidates at each stage
- Database-heavy filtering (ClickHouse is fast)
- Minimal Python-side processing

---

### Case Study 3: When MinHash Fails

**Scenario**: 5 million patterns, trying to use MinHash with default config.

**Configuration (problematic):**
```python
config = SessionConfiguration(
    filter_pipeline=['minhash', 'jaccard'],
    minhash_threshold=0.3,       # LOW threshold
    minhash_bands=20,            # DEFAULT parameters
    minhash_rows=5,
    jaccard_threshold=0.3
)
```

**What happens:**
```
MinHash LSH query: 5,000,000 patterns scanned
  - P(collision) at J=0.3 ≈ 5%
  - Expected candidates: 250,000 (most are false positives)
  - Actual candidates: ~10,000 (many false negatives)

MinHash Python verification: 10,000 candidates
  - Filters to ~500 with J≥0.3

Jaccard query: 500 candidates (refined)
  - Finds ~100 with exact J≥0.3

Problem: MinHash missed patterns that Jaccard alone would find!
```

**Better configuration:**
```python
config = SessionConfiguration(
    filter_pipeline=['jaccard'],  # Skip MinHash entirely
    jaccard_threshold=0.3,
    jaccard_min_overlap=3
)
```

**Results:**
```
Jaccard query: 5,000,000 patterns scanned
  - Exact calculation: finds ALL patterns with J≥0.3
  - Time: 500-800ms (still very fast!)
  - No false negatives ✅

Comparison:
  MinHash pipeline: 90ms, found 100 patterns (missed 50)
  Jaccard only:    600ms, found 150 patterns (missed 0)

Winner: Jaccard (better recall, acceptable latency)
```

**Lesson**: For <10M patterns, MinHash adds complexity without benefit.

---

## Quick Reference Tables

### Filter Comparison

| Filter | Type | Speed | Accuracy | Best For |
|--------|------|-------|----------|----------|
| Length | DB | ★★★★★ | Exact | First stage, sanity check |
| Jaccard | DB | ★★★★☆ | Exact | <10M patterns, any threshold |
| MinHash | Hybrid | ★★★★★ | Approximate | >10M patterns, J≥0.7 |
| Bloom | Python | ★★★★★ | Exact (set membership) | Post-DB filtering |
| RapidFuzz | Python | ★★★☆☆ | Exact (sequence) | Final stage only |

### When to Use Each Filter

| Dataset Size | Recommended Pipeline |
|-------------|---------------------|
| < 100K | `['jaccard']` |
| 100K - 1M | `['length', 'jaccard']` |
| 1M - 10M | `['length', 'jaccard']` |
| 10M - 100M | `['minhash', 'jaccard']` (tune MinHash!) |
| > 100M | `['minhash', 'jaccard']` (essential) |

### MinHash Parameter Presets

| Target Similarity | Bands | Rows | Num Hashes | Expected Recall |
|-------------------|-------|------|------------|----------------|
| J ≥ 0.8 | 20 | 5 | 100 | ~99% |
| J ≥ 0.7 | 20 | 5 | 100 | ~95% |
| J ≥ 0.6 | 30 | 4 | 120 | ~85% |
| J ≥ 0.5 | 40 | 3 | 120 | ~70% |
| J ≥ 0.4 | 50 | 2 | 100 | ~40% |
| J < 0.4 | Use Jaccard instead | | |

---

## See Also

- [Hybrid Architecture](../HYBRID_ARCHITECTURE.md) - ClickHouse + Redis architecture overview
- [Pattern Matching](../research/pattern-matching.md) - Core matching algorithms
- [Configuration Reference](configuration-vars.md) - Complete config parameter list
- [API Reference](api/) - REST API documentation

---

**Last Updated**: November 2025
**KATO Version**: 3.0+
