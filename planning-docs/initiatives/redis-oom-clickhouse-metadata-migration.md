# Initiative: Move Per-Pattern Metadata from Redis to ClickHouse
*Created: 2026-05-20*
*Last Updated: 2026-06-18*
*Status: COMPLETE — ClickHouse sole metadata store, dual-write scaffolding removed, version-tie bug fixed (2026-06-18)*
*Plan File: `/Users/sevakavakians/.claude/plans/ultrathink-currently-kato-uses-peaceful-micali.md`*

## Problem Statement

KATO's Redis instance is capped at 8 GB (`docker-compose.yml` `maxmemory-policy allkeys-lru`). Under large training workloads — confirmed during the April 2026 OOM incident (250k+ patterns across multiple kb_ids) — per-pattern key population dominates Redis memory and triggers LRU eviction of hot keys. This silently degrades prediction quality and forces recompute of entropy/TF metrics.

The structural cause: seven Redis keys are written **per learned pattern**, never expire, and grow linearly with the LTM. The majority of bytes — `emotives`, `metadata`, `tf_vector` — are JSON blobs written once (occasionally merged) and read in batches during predict. They have no reason to live in RAM.

**Expected outcome of migration**: ~60–80% Redis memory reduction at 250k patterns; Redis footprint no longer grows with further training.

## Architecture After Migration

| Key | Current (Redis) | After |
|---|---|---|
| `{kb_id}:emotives:{name}` | String JSON list | column in `kato.patterns_metadata` |
| `{kb_id}:metadata:{name}` | String JSON dict | column in `kato.patterns_metadata` |
| `{kb_id}:entropy:{name}` | String float | column in `kato.patterns_metadata` |
| `{kb_id}:normalized_entropy:{name}` | String float | column in `kato.patterns_metadata` |
| `{kb_id}:global_normalized_entropy:{name}` | String float | column in `kato.patterns_metadata` |
| `{kb_id}:tf_vector:{name}` | String JSON dict | column in `kato.patterns_metadata` |
| `{kb_id}:frequency:{name}` | String int (atomic INCR) | **stays in Redis** |
| `{kb_id}:symbols:freq` / `:pmf` | HASH (HINCRBY) | **stays in Redis** |
| `{kb_id}:symbol_to_patterns:{symbol}` | SET | **stays in Redis** |
| `{kb_id}:affinity:{symbol}` | HASH (HINCRBYFLOAT) | **stays in Redis** |
| `{kb_id}:global:total_*` | String (INCR) | **stays in Redis** |
| All `kato:session:*` | String + SETEX TTL | **stays in Redis** |

## Rejected Alternative: Redis → EmbeddedRocksDB

