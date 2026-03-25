# ADR-002: Database Bottleneck Fix Strategy — In-Place Fixes vs Migration

**Status**: Accepted
**Date**: 2026-03-25
**Deciders**: KATO Development Team
**Context**: Performance profiling on branch `perf/bottleneck-profiling` identified three critical bottlenecks in the ClickHouse + Redis hybrid architecture

---

## Context and Problem Statement

Benchmark profiling revealed that three specific code patterns were responsible for the majority of latency in the learning and prediction paths:

1. **Premature ClickHouse flush**: `learnPattern()` called `flush()` after every single pattern write, bypassing the write buffer introduced in the 2026-03-19 optimization pass. This caused a full ClickHouse round-trip on every learn call.

2. **O(N) Redis SCAN for symbol lookup**: `get_all_symbols_batch()` stored symbols as individual string keys, requiring a full `SCAN` of the Redis keyspace. At 10K symbols this measured ~2016ms per call.

3. **ClickHouse IN-clause for first_token lookup**: The prediction path used a large `IN (token1, token2, ...)` clause across the full pattern table rather than querying the indexed `first_token` column directly. At 10K+ patterns this caused table scans.

The question was whether to fix these within the existing ClickHouse + Redis architecture or migrate to a different database backend entirely.

---

## Decision Drivers

- Minimize development time and operational risk
- Achieve target performance gains without architectural regression
- Maintain the existing hybrid architecture that has proven stable at production scale
- Avoid 4-8 week database migrations when targeted code fixes achieve equivalent results

---

## Considered Options

### Option 1: Migrate to DuckDB (Embedded Columnar)

**Description**: Replace ClickHouse with DuckDB, an in-process columnar analytical database that eliminates network overhead entirely.

**Pros**:
- Zero network latency (in-process execution)
- Excellent columnar read performance for analytical queries
- No separate database server to operate

**Cons**:
- Not designed for concurrent write workloads; single-writer lock degrades under parallel learn sessions
- Full storage layer migration required: schema redesign, data migration scripts, driver replacement
- Estimated 4-8 weeks of development and validation work
- No production validation with KATO's access patterns (high-frequency small writes + large-scan reads)
- Loses Redis session/metadata co-location benefit (still requires Redis)
- MinHash/LSH pipeline would need reimplementation or removal

**Decision**: Rejected

### Option 2: Migrate to PostgreSQL (Transactional RDBMS)

**Description**: Replace ClickHouse with PostgreSQL for better tooling familiarity and ACID guarantees.

**Pros**:
- Battle-tested, mature ecosystem
- Excellent tooling and operational support
- Strong ACID guarantees

**Cons**:
- Row-oriented storage: not optimized for KATO's pattern analytics workload (large sequential scans)
- Full schema migration required
- Estimated 4-8 weeks of development work
- Higher per-row overhead than ClickHouse for billion-scale pattern storage
- Does not eliminate the three identified bottlenecks (which are code patterns, not database limitations)

**Decision**: Rejected

### Option 3: Migrate to SQLite (Embedded Relational)

**Description**: Replace ClickHouse with SQLite for zero-network-overhead embedded storage.

**Pros**:
- Zero network overhead
- Trivial deployment (single file)

**Cons**:
- Single-writer lock: concurrent learn sessions serialize completely; performance degrades linearly with session count
- Not designed for billion-scale pattern storage
- Feature regression vs ClickHouse: no MinHash/LSH pipeline, no columnar compression
- Does not fix the three identified bottlenecks (which exist independent of which database is used)
- Estimated 4-8 weeks of migration work

**Decision**: Rejected

### Option 4: In-Place ClickHouse + Redis Fixes (Selected)

**Description**: Fix the three identified bottlenecks with targeted code changes inside the existing storage layer, without changing databases.

**Root Cause Analysis**:
- Bottleneck 1 is a code error: the premature `flush()` call negates the write buffer that already exists.
- Bottleneck 2 is a data structure choice: individual Redis string keys are the wrong structure for a set; Redis HASH eliminates the SCAN entirely.
- Bottleneck 3 is a query pattern: querying by `first_token` column (indexed) is the correct pattern; the IN-clause was using an unindexed path.

None of the bottlenecks are fundamental to ClickHouse or Redis. All three are fixable in ~3 days of targeted work.

**Pros**:
- ~3 days vs 4-8 weeks
- No data migration, no schema changes, no operational risk
- Fixes are surgical, reversible, and independently testable
- Validates profiling-driven optimization methodology for future use
- Maintains the battle-tested hybrid architecture

**Cons**:
- Remains coupled to ClickHouse + Redis operational complexity (separate database servers, Docker dependencies)

**Decision**: Accepted

---

## Implementation

### Fix 1: Deferred ClickHouse Flush

Remove the premature `flush()` call from the `learnPattern()` hot path. Add flush-before-predict guards to ensure predictions always see committed data without forcing a flush on every write.

**Files**: `kato/storage/knowledge_base.py`, `kato/storage/clickhouse_writer.py`, `kato/workers/pattern_processor.py`

**Expected gain**: Learning throughput 10/sec → 100+/sec

### Fix 2: Redis HASH Restructure

Replace per-symbol individual Redis string keys with a Redis HASH structure keyed by node/kb namespace. Symbol lookups use `HGETALL` (one round-trip) instead of `SCAN` + per-key `GET` (O(N) round-trips).

**Files**: `kato/storage/redis_writer.py`

**Expected gain**: `get_all_symbols_batch` 2016ms → 5ms at 10K symbols

### Fix 3: first_token ClickHouse Query

Replace the `IN (token1, token2, ...)` clause (which forces a full pattern table scan) with a direct query on the indexed `first_token` column. Add a chunked IN-clause path to the filter executor for large token sets that exceed practical IN-list limits.

**Files**: `kato/workers/pattern_processor.py`, `kato/searches/executor.py`

**Expected gain**: Single-symbol prediction at 10K patterns from failure → 5-10ms

---

## Performance Targets

| Operation | Baseline | Target |
|-----------|----------|--------|
| Learning throughput | ~10/sec | 100+/sec |
| `get_all_symbols_batch` (10K symbols) | ~2016ms | ~5ms |
| Single-symbol predict (10K patterns) | failure | 5-10ms |

---

## Consequences

### Positive
- Maintains architectural stability — no migration risk
- Achieves target performance in days, not weeks
- Each fix is independently testable and reversible
- Reinforces the profiling-driven optimization methodology established by the 2026-03-24 benchmarking infrastructure

### Negative
- Operational complexity of running ClickHouse + Redis remains (acceptable — already in production)
- Future performance improvements still require working within the ClickHouse + Redis constraint

### Neutral
- Does not affect the stateless processor refactor (Phase 1/2 work) — parallel tracks
- Does not change any public API contracts

---

## Related Decisions

- **DECISION-011** (DECISIONS.md): Database bottleneck fix strategy summary
- **ADR-001**: Stateless processor architecture (parallel initiative)
- **2026-03-19 optimization pass**: Established write buffering and Redis pipeline batching that Fix 1 and Fix 2 build upon

---

## Branch

`perf/bottleneck-profiling`

---

*Last Updated: 2026-03-25*
