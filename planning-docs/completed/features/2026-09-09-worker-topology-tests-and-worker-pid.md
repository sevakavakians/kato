# Worker-Topology Tests Replace Flaky Multi-Worker Tests + `worker_pid` Field

**Completed**: 2026-09-09
**Status**: COMPLETE — tests in place, run, and characterized; NOT committed yet
**Decision**: DECISION-020 (`planning-docs/DECISIONS.md`)
**Type**: Test infrastructure (deterministic replacement for flaky tests) + small product addition (`worker_pid`) + bug confirmation (not a fix)
**Follows**: Anomalies/fuzzy_matches field split (DECISION-019, same day)

## Summary

Replaced the five known-flaky/failing tests that depended on the live container's fixed `KATO_WORKERS=4` runtime topology (4 websocket event-delivery tests + `test_session_cleanup`) with a new deterministic test module, `tests/tests/integration/test_worker_topology.py`, that launches its own throwaway containers at multiple worker counts and proves cross-worker behavior directly instead of hoping to observe it against whatever the shared dev container happens to be running.

## Motivation

Before this change, multi-worker cross-worker bugs (websocket event fan-out, session count consistency) were only visible as intermittent failures against the one shared `kato` container on `:8000` (`KATO_WORKERS=4` by default). This made them:
- Indistinguishable from genuine flakiness when reported in a full-suite run
- Impossible to test at `KATO_WORKERS=1` (no failure) vs `>1` (failure) without manually reconfiguring and restarting the shared container
- A source of noise in every "is this failure caused by my change" verification during unrelated work (see the `anomalies`/fuzzy_matches, metadata-sidecar, and configuration-audit work earlier the same day, each of which had to characterize-and-dismiss these failures)

## What Was Built

### New file: `tests/tests/integration/test_worker_topology.py`
- Module-scoped fixture parametrized over `KATO_WORKERS` in `{1, 2, 4}`
- For each value, launches a throwaway `kato:latest` container via the `docker` CLI on the compose network, copying the running `kato` container's environment so only `KATO_WORKERS` (and `SESSION_COUNT_CACHE_TTL_SECONDS=2`, for faster test iteration) differ from the real deployment
- Readiness and actual worker count are verified from uvicorn's own `"Started server process [pid]"` log lines (not assumed from the requested `KATO_WORKERS` value)
- Five tests:
  1. `container_runs_requested_worker_count` — sanity check that the requested topology was actually achieved
  2. `session_created_event_reaches_every_client`
  3. `session_destroyed_event_reaches_every_client`
  4. `client_sees_full_session_lifecycle_in_order`
  5. `session_count_converges_on_every_worker`

### Determinism mechanism
Before asserting delivery, each delivery test opens websocket clients until they provably sit on ≥2 distinct worker PIDs (bounded at `16 * workers` connection attempts). This means an in-process (per-worker) broadcaster is guaranteed to fail on every run once achieved — the test doesn't rely on scheduling luck to land connections on different workers.

