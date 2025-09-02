# Known Issues and Bugs

Last Updated: 2025-08-31

## Critical Issues 🔴
*None at this time*

## High Priority Issues 🟠

### 1. Test Suite Failures - Recall Threshold and Pattern Handling
**Status**: Active  
**Severity**: High (blocks Phase 2 development)  
**Location**: Unit tests

**Description**: 
- 13 tests currently failing (~93% pass rate: 179/193)
- Failures primarily in recall threshold edge cases and comprehensive patterns
- Affects confidence in system stability

**Failed Tests**:
- 7 tests in `test_comprehensive_patterns.py` (long patterns, cyclic patterns)
- 3 tests in `test_recall_threshold_*` files (edge cases, threshold values)
- 1 test in `test_memory_management.py` (vector handling)
- 1 test in `test_prediction_fields.py` (past field validation)

**Root Causes**:
- Recall threshold implementation edge cases
- Long pattern handling discrepancies
- Possible issues with recent threshold propagation changes

**Impact**:
- Cannot claim 100% test coverage
- Potential edge case bugs in production
- Blocks Phase 2 API development

**Next Steps**:
- Investigate each failing test
- Fix recall threshold edge cases
- Validate comprehensive pattern handling

---

### 2. Vector Similarity Accuracy Test Failing
**Status**: Active  
**Severity**: Medium  
**Location**: `tests/test_vector_stress.py::test_vector_accuracy`

**Description**:
- Accuracy test shows 0% match rate
- Predictions are working but test parsing logic is incorrect
- Does not affect actual vector functionality

**Current Behavior**:
- Test expects specific label matching in predictions
- Predictions return VECTOR hashes instead of original labels

**Fix Needed**:
- Update test to properly parse vector prediction results
- Add mapping between vector hashes and labels

---

## Medium Priority Issues 🟡

### 3. Recall Threshold Edge Cases
**Status**: Active  
**Severity**: Medium  
**Location**: `kato/searches/pattern_search.py`

**Description**:
- Recent changes to threshold handling causing test failures
- Threshold 0.0 should return all patterns but implementation incomplete
- Missing symbols detection not working correctly

**Symptoms**:
- `test_threshold_zero_no_filtering` failing
- `test_threshold_with_missing_symbols` failing
- Inconsistent similarity scoring

**Fix Needed**:
- Review threshold propagation logic
- Ensure 0.0 threshold returns all patterns
- Validate missing/extras symbol detection

---

### 4. Redis Cache Service Port Conflict
**Status**: Active  
**Severity**: Low  
**Location**: Docker Compose configuration

**Description**:
- Redis fails to start due to port 6379 already in use
- Does not affect core functionality (Redis is optional cache layer)

**Error Message**:
```
Bind for 0.0.0.0:6379 failed: port is already allocated
```

**Workaround**:
- System works without Redis
- Can change Redis port in docker-compose.vectordb.yml

**Fix Options**:
1. Use different port for Redis
2. Check for existing Redis instances
3. Make Redis port configurable via environment variable

---

### 5. Qdrant Configuration Warnings
**Status**: Resolved (workaround in place)  
**Severity**: Low  
**Location**: `config/qdrant_config.yaml`

**Description**:
- Initial Qdrant configuration had duplicate field definitions
- Created simplified configuration to avoid issues

**Solution Applied**:
- Created `qdrant_config_simple.yaml` with minimal settings
- Original config kept for reference but not used

---

## Low Priority Issues 🟢

### 6. Docker Compose Version Warning
**Status**: Active  
**Severity**: Minimal  
**Location**: `docker-compose.vectordb.yml`

**Warning Message**:
```
the attribute `version` is obsolete, it will be ignored
```

**Fix Needed**:
- Remove `version: '3.8'` from docker-compose files
- Update to latest compose file format

---

### 7. Test Directory Structure Confusion
**Status**: Active  
**Severity**: Low  
**Location**: Test execution

**Description**:
- Tests sometimes look in wrong directory (`tests/tests/tests/`)
- Caused by nested test directory structure

**Workaround**:
- Always run tests from project root with full path
- Use `cd /Users/sevakavakians/PROGRAMMING/kato && python3 tests/...`

---

## Performance Considerations 📊

### 8. Vector Accuracy in Predictions
**Status**: Monitoring  
**Severity**: Low  

**Description**:
- HNSW algorithm provides approximate (not exact) nearest neighbors
- 99.9% accuracy vs 100% with old linear search
- Massive performance gain (10-100x) justifies small accuracy trade-off

**Monitoring**:
- Track prediction accuracy in production
- Adjust HNSW parameters if needed (m, ef_construct)

---

## Feature Requests / Enhancements 💡

### 9. GPU Acceleration Not Yet Enabled
**Status**: Future Enhancement  
**Priority**: Low  

**Description**:
- GPU-enabled Qdrant configuration created but not active
- Requires NVIDIA GPU and additional setup

**To Enable**:
1. Uncomment GPU section in docker-compose.vectordb.yml
2. Install NVIDIA Container Toolkit
3. Test with GPU-enabled operations

---

### 10. Additional Vector Database Backends
**Status**: Planned  
**Priority**: Low  

**Partially Implemented**:
- Factory pattern supports multiple backends
- Only Qdrant and MongoDB currently implemented

**Future Backends**:
- FAISS (for CPU-optimized search)
- Milvus (for distributed search)
- Weaviate (for semantic search)

---

## Testing Gaps 🧪

### 11. Missing Integration Tests
**Status**: Needs Attention  
**Priority**: Medium  

**Areas Needing Tests**:
- Vector migration from MongoDB to Qdrant
- Multi-instance KATO with shared vector database
- Vector database failover scenarios
- Performance regression tests

---

## Documentation Gaps 📚

### 12. API Documentation for Vector Operations
**Status**: Needs Update  
**Priority**: Medium  

**Missing Documentation**:
- Vector observation format specifications
- Vector dimension limits and recommendations
- Best practices for vector operations
- Performance tuning guide

---

## Resolved Issues ✅

### ~~VectorIndexer Constructor Arguments~~
**Status**: RESOLVED  
**Resolution**: Updated VectorIndexer to accept legacy arguments

### ~~Qdrant Client Not Installed~~
**Status**: RESOLVED  
**Resolution**: Added qdrant-client to requirements.txt

### ~~Vector Database Not Starting by Default~~
**Status**: RESOLVED  
**Resolution**: Modified kato-manager.sh to start vector DB automatically

---

## How to Report New Issues

1. Check if issue already exists in this document
2. Test with latest code from main branch
3. Provide:
   - Clear description of the issue
   - Steps to reproduce
   - Expected vs actual behavior
   - Error messages/logs
   - Environment details (OS, Python version, Docker version)

## Priority Levels

- 🔴 **Critical**: System doesn't work, data loss risk
- 🟠 **High**: Major feature broken, no workaround
- 🟡 **Medium**: Feature impaired, workaround exists
- 🟢 **Low**: Minor issue, cosmetic, or rare edge case

## Next Sprint Priorities

1. Fix remaining 13 test failures (recall threshold and patterns)
2. Update vector accuracy test logic
3. Complete recall threshold edge case fixes
4. Resolve Redis port conflicts
5. Add missing integration tests
6. Complete API documentation