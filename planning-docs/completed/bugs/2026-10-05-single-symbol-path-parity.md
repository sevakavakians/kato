# Single-Symbol Prediction Path Returned a Different Prediction From the Normal Path

**Completed**: 2026-10-05
**Status**: COMPLETE, VERIFIED, COMMITTED (`c39ffa1`) and RELEASED as v6.3.1 (release commit `31923d2`, tag `v6.3.1`)
**Decisions**: DECISION-046
**Type**: Bug (correctness). Silent: wrong ranking key, missing fields.

## Symptom
A state of one symbol produced a prediction with fourteen fields absent and three fields (`potential`, `snr`, `evidence`) disagreeing with what the normal path computes for the same pattern.

## Root cause
The fast path hand-rolled prediction construction and returned early, carrying a comment that `predictPattern` would calculate the metrics. It never did. Every formula was a second copy free to drift.
- Absent (14): `predictive_information`, `confluence`, `entropy`, `normalized_entropy`, `global_normalized_entropy`, `itfdf_similarity`, `tfidf_score`, `pattern_probability`, `bayesian_prior`, `bayesian_likelihood`, `bayesian_posterior`, `weighted_strength`, `type`, `sequence`.
- Disagreeing (3): `potential` (ranking key; lacked the `itfdf_similarity` term), `snr` (`m/(m+x)` vs `(2m-x)/(2m+x)`; identical when no extras, so smoke tests passed), `evidence` (different divisor).

## Fix
`_single_symbol_candidates` selects candidates and builds Prediction objects through the shared constructor; `predictPattern` runs one shared tail for both strategies. `future_potentials` is now populated for one-symbol states. The retirement barrier moved into the shared tail (after selection, before pruning) because the fast path had applied it only inside the metrics loop that was removed; this was a regression caught before commit.

## Behaviour change
Single-symbol predictions no longer carry `pattern_data` or `length` (no other path ever did). `sequence` has identical content. PATCH classification rationale in DECISION-046.

## Verification
Parity against a parent-commit build: only the single-symbol probe changed, 13 multi-symbol probes byte-identical; `potential` 2.125 -> 3.125 (exactly the prediction's `itfdf_similarity`); field sets identical (35 each); formulas match to 1e-9. 21 new tests in `tests/tests/api/test_single_symbol_path_parity.py`. Full suite 855 passed / 3 skipped / 1 xfailed / 0 failed; ruff, bandit clean.

## Related files
`kato/workers/pattern_processor.py`, `tests/tests/api/test_single_symbol_path_parity.py`, `CHANGELOG.md` (6.3.1).

## Lesson
See `project-manager/patterns.md` (2026-10-05): a comment promising downstream work is a claim to verify; a smoke test that cannot produce the diverging input (no extras) cannot detect the divergence.
