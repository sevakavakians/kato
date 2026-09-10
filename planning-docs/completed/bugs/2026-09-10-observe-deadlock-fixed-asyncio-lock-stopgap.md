# Observe-Path Deadlock Fixed — asyncio.Lock Stopgap (DECISION-025 Option A)

**Completed**: 2026-09-10
**Status**: COMPLETE (stopgap) — committed as `9de98c3` "fix(workers): stop deadlocking a worker on overlapping same-node requests"
**Decision**: DECISION-025 (`planning-docs/DECISIONS.md`)
**Decision context**: Multi-Worker Uvicorn + Concurrent Training Safety initiative, Phase C
**Type**: Bug fix (critical — production-breaking deadlock), explicitly a stopgap; Phase 1.6 (lock-free) is the immediate follow-on

## Summary

While verifying Phase C of the Multi-Worker Uvicorn initiative, the new perf test (`test_multi_worker_throughput.py`) exposed a severe, deterministic deadlock: any two overlapping `observe` requests for the same `node_id` permanently hung the uvicorn worker process handling them, taking `/health` down with it (the event loop itself was blocked). This is exactly the initiative's target workload (several threads training on one node), so it blocked the initiative's closure.

Root cause: `kato/workers/observation_processor.py` held a blocking `multiprocessing.Lock` across an `async`/`await` boundary in `kato/workers/kato_processor.py`'s `observe` — request A holds the lock and awaits, request B blocks the thread trying to acquire it, and A can never resume on a single event loop.

The user decided: **"Do A as a stopgap now, then B."** This entry documents Option A, shipped the same day.

## What Changed

### `kato/workers/kato_processor.py`
- New `self._bridge_lock = asyncio.Lock()` per `KatoProcessor` instance.
- `learn` converted to `async def` (previously sync).
- The bridge sections of `observe`, `learn`, and `get_predictions` wrapped in `async with self._bridge_lock:` — an await-aware lock that yields the event loop instead of blocking the OS thread.
- The second, unused `multiprocessing.Lock` (dead code, old line 73) removed.

### `kato/api/endpoints/sessions.py`
- 3 call sites of `processor.learn(...)` updated to `await` it, since `learn` is now a coroutine.

### `kato/workers/observation_processor.py`
- The `multiprocessing.Lock` (created at old line 53) and its `with self.processing_lock:` block removed entirely.

### `Dockerfile`
- `HEALTHCHECK` fixed: was `python -c "import requests; ..."`, but `requests` is not installed in the image, so `docker run` containers always reported unhealthy. Switched to `urllib`, matching what compose-based deployments already used (unaffected by this bug, since they use `urllib`).

### Tests
- New `tests/tests/performance/test_multi_worker_throughput.py` (Phase C, opt-in `KATO_PERF=1`): per-request timeouts; asserts speedup > 1, exact pattern counts, exact shared-pattern frequency (threads × rounds), Redis/ClickHouse agreement, every worker still answering `/health` after the run, and a clean clear-all.

### Docs
- `docs/developers/testing.md` — new perf-test section.
- `docs/users/parallel-processing.md` — note that same-node requests now serialize within a worker under this stopgap (still parallel across workers).
- `CHANGELOG.md` `[Unreleased]` entries.

## Verification

- **Deadlock reproduction** (8 threads × one session each on one node, 20 rounds): before the fix, the 1-worker container died at 9 patterns and the 4-worker container stalled at 28/161 with 2 of 4 workers dead; after the fix, both topologies complete 161/161 patterns, shared-pattern frequency exactly 160, all workers still answering `/health`. 4 workers were 1.9× faster than 1 on that run (58.6s vs 31.2s).
- **Perf test** (`KATO_PERF=1`, 8 threads × 10 rounds): PASSED on both topologies; speedup 1.15× measured while the full suite ran concurrently (noisy environment); all integrity assertions held.
- **Full suite**: 479 passed / 4 skipped / 1 xfailed / 0 failed (648s). Previous baseline 475/4/0 — the +4 are the new Phase A store-cleanup tests; the xfail is the DECISION-024 documented limitation.

## Why This Is a Stopgap, Not the Final Fix

`_bridge_lock` still serializes concurrent requests to the same `KatoProcessor` (same `node_id`) within a worker — a real, if narrower, instance of the pattern this project's no-locks rule (`CLAUDE.md`: "remember to not create locks for this project") exists to prevent. The underlying design issue is the "BRIDGE" pattern: session STM is loaded into shared `pattern_processor` instance state for the duration of a request. DECISION-025 makes the Phase 1.6 refactor (threading per-request working state through instead of mutating shared instance state, then deleting `_bridge_lock` entirely) the immediate next task, not a someday item.

## Related

- DECISION-025 in `planning-docs/DECISIONS.md` — full rationale, alternatives considered, and Phase 1.6 work items.
- `planning-docs/project-manager/pending-updates.md` — the "Observe Path Deadlock" human-alert entry this resolves (moved to Resolved Issues).
- Multi-Worker Uvicorn + Concurrent Training Safety initiative, `planning-docs/SPRINT_BACKLOG.md` (Active Projects) — Phase C (stopgap done) and Phase 1.6 (now active).
- Sibling commits from the same day: `7aad817` (Phase A), `bef2b47` (Phase B).
- ADR-001 (stateless processor architecture) — Phase 1.6 completes that architecture's original intent for the observe/learn/predict bridge sections.
