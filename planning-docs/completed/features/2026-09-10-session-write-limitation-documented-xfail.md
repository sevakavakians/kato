# One-Writer-Per-Session Documented + Strict xfail

**Completed**: 2026-09-10
**Status**: COMPLETE — committed as `bef2b47` "docs(sessions): one writer per session; strict xfail"
**Decision**: DECISION-024 (`planning-docs/DECISIONS.md`)
**Decision context**: Multi-Worker Uvicorn + Concurrent Training Safety initiative, Phase B
**Type**: Documentation + test correction (architectural scope decision)

## Summary

DECISION-024 decided that same-session cross-worker write loss (`test_concurrent_session_modifications` losing concurrent writes to one session across uvicorn worker processes) would be documented as a known limitation rather than fixed — no CAS, no distributed locks, consistent with this project's no-locks rule and the actual workload (one session, one writer at a time). This commit implements that decision.

## What Changed

### Docs
- `docs/users/session-management.md` — new "One Writer Per Session" section stating the rule explicitly.
- `docs/users/parallel-processing.md` — cross-reference to the rule.
- `docs/reference/api/sessions.md` — new "Concurrency" section.

### Tests
- `test_concurrent_session_modifications` (`tests/tests/integration/test_session_management.py::TestSessionErrorHandling`) converted from a silent skip (previously only "passed" by being skipped when `KATO_WORKERS>1`) to a strict `xfail` with the DECISION-024 reason — verified XFAIL, so the limitation is asserted rather than hidden.

### Planning-doc correction (same day, prior update)
- Corrected a misattribution in `SPRINT_BACKLOG.md`: earlier text said the SETNX new-pattern gate (Change 3 of the Multi-Worker Uvicorn initiative) "should confirm and close this remaining symptom." That gate guards new-*pattern* creation in `learnPattern` and has no bearing on session-state writes — corrected.

## Verification

Full suite (combined with the rest of this session's work): 479 passed / 4 skipped / **1 xfailed** / 0 failed (648s) — the xfail is `test_concurrent_session_modifications`, confirming the documented limitation holds under `KATO_WORKERS>1`.

## Related

- DECISION-024 in `planning-docs/DECISIONS.md` — full rationale and rejected alternatives (CAS/optimistic locking, distributed lock, sticky routing).
- Multi-Worker Uvicorn + Concurrent Training Safety initiative, `planning-docs/SPRINT_BACKLOG.md` (Active Projects) — Phase B.
- Sibling commits from the same day: `7aad817` (Phase A), `9de98c3` (Phase C deadlock stopgap, DECISION-025).
