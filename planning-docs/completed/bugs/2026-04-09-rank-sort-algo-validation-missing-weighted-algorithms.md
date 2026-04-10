# Bug Fix: rank_sort_algo Validation Whitelist Missing Weighted Algorithms
*Completed: 2026-04-09*
*Status: FIXED - All tests passing (454 passed, 2 skipped, 0 failures)*

## Summary
The `validate_configuration_update()` method in `ConfigurationService` rejected all weighted `rank_sort_algo` values (`weighted_similarity`, `weighted_evidence`, `weighted_confidence`, `weighted_snr`) with HTTP 400 because they were not included in the `valid_algorithms` whitelist. This silently prevented the affinity-weighted pattern matching feature (completed 2026-03-31) from being used via the session config update API.

## Root Cause
When the affinity-weighted pattern matching feature was added (2026-03-31), the `valid_algorithms` list in `configuration_service.py:240-248` was not updated to include the 4 new weighted ranking algorithms. The feature implementation touched `pattern_processor.py`, `pattern_search.py`, `prediction.py`, and `session_config.py`, but the validation layer in `configuration_service.py` was missed.

## Discovery Context
Discovered during the churn analysis emotives experiment in `kato-notebooks/kato-tutorials`. The notebook's parameter sweep sent `rank_sort_algo: "weighted_similarity"` via `POST /sessions/{id}/config`, which was silently rejected. The sweep code did not check the config update response status, so it continued with the previous (unweighted) config. Predictions then returned `None` for weighted fields, causing a `TypeError: '>' not supported between instances of 'NoneType' and 'int'`.

## Fix Applied
Added the 4 weighted algorithms to the `valid_algorithms` list in `kato/config/configuration_service.py`:
```python
valid_algorithms = [
    'potential', 'similarity', 'evidence', 'confidence', 'snr',
    'fragmentation', 'frequency', 'normalized_entropy',
    'global_normalized_entropy', 'itfdf_similarity', 'confluence',
    'predictive_information', 'bayesian_posterior', 'bayesian_prior',
    'bayesian_likelihood', 'tfidf_score',
    'weighted_similarity', 'weighted_evidence',    # NEW
    'weighted_confidence', 'weighted_snr',          # NEW
]
```

## Files Modified
- `kato/config/configuration_service.py` — Added 4 weighted algorithms to `valid_algorithms` list (line 240-248)

## Impact
- **Severity**: High — completely blocked the affinity-weighted pattern matching feature from working via the API
- **Scope**: Any client using weighted `rank_sort_algo` values via `POST /sessions/{id}/config`
- **Related Feature**: [2026-03-31-affinity-weighted-pattern-matching](../features/2026-03-31-affinity-weighted-pattern-matching.md)

## Test Results
- 454 total tests passing (up from 288 at feature completion — reflects test suite growth)
- Zero regressions introduced

## Completion Date
2026-04-09
