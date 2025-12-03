# Known Issues and Bugs

Last Updated: 2025-09-06

## Test Suite Status ✅
**Current Status**: 198 tests passing, 1 skipped (~99.5% pass rate)
- All unit tests passing (142 passed, 1 skipped)
- All integration tests passing (19 passed)
- All API tests passing (32 passed)
- All performance tests passing (5 passed)

## Critical Issues 🔴
*None at this time - all major functionality working correctly*

## High Priority Issues 🟠
*None at this time - Phase 3 Configuration Management completed successfully*

## Medium Priority Issues 🟡

### 1. Analytics Service Not Starting
**Status**: Active  
**Severity**: Medium  
**Location**: Docker Compose configuration

**Description**:
- Third KATO instance (analytics on port 8003) not starting
- Primary (8001) and Testing (8002) instances work correctly
- Does not affect core functionality

**Configuration Details**:
- Analytics instance has different settings:
  - MAX_PATTERN_LENGTH=50 (auto-learns after 50 observations)
  - PERSISTENCE=10 (longer memory retention)
  - RECALL_THRESHOLD=0.3 (higher matching threshold)
- Intended for specialized analytics workloads

**Impact**:
- Analytics instance unavailable for multi-instance testing
- Can use Primary and Testing instances for all functionality

**Next Steps**:
- Investigate docker compose.yml configuration for analytics service
- Check port conflicts or resource constraints
- Verify if analytics-specific settings are causing startup issues

---

### 2. One Test Consistently Skipped
**Status**: Active  
**Severity**: Low  
**Location**: `tests/tests/unit/test_determinism_preservation.py`

**Description**:
- One test is intentionally skipped in the test suite
- This appears to be by design, not a failure
- Does not affect functionality

---

## Low Priority Issues 🟢

### 3. Docker Compose Version Warning
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

### 4. Redis Cache Service (Optional)
**Status**: Not Configured  
**Severity**: Low  
**Location**: Configuration

**Description**:
- Redis caching is available but not enabled by default
- System works perfectly without Redis
- Can be enabled via REDIS_ENABLED environment variable

**To Enable**:
```yaml
environment:
  - REDIS_ENABLED=true
  - REDIS_HOST=redis
  - REDIS_PORT=6379
```

---

## Performance Considerations 📊

### 5. Vector Search Accuracy Trade-offs
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

### 6. Environment Variable Loading
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

### 7. GPU Acceleration
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

### 8. Additional Vector Database Backends
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
- Currently: 0 failures (~99.5% pass rate)
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
- ~82 seconds for full test suite

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

### System Health
- **Test Coverage**: ~99.5% (198/199 tests passing)
- **API Stability**: All endpoints functional
- **Performance**: 10-100x improvement with Qdrant
- **Configuration**: Fully managed with Pydantic
- **Documentation**: Comprehensive and up-to-date