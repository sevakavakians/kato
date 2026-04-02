# Session Prompt: Session Management Concurrency Investigation

Use this prompt to start your next session working on the session concurrency issue.

---

## Prompt for Next Session

```
I need help investigating and fixing a session management concurrency issue in the KATO system.

CRITICAL: Read the comprehensive investigation report first:
docs/investigations/session-concurrency-investigation-2025-10-09.md

Quick context:
- 5 out of 15 session tests are failing (67% pass rate)
- All failures involve SESSION_NOT_FOUND errors under concurrent load
- Sessions are created but not immediately queryable
- Previous attempt to fix with retries/connection pooling made it WORSE (10% → 2% success)
- All changes have been REVERTED - we're back to baseline

THE KEY FINDING: Write verification code was added but NEVER LOGGED ANYTHING. This suggests:
- Code path not executing, OR
- Logging configuration broken, OR
- Fundamental execution model misunderstanding

START HERE:
1. Read the full investigation report (it's comprehensive)
2. Focus on "Phase 1: Verify Observability" - we need to confirm code executes
3. Add print() statements (not logger) to create_session method in kato/sessions/redis_session_manager.py
4. Run a single test and check Docker logs for TRACE output
5. If prints don't appear → investigate WHY code path not reached
6. If prints appear → logging config is the issue, use prints for rest of investigation

DO NOT:
- Add more retries or connection pooling (already failed)
- Make changes without confirming code executes
- Trust logger output (it didn't work before)
- Skip the investigation report

Current baseline (confirmed working):
- Tests: 10/15 passing (67%)
- Stress test: 10% success rate
- Services running: Redis, MongoDB, Qdrant, FastAPI

The investigation report contains:
- Detailed timeline of what was tried
- Root cause hypotheses (prioritized)
- Recommended investigation phases
- Lessons learned (what NOT to do)
- Success criteria
- Minimal reproduction test code

After you read the report, let me know:
1. Which phase you want to start with
2. What questions you have
3. What your investigation approach will be

Remember: Previous investigation failed by treating symptoms. This time we need ROOT CAUSE.
```

---

## Quick Reference (For You)

### Investigation Report Location
`docs/investigations/session-concurrency-investigation-2025-10-09.md`

### Key Sections to Reference
- **Critical Discovery** (write verification mystery)
- **Root Cause Hypotheses** (prioritized list)
- **Phase 1: Verify Observability** (concrete next steps)
- **What NOT To Do** (lessons learned)

### Starting Point Commands
```bash
# Ensure services are running
./start.sh

# Add print statements to kato/sessions/redis_session_manager.py
# Around line 244-250 in create_session method

# Run single test
./run_tests.sh --no-start --no-stop tests/tests/integration/test_session_management.py::TestSessionIsolation::test_basic_session_isolation

# Check logs
docker logs kato | grep TRACE
```

### Files You'll Need
- `kato/sessions/redis_session_manager.py` - Main session management
- `kato/api/endpoints/sessions.py` - REST endpoints
- `tests/tests/integration/test_session_management.py` - Failing tests
- `kato/services/kato_fastapi.py` - FastAPI setup

### Current Status
✅ All failed changes reverted
✅ Baseline restored (10/15 passing, 10% stress)
✅ Docker image rebuilt
✅ Tests confirmed working at baseline
⏳ Ready for fresh investigation

### Success Criteria
- [ ] Understand why verification code didn't log
- [ ] Measure actual Redis write→read latency
- [ ] Create minimal reproduction
- [ ] Identify root cause with evidence
- [ ] Improve to >90% test pass rate

---

**Document Created**: 2025-10-09
**Investigation Phase**: Phase 0 Complete (Failed approach reverted)
**Next Phase**: Phase 1 - Verify Observability
