# Remediation Pass 1 — High-Value, Low-Risk Fixes

**Completed**: 2026-09-16
**Branch**: `chore/remediation-pass-1` (uncommitted, not merged — see "Status" below)
**Base**: v5.0.2, commit `bf14579`
**Decision**: DECISION-030 (`planning-docs/DECISIONS.md`)
**Type**: Bug Fix + Security Hardening + Performance + Dead Code Removal + CI

## Background
Triggered by a comprehensive review of the repo for technical debt, security vulnerabilities, and performance. The user set explicit scope: trusted-network deployment (authentication work deferred), exact-safe filters only (the default `filter_pipeline` stays `[]` — not touched), "quick wins first, then re-assess" (structural work deferred), and delete `kato/gpu/`.

## Delivered

### Live bugs found and fixed
1. **KATO's structured error-handling layer was dead in production.** `setup_error_handlers(app)` was called from inside `@app.on_event("startup")` in `kato/services/kato_fastapi.py`. Starlette builds its middleware stack on the first `__call__` and copies `app.exception_handlers` into a fresh dict at that point, so handlers registered afterward are silently ignored — proven with a minimal repro inside the running container (starlette 0.48.0). All of `kato/exceptions/handlers.py` never ran; KATO exceptions escaped as plain 500s. Fixed by registering at module scope. Deliberately scoped: only `KatoV2Exception` and the `Exception` catch-all are registered, leaving `HTTPException`/`RequestValidationError` on FastAPI's defaults so the existing flat `{"detail": ...}` response shape is unchanged (verified live). New `include_http_handlers=True` parameter makes taking those over an explicit opt-in.
2. **Every `ValidationError` raise site was a `TypeError`.** 12 sites across `kato/workers/observation_processor.py` and `kato/workers/pattern_operations.py` passed the message positionally *and* `field_name=` as a keyword; `ValidationError.__init__`'s first positional is `field_name`, so every raise produced `TypeError: got multiple values for argument 'field_name'` instead of a `ValidationError`. Masked by bug 1 (everything became a 500 anyway regardless). Fixed by passing `message=` explicitly at all 12 sites.
3. **LRU processor eviction permanently deleted a live tenant's vectors.** `ProcessorManager._evict_oldest()` called `delete_collection()` unconditionally on `vectors_{processor_id}`, which is persistent per-node storage, not a cache. Now gated on a `test_` prefix, matching the pattern-database branch directly below it and the TTL path.
4. **Unbounded Redis leak.** `RedisWriter.write_prediction` used `set()` with no TTL — one key per observation, forever. 4,464 such keys (TTL `-1`) were found live, ~11% of the 38,902-key database at audit time. Now uses `setex` with the session TTL (verified: new keys get TTL 3598s). The pre-existing 4,464 orphan keys were deliberately **not** cleaned up — needs the user's go-ahead (see "Status" below).
5. **`KatoProcessor.get_stm()` called `MemoryManager.get_stm_state()`, which does not exist** — any call raised `AttributeError`. Zero callers found; deleted.
6. **`delete_pattern` reported success after a failed delete** — it removed the RAM copy then swallowed ClickHouse/Redis failures with `logger.warning`, leaving the pattern in storage while the caller believed it was gone. Now propagates the failure.
7. **`POST /sessions/{id}/config` bypassed all validation** — a `setattr` loop wrote attributes directly, never calling `SessionConfiguration.validate()`, so out-of-range filter parameters reached the query layer and identity fields like `node_id` could be overwritten via config update. Now routed through the existing `SessionConfiguration.update()` (validates + rolls back atomically on failure), returning 400 for invalid input. Verified live.

