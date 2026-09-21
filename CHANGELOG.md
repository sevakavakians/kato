# Changelog

All notable changes to KATO will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [6.0.0] - 2026-09-21

Stops every prediction pulling the node's entire pattern corpus into Python.
ClickHouse now evaluates a provable upper bound on the similarity score, so
patterns that cannot reach `recall_threshold` are never loaded. Prediction
output is byte-identical: the real scorer still decides, unchanged, on every
pattern that survives.

Two settings are removed in the process, which is what makes this a major
release. See Upgrade notes.

### Upgrade notes — BREAKING

**`recall_threshold = 0` is rejected.** It previously meant "return every
pattern regardless of similarity". It is now a `400` from `POST /sessions` and
`POST /sessions/{id}/config`, and a startup validation error from
`RECALL_THRESHOLD=0`. A session already persisted with `0` is not broken: it
rehydrates with a warning and falls back to the system default. Use a small
positive value such as `0.01` for the same practical effect.

**`LengthFilter` is removed**, along with the `length_min_ratio` and
`length_max_ratio` settings and the `'length'` entry in `filter_pipeline`. A
`filter_pipeline` naming `'length'` is now rejected by config validation with a
message naming the filter, rather than being silently skipped. Remove the entry;
the recall-safe bound replaces it and needs no configuration.

The filter was recall-lossy and always had been. It bounded pattern length by
fixed `0.5x`/`2.0x` ratios that ignored `recall_threshold`, so at
`recall_threshold=0.1` with a 20-token STM it kept only lengths `[10, 40]` where
recall-safety requires `[1, 380]` — silently discarding patterns scoring as high
as 0.66. If you had it in a pipeline, removing it means you will now see
predictions it had been hiding.

No endpoint, request schema or response field is added, removed or renamed, and
no prediction value changes.

### Added
- **Recall-safe candidate bounding** (`kato/filters/recall_bounds.py`). ClickHouse
  cannot evaluate KATO's scorer — it has no longest-common-subsequence function,
  and `arrayLevenshteinDistance` is a different metric (it permits substitution,
  which LCS does not), so using it would change predictions. Instead a *necessary
  condition* is pushed down: from `LCS <= min(P, L)` a window on pattern length,
  and from `LCS <= (count of pattern tokens present in the STM)` an overlap
  predicate. Both are provable upper bounds on `2*LCS/(P+L)`, so anything they
  reject cannot clear `recall_threshold`. Uses the existing `idx_token_bloom` and
  the `(kb_id, length, name)` primary key — no schema migration.
- **`KATO_RECALL_BOUND_ENABLED`** (default `true`) — kill switch. When disabled
  the emitted query is identical to the pre-6.0 one.
- **`KATO_RECALL_BOUND_AUDIT`** (default `false`) — shadow-runs the unbounded
  query and logs `RECALL BOUND VIOLATION` for anything dropped that was
  reachable. Recommended for the first day on a new corpus shape.
- `--boundary` mode for `scripts/check_prediction_parity.py`, building patterns
  that sit exactly on the bound's edge.

### Changed
- `recall_threshold` must now be `> 0.0` and `<= 1.0` (was `>= 0.0`). Validation
  moved in lockstep across the Pydantic field, `SessionConfiguration.validate()`
  and `ConfigurationService`, and now also rejects `bool`, which is an `int`
  subclass and previously passed as `1.0`.

### Fixed
- **`POST /sessions` never validated its `config` payload**, unlike
  `POST /sessions/{id}/config`. Create-time configuration was accepted unchecked.
- **Both session managers discarded `SessionConfiguration.update()`'s result**, so
  a rejected value silently became the default instead of raising.
- `RapidFuzzFilter` read `recall_threshold` with `or 0.1` (coercing a legitimate
  `0.0`) and `getattr(config, 'use_token_matching', True)`, which returns `None`
  — not `True` — when the attribute exists and is `None`, silently selecting
  character-level matching.
- Corrected two comments asserting that query parameters are bound server-side.
  `clickhouse-connect` resolves `%(name)s` client-side; values are escaped, but
  they do land in the statement text and count against `max_query_size`.

### Performance
Measured on a 3,000-pattern corpus, identical prediction counts in both
configurations:

| corpus shape | bound on | bound off |
|---|---|---|
| wide vocabulary (4,000 symbols) | 25.4 ms | 89.5 ms |
| narrow vocabulary (40 symbols) | 109.9 ms | 160.8 ms |

The predicate evaluated over 1,000,000 synthetic patterns with no index
assistance takes 206 ms and returns 3,925 rows.

The benefit depends entirely on how much vocabulary a corpus shares with its
probes: large on diverse data, near-none where most patterns genuinely match.
It never costs correctness.

## [5.2.0] - 2026-09-18

Makes the prediction path give the same answer twice, and stops it doing work
that grows with the corpus to produce a fixed-size result. Also clears the
deprecation warnings left behind by the 5.1.1 dependency upgrade, plus three
resource-teardown defects found in the code that migration rewrites.

Three ways the same request could return different answers are fixed, one of
them a session-isolation break. Prediction latency falls by 27% at 6,000
patterns, and by more as a corpus grows, because a lookup that scaled with the
number of matching patterns now scales with `max_predictions` instead.

### Upgrade notes

Some prediction values change. All of these are corrections — the previous values
were not reproducible — but they are observable:

- **Single-symbol predictions return an empty `future_potentials`.** They
  previously returned whichever list the last multi-symbol prediction on that
  node had left behind, which belonged to a different session. The fast path
  computes no ensemble predictive information, so empty is the honest answer.
- **`confluence`, `normalized_entropy`, `global_normalized_entropy` and
  `itfdf_similarity` may change on a multi-worker deployment.** They were computed
  from whatever symbol statistics the answering worker happened to have cached;
  a worker that had missed a learn returned figures for data that no longer
  existed (confluence 0.049 where the correct value was 0.025).
- **`global_normalized_entropy` may move by one unit in the last place.** Three
  float sums iterated unordered sets, so the result depended on the process hash
  seed and changed when the container restarted.

Nothing in the HTTP contract changes: no endpoint, request schema or response
field is added, removed or renamed.

### Changed
- **Migrated from `@app.on_event` to a `lifespan` context manager.** FastAPI
  deprecated `on_event`, and it emitted a `DeprecationWarning` on every import of
  `kato/services/kato_fastapi.py`. `startup_event`/`shutdown_event` are now
  `_startup()`/`_shutdown()`, driven by a `lifespan` context manager passed to
  `FastAPI(...)`. Startup and shutdown step order is unchanged, and shutdown keeps
  its per-step try/except-and-continue behaviour. `setup_error_handlers(app)`
  deliberately **stays at module scope** — Starlette builds its middleware stack
  before dispatching the lifespan scope and snapshots `app.exception_handlers`, so
  registering from the lifespan would be as dead as the old startup hook was.
  Note that `@app.on_event` on this app is now a silent no-op; new startup and
  shutdown work belongs in `_startup`/`_shutdown`.
