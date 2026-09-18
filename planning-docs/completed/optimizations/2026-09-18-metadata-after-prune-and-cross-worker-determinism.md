# Optimization: Pattern Metadata Fetched After Top-K Pruning + Cross-Worker Determinism Fixes

**Completed**: 2026-09-18
**Type**: Performance (algorithmic complexity) + Bug Fix (cross-worker correctness, determinism, session leak, security)
**Impact**: Converts pattern-metadata lookup from an O(matched-candidates) cost to an O(max_predictions * PRUNING_FACTOR) cost (a constant, 300 by default) — the single largest remaining lever in the prediction path identified by DECISION-031's cost breakdown. Also fixes a real cross-worker statistics divergence, closes a session-state leak, hardens several security/robustness gaps, and moves a query-chunking fix to cover all callers. Shipped in KATO v5.2.0.
**Decision**: DECISION-032 in `planning-docs/DECISIONS.md`

## Summary

DECISION-031 (2026-09-16) measured that pattern-metadata lookup (frequency, emotives) was ~35% of total prediction time (~430ms of ~1271ms at 6000 patterns/candidates), because metadata was fetched for every matched pattern even though only `max_predictions` survive ranking. That decision explicitly deferred acting on it, pending confirmation that the top-K prune metrics (`_pre_potential`: evidence, confidence, snr, fragmentation) don't themselves require metadata. This session confirmed they don't (all four are derivable purely from match/segmentation data) and implemented the reordering (Phase 1a).

While verifying the change across multiple uvicorn workers, a second, unrelated bug surfaced: a worker was stuck reporting a stale symbol-frequency value (0.049) instead of the correct post-write value (0.025) — a cross-worker statistics divergence caused by an unconditional per-process `_global_metadata_cache` with no invalidation mechanism. Fixed with a `stats_version` scheme.

Several smaller determinism, leak, and query-chunking fixes were made in the same effort, plus a round of security/robustness hardening (SQL parameterization, identifier allowlisting, error-handler registration, CORS, a redundant lock).

## What Changed

### 1. Metadata fetched after top-K pruning (Phase 1a)
- New `PatternSearcher.attach_pattern_metadata(predictions)` in `kato/searches/pattern_search.py` — attaches frequency/emotives and precomputed metrics onto `Prediction` objects that have already survived the top-K prune.
- `_build_predictions_batch` now constructs `Prediction` objects with metadata placeholders during the initial scoring/pruning pass, and only calls `attach_pattern_metadata` on the survivors.
- This also merges what used to be two separate reads of the same ClickHouse rows into one.
- **Effect**: metadata-fetch cost is now bounded by `max_predictions * PRUNING_FACTOR` (default 300) regardless of corpus size or match rate, instead of scaling with the number of matched candidates.

### 2. Cross-worker statistics divergence fixed
- Root cause: `_global_metadata_cache` was a per-uvicorn-process, unconditionally-cached global metadata store with no cross-process invalidation signal. A write from one worker was invisible to any other worker's cache indefinitely.
- Fix: new `stats_version` — a nanosecond timestamp stored at Redis key `"{kb_id}:stats:version"`, written on every mutating metadata write. `get_all_symbols_optimized(collection, stats_version=...)` in `kato/storage/aggregation_pipelines.py` compares the caller's cached version against the current one and refetches on mismatch. The old unconditional cache was removed entirely.
- **Reproduced pre-fix**: a worker stuck at 0.049 vs. the correct 0.025 after a write from a different worker. **Confirmed fixed** post-fix.

### 3. Determinism fixes
- Three unordered float sums over `set`s made order-stable: `sorted(set(...))` in `kato/workers/pattern_processor.py`, and `symbol in sorted(symbols)` in `kato/informatics/metrics.py`. Root cause of the nondeterminism: float non-associativity combined with per-process Python string-hash randomization (each uvicorn worker iterates a `set` of the same strings in a different order).
- `rank_predictions()` (introduced in DECISION-031) re-confirmed to still provide a total ordering on `(metric, name)` at all three call sites after this session's restructuring.

### 4. Session leak fix
- The single-symbol fast path (`_predict_single_symbol_fast` in `pattern_processor.py`) now resets `self.future_potentials` before returning — previously left stale state that could leak into a subsequent request on the same processor.

### 5. Unchunked-query fix (extends DECISION-031's `METADATA_QUERY_CHUNK`)
- `METADATA_QUERY_CHUNK = 500` chunking moved *inside* `get_pattern_metadata_batch` in `kato/storage/clickhouse_writer.py`, so it covers every caller of that function, not just the one caller DECISION-031 originally patched.
- Previously, a large `max_predictions` could still build an unchunked `IN` list at a different call site, overflowing ClickHouse's `max_query_size` (262144 bytes). The resulting exception was swallowed, silently degrading every affected prediction to `frequency=1` and default metrics — a re-run of the exact silent-failure shape DECISION-031 fixed once already, just at a second call site.

