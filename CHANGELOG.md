# Changelog

All notable changes to KATO will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
