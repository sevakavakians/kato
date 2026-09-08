# Project-Manager Patterns Log
*Productivity insights, trend analysis, and assumption-to-reality mappings*

---

## Performance Optimization Patterns

### 2026-03-25 - Profiling-Driven Fix Scope Decision: Bottleneck Type Determines Remedy

**Pattern**: When profiling surfaces performance bottlenecks, the first question is whether the bottleneck is a code pattern error, a data structure mismatch, or a fundamental database limitation. The answer determines whether targeted fixes or full migration is warranted.

**Discovery Trigger**: After the 2026-03-24 benchmarking infrastructure identified three bottlenecks, the team evaluated DuckDB, PostgreSQL, and SQLite as ClickHouse replacements. Analysis revealed that none of the three bottlenecks were fundamental database limitations — all three were fixable code patterns.

**Assumption → Reality**:
- Assumed: poor performance might indicate the wrong database choice
- Reality: the bottlenecks (premature flush, O(N) SCAN, unindexed query path) exist independent of which database is used; they are code errors and data structure mismatches, not database limitations

**Bottleneck Classification Framework**:
1. **Code error** (e.g., calling flush() in a loop when write buffering already exists): fix the code, 1 day
2. **Data structure mismatch** (e.g., individual string keys where a HASH is correct): change the data structure, 1 day
3. **Query pattern** (e.g., full table scan when an indexed column is available): fix the query, 1 day
4. **Fundamental database limitation** (e.g., single-writer lock under concurrent writes): consider migration, 4-8 weeks

**Resolution Pattern**: Before evaluating database migrations, classify each bottleneck into one of the four categories above. Categories 1-3 are always faster to fix in-place. Only Category 4 justifies migration scope.

**Lesson**: Database migration is the most expensive remedy. It is rarely necessary unless the bottleneck is provably a fundamental limitation of the current database's architecture (e.g., write concurrency model, storage layout). Profiling data that shows slow queries is not by itself evidence for migration.

**Recurrence Risk**: Low — this framework is now documented. Future performance work should start with bottleneck classification before entertaining migration options.

**Time Savings**: 4-8 weeks (migration) → 3 days (targeted fixes) = ~30x faster time-to-resolution

---

## Performance Profiling Patterns

### 2026-03-24 - Monkey-Patching for Zero-Intrusion Production-Accurate Profiling

**Pattern**: When building a profiling infrastructure for an existing codebase, monkey-patching
live class methods is preferable to modifying source files. The instrumented code is byte-for-byte
identical to production; there is no risk of accidentally altering the behavior being measured.

**Implementation**: Wrap each target method with a closure that records `time.perf_counter()`
before and after the real call, appends the delta to a `TimingCollector`, then returns the
original result unchanged. A single `instrument_class(cls, collector)` utility can wrap all
public methods of a class in one call.

**When to Use**:
- When profiling must not alter production code (zero-diff requirement)
- When the profiling infrastructure must be disposable (no cleanup needed)
- When you want to benchmark the exact code that runs in Docker, not a modified version