### 6. Security/robustness hardening
- ClickHouse queries parameterized at additional call sites.
- New `kato/storage/identifiers.py`: `KB_ID_RE` and `PATTERN_NAME_RE` validate identifiers before they're inlined into statements that can't bind parameters (`DROP PARTITION`, `ALTER DELETE`).
- Error handlers in `kato/services/kato_fastapi.py` moved to module scope — they were dead code registered inside `on_event("startup")`, after Starlette had already snapshotted its middleware/exception-handler stack on first `__call__` (the same class of bug DECISION-030 fixed once before at a different registration site).
- CORS `allow_credentials=False`.
- A redundant `asyncio.Lock` that was being acquired twice per request removed.

## New Test and Tooling Assets

- **`scripts/check_prediction_parity.py`** — byte-for-byte prediction parity gate. Pins to one uvicorn worker via a keep-alive session (HTTP keep-alive pins to one worker — the same fixture behavior DECISION-031's testing lesson documented), guarantees `frequency > 1` and non-empty emotives in its corpus, and includes `PRUNED_PROBES` with a low `max_predictions` so the pruned path (the actual subject of this change) is genuinely exercised. Self-checks and refuses to report success without those signals — see the Process Lesson below on why that self-check exists.
- **`benchmarks/test_service_scaling.py`** — HTTP-level scaling benchmark with `--baseline` / `--keep` / `--rebuild`.
- **New unit tests**: `test_error_handlers.py` (7), `test_identifier_validation.py` (23), `test_observation_validation.py` (10), `test_processor_eviction.py` (3), `test_prediction_ranking.py` (7), `test_metadata_batch_chunking.py` (5), `test_stats_version.py` (6), `test_metadata_query_chunking.py` (6), `test_qdrant_client_api.py`.

## Process Lessons (three instances of the same failure mode — a verification that could not have failed)

1. **The `.dockerignore` fix was "verified" with zero `__pycache__` directories on disk, so it proved nothing.** 76 stale `.pyc` files still shipped in 5.1.1 despite the "fix." Corrected in 5.1.2 and re-verified with 17 caches genuinely present on disk during the check. Also: `.dockerignore` uses Go `filepath.Match` semantics, not gitignore syntax — it needs `**/` for nested paths.
2. **The parity gate initially did not exercise the pruned path** — its corpus produced only 17 predictions against a `max_predictions` threshold of 300, so pruning never actually engaged during the "parity" check. Fixed by adding a dedicated crowded corpus and `PRUNED_PROBES` with a deliberately low `max_predictions`.
3. **The chunking unit test asserted against `METADATA_QUERY_CHUNK`** — the very constant under test — so it passed even with chunking disabled entirely (nothing independent was actually being checked). Rewritten to bound expectations by `CLICKHOUSE_MAX_QUERY_SIZE` (262144) / `BYTES_PER_NAME` (44), an independent ceiling.

**General lesson**: a verification step that cannot fail under the bug it's meant to catch is not a verification — before trusting a "confirmed fixed," check that the check's inputs actually exercise the changed code path, and that its pass condition isn't circularly defined by the same constant being changed.

Also recorded this session: `pip-compile` must regenerate `requirements.lock` **in place** — writing to a fresh file gives it no existing pins to honor and bumps every dependency, not just the one intended. And `qdrant-client` is deliberately held at `<1.16` because 1.17 removed `QdrantClient.search()` and the resulting failure was swallowed rather than raised, silently degrading vector search.

## Verification

- Full suite: **625 passed / 3 skipped / 1 xfailed / 0 failed**
- ruff, bandit, pip-audit: all clean
- Cross-worker divergence reproduction and fix confirmed live
- Fresh-pull image verification (see `planning-docs/completed/features/2026-09-18-kato-v5.2.0-release.md`): `attach_pattern_metadata` present, metadata chunk size 500, 0 `.pyc` files shipped

## Decision Reference

**Decision**: DECISION-032 in `planning-docs/DECISIONS.md`
**Shipped in**: KATO v5.2.0 — see `planning-docs/completed/features/2026-09-18-kato-v5.2.0-release.md` and DECISION-033
**Related Files**: `kato/searches/pattern_search.py`, `kato/storage/redis_writer.py`, `kato/storage/aggregation_pipelines.py`, `kato/storage/clickhouse_writer.py`, `kato/storage/identifiers.py`, `kato/workers/pattern_processor.py`, `kato/informatics/metrics.py`, `kato/services/kato_fastapi.py`, `scripts/check_prediction_parity.py`, `benchmarks/test_service_scaling.py`, `tests/tests/unit/test_error_handlers.py`, `tests/tests/unit/test_identifier_validation.py`, `tests/tests/unit/test_observation_validation.py`, `tests/tests/unit/test_processor_eviction.py`, `tests/tests/unit/test_prediction_ranking.py`, `tests/tests/unit/test_metadata_batch_chunking.py`, `tests/tests/unit/test_stats_version.py`, `tests/tests/unit/test_metadata_query_chunking.py`, `tests/tests/unit/test_qdrant_client_api.py`
