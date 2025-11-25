# Stateless Processor Refactor Initiative
*Created: 2025-11-25*
*Status: ACTIVE - Critical Priority*

## Executive Summary

**Critical Bug Discovered**: Session isolation broken in KATO v3.0 due to stateful `KatoProcessor` design.

**Root Cause**: `KatoProcessor` holds STM, emotives, and percept_data as instance variables. When multiple sessions share the same `node_id`, they share the same processor instance, causing session data to leak across sessions.

**Current Workaround**: Processor locks implemented to force sequential processing (architectural band-aid).

**Proper Solution**: Refactor `KatoProcessor` to be stateless (standard web application pattern).

## Architectural Decision

### Current (Broken) Architecture
```python
class KatoProcessor:
    def __init__(self):
        self.stm = []              # SHARED across sessions!
        self.emotives = []         # SHARED across sessions!
        self.percept_data = []     # SHARED across sessions!

    def observe(self, observation):
        self.stm.append(observation)  # MUTATES shared state!
```

**Problem**: Multiple sessions with same `node_id` share processor instance → session data leaks.

### Target (Correct) Architecture
```python
class KatoProcessor:
    def observe(self, session_state: SessionState, observation: Observation) -> SessionState:
        new_stm = session_state.stm + [observation]
        return SessionState(stm=new_stm, ...)  # RETURNS new state, no mutation
```

**Benefits**:
- ✅ Session isolation guaranteed
- ✅ True concurrency (no locks)
- ✅ Horizontal scalability
- ✅ Simpler code
- ✅ Standard web pattern
- ✅ 5-10x performance improvement expected

## Scope Overview

### Phase 1: Stateless Processor Refactor (CRITICAL)
**Priority**: P0 - Blocks all other work
**Duration**: 1-2 days
**Risk**: Medium (significant refactor, well-understood pattern)

#### Components to Refactor
1. **MemoryManager** → Stateless methods
2. **KatoProcessor** → Accept SessionState parameters
3. **Session Endpoints** (7 files) → Use stateless pattern
4. **ProcessorManager** → Remove all locks
5. **Helper Modules** → Update to stateless pattern

### Phase 2: Test Updates (HIGH)
**Priority**: P1 - Required for verification
**Duration**: 1 day

#### Test Work Required
1. Update fixtures (remove `update_genes`, add `update_session_config`)
2. Verify session isolation test passes
3. Update gene references (47 occurrences, 9 files)
4. Create configuration tests
5. Create prediction metrics tests
6. Update Bayesian metrics tests

### Phase 3: Documentation Updates (MEDIUM)
**Priority**: P2 - Can be done in parallel with testing
**Duration**: 0.5 days

#### Documentation Cleanup
1. Remove MongoDB references (224 locations - already identified)
2. Update HYBRID_ARCHITECTURE.md
3. Update user documentation (12 files)
4. Update developer documentation (4 files)
5. Update operations documentation (3 files)
6. Update configuration documentation
7. Update ARCHITECTURE_DIAGRAM.md

### Phase 4: Verification & Testing (CRITICAL)
**Priority**: P0 - Must pass before release
**Duration**: 0.5 days

#### Verification Steps
1. Full test suite execution
2. Session isolation stress test
3. Concurrent load test (100 sessions, same node_id)
4. Manual testing
5. Performance benchmarking

### Phase 5: Cleanup (LOW)
**Priority**: P3 - Nice to have
**Duration**: 0.25 days

#### Cleanup Tasks
1. Remove obsolete gene code
2. Update CLAUDE.md
3. Add ADR-001 (Architecture Decision Record)

## Detailed Task Breakdown

### Phase 1 Tasks

#### Task 1.1: Make MemoryManager Stateless (4-6 hours)
**File**: `kato/workers/memory_manager.py`

**Current Pattern**:
```python
class MemoryManager:
    def __init__(self):
        self.stm = []
        self.ltm = []

    def add_to_stm(self, item):
        self.stm.append(item)  # MUTATION!
```

**Target Pattern**:
```python
class MemoryManager:
    @staticmethod
    def add_to_stm(stm: List, item) -> List:
        return stm + [item]  # PURE FUNCTION
```

**Work**:
- Convert all instance methods to static methods
- Remove `__init__` method
- Accept memory state as parameters
- Return new memory state as results
- Update all 15+ method signatures

**Risk**: Low - Simple transformation, clear pattern

