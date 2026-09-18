# Project-Manager Patterns Log
*Productivity insights, trend analysis, and assumption-to-reality mappings*

---

## Testing Strategy Patterns

### 2026-09-17 - Proving a Negative Against a Deprecated Lifecycle Hook Requires Rewriting the Guard Against Its Replacement, Not Just Updating Call Sites

**Pattern**: `test_late_registration_is_ignored` existed to prove a negative — that registering an error handler after the app has already dispatched once is silently ignored (the root cause the Remediation Pass 1 dead-error-handling bug fix, DECISION-030, depends on staying true). Migrating `kato/services/kato_fastapi.py` from `@app.on_event` to a `lifespan` context manager meant the mechanism the test needed to drive (Starlette snapshotting `app.exception_handlers` on first dispatch) is now reached through a different code path. The test was rewritten to drive the real `lifespan` context manager directly rather than just swapping `on_event` references for `lifespan` references inside the existing test scaffolding — the assertions themselves (a handler registered late gets no effect) were unchanged, only the mechanism used to reach "already dispatched once" changed.

**Discovery Trigger**: Routine deprecation-warning cleanup; the test needed updating anyway since it referenced `on_event` directly.

**Resolution Pattern**: When a test proves a negative that depends on framework lifecycle mechanics (here: Starlette's middleware-stack snapshot timing), and the lifecycle API changes, don't just search-and-replace the deprecated API name in the test — re-derive what actually has to happen (app dispatched once, snapshot taken) and drive that through the new mechanism directly. A negative-proof test that still imports the deprecated API can end up either not compiling, or worse, silently not exercising the real path anymore.

**Recurrence Risk**: Low-Medium — will recur for any other test coupled to a framework lifecycle hook (`on_event`, deprecated middleware ordering guarantees, etc.) whenever that framework's API surface changes.

---

### 2026-09-16 - Cross-Worker Nondeterminism Cannot Be Tested Through a Shared-Session HTTP Fixture; Test the Invariant as a Pure Function Instead

**Pattern**: A guard test for a prediction-ranking determinism fix was first written as an integration test using the standard `kato_fixture`, and it **passed against a deliberately reverted (buggy) build** — meaning it provided zero actual protection despite looking like a real regression test. Cause: `tests/tests/fixtures/kato_fixtures.py` constructs a single `requests.Session()` shared across a test's requests; HTTP keep-alive on that session pins every request to the same TCP connection, and a uvicorn/FastAPI worker process handles all requests received on a given connection — so the "cross-worker" nondeterminism (each process's `set` iterates pattern names in a different, per-process-randomized order) never had a chance to manifest, because the test only ever talked to one worker.

**Discovery Trigger**: The bug being guarded against — prediction ranking ties broken by unstable `set`/`asyncio.as_completed()` arrival order — was independently confirmed live (40 identical requests, 7 distinct orderings) before the guard test was written. When the first integration-test version of the guard was run against a manually-reverted build, it passed, which should have failed given the confirmed live bug — that contradiction is what surfaced the fixture's keep-alive pinning as the cause.

**Assumption → Reality**:
- Assumed: an integration test hitting the real HTTP API through the standard test fixture exercises the same code path (and the same multi-worker nondeterminism) that a real client hitting the deployed service would.
- Reality: the standard fixture's connection reuse silently collapses "the deployed service, potentially many workers" down to "one worker, deterministically," for the whole duration of any test using it — which is exactly the condition under which the bug being tested for does NOT manifest.

**Resolution Pattern**: When a bug's manifestation depends on cross-process/cross-worker variation (randomized `set`/dict iteration order per interpreter, `asyncio.as_completed()` timing, or anything else where two different worker processes can legitimately disagree), do not rely on an HTTP integration test through a connection-reusing fixture to exercise that variation — it structurally cannot, regardless of how many requests the test sends. Instead, extract the invariant into a pure function (here: `rank_predictions(predictions, metric, limit)`, tested directly with shuffled input orderings standing in for "whatever order a `set` or `as_completed()` might produce") and test that function's contract in isolation. The old, worthless integration-level guard was deleted rather than kept alongside the new one, to avoid a false sense of double coverage.

**Recurrence Risk**: Medium — any future bug involving multi-worker/multi-process nondeterminism (session/state races, cache incoherence across workers, anything keyed on `KATO_WORKERS>1`) is at risk of the same false-negative if a guard test is written against the shared-session HTTP fixture rather than as a targeted pure-function or fixture-level test that actually varies the condition being guarded against. When in doubt, ask "would this test still exercise both code paths if every request in the test landed on the exact same worker process?" — if the answer is no, the fixture is the wrong tool.

---

### 2026-09-10 - Session-Scoped Test Cleanup That Flushes Shared State Interferes With Any Concurrent User of That State

**Pattern**: `tests/tests/conftest.py`'s session-scoped autouse fixture deleted every `kato:session:*` Redis key at the start of each pytest invocation. In isolation this is harmless test hygiene. But Redis is shared infrastructure on the dev stack — a second overlapping pytest invocation, a deployment container being recreated mid-run, or a live client (a training notebook) all read/write the same `kato:session:*` keyspace. Running the full suite while a deployment container recreate and a topology-suite re-run were also in progress produced 4 failures: 1 connection-refused (from the container recreate itself) and 3 "sessions vanished mid-test" (the conftest fixture's blanket delete racing the other processes' live sessions). A rerun on a quiet stack passed cleanly (482/4/1xfail/0), confirming the failures were cross-process interference, not a regression.

**Discovery Trigger**: The user ran the full suite manually while another process (a deployment container recreate + topology-suite re-run) was concurrently active on the same Redis-backed stack; the resulting failures didn't reproduce on a subsequent quiet run.