- **`redis` async `close()` → `aclose()`** in `RedisSessionManager.shutdown()`,
  `CacheManager.cleanup()` and `DistributedSTMManager.close()`. redis-py deprecated
  the async `close()` in 5.0.1; the floor in `requirements.txt` is raised to match,
  and `tests/requirements.txt` (which sat below the runtime floor at `>=4.5.0`) is
  aligned. The **sync** client in `connection_manager.py` is untouched — `close()`
  is not deprecated there.
- **`httpx2` added to `tests/requirements.txt`.** starlette 1.6's test client
  prefers `httpx2` and warns on the `httpx` fallback. `httpx` stays: `qdrant-client`
  depends on it, as does `tests/tests/fixtures/kato_session_client.py`.
- **`anyio` floor raised to `>=4.10,<4.15`** (locked 3.7.1 → 4.14.2). The floor is
  what `httpx2` requires; the 3.7.1 pin was stale rather than deliberate, since
  nothing under `kato/` imports anyio and `httpcore[asyncio]` already wanted `>=4.0`.
  The **cap is measured, not cautionary**: anyio 4.15.0 deprecated the
  `anyio.abc.BlockingPortal` alias that `starlette/testclient.py` still imports, so
  `>=4.15` merely trades the old httpx warning for a new one that cannot be fixed
  from here. Drop the cap once starlette moves to `anyio.from_thread.BlockingPortal`.
  Only `anyio` moved in the lock (`sniffio` drops out, being an anyio 3 dependency).
- **Pattern metadata is fetched after the top-K prune, not before.** The lookup
  ran for every matching pattern, then the list was cut to `max_predictions * 3`
  — 300 by default — and only then was the metadata used. Nothing the prune reads
  comes from metadata, and every consumer of `frequency` or `emotives` runs after
  it, so the fetch moved. Measured end to end, output unchanged:

  | corpus | before | after | |
  |---|---|---|---|
  | 500 | 195.9 ms | 189.7 ms | −3% |
  | 2,000 | 488.9 ms | 421.9 ms | −14% |
  | 6,000 | 1288.1 ms | 937.5 ms | −27% |

  The saving grows with the corpus, because an O(matched) term became
  O(`max_predictions` × 3). At 6,000 matches the lookup went from 12 chunked
  round trips to one.
- **`patterns_metadata` is read once per prediction instead of twice.** The second
  read fetched the precomputed entropy and tf columns that the first query had
  already selected and discarded.

### Fixed
- **The session manager was never shut down.** Shutdown guarded on
  `hasattr(session_manager, 'close')`, but neither `RedisSessionManager` nor the
  in-memory `SessionManager` has ever defined `close()` — both define `shutdown()`.
  The branch was therefore always false and silently did nothing, leaking the Redis
  connection pool and the session cleanup task on every restart. Shutdown now calls
  `shutdown()`, and reads the private `_session_manager` rather than the lazy
  property so teardown cannot *construct* a session manager the process never used.
  Verified by driving the real ASGI lifespan protocol: the shutdown sequence now
  logs `RedisSessionManager shutdown complete`, which it never did before.
- **The concurrency reporter task was unmanaged.** `asyncio.create_task(...)`
  discarded the handle, so the task could be garbage-collected mid-flight and was
  never cancelled — it was torn down abruptly when the loop closed. The handle is
  kept and cancelled first during shutdown, before anything holding resources.
- **`MetricsCacheManager` leaked its Redis client.** It opened a `redis.asyncio`
  client in `initialize()` and had no teardown path at all. It now has `close()`,
  plus a `close_metrics_cache_manager()` companion that drops the singleton so a
  later `get_metrics_cache_manager()` re-initializes cleanly; shutdown calls it,
  guarded so it does not construct the manager during teardown.
- **Single-symbol predictions leaked another session's `future_potentials`.** The
  field is stored on the `PatternProcessor`, which every session on a node shares,
  and the endpoint reads it off that instance after the call. The single-symbol
  fast path returned before both places it is ever assigned, so it left the
  previous request's value in place. Demonstrated across three sessions on one
  node: session A produced two entries, and sessions B and C then got A's two
  entries back verbatim — B while returning no predictions of its own. This breaks
  the session-isolation guarantee, not only determinism.
- **uvicorn workers disagreed about the same data.** Each worker memoises the
  node's symbol table and global counters and dropped them only when *that*
  process served a learn, so a worker that missed one kept answering from stale
  figures indefinitely. Every write now stamps a per-node version that readers
  check before reusing a cache; the stamp travels in an MGET and a pipeline that
  were already being issued, so it costs no extra round trip. Reproducing it needs
  three steps in order — cache, miss a learn, answer again — which is why it went
  unnoticed.
- **Three float sums depended on the process hash seed.**
  `global_normalized_entropy` in `metrics.py` and two inlined copies in
  `pattern_processor.py` summed over raw `set` iteration order, and floating-point
  addition is not associative. Restarting the container with no code change
  returned `0.6586558556598887`, `...887`, then `...888`. All three now sum in
  sorted order.
- **Pattern metadata reads could fail silently above ~2000 `max_predictions`.**
  Names are expanded into the statement text and ClickHouse rejects anything over
  `max_query_size`; the error was caught and `{}` returned, so predictions fell
  back to `frequency=1` and runtime entropy with nothing surfaced. Two call sites
  passed unbounded lists. Chunking now lives in the writer, where the constraint
  applies, so every caller is covered.
- **`metrics.py`'s `global_normalized_entropy` docstring** gave a result the code
  had never produced (`0.3918295834173894` against an actual
  `0.6442358590725441`). Note 5 of that module's 15 doctests still fail and
  nothing runs them.

### Added
- **`scripts/check_prediction_parity.py`** — captures the full prediction payload
  for a fixed corpus and diffs it against a later run, which is how every
  prediction change in this release was verified. Its corpus is built so patterns
  carry `frequency > 1` and non-empty emotives, and so a low `max_predictions`
  forces the top-K prune; it refuses to report success if either signal is
  missing, because without them a change that dropped metadata entirely would
  produce identical output and the tool would pass while proving nothing.
- **Tests** for the cross-worker cache contract (`test_stats_version.py`) and for
  metadata query chunking (`test_metadata_query_chunking.py`), each confirmed to
  fail when its fix is reverted.

## [5.1.2] - 2026-09-17

Build hygiene only. No code, dependency or behaviour changes from 5.1.1 — the
sole difference is what the image does **not** contain.

