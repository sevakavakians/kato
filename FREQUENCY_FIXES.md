# KATO Frequency Metrics Analysis and Fixes

## STATUS: ✅ COMPLETED

All issues have been fixed and TF-IDF has been successfully implemented.

## Executive Summary

Critical issues discovered in KATO's symbol frequency calculations that affected probability calculations and prevented proper TF-IDF implementation. The core issue was a units mismatch in `symbolProbability()` and missing tracking of total unique patterns.

## Current Symbol Frequency Metrics

### 1. `symbol_frequency` (Redis: `{kb_id}:symbol:freq:{symbol}`)
- **Definition**: Total occurrences of a symbol across ALL patterns
- **Example**: If "hello" appears 3 times in pattern A and 2 times in pattern B → symbol_frequency = 5
- **Information Retrieval Equivalent**: Collection Frequency (CF)
- **Incremented**: By count of occurrences when pattern is learned

### 2. `pattern_member_frequency` (Redis: `{kb_id}:symbol:pmf:{symbol}`)
- **Definition**: Number of UNIQUE patterns containing this symbol
- **Example**: If "hello" appears in patterns A, B, C (regardless of count) → pattern_member_frequency = 3
- **Information Retrieval Equivalent**: Document Frequency (DF)
- **Incremented**: By 1 when NEW pattern containing symbol is learned

### 3. `total_symbols_in_patterns_frequencies` (Redis: `{kb_id}:global:total_symbols_in_patterns_frequencies`)
- **Definition**: Sum of all symbol occurrences across all patterns
- **Example**: Total words in the corpus
- **Incremented**: By pattern length when pattern is learned

### 4. `total_pattern_frequencies` (Redis: `{kb_id}:global:total_pattern_frequencies`)
- **Definition**: Sum of all pattern frequencies (frequency-weighted count)
- **Example**: If pattern A has frequency=5, pattern B has frequency=3 → total = 8
- **NOT**: Count of unique patterns

### 5. `total_unique_patterns` (MISSING!)
- **Definition**: Count of unique patterns (NOT frequency-weighted)
- **Example**: If we have patterns A, B, C → total_unique_patterns = 3
- **Status**: ❌ NOT CURRENTLY TRACKED

## Critical Issues Found

### Issue 1: Units Mismatch in symbolProbability()

**Location**: `pattern_processor.py:535-536`

```python
# CURRENT (WRONG):
pattern_member_frequency = symbol_data.get('pattern_member_frequency', 0)
return float(pattern_member_frequency / total_symbols_in_patterns_frequencies)
```

**Problem**:
- Numerator: Number of PATTERNS containing symbol (document count)
- Denominator: Total SYMBOL OCCURRENCES (word count)
- This is like dividing "number of books containing word X" by "total words in library"

**Impact**:
- Produces meaningless probability values
- Affects confluence, normalized_entropy, and other metrics that use symbolProbability()

### Issue 2: Missing Total Unique Patterns Counter

**Problem**:
- We track frequency-weighted pattern count but not unique pattern count
- Needed for proper probability calculations and TF-IDF

**Impact**:
- Cannot calculate proper document-based probabilities
- Cannot implement standard TF-IDF without this

## Correct Usage Matrix

| Metric | Current (Wrong) Usage | Correct TF-IDF Usage | Correct Probability Usage |
|--------|----------------------|---------------------|--------------------------|
| `pattern_member_frequency` | Divided by total_symbols_in_patterns_frequencies | ✅ IDF denominator: patterns containing term | Divide by total_unique_patterns |
| `symbol_frequency` | Not used in predictions | Not needed for TF-IDF | Divide by total_symbols_in_patterns_frequencies |
| `total_unique_patterns` | ❌ Doesn't exist | ✅ IDF numerator: total documents | Denominator for pattern probability |
| `total_symbols_in_patterns_frequencies` | Used incorrectly with pattern_member_frequency | Not needed for TF-IDF | Denominator for symbol occurrence probability |

## Proposed Fixes

### Fix 1: Add total_unique_patterns Counter

**Implementation**:
1. Add to `redis_writer.py`:
   - `increment_unique_pattern_count()`
   - Update `get_global_metadata()` to include this
2. Modify `knowledge_base.py`:
   - Increment only when NEW pattern is created
   - Don't increment when existing pattern frequency increases

### Fix 2: Fix symbolProbability() Function

**Current (Wrong)**:
```python
def symbolProbability(self, symbol, total_symbols_in_patterns_frequencies):
    pattern_member_frequency = symbol_data.get('pattern_member_frequency', 0)
    return float(pattern_member_frequency / total_symbols_in_patterns_frequencies)
```

