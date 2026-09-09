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

**Status**: Stable and production-ready (maintenance mode)
**Architecture**: FastAPI with direct processor embedding (ClickHouse + Redis hybrid)
**Test Coverage**: **Full-suite expectation superseded 2026-09-09** — the earlier "3 known multi-worker failures" characterization (452 passed / 4 skipped / 3 failed) no longer applies. The five tests behind that number (4 websocket event-delivery tests + `test_session_cleanup`) were replaced by a new deterministic `tests/tests/integration/test_worker_topology.py`; expect **6 deterministic topology failures** (3 websocket-delivery tests × 2 multi-worker topologies, `KATO_WORKERS` in {2, 4}) plus the pre-existing flaky `test_metrics_collection_after_requests`, until the cross-worker websocket broadcaster follow-up lands (see DECISION-020, `planning-docs/SPRINT_BACKLOG.md`). Targeted (non-full-suite) results recorded 2026-09-09: trimmed `test_websocket_events.py` 3 passed; `tests/tests/api` 32 passed / 1 skipped / 1 failed (the 1 is the known `test_metrics_collection_after_requests` flake); topology suite at `KATO_WORKERS=1` 5/5 passed, at `KATO_WORKERS=2` and `4` each 2/5 passed (3 deterministic delivery failures). Earlier same-day: 233 passed / 1 skipped across unit + integration prediction suites and `tests/tests/api` (anomalies/fuzzy_matches breaking change verification) — the 1 failure was the same pre-existing metrics flake. See `planning-docs/SPRINT_BACKLOG.md`
**Performance**: ~10ms average response time; ClickHouse pattern writes batched server-side via ClickHouse's own `async_insert` queue (coalesces across all uvicorn workers) — client-side write buffering is deliberately disabled (`DEFAULT_BATCH_SIZE=1`; commit `f809a84` fixed a per-worker orphaned-row bug this way, and `settings.performance.batch_size` was deleted rather than wired for the same reason, see DECISION-017); Redis round-trips batched where read/write shape allows; symbol table cached; MinHash optional xxhash acceleration (not yet in the running container — `xxhash` was missing from `requirements.lock` until 2026-09-08's fix; takes effect on the next `docker compose build --no-cache kato`, silently falls back to SHA-1 until then); prediction pipeline vectorized with top-K pruning and executor parallelism
**Code Quality**: 96% technical debt reduction achieved (6,315 → 67 ruff issues); configuration surface further cleaned 2026-09-09 (29 files, +666/-1950 — dead settings fields, 4 zero-importer modules, and the entire `APIConfig` class removed)
**Last Major Update**: Five flaky/failing multi-worker tests (4 websocket event-delivery tests + `test_session_cleanup`) replaced with a new deterministic `tests/tests/integration/test_worker_topology.py` — launches throwaway `kato:latest` containers at `KATO_WORKERS` in {1, 2, 4} and forces test clients onto ≥2 distinct worker PIDs before asserting cross-worker delivery, so an in-process broadcaster fails every run rather than by scheduling luck. Confirms deterministically that the in-process `EventBroadcaster` (`kato/websocket/event_broadcaster.py`) cannot fan websocket events out across uvicorn workers — surfaces as exactly 6 deterministic failures (3 delivery tests × 2 multi-worker topologies) instead of the previous 2-4 random failures per full-suite run. Also recharacterizes the old "session delete does not decrement active-session count" bug: the rewritten `test_session_cleanup` now passes by honoring the documented per-process `/sessions/count` TTL cache — the prior failure was a test not waiting for cache expiry, not a missing decrement. New `worker_pid` (`os.getpid()`) field added to `/health` and websocket `state.snapshot` responses to make the topology tests possible. Broadcaster fix (e.g. Redis pub/sub fan-out) **NOT started** — flagged for human decision, alongside the still-open DECISION-019 version-bump question. See DECISION-020 (2026-09-09). Preceded same-day by the `anomalies` prediction field split into a flat deviation list (missing, then extras, then each fuzzy match's observed token) plus a new `fuzzy_matches` field holding the `{observed, expected, similarity}` records `anomalies` used to carry — **BREAKING CHANGE** for consumers reading fuzzy detail from `anomalies` (see DECISION-019); bundled with a multiset (`collections.Counter`) fix for repeated-symbol under-reporting in `missing`/`extras`, and a new test file (`tests/tests/unit/test_hello_world_character_predictions.py`) locking in character-level prediction behavior. Release version bump not yet decided — flagged in `planning-docs/project-manager/pending-updates.md`; nothing committed yet. Preceded same-day by the metadata sidecar re-learn path fix — eliminated a duplicate ClickHouse SELECT (2 → 1 per re-learn), and corrected the framing of the P2 backlog item that had proposed an unachievable "batched call shape at `learnPattern`" fix (there is no batch to form — `learn()` produces exactly one Pattern per call; see DECISION-018). Structural follow-up (append-only emotives/metadata) remains open. Preceded that same-day by a full configuration audit — every `Settings` field and documented `KATO_*` env var checked for both binding and actual consumption; corrected and resolved the 2026-09-08 "dead `KATO_*` env names" P2 item; fixed `/concurrency`'s 4x capacity under-report; aliased 5 more dead env names; wired `LOG_FORMAT`/`LOG_OUTPUT`/`CONNECTION_POOL_SIZE`/`REQUEST_TIMEOUT`/`fuzzy_token_threshold`; deleted vestigial fields, the `APIConfig` class, and 4 zero-importer modules. See DECISION-017, DECISION-018, and DECISION-019 (2026-09-09)

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