#### Task 1.2: Update KatoProcessor to Accept SessionState (8-12 hours)
**File**: `kato/workers/kato_processor.py`

**Current Pattern**:
```python
def observe(self, observation):
    self.stm = MemoryManager.add_to_stm(self.stm, observation)
```

**Target Pattern**:
```python
def observe(self, session_state: SessionState, observation: Observation) -> SessionState:
    new_stm = MemoryManager.add_to_stm(session_state.stm, observation)
    return SessionState(stm=new_stm, ltm=session_state.ltm, ...)
```

**Work**:
- Update all 10+ public methods
- Remove instance variables (stm, emotives, percept_data)
- Accept SessionState as first parameter
- Return SessionState as result
- Update all internal method calls
- Update type hints

**Risk**: Medium - Core component, many dependencies

#### Task 1.3: Update Session Endpoints (12-16 hours)
**Files** (7 total):
1. `kato/api/endpoints/sessions.py` (primary)
2. `kato/api/endpoints/observe.py`
3. `kato/api/endpoints/predictions.py`
4. `kato/api/endpoints/learn.py`
5. `kato/api/endpoints/recall.py`
6. `kato/api/endpoints/clear.py`
7. `kato/api/endpoints/config.py`

**Current Pattern**:
```python
@router.post("/sessions/{session_id}/observe")
async def observe(session_id: str, observation: Observation):
    processor = get_processor(session.node_id)
    processor.observe(observation)  # MUTATES processor!
    save_session(session)
```

**Target Pattern**:
```python
@router.post("/sessions/{session_id}/observe")
async def observe(session_id: str, observation: Observation):
    processor = get_processor(session.node_id)
    new_state = processor.observe(session.state, observation)  # PURE!
    session.state = new_state
    save_session(session)
```

**Work**:
- Load SessionState from Redis before processor calls
- Pass SessionState to processor methods
- Update SessionState with returned values
- Save updated SessionState to Redis
- Remove all lock acquisitions
- Update error handling

**Risk**: Medium - Multiple files, critical path

#### Task 1.4: Remove All Processor Locks (2-4 hours)
**Files**:
1. `kato/processors/processor_manager.py`
2. `kato/api/endpoints/sessions.py`

**Work**:
- Remove `processor_locks` dictionary
- Remove all `async with lock:` blocks
- Remove lock cleanup code
- Update ProcessorManager to remove lock management
- Verify no deadlock conditions remain

**Risk**: Low - Simple deletion, locks become unnecessary

#### Task 1.5: Update Helper Modules (4-6 hours)
**Files**:
1. `kato/workers/observation_processor.py`
2. `kato/workers/pattern_operations.py`
3. Any other modules that interact with KatoProcessor

**Work**:
- Update method signatures to accept SessionState
- Update return types to return SessionState
- Remove any stateful assumptions
- Update tests

**Risk**: Low-Medium - Depends on module complexity

### Phase 2 Tasks

#### Task 2.1: Update Test Fixtures (2-3 hours)
**File**: `tests/tests/fixtures/kato_fixtures.py`

**Changes**:
1. Remove `update_genes()` fixture (obsolete with configuration system)
2. Add `update_session_config()` fixture
3. Update all processor-related fixtures to use stateless pattern
4. Update session fixtures to load/save SessionState properly

**Risk**: Low - Test infrastructure, low external dependencies

#### Task 2.2: Run Session Isolation Test (1 hour)
**File**: `tests/tests/integration/test_session_isolation.py`

**Work**:
1. Run existing test
2. Verify sessions with same node_id are properly isolated
3. Add additional edge case tests
4. Document results

**Expected**: Should pass with stateless refactor

**Risk**: Low - Existing test, should pass automatically

#### Task 2.3: Update Gene References in Tests (3-4 hours)
**Files** (9 total, 47 occurrences):
1. `tests/tests/api/test_genes_api.py`
2. `tests/tests/integration/test_session_management.py`
3. `tests/tests/unit/test_configuration_service.py`
4. ... (6 more files)

**Changes**:
- Replace `genes` with `session.config`
- Replace `update_genes()` with `update_session_config()`
- Update assertions to check `session.config` instead of `genes`
- Update test data structures

**Risk**: Low - Simple search/replace with verification

#### Task 2.4: Create Configuration Tests (4-6 hours)
**Files** (new):
1. `tests/tests/unit/test_session_configuration.py`
2. `tests/tests/integration/test_configuration_lifecycle.py`

