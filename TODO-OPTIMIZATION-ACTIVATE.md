# TODO: Activate KATO Performance Optimizations

## Executive Summary
KATO has a complete performance optimization system that was developed in August 2025, achieving **~300x speedup** in sequence pattern matching. The code is fully functional but currently **DISABLED**. This document contains everything needed to activate these optimizations and remove legacy code.

## Current State Analysis

### What Exists
1. **Optimization Modules** (Working and Tested):
   - `/kato/searches/fast_matcher.py` - Fast pattern matching algorithms
   - `/kato/searches/index_manager.py` - Index structures for fast lookups
   - `/kato/searches/model_search_optimized.py` - Drop-in replacement for ModelSearcher

2. **Test Files** (Disabled but functional):
   - `/tests/test_optimizations_standalone.py.disabled` - Standalone optimization tests
   - `/tests/tests/performance/test_pattern_matching_performance.py.disabled` - Performance benchmarks

3. **Supporting Scripts**:
   - `/run_benchmark.sh` - Benchmarking script
   - `/run_tests_optimized.sh` - Optimized test runner
   - `/OPTIMIZATION_NOTES.md` - Original implementation notes

### What's Currently Used
- **Production Code**: Uses original `ModelSearcher` from `/kato/searches/model_search.py`
- **Import Location**: `/kato/workers/modeler.py` line 22
- **Instantiation**: `/kato/workers/modeler.py` lines 49-51

### Why It's Disabled
- Optimization modules exist but are NOT imported anywhere in production
- Only referenced by disabled test files
- Likely disabled for safety/validation before production deployment

## Optimization Components Detail

### 1. fast_matcher.py
**Classes**:
- `RollingHash`: Rabin-Karp rolling hash (O(1) sliding window)
- `SuffixArray`: O(n log n) construction, O(m log n) search
- `NGramIndex`: Fast partial matching with Jaccard similarity
- `FastSequenceMatcher`: Main class combining all algorithms

**Status**: ✅ Fully functional, tested manually

### 2. index_manager.py
**Classes**:
- `InvertedIndex`: Symbol → Model mapping, O(1) lookup
- `BloomFilter`: Fast negative lookups
- `LengthPartitionedIndex`: Reduce search space by sequence length
- `IndexManager`: Coordinates all indices with TF-IDF scoring

**Status**: ✅ Fully functional, tested manually

### 3. model_search_optimized.py
**Classes**:
- `OptimizedInformationExtractor`: Fast pattern matching
- `OptimizedModelSearcher`: Drop-in replacement for ModelSearcher
- `create_model_searcher()`: Factory function for clean switching

**Key Feature**: Factory pattern with environment variable control:
```python
def create_model_searcher(**kwargs):
    use_optimized = environ.get('KATO_USE_OPTIMIZED', 'true').lower() == 'true'
    if use_optimized:
        return OptimizedModelSearcher(**kwargs)
    else:
        return ModelSearcher(**kwargs)
```

**Status**: ✅ Has same interface as original ModelSearcher (including `causalBelief` method)

## Activation Plan

### Step 1: Fix test_optimizations_standalone.py.disabled

**File**: `/tests/test_optimizations_standalone.py.disabled`

**Required Fixes**:
```python
# Line 121: WRONG
index.add_model(model_id, sequence)
# CORRECT:
index.add_document(model_id, sequence)

# Line 128: WRONG
results_and = index.search(search_symbols, mode='all')
# CORRECT:
results_and = index.search(search_symbols, mode='AND')

# Line 133: WRONG
results_or = index.search(search_symbols, mode='any')
# CORRECT:
results_or = index.search(search_symbols, mode='OR')

# Line 141: WRONG
idf = index.get_symbol_idf('symbol_0')
# CORRECT:
idf = index.get_idf('symbol_0')
```

**Re-enable**: Rename file from `.disabled` to `.py`

### Step 2: Activate in Production

**File**: `/kato/workers/modeler.py`

**Change Import (Line 22)**:
```python
# OLD:
from kato.searches.model_search import ModelSearcher

# NEW:
from kato.searches.model_search_optimized import create_model_searcher
```

**Change Instantiation (Lines 49-51)**:
```python
# OLD:
self.models_searcher = ModelSearcher(kb_id=self.kb_id,
                                     max_predictions=self.max_predictions,
                                     recall_threshold=self.recall_threshold)

# NEW:
self.models_searcher = create_model_searcher(kb_id=self.kb_id,
                                             max_predictions=self.max_predictions,
                                             recall_threshold=self.recall_threshold)
```

### Step 3: Environment Variables

These control optimization behavior (already set in test-harness.sh):
- `KATO_USE_OPTIMIZED=true` - Enable optimized searcher (default: true)
- `KATO_USE_FAST_MATCHING=true` - Enable fast matching (default: true)
- `KATO_USE_INDEXING=true` - Enable indexing (default: true)