### Fixed
- **Published images no longer carry the builder's Python bytecode.** The
  `.dockerignore` added for 5.1.1 was written in gitignore syntax, but
  `.dockerignore` matches each pattern against the whole path from the context
  root, so a bare `__pycache__` excluded only a top-level one and every nested
  cache still shipped. v5.1.1 therefore contained 76 `.pyc` files across 17
  `__pycache__` directories, and v5.1.0 contained 164. They were inert — the
  bytecode was `cpython-313` from the builder's virtualenv while the image runs
  `cpython-310`, so the interpreter could not load them and imports came from
  source — but they meant an image's contents varied with whoever built it.
  Nested patterns now carry the required `**/` prefix, verified with caches
  present on disk rather than absent: `/app/kato` is 1.1M instead of 2.2M, with
  zero `.pyc`.

## [5.1.1] - 2026-09-17

A security-driven dependency upgrade clearing every advisory against the pinned
runtime set, plus the two defects that upgrade surfaced. No API changes.

### Security
- **Dependency upgrade clearing 23 published advisories across 10 packages.** `pip-audit` against the v5.1.0 lock reported vulnerabilities in `starlette` (6), `python-multipart` (6), `urllib3` (4), `click`, `h2`, `idna`, `protobuf`, `pygments`, `pytest` and `python-dotenv`; it now reports none. The upgrade was deliberately narrow — only packages with advisories moved, plus what their resolution required. `clickhouse-connect`, `redis`, `datasketch`, `numpy`, `scipy`, `uvicorn`, `websockets`, `pydantic` and `rapidfuzz` are all unchanged, `datasketch` especially so: its MinHash output is persisted in `lsh_bands`/`minhash_sig`, and changing it would invalidate every stored signature.
- **`fastapi` 0.118.3 → 0.141.1 and `starlette` 0.48.0 → 1.6.0.** The previous `fastapi<0.119.0` cap dated from an unrelated routing investigation rather than a known incompatibility, and it held `starlette` below every version that fixes its advisories. Verified on the new pair: `on_event` handlers still run, import-time exception handlers still fire, and `HTTPException` responses keep their flat `{"detail": ...}` shape.
- **Test dependencies no longer ship in the runtime image.** `pytest` and `pytest-asyncio` were declared in `requirements.txt`, so they were installed into every published image — which is why a `pytest` advisory appeared in the audit at all. They are declared in `tests/requirements.txt`, where they belong.
- **The Qdrant server image is pinned** (`qdrant/qdrant:v1.17.1`), so it cannot drift again. It was `:latest` and had moved to 1.17 while `qdrant-client` stayed at 1.15, which the client warns about on every startup. `qdrant-client` is deliberately held at `<1.16` rather than raised to close that gap: **1.17 removed `QdrantClient.search()`**, which `kato/storage/qdrant_store.py` calls, and `QdrantStore.search` catches the resulting `AttributeError` — so on 1.17 nearest-neighbour lookup returns nothing, multimodal observations stop resolving to their `VCTR|` symbols, and predictions silently lose matches. Verified: the 1.15 client returns correct results against the 1.17.1 server despite the warning. Moving past 1.15 requires migrating to `query_points()` first.

### Fixed
- **The vector search cache was never cleared.** `VectorSearchEngine.clear_cache` was a coroutine, but its only caller — the synchronous `clearPatternsFromRAM` — called it without awaiting, so the body never ran and Python emitted "coroutine 'clear_cache' was never awaited" on every clear-all while stale vectors survived. It does no I/O, so it is now an ordinary function.
- **`HTTP_422_UNPROCESSABLE_ENTITY`** is resolved through a compatibility shim; Starlette 1.6 renamed it to `HTTP_422_UNPROCESSABLE_CONTENT` and deprecated the old spelling.

### Added
- **`pip-audit` runs in CI** against `requirements.lock`, so a new advisory fails the build rather than waiting for someone to look.
- **`tests/tests/unit/test_qdrant_client_api.py`**: asserts the Qdrant client still exposes the methods and `search()` keyword arguments `qdrant_store.py` depends on. The 1.17 removal above degraded silently and was only caught by a vector test that happened to rely on nearest-neighbour recall; this fails immediately and explains why.

## [5.1.0] - 2026-09-16

Fixes a set of live defects found by a repo-wide review, makes prediction output
deterministic, removes a large amount of dead code, and adds the project's first
Python CI. Prediction payloads and error responses both change observably —
see "Upgrade notes" before deploying.

### Upgrade notes

- **`node_id` sanitisation changed, and it determines where data lives.** The
  derived `kb_id` (the ClickHouse partition, Redis namespace and Qdrant
  collection name) is now built from an allowlist: every character outside
  `[A-Za-z0-9_]` becomes `_`. The previous rule replaced a fixed list of 14
  characters, so a `node_id` containing anything else — `!`, `@`, `#`, `+`, `~`,
  `(`, `)`, or a single quote — kept it verbatim and now maps to a *different*
  `kb_id`, leaving that node's existing patterns and vectors unreachable. Node
  ids made only of letters, digits, `_`, and the previously-replaced characters
  are unaffected and map exactly as before. Check with:
  `SELECT DISTINCT kb_id FROM kato.patterns_data WHERE NOT match(kb_id, '^[A-Za-z0-9_]{1,60}$')`
  — if that returns nothing, nothing moves.
- **KATO exceptions now produce their intended HTTP status and body.** They
  previously escaped as a plain-text `500 Internal Server Error` because the
  handlers were never registered (see Fixed). A client that treated any 500 as
  retryable will now see `404`, `410`, `422`, `429`, `503` or `504` with a
  structured `{"error": {...}}` body instead. Responses raised as
  `HTTPException` by route handlers are unchanged — still flat
  `{"detail": "..."}`.
- **Tied predictions now come back in a defined order**, which may differ from
  whichever order a given worker happened to produce before.
- **Backing-store ports are now published on `127.0.0.1` only**
  (Redis 6379, ClickHouse 8123/9000, Qdrant 6333, in both `docker-compose.yml`
  and `deployment/docker-compose.yml`). Container-to-container traffic and
  host-local tooling are unaffected; access from other machines is not.

