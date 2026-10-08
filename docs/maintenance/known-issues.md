# Known Issues and Bugs

## Critical Issues 🔴
*None at this time.*

## High Priority Issues 🟠
*None at this time.*

## Medium Priority Issues 🟡

*None at this time.*

## Low Priority Issues 🟢

### 1. Redis is Required
**Status**: By Design
**Severity**: Informational
**Location**: Configuration

**Description**:
- Redis is a **required** service (ClickHouse + Redis hybrid architecture)
- Redis handles session management, pattern metadata, and caching
- KATO will fail to start if Redis is unavailable

---

## Performance Considerations 📊

### 2. Vector Search Accuracy Trade-offs
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

## Feature Enhancements (Future) 💡

### 3. Additional Vector Database Backends
**Status**: Architecture Ready
**Priority**: Low

**Current Support**:
- ✅ Qdrant (primary, implemented)
- ⏳ FAISS (planned)
- ⏳ Milvus (planned)
- ⏳ Weaviate (planned)

The backend factory exists (`kato/storage/vector_store_factory.py`); only Qdrant is implemented.

---

## Testing Requirements

### Running Tests
```bash
# Services must be running
./start.sh start

# Run all tests
./run_tests.sh --no-start --no-stop

# Run specific suites
./run_tests.sh --no-start --no-stop tests/tests/unit/
./run_tests.sh --no-start --no-stop tests/tests/integration/
./run_tests.sh --no-start --no-stop tests/tests/api/
```

### Test Architecture
- Tests run in local Python environment
- Each test uses a unique `test_`-prefixed node_id for isolation
- Services must be running before tests

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

Tracked in `planning-docs/`, not here — see `SESSION_STATE.md` for what is in
flight, `SPRINT_BACKLOG.md` for what is queued, and `DECISIONS.md` for why things
are the way they are. Release contents are in
[CHANGELOG.md](../../CHANGELOG.md).

A duplicate summary lived here and went stale without anything failing: it claimed
445 passing tests long after the suite passed 800, and listed completed phases by a
version several majors back. A figure that is only correct on the day it is written
does not belong in a guide.