**Test Coverage**:
- Session config creation
- Config updates
- Config inheritance
- Default values
- Validation rules
- Edge cases

**Risk**: Low - New tests, no dependencies

#### Task 2.5: Create Prediction Metrics Tests (4-6 hours)
**Files** (new/update):
1. `tests/tests/unit/test_prediction_metrics_v3.py` (new)
2. `tests/tests/unit/test_bayesian_metrics.py` (update)

**Test Coverage**:
- `bayesian_posterior` metric calculation
- `bayesian_prior` metric calculation
- `bayesian_likelihood` metric calculation
- `tfidf_score` metric calculation
- Edge cases (zero probabilities, empty predictions)
- Integration with prediction pipeline

**Risk**: Low-Medium - New metrics, need to understand calculations

### Phase 3 Tasks

#### Task 3.1: Remove MongoDB References (4-6 hours)
**Scope**: 224 occurrences across documentation

**Files** (high priority):
1. `docs/HYBRID_ARCHITECTURE.md` - Update architecture diagram
2. `docs/users/*.md` (12 files) - Remove MongoDB, emphasize ClickHouse + Redis
3. `docs/developers/*.md` (4 files) - Update development guides
4. `docs/operations/*.md` (3 files) - Update deployment guides

**Work**:
- Search for "MongoDB", "mongo", "pymongo"
- Replace with ClickHouse/Redis equivalents
- Update architecture diagrams
- Update command examples
- Verify consistency

**Risk**: Low - Documentation only, no code impact

#### Task 3.2: Update Configuration Documentation (2-3 hours)
**Files**:
1. `docs/reference/configuration-vars.md`
2. `docs/users/configuration.md`
3. `CLAUDE.md` (configuration section)

**Work**:
- Document new session configuration system
- Remove gene-based configuration references
- Add examples of session config updates
- Document configuration inheritance
- Update environment variable list

**Risk**: Low - Documentation clarity improvement

#### Task 3.3: Update Architecture Documentation (2-3 hours)
**Files**:
1. `ARCHITECTURE_DIAGRAM.md`
2. `docs/developers/architecture.md`

**Work**:
- Add stateless processor pattern
- Update session state management flow
- Remove processor lock references
- Add concurrency guarantees
- Update component interaction diagrams

**Risk**: Low - Reflects new reality

### Phase 4 Tasks

#### Task 4.1: Full Test Suite Execution (1 hour)
**Command**: `./run_tests.sh --no-start --no-stop`

**Verification**:
- All unit tests pass (100%)
- All integration tests pass (100%)
- All API tests pass (100%)
- No regressions

**Risk**: Low - Tests already updated in Phase 2

#### Task 4.2: Session Isolation Stress Test (2-3 hours)
**Test**: Create concurrent test with 100 sessions, same node_id

**Verification**:
- No session data leaks
- All sessions maintain independent state
- No race conditions
- No deadlocks
- Performance scales linearly

**Risk**: Medium - New test, may reveal edge cases

#### Task 4.3: Concurrent Load Test (2-3 hours)
**Test**: Simulate production load

**Scenarios**:
1. 100 sessions, same node_id, concurrent observations
2. 100 sessions, different node_ids, concurrent observations
3. Mixed workload (observe, predict, learn, recall)

**Metrics**:
- Throughput (req/sec)
- Latency (p50, p95, p99)
- Error rate
- Memory usage
- CPU usage

**Risk**: Medium - Real-world simulation, may reveal bottlenecks

#### Task 4.4: Manual Testing (2-3 hours)
**Scenarios**:
1. Create session → observe → predict → verify isolation
2. Multiple sessions same node_id → verify independence
3. Session TTL and expiration → verify cleanup
4. Config updates → verify propagation
5. Edge cases (empty observations, malformed data)

**Risk**: Low - Exploratory testing

#### Task 4.5: Performance Benchmarking (2-3 hours)
**Comparison**: Before (with locks) vs After (stateless)

**Metrics**:
- Throughput improvement (expected: 5-10x)
- Latency reduction (expected: 50-80%)
- Concurrency level (expected: unlimited)
- Lock contention (expected: 0)

**Risk**: Low - Should show significant improvement

### Phase 5 Tasks

#### Task 5.1: Remove Obsolete Gene Code (2-3 hours)
**Files**:
- Search for remaining `gene` references
- Remove dead code
- Update comments
- Clean up imports

**Risk**: Low - Code cleanup