**Assumption → Reality**:
- Assumed: a broad "clean slate" delete of all session-shaped keys at test-session start is safe because pytest owns the keyspace it's about to populate.
- Reality: the keyspace is shared with anything else pointed at the same Redis — other concurrent test runs, container lifecycle events, and live non-test clients. A blanket delete is only safe when the test run has exclusive use of that Redis instance, which is not guaranteed on a shared dev stack.

**Resolution Pattern**: Scope cleanup to what the test run itself created, not to the whole shared keyspace. New `tests/tests/fixtures/redis_test_cleanup.py`'s `clear_test_session_state()` deletes only sessions whose `node_id` starts with a recognized test prefix (`test`, `topology_`, `perf_`, `load_test`; overridable via `KATO_TEST_NODE_PREFIXES`), plus that session's node pointer, active-session-index entry, and `stm:events` stream — leaving `stm:global` and every other node's state untouched. `node` was deliberately excluded as a prefix since production nodes are `node0`..`node3` and would otherwise be swept up. A full-flush escape hatch (`KATO_TEST_REDIS_FLUSHALL=1`) remains for anyone running against a dedicated, non-shared test Redis. `test_multi_user_scenarios` was renamed `node_{i}` → `test_node_{i}` so its own nodes qualify for cleanup under the new rule. Committed `e951148`. Verified: new self-test plants one live-looking and one test-looking session and asserts only the latter is removed; 53 passed across session/error-handling/redis-session suites plus the self-test; 7 passed in the renamed multi-user file.

**Recurrence Risk**: Medium — this is the second time this project has hit "test cleanup is too broad for shared infrastructure" (see `test_suite_flushes_shared_redis` in the auto-memory index / the 2026-09-08 conftest FLUSHALL fix below, which scoped an earlier unconditional `FLUSHALL` down to ephemeral key patterns). The underlying operational rule is unchanged and still not enforced automatically: **never overlap two pytest runs, or a pytest run and a container recreate, on the same stack** — even prefix-scoped cleanup and the shared active-session index can still interfere between two concurrent test runs that both use test-shaped node ids.

---

### 2026-09-10 - Shared-Redis Global Counters Make Absolute-Delta Assertions Flaky; Assert on Your Own Keys or Truth-at-the-Same-Instant

**Pattern**: `test_session_count_converges_on_every_worker` asserted "global active-session count returns to baseline ± N" after creating and deleting N sessions of its own. This held in isolation but failed intermittently (4 failures, then 1 on rerun) immediately after the v5.0.2 deployment container restart, because the active-session index (Redis `SET kato:session:_active_index`) is a single shared counter/index across *every* KATO process on the stack — not just the test's own sessions. The deployment container's own expiry sweep removed other, unrelated short-TTL perf-run sessions during the exact window the test was polling, so the "before/after delta" the test computed included churn the test had no way to control or know about.

**Discovery Trigger**: Immediately after swapping the deployment stack's `docker-compose.override.yml` from the local `kato:latest` build to the released `ghcr.io/sevakavakians/kato:5.0.2` image (DECISION-027), the topology suite showed 4 failures on the first run and 1 on an immediate rerun, all in the same test, all shaped like "expected count to return to 6 after deleting 5, got 1" — a classic sign of a global counter racing something outside the test's control.

**Assumption → Reality**:
- Assumed: a global session-count endpoint (`/sessions/count`) returning to its pre-test baseline after the test cleans up its own sessions is a valid correctness check, since the test controls session creation/deletion itself.
- Reality: the count is shared mutable state across every process touching Redis on that host, including the deployment container's background expiry sweep and any concurrently running perf-test sessions with short TTLs. "Baseline ± delta from my own actions" is only true when nothing else is mutating the same counter during the measurement window — a condition a live deployment stack does not actually guarantee, even though a quiet CI-only environment usually does.

**Resolution Pattern**: For any test asserting on a value shared across processes/workers (a global count, a shared index, an aggregate cache), prefer assertions that are true regardless of unrelated concurrent activity: (a) assert *membership* of your own known ids in the shared structure, rather than an aggregate count delta, and (b) where an aggregate value genuinely must be checked, read all the interrelated values *at the same instant* (e.g., every worker's local count vs. the shared index's cardinality, in one snapshot) rather than comparing a "before" snapshot to an "after" snapshot separated by time in which other actors can mutate the shared state. Bounded retry to find a quiet window is an acceptable fallback when true instant-snapshot reads aren't available. Applied here: the test was rewritten to assert its own session ids are present/absent in the index (exact, churn-proof) and, separately, that every worker's `/sessions/count` equals the index cardinality read at the same instant, found via bounded retry. Committed as `61e16cd`; topology suite 18/18 afterwards. Event-delivery timeout was also raised 5s→10s after one timeout was observed during the container's CPU-heavy startup — a related but separate flakiness source worth noting for future startup-adjacent test runs.

**Recurrence Risk**: Medium — any future test that computes a shared/global counter's before/after delta (session counts, connection counts, queue depths, cache sizes) on a stack with other concurrently-running processes (other test suites, perf runs, production-like background sweeps) is susceptible to the same flakiness. Prefer own-id membership or same-instant cross-checks by default for shared counters; reserve absolute-delta assertions for state genuinely private to the test (e.g., a per-test-prefixed key namespace).

---

### 2026-09-10 - A Perf/Integrity Test That Finally Exercises the Real Target Workload Can Surface Latent Architectural Defects Sequential Suites Structurally Cannot Catch

**Pattern**: A sequential test suite — even a large, passing one (475 passed / 4 skipped / 0 failed) — cannot detect bugs that only manifest when two requests concurrently hit the *same* shared instance (here, one `KatoProcessor` per `node_id`). The one test using threads in this suite (`test_multi_user_scenarios`) used distinct nodes, so it never collided on a processor instance. It took a purpose-built perf test reusing the initiative's own target workload (several threads training on one node) to expose a deadlock that had been latent in the codebase since `52e9284` (2025-09-08) — roughly six months of runtime with no test ever exercising the failure condition.

