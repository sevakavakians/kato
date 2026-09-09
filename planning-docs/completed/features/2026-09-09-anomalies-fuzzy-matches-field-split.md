# Feature/Breaking Change: Split `anomalies` into Flat Deviation List + New `fuzzy_matches` Field (+ Bundled Repeated-Symbol Bug Fix)

**Completed**: 2026-09-09
**Type**: Architectural decision (breaking API change) + bug fix + new test coverage
**Impact**: `anomalies` prediction field redefined (BREAKING for consumers reading fuzzy detail from it); new `fuzzy_matches` field added; repeated-symbol under-reporting in `missing`/`extras` fixed
**Decision**: DECISION-019 (`planning-docs/DECISIONS.md`)
**Files**: 3 code files, 3 test files (2 updated, 1 new), 8 doc files, `CHANGELOG.md`

---

## Summary

Three pieces of related work landed together, all touching the prediction pipeline's deviation-reporting fields:

1. **New test file** `tests/tests/unit/test_hello_world_character_predictions.py` — three tests that learn "hello world" one character per event and assert `past`/`present`/`future`/`missing`/`extras`/`anomalies` for observations `"hello"`, `"world"`, and the perturbed `"o wxld"`. All three pass.
2. **Bug fix** in `kato/representations/prediction.py` — event-aligned `missing`/`extras` (and the flat fallback `missing`) under-reported repeated symbols.
3. **Architectural decision** (DECISION-019, user chose from three presented options) — `anomalies` redefined as a flat list of every deviating symbol; the fuzzy-match detail records it used to hold move to a new `fuzzy_matches` field. This is a **breaking change** for API consumers reading fuzzy details from `anomalies`.

---

## 1. New Test Coverage

`tests/tests/unit/test_hello_world_character_predictions.py` — learns "hello world" one character per event (character-level STM), then asserts full prediction structure for three observation cases:
- `"hello"` — exact prefix match
- `"world"` — exact suffix match, including the repeated `'o'`
- `"o wxld"` — perturbed observation (space and substituted/missing characters), exercising `missing`/`extras`/`anomalies` together

All 3 tests pass.

---

## 2. Bug Fix: Repeated Symbols Under-Reported in `missing`/`extras`

**Root cause**: `missing`/`extras` computation (event-aligned and the flat fallback `missing`) used a flat `in` membership test against `matches`/`present`. Membership testing does not account for *how many times* a symbol was matched versus how many times it appears in the pattern — an earlier occurrence of a symbol satisfies the `in` check for every later occurrence too.

**Concrete manifestation**: learning "hello world" character-by-character, then observing the perturbed `"o wxld"` — the second `'o'` (from "world", now missing after the perturbation) was never reported as missing. The **first** `'o'` (from "hello", present earlier in the pattern) satisfied the `in matches` check, masking the fact that the second `'o'` was never actually observed.

**Fix**: `missing`/`extras` now consume `matches`/`present` as a **multiset**, via `collections.Counter`, so each occurrence of a repeated symbol is accounted for independently instead of collapsing to a single boolean membership check.

---

## 3. Architectural Decision: `anomalies` → Flat Deviation List, New `fuzzy_matches` Field

Full rationale, alternatives considered, and implementation detail: see **DECISION-019** in `planning-docs/DECISIONS.md`. Summary:

- `anomalies`: now a flat `list[str]` — every deviating symbol, in order: all `missing` symbols, then all `extras` symbols, then the `observed` token of each fuzzy match.
- `fuzzy_matches`: **new** field — the `{observed, expected, similarity}` records `anomalies` previously held.
- `Prediction`'s constructor kwarg renamed `anomalies` → `fuzzy_matches`; `anomalies` is now computed internally, after `missing`/`extras` (letting it reuse the corrected multiset accounting from the bug fix above).
- **Alternatives rejected**: (a) replacing `anomalies`'s meaning outright and dropping fuzzy detail — loses information with no migration path; (b) mode-dependent typing (`list[str]` vs `list[dict]` depending on `use_token_matching`) — inconsistent type by config, unsafe for generic prediction-consumer code.

### Code Changes
- `kato/representations/prediction.py` — constructor kwarg rename; `anomalies` computed after `missing`/`extras`; multiset accounting.
- `kato/searches/pattern_search.py` — both `Prediction()` call sites updated (`anomalies=` → `fuzzy_matches=`).
- `kato/workers/pattern_processor.py` — single-symbol fast-path dict now emits both `anomalies` and `fuzzy_matches`.

### Tests Updated
- `tests/tests/unit/test_fuzzy_token_matching.py` — 5 assertions updated to read `fuzzy_matches`; class renamed `TestAnomaliesStructure` → `TestFuzzyMatchesStructure`.
- `tests/tests/unit/test_filter_pipeline_parameters.py` — 1 assertion updated.

### Docs Updated (8 files)
`docs/reference/prediction-object.md`, `docs/reference/session-configuration.md`, `docs/reference/api/predictions.md`, `docs/reference/api/configuration.md`, `docs/research/pattern-matching.md`, `docs/users/predictions.md`, `docs/users/configuration.md`, `docs/users/api-reference.md`.

### Changelog
`CHANGELOG.md` `[Unreleased]` — "Changed (BREAKING)" entry for the `anomalies`/`fuzzy_matches` split, "Fixed" entry for the repeated-symbol bug.

---

## Verification

233 passed / 1 skipped across `tests/tests/unit/` prediction suites, `tests/tests/integration/` prediction suites, and `tests/tests/api/`.

**One failure, pre-existing and unrelated** (not part of this work): `tests/tests/api/test_monitoring_endpoints.py::TestMonitoringEndpoints::test_metrics_collection_after_requests` — `assert 3204.0 > 3204.0`. `/metrics` `total_requests` bounces between two values across consecutive reads (3208 → 1454 → 3208), consistent with per-worker in-process metrics under multiple uvicorn workers (no shared counter across `KATO_WORKERS`). Filed as a known issue/follow-up — see `planning-docs/SPRINT_BACKLOG.md`.

---

## Operational Notes (Knowledge Refinement)

- The live `kato` container on `:8000` belongs to the `deployment/` compose project (`deployment/docker-compose.override.yml` pins `image: kato:latest`). `docker compose restart` from the repo root does **not** pick up code changes against that container. Working rebuild sequence: `docker compose build kato` (repo root), then `docker compose -f deployment/docker-compose.yml -f deployment/docker-compose.override.yml up -d kato`.
- `./run_tests.sh` only honors its **first** path argument — a multi-file/multi-directory run needs pytest directly: `PYTHONPATH="$PWD:$PWD/tests" ./venv/bin/python -m pytest <paths...>`.

---

## Open Item — Flagged for Human Review, Not Decided

This is a breaking change to the prediction API contract. Whether it warrants a major version bump if released has **not been decided**. Flagged in `planning-docs/project-manager/pending-updates.md` rather than decided unilaterally. Nothing from this work has been committed yet.

## Completion Date
2026-09-09
