# SESSION_STATE.md - Current Development State
*Last Updated: 2026-09-11 (event-aware alignment refinement fix — COMPLETE, committed `34910a70`; see "Current Task" and "Previous Task" below)*

## Current Task
**None.** No active task in progress. Next action is user-driven: pick an item from `planning-docs/SPRINT_BACKLOG.md`'s Backlog section.

**Two pending human decisions carried forward** (see `planning-docs/project-manager/pending-updates.md` for full detail):
1. **v5.0.3 release** — released v5.0.2 lacks both `e0ee17d` (DECISION-028, position-based segmentation) and `34910a70` (DECISION-029, event-aware alignment refinement, below). The deployment stack runs the local `kato:latest` dev build with both fixes. Decide whether/when to cut a patch release via `./container-manager.sh patch`.
2. **`_predict_single_symbol_fast` first-token-only matching semantics** — the fast path only matches patterns whose first token equals the observed symbol, so a symbol that appears only mid-pattern yields no prediction via that path. Decide whether to extend it (general-path fallback or a symbol-position index, trading some speed) or keep current behavior (now pinned by tests).

## Previous Task
**Event-Aware Alignment Refinement (Event-Mate + Tightness Rules) — COMPLETE (2026-09-11)**

**Commit**: `34910a70` "fix(predictions): attribute repeated symbols to the event their neighbours matched". **Decision**: DECISION-029 in `planning-docs/DECISIONS.md` (extends DECISION-028).

**Background**: while implementing DECISION-028 (2026-09-11, position-based segmentation, commit `e0ee17d`), the user found a real misattribution bug in the "'y' dropped from event 1" test — the flat/positional matcher can't see event boundaries, so difflib's longest-run tie-break sometimes attributes a missing/extra symbol to the wrong event. An independent audit of all 34 atlas test outcomes found 2 outcomes actually wrong (`#26`: repeated-symbol dropped from event 1, attributed to event 0 instead; `#32`: lone `'x'` on the REPEATS pattern should exact-match pattern event `['x']`, not partially match `['x','y']`) and 4 right only by coincidence (`#25`, `#28`, `#29`, `#31`).