**Discovery Trigger**: The "Multi-Worker Uvicorn + Concurrent Training Safety" initiative's Phase C throughput-verification test (`tests/tests/performance/test_multi_worker_throughput.py`) was written specifically to reproduce the notebook's real parallel-training shape (several threads, one node) as an in-repo stand-in. Running it for the first time immediately deadlocked the server — a blocking `multiprocessing.Lock` held across an `async`/`await` boundary in the observe path.

**Assumption → Reality**:
- Assumed: a 475/4/0 full-suite result plus deterministic multi-worker topology tests (websocket delivery, session-count convergence) meant the multi-worker story was essentially sound, modulo the already-known and already-decided same-session write-loss limitation (DECISION-024).
- Reality: none of the existing tests — including the topology suite built specifically for multi-worker correctness — exercised concurrent requests *within a single node_id*, which is exactly the shape production training workloads use. A green suite says nothing about concurrency shapes it never drives.

**Resolution Pattern**: When an initiative's stated target workload has a specific concurrency shape (here: N threads, 1 node), write the throughput/integrity test to reproduce that *exact* shape as early as possible, not as a final verification step — it can surface defects that no amount of additional unit/integration coverage in unrelated shapes would ever catch. Treat "the suite is green" and "the target workload has actually been exercised" as two separate claims.

**Recurrence Risk**: Medium — any initiative whose target concurrency shape isn't already covered by an existing deterministic test (the way `test_worker_topology.py` covers cross-worker delivery) should get a same-shape stress/perf test written and run *before* declaring the initiative verified, not after.

---

### 2026-09-10 - A Two-Option Human-Alert Can Come Back as "Both, Staged" Rather Than a Single Pick

**Pattern**: The deadlock blocker above was framed to the user as a binary choice — Option A (fast asyncio.Lock stopgap, still a lock) vs. Option B (Phase 1.6 lock-free refactor, larger scope, recommended). The user's actual answer was neither pick alone: "Do A as a stopgap now, then B" — sequencing both rather than selecting one. The framing correctly surfaced the tradeoff (speed vs. architectural correctness) but implicitly presented it as either/or.

**Discovery Trigger**: The decision came back from the user as an explicit two-step instruction rather than a single-letter answer to the `pending-updates.md` entry's "Suggested Action" list.

**Assumption → Reality**:
- Assumed: a "choose A or B" framing would produce a single chosen path, with the other option either dropped or deferred indefinitely to a future backlog item.
- Reality: for a production-breaking bug with a known-larger proper fix, the user preferred to unblock immediately with the smaller fix *and* commit to the larger fix as the very next task — not a someday item, not an either/or.

**Resolution Pattern**: When a human-alert presents a fast/narrow fix against a slower/architecturally-correct one for something already broken in a way that blocks other work, consider explicitly offering "do the narrow fix now as a stopgap, then the correct fix next" as a third option alongside the binary choice — it may better match what a high-intensity, ship-fast-then-do-it-right workflow actually wants. DECISION-025 records this as an explicit stopgap with the follow-on named as the *active* next task (not just a backlog line item), which is the documentation shape this kind of staged decision needs — a plain "Option A chosen" would have understated the intent to still do B.

**Recurrence Risk**: Medium — this project has already made a similar staged call once (see the multi-phase Multi-Worker Uvicorn initiative itself); future critical/blocking bugs with a fast-vs-correct tradeoff should probably be pre-framed with a staged option from the start rather than presenting a strict binary.

---

### 2026-09-09 - A Deterministic Bug-Reproduction Test Pays Off Twice: Confirmation, Then Free Fix Verification

**Pattern**: When a test suite is built specifically to manufacture the exact runtime condition needed to reproduce a bug on demand (rather than hoping to observe it intermittently), the investment pays off a second time, for free, when the fix lands — the same tests, unmodified, flip from deterministic failure to deterministic pass and constitute the fix's verification.

**Discovery Trigger**: `tests/tests/integration/test_worker_topology.py` (DECISION-020) was built same-day to prove the cross-worker WebSocket broadcaster gap deterministically (3 tests failing every run at `KATO_WORKERS` in {2, 4}, 0 failures at {1}) rather than relying on the previous 2-4 intermittent failures per full-suite run. Later the same day, once the Redis pub/sub fix (DECISION-021) landed, those exact same tests — no changes made to them — passed 15/15 across all three topologies, serving as the fix's primary evidence.

**Assumption → Reality**:
- Assumed: writing a rigorous reproduction test for a bug that "isn't being fixed right now" is scoped work whose payoff ends at confirmation.
- Reality: if the reproduction is deterministic and topology-parametrized (rather than a one-off repro script), it doubles as the regression test for whenever the fix does land — with zero additional authoring cost at fix time.

**Resolution Pattern**: When confirming a bug deterministically (even with no fix requested yet), prefer building the reproduction as a proper parametrized test in the permanent suite over a throwaway diagnostic script. Structure it so the "control" case (the topology/condition where the bug does NOT manifest) is also asserted — this is what makes the later fix's before/after comparison unambiguous.

**Recurrence Risk**: Low as a risk, high as an opportunity — this is a pattern worth repeating deliberately whenever a bug is confirmed-but-deferred rather than confirmed-and-fixed-immediately.

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

## Correctness / API Design Patterns

### 2026-09-09 - Flat Membership Tests Under-Report Repeated Symbols; Overloaded Fields Should Split Rather Than Type-Switch

**Pattern**: Two related but distinct lessons from the same day's work on `kato/representations/prediction.py`.

