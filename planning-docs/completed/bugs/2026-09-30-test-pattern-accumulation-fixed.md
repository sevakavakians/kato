# Test Pattern Accumulation Fixed — Learned Patterns Were Never Reclaimed Between Test Runs

**Completed**: 2026-09-30 (work complete; **not yet merged to `main`** — see Commit Status)
**Status**: COMPLETE, VERIFIED locally, **PR #10 OPEN on branch `fix/test-pattern-accumulation`, CI pending as of this writing**
**Decision**: None filed
**Type**: Bug fix (test infrastructure) — root cause was a naming-convention gap, not a missing cleanup step

## Summary

Sessions were cleaned up between test runs, but learned patterns never were. Patterns are durable by design — they outlive the session that created them, which is exactly the property `test_database_persistence.py` exercises — so every suite run left its corpus behind permanently. The stack this was found on held **17,869 patterns**, nearly all of it dead test data, the oldest from `stress_200_*` runs months old.

This is not just untidy: corpus size feeds `total_unique_patterns` and the symbol statistics behind prediction metrics, and a larger corpus means more candidates flowing through the filter pipeline — so the pile made the suite progressively slower and its timing-sensitive tests less reproducible over time.

## Root Cause

`generate_unique_node_id` in `test_database_persistence.py` emitted node ids shaped `<descriptive>_<8 hex>` — `stress_200_...`, `user_alice_...`, `vector_persist_...` — none of which carry the `test_` prefix that `redis_test_cleanup` matches on. Fixed at source: it now emits `test_<descriptive>_<8 hex>`, so new data is reclaimable going forward without anyone maintaining a list of shapes.

Pre-fix data (already in the corpus before this change) is covered by a closed list of 11 prefixes, each traced to a specific call site in that file. These are matched on the **exact shape** the old generator produced — trailing 8-hex token required — not by prefix alone, deliberately: a real node genuinely named `user_alice` or `user_alice_prod` can never be mistaken for test data and purged. The list can be deleted once no stack still holds pre-fix data.

## What Changed

New `tests/tests/fixtures/store_test_cleanup.py`, wired into the conftest session fixture; `KATO_TEST_KEEP_PATTERNS=1` skips it entirely for a local debugging session that wants to inspect learned patterns afterward.

Two properties the implementation deliberately preserves:

1. **Concurrent-run safety.** `redis_test_cleanup` was already made safe to run alongside another suite or a live notebook; a naive purge-by-name would give that up, since two concurrent runs both create test-prefixed nodes and each could delete the other's in-progress corpus. Only partitions whose newest ClickHouse part has been idle for `KATO_TEST_PURGE_QUIET_MINUTES` (default 15) are dropped — anything actively being written to is left alone. Every unparseable override falls back to the default rather than to zero, because zero means "purge what is in flight."
2. **Cost.** A naive implementation would issue one `DROP PARTITION` per partition per table — thousands of round trips, enough to dominate suite startup on its own. Implemented instead as one `system.parts` query, batched `DROP PARTITION` clauses, and a single Redis keyspace pass rather than one scan per `kb_id`.

Safety: a `kb_id` must both carry a test marker (or match the legacy 11-prefix shape) and pass `validate_kb_id`, because `DROP PARTITION` cannot bind parameters and the value is inlined into statement text. Tests cover the near misses — production `node0..node3`, prefix-sharing names, malformed hex tokens, and an injection attempt behind a valid test prefix.

## Verification

- Steady-state cost: **~3s** per suite run.
- One-time backlog cleanup: clearing the pre-existing 17,869-pattern pile took **1m42s**.
- Full local suites after the change: **566 unit, 129 integration (1 documented xfail), 49 api**.

## Commit Status

**Not yet merged.** Work is complete on branch `fix/test-pattern-accumulation`, committed as `038057c` "fix(tests): reclaim learned patterns instead of accumulating them forever". PR #10 (https://github.com/sevakavakians/kato/pull/10) is **OPEN**, targeting `main`; CI was still pending as of this writing. Not to be confused with already-merged: this branch was cut from `main` after the async-insert-visibility-race merge (`92a977c`) landed, so it also carries that fix.

## Related

- PR #10: https://github.com/sevakavakians/kato/pull/10 — "fix(tests): reclaim learned patterns instead of accumulating them forever"
- `tests/tests/fixtures/store_test_cleanup.py` (new), `tests/tests/fixtures/test_database_persistence.py` (`generate_unique_node_id` fix)
