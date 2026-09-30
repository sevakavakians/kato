# Vector Modes Ported from a Collaborator's Branch (Session-Scoped Vector Event Modes, Metric-Cache Generation Token, Distributed-STM Opt-Out)

**Completed**: 2026-09-30
**Status**: COMPLETE, VERIFIED, **COMMITTED and MERGED to `main`** — merge commit `6a25b87` (PR #7), author commits `9da9d82`/`12a0cb6`/`01d3990` by Brian <briank.reed@icloud.com>, correction commit `6215504` by Sevak Avakians
**Decision**: DECISION-040 (`planning-docs/DECISIONS.md`)
**Type**: Feature (session-scoped vector configuration + diagnostics) + Performance (cache invalidation) — ported from an external collaborator's branch with three corrections applied before merge

## Summary

Ports the lower-risk half of a collaborator's (Brian Reed) branch `codex/kato-reliability-vector-modes-20260918` onto `main` (based on v6.0.2): session-scoped vector event modes with opt-in search diagnostics, generation-token metric-cache invalidation, and a distributed-STM opt-out. His three commits are preserved with him as author; a fourth commit applies three corrections found during review, authored by Sevak Avakians.

Deliberately **not** merged, still under review in PR #6: the pattern retirement/purge lifecycle (10 documented blockers), `single_symbol_match_mode` (reads `self.patterns_searcher.session_config` directly instead of taking a parameter, so it is inert on the observe path and leaks across sessions — not safe to ship as-is), and bumping `wait_for_async_insert` from 0 to 1 on `patterns_data` (wants a throughput measurement first; superseded in spirit by the separate async-insert visibility fix merged later the same day, see the async-insert-race archive entry).

## What Changed

### `vector_event_mode` (session-scoped, new)
`'neighbors_plus_self'` (default, unchanged behavior) or `'self_only'`, which skips the Qdrant neighbour search entirely and emits only the query vector's own ID as a symbol. Both modes still queue the vector for learning.

### `vector_search_limit` (session-scoped, new)
Nearest-neighbour count for the Qdrant search, range 1-100. **Kept at its previous hard-coded default of 3**, not raised to 20 as the source branch had it — see "Corrections Applied" below.

### `return_vector_search_results` (session-scoped, new, default `false`)
Opt-in request-local diagnostics attached to the observe response: query vector ID, requested limit, search status, metric, score direction, and ranked matches. An appended "self" ID (when `vector_event_mode='neighbors_plus_self'`) is reported with a null score and `source=self_appended` so it is never mistaken for a retrieved neighbour. These diagnostics are returned with the response only — never written to session state or into a learned pattern's events.

`VectorIndexer` gains `findNearestResults()`, returning full `VectorSearchResult` objects; `findNearestPoints()` remains as the existing ID-only wrapper used by the non-diagnostic path.

Config is threaded as parameters from `ObservationProcessor` down to `VectorProcessor.process()` — nothing is staged on processor instance state, consistent with the project's stateless-processor architecture.

### Generation-token metric-cache invalidation
Metric cache invalidation previously maintained a `kato:metrics:_index` Redis set and, on every learned pattern, scanned it and `UNLINK`ed each member — O(keys) per learn. Replaced with a generation token (`kato:metrics_generation:v1`) embedded in every cache key: rotating the token makes all prior keys unreachable in a single `SET`, O(1) regardless of index size. Scope is unchanged — the old `_invalidate_indexed_keys()` already invalidated every indexed key regardless of which pattern changed, so this is the same behavior at lower cost. Rotated-away values are not actively deleted; they lapse on their existing TTL. `CachedMetricsCalculator` pins one generation across lookup, compute, and publish, so an invalidation landing mid-calculation cannot poison the new generation.

### `KATO_DISTRIBUTED_STM_ENABLED` opt-out (new)
`get_distributed_stm_manager()` now returns `None` when this is set false/`0`/`no`. The distributed STM mirror is an optional cross-worker event log, not session STM or learned-pattern storage, so a single-worker deployment can skip it rather than accumulate a vector log nothing consumes. Default is unchanged (enabled); both existing call sites (`kato_processor.py:114`, `monitoring.py:209,213`) already guard on a falsy manager, so the opt-out degrades to local STM with no further code changes needed.

## Corrections Applied on the Way In (commit `6215504`)

Three corrections to the ported vector path, none changing the new opt-in behavior:

1. **`vector_search_limit` default kept at 3, not raised to 20.** The retrieved neighbour IDs become symbols in the STM event, which feed the learned pattern's SHA1 name. Raising the default would silently change the identity of every pattern learned from vector input going forward, making an existing corpus non-comparable with anything learned after the upgrade. 20 remains available per session via `vector_search_limit` — that is where a retrieval-recall change belongs, opt-in, not a silent default change. See DECISION-040 for the standing rule this establishes.
2. **`sorted(set(...))` instead of `list(set(...))`** for assembling vector symbols. Python `set` iteration order over strings varies with `PYTHONHASHSEED`, so the event — and the pattern hash built from it — was not reproducible across processes. The downstream sort that would have masked this is conditional on `sort_symbols`, which character-level matching turns off, so the nondeterminism was reachable in production configurations. New test fails under every hash seed tried with `list(set(...))` and passes with `sorted()`.
3. **A non-finite search score no longer raises** out of `_build_diagnostics`. Previously `ValueError` turned an otherwise-successful observation into a 500 over a reporting detail on an opt-in response field; the anomaly is now logged and the score reported as `null`.

## Verification

Verified against a container built from the branch: **521 unit, 127 integration (1 documented xfail), 49 api** tests pass; `ruff` and `bandit` clean; `scripts/check_prediction_parity.py` reports prediction output **byte-identical to v6.0.1**.

## Related

- DECISION-040 in `planning-docs/DECISIONS.md` — full rationale for the three corrections and the standing rule on `vector_search_limit`.
- PR #7: https://github.com/sevakavakians/kato/pull/7 — "Port vector event modes, metric-cache generation token and distributed-STM opt-out"
- Source branch: `codex/kato-reliability-vector-modes-20260918` (collaborator Brian Reed's work); PR #6 tracks the remainder still under review (pattern retirement/purge lifecycle, `single_symbol_match_mode`, `wait_for_async_insert` bump).
- Commits: `9da9d82` (metric-cache generation token), `12a0cb6` (distributed-STM opt-out), `01d3990` (vector event modes + diagnostics), `6215504` (three corrections), merge `6a25b87`.