**(1) Multiset bugs hide behind "mostly correct" output.** `missing`/`extras` computed membership via a flat `in` test against `matches`/`present`. For a repeated symbol, this is wrong: an *earlier* occurrence satisfies the check for a *later* occurrence that was never actually observed. The bug was invisible in the common case (few repeats) and only surfaced when a new test deliberately exercised a repeated character ("hello world" has a repeated `'o'`; perturbing the second occurrence exposed the masking).

**(2) A field whose type depends on session config is a worse API than two consistently-typed fields.** `anomalies` held fuzzy-match detail dicts under character-level matching but (implicitly) nothing consistent under token-level matching. Rather than "fix" this by formalizing the mode-dependent type, the decision (DECISION-019) split it: `anomalies` becomes a flat `list[str]` always, and a new `fuzzy_matches` field carries the mode-specific detail. Consumers no longer need to know the session's matching mode to safely handle the field's shape.

**Discovery Trigger**: Writing `tests/tests/unit/test_hello_world_character_predictions.py` — a test that happened to include a repeated character in its learned pattern and then perturbed the repeated instance, which is exactly the condition a flat membership check gets wrong.

**Assumption → Reality**:
- Assumed: `in matches` is a correct way to ask "was this symbol observed"
- Reality: for a value that can appear multiple times in both the pattern and the observation, "was *this occurrence* observed" requires counting, not membership — `collections.Counter` (multiset) is the correct primitive

**Resolution Pattern**: Any time code asks "is X in this collection" where X is a symbol/token that can legitimately repeat, check whether occurrence-count matters to the caller's semantics. If it does (as with missing/extra accounting), use multiset (`Counter`) subtraction, not `in`. Separately: when a field's meaning already varies by configuration, prefer splitting it into two consistently-typed fields over formalizing the variation — write the two-vs-one-field trade-off into an explicit decision record even when it's "just" a field rename, because it's an API compatibility decision, not merely an implementation detail.

**Lesson**: A test that deliberately includes a repeated element ("hello world" as `character` events) is a cheap, high-value regression guard against multiset-shaped bugs. When writing tests for anything that touches match/observed accounting, deliberately include repeats — the common case (no repeats) gives multiset and membership logic identical output, so it never catches this bug class.

**Recurrence Risk**: Medium — anywhere else in the codebase that computes a "what wasn't observed" or "what was extra" set via `in`/set-difference against a sequence that can contain repeats (rather than a true set) is at risk of the same class of under-reporting. Worth an audit pass if similar accounting logic exists elsewhere (e.g., symbol frequency reconciliation).

---

## Documentation Correctness Patterns

### 2026-09-09 - A Backlog Item's Fix Direction, Not Just Its Symptom, Can Be Architecturally Impossible

**Pattern**: The P2 "Metadata sidecar write path is un-batched" item was filed same-day with a specific proposed fix: "needs a batched upsert call shape at the `learnPattern` level." The symptom (two blocking ClickHouse round trips per learn) was correctly diagnosed. The proposed *fix direction* was not — there is no batch to form. `pattern_processor.learn()` builds exactly one Pattern per call and never fans out, so nothing exists at the `learnPattern` level to group into a batch. This is a distinct failure mode from DECISION-017's same-day correction, which fixed an overstated *impact* claim (a dead field with zero consumers, implying a performance cost that never existed) — here the symptom and impact were both real, only the remedy was unreachable.

**Discovery Trigger**: Attempting the fix. Investigation into "how would batching actually work here" revealed the batch-forming premise didn't exist, which redirected the work toward the real, achievable win one layer deeper — a duplicate SELECT hiding inside the existing single-pattern write path.