### Added
- **Multi-symbol-event prediction tests** (`tests/tests/unit/test_multi_symbol_event_predictions.py`, 34 tests): patterns with 1–4 symbols per event and repeated symbols across events, observed as the full pattern, halves, middle, single events, mid-event starts/ends, dropped/added symbols, unexpected whole events, split/merged/reordered events, duplicates, gaps, single symbols (fast path), and two near-identical patterns — each asserting `past`/`present`/`future`/`missing`/`extras`/`anomalies` in full.
- **Python CI** (`.github/workflows/ci.yml`): `ruff`, `bandit`, and the unit suite on every push and pull request. The repository previously had no Python CI at all — only the Helm chart workflow — and `.pre-commit-config.yaml` was never installed in practice, so `ruff check kato/` had accumulated 282 unreported errors. It now passes; the remaining stylistic categories are parked in a labelled backlog in `pyproject.toml` so the correctness rules (unused imports and variables, undefined names) are enforced from here on.
- **`PROCESS_POOL_CANDIDATE_THRESHOLD`** (default `0`, disabled): candidate count above which prediction matching fans out to a `ProcessPoolExecutor` instead of a `ThreadPoolExecutor`. See Changed for why it is off.
- **`kato/storage/identifiers.py`**: allowlist validation (`validate_kb_id`, `validate_pattern_name`) for the identifiers that must be inlined into statement text because ClickHouse accepts no bound parameters in `ALTER TABLE ... DROP PARTITION` or in an `ALTER TABLE ... DELETE` predicate.
- **`rank_predictions()`** in `kato/representations/prediction.py`: the single, deterministic ranking used by every prediction ranking, pruning and truncation site.
- **`PatternFilter.get_query_parameters()`**: filters now supply bind values for their SQL instead of formatting them into it.
- **New tests** (55): error-handler registration and status mapping, identifier validation, observation validation, processor eviction, prediction ranking determinism, and metadata-batch chunking.

### Changed
- **Prediction ranking tie-breaks on the pattern name.** Ranking used the configured metric alone, so ties were settled by the order candidates happened to arrive in — which is not stable, because candidates come out of a `set` (string hashing is randomised per process, so each uvicorn worker iterates differently) and batch results are gathered with `as_completed()`. Ranking is now on `(metric, name)`, a total order since names are unique. Only tied predictions are affected; their order, and which of them survive `max_predictions`, are now fixed rather than arbitrary.
- **The per-request `ProcessPoolExecutor` is off by default.** It engaged above 500 candidates and built a fresh pool — up to four interpreters, plus pickling each batch across the boundary — on *every* request. Measured at 6000 patterns / 6000 candidates: **3378 ms** with it engaged versus **1231 ms** on the thread pool alone, for byte-identical prediction payloads. RapidFuzz already releases the GIL, so the thread pool had real parallelism regardless. Re-enable for heavier per-candidate workloads with `PROCESS_POOL_CANDIDATE_THRESHOLD`.
- **`POST /sessions/{id}/config` now validates every field.** It wrote attributes directly and never called `SessionConfiguration.validate()`, so out-of-range filter parameters (`jaccard_threshold`, length ratios, MinHash bands) were accepted and reached the query layer, and identity fields such as `node_id` could be overwritten. Updates now go through `SessionConfiguration.update()`, which validates and rolls back atomically; a rejected update returns `400` where it previously returned `200`.
- **CORS `allow_credentials` is now `false`.** With `allow_origins=["*"]` Starlette reflects the caller's `Origin` when credentials are enabled, which makes every origin trusted for credentialed requests. KATO has no cookie or browser-session auth, so nothing needed it.
- **Redis prediction keys are written with a TTL** (the session TTL) instead of never expiring. One key was produced per observation and nothing reaped them.
- **`kato.exceptions.MemoryError` → `MemoryOperationError`, `TimeoutError` → `KatoTimeoutError`.** Both shadowed Python builtins: `handlers.py` imported the KATO `TimeoutError`, shadowing the builtin for that whole module, while `websocket/event_broadcaster.py` raises the builtin one. `MemoryOperationError` was already the name every caller used via an alias.
- **`config/redis.conf` sets `protected-mode no` explicitly.** It cannot be enabled while no password is configured — with `protected-mode yes` and no password, Redis refuses every non-loopback connection, and a `bind` directive does not exempt it. Setting it explicitly rather than inheriting the base image's default (`redis:7-alpine` ships `no`, upstream Redis ships `yes`) keeps behaviour independent of the image. Set `REDIS_PASSWORD` to add authentication, after which protected mode can be turned back on.

### Fixed
- **KATO's structured error handling never ran.** `setup_error_handlers(app)` was called from inside `@app.on_event("startup")`. Starlette builds its middleware stack on the first `__call__` — the lifespan scope — and `build_middleware_stack()` copies `app.exception_handlers` into a fresh dict, so handlers registered afterwards are discarded silently. Every KATO exception therefore escaped as a plain-text `500 Internal Server Error`, and the whole of `kato/exceptions/handlers.py` — status mapping, recovery suggestions, and the traceback-suppressing catch-all — was dead. Registration moved to module scope, scoped to `KatoV2Exception` and the `Exception` catch-all so `HTTPException` responses keep their existing flat `{"detail": ...}` shape.
- **Every `ValidationError` raise site raised `TypeError` instead.** All 12 sites in `observation_processor.py` and `pattern_operations.py` passed the message positionally *and* `field_name=` as a keyword; `field_name` is the first positional parameter, so each one raised `TypeError: got multiple values for argument 'field_name'`. Masked by the dead handlers, since everything became a 500 either way.
- **LRU processor eviction permanently deleted a live node's vectors.** `ProcessorManager._evict_oldest()` called `delete_collection()` unconditionally, but `vectors_{processor_id}` is persistent per-node storage, not a cache — so any node pushed out of the 100-entry LRU lost its embeddings for good. Now gated on a `test_` prefix, matching the pattern-database branch beside it and the TTL-expiry path, neither of which ever did this.
- **Pattern metadata was silently lost above roughly 6000 patterns.** The names go into an `IN` list expanded into the statement text, and ClickHouse rejects anything over `max_query_size` (262144 bytes). `ClickHouseWriter` logged the rejection and returned `{}`, so every prediction quietly fell back to `frequency=1` and default metrics. Lookups are now chunked at 500.
- **`delete_pattern` reported success after a failed delete.** It removed the in-memory copy, then swallowed ClickHouse and Redis failures with a warning, leaving the pattern in persistent storage while the caller was told it was gone. Failures now propagate.
- **`KatoProcessor.get_stm()` called a method that does not exist** (`MemoryManager.get_stm_state()`), so any call raised `AttributeError`. It had no callers and has been removed.
- **Database connections were never closed on shutdown.** `shutdown_event` called `OptimizedConnectionManager.get_instance()`, which is not a method on that class; the resulting `AttributeError` was swallowed by the surrounding `except`.
- **Predictions are no longer re-ranked by chance.** See Changed — 40 identical requests over 10 tied patterns with `max_predictions=3` previously returned 7 distinct orderings and 5 distinct result sets.
- **Startup counted every tenant's patterns.** The `SELECT COUNT(*) FROM kato.patterns_data` run when a processor is first created had no `kb_id` predicate.
- **`.gitignore` was corrupt.** `*.nvvp` had lost its trailing newline and merged with the following line into a single nonsense pattern, so neither it nor the path after it was ignored.
- **Prediction segmentation now follows the matcher's positions, not symbol identity.** `present`'s boundaries and per-event `missing`/`extras` were re-derived from flat lengths plus a "first matched symbol" heuristic, which misplaced the boundary and misattributed `missing` when a symbol recurs across events (observing `[['y','z'],['x']]` on `[['x','y'],['y','z'],['x'],…]` pulled event 0 into `present` and reported two phantom missing symbols). The exact-match path now passes its matched pattern/state indices through, and `Prediction` segments from them; the fuzzy path keeps the previous symbol-based accounting.
- **Repeated symbols are attributed to the right event.** The flat matcher cannot tell which occurrence of a recurring symbol an observation refers to (dropping the `y` from event 1 of `[[x,y],[y,z],[x],[w,y,z]]` flattens to the same state as dropping it from event 0), and difflib's longest-run tie-break reported the earlier occurrence missing regardless. Segmentation now refines the alignment with event structure: a matched symbol goes to the pattern event where its observed neighbours matched, and a symbol observed alone prefers the occurrence leaving the fewest symbols missing (a lone `[x]` now matches the exact event `[x]`, not the `x` of `[x,y]`). Match count and `similarity` are unchanged.
- **Single-symbol predictions were flat.** The fast path hand-built `past`/`present`/`future`/`missing`/`extras` as flat symbol lists (`present: ['a']`); it now uses the same event-structured segmentation as every other prediction (`present: [['a','b','c']]`, `missing: [['b','c']]`).
- **Test suite no longer deletes live sessions on a shared Redis.** The session-scoped cleanup fixture deleted every `kato:session:*` key at the start of each pytest run, so running the suite next to a training notebook — or two suites at once — destroyed their sessions mid-flight. It now removes only sessions (plus node pointers, active-index entries and distributed-STM streams) whose `node_id` carries a test prefix (`test`, `topology_`, `perf_`, `load_test`; override with `KATO_TEST_NODE_PREFIXES`) and never touches `stm:global`. `tests/tests/fixtures/redis_test_cleanup.py`, with a self-test.

