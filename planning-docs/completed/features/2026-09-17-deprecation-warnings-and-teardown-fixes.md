# Deprecation Warnings Cleanup + Resource-Teardown Bug Fixes

**Completed**: 2026-09-17
**Status**: Implementation COMPLETE and verified. **NOT YET COMMITTED** — sits as uncommitted working-tree changes on local branch `perf/prediction-path-scaling`, which currently points at the same commit as `main` (`adc066d`, no divergent history) — effectively uncommitted changes on top of `main`.
**Type**: Bug Fix (3 latent resource-teardown defects) + Maintenance (deprecation-warning cleanup following the 5.1.1/5.1.2 dependency upgrade)
**Time**: Not tracked against an estimate (ad-hoc follow-up work, not a backlog item)

## Trigger

Following the 5.1.1/5.1.2 dependency-related releases, the codebase was emitting `DeprecationWarning`s on import and at runtime. The user asked to clear these. While rewriting the affected code, three latent resource-teardown bugs were found in the same functions being touched and fixed alongside.

## Files Modified

- `kato/services/kato_fastapi.py` — `@app.on_event` → `lifespan` context manager; shutdown bug fixes
- `kato/sessions/redis_session_manager.py` — `close()` → `aclose()`
- `kato/storage/pattern_cache.py` — `close()` → `aclose()`
- `kato/storage/redis_streams.py` — `close()` → `aclose()`
- `kato/storage/metrics_cache.py` — new `close()` + `close_metrics_cache_manager()`
- `kato/exceptions/handlers.py` — docstring updated to reference `lifespan` instead of `on_event`
- `requirements.txt` / `requirements.lock` — `anyio` floor raised to `>=4.10,<4.15` (locked 3.7.1 → 4.14.2, `sniffio` dropped); `redis` floor raised to `>=5.0.1`
- `tests/requirements.txt` — `httpx2` added; `redis` floor aligned to `>=5.0.1`
- `tests/tests/unit/test_error_handlers.py` — `test_late_registration_is_ignored` rewritten against a `lifespan` context manager instead of `on_event`
- `CHANGELOG.md` — `[Unreleased]` Changed/Fixed entries added (already written as part of this change, not yet promoted to a version)

## What Changed

### 1. `@app.on_event` → `lifespan` (`kato/services/kato_fastapi.py`)
`startup_event`/`shutdown_event` became plain `_startup()`/`_shutdown()` coroutines, driven by an `@asynccontextmanager lifespan(app)` passed to `FastAPI(lifespan=lifespan, ...)`. Startup and shutdown step **order is unchanged**; shutdown keeps its existing per-step try/except-and-continue behavior so one failing teardown step doesn't block the rest.

`setup_error_handlers(app)` **deliberately stays at module scope**, not moved into `_startup`. Starlette snapshots `app.exception_handlers` into its middleware stack the first time the app is called (which includes dispatching the lifespan scope) — registering handlers from inside `lifespan` would be exactly as dead as the old `@app.on_event("startup")` registration was (this was in fact the root cause of the dead-error-handling-layer bug fixed in Remediation Pass 1, see DECISION-030). `kato/exceptions/handlers.py`'s docstring was updated to describe this in terms of `lifespan` rather than the now-removed `on_event`.

**Consequence for future work**: `@app.on_event` on this app is now a silent no-op (FastAPI still parses it but the app never dispatches through the old path). Any new startup/shutdown work must go in `_startup`/`_shutdown`.

### 2. Redis async `close()` → `aclose()`
redis-py deprecated the async `close()` method starting at 5.0.1. Updated at three call sites: `RedisSessionManager.shutdown()`, `pattern_cache.py`'s cache manager cleanup, `redis_streams.py`. The **synchronous** client in `kato/storage/connection_manager.py` is deliberately untouched — `close()` is not deprecated on the sync client, only the async one.

### 3. `httpx2` + `anyio` floor
starlette's `TestClient` prefers `httpx2` and warns on the `httpx` fallback; `httpx2` added to `tests/requirements.txt` (plain `httpx` is kept too — `qdrant-client` depends on it, as does `tests/tests/fixtures/kato_session_client.py`). `anyio` floor raised to `>=4.10,<4.15` in both `requirements.txt` and the lock (3.7.1 → 4.14.2; the 3.7.1 pin was stale, not deliberate — nothing under `kato/` imports anyio directly, and `httpcore[asyncio]` already wanted `>=4.0`). **The `<4.15` cap is measured, not cautionary**: anyio 4.15.0 deprecates the `anyio.abc.BlockingPortal` alias that `starlette/testclient.py` still imports, so going past 4.15 would just trade the old httpx warning for a new, currently-unfixable one. Drop the cap once starlette moves to `anyio.from_thread.BlockingPortal`. Only `anyio` moved in the regenerated lock section (`sniffio` dropped out as an anyio-3-only dependency); nothing else shifted.

### 4. Test rewrite
`tests/tests/unit/test_error_handlers.py::test_late_registration_is_ignored` now proves the same negative (a handler registered after the app has been dispatched once is silently ignored) against a `lifespan` context manager instead of `on_event`. Assertions unchanged.

## Bugs Fixed (all latent, all found in the code being rewritten)

