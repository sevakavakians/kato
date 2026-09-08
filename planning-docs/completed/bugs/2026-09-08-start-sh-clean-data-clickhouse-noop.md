# Bug Fix: `start.sh clean-data` Was a Silent No-Op Against ClickHouse

*Completed: 2026-09-08*
*Status: FIXED*

## Summary
`./start.sh clean-data` was supposed to clear all data across Qdrant, Redis, and ClickHouse, but the ClickHouse step never actually cleared anything — it silently no-opped while printing "✓ All database data has been cleared!" regardless of outcome. Fixed by truncating the correct tables in the correct database. Immediately after the fix, the (now-working) command — plus manual verification — was used to purge all local test data at the user's explicit direction, closing out an unrelated question about recovering pre-flush Redis metadata.

## Root Cause
The ClickHouse step in the `clean-data` case ran:
```bash
DROP TABLE IF EXISTS default.patterns_data
```
but KATO's pattern tables live in the `kato` database, not `default` — confirmed via `system.tables` (only `kato.patterns_data` exists; no `default.patterns_data`). `IF EXISTS` made the DROP against a nonexistent table succeed silently as a no-op. The command's stderr was also suppressed with `2>/dev/null`, so nothing would have surfaced even if the query had failed outright. The step additionally never touched `kato.patterns_metadata`, `kato.lsh_buckets`, or `kato.pattern_stats` — only `patterns_data` was ever targeted, and against the wrong database.

**Net effect**: `clean-data` correctly cleared Redis (`FLUSHALL`) and Qdrant (delete-all-collections loop), but left every row in all four ClickHouse pattern tables untouched while unconditionally reporting success.

## Fix Applied
In `/Users/sevakavakians/PROGRAMMING/kato/start.sh`, `clean-data` case:
- Replaced the `DROP TABLE ... default.patterns_data` + re-run-`init.sql` approach with a loop that `TRUNCATE TABLE IF EXISTS kato.$table`s each of `patterns_data`, `patterns_metadata`, `lsh_buckets`, `pattern_stats`. TRUNCATE preserves schema and partitioning, so `init.sql` no longer needs to re-run after a clear.
- Removed the `2>/dev/null` error suppression; each table's truncate failure now prints a warning naming the specific table (`Failed to truncate kato.$table`), instead of failing silently.
- Added `docker exec kato-redis redis-cli ... BGREWRITEAOF` immediately after the existing `FLUSHALL`, since `FLUSHALL` empties the Redis keyspace but does not shrink the on-disk AOF file — without a rewrite, disk usage from prior data stays resident.

```bash
# Clear ClickHouse - truncate the pattern tables (they live in the
# `kato` database, not `default`). TRUNCATE keeps the schema and
# partitioning, so init.sql does not need to re-run.
print_info "Clearing ClickHouse data..."
for table in patterns_data patterns_metadata lsh_buckets pattern_stats; do
    docker exec kato-clickhouse clickhouse-client --user "${CLICKHOUSE_USER:-default}" --password "${CLICKHOUSE_PASSWORD:-}" --query "TRUNCATE TABLE IF EXISTS kato.$table" || print_warn "Failed to truncate kato.$table"
done
```

## Verification
With 347 rows in `patterns_data`, 370 in `patterns_metadata`, 1721 Redis keys, and 2 Qdrant collections present, running `./start.sh clean-data` brought all of them to 0/empty, with the four ClickHouse tables still existing afterward (schema intact — confirmed via `system.tables`). `bash -n start.sh` syntax check passed.

## Files Modified
- `start.sh` — `clean-data` case rewritten (ClickHouse TRUNCATE loop, error suppression removed, Redis `BGREWRITEAOF` added)

## Impact
- **Severity**: Medium — the command was the documented "soft reset" path for local development but did nothing to the majority of stored pattern data (ClickHouse holds pattern rows; Redis mostly holds derived metadata/sessions). Anyone relying on `clean-data` to fully reset local state was working against stale ClickHouse data without any indication.
- **Scope**: Operational tooling only (`start.sh`); no production code (`kato/`) changed.

---

## Additional Action: Local Test Data Purge (Maintenance)

**Date**: 2026-09-08
**Type**: Maintenance / operational cleanup (not a code change)

### Context
Verifying the `clean-data` fix above required real data to clear. Separately, the question of whether pre-flush Redis metadata (an Apr 28 AOF base snapshot, from before an earlier unrelated `FLUSHALL` incident) needed recovery was still open. The user confirmed directly that nothing on this machine is production data ("These are all just my tests and are not production data. They can all be cleared out."), which closed out the recovery question — no recovery was needed or attempted — and authorized a full purge of all local test data.

### What Was Cleared
- **ClickHouse**: 238 `kb_id`s / 2,977 rows in `patterns_data`; 1,313 `kb_id`s / 3,595 rows in `patterns_metadata` (includes the former `node0_kato` (301 rows) and `node1_kato` (62 rows) from the 2026-04-13 hierarchical training run)
- **Redis**: 56 keys
- **Qdrant**: 13 `vectors_test_*` collections
- **Redis disk reclaim**: 4.4 GB → 40 KB via `BGREWRITEAOF`. The AOF had accumulated a 2.69 GB base file from an Apr 28 snapshot plus a 2.07 GB incremental log on top of it.

### Post-Cleanup Verification
- All four ClickHouse pattern tables: 0 rows, schema intact
- Redis: `DBSIZE` 0
- Qdrant: no collections remaining
- `/health`: 200 OK
- Functional smoke test on a fresh node: learn → count → clear-all behaved correctly (pattern count 0 → 1 → 0)
- Test suites run from the empty state: `tests/tests/api/` plus `tests/tests/integration/test_database_persistence.py` — 60 passed / 1 skipped

### Related Correction (Knowledge Refinement)
Earlier the same day, some planning-doc entries described the conftest.py FLUSHALL data-loss risk as being "combined with no Redis persistence by default" — implying Redis persistence was currently disabled. **That was incorrect.** `REDIS_PERSISTENCE=true` is set in both `.env` and `deployment/.env`, unchanged since the 2026-04-13 fix (see `planning-docs/completed/features/2026-04-13-redis-rehydration-persistence-fix.md`), and the running container has `--save "900 1" ...` plus `--appendonly yes` with `aof_enabled:1`. Persistence was and is enabled; it did not prevent the earlier data-loss incidents because **persistence protects against restarts and crashes, not against an explicit deletion command** — an intentional `FLUSHALL` gets durably persisted too, emptied state and all. Corrected in `planning-docs/project-manager/patterns.md` and `planning-docs/completed/bugs/2026-09-08-conftest-redis-flushall-scoped-to-ephemeral-keys.md`.

## Completion Date
2026-09-08
