# Project-Manager Patterns Log
*Productivity insights, trend analysis, and assumption-to-reality mappings*

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