**Assumption → Reality**:
- Assumed: the fix is architectural (change the call shape to batch multiple learns' metadata writes together)
- Reality: the fix is local (eliminate a redundant read inside the existing single-call path); the architectural batching premise was invalid — a per-request buffer can't exist (nothing to batch with) and a cross-request buffer reintroduces the exact per-worker-orphaned-row bug commit `f809a84` already removed

**Resolution Pattern**: When a filed item's "fix direction" line describes a specific mechanism (not just a goal), verify that mechanism is actually constructible before starting implementation — trace the actual call path end to end first. Here, tracing `get_metadata()` → discard columns → `upsert_pattern_metadata()` → re-fetch same columns surfaced the real, narrower, achievable fix.

**Lesson**: Filing a backlog item under load (mid-audit, multiple findings at once) can correctly identify a symptom while guessing wrong about the remedy. Treat a filed "fix direction" as a hypothesis to verify at implementation time, not a spec to execute — and when it turns out wrong, correct the record (here: DECISION-018, plus rewriting the backlog entry) rather than silently implementing something different under the old label.

**Recurrence Risk**: Medium — any backlog item filed by pattern-matching against a similar-looking prior fix (here: "just like the pattern-write batching that already exists via `async_insert`, do the same for metadata") is at risk of this if the two code paths don't actually share the same call shape.

---

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

### 2026-09-17 - A Duck-Typed `hasattr(obj, 'close')` Teardown Guard Silently Never Fired Because Neither Real Implementation Defines `close()`

**Pattern**: `kato_fastapi.py`'s shutdown sequence guarded session-manager teardown with `hasattr(session_manager, 'close')`, presumably written defensively so shutdown wouldn't crash if the manager didn't support cleanup. Neither concrete implementation (`RedisSessionManager`, the in-memory `SessionManager`) has ever defined `close()` — both define `shutdown()`. The guard was therefore always `False`, and teardown silently did nothing, every single time the process shut down — leaking the Redis connection pool and the session cleanup task on every restart, with no error, warning, or log line to indicate anything was wrong.

**Discovery Trigger**: Rewriting `@app.on_event` shutdown into a `lifespan` context manager for an unrelated deprecation-warning cleanup pass required reading the shutdown sequence closely enough to notice the guarded method name didn't match either class's actual API.

**Assumption → Reality**:
- Assumed: the `hasattr(...)` guard was a reasonable defensive check that degraded gracefully if a manager type didn't support explicit cleanup.
- Reality: it was checking for a method name that plain never existed on any implementation ever passed to it — not a graceful degradation, a permanent no-op silently masquerading as one.

**Resolution Pattern**: Call `shutdown()` (the method that actually exists) directly instead of guarding on `hasattr` for a method name that was never verified against the real implementations. Also switched from reading the manager via its lazy property to reading the private `_session_manager` attribute directly, so the shutdown path itself cannot *construct* a manager the process never used just by touching it during teardown. Verified the fix by driving the real ASGI lifespan protocol end-to-end and confirming the shutdown log now contains lines (`RedisSessionManager shutdown complete`, `Session manager shut down`) that had never appeared before, on any prior run.

**Recurrence Risk**: Medium — any `hasattr(obj, 'method_name')` duck-typing guard is only as good as someone having verified `method_name` actually exists on every real type that flows through it; it will pass code review looking "defensive" while doing nothing at all. Worth grepping for other `hasattr(..., '...')` teardown/cleanup guards in the codebase as a follow-up audit, since this exact shape (a guard that silently never fires) leaves no trace in logs or test failures — it was only found by reading the code, not by any test or runtime signal.

---

### 2026-09-09 - Two Independent Stale-Credential Failures Blocked a Release, and the Release Script's Operation Order Made the Failure Mode Worse Than a Clean Abort

**Pattern**: Releasing KATO v5.0.0 via `./container-manager.sh major` first failed on `GITHUB_PERSONAL_ACCESS_TOKEN` being an expired token in the running shell (GitHub API 401), and — separately, not as a symptom of the same cause — the macOS keychain's cached `ghcr.io` Docker credential was also dead (403 on push). Two unrelated stale-credential failures had to be found and fixed, not one. Compounding this: `container-manager.sh` does not perform its own registry login, and it pushes the tag + publishes the GitHub release **before** building and pushing the container image — so a registry-auth failure surfaces only after the release is already public, leaving a tagged, released version with no matching image on `ghcr.io`, rather than a clean pre-flight abort.

**Discovery Trigger**: Running the release script and hitting the auth failures in sequence — first the GitHub API call, then (after fixing that) the Docker push.

**Assumption → Reality**:
- Assumed: a single valid credential (or a single `source ~/.bash_profile`) would cover both GitHub API access and `ghcr.io` Docker registry access for the release
- Reality: these are two independently-cached credentials (shell env var vs. Docker/keychain credential store) that can go stale on different schedules; fixing one does not fix the other

**Resolution Pattern**: `source ~/.bash_profile` refreshed the shell's `GITHUB_PERSONAL_ACCESS_TOKEN` to a current token (scopes include `write:packages`); `docker login ghcr.io -u sevakavakians --password-stdin` then re-established the Docker registry credential. Both were required before `container-manager.sh` could complete successfully.

**Lesson**: Before invoking `container-manager.sh` (or any release tooling with a similar tag-then-build order), verify *both* GitHub API auth and `ghcr.io` Docker auth explicitly — don't assume one implies the other, and don't rely on the script to fail safely, since its release-artifacts-first ordering means a late-stage auth failure leaves a public release with no image. See DECISION-022 and `planning-docs/completed/features/2026-09-09-kato-v5.0.0-release.md` for the full release record.

**Recurrence Risk**: Medium — both credentials (PAT, Docker/keychain) can expire independently again on future releases; this project's release cadence is currently ad hoc (not scheduled), so credential expiry between releases is plausible. No permanent fix (e.g., a pre-flight auth-check step added to `container-manager.sh` itself) has been implemented — this is process knowledge only, not yet automated.

---

### 2026-09-10 - Release Wrapper's `set -e` Turned a Harmless Non-Interactive `source` Failure Into an Aborted Release, and a "COMPLETE" Planning-Doc Entry Turned Out to Be Uncommitted Code

**Pattern**: Two related process gaps surfaced releasing KATO v5.0.1, both in the same family as the 2026-09-09 credential incident above (release-wrapper environment assumptions breaking under real conditions):
1. The first v5.0.1 release attempt aborted immediately: `source ~/.bash_profile` returned non-zero when run from the non-interactive release shell, and the wrapper script used `set -e`, so the whole run exited before anything was bumped or tagged.
2. Separately, the DECISION-018 metadata-sidecar duplicate-SELECT fix had been logged **COMPLETE** in `SPRINT_BACKLOG.md`/`DECISIONS.md` on 2026-09-09 and even listed in v5.0.0's "What's Bundled" table — but the actual code change was never committed. It sat as uncommitted working-tree WIP (`M kato/informatics/knowledge_base.py`, `M kato/storage/metadata_router.py`) straight through the v5.0.0 release (coincidentally protected by the same `git stash push -u` that was meant to exclude a *different*, still-open piece of sidecar work) and was still sitting there a day later.

**Discovery Trigger**: (1) The release script exiting with no tag/bump applied on the first attempt, traced to the `source` command's non-zero exit under `set -e`. (2) Noticing `git status` still showed the two sidecar files modified against a clean `main`, one day after v5.0.0 was supposedly released with that fix bundled in.

**Assumption → Reality**:
- Assumed (1): `source ~/.bash_profile` behaves the same in a non-interactive release shell as it does interactively — succeeds silently.
- Reality (1): a guard clause (or similar) in the profile can make `source` return non-zero in a non-interactive context even though the environment variables it sets are still picked up correctly; under `set -e` that non-zero exit is fatal regardless of whether the sourcing "worked."
- Assumed (2): marking a task COMPLETE in planning docs (with a decision record and an archive entry) means the corresponding code is committed and will be included in the next release.
- Reality (2): planning-doc status and git commit status are tracked independently and can silently diverge — a "COMPLETE" fix can still be uncommitted WIP, and nothing in the release process cross-checks the two.

**Resolution Pattern**: (1) Re-ran with `source ~/.bash_profile || true` — safe because the goal was only to refresh environment variables, not to assert the source itself succeeded; the retry completed the release normally. (2) Committed the sidecar fix as `ca8e47a` and shipped it in v5.0.1 (patch bump, since it's behavior-preserving).

**Lesson**: For any release wrapper using `set -e`, audit every `source`d script for non-interactive-shell exit-code behavior — don't assume a script that "works" interactively is `set -e`-safe non-interactively; suppress with `|| true` for setup steps where only the side effect (env vars set) matters, not the exit code. Separately: a "COMPLETE" status in planning docs is a claim about the code, not a substitute for checking it — a `git status`/`git diff` pass against what the docs claim is shipped (done right before or right after a release) would have caught the uncommitted DECISION-018 fix a day earlier, before it was misreported as bundled into v5.0.0.

**Recurrence Risk**: Medium for both. (1) Any future addition to the release wrapper that sources another script non-interactively carries the same risk unless explicitly guarded. (2) This is now the second time in two consecutive releases that an assumption about release-wrapper/environment behavior caused a process gap (see the 2026-09-09 entry above) — worth watching for a third occurrence, at which point a permanent fix (e.g., a `git diff --stat` sanity check baked into the release process, and `|| true` applied proactively to every non-interactive `source` in release tooling) should be treated as due rather than optional. See DECISION-023 and `planning-docs/completed/features/2026-09-10-kato-v5.0.1-release.md` for the full release record.

---

### 2026-09-09 - Manufacture the Failure Condition Instead of Waiting to Observe It: Flaky-by-Topology Tests Fixed by Owning the Container

**Pattern**: Four websocket event-delivery tests plus `test_session_cleanup` had been intermittently failing for months against the one shared dev container (`KATO_WORKERS=4`), and every unrelated piece of work that day (anomalies/fuzzy_matches, metadata-sidecar, configuration-audit) had to separately re-confirm "yes, those are the known pre-existing failures, not caused by my change." The actual fix wasn't a smarter assertion or a longer timeout — it was making the test launch its own throwaway containers at each worker count and proving, per-connection, that the test client had landed on ≥2 distinct worker PIDs before asserting cross-worker behavior. This turned "sometimes fails, depending on which worker a websocket connection happens to land on" into "fails every single time, with the exact missed worker PIDs named in the assertion."

**Discovery Trigger**: Repeatedly having to dismiss the same 3-5 failures as "known, pre-existing, unrelated" during unrelated verification work made the actual cost of *not* having a deterministic reproduction visible — every dismissal required re-deriving the same evidence (single-worker passes, multi-worker fails) from scratch or citing an old archive note.

**Assumption → Reality**:
- Assumed: a test that depends on multi-worker behavior can only be as deterministic as the shared container's topology happens to allow at test-run time
- Reality: the test can own its own container lifecycle and topology entirely, making the "worker count" variable something the test controls and varies (1, 2, 4) rather than something it passively inherits — turning an environmental flake into a controlled experiment with a real single-worker control group

**Resolution Pattern**: When a bug is topology/environment-dependent (multi-worker, multi-process, timing-window, etc.) and only reproduces intermittently against a long-lived shared instance, consider whether the test can instead spin up its own instance(s) at the exact parameter values needed to force the condition — and verify the condition was actually achieved (here: parsing worker PIDs from the log, and proving client connections span ≥2 of them) rather than assuming the requested configuration took effect. This converts "randomly reproduces sometimes" into "reproduces every time," which is strictly more useful even when — especially when — the underlying bug isn't being fixed yet.

**Lesson**: A flaky test and a deterministic test of the same underlying condition are not equally informative even if the "known failure" conclusion is the same either way — the deterministic version gives an exact, stable failure count (here: 6, not "2-4 depending on the run") and stops costing verification time on every unrelated piece of work. This is also how a previously-uninvestigated backlog item (Root cause #3, "session delete does not decrement active-session count") turned out to be a mischaracterized test (reading a TTL-cached value too early) rather than a real product bug — writing a more rigorous test revealed the original test, not the product, was wrong.

**Recurrence Risk**: Low for this specific gap — see `planning-docs/completed/features/2026-09-09-worker-topology-tests-and-worker-pid.md`, DECISION-020. General risk (other topology/timing-dependent tests still asserting against the shared container rather than a controlled one) not separately tracked — noted here for awareness.

---

### 2026-09-09 - A Bug Report's Own Impact Framing Overstated the Problem (No Performance Was Ever Lost)

**Pattern**: A P2 backlog item logged 2026-09-08 described `KATO_BATCH_SIZE`'s dead `json_schema_extra={'env': ...}` binding with the symptom "container runs with `batch_size=1000` instead of `10000`" — phrasing that implied real throughput was being left on the table by the broken binding. A follow-up configuration audit found `settings.performance.batch_size` had **zero consumers anywhere** in the codebase. The binding really was broken (pydantic-v1 idiom, ignored by pydantic-settings v2) — but even a working binding would have changed nothing, because nothing ever read the resulting value. The root-cause diagnosis in the original report was correct as far as it went; its *impact* framing was not.

**Discovery Trigger**: A full configuration audit that checked every `Settings` field against two separate questions — "does the name bind" and "does the bound value have a consumer" — rather than stopping at the first (binding) question, which is what the original bug report had checked.

**Assumption → Reality**:
- Assumed (from the original report): fixing the binding would restore the intended `batch_size=10000` behavior and its associated performance benefit
- Reality: there was no performance benefit to restore — `batch_size` had never been read by any code path, at any point in its history (traced back to `f1c862d`, the commit that introduced the field with no consumer ever added)

**Resolution Pattern**: When auditing a "config value doesn't bind" bug, always check the second half of the chain too — does anything actually consume the value once bound — before writing (or accepting) a symptom description that implies a specific real-world impact. A broken binding on a field with no consumer has *zero* behavioral impact, not a degraded one; conflating "the binding is broken" with "therefore the intended behavior is being lost" produces an inaccurate severity/impact picture even when the technical root cause is correctly identified.

**Lesson**: "It's not wired up correctly" and "therefore it's not working as intended" are not the same claim — the second requires confirming intended behavior actually exists downstream of the wiring, not just that the wiring itself is broken. This is the same class of gap as the 2026-09-08 "narrowly-logged bug" entry below, but inverted: that one under-scoped the *cause*, this one over-scoped the *effect*.

**Recurrence Risk**: Low for this specific field (deleted, not wired — see DECISION-017, `planning-docs/DECISIONS.md`). General risk (future config-audit bug reports asserting impact without checking for a downstream consumer) not separately tracked — noted here for awareness.

---

### 2026-09-08 - A Narrowly-Logged Bug (One Crashing Env Var) Turned Out to Be a Systemic One (Nearly All of Them)

**Pattern**: A P2 bug was logged as `.env`'s `REDIS_PERSISTENCE=true` crashing a locally-run (non-Docker) KATO server. Investigating the actual crash mechanism — `Settings.model_config`'s `env_file='.env'` combined with inherited `extra='forbid'` — revealed that pydantic-settings' dotenv loader forwards *every* `.env` key it can't match onto the model, not just the one that happened to be reported first. Since `Settings` only declares 8 top-level fields and `.env` contains dozens of real leaf variable names, nearly every `.env` key crashed it; `REDIS_PERSISTENCE` was simply the alphabetically/positionally first one anyone hit and reported.

**Discovery Trigger**: Reproducing the reported crash and reading the actual pydantic-settings traceback/source (`DotEnvSettingsSource`) instead of assuming the fix was "add `REDIS_PERSISTENCE` as an ignored field" (the narrowest fix that would have satisfied the literal bug report).

**Assumption → Reality**:
- Assumed (from the bug report): one specific env var (`REDIS_PERSISTENCE`) was the problem
- Reality: the mechanism causing it (`env_file=` + `extra='forbid'`) affected essentially all of `.env`, and a couple of other names (`SERVICE_NAME`, `SESSION_TTL`) were being silently swallowed without ever taking effect, an even quieter failure than a crash

**Resolution Pattern**: When a bug report names one specific instance of a class of input (one env var, one file, one endpoint), check whether the reported instance is representative or just the first one someone happened to hit. Reproduce the actual failure and read the real error/traceback before scoping the fix — a fix scoped to the literal report (add `REDIS_PERSISTENCE` as a field) would have left the underlying mechanism, and every other real variable, still broken.

**Lesson**: "It crashes on X" bug reports for config/env-loading code deserve a check of *why X specifically* triggered it, not just *how to make X stop triggering it* — the failure surface for loader/validation code is often the entire input space, not the one value that happened to be logged. This is doubly true when the loader's `extra='forbid'`-style strictness means the *first* unrecognized key found aborts the whole load; a report from one such bug says nothing about how many other keys would also fail.

**Recurrence Risk**: Low for this specific mechanism — fixed by removing `env_file=` from `Settings.model_config` entirely (loading is now via `os.environ` in `kato/env_loader.py`, called from `kato/__init__.py`) and documenting in that module's docstring why `env_file=` must not be reintroduced. See archive: `planning-docs/completed/bugs/2026-09-08-env-dotenv-settings-crash.md`, decision: DECISION-016.

---

### 2026-09-08 - Stale Lock File Discovered as a Side Effect of an Unrelated Fix (`xxhash` Never Installed, `pymongo`/`dnspython` Never Removed)

**Pattern**: Regenerating `requirements.lock` as a routine step of the `.env`-loading fix (needed because `python-dotenv` was promoted from transitive to explicit) surfaced two pieces of unrelated drift that had been silently live for some time: `xxhash` was declared in `requirements.txt` but absent from `requirements.lock`, so it was never actually installed in the container — the `MINHASH_HASH_FUNC=xxhash` optimization had been silently falling back to SHA-1 the entire time it was documented as an active performance feature. Separately, `pymongo`/`dnspython` were still pinned in the lock file despite MongoDB being fully removed from the codebase in v3.0, and were confirmed still installed in the running container.

**Discovery Trigger**: Running `pip-compile` for an unrelated reason and diffing the regenerated lock file against the previous one.

**Assumption → Reality**:
- Assumed: `requirements.lock` accurately reflects `requirements.txt` and the codebase's actual dependencies at all times
- Reality: it can silently drift — a declared dependency can be missing from the installed set (`xxhash`), and a fully-removed dependency can still be installed (`pymongo`/`dnspython`) — with no error or warning anywhere, because nothing forces `requirements.lock` regeneration except manually running `pip-compile`

**Resolution Pattern**: A lock file's correctness is only as good as the last time someone regenerated it after `requirements.txt` changed. Neither a missing-but-declared package nor a present-but-no-longer-declared package produces any runtime signal — both require someone to actually diff the regenerated lock, which happened here only as an incidental side effect of unrelated work.

**Lesson**: Consider periodically regenerating and diffing `requirements.lock` even with no `requirements.txt` change pending, specifically to catch this class of silent drift — a documented "optional acceleration" feature (`MINHASH_HASH_FUNC=xxhash`) can be silently non-functional for an extended period with zero test failures, since the code correctly falls back to a slower default rather than erroring.

**Recurrence Risk**: Low for these two specific packages (both now corrected in the lock file, effective on the next `docker compose build --no-cache kato`), but the general risk (lock/manifest drift going undetected) remains until/unless a periodic check is added. Not currently tracked as a backlog item — noted here for awareness only.

---

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

## Process Verification Patterns

### 2026-09-18 - Three Instances of the Same Failure Mode: "A Verification That Could Not Have Failed"

**Pattern**: Across the work that shipped in KATO v5.2.0 (DECISION-032), three separate verification steps were written in a way that could not have detected the bug they were meant to catch — each looked like a real check, passed, and gave false confidence.

1. **The `.dockerignore` fix (5.1.1) was "verified" against zero `__pycache__` directories on disk** — a check with nothing present to catch, so it necessarily passed regardless of whether the fix worked. It didn't: 76 stale `.pyc` files still shipped in the 5.1.1 image. Fixed for real in 5.1.2 and re-verified only once real cache directories (17 of them) were confirmed present on disk *during* the check. Related fact: `.dockerignore` uses Go `filepath.Match` semantics, not gitignore syntax — nested-path patterns need an explicit `**/` prefix, a natural place for this kind of pattern-syntax mistake to hide.
2. **The prediction-parity gate (`scripts/check_prediction_parity.py`) initially did not exercise the pruned path it existed to guard** — its corpus produced only 17 predictions against a `max_predictions` threshold of 300, so the top-K prune never actually engaged during the "parity" check. A gate that never exercises the changed code path can't fail on a regression in that path. Fixed by adding a deliberately crowded corpus plus `PRUNED_PROBES` with a low `max_predictions`, and by making the script self-check and refuse to report success unless those signals (frequency > 1, non-empty emotives, prune actually engaged) are present.
3. **A chunking unit test asserted against `METADATA_QUERY_CHUNK`** — the very constant the change under test was supposed to correctly apply — so the test passed even with chunking disabled entirely, because it was only checking internal consistency with itself, not an independent invariant. Rewritten to bound expectations against `CLICKHOUSE_MAX_QUERY_SIZE` (262144) / `BYTES_PER_NAME` (44) instead — a ceiling that exists independently of the code being tested.

**Discovery Trigger**: Noticing, while reviewing this session's own verification work, that each of these three checks would have printed the same "passed" result whether or not the underlying fix was real — either because there was nothing to catch, the path under test was never reached, or the assertion was circular.

**Resolution Pattern**: Before trusting any "verified"/"confirmed fixed" claim, ask two questions of the check itself: (1) does its input actually reach the changed code path (not just call the function, but exercise the specific branch/condition that changed)? (2) is its pass/fail condition defined independently of the value being changed, or does it just restate the same constant/expectation back at itself? A check that fails either question is not evidence, even if it's green.

**Lesson**: "Verified" is not a fact about a claim — it's a fact about a check, and a check can be worthless while still reporting success. This generalizes DECISION-031's earlier testing lesson (a shared `requests.Session()` hid cross-worker nondeterminism by accident) — that was a check with a *blind spot*; these three are checks with *no possible failure mode at all*, a stronger and more dangerous version of the same problem. When writing a regression guard, deliberately try to make it fail first (revert the fix, or use an empty/synthetic setup that lacks the triggering condition) before trusting a pass against the real fix.

**Recurrence Risk**: Medium — any new verification step written quickly under time pressure is at risk of one of these three specific shapes (empty-input check, path-not-exercised check, circular-constant check). Worth a standing habit: when writing a new automated check, spend one extra step confirming it can print "FAIL" under the exact bug it exists to catch.

---

## Operational Gotchas

### 2026-09-18 - `pip-compile` Must Regenerate `requirements.lock` In Place; `qdrant-client` Held Below 1.16

**Fact (verified)**: `pip-compile --output-file=requirements.lock requirements.txt` must be run so it regenerates the **existing** lock file in place. Pointing it at a fresh/empty output file gives it no prior pins to honor, so it re-resolves and bumps every dependency at once rather than only the ones actually affected by the `requirements.txt` change — this is the same class of "full accidental upgrade" outcome flagged as an open item after Remediation Pass 1 (nearly every pin moved when a full regen was attempted in a clean container).

**Fact (verified)**: `qdrant-client` is deliberately held at `<1.16` in this project's dependency pins. Version 1.17 removed `QdrantClient.search()` entirely, and the resulting failure was swallowed rather than raised — silently degrading vector search rather than breaking loudly. Confirmed still respected in the v5.2.0 fresh-pull image verification (`qdrant-client` 1.15.1).

**Recurrence Risk**: Low for the pin itself (documented and checked at each release verification), but the `pip-compile` in-place requirement is easy to forget for anyone regenerating the lock file by hand rather than through the project's standard flow — worth restating any time `requirements.lock` is touched.

---

### 2026-09-10 - ClickHouse's HTTP Interface Treats GET as Read-Only by Design

**Fact (verified)**: ClickHouse's HTTP interface (port 8123, used by `kato/storage/clickhouse_writer.py` and the ops/debugging scripts in this repo) only executes mutating statements (`INSERT`, `ALTER`, `DROP`, `TRUNCATE`, etc.) when the request is sent as an HTTP `POST`. A mutating query sent as a `GET` is rejected/no-op'd by ClickHouse itself — this is a deliberate ClickHouse server safety property, not a KATO bug. Ad-hoc debugging via `curl` (or any quick HTTP client) against ClickHouse must use `-X POST` (or an equivalent) for anything beyond a `SELECT`, or the request will silently fail to do what it looks like it's doing.

**Discovery Trigger**: Encountered while doing ad-hoc ClickHouse debugging/verification work in this project.

**Recurrence Risk**: Low, but worth keeping documented — anyone reaching for a quick `curl http://localhost:8123/?query=...` to run a mutating statement by hand (rather than through `clickhouse_writer.py`, which already does this correctly) will hit this if they default to GET.

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
