# Pattern Purge: Permanent Deletion of Retired Patterns, With Statistics Unwound

**Completed**: 2026-10-01
**Status**: COMPLETE, VERIFIED, **MERGED to `main`** as `916f4c0` (merge of `feat/pattern-purge`, branch deleted locally). NOT yet released: version on `main` is still 6.2.0; a 6.3.0 MINOR release is pending a user decision.
**Decisions**: DECISION-045
**Type**: Feature (API + storage). Completes the retirement lifecycle v6.2.0 began, and closes the last half of collaborator PR #6 (Brian Reed's `codex/kato-reliability-vector-modes-20260918`). PR #6 is still OPEN and its remote branch still exists -- the last stale branch. Vector-modes half merged 2026-09-30; retirement half in v6.2.0; purge half is this work.

## Commits on main
- `0d66947` (author Brian <briank.reed@icloud.com>) feat(patterns): purge retired patterns and unwind their statistics
- `6d51826` test(patterns): cover purge arithmetic and the purge endpoint
- `11a1fe6` docs(patterns): document purging, and the endpoints 6.2.0 left out

## What shipped
- `POST /sessions/{session_id}/patterns/purge`: permanently deletes retired patterns and unwinds their contribution to node statistics. Only a retired pattern can be purged. Resumable, idempotent, per-pattern error isolation. Request: optional `pattern_ids` (1-1000; omit to purge all retired), `max_patterns` (1-10000, default 1000). Response: `status` (`completed`/`partial`/`nothing_to_purge`), `purged[]`, `failed{id: reason}`, `remaining`.
- Tombstone state machine: retired -> prepared -> redis_cleaned -> purged; each transition durable before the work it authorises.
- Three Lua scripts in `kato/storage/redis_writer.py` for atomic counter reversal; `PER_PATTERN_KEY_SUFFIXES` is the single definition of what a pattern owns.
- Per-pattern affinity ledger written at learn time (`kato/informatics/knowledge_base.py` `_update_symbol_affinity` now takes `pattern_name`). Needed because affinity sums *averaged* emotives and the average shifts with the rolling persistence window, so it cannot be recomputed later.
- ClickHouse: `purge_patterns`, `wait_until_absent`, `patterns_still_present`, `invalidate_precomputed_metrics` (node-wide).
- New `OptimizedConnectionManager.build_clickhouse_client()` for callers needing their own session-bound client.

## Verification (all gates passed)
- Full suite: 834 passed, 3 skipped, 1 xfailed, 0 failed (652s).
- Prediction parity vs main: IDENTICAL across 23 predictions, 21 carrying emotives (captured on main's build, compared on the branch's build).
- 30 real-Redis arithmetic tests: `tests/tests/integration/test_pattern_purge_redis.py`.
- 17 request-level tests: `tests/tests/api/test_pattern_purge_endpoints.py`.
- Side effect: API test suite 80s -> 17s (no blocking mutations_sync wait).

## Correction recorded
An earlier concern that Brian's vector work had affected emotives/affinity was investigated and DISPROVEN. His merged metrics-cache commit `9da9d82` has zero references to affinity or emotives; `git diff merge-base..main` on `kato/informatics/knowledge_base.py` shows no affinity or average_emotives changes. The only affinity change is this purge ledger, and `test_ledger_does_not_change_affinity_values` proves it purely additive (byte-identical affinity hashes with and without journalling).

## Open items arising
- `kato/api/endpoints/kato_ops.py:99` runs `asyncio.to_thread(processor.get_pattern_count, flush)` against the SHARED ClickHouse client. clickhouse-connect clients are session-bound, so this can raise "Attempt to execute concurrent queries within the same session" and surface as a 500 on an unrelated request. Pre-existing on main, not introduced here; `build_clickhouse_client()` makes the fix available. Awaiting a scope decision from the user.
- 6.3.0 MINOR release decision pending. PR #6 still open; close it once the release decision is made.
