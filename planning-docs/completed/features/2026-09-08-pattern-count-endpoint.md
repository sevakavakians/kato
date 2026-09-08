# Completed Feature: Pattern Count Endpoint
*Archived: 2026-09-08*

## Summary
Exposed learned-pattern count to KATO clients via a new node-scoped `GET /patterns/count` endpoint. The counting capability already existed at the storage layer (`PatternOperations.get_pattern_count()`) but was dead code — nothing called it, and `docs/reference/api/learning.md` documented a `GET /status` -> `processors.patterns_count` field that never actually existed in the codebase.

## Motivation
No client-facing way existed to ask "how many patterns have been learned". This is a basic introspection capability expected by users and was already partially built (storage-layer method existed, unused) and partially documented (incorrectly, pointing at a non-existent field).

## Implementation Details

### New Endpoint
- `GET /patterns/count` in `kato/api/endpoints/kato_ops.py`
  - Node-scoped: `node_id` query param, falls back to header via `get_node_id_from_request`
  - `flush` query param (default `true`)
  - Returns `{"pattern_count": int, "node_id": str}`
  - **Path chosen deliberately**: `/patterns/count` (plural), not `/pattern/count`, to avoid being shadowed by the existing `GET /pattern/{pattern_id}` route
  - Handler wraps the call in `asyncio.to_thread` because the underlying ClickHouse count is a sync driver call, and `flush_async_insert_queue()` sleeps 0.5s when it lacks the FLUSH privilege

### Schema
- `PatternCountResponse` model added to `kato/api/schemas/kato_ops.py`

### Storage Layer
- `PatternOperations.get_pattern_count(flush=True)` (previously dead code, now wired up) optionally flushes pending ClickHouse async-insert writes before counting — required for read-your-writes correctness, since pattern inserts use `wait_for_async_insert=0`
- `KatoProcessor.get_pattern_count(flush=True)` delegate added (`kato/workers/kato_processor.py:140-142`)

### Client Library
- `examples/python-client.py`: new `get_pattern_count(flush=True)` method
- Module version bumped to 3.6.0

### Documentation Fixes
- Fixed the broken snippet in `docs/reference/api/learning.md` (previously referenced non-existent `GET /status` -> `processors.patterns_count`)
- Added a "Get Pattern Count" section to `docs/reference/api/utility.md`
- Added the endpoint to `docs/reference/api/README.md`
- Corrected three additional doc blocks that documented a non-existent `patterns_count`/`active_processors` response shape: `docs/reference/api/health.md`, `docs/reference/api/monitoring.md`, `docs/developers/architecture.md` — verified the real `/status` shape is `total_processors`/`max_processors`/`eviction_ttl_seconds`/`processors[]`

## Design Decision
**ClickHouse is the authoritative count source, NOT the Redis `total_unique_patterns` counter.** The Redis counter has no decrement path — `PatternOperations.delete_pattern()` never touches it — so it drifts high (overcounts) after any pattern deletions. See DECISION-015 in `planning-docs/DECISIONS.md`.

## Files Modified
- `kato/api/endpoints/kato_ops.py` — new `GET /patterns/count` endpoint
- `kato/api/schemas/kato_ops.py` — `PatternCountResponse` model
- `kato/workers/pattern_operations.py` — `get_pattern_count(flush=True)` wired up (was dead code)
- `kato/workers/kato_processor.py` — delegate method added
- `examples/python-client.py` — `get_pattern_count()` client method; version 3.6.0
- `docs/reference/api/learning.md` — broken snippet fixed
- `docs/reference/api/utility.md` — new "Get Pattern Count" section
- `docs/reference/api/README.md` — endpoint listed
- `docs/reference/api/health.md`, `docs/reference/api/monitoring.md`, `docs/developers/architecture.md` — corrected `/status` response shape
- `tests/tests/api/test_fastapi_endpoints.py` — 3 new tests (zero count, count after learn with flush, flush=false accepted, unique-vs-frequency semantics)
- `tests/tests/integration/test_database_persistence.py` — `count_patterns_for_node` helper now calls the real endpoint instead of a dead prediction-count proxy

## Test Results
- Full local suite: 448 passed / 2 skipped / 4 failed — all 4 failures target a stale port-8000 container (2-week-old image), unrelated to this change
- WebSocket subset: 7/7 passing against the new build
- `test_session_cleanup` fails in isolation even on a freshly flushed Redis (pre-existing session-count accounting bug, unrelated — see Known Issues below)
- API suite: 50 passed
- Integration persistence suite: 10 passed
- Functional smoke test: 0 -> 1 immediately after learn (flush works, 12.7ms, no privilege warning); relearn stays at 1; learning a distinct sequence goes to 2

## Completion Date
2026-09-08