**Delivered**: new `refine_alignment_by_events()` in `kato/representations/prediction.py`, invoked at the top of `segment_by_alignment()` (shared by the main prediction path and the single-symbol fast path). Applies an event-mate rule (pattern side and observed/state side) plus a tightness rule for lone symbols with no event-mates, using a lexicographic potential function to guarantee termination — greedy, not a DP (an event-level DP was rejected: Φ is pairwise, not an additive LCS objective, and a DP would have to reproduce the flat LCS count exactly or similarity/evidence would diverge from missing/extras). Match count, matches, and similarity are unchanged by design — only missing/extras/anomalies and (when a lone symbol relocates) present bounds/confidence can change. New `tests/tests/unit/test_alignment_refinement.py` (23 pure-function tests: the three dropped-`'y'` variants, lone-symbol tightness (two shapes), observed-side mirror, unchanged repeats/ragged shapes, invariants + idempotence, short-circuit, empty alignment). `tests/tests/unit/test_multi_symbol_event_predictions.py` updated: the two dropped-`'y'` variants now expect different `missing`; lone `'x'` expects `present=[['x']]` with `confidence=1.0`; new observed-side mirror case (pattern `[['a'],['b','c']]`, observed `[['a','b'],['b','c']]` → `extras=[['b'],[]]`). `docs/reference/prediction-object.md` updated (rule under `missing` + Known limitations); `CHANGELOG.md` `[Unreleased]` Fixed entry. Atlas artifact regenerated and republished (same URL https://claude.ai/code/artifact/8f775ef3-10ee-4db2-8326-fe94ed1413eb) — "'y' dropped from event 1" now marks event 1; lone `'x'` shows `present=[['x']]`.

**Verification**: refinement + multi-symbol + hello-world suites 61 passed; prediction-neighbourhood suite 148 passed; full suite **552 passed / 4 skipped / 1 xfailed / 0 failed** (700.9s), +24 vs. the 528 baseline (23 pure tests + 1 mirror case).

**Deployment**: the local `deployment/` stack runs the dev `kato:latest` build with this fix. Released 5.0.2 lacks it (and `e0ee17d`) — v5.0.3 remains pending on the user, as is the fast-path first-token decision (both called out under "Current Task" above).

**Archive**: `planning-docs/completed/features/2026-09-11-event-aware-alignment-refinement.md`.

## Earlier Task (context preserved)
**Multi-Symbol Event Prediction Test Suite + Position-Based Segmentation Fix — COMPLETE (2026-09-11)**

**Request**: variations on the hello-world prediction test — learned patterns with multiple symbols per event, varying sizes; observed states full/partial (first half, second half, middle)/mixed with missing or extra symbols; comprehensive edge-case coverage.

**Delivered**: new `tests/tests/unit/test_multi_symbol_event_predictions.py` (34 tests, two patterns — RAGGED: varying event widths; REPEATS: recurring symbols — covering full/half/middle/single-event/mid-event-start-end observations, dropped/added symbols, split/merged/reordered/duplicate events, fast-path single-symbol cases, near-twin disambiguation). Exploration exposed two real bugs, fixed in the same commit `e0ee17d` "fix(predictions): segment by matched positions; event-structured fast path": (1) the past/present/future/missing/extras segmentation used flat slice lengths plus a symbol-identity heuristic that misattributed events when a symbol recurs across events (phantom `missing` symbols) — replaced with position-based `segment_by_alignment()` built from the matched pattern/state indices `extract_prediction_info` now returns (11th tuple element; fuzzy path unaffected, keeps legacy accounting); (2) the single-symbol fast path (`_predict_single_symbol_fast`) returned flat non-event-structured fields — now uses the same segmentation function. A residual ambiguity (flattened-sequence matching ties on which occurrence of a repeated symbol is "the" unmatched one) was documented at the time as not a bug — **superseded**: the independent 34-outcome audit that kicked off the Current Task above found that ambiguity actually manifests as 2 real misattribution bugs (`#26`, `#32`), now being fixed. `docs/reference/prediction-object.md` and `CHANGELOG.md` updated.

**Verification**: full suite 528 passed / 4 skipped / 1 xfailed / 0 failed (699s), +46 vs. the 482 baseline.

**One item still needs a human decision** (see `planning-docs/project-manager/pending-updates.md`): whether `_predict_single_symbol_fast`'s first-token-only matching semantics should change (would need the general path or a symbol index, at some performance cost) — this fix only pinned the current behavior with a test. (The other former pending item, whether a v5.0.3 patch release is warranted, is being carried forward into the Current Task above rather than decided separately, since this event-aware refinement fix should ship in the same release as `e0ee17d`.)

**Archive**: `planning-docs/completed/features/2026-09-11-multi-symbol-event-prediction-tests-and-segmentation-fix.md`. **Decision**: DECISION-028 in `planning-docs/DECISIONS.md`.

## Earlier Task (context preserved)
**Post-v5.0.2 Bug Fix: conftest Session-Cleanup Scoping — COMPLETE (2026-09-10)**
`tests/tests/conftest.py`'s session-scoped autouse fixture was deleting every `kato:session:*` Redis key at the start of each pytest run, so any concurrent pytest run, container recreate, or live client lost its sessions mid-flight; new `tests/tests/fixtures/redis_test_cleanup.py` (`e951148`) now deletes only test-prefixed sessions. Verified: 53 passed (session/error-handling/redis-session suites + new self-test) + 7 passed (`test_multi_user_scenarios`).

**KATO v5.0.2 Release — COMPLETE (2026-09-10)**

### Release Summary
Released via `./container-manager.sh patch` (AUTO_MODE), bumping 5.0.1 → 5.0.2. Ships the Multi-Worker Uvicorn + Concurrent Training Safety initiative's fixes (DECISION-024/025/026) to a published image for the first time: the observe-path deadlock fix (stopgap `9de98c3`, then the Phase 1.6 lock-free refactor `b155cb5`), clear-all residue fixes + `escape_glob` (`7aad817`), a store-parity tool, the container `HEALTHCHECK` fix, one-writer-per-session docs + strict xfail (`bef2b47`), and the perf/integrity test. PATCH bump — no API change (`KatoProcessor.learn` becoming a coroutine is internal).

**Commits**: five initiative commits (`7aad817`, `bef2b47`, `9de98c3`, `b155cb5`, `a2c7182`) pushed to `origin/main` before the release; `b9f94bb` docs(changelog) promoting `[Unreleased]` → `[5.0.2] - 2026-09-10`; `b76d955` chore: bump version to 5.0.2; then `61e16cd` test(topology): make the session-count check churn-proof (post-release hardening, see below). `main` at `61e16cd` (not yet pushed — will be pushed together with this planning-docs commit).

**Release artifacts**: Tag `v5.0.2` pushed; GitHub release https://github.com/sevakavakians/kato/releases/tag/v5.0.2 (`kato-deployment-v5.0.2.tar.gz` + Helm chart `kato-0.1.1.tgz`); images `ghcr.io/sevakavakians/kato:5.0.2`/`:5.0`/`:5`/`:latest`, all digest `sha256:6c46ff688321…`.

**Deployment**: gitignored `deployment/docker-compose.override.yml` re-pinned from the dev `kato:latest` build to `ghcr.io/sevakavakians/kato:5.0.2`; only the `kato` service recreated (Redis `SAVE` first; `DBSIZE` 30,346 → 30,356 during the swap from concurrent test sessions; ClickHouse 6,047 patterns). Verified in the registry image: `learn_from` present, zero `multiprocessing` locks, `escape_glob` present, `KATO_WORKERS=4` with fan-out on all 4, container healthcheck reports healthy.

**Verification**: worker-topology suite 18/18 against the deployed image; full suite 482 passed / 4 skipped / 1 xfailed / 0 failed (675.08s), no `FAILED` lines; store-parity tool 0 mismatched `kb_id`s.

**Post-release finding + fix (`61e16cd`)**: right after the deployment container restart, the topology suite showed 4 failures, then 1 on rerun (`test_session_count_converges_on_every_worker`). Root cause was test fragility, not a product bug: the active-session index (Redis `SET kato:session:_active_index`) is shared by every KATO process on the stack, and the deployment container's expiry sweep removed other short-TTL perf-run sessions during the test window, so "global count == baseline ± 5" only held on a quiet Redis. Fixed by asserting membership of the test's own session ids (exact regardless of churn) and, in a quiet window found by bounded retry, that every worker's `/sessions/count` equals the index cardinality read at the same instant; event-delivery timeout raised 5s → 10s. Topology suite 18/18 afterwards. Logged as a generalized testing pattern in `project-manager/patterns.md` (shared-Redis global counters make absolute-delta assertions flaky; assert on your own keys or truth-at-the-same-instant).

**This resolves** the `pending-updates.md` "Release Needed" item (moved to Resolved) and the release-gap note in `README.md`'s Version line.

**Archive**: `planning-docs/completed/features/2026-09-10-kato-v5.0.2-release.md`. **Decision**: DECISION-027 in `planning-docs/DECISIONS.md`.

### Earlier Same-Day Progress (context preserved below)
The subsections immediately below describe the Multi-Worker Uvicorn + Concurrent Training Safety initiative's closure earlier on 2026-09-10, before the v5.0.2 release — kept for historical continuity within this same day's work.

**Multi-Worker Uvicorn + Concurrent Training Safety — COMPLETE (2026-09-10)**

### Closing Update: Phase 1.6 Shipped (DECISION-026), Initiative Closed
Phase 1.6 (DECISION-025 Option B — the lock-free per-request working-state refactor) is done, committed as `b155cb5` "refactor(workers): per-request working state through observe/learn/predict (Phase 1.6)". The `_bridge_lock` stopgap from `9de98c3` is removed entirely — `observation_processor.process_observation`/`check_auto_learning` and `pattern_processor.learn_from`/`predict_from` (plus `pattern_operations.learn_pattern_from`) now take the session's STM/emotives/metadata as explicit arguments and return the updated STM, instead of staging it into shared `pattern_processor` instance state for the duration of a request. The legacy stateful `learn()`/`processEvents()` remain as thin delegates over the processor's own STM for non-request callers. New `tests/tests/integration/test_worker_topology.py::test_interleaved_sessions_keep_their_own_stm` (parametrized `KATO_WORKERS` in {1, 2, 4}; the `workers=1` case is the deterministic same-processor interleaving test — the exact scenario the old bridge/lock existed to protect). One pre-existing quirk preserved and now documented in code rather than left implicit: auto-learned patterns are stored without the session's emotives/metadata (the old bridge only ever loaded STM on the observe path) — flagged as a possible follow-up, not fixed here. `CLAUDE.md`'s "Stateless Processor Architecture" section rewritten to describe per-request working state instead of the bridge pattern; ADR-001 got a history line; `CHANGELOG.md` updated.

**Verification**: worker-topology suite 18/18 (including the new interleaving test across all three worker counts); perf/integrity test (`KATO_PERF=1`, 8 threads × 10 rounds) PASSED with 1.83× speedup (4 workers vs. 1), exact pattern counts, exact shared-pattern frequency, Redis/ClickHouse agreement, every worker still alive, clean clear-all; full suite 482 passed / 4 skipped / 1 xfailed / 0 failed (651s), up from the 475/4/0 baseline before this initiative began; store-parity tool 0 mismatched kb_ids.

**Initiative status: COMPLETE.** All phases done — Phase A (cleanup fixes + parity tool, `7aad817`), Phase B (limitation documented + strict xfail, `bef2b47`), Phase C (perf/integrity test; deadlock found and fixed via the A stopgap then the B refactor, `9de98c3` → `b155cb5`), Phase D (planning docs, this update). Verification list items 1-4 done; item 5 (the `kato-notebooks` `MAX_SAMPLES=10000` notebook scale run) remains an optional manual follow-up, with the in-repo perf/integrity test standing in as the accepted verification.

**New follow-ups filed** (not blocking closure, see `SPRINT_BACKLOG.md` Backlog): (1) auto-learned patterns don't carry session emotives/metadata — pre-existing, decide whether to change; (2) `vector_processor.deferred_vectors_for_learning` is per-processor state spanning requests on the legacy VI indexer path — pre-existing, only matters if that path is used concurrently; (3) a release is warranted — see `pending-updates.md`.

**Archive**: `planning-docs/completed/features/2026-09-10-phase-1.6-lock-free-refactor.md`. **Decision**: DECISION-026 in `planning-docs/DECISIONS.md`.

### Earlier Same-Day Progress (context preserved below)
The subsections immediately below describe the initiative's state earlier on 2026-09-10, before Phase 1.6 landed — kept for historical continuity within this same day's work.

### Decision Made and Shipped (2026-09-10): DECISION-025 — "Do A as a stopgap now, then B"
The observe-path deadlock blocker (below) is **resolved**. User decision: ship Option A (one `asyncio.Lock` per `KatoProcessor` around the `observe`/`learn`/`get_predictions` bridge sections; both `multiprocessing.Lock`s deleted) immediately as a stopgap, then make Option B (the Phase 1.6 lock-free refactor) the immediate follow-on task. Rationale: A is ~30 lines and fixes a production-breaking deadlock today; B is the roadmap-consistent fix (no locks) but needs its own dedicated pass. Full rationale, alternatives, and work items: DECISION-025 in `planning-docs/DECISIONS.md`. This resolves the `planning-docs/project-manager/pending-updates.md` blocker entry (moved to Resolved Issues).

### Completed and Committed (main, not yet pushed)
- **`7aad817`** fix(storage): make clear-all leave nothing behind; add a store parity tool — **Phase A**. `escape_glob()` at all 4 `RedisWriter` scan sites + tests cleanup helper; `clear_all_memory` flushes the async-insert queue before `DROP PARTITION` and also drops the `patterns_metadata` partition; `scripts/check_store_parity.py` (report; `--purge-prefix`/`--execute`); `tests/tests/integration/test_store_cleanup.py` (4 tests incl. bracketed kb_id); `docs/users/database-persistence.md` "Checking Store Consistency". The 88 `test_*` residue kb_ids were purged (user-approved); parity is 0 mismatched; a full-suite run creates no new residue.
- **`bef2b47`** docs(sessions): one writer per session; strict xfail — **Phase B**. Docs in `docs/users/session-management.md` ("One Writer Per Session"), `docs/users/parallel-processing.md`, `docs/reference/api/sessions.md` ("Concurrency"); `test_concurrent_session_modifications` is a strict `xfail` under `KATO_WORKERS>1` (verified XFAIL).
- **`9de98c3`** fix(workers): stop deadlocking a worker on overlapping same-node requests — **the stopgap (DECISION-025 Option A)**: `kato/workers/kato_processor.py` (`_bridge_lock = asyncio.Lock()`; `learn` is now `async def` and its 3 callers in `kato/api/endpoints/sessions.py` await it; `observe`/`learn`/`get_predictions` bridge sections wrapped), `kato/workers/observation_processor.py` (`multiprocessing.Lock` and the `with` block removed), `Dockerfile` `HEALTHCHECK` fixed (`urllib` instead of the uninstalled `requests`), `tests/tests/performance/test_multi_worker_throughput.py` (Phase C, opt-in `KATO_PERF=1`; per-request timeouts; asserts speedup>1, exact pattern counts, exact shared-pattern frequency = threads×rounds, Redis/ClickHouse agreement, every worker still answering `/health`, clean clear-all), `docs/developers/testing.md` section, `docs/users/parallel-processing.md` note that same-node requests serialize within a worker, `CHANGELOG.md` `[Unreleased]` entries for all of the above.

### Verification
- **Deadlock reproduction** (8 threads × one session each on one node, 20 rounds): before the fix, 1-worker died at 9 patterns and 4-worker stalled at 28/161 with 2 of 4 workers dead; after the fix, both complete 161/161 patterns, shared-pattern frequency exactly 160, all workers answering; 4 workers 1.9× faster than 1 on that run (58.6s vs 31.2s).
- **Perf test** (`KATO_PERF=1`, 8 threads × 10 rounds): PASSED on both topologies; speedup 1.15× measured while the full suite ran concurrently (noisy); all integrity assertions held.
- **Full suite** on the fixed image (deployment stack currently running the local `kato:latest` build, override temporarily pointed at it): 479 passed / 4 skipped / 1 xfailed / 0 failed (648s). Previous baseline 475/4/0 — the +4 are the new store-cleanup tests; the xfail is the documented limitation (DECISION-024).
- Initiative verification list status: 1 done, 2 done (clean), 3 done (0 duplicate groups), 4 done (parity 0), 5 partially — the notebook `MAX_SAMPLES=10000` run remains manual; the in-repo perf test stands in.

### Still Open / Next
- **Phase 1.6 refactor (Option B) is the active task**: thread a per-request working STM/emotives/metadata through `observation_processor.process_observation`/`check_auto_learning`, `pattern_operations.learn_pattern`, and `pattern_processor` (`setCurrentEvent`/`processEvents`/`learn`/`maintain_rolling_window` read `self.STM` in 11 places; `predictions`/`trigger_predictions`/`last_learned_pattern_name` are instance state; `vector_processor.deferred_vectors_for_learning` is per-processor state spanning requests on the legacy VI indexer path — note as a Phase 1.6 item); remove `_bridge_lock` afterwards.
- Deployment stack is running the unreleased local build (which has the deadlock fix) rather than 5.0.1 (which has the deadlock); a release (5.0.2 or 5.1.0) should follow Phase 1.6, or sooner if the deadlock fix needs to ship ahead of it.

### Superseded Status (context preserved, no longer current)
The subsections immediately below (Status Correction, Verification Results, Decisions Made, Agreed Plan, Blocker) describe the state as of earlier on 2026-09-10, before Phases A/B/C-stopgap were committed and DECISION-025 was made. Kept for historical continuity within this same day's work.

### Status Correction (2026-09-10)
The backlog entry was stale: it said "ACTIVE - Implementation in progress" and pointed at a plan file, `/Users/sevakavakians/.claude/plans/ultrathink-enable-multi-worker-recursive-marble.md`, that **no longer exists**. In fact Changes 1, 2, and 3 (multi-worker CMD + `KATO_WORKERS` + `kato-manager --workers`; ClickHouse `async_insert` + `DEFAULT_BATCH_SIZE=1` + `flush_async_insert_queue` at finalize; SETNX new-pattern gate + frequency ownership moved to SETNX/INCR) **all shipped already**, in commit `f809a84` (2026-04-23). The dead plan-file reference has been removed from the backlog. What actually remained was the initiative's Verification list, run today.

### Verification Results (2026-09-10)
1. **N workers start** — confirmed by `tests/tests/integration/test_worker_topology.py` at `KATO_WORKERS` in {1, 2, 4}.
2. **Full suite** — 475 passed / 4 skipped / 0 failed on the deployed 5.0.1 image. BUT `test_concurrent_session_modifications` (`tests/tests/integration/test_session_management.py::TestSessionErrorHandling`) only "passes" by being skipped when `run_tests.sh` exports the container's `KATO_WORKERS>1`; run directly against the 4-worker stack it fails 3/3. **Root cause confirmed**: `kato/api/endpoints/sessions.py`'s `observe` handler (~lines 345-411) holds a per-process `asyncio.Lock` around `get_session` → `processor.observe` → `update_session`, and `redis_session_manager._save_session` (~lines 739-778) `SETEX`es the whole session as one JSON blob — a lost update when two worker processes hold the same session. The old backlog text attributing the fix to the SETNX-gate work (Change 3) was a **misattribution** — that gate guards new-pattern creation in `learnPattern`, not session state — now corrected in `SPRINT_BACKLOG.md`.
3. **ClickHouse duplicate-row check** — 0 duplicate `(kb_id, name)` groups. Clean.
4. **Redis vs ClickHouse parity** — 88 of 261 `kb_id`s mismatch (all `test_*` residue), from two distinct cleanup bugs, NOT multi-worker write loss: (a) `redis_writer.py`'s `delete_all_metadata()` and similar `scan_iter(match=f"{kb_id}:*")` calls don't glob-escape `kb_id`, so pytest's `[...]`-bracketed parametrize ids are read as glob character classes and cleanup silently no-ops; `clear_all_memory()` also never calls `metadata_router.delete_all_pattern_metadata()`, leaking `patterns_metadata` rows on every clear-all. (b) `clear_all_memory()` doesn't call `flush_async_insert_queue()` before `DROP PARTITION` (unlike `finalize_training`, which does), so a learn's ~200ms-buffered async-insert row can land after the drop and survive. Both logged as new Bug entries in `SPRINT_BACKLOG.md`.
5. **Scale test** (`MAX_SAMPLES=10000` notebook, expect 4-5x) — not done; external notebook workload, deferred to Phase C's in-repo stand-in.

### Decisions Made (2026-09-10)
- **Same-session cross-worker write loss: document as a limitation, do not fix.** No CAS, no distributed locks — consistent with this project's no-locks rule and the actual workload (one session, one writer at a time). See DECISION-024 in `DECISIONS.md` for full rationale and the rejected CAS/optimistic-locking alternative.
- **Test residue: yes, clean it up.** Delete the 88 `test_*`-prefixed kb_ids' orphaned Redis keys / ClickHouse rows once the two cleanup bugs (Phase A) are fixed, then re-run parity expecting 0 mismatches. Production kb_ids are untouched (none contain brackets).

### Agreed Plan (record as the active task, in order)
- **Phase A — Data-integrity fixes** (DONE, uncommitted): `escape_glob()` applied at all 4 `scan_iter(match=...)` sites in `kato/storage/redis_writer.py` plus `tests/tests/fixtures/cleanup_utils.py`; `clear_all_memory()` (`kato/informatics/knowledge_base.py`) now flushes the async-insert queue before `DROP PARTITION` and also clears `patterns_metadata`; new `tests/tests/integration/test_store_cleanup.py` (4 tests, passing; one parametrized with a bracketed id); new `scripts/check_store_parity.py` ops tool (report + `--purge-prefix`/`--execute`); the 88 `test_*` residue kb_ids purged (user-approved) — parity now 0 mismatched; re-running the residue-producing suite creates no new residue. Docs updated: `docs/users/database-persistence.md` ("Checking Store Consistency"), `docs/developers/testing.md` (perf-test section); `CHANGELOG.md` `[Unreleased]` entries added. Nothing committed yet.
- **Phase B — Limitation documentation + correction** (DONE, uncommitted): `test_concurrent_session_modifications` converted to strict `xfail` under `KATO_WORKERS>1` (verified XFAIL); one-writer-per-session rule documented in `docs/users/session-management.md`, `docs/users/parallel-processing.md`, `docs/reference/api/sessions.md`.
- **Phase C — Throughput verification** (BLOCKED — see Blocker below): new `tests/tests/performance/test_multi_worker_throughput.py` written (opt-in `KATO_PERF=1`; self-launched 1- and 4-worker containers; asserts speedup + integrity + clean clear-all). **Running it is what exposed the deadlock blocker** — the test itself cannot be verified passing until the blocker is fixed, because its target workload (several threads on one node) is exactly what triggers the deadlock.
- **Phase D — Planning docs**: Changes 1-3 marked shipped in `f809a84` (done, 2026-09-10 earlier update); closing the initiative is now gated on the blocker's resolution, not just Phases A-C landing.

### Blocker (2026-09-10, severe, confirmed): observe path deadlocks any uvicorn worker on overlapping same-node_id requests
**Discovered by**: running the new Phase C perf test (`tests/tests/performance/test_multi_worker_throughput.py`) against the initiative's actual target workload (several threads training on one node) — the first real concurrent-same-node_id load this initiative has thrown at the server.

**Evidence**: `py-spy` dump of a hung single-worker container shows the event-loop `MainThread` blocked in `multiprocessing/synchronize.py:__enter__`, called from `kato/workers/observation_processor.py:346` (`with self.processing_lock:` — a `multiprocessing.Lock` created at line 53) via `kato/workers/kato_processor.py:281` (`observe`). `process_observation` is `async` and awaits (`pattern_processor.processEvents` → predictions) *while holding* the blocking lock; on a single event loop, request A holds the lock and awaits, request B blocks the thread trying to acquire it, and A can never resume → permanent deadlock. `/health` stops answering (the event loop itself is blocked).

**Reproduced deterministically** (twice): 8 threads × one session each, one node → 1-worker container dies after exactly 9 patterns. 4-worker container: driver stalls at 28/161 patterns; afterwards only 2 of 4 worker pids still answer `/health` (two workers dead). This is precisely the target parallel-training workload (several threads on one node), so **the initiative cannot be verified or closed until this is fixed.**

**Origin**: lock introduced in `52e9284` (2025-09-08, "Extract KatoProcessor into modular components"). A second, unused `multiprocessing.Lock` exists at `kato/workers/kato_processor.py:73` (dead code). **Both violate this project's no-locks rule** (CLAUDE.md: "remember to not create locks for this project").

**Underlying design issue**: the "BRIDGE" pattern (session STM loaded into shared `pattern_processor` instance state for the duration of a request — `kato_processor.observe` ~lines 272-284, `learn` ~193-208, `get_predictions` ~359) means concurrent requests on the same processor instance would corrupt each other's STM at await points without serialization — and the load happens *before* the lock is taken, so even a correctly scoped lock at the current call site would not protect it. This is the CLAUDE.md "TODO (Phase 1.6/1.7)" bridge follow-up, now shown to be load-bearing for correctness, not just a stylistic TODO.

**Why the existing suite never caught it**: tests run sequentially; the only test using threads (`test_multi_user_scenarios`) uses distinct nodes → distinct processor instances → no lock collision.

**Related pre-existing defect found alongside this** (being fixed alongside, not blocking): `Dockerfile` `HEALTHCHECK` runs `python -c "import requests; ..."`, but `requests` is not in the image, so `docker run` containers always report unhealthy; compose-based deployments use `urllib` and are unaffected.

**Decision pending (asked of the user)** — two options to unblock Phase C and close the initiative:
- **Option A**: replace both `multiprocessing.Lock`s with one `asyncio.Lock` per `KatoProcessor` around `observe`/`learn`/`get_predictions` (~30 lines). Deadlock fixed; same-node requests serialize per worker (still parallel across workers). Keeps a lock — a smaller violation of the no-locks rule than what exists today, but still a lock.
- **Option B (recommended)**: Phase 1.6 refactor — pass per-request working STM/emotives/metadata through `observation_processor` and `pattern_processor` instead of mutating shared instance state (`setCurrentEvent`/`processEvents`/`learn`/`check_auto_learning`/`maintain_rolling_window` read `self.STM` in ~11 places). Delete both locks (~150-250 lines across 3 files). Lock-free; consistent with the no-locks rule; validated by the full suite plus the new Phase C perf/integrity test.

**Next immediate action**: awaiting the user's choice of Option A vs Option B (see `planning-docs/project-manager/pending-updates.md` for the human-alert entry); Phase C stays blocked until then. Phase A/B source changes remain uncommitted in the working tree — leave them alone until the blocker's fix is also ready to land together.

**Full details**: `planning-docs/SPRINT_BACKLOG.md` (Active Projects → "Multi-Worker Uvicorn + Concurrent Training Safety" → new Bug entry for this deadlock); `planning-docs/DECISIONS.md` (DECISION-024, prior scope decision); `planning-docs/project-manager/pending-updates.md` (human-alert entry, decision pending).

## Earlier Task (context preserved)
**KATO v5.0.1 Release (PATCH) — COMPLETE (2026-09-10)**
- Status: RELEASED — `./container-manager.sh patch` (AUTO_MODE). Bump commit `1481e44` "chore: bump version to 5.0.1"; tag `v5.0.1` pushed to origin; `main` at `1481e44`, in sync with `origin/main`
- Milestone release, not a queued initiative; Multi-Worker Uvicorn initiative below remains next in the sprint backlog
- Decision: DECISION-023 in `planning-docs/DECISIONS.md`
- Archive: `planning-docs/completed/features/2026-09-10-kato-v5.0.1-release.md`
- Commits since v5.0.0: `f100e4a` fix(examples) — reference Python client recovery/coverage fixes, examples only (see "Earlier Task" below); `ca8e47a` perf(metadata) — sidecar re-learn now reads its ClickHouse row once via `get_metadata_for_merge()` + `upsert_pattern_metadata(prev=...)` — this is the DECISION-018 work, documented COMPLETE on 2026-09-09 but left **uncommitted** and NOT included in the v5.0.0 image; now committed and released; `ce7d21c` docs(planning); `8bf906c` docs(changelog) promoting `[Unreleased]` to `[5.0.1] - 2026-09-10`; `1481e44` chore: bump version to 5.0.1
- GitHub release: https://github.com/sevakavakians/kato/releases/tag/v5.0.1 (assets `kato-deployment-v5.0.1.tar.gz`, `kato-0.1.1.tgz` Helm chart — attached by the tag-triggered workflow)
- Images: `ghcr.io/sevakavakians/kato:5.0.1`, `:5.0`, `:5`, `:latest` — pushed and verified, all the same digest `sha256:54c13094932b…`
- Rationale: PATCH — a behavior-preserving round-trip elimination plus example-client bug fixes; no API change (contrast with v5.0.0's major bump for the breaking `anomalies`/`fuzzy_matches` split)
- Deployment: local `deployment/` compose stack's gitignored `docker-compose.override.yml` pinned to `ghcr.io/sevakavakians/kato:5.0.1`; only the `kato` service was recreated (databases untouched). Verified: API reports 5.0.1, `get_metadata_for_merge` present in the image, `KATO_WORKERS=4` with cross-worker fan-out enabled on all 4, `NO_PROXY` override applied, Redis 23,253 keys before/after (forced `SAVE` first), ClickHouse 4,528 patterns
- Verification: smoke 28 passed against the deployed 5.0.1 image (`test_emotives_comprehensive`, `test_metadata_comprehensive`, hello-world predictions, websocket events); full suite **475 passed / 4 skipped / 0 failed** (624.50s) — identical pass/fail counts to the pre-release 2026-09-09 baseline (585s); the duration difference is run-to-run variance, not a regression
- Process note: the first release attempt aborted harmlessly — `source ~/.bash_profile` returns non-zero in a non-interactive shell, and the wrapper used `set -e`, so nothing had been bumped/tagged; re-run with `source ~/.bash_profile || true` succeeded. Recorded alongside the 2026-09-09 stale-credential note — see `planning-docs/project-manager/patterns.md` and `maintenance-log.md`
- **Resolves**: the `planning-docs/SPRINT_BACKLOG.md` "Optimization: Metadata Sidecar Re-Learn Duplicate SELECT Eliminated" entry's done-but-uncommitted status — that work (DECISION-018) is now committed (`ca8e47a`) and released as part of v5.0.1. The separate structural follow-up ("Metadata sidecar read-modify-write shape") remains open/uncommitted.

**Reference Python Client: Close API-Coverage Gap — COMPLETE (2026-09-10)**
- Status: COMPLETE — ad-hoc maintenance task, not part of the Multi-Worker Uvicorn initiative (that remains next queued in `SPRINT_BACKLOG.md`)
- Scope: `examples/python-client.py` (the `KATOClient` reference client) + `examples/README.md`; no `kato/` service code touched
- Audit finding: only 26 of 39 routes wrapped; 2 wrappers pointed at deprecated, empty-payload endpoints; 1 wrapper (`get_session_config()`) never called its route; session-recovery retry path had never worked
- Fixed `_request`'s session-recovery retry: (1) it retried against the stale pre-recovery session id baked into the endpoint string — now rewritten to the new session id before retry; (2) the "skip retry for session lifecycle ops" guard (`'/sessions' in endpoint and method in ['POST','DELETE']`) matched every session-scoped POST (observe, learn, clear-stm, config, extend, ...), so recovery only ever fired for GETs — narrowed to exactly `POST /sessions` / `DELETE /sessions/{id}`; added a `_recovering` re-entrancy guard
- Repointed `get_percept_data()`/`get_cognition_data()` from deprecated node-scoped routes (server returns empty payload) to session-scoped `/sessions/{sid}/percept-data`/`/cognition-data`; legacy versions kept as `get_node_percept_data()`/`get_node_cognition_data()`, marked deprecated
- Fixed `get_session_config()` to actually call `GET /sessions/{sid}/config` instead of deriving from `get_session_info()`
- Added 9 missing wrappers (`clear_all()`, `get_active_session_count()`, `get_symbol_affinities()`, `get_symbol_stats()`, `get_symbol_affinity()`, `get_concurrency_stats()`, `get_prometheus_metrics()`, +2 more)
- Rewrote the `python-client.py` section of `examples/README.md` (previously wrong in every particular — advertised async/httpx for a sync `requests` client, wrong class name, wrong constructor kwarg, nonexistent method signatures)
- Verification: coverage re-audited against live `/openapi.json` — 37/38 routes now wrapped (remaining 2 deliberate: a routing smoke-test route, and `WS /ws/events` which `requests` cannot speak — WebSocket support explicitly excluded by the user); recovery path regression-tested live (deleted a session out from under a client, confirmed transparent recovery on next `observe()`); full suite 475 passed / 4 skipped
- Archive: `planning-docs/completed/features/2026-09-10-python-client-api-coverage.md`
- Note: working tree also carried unrelated in-progress changes to `kato/informatics/knowledge_base.py` and `kato/storage/metadata_router.py` (concurrent metadata-sidecar work) — not touched by, and not part of, this task; the 475/4 verification run covered the combined tree. That WIP is the DECISION-018 sidecar fix, since committed as `ca8e47a` and released in v5.0.1 — see "Previous Task" above.

**KATO v5.0.0 Release (MAJOR) — COMPLETE (2026-09-09)**
- Status: RELEASED — `./container-manager.sh major` (AUTO_MODE). Bump commit `5c4b282` "chore: bump version to 5.0.0" (`pyproject.toml`, `setup.py`, `kato/__init__.py`, `charts/kato/Chart.yaml` `appVersion`); tag `v5.0.0` pushed to origin; `main` at `5c4b282`, in sync with `origin/main`
- Milestone release, not a queued initiative; Multi-Worker Uvicorn initiative below remains next in the sprint backlog
- Decision: DECISION-022 in `planning-docs/DECISIONS.md` (resolves DECISION-019's open version-bump question)
- Archive: `planning-docs/completed/features/2026-09-09-kato-v5.0.0-release.md`
- GitHub release: https://github.com/sevakavakians/kato/releases/tag/v5.0.0 (assets `kato-deployment-v5.0.0.tar.gz`, `kato-0.1.1.tgz` Helm chart)
- Images: `ghcr.io/sevakavakians/kato:5.0.0`, `:5.0`, `:5`, `:latest` — pushed and verified, all the same digest `sha256:c0bb53152507…`
- Rationale: MAJOR because the breaking `anomalies`→`fuzzy_matches` prediction-field change (DECISION-019) is a contract break for any consumer reading fuzzy detail from `anomalies`; this resolves the previously-open "major-version-bump" item in `planning-docs/project-manager/pending-updates.md` (now moved to Resolved)
- `CHANGELOG.md` promoted `[Unreleased]` → `[5.0.0] - 2026-09-09` in commit `6b621ac`, backfilling 11 previously-unlogged post-4.0.0 commits plus a "Migration from 4.x" section
- Pre-release verification: full suite **475 passed / 4 skipped / 0 failed**; ruff finding count in `kato/` unchanged from baseline (283, pre-existing)
- Process notes recorded for next release (see `planning-docs/project-manager/maintenance-log.md` and DECISION-022): (1) verify `ghcr.io` registry auth (`docker login`) before invoking `container-manager.sh` — it does not log in itself, and it pushes the tag + publishes the GitHub release **before** building/pushing the image, so a failed push leaves a tagged release with no matching image; (2) hold out any in-flight uncommitted WIP via `git stash push -u` before bumping and restore it after (done here for the metadata-sidecar planning file's uncommitted follow-up work, which is **not** part of this release)
- **Not part of this release**: the metadata-sidecar structural follow-up (append-only emotives/metadata, see `planning-docs/SPRINT_BACKLOG.md` "Follow-up: Metadata sidecar read-modify-write shape") remains open, uncommitted, and out of scope for v5.0.0

**Cross-Worker WebSocket Broadcaster Fix via Redis Pub/Sub — COMPLETE (2026-09-09)**
- Status: COMPLETE — committed as `ba3d194` "fix(websocket): fan events out across uvicorn workers via Redis pub/sub" (same commit also carries the worker-topology-tests/worker_pid work below, previously recorded as DECISION-020 but not yet committed at the time)
- Ad-hoc bug fix, closing the open follow-up flagged by DECISION-020; Multi-Worker Uvicorn initiative below remains next in the sprint backlog
- Decision: DECISION-021 in `planning-docs/DECISIONS.md`
- Archive: `planning-docs/completed/features/2026-09-09-websocket-cross-worker-broadcaster-redis-pubsub.md`
- Fix: `kato/websocket/event_broadcaster.py`'s `broadcast_event` now publishes the event JSON to a Redis pub/sub channel (`kato:ws_events`, overridable via `KATO_WS_EVENTS_CHANNEL`); each uvicorn worker subscribes at startup (`EventBroadcaster.start(REDIS_URL)` called from the app startup hook in `kato/services/kato_fastapi.py`, right after the Redis session manager initializes; `stop()` on shutdown) and a per-worker listener task delivers received events to that worker's own local connections. The publishing worker does not also deliver locally from `broadcast_event` itself — delivery happens only via its own listener receiving what it just published — giving exactly-once delivery per client. `start()` blocks until Redis acknowledges the `SUBSCRIBE`, so no post-startup event is missed.
- Fallbacks (no locks used anywhere): no `REDIS_URL` / Redis unreachable → local-only delivery with a log line; publish failure → local delivery for that event; listener error → resubscribe after 1s.
- Tests: new `tests/tests/unit/test_event_broadcaster.py` (6 tests, fakes: local fallback, publish-once-no-double-delivery, publish-failure fallback, listener-side delivery, dead-connection pruning, `start(None)` stays local). The DECISION-020 worker-topology tests now pass on all topologies: 15/15 across `KATO_WORKERS` in {1, 2, 4} (previously 6 deterministic failures at {2, 4}).
- Docs: `docs/integration/websocket-integration.md` (new "Cross-Worker Delivery" section), `docs/operations/environment-variables.md` (`KATO_WS_EVENTS_CHANNEL`), `CHANGELOG.md` `[Unreleased]` "Fixed" entry.
- Verification: full suite after rebuild with default `KATO_WORKERS=4` — **475 passed, 4 skipped, 0 failed (585s)**. Previous full-suite baseline was 453 passed / 5 failed. The pre-existing `test_metrics_collection_after_requests` flake (10s metrics interval vs. 1s test sleep) passed this run but remains flaky by construction — kept as an open, low-priority, unrelated item; see `planning-docs/SPRINT_BACKLOG.md`.
- **Resolved**: the `planning-docs/project-manager/pending-updates.md` "Cross-Worker WebSocket Broadcaster Fix: Priority Decision Needed" entry (filed alongside DECISION-020) — moved to that file's Resolved Issues section.
- **Still open, unrelated**: DECISION-019's major-version-bump decision (breaking `anomalies`/`fuzzy_matches` field split) remains undecided **as of this point in the day — resolved later the same day via the v5.0.0 release, see DECISION-022 and the "Previous Task" entry above**. `test_concurrent_session_modifications`'s concurrent-write-loss symptom (from the original 2026-09-08 multi-worker bug report) was never established to share this root cause and was out of scope here — still tracked as open/unconfirmed in `planning-docs/SPRINT_BACKLOG.md`.

**Worker-Topology Tests Replace Flaky Multi-Worker Tests + `worker_pid` Field — COMPLETE (2026-09-09)**
- Status: COMPLETE — tests written, run, characterized; NOT committed; broadcaster fix itself NOT started (not requested)
- Ad-hoc test-infrastructure work (not from a queued initiative); Multi-Worker Uvicorn initiative below remains next in the sprint backlog, and this work deterministically confirms part of what it needs to address
- Decision: DECISION-020 in `planning-docs/DECISIONS.md`
- Archive: `planning-docs/completed/features/2026-09-09-worker-topology-tests-and-worker-pid.md`
- Replaced the five known-flaky/failing tests (4 websocket event-delivery tests + `test_session_cleanup`) with a new `tests/tests/integration/test_worker_topology.py`: a module-scoped fixture parametrized over `KATO_WORKERS` in {1, 2, 4} launches a throwaway `kato:latest` container per value via the Docker CLI on the compose network, copying the running `kato` container's env so only `KATO_WORKERS` (and `SESSION_COUNT_CACHE_TTL_SECONDS=2` for speed) differ. Readiness/worker count verified from uvicorn's own `"Started server process [pid]"` log lines. 5 tests: `container_runs_requested_worker_count`, `session_created_event_reaches_every_client`, `session_destroyed_event_reaches_every_client`, `client_sees_full_session_lifecycle_in_order`, `session_count_converges_on_every_worker`.
- Determinism mechanism: delivery tests open websocket clients until they provably span ≥2 distinct worker PIDs (bounded at `16*workers` connections) before asserting, so an in-process broadcaster fails every run, not by scheduling luck.
- `tests/tests/integration/test_websocket_events.py` trimmed: removed `test_session_created_event`, `test_session_destroyed_event`, `test_multiple_websocket_connections`, `TestQuickStartExample` (moved to the topology module); kept connection/ping-pong/disconnect-cleanup tests.
- `tests/tests/integration/test_session_management.py::test_session_cleanup` rewritten to honor the documented per-process `/sessions/count` TTL cache: reads only after `SESSION_COUNT_CACHE_TTL_SECONDS` (default 5) + 0.5s, requires 16 reads to agree. Now passes against the live 4-worker main container.
- Product addition: `worker_pid` (`os.getpid()`) added to `/health` responses (`kato/api/endpoints/health.py` + `HealthResponse` schema in `kato/api/schemas/health.py`) and to websocket `state.snapshot` data (`kato/websocket/event_broadcaster.py`) — this is what makes the PID-spanning determinism mechanism possible. Documented in `docs/reference/api/health.md`, `docs/integration/websocket-integration.md`, `docs/developers/testing.md` (new "Worker-Topology Tests" section), `CHANGELOG.md` `[Unreleased]` "Added".
- Results (image rebuilt, main container recreated with default `KATO_WORKERS=4`): `KATO_WORKERS=1` — all 5 topology tests pass. `KATO_WORKERS=2` and `4` — the 3 websocket-delivery tests **FAIL deterministically** (missed worker pids named in the assertion, e.g. "reached 0 client(s), missed pids [7, 10]"); the count and worker-count tests pass on all topologies. **This is the intended outcome**: confirms the in-process `EventBroadcaster` (`kato/websocket/event_broadcaster.py`, per-process `active_connections` list) cannot deliver across uvicorn workers. Previously surfaced as 2-4 random failures per full-suite run; now surfaces as exactly 6 deterministic failures (3 tests × 2 multi-worker topologies) until the broadcaster is made cross-worker (e.g. Redis pub/sub fan-out). **The fix was NOT started** (not requested) — recorded as an open follow-up.
- Rewritten `test_session_cleanup` passes; trimmed websocket file passes (3 tests); `tests/tests/api` suites 32 passed / 1 skipped / 1 failed (the 1 is the pre-existing `test_metrics_collection_after_requests` flake — 10s metrics-collection interval vs. 1s test sleep — still open, unchanged).
- Lint: new topology file ruff-clean; other ruff findings in touched files pre-existing.
- **Full-suite expectation update**: the "3 known multi-worker failures" characterization is superseded — expect **6 deterministic topology failures** (workers=2/4 delivery tests) plus the flaky metrics test until the broadcaster follow-up lands. See `planning-docs/SPRINT_BACKLOG.md`.
- **Knowledge refinement**: the 2026-06-18-filed "session delete does not decrement active-session count" bug (Root cause #3) is recharacterized — not a product bug. The count converges correctly; the original test read a per-process TTL-cached value before it expired. The websocket-timeout half of that same entry is merged into the multi-worker broadcaster bug above rather than treated as separate.
- **Resolved 2026-09-09** (same day, later): the cross-worker broadcaster fix (Redis pub/sub) was requested and completed — see "Previous Task" (Cross-Worker WebSocket Broadcaster Fix, DECISION-021) above. The DECISION-019 major-version-bump question **is now also resolved** — KATO v5.0.0 released the same day, see DECISION-022 and the top "Previous Task" entry above.

**Anomalies/Fuzzy_Matches Field Split (Breaking) + Repeated-Symbol Multiset Fix + New Hello-World Character-Prediction Tests — COMPLETE (2026-09-09)**
- Status: COMPLETE — code, tests, and docs updated; **now committed as `a0e4acf` and released as part of v5.0.0** (see DECISION-022 and the top "Previous Task" entry above)
- Ad-hoc bug fix + architectural decision (not from a queued initiative); Multi-Worker Uvicorn initiative below remains next in the sprint backlog
- Decision: DECISION-019 in `planning-docs/DECISIONS.md`
- Archive: `planning-docs/completed/features/2026-09-09-anomalies-fuzzy-matches-field-split.md`
- New test file: `tests/tests/unit/test_hello_world_character_predictions.py` — 3 tests, learns "hello world" one character per event, asserts past/present/future/missing/extras/anomalies for "hello", "world", and perturbed "o wxld"; all 3 pass
- Bug fixed: `kato/representations/prediction.py`'s event-aligned `missing`/`extras` (and the flat fallback `missing`) used a flat `in` membership test against `matches`/`present`, so a repeated symbol was under-reported — an earlier occurrence masked a later unobserved one (the second `'o'` of "world" was never reported missing for "o wxld"). Fixed by consuming symbols as a multiset via `collections.Counter`.
- Architectural decision (DECISION-019, user chose from three options): `anomalies` redefined as a flat list of every symbol deviating from the pattern — missing, then extras, then each fuzzy match's observed token. The fuzzy-match detail records (`{observed, expected, similarity}`) `anomalies` used to hold move to a **new** `fuzzy_matches` field. **BREAKING CHANGE** for API consumers reading fuzzy details from `anomalies`. Alternatives rejected: replacing outright (loses fuzzy detail), mode-dependent typing (inconsistent type by config).
- Code (3 files): `kato/representations/prediction.py` (constructor kwarg `anomalies`→`fuzzy_matches`, `anomalies` computed after `missing`/`extras`), `kato/searches/pattern_search.py` (2 `Prediction()` call sites), `kato/workers/pattern_processor.py` (single-symbol fast-path dict now emits both fields)
- Tests updated (2 files): `tests/tests/unit/test_fuzzy_token_matching.py` (5 assertions, class renamed `TestAnomaliesStructure`→`TestFuzzyMatchesStructure`), `tests/tests/unit/test_filter_pipeline_parameters.py` (1 assertion)
- Docs updated (8 files): `docs/reference/prediction-object.md`, `docs/reference/session-configuration.md`, `docs/reference/api/predictions.md`, `docs/reference/api/configuration.md`, `docs/research/pattern-matching.md`, `docs/users/predictions.md`, `docs/users/configuration.md`, `docs/users/api-reference.md`. `CHANGELOG.md` `[Unreleased]` has a "Changed (BREAKING)" entry for anomalies/fuzzy_matches and a "Fixed" entry for the repeated-symbol bug.
- Verification: 233 passed / 1 skipped across unit prediction suites, integration prediction suites, and `tests/tests/api`. One failure, pre-existing and unrelated: `tests/tests/api/test_monitoring_endpoints.py::TestMonitoringEndpoints::test_metrics_collection_after_requests` (`assert 3204.0 > 3204.0`) — `/metrics` `total_requests` bounces between two values across consecutive reads (3208 → 1454 → 3208), consistent with per-worker in-process metrics under multiple uvicorn workers. Recorded as a known issue/follow-up, not part of this task — see `planning-docs/SPRINT_BACKLOG.md`.
- Operational notes recorded (knowledge refinement): the live `kato` container on `:8000` belongs to the `deployment/` compose project (`deployment/docker-compose.override.yml` pins `image: kato:latest`) — `docker compose restart` from the repo root does **not** pick up code changes; working sequence is `docker compose build kato` (root) then `docker compose -f deployment/docker-compose.yml -f deployment/docker-compose.override.yml up -d kato`. Also `./run_tests.sh` only honors its first path argument — multi-file runs need pytest directly with `PYTHONPATH="$PWD:$PWD/tests" ./venv/bin/python -m pytest`.
- **RESOLVED 2026-09-09**: this breaking API change was released as part of **KATO v5.0.0** with a major version bump — see DECISION-022 and `planning-docs/completed/features/2026-09-09-kato-v5.0.0-release.md`. Now committed as `a0e4acf`.

**Metadata Sidecar Re-Learn Duplicate SELECT Eliminated (+ Backlog Item Framing Correction) — COMPLETE (2026-09-09)**
- Status: COMPLETE (round-trip elimination) — the P2 "Metadata sidecar write path is un-batched" item is **partially** resolved, not closed; the append-only structural fix remains open
- Ad-hoc bug/optimization fix (grew out of the P2 item filed during the same-day configuration audit); Multi-Worker Uvicorn initiative below remains next in the sprint backlog
- Decision: DECISION-018 in `planning-docs/DECISIONS.md`
- Archive: `planning-docs/completed/optimizations/2026-09-09-metadata-sidecar-relearn-duplicate-select-eliminated.md`
- **Framing correction**: the item as originally filed said the fix "needs a batched upsert call shape at the `learnPattern` level." That's unachievable — `learn()` produces exactly one Pattern per call and never fans out, so there's no batch to form within a request; forming one across requests would need a per-worker buffer, which is exactly what `f809a84` removed to fix a correctness bug (orphaned rows across the 4 uvicorn workers). Corrected framing: **eliminate round trips, don't group them**. (Nuance: `observe-sequence` with `learn_after_each=True` can produce N+1 learns in one request, but that loop is strictly sequential — each `learnPattern` mutates Redis stats the next iteration reads — so it isn't safe to batch either.)
- Root cause: the re-learn path SELECTed the same ClickHouse row twice per learn — `knowledge_base.py`'s call to `metadata_router.get_metadata()` fetched the full row then discarded the metric columns (entropy/normalized_entropy/global_normalized_entropy/tf_vector) plus an unused Redis frequency `MGET`; `upsert_pattern_metadata` then re-issued the identical SELECT to recover those discarded columns.
- Fix (2 files, +39/-5): new `metadata_router.get_metadata_for_merge()` (raw full row, no unused Redis lookup); `upsert_pattern_metadata` gained optional `prev=` so a caller that already read the row can hand it over (`prev=None` preserves old behavior for other callers); `knowledge_base.py`'s re-learn branch threads the row through as `prev=`
- Measured: re-learn path 2 SELECTs → 1 (unit-level instrumentation); end-to-end against the running container, background noise subtracted: 8 → 7.27 ClickHouse queries per re-learn; entropy/tf_vector survival verified directly through the `prev`-threaded path; `test_emotives_comprehensive.py` + `test_metadata_comprehensive.py` 22 passed; full suite 452 passed / 4 skipped / 3 failed (best result this session; remaining 3 are the known multi-worker session_cleanup + websocket failures)
- Design constraint recorded prominently (see archive + DECISION-018): the NEW-pattern-branch read in `upsert_pattern_metadata` looks redundant but is deliberately kept — `is_new` comes from a Redis `SETNX` that can be empty while ClickHouse still holds the row post Redis-loss-then-rehydrate (hit twice in this project: April 2026 persistence incident, and this session's conftest FLUSHALL bug). Also: `wait_for_async_insert=1` on this path is load-bearing (unlike `patterns_data`'s `=0`) — emotives accumulation is a cross-process read-modify-write, so a re-learn inside the ~200ms async-insert window would read stale emotives
- **Open follow-up (not done)**: the structural fix — make emotives/metadata append-only, apply `persistence` at read time (`groupArray`+tail; `groupUniqArray` for metadata) instead of merging on write — remains open. Cost: schema split of `patterns_metadata`, backfill, reader updates. See `planning-docs/SPRINT_BACKLOG.md` "Follow-up: Metadata sidecar read-modify-write shape"
- Also filed: P3 test flakiness in `test_bayesian_likelihood_equals_similarity` (observed during verification, unrelated to this fix — likely the same `patterns_data` async_insert visibility race as backlog item 1 below) — see `planning-docs/SPRINT_BACKLOG.md`

**Configuration Audit: Env Var Wiring, Dead-Parameter Removal, and `/concurrency` 4x Undercount Fix — COMPLETE (2026-09-09)**
- Status: COMPLETE — resolves the prior "dead `KATO_*` env names" P2 backlog item (with a corrected, narrower understanding), plus wiring/cleanup/bug fixes beyond that item's original scope
- Ad-hoc audit (grew out of the 2026-09-08 dead-env-names finding, not from a queued initiative); Multi-Worker Uvicorn initiative below remains next in the sprint backlog
- Decision: DECISION-017 in `planning-docs/DECISIONS.md`
- Archive: `planning-docs/completed/refactors/2026-09-09-configuration-audit-wiring-dead-parameter-removal.md`
- Corrected understanding: `KATO_BATCH_SIZE` was dead on two independent levels, not one — `json_schema_extra={'env': ...}` never bound (pydantic-v1 idiom, ignored by v2), **and** `settings.performance.batch_size` had zero consumers anywhere, so there was never a lost-performance impact as the original item implied. `KATO_VECTOR_BATCH_SIZE` bound correctly via raw `os.getenv()` but its attribute also had no consumers.
- Key finding: KATO already batches ClickHouse pattern writes server-side via `async_insert=1` (`clickhouse_writer.py`), coalescing across all uvicorn workers. Client-side buffering is deliberately disabled (`DEFAULT_BATCH_SIZE=1`; commit `f809a84` dropped it from 50 to 1 to fix a per-worker orphaned-row correctness bug). Wiring `batch_size` would have re-introduced that bug, so it was deleted instead of wired.
- Bugs fixed: `/concurrency` under-reported capacity 4x (`UVICORN_WORKERS`/`UVICORN_LIMIT_CONCURRENCY` never exported by uvicorn; corrected to `KATO_WORKERS`/`KATO_LIMIT_CONCURRENCY`, new `WORKER_COUNT` constant); 5 dead env names now bound via `AliasChoices` (`KATO_USE_TOKEN_MATCHING`, `KATO_FUZZY_TOKEN_THRESHOLD`, `KATO_USE_FAST_MATCHING`, `KATO_USE_INDEXING`, `KATO_CONFIG_FILE`; `SORT` deliberately not aliased)
- Newly wired: `LOG_FORMAT`/`LOG_OUTPUT` (behavior change: logs now default to stdout, was stderr), `CONNECTION_POOL_SIZE` (default 10→200), `REQUEST_TIMEOUT` (compose's 120.0 now genuinely applies), `fuzzy_token_threshold`
- Deleted: `performance.batch_size`, `use_optimized`, `vector_batch_size`, `vector_search_limit`, `auto_learn_enabled`, `auto_learn_threshold`, `service_version`, `QDRANT_COLLECTION_PREFIX`, entire `APIConfig` class, `KATO_ARCHITECTURE_MODE`/`KATO_STRICT_MODE` dead reads, 4 zero-importer modules (`config/database.py`, `config/api.py`, `config/user_config.py`, `storage/query_batcher.py`); removed from compose files, Helm chart, 14 docs
- Verification: ruff clean (net -4 findings); settings load + vectordb `EXAMPLE_CONFIGS` validate; image rebuilt/restarted; `/concurrency` confirmed 4/400 live; vector observe+learn+count 200; full suite 451 passed / 4 skipped / 4 failed (best result this session; remaining 4 are the known multi-worker websocket/session issues)
- New backlog items filed: P2 metadata-sidecar write path un-batched (synchronous per-learn ClickHouse round trip; real batching win — **the "needs batched call shape" fix direction below was later corrected as unachievable; see DECISION-018 and "Previous Task" above**); P3 dead no-op flush methods in `clickhouse_writer.py`; P3 `CLAUDE.md` PROCESSOR_ID drift; P3 aspirational JWT docs; P3 stale gunicorn performance-tuning docs — see `planning-docs/SPRINT_BACKLOG.md`

**`.env`/dotenv-settings Crash Bug Fix — COMPLETE (2026-09-08)**
- Status: COMPLETE — bug fixed, verified end-to-end
- Ad-hoc bug fix (originally logged P2 backlog item, not from a queued initiative); Multi-Worker Uvicorn initiative below remains next in the sprint backlog
- Decision: DECISION-016 in `planning-docs/DECISIONS.md`
- Archive: `planning-docs/completed/bugs/2026-09-08-env-dotenv-settings-crash.md`
- Bug (as originally logged): `.env`'s `REDIS_PERSISTENCE=true` crashed a locally-run (non-Docker) KATO server with a pydantic `ValidationError`
- Real root cause (broader): `Settings.model_config` declared `env_file='.env'` while inheriting `extra='forbid'`; pydantic-settings' dotenv loader forwards every unmatched `.env` key onto the model, so nearly every real KATO variable (`LOG_LEVEL`, `QDRANT_HOST`, `REDIS_URL`, `CLICKHOUSE_HOST`) crashed it, while a couple (`SERVICE_NAME`, `SESSION_TTL`) were silently swallowed via accidental field-name prefix matching. `.env` was effectively unusable outside Docker. Docker was never affected (`.env` not `COPY`ed into the image)
- Fix: new `kato/env_loader.py` loads `.env` into `os.environ` via `python-dotenv` (deterministic order: `KATO_ENV_FILE` -> repo-root `.env` -> CWD `.env`; `KATO_SKIP_DOTENV=1` opt-out), called first thing in `kato/__init__.py` (reaches both pydantic `Settings` and the several hot paths that read `os.environ` directly and never go through pydantic); `env_file`/`env_file_encoding` removed from `Settings.model_config`; `extra='forbid'` deliberately kept (still protects `KATO_CONFIG_FILE` validation); `.env.example` rewritten (dead names removed); `kato.api.main` -> `kato.services.kato_fastapi` corrected across 12 docs; new `make run` target; `requirements.lock` regenerated
- Verification: crash gone; `.env` values (`QDRANT_PORT`/`LOG_LEVEL`/`REDIS_ENABLED`/`SESSION_TTL`) confirmed genuinely applying; process env still beats `.env`; `KATO_SKIP_DOTENV` opts out; CWD-independent; `make run` fully functional (observe/learn/patterns-count/predictions/clear-all all 200, learn->count 0->1->0); Docker unaffected (no `.env` in image, compose values still win). Full suite 447 passed / 2 skipped / 5 failed (improvement on 446/2/6 baseline; remaining 5 are the known multi-worker websocket/session backlog bug)
- Incidental findings fixed via the lock regeneration: `xxhash` was declared in `requirements.txt` but missing from `requirements.lock` (never installed in the container — `MINHASH_HASH_FUNC=xxhash` silently fell back to SHA-1); stale `pymongo`/`dnspython` were still pinned despite MongoDB's v3.0 removal (currently installed in the running container). Both corrected in the lock file; not yet reflected in the running container until the next `docker compose build --no-cache kato`
- New backlog item added: dead `KATO_*` env names via `json_schema_extra={'env': ...}` (pydantic-v1 idiom, ignored by pydantic-settings v2) — `docker-compose.yml`'s `KATO_BATCH_SIZE=10000` has no effect; P2, see `planning-docs/SPRINT_BACKLOG.md`

**`start.sh clean-data` ClickHouse No-Op Bug Fix + Local Test Data Purge — COMPLETE (2026-09-08)**
- Status: COMPLETE — bug fixed, verified end-to-end, then used to purge all local test data at the user's explicit direction
- Ad-hoc bug fix + user-directed maintenance action (not from a queued initiative); Multi-Worker Uvicorn initiative below remains next in the sprint backlog
- Archive: `planning-docs/completed/bugs/2026-09-08-start-sh-clean-data-clickhouse-noop.md`
- Bug: ClickHouse step ran `DROP TABLE IF EXISTS default.patterns_data`, but pattern tables live in the `kato` database, not `default` — silent no-op (masked by `IF EXISTS` + suppressed stderr) that unconditionally reported success while never touching `patterns_data`, `patterns_metadata`, `lsh_buckets`, or `pattern_stats`
- Fix: `TRUNCATE TABLE IF EXISTS kato.$table` loop over all four tables; `2>/dev/null` suppression removed so future failures surface; `BGREWRITEAOF` added after Redis `FLUSHALL` to reclaim AOF disk
- Maintenance: purged 238 kb_ids / 2,977 rows (patterns_data) + 1,313 kb_ids / 3,595 rows (patterns_metadata) from ClickHouse, 56 Redis keys, 13 Qdrant `vectors_test_*` collections; Redis disk reclaimed 4.4 GB → 40 KB
- Verification: all four ClickHouse tables 0 rows/schema intact, Redis DBSIZE 0, Qdrant no collections, `/health` 200, learn→count→clear-all smoke test correct (0→1→0); `tests/tests/api/` + `tests/tests/integration/test_database_persistence.py` — 60 passed / 1 skipped from the empty state
- Knowledge refinement: corrected an earlier same-day claim that Redis persistence was disabled — `REDIS_PERSISTENCE=true` has been set in `.env`/`deployment/.env` since 2026-04-13; persistence protects against restarts/crashes, not explicit deletion, so it never prevented the FLUSHALL data-loss risk

**Pattern Count Endpoint — COMPLETE (2026-09-08)**
- Status: COMPLETE — `GET /patterns/count` added, storage-layer dead code wired up, doc drift fixed
- Ad-hoc feature work (not from a queued initiative); Multi-Worker Uvicorn initiative below remains next in the sprint backlog
- Decision: DECISION-015 in `planning-docs/DECISIONS.md`
- Archive: `planning-docs/completed/features/2026-09-08-pattern-count-endpoint.md`
- Test results: full suite 448 passed / 2 skipped / 4 failed (4 failures target a stale port-8000 container, unrelated); API suite 50 passed; integration persistence suite 10 passed

**Redis OOM Fix: Move Per-Pattern Metadata from Redis to ClickHouse — COMPLETE (2026-06-18)**
- Status: COMPLETE — all phases done, dual-write scaffolding removed, ClickHouse sole metadata store
- Engineering complete (phases 0–5): 2026-05-20 / Staging validated (phases 3–5): 2026-05-22
- Correctness bug fixed + finalization (phases 6–7, dual-write removal): 2026-06-18
- Initiative File: `planning-docs/initiatives/redis-oom-clickhouse-metadata-migration.md`
- Decision: DECISION-014 in `planning-docs/DECISIONS.md`
- Archive: `planning-docs/completed/features/2026-06-18-redis-clickhouse-metadata-migration-complete.md`
- Final test results: 446 passed, 6 pre-existing failures (unrelated to migration)
- Key correctness fix: `version UInt64` (`time.time_ns()`) replaces `updated_at DateTime` as `ReplacingMergeTree` version and `argMax` tiebreaker — eliminates same-second row ambiguity that lost emotive rolling-window merges

**Multi-Worker Uvicorn + Concurrent Training Safety**
- Status: QUEUED (planned 2026-04-20, superseded by Redis OOM initiative — now ready to resume)
- Plan File: `/Users/sevakavakians/.claude/plans/ultrathink-enable-multi-worker-recursive-marble.md`
- Objective: Enable `--workers N` uvicorn, fix per-worker ClickHouse buffer orphan risk, close SETNX/frequency races
- Note: Distributed session locks are NOT in scope

## Critical Issue Discovered

**Bug**: Session isolation broken in KATO v3.0
**Root Cause**: KatoProcessor is stateful (holds STM, emotives, percept_data as instance variables)
**Impact**: Multiple sessions with same node_id share processor instance → session data leaks
**Current Workaround**: Processor locks (forces sequential processing - architectural band-aid)
**Proper Fix**: Make KatoProcessor stateless (standard web application pattern)

## Progress - Stateless Processor Refactor Initiative
**Total Progress: 52% COMPLETE** 🎯 (Phases 1 & 3 Complete, Phase 2 In Progress - 60%)

### Phase 1: Stateless Processor Refactor (INCOMPLETE - 80%) ⚠️
**Duration**: 1-2 days (30-44 hours actual + additional time needed)
**Status**: INCOMPLETE - Critical issues discovered 2025-11-26

**Tasks**:
1. ✅ Make MemoryManager stateless (Phase 1.1 - COMPLETE)
   - Converted all methods to static/pure functions
   - Removed all instance variables (symbols, time, emotives, percept_data)
   - All methods accept state as input, return new state as output
   - Commit: 3dc344d
2. ✅ Update KatoProcessor to accept SessionState (Phases 1.2-1.5 - COMPLETE)
   - __init__: Removed all session-specific instance variables
   - observe(): Accepts session_state + config, returns new state dict
   - get_predictions(): Accepts session_state + config, returns predictions
   - learn(): Accepts session_state, returns (pattern_name, new_stm)
   - Commit: 4a257d6
3. ✅ Update session endpoints to use stateless pattern (Phases 1.6-1.8 - COMPLETE)
   - observe_in_session: Calls processor.observe(observation, session_state, config)
   - get_session_predictions: Calls processor.get_predictions(session_state, config)
   - learn_in_session: Calls processor.learn(session_state)
   - observe_sequence_in_session: Chains state through sequence
   - All follow: load session → call processor → save returned state
   - Commit: 8e74f94
4. ⚠️ Remove all processor locks (Phases 1.9-1.10 - REVERTED)
   - **CRITICAL**: Lock removal was premature
   - **Root Cause**: Pattern processor still shares STM across sessions (pattern_processor.STM instance variable)
   - **Test Failures**: 2 of 5 session isolation tests failing
     - test_stm_isolation_concurrent_same_node: Session 1 STM overwritten by Session 2
     - test_stm_isolation_after_learn: Session 1 STM changed from [['hello'], ['world']] to [['foo'], ['bar']]
   - **Legacy Sync Code Found**: get_session_stm endpoint syncs STM FROM processor TO session
   - **Fix Applied**: Re-added processor-level locks as temporary fix (commit pending)
   - **Next Steps**: Find and remove all processor→session sync code, make pattern_processor truly stateless
5. ✅ Update helper modules (Phase 1.7 - COMPLETE)
   - observation_processor: Compatible with stateless MemoryManager
   - pattern_operations: Uses MemoryManager static methods
   - Commit: 8e74f94
6. ⏸️ Make pattern_processor stateless (Phase 1.11 - NEW TASK REQUIRED)
   - Pattern processor stores STM as instance variable (violates stateless design)
   - Pattern processor is shared across sessions with same node_id
   - Need to remove processor.STM and make fully stateless
   - Need to find/remove all processor→session sync code

**Architecture Status**:
- ⚠️ LOCKS RE-ADDED: Temporarily restored to fix session isolation bug
- ⚠️ SEQUENTIAL PROCESSING: Still bottlenecked until pattern_processor is stateless
- ❌ SESSION ISOLATION: Tests failing - STM leaking between sessions
- ⏸️ TRUE CONCURRENCY: Blocked until pattern_processor refactor complete
- ⏸️ HORIZONTAL SCALABILITY: Blocked until stateless pattern complete

### Phase 2: Test Updates (IN PROGRESS - 60%)
**Duration**: 1 day (14-19 hours)
**Status**: IN PROGRESS - 3 of 5 tasks complete (2025-11-28)

**Tasks**:
1. ✅ Update test fixtures (2-3 hours) - COMPLETE
   - Deprecated aliases added for backward compatibility
   - Modern config terminology available
   - Both old and new methods work
2. ✅ Run session isolation test (1 hour) - COMPLETE
   - All 5 session isolation tests passing
   - Phase 1 stateless refactor successful
3. ✅ Update gene references (3-4 hours, 47 occurrences, 9 files) - COMPLETE
   - **Files Modified**: 8 test files
   - **Total Changes**: 47 occurrences replaced
   - All update_genes() calls → update_config()
   - All get_genes() calls → get_config()
   - Comments and documentation updated
   - Deprecated aliases remain in fixtures (intentional)
   - **Test Results**: All updated tests passing
   - **Pre-existing Issue**: 1 test failure in test_rolling_window_integration.py::test_time_series_pattern_learning (unrelated to terminology changes)
4. ⏸️ Create configuration tests (4-6 hours)
   - Session config creation/updates
   - Default values and validation
5. ⏸️ Create prediction metrics tests (4-6 hours)
   - Bayesian metrics tests
   - TF-IDF score tests

### Phase 3: Documentation Updates (COMPLETE ✅ - 100%)
**Duration**: 0.5 days (6 hours actual)
**Status**: 100% COMPLETE (2025-11-28)

**Tasks**:
1. ✅ Remove MongoDB references (~200 references across 24 files) - COMPLETE
   - Manually updated 3 critical architecture files
   - Batch updated 21 additional documentation files via general-purpose agent
   - Total: ~200 MongoDB references removed
   - Files: HYBRID_ARCHITECTURE.md (4), KB_ID_ISOLATION.md (1), configuration-management.md (1), 21 others (~194)
2. ✅ Verify documentation completeness - COMPLETE
   - No MongoDB references remain in active documentation
   - Archive and investigation directories preserved as historical records

### Phase 4: Verification & Testing (PENDING - 0%)
**Duration**: 0.5 days (7-9 hours)
**Status**: Blocked by Phase 1 & 2

**Tasks**:
1. ⏸️ Full test suite execution (1 hour)
2. ⏸️ Session isolation stress test (2-3 hours)
3. ⏸️ Concurrent load test (2-3 hours)
4. ⏸️ Manual testing (2-3 hours)
5. ⏸️ Performance benchmarking (2-3 hours)

### Phase 5: Cleanup (PENDING - 0%)
**Duration**: 0.25 days (2-8 hours)
**Status**: Blocked by Phase 4

**Tasks**:
1. ⏸️ Remove obsolete gene code (2-3 hours)
2. ⏸️ Update CLAUDE.md (1-2 hours)
3. ⏸️ Add ADR-001 architecture decision record (2-3 hours)

## Active Files
**Phase 1 Target Files**:
- `kato/workers/memory_manager.py` - Make stateless
- `kato/workers/kato_processor.py` - Accept SessionState parameters
- `kato/api/endpoints/sessions.py` - Update to stateless pattern
- `kato/api/endpoints/observe.py` - Update to stateless pattern
- `kato/api/endpoints/predictions.py` - Update to stateless pattern
- `kato/api/endpoints/learn.py` - Update to stateless pattern
- `kato/api/endpoints/recall.py` - Update to stateless pattern
- `kato/api/endpoints/clear.py` - Update to stateless pattern
- `kato/api/endpoints/config.py` - Update to stateless pattern
- `kato/processors/processor_manager.py` - Remove locks
- `kato/workers/observation_processor.py` - Update to stateless
- `kato/workers/pattern_operations.py` - Update to stateless

## Next Immediate Action
**SUPERSEDED (2026-09-10) — see "Current Task" at the top of this file for the live status.** Current next action: Phase 1.6 lock-free refactor (DECISION-025 Option B) for the Multi-Worker Uvicorn + Concurrent Training Safety initiative. The historical content below is kept for continuity.

~~**Resume Multi-Worker Uvicorn + Concurrent Training Safety**~~

The configuration audit (env var wiring, dead-parameter removal) is complete. The next queued initiative is multi-worker uvicorn support (see SPRINT_BACKLOG.md for full plan). Known backlog bugs (all P2 unless noted, non-blocking):

1. **Bug: patterns_data async_insert visibility race (Root cause #1)** — P2
   - `knowledge_base.py:~413` `wait_for_async_insert=0` on patterns_data writes; no server-queue drain on the learn/predict hot path
   - Symptom: flaky "0 predictions" under load; `test_bayesian_likelihood_equals_similarity` passes in isolation but fails in full suite
   - Fix: add server-side queue drain or switch specific write to `wait_for_async_insert=1`

2. ~~**Bug: session delete does not decrement active-session count (Root cause #3)**~~ — **RESOLVED/RECHARACTERIZED 2026-09-09**: not a product bug. The rewritten `test_session_cleanup` (see `tests/tests/integration/test_worker_topology.py` work above, DECISION-020) waits for the documented per-process `/sessions/count` TTL cache (`SESSION_COUNT_CACHE_TTL_SECONDS`, default 5) to expire before reading, and passes deterministically. The count converges correctly; the original test simply read a cached value too early. See `planning-docs/completed/features/2026-09-09-worker-topology-tests-and-worker-pid.md`.

3. ~~**Bug: Multi-worker (`KATO_WORKERS=4`) breaks websocket event delivery**~~ — **RESOLVED 2026-09-09** (websocket-delivery half). Fixed via Redis pub/sub fan-out — see DECISION-021 and `planning-docs/completed/features/2026-09-09-websocket-cross-worker-broadcaster-redis-pubsub.md`. `tests/tests/integration/test_worker_topology.py` now passes 15/15 across `KATO_WORKERS` in {1, 2, 4}. Full suite: 475 passed / 4 skipped / 0 failed.
   - **Still open, separate symptom**: `test_concurrent_session_modifications` losing half its concurrent writes (`assert 5 == 10`, originally reported 2026-09-08) was never confirmed to share this root cause and is **not** addressed by the pub/sub fix — remains open/unconfirmed. See `planning-docs/SPRINT_BACKLOG.md`.
   - Overlaps with the "Multi-Worker Uvicorn + Concurrent Training Safety" initiative — see `planning-docs/SPRINT_BACKLOG.md`

4. **Follow-up: Metadata sidecar read-modify-write shape (structural fix — append-only emotives/metadata)** — P2 (discovered 2026-09-09 during configuration audit; re-scoped and partially resolved 2026-09-09)
   - Originally filed as needing "a batched call shape at the `learnPattern` level" — that framing was **wrong** and has been corrected (see DECISION-018): `learn()` produces exactly one Pattern per call with no fan-out, so there is no batch to form; the achievable fix is round-trip elimination, not call grouping
   - **Already fixed**: the re-learn path's duplicate ClickHouse SELECT is eliminated (2 → 1) — see `planning-docs/completed/optimizations/2026-09-09-metadata-sidecar-relearn-duplicate-select-eliminated.md`
   - **Still open**: the read-modify-write shape itself (why `upsert_pattern_metadata` must read before writing at all, and why it's forced onto blocking `wait_for_async_insert=1`). Structural fix is making emotives/metadata append-only — see `planning-docs/SPRINT_BACKLOG.md` "Follow-up: Metadata sidecar read-modify-write shape"

**Resolved 2026-09-09** (previously item 3 here): dead `KATO_*` env names via `json_schema_extra={'env': ...}` — see "Previous Task" above and `planning-docs/SPRINT_BACKLOG.md` Recently Completed. Corrected understanding: the impact was overstated (`batch_size` had zero consumers regardless of binding); `batch_size` was deleted rather than wired, other dead names were aliased forward.

## Blockers
**1 active blocker (severe, confirmed) — 2026-09-10**: observe path deadlocks any uvicorn worker on overlapping same-node_id requests (BRIDGE-pattern lock introduced in `52e9284`, holds a blocking `multiprocessing.Lock` across an `await`). Blocks Phase C and closure of the "Multi-Worker Uvicorn + Concurrent Training Safety" initiative. Decision pending: Option A (asyncio.Lock, keeps a lock) vs Option B (Phase 1.6 stateless-STM refactor, no-locks-rule compliant, recommended). See "Current Task" above and `planning-docs/project-manager/pending-updates.md`.

Other backlog bugs (Phase A/B related, P2) remain non-blocking.

## Context
**Current Initiative**: Stateless Processor Refactor (Critical Priority)

**Background**:
- KATO v3.0 has a critical session isolation bug
- Multiple sessions with same node_id share processor instance
- Stateful processor design causes session data to leak
- Current workaround (processor locks) causes sequential processing bottleneck
- Proper fix requires architectural refactor to stateless pattern

**Objective**:
Make KatoProcessor stateless following standard web application patterns:
- Processors accept session state as parameters
- Processors return new state as results
- No instance variable mutations
- No locks needed (true concurrent access)

**Expected Benefits**:
- ✅ Session isolation guaranteed
- ✅ True concurrency (5-10x performance improvement)
- ✅ Horizontal scalability
- ✅ Simpler code (no lock management)
- ✅ Standard web architecture pattern

**Timeline**: 2-3 days total

## Key Metrics - Stateless Refactor Initiative

**Timeline**:
- **Phase 1**: 1-2 days (30-44 hours) - Core refactoring
- **Phase 2**: 1 day (14-19 hours) - Test updates
- **Phase 3**: 0.5 days (4-6 hours) - Documentation (parallel)
- **Phase 4**: 0.5 days (7-9 hours) - Verification
- **Phase 5**: 0.25 days (2-8 hours) - Cleanup
- **Total**: 2.5-3.5 days (51-72 hours)

**Scope**:
- Files to modify: ~15 core files
- Tests to update: ~9 test files (47 occurrences)
- Documentation to update: ~20+ docs (224 MongoDB references)
- New tests to create: 3 test files

**Performance Targets**:
- 5-10x throughput improvement
- 50-80% latency reduction
- Zero lock contention
- Linear scaling with concurrent sessions

**Code Quality Targets**:
- 100% test pass rate
- Zero session data leaks
- No instance variable mutations
- Clean functional signatures

## Documentation
- **Initiative Plan**: planning-docs/initiatives/stateless-processor-refactor.md
- **Architecture Decision**: docs/architecture-decisions/ADR-001-stateless-processor.md (to be created)
- **Related Work**: planning-docs/initiatives/hybrid-clickhouse-redis.md (v3.0 architecture)

## Recent Achievements
- **Bug Fix: `.env`/dotenv-settings Crash — COMPLETE** (2026-09-08): BUG FIX (P2, root cause broader than originally logged)
  - **What**: Originally logged as `.env`'s `REDIS_PERSISTENCE=true` crashing a locally-run (non-Docker) KATO server. Real root cause: `Settings.model_config` declared `env_file='.env'` while inheriting `extra='forbid'`; pydantic-settings' dotenv loader forwards every key it can't match onto the model, so nearly every real `.env` variable (`LOG_LEVEL`, `QDRANT_HOST`, `REDIS_URL`, `CLICKHOUSE_HOST`) crashed it, while a couple (`SERVICE_NAME`, `SESSION_TTL`) were silently swallowed via accidental prefix-matching. `.env` was effectively unusable outside Docker; Docker itself was never affected (`.env` not `COPY`ed into the image)
  - **Fix**: New `kato/env_loader.py` loads `.env` into `os.environ` via `python-dotenv` (order: `KATO_ENV_FILE` -> repo-root `.env` -> CWD `.env`; `KATO_SKIP_DOTENV=1` opt-out), called first in `kato/__init__.py` so it reaches both pydantic `Settings` and the several hot paths reading `os.environ` directly (never through pydantic). `env_file`/`env_file_encoding` removed from `Settings.model_config`; `extra='forbid'` deliberately kept (still protects `KATO_CONFIG_FILE` validation). `.env.example` rewritten (dead names removed); `kato.api.main` -> `kato.services.kato_fastapi` corrected across 12 docs; new `make run` target; `requirements.lock` regenerated
  - **Verification**: crash reproduced then gone; `.env` values (`QDRANT_PORT`/`LOG_LEVEL`/`REDIS_ENABLED`/`SESSION_TTL`) confirmed genuinely applying; process env still beats `.env`; `KATO_SKIP_DOTENV` opts out; CWD-independent; `make run` produced a fully working non-Docker server (observe/learn/patterns-count/predictions/clear-all all 200, learn->count 0->1->0); Docker unaffected (compose values still win)
  - **Test results**: full suite 447 passed / 2 skipped / 5 failed — improvement on the 446/2/6 baseline; remaining 5 are the already-characterized multi-worker websocket/session backlog bug (item 4 below), unrelated
  - **Incidental findings fixed via lock regeneration**: `xxhash` was declared in `requirements.txt` but missing from `requirements.lock` (never installed in the container; `MINHASH_HASH_FUNC=xxhash` silently fell back to SHA-1); stale `pymongo`/`dnspython` still pinned in the lock despite MongoDB's v3.0 removal (currently installed in the running container). Both corrected in the lock file — effective on the next `docker compose build --no-cache kato`, not yet in the running container
  - **New backlog item**: dead `KATO_*` env names via `json_schema_extra={'env': ...}` (pydantic-v1 idiom, ignored by pydantic-settings v2) — `docker-compose.yml`'s `KATO_BATCH_SIZE=10000` has no effect — P2, see item 3 above and `planning-docs/SPRINT_BACKLOG.md`
  - **Decision**: DECISION-016 in `planning-docs/DECISIONS.md`
  - **Archive**: `planning-docs/completed/bugs/2026-09-08-env-dotenv-settings-crash.md`
- **Bug Fix: `start.sh clean-data` ClickHouse No-Op — COMPLETE + Local Test Data Purge** (2026-09-08): BUG FIX + MAINTENANCE
  - **What**: `./start.sh clean-data`'s ClickHouse step ran `DROP TABLE IF EXISTS default.patterns_data` — wrong database (tables live in `kato`, not `default`), so the command silently no-opped (masked by `IF EXISTS` + `2>/dev/null`) while unconditionally printing "✓ All database data has been cleared!" It also never referenced `patterns_metadata`, `lsh_buckets`, or `pattern_stats` at all
  - **Fix**: Replaced with a `TRUNCATE TABLE IF EXISTS kato.$table` loop over all four real tables (preserves schema/partitioning, no `init.sql` re-run needed); removed `2>/dev/null` so future failures print a per-table warning; added Redis `BGREWRITEAOF` after the existing `FLUSHALL` (FLUSHALL empties the keyspace but doesn't shrink the on-disk AOF)
  - **Verification**: 347/370 rows across `patterns_data`/`patterns_metadata`, 1721 Redis keys, 2 Qdrant collections all brought to 0/empty by one `clean-data` run; ClickHouse tables confirmed still present with schema intact; `bash -n` clean
  - **Maintenance action**: user confirmed all local data is test data, not production ("They can all be cleared out"), closing out a separate open question about recovering pre-flush Redis metadata (no recovery needed/attempted). Purged 238 kb_ids / 2,977 rows (`patterns_data`) + 1,313 kb_ids / 3,595 rows (`patterns_metadata`, including the former `node0_kato`/`node1_kato`), 56 Redis keys, 13 Qdrant `vectors_test_*` collections; Redis disk reclaimed 4.4 GB → 40 KB via `BGREWRITEAOF` (AOF had a 2.69 GB Apr 28 base + 2.07 GB incremental log)
  - **Post-cleanup verification**: all 4 ClickHouse tables 0 rows/schema intact, Redis `DBSIZE` 0, Qdrant no collections, `/health` 200; learn→count→clear-all smoke test correct (0→1→0); `tests/tests/api/` + `tests/tests/integration/test_database_persistence.py` — 60 passed / 1 skipped from the empty state
  - **Knowledge refinement**: corrected an earlier same-day claim (in this file and two archive docs) that Redis persistence was disabled/absent by default. It was wrong — `REDIS_PERSISTENCE=true` is set in both `.env` and `deployment/.env`, unchanged since the 2026-04-13 fix, and the running container has `--appendonly yes`, `aof_enabled:1`. Persistence protects against restarts/crashes, not explicit deletion commands — it never prevented the FLUSHALL-related data-loss risks
  - **Archive**: `planning-docs/completed/bugs/2026-09-08-start-sh-clean-data-clickhouse-noop.md`
- **Bug Fix: conftest.py Redis FLUSHALL Scoped to Ephemeral Keys — COMPLETE** (2026-09-08): BUG FIX (P2, data-loss risk)
  - **What**: `tests/tests/conftest.py`'s `flush_redis_before_tests` fixture no longer runs an unconditional `docker exec kato-redis redis-cli FLUSHALL`. It now deletes only ephemeral session/STM keys via a new `EPHEMERAL_KEY_PATTERNS = ("kato:session:*", "stm:events:*", "stm:global")` constant, using `redis.Redis(...).scan_iter()` with batched deletes (batches of 1000)
  - **Connection**: Uses the `redis` Python client honoring `REDIS_HOST`/`REDIS_PORT` env vars instead of hardcoded `docker exec kato-redis`; `subprocess` import removed, `os`/`redis` added
  - **Escape hatch**: `KATO_TEST_REDIS_FLUSHALL=1` restores the full FLUSHALL (with a printed warning) for a Redis dedicated to testing
  - **Why safe**: Durable pattern metadata is namespaced under `kb_id` (`<kb_id>:frequency:*`, `:symbols:freq`, `:symbols:pmf`, `:symbol_to_patterns:*`, `:affinity:*`, `:global:*`, `:prediction:*` per `kato/storage/redis_writer.py`), which cannot match any of the three ephemeral patterns
  - **Verification**: Seeded durable metadata (including adversarial `kb_id="kato"`) plus ephemeral keys, ran a test session, confirmed durable keys survived intact and ephemeral keys were cleared; confirmed `KATO_TEST_REDIS_FLUSHALL=1` still full-flushes; ruff clean
  - **Test results**: full suite (excluding performance) 446 passed, 2 skipped, 6 failed — all 6 failures confirmed pre-existing and unrelated (identical failures reproduce under old FLUSHALL behavior via `KATO_TEST_REDIS_FLUSHALL=1`)
  - **New bug characterized from the 6 failures**: multi-worker (`KATO_WORKERS=4`) breaks websocket event fan-out and concurrent session write consistency — added as new backlog item 4 above, see `planning-docs/SPRINT_BACKLOG.md`
  - **Archive**: `planning-docs/completed/bugs/2026-09-08-conftest-redis-flushall-scoped-to-ephemeral-keys.md`
- **Pattern Count Endpoint — COMPLETE** (2026-09-08): NEW API FEATURE + DOC FIX
  - **What**: New `GET /patterns/count` endpoint (node-scoped via `node_id` param/header, `flush` param default `true`) returns `{"pattern_count": int, "node_id": str}`. Wires up previously-dead `PatternOperations.get_pattern_count()`.
  - **Path choice**: `/patterns/count` (plural), not `/pattern/count`, to avoid being shadowed by the existing `GET /pattern/{pattern_id}` route
  - **Flush**: Handler runs in `asyncio.to_thread` (sync ClickHouse driver call); `flush=True` default guarantees read-your-writes since pattern inserts use `wait_for_async_insert=0`
  - **Decision**: ClickHouse is the authoritative count source, not the Redis `total_unique_patterns` counter (which has no decrement path and drifts high after deletions) — DECISION-015
  - **Doc fix**: `docs/reference/api/learning.md` documented a `GET /status` -> `processors.patterns_count` field that never existed; fixed. Also corrected the `/status` response shape (`total_processors`/`max_processors`/`eviction_ttl_seconds`/`processors[]`) in `docs/reference/api/health.md`, `docs/reference/api/monitoring.md`, `docs/developers/architecture.md`
  - **Client**: `examples/python-client.py` `get_pattern_count()` added, version bumped to 3.6.0
  - **Tests**: 3 new tests in `tests/tests/api/test_fastapi_endpoints.py`; dead prediction-count proxy in `tests/tests/integration/test_database_persistence.py::count_patterns_for_node` replaced with a real call to the new endpoint
  - **Test results**: full suite 448 passed / 2 skipped / 4 failed (4 failures target a stale port-8000 container, unrelated to this work); API suite 50 passed; integration persistence suite 10 passed; functional smoke confirmed 0 -> 1 after learn (12.7ms), relearn stays 1, distinct sequence goes to 2
  - **Two pre-existing issues discovered (not part of this change)**: `tests/tests/conftest.py:24` unconditional Redis FLUSHALL destroys live metadata regardless of persistence (persistence protects against restarts/crashes, not explicit deletion); `.env`'s `REDIS_PERSISTENCE=true` crashes KATO run locally outside Docker (pydantic `Settings` forbids extra inputs) — both added to backlog, see Next Immediate Action above
  - **Archive**: `planning-docs/completed/features/2026-09-08-pattern-count-endpoint.md`
- **Redis OOM Fix: Metadata Migration to ClickHouse — FULLY COMPLETE** (2026-06-18): CORRECTNESS FIX + MIGRATION FINALIZATION
  - **Correctness Bug Fixed**: `kato.patterns_metadata` used `updated_at DateTime` (1-second resolution) as both `ReplacingMergeTree` version and `argMax` tiebreaker; same-second re-learns produced identical versions, silently losing emotive rolling-window merges. Fixed by adding `version UInt64` (`time.time_ns()`) as strictly-monotonic version column; `updated_at` downgraded to `DateTime64(3)` informational only.
  - **wait_for_async_insert**: Metadata writes switched to `wait_for_async_insert=1` (low-volume; gives immediate read-after-write visibility).
  - **Dual-write removal**: `MetadataRouter` simplified to ClickHouse-only; `MetadataMigrationConfig` and `metadata_migration` field removed from `settings.py`; `KATO_METADATA_*` env vars are now no-ops.
  - **Dead code removed**: `write_metadata`, `get_metadata`, `get_metadata_batch`, `write_precomputed_metrics_batch`, `get_precomputed_metrics_batch` removed from `redis_writer.py`; migration scripts `backfill_pattern_metadata.py` and `delete_moved_redis_keys.py` deleted; migration-specific tests `test_metadata_router.py` and `test_pattern_metadata_migration.py` deleted.
  - **Test suite updated**: `test_emotives_comprehensive.py` and `test_metadata_comprehensive.py` read metadata from ClickHouse as source of truth; `redis_has_metadata_keys` helper + assertion added confirming metadata absent from Redis.
  - **Test results**: 23 failed → 6 failed (445 → 446 passed); `test_emotive_persistence_with_rolling_window` now passes.
  - **Remaining 6 failures (pre-existing, NOT this work)**: 1 flaky async_insert visibility race (`test_bayesian_likelihood_equals_similarity`), 5 session-cleanup active-count + WebSocket event timeout tests.
  - **Archive**: `planning-docs/completed/features/2026-06-18-redis-clickhouse-metadata-migration-complete.md`
- **Relicense Apache 2.0 + Ownership Consolidation - COMPLETE** (2026-05-05): ADMINISTRATIVE
  - **License**: LGPL 2.1 replaced with Apache 2.0 (explicit patent grant, no linking ambiguity, broader corporate adoption)
  - **Ownership**: All "Intelligent Artifacts" references replaced with `Sevak Avakians <sevakavakians@gmail.com>` across 14 files (pyproject.toml, setup.py, Dockerfile OCI labels, Helm chart, docs)
  - **NOTICE** file created (Apache 2.0 §4(d)); git history not rewritten; per-file SPDX headers out of scope
  - **Commit**: `781cb18` on `main`; already-published artifacts retain prior license metadata
  - **Decision**: DECISION-013 in DECISIONS.md
- **Redis Rehydration & Persistence Fix - COMPLETE** (2026-04-13): BUG FIX + RESILIENCE
  - **Problem**: 250,850 patterns trained across 4 hierarchical nodes (node0_kato–node3_kato) returned zero prediction metrics because Redis (no persistence enabled) lost all metadata on restart while ClickHouse retained pattern data
  - **Fix 1**: Created `scripts/rehydrate_redis.py` — standalone script rebuilding all Redis metadata (frequency=1, symbol stats, global counters, pre-computed entropy/TF metrics) from ClickHouse; 250,850 patterns rehydrated in 51 seconds
  - **Fix 2**: Enabled `REDIS_PERSISTENCE=true` as default in `deployment/.env.example`; added data-loss warning comments to `config/redis.conf`
  - **Fix 3**: Added defensive frequency floor (floor at 1 with warning log) in `pattern_search.py` and `pattern_processor.py` — prevents silent metric cascading to zero when pattern exists in ClickHouse but has frequency=0 in Redis
  - **Verification**: 193,900 frequency keys, 31,029 symbols, pre-computed metrics confirmed present for node0_kato; Redis at 361MB of 8GB
  - **Files Modified**: `scripts/rehydrate_redis.py` (new), `deployment/.env.example`, `config/redis.conf`, `kato/searches/pattern_search.py`, `kato/workers/pattern_processor.py`
  - **Archive**: planning-docs/completed/features/2026-04-13-redis-rehydration-persistence-fix.md
- **Affinity-Weighted Pattern Matching - COMPLETE** (2026-03-31): NEW PREDICTION FEATURE
  - **What**: Opt-in weighted prediction metrics that use per-symbol affinity scores (from Symbol Affinity, 2026-03-27) to amplify predictions whose matched symbols carry stronger emotive weight. Activates when `affinity_emotive` is set in session config.
  - **Weight Formula**: `|affinity[s]| / (freq[s] + epsilon)` — frequency-normalized affinity magnitude
  - **New Prediction Fields**: `weighted_similarity`, `weighted_evidence`, `weighted_confidence`, `weighted_snr` (all `Optional`; `None` when feature inactive)
  - **Batch Reads**: `get_symbol_affinity_batch()` and `get_symbol_frequencies_batch()` added to `redis_writer.py` — single pipeline per call
  - **Integration**: Both `predictPattern` and `_predict_single_symbol_fast` paths updated; weighted metrics feed into `potential` ensemble ranking when active
  - **Tests**: 12 new unit tests; all 288 unit tests passing; zero regressions
  - **Files Modified**: `redis_writer.py`, `pattern_search.py`, `pattern_processor.py`, `prediction.py`, `session_config.py`, `test_affinity_weighted_matching.py` (new)
  - **Archive**: planning-docs/completed/features/2026-03-31-affinity-weighted-pattern-matching.md
- **Symbol Affinity Feature - COMPLETE** (2026-03-27): NEW API FEATURE
  - **What**: Per-symbol running cumulative sum of averaged emotive values, accumulated across every pattern that contains the symbol when learned with emotives. Monotonic (never decrements), unlike pattern emotives (rolling window).
  - **Storage**: Redis HASH at `{kb_id}:affinity:{symbol}` with atomic `HINCRBYFLOAT` updates — fully namespaced by `kb_id`
  - **Write Path**: `_update_symbol_affinity()` helper integrated into both branches of `learnPattern()` in `knowledge_base.py`
  - **Read Path**: `get_symbol_affinity()` and `get_all_symbol_affinities()` in `redis_writer.py`
  - **API**: `GET /symbols/affinity` (all) and `GET /symbols/{symbol}/affinity` (single)
  - **Tests**: 10/10 new tests passing (6 unit + 4 integration); 433/442 total; zero regressions
  - **Files Modified**: `redis_writer.py`, `knowledge_base.py`, `kato_ops.py`, `test_symbol_affinity.py`, `test_symbol_affinity_e2e.py`
  - **Archive**: planning-docs/completed/features/2026-03-27-symbol-affinity.md
- **Prediction Speed Optimizations Phases A-E COMPLETED** (2026-03-26): Six optimization phases implemented in the KATO prediction pipeline — zero regressions (430 passed, 2 pre-existing failures, 2 skipped).
  - **Phase A1**: Hoisted state-level entropy metrics before per-prediction loop (eliminates N-1 redundant calls)
  - **Phase A2**: Processor-level cache for `global_metadata`; removed dead MongoDB metadata fetch; derived `total_symbols` from cache length; invalidation on `learn()` and `clear_all_memory()`
  - **Phase B**: Pre-potential pruning after `causalBeliefAsync` — keeps top `max_predictions * 3` candidates before expensive metrics loop (2-3x fewer loop iterations for large sets)
  - **Phase C**: Vectorized cosine distance (C1), Bayesian posteriors (C2), potential calculation (C3) using numpy batch matrix ops
  - **Phase D**: `ThreadPoolExecutor` in `_predict_single_symbol_fast` for `extract_prediction_info` calls (threshold: >100 candidates; RapidFuzz releases GIL)
  - **Phase E**: `ProcessPoolExecutor` in `causalBeliefAsync` for true CPU parallelism (threshold: >500 candidates; module-level `_process_batch_worker` for picklability)
  - **Files Modified**: `kato/workers/pattern_processor.py` (A1, A2, B, C, D), `kato/searches/pattern_search.py` (E)
  - **Archive**: planning-docs/completed/optimizations/2026-03-26-prediction-speed-optimizations-phases-a-e.md
- **Test Suite Audit COMPLETED** (2026-03-25): 30 issues found across 5 categories — all resolved. Removed 3 misleading tests (MongoDB fallback, cache assert True, swallowed WebSocket), replaced 5 Redis mock tests with real integration tests, fixed 10+ assert True instances, removed all local env var manipulation from rapidfuzz tests, added 9 new regression tests (deferred flush, symbol batch, fast path, filter pipeline), cleaned up MongoDB references and pymongo dependency. 18 files modified (16 existing + 2 new), 3 tests deleted.
  - **Archive**: planning-docs/completed/refactors/2026-03-25-test-suite-audit.md
- **Database Bottleneck Fixes - THREE FIXES IMPLEMENTED** (2026-03-25): PENDING VERIFICATION
  - **Branch**: `perf/bottleneck-profiling`
  - **Decision**: DECISION-011 — fix in-place (no database migration); DuckDB/PostgreSQL/SQLite alternatives evaluated and rejected; 3-day fix vs 4-8 week migration
  - **Fix 1 (Deferred ClickHouse Flush)**: Removed premature `flush()` from `learnPattern()` hot path; added flush-before-predict guards; files: `knowledge_base.py`, `clickhouse_writer.py`, `pattern_processor.py`
  - **Fix 2 (Redis HASH Restructure)**: Replaced per-symbol individual keys with Redis HASH structures; eliminated O(N) SCAN; file: `redis_writer.py`
  - **Fix 3 (first_token ClickHouse Query)**: Replaced IN-clause with direct `first_token` column query; added chunked IN-clause to filter executor; files: `pattern_processor.py`, `executor.py`
  - **Expected Gains**: Learning 10/sec → 100+/sec; `get_all_symbols_batch` 2016ms → 5ms; single-symbol at 10K from failure → 5-10ms
  - **ADR**: `docs/architecture-decisions/ADR-002-database-bottleneck-fix-strategy.md`
  - **Next Step**: Run full test suite + benchmarks, merge to main, patch release
- **Performance Bottleneck Profiling Infrastructure - IMPLEMENTATION COMPLETE** (2026-03-24): READY FOR EXECUTION
  - **Branch**: `perf/bottleneck-profiling` (uncommitted)
  - **Approach**: Zero-invasive monkey-patching — no changes to `kato/` source code
  - **`benchmarks/profiler.py`**: `TimingCollector`, `PerfTimer` (time.perf_counter), `instrument_class/instance` utilities
  - **`benchmarks/data_generator.py`**: Zipf-distributed vocabulary; four scale tiers (100/1K/10K/100K); unique processor_id per tier for full DB isolation
  - **`benchmarks/test_database_latency.py`**: Raw ClickHouse, Redis, and computation (MinHash/SHA1/LCS) baselines
  - **`benchmarks/test_learning_path.py`**: Instrumented observe→learn path with per-operation breakdown
  - **`benchmarks/test_prediction_path.py`**: Single-symbol fast path + multi-symbol filter pipeline stage timing
  - **`benchmarks/bottleneck_runner.py`**: Orchestrator with JSON reporting, bottleneck ranking, and scaling analysis
  - **Next Step**: Commit branch, run `python benchmarks/bottleneck_runner.py`, analyze top-3 bottlenecks
  - **Archive**: planning-docs/completed/optimizations/2026-03-24-performance-bottleneck-profiling-infrastructure.md
- **TLS/HTTPS Support for All Database Connections - COMPLETE** (2026-03-20): SECURITY FEATURE + BUG FIX
  - **Bug Fixed**: `qdrant-client` library auto-enables HTTPS when `api_key` is passed, causing SSL failures against plain HTTP Qdrant; fixed by passing `https` explicitly from `QDRANT_HTTPS` env var to `QdrantClient`
  - **New Env Vars**: `QDRANT_HTTPS`, `CLICKHOUSE_SECURE`, `REDIS_TLS` — all default `false` (zero breaking changes)
  - **`settings.py`**: TLS bool fields added; `qdrant_url` and `redis_url` properties respect TLS flags
  - **`connection_manager.py`**: `CLICKHOUSE_SECURE` → `secure=True`; Redis host/port path → `ssl=True`; Redis URL path uses upgraded `redis_url`
  - **`vectordb_config.py`**: `https` field added to `QdrantConfig`; `get_url()` uses correct scheme
  - **Docker Compose**: TLS env vars wired in `docker-compose.yml` and `deployment/docker-compose.yml`
  - **`kato-manager.sh`**: `setup-auth` now generates TLS vars alongside credential vars
  - **Docs**: `.env.example`, `deployment/.env.example`, `docs/reference/configuration-vars.md` updated
  - **Decision**: Documented as DECISION-010 in DECISIONS.md
  - **Archive**: planning-docs/completed/features/2026-03-20-tls-https-database-connections.md
- **Performance Optimization Phase - 5 Optimizations - COMPLETE** (2026-03-19): FULLY VERIFIED
  - **Scope**: Five targeted optimizations across storage, search, and filter pipeline layers
  - **#2 Batch ClickHouse Inserts** (`clickhouse_writer.py`): Write buffer (default 50 rows); `write_pattern()` auto-flushes at threshold; `flush()` called from `learnPattern()` for immediate visibility; reduces ClickHouse round-trips from N to ceil(N/50)
  - **#3 Pipelined Redis Symbol Lookups** (`redis_writer.py`): Rewrote `get_all_symbols_batch()` with two-phase SCAN + pipeline; eliminates N*2 Redis round-trips, replaced with 1 pipelined call
  - **#4 Skip Double Similarity Computation** (`pattern_search.py`): `precomputed_similarity` parameter added to `extract_prediction_info()`; eliminates redundant O(n*m) LCS recomputation per candidate pattern; non-pipeline callers pass `None` for backward compatibility
  - **#6 Cache Symbol Table Across Predictions** (`aggregation_pipelines.py`, `pattern_processor.py`): Wired up existing `_symbol_cache`/`_cache_valid` in `OptimizedQueryManager`; `invalidate_caches()` called on `learn()`, `clear_all_memory()`, `delete_pattern()`; symbol table now loaded once per cache lifetime
  - **#7 Faster MinHash with xxhash** (`clickhouse_writer.py`, `minhash_filter.py`): xxhash added as optional dependency; opt-in via `MINHASH_HASH_FUNC=xxhash` env var (default: sha1 for backward compat); ~3-5x faster MinHash computation; tokens pre-encoded to bytes in batch
  - **Test Results**: 444 passed, 3 skipped, 2 pre-existing flaky failures — zero regressions
  - **Archive**: planning-docs/completed/optimizations/2026-03-19-performance-optimization-phase-5-optimizations.md
- **Documentation Audit + MongoDB Removal Phase A-D - COMPLETE** (2026-03-19): FULLY VERIFIED
  - **Scope**: Full audit of codebase and documentation; 21 discrepancies identified and resolved
  - **Code (Phases A-D)**: Deleted 2 dead files (`connection_pool.py`, `diagnose_test_patterns.py`); cleaned 7 source/test files to remove all pymongo imports and MongoDB fallback logic
  - **`kato/workers/pattern_processor.py`**: Default `KATO_ARCHITECTURE_MODE` changed from `'mongodb'` to `'hybrid'`; `update_pattern()` and `delete_pattern()` rewritten for ClickHouse + Redis; MongoDB fallback entirely removed (strict mode)
  - **`kato/config/database.py`**: Removed `MongoDBConfig`, `DatabaseManager`, and `mongodb_nodes` field
  - **Docs**: CHANGELOG.md gaps filled (v3.1.1–v3.4.0); README.md tags/counts/links fixed; ARCHITECTURE_DIAGRAM.md corrected (ports, columns, FilterPipelineExecutor added, stateless claim fixed); docs/MODE_SWITCHING.md MongoDB mode removed; docs/maintenance/known-issues.md updated to Mar 2026; CLAUDE.md corrected (bridge pattern, min sequence length, sort auto-toggle)
  - **Verification**: Zero pymongo imports in `kato/` or `tests/`; all modified Python files pass syntax check
  - **Archive**: planning-docs/completed/refactors/2026-03-19-documentation-audit-mongodb-removal-phase-a-d.md
- **Performance Optimization: Redis Batching, Logging, RapidFuzz, Import Cleanup - COMPLETE** (2026-03-19): FULLY VERIFIED
  - **Scope**: Multi-phase optimization pass targeting Redis round-trips, log overhead, object recomputation, fuzzy-match complexity, and module-load cost
  - **Phase 1A** (`redis_writer.py`): Added `get_metadata_batch()` and `batch_update_symbol_stats()`; updated `get_global_metadata()` to use `mget()` — collapses 3N GETs into 1 pipeline
  - **Phase 1B** (`knowledge_base.py`): Both `learnPattern()` paths now call `batch_update_symbol_stats()` — 50-symbol pattern drops from 150+ Redis calls to 1 pipeline
  - **Phase 1C** (`pattern_search.py`, `pattern_processor.py`): `_build_predictions_batch()` and `_predict_single_symbol_fast()` pre-load all candidate metadata in single batch calls
  - **Phase 2A** (`knowledge_base.py`): 10+ `logger.info()` calls in `learnPattern()` downgraded to `logger.debug()`
  - **Phase 2B** (`pattern.py`, `pattern_processor.py`): `@functools.cached_property` on `Pattern.flat_data`; used in `learn()` hot path
  - **Phase 2C** (`knowledge_base.py`): Removed duplicate in-function imports of `chain` and `Counter`
  - **Phase 3A** (`pattern_search.py`): Replaced O(n×m) manual fuzzy loop with RapidFuzz `process.extractOne()` batch API; manual fallback retained
  - **Phase 4A** (`clickhouse_writer.py`): Moved `MinHash` and `datetime` imports to module level
  - **Test Results**: 445 passed, 2 failed (pre-existing), 2 skipped — zero correctness regressions
  - **Archive**: planning-docs/completed/optimizations/2026-03-19-redis-batch-logging-rapidfuzz-optimizations.md
- **Optional Database Authentication - COMPLETE** (2026-03-17): FULLY DEPLOYED
  - **Scope**: All three databases (ClickHouse, Redis, Qdrant) now support optional auth via `.env`
  - **ClickHouse**: `CLICKHOUSE_USER` / `CLICKHOUSE_PASSWORD` fields in `settings.py`; `users.xml` uses `from_env` pattern
  - **Qdrant**: `QDRANT_API_KEY` field in `settings.py`; wired through `vectordb_config.py` and `connection_manager.py` to `QdrantClient`
  - **Scripts**: `kato-manager.sh` and `start.sh` now source `.env` and pass credentials to all CLI calls; new `setup-auth` command added to `kato-manager.sh`
  - **Backward Compatibility**: Zero changes required for existing deployments — absent credentials = no auth
  - **Files Modified**: 11 files across config, storage, Docker Compose, scripts, and env examples
  - **Archive**: planning-docs/completed/features/2026-03-17-optional-database-authentication.md
- **Qdrant Vector Storage: ID Format, Error Handling, and Test Coverage - COMPLETE** (2026-03-17): FULLY VERIFIED
  - **Bug 1**: `VCTR|sha1hash` names were passed directly to Qdrant, which rejects non-UUID IDs — fixed with deterministic `uuid.uuid5()` conversion at all Qdrant interaction points (add/search/update/delete)
  - **Bug 2**: `assignNewlyLearnedToWorkers()` did not check return values, silently swallowing storage failures — now checks returns and logs failures with context
  - **Bug 3**: `qdrant_store.py` exception messages omitted the exception type — now included for faster diagnosis
  - **New Tests**: Added `tests/tests/integration/test_vector_qdrant_storage.py` with 4 tests verifying actual Qdrant storage (not just symbolic matching): `test_vector_id_deterministic`, `test_vectors_stored_in_qdrant`, `test_search_returns_vctr_names`, `test_similarity_prediction_accuracy`
  - **Verification**: 4/4 new tests + 8/8 existing vector tests + full suite passing
  - **Archive**: planning-docs/completed/bugs/2026-03-17-qdrant-id-format-error-handling-tests.md
- **Vectors Never Persisted to Qdrant Bug Fix - COMPLETE** (2026-03-17): FULLY VERIFIED
  - **Primary Bug**: `assignNewlyLearnedToWorkers()` in `kato/searches/vector_search_engine.py` was a no-op - no code actually persisted vectors to Qdrant
  - **Secondary Bug**: `add_vector_sync` and `add_vectors_batch_sync` used `self._loop.run_until_complete()` directly, causing `RuntimeError: This event loop is already running` in FastAPI async contexts
  - **Symptom**: Digits classification tutorial (Section 11, kato-notebooks) produced 0% accuracy because Qdrant collection remained empty after training
  - **Fix**: (1) Replaced no-op with `self.engine.add_vector_sync(vector_obj)` calls; (2) Replaced bare `run_until_complete()` with `self._run_async_in_sync()` in sync wrapper methods
  - **Verification**: 8/8 vector integration tests passed, 441/443 full suite passed, 5/5 vector stress tests passed
  - **Archive**: planning-docs/completed/bugs/2026-03-17-vectors-never-persisted-to-qdrant.md
- **Deployment Network Auto-Creation Bug Fix - COMPLETE** (2025-12-17): ✅ OPERATIONS IMPROVEMENT
  - **Bug**: Users following Quick Start guide encountered "network declared as external, but could not be found" error
  - **Root Cause**: deployment/docker-compose.yml required pre-existing network (external: true)
  - **Fix**: Changed to auto-creating network with bridge driver and IPAM config (matches development setup)
  - **Impact**: First-time deployments now work without manual network creation step
  - **Verification**: Configuration validated, no changes required to kato-manager.sh
  - **Commit**: e0800cb - "fix: Auto-create Docker network in deployment package"
- **Filter Pipeline Default Changed to Empty - COMPLETE** (2025-11-29): ✅ BREAKING CHANGE IMPLEMENTATION
  - **Breaking Change**: Default filter pipeline changed from `["length", "jaccard", "rapidfuzz"]` to `[]`
  - **Rationale**: Maximum transparency and recall by default, explicit opt-in for filtering
  - **Code Changes**: 3 files updated (executor.py, configuration_service.py, pattern_processor.py)
  - **Documentation**: 4 files updated with new default and migration guidance
  - **Impact**: Production systems with >100K patterns should add explicit filter pipeline configuration
  - **Philosophy**: Aligns with KATO's transparency principle (no hidden filtering)
  - **Reversibility**: High - users can restore old behavior with explicit config
  - **Decision**: Documented as DECISION-008 in DECISIONS.md
- **Stateless Processor Refactor Phase 3 - COMPLETE** (2025-11-28): ✅ DOCUMENTATION CLEANUP
  - **MongoDB References Removed**: ~200 references across 24 documentation files
  - **Critical Files Updated**: HYBRID_ARCHITECTURE.md (4), KB_ID_ISOLATION.md (1), configuration-management.md (1)
  - **Batch Updates**: 21 additional files via general-purpose agent (~194 references)
  - **Verification**: All active documentation now reflects ClickHouse + Redis hybrid architecture
  - **Historical Preservation**: Archive and investigation directories intentionally preserved
  - **Duration**: 6 hours (within 4-6 hour estimate)
- **Stateless Processor Refactor Phase 2 Task 2.3 - COMPLETE** (2025-11-28): ✅ TEST SUITE MODERNIZATION
  - **Terminology Migration**: 47 "genes" references → "config" terminology
  - **Files Updated**: 8 test files completely updated
  - **Method Calls Updated**: All update_genes() → update_config(), get_genes() → get_config()
  - **Test Results**: All updated tests passing (7 of 8 in rolling_window_integration)
  - **Backward Compatibility**: Deprecated aliases maintained in fixtures
  - **Duration**: 3 hours (within 3-4 hour estimate)
- **Stateless Processor Refactor Phase 1 - 100% COMPLETE** (2025-11-26): ✅ CRITICAL ARCHITECTURE FIX
  - **Session Isolation Bug Fixed**: Stateful processor replaced with stateless design
  - **Locks Eliminated**: 0 processor locks remaining (sequential bottleneck removed)
  - **Performance**: 5-10x throughput improvement expected
  - **Files Modified**: 6 core files (memory_manager, kato_processor, sessions, processor_manager, observation_processor, pattern_operations)
  - **Commits**: 4 commits (3dc344d, 4a257d6, 8e74f94, ed436ab)
  - **Duration**: ~30 hours (within 30-44 hour estimate)
- **Comprehensive Documentation Project - 100% COMPLETE** (2025-11-13): ✅ ALL 6 PHASES DELIVERED
  - **Total Achievement**: 77 documentation files, ~707KB (~35,000+ lines)
  - Duration: 3 days (~50 hours total effort)
  - Quality: 100% production-ready with comprehensive cross-referencing
- **MongoDB Removal - COMPLETE** (2025-11-13): ✅ All MongoDB code, config, dependencies removed
  - Simplified architecture (2 databases instead of 3)
  - ClickHouse + Redis hybrid now mandatory
  - 374 lines removed net
- **Hybrid Architecture - COMPLETE** (2025-11-13): ✅ ClickHouse + Redis production-ready
  - 100-300x performance improvement
  - Billion-scale pattern storage
  - Complete node isolation via kb_id
