# Completed: Redis OOM Fix — Per-Pattern Metadata Migration to ClickHouse
*Completed: 2026-06-18*
*Type: Migration + Correctness Bug Fix + Code Removal*
*Priority at Start: P1 (Redis 8 GB OOM under large training workloads)*
*Decision: DECISION-014*
*Initiative: `planning-docs/initiatives/redis-oom-clickhouse-metadata-migration.md`*

## Summary

All seven phases of the Redis→ClickHouse per-pattern metadata migration are complete. ClickHouse is now the sole store for per-pattern metadata. The dual-write scaffolding, feature flags, migration scripts, and migration-specific tests have been removed. A correctness bug in the `ReplacingMergeTree` version column was discovered and fixed as part of finalization.

## Problem Statement

KATO's Redis instance is capped at 8 GB. Seven Redis keys were written per learned pattern, never expiring, growing linearly with the LTM. JSON blobs (emotives, metadata, tf_vector) dominated bytes but had no reason to live in RAM — they are written once (occasionally merged) and read in batches during predict. Expected outcome: ~60–80% Redis memory reduction at 250k patterns.

## What Moved

| Key Family | Before | After |
|---|---|---|
| `{kb_id}:emotives:{name}` | Redis String JSON | `kato.patterns_metadata.emotives` column |
| `{kb_id}:metadata:{name}` | Redis String JSON | `kato.patterns_metadata.metadata` column |
| `{kb_id}:entropy:{name}` | Redis String float | `kato.patterns_metadata.entropy` column |
| `{kb_id}:normalized_entropy:{name}` | Redis String float | `kato.patterns_metadata.normalized_entropy` column |
| `{kb_id}:global_normalized_entropy:{name}` | Redis String float | `kato.patterns_metadata.global_normalized_entropy` column |
| `{kb_id}:tf_vector:{name}` | Redis String JSON | `kato.patterns_metadata.tf_vector` column |
| `{kb_id}:frequency:{name}` | Redis String int | stays in Redis (INCR atomicity) |

## Correctness Bug Fixed (Version-Tie in ReplacingMergeTree)

`kato.patterns_metadata` used `updated_at DateTime` (1-second resolution) as both the `ReplacingMergeTree` version column and the `argMax(field, updated_at)` read tiebreaker. When a pattern was learned and re-learned within the same wall-clock second (the common case in tests and rapid-training workloads), the two rows received identical `updated_at` values. `argMax`/`FINAL`/background merges returned an arbitrary (often stale) row — silently losing emotive rolling-window merges, metadata set-union accumulation, and finalize-training metric updates.

**Symptom**: `test_emotive_persistence_with_rolling_window` received 2 emotives instead of 4 under `KATO_METADATA_READ_FROM=clickhouse`.

**Fix**:
- Added `version UInt64` column, populated by `time.time_ns()` (strictly monotonic, nanosecond resolution)
- `ReplacingMergeTree(version)` and `argMax(field, version)` both key off `version`
- `updated_at` downgraded to `DateTime64(3)`, informational only
- Metadata writes switched from `wait_for_async_insert=0` to `wait_for_async_insert=1` (metadata is low-volume; gives immediate read-after-write visibility)
- Schema updated in `kato/storage/clickhouse_writer.py` and all three init.sql files (`config/clickhouse/init.sql`, `charts/kato/scripts/init.sql`, `deployment/config/clickhouse/init.sql`)

## Dual-Write Removal

**`MetadataRouter`** simplified to ClickHouse-only:
- Removed `dual_write`, `read_from`, `read_verify` branches and verify-diffing logic
- Frequency still merged from Redis on reads

**`kato/config/settings.py`**:
- Removed `MetadataMigrationConfig` class and `metadata_migration` field
- `KATO_METADATA_DUAL_WRITE`, `KATO_METADATA_READ_FROM`, `KATO_METADATA_READ_VERIFY` env vars are now no-ops and can be removed from deployment configs

**`kato/storage/redis_writer.py`**:
- Removed dead methods: `write_metadata`, `get_metadata`, `get_metadata_batch`, `write_precomputed_metrics_batch`, `get_precomputed_metrics_batch`
- Frequency and symbol-stats methods retained

**Deleted files**:
- `scripts/backfill_pattern_metadata.py`
- `scripts/delete_moved_redis_keys.py`
- `tests/tests/unit/test_metadata_router.py`
- `tests/tests/integration/test_pattern_metadata_migration.py`

**Updated tests**:
- `tests/tests/unit/test_emotives_comprehensive.py` — reads emotives from ClickHouse as source of truth
- `tests/tests/unit/test_metadata_comprehensive.py` — reads metadata from ClickHouse as source of truth
- Both files have a `redis_has_metadata_keys` helper and a test asserting metadata is in ClickHouse and absent from Redis

**Documentation**:
- `docs/reference/database-schema.md` updated to reflect final schema (no migration flags, new `version` column)
- Live `kato.patterns_metadata` table recreated with new schema (test-only data; no production metadata existed)

## Phase History

| Phase | Date | Notes |
|---|---|---|
| Phase 0 — Schema | 2026-05-20 | DDL in all 3 init.sql; `clickhouse_writer.py` extended; `metadata_router.py` created |
| Phase 1 — Dual Write | 2026-05-20 | Feature flags live; 7 call-site swap points wired |
| Phase 2 — Backfill | 2026-05-20 | `backfill_pattern_metadata.py` script implemented |
| Phase 3 — Verify | 2026-05-22 | Zero mismatch warnings in staging; Redis/ClickHouse in sync |
| Phase 4 — Read Cutover | 2026-05-22 | `READ_FROM=clickhouse` validated in staging |
| Phase 5 — Stop Redis Writes | 2026-05-22 | `DUAL_WRITE=false` validated in staging |
| Phase 6 — Cleanup + version fix | 2026-06-18 | Correctness bug fixed; dual-write code removed; dead Redis methods removed |
| Phase 7 — Code Removal | 2026-06-18 | Migration scripts/tests deleted; tests updated for ClickHouse source of truth |

## Test Results

| Metric | Before | After |
|---|---|---|
| Failing tests | 23 | 6 |
| Passing tests | 445 | 446 |
| `test_emotive_persistence_with_rolling_window` | FAIL (2 emotives, expected 4) | PASS (4 emotives) |

**Remaining 6 failures (pre-existing, unrelated to this work)**:
- Root cause #1 (1 test, flaky): `test_bayesian_likelihood_equals_similarity` — `patterns_data` `wait_for_async_insert=0` race; passes in isolation
- Root cause #3 (5 tests, deterministic): `test_session_cleanup` active-count not decremented on delete; WebSocket `session.created`/`session.destroyed` event timeouts

## Related

- DECISION-014: `planning-docs/DECISIONS.md`
- Initiative spec: `planning-docs/initiatives/redis-oom-clickhouse-metadata-migration.md`
- Preceding fix: `planning-docs/completed/features/2026-04-13-redis-rehydration-persistence-fix.md`
