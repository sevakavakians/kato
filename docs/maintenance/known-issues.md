# Known Issues and Bugs

Last Updated: 2026-03-19

## Test Suite Status ✅
**Current Status**: 445+ tests passing, 2 skipped
- All test suites passing

## Critical Issues 🔴
*None at this time - all major functionality working correctly*

## High Priority Issues 🟠
*None at this time - Phase 3 Configuration Management completed successfully*

## Medium Priority Issues 🟡

### 1. One Test Consistently Skipped
**Status**: Active  
**Severity**: Low  
**Location**: `tests/tests/unit/test_determinism_preservation.py`

**Description**:
- One test is intentionally skipped in the test suite
- This appears to be by design, not a failure
- Does not affect functionality

---

## Low Priority Issues 🟢

### 2. Docker Compose Version Warning
**Status**: Active  
**Severity**: Minimal  
**Location**: `docker compose.yml` files

**Warning Message**:
```
the attribute `version` is obsolete, it will be ignored
```

**Fix Needed**:
- Remove `version: '3.8'` from docker compose files
- Update to latest compose file format

---

### 3. Redis is Required (v3.0+)
**Status**: By Design
**Severity**: Informational
**Location**: Configuration

**Description**:
- Redis is a **required** service in KATO v3.0+ (ClickHouse + Redis hybrid architecture)
- Redis handles session management, pattern metadata, and caching
- KATO will fail to start if Redis is unavailable

---

## Performance Considerations 📊

### 4. Vector Search Accuracy Trade-offs
**Status**: By Design  
**Severity**: Informational  

**Description**:
- HNSW algorithm in Qdrant provides approximate nearest neighbors
- ~99.9% accuracy vs 100% with old linear search
- 10-100x performance improvement justifies minimal accuracy trade-off

**Monitoring**:
- Track prediction accuracy in production
- Adjust HNSW parameters if needed (m, ef_construct)

---

## Configuration Notes 📝

### 5. Environment Variable Loading
**Status**: Resolved  
**Implementation**: Application Startup Pattern

**Solution Implemented**:
- Configuration now uses FastAPI lifespan context manager
- Settings loaded at startup, not module import time
- Dependency injection ensures correct configuration
- Fully compatible with Docker environment variables

See [Configuration Management](CONFIGURATION_MANAGEMENT.md) for details.

---

## Feature Enhancements (Future) 💡

### 6. GPU Acceleration
**Status**: Prepared but Not Active  
**Priority**: Low  

**Description**:
- GPU-enabled Qdrant configuration exists but not enabled
- Requires NVIDIA GPU and container toolkit

**To Enable**:
1. Install NVIDIA Container Toolkit
2. Uncomment GPU section in docker compose.yml
3. Set appropriate GPU device IDs

---

### 7. Additional Vector Database Backends
**Status**: Architecture Ready
**Priority**: Low

**Current Support**:
- ✅ Qdrant (primary, implemented)
- ⏳ FAISS (planned)
- ⏳ Milvus (planned)
- ⏳ Weaviate (planned)

Factory pattern can be implemented if needed

---

## Recently Resolved Issues ✅

### Phase 3 Configuration Management
**Status**: COMPLETED (2025-09-06)
- Implemented Application Startup Pattern
- Fixed Docker environment variable timing issues
- Added comprehensive Pydantic configuration system
- All endpoints use dependency injection
- Full test coverage passing

### Recall Threshold Behavior
**Status**: RESOLVED
- Understood as heuristic filter, not exact decimal matching
- Documentation updated across all files
- Tests updated to reflect approximate behavior

### Test Suite Failures
**Status**: RESOLVED
- Previously: 102 failures (~46% pass rate)
- Currently: 0 failures (445+ tests passing)
- All pattern handling tests passing
- All memory management tests passing
- All API tests passing

---

## Testing Requirements

### Running Tests
```bash
# Services must be running
./start.sh

# Run all tests
./run_tests.sh --no-start --no-stop

# Run specific suites
./run_tests.sh --no-start --no-stop tests/tests/unit/
./run_tests.sh --no-start --no-stop tests/tests/integration/
./run_tests.sh --no-start --no-stop tests/tests/api/
```

### Test Architecture
- Tests run in local Python environment
- Each test gets unique session_id for isolation
- Services must be running before tests
- ~590 seconds (10 min) for full test suite

---

## How to Report New Issues

1. Verify issue exists with latest code from main branch
2. Check if issue already documented here
3. Provide:
   - Clear description
   - Steps to reproduce
   - Expected vs actual behavior
   - Error messages/logs
   - Environment details

## Priority Levels

- 🔴 **Critical**: System broken, data loss risk
- 🟠 **High**: Major feature broken, no workaround
- 🟡 **Medium**: Feature impaired, workaround exists
- 🟢 **Low**: Minor issue, cosmetic, or rare edge case

## Current Development Status

### Completed Phases
- ✅ Phase 1: Structured Logging and Error Handling
- ✅ Phase 2: Type Hints and Documentation
- ✅ Phase 3: Configuration Management System
- ✅ ClickHouse + Redis Hybrid Architecture (v3.0)
- ✅ Stateless Processor Architecture (v3.0)
- ✅ Database Authentication Support (v3.4)

### System Health
- **Test Coverage**: 445+ tests passing
- **API Stability**: All endpoints functional
- **Performance**: 100-300x improvement with ClickHouse/Redis hybrid + Qdrant
- **Configuration**: Fully managed with Pydantic
- **Documentation**: Comprehensive and up-to-date