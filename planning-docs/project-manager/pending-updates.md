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

## 2026-09-16 - Decision Needed: Commit and Merge `chore/remediation-pass-1`?
**Issue**: Remediation Pass 1 (7 live bug fixes, SQL-injection parameterization, CORS/store-binding hardening, performance quick-wins, ~10,100 lines of dead code removed, new CI workflow, 43 new tests — see DECISION-030 and `planning-docs/completed/features/2026-09-16-remediation-pass-1.md`) is complete and verified (full suite 588 passed / 3 skipped / 1 xfailed / 0 failed) but sits entirely **uncommitted** on branch `chore/remediation-pass-1`. Nothing here is protected by version control yet.
**Impact**: Until committed, this work exists only in the working tree — vulnerable to loss from any destructive git operation, a `git stash` mishap, or simply not being there next session.
**Suggested Action**: Review the branch's diff, commit (likely as several logical commits given the breadth — bugs / security / performance / dead-code-removal / CI are natural boundaries), and decide whether to merge directly to `main` or open a PR first.
**Priority**: High — real, verified fixes for production-severity bugs sitting unprotected.
**Status**: Open

## 2026-09-16 - Action Needed: Regenerate `requirements.lock` After `aioredis` Removal
**Issue**: Remediation Pass 1 dropped the unused `aioredis` dependency from `requirements.txt` (no importer anywhere; everything uses `redis.asyncio`), but `requirements.lock` was not regenerated to match, per `CLAUDE.md`'s standing rule ("After editing requirements.txt, regenerate lock file").
**Impact**: `requirements.lock` is now stale relative to `requirements.txt`. Low risk in practice (removing an unused package from the lock file is unlikely to break a build), but leaves the two files out of sync.
**Suggested Action**: Run `pip-compile --output-file=requirements.lock requirements.txt` then `docker compose build --no-cache kato`, before or alongside committing the branch.
**Priority**: Medium — should happen before/with the commit in the item above, not urgent on its own.
**Status**: Open

## 2026-09-16 - Decision Needed: Clean Up 4,464 Orphan Redis Prediction Keys?
**Issue**: Remediation Pass 1 fixed `RedisWriter.write_prediction`'s unbounded leak (it used `set()` with no TTL; now `setex` with the session TTL), but the 4,464 pre-existing orphan keys (TTL `-1`) this bug already produced — ~11% of the 38,902-key database at audit time — were deliberately left alone, not cleaned up.
**Impact**: Those keys continue occupying Redis memory indefinitely until manually removed; the fix only stops the leak from growing further.
**Suggested Action**: Write and run a small one-off cleanup script (find keys matching the prediction-key pattern with TTL `-1`, delete them) — given this project's prior Redis-data-loss incident (`redis_persistence_data_loss_2026_04_13.md`, project memory), this needs explicit user approval before running against the live store, and should be scoped precisely to avoid touching anything else.
**Priority**: Medium — memory growth, not correctness; bounded and non-urgent, but should not be left indefinitely.
**Status**: Open

## 2026-09-16 - Action Needed: Full Stack Recreate to Apply `docker-compose.yml`/`redis.conf` Binding Changes
**Issue**: Remediation Pass 1 bound the backing stores (Redis 6379, ClickHouse 8123/9000, Qdrant 6333) to `127.0.0.1` in `docker-compose.yml` and removed `protected-mode no` from `config/redis.conf`, closing unauthenticated-access-from-the-host exposure. These changes only take effect on a full container recreate for each affected service — during this pass's live verification, only the `kato` service itself was recreated (to pick up the code fixes), so Redis/ClickHouse/Qdrant are still running under their pre-change container configuration.
**Impact**: The store-binding security fix is written but not yet in effect on the running stack.
**Suggested Action**: Once the branch is committed (see item above), do a full `docker compose down && docker compose up -d` (or equivalent, service-by-service) to recreate Redis/ClickHouse/Qdrant with the new bindings. Verify container-to-container access still works afterward (already smoke-tested once during this pass, per the archive entry) and that host access is now refused.
**Priority**: Medium — the fix exists but isn't live yet; do alongside or shortly after the branch commit/merge.
**Status**: Open

## 2026-09-11 - Release Needed: v5.0.2 Lacks the Prediction Segmentation Fix (now two fixes)
**Issue**: `e0ee17d` (2026-09-11, DECISION-028) fixed a real correctness bug — prediction segmentation misattributed events (phantom `missing` symbols) when a symbol recurs across events, plus made the single-symbol fast path return event-structured fields. `34910a70` (2026-09-11, DECISION-029) fixed a second, related bug the first fix's own audit surfaced — the flat matcher's difflib tie-break could still attribute a missing/extra symbol to the wrong event, or mismatch a lone symbol against the wrong occurrence — see `planning-docs/completed/features/2026-09-11-multi-symbol-event-prediction-tests-and-segmentation-fix.md` and `planning-docs/completed/features/2026-09-11-event-aware-alignment-refinement.md`. The currently released **v5.0.2** image includes neither fix; the deployment stack is running an unreleased local `kato:latest` dev build with both.
**Impact**: Anyone pulling `ghcr.io/sevakavakians/kato:5.0.2`/`:5.0`/`:5`/`:latest` gets a build that can report incorrect `missing`/`extras`/`present` for predictions involving patterns with repeated symbols across events — a real-but-narrow correctness bug in the current published image.
**Suggested Action**: Release a **v5.0.3** patch (bug fix, no API contract change — field names/shapes unchanged, only internal derivation) via `./container-manager.sh patch`, following the same process as v5.0.1/v5.0.2 (DECISION-023/DECISION-027), bundling both `e0ee17d` and `34910a70`.
**Priority**: Medium — real bug, but narrow trigger condition (repeated symbols across events); not a deadlock/data-loss class issue like the v5.0.2 release gap.
**Status**: Open

## 2026-09-11 - Decision Needed: Should the Single-Symbol Fast Path Match Any Position, Not Just the First Token?
**Issue**: `_predict_single_symbol_fast` (`kato/workers/pattern_processor.py`) only considers candidate patterns whose **first token** equals the observed symbol — a deliberate design choice (per its docstring) that uses the ClickHouse `first_token` column for speed. As a result, observing a single symbol that appears only mid-pattern (not as the first token of any learned pattern) yields **no prediction**, even though that same symbol as part of a two-symbol observation would match normally via the general path. This is pinned as current behavior by a new test (`tests/tests/unit/test_multi_symbol_event_predictions.py`) added in `e0ee17d` (2026-09-11, DECISION-028) — the fix that commit shipped only made the fast path's *output shape* consistent (event-structured fields), not its matching scope.
**Impact**: Users relying on single-symbol observations to surface mid-pattern predictions will silently get nothing from the fast path today. This is existing, not new, behavior — the recent work only made it more visible/documented.
**Suggested Action**: Decide whether to (a) keep current behavior (fast, but misses mid-pattern single-symbol matches) or (b) extend single-symbol matching to any position — would require either falling back to the general (slower) path for single-symbol observations or building a symbol-position index, trading some of the fast path's speed advantage for completeness.
**Priority**: Low-Medium — correctness-adjacent (arguably a documented limitation, not a bug) but affects real prediction completeness for single-symbol queries.
**Status**: Open

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
