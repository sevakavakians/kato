# Pending Updates - Human Review Required

## Purpose
Track issues and updates that require human intervention or review.

## Format
```markdown
## [Timestamp] - [Issue Type]
**Issue**: Brief description
**Impact**: How this affects development
**Suggested Action**: Recommended resolution
**Priority**: Critical/High/Medium/Low
**Status**: Open/In Review/Resolved
```

## Current Issues

*No open issues at this time.*

---

## Resolved Issues

## 2026-09-10 - Release Needed: Main Has the Deadlock Fix + Phase 1.6 Refactor, But No Released Image Does — RESOLVED
**Issue (as originally filed)**: The "Multi-Worker Uvicorn + Concurrent Training Safety" initiative was COMPLETE on `main` — the observe-path deadlock stopgap (DECISION-025, `9de98c3`) and the Phase 1.6 lock-free refactor that replaced it (DECISION-026, `b155cb5`) were both committed. The released **v5.0.1** image (and every image tagged before it) still had the original deadlock bug: any two overlapping observe requests for the same `node_id` would permanently hang a uvicorn worker. The deployment stack was running an unreleased local `kato:latest` build with the fix, not a published image.
**Impact**: Anyone pulling `ghcr.io/sevakavakians/kato:5.0.1`/`:5.0`/`:5`/`:latest` got a build that deadlocks under realistic concurrent training load (several threads training on one node) — a production-severity bug in every image published at the time.
**Resolution**: The user chose a patch bump. KATO **v5.0.2** was released 2026-09-10 via `./container-manager.sh patch` (AUTO_MODE) — bump commit `b76d955`, tag `v5.0.2` pushed to origin, GitHub release published (https://github.com/sevakavakians/kato/releases/tag/v5.0.2), images `ghcr.io/sevakavakians/kato:5.0.2`/`:5.0`/`:5`/`:latest` built and verified (digest `sha256:6c46ff688321…`). Deployment stack re-pinned from the local build to the registry image. See DECISION-027 (`planning-docs/DECISIONS.md`) and `planning-docs/completed/features/2026-09-10-kato-v5.0.2-release.md`.
**Verification**: Worker-topology suite 18/18 against the deployed image; full suite 482 passed / 4 skipped / 1 xfailed / 0 failed (675.08s); store-parity tool 0 mismatched `kb_id`s. A post-release topology-test fragility (`test_session_count_converges_on_every_worker`, unrelated to the release contents — a shared-Redis global-counter racing the deployment container's own expiry sweep) was found and fixed same day (`61e16cd`); topology suite 18/18 after the fix.
**Resolved**: 2026-09-10

## 2026-09-10 - Observe Path Deadlock: Fix Approach Decision Needed (Blocks Multi-Worker Initiative Closure) — RESOLVED
**Issue (as originally filed)**: While running the new Phase C perf test (`tests/tests/performance/test_multi_worker_throughput.py`) for the "Multi-Worker Uvicorn + Concurrent Training Safety" initiative, discovered that the `observe` path deadlocks any uvicorn worker that receives two overlapping requests for the same `node_id`. `kato/workers/observation_processor.py:346` holds a blocking `multiprocessing.Lock` (created at line 53) across an `async`/`await` boundary in `kato/workers/kato_processor.py:281` (`observe`) — request A holds the lock and awaits, request B blocks the thread trying to acquire it, and A can never resume. `/health` stops responding because the event loop itself is blocked. Reproduced deterministically twice: 8 threads × one session each on one node → 1-worker container dies after exactly 9 patterns; 4-worker container's driver stalls at 28/161 patterns, after which only 2 of 4 worker pids still answer `/health`. This is exactly the initiative's target workload (several threads training on one node). Root design issue: the "BRIDGE" pattern loads session STM into shared `pattern_processor` instance state before the lock is even taken, so concurrent requests on the same processor would corrupt each other's STM at await points regardless of lock placement — this is the CLAUDE.md "TODO (Phase 1.6/1.7)" bridge follow-up. Both the active lock (introduced in `52e9284`) and a second, unused `multiprocessing.Lock` at `kato/workers/kato_processor.py:73` violate this project's no-locks rule.
**Impact**: The Multi-Worker Uvicorn + Concurrent Training Safety initiative could not be verified or closed — Phase C (throughput verification) could not pass while the exact concurrency shape it tests deadlocked the server.
**Resolution**: User decided **"Do A as a stopgap now, then B."** Option A (one `asyncio.Lock` per `KatoProcessor` around the `observe`/`learn`/`get_predictions` bridge sections; both `multiprocessing.Lock`s deleted) shipped the same day, committed as `9de98c3`. Option B (the Phase 1.6 per-request working-state refactor that removes the lock entirely) is now the active task — see DECISION-025 (`planning-docs/DECISIONS.md`) for full rationale, verification, and Phase 1.6 work items.
**Verification**: Deadlock reproduction (8 threads × one session, 20 rounds) now completes 161/161 patterns on both 1- and 4-worker topologies (previously died at 9 and stalled at 28/161); Phase C perf test passes on both topologies with `KATO_PERF=1`; full suite 479 passed / 4 skipped / 1 xfailed / 0 failed (648s).
**Resolved**: 2026-09-10

## 2026-09-09 - Release Version Bump Decision Needed (Breaking API Change, Not Yet Released) — RESOLVED
**Issue (as originally filed)**: DECISION-019 (`planning-docs/DECISIONS.md`) redefined the `anomalies` prediction field (flat deviation list) and added a new `fuzzy_matches` field, moving the `{observed, expected, similarity}` fuzzy-match detail out of `anomalies`. This is a breaking change for any API consumer currently reading fuzzy-match details from `anomalies`. At filing time, nothing from this work had been committed.
**Impact**: Per this repo's semver workflow (`CLAUDE.md` "Container Manager Workflow Protocol"), this warranted a **major** version bump, not patch/minor — the call was deliberately left to the user rather than made unilaterally by the agent doing the code work.
**Resolution**: The user decided to proceed. KATO **v5.0.0** was released the same day (2026-09-09) via `./container-manager.sh major` (AUTO_MODE) — bump commit `5c4b282`, tag `v5.0.0` pushed to origin, GitHub release published (https://github.com/sevakavakians/kato/releases/tag/v5.0.0), images `ghcr.io/sevakavakians/kato:5.0.0`/`:5.0`/`:5`/`:latest` built and verified. No deprecation/compatibility shim for `anomalies` consumers was added — the major bump itself is the compatibility signal. See DECISION-022 (`planning-docs/DECISIONS.md`) and `planning-docs/completed/features/2026-09-09-kato-v5.0.0-release.md`.
**Verification**: Pre-release full suite 475 passed / 4 skipped / 0 failed; ruff finding count in `kato/` unchanged (283, pre-existing).
**Resolved**: 2026-09-09

---

## 2026-09-09 - Cross-Worker WebSocket Broadcaster Fix: Priority Decision Needed — RESOLVED
**Issue (as originally filed)**: DECISION-020 confirmed deterministically that `kato/websocket/event_broadcaster.py`'s in-process `EventBroadcaster` cannot deliver websocket events across uvicorn workers at `KATO_WORKERS=2`/`4` (the container's default). The fix had not been started and needed a human priority decision before the next release.
**Resolution**: The fix was requested and completed the same day (2026-09-09), committed as `ba3d194`. `EventBroadcaster.broadcast_event` now publishes to a Redis pub/sub channel (`kato:ws_events`); every uvicorn worker subscribes at startup and delivers received events to its own local connections, giving exactly-once delivery per client with no locks. See DECISION-021 (`planning-docs/DECISIONS.md`) and `planning-docs/completed/features/2026-09-09-websocket-cross-worker-broadcaster-redis-pubsub.md`.
**Verification**: New `tests/tests/unit/test_event_broadcaster.py` (6 tests) plus the existing `tests/tests/integration/test_worker_topology.py`, now passing 15/15 across `KATO_WORKERS` in {1, 2, 4} (previously 6 deterministic failures at {2, 4}). Full suite: 475 passed / 4 skipped / 0 failed.
**Note**: This resolves only the websocket-delivery half of the broader "Bug: Multi-worker (KATO_WORKERS=4) breaks websocket event delivery and concurrent session modification consistency" backlog entry. The separate `test_concurrent_session_modifications` concurrent-write-loss symptom is **not** addressed by this fix and remains open — see `planning-docs/SPRINT_BACKLOG.md`.
**Resolved**: 2026-09-09

---

*Resolved issues will be moved here with resolution notes*

---

*This file is automatically maintained by the project-manager agent*