**Limitation**: Monkey-patching does not capture C-extension internals (e.g., time inside
ClickHouse's own serialization). Measure at the Python call boundary and treat the delta as
the total round-trip including network + driver overhead.

**Scaling Analysis Convention**: Report scaling coefficient as `time_at_100K / time_at_100`.
Linear (100x) is expected; >100x flags super-linear algorithmic growth; <100x confirms
caching/batching is working. This ratio makes bottleneck reports actionable regardless of
absolute latency differences across machines.

---

## Security Patterns

### 2026-03-20 - Client Library Auth Flags Can Silently Change Transport Protocol

**Pattern**: Adding authentication to a client library call can trigger implicit behavior changes beyond just authentication. The `qdrant-client` library treats the presence of an `api_key` argument as a signal to auto-upgrade the connection to HTTPS, regardless of whether the server is running with TLS.

**Discovery Trigger**: SSL handshake failures appeared after DECISION-009 added `QDRANT_API_KEY` support. The connection worked without the key; setting the key caused SSL errors against a plain HTTP instance.

**Assumption → Reality**:
- Assumed: passing `api_key` to `QdrantClient` only affects the `Authorization` header
- Reality: `qdrant-client` also silently sets `https=True` when `api_key` is non-empty

**Resolution Pattern**: Always pass transport-layer parameters (e.g., `https`, `ssl`, `secure`) explicitly rather than relying on client library defaults. Any time a security credential is added to a driver call, audit the driver's documentation for implicit protocol-upgrade behavior.

**Lesson**: Auth and transport encryption are separate concerns. When adding credentials to a database client, verify that the library does not conflate the two. The safest pattern is to always pass both `api_key` and `https` explicitly from separate, independently-controlled env vars.

**Recurrence Risk**: Medium — other drivers (e.g., Elasticsearch, MongoDB Atlas) also have implicit TLS-on-auth behavior. Audit new driver integrations for this pattern.

---

## Documentation Correctness Patterns

### 2026-09-08 - Dead Storage-Layer Code Paired with Documentation for a Field That Never Existed

**Pattern**: A storage-layer method (`PatternOperations.get_pattern_count()`) was fully implemented but never called from any endpoint or processor method — pure dead code. Simultaneously, `docs/reference/api/learning.md` documented a `GET /status` -> `processors.patterns_count` response field that had never existed anywhere in the codebase. The two facts look related (both "about pattern counting") but were independent: the doc's fabricated field was not a stale reference to the dead method: they were unconnected. Wiring up the dead method into a new, correctly-scoped endpoint (`GET /patterns/count`) fixed the capability gap; separately, three other docs files (`health.md`, `monitoring.md`, `docs/developers/architecture.md`) turned out to have the exact same fabricated `/status` shape and needed independent correction.

**Discovery Trigger**: Implementing the client-facing count feature required checking what `/status` actually returns, which surfaced the doc/code mismatch.

**Assumption → Reality**:
- Assumed: `/status` returns `processors.patterns_count` and `processors.active_processors` (per docs)
- Reality: `/status` returns `total_processors`/`max_processors`/`eviction_ttl_seconds`/`processors[]` — no `patterns_count` field exists or ever existed there

**Resolution Pattern**: When a documented field/endpoint is needed for new work and turns out not to exist, grep the same claim across sibling docs (health/monitoring/architecture files often duplicate response-shape examples) rather than fixing only the file that triggered the discovery.

**Lesson**: Dead code and documentation drift are separate defect classes that often coexist without being causally linked. Finding one is a good trigger to check for the other, but don't assume they explain each other — verify each independently against the real code.

**Recurrence Risk**: Medium — any response-shape example duplicated across multiple reference docs is a drift risk each time the actual response shape changes. Consider a single source-of-truth schema doc referenced from the others instead of duplicating example JSON.

---

### 2026-03-19 - Documentation Drift During Multi-Phase Refactors

**Pattern**: After a large architectural change (e.g., MongoDB → ClickHouse + Redis), documentation across 20+ files is updated in batches. Version-tagged items (container image tags, test counts, port numbers, column names) and behavioral claims (stateless model, minimum input lengths, sort behavior) are the most common drift points because they are easy to miss in bulk find-replace passes.

**Discovery Trigger**: Systematic audit pass cataloguing every claim in README.md, ARCHITECTURE_DIAGRAM.md, CHANGELOG.md, CLAUDE.md, and operational docs against the actual running codebase.

**Assumption → Reality Mappings Found**:
- Assumed: container tags were `v2` in README — Reality: deployed images are `v3.4`
- Assumed: test count was `185` — Reality: test suite has grown to `445+`
- Assumed: processor is "pure stateless" — Reality: uses bridge pattern (instance exists, state passed as parameter)
- Assumed: minimum STM requirement is "2+ strings" — Reality: "1+ strings" triggers predictions
- Assumed: sort is always on — Reality: alphanumeric sort is configurable and auto-toggles
- Assumed: CHANGELOG covered all releases — Reality: gap existed from v3.0 to v3.4

**Resolution Pattern**: A dedicated audit pass comparing docs-as-written against code-as-deployed catches all of these. Key audit targets: (1) version numbers in quickstart examples, (2) test counts in status sections, (3) architectural claims in CLAUDE.md / ARCHITECTURE_DIAGRAM.md, (4) CHANGELOG completeness.

**Lesson**: Schedule a documentation audit pass after each minor or major version bump, not only after major architectural refactors. Version-tagged claims in docs rot faster than architectural descriptions.

**Recurrence Risk**: Medium — version tags and counts will drift again with the next performance or feature release unless the release checklist explicitly includes a docs-audit step.

---

## Optimization Patterns

### 2026-03-19 - Redis Round-Trip Batching on Hot Paths

**Pattern**: Individual Redis calls inside loops on learn/predict hot paths accumulate latency that far exceeds the cost of the logical work. A 50-symbol pattern was issuing 150+ sequential Redis round-trips where 1 pipeline suffices.

**Discovery Trigger**: Systematic audit of `learnPattern()` and prediction-build code paths.

**Resolution Pattern**: Introduce batch methods (`get_metadata_batch()`, `batch_update_symbol_stats()`) that collect all keys/values up-front and issue a single `pipeline()` execute. Pre-load all metadata before entering scoring loops rather than loading on demand.

**Lesson**: Any loop that calls Redis (or any networked store) per iteration should be treated as a candidate for pipeline batching. The boundary is: collect keys → single pipeline → distribute results.

**Complementary Gains**: Pairing pipeline batching with `@functools.cached_property` on hot computed attributes and module-level imports eliminates secondary CPU costs that become visible once network latency is removed.

**Recurrence Risk**: Low for existing paths (now batched). Medium for future features — any new loop touching Redis should default to pipeline pattern from the start.

---

### 2026-03-19 - Multi-Layer Optimization: Storage Buffer + Precomputed Scores + Cache + Optional Hash

**Pattern**: A second optimization pass on the same codebase surfaces a different tier of wins. After the first pass eliminated per-iteration Redis calls, the remaining costs were: (1) write amplification to ClickHouse on every `write_pattern()`, (2) redundant similarity recomputation inside prediction loops, (3) repeated symbol table loads across predictions, and (4) hash function overhead inside MinHash.

**Discovery Trigger**: Systematic audit of write path (`write_pattern()`), search loop (`extract_prediction_info()`), and cache infrastructure (`_symbol_cache`/`_cache_valid` already existed but was not wired up).

**Optimization Patterns Applied**:
1. **Write buffering**: Collect rows in memory, flush at threshold. ClickHouse benefits far more from batch inserts than per-row inserts. The explicit `flush()` call at `learnPattern()` ensures freshness without sacrificing batch efficiency.
2. **Precomputed intermediate values**: Pass already-computed scores across function boundaries rather than recomputing. Adding a `precomputed_similarity` parameter is low-risk and zero-overhead for callers that do not need it (pass `None`).
3. **Read-through cache with explicit invalidation**: When a resource changes infrequently (symbol table only changes on learn/delete), cache it and invalidate on the mutating operations. The cache infrastructure already existed — the missing piece was wiring invalidation to the mutating methods.
4. **Optional fast hash path**: SHA1 is cryptographically strong but unnecessarily slow for MinHash (which only needs uniform distribution, not collision resistance). Providing xxhash as an opt-in preserves backward compatibility while giving advanced deployments a ~3-5x hash speedup.

**Lesson**: After a batching pass, the next tier of gains usually comes from: (a) write buffering, (b) eliminating redundant recomputation of already-known values across call boundaries, (c) activating dormant cache infrastructure, and (d) replacing over-specified primitives (cryptographic hash where non-cryptographic suffices).

**Recurrence Risk**: Low for these specific paths. For future features: (a) always pass precomputed values across inner-loop call boundaries instead of recomputing, (b) check for unused cache fields before adding new caching infrastructure, (c) use non-cryptographic hashes for any similarity/bucketing use case.

---

## Bug Patterns

### 2026-09-08 - Test Infrastructure Data-Loss Risk Surfaced by Unrelated Feature Work

**Pattern**: While verifying a new endpoint, `tests/tests/conftest.py:24`'s unconditional `docker exec kato-redis redis-cli FLUSHALL` fired at test-session start and destroyed live Redis metadata (frequency, emotives, symbol affinity) that has no reliable reconstruction path per `scripts/rehydrate_redis.py`'s own documented limitations. This is the same underlying fragility — Redis metadata, once destroyed, has no exact reconstruction path — previously encountered in production in the 2026-04-13 Redis Rehydration & Persistence Fix (see `planning-docs/completed/features/2026-04-13-redis-rehydration-persistence-fix.md`, where persistence *was* off at the time and was subsequently turned on by default as part of that fix) but left unaddressed in test infrastructure, which still targets a live-named container (`kato-redis`) unconditionally.

**Discovery Trigger**: Running the local test suite during Pattern Count Endpoint verification.

**Assumption → Reality**:
- Assumed: test suite setup only affects an isolated/ephemeral test database
- Reality: `conftest.py` flushes whatever Redis is reachable at the well-known container name `kato-redis`, with no guard against that being a live/shared instance

**Resolution Pattern**: Treat any unconditional destructive operation in shared test fixtures (`FLUSHALL`, `DROP TABLE`, `rm -rf`) as a standing risk, not just at the time it was written. Persistence protects against restarts and crashes, not against explicit deletion commands — it cannot substitute for scoping destructive operations to what actually needs clearing.

**Lesson**: A previously-fixed production bug class (Redis metadata loss with no exact reconstruction path) can still be live in adjacent tooling (test fixtures) that was not in scope for the original fix, even after the original root cause was independently closed. When auditing for a specific bug class, check test/ops scripts alongside application code, and don't assume a related production fix also closed the risk elsewhere.

**Correction (2026-09-08)**: This entry originally stated the risk was "combined with no Redis persistence by default" and called it "the same underlying fragility (no Redis persistence)" as the 2026-04-13 incident — implying Redis persistence was currently disabled. That was wrong. `REDIS_PERSISTENCE=true` has been set in `.env` and `deployment/.env` since the April 2026 fix (confirmed unchanged; the running container has `--save "900 1" ...` plus `--appendonly yes`, `aof_enabled:1`). Persistence was never the missing safeguard here — persistence durably commits whatever state Redis is in, including a deliberately emptied one, so it offers no protection against an explicit `FLUSHALL`. The actual risk was always an unconditional destructive command with no scope-guard. Corrected during the `start.sh clean-data` bug fix session — see `planning-docs/completed/bugs/2026-09-08-start-sh-clean-data-clickhouse-noop.md`.

**Recurrence Risk**: ~~Medium~~ RESOLVED 2026-09-08 — `conftest.py` now scopes deletion to ephemeral keys only, with `KATO_TEST_REDIS_FLUSHALL=1` as an explicit opt-in for full-flush. See archive: `planning-docs/completed/bugs/2026-09-08-conftest-redis-flushall-scoped-to-ephemeral-keys.md`.

---

### 2026-09-08 - Fix Verified, Then a Second Bug Surfaced Behind the First (Multi-Worker Websocket/Concurrency)

**Pattern**: Fixing the conftest.py FLUSHALL data-loss bug required a full-suite regression run to verify no new failures were introduced. That run showed 6 failures — the same 6 that were already known/pre-existing. Rather than assume "pre-existing" without checking, the failures were re-run with the *old* FLUSHALL behavior (`KATO_TEST_REDIS_FLUSHALL=1`) restored, producing identical results — proving the fix was not the cause. Digging into *why* those 6 fail at all (not just confirming they're unrelated) surfaced a second, previously uncharacterized bug: the container's `KATO_WORKERS=4` config breaks websocket event fan-out and concurrent session write consistency across workers, because websocket publishing is in-process only and session writes aren't coordinated across workers.

**Discovery Trigger**: Comparing failure counts/identities between the fix and an old-behavior control run (`KATO_TEST_REDIS_FLUSHALL=1`), then noticing the failing tests were all either websocket-event or concurrent-write tests — a pattern pointing at worker count rather than Redis behavior. Confirmed by noting the same websocket tests passed 7/7 against an earlier single-worker run.

**Assumption → Reality**:
- Assumed: "6 pre-existing failures" (as already noted in `SESSION_STATE.md` from 2026-06-18) was a stable, already-understood baseline
- Reality: the failures had never been root-caused to a specific mechanism; the actual cause (`KATO_WORKERS=4` breaking in-process websocket fan-out and cross-worker write consistency) was only characterized now, and is itself a new actionable P2 bug rather than acceptable baseline noise

**Resolution Pattern**: When a fix's verification run shows failures that look "pre-existing," don't stop at "unrelated" — (1) prove it with a control run under the old behavior, and (2) root-cause the failure pattern itself if it hasn't been root-caused before. A previously-uncharacterized bug can be sitting inside a bucket of already-tolerated "known failures" indefinitely if nobody looks closer.

**Lesson**: "Pre-existing failure" is not the same as "understood failure." Multi-worker deployments (`KATO_WORKERS=N`) need in-process state (websocket subscriber lists, per-request session mutation) replaced with cross-worker-safe mechanisms (e.g., Redis pub/sub) — this is exactly the class of correctness gap the already-queued "Multi-Worker Uvicorn + Concurrent Training Safety" initiative exists to close.

**Recurrence Risk**: Medium until the multi-worker initiative lands — every test run against the `KATO_WORKERS=4` container will keep showing these failures. Tracked as a new P2 backlog bug in `planning-docs/SPRINT_BACKLOG.md`, explicitly scoped as in-scope for the queued multi-worker initiative.

---

### 2026-09-08 - Silent-Success Ops Command: Wrong Database Name, `IF EXISTS` Masked the Failure

**Pattern**: `./start.sh clean-data`'s ClickHouse step ran `DROP TABLE IF EXISTS default.patterns_data`, but KATO's pattern tables live in the `kato` database, not `default`. `IF EXISTS` made the DROP against a nonexistent table a silent success (no error, nothing to drop), and `2>/dev/null` would have hidden any error anyway. The script unconditionally printed "✓ All database data has been cleared!" regardless of whether anything was actually cleared, so the no-op was invisible — Redis and Qdrant genuinely cleared, giving the whole command an appearance of working.

**Discovery Trigger**: Investigating whether `clean-data` had ever actually cleared ClickHouse; confirmed via `system.tables` that only `kato.patterns_data` exists, never `default.patterns_data`.

**Assumption → Reality**:
- Assumed: `clean-data` fully resets local state across all three databases, as its help text and success message claim
- Reality: ClickHouse was never touched — every row in `patterns_data`, `patterns_metadata`, `lsh_buckets`, and `pattern_stats` persisted across every prior "clean-data" run; only `patterns_data` was even targeted (the other three tables were never referenced at all)

**Resolution Pattern**: `IF EXISTS`/`IF NOT EXISTS` guards are appropriate for idempotency, but combined with wrong-target names and suppressed stderr, they convert a hard failure into total silence. Any destructive ops command that prints an unconditional success message should either (a) check affected-row/object counts before declaring success, or (b) let real failures surface (no blanket stderr suppression) so a wrong-target mistake is visible the first time it's run.

**Lesson**: A command that "has always worked" (no errors, expected success message) is not evidence it does what its name says — verify against the actual data (row counts, `system.tables`), not against the absence of errors, especially for any command using `IF EXISTS`/`IF NOT EXISTS` plus suppressed stderr together.

**Recurrence Risk**: Low — fixed by switching to `TRUNCATE TABLE IF EXISTS kato.$table` for all four real tables in a loop, with `2>/dev/null` removed so future name/permission mismatches surface per-table warnings instead of silent success. See archive: `planning-docs/completed/bugs/2026-09-08-start-sh-clean-data-clickhouse-noop.md`.

---

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
