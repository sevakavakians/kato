# Store Cleanup: Glob-Escape Fix + ClickHouse/Redis Parity Tool

**Completed**: 2026-09-10
**Status**: COMPLETE — committed as `7aad817` "fix(storage): make clear-all leave nothing behind; add a store parity tool"
**Decision context**: Multi-Worker Uvicorn + Concurrent Training Safety initiative, Phase A
**Type**: Bug fix (data integrity) + new ops tool

## Summary

Phase A of the Multi-Worker Uvicorn initiative's verification re-run found two independent cleanup bugs while checking Redis/ClickHouse parity (88 of 261 `kb_id`s mismatched, all `test_*` residue — not multi-worker write loss). Both are fixed in this commit.

## What Changed

### Bug 1: unescaped glob characters in `scan_iter`
- `kato/storage/redis_writer.py`'s `delete_all_metadata()` and 3 other `scan_iter(match=f"{kb_id}:*")` call sites built patterns without escaping `kb_id`. Redis `SCAN MATCH` treats `[...]` as a glob character class, so pytest's bracketed parametrize ids (`test_threshold_filters_by_similarity[...]`) matched nothing and cleanup silently no-oped, leaving 11 orphaned Redis keys per affected kb.
- Fix: `escape_glob()` (escapes `[`, `]`, `*`, `?`) applied at all 4 `scan_iter` sites in `redis_writer.py` plus `tests/tests/fixtures/cleanup_utils.py`.

### Bug 2: `clear_all_memory` leaked `patterns_metadata` and raced the async-insert queue
- `clear_all_memory()` (`kato/informatics/knowledge_base.py`) called `clickhouse_writer.delete_all_patterns()` and `redis_writer.delete_all_metadata()` but never called `metadata_router.delete_all_pattern_metadata()` — a `patterns_metadata` row leak on every clear-all.
- Separately, `clear_all_memory()` issued `DROP PARTITION` without first calling `flush_async_insert_queue()` (unlike `finalize_training`, which does) — a learn's ~200ms-buffered async-insert row could land after the drop and survive.
- Fix: `clear_all_memory()` now flushes the async-insert queue before `DROP PARTITION` and also drops the `patterns_metadata` partition.

### New ops tool
- `scripts/check_store_parity.py` — reports Redis vs ClickHouse `kb_id`/pattern-count mismatches; `--purge-prefix`/`--execute` flags to clean up matching residue.

### Tests
- `tests/tests/integration/test_store_cleanup.py` — 4 new tests, including one parametrized with a bracketed `kb_id`, covering both bugs.

### Docs
- `docs/users/database-persistence.md` — new "Checking Store Consistency" section.
- `docs/developers/testing.md` — perf-test section (shared with the Phase C stopgap work).
- `CHANGELOG.md` `[Unreleased]` entries.

## Verification

- The 88 `test_*` residue `kb_id`s were purged (user-approved) using the new tool; production `kb_id`s untouched (none contain brackets).
- Parity re-run: **0 mismatches** (was 88/261).
- Re-running the residue-producing suite creates no new residue.
- Full suite (combined with the rest of this session's work): 479 passed / 4 skipped / 1 xfailed / 0 failed (648s).

## Related

- Multi-Worker Uvicorn + Concurrent Training Safety initiative, `planning-docs/SPRINT_BACKLOG.md` (Active Projects) — Phase A.
- Two Backlog Bug entries this closes: "scan_iter glob-unescaped kb_id..." and "clear_all_memory drops the ClickHouse partition before the async-insert queue flushes...".
- Sibling commits from the same day: `bef2b47` (Phase B), `9de98c3` (Phase C deadlock stopgap, DECISION-025).