### Security
- **SQL parameterization.** User-controlled values were reaching ClickHouse as literal text: an observation token in `WHERE first_token = '{symbol}'` (`pattern_processor.py`), STM tokens concatenated into an array literal (`jaccard_filter.py`), plus `kb_id`/pattern-name interpolation in `clickhouse_writer.py` and `filters/executor.py`. All converted to server-side bound parameters (`parameters={...}`), matching the shape already used correctly by `ClickHouseWriter.get_pattern_metadata_batch`. New `get_query_parameters()` hook on `PatternFilter` carries filter bind values. Verified live: an adversarial `UNION ALL` symbol now returns clean empty predictions (HTTP 200) instead of leaking rows.
- **New module `kato/storage/identifiers.py`**, an allowlist (`^[A-Za-z0-9_]{1,60}$` for `kb_id`, `^[0-9a-f]{40}$` for pattern names) for the handful of statements that cannot bind parameters (`DROP PARTITION`, `ALTER ... DELETE`).
- **`ProcessorManager._get_processor_id` blacklist replaced with an allowlist.** The old 14-character blacklist did not include the single quote, tab, or newline. Verified against the live stores that all 266 existing `kb_id`s already satisfy the new rule, so nothing is orphaned by the tightening; normal node ids sanitize identically before and after.
- **CORS**: `allow_credentials` set to `False` — with `allow_origins=["*"]`, Starlette reflects the caller's `Origin` header, making every origin trusted for credentialed requests. Verified live.
- **Backing stores bound to `127.0.0.1`** in `docker-compose.yml` (Redis 6379, ClickHouse 8123/9000, Qdrant 6333) — none have authentication enabled by default, and ClickHouse was answering unauthenticated queries from the host. `protected-mode no` removed from `config/redis.conf` after verifying empirically that with an explicit `bind` directive, container-to-container access still works. These compose/redis.conf changes only take effect on the next full stack recreate — only the `kato` service was recreated during this work (see "Status").

### Performance (prediction output unchanged)
- Removed an `asyncio.Lock` acquired twice per request in `concurrency_monitor_middleware` — pure overhead on a single-threaded event loop, and a violation of the project's no-locks rule.
- Hoisted `get_metadata_batch()` above the `asyncio.gather` batch split in `pattern_search.py` — it is a synchronous ClickHouse+Redis call, so N gathered batches were serializing N ClickHouse queries and N Redis `MGET`s where one of each suffices.
- Added the missing `kb_id` predicate to the startup `SELECT COUNT(*) FROM kato.patterns_data` (it was counting every tenant's rows, not just the current node's).
- Replaced `pattern_symbols.count(symbol)` inside a loop with `collections.Counter` (O(n²) → O(n)); also makes float summation order deterministic, where `set` iteration previously was not.
- Removed unconditional f-string logging from hot paths, including a leftover `logger.error(f"!!! DEBUG: ...")` on every config update.

### Dead code removed (~10,100 deleted lines total)
`kato/gpu/` + `kato/config/gpu_settings.py` + `tests/tests/gpu/` + `docs/developers/gpu/` (zero importers; its encoder still targeted the removed MongoDB layer); `kato/sessions/session_middleware.py` and `session_middleware_fixed.py`; `kato/storage/connection_pool_monitor.py`; `kato/auxiliary/`, `kato/scripts/`, `kato/utils/`; `kato/sessions/redis_session_store.py` (closes the `pickle.loads` finding recorded in `docs/maintenance/security-review-baseline.md:22`). `session_middleware_simple.py` renamed to `session_middleware.py`. **Correction to an earlier in-pass assessment**: `tests/tests/integration/test_redis_sessions.py` was NOT deleted — it also covers the live `RedisSessionManager`; only its dead `TestRedisSessionStore` class (4 tests, tied to the deleted store) was removed.

Also: `MemoryError` and `TimeoutError` in `kato/exceptions/__init__.py` shadowed Python builtins (`handlers.py` imported the KATO `TimeoutError`, shadowing the builtin for that whole module, while `websocket/event_broadcaster.py` raises the builtin one). Renamed to `MemoryOperationError` (already the name every caller used via an alias) and `KatoTimeoutError`.

### Hygiene and CI
- `.gitignore` was corrupt: `*.nvvp` had lost its trailing newline and merged into the next line, producing the nonsense pattern `*.nvvptests/tests/unit/test_debug_predictions.py` — neither pattern worked. Fixed; `logs/test-runs/` (107 tracked files) and `benchmark_results.json` untracked and ignored.
- Dropped the unused `aioredis` dependency from `requirements.txt` (no importer anywhere; everything uses `redis.asyncio`). **`requirements.lock` still needs regeneration** with `pip-compile` — not done as part of this pass (see "Status").
- Removed the `mongo:4.4` service, `MONGO_BASE_URL`, and the mongo volume/healthcheck from `docker-compose.test.yml`.
- Fixed 5 `F821 undefined-name` errors (`'SessionState'` annotations with no import) in `kato_processor.py` via a `TYPE_CHECKING` import.
- Corrected `CLAUDE.md:148` (`qdrant_manager.py` → `qdrant_store.py`).
- **New `.github/workflows/ci.yml`**: ruff + bandit + unit tests. There was previously **no Python CI at all** (only `helm.yaml`), and `.git/hooks/` was empty so `.pre-commit-config.yaml` had never run in this clone. ruff went from 282 errors in `kato/` to passing; bandit passes with no issues. A clearly-labelled LINT BACKLOG ignore list in `pyproject.toml` parks the remaining stylistic categories (UP006/UP035 typing migration, N8xx from the camelCase legacy API) so the correctness rules (the F category: undefined names, unused imports/variables) are enforced from now on.