### Removed
- **`kato/gpu/`** and its supporting `kato/config/gpu_settings.py`, `tests/tests/gpu/` and `docs/developers/gpu/` (~1,300 lines). Nothing outside `kato/gpu/` imported it, its 34 tests were skipped in every environment, and its encoder was still written against the MongoDB layer removed in v3.0.
- **Dead modules with no importers**: `kato/sessions/session_middleware.py` (a pass-through that still carried a `process_request_old` method), `kato/sessions/session_middleware_fixed.py`, `kato/storage/connection_pool_monitor.py` (the `/connection-pools` endpoint does not use it), and the empty packages `kato/auxiliary/`, `kato/scripts/`, `kato/utils/`. The live middleware, `session_middleware_simple.py`, is renamed to `session_middleware.py`.
- **`kato/sessions/redis_session_store.py`**, which had no importer in `kato/` and defaulted to `pickle` for session serialisation. This closes the `pickle.loads` finding recorded in `docs/maintenance/security-review-baseline.md`.
- **`aioredis`** from `requirements.txt` — nothing imported it (everything uses `redis.asyncio`) and the project is archived. Every other pin in `requirements.lock` is unchanged.
- **MongoDB remnants** from `docker-compose.test.yml`: the `mongo:4.4` service, its volume and healthcheck, and the `MONGO_BASE_URL` variable that nothing read.

### Security
- **User input no longer reaches ClickHouse as SQL text.** An observation token was interpolated into `WHERE first_token = '{symbol}'`, and STM tokens were concatenated into an array literal in the Jaccard filter; `kb_id` and pattern names were interpolated across `clickhouse_writer.py` and the filter executor. All of these now bind server-side. The two statement types that cannot bind parameters (`DROP PARTITION`, `ALTER ... DELETE`) validate their identifiers against a strict allowlist first.
- **`node_id` sanitisation is an allowlist, not a blacklist.** The previous 14-character blacklist did not include the single quote, tab or newline, any of which could survive into statement text via `kb_id`. See "Upgrade notes".
- **`GET /pattern/{pattern_id}` validates its path parameter** as a SHA1 digest before it reaches a query.
- **Backing stores are no longer published on every host interface.** Redis, ClickHouse and Qdrant all run without authentication by default, so their published ports are now bound to `127.0.0.1`.
- **CORS no longer allows credentialed requests from arbitrary origins** (see Changed).

## [5.0.2] - 2026-09-10

Fixes a worker deadlock under concurrent same-node requests that is present in every 5.x image so far, makes the request path lock-free, and makes clear-all actually clean up.

### Added
- **`scripts/check_store_parity.py`**: reports per-`kb_id` pattern counts that disagree between Redis (`frequency` keys) and ClickHouse (`patterns_data`); `--purge-prefix PREFIX --execute` removes the residue of mismatched kb_ids with that prefix from both stores.
- **Opt-in multi-worker throughput and integrity test** (`tests/tests/performance/test_multi_worker_throughput.py`, `KATO_PERF=1`): runs the parallel-training shape against self-launched 1- and 4-worker containers, reports the speedup, and asserts exact pattern counts, exact shared-pattern frequency under contention, Redis/ClickHouse agreement, and a clean clear-all.
- **Documented limitation — one writer per session.** Overlapping mutating requests on the same `session_id` from different uvicorn workers lose updates (per-worker read-modify-write of the whole session). Stated in the session docs and the API reference; `test_concurrent_session_modifications` is now a strict xfail under `KATO_WORKERS > 1` instead of a skip, so the limitation stays visible.

