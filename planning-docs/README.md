# KATO Planning Documentation

## Overview
This directory contains planning and design documentation for the KATO (Knowledge Abstraction for Traceable Outcomes) project. The documentation is kept minimal and focused on current development needs.

## Quick Start for Development

### Essential Files (Read First)
1. **PROJECT_OVERVIEW.md** - Core project information and current status
2. **DECISIONS.md** - Important architectural and design decisions with rationale

### Reference Files
- **FUTURE_FEATURES.md** - Aspirational features and research ideas
- **ARCHIVE_SUMMARY.md** - Summary of completed major milestones
- **completed/** - Detailed documentation of completed work

### System Status Check
```bash
# Check KATO system status
docker compose ps

# Run all tests
./run_tests.sh

# View API health
curl http://localhost:8000/health
```

## Development Workflow

### Standard Development Commands
```bash
# Start KATO services
./start.sh

# Stop services
docker compose down

# Build and restart
docker compose up -d --build

# Run all tests
./run_tests.sh

# Run specific test categories
./run_tests.sh tests/tests/unit/
./run_tests.sh tests/tests/integration/
./run_tests.sh tests/tests/api/

# View logs
docker compose logs
docker logs kato --tail 50
```

### Service URLs (After Starting)
- **KATO Service**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs

### Common Development Tasks

#### Making Changes
```bash
# 1. Make code changes
vim kato/workers/kato_processor.py

# 2. Rebuild and restart
docker compose up -d --build

# 3. Run relevant tests
./run_tests.sh tests/tests/unit/test_processor.py

# 4. Run full test suite if major changes
./run_tests.sh
```

#### Adding New Features
1. Review existing code patterns for consistency
2. Implement following established patterns
3. Add comprehensive tests
4. Update documentation if needed
5. Document decisions in **DECISIONS.md** if architectural

#### Troubleshooting
- Check service status: `docker compose ps`
- View system logs: `docker compose logs`
- Test basic functionality: `curl http://localhost:8000/health`
- Run specific failing tests: `./run_tests.sh tests/tests/unit/test_failing.py`

## Current System State

**Version**: **5.0.2** — released 2026-09-10 via `./container-manager.sh patch` (AUTO_MODE). Tag `v5.0.2` pushed; GitHub release [v5.0.2](https://github.com/sevakavakians/kato/releases/tag/v5.0.2) (assets `kato-deployment-v5.0.2.tar.gz` + Helm chart `kato-0.1.1.tgz`); images `ghcr.io/sevakavakians/kato:5.0.2`/`:5.0`/`:5`/`:latest` (same digest `sha256:6c46ff688321…`). Patch bump — closes the release gap flagged after DECISION-026: ships the observe-path deadlock fix (stopgap `9de98c3`, then the Phase 1.6 lock-free request path `b155cb5`) plus clear-all residue fixes + `escape_glob`, a store-parity tool, the container `HEALTHCHECK` fix, one-writer-per-session docs + strict xfail, and the perf/integrity test — to every published image for the first time. No API change (`KatoProcessor.learn` becoming a coroutine is internal). See DECISION-027 in `DECISIONS.md` and `completed/features/2026-09-10-kato-v5.0.2-release.md`. **Post-release**: a topology-test fragility (not a product bug) was found and fixed same-day, committed as `61e16cd` — see the Test Coverage line and `project-manager/patterns.md`. Prior release: **5.0.1** — 2026-09-10 via `./container-manager.sh patch` (a behavior-preserving round-trip elimination plus example-client bug fixes; no API change); see DECISION-023 and `completed/features/2026-09-10-kato-v5.0.1-release.md`. Before that, **5.0.0** — 2026-09-09 via `./container-manager.sh major` (major bump for the breaking `anomalies`→`fuzzy_matches` prediction-field split, DECISION-019); see DECISION-022 and `completed/features/2026-09-09-kato-v5.0.0-release.md`.
**Status**: Stable and production-ready (maintenance mode)
**Architecture**: FastAPI with direct processor embedding (ClickHouse + Redis hybrid)
**Test Coverage**: **482 passed / 4 skipped / 1 xfailed / 0 failed** (675.08s) — verified 2026-09-10 against the deployed **v5.0.2 registry image** (`ghcr.io/sevakavakians/kato:5.0.2`); worker-topology suite 18/18; store-parity tool confirms 0 mismatched `kb_id`s. The single xfail is `test_concurrent_session_modifications`, the documented DECISION-024 same-session concurrent-write limitation (expected, not a regression). Same pass/fail shape as the pre-release verification against the unreleased local build (651s) — the duration difference is run-to-run variance, not a regression. **Post-release finding (fixed same day, `61e16cd`)**: right after the deployment container restart, the topology suite showed transient failures in `test_session_count_converges_on_every_worker` — root-caused to test fragility (a shared-Redis active-session-index count racing the deployment container's own expiry sweep, not a product bug); the test was rewritten to assert membership of its own session ids and truth-at-the-same-instant counts rather than an absolute before/after delta, and its event-delivery timeout raised 5s→10s. Topology suite 18/18 after the fix. See DECISION-027 and `project-manager/patterns.md` for the generalized testing-pattern note. The only other known-intermittent item remains `tests/tests/api/test_monitoring_endpoints.py::test_metrics_collection_after_requests` (10s metrics-collection interval racing a 1s test sleep under multi-worker) — flaky by construction, unrelated to recent work. See `planning-docs/SPRINT_BACKLOG.md` and `planning-docs/completed/features/2026-09-10-phase-1.6-lock-free-refactor.md`
**Performance**: ~10ms average response time; observe/learn/get_predictions now run with **no locks in the request path** (the DECISION-025 `asyncio.Lock` stopgap was removed by the Phase 1.6 refactor, DECISION-026) — perf/integrity test measured 1.83× speedup at 4 workers vs. 1 with full pattern-count/frequency/store-parity integrity holding; ClickHouse pattern writes batched server-side via ClickHouse's own `async_insert` queue (coalesces across all uvicorn workers) — client-side write buffering is deliberately disabled (`DEFAULT_BATCH_SIZE=1`; commit `f809a84` fixed a per-worker orphaned-row bug this way, and `settings.performance.batch_size` was deleted rather than wired for the same reason, see DECISION-017); Redis round-trips batched where read/write shape allows; symbol table cached; MinHash optional xxhash acceleration (not yet in the running container — `xxhash` was missing from `requirements.lock` until 2026-09-08's fix; takes effect on the next `docker compose build --no-cache kato`, silently falls back to SHA-1 until then); prediction pipeline vectorized with top-K pruning and executor parallelism
**Code Quality**: 96% technical debt reduction achieved (6,315 → 67 ruff issues); configuration surface further cleaned 2026-09-09 (29 files, +666/-1950 — dead settings fields, 4 zero-importer modules, and the entire `APIConfig` class removed)
**Last Major Update**: KATO v5.0.2 released (2026-09-10, DECISION-027) — closes the release gap left open when the Multi-Worker Uvicorn + Concurrent Training Safety initiative completed on `main` without a matching published image; every image tagged before v5.0.2 still carried the observe-path deadlock. See "Version" above for full release contents; a post-release topology-test fragility (shared-Redis global-counter churn, not a product bug) was found and fixed same-day (`61e16cd`), logged as a testing pattern in `project-manager/patterns.md`. Preceded same-day by the initiative's closure itself: an observe-path deadlock discovered while verifying the initiative's throughput/integrity test (any two overlapping observe requests for the same `node_id` permanently hung a uvicorn worker) was fixed in two steps: an `asyncio.Lock` stopgap (DECISION-025, `9de98c3`), then Phase 1.6 (DECISION-026, `b155cb5`) removed the shared per-processor request state that lock was protecting — session STM/emotives/metadata are now threaded explicitly through `observation_processor`/`pattern_operations`/`pattern_processor` per request instead of being staged into shared instance state, so the observe/learn/predict path now runs with no lock at all. This completes the `CLAUDE.md`-flagged "TODO (Phase 1.6/1.7)" stateless-processor follow-up. Verified: worker-topology suite 18/18 (new same-processor interleaving test across `KATO_WORKERS` in {1, 2, 4}); perf/integrity test 1.83× speedup at 4 workers with full integrity; full suite 482 passed / 4 skipped / 1 xfailed / 0 failed. See DECISION-024, DECISION-025, DECISION-026, and `planning-docs/completed/features/2026-09-10-phase-1.6-lock-free-refactor.md`. **Not yet released** — see "Release gap" note above. Preceded same-day (earlier) by cross-worker WebSocket delivery fixed via Redis pub/sub — `kato/websocket/event_broadcaster.py`'s `broadcast_event` now publishes to a `kato:ws_events` channel (override: `KATO_WS_EVENTS_CHANNEL`) that every uvicorn worker subscribes to at startup, delivering to each worker's own local connections for exactly-once delivery per client; falls back to local-only delivery with no locks if Redis is unavailable. Committed as `ba3d194`. Closes the open follow-up from the same-day worker-topology test work (DECISION-020): `tests/tests/integration/test_worker_topology.py` now passes 15/15 across `KATO_WORKERS` in {1, 2, 4} (was 6 deterministic failures at {2, 4}); new `tests/tests/unit/test_event_broadcaster.py` (6 tests) pins the transport rules. Full suite: 475 passed / 4 skipped / 0 failed (585s), up from 453 passed / 5 failed. Design choice (Redis pub/sub over per-worker sticky routing or Redis Streams) recorded in DECISION-021 (2026-09-09); DECISION-019's version-bump question remains separately open. Preceded same-day by the worker-topology test infrastructure itself (5 flaky/failing multi-worker tests replaced with the deterministic `test_worker_topology.py`, launching throwaway `kato:latest` containers at `KATO_WORKERS` in {1, 2, 4} and forcing test clients onto ≥2 distinct worker PIDs before asserting cross-worker delivery; also recharacterized the old "session delete does not decrement active-session count" bug as a test-timing issue, not a product bug; added `worker_pid` to `/health` and websocket `state.snapshot`) — see DECISION-020. Preceded same-day by the `anomalies` prediction field split into a flat deviation list (missing, then extras, then each fuzzy match's observed token) plus a new `fuzzy_matches` field holding the `{observed, expected, similarity}` records `anomalies` used to carry — **BREAKING CHANGE** for consumers reading fuzzy detail from `anomalies` (see DECISION-019); bundled with a multiset (`collections.Counter`) fix for repeated-symbol under-reporting in `missing`/`extras`, and a new test file (`tests/tests/unit/test_hello_world_character_predictions.py`) locking in character-level prediction behavior. Release version bump not yet decided — flagged in `planning-docs/project-manager/pending-updates.md`; nothing committed yet. Preceded same-day by the metadata sidecar re-learn path fix — eliminated a duplicate ClickHouse SELECT (2 → 1 per re-learn), and corrected the framing of the P2 backlog item that had proposed an unachievable "batched call shape at `learnPattern`" fix (there is no batch to form — `learn()` produces exactly one Pattern per call; see DECISION-018). Structural follow-up (append-only emotives/metadata) remains open. Preceded that same-day by a full configuration audit — every `Settings` field and documented `KATO_*` env var checked for both binding and actual consumption; corrected and resolved the 2026-09-08 "dead `KATO_*` env names" P2 item; fixed `/concurrency`'s 4x capacity under-report; aliased 5 more dead env names; wired `LOG_FORMAT`/`LOG_OUTPUT`/`CONNECTION_POOL_SIZE`/`REQUEST_TIMEOUT`/`fuzzy_token_threshold`; deleted vestigial fields, the `APIConfig` class, and 4 zero-importer modules. See DECISION-017, DECISION-018, and DECISION-019 (2026-09-09)

## Directory Structure
```
planning-docs/
├── README.md              # This file
├── PROJECT_OVERVIEW.md    # Core project information
├── DECISIONS.md           # Design decisions log
├── FUTURE_FEATURES.md     # Aspirational features
├── ARCHIVE_SUMMARY.md     # Completed milestone summary
├── completed/             # Detailed completed work docs
├── sessions/              # Session logs
├── project-manager/       # Agent workspace and logs
└── archive-2024/          # Archived planning documents
```

## Documentation Philosophy

This documentation follows a "minimal and current" approach:
- **Essential information only** - No outdated or aspirational content mixed with current facts
- **Clear separation** - Historical work in archives, future ideas in dedicated files
- **Developer-focused** - Practical information for getting work done
- **Self-maintaining** - Simple structure that doesn't require constant updates

---

*Keep this documentation clean, current, and focused on what developers actually need.*