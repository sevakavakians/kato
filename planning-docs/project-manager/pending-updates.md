# Pending Updates - Human Review Required

## Purpose
Track issues and updates that require human intervention or review.

## Format
```markdown
## [Timestamp] - [Issue Type]
**Issue**: Brief description
**Impact**: How this affects development
**Suggested Action**: Recommended resolution
**Priority**: Critical/High/Medium/Low
**Status**: Open/In Review/Resolved
```

## Current Issues

*No open issues.*

---

## Resolved Issues

## 2026-09-09 - Release Version Bump Decision Needed (Breaking API Change, Not Yet Released) — RESOLVED
**Issue (as originally filed)**: DECISION-019 (`planning-docs/DECISIONS.md`) redefined the `anomalies` prediction field (flat deviation list) and added a new `fuzzy_matches` field, moving the `{observed, expected, similarity}` fuzzy-match detail out of `anomalies`. This is a breaking change for any API consumer currently reading fuzzy-match details from `anomalies`. At filing time, nothing from this work had been committed.
**Impact**: Per this repo's semver workflow (`CLAUDE.md` "Container Manager Workflow Protocol"), this warranted a **major** version bump, not patch/minor — the call was deliberately left to the user rather than made unilaterally by the agent doing the code work.
**Resolution**: The user decided to proceed. KATO **v5.0.0** was released the same day (2026-09-09) via `./container-manager.sh major` (AUTO_MODE) — bump commit `5c4b282`, tag `v5.0.0` pushed to origin, GitHub release published (https://github.com/sevakavakians/kato/releases/tag/v5.0.0), images `ghcr.io/sevakavakians/kato:5.0.0`/`:5.0`/`:5`/`:latest` built and verified. No deprecation/compatibility shim for `anomalies` consumers was added — the major bump itself is the compatibility signal. See DECISION-022 (`planning-docs/DECISIONS.md`) and `planning-docs/completed/features/2026-09-09-kato-v5.0.0-release.md`.
**Verification**: Pre-release full suite 475 passed / 4 skipped / 0 failed; ruff finding count in `kato/` unchanged (283, pre-existing).
**Resolved**: 2026-09-09

---

## 2026-09-09 - Cross-Worker WebSocket Broadcaster Fix: Priority Decision Needed — RESOLVED
**Issue (as originally filed)**: DECISION-020 confirmed deterministically that `kato/websocket/event_broadcaster.py`'s in-process `EventBroadcaster` cannot deliver websocket events across uvicorn workers at `KATO_WORKERS=2`/`4` (the container's default). The fix had not been started and needed a human priority decision before the next release.
**Resolution**: The fix was requested and completed the same day (2026-09-09), committed as `ba3d194`. `EventBroadcaster.broadcast_event` now publishes to a Redis pub/sub channel (`kato:ws_events`); every uvicorn worker subscribes at startup and delivers received events to its own local connections, giving exactly-once delivery per client with no locks. See DECISION-021 (`planning-docs/DECISIONS.md`) and `planning-docs/completed/features/2026-09-09-websocket-cross-worker-broadcaster-redis-pubsub.md`.
**Verification**: New `tests/tests/unit/test_event_broadcaster.py` (6 tests) plus the existing `tests/tests/integration/test_worker_topology.py`, now passing 15/15 across `KATO_WORKERS` in {1, 2, 4} (previously 6 deterministic failures at {2, 4}). Full suite: 475 passed / 4 skipped / 0 failed.
**Note**: This resolves only the websocket-delivery half of the broader "Bug: Multi-worker (KATO_WORKERS=4) breaks websocket event delivery and concurrent session modification consistency" backlog entry. The separate `test_concurrent_session_modifications` concurrent-write-loss symptom is **not** addressed by this fix and remains open — see `planning-docs/SPRINT_BACKLOG.md`.
**Resolved**: 2026-09-09

---

*Resolved issues will be moved here with resolution notes*

---

*This file is automatically maintained by the project-manager agent*
