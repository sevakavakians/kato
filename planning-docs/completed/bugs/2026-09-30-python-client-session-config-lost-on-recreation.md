# examples/python-client.py 3.7.0: Runtime Session Config Lost on Session Recreation

> **⚠️ STATUS CORRECTION (2026-09-30, later the same day): THIS IS NOT COMPLETE. The implementation described below does NOT exist in the working tree or on `main`.**
>
> `examples/python-client.py` on disk is confirmed **byte-identical to `main`** at version 3.6.0 ("Added `get_pattern_count()`..."). `git diff main -- examples/python-client.py` is empty. `git stash list` has nothing from this session. The reflog shows no trace of the 3.7.0 changes. The design and the offline verification described below were genuinely done earlier in this session — the diff was seen and reviewed — but the code implementing it has since vanished from the working tree by some means outside any tracked `git` operation (not a `git checkout`, not a stash, not a reset visible in the reflog). It is **not recoverable** by ordinary git means.
>
> This document is filed under `completed/bugs/` only because no better location exists in this planning-docs structure for "designed and once-verified, but currently absent from the working tree" work — it does **not** mean this task is finished. Treat everything below as a **specification to re-implement**, not a record of shipped code. The point of keeping this much detail is to make redoing the work cheap: the bug, the fix shape, the new constructor params, and the offline verification approach are all still accurate as a design; only their presence in `examples/python-client.py` is false.
>
> **Next action**: reimplement the changes below in `examples/python-client.py` (currently at 3.6.0), re-run the offline verification, then verify against a live server (not done even before the loss) and commit. See `planning-docs/project-manager/pending-updates.md`.

**Originally recorded**: 2026-09-30
**Status**: ~~COMPLETE, verified offline only (fake HTTP layer); NOT verified against a live server (Docker services were down). UNCOMMITTED.~~ **CORRECTED: DESIGN LOST — NOT IN WORKING TREE, NEEDS REDOING.**
**Type**: Bug fix + small feature (client example, no server code changed) — design record only; implementation absent
**Files**: `examples/python-client.py` (KATOClient) — **the version bump to 3.7.0 and everything below is NOT present on disk; the file is at 3.6.0**

## Bug (as designed — needs to be re-fixed)
`update_session_config()` sent the config to the server but never stored it in `self._session_config`. When a session expired (404), auto-recreation re-applied only the constructor settings, so runtime settings such as `vector_search_limit` silently reverted to defaults (3 neighbours). Patterns learned from vector input afterward had different identities than before expiry, with no error raised.

## Fix (as designed — needs to be re-applied)
Accepted updates are merged into `self._session_config` after the request succeeds. Rejected updates are not remembered.

## Added (as designed — needs to be re-added)
Constructor parameters `vector_search_limit` (default 3), `vector_event_mode` (default `'neighbors_plus_self'`), `return_vector_search_results` (default False). Sent to the server only when non-default. Documented in the class, `__init__` and `update_session_config` docstrings.

## Verification (as performed against the since-lost code — offline, fake HTTP layer)
Constructor sends vector params; defaults send nothing; update survives session expiry; rejected update not remembered; an update that itself hits 404 lands on the new session. This verification is no longer meaningful as evidence of anything currently on disk — it describes what was checked against code that no longer exists, and would need to be rerun once the code is rewritten.

## Known remaining limitation (not fixed by this design; still applies once redone)
STM replay during session recovery replays only strings. Vectors, emotives and metadata in the STM are dropped on recovery.

## Related

- `planning-docs/SESSION_STATE.md` — "Previous Task (context preserved)" section, corrected in place with the same status.
- `planning-docs/SPRINT_BACKLOG.md` — "Recently Completed" entry, corrected in place with the same status.
- `planning-docs/project-manager/pending-updates.md` — the "verify and commit" item rewritten to "reimplement, then verify and commit."
