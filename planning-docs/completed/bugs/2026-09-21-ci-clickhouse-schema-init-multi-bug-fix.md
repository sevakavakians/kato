# CI ClickHouse Schema Init Failure — Three-Bug Fix (Including a Latent Helm Production Bug)

**Completed**: 2026-09-21
**Status**: COMPLETE, VERIFIED, **COMMITTED and PUSHED**, **FULLY RESOLVED** — `3706e73` on `origin/main`; no live Helm deployments existed, so the latent bootstrap defect never affected a real deployment
**Decision**: DECISION-038 (`planning-docs/DECISIONS.md`)
**Type**: Bug fix (CI infrastructure) — surfaced a second, more serious latent bug (Helm production bootstrap never applying schema; confirmed to have had zero real-world impact since no deployments existed)

## Summary

The "Unit tests" CI job has been failing on `main` since the CI workflow was added — the "Initialise ClickHouse schema" step exited with curl code 22 (most recently run `35632623893`, 2026-09-21). Root-causing it empirically against a throwaway `clickhouse/clickhouse-server:24.8` container turned up **three separate bugs**, only the first of which was the visible CI symptom:

1. **CI sent the whole `init.sql` file as one HTTP POST.** ClickHouse's HTTP interface executes exactly one statement per request. Result: `Code: 62 ... Multi-statements are not allowed`. GitHub Copilot's suggested fix — appending `?multiquery=1` to the request URL — was tried and **does not work**: `Code: 115 ... Setting multiquery is neither a builtin setting nor started with the prefix 'SQL_' (UNKNOWN_SETTING)`. `multiquery` is a `clickhouse-client` CLI flag, not a server-side HTTP setting; there is no HTTP equivalent, which is exactly why the interface only accepts one statement per request.
2. **The CI clickhouse service container had no configured user/password**, so the stock image logs "disabling network access for user 'default'" and every request from the runner over the mapped port fails with `Code: 516 AUTHENTICATION_FAILED`.
3. **Latent production bug, found only because bug #1 forced a close read of how `init.sql` gets split into statements**: the Helm chart's pre-install/pre-upgrade bootstrap hook (`charts/kato/scripts/bootstrap.py`) split `init.sql` on `;` and then dropped any resulting fragment that started with `--`. Every one of the file's 8 statements sits under a comment block, so the filter discarded each statement's comment *and, as a side effect, mis-segmented the split* — 8 statements collapsed to 3: a no-op `USE kato` and two `ALTER TABLE patterns_data` statements that fail with `UNKNOWN_TABLE` because the `CREATE TABLE` statements were never among the 3 survivors. **The Helm bootstrap Job had never actually applied the schema in any real deployment of this chart.**

## What Changed

### `config/clickhouse/init.sql`, `deployment/config/clickhouse/init.sql`, `charts/kato/scripts/init.sql` (kept byte-identical)
All tables database-qualified (`kato.patterns_data`, `kato.lsh_buckets`, `kato.pattern_stats`, `kato.patterns_metadata`); `USE kato;` removed. This is required, not cosmetic: the appliers (CI script, Helm bootstrap) send one statement per HTTP request with no session between requests, so `USE kato` from one request has no effect on the next — unqualified `CREATE TABLE` statements were silently creating tables in `default`.

### `scripts/apply_clickhouse_schema.py` (new)
Stdlib-only (no new dependency) applier used by CI and available for manual/ops use:
- Waits for ClickHouse's `/ping` endpoint, failing **explicitly** on timeout (the previous CI loop did not fail explicitly on timeout — it just ran out of retries and fell through to the broken multi-statement POST).
- Splits the schema file into individual statements (comment-aware — see the shared splitter below) and POSTs them one at a time.
- On a non-2xx response, prints ClickHouse's actual error response body instead of a bare curl exit code — the original failure (`curl code 22`) gave no indication which of the three bugs was in play.
- Takes `--wait <seconds>` (CI calls it with `--wait 60`).

### `.github/workflows/ci.yml`
- "Initialise ClickHouse schema" step now runs `python scripts/apply_clickhouse_schema.py --wait 60` instead of a raw `curl` against the whole file.
- The `clickhouse` service gains `CLICKHOUSE_SKIP_USER_SETUP: '1'` — CI-only; `docker compose` uses `users.xml` and the Helm chart uses secrets, neither of which needed a change for this.