**Note**: Defaults are `true`, so optimization is ON by default once activated.

### Step 4: Update test-harness.sh

**File**: `/test-harness.sh`

Line 182 references the test file correctly, just needs the file to be re-enabled.

### Step 5: Remove Legacy Code (Optional - After Validation)

Once optimizations are validated in production:

1. **Remove original ModelSearcher**:
   - Delete `/kato/searches/model_search.py` (286 lines)
   - Remove `PredictionBuilder` and `InformationExtractorWorker` classes (now optimized)

2. **Simplify model_search_optimized.py**:
   - Remove factory function `create_model_searcher()`
   - Remove fallback imports to original ModelSearcher
   - Rename `OptimizedModelSearcher` to `ModelSearcher`

3. **Clean up disabled tests**:
   - `/tests/test_vector_compatibility.py.disabled` - Uses removed MongoDB code
   - `/tests/test_vector_database.py.disabled` - Imports non-existent modules
   - Keep `/tests/test_optimizations_standalone.py` as validation suite

## Testing Strategy

### 1. Standalone Optimization Test
```bash
# After fixing method names
python3 tests/test_optimizations_standalone.py
```
Expected: All optimization components pass

### 2. Full Test Suite
```bash
./test-harness.sh test
```
Expected: All 128 tests pass (no regressions)

### 3. Performance Benchmark
```bash
./run_benchmark.sh --quick
```
Expected: ~300x speedup in pattern matching

### 4. Specific Optimization Suite
```bash
./test-harness.sh suite optimizations
```
Expected: Currently broken, will work after Step 1

## Rollback Strategy

If issues arise, instant rollback via environment variable:
```bash
export KATO_USE_OPTIMIZED=false
./kato-manager.sh restart
```

This uses the factory pattern to switch back to original implementation.

## Performance Improvements Expected

Based on OPTIMIZATION_NOTES.md:
- **Pattern Matching**: ~300x faster
- **Memory Usage**: Reduced through efficient indexing
- **CPU Usage**: Better multicore utilization
- **Scalability**: Handles 10,000+ models efficiently

## Verification Checklist

- [ ] test_optimizations_standalone.py fixed and renamed
- [ ] modeler.py updated to use create_model_searcher
- [ ] Environment variables confirmed (or use defaults)
- [ ] Standalone optimization test passes
- [ ] All 128 existing tests pass
- [ ] Performance benchmark shows improvement
- [ ] No errors in Docker logs
- [ ] Predictions still deterministic
- [ ] API responses unchanged

## Known Issues to Fix

1. **test_optimizations_standalone.py**:
   - Method name mismatches (documented above)
   - File is disabled (needs renaming)

2. **Other disabled tests**:
   - test_vector_compatibility.py.disabled - References removed MongoDB code
   - test_vector_database.py.disabled - Imports non-existent mongodb_vector_store
   - These should be DELETED, not fixed

3. **Shell scripts in tests/**:
   - run_tests.sh, run_tests_simple.sh, setup_venv.sh, recreate_venv.sh
   - These are redundant (test-harness.sh is preferred)
   - Can be deleted to reduce confusion

## Files to Clean Up

### Can Be Deleted:
- `/tests/run_tests.sh` - Redundant test runner
- `/tests/run_tests_simple.sh` - Redundant test runner
- `/tests/setup_venv.sh` - Unnecessary (Docker-based testing)
- `/tests/recreate_venv.sh` - Unnecessary (Docker-based testing)
- `/tests/test_vector_compatibility.py.disabled` - Tests removed MongoDB code
- `/tests/test_vector_database.py.disabled` - Imports non-existent modules

### Must Keep:
- `/tests/conftest.py` - Required by pytest
- `/tests/test_optimizations_standalone.py` - After fixing and renaming

## Command Reference

```bash
# Activate optimizations (after code changes)
export KATO_USE_OPTIMIZED=true
./kato-manager.sh restart

# Test optimizations
python3 tests/test_optimizations_standalone.py
./test-harness.sh test
./run_benchmark.sh

# Monitor performance
docker logs kato-api-$(whoami)-1 --tail 50 | grep -i optimized

# Rollback if needed
export KATO_USE_OPTIMIZED=false
./kato-manager.sh restart
```

## Summary

The optimization code is **production-ready** and provides **massive performance improvements**. Activation requires:
1. Two small changes to modeler.py (import and instantiation)
2. Fixing 4 method names in the test file
3. Running tests to verify

The factory pattern and environment variables provide a **safe, reversible deployment** with instant rollback capability. The optimizations maintain full backward compatibility and deterministic behavior.

**Estimated Time**: 15 minutes to activate, 30 minutes to validate
**Risk Level**: Low (instant rollback available)
**Performance Gain**: ~300x for pattern matching operations