#### Task 5.2: Update CLAUDE.md (1-2 hours)
**Work**:
- Document stateless processor pattern
- Update development workflow
- Add concurrency guarantees
- Remove lock-related warnings

**Risk**: Low - Documentation update

#### Task 5.3: Add ADR-001 (2-3 hours)
**File**: `docs/architecture-decisions/ADR-001-stateless-processor.md`

**Content**:
- Context (session isolation bug)
- Decision (stateless processor)
- Consequences (pros/cons)
- Alternatives considered (locks, separate processors)
- Implementation notes
- Migration guide

**Risk**: Low - Historical record

## Timeline

### Critical Path
1. **Phase 1**: 1-2 days (30-44 hours)
2. **Phase 2**: 1 day (14-19 hours)
3. **Phase 4**: 0.5 days (7-9 hours)

**Total Critical Path**: 2.5-3.5 days

### Parallel Work
- **Phase 3** (Documentation): Can run in parallel with Phase 2
- **Phase 5** (Cleanup): Can run after Phase 4

### Total Estimated Time
**Best Case**: 2 days (16 hours/day = 32 hours)
**Expected Case**: 2.5 days (40 hours)
**Worst Case**: 3.5 days (56 hours)

## Risk Assessment

### Technical Risks
| Risk | Severity | Mitigation |
|------|----------|------------|
| Stateless refactor introduces regressions | High | Comprehensive test suite in Phase 2 |
| Performance doesn't improve as expected | Medium | Benchmark before/after, profile bottlenecks |
| Session state becomes too large | Low | Monitor state size, add compression if needed |
| Concurrency edge cases | Medium | Stress testing in Phase 4 |

### Organizational Risks
| Risk | Severity | Mitigation |
|------|----------|------------|
| Timeline overruns | Low | Well-understood pattern, clear tasks |
| Breaking changes for users | None | Internal refactor, API unchanged |
| Documentation drift | Low | Phase 3 updates all docs |

## Success Criteria

### Functional Success
- ✅ All tests pass (100%)
- ✅ Session isolation verified (no data leaks)
- ✅ Concurrent sessions work correctly
- ✅ No locks in processor code
- ✅ SessionState properly managed

### Performance Success
- ✅ 5-10x throughput improvement
- ✅ 50-80% latency reduction
- ✅ Linear scaling with concurrent sessions
- ✅ Zero lock contention

### Code Quality Success
- ✅ Stateless pattern implemented correctly
- ✅ No instance variable mutations
- ✅ Clean function signatures
- ✅ Comprehensive test coverage
- ✅ Documentation updated

## Dependencies

### External Dependencies
- None (internal refactor only)

### Internal Dependencies
- Redis session storage (already working)
- SessionState data structure (already exists)
- Test infrastructure (already working)

## Rollback Plan

If refactor fails, rollback is simple:
1. Revert git commits
2. Keep processor locks in place
3. Document architectural debt
4. Plan alternative approach

**Rollback Risk**: Low - Git-based, well-contained changes

## Communication Plan

### Stakeholders
- Development team (primary)
- Users (no API changes, transparent)

### Updates
- Daily progress updates in SESSION_STATE.md
- Phase completion notifications
- Performance benchmark results
- Final completion report

## Post-Implementation

### Monitoring
- Track session throughput metrics
- Monitor error rates
- Profile performance hotspots
- Watch for session state size growth

### Follow-up Work
- Optimize session state serialization if needed
- Add session state compression if state grows large
- Consider session state caching strategies
- Add advanced concurrency metrics

## Related Work

### Original Issues
- Session isolation bug discovered in v3.0
- Temporary fix: processor locks (sequential processing)

### Future Enhancements
- Session state compression
- Advanced caching strategies
- Distributed session management
- Horizontal processor scaling

## References

### Related Documents
- `planning-docs/initiatives/hybrid-clickhouse-redis.md` - v3.0 architecture
- `planning-docs/DECISIONS.md` - Decision log
- `docs/HYBRID_ARCHITECTURE.md` - System architecture
- `docs/developers/architecture.md` - Developer guide

### Related Code
- `kato/workers/kato_processor.py` - Core processor
- `kato/workers/memory_manager.py` - Memory management
- `kato/api/endpoints/sessions.py` - Session endpoints
- `kato/sessions/redis_session_manager.py` - Session storage

---

**Initiative Owner**: Claude Code (project-manager agent)
**Start Date**: 2025-11-25
**Target Completion**: 2025-11-28
**Status**: ACTIVE - Ready to begin Phase 1
