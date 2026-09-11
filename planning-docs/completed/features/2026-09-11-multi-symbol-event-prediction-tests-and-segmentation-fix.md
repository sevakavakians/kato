# Multi-Symbol Event Prediction Test Suite + Position-Based Segmentation Fix

**Completed**: 2026-09-11
**Commit**: `e0ee17d` "fix(predictions): segment by matched positions; event-structured fast path"
**Decision**: DECISION-028 (`planning-docs/DECISIONS.md`)
**Type**: Feature (test coverage) + Bug Fix (prediction segmentation)

## Request
"Make variations on the hello-world prediction test — learned patterns with multiple symbols per event, varying sizes; observed states that are full, partial (first half, second half, middle), and mixed with missing/extra symbols; comprehensive tests for variations and edge cases."

## Delivered

### 1. New test file: `tests/tests/unit/test_multi_symbol_event_predictions.py` (34 tests)
Two learned patterns:
- **RAGGED**: events of 3/1/2/4/1/2 symbols (varying event widths)
- **REPEATS**: symbols recurring across events (stresses segmentation attribution)

Coverage: full pattern, first/second half, middle third, single wide event, dropped symbol, added symbol, mixed missing+extras across events, unexpected whole event between matches, first-and-last-only gap (everything between missing), one symbol from each of two events, event split across observations, two events merged into one observation, out-of-order events, duplicate symbol within an event, nothing-in-common → no prediction, repeats full, repeated-symbol-dropped (parametrized over which event; documents the flat-alignment tie rule), dropped-from-last-event, middle-two-events, single-first/last-event, mid-event start, mid-event end, single-first-symbol fast path (both patterns), single-mid-pattern-symbol → no prediction (pins the fast path's first-token filter), exact-match-outranks-near-twin, shared-prefix-predicts-both-futures.

### 2. Two prediction defects found and fixed in the same commit

**(a) Segmentation heuristic misattributed events with repeated symbols.**
`kato/representations/prediction.py` used to derive past/present/future from flat slice lengths, then applied a symbol-identity heuristic ("if the first matched symbol is in the last past event, move that event into present") to repair mid-event match starts. With a symbol recurring across events, the heuristic grabbed the wrong event — reporting phantom `missing` symbols that were never actually expected.

Fix: `extract_prediction_info` (`kato/searches/pattern_search.py`) now returns the matched pattern/state indices as an 11th tuple element (fuzzy path returns `None`, keeping legacy symbol-based accounting). New `segment_by_alignment()` (`kato/representations/prediction.py`) builds `present`/`missing`/`extras`/`past`/`future` directly from those positions — no heuristic. All tuple builders/unpackers updated; `tests/tests/unit/test_affinity_weighted_matching.py` unpacking adjusted to `result[:10]`.

**(b) Single-symbol fast path returned flat, non-event-structured fields.**
`kato/workers/pattern_processor.py::_predict_single_symbol_fast` hand-built `{'present': ['a']}`-style flat fields. Now calls `segment_by_alignment()` like every other prediction path.

### 3. Residual ambiguity documented (not a bug)
Matching runs on the flattened symbol sequence, so dropping either of two equal occurrences of a repeated symbol yields the identical observation; the matcher keeps the longest contiguous run, and the *earlier* occurrence is the one reported unmatched. Documented in `docs/reference/prediction-object.md` and the test docstring; pinned by a parametrized test.

### 4. Deferred question (filed for human decision — see `pending-updates.md`)
`_predict_single_symbol_fast` only considers patterns whose first token is the observed symbol (deliberate, for speed, via the ClickHouse `first_token` column). A lone mid-pattern symbol therefore yields no prediction even though it would match as part of a two-symbol observation. The new test pins current behavior; whether to change it (general-path match, at some performance cost) is left to the user.

### 5. Documentation
- `docs/reference/prediction-object.md`: repeated-symbol rule under `missing`; position-based segmentation + fast-path note added before `past`.
- `CHANGELOG.md`: `[Unreleased]` Added/Fixed entries.

## Verification
Full suite on the dev build: **528 passed / 4 skipped / 1 xfailed / 0 failed (699s)** — +46 versus the prior 482 baseline (34 new prediction tests + 12 cleanup self-tests from the previous, unrelated commit). Prediction-neighborhood suites (fields, misaligned, predictions, edge cases, comprehensive, metrics_v3, fuzzy, character-level, rapidfuzz, recall threshold, affinity, symbol affinity, predictive-info e2e) all green.

## Files Changed
- `kato/representations/prediction.py` (+216/-… — `segment_by_alignment()`)
- `kato/searches/pattern_search.py` (11th tuple element)
- `kato/workers/pattern_processor.py` (fast path uses `segment_by_alignment()`)
- `tests/tests/unit/test_multi_symbol_event_predictions.py` (new, 390 lines, 34 tests)
- `tests/tests/unit/test_affinity_weighted_matching.py` (unpacking adjusted)
- `docs/reference/prediction-object.md`
- `CHANGELOG.md`

## State / Follow-ups
- Deployment stack currently runs the local `kato:latest` dev build (override temporarily pointed at it). Released **v5.0.2** lacks these fixes — a **v5.0.3** patch release is warranted. Left to the user (see `planning-docs/project-manager/pending-updates.md`).
- Fast-path first-token-only matching semantics — human decision needed (see `pending-updates.md`).

## Related
- DECISION-028 (`planning-docs/DECISIONS.md`)
- DECISION-019 (2026-09-09) — the prior `anomalies`/`fuzzy_matches` split and multiset fix this builds on
