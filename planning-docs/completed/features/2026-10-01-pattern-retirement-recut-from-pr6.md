# Pattern Retirement (Node-Scoped Tombstones), Re-Cut From Collaborator PR #6

**Completed**: 2026-10-01
**Status**: COMPLETE, VERIFIED, **MERGED to `main` and RELEASED in v6.2.0** -- PR #14, merge commit `f3b84ea`
**Decisions**: DECISION-042 (re-cut rather than rebase), DECISION-043 (un-retire, edge validation, 409)
**Type**: Feature (API + read-path filtering). Six commits: `dcc539d` registry and `6bb38a9` read-path barriers authored to Brian <briank.reed@icloud.com>; `5299131`, `f51b184`, `6c59942`, `519abd6` by the repo owner.

## What landed

- **Registry**: node-scoped tombstones at Redis key `{kb_id}:retired_patterns`. Durable; every session on the `node_id` is affected, a session on another node is not, and a tombstone outlives the session.
- **Read-path filtering at four exit points**: `PatternSearcher.causalBelief`/`causalBeliefAsync`, `PatternProcessor._predict_single_symbol_fast`, `PatternOperations.get_predictions`, and `GET /sessions/{id}/cognition-data`.
- **Endpoints**: `POST /sessions/{id}/patterns/retire` and `POST /sessions/{id}/patterns/un-retire`, 1-1000 pattern IDs per call, with or without the `PTRN|` prefix.
- User docs: `docs/` retirement page (commit `519abd6`).

## What it does NOT do

Retirement hides a pattern without deleting the learned row. It does **not** reclaim storage; physical purge is still unimplemented (PR #6, open).

## Why re-cut, not rebased

PR #6 was 40 commits behind with 6 conflicts and about half its content already merged. Merging it in its own direction would have reverted main: deleted `kato/filters/recall_bounds.py`, re-added the deleted `length_filter.py`, restored `recall_threshold = 0`, and failed to start the service (`pattern_processor.py` passed `length_min_ratio` into a dataclass that no longer has that field). See DECISION-042.

## Deliberate changes from the PR #6 version

- Un-retire added: without it retirement was irreversible, and the learn-side guard refuses a tombstoned hash, so one mistaken retire permanently blocks learning that sequence on the node.
- IDs validated at the edge (40-char lowercase SHA1, whitespace stripped, 422 otherwise); previously only blanks were rejected, so a typo became a permanent unmatched tombstone.
- Re-learning a retired pattern returns **409**, not 500. New `RetiredPatternError` based on `KatoV2Exception` (the FastAPI handler is registered for that class, not `KatoBaseException`, so a `KatoBaseException` subclass would map to 500 regardless of the status table), plus explicit passthroughs in `learnPattern` and `learn_pattern_from` whose bare `except Exception` clauses discarded the type.
- Barriers reduced from 10 call sites to 4, one per distinct exit path. The Redis client is synchronous, so each is a blocking round trip inside an async request. A node with no tombstones pays one `EXISTS` against a missing key.
- No node-shared processor state mutated from a session-scoped request: PR #6 cleared `self.predictions` and `self.future_potentials` (node-level) inside `retire_patterns`, which would have blanked another session's in-flight state.

## Verification

583 unit, 129 integration (1 documented xfail), 70 api including 14 new request-level tests. Prediction parity byte-identical to the pre-retirement baseline. ruff and bandit clean.

## Outstanding (PR #6 remains open for physical purge)

See `project-manager/pending-updates.md` ("PR #6 physical purge") and `SPRINT_BACKLOG.md` for the ten documented blockers and the new `ensure_visible()` requirement.
