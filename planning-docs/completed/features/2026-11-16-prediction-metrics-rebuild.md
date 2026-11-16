# Prediction metrics rebuild (PR #22, DECISION-051)
*Merged 2026-11-16; gated and recorded 2026-11-16. UNRELEASED: release 7.0.0 (MAJOR) is next.*

## Delivery
- origin/main = `dff5169`, merge of PR #22 (branch `feat/prediction-metrics`), 2026-11-16.
- Commits: `1cdd8c1` feat(predictions): good-odds, the trained potential and the proper Bayesian fields; `3a6b413` test(predictions): pin the new metric values and the scoring order; `bd221aa` docs(predictions): the delivered formulas, a table of every metric, measured accuracy.
- Merged before it: PR #21 (`bcc0849` merge, `beed420` docs(config): show how much of a pattern each recall_threshold requires). Also in Unreleased since 6.4.3: `02cd5d2` kato-manager.sh override fix.
- Provenance: done and accepted by the user in another Claude session without Docker or planning-docs access. This session pulled it (local main fast-forwarded `9039d9c` -> `dff5169`), gated it and recorded it.
- Source of truth: `CHANGELOG.md` [Unreleased] (Upgrade notes first), `docs/reference/prediction-object.md`, `kato/informatics/prediction_metrics.py`, PR #22 description. Study code, data and fits are outside the repo in bundles the user holds; the fitting recipe is in `docs/research/potential-function.md`.

## User decisions (2026-11-16)
1. `good_odds` joins every prediction, named for I. J. Good: prior log-odds plus weight of evidence equals posterior log-odds.
2. `potential` is a weighted sum of eleven terms; weights fitted once, constants in code (`POTENTIAL_WEIGHTS`); nothing fitted at prediction time, no seed.
3. `total_pattern_frequencies` counts every learn, as documented (used to go up only for a new pattern).
4. `bayesian_prior`, `bayesian_likelihood`, `bayesian_posterior`, `predictive_information`, `confluence` and `future_potentials` get proper formulas, stated in `docs/reference/prediction-object.md`.
5. Every numeric prediction metric is a `rank_sort_algo` value (24 of them).
6. Docs state the new formulas with no notes about what changed, and carry a table of every metric and its measured accuracy.

## Consequences reviewed and accepted the same day
- (a) `potential` is exactly the trained sum. `onset_alignment` no longer added for a single-event STM; position enters via `evidence_to_end`. Affinity-weighted metrics no longer enter `potential`; a session with `affinity_emotive` must set `rank_sort_algo` to a weighted metric to rank by affinity.
- (b) A `future_potentials` entry is `{next_event, probability, supporting_patterns}`: grouped by next event, weighted by `e^potential`, over every candidate. `chance_posterior` returned beside it. Old keys `future`, `aggregate_potential`, `total_weighted_frequency` gone.
- (c) `pattern_probability` and `weighted_strength` removed from predictions. `kato/informatics/predictive_information.py` and `metrics.confluence()` removed.
- (d) Every candidate above `recall_threshold` scored before the cut to `max_predictions`; the `max_predictions` x 3 pre-prune is gone. Values no longer depend on `max_predictions`, candidate arrival order or ranking key. Measured on a generated node of 20,000 patterns: 11.5% more time in the prediction path, plus a Redis read of every candidate's frequency. Not measured on the live instance.
- (e) A prior never exceeds 1. On a node whose counter is behind, priors are taken against the candidates' own total and a warning names the recount script; a purge of a pattern learned more often than the counter holds is refused.
- (f) `itfdf_similarity` and `tfidf_score` no longer depend on which candidates were kept.
- (g) `CachedMetricsCalculator` and `conditionalProbability` stay in the code, unused by the prediction path.

## Evidence
57 data sets (generated libraries, HDFS logs, MSNBC click streams, WikiText-2), 117,200 test queries read once. CHANGELOG: top prediction with a future names the right next event 63.1% vs 43.1% for the previous formula (mean of four kinds of data). Per-metric tables: `docs/reference/prediction-object.md` "Measured Accuracy".

## Gate (2026-11-16, this session, 15:33-15:44 EST)
- Before: CI on `dff5169` green (ruff, bandit, pip-audit, `tests/tests/unit/` 817 passed).
- `:8000` found as documented: `deployment/` stack, `ghcr.io/sevakavakians/kato:6.4.3` (repo digest `sha256:0b79f5ec...8756`), `KATO_WORKERS=4`, override pins 6.4.3, root-compose stack down.
- Playbook: Redis BGSAVE, snapshot of `kato_redis-data` to the session scratchpad (`kato_redis-data-pre-7.0.0-gate.tgz`, 115 MB); durable Redis keys (not `test*`, `kato:session:`, `stm:`) = 813 (6.4.3 record: 814 on 2026-11-11; live stack in use since; full key list diffed, not just counted); `deployment/` stack stopped with `docker compose down` (volumes kept); `docker compose build --no-cache kato`; `./start.sh start` (root compose, same `kato_*` volumes); durable key set identical after start; `KATO_WORKERS=4 ./run_tests.sh --no-start --no-stop`.
- Result on `dff5169`: **1092 passed, 3 skipped, 1 xfailed, 0 failed, 689.62s (11m29s)**. Skips and xfail same as the 6.4.3 gate: `test_websocket_endpoint`, `test_metrics_collection_after_requests`, `test_multi_worker_throughput_and_integrity` skipped; strict xfail `test_concurrent_session_modifications`. 6 warnings (redis `setex` DeprecationWarning in `test_redis_sessions.py`, pre-existing).
- Per directory: unit 817, integration 162, api 111, performance 6 (= 1096 outcomes). At v6.4.3 the same collection gives 644/160/112/6 = 922 = 918+3+1. Difference: unit +173 (the brief said the unit suite grew from 684; it was 644 at both v6.4.3 and `9039d9c`), integration +2 (`test_predictive_information_e2e.py` replaced 4 tests with 6), api -1 (`test_single_symbol_path_parity.py` field parametrize dropped `pattern_probability` and `weighted_strength`, added `good_odds`).
- Changed non-unit files, all passed on the live stack: `api/test_single_symbol_path_parity.py` 20, `integration/test_predictive_information_e2e.py` 6, `integration/test_pattern_purge_redis.py` 30. No test changed in this session; no commits besides planning-docs.
- After: durable key set identical (813) to the pre-gate snapshot; root stack down; `deployment/` stack restarted with `./kato-manager.sh start` (override pin still 6.4.3, loaded by the `02cd5d2` fix); kato image unchanged, `/health` healthy, `/` reports 6.4.3, `KATO_WORKERS=4`, `NO_PROXY` set, dashboard :3001 HTTP 200. `scripts/recount_pattern_frequencies.py` not run.

## Release impact and next steps
- MAJOR (7.0.0) per `docs/maintenance/releasing.md`: response schema changed (`future_potentials` keys; `pattern_probability` and `weighted_strength` removed), core algorithms changed, existing nodes need a one-time recount (`scripts/recount_pattern_frequencies.py`; NOT run anywhere yet; NOT in the image, the Dockerfile copies only `kato/`).
- Next: release 7.0.0 (MAJOR), then a second planning pass.
- Open: the 11.5% cost is not measured on the live instance; the recount has not been run on live node data.