### Fixed
- **Observe/learn/predict no longer stage session state in the shared processor (Phase 1.6).** `ObservationProcessor.process_observation` and `check_auto_learning`, `PatternOperations.learn_pattern_from`, and `PatternProcessor.learn_from`/`predict_from` now take the session's STM (and accumulators) as arguments and return the updated STM, instead of loading it into `pattern_processor.STM` for the duration of a request. Concurrent requests for the same node on one worker therefore run without any lock — the stopgap `asyncio.Lock` below was removed again — and can overlap while one waits on ClickHouse or Redis. The legacy stateful `learn()`/`processEvents()` remain as thin delegates. Verified by a new same-worker interleaving test and the perf/integrity test (1.83× on 4 workers vs 1).
- **Overlapping requests for one node deadlocked the uvicorn worker serving them.** `ObservationProcessor.process_observation` held a blocking `multiprocessing.Lock` across its awaits; on a single event loop, the second concurrent request blocked the loop thread waiting for a lock the first request could no longer release. The worker stopped answering everything, `/health` included, and stayed dead. Reproduced deterministically with two clients training one `node_id`; on the default 4-worker deployment it killed workers one by one. Both `multiprocessing` locks are gone; `KatoProcessor` now serializes its observe/learn/predict bridge sections with an await-aware `asyncio.Lock` per processor (requests for different nodes never contend; requests for the same node still run in parallel across workers). This is a stopgap ahead of making the bridge per-request (Phase 1.6). `KatoProcessor.learn` is now a coroutine.
- **Image HEALTHCHECK always failed.** The Dockerfile probe did `import requests`, which is not installed in the image, so containers started with `docker run` reported unhealthy forever (the compose files probe with `urllib` and were unaffected). The Dockerfile now uses the same `urllib` probe.
- **Clear-all silently left Redis keys behind for kb_ids containing glob metacharacters.** `RedisWriter` built `SCAN MATCH {kb_id}:*` unescaped; a kb_id such as `name[case]_kato` (pytest parametrize ids reach kb_ids this way) is a character class, matched nothing, and every key survived. All four scan sites now escape the kb_id (`escape_glob`); the test suite's own cleanup helper too.
- **Clear-all never dropped `patterns_metadata`.** `clear_all_memory` dropped the `patterns_data` partition and Redis keys but left the per-pattern metadata sidecar rows; it now drops that partition as well.
- **A pattern learned just before clear-all could survive it.** Inserts sit in ClickHouse's server-side `async_insert` queue (~200 ms); `clear_all_memory` dropped the partition without draining the queue first, so the row landed afterwards. The queue is now flushed before the drop.

## [5.0.1] - 2026-09-10

One fewer ClickHouse round trip per re-learn, and a working reference Python client.

### Changed
- **Metadata sidecar re-learn path reads its ClickHouse row once, not twice.** `learnPattern` fetched the pattern's `patterns_metadata` row, discarded its metric columns, and `upsert_pattern_metadata` then re-issued the identical `SELECT` to recover them (plus an unused Redis frequency lookup). New `MetadataRouter.get_metadata_for_merge()` returns the full row and `upsert_pattern_metadata(prev=...)` reuses it. Behaviour is unchanged; the new-pattern path deliberately keeps its own read, because Redis and ClickHouse can disagree after a Redis loss + rehydrate and that read is what preserves rehydrated patterns' emotives and metrics.

### Fixed
- **Reference Python client (`examples/python-client.py`)**: session-recovery retry never worked — it retried against the dead session's URL and its "skip lifecycle ops" guard matched every session-scoped `POST`; both fixed, with a re-entrancy guard. `get_percept_data()`/`get_cognition_data()` repointed from deprecated node-scoped routes (which return empty payloads) to the session-scoped ones; `get_session_config()` now actually calls its route; 9 missing wrappers added, bringing coverage to 37 of 38 HTTP routes. `examples/README.md`'s client section rewritten to match the real (synchronous, `requests`-based) API.

## [5.0.0] - 2026-09-09

Redefines the `anomalies` prediction field (breaking), makes WebSocket events reach every uvicorn worker, and lands the configuration audit: settings that were documented but never bound now work, and dead configuration surface is gone.

### Added
- **`worker_pid`** on `/health` responses and on the WebSocket `state.snapshot` event: the uvicorn worker process that served the request / owns the connection. Lets clients and tests reason about cross-worker delivery.
- **Worker-topology tests** (`tests/tests/integration/test_worker_topology.py`): launch a dedicated `kato:latest` container per `KATO_WORKERS` value (1, 2, 4) and assert the same WebSocket-delivery and `/sessions/count` contracts against each. Clients are provably placed on ≥2 workers before asserting delivery, so the in-process `EventBroadcaster` limitation now fails deterministically instead of by scheduling luck. Replaces the four scheduling-dependent websocket tests and the immediate-consistency assertion in `test_session_cleanup`, which now honours the documented `/sessions/count` cache TTL.
- **`GET /patterns/count`** endpoint returning `{pattern_count, node_id}` for a node, plus a matching client method. The storage-layer count already existed but had no caller.
- **`make run`** target to start KATO without Docker (`HOST`/`PORT`/`RELOAD` overridable), and `.env.example` rewritten to list only variables the code actually reads.
- **`python-dotenv`** declared as a direct dependency (it is imported by `kato/env_loader.py`); `requirements.lock` regenerated, which also restored `xxhash`, previously declared but missing from the lock.
- **Configuration reference** now documents the live-but-undocumented variables (`MINHASH_HASH_FUNC`, `KATO_USE_BLOOM_FILTER`, `KATO_USE_REDIS_CACHE`, `SESSION_COUNT_CACHE_TTL_SECONDS`, `METRICS_CACHE_TTL_SECONDS`, `KATO_ENV_FILE`, `KATO_SKIP_DOTENV`, `KATO_WORKERS`, `KATO_LIMIT_CONCURRENCY`, the vectordb `KATO_*` family).

### Changed (BREAKING)
- **`anomalies` prediction field** is now a flat list of every symbol that deviates from the pattern: missing symbols, then extras, then the observed token of each fuzzy match. It was previously the list of fuzzy-match records.
- **New `fuzzy_matches` prediction field** carries the `{observed, expected, similarity}` records that `anomalies` used to hold. Consumers reading fuzzy-match details from `anomalies` must switch to `fuzzy_matches`.
- **Environment names that never bound now do.** `json_schema_extra={'env': ...}` is a pydantic-v1 idiom that pydantic-settings v2 ignores, so `KATO_USE_TOKEN_MATCHING`, `KATO_FUZZY_TOKEN_THRESHOLD`, `KATO_USE_FAST_MATCHING`, `KATO_USE_INDEXING` and `KATO_CONFIG_FILE` were silently inert; both the `KATO_`-prefixed and bare spellings are now accepted. `SORT` is deliberately not aliased — use `SORT_SYMBOLS`.
- **Previously inert settings now take effect**, with defaults chosen to preserve current behaviour: `LOG_FORMAT`/`LOG_OUTPUT` (structured logging is now actually configured — **logs default to stdout, previously stderr**), `CONNECTION_POOL_SIZE` (Redis connections per worker; default 10 → 200 to match the value that was hardcoded), `REQUEST_TIMEOUT` (ClickHouse send/receive timeout, previously hardcoded 30 s). `fuzzy_token_threshold` now reaches the default configuration, not only per-session config.

