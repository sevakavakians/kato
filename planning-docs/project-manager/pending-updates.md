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

## 2026-09-18 - Discussion Needed: Candidate-Set Bounding Strategy (USER-REQUESTED — highest priority)
**Issue**: With KATO v5.2.0 released (DECISION-032/033 — pattern metadata now fetched after top-K pruning, bounding that cost to a constant), the next-largest remaining scaling gap is upstream of it: the default `filter_pipeline` is `[]`, so every prediction request pulls **every pattern in the node** into Python (`_get_all_patterns`, no `LIMIT`) before any pruning happens at all — O(N) time and memory in the corpus size, not bounded by `max_predictions`. The user said: *"Let's discuss this after the other changes. I want to learn more about it from you before making a decision."*
**Impact**: Not an active production problem today — the user's framing is "not hurting yet — pre-empting growth" — but the target corpus scale is 100k–1M+ patterns and growing, and at that scale the full-corpus pull becomes the dominant cost regardless of how cheap the post-fetch pipeline is made.
**Suggested Action**: Present the user with measurements (not just proposals) for at least three options, then let them decide: (1) push the `recall_threshold` cutoff into ClickHouse — expressible on the stored length/token_set columns, bounds the candidate set at the source; (2) stream candidates in bounded chunks — caps peak memory without changing the eventual candidate set or result semantics; (3) reopen the recall-safe length filter derived from `recall_threshold` (`T·L/(2−T) ≤ P ≤ L·(2−T)/T`, identified during Remediation Pass 1's re-assess list, DECISION-030) — pending confirmation the bound holds for `weighted_similarity`. See `planning-docs/SPRINT_BACKLOG.md`'s "Discussion Needed: Candidate-Set Bounding Strategy" entry for the same framing kept in sync.
**Priority**: High — user-requested, explicitly the next thing to work through, though not urgent in the "actively broken" sense.
**Status**: Open

## 2026-09-17 - Decision Needed: Commit the Deprecation-Warnings + Resource-Teardown Fixes? — RESOLVED
**Issue (as originally filed)**: A complete, verified body of work clearing `DeprecationWarning`s from the 5.1.1/5.1.2 dependency upgrade (`@app.on_event`→`lifespan`, redis `close()`→`aclose()`, `httpx2`/`anyio` floor raise) plus 3 latent resource-teardown bug fixes (session manager never shut down, concurrency reporter task unmanaged, `MetricsCacheManager` Redis client leak) sat entirely uncommitted in the working tree. Local branch `perf/prediction-path-scaling` pointed at the same commit as `main` (`adc066d`) — no divergent history — so this was effectively uncommitted work directly on top of `main`.
**Impact**: Three real resource-leak bugs (confirmed via before/after shutdown-log evidence) were unfixed in the committed codebase until this landed. Low urgency in practice (each leak only manifests on process shutdown/restart, not mid-request), but it was real, verified, ready work with nothing blocking it.
**Resolution**: Committed directly (no dedicated branch/merge) as `66fa692` "fix: clear post-upgrade deprecation warnings and three teardown leaks" — 18 files, 437 insertions, 49 deletions (the 11 code/dependency/test files plus all 7 planning-docs files for this task, in the same commit). Branch remains `perf/prediction-path-scaling`. Three files belonging to a concurrent performance-work session in the same working tree (`kato/informatics/metrics.py`, `kato/workers/pattern_processor.py`, untracked `scripts/check_prediction_parity.py`) were deliberately excluded and remain uncommitted, tracked by that other session.
**Priority**: Medium — verified and ready, no known risk, was not urgent (leaks are shutdown-time only).
**Status**: Resolved (2026-09-17, commit `66fa692`)

## 2026-09-17 - Documentation Gap: v5.1.1/v5.1.2 Releases and a Benchmark Commit Are Undocumented in planning-docs
**Issue**: `planning-docs/SESSION_STATE.md`'s most recent entry before 2026-09-17 was dated 2026-09-16. Git history shows KATO was released as **v5.1.1** and **v5.1.2** on 2026-09-17 (`CHANGELOG.md` has both `[5.1.1]` and `[5.1.2] - 2026-09-17` sections; `kato/__init__.py` reads `5.1.2`; commits `5ffde69` chore: bump to 5.1.1, `c3305b1` build: fix `.dockerignore` pattern syntax, `810cc48` docs(changelog) promote to 5.1.2, `a813fdd` chore: bump to 5.1.2), and a benchmark script was added (`adc066d` "bench: add a repeatable end-to-end prediction scaling benchmark", 2026-09-17). None of this — release rationale, verification, deployment status, or the benchmark's purpose/results — is recorded in `SESSION_STATE.md`, `DECISIONS.md`, or `completed/features/`. `planning-docs/README.md`'s "Current System State" section is also stale, still describing v5.0.2 as current.
**Impact**: Planning docs no longer reflect the true state of `main` — anyone resuming work from these docs alone would not know two releases happened or why, would not know the benchmark script exists, and would see an incorrect "current version" in `README.md`.
**Suggested Action**: Run a dedicated project-manager catch-up pass (with access to the actual session/commit history for that work) to backfill `SESSION_STATE.md`, `README.md`'s Current System State, and `DECISIONS.md`/`completed/features/` as warranted for the 5.1.1/5.1.2 releases and the `adc066d` benchmark commit. This agent did not perform that work and has no first-hand record of its rationale, so it was deliberately not reconstructed here.
**Priority**: Medium — no functional impact, but the documentation-continuity gap will compound if left across further sessions.
**Status**: Open

## 2026-09-16 - Action Needed: Schedule a Full Dependency Upgrade
**Issue**: While closing out Remediation Pass 1's `requirements.lock` item, a full `pip-compile --output-file=requirements.lock requirements.txt` regeneration was run in a clean `python:3.10` container to see what it would produce. It bumped nearly every pin: `clickhouse-connect` 0.9.2→1.8.0, `redis` 6.4→8.1, `pytest` 8→9, `pydantic`, `qdrant-client` 1.15→1.19, `uvicorn` 0.37→0.53, among others. That result was **rejected** as far outside the scope of removing one unused dependency (`aioredis`) — instead, only the `aioredis` entry and its two `# via` back-references were removed surgically from the existing lock file, leaving every other pin byte-identical. The image was verified to build and to be free of `aioredis`.
**Impact**: `requirements.lock` is now internally consistent with `requirements.txt` again (the immediate goal), but the project's pins are increasingly far behind current upstream releases across several major/minor versions — a growing gap that will only get riskier to cross the longer it's deferred.
**Suggested Action**: Schedule a dedicated pass to evaluate and apply the full dependency upgrade — each major-version jump (`redis` 6→8, `qdrant-client` 1.15→1.19, `pytest` 8→9, etc.) should get its own changelog review and targeted test run before being accepted, not a single blind `pip-compile` + rebuild.
**Priority**: Medium — no known live breakage from the current pins, but the drift is accumulating and each cycle of deferral increases the blast radius of eventually doing it.
**Status**: Open

## 2026-09-16 - Action Needed: Set `REDIS_PASSWORD`, Then Re-Enable `protected-mode`
**Issue**: Remediation Pass 1 (DECISION-030) originally claimed `protected-mode no` was safely removed from `config/redis.conf` after "verifying container-to-container access still works." That verification was invalid: `redis:7-alpine` (7.4.8) already ships `protected-mode no` as its own image default, so removing the line had no effect either way, and protected mode was never actually tested *on*. When genuinely tested with `protected-mode yes` set, cross-container Redis connections were refused outright, even with an explicit `bind` directive — only a configured password exempts a connection from that check. `protected-mode no` has been reverted (restored, now set explicitly rather than relying on the image default) — see DECISION-030's correction note and DECISION-031's archive, commit `8deab2c`.
**Impact**: Redis currently has no application-level authentication. What protects it today is solely the host-published port being bound to `127.0.0.1` (applied in both `docker-compose.yml` and `deployment/docker-compose.yml`) — there is no password, and `protected-mode` cannot be safely re-enabled without one (it would just break legitimate container-to-container access the same way it blocked the test).
**Suggested Action**: Set `REDIS_PASSWORD` (a `requirepass` equivalent) across the compose configs and any client connection strings, verify container-to-container access still works with it in place, then re-enable `protected-mode yes`.
**Priority**: Medium — bounded by the trusted-network deployment scoping decision (DECISION-030), but this is the natural next step in that same hardening line, and the previous claim that it was already handled needs replacing with real protection.
**Status**: Open

## 2026-09-16 - Action Needed: Harden the Dashboard (Default Credentials, Docker Socket Mount, Public Port)
**Issue**: The dashboard still ships default credentials `admin`/`changeme`, mounts the Docker socket read-write, and publishes port 3001 on all interfaces (not loopback-only like the backing stores were bound in Remediation Pass 1 + its follow-on). Flagged in the original comprehensive review that produced Remediation Pass 1 but never addressed by any pass to date — explicitly out of scope for both DECISION-030 and DECISION-031.
**Impact**: On a trusted-network deployment this is lower urgency than an internet-facing one, but a read-write Docker socket mount behind default credentials is a full host-compromise path for anyone who reaches the dashboard, and default credentials are the kind of thing that gets missed at deployment time.
**Suggested Action**: Rotate the default credentials (or require setting them, refuse to start with the defaults), bind port 3001 to `127.0.0.1` to match the backing-store hardening already applied, and re-assess whether the dashboard actually needs Docker-socket read-write access or could work with a narrower capability.
**Priority**: Medium-High — the Docker socket mount specifically is a significant privilege-escalation surface if the dashboard is ever reachable by an untrusted party.
**Status**: Open

## 2026-09-11 - Release Needed: v5.0.2 Lacks the Prediction Segmentation Fix (now expanded — Remediation Pass 1 + DECISION-031 also unreleased) — RESOLVED
**Issue (as originally filed)**: `e0ee17d` (2026-09-11, DECISION-028) fixed a real correctness bug — prediction segmentation misattributed events (phantom `missing` symbols) when a symbol recurs across events, plus made the single-symbol fast path return event-structured fields. `34910a70` (2026-09-11, DECISION-029) fixed a second, related bug the first fix's own audit surfaced. **Update 2026-09-16**: the released image was further behind still — it also lacked the entire Remediation Pass 1 body of work (`df9a76a`/`7233155`: 7 live bug fixes, SQL-injection parameterization, CORS/store hardening) and DECISION-031 (`7bae726`: the prediction-ranking nondeterminism fix and the ProcessPoolExecutor performance fix). The then-released **v5.0.2** image included none of this; the deployment stack ran an unreleased local `kato:latest` dev build with everything.
**Resolution**: **KATO v5.2.0** released 2026-09-18 (MINOR bump) — ships every commit this entry was tracking (`e0ee17d`, `34910a70`, `df9a76a`/`7233155`, `8deab2c`, `7bae726`), plus the deprecation-warnings/teardown fixes (`66fa692`) and this session's own metadata-after-prune + cross-worker determinism work (DECISION-032). Images `ghcr.io/sevakavakians/kato:5.2.0`/`:5.2`/`:5`/`:latest` published; GitHub release https://github.com/sevakavakians/kato/releases/tag/v5.2.0. See DECISION-033 and `planning-docs/completed/features/2026-09-18-kato-v5.2.0-release.md`.
**Verification**: pre-release gates (ruff, bandit, pip-audit) clean; full suite 625 passed / 3 skipped / 1 xfailed / 0 failed; fresh-pull image verification confirmed the published artifact matches source; post-release end-to-end observe/learn/predict cycle verified against the deployed image with zero data loss.
**Resolved**: 2026-09-18

## 2026-09-11 - Decision Needed: Should the Single-Symbol Fast Path Match Any Position, Not Just the First Token?
**Issue**: `_predict_single_symbol_fast` (`kato/workers/pattern_processor.py`) only considers candidate patterns whose **first token** equals the observed symbol — a deliberate design choice (per its docstring) that uses the ClickHouse `first_token` column for speed. As a result, observing a single symbol that appears only mid-pattern (not as the first token of any learned pattern) yields **no prediction**, even though that same symbol as part of a two-symbol observation would match normally via the general path. This is pinned as current behavior by a test in `tests/tests/unit/test_multi_symbol_event_predictions.py` (DECISION-028).
**Impact**: Users relying on single-symbol observations to surface mid-pattern predictions will silently get nothing from the fast path today. This is existing, not new, behavior.
**Suggested Action**: Decide whether to (a) keep current behavior (fast, but misses mid-pattern single-symbol matches) or (b) extend single-symbol matching to any position — would require either falling back to the general (slower) path for single-symbol observations or building a symbol-position index, trading some of the fast path's speed advantage for completeness.
**Priority**: Low-Medium — correctness-adjacent (arguably a documented limitation, not a bug) but affects real prediction completeness for single-symbol queries.
**Status**: Open

---

## Resolved Issues

## 2026-09-16 - Decision Needed: Commit and Merge `chore/remediation-pass-1`? — RESOLVED (see also three more Remediation Pass 1 items resolved the same day, immediately below)
**Issue (as originally filed)**: Remediation Pass 1 (7 live bug fixes, SQL-injection parameterization, CORS/store-binding hardening, performance quick-wins, ~10,100 lines of dead code removed, new CI workflow, 43 new tests) was complete and verified but sat entirely uncommitted on branch `chore/remediation-pass-1`.
**Resolution**: Committed as `df9a76a` "fix: repair dead error handling, SQL parameterization, and data-loss bugs (Remediation Pass 1)" and merged to `main` via no-ff merge `7233155`.
**Resolved**: 2026-09-16

## 2026-09-16 - Action Needed: Regenerate `requirements.lock` After `aioredis` Removal — RESOLVED
**Issue (as originally filed)**: Remediation Pass 1 dropped the unused `aioredis` dependency from `requirements.txt` but `requirements.lock` was not regenerated to match.
**Resolution**: A full `pip-compile` regeneration was attempted and rejected as out of scope (see the new "Schedule a Full Dependency Upgrade" item above for that follow-on). Instead, only the `aioredis` entry and its two `# via` back-references were removed surgically from `requirements.lock`, leaving every other pin untouched. Verified the image builds and is free of `aioredis`.
**Resolved**: 2026-09-16

## 2026-09-16 - Decision Needed: Clean Up 4,464 Orphan Redis Prediction Keys? — RESOLVED
**Issue (as originally filed)**: Remediation Pass 1 fixed `RedisWriter.write_prediction`'s unbounded leak going forward, but the 4,464 pre-existing orphan keys (TTL `-1`) it already produced were deliberately left alone pending approval.
**Resolution**: All 4,464 keys deleted with `UNLINK`, after verifying every one matched the expected `<kb_id>:prediction:obs-<hex>` shape (nothing outside the known leak pattern touched). The 549 keys written after the TTL fix were deliberately left — they carry a correct TTL and expire on their own. Redis `DBSIZE` 44057 → 39593; verified zero surviving prediction keys without a TTL afterward.
**Resolved**: 2026-09-16

## 2026-09-16 - Action Needed: Full Stack Recreate to Apply `docker-compose.yml`/`redis.conf` Binding Changes — RESOLVED
**Issue (as originally filed)**: The store-binding security fix (Redis/ClickHouse/Qdrant bound to `127.0.0.1`, `protected-mode no` removed) was written but only the `kato` service had been recreated during verification.
**Resolution**: Full stack recreated. Data integrity verified before/after: Redis `DBSIZE` 39593 unchanged, ClickHouse 8824 patterns / 19513 metadata rows / 301 distinct `kb_id`s unchanged, all 84 Qdrant collections recovered, end-to-end observe/learn/predict verified. A `redis-cli SAVE` was taken first. Loopback bindings were additionally applied to `deployment/docker-compose.yml` (the compose project the running stack actually uses) — the original fix had only touched the root `docker-compose.yml`, which alone had no effect on the live deployment. Separately, the `protected-mode no` removal itself was found invalid and reverted — see the new "Set `REDIS_PASSWORD`" item above.
**Resolved**: 2026-09-16

---

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
