# Vector modes and pattern lifecycle publication preparation

Date: 2026-09-18
Status: Prepared for publication; repository write access pending.

- Upstream base: `main` at `05e3e68def882d19ff8bbdb89210af55dbbf5498`.
- Prepared branch: `codex/kato-reliability-vector-modes-20260918`.
- Work was prepared in an isolated clone; the original working checkout was preserved.

## Scope

Port local KATO changes onto current upstream: configurable vector event modes and request-local vector search diagnostics, including the default vector search limit change to 20; opt-in single-symbol matching anywhere in the first event; durable ClickHouse inserts; generation-based metric-cache invalidation; distributed STM opt-out; exact interrupted-learn repair; and pattern retirement with verified physical purge.

Repair and lifecycle operations now follow upstream's ClickHouse metadata sidecar architecture. Purge removes and verifies sidecar rows, invalidates corpus-dependent metrics while preserving remaining patterns' emotives and metadata, and updates Redis statistics versions for other workers.

Host-specific Docker Compose rewrites, environment-file recovery changes, and ClickHouse broken-part recovery settings are excluded.

## Validation and remaining work

- 151 selected feature and upstream offline tests passed.
- Repository-wide Ruff checks passed.
- Final Python 3.10 Bandit security scan passed with zero findings.
- 11 tests covering the final SQL edits were rerun and passed after the preceding 151-test combined run.
- An isolated validation image was built; runtime services were unchanged.
- Publication awaits repository write access; no successful push is claimed here.

No live deployment or release was requested or performed.
