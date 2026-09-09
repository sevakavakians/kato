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