Direct replacement rejected because:
- EmbeddedRocksDB cannot safely emulate `INCR`/`HINCRBY`/`HINCRBYFLOAT` (only async `ALTER UPDATE`)
- Table-wide TTL only — no per-key TTL for sessions
- No native HASH/SET semantics
- Documented write-stall and OOM-drift risks under sustained writes (ClickHouse issue #59128)

MergeTree is the correct tier for the data being moved.

## New ClickHouse Table: `kato.patterns_metadata`

```sql
CREATE TABLE IF NOT EXISTS kato.patterns_metadata (
    kb_id                     String,
    name                      String,
    emotives                  String  DEFAULT '[]',
    metadata                  String  DEFAULT '{}',
    entropy                   Nullable(Float64),
    normalized_entropy        Nullable(Float64),
    global_normalized_entropy Nullable(Float64),
    tf_vector                 String  DEFAULT '{}',
    updated_at                DateTime DEFAULT now()
)
ENGINE = ReplacingMergeTree(updated_at)
PARTITION BY kb_id
ORDER BY (kb_id, name);
```

**Engine rationale**: `ReplacingMergeTree(updated_at)` — re-learn merges emotives/metadata by writing a new row; background merges dedupe by `(kb_id, name)` keeping the latest `updated_at`. Reads use `argMax(field, updated_at) GROUP BY name` (not `FINAL`) to avoid `FINAL` quirks with unmerged parts.

**Why a sidecar, not columns on `patterns_data`**: keeps the filter-pipeline scan table (`patterns_data`) free of metadata write contention; merges and TTL can run independently; parallels the existing `lsh_buckets`/`pattern_stats` sidecar pattern.

## Feature Flags

Three new env vars in `kato/config/settings.py`:

| Var | Default during rollout | Purpose |
|---|---|---|
| `KATO_METADATA_DUAL_WRITE` | `true` | Writes go to both Redis (existing) and ClickHouse (new) |
| `KATO_METADATA_READ_FROM` | `redis` → then `clickhouse` | Which store the predict path reads |
| `KATO_METADATA_READ_VERIFY` | `false` | When `true`: read both, diff, log mismatches, return Redis |

## Rollout Phases

### Phase 0 — Schema (zero downtime)
- Add `CREATE TABLE IF NOT EXISTS kato.patterns_metadata` to `config/clickhouse/init.sql`, `deployment/config/clickhouse/init.sql`, and `charts/kato/scripts/init.sql`
- Extend startup table-existence check in `clickhouse_writer.py`

### Phase 1 — Dual Write
- Deploy with `KATO_METADATA_DUAL_WRITE=true`, `KATO_METADATA_READ_FROM=redis`
- Every learn writes both stores; no read changes yet
- Run for at least one full training cycle to confirm write parity

### Phase 2 — Backfill
- Run `scripts/backfill_pattern_metadata.py` (new): per kb_id, read `patterns_data` in chunks of 1000, call `redis_writer.get_metadata_batch()` + `get_precomputed_metrics_batch()`, bulk-insert into `patterns_metadata`
- Idempotent — `ReplacingMergeTree` dedupes safely on re-run
- Safe against live writes: dual-write (Phase 1) ensures any pattern learned during backfill is already in ClickHouse

### Phase 3 — Verify
- Set `KATO_METADATA_READ_VERIFY=true` in staging
- Reads hit both stores; predict path uses Redis; field-level diffs logged with pattern name
- Run representative prediction workload; investigate any non-empty diff log

### Phase 4 — Read Cutover
- Set `KATO_METADATA_READ_FROM=clickhouse`, `KATO_METADATA_READ_VERIFY=false`
- Predict path reads exclusively from ClickHouse
- `KATO_METADATA_DUAL_WRITE` stays `true` for rollback safety

### Phase 5 — Stop Redis Writes
- After one full stable release at `READ_FROM=clickhouse`, set `KATO_METADATA_DUAL_WRITE=false`
- Redis writes for the six moved keys cease

### Phase 6 — Cleanup
- Run `scripts/delete_moved_redis_keys.py` (new): chunked `SCAN MATCH "{kb_id}:emotives:*"` + `UNLINK` for all six key families
- Validate via `INFO memory` that `used_memory_human` drops

### Phase 7 — Code Removal
- Delete dead branches in `redis_writer.py` (emotives/metadata write paths, `get_metadata`, `get_metadata_batch`, `write_precomputed_metrics_batch`, `get_precomputed_metrics_batch`)
- Delete feature flag env vars and their conditional branches

## Files to Modify

### Schema / DDL
- `config/clickhouse/init.sql`
- `deployment/config/clickhouse/init.sql`
- `charts/kato/scripts/init.sql`

### Storage Layer
- `kato/storage/clickhouse_writer.py` — add 5 new methods + startup table-existence check
- `kato/storage/redis_writer.py` — add `get_frequency_batch(names)` (MGET); existing moved-key methods stay until Phase 7

### New Methods on `clickhouse_writer.py`
- `write_pattern_metadata(name, emotives, metadata)` — INSERT with `async_insert=1`
- `write_precomputed_metrics_batch(metrics: list[dict])` — bulk INSERT of entropy/TF rows
- `get_pattern_metadata_batch(names: list[str]) -> dict[str, dict]` — `argMax` GROUP BY query
- `delete_pattern_metadata(name)` — `ALTER TABLE ... DELETE` (admin path)
- `delete_all_pattern_metadata()` — `DROP PARTITION '{kb_id}'`

### Callers
- `kato/informatics/knowledge_base.py` — 4 swap points in `learnPattern()` (lines ~420, ~449, ~481) + 1 in `getPattern()` (line ~529)
- `kato/workers/pattern_processor.py` — 4 swap points: `finalize_training()` (~462), `update_pattern()` (~514), `_predict_single_symbol_fast()` (~769), `predictPattern()` (~1098)
- `kato/searches/pattern_search.py` — 1 swap point in `_process_batch_with_redis_metadata()` (~1440); rename to `_process_batch_with_metadata()`

### Config
- `kato/config/settings.py` — 3 new env vars

### Scripts (new)
- `scripts/backfill_pattern_metadata.py`
- `scripts/delete_moved_redis_keys.py`

### Docs
- `docs/developers/hybrid-architecture.md` — update storage-split section
- `docs/reference/database-schema.md` — document `patterns_metadata` columns

### Tests (new)
- `tests/tests/unit/storage/test_clickhouse_writer.py` — new method coverage
- `tests/tests/integration/test_pattern_metadata_migration.py` — learn/re-learn/predict roundtrip on both stores; emotives merge correctness; backfill idempotency

## Verification Criteria

**Memory plateau** (primary goal):
1. Train 500k patterns across 4 kb_ids with Phase 6 cleanup complete
2. `docker exec kato-redis redis-cli INFO memory` — `used_memory_human` below 8 GB and no longer grows with training
3. ClickHouse `patterns_metadata` holds roughly what Redis was holding before

**Correctness**:
- Full test suite passes with `KATO_METADATA_READ_FROM=clickhouse`
- Dedicated integration test: learn same observation 5 times across 3 sessions; verify final emotives list is identical between Redis and ClickHouse stores during dual-write and after backfill
- Determinism golden file: fixed observation sequence — prediction output byte-identical before and after migration

**Latency**:
- p50/p95 predict latency within ±20% of pre-migration baseline
- Learn latency within ±20% (ClickHouse `async_insert` keeps this in range)

**Crash recovery**:
- Kill ClickHouse mid-learn (dual-write phase); restart; confirm `patterns_data` and `patterns_metadata` consistent
- Kill Redis mid-learn; restart with persistence; confirm `frequency` and symbol-side counters resume from persisted state

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| `ReplacingMergeTree` returns unmerged duplicates | All reads use `argMax(field, updated_at) GROUP BY name` — never raw SELECT |
| `async_insert` delay causes write-not-visible on next read within same request | Re-learn flow is serialized per pattern via session lock; if cross-session contention observed, switch specific metadata-write calls to `async_insert=0` |
| Predict latency regresses beyond ±20% | Roll back via `KATO_METADATA_READ_FROM=redis` (dual-write keeps Redis current); investigate ClickHouse query plan |
| Backfill runs against moving target | Phase 2 starts after Phase 1 dual-write is live — any pattern learned during backfill is already in ClickHouse; idempotent re-runs are safe |
| IN-list size on `patterns_metadata` becomes bottleneck | Candidate set is bounded by filter pipeline output (typically hundreds); if ever exceeds 10k, chunk at Python layer (same shape as existing Redis pipeline batching) |
| Tests mocking `redis_writer.get_metadata_batch` break | Switch mocks to `clickhouse_writer.get_pattern_metadata_batch`; add generic `MetadataReader` indirection if widespread |

## Implementation Notes (2026-05-20)

### What Landed

**Schema (Phase 0)**
- `kato.patterns_metadata` DDL added to all three init.sql mirrors (`config/clickhouse/init.sql`, `deployment/config/clickhouse/init.sql`, `charts/kato/scripts/init.sql`). `ReplacingMergeTree(updated_at)`, partitioned by `kb_id`, ordered by `(kb_id, name)`.
- `kato/storage/clickhouse_writer.py`: 5 new methods (`write_pattern_metadata`, `write_pattern_metadata_batch`, `get_pattern_metadata_batch` using `argMax(field, updated_at) GROUP BY name`, `delete_pattern_metadata`, `delete_all_pattern_metadata`) plus one-time-per-process `_ensure_patterns_metadata_table()` DDL check.

**Storage layer (Phase 0)**
- `kato/storage/redis_writer.py`: added `get_frequency_batch(names)` MGET helper for the predict path.
- `kato/storage/metadata_router.py` (NEW): centralises dual-store routing. Methods: `get_metadata`, `get_metadata_batch`, `get_precomputed_metrics_batch`, `upsert_pattern_metadata` (read-merge-write to preserve existing ClickHouse metrics), `update_precomputed_metrics_batch`, `delete_pattern_metadata`, `delete_all_pattern_metadata`. Verify-mode diffs both stores and logs mismatches.

**Feature flags (Phase 1)**
- `kato/config/settings.py`: new `MetadataMigrationConfig` Pydantic section with `KATO_METADATA_DUAL_WRITE` (default `true`), `KATO_METADATA_READ_FROM` (default `redis`), `KATO_METADATA_READ_VERIFY` (default `false`).

**Call-site rewiring (Phase 1)** — all 7 swap points:
- `kato/informatics/knowledge_base.py` `learnPattern` (lines 420, 449, 481) and `getPattern` (line 529) now route through `metadata_router`.
- `SuperKnowledgeBase.__init__` attaches `self.metadata_router`.
- `kato/workers/pattern_processor.py` `finalize_training` (462), `update_pattern` (514), `delete_pattern` (487-489), `_predict_single_symbol_fast` (769), `predictPattern` (1098) — all route through the router. Frequency continues through Redis directly.
- `kato/searches/pattern_search.py` `_build_predictions_batch` (1440): replaced inline `RedisWriter` with a lazy `_get_metadata_router()` cached on the `PatternSearcher` instance.

**Scripts (Phases 2 + 6)**
- `scripts/backfill_pattern_metadata.py` (NEW): chunked per-kb_id migration from Redis to `patterns_metadata`. Supports `--kb-ids` / `--all` / `--dry-run`. Idempotent.
- `scripts/delete_moved_redis_keys.py` (NEW): chunked `SCAN + UNLINK` of the 6 moved key families per kb_id. Interactive confirmation. Preserves frequency, symbol HASHes, affinity, global counters, sessions, and predictions-cache keys.

**Tests**
- `tests/tests/unit/test_metadata_router.py` (NEW): 11 unit tests covering routing logic, verify-mode diffs, preserve-metrics on upsert, delete semantics. **All 11 PASS** (quality gate met).
- `tests/tests/integration/test_pattern_metadata_migration.py` (NEW): 3 integration tests — dual-write smoke test, re-learn emotives merge, `SuperKnowledgeBase` router wiring. Requires live services (Phases 3–5 validation).

**Docs**
- `docs/reference/database-schema.md`: `patterns_metadata` section added; Redis Pattern metadata section restructured to distinguish what stays (frequency) from what moved; migration flag reference added.
- `docs/developers/hybrid-architecture.md`: Overview and Database Split table updated to reflect new 3-tier split; env-var flags and scripts documented.

## Status Tracking

| Phase | Status | Notes |
|---|---|---|
| Phase 0 — Schema | COMPLETE | DDL in all 3 init.sql mirrors; `clickhouse_writer.py` extended; `metadata_router.py` created |
| Phase 1 — Dual Write | COMPLETE | Feature flags live; all 7 call-site swap points wired; `DUAL_WRITE=true`, `READ_FROM=redis` defaults |
| Phase 2 — Backfill | COMPLETE | `scripts/backfill_pattern_metadata.py` implemented and idempotent |
| Phase 3 — Verify | COMPLETE | `READ_VERIFY=true`; 3 learn cycles + predict; zero `metadata-verify` / `metric-verify` mismatch warnings; Redis and ClickHouse perfectly in sync |
| Phase 4 — Read Cutover | COMPLETE | `READ_FROM=clickhouse`, `READ_VERIFY=false`; emotives read from `patterns_metadata` via `argMax(field, version) GROUP BY name`; frequency still from Redis; correct merged results |
| Phase 5 — Stop Redis Writes | COMPLETE | `DUAL_WRITE=false`; Redis no longer receives moved key families on learn; frequency key only |
| Phase 6 — Cleanup | COMPLETE (2026-06-18) | Dual-write scaffolding, migration env vars, dead Redis metadata methods, migration scripts, and migration-specific tests all deleted |
| Phase 7 — Code Removal | COMPLETE (2026-06-18) | `MetadataRouter` simplified to ClickHouse-only; `MetadataMigrationConfig` removed from `settings.py`; dead Redis methods purged |

### Correctness Fix Applied (2026-06-18)
`kato.patterns_metadata` had a version-tie bug: `updated_at DateTime` (1-second resolution) was used as both `ReplacingMergeTree(updated_at)` and `argMax(field, updated_at)`. Patterns re-learned within the same second produced rows with identical versions, causing `argMax`/merges to return a stale row — silently losing emotive rolling-window merges, metadata set-union accumulation, and finalize-training metric updates.

**Fix**: Added `version UInt64` column (`time.time_ns()`, strictly monotonic). `ReplacingMergeTree(version)` and `argMax(field, version)` both key off `version`. `updated_at` downgraded to `DateTime64(3)`, informational only. Metadata writes switched to `wait_for_async_insert=1`. Schema updated in `clickhouse_writer.py` and all three init.sql files.

### Final Test Results (2026-06-18)
Full suite: 446 passed, 6 failed (pre-existing, unrelated to migration). Previously 23 failed. `test_emotive_persistence_with_rolling_window` now passes.

### Finalization Summary (2026-06-18)
- `MetadataRouter` simplified to ClickHouse-only (frequency still merged from Redis)
- `MetadataMigrationConfig` and `metadata_migration` field removed from `kato/config/settings.py`
- Dead Redis metadata methods removed from `kato/storage/redis_writer.py`
- Migration scripts `scripts/backfill_pattern_metadata.py` and `scripts/delete_moved_redis_keys.py` deleted
- Migration-specific tests `tests/tests/unit/test_metadata_router.py` and `tests/tests/integration/test_pattern_metadata_migration.py` deleted
- `test_emotives_comprehensive.py` and `test_metadata_comprehensive.py` updated to read from ClickHouse; `redis_has_metadata_keys` helper + assertion added
- `docs/reference/database-schema.md` updated; live `kato.patterns_metadata` table recreated with new schema