### New tests (43)
`tests/tests/unit/test_error_handlers.py` (7), `test_identifier_validation.py` (23), `test_observation_validation.py` (10), `test_processor_eviction.py` (3). The error-handler and eviction guards were each proven to fail when their fix is reverted.

## Verification
Full suite: **588 passed, 3 skipped, 1 xfailed, 0 failed (689.83s)**, up from the 552-passed baseline (552 + 40 new − 4 removed = 588 exactly; 3 more eviction tests were added after that count was struck and a final re-run was in progress at write-up time — see "Status"). ruff and bandit clean. Live verification against the running deployment stack (`kato` service recreated on the rebuilt `kato:latest` image): HTTPException response shape unchanged, CORS credentials header gone, config validation rejecting out-of-range values, adversarial SQL symbol returning clean results, and prediction-key TTL set correctly.

## New issue found, NOT fixed (needs its own change)
**Session-level `sort_symbols` has no effect.** `kato/workers/observation_processor.py` resolves the session's `sort_symbols` from config at ~line 358 and nothing reads it; the actual sorting (~lines 181/210) uses `self.sort_symbols`, the processor's construction-time default. Since a processor is per-node and shared across sessions, a per-session `sort_symbols`/`use_token_matching` override does not take effect for any session after the first on that node. Not fixed here because it changes pattern hashes. Marked in the code with a `# noqa: F841` and an explanatory comment so it stays visible. Filed as a new Bug entry in `planning-docs/SPRINT_BACKLOG.md`.

## Deferred (explicitly out of scope for this pass — the re-assess list)
- Default `filter_pipeline` is still `[]`, so every prediction still scans the node's whole corpus and all of `kato/filters/` is unreachable by default. The exact-safe route identified: derive `LengthFilter` bounds from `recall_threshold` (`T·L/(2−T) ≤ P ≤ L·(2−T)/T`), pending confirmation the bound holds for `weighted_similarity`.
- Per-request `PatternSearcher` construction swapped onto the shared processor — a real cross-request config race for concurrent predicts on one node.
- Synchronous redis/clickhouse clients blocking the event loop (the throughput ceiling).
- Per-request `ProcessPoolExecutor`.
- `conditional_probability_cached` md5-hashing the whole symbol table per prediction.
- The unreachable legacy stateful cluster (~400 lines, zero callers).
- 25 `pytest.skip("KATO services not available")` calls that make a green run potentially misleading.
- Unbounded request payloads.
- Authentication and tenant binding — `node_id` comes from a client header with no verification and IS the tenant boundary. Explicitly deferred per the user's trusted-network scoping decision for this pass.
- The 4,464 orphan Redis prediction keys (see bug 4 above).

Filed as a single consolidated Backlog entry in `planning-docs/SPRINT_BACKLOG.md` ("Follow-up: Remediation Pass 1 — Deferred Items (Re-assess List)").

## Status — nothing committed, four items need the user's decision
This entire pass is **uncommitted, working-tree-only, on branch `chore/remediation-pass-1`** (not merged to `main`). Four things still need the user's explicit go-ahead before this can be considered fully closed:
1. **Whether/when to commit and merge** `chore/remediation-pass-1`.
2. **`requirements.lock` regeneration** (`pip-compile --output-file=requirements.lock requirements.txt`) after the `aioredis` removal — not run.
3. **The 4,464 pre-existing orphan Redis prediction keys** — cleanup script not written/run; deliberately left for the user to approve given past Redis-data-loss history on this project (see `redis_persistence_data_loss_2026_04_13.md` in project memory).
4. **A full stack recreate** to pick up the `docker-compose.yml`/`config/redis.conf` binding changes — only the `kato` service was recreated during live verification; Redis/ClickHouse/Qdrant are still running under their pre-change container config until a full `docker compose down && docker compose up -d` (or equivalent) is done.

See `planning-docs/project-manager/pending-updates.md` for the corresponding human-alert entries.

## Related
- DECISION-030 (`planning-docs/DECISIONS.md`) — full scope decision and rationale.
- `docs/maintenance/security-review-baseline.md` — the `pickle.loads` finding this pass's `redis_session_store.py` deletion closes.
