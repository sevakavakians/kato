# Refactor: Configuration Audit, Wiring, and Dead-Parameter Removal

*Completed: 2026-09-09*
*Status: FIXED*
*Decision: DECISION-017 (`planning-docs/DECISIONS.md`)*

## Summary
Full audit of every `Settings` field in `kato/config/settings.py` and every documented/`KATO_*` env var in the codebase, checked against two questions: does the name actually bind (pydantic-settings v2 resolution, or a raw `os.getenv()`), and does the resulting value actually have a consumer anywhere. 29 files changed, +666/-1950. Corrects and resolves the P2 backlog item "dead `KATO_*` env names" originally logged 2026-09-08 (see `planning-docs/SPRINT_BACKLOG.md`), which understated how dead `KATO_BATCH_SIZE` actually was and wrongly implied a lost-performance impact.

## Corrected Understanding (vs. the original 2026-09-08 backlog framing)
The original item said `KATO_BATCH_SIZE=10000` in `docker-compose.yml` "has no effect; the container runs with `batch_size=1000` regardless" — implying real throughput was left on the table. That framing was inaccurate on two counts:
1. **Root cause was broader than one binding bug.** `KATO_BATCH_SIZE` was dead on two independent levels: (a) `json_schema_extra={'env': 'KATO_BATCH_SIZE'}` is a pydantic-v1 idiom pydantic-settings v2 does not read for env-var resolution, so the name never bound; **and** (b) `settings.performance.batch_size` had **zero consumers anywhere** in the codebase — no code ever read the field, bound or not.
2. **There was never a performance impact.** Since nothing read the value, "runs with `batch_size=1000` instead of `10000`" was never true in any sense that mattered — the field's value, whatever it resolved to, did nothing.
3. **`KATO_VECTOR_BATCH_SIZE` was a genuinely different case**: it bound correctly via a raw `os.getenv()` call in `kato/config/vectordb_config.py` (not the broken `json_schema_extra` idiom) — but the attribute it set also had no consumers, so it was equally inert for a different reason.

## Key Finding: Batching Already Exists, Server-Side
KATO already gets pattern-write batching from ClickHouse's **server-side async_insert** (`kato/storage/clickhouse_writer.py` sets `async_insert=1, wait_for_async_insert=0`), which coalesces inserts in ClickHouse's own queue across **all** uvicorn workers. Client-side buffering is deliberately disabled: `DEFAULT_BATCH_SIZE=1`. Commit `f809a84` changed this from 50 to 1 as a **correctness fix** — a per-worker client-side buffer holds rows in one worker's process memory, invisible to the others, so predictions issued against a different worker could miss a just-learned pattern until that worker's buffer happened to flush ("orphaned rows").

**Consequence for this change**: wiring `settings.performance.batch_size` up to actually control client-side batching would have **re-introduced** the exact bug `f809a84` fixed. It was deleted rather than wired, and the reasoning is recorded in DECISION-017 specifically so a future contributor does not "helpfully" re-add a batch-size knob.

**Git archaeology**: `performance.batch_size` was born already-dead in `f1c862d` (bulk config scaffold — no consumer was ever added at any point in its history). `KATO_BATCH_SIZE=10000` was added to `docker-compose.yml` by `935faf0`, tuning a variable nothing read.

## Bugs Fixed
1. **`/concurrency` endpoint under-reported capacity 4x.** `kato_fastapi.py` and `monitoring.py` read `UVICORN_WORKERS` / `UVICORN_LIMIT_CONCURRENCY` — names uvicorn never exports as env vars. The real names, expanded in the Dockerfile CMD, are `KATO_WORKERS` / `KATO_LIMIT_CONCURRENCY`. The endpoint always reported `workers=1, total_capacity=100` regardless of the actual worker count. Now correctly reports the true `4` / `400` — verified live against the running container. A new exported `WORKER_COUNT` constant centralizes this so both call sites read the same source of truth.
2. **Documented env names that never bound now work**, via `validation_alias=AliasChoices` on the affected `Settings` fields: `KATO_USE_TOKEN_MATCHING`, `KATO_FUZZY_TOKEN_THRESHOLD`, `KATO_USE_FAST_MATCHING`, `KATO_USE_INDEXING`, `KATO_CONFIG_FILE` (each now accepts both the bare field name and its documented `KATO_`-prefixed name). **`SORT` was deliberately NOT aliased** — it is a dangerously generic env name that could collide with an unrelated variable in someone's environment, and since it never worked nobody can already depend on it; the supported name remains `SORT_SYMBOLS`.