1. **Session manager was never shut down.** Shutdown guarded on `hasattr(session_manager, 'close')`, but neither `RedisSessionManager` nor the in-memory `SessionManager` has ever defined `close()` — both define `shutdown()`. The guard was therefore always false, and shutdown silently did nothing: the Redis connection pool and the session cleanup task leaked on every process restart. Fixed to call `shutdown()`, and to read the private `_session_manager` attribute rather than the lazy property, so teardown can no longer construct a session manager the process never actually used.
2. **Concurrency reporter task was unmanaged.** `asyncio.create_task(...)` discarded its handle; the task was never tracked or cancelled, so it was torn down abruptly (or leaked) whenever the loop closed rather than being cancelled cleanly. The handle is now kept and cancelled first during shutdown, before anything the task might depend on is torn down.
3. **`MetricsCacheManager` leaked its Redis client.** It opened a `redis.asyncio` client in `initialize()` with no teardown path at all. Added `close()` plus a module-level `close_metrics_cache_manager()` that also drops the singleton (so a later `get_metrics_cache_manager()` call re-initializes cleanly instead of returning a closed client); wired into `_shutdown()`, guarded so calling it doesn't itself construct the manager during teardown.

## Verification Performed

- `python -W error::DeprecationWarning -c "import kato.services.kato_fastapi"` — clean, both in the local venv and inside the rebuilt Docker image (Python 3.10, anyio 4.14.2 confirmed installed).
- Drove the real ASGI lifespan protocol in-process against live services: startup step order preserved, shutdown step order preserved, and the shutdown log now contains `RedisSessionManager shutdown complete` / `Session manager shut down` — lines that **never appeared before this fix** (direct evidence bug #1 is real and now fixed). Confirmed the concurrency reporter task is not leaked.
- Full local suite: `tests/tests/unit/` — 431 passed, 1 failed; `tests/tests/integration/` + `tests/tests/api/` — 177 passed, 1 failed, 1 skipped.
- **Both failures independently verified pre-existing**, unrelated to this change: reproduced identically against a clean `git stash` of `HEAD` (i.e. before any of this work), and the Docker service under test still runs the published 5.1.2 image.
  - `test_determinism_preservation.py::test_multiple_model_interaction_determinism` — flaky under full-suite load; passes 3/3 in isolation.
  - `test_session_management.py::TestSessionErrorHandling::test_concurrent_session_modifications` — exercises concurrent writers to a single session, which `CLAUDE.md`/`docs/users/session-management.md` document as an unsupported configuration (same root cause family as DECISION-024's documented one-writer-per-session limitation).
- CI dependency install order simulated fresh in `python:3.10-slim`: `anyio` resolves to 4.14.2, `pip check` clean.
- `ruff check` clean on every changed file.

## Known Follow-Ups (not yet actioned, logged to `SPRINT_BACKLOG.md`)

1. `SessionManager.shutdown()` cancels `_cleanup_task` but never resets the attribute to `None`, while `get_or_create_session` only restarts the cleanup loop `if not self._cleanup_task`. Inert today (one `lifespan` per process, so `shutdown()` is only ever called once before process exit) but a one-line hardening worth doing opportunistically.
2. Two competing pytest configs exist: `pyproject.toml`'s `[tool.pytest.ini_options]` (carries `--disable-warnings`) and `tests/pytest.ini` (does not). `tests/pytest.ini` wins for the normal `./run_tests.sh` invocation, which is exactly why these deprecation warnings became visible in the first place. Worth consolidating to one config so warning visibility is a deliberate choice, not an accident of which config file pytest picks up.
3. `tests/tests/integration/test_session_management.py::test_concurrent_session_modifications` asserts behavior that `CLAUDE.md` documents as unsupported (single-writer-per-session) — the test, not the code, is likely the thing that needs to change (e.g. to an `xfail`, matching the treatment `test_concurrent_session_modifications` under multi-worker topology already got per DECISION-024/DECISION-030).
4. Drop the `anyio<4.15` cap once starlette moves to `anyio.from_thread.BlockingPortal` (tracked upstream; re-check on the next starlette bump).

## Open Question for the User

This work is complete and verified but **not committed**. It sits as uncommitted changes in the working tree while the current local branch (`perf/prediction-path-scaling`) points at the same commit as `main` — no divergent commit history exists yet, so this is effectively "uncommitted changes on top of `main`." A commit/branch decision is needed: commit directly, or via a dedicated branch and merge. See `planning-docs/project-manager/pending-updates.md`.

## Related

- Extends the module-scope `setup_error_handlers(app)` placement established during Remediation Pass 1 (see DECISION-030 in `planning-docs/DECISIONS.md`) — this change had to preserve that placement exactly, for the same Starlette middleware-snapshot reason.
- Separately noted (not addressed by this work): `planning-docs/SESSION_STATE.md`'s most recent dated entry before this one was 2026-09-16; KATO was released as v5.1.1 and v5.1.2 on 2026-09-17 (per `CHANGELOG.md` and `kato/__init__.py`), and a benchmark script (`adc066d` "bench: add a repeatable end-to-end prediction scaling benchmark") was committed the same day — none of that is documented in planning-docs. Flagged as a documentation-gap item in `pending-updates.md` rather than reconstructed here, since this agent has no first-hand record of that work's rationale or verification.
