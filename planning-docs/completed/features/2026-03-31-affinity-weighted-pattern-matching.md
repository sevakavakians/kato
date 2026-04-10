# Completed Feature: Affinity-Weighted Pattern Matching
*Archived: 2026-03-31*

## Summary
Implemented Affinity-Weighted Pattern Matching — an opt-in feature that uses per-symbol affinity scores to weight prediction similarity metrics. When enabled via `affinity_emotive` session config, the prediction pipeline computes `weighted_similarity`, `weighted_evidence`, `weighted_confidence`, and `weighted_snr` using frequency-normalized affinity magnitudes, and feeds those into the `potential` ensemble ranking formula.

## Motivation
Raw pattern matching treats all symbols as equally important. Symbol affinity (introduced 2026-03-27) accumulates emotive signal per symbol across learning history. This feature closes the loop by using that signal to amplify predictions whose matched symbols carry stronger emotive weight — enabling affect-sensitive retrieval without changing the deterministic core.

## Implementation Details

### Configuration
- `affinity_emotive: Optional[str]` added to `SessionConfiguration` (`kato/config/session_config.py`)
- Feature is fully opt-in: if `affinity_emotive` is not set, all weighted fields remain `None` and behavior is identical to pre-feature baseline

### Weight Computation
- `_compute_affinity_weights(symbols, kb_id, affinity_emotive)` added to `PatternProcessor`
- Formula: `weight[s] = |affinity[s]| / (freq[s] + epsilon)` — frequency-normalized affinity magnitude
- Uses new batch read methods `get_symbol_affinity_batch()` and `get_symbol_frequencies_batch()` in `redis_writer.py` (single pipeline per call, no per-symbol round-trips)

### Prediction Class Extensions
- `Prediction` dataclass updated with four new optional fields:
  - `weighted_similarity` — affinity-weighted match similarity
  - `weighted_evidence` — affinity-weighted evidence score
  - `weighted_confidence` — affinity-weighted confidence
  - `weighted_snr` — affinity-weighted signal-to-noise ratio
- Fields are `None` when feature is inactive; present when `affinity_emotive` is set

### Integration Points
- `extract_prediction_info` in `kato/searches/pattern_search.py` accepts optional `weights` dict and computes weighted metrics when provided
- Both `predictPattern` and `_predict_single_symbol_fast` in `kato/workers/pattern_processor.py` call `_compute_affinity_weights()` and pass weights into `extract_prediction_info`
- Weighted metrics participate in the `potential` ensemble ranking formula when active

## Files Modified
- `kato/storage/redis_writer.py` — Added `get_symbol_affinity_batch()` and `get_symbol_frequencies_batch()`
- `kato/searches/pattern_search.py` — Extended `extract_prediction_info` with optional `weights` dict and weighted metric computation
- `kato/workers/pattern_processor.py` — Added `_compute_affinity_weights()`; integrated into both prediction paths
- `kato/representations/prediction.py` — Added `weighted_similarity`, `weighted_evidence`, `weighted_confidence`, `weighted_snr` fields
- `kato/config/session_config.py` — Added `affinity_emotive: Optional[str]`
- `tests/tests/unit/test_affinity_weighted_matching.py` — 12 new unit tests (new file)

## Test Results
- 12/12 new affinity-weighted matching unit tests passing
- 288/288 total unit tests passing
- Zero regressions introduced

## Key Design Properties
- **Opt-in**: Feature activates only when `affinity_emotive` is set in session config; zero behavioral change for existing sessions
- **Backward compatible**: All new `Prediction` fields are `Optional`; clients that do not read them are unaffected
- **Batch-efficient**: Two batch Redis reads per prediction call regardless of candidate set size (no per-symbol round-trips)
- **Frequency-normalized**: Raw affinity divided by symbol frequency prevents high-frequency symbols from dominating purely due to exposure volume
- **Deterministic**: Same session config + same patterns + same observations produce identical weighted scores (consistent with KATO's determinism guarantee)
- **Non-destructive**: Existing similarity, evidence, confidence, and SNR fields are unchanged; weighted variants are additive

## Follow-Up Bug Fix
**2026-04-09**: The `valid_algorithms` whitelist in `configuration_service.py` was not updated to include the 4 weighted `rank_sort_algo` values, causing config updates with weighted algorithms to be rejected with HTTP 400. Fixed in [2026-04-09-rank-sort-algo-validation-missing-weighted-algorithms](../bugs/2026-04-09-rank-sort-algo-validation-missing-weighted-algorithms.md).

## Completion Date
2026-03-31
