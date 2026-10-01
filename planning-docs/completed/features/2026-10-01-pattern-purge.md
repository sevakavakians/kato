# Pattern Purge: Permanent Deletion of Retired Patterns, With Statistics Unwound

**Completed**: 2026-10-01
**Status**: COMPLETE, VERIFIED, MERGED to `main` as `916f4c0` and **RELEASED as v6.3.0** (2026-10-01, `./container-manager.sh minor`, release commit `5684a56`, tag `v6.3.0`; images `ghcr.io/sevakavakians/kato:6.3.0`/`:6.3`/`:6`/`:latest`; https://github.com/sevakavakians/kato/releases/tag/v6.3.0).
**Decisions**: DECISION-045
**Type**: Feature (API + storage). Completes the retirement lifecycle v6.2.0 began, and closes the last half of collaborator PR #6 (Brian Reed's `codex/kato-reliability-vector-modes-20260918`). PR #6 was CLOSED 2026-10-01 as fully absorbed (closing comment issuecomment-5937318293) and its remote branch deleted. Vector-modes half merged 2026-09-30; retirement half in v6.2.0; purge half is this work.

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

## Release and close-out (v6.3.0)
- Version 6.2.0 -> 6.3.0 in `pyproject.toml`, `kato/__init__.py`, `charts/kato/Chart.yaml`; consistent. CI green on `5684a56` and all commits leading to it. Published image verified by deploying it and running the 31 lifecycle tests (17 purge + 14 retirement); all passed.
- Extra fix `7914db1`: Bandit B608 failed lint on main (merge `916f4c0` was CI-red); table names now literal instead of loop-interpolated; no nosec.
- Extra fix `fc32c52`: the `kato_ops.py:99` shared-client concurrency P2 is CLOSED by removing the `asyncio.to_thread` entirely (its justification, a 0.5s sleep in `flush_async_insert_queue()` without FLUSH privilege, no longer exists). 12 concurrent `/patterns/count` requests all returned 200.
- PR #6: closing comment maps each half of the branch to its release and Brian's commit, explains the re-cut, withdraws blockers 1, 3, 8 plus two sub-claims, lists five additional purge-half defects. Branch `codex/kato-reliability-vector-modes-20260918` deleted; only `main`/`origin/main` remain; no open PRs. Brian's commits on main: `01d3990`, `12a0cb6`, `9da9d82` (6.1.0); `dcc539d`, `6bb38a9` (6.2.0); `0d66947` (6.3.0).

## Still open (not part of this work)
- Three old git stashes undropped, awaiting user decision (stash@{0} 2026-04-21 superseded multi-worker attempt; stash@{1} three .pyc; stash@{2} two log files).
- Per-session `sort_symbols` inert P2 remains open.
