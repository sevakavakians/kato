# Project-Manager Trigger Log
*Event activation log for system tuning and optimization*

---

## 2026-09-09 - Task Completion + Architectural Decision (Cross-Worker WebSocket Broadcaster Fixed via Redis Pub/Sub)

**Trigger Type**: Primary — Task Completion (`kato/websocket/event_broadcaster.py` now fans events out across uvicorn workers via Redis pub/sub; committed as `ba3d194`) + Architectural Decision (DECISION-021: Redis pub/sub chosen over per-worker sticky routing and Redis Streams)
**Secondary**: Resolution of a previously-open human-alert item (`pending-updates.md` "Cross-Worker WebSocket Broadcaster Fix: Priority Decision Needed", filed alongside DECISION-020)

**Event**: `EventBroadcaster.broadcast_event` now publishes to a Redis pub/sub channel (`kato:ws_events`) that every uvicorn worker subscribes to at startup, delivering received events only to that worker's own local connections — closing the gap the DECISION-020 worker-topology tests had proven deterministic (3 delivery tests failing every run at `KATO_WORKERS` in {2, 4}). Those same tests now pass 15/15 across `KATO_WORKERS` in {1, 2, 4} with no changes to the tests themselves — only the product code changed. Full suite: 475 passed / 4 skipped / 0 failed, up from 453 passed / 5 failed.