### Removed
- **Four modules nothing imported**: `kato/config/database.py`, `kato/config/api.py`, `kato/config/user_config.py`, `kato/storage/query_batcher.py`.
- **Vestigial settings fields**: `performance.batch_size`, `use_optimized`, `vector_batch_size`, `vector_search_limit`, `learning.auto_learn_*` (auto-learn is driven solely by `MAX_PATTERN_LENGTH`), `service_version`, `QDRANT_COLLECTION_PREFIX`, and the whole `APIConfig` class. `batch_size` must not be reintroduced: ClickHouse `async_insert` already batches server-side across all workers, and client-side buffering was disabled on purpose because per-worker buffers orphaned rows.
- **Deployment variables nothing read**, from `docker-compose.yml`, `deployment/docker-compose.yml` and the Helm chart: `KATO_BATCH_SIZE`, `KATO_ARCHITECTURE_MODE`, `KATO_STRICT_MODE`, `QDRANT_COLLECTION_PREFIX`, `AUTO_LEARN_ENABLED`/`AUTO_LEARN_THRESHOLD`, and `CONNECTION_POOL_SIZE=50` (honouring it now would have cut the Redis pool from the long-standing effective 200).
- Roughly twenty documented-but-dead environment variables removed from the configuration reference, along with two endpoints that never existed (`/admin/log-level`, `/admin/config`).

### Fixed
- **WebSocket events lost across uvicorn workers**: `EventBroadcaster` kept its connection list per process, so `session.created` / `session.destroyed` only reached clients whose WebSocket happened to be held by the worker that served the HTTP request. Events are now published to a Redis pub/sub channel (`kato:ws_events`, override with `KATO_WS_EVENTS_CHANNEL`) and each worker delivers what it receives to its own connections — exactly-once per client on any worker count. Falls back to local delivery without `REDIS_URL`.
- **Repeated symbols under-reported in `missing`/`extras`**: event alignment used a flat membership test, so an earlier occurrence of a symbol masked a later unobserved one (e.g. the second `o` of `world`). Symbols are now consumed as a multiset.
- **Non-Docker runs crashed at import** with `redis_persistence: Extra inputs are not permitted`: pydantic-settings forwarded every `.env` key onto `Settings`, which forbids extras. `.env` is now loaded into `os.environ` by `kato/env_loader.py` instead.
- **`/concurrency` always reported `workers=1`, `total_capacity=100`**: it read `UVICORN_WORKERS`/`UVICORN_LIMIT_CONCURRENCY`, which nothing sets; it now reads `KATO_WORKERS`/`KATO_LIMIT_CONCURRENCY` (the `UVICORN_*` spellings remain a fallback).
- **`./start.sh clean-data` never cleared ClickHouse**: it dropped `default.patterns_data`, but the tables live in the `kato` database, and stderr was suppressed so it reported success anyway. It now truncates the four real `kato.*` tables and reclaims Redis AOF disk.
- **Test suite wiped live Redis**: the session-scoped conftest fixture ran an unconditional `FLUSHALL` against the shared `kato-redis` container, destroying unrecoverable pattern metadata. Cleanup is now scoped to session/STM keys; `KATO_TEST_REDIS_FLUSHALL=1` opts back in.
- Documentation referenced a nonexistent `kato.api.main` module in twelve places, including ten runnable commands that could not work as written; all point at `kato.services.kato_fastapi` now.

### Migration from 4.x
- Read fuzzy-match details from `fuzzy_matches`, not `anomalies`. `anomalies` is now `list[str]`; code that indexed `anomaly['observed']` will break.
- If you parse KATO logs from stderr, switch to stdout (or set `LOG_OUTPUT=stderr`).
- Replace `SORT` with `SORT_SYMBOLS`. If you relied on `KATO_USE_TOKEN_MATCHING` et al. and they seemed to do nothing, they now do — check the values you set.
- If you imported `kato.config.database`, `kato.config.api`, `kato.config.user_config` or `kato.storage.query_batcher`, those modules are gone (nothing in KATO used them).
- `CONNECTION_POOL_SIZE` now applies per worker; a low value copied from an old compose file will shrink the Redis pool.

## [4.0.0] - 2026-06-18

Completes the Redis → ClickHouse per-pattern metadata migration and fixes a metadata-loss regression.

### Fixed
- **Metadata loss on rapid re-learn (regression)**: The `patterns_metadata` ReplacingMergeTree used `updated_at DateTime` (1-second resolution) as both the engine version and the `argMax` read tiebreaker. Same-second learn→re-learn produced tied versions, so reads/merges could return a stale row — silently dropping emotive rolling-window merges, metadata set-union accumulation, and finalize-training metric updates. Now uses a strictly-monotonic `version UInt64` (`time.time_ns()`).

### Changed
- **Metadata version column**: `patterns_metadata` now has a `version UInt64` column used as `ReplacingMergeTree(version)` and `argMax(field, version)`; `updated_at` downgraded to informational `DateTime64(3)`.
- **Metadata write durability**: per-pattern metadata writes now use `wait_for_async_insert=1` (low volume) for immediate read-after-write visibility.
- `MetadataRouter` is now ClickHouse-only (frequency still merged from Redis).

### Removed (BREAKING)
- **`KATO_METADATA_*` configuration parameters** removed (`KATO_METADATA_DUAL_WRITE`, `KATO_METADATA_READ_FROM`, `KATO_METADATA_READ_VERIFY`); these rollout flags are now no-ops. ClickHouse is the sole store for per-pattern metadata.
- Dead Redis metadata methods (`write_metadata`, `get_metadata`, `get_metadata_batch`, `write_precomputed_metrics_batch`, `get_precomputed_metrics_batch`); frequency and symbol-stats methods retained.
- Migration scripts `scripts/backfill_pattern_metadata.py` and `scripts/delete_moved_redis_keys.py`, and migration-specific tests.

### Migration
- **Required**: the `kato.patterns_metadata` table must be recreated with the new schema (it gains a `version UInt64` column and switches the engine version column from `updated_at` to `version`). The column cannot be altered in place. Drop and recreate the table (`init.sql` updated; `_ensure_patterns_metadata_table` recreates on startup if absent).

## [3.x Unreleased backlog]

### Removed
- **MongoDB Dead Code**: Removed `connection_pool.py`, `MongoDBConfig`, `DatabaseManager`, and pymongo imports
- **MongoDB Fallback Logic**: Hybrid architecture (ClickHouse + Redis) is now the only mode; no MongoDB fallback

### Changed
- Default `KATO_ARCHITECTURE_MODE` changed from `mongodb` to `hybrid`
- `update_pattern()` and `delete_pattern()` now use ClickHouse/Redis instead of MongoDB APIs

### Documentation
- Fixed README.md: updated container tags (v2.0.0 → v3.4.0), test counts (185 → 445+), broken doc links
- Fixed ARCHITECTURE_DIAGRAM.md: single instance on port 8000, correct ClickHouse columns, added FilterPipelineExecutor
- Updated MODE_SWITCHING.md: removed MongoDB mode, hybrid is the only architecture
- Updated known-issues.md: refreshed test counts and removed stale September 2025 issues