### `charts/kato/scripts/bootstrap.py`
The `;`-then-drop-comment-lines splitter is replaced by a shared-rule `split_statements()` function — strips line comments (`--...`) before splitting on `;`, so a statement's leading comment block no longer causes it to be discarded. This function is a manual copy kept in lockstep with the same logic in `scripts/apply_clickhouse_schema.py`, not an import: `bootstrap.py` is vendored into a Helm `ConfigMap` and has no access to the rest of the repo at render/run time. See DECISION-038 for the explicit tradeoff (duplication vs. drift risk) and the guardrail adopted for it.

### `tests/tests/unit/test_clickhouse_schema_init.py` (new, 9 tests)
- Both splitters (the CI script's and the vendored Helm one) yield all 8 statements from the canonical `init.sql`.
- Each of the 4 tables is created exactly once across the 8 statements (guards against the old silent-collapse failure mode recurring).
- The schema is fully database-qualified with no `USE` statement present.
- The two mirror files (`deployment/config/clickhouse/init.sql`, `charts/kato/scripts/init.sql`) are byte-identical to the canonical `config/clickhouse/init.sql` (guards the three-way mirror against drift).

## Verification

- Both appliers (`scripts/apply_clickhouse_schema.py` and the corrected `charts/kato/scripts/bootstrap.py` splitter) were run **end-to-end and idempotently** against a real ClickHouse 24.8 container (not mocked): result was 4 tables created in the `kato` database, 3 data-skipping indexes present, **0 tables in `default`** (confirming the database-qualification fix actually closes the leak, not just removes the symptom).
- Full local unit test suite: **488 passed**, 0 failed.
- `ruff check kato/ tests/ benchmarks/`: clean.
- The `?multiquery=1` dead end (GitHub Copilot's suggestion) was tested against the real server and confirmed non-viable, not assumed — see DECISION-038 and `project-manager/patterns.md` for this as a logged knowledge-refinement item.

## Commit Status

**Committed and pushed.** Commit `3706e73` "fix(ci): apply the ClickHouse schema one statement per request" on branch `main` (previous HEAD `80901c5`), pushed to `origin/main`. The commit contains exactly the 7 source/config/test files: `.github/workflows/ci.yml`, `charts/kato/scripts/bootstrap.py`, `charts/kato/scripts/init.sql`, `config/clickhouse/init.sql`, `deployment/config/clickhouse/init.sql`, `scripts/apply_clickhouse_schema.py`, `tests/tests/unit/test_clickhouse_schema_init.py`. The planning-docs recording this fix were themselves committed as `723fc3c` "docs(planning): record the CI ClickHouse schema-init fix", also pushed to `origin/main`. CI run `35650420692` on `3706e73`: Lint, "Initialise ClickHouse schema", and Import check all green; the unit-test step was still running as of this update.

**Helm deployment impact — fully resolved.** The user confirmed no live Helm deployments of this chart exist as of 2026-09-21, so bug #3's defect never actually affected a real deployment — there was no database anywhere left uninitialized to remediate. **No manual schema re-application is needed.** This is closed because no deployment existed to be harmed by the defect, not because the old bootstrap logic turned out to work — it remained genuinely broken (8 statements silently collapsing to 3) for the entire period no deployment existed. The first real deployment made from this fixed chart will apply the schema correctly. See `project-manager/pending-updates.md` (RESOLVED).

## Related

- DECISION-038 in `planning-docs/DECISIONS.md` — full rationale, the `?multiquery=1` dead end, and the shared-splitter duplication tradeoff.
- `planning-docs/project-manager/pending-updates.md` — RESOLVED in place: both the commit/push portion and the Helm re-bootstrap decision (no live deployments exist, so no remediation needed).
- `planning-docs/project-manager/patterns.md` — new knowledge-refinement entry: ClickHouse HTTP interface is strictly one-statement-per-request with no multi-statement mode, and `multiquery` is a `clickhouse-client`-only flag with no HTTP equivalent.
- CI run that first surfaced this in its currently-failing form: `35632623893` (2026-09-21). CI run triggered by the fix's push: `35650420692` (2026-09-21, in progress at time of writing).