**Option A - Pattern-Based Probability** (Recommended):
```python
def symbolProbability(self, symbol, total_unique_patterns):
    # Probability that a random pattern contains this symbol
    pattern_member_frequency = symbol_data.get('pattern_member_frequency', 0)
    return float(pattern_member_frequency / total_unique_patterns)
```

**Option B - Occurrence-Based Probability**:
```python
def symbolProbability(self, symbol, total_symbols_in_patterns_frequencies):
    # Probability that a random symbol occurrence is this symbol
    symbol_frequency = symbol_data.get('frequency', 0)  # Use symbol_frequency, not pattern_member_frequency!
    return float(symbol_frequency / total_symbols_in_patterns_frequencies)
```

### Fix 3: Implement TF-IDF Correctly

**Term Frequency (TF)**:
```python
# Count occurrences in THIS pattern
symbol_count_in_pattern = pattern_symbols.count(symbol)
pattern_length = len(pattern_symbols)
TF = symbol_count_in_pattern / pattern_length
```

**Inverse Document Frequency (IDF)**:
```python
# Use pattern_member_frequency (DF) correctly
total_unique_patterns = global_metadata.get('total_unique_patterns', 1)
patterns_containing_symbol = symbol_stats.get('pattern_member_frequency', 1)
IDF = log(total_unique_patterns / patterns_containing_symbol) + 1
```

**TF-IDF Score**:
```python
TFIDF = TF * IDF
```

## Impact Analysis

### Affected Metrics
1. **symbolProbability()** - Currently produces incorrect values
2. **confluence** - Uses symbolProbability internally
3. **normalized_entropy** - May use symbol probabilities
4. **global_normalized_entropy** - Uses symbol probability cache

### Backward Compatibility
- Existing patterns don't have `total_unique_patterns` tracked
- Will need migration script to count existing unique patterns
- New patterns will track correctly going forward

## Implementation Priority

1. **High Priority**: Add `total_unique_patterns` counter
2. **High Priority**: Fix symbolProbability() to use correct units
3. **Medium Priority**: Implement TF-IDF with correct frequencies
4. **Low Priority**: Migration script for existing data

## Testing Requirements

1. Verify `total_unique_patterns` increments only on NEW patterns
2. Verify symbolProbability() returns values in [0, 1] range
3. Verify TF-IDF produces reasonable scores
4. Check confluence and entropy calculations still work

## Notes

- `pattern_member_frequency` IS correct for TF-IDF's document frequency
- The infrastructure (Redis counters) is already in place
- Main issue is conceptual: mixing pattern-level and symbol-level probabilities

## Implementation Complete ✅

### Fixed Issues

1. **Added `total_unique_patterns` counter**:
   - `redis_writer.py`: Added `increment_unique_pattern_count()` method
   - `redis_writer.py`: Updated `get_global_metadata()` to return `total_unique_patterns`
   - `knowledge_base.py`: Updated to increment counter only for NEW patterns

2. **Fixed symbolProbability() units mismatch**:
   - Changed from `pattern_member_frequency / total_symbols_in_patterns_frequencies` (wrong units)
   - To `pattern_member_frequency / total_unique_patterns` (compatible units)
   - Fixed in both method signature and inline calculations

3. **Implemented TF-IDF**:
   - Added TF-IDF calculation in `pattern_processor.py` async `predictPattern()`
   - Uses mean aggregation for pattern-level scores
   - Formula: `TF × log2(total_unique_patterns / patterns_with_symbol) + 1`

4. **Updated Configuration**:
   - Added `tfidf_score` to valid `rank_sort_algo` options in:
     - `session_config.py`
     - `configuration_service.py`

5. **Migration Support**:
   - Created `scripts/migrate_unique_patterns_count.py` for existing installations
   - Counts unique patterns in ClickHouse and initializes Redis counter

6. **Documentation**:
   - Updated `docs/reference/prediction-object.md` with TF-IDF metric documentation
   - Fixed potential metric range documentation (can be negative)

### Files Modified

1. ✅ `kato/storage/redis_writer.py`
2. ✅ `kato/informatics/knowledge_base.py`
3. ✅ `kato/workers/pattern_processor.py`
4. ✅ `kato/config/session_config.py`
5. ✅ `kato/config/configuration_service.py`
6. ✅ `kato/filters/executor.py` (fixed missing `length` column)
7. ✅ `docs/reference/prediction-object.md`
8. ✅ `scripts/migrate_unique_patterns_count.py` (created)

### To Deploy

1. Rebuild KATO container: `docker-compose build --no-cache kato`
2. Run migration for existing data: `python scripts/migrate_unique_patterns_count.py`
3. Test TF-IDF ranking: Set `rank_sort_algo: 'tfidf_score'` in session config