## [3.4.0] - 2026-03-15

### Added
- **Database Authentication**: Optional authentication support for ClickHouse, Redis, and Qdrant

### Fixed
- Prevent empty Qdrant API key from blocking all vector operations

## [3.3.1] - 2026-03-10

### Fixed
- Minor stability improvements

## [3.3.0] - 2026-02-20

### Added
- **Redis OOM Protection**: Comprehensive memory monitoring and Redis protection
- **Manager Enhancements**: Memory monitoring command for kato-manager.sh
- **Request Limit**: Increased uvicorn request limit from 10k to 100k for training workloads

### Fixed
- Use `_run_async_in_sync` for vector sync wrappers to prevent event loop crash
- Recreate ClickHouse schema after clean-data command

## [3.2.1] - 2026-01-28

### Fixed
- Prevent ClickHouse system log bloat causing memory exhaustion

### Added
- Semantic version display in kato-manager.sh status command

## [3.2.0] - 2026-01-15

### Added
- **Single-Symbol Predictions**: 1+ STM prediction support with fast path optimization (previously required 2+ symbols)

### Fixed
- Remove DEBUG prefixes from production INFO-level logs

## [3.1.2] - 2025-12-20

### Fixed
- Remove DEBUG prefixes from production INFO-level logs

## [3.1.1] - 2025-12-16

### Fixed
- Resolve critical deployment configuration bugs for fresh installations
- Auto-create Docker network in deployment package

## [3.1.0] - 2025-12-12

### Added
- **Fuzzy Token Matching**: Token-level similarity matching with configurable threshold (0.0-1.0)
  - Uses RapidFuzz for 5-10x faster similarity calculation vs difflib
  - Configurable via `fuzzy_token_threshold` parameter (default: 0.0, disabled)
  - New `anomalies` field in predictions tracking fuzzy matches with similarity scores
  - Handles typos, misspellings, and minor token variations
  - Recommended threshold: 0.85 for balanced fuzzy matching
  - Complete documentation across 9 documentation files

### Changed
- Removed exception masking in metric calculations for better error visibility

### Documentation
- Updated reference docs: configuration-vars.md, session-configuration.md, prediction-object.md
- Updated API docs: api/configuration.md, api/predictions.md
- Updated research docs: pattern-matching.md
- Updated user docs: configuration.md, predictions.md

## [3.0.2] - 2025-11-13

### Added
- Container image versioning with semantic version tags
- OCI-compliant image labels for metadata
- `build-and-push.sh` script for automated multi-tag builds
- `bump-version.sh` utility for version management
- CHANGELOG.md for version history tracking
- RELEASING.md for release process documentation

### Changed
- Standardized version to 3.0.2 across all files (pyproject.toml, setup.py, __init__.py)
- Enhanced Dockerfile with version build arguments

## [2.0.0] - 2025-10-31

### Added
- **GPU Optimization Foundation**: CUDA-accelerated pattern matching with cuPy integration
- **Token-level Pattern Matching**: Configurable matching mode with exact difflib compatibility
- **Standalone Deployment Package**: Pre-built container images for simplified deployment
- **Session Auto-Extension**: Sliding window session expiration for long-running tasks
- **WebSocket Event Notifications**: Real-time session monitoring and updates
- **Session Isolation**: Complete STM isolation per user session with Redis-backed state
- **Write Guarantees**: MongoDB majority write concern to prevent data loss

### Changed
- **FastAPI Architecture**: Direct embedding of KATO processor (removed REST/ZMQ complexity)
- **Vector Database**: Migrated from linear search to Qdrant (10-100x performance improvement)
- **HTTP Client**: Migrated from aiohttp to httpx for 100% reliable concurrent requests
- **Configuration Optimization**: Tuned for hierarchical training workloads

### Fixed
- Broken performance benchmark in RapidFuzz unit tests
- KATO_SERVICES_RUNNING gate interference in RapidFuzz tests
- Prediction computation when `process_predictions=False`
- Missing asyncio import in sessions endpoint
- Session expiration during long-running training operations
- Race condition in session lock creation causing lost observations
- Event alignment for missing/extras fields in predictions
- Resource cleanup on processor eviction
- Missing trace_context context manager causing ImportError

### Performance
- 3.57x throughput improvement
- 72% latency reduction
- Comprehensive CPU optimizations
- Connection retry logic for improved reliability
- Optimized session storage (TTL-only updates to prevent race conditions)

### Documentation
- Documented observe_sequence emotives and metadata placement behavior
- Comprehensive logging technical debt cleanup
- Enhanced API endpoint documentation

## [1.0.0] - 2024-09-15

### Added
- Initial public release
- Core KATO processor with deterministic learning
- MongoDB pattern storage with SHA1-based pattern identification
- Basic vector storage with linear search
- FastAPI service with core endpoints
- Multi-modal support (strings, vectors, emotives)
- Temporal prediction with past/present/future segmentation
- Auto-learning modes (CLEAR and ROLLING)
- Docker Compose deployment with MongoDB, Redis, and Qdrant

### Features
- Deterministic pattern learning and recall
- Emotive context tracking with rolling windows
- Pattern metadata with set-union accumulation
- Short-term and long-term memory architecture
- Configurable recall thresholds
- Pattern frequency tracking
- Session-based configuration

---

## Version History

- **3.4.0** (2026-03-15): Database authentication support
- **3.3.0** (2026-02-20): Redis OOM protection, memory monitoring
- **3.2.0** (2026-01-15): Single-symbol predictions, ClickHouse memory fix
- **3.1.0** (2025-12-12): Fuzzy token matching with RapidFuzz
- **3.0.2** (2025-11-13): Container image versioning
- **2.0.0** (2025-10-31): Major architecture modernization, GPU support, performance optimizations
- **1.0.0** (2024-09-15): Initial public release

---

## Upgrade Notes

### Upgrading to 2.0.0

**Breaking Changes:**
- API endpoint migration to session-based architecture
- FastAPI direct embedding (removed REST/ZMQ services)
- Vector database change from custom implementation to Qdrant

**Migration Steps:**
1. Update docker compose.yml to use new service configuration
2. Migrate existing patterns to Qdrant (migration script provided)
3. Update client code to use session-based endpoints
4. Review and update configuration for new defaults

**Compatibility:**
- Automatic session middleware provides backward compatibility for non-session endpoints
- Existing pattern data can be migrated without loss

---

## Contributing

When adding entries to the CHANGELOG:
1. Add unreleased changes under `[Unreleased]` section
2. Categorize changes: Added, Changed, Deprecated, Removed, Fixed, Security, Performance, Documentation
3. Use present tense ("Add feature" not "Added feature")
4. Reference issue numbers when applicable
5. On release, move `[Unreleased]` entries to new version section with date
