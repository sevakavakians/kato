# Single-Event vs. Multi-Event Pattern Grouping — Investigation Closed, NOT A BUG

**Completed**: 2026-09-22
**Status**: COMPLETE — **NOT A BUG** (reported concern not reproduced); coverage gap and doc/docstring/API-message defects fixed instead. **UNCOMMITTED** as of this entry.
**Decision**: DECISION-039 (`planning-docs/DECISIONS.md`)
**Type**: Investigation (bug report, not reproduced) → Test coverage gap + documentation fixes + one cosmetic API bug

## Summary

The user suspected a bug in how KATO distinguishes a pattern learned as **one event** with multiple symbols (`observe(["hello","world"])` → `learn()`) from the same symbols learned as **two events** (`observe(["hello"])`; `observe(["world"])` → `learn()`). Expectation: after later observing only `["hello"]`, the one-event pattern should report `world` in `missing` (still part of the event you're inside), while the two-event pattern should report it in `future` (the next, not-yet-reached event).

**Finding: NOT A BUG.** Verified live against the running KATO 6.0.1 service (`localhost:8000`) with isolated `node_id`s. Actual behavior matched the user's expectation exactly:

| Pattern grouping | Observation | `present` | `missing` | `future` | `confidence` | Pattern hash |
|---|---|---|---|---|---|---|
| `[["hello","world"]]` (one event) | `["hello"]` | `[["hello","world"]]` | `[["world"]]` | `[]` | 0.5 | `3814b8c0...` |
| `[["hello"],["world"]]` (two events) | `["hello"]` | `[["hello"]]` | `[[]]` | `[["world"]]` | 1.0 | `7d0678ba...` |

Both patterns loaded into one node simultaneously produce two distinct, correctly-segmented predictions with no cross-talk. ClickHouse's stored `pattern_data` confirmed the two patterns nest differently (`[["hello","world"]]` vs. `[["hello"],["world"]]`) — they are genuinely different rows, not a query-layer artifact.

Both cases take the single-symbol fast path (`kato/workers/pattern_processor.py:1035`, `_predict_single_symbol_fast`), which since `e0ee17d` (DECISION-028, 2026-09-11) delegates to the same `segment_by_alignment()` (`kato/representations/prediction.py:206`) used by the general multi-symbol path — one segmentation implementation, not two that could silently diverge.

## What Changed

### `tests/tests/unit/test_multi_symbol_event_predictions.py` (coverage gap closed)
The existing 34-test atlas (DECISION-028) covered event-grouping semantics piecemeal but never ran this exact head-to-head comparison, and never with a single-symbol observation against a single-event pattern (the fast-path case). Added 4 tests:
- `test_one_event_grouping_puts_the_rest_of_the_event_in_missing`
- `test_two_event_grouping_puts_the_next_event_in_future`
- `test_groupings_of_the_same_symbols_learn_as_distinct_patterns`
- `test_both_groupings_coexist_and_predict_side_by_side`

### `kato/workers/pattern_processor.py:318`, `kato/workers/pattern_operations.py` (2 places) — wrong docstrings
All three claimed patterns "shorter than two events" (or "only one event") are not learned. The actual guard is `len(pattern) <= 1`, and `Pattern.__len__` counts **symbols**, not events — a single event of 2+ symbols genuinely is learned. Docstrings corrected to describe the symbol-count threshold and to note that event grouping is part of a pattern's identity.

### `docs/users/concepts.md` — wrong user-doc examples
- "Simple Sequential Match" example showed a prediction for observing `[['B']]` against `[['A'],['B'],['C']]` — that observation actually returns **no prediction** (the fast path only considers patterns whose first token matches; `'B'` isn't a first token). Corrected to observe `[['A']]`, with a note on the fast-path restriction.
- Two examples showed flat `missing: []` / `extras: []` instead of the actual nested, event-aligned form (`[[], []]`). Corrected.
- Added a short section explaining that event grouping is part of what gets learned, with the `hello`/`world` one-event-vs-two-event contrast as the illustration.

### `docs/reference/prediction-object.md` — internally inconsistent doc
One example showed flat `missing: ["b","d"]` while the rest of the file consistently shows the nested, event-aligned form. Corrected to `[["b"], ["d"]]`. Added a note under `future` documenting the event-grouping distinction this investigation was about.

### `kato/api/endpoints/sessions.py:504` — cosmetic API bug (real, unrelated to the reported concern)
`POST /sessions/{id}/learn`'s response message was built from `len(session.stm)` **after** `session.stm` had already been reassigned to the post-learn remainder, so every learn response read "Learned pattern ... from 0 events" regardless of the actual count. Fixed by capturing `learned_event_count = len(session.stm)` before calling `processor.learn()`.

```python
# before
pattern_name, new_stm = await processor.learn(session_state=session)
session.stm = new_stm
...
message=f"Learned pattern {pattern_name} from {len(session.stm)} events"  # always 0

# after
learned_event_count = len(session.stm)
pattern_name, new_stm = await processor.learn(session_state=session)
session.stm = new_stm
...
message=f"Learned pattern {pattern_name} from {learned_event_count} events"
```

**Not yet verified at runtime**: the live deployment serves `ghcr.io/sevakavakians/kato:6.0.1` from `deployment/docker-compose.yml`, not a locally rebuilt image, and was not restarted during this investigation (26h uptime, 191 active sessions at time of investigation). The "from 0 events" message remains live in production until a rebuild/redeploy.

## Verification

Full local unit suite: `./run_tests.sh --no-start --no-stop tests/tests/unit/` → **492 passed** in 319s. No test behavior changed apart from the 4 new tests; the API message-string fix changes response text only (no return value, status code, or schema change), so no existing test needed updating and none broke.

## Commit Status

**Not committed.** 6 files modified in the working tree: `docs/reference/prediction-object.md`, `docs/users/concepts.md`, `kato/api/endpoints/sessions.py`, `kato/workers/pattern_operations.py`, `kato/workers/pattern_processor.py`, `tests/tests/unit/test_multi_symbol_event_predictions.py`. See `planning-docs/project-manager/pending-updates.md` for the open commit + rebuild/redeploy decision.

## Related

- DECISION-039 in `planning-docs/DECISIONS.md` — full investigation writeup, rationale for closing as not-a-bug, and open items.
- DECISION-028 (2026-09-11) — introduced `segment_by_alignment()` and the single-symbol fast path's use of it; this investigation confirmed both still correctly distinguish event grouping.
- DECISION-029 (2026-09-11) — the related event-misattribution fix (`refine_alignment_by_events()`); addresses a different case (symbol recurrence across events), not implicated here.
- `planning-docs/project-manager/pending-updates.md` — open item: commit the working tree; rebuild/redeploy to verify the cosmetic API-message fix at runtime.
- `planning-docs/project-manager/patterns.md` — new knowledge-refinement entry: user-suspected bug not reproduced; investigation methodology (live verification + direct ClickHouse cross-check) that closed it with high confidence.
