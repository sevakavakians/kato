# Project-Manager Patterns Log
*Productivity insights, trend analysis, and assumption-to-reality mappings*

---

## Bug Patterns

### 2026-03-17 - Compound Bug: Silent Failure in Async Context

**Pattern**: A visible no-op bug masked a deeper async-context failure. The first fix (`assignNewlyLearnedToWorkers()`) was correct but incomplete — vectors were still failing to persist when called from FastAPI async endpoints due to a separate `RuntimeError: This event loop is already running` in the sync wrapper methods.

**Discovery Trigger**: Full test suite run after the initial fix revealed the secondary failure path via the event loop error.

**Assumption → Reality**:
- Assumed: Fixing the no-op in `assignNewlyLearnedToWorkers()` was the complete fix
- Reality: Sync wrapper methods (`add_vector_sync`, `add_vectors_batch_sync`) also had a latent async-context incompatibility using bare `self._loop.run_until_complete()`

**Resolution Pattern**: Replace bare `loop.run_until_complete()` calls with the safe `_run_async_in_sync()` helper that detects whether an event loop is already running.

**Lesson**: When fixing persistence failures in async FastAPI services, audit all sync wrapper methods for bare `run_until_complete()` calls. FastAPI's async context means an event loop is always running — direct `run_until_complete()` will always raise `RuntimeError` from async request handlers.

**Recurrence Risk**: Medium — this pattern can recur any time a new sync convenience wrapper is added to an async-native class without using the safe `_run_async_in_sync()` helper.

---

## Time Estimate Accuracy

| Task Type | Estimated | Actual | Accuracy |
|-----------|-----------|--------|----------|
| Vector persistence bug fix (initial) | N/A | N/A | N/A (undiscovered bug) |
| Event loop async fix (secondary) | N/A | N/A | N/A (discovered during verification) |

*Insufficient data for trend analysis. Will update as estimates are provided.*

---

## Productivity Insights

### 2026-03-17
- Two-phase bug discovery (visible symptom → hidden root cause) is a recurring pattern in async service work
- Running the full test suite immediately after a targeted fix is essential — targeted fixes in async services often have sibling failure modes
- Stress tests (5/5 passed) provided higher confidence than integration tests alone for persistence correctness
