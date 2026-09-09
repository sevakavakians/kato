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

## 2026-09-09 - Cross-Worker WebSocket Broadcaster Fix: Priority Decision Needed
**Issue**: DECISION-020 (`planning-docs/DECISIONS.md`) confirms deterministically — via new `tests/tests/integration/test_worker_topology.py` — that `kato/websocket/event_broadcaster.py`'s in-process `EventBroadcaster` cannot deliver websocket events across uvicorn workers. At `KATO_WORKERS=2` and `4` (the container's production default), 3 tests fail every run; at `KATO_WORKERS=1` they pass. This was previously only visible as 2-4 intermittent failures per full-suite run; it is now a stable, well-characterized gap. The fix (most likely Redis pub/sub fan-out so every worker publishes/receives the same events) has **not been started** — it was out of scope for the test-infrastructure work that confirmed it.
**Impact**: Any deployment running `KATO_WORKERS>1` (the container default) silently drops websocket `session.created`/`session.destroyed` events for clients connected to a different worker than the one that handled the triggering request. This also overlaps with the queued "Multi-Worker Uvicorn + Concurrent Training Safety" initiative (`planning-docs/SPRINT_BACKLOG.md`), which has not yet scoped a fix for it either.
**Suggested Action**: Decide whether to fix the broadcaster (Redis pub/sub or similar) before the next release, and whether that fix belongs inside the existing "Multi-Worker Uvicorn + Concurrent Training Safety" initiative or as its own separate piece of work.
**Priority**: Medium — not urgent (nothing committed or released yet; the gap already exists in the current default multi-worker deployment, so this is a known-issue disclosure decision, not a new regression), but should be resolved or explicitly deferred before the next release given the container's default is multi-worker.
**Status**: Open

---

## 2026-09-09 - Release Version Bump Decision Needed (Breaking API Change, Not Yet Released)
**Issue**: DECISION-019 (`planning-docs/DECISIONS.md`) redefines the `anomalies` prediction field (flat deviation list) and adds a new `fuzzy_matches` field, moving the `{observed, expected, similarity}` fuzzy-match detail out of `anomalies`. This is a breaking change for any API consumer currently reading fuzzy-match details from `anomalies`. Nothing from this work has been committed yet.
**Impact**: If released as-is per this repo's semver workflow (see `CLAUDE.md` "Container Manager Workflow Protocol"), this would warrant a **major** version bump, not patch/minor — but that call was deliberately left to the user rather than made unilaterally by the agent doing the code work.
**Suggested Action**: Decide (a) whether to release this change at all in its current form, (b) if released, confirm a major version bump via `./container-manager.sh major "..."`, and (c) whether any deprecation/compatibility shim for `anomalies` consumers is warranted before release.
**Priority**: Medium — not urgent (nothing committed or released yet), but should be resolved before this work is committed/released so it isn't accidentally shipped as a patch/minor bump.
**Status**: Open

---

## Resolved Issues

*Resolved issues will be moved here with resolution notes*

---

*This file is automatically maintained by the project-manager agent*
