# Bug Fix: conftest.py Unconditional Redis FLUSHALL Scoped to Ephemeral Keys Only

*Completed: 2026-09-08*
*Status: FIXED*

## Summary
The session-scoped autouse fixture `flush_redis_before_tests` in `tests/tests/conftest.py` ran an unconditional `docker exec kato-redis redis-cli FLUSHALL` at the start of every test session, wiping all Redis data — including durable pattern metadata (frequency, emotives, symbol affinity) — for whatever Redis instance was configured, not just a dedicated test instance. This was an unrecoverable data-loss risk since Redis persistence protects against restarts/crashes, not against an explicit `FLUSHALL` — the destructive command gets durably persisted too. Fixed by scoping the fixture's deletions to only the three ephemeral session/STM key patterns that tests actually need cleared, leaving all durable kb_id-namespaced metadata untouched.

> **Correction (2026-09-08)**: This summary originally read "Combined with no Redis persistence enabled by default, this was an unrecoverable data-loss risk," implying Redis persistence was disabled. That was wrong — `REDIS_PERSISTENCE=true` is set in both `.env` and `deployment/.env` (unchanged since the 2026-04-13 fix), and the running container has `--appendonly yes` with `aof_enabled:1`. See `planning-docs/completed/bugs/2026-09-08-start-sh-clean-data-clickhouse-noop.md` for the full correction.

## Root Cause
`tests/tests/conftest.py:24` ran `docker exec kato-redis redis-cli FLUSHALL` unconditionally, hardcoded to the container name `kato-redis`, with no guard against that being a live/shared Redis instance. Identified 2026-09-08 during Pattern Count Endpoint verification work; tracked as a P2 backlog bug in `planning-docs/SPRINT_BACKLOG.md` pending fix.

## Fix Applied
In `tests/tests/conftest.py`:
- The `flush_redis_before_tests` fixture no longer runs `docker exec kato-redis redis-cli FLUSHALL`.
- It now deletes only ephemeral session/STM namespaces, defined in a new module constant:
  ```python
  EPHEMERAL_KEY_PATTERNS = ("kato:session:*", "stm:events:*", "stm:global")
  ```
  using `redis.Redis(...).scan_iter()` with batched deletes (batches of 1000).
- It connects via the `redis` Python client, honoring `REDIS_HOST`/`REDIS_PORT` env vars, instead of hardcoding `docker exec kato-redis`. The `subprocess` import was removed; `os` and `redis` were added.
- `KATO_TEST_REDIS_FLUSHALL=1` is a new opt-in escape hatch that restores the full FLUSHALL behavior, with a warning printed when used. Documented in-file as "only for a Redis dedicated to testing".
- Comments in the file record why the scoping is safe: all durable pattern metadata is namespaced under `kb_id` (`<kb_id>:frequency:*`, `:symbols:freq`, `:symbols:pmf`, `:symbol_to_patterns:*`, `:affinity:*`, `:global:*`, `:prediction:*` per `kato/storage/redis_writer.py`), which cannot match any of the three ephemeral patterns.

## Verification
- Seeded durable metadata keys — including the adversarial case of a `kb_id` literally named `"kato"` (to confirm no accidental prefix-match against the old `kato-redis`-scoped thinking) — plus ephemeral session/STM keys, ran a test session, and confirmed all durable keys survived with values intact while all ephemeral keys were cleared.
- Confirmed the `KATO_TEST_REDIS_FLUSHALL=1` path still destroys everything as intended (escape hatch works).
- Ruff clean, compiles.
- Full suite (excluding performance): 446 passed, 2 skipped, 6 failed.

## Test Results Analysis — 6 Failures Are Pre-Existing, NOT Caused By This Fix
Re-running the same 6 failing tests with `KATO_TEST_REDIS_FLUSHALL=1` (old FLUSHALL behavior restored) produces the identical 6 failures — confirming this fix is not the cause. Root cause is the container running `KATO_WORKERS=4`:
- 4 websocket tests fail because websocket events are published in-process only; a client connected to one uvicorn worker misses events published from another worker. The same websocket tests passed 7/7 earlier against a single-worker instance.
- `test_concurrent_session_modifications` loses half its concurrent writes (`assert 5 == 10`) — writes split across workers aren't consistently visible to each other.
- `test_session_cleanup` fails even in isolation on a freshly flushed Redis (pre-existing session-count accounting bug, already tracked as backlog bug "session delete does not decrement active-session count + WebSocket event timeouts", root cause #3).

This newly-characterized multi-worker issue (websocket fan-out + concurrent session write loss) has been added as a new P2 backlog bug in `planning-docs/SPRINT_BACKLOG.md`.

## Files Modified
- `tests/tests/conftest.py` — `flush_redis_before_tests` fixture rewritten; `EPHEMERAL_KEY_PATTERNS` constant added; `subprocess` import removed, `os`/`redis` imports added

## Impact
- **Severity**: High (data-loss risk eliminated) — previously any local test run could destroy live Redis metadata for a shared/production-named Redis instance
- **Scope**: Test infrastructure only; no production code changed
- **Related backlog bug (now closed)**: "Bug: conftest.py unconditional Redis FLUSHALL destroys live metadata" (identified 2026-09-08, `planning-docs/SPRINT_BACKLOG.md`)
- **New backlog bug opened as a result of verification**: multi-worker websocket/concurrency issue (see `planning-docs/SPRINT_BACKLOG.md`)

## Completion Date
2026-09-08
