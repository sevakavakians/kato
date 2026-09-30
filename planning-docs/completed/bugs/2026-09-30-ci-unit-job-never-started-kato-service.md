# CI Unit Job Never Started a KATO Service — 291 Skipped, 10 Failed, Red on Every Commit for 9 Days

**Completed**: 2026-09-30
**Status**: COMPLETE, VERIFIED, **COMMITTED and MERGED to `main`** — fix commit `a264dc2`, merge commit `7c7e2c0` (PR #8)
**Decision**: None filed — straightforward CI infrastructure fix, no architectural tradeoff
**Type**: Bug fix (CI infrastructure)

## Summary

The "Unit tests" CI job started Redis, Qdrant, and ClickHouse but never started a KATO service itself, even though `tests/tests/unit/` is only partly in-process — the rest talks to a running server over HTTP. Result, on every commit since the CI workflow was added (9 days of red CI): 291 tests skipped for want of a service, and the 10 tests in `test_error_handling.py` failed outright, because that file calls `requests` directly rather than going through the `services_available` guard the fixture-based tests use, so each one exhausted its retry budget against a closed port. The job took roughly 59 minutes and reported failure every time — red regardless of the actual change, making it useless as a signal.

## What Changed

`.github/workflows/ci.yml`'s unit-test job now starts `uvicorn` against the existing service containers and waits for `/health` before running the suite. The server log is printed unconditionally (a 500 raised inside a request only shows its traceback there; test output alone only shows a status code).

Two non-obvious settings were required, not just "start the server":

1. **`REDIS_ENABLED=true` is required.** Without it, `SuperKnowledgeBase` refuses to build a Redis client and every `observe` call returns 500 — but `/health` and session creation still succeed, because the session manager holds its own independent connection. The service therefore looks healthy while every observe fails, and the failures read like test bugs rather than a missing environment variable. The Docker Compose stack sets this explicitly; the CI workflow had been inheriting the (disabled) default.
2. **`KATO_WORKERS` is pinned to 1.** Several tests gate behavior on it — the same-session write-serialization guarantee (DECISION-024) only holds under a single worker — and `run_tests.sh` normally detects the worker count from the running container, which does not exist in this CI context. Left unset, those gates default to 1 while the server could in principle be running more, turning a strict `xfail` into a hard failure.

## Verification

Locally, with the runner's environment: **10 failed / 220 passed / 291 skipped in 58m37s** → **521 passed, nothing skipped, in 5m03s**. On the actual GitHub Actions runner (verified before merging): **10 failed / 220 passed / 291 skipped in 58m37s** → **521 passed, nothing skipped, in 1m33s**. The 291 previously-skipped tests now execute in CI for the first time, including the session, observe, and predict HTTP surface.

## Commit Status

**Committed and merged.** Fix commit `a264dc2` "fix(ci): run a KATO service for the unit suite"; merge commit `7c7e2c0` "Merge branch 'fix/ci-start-kato-service'" (PR #8) on `main`.

## Related

- PR #8: https://github.com/sevakavakians/kato/pull/8 — "fix(ci): run a KATO service for the unit suite"
- Distinct from the earlier 2026-09-21 CI fix (DECISION-038, "Initialise ClickHouse schema" step) — that fix made the schema-init step itself succeed; this fix addresses a separate gap where the unit-test step ran with no KATO service at all, discovered only after the schema-init step was already green.