## Parameters Newly Wired
Previously documented but inert; defaults chosen to preserve existing behavior exactly except where flagged below.
- **`LOG_FORMAT` (`json`|`human`) and `LOG_OUTPUT` (`stdout`|`stderr`|path)**: `configure_logging()` in `kato/config/logging_config.py` already fully implemented JSON formatting with `trace_id`/`duration_ms` and stream selection — it was simply never called anywhere. Now called from `AppState.__init__`. **Behavior change to note**: logs now go to stdout by default; previously `logging.basicConfig` sent them to stderr.
- **`CONNECTION_POOL_SIZE`**: now sets Redis `max_connections` per worker. Default changed 10 → 200 to match the value that was already hardcoded in `connection_manager.py`. The compose entry `CONNECTION_POOL_SIZE=50` was **removed deliberately** — honoring it as-is would have cut the effective pool from 200 down to 50.
- **`REQUEST_TIMEOUT`**: now sets the ClickHouse send/receive timeout (previously hardcoded at 30, and the field's own default is also 30, so no default-value change). The compose entry `REQUEST_TIMEOUT=120.0` was **kept** and now genuinely applies — a deliberate, flagged behavior change from the previously-ignored 30s hardcode.
- **`fuzzy_token_threshold`**: now flows from `settings` into `configuration_service`'s default configuration; previously reachable only through per-session config overrides.

## Deleted (Vestigial — Would Provide No Value Even If Wired)
- **Settings fields**: `performance.batch_size`, `use_optimized`, `vector_batch_size`, `vector_search_limit`; `learning.auto_learn_enabled`, `auto_learn_threshold` (auto-learn is driven solely by `MAX_PATTERN_LENGTH`); `service.service_version`; `database.QDRANT_COLLECTION_PREFIX` (collection names are always `vectors_{processor_id}`, prefix is never applied); the **entire `APIConfig` class** (host/port/workers/CORS/docs/max_request_size are all hardcoded directly in FastAPI and the uvicorn CMD) plus `Settings.api` and `get_api_config()`.
- **Dead env reads**: `KATO_ARCHITECTURE_MODE` (assigned to a local variable that was never used — hybrid is the only architecture KATO supports), `KATO_STRICT_MODE` (zero readers), and the inert `KATO_VECTOR_BATCH_SIZE` / `KATO_VECTOR_SEARCH_LIMIT` / `QDRANT_COLLECTION` reads in `vectordb_config.py`.
- **4 zero-importer modules deleted entirely**: `kato/config/database.py` (181 lines), `kato/config/api.py` (343 lines), `kato/config/user_config.py` (194 lines), `kato/storage/query_batcher.py` (299 lines).
- **Removed from**: `docker-compose.yml`, `deployment/docker-compose.yml`, the Helm configmap and `values.yaml`, and 14 documentation files.

## Verification
- `ruff` clean on all edited files (net -4 findings overall, exactly matching the deleted modules' prior findings)
- Settings load successfully; all `vectordb_config.py` `EXAMPLE_CONFIGS` validate
- Image rebuilt (`docker compose build --no-cache kato`), container restarted
- `/concurrency` confirmed reporting the true `4` workers / `400` total capacity, live
- Vector observe + learn + count round trip returned 200 end-to-end
- Full suite (`./run_tests.sh --no-start --no-stop`): **451 passed, 4 skipped, 4 failed** — best result this session; all 4 failures are the already-known multi-worker websocket/session issues tracked separately in `planning-docs/SPRINT_BACKLOG.md`

## Files Modified
29 files, +666/-1950. Concentrated in:
- `kato/config/settings.py` (alias wiring, field deletions, `APIConfig` removal)
- `kato/config/vectordb_config.py` (dead env reads removed)
- `kato/config/logging_config.py` / `AppState.__init__` (LOG_FORMAT/LOG_OUTPUT wiring call site)
- `kato/services/kato_fastapi.py`, monitoring module (`/concurrency` fix, `WORKER_COUNT` constant)
- `kato/services/connection_manager.py` (CONNECTION_POOL_SIZE default)
- `kato/storage/clickhouse_writer.py` (REQUEST_TIMEOUT wiring)
- `kato/services/configuration_service.py` (fuzzy_token_threshold default flow)
- 4 deleted modules: `kato/config/database.py`, `kato/config/api.py`, `kato/config/user_config.py`, `kato/storage/query_batcher.py`
- `docker-compose.yml`, `deployment/docker-compose.yml`, Helm configmap/`values.yaml`
- 14 documentation files (dead-parameter references removed)

## Still Open (Not Fixed By This Work — Filed as New Backlog Items)
- **P2**: Metadata sidecar write path is un-batched. `metadata_router.upsert_pattern_metadata` does a read (`get_pattern_metadata_batch`) followed by a **synchronous** insert with `wait_for_async_insert=1` (`clickhouse_writer.py:469`) for every learned pattern — two blocking ClickHouse round trips per learn. `write_pattern_metadata_batch` already exists and is correct, but is only used at finalize. This is the real remaining batching win, and needs a batched upsert call shape at the `learnPattern` level, not a config knob.
- **P3**: `has_pending` / `flush_if_pending()` / `flush_all_pending_writes()` in `clickhouse_writer.py` are permanent no-ops at `DEFAULT_BATCH_SIZE=1` and could be removed; the `__init__` docstring there still says "default: 50".
- **P3**: `CLAUDE.md` lists `PROCESSOR_ID` as a required environment variable, but nothing under `kato/` reads it (only `docker-compose.test.yml` sets it). `CLAUDE.md` was not edited as part of this change.
- **P3**: `docs/operations/security-configuration.md` documents `JWT_SECRET_KEY`/`JWT_ALGORITHM`/`JWT_EXPIRE_MINUTES`, none of which any code reads — that page is aspirational, not current-state.
- **P3**: `docs/operations/performance-tuning.md` recommends launching under gunicorn with worker-count math that ignores `KATO_WORKERS` — stale relative to the current deployment model.

## Impact
- **Severity**: No behavior-changing impact for the vast majority of deployments (defaults preserve prior effective behavior). Two deliberate, flagged behavior changes: (1) logs now default to stdout instead of stderr; (2) `REQUEST_TIMEOUT=120.0` in compose now genuinely applies to ClickHouse operations (was silently ignored before, hardcoded at 30s).
- **Scope**: Configuration layer only (`kato/config/`), plus the small number of call sites that now actually read newly-wired values, plus deployment manifests and docs. No pattern-processing logic touched.
- **Risk avoided**: Wiring `batch_size` would have silently reintroduced a real multi-worker correctness bug (orphaned pattern rows) that commit `f809a84` had already fixed. Deleting it instead removes that risk permanently and is recorded in DECISION-017 to prevent recurrence.

## Related
- `planning-docs/DECISIONS.md` — DECISION-017
- `planning-docs/SPRINT_BACKLOG.md` — corrects and resolves the prior "dead `KATO_*` env names" P2 item; new backlog items filed under "Backlog (Future Work)"
- Commit `f809a84` (client-side batch default 50→1, orphaned-row correctness fix)
- Commit `f1c862d` (bulk config scaffold — origin of the dead `performance.batch_size` field)
- Commit `935faf0` (added `KATO_BATCH_SIZE=10000` to compose)

## Completion Date
2026-09-09
