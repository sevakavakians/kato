# Event-Aware Alignment Refinement (Event-Mate + Tightness Rules)

**Completed**: 2026-09-11
**Commit**: `34910a70` "fix(predictions): attribute repeated symbols to the event their neighbours matched"
**Decision**: DECISION-029 (`planning-docs/DECISIONS.md`, extends DECISION-028)
**Type**: Bug Fix (prediction segmentation) — addendum to the position-based segmentation fix shipped as `e0ee17d`

## Background
DECISION-028 (`e0ee17d`, same day) made prediction segmentation position-based, deriving `past`/`present`/`future`/`missing`/`extras` from the matcher's matched pattern/state indices instead of a flat-slice symbol-identity heuristic. While implementing that fix, the user spotted a residual case: the matcher still aligns the **flattened** symbol sequence and has no notion of event boundaries, so when a symbol recurs across events, difflib's longest-run tie-break can still land the match on the wrong occurrence.

An independent audit of all 34 outcomes in `tests/tests/unit/test_multi_symbol_event_predictions.py` (byte-for-byte reproduction against the actual matcher output) found two real bugs:
- **`#26`** `test_repeated_symbol_dropped_once[drop-event1-y]` — pattern `[['x','y'],['y','z'],['x'],['w','y','z']]`, observed `[['x','y'],['z'],['x'],['w','y','z']]` (event 1's `'y'` dropped). Recorded `missing=[['y'],[],[],[]]` (event 0), should be `[[],['y'],[],[]]` (event 1).
- **`#32`** `test_single_symbol_that_starts_the_pattern_with_repeats` — observed `[['x']]` against the REPEATS pattern should exact-match pattern event `['x']` (`present=[['x']]`, `missing=[[]]`, `confidence=1.0`), not partially match `['x','y']` (`present=[['x','y']]`, `missing=[['y']]`, `confidence=0.5`).

Four more outcomes (`#25`, `#28`, `#29`, `#31`) were right, but only by coincidence — the same underlying ambiguity happened not to produce a wrong answer for those specific inputs.

## Delivered

### Fix
`refine_alignment_by_events()` in `kato/representations/prediction.py`, called at the top of `segment_by_alignment()` (shared by the main prediction path and the single-symbol fast path). Two rules:
- **Event-mate rule** (pattern side and observed/state side, mirrored): a matched symbol is re-attributed to the pattern event where the other symbols of its observed event matched (and the mirror for extras) — if another event's neighbours already agree on it, move the match there.
- **Tightness rule**: a symbol observed alone with no event-mates moves to whichever unmatched same-symbol occurrence strictly reduces the total `missing` count.

A lexicographic potential function Φ (same-event neighbour agreement, then fewest missing) strictly increases on every move, guaranteeing termination and ruling out oscillation. Moves keep the alignment monotone and the matched symbols identical, so match count, `matches`, and `similarity` never change. The fuzzy-matching path is unaffected. An event-level DP alternative was considered and rejected — see DECISION-029 for the full rationale (Φ is pairwise, not an additive LCS objective).

### Tests
- New `tests/tests/unit/test_alignment_refinement.py` (23 pure-function tests): the three dropped-`'y'` variants, lone-symbol tightness (two shapes), the observed-side mirror case, unchanged-repeats/ragged shapes, invariants + idempotence, the short-circuit path, empty alignment.
- `tests/tests/unit/test_multi_symbol_event_predictions.py`: the two dropped-`'y'` variants now expect different `missing`; lone `'x'` expects `present=[['x']]` with `confidence=1.0`; new observed-side mirror case (pattern `[['a'],['b','c']]`, observed `[['a','b'],['b','c']]` → `extras=[['b'],[]]`).

### Docs
`docs/reference/prediction-object.md` — the event-mate/tightness rule documented under `missing`, plus a new "Known limitations" note; `CHANGELOG.md` `[Unreleased]` "Fixed" entry.

### Atlas Artifact
Regenerated and republished to the same URL (https://claude.ai/code/artifact/8f775ef3-10ee-4db2-8326-fe94ed1413eb) — "'y' dropped from event 1" now correctly marks event 1; lone `'x'` shows `present=[['x']]`.

## By-Design Behaviours Recorded (not bugs, not in scope)
- Split/merged events counting as full matches under flat matching.
- An out-of-order symbol legitimately appearing in both `past` and `extras` simultaneously.
- `missing` indexed by present-events while `extras` is indexed by observed-events (can differ in length).
- A never-observed middle pattern event looking identical to a partially-observed one in some representations.
- `_predict_single_symbol_fast`'s first-token-only matching restriction — remains a separate, still-open decision for the user.
- difflib's matched blocks not being LCS-optimal even though `similarity` is computed from a true LCS.

## Verification
- `tests/tests/unit/test_alignment_refinement.py` — 23 passed.
- Refinement + multi-symbol + hello-world suites — 61 passed.
- Prediction-neighbourhood suite — 148 passed.
- Full suite (`./run_tests.sh --no-start --no-stop`) — **552 passed / 4 skipped / 1 xfailed / 0 failed** (700.9s), +24 vs. the 528 baseline (23 new pure-function tests + 1 new mirror case in the multi-symbol suite).

## Deployment / Release Status
The local `deployment/` stack runs the dev `kato:latest` build with this fix. Released **v5.0.2 lacks both this fix and `e0ee17d`**. Two items remain pending on the user (see `planning-docs/project-manager/pending-updates.md`):
1. Whether to cut a **v5.0.3** patch release bundling `e0ee17d` and `34910a70`.
2. Whether `_predict_single_symbol_fast`'s first-token-only matching semantics should change.

## Related
- DECISION-029 (`planning-docs/DECISIONS.md`) — full rationale, rejected DP alternative, by-design list.
- DECISION-028 (`planning-docs/DECISIONS.md`) — the position-based segmentation this decision extends.
- `planning-docs/completed/features/2026-09-11-multi-symbol-event-prediction-tests-and-segmentation-fix.md` — the prior same-day fix this one follows up on.