**Key Findings**:
- A test suite built to manufacture a failure condition deterministically (DECISION-020's topology tests) pays off twice: once to confirm the bug with a stable, citable failure count, and again — with zero additional test-authoring effort — to prove the fix once one lands. The same 5 tests flip from "6 deterministic failures" to "15/15 passing" purely because the product code changed underneath them.
- Fire-and-forget notification semantics (no delivery guarantee beyond best-effort to currently-connected clients, no replay requirement) should be matched to the messaging primitive's actual guarantees rather than reached for the most feature-rich option available (Redis Streams was considered and rejected as overkill for exactly this reason).
- A human-alert item filed as "needs a priority decision before the next release" can be resolved same-day if the fix turns out to be straightforward and gets requested promptly — the alert did its job (surfacing the open question) without blocking or being ignored.

**Documentation Actions**:
- Created: `planning-docs/completed/features/2026-09-09-websocket-cross-worker-broadcaster-redis-pubsub.md`
- Updated: `planning-docs/DECISIONS.md` (DECISION-021), `planning-docs/SPRINT_BACKLOG.md`, `planning-docs/SESSION_STATE.md`, `planning-docs/README.md`, `planning-docs/project-manager/pending-updates.md` (item moved to Resolved), `planning-docs/project-manager/patterns.md`, `planning-docs/project-manager/maintenance-log.md`

**Agent Response Time**: Immediate
**Action Result**: All docs updated; the one previously-open alert for this issue is now resolved; DECISION-019's major-version-bump question remains the sole open pending-updates.md item

---

## 2026-09-09 - Task Completion + Architectural Decision + Knowledge Refinement + Human Alert (Worker-Topology Tests Replace Flaky Multi-Worker Tests, `worker_pid` Field Added)

**Trigger Type**: Primary — Task Completion (5 flaky/failing multi-worker tests replaced with 5 deterministic ones; new `worker_pid` field shipped) + Architectural Decision (DECISION-020: deterministic topology-testing strategy; confirms the cross-worker websocket broadcaster gap) + Knowledge Refinement (2026-06-18 "session delete does not decrement active-session count" backlog bug recharacterized as a TTL-cache test issue, not a product bug)
**Secondary**: Human Alert — cross-worker broadcaster fix priority flagged for review rather than decided; multi-worker backlog bug entry rewritten with deterministic (not intermittent) evidence

**Event**: `tests/tests/integration/test_worker_topology.py` was added, launching throwaway `kato:latest` containers at `KATO_WORKERS` in {1, 2, 4} and requiring test websocket clients to provably span ≥2 distinct worker PIDs before asserting cross-worker event delivery. This replaced 4 previously-flaky websocket event-delivery tests and `test_session_cleanup` (all of which had been intermittently failing against the shared 4-worker dev container for months). Result: `KATO_WORKERS=1` passes 5/5; `KATO_WORKERS=2`/`4` fail the 3 delivery tests **every run**, with exact missed worker PIDs named in the assertion. This confirms deterministically — not intermittently — that `kato/websocket/event_broadcaster.py`'s in-process `EventBroadcaster` cannot fan events out across uvicorn workers. Separately, the rewritten `test_session_cleanup` (which waits for the documented `/sessions/count` TTL cache to expire before reading) now passes, revealing that the 2026-06-18-filed "session delete does not decrement active-session count" bug was never a real product bug — the count converges correctly; the original test just read a cached value too early.

**Key Findings**:
- A test that manufactures its own failure condition (own container, own topology, proven worker-PID diversity) produces strictly better evidence than a test that happens to fail sometimes against a shared instance configured for unrelated reasons — it also stops costing verification time on every unrelated piece of work that has to re-confirm "yes, that's the known failure"
- A years-old backlog bug can turn out to be a mischaracterized test, not a product defect — this was only discovered by rewriting the test more rigorously (honoring a documented TTL cache) rather than continuing to assume the original symptom description was correct
- Confirming a bug deterministically (vs. leaving it as "known but intermittent") is valuable even when the fix itself is explicitly out of scope — it produces a stable, citable failure count and converts a vague "some multi-worker tests are flaky" into an exact, well-understood gap with named root cause and file
- A small, targeted product addition (`worker_pid` on two existing response shapes) can be the specific unlock that makes an otherwise-impossible-to-write-deterministically test class possible

**Documentation Actions**:
- Created: `planning-docs/completed/features/2026-09-09-worker-topology-tests-and-worker-pid.md`
- Updated: `planning-docs/DECISIONS.md` (new DECISION-020), `planning-docs/SPRINT_BACKLOG.md` (Recently Completed entry, Root-cause-#3 bug marked resolved, multi-worker bug entry rewritten, initiative verification step updated), `planning-docs/SESSION_STATE.md` (Current Task, new Previous Task block, Next Immediate Action items 2-3 rewritten), `planning-docs/README.md` (Test Coverage + Last Major Update), `planning-docs/project-manager/pending-updates.md` (new Open item), `planning-docs/project-manager/patterns.md` (new pattern entry)

**Agent Response Time**: Immediate
**Action Result**: All docs updated; 1 human alert raised in `pending-updates.md` (broadcaster-fix priority decision) — not resolved by the agent, per explicit instruction

---

## 2026-09-09 - Task Completion + Architectural Decision + Knowledge Refinement + Human Alert (anomalies/fuzzy_matches Breaking Field Split, Repeated-Symbol Bug Fixed, New Test File)

**Trigger Type**: Primary — Task Completion (new passing test file; repeated-symbol `missing`/`extras` under-reporting bug fixed) + Architectural Decision (DECISION-019: `anomalies` redefined as a flat deviation list, new `fuzzy_matches` field added — BREAKING) + Knowledge Refinement (deployment-container rebuild sequence; `run_tests.sh` single-path-argument limitation)
**Secondary**: Human Alert — release version bump for a breaking, uncommitted API change flagged for review rather than decided; 2 new backlog items filed (P3 `test_metrics_collection_after_requests` flakiness; P3 ops/docs gotcha)

**Event**: Three tests were added (`tests/tests/unit/test_hello_world_character_predictions.py`) to lock in character-level "hello world" prediction behavior. Building/verifying them surfaced a real bug: `missing`/`extras` used flat `in` membership against `matches`/`present`, so a repeated symbol's earlier occurrence masked a later unobserved occurrence (second `'o'` of "world" never reported missing for the perturbed observation "o wxld"). Fixed with `collections.Counter` multiset accounting. Separately, the user made an architectural decision (from three presented options) to redefine `anomalies` as a flat list of every deviating symbol and move the fuzzy-match detail records it used to hold into a new `fuzzy_matches` field — a breaking API change. Verification: 233 passed / 1 skipped across prediction and API suites; one pre-existing, unrelated failure (`test_metrics_collection_after_requests`, a `/metrics` multi-worker counter race) filed as a new backlog item, not a regression.

**Key Findings**:
- Flat `in` membership tests against a matches/present collection silently under-report when the checked value can legitimately repeat — this is a distinct bug class from a straightforward off-by-one or missing-branch bug, because it produces *plausible-looking, partially-correct* output (some but not all missing/extra instances reported) rather than an obvious failure
- A field's *type stability across configuration modes* is itself an API design concern worth an explicit decision record — `anomalies` silently changing shape (`list[str]` vs `list[dict]`) based on `use_token_matching` was rejected specifically because it makes generic prediction-consumer code unsafe to write without checking session config first
- Breaking API changes should be flagged for a human release/versioning decision even when the code-level change is otherwise complete and verified — completeness of implementation and correctness of scope/impact are separate judgment calls
- Two more operational facts were only discovered by attempting the "obvious" verification steps: `docker compose restart` looked sufficient but silently serves stale code because the live container belongs to a different compose project; `run_tests.sh`'s CLI silently truncates multi-path invocations to the first path

**Documentation Actions**:
- Created: `planning-docs/completed/features/2026-09-09-anomalies-fuzzy-matches-field-split.md`, `planning-docs/project-manager/pending-updates.md` (new file)
- Updated: `planning-docs/DECISIONS.md` (new DECISION-019), `planning-docs/SPRINT_BACKLOG.md` (Recently Completed entry + 2 new P3 items), `planning-docs/SESSION_STATE.md` (Current Task, new Previous Task block), `planning-docs/README.md` (Test Coverage + Last Major Update), `planning-docs/project-manager/patterns.md` (new pattern entry)

**Agent Response Time**: Immediate
**Action Result**: All docs updated; 1 human alert raised in `pending-updates.md` (release version bump decision) — not resolved by the agent, per explicit instruction

---

## 2026-09-09 - Task Completion + Architectural Decision + Knowledge Refinement (Metadata Sidecar Re-Learn Duplicate SELECT Eliminated, P2 Item Framing Corrected)

**Trigger Type**: Primary — Task Completion (root cause found and fixed: duplicate ClickHouse SELECT on the metadata sidecar re-learn path) + Architectural Decision (DECISION-018: the fix is round-trip elimination, not call-level batching) + Knowledge Refinement (corrects the fix-direction framing of the P2 "Metadata sidecar write path is un-batched" item filed earlier the same day — the proposed "batched call shape at `learnPattern`" was unachievable, not merely imprecise)
**Secondary**: 1 new backlog item filed (P3 test flakiness, unrelated to this fix, observed during its verification)

**Event**: The P2 metadata-sidecar item filed during the same-day configuration audit assumed a fix shape (batching multiple `learnPattern` calls' metadata writes together) that doesn't exist — `learn()` produces exactly one Pattern per call with no fan-out, and the one place multiple learns *do* happen in one request (`observe-sequence` with `learn_after_each=True`) has a strict sequential Redis dependency between iterations that forbids grouping them. Investigation found the real, achievable win: the re-learn path was issuing the same ClickHouse SELECT twice (`get_metadata()` fetched the full row then discarded the metric columns it needed later; `upsert_pattern_metadata` re-SELECTed to recover them). Threading the already-read row through a new `prev=` parameter collapsed this to one SELECT. Measured 2→1 SELECTs per re-learn at the unit level, 8→7.27 ClickHouse queries per re-learn end-to-end. Full suite: 452 passed / 4 skipped / 3 failed (best result this session).

**Key Findings**:
- A backlog item's proposed *fix direction*, not just its symptom/impact framing, can be architecturally impossible — this is distinct from (and discovered independently of) DECISION-017's same-day correction of the dead-`KATO_*`-env-names item's *impact* framing; here the direction itself ("batch the calls") had no valid target to batch
- The actually-fixable problem was hiding one layer deeper than the filed item described: not "no batching exists" but "an unnecessary duplicate read exists," found only by tracing the actual call path (`get_metadata()` → discard columns → `upsert_pattern_metadata` → re-fetch same columns)
- A design constraint worth over-documenting: a read that looks purely redundant (SELECT on a definitely-new pattern) can be silently load-bearing for a rare-but-real failure mode (Redis-loss-then-rehydrate) that has already occurred twice in this project — removing it without a replacement safeguard would be a regression invisible to normal testing
- Partial resolution is a valid outcome: the achievable half of a backlog item can be shipped and measured while the unachievable half is corrected (not deleted) and the remaining structural half is kept open rather than folded into "done"

**Documentation Actions**:
- Created: `planning-docs/completed/optimizations/2026-09-09-metadata-sidecar-relearn-duplicate-select-eliminated.md`
- Updated: `planning-docs/DECISIONS.md` (new DECISION-018), `planning-docs/SPRINT_BACKLOG.md` (backlog entry replaced/re-scoped, Recently Completed entry added, 1 new P3 item), `planning-docs/SESSION_STATE.md` (Current Task, new Previous Task block, backlog-bug item 4 rewritten), `planning-docs/README.md` (Test Coverage + Last Major Update)

**Agent Response Time**: Immediate
**Action Result**: All docs updated; no human alerts required

---

## 2026-09-09 - Task Completion + Architectural Decision + Knowledge Refinement (Configuration Audit, Wiring, and Dead-Parameter Removal)

**Trigger Type**: Primary — Task Completion (configuration audit: env wiring + dead-parameter removal + 2 bug fixes) + Architectural Decision (DECISION-017: delete `performance.batch_size` rather than wire it) + Knowledge Refinement (corrects the impact framing of the 2026-09-08 "dead `KATO_*` env names" P2 backlog item)
**Secondary**: 5 new backlog items filed (1 P2, 4 P3)

**Event**: A full audit of every `Settings` field and every documented/`KATO_*` env var (checked for both "does it bind" and "does the bound value have a consumer") resolved the P2 item logged 2026-09-08. The original item understated the problem: `KATO_BATCH_SIZE` was dead on two independent levels (broken binding **and** zero consumers on the field itself), so the originally-implied performance cost never existed. The audit also found KATO already batches ClickHouse writes server-side via `async_insert`, and that client-side batching (`DEFAULT_BATCH_SIZE=1`) is deliberately disabled per commit `f809a84` to avoid a per-worker orphaned-row bug — so `batch_size` was deleted rather than wired, to avoid reintroducing that bug. Two real bugs fixed along the way (`/concurrency` 4x undercount; 5 dead-but-documented env names now bound via `AliasChoices`), 5 params newly wired, and a large set of vestigial config surface deleted (29 files, +666/-1950). Full suite: 451 passed / 4 skipped / 4 failed (best result this session).

**Key Findings**:
- A backlog item's own "Symptom"/impact framing can itself be wrong, not just its root-cause diagnosis — this one implied a real performance cost from day one that a deeper audit showed never existed, because the value was never consumed regardless of whether the env var bound
- Correctness history matters when deciding whether to wire a dead parameter: `batch_size` looked like a plausible, purely additive fix (bind the env name, done) — but the surrounding git history (`f809a84`) showed that a *working* client-side batch value above 1 is actively dangerous under the current multi-worker architecture, making deletion the correct fix, not wiring
- When multiple dead env names are found in one audit, some can be safely aliased forward (5 names via `AliasChoices`, defaults preserved) while others should be deliberately left unaliased (`SORT` — name too generic/collision-prone) or deleted outright (`batch_size`, `vector_batch_size`, etc. — no consumer exists, wiring would add complexity/risk with zero benefit) — the fix is not one-size-fits-all across a batch of similar-looking findings
- New backlog items surfaced by the audit itself point at the *actual* remaining batching gap (metadata sidecar write path, un-batched at the `learnPattern` level) — distinguishing this from the deleted-not-wired `batch_size` knob was important so the real fix doesn't get mistaken for "just re-enable batch_size"

**Documentation Actions**:
- Created: `planning-docs/completed/refactors/2026-09-09-configuration-audit-wiring-dead-parameter-removal.md`
- Updated: `planning-docs/DECISIONS.md` (new DECISION-017)
- Updated: `planning-docs/SPRINT_BACKLOG.md` (removed the inaccurate P2 item from Backlog, new Recently Completed entry with corrected understanding, 5 new backlog items added)
- Updated: `planning-docs/SESSION_STATE.md` (Current Task, new Previous Task block, Last Updated)
- Updated: `planning-docs/project-manager/patterns.md` (new pattern entry: symptom/impact framing can overstate a bug even when the root-cause diagnosis is later found to be incomplete)
- Updated: `planning-docs/project-manager/maintenance-log.md`
- Updated: `planning-docs/project-manager/triggers.md` (this entry)

---

## 2026-09-08 - Task Completion + Architectural Decision (`.env`/dotenv-settings Crash Bug Fixed — Root Cause Broader Than Originally Logged)

**Trigger Type**: Primary — Task Completion (bug fix) + Architectural Decision (DECISION-016: load `.env` via `os.environ` in `kato/__init__.py`, not pydantic-settings `env_file=`)
**Secondary**: New backlog item added (dead `KATO_*` env names); two incidental dependency-lock findings recorded

**Event**: A P2 bug originally logged as `.env`'s `REDIS_PERSISTENCE=true` crashing a locally-run (non-Docker) KATO server was fixed. Investigation found the actual root cause was systemic: `Settings.model_config`'s `env_file='.env'` plus inherited `extra='forbid'` caused pydantic-settings' dotenv loader to forward every unmatched `.env` key onto the model, crashing on nearly all of them (not just `REDIS_PERSISTENCE`) while silently swallowing a couple of others (`SERVICE_NAME`, `SESSION_TTL`) without effect. Fixed by loading `.env` into `os.environ` via a new `kato/env_loader.py`, called first thing in `kato/__init__.py`, instead of through pydantic-settings' `env_file` mechanism — `extra='forbid'` deliberately kept. Full suite improved from 446/2/6 baseline to 447/2/5 (remaining 5 are the known multi-worker backlog bug, unrelated).

**Key Findings**:
- The bug report named one symptom (`REDIS_PERSISTENCE`) of a mechanism that affected nearly the entire `.env` file — reproducing the actual crash and reading the real pydantic-settings error, rather than fixing the literal reported symptom, was necessary to find the true scope
- A fix scoped only to pydantic `Settings` would not have reached the several hot code paths that read `os.environ` directly and never go through pydantic at all (`kato/__init__.py` LOG_LEVEL, `pattern_processor.py` KATO_ARCHITECTURE_MODE, `kato_fastapi.py` SERVICE_NAME, `storage/*` REDIS_URL) — loading into `os.environ` itself was the only mechanism reaching all consumers uniformly
- `extra='forbid'` was deliberately kept on `Settings` even after removing `env_file=` — it still protects `KATO_CONFIG_FILE` YAML/JSON validation, an unrelated but real safety net
- Regenerating `requirements.lock` (needed because `python-dotenv` was promoted to explicit) as a side effect surfaced two unrelated pieces of drift: `xxhash` was declared but never actually installed (silent SHA-1 fallback for the documented `MINHASH_HASH_FUNC=xxhash` optimization), and `pymongo`/`dnspython` were still installed despite MongoDB's v3.0 removal
- A new P2 backlog bug was identified but NOT fixed: `json_schema_extra={'env': ...}` on `Settings` fields is a pydantic-v1 idiom silently ignored by pydantic-settings v2, so `docker-compose.yml`'s `KATO_BATCH_SIZE=10000` has no effect

**Documentation Actions**:
- Created: `planning-docs/completed/bugs/2026-09-08-env-dotenv-settings-crash.md`
- Updated: `planning-docs/DECISIONS.md` (new DECISION-016)
- Updated: `planning-docs/SPRINT_BACKLOG.md` (removed fixed bug from Backlog, new Recently Completed entry, new P2 backlog item for dead `KATO_*` env names)
- Updated: `planning-docs/SESSION_STATE.md` (Current Task, new Previous Task block, Next Immediate Action renumbered with new item, new Recent Achievements entry, Last Updated)
- Updated: `planning-docs/README.md` (Last Major Update refreshed, Performance line corrected for the `xxhash` finding)
- Updated: `planning-docs/project-manager/patterns.md` (two new pattern entries: narrow-report-vs-systemic-cause, stale-lock-file discovery)
- Updated: `planning-docs/project-manager/maintenance-log.md`
- Updated: `planning-docs/project-manager/triggers.md` (this entry)

---

## 2026-09-08 - Task Completion + Knowledge Refinement (start.sh clean-data ClickHouse No-Op Fixed; Local Test Data Purged; Persistence Claim Corrected)

**Trigger Type**: Primary — Task Completion (bug fix: `start.sh clean-data` ClickHouse no-op) + Knowledge Refinement (an earlier same-day claim that Redis persistence was disabled was wrong; propagated to 3 planning-doc locations, all corrected)
**Secondary**: Maintenance action (full local test-data purge, user-directed)

**Event**: `./start.sh clean-data`'s ClickHouse step targeted `default.patterns_data` instead of `kato.patterns_data`, so it silently no-opped every time it ran while unconditionally reporting success — Redis and Qdrant genuinely cleared, ClickHouse never did. Fixed with a `TRUNCATE`-loop over the four real tables in `kato.*`. Verified end-to-end, then used (plus manual confirmation) to purge all local test data after the user confirmed none of it was production data — which also closed out a separate open question about recovering pre-flush Redis metadata. Verification work surfaced that an earlier same-day claim ("no Redis persistence enabled by default") was factually wrong and had propagated into three planning-doc locations.

**Key Findings**:
- `IF EXISTS` + suppressed stderr (`2>/dev/null`) combined to make a wrong-database DROP indistinguishable from success — the command's own success message was unconditional, so the no-op was invisible for as long as the bug existed
- Only `patterns_data` was ever targeted by the old code; `patterns_metadata`, `lsh_buckets`, and `pattern_stats` were never referenced regardless of database
- `REDIS_PERSISTENCE=true` is and has been set in `.env`/`deployment/.env` since the 2026-04-13 Redis Rehydration & Persistence Fix — persistence was never disabled today; the earlier-in-the-day claim to the contrary was incorrect and has now been corrected everywhere it appeared
- Persistence protects against restarts/crashes, not against explicit deletion commands (`FLUSHALL`, `DROP`, `TRUNCATE`) — an intentional destructive command gets durably persisted too, which is why persistence status was never actually relevant to either FLUSHALL data-loss risk discussed today

**Documentation Actions**:
- Created: `planning-docs/completed/bugs/2026-09-08-start-sh-clean-data-clickhouse-noop.md`
- Updated: `planning-docs/SPRINT_BACKLOG.md` (new Recently Completed entry)
- Updated: `planning-docs/SESSION_STATE.md` (Current Task, new Previous Task block, new Recent Achievements entry, persistence-claim correction, Last Updated)
- Updated: `planning-docs/README.md` (Last Major Update refreshed)
- Corrected: `planning-docs/completed/bugs/2026-09-08-conftest-redis-flushall-scoped-to-ephemeral-keys.md` (persistence claim)
- Corrected + extended: `planning-docs/project-manager/patterns.md` (persistence claim correction + new pattern entry for the clean-data bug)
- Updated: `planning-docs/project-manager/maintenance-log.md`
- Updated: `planning-docs/project-manager/triggers.md` (this entry)

---

## 2026-09-08 - Task Completion + New Task Creation (conftest.py Redis FLUSHALL Bug Fixed; New Multi-Worker Bug Characterized)

**Trigger Type**: Primary — Task Completion (P2 bug fix: conftest.py Redis FLUSHALL scoped to ephemeral keys) + New Task Creation (new P2 backlog bug: multi-worker websocket/concurrency issue)

**Event**: The P2 bug logged earlier today ("conftest.py unconditional Redis FLUSHALL destroys live metadata") is fixed — the fixture now scopes deletion to ephemeral session/STM keys only, with an opt-in full-flush escape hatch. Verification of the fix (full suite run, 6 failures) determined those 6 failures are pre-existing and caused by the container's `KATO_WORKERS=4` config, not this fix — a new P2 bug was characterized and added to backlog.

**Key Findings**:
- Scoped deletion is safe because durable pattern metadata is `kb_id`-namespaced in Redis and structurally cannot match the three ephemeral key patterns being deleted
- The 6 full-suite failures reproduce identically whether the fix is active or `KATO_TEST_REDIS_FLUSHALL=1` (old FLUSHALL) is used — proving the fix is not the cause
- 4 websocket event-delivery tests and `test_concurrent_session_modifications` fail specifically because `KATO_WORKERS=4` — in-process websocket publishing and concurrent session writes are not coordinated across workers; the same tests pass 7/7 under a single worker
- `test_session_cleanup`'s failure is a separate, already-tracked pre-existing bug (root cause #3, session-count accounting), not part of the new multi-worker finding

**Documentation Actions**:
- Created: `planning-docs/completed/bugs/2026-09-08-conftest-redis-flushall-scoped-to-ephemeral-keys.md`
- Updated: `planning-docs/SPRINT_BACKLOG.md` (bug moved from Backlog to Recently Completed; new multi-worker P2 bug added to Backlog)
- Updated: `planning-docs/SESSION_STATE.md` (Next Immediate Action renumbered, Recent Achievements prepended, Last Updated refreshed)
- Updated: `planning-docs/README.md` (Current System State refreshed)
- Updated: `planning-docs/project-manager/patterns.md`
- Updated: `planning-docs/project-manager/maintenance-log.md`
- Updated: `planning-docs/project-manager/triggers.md` (this entry)

---

## 2026-09-08 - Task Completion + Architectural Decision + Knowledge Refinement (Pattern Count Endpoint Complete)

**Trigger Type**: Primary — Task Completion (new `GET /patterns/count` endpoint) + Architectural Decision (DECISION-015: ClickHouse as authoritative count source) + Knowledge Refinement (`/status` response shape docs were wrong in 4 files, now corrected)

**Event**: New client-facing pattern-count capability delivered end-to-end (endpoint, schema, storage-layer wiring, client library, tests, docs). Two new P2 bugs discovered during verification and added to backlog; one existing P2 bug reconfirmed still reproducing.

**Key Findings**:
- `PatternOperations.get_pattern_count()` existed at the storage layer but was unreachable dead code — no endpoint or processor method called it
- `docs/reference/api/learning.md` documented a `GET /status` -> `processors.patterns_count` field that never existed in the codebase; same wrong shape also present in `health.md`, `monitoring.md`, `docs/developers/architecture.md` — all four corrected to the real shape (`total_processors`/`max_processors`/`eviction_ttl_seconds`/`processors[]`)
- Redis `total_unique_patterns` counter is unsuitable as a count source — no decrement path, drifts high after deletions — ClickHouse chosen as authoritative instead (DECISION-015)
- `tests/tests/conftest.py:24`'s unconditional Redis FLUSHALL is a data-loss risk given no default Redis persistence — newly documented as P2 backlog bug
- `.env`'s `REDIS_PERSISTENCE=true` crashes a local non-Docker KATO server run via pydantic `Settings` strictness — newly documented as P2 backlog bug
- Session-cleanup active-count bug (pre-existing, root cause #3) reconfirmed still reproducing in isolation even against a freshly flushed Redis

**Documentation Actions**:
- Created: `planning-docs/completed/features/2026-09-08-pattern-count-endpoint.md`
- Updated: `planning-docs/DECISIONS.md` (DECISION-015 added)
- Updated: `planning-docs/SESSION_STATE.md` (Current Task, Previous Task, Recent Achievements, Next Immediate Action, Blockers)
- Updated: `planning-docs/SPRINT_BACKLOG.md` (two new P2 backlog bugs)
- Updated: `planning-docs/README.md` (Current System State refreshed)
- Updated: `planning-docs/project-manager/maintenance-log.md`
- Updated: `planning-docs/project-manager/triggers.md` (this entry)

---

## 2026-06-18 - Task Completion + Knowledge Refinement (Redis OOM Fix: All Phases Complete, Correctness Bug Fixed)

**Trigger Type**: Primary — Task Completion + Knowledge Refinement (ReplacingMergeTree same-second version-tie assumption corrected) + Architectural Decision Update (DECISION-014 COMPLETE)
**Event**: Migration fully complete. Dual-write scaffolding removed, ClickHouse sole metadata store. Version-tie correctness bug discovered and fixed (`updated_at DateTime` → `version UInt64 time.time_ns()`). Two pre-existing bugs documented in backlog (async_insert race, session delete active-count).

**Key Findings**:
- `ReplacingMergeTree(updated_at)` + `argMax(field, updated_at)` with 1-second resolution is unsafe for sub-second re-learns; `time.time_ns()` UInt64 version eliminates the ambiguity
- `test_emotive_persistence_with_rolling_window` was the canary: 2 emotives vs expected 4 under `KATO_METADATA_READ_FROM=clickhouse`
- `KATO_METADATA_*` env vars can now be removed from all deployment configs (code removed)
- 6 pre-existing failures remain (root cause #1: async_insert race; root cause #3: session accounting + WebSocket timeouts)
- Test improvement: 23 failed → 6 failed (445 → 446 passed)

**Documentation Actions**:
- Updated: `planning-docs/DECISIONS.md` (DECISION-014 status COMPLETE + finalization section)
- Updated: `planning-docs/initiatives/redis-oom-clickhouse-metadata-migration.md` (all phases COMPLETE, correctness fix, finalization summary)
- Updated: `planning-docs/SESSION_STATE.md` (no active task, migration to Previous Task, new bugs in Next Immediate Action, leading Recent Achievement)
- Updated: `planning-docs/SPRINT_BACKLOG.md` (active item removed, two new backlog bugs, Recently Completed entry)
- Created: `planning-docs/completed/features/2026-06-18-redis-clickhouse-metadata-migration-complete.md`
- Updated: `planning-docs/project-manager/maintenance-log.md`
- Updated: `planning-docs/project-manager/triggers.md` (this entry)

---

## 2026-05-22 - Milestone Completion (Redis OOM Fix: Phases 3/4/5 Validated in Staging)

**Trigger Type**: Primary — Milestone Completion + Knowledge Refinement (Pydantic v2 env-var assumption corrected)
**Event**: Phases 3 (Read-Verify), 4 (Read Cutover), and 5 (Stop Redis Writes) validated in staging (localhost). Critical bug found and fixed: `MetadataMigrationConfig` Pydantic v2 env-var silent ignore. Staging left at Phase 4 end-state: `DUAL_WRITE=true`, `READ_FROM=clickhouse`, `READ_VERIFY=false`.

**Key Findings**:
- Pydantic v2 silently ignores `json_schema_extra={'env': '...'}` — must use `validation_alias`
- Two regression tests added; quality gate count corrected from 11 to 13
- Zero mismatch warnings across all three phase verifications
- Cleanup dry-run validated (~8 keys); execution deferred
- OrbStack `HTTP_PROXY` interception patched via `deployment/docker-compose.override.yml`
- Test suite regression delta is within run-to-run variance (pre-existing async_insert flakiness)

**Documentation Actions**:
- Updated: `planning-docs/initiatives/redis-oom-clickhouse-metadata-migration.md` (status, Phase 3/4/5 rows, steady-state config block)
- Updated: `planning-docs/DECISIONS.md` (DECISION-014 staging validation note + Pydantic v2 bug record)
- Updated: `planning-docs/SESSION_STATE.md` (current task, quality gate count, next immediate action)
- Updated: `planning-docs/SPRINT_BACKLOG.md` (phase validation table, critical fix note, deployment note)
- Updated: `planning-docs/project-manager/maintenance-log.md`
- Updated: `planning-docs/project-manager/triggers.md` (this entry)

---

## 2026-05-20 - Milestone Completion (Redis OOM Fix: Phases 0/1/2/6 Implemented)

**Trigger Type**: Primary — Milestone Completion + Task Status Change
**Event**: Engineering implementation complete for Phases 0 (Schema), 1 (Dual Write + call-site rewiring), 2 (Backfill script), and 6 (Cleanup script). Quality gate: 11/11 unit tests passing in `test_metadata_router.py`.
**Remaining**: Phases 3–5 and 7 are operational steps only (env-var flips + monitoring — no code changes).

**Key New Artifacts**:
- `kato/storage/metadata_router.py` (NEW)
- `scripts/backfill_pattern_metadata.py` (NEW)
- `scripts/delete_moved_redis_keys.py` (NEW)
- `tests/tests/unit/test_metadata_router.py` (NEW — 11 tests, all pass)
- `tests/tests/integration/test_pattern_metadata_migration.py` (NEW — 3 tests, require live services)

**Documentation Actions**:
- Updated: `planning-docs/initiatives/redis-oom-clickhouse-metadata-migration.md` (status + implementation notes)
- Updated: `planning-docs/DECISIONS.md` (DECISION-014 status)
- Updated: `planning-docs/SESSION_STATE.md` (current task, next action)
- Updated: `planning-docs/SPRINT_BACKLOG.md` (active item reflects implemented state)
- Updated: `planning-docs/project-manager/maintenance-log.md`
- Updated: `planning-docs/project-manager/triggers.md` (this entry)

---

## 2026-05-20 - New Specifications (Redis OOM Fix: Per-Pattern Metadata Migration to ClickHouse)

**Trigger Type**: Primary — New Specifications + Architectural Decision + Context Switch
**Event**: Approved plan for moving six per-pattern Redis keys to new ClickHouse sidecar table `kato.patterns_metadata`
**Source**: User — plan file at `/Users/sevakavakians/.claude/plans/ultrathink-currently-kato-uses-peaceful-micali.md`

**Plan Summary**:
- Root cause: 7 Redis keys per pattern, never expiring, grow linearly with LTM; JSON blobs dominate memory
- Solution: Move 6 keys to `kato.patterns_metadata` (ReplacingMergeTree); frequency stays in Redis (INCR atomicity)
- Rejected: EmbeddedRocksDB — async-only INCR, table-wide TTL, no HASH/SET semantics, write-stall risk
- Rollout: 7 phases gated by KATO_METADATA_DUAL_WRITE / KATO_METADATA_READ_FROM / KATO_METADATA_READ_VERIFY
- Expected outcome: ~60–80% Redis memory reduction at 250k patterns; predict latency within ±20%

**Decision logged**: DECISION-014 in `planning-docs/DECISIONS.md`

**Documentation Actions**:
- Created: `planning-docs/initiatives/redis-oom-clickhouse-metadata-migration.md`
- Updated: `planning-docs/DECISIONS.md` (DECISION-014)
- Updated: `planning-docs/SESSION_STATE.md` (current task, next action)
- Updated: `planning-docs/SPRINT_BACKLOG.md` (new active item at top)
- Updated: `planning-docs/project-manager/maintenance-log.md`
- Updated: `planning-docs/project-manager/triggers.md` (this entry)

---

## 2026-04-20 - New Specifications (Multi-Worker Uvicorn + Concurrent Training Safety)

**Trigger Type**: Primary — New Specifications + Context Switch
**Event**: Approved implementation plan for multi-worker uvicorn support; prior distributed-lock draft rejected
**Source**: User — plan file at `/Users/sevakavakians/.claude/plans/ultrathink-enable-multi-worker-recursive-marble.md`

**Plan Summary**:
- Change 1: `KATO_WORKERS` env var wired into Dockerfile, both compose files, and kato-manager.sh `--workers N` flag
- Change 2: `DEFAULT_BATCH_SIZE=1` + ClickHouse `async_insert=1, wait_for_async_insert=1` — eliminates per-worker buffer orphan at finalize
- Change 3: SETNX gate in `learnPattern` + `write_metadata(frequency=None)` — closes duplicate row, double-increment, and SET-clobbers-INCR races

**Rejected approach noted**: Distributed session locks were in the prior draft. Explicitly out of scope — training never accesses the same session concurrently.

**Documentation Actions**:
- Updated: `planning-docs/SESSION_STATE.md` (current task, next action)
- Updated: `planning-docs/SPRINT_BACKLOG.md` (new active item at top)
- Updated: `planning-docs/project-manager/maintenance-log.md`
- Updated: `planning-docs/project-manager/triggers.md` (this entry)

---

## 2026-04-02 - Task Completion (Swagger/OpenAPI Documentation Fix — FULLY COMPLETED)

**Trigger Type**: Primary — Task Completion
**Event**: Swagger/OpenAPI documentation issues fixed; all 36 endpoints now have response_model=; version corrected; routing conflict resolved; deprecated endpoints marked
**Source**: Developer report — 5 new schema files, 28 new Pydantic models, route reordering, dynamic version import

**Fix Summary**:
- Route ordering: `GET /symbols/stats` moved above `GET /symbols/{symbol}/affinity` (FastAPI static-before-parameterized rule)
- Version: `kato_fastapi.py` and `health.py` import `__version__` from `kato` package (was hardcoded `"1.0.0"`)
- Deprecated: `/percept-data` and `/cognition-data` have `deprecated=True` in route decorator
- New schema files: `kato/api/schemas/root.py`, `health.py`, `monitoring.py`, `kato_ops.py`, `session_extra.py`
- 28 new Pydantic response models; `response_model=` wired to all 36 endpoints (was 8)

**Documentation Actions**:
- Created archive: `planning-docs/completed/features/2026-04-02-swagger-openapi-documentation-fix.md`
- Updated: `README.md`, `maintenance-log.md`, `triggers.md`

---

## 2026-03-31 - Task Completion (Affinity-Weighted Pattern Matching — FULLY COMPLETED)

**Trigger Type**: Primary — Task Completion
**Event**: Affinity-Weighted Pattern Matching implemented, 12/12 new unit tests passing, 288/288 total unit tests passing, zero regressions
**Source**: Developer report — opt-in weighted prediction metrics using per-symbol affinity scores

**Feature Summary**:
- `affinity_emotive` field added to `SessionConfiguration`; opt-in, zero behavioral change when unset
- Weight formula: `|affinity[s]| / (freq[s] + epsilon)` — frequency-normalized affinity magnitude per symbol
- New `Prediction` fields: `weighted_similarity`, `weighted_evidence`, `weighted_confidence`, `weighted_snr` (all Optional)
- Batch Redis reads: `get_symbol_affinity_batch()` and `get_symbol_frequencies_batch()` in `redis_writer.py`
- `_compute_affinity_weights()` added to `PatternProcessor`; wired into both `predictPattern` and `_predict_single_symbol_fast`
- `extract_prediction_info` in `pattern_search.py` extended with optional `weights` dict
- Weighted metrics feed into `potential` ensemble ranking when active

**Documentation Actions**:
- Created archive: `planning-docs/completed/features/2026-03-31-affinity-weighted-pattern-matching.md`
- Updated: `SESSION_STATE.md`, `README.md`, `maintenance-log.md`, `triggers.md`

---

## 2026-03-27 - Task Completion (Symbol Affinity — FULLY COMPLETED)

**Trigger Type**: Primary — Task Completion
**Event**: Symbol Affinity feature implemented, 10/10 tests passing, zero regressions
**Source**: Developer report — 433/442 total tests passing; 9 pre-existing failures unrelated

**Feature Summary**:
- Per-symbol running cumulative sum of averaged emotive values (monotonic, unlike rolling-window pattern emotives)
- Redis HASH storage at `{kb_id}:affinity:{symbol}` — atomic HINCRBYFLOAT, fully kb_id namespaced
- Write path: `_update_symbol_affinity()` in `knowledge_base.py` — integrated into both branches of `learnPattern()`
- Read path: `get_symbol_affinity()` and `get_all_symbol_affinities()` in `redis_writer.py`
- API: `GET /symbols/affinity` and `GET /symbols/{symbol}/affinity` in `kato_ops.py`
- New tests: `test_symbol_affinity.py` (6 unit) + `test_symbol_affinity_e2e.py` (4 integration)

**Files Updated by project-manager**:
- `planning-docs/completed/features/2026-03-27-symbol-affinity.md` (created)
- `planning-docs/SESSION_STATE.md` (Recent Achievements updated)
- `planning-docs/SPRINT_BACKLOG.md` (Recently Completed section updated)
- `planning-docs/project-manager/maintenance-log.md` (logged)
- `planning-docs/project-manager/triggers.md` (this entry)

---

## 2026-03-26 - Task Completion (Prediction Speed Optimizations — Phases A-E — FULLY COMPLETED)

**Trigger Type**: Primary — Task Completion
**Event**: Six prediction pipeline optimization phases implemented and verified — zero regressions
**Source**: Developer report — 430 passed, 2 pre-existing failures, 2 skipped

**Phase Summary**:
- Phase A1: Hoisted state-level entropy metrics before per-prediction loop
- Phase A2: Processor-level global_metadata cache; dead MongoDB fetch removed; total_symbols derived from cache; invalidation on learn/clear
- Phase B: Pre-potential top-K pruning (keeps max_predictions * 3) after causalBeliefAsync — 2-3x fewer loop iterations for large candidate sets
- Phase C: Vectorized cosine distance (C1), Bayesian posteriors (C2), potential calculation (C3) via numpy
- Phase D: ThreadPoolExecutor in _predict_single_symbol_fast (threshold >100; RapidFuzz GIL-releasing)
- Phase E: ProcessPoolExecutor in causalBeliefAsync (threshold >500; module-level _process_batch_worker for picklability)

**Files Modified**:
- `kato/workers/pattern_processor.py` (Phases A1, A2, B, C, D)
- `kato/searches/pattern_search.py` (Phase E)

**Documents Updated**:
- `planning-docs/completed/optimizations/2026-03-26-prediction-speed-optimizations-phases-a-e.md` (created)
- `planning-docs/SESSION_STATE.md` (Recent Achievements updated, timestamp refreshed)
- `planning-docs/SPRINT_BACKLOG.md` (added to Recently Completed)
- `planning-docs/README.md` (Performance line and Last Major Update refreshed)
- `planning-docs/project-manager/maintenance-log.md`
- `planning-docs/project-manager/triggers.md` (this entry)

**Agent Response Time**: Immediate

---

## 2026-03-25 - Task Completion (Test Suite Audit — Analysis AND Implementation FULLY COMPLETED)

**Trigger Type**: Primary — Task Completion
**Event**: Comprehensive Test Suite Audit fully completed — both analysis and implementation phases done
**Source**: Developer report — 30 issues found across 5 categories, all resolved; 18 files modified, 3 tests deleted, 5 mocks replaced with real integration tests, 9 regression tests added

**Details**:
- Category A (Misleading tests): 3 deleted — MongoDB fallback, cache assert True, swallowed WebSocket
- Category B (Broken assertions): 10+ assert True instances replaced with meaningful assertions
- Category C (Outdated references): MongoDB refs and pymongo dependency removed from test layer
- Category D (Missing regression tests): 9 new tests added covering deferred flush, symbol batch, fast path, filter pipeline
- Category E (Infrastructure): Local env var manipulation removed from rapidfuzz tests

**Documents Updated**:
- `planning-docs/completed/refactors/2026-03-25-test-suite-audit.md` (created)
- `planning-docs/SESSION_STATE.md` (Recent Achievements updated, timestamp refreshed)
- `planning-docs/SPRINT_BACKLOG.md` (added to Recently Completed)
- `planning-docs/project-manager/maintenance-log.md`
- `planning-docs/project-manager/triggers.md`

**Agent Response Time**: Immediate

---

## 2026-03-25 - Task Completion (Test Suite Audit — 5 Phases — prior entry)

**Trigger Type**: Primary — Task Completion
**Event**: Test Suite Audit completed across 5 phases
**Source**: Developer report — full audit and overhaul of test suite for correctness, coverage, and architecture alignment

**Phase Summary**:
- Phase 1: Misleading tests eliminated (MongoDB fallback, silent skips, bare assert True, debug code)
- Phase 2: Broken patterns fixed (assert True, over-permissive status codes, mock-heavy tests replaced with real integration tests)
- Phase 3: Outdated references removed (MongoDB/pymongo purged from test layer)
- Phase 4: 9 new regression tests added (deferred flush, symbol batch, fast path, filter pipeline config)
- Phase 5: Infrastructure hardened (hardcoded URLs → env vars)

**Documents Updated**:
- `planning-docs/completed/refactors/2026-03-25-test-suite-audit-complete.md` (created)
- `planning-docs/SESSION_STATE.md` (new Recent Achievement entry, timestamp updated)
- `planning-docs/README.md` (Test Coverage and Last Major Update lines refreshed)
- `planning-docs/project-manager/maintenance-log.md`
- `planning-docs/project-manager/triggers.md` (this entry)

**Agent Response Time**: Immediate

---

## 2026-03-25 - Architectural Decision + Implementation Progress (Database Bottleneck Fixes)

**Trigger Type**: Primary — Architectural Decision + Task Progress
**Event**: DECISION-011 made (in-place fixes selected over database migration); three fixes implemented on `perf/bottleneck-profiling`
**Source**: Developer report — DuckDB/PostgreSQL/SQLite alternatives evaluated and rejected; three targeted fixes for premature flush, Redis SCAN, and first_token query

**Decision Details**:
- Alternatives evaluated: DuckDB (embedded columnar), PostgreSQL (transactional RDBMS), SQLite (embedded relational)
- All rejected: 4-8 week migration scope vs 3-day targeted fix; bottlenecks are code patterns not database limitations
- Selected: In-place ClickHouse + Redis fixes

**Fix Summary**:
- Fix 1: Deferred ClickHouse flush — `knowledge_base.py`, `clickhouse_writer.py`, `pattern_processor.py`
- Fix 2: Redis HASH restructure — `redis_writer.py`
- Fix 3: first_token column query — `pattern_processor.py`, `executor.py`

**Documents Updated**:
- `planning-docs/DECISIONS.md` (DECISION-011 prepended, Last Updated 2026-03-25)
- `docs/architecture-decisions/ADR-002-database-bottleneck-fix-strategy.md` (created)
- `planning-docs/SESSION_STATE.md` (Recent Achievements new entry, Next Immediate Action updated, timestamp)
- `planning-docs/project-manager/maintenance-log.md`
- `planning-docs/project-manager/triggers.md`
- `planning-docs/project-manager/patterns.md`

**Agent Response Time**: Immediate

---

## 2026-03-24 - Task Completion (Optimization: Performance Bottleneck Profiling Infrastructure)

**Trigger Type**: Primary - Task Completion
**Event**: Profiling infrastructure implementation complete — 6 files on branch `perf/bottleneck-profiling`
**Source**: Developer report — benchmarks/profiler.py, data_generator.py, test_database_latency.py, test_learning_path.py, test_prediction_path.py, bottleneck_runner.py

**Details**:
- `benchmarks/profiler.py`: `TimingCollector`, `PerfTimer`, `instrument_class/instance`
- `benchmarks/data_generator.py`: Zipf vocabulary, 4 scale tiers, unique processor_id per tier
- `benchmarks/test_database_latency.py`: Raw ClickHouse / Redis / compute baselines
- `benchmarks/test_learning_path.py`: observe→learn path per-operation breakdown
- `benchmarks/test_prediction_path.py`: fast path + filter pipeline stage timing
- `benchmarks/bottleneck_runner.py`: JSON report, bottleneck ranking, scaling analysis

**Documents Updated**:
- Created `planning-docs/completed/optimizations/2026-03-24-performance-bottleneck-profiling-infrastructure.md`
- `planning-docs/SESSION_STATE.md` Recent Achievements (new entry at top), Next Immediate Action updated, Last Updated timestamp
- `planning-docs/project-manager/maintenance-log.md`
- `planning-docs/project-manager/triggers.md`
- `planning-docs/project-manager/patterns.md`

**Agent Response Time**: Immediate

---

## 2026-03-20 - Task Completion (Feature: TLS/HTTPS Support for All Database Connections)

**Trigger Type**: Primary - Task Completion + Architectural Decision
**Event**: Security feature implemented — TLS/HTTPS opt-in for ClickHouse, Redis, Qdrant; Qdrant HTTPS auto-enable bug fixed
**Source**: Developer report — triggered by discovering qdrant-client silently enables HTTPS when api_key is passed

**Details**:
- `kato/config/vectordb_config.py`: `QdrantConfig.https` field added; `get_url()` scheme updated
- `kato/config/settings.py`: `QDRANT_HTTPS`, `CLICKHOUSE_SECURE`, `REDIS_TLS` bool fields; `qdrant_url` and `redis_url` properties handle TLS
- `kato/storage/qdrant_store.py`: Explicit `https=` kwarg to `QdrantClient`
- `kato/storage/connection_manager.py`: TLS wired to all three clients
- `docker-compose.yml` + `deployment/docker-compose.yml`: TLS env vars added
- `deployment/kato-manager.sh`: `setup-auth` generates TLS vars
- `.env.example`, `deployment/.env.example`, `docs/reference/configuration-vars.md`: Updated

**Documents Updated**:
- Created `planning-docs/completed/features/2026-03-20-tls-https-database-connections.md`
- `planning-docs/SESSION_STATE.md` Recent Achievements (new entry at top), Last Updated timestamp
- `planning-docs/DECISIONS.md` (DECISION-010 added), Last Updated timestamp
- `planning-docs/project-manager/maintenance-log.md`
- `planning-docs/project-manager/triggers.md`
- `planning-docs/project-manager/patterns.md`

**Agent Response Time**: Immediate

---

## 2026-03-19 - Task Completion (Optimization: Performance Optimization Phase - 5 Optimizations)

**Trigger Type**: Primary - Task Completion
**Event**: Performance optimization pass completed — 5 optimizations across storage, search, and filter pipeline; 444 passed, 3 skipped, 2 pre-existing flaky failures; zero regressions
**Source**: Developer report — batch ClickHouse inserts (#2), pipelined Redis symbol lookups (#3), precomputed similarity (#4), symbol table cache (#6), xxhash MinHash (#7)

**Details**:
- `kato/storage/clickhouse_writer.py`: Write buffer (batch size 50); `flush()` method; `_prepare_row()` helper; xxhash support via `MINHASH_HASH_FUNC` env var
- `kato/storage/redis_writer.py`: `get_all_symbols_batch()` rewritten — SCAN phase + single pipeline phase
- `kato/searches/pattern_search.py`: `precomputed_similarity` parameter on `extract_prediction_info()`; `_process_with_rapidfuzz()` and `_process_batch_rapidfuzz()` updated
- `kato/storage/aggregation_pipelines.py`: `_symbol_cache`/`_cache_valid` wired into `OptimizedQueryManager.get_all_symbols_optimized()`
- `kato/workers/pattern_processor.py`: `invalidate_caches()` calls added to `learn()`, `clear_all_memory()`, `delete_pattern()`
- `kato/filters/minhash_filter.py`: xxhash support; tokens pre-encoded to bytes in batch
- `kato/informatics/knowledge_base.py`: `flush()` called after `write_pattern()`
- `requirements.txt`: xxhash added as optional dependency

**Documents Updated**:
- Created `planning-docs/completed/optimizations/2026-03-19-performance-optimization-phase-5-optimizations.md`
- `planning-docs/SESSION_STATE.md` Recent Achievements (new entry at top), Last Updated timestamp
- `planning-docs/README.md` Current System State (test count, performance description, last major update)
- `planning-docs/project-manager/maintenance-log.md`
- `planning-docs/project-manager/triggers.md`
- `planning-docs/project-manager/patterns.md`

**Agent Response Time**: Immediate
**Action Result**: All docs updated; no human alerts required

---

## 2026-03-19 - Task Completion (Refactor: Documentation Audit + MongoDB Removal Phase A-D)

**Trigger Type**: Primary - Task Completion + Knowledge Refinement
**Event**: Documentation audit completed — 21 discrepancies fixed, zero pymongo imports remaining
**Source**: Developer report — full audit pass covering source code, test fixtures, and 6 documentation files

**Details**:
- `kato/workers/pattern_processor.py`: `KATO_ARCHITECTURE_MODE` default → `'hybrid'`; MongoDB fallback path removed; `update_pattern()` / `delete_pattern()` use ClickHouse + Redis
- `kato/config/database.py`: `MongoDBConfig`, `DatabaseManager`, `mongodb_nodes` removed
- `kato/storage/aggregation_pipelines.py`, `kato/storage/pattern_cache.py`, `kato/gpu/encoder.py`: pymongo.Collection → duck-type alias
- `tests/tests/fixtures/cleanup_utils.py`: MongoDB cleanup → ClickHouse cleanup
- `tests/tests/gpu/conftest.py`: MongoDB fixtures → in-memory mock
- Deleted: `kato/resilience/connection_pool.py`, `scripts/diagnose_test_patterns.py`
- Docs corrected: CHANGELOG.md (v3.1.1–v3.4.0 entries added), README.md (tags/counts/links), ARCHITECTURE_DIAGRAM.md (ports, columns, FilterPipelineExecutor, stateless claim), docs/MODE_SWITCHING.md (MongoDB mode removed), docs/maintenance/known-issues.md (Mar 2026, updated counts), CLAUDE.md (bridge pattern, min sequence length, sort auto-toggle)

**Documents Updated**:
- Created `planning-docs/completed/refactors/2026-03-19-documentation-audit-mongodb-removal-phase-a-d.md`
- `planning-docs/SESSION_STATE.md` Recent Achievements (new entry at top)
- `planning-docs/README.md` Current System State
- `planning-docs/project-manager/maintenance-log.md`
- `planning-docs/project-manager/triggers.md`
- `planning-docs/project-manager/patterns.md`

**Agent Response Time**: Immediate
**Action Result**: All docs updated; no human alerts required

---

## 2026-03-19 - Task Completion (Optimization: Redis Batching, Logging, RapidFuzz, Import Cleanup)

**Trigger Type**: Primary - Task Completion + Performance Optimization
**Event**: Multi-phase performance optimization pass completed across learn and predict hot paths
**Source**: Developer report — 445 tests passing, zero correctness regressions

**Details**:
- `kato/storage/redis_writer.py`: `get_metadata_batch()`, `batch_update_symbol_stats()`, `mget()` in `get_global_metadata()`
- `kato/storage/knowledge_base.py`: Both `learnPattern()` paths use `batch_update_symbol_stats()`; 10+ `logger.info()` → `logger.debug()`; removed duplicate in-function imports
- `kato/searches/pattern_search.py`: `_build_predictions_batch()` batch metadata load; RapidFuzz `process.extractOne()` batch API
- `kato/workers/pattern_processor.py`: `_predict_single_symbol_fast()` batch metadata load; cached property usage
- `kato/models/pattern.py`: `@functools.cached_property` on `flat_data`
- `kato/storage/clickhouse_writer.py`: `MinHash` and `datetime` moved to module level

**Documents Updated**:
- Created `planning-docs/completed/optimizations/2026-03-19-redis-batch-logging-rapidfuzz-optimizations.md`
- `planning-docs/SESSION_STATE.md` Recent Achievements (new entry at top)
- `planning-docs/README.md` Current System State
- `planning-docs/project-manager/maintenance-log.md`
- `planning-docs/project-manager/triggers.md`
- `planning-docs/project-manager/patterns.md`

**Agent Response Time**: Immediate
**Action Result**: All docs updated; no human alerts required

---

## 2026-03-17 - Task Completion (Feature: Optional Database Authentication)

**Trigger Type**: Primary - Task Completion + Architectural Decision
**Event**: Optional authentication added for ClickHouse, Redis, and Qdrant via env vars
**Source**: Developer report — 11 files modified, fully backward compatible

**Details**:
- `kato/config/settings.py`: `CLICKHOUSE_USER`, `CLICKHOUSE_PASSWORD`, `QDRANT_API_KEY` fields added
- `kato/config/vectordb_config.py`: `api_key` added to `QdrantConfig`
- `kato/storage/connection_manager.py`: Auth credentials wired to ClickHouse and Qdrant clients
- `kato/storage/qdrant_store.py`: Passes `api_key` to `QdrantClient`
- `config/clickhouse/users.xml`: Uses `from_env` pattern for password injection
- `docker-compose.yml` + `deployment/docker-compose.yml`: Auth env vars, updated healthchecks
- `deployment/kato-manager.sh`: Sources `.env`, new `setup-auth` command, authenticated CLI calls
- `start.sh`: Sources `.env`, authenticated CLI calls
- `deployment/.env.example` + `.env.example`: Auth documentation added

**Documents Updated**:
- Created `planning-docs/completed/features/2026-03-17-optional-database-authentication.md`
- Added DECISION-009 to `planning-docs/DECISIONS.md`
- `planning-docs/SESSION_STATE.md` Recent Achievements (new entry at top)
- `planning-docs/project-manager/maintenance-log.md`
- `planning-docs/project-manager/triggers.md`

**Agent Response Time**: Immediate
**Action Result**: All docs updated; no human alerts required

---

## 2026-03-17 - Task Completion (Bug Fix: Qdrant ID Format, Error Handling, and Test Coverage)

**Trigger Type**: Primary - Task Completion
**Event**: Qdrant vector storage bug fix — ID format correction, error visibility improvements, and new integration test file
**Source**: Developer report — 4 new tests + 8 existing vector tests + full suite passing

**Details**:
- `VCTR|sha1hash` names replaced with deterministic `uuid.uuid5()` UUIDs at all Qdrant interaction points
- Original names stored in Qdrant payload for reverse mapping; search results still return `VCTR|hash` names
- `assignNewlyLearnedToWorkers()` now checks return values and logs failures explicitly
- `qdrant_store.py` exception messages now include exception type
- New test file: `tests/tests/integration/test_vector_qdrant_storage.py` (4 tests, all passing)

**Documents Updated**:
- Created `planning-docs/completed/bugs/2026-03-17-qdrant-id-format-error-handling-tests.md`
- `planning-docs/SESSION_STATE.md` Recent Achievements (new entry added at top)
- `planning-docs/project-manager/maintenance-log.md`
- `planning-docs/project-manager/triggers.md`

**Agent Response Time**: Immediate
**Action Result**: All docs updated; no human alerts required

---

## 2026-03-17 - Task Completion (Bug Fix Verified)

**Trigger Type**: Primary - Task Completion
**Event**: Vector persistence bug fully verified after secondary event loop fix
**Source**: Developer report — 8/8 vector integration tests, 441/443 full suite, 5/5 stress tests passing

**Details**:
- Primary issue: `assignNewlyLearnedToWorkers()` no-op in `vector_search_engine.py`
- Secondary issue: `RuntimeError: This event loop is already running` in async FastAPI context (bare `run_until_complete()` calls)
- Both issues resolved; Docker container rebuilt and restarted before verification

**Documents Updated**:
- `planning-docs/completed/bugs/2026-03-17-vectors-never-persisted-to-qdrant.md`
- `planning-docs/SESSION_STATE.md`
- `planning-docs/project-manager/maintenance-log.md`
- `planning-docs/project-manager/patterns.md`

**Agent Response Time**: Immediate
**Action Result**: All docs updated; no human alerts required

---

## 2026-03-17 - Task Completion (Bug Fix Archived, Pending Verification)

**Trigger Type**: Primary - Task Completion
**Event**: Initial vector persistence bug fix applied to `vector_search_engine.py`
**Source**: Developer report — `assignNewlyLearnedToWorkers()` replaced no-op with actual Qdrant write calls

**Documents Updated**:
- Created `planning-docs/completed/bugs/2026-03-17-vectors-never-persisted-to-qdrant.md`
- `planning-docs/SESSION_STATE.md` Recent Achievements

**Agent Response Time**: Immediate
**Action Result**: Archived with PENDING VERIFICATION status; verification required before closing
