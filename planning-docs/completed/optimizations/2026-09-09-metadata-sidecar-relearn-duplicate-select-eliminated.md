# Optimization: Eliminate Duplicate ClickHouse SELECT on the Metadata Sidecar Re-Learn Path

**Completed**: 2026-09-09
**Type**: Optimization (redundant round-trip elimination) + backlog item framing correction
**Impact**: Re-learn path drops from 2 ClickHouse SELECTs to 1 (measured, not estimated)
**Files**: 2 files, +39/-5
**Corrects**: The P2 "Metadata sidecar write path is un-batched" backlog item filed 2026-09-08 during the configuration audit (see `planning-docs/SPRINT_BACKLOG.md`, `planning-docs/DECISIONS.md` DECISION-017's forward pointer, and DECISION-018 below)

---

## Framing Correction (Read This First)

The original backlog item said the fix "needs a batched upsert call shape at the `learnPattern` level." **That is not achievable.**

- `pattern_processor.learn()` builds exactly **one** `Pattern` per call and clears STM.
- `POST /sessions/{id}/learn` never fans out to multiple patterns.
- There is therefore no batch to form *within* a single request.
- Forming one *across* requests would require a per-worker buffer — exactly what commit `f809a84` removed, because per-worker buffers orphaned rows invisible to KATO's other 3 uvicorn workers (see DECISION-017).

**Corrected framing**: the fix eliminates round trips; it does not group them.

**Nuance**: `observe-sequence` with `learn_after_each=True` can issue N+1 `learnPattern` calls within one HTTP request. Even there, batching those calls together is not safe — the loop is strictly sequential because each `learnPattern` mutates Redis stats (frequency, SETNX-based `is_new`) that the next iteration's `learnPattern` reads.

This correction is recorded here and in DECISION-018 (`planning-docs/DECISIONS.md`) specifically so a future optimizer does not re-attempt call-level batching.

---

## Root Cause

On the re-learn path, the **same ClickHouse row was SELECTed twice per learn**:

1. `kato/informatics/knowledge_base.py` calls `metadata_router.get_metadata()`, which fetches the full row via `get_pattern_metadata_batch` (entropy, normalized_entropy, global_normalized_entropy, tf_vector, emotives, metadata) — then **discards** the four metric columns, keeping only emotives/metadata. It also does a Redis `MGET` for frequency that `learnPattern` never uses.
2. `metadata_router.upsert_pattern_metadata` then re-issues the **identical SELECT** purely to recover the metric columns discarded in step 1, so it can merge them with the new write.

Net: 2 SELECTs carrying redundant work, plus an unused Redis round trip, per re-learned pattern.

## Fix

- **`kato/storage/metadata_router.py`**:
  - New `get_metadata_for_merge(pattern_name)` — returns the raw full ClickHouse row (keeps the metric columns that `get_metadata()` discards; skips the Redis frequency lookup `learnPattern` never uses).
  - `upsert_pattern_metadata` gained an optional `prev` parameter: a caller that already read the row can hand it over instead of paying for a second SELECT. `prev=None` preserves the prior self-reading behavior for every other caller (no behavior change for callers that don't pass it).
- **`kato/informatics/knowledge_base.py`**: the re-learn branch now calls `get_metadata_for_merge()` once and threads that same dict through to `upsert_pattern_metadata(..., prev=...)`.

## Measured Result (Not Estimated)

- **Deterministic unit-level proof**, instrumenting `get_pattern_metadata_batch` call counts:
  - `upsert_pattern_metadata` without `prev`: 1 SELECT (inside upsert).
  - `get_metadata_for_merge` + `upsert_pattern_metadata(prev=...)`: 1 SELECT total, 0 inside upsert.
  - Re-learn path: **2 SELECTs → 1 SELECT**.
- **End-to-end against the running container**, background noise measured and subtracted (idle drift was only 2 queries/30s): **8 ClickHouse queries per re-learn before → 7.27 after**.
- **Correctness check specific to this change's risk** (does the metric-column merge still survive when threaded through `prev` instead of self-read): entropy (1.25) and `tf_vector` verified to survive a `prev`-threaded upsert directly.
- `tests/tests/unit/test_emotives_comprehensive.py` + `tests/tests/unit/test_metadata_comprehensive.py`: 22 passed.
- Full suite via `./run_tests.sh --no-start --no-stop`: **452 passed, 4 skipped, 3 failed** — best result recorded this session; the 3 failures are the known pre-existing multi-worker `session_cleanup` + websocket issues (see `planning-docs/SPRINT_BACKLOG.md`), unrelated to this change.

---

## Design Constraint — Record Prominently (Do Not Regress)

The read inside `upsert_pattern_metadata` on the **NEW-pattern** branch looks redundant — a genuinely new pattern has no metadata row yet, so the SELECT returns empty — but it was **deliberately kept**, and a code comment now explains why:

`is_new` is derived from a Redis `SETNX` on the frequency key. Redis can be empty while ClickHouse still holds the row — precisely the state after a Redis data loss followed by rehydrate-from-ClickHouse. This project has hit that exact scenario **twice**: the April 2026 Redis persistence incident (see memory `redis_persistence_data_loss_2026_04_13.md`) and the conftest `FLUSHALL` bug during this same working session (see `planning-docs/completed/bugs/2026-09-08-conftest-redis-flushall-scoped-to-ephemeral-keys.md`). Skipping that read on the "new" branch would silently destroy the retained emotives and precomputed metrics of every rehydrated pattern on its next learn.

**Also record**: `wait_for_async_insert=1` on this metadata sidecar path is **load-bearing** — unlike `patterns_data`, which correctly uses `wait_for_async_insert=0`. Emotives accumulation is a cross-process read-modify-write; a re-learn landing inside the ~200ms async-insert buffer window would read stale emotives and silently drop the intervening learn. Do not "optimize" this path to `wait_for_async_insert=0` without first removing the read-modify-write shape (see Open Follow-Up below).

---

## Open Follow-Up (Not Done — Structural Fix Still Needed)

The remaining and larger fix is **not applied here**: make emotives/metadata append-only, applying `persistence` at read time (`groupArray` + tail for emotives; `groupUniqArray` for the metadata set-union) instead of merging on write. That removes the read-modify-write entirely, allows `wait_for_async_insert=0` on this path, and collapses both the new-pattern and re-learn paths to a single non-blocking insert.

**Cost**: a schema split of `patterns_metadata` into an append-only emotives/metadata table plus a replace-semantics metrics table (entropy/normalized_entropy/global_normalized_entropy/tf_vector), a backfill of existing rows, and updates to every emotives reader.

Tracked as an open backlog item — see `planning-docs/SPRINT_BACKLOG.md` ("Follow-up: Metadata sidecar read-modify-write round trip").

---

## Minor, Unrelated Finding (Filed, Not Fixed)

`tests/tests/unit/test_bayesian_metrics.py::test_bayesian_likelihood_equals_similarity` is flaky under full-suite load — failed once with "Should have at least one prediction," then passed 5/5 in isolation. Likely a learn→predict race against the ~200ms `patterns_data` `async_insert` visibility window (same underlying mechanism as the already-tracked Root Cause #1 item in `planning-docs/SESSION_STATE.md`). Filed as P3 test-flakiness, not a regression from this change — see `planning-docs/SPRINT_BACKLOG.md`.

## Completion Date
2026-09-09
