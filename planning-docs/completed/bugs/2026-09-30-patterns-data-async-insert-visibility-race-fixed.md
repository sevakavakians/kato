# patterns_data async_insert Visibility Race Fixed — Predictions After a Learn Could Return Nothing

**Completed**: 2026-09-30
**Status**: COMPLETE, VERIFIED, **COMMITTED and MERGED to `main`** — fix commit `c050119`, merge commit `92a977c` (PR #9)
**Decision**: DECISION-041 (`planning-docs/DECISIONS.md`)
**Type**: Bug fix (correctness under load) — closes a P2 backlog item open since 2026-06-18 and a related dead-no-op tech-debt item

## Summary

A prediction issued shortly after a learn could return nothing. `patterns_data` is inserted with `wait_for_async_insert=0`, so a written row sits in ClickHouse's server-side async buffer and is not queryable until that buffer flushes. ClickHouse adapts the flush delay between `async_insert_busy_timeout_min_ms` and `_max_ms` (50ms/200ms by default), *increasing* it under load — so the visibility window is widest exactly when traffic is heaviest. `finalize_training` is documented as optional, so predicting immediately after learning is supported usage, not a misuse pattern.

This closes the P2 bug already tracked in `SPRINT_BACKLOG.md` ("patterns_data async_insert visibility race (Root cause #1)", identified 2026-06-18) and the related P3 tech-debt item ("`has_pending`/`flush_if_pending()`/`flush_all_pending_writes()` are permanent no-ops at `DEFAULT_BATCH_SIZE=1`").

## Root Cause

The read paths already had code that *looked* like it handled this — `predictPattern` and `getPattern` called `flush_if_pending()`, which reads as "make recent writes visible" but actually drains only the **client-side** write buffer, permanently empty at `DEFAULT_BATCH_SIZE=1` (every insert flushes immediately client-side; there is never anything pending to flush). It was a no-op that had been silently relied upon as the fix. The function that actually performs a server-side drain, `flush_async_insert_queue()` (`SYSTEM FLUSH ASYNC INSERT QUEUE`), was reachable only from `finalize_training` and `get_pattern_count` — never from the prediction read path.

Confirmed directly from the server's own log, not inferred: for one symbol, the single-symbol fast path logged
```
14:39:44.248  No patterns found starting with symbol 'stale_head_6'
14:39:44.430  Found 1 patterns starting with symbol 'stale_head_6'
```
the same query, 182ms apart, with nothing changed but time.

## What Changed

`ClickHouseWriter.ensure_visible(stats_version)` (new) performs the real drain (`flush_if_pending()` + `flush_async_insert_queue()`), gated on the Redis `{kb_id}:stats:version` stamp so it is skipped unless a learn has landed since the last drain. Two properties make that stamp the correct gate:

1. It is written **after** `write_pattern` enqueues the insert, so observing a new version implies the row is already in the server's buffer and a drain will expose it.
2. It is shared across uvicorn workers, which an instance flag could not be — each worker process holds its own `ClickHouseWriter`, and a learn served by one worker must be visible to a prediction served by another.

Drains are therefore bounded by learns rather than by reads, which matters because `SYSTEM FLUSH ASYNC INSERT QUEUE` is server-global, not per-`kb_id`.

Wired in at `predictPattern` — the sole entry point for predictions, so one gate covers the single-symbol fast path too — and at `getPattern` for the point lookup. The previous 0.5s `time.sleep()` fallback inside `flush_async_insert_queue()` (used when the flush statement is refused for lack of privilege) is replaced by latching the refusal once per process with a loud warning: sleeping was tolerable at a training checkpoint but is unacceptable on a read path hit by every prediction.

`flush_if_pending()` itself remains in place (not deleted) and is still a functional no-op at `DEFAULT_BATCH_SIZE=1` — the tech-debt item's literal removal candidacy is unchanged — but it is no longer relied upon, alone, as the mechanism that makes recent writes visible. `ensure_visible()` is the real fix; calling the harmless no-op alongside it costs nothing.

New `tests/tests/fixtures/store_diagnostics.py`: an empty prediction result cannot otherwise be told apart from a pattern that was never written, one written but not yet queryable, or one present that the pipeline declined to select. Attaching that diagnostic state to the test assertion is what identified this bug, after two wrong initial guesses about the cause.

## Verification

- Cost measured: predictions that skip the drain are unchanged at **38.9ms median**; those that drain cost **44.5ms**, so **+5.7ms only on a prediction immediately following a learn**.
- The reproducer under concurrent load failed within ~5 attempts before the fix; **15/15 passed after**.
- Prediction output is **byte-identical** (`scripts/check_prediction_parity.py`).

## Known Limits (Recorded, Not Closed)

- **Residual window, not closed**: between `write_pattern` enqueueing the insert and `batch_update_symbol_stats` bumping the Redis version a few lines later, a reader can observe the old version and skip the drain. This gap is microseconds, not up to 200ms, and the *next* read self-corrects. It cannot be closed by reordering (bumping the version first would drain too early, before the row is even enqueued) — only by making the two-store write atomic, which is out of scope here.
- **Redundant server-global drains** when several nodes learn concurrently (2,197 observed in a 5-minute load test) — left in rather than coalesced, because coalescing would require comparing a Redis nanosecond timestamp against a local wall clock, which is unsound across machines with different clocks.

## Related

- DECISION-041 in `planning-docs/DECISIONS.md` — the decision to gate the drain on the Redis stats version rather than switching `patterns_data` to `wait_for_async_insert=1`.
- PR #9: https://github.com/sevakavakians/kato/pull/9 — "fix(predictions): drain the async_insert queue before reading patterns_data"
- Closes `SPRINT_BACKLOG.md`'s "Bug: patterns_data async_insert visibility race (Root cause #1)" (P2, open since 2026-06-18) and "Tech Debt: `has_pending`/`flush_if_pending()`/`flush_all_pending_writes()` are permanent no-ops" (P3).
- Likely also the root cause of the previously-logged flaky test `test_bayesian_likelihood_equals_similarity` ("Test Flakiness" entry in `SPRINT_BACKLOG.md`, same underlying async_insert visibility window) — not separately re-verified here, but the mechanism matches exactly.
