# Cross-Worker WebSocket Broadcaster Fix — Redis Pub/Sub Fan-Out

**Completed**: 2026-09-09
**Status**: COMPLETE — committed as `ba3d194` "fix(websocket): fan events out across uvicorn workers via Redis pub/sub"
**Decision**: DECISION-021 (`planning-docs/DECISIONS.md`)
**Type**: Bug fix (architectural — messaging/fan-out design)
**Follows**: Worker-topology tests + `worker_pid` field (DECISION-020, same day) — this closes that work's open follow-up

## Summary

`kato/websocket/event_broadcaster.py`'s `EventBroadcaster` kept its `active_connections` list per process, so `session.created`/`session.destroyed` events only reached clients whose WebSocket connection happened to be held by the same uvicorn worker that handled the triggering HTTP request. DECISION-020 (earlier the same day) added deterministic tests proving this fails every run at `KATO_WORKERS` in {2, 4} (the container's default topology). This work fixes it via Redis pub/sub fan-out.

## What Changed

### `kato/websocket/event_broadcaster.py`
- `broadcast_event` now publishes the event JSON to a Redis pub/sub channel: `kato:ws_events` by default, overridable via `KATO_WS_EVENTS_CHANNEL`.
- Each uvicorn worker subscribes to that channel at startup; a per-worker listener task delivers every event it receives to that worker's own local `active_connections`.
- The publishing worker does **not** additionally deliver the event to its own connections directly inside `broadcast_event` — delivery happens only through its own listener receiving the message it just published. This gives exactly-once delivery per client regardless of worker count or which worker originated the event.
- `EventBroadcaster.start(redis_url)` blocks until Redis acknowledges the `SUBSCRIBE`, so no event published after startup completes is missed by a listener that hasn't finished subscribing.
- Fallback behavior (no locks anywhere):
  - No `REDIS_URL` / Redis unreachable at `start()` → local-only delivery, with a log line noting the fallback.
  - A `publish()` call fails → falls back to local delivery for that specific event.
  - The listener task errors → resubscribes after a 1-second backoff instead of dying silently.

### `kato/services/kato_fastapi.py`
- `EventBroadcaster.start(REDIS_URL)` called from the app startup hook, immediately after the Redis session manager initializes.
- `stop()` called on shutdown.

### Tests
- New `tests/tests/unit/test_event_broadcaster.py` — 6 tests using fakes: local-fallback delivery (no Redis configured), publish-once-no-double-delivery on the origin worker, publish-failure falls back to local delivery, listener-side delivery to local connections, dead-connection pruning, `start(None)` stays local-only.
- `tests/tests/integration/test_worker_topology.py` (from DECISION-020) — the 3 previously-deterministically-failing delivery tests now pass. Full topology suite: 15/15 across `KATO_WORKERS` in {1, 2, 4} (previously 6 deterministic failures across the {2, 4} topologies).

### Docs
- `docs/integration/websocket-integration.md` — new "Cross-Worker Delivery" section.
- `docs/operations/environment-variables.md` — `KATO_WS_EVENTS_CHANNEL` documented.
- `CHANGELOG.md` `[Unreleased]` — "Fixed" entry.

## Verification

Full suite after an image rebuild with the default `KATO_WORKERS=4`: **475 passed, 4 skipped, 0 failed (585s)**. Previous full-suite baseline was 453 passed / 5 failed (the 5 being the DECISION-020-era topology/websocket failures at multi-worker topologies plus stragglers). The pre-existing `test_metrics_collection_after_requests` flake (10s metrics-collection interval racing a 1s test sleep — an unrelated in-process-metrics-under-multi-worker issue, see `planning-docs/SPRINT_BACKLOG.md`) passed on this particular run but remains flaky by construction; it is not part of the websocket/broadcaster fix and is tracked separately as a known-intermittent item.

## Design Alternatives Considered (see DECISION-021 for full rationale)

1. **Per-worker sticky routing** — rejected: doesn't exist in uvicorn without an external reverse-proxy layer that isn't part of this deployment.
2. **Redis Streams** — rejected as overkill: adds consumer-group/offset/replay semantics for a fire-and-forget notification with no replay requirement. Plain pub/sub's at-most-once model is the correct fit, not a compromise.
3. **Chosen: Redis pub/sub** — reuses infrastructure already required by the architecture (Redis is a hard dependency for session state), matches the actual delivery requirements exactly, and needs no locks.

## Resolved Tracking Items

- `planning-docs/project-manager/pending-updates.md` — "Cross-Worker WebSocket Broadcaster Fix: Priority Decision Needed" (filed 2026-09-09 alongside DECISION-020) is now resolved; moved to that file's Resolved Issues section.
- `planning-docs/SPRINT_BACKLOG.md` — "Bug: Multi-worker (`KATO_WORKERS=4`) breaks websocket event delivery..." — the websocket-delivery half is resolved. The separate, unconfirmed `test_concurrent_session_modifications` concurrent-write-loss symptom from that same backlog entry is **not** addressed by this fix and remains open (it was never established to share the same root cause).
- `planning-docs/README.md` — test-coverage expectation updated to 475 passed / 4 skipped / 0 failed, with only the metrics flake noted as known-intermittent.

## Still Open (unrelated to this fix)

- DECISION-019's major-version-bump decision for the breaking `anomalies`/`fuzzy_matches` field split — undecided, tracked separately in `planning-docs/project-manager/pending-updates.md`.
- `test_concurrent_session_modifications` concurrent-write-loss symptom (original 2026-09-08 characterization) — not re-verified since, still tracked in `planning-docs/SPRINT_BACKLOG.md`.
- `test_metrics_collection_after_requests` flake — pre-existing, unrelated, tracked in `planning-docs/SPRINT_BACKLOG.md`.

## Files

- Product: `kato/websocket/event_broadcaster.py`, `kato/services/kato_fastapi.py`
- Tests: `tests/tests/unit/test_event_broadcaster.py` (new)
- Docs: `docs/integration/websocket-integration.md`, `docs/operations/environment-variables.md`, `CHANGELOG.md`
- Commit: `ba3d194`
