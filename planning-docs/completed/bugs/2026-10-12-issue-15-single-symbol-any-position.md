# Issue #15: Single-Symbol Queries Omit Patterns When the Symbol Is Not First

**Completed**: 2026-10-12 (merged and released as v6.4.0)
**Decision**: DECISION-048
**PR / commits**: PR #16 merged to `main` as merge commit `5252143`; fix commit `81f408d` (fix: match a lone symbol anywhere in a pattern; add cohesion and onset metrics); planning commit `e730e96`. Issue #15 closed automatically on merge. Branch `fix/issue-15-single-symbol-any-position`.
**Release**: v6.4.0 (MINOR). See `completed/features/2026-10-12-kato-v6.4.0-release.md`.

## Root cause
`PatternProcessor._single_symbol_candidates` selected only `first_token = symbol` and re-checked `pattern_data[0][0] == symbol`. Events are sorted alphabetically, so eligibility depended on sort order within the first event (`[[A,B,C],[marker]]`: lone `A` matched, `B`/`C`/`marker` never did). Arbitrary, and inconsistent with the multi-symbol path (matches anywhere). It had been documented as a known limitation and tracked since 2026-09-11 (left open by DECISION-046).

## Fix
1. Candidate selection matches the symbol anywhere via ClickHouse `has(token_set, symbol)` (existing `idx_token_bloom`); positional filter dropped; threshold stays 0.0 (applying `recall_threshold` would drop long patterns returned today); parameter binding kept.
2. New prediction fields: `event_cohesion` (position-free, reported only) and `onset_alignment` (first non-empty STM event's best overlap / (1+j), position-decaying), via `event_overlap_metrics()` in `kato/representations/prediction.py`. Onset computed from `pattern_data`, not `past`.
3. `onset_alignment` joins `potential` and the top-K `_pre_potential` only for single non-empty-event STMs; multi-event rankings unchanged.
4. Both fields added to `rank_sort_algo` allowlists (`session_config.py`, `configuration_service.py`).
5. Docs and CHANGELOG updated; 15 new tests in `tests/tests/unit/test_single_symbol_any_position.py`.

## Verification
Full serial suite against source on :8011 (the :8000 deployment untouched): 868 passed, 1 skipped, 2 unrelated failures (`test_concurrent_session_modifications`, identical on `main`; `test_metrics_collection_after_requests`, flaky). Issue repro: on `main` a lone B/C/marker returned nothing; on the branch all return the pattern with correct segmentation; an absent symbol returns nothing.

## Open follow-ups
- Benchmark single-symbol candidate volume on a large node (result sets grow before pruning).
- Open question, user undecided: whether `event_cohesion` should enter `potential`; pending a ranking benchmark.
- Onset weighting is a heuristic; validate against a real corpus.