### `tests/tests/integration/test_websocket_events.py` trimmed
Removed: `test_session_created_event`, `test_session_destroyed_event`, `test_multiple_websocket_connections`, and the `TestQuickStartExample` class — all moved to (superseded by) the new topology module. Kept: connection, ping/pong, disconnect-cleanup tests (these don't depend on multi-worker topology).

### `tests/tests/integration/test_session_management.py::test_session_cleanup` rewritten
The old test asserted the active-session count immediately after delete. The rewritten version honors the documented per-process `/sessions/count` TTL cache: it reads only after `SESSION_COUNT_CACHE_TTL_SECONDS` (default 5) + 0.5s have elapsed, and requires 16 consecutive reads (one per likely worker-routing outcome) to agree. **Knowledge refinement**: this recharacterizes the old backlog bug "session delete does not decrement active-session count" (tracked as Root cause #3 since 2026-06-18) — the count does converge correctly, the original test simply read it before the per-process cache had expired. Now passes deterministically against the live 4-worker main container.

### Product addition: `worker_pid`
Added `worker_pid` (`os.getpid()`) to:
- `/health` responses — `kato/api/endpoints/health.py` + `HealthResponse` schema in `kato/api/schemas/health.py`
- WebSocket `state.snapshot` data — `kato/websocket/event_broadcaster.py`

This is what makes the topology tests' "prove ≥2 distinct worker PIDs before asserting" mechanism possible — without it, a test has no way to know which uvicorn worker served a given connection.

**Docs updated**: `docs/reference/api/health.md`, `docs/integration/websocket-integration.md`, `docs/developers/testing.md` (new "Worker-Topology Tests" section), `CHANGELOG.md` `[Unreleased]` "Added".

## Results (image rebuilt, main container recreated with default `KATO_WORKERS=4`)

- **`KATO_WORKERS=1`**: all 5 topology tests pass.
- **`KATO_WORKERS=2` and `KATO_WORKERS=4`**: the 3 websocket-delivery tests (`session_created_event_reaches_every_client`, `session_destroyed_event_reaches_every_client`, `client_sees_full_session_lifecycle_in_order`) **FAIL deterministically**, with the missed worker PIDs reported in the assertion message (e.g. "reached 0 client(s), missed pids [7, 10]"). `container_runs_requested_worker_count` and `session_count_converges_on_every_worker` pass on all three topologies.
- **This is the intended outcome, not a regression to fix here.** It confirms that the in-process `EventBroadcaster` (`kato/websocket/event_broadcaster.py`, a per-process `active_connections` list) structurally cannot deliver events across uvicorn workers. Previously this surfaced as 2-4 randomly-selected failures per full-suite run (depending on which worker a given test's websocket connection happened to land on); it now surfaces as **exactly 6 deterministic failures** (3 tests × 2 multi-worker topologies) every run, until the broadcaster is made cross-worker (e.g. Redis pub/sub fan-out). **The fix was NOT started** — the user has not asked for it; it is recorded as an open follow-up (see `planning-docs/SPRINT_BACKLOG.md` and `planning-docs/project-manager/pending-updates.md`).
- Rewritten `test_session_cleanup` passes.
- Trimmed `test_websocket_events.py` passes (3 tests).
- `tests/tests/api` suites: 32 passed / 1 skipped / 1 failed — the 1 failure is the pre-existing `test_metrics_collection_after_requests` flake (10s metrics-collection interval vs. a 1s sleep in the test), unrelated and still open.
- Lint: the new topology file is ruff-clean; other ruff findings in touched files are pre-existing.

## Knowledge Refinements Recorded

1. **"Session delete does not decrement active-session count" (Root cause #3, filed 2026-06-18) is recharacterized, not a real product bug**: the count does converge; the per-process `/sessions/count` response is cached with a TTL (`SESSION_COUNT_CACHE_TTL_SECONDS`, default 5), and the original test read it before expiry. See DECISION-020 and `planning-docs/SPRINT_BACKLOG.md`.
2. **The websocket-delivery half of Root cause #3** (4 tests timing out waiting for `session.created`/`session.destroyed` events) is **not a separate bug** — it is the same cross-worker broadcaster gap already tracked as "Bug: Multi-worker (`KATO_WORKERS=4`) breaks websocket event delivery..." (filed 2026-09-08). The two backlog entries are merged; the multi-worker entry now has deterministic (not just intermittent) confirmation via the new topology suite.
3. **Full-suite failure-count expectation is superseded**: "3 known multi-worker failures" (452/4/3, recorded earlier 2026-09-09) no longer applies now that the underlying tests have been replaced. New expectation: 6 deterministic topology failures (workers=2/4 delivery tests) + the pre-existing `test_metrics_collection_after_requests` flake, until the broadcaster follow-up lands.

## Open Follow-Up (Not Started)

Make `EventBroadcaster` cross-worker (most likely: Redis pub/sub, with each worker subscribing and re-broadcasting to its own local websocket clients). This would also likely resolve the related `test_metrics_collection_after_requests` flake's root class of problem (in-process-only state under multi-worker) if request-count tracking were moved the same way, though that is a separate metric/counter, not the websocket broadcaster itself. Flagged for human decision on priority relative to the next release, alongside the still-open DECISION-019 major-version-bump question — see `planning-docs/project-manager/pending-updates.md`.

## Files

- New: `tests/tests/integration/test_worker_topology.py`
- Modified: `tests/tests/integration/test_websocket_events.py`, `tests/tests/integration/test_session_management.py`
- Product: `kato/api/endpoints/health.py`, `kato/api/schemas/health.py`, `kato/websocket/event_broadcaster.py`
- Docs: `docs/reference/api/health.md`, `docs/integration/websocket-integration.md`, `docs/developers/testing.md`, `CHANGELOG.md`
