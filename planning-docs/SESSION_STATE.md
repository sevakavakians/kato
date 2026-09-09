# SESSION_STATE.md - Current Development State
*Last Updated: 2026-09-09 (anomalies/fuzzy_matches breaking field split + repeated-symbol multiset bug fix + new hello-world character-prediction test file; DECISION-019; release version bump flagged, not decided)*

## Current Task
**No active task — anomalies/fuzzy_matches field split + repeated-symbol bug fix is COMPLETE (nothing committed yet; version-bump decision flagged, see `planning-docs/project-manager/pending-updates.md`). Pick next item from sprint backlog (Multi-Worker Uvicorn + Concurrent Training Safety is next queued).**

## Previous Task (context preserved)
**Anomalies/Fuzzy_Matches Field Split (Breaking) + Repeated-Symbol Multiset Fix + New Hello-World Character-Prediction Tests — COMPLETE (2026-09-09)**
- Status: COMPLETE — code, tests, and docs updated; NOT committed; release version bump NOT decided (flagged for human review)
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
- **Open, flagged for human review (not decided)**: this is a breaking API change; whether it warrants a major version bump if released has not been decided — see `planning-docs/project-manager/pending-updates.md`. Nothing from this work has been committed yet.

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
**Resume Multi-Worker Uvicorn + Concurrent Training Safety**

The configuration audit (env var wiring, dead-parameter removal) is complete. The next queued initiative is multi-worker uvicorn support (see SPRINT_BACKLOG.md for full plan). Known backlog bugs (all P2 unless noted, non-blocking):

1. **Bug: patterns_data async_insert visibility race (Root cause #1)** — P2
   - `knowledge_base.py:~413` `wait_for_async_insert=0` on patterns_data writes; no server-queue drain on the learn/predict hot path
   - Symptom: flaky "0 predictions" under load; `test_bayesian_likelihood_equals_similarity` passes in isolation but fails in full suite
   - Fix: add server-side queue drain or switch specific write to `wait_for_async_insert=1`

2. **Bug: session delete does not decrement active-session count (Root cause #3)** — P2
   - `test_session_cleanup` fails because global active-session counter is not decremented on delete
   - 5 tests also fail on WebSocket `session.created`/`session.destroyed` event timeouts (5s)
   - Confirmed still reproducing 2026-09-08 during Pattern Count Endpoint verification (fails in isolation even against a freshly flushed Redis)

3. **Bug: Multi-worker (`KATO_WORKERS=4`) breaks websocket event delivery and concurrent session modification consistency** — P2 (discovered 2026-09-08, characterized during conftest.py FLUSHALL bug fix verification)
   - Websocket events are published in-process only and are not fanned out across uvicorn workers — a client connected to one worker misses events published by another
   - `test_concurrent_session_modifications` loses half its concurrent writes (`assert 5 == 10`) — writes split across workers aren't consistently visible to each other
   - Evidence: same websocket tests passed 7/7 against a single-worker instance; fail only under the 4-worker container. Confirmed unrelated to the conftest.py FLUSHALL fix — identical failures reproduce with `KATO_TEST_REDIS_FLUSHALL=1` (old FLUSHALL behavior)
   - Overlaps with the "Multi-Worker Uvicorn + Concurrent Training Safety" initiative — see `planning-docs/SPRINT_BACKLOG.md`

4. **Follow-up: Metadata sidecar read-modify-write shape (structural fix — append-only emotives/metadata)** — P2 (discovered 2026-09-09 during configuration audit; re-scoped and partially resolved 2026-09-09)
   - Originally filed as needing "a batched call shape at the `learnPattern` level" — that framing was **wrong** and has been corrected (see DECISION-018): `learn()` produces exactly one Pattern per call with no fan-out, so there is no batch to form; the achievable fix is round-trip elimination, not call grouping
   - **Already fixed**: the re-learn path's duplicate ClickHouse SELECT is eliminated (2 → 1) — see `planning-docs/completed/optimizations/2026-09-09-metadata-sidecar-relearn-duplicate-select-eliminated.md`
   - **Still open**: the read-modify-write shape itself (why `upsert_pattern_metadata` must read before writing at all, and why it's forced onto blocking `wait_for_async_insert=1`). Structural fix is making emotives/metadata append-only — see `planning-docs/SPRINT_BACKLOG.md` "Follow-up: Metadata sidecar read-modify-write shape"

**Resolved 2026-09-09** (previously item 3 here): dead `KATO_*` env names via `json_schema_extra={'env': ...}` — see "Previous Task" above and `planning-docs/SPRINT_BACKLOG.md` Recently Completed. Corrected understanding: the impact was overstated (`batch_size` had zero consumers regardless of binding); `batch_size` was deleted rather than wired, other dead names were aliased forward.

## Blockers
**No active blockers** (backlog bugs above are P2, non-blocking)

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
