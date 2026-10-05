# Entropy Metrics Flipped After finalize-training: Prediction-Time Fallback Computed Over `present`, Not the Whole Pattern

**Completed**: 2026-10-05
**Status**: COMPLETE, VERIFIED, **UNCOMMITTED** (in CHANGELOG "Unreleased"; not in v6.3.1)
**Decisions**: DECISION-047
**Type**: Bug (correctness). Silent: same pattern reported different metric values depending on whether finalize-training had run.

## Trigger
An external reviewer claimed the `hamiltonian` and `grand_hamiltonian` metrics are not implemented. Verified: they ARE implemented, renamed in commit `1bbb3ed` to `normalized_entropy` and `global_normalized_entropy` (`kato/informatics/metrics.py`; precomputed in `PatternProcessor.finalize_training`; returned on every prediction). The claim was a stale-name artifact, not a missing feature. The review did, however, surface a real bug.

## Symptom
Every learn clears stored metrics for the node, so predictions use a prediction-time fallback until finalize-training runs. The fallback computed the pattern-intrinsic metrics (`entropy`, `normalized_entropy`, `global_normalized_entropy`, `tfidf_score`) over `present` (matched events only); `finalize_training` computes them over the whole pattern. Values flipped after finalize-training (example: Shannon entropy 1.0 vs 1.92).

## Root cause
Two copies of each formula with different inputs. Additionally the fallback's `global_normalized_entropy` read probability 0 for past/future symbols, because `symbol_probability_cache` only covers matched + missing symbols.

## Fix
- Fallback now computes over the whole pattern (`prediction['pattern_data']`).
- New `_corpus_probability` helper in `kato/workers/pattern_processor.py` for symbols outside the cache.
- Both paths call `metrics.normalized_entropy` / `metrics.global_normalized_entropy` (inline duplicate formulas removed); those functions now always return float.
- Two wrong docstring examples in `metrics.py` corrected.
- Docs updated: entropy metrics are of the pattern's symbols, not `present` (`docs/reference/api/predictions.md`, `docs/reference/prediction-object.md`, `docs/users/api-reference.md`, `docs/users/predictions.md`); CHANGELOG Unreleased entry.

## Verification
- New `tests/tests/api/test_entropy_metrics_finalize_parity.py`: fails on released 6.3.1, passes on the fix.
- Full unit + integration + api suite: 841 passed, 2 skipped, 1 xfailed (documented multi-worker same-session limitation).
- 11 caplog errors were a test-invocation artifact (`-p no:logging`); that file passes 17/17 when run normally.

## Related files (all uncommitted)
`kato/informatics/metrics.py`, `kato/workers/pattern_processor.py`, `CHANGELOG.md`, the four docs above, `tests/tests/api/test_entropy_metrics_finalize_parity.py`.

## Lesson
Same family as the single-symbol parity bug (2026-10-05): a second copy of a formula drifts. See `project-manager/patterns.md`.
