# Remediation Pass 1 Follow-On: Branch Closed Out + Deterministic Prediction Ranking / ProcessPool Removal

**Completed**: 2026-09-16
**Commits**: `df9a76a` (Remediation Pass 1 itself), `7233155` (merge to `main`), `8deab2c` (protected-mode revert + explanation), `7bae726` (deterministic ranking + ProcessPool removal)
**Decisions**: DECISION-030 (`planning-docs/DECISIONS.md`, correction note added this session), DECISION-031 (new, same file)
**Type**: Process Closure (commit/merge, cleanup) + Bug Fix (determinism) + Performance + Security Correction

## Background
This is the direct follow-on to Remediation Pass 1 (`planning-docs/completed/features/2026-09-16-remediation-pass-1.md`, DECISION-030), which had shipped complete but uncommitted, with four open items requiring the user's decision, plus one unrelated bug (session-level `sort_symbols`) left explicitly unfixed. This session closed all four open items, corrected one claim in DECISION-030 that turned out to be invalid, and — while investigating a separate performance question the user raised — found and fixed a real correctness bug in prediction ranking.

---

## Part 1 — Remediation Pass 1's Four Open Items, All Resolved

### 1. Branch committed and merged
`chore/remediation-pass-1` committed as `df9a76a` "fix: repair dead error handling, SQL parameterization, and data-loss bugs (Remediation Pass 1)"; merged to `main` via a no-ff merge, `7233155`. All Remediation Pass 1 content (see the prior archive entry for the full breakdown) is now on `main` and protected by version control.

### 2. Orphaned Redis prediction keys cleaned up
4,464 `*:prediction:*` keys with no TTL were deleted with `UNLINK`, after first verifying every one of the 4,464 matched the expected `<kb_id>:prediction:obs-<hex>` shape — i.e., nothing outside the known leak pattern (fixed going-forward by Remediation Pass 1's `setex` change) was touched. The 549 keys written *after* that fix landed were deliberately left alone; they carry a correct TTL and will expire on their own, so touching them would have added risk for zero benefit. Redis `DBSIZE` went 44057 → 39593. Verified afterward: zero surviving prediction keys without a TTL.

### 3. Full stack recreated
Redis, ClickHouse, and Qdrant were recreated (Remediation Pass 1's live verification had only recreated the `kato` service itself). Data integrity was verified both before and after the recreate:
- Redis `DBSIZE`: 39593, unchanged across the recreate.
- ClickHouse: 8824 patterns, 19513 metadata rows, 301 distinct `kb_id`s — all unchanged.
- Qdrant: all 84 collections recovered.
- End-to-end smoke test: observe/learn/predict returns the expected future.
A `redis-cli SAVE` was taken before the recreate as a safety measure.

While doing this, it was noticed that Remediation Pass 1's loopback-binding change had only been applied to the root `docker-compose.yml` — but the actually-running stack uses the `deployment/` compose project (`deployment/docker-compose.yml` + override). That meant the original binding change had **no effect on the live deployment** despite being recorded as done. The same loopback bindings (Redis 6379, ClickHouse 8123/9000, Qdrant 6333 → `127.0.0.1`) were applied to `deployment/docker-compose.yml`. KATO's own port 8000 and the dashboard's port 3001 are unchanged (the dashboard's exposure is tracked separately — see `pending-updates.md`).

### 4. `requirements.lock` — resolved, but not the way originally planned
The plan had been a straightforward `pip-compile --output-file=requirements.lock requirements.txt` after Remediation Pass 1 dropped `aioredis`. That was attempted in a clean `python:3.10` container to see the actual diff — and the diff bumped nearly every pin in the file: `clickhouse-connect` 0.9.2→1.8.0, `redis` 6.4→8.1, `pytest` 8→9, `pydantic`, `qdrant-client` 1.15→1.19, `uvicorn` 0.37→0.53, among others. That result was **rejected** — a single dependency removal should not silently become a full upgrade sweep across major versions with no individual changelog review. Instead, only the `aioredis` entry and its two `# via` back-references were removed surgically from the existing `requirements.lock`, leaving every other pin byte-identical to before. Verified the image builds and contains no `aioredis`. **A full dependency upgrade is now tracked as its own separate, explicitly open item** (see `pending-updates.md`) rather than folded into this cleanup.

---

## Part 2 — Correction to DECISION-030: the `protected-mode` Verification Was Invalid

DECISION-030's "Security" section claimed `protected-mode no` was safely removed from `config/redis.conf`, "verified empirically that with an explicit `bind` directive, container-to-container access still works." That verification proved nothing: `redis:7-alpine` (the exact image tag in use, resolving to Redis 7.4.8) already ships `protected-mode no` as its own default — so removing the line from `redis.conf` left protected mode off regardless of the file change, and the claimed test never actually exercised protected mode being *on*.

When protected mode was genuinely set (`protected-mode yes`, with the existing explicit `bind` directive and no password configured), a cross-container Redis connection was refused outright: `DENIED Redis is running in protected mode because protected mode is enabled and no bind or authentication configuration is set ... connections are only accepted from the loopback interface`. The `bind` directive does **not** exempt a connection from this check — only a configured password does.

**Resolution**: `protected-mode no` is restored in `config/redis.conf`, and now set **explicitly** in the file rather than left to the image's own default (upstream Redis itself ships `protected-mode yes`; relying on a specific image's default silently is fragile across image updates). Committed as `8deab2c` "fix(redis): keep protected-mode off, and say why", with the reasoning above captured as an in-file comment.

What actually protects this Redis instance today: (1) the host-published port bound to `127.0.0.1` (Part 1, item 3, above — now applied in both compose files), and (2) nothing else — there is currently no `REDIS_PASSWORD` configured. **Setting `REDIS_PASSWORD` is the recommended next step**, after which `protected-mode` could be safely turned back on without breaking legitimate container-to-container access. Tracked as a new open item in `planning-docs/project-manager/pending-updates.md`.

---

## Part 3 — DECISION-031: Prediction Ranking Was Non-Deterministic (Fixed) + Per-Request ProcessPoolExecutor Removed

### How this was found
The user asked whether the default full-corpus prediction scan (`filter_pipeline=[]`, deliberately left unchanged by Remediation Pass 1's "exact-safe only" scoping) could be made faster while keeping output deterministic. Investigating that question — **before attempting any optimisation** — surfaced that the premise didn't hold: output was not deterministic to begin with.

### The bug
Predictions are ranked on the configured metric; ties are broken by whatever order candidates happen to arrive in. That order is not stable: candidates come out of a Python `set` (string hashing is randomized per process by default, so each uvicorn worker iterates the same set of pattern names in a different order), and batch results are gathered with `asyncio.as_completed()`, which yields batches in whichever order they happen to finish. `heapq.nlargest` keeps the first-seen of equal keys and `sorted` is stable — so the *tie order*, not just which items tie, depends on per-process/per-request arrival order. Once `max_predictions` truncates the ranked list, a different tie order doesn't just reorder the response — it changes which predictions are in it at all.

**Measured against the running service**: 40 identical requests over a corpus of 10 mutually-tied patterns, `max_predictions=3` — **7 distinct orderings, 5 distinct result sets**. This directly contradicts `CLAUDE.md`'s stated guarantee: "Deterministic: Same inputs → same outputs (always)."

### The fix
New pure function `rank_predictions(predictions, metric, limit)` in `kato/representations/prediction.py`, ordering on `(metric, name)`. Pattern names are unique, so this is a genuine total order — arrival order, worker process, and async completion timing cannot influence the result. Applied at all three ranking sites:
1. The final ranking in `predictPattern`.
2. The top-K prune ahead of the metrics loop — this one is not cosmetic: ties here previously decided which candidates even received metrics computed at all, not just their final display order.
3. The single-symbol fast path — ClickHouse gives no row-order guarantee absent an explicit `ORDER BY`, so this path was equally exposed.

Re-measured after the fix: 40 identical requests, 1 ordering, 1 result set.

### Testing note that generalizes (recorded in `patterns.md`)
The first guard test written for this fix was an integration test using the standard `kato_fixture`, and it **passed against a deliberately reverted (buggy) build** — worthless as a regression guard. Cause: `tests/tests/fixtures/kato_fixtures.py` shares one `requests.Session()`, and HTTP keep-alive pins every request in a test to a single TCP connection, which a single uvicorn worker handles — so the cross-worker `set`-iteration-order nondeterminism this bug depends on never had a chance to manifest inside that test. Deleted that integration-level test and replaced it with a pure-function unit suite, `tests/tests/unit/test_prediction_ranking.py` (7 tests), which shuffles input order directly rather than relying on server-side nondeterminism to surface — confirmed to fail when the tie-breaker is reverted. Generalized lesson logged in `planning-docs/project-manager/patterns.md`: cross-worker/cross-process nondeterminism cannot be tested through the shared HTTP fixture; test the invariant as a pure function instead.

### ProcessPoolExecutor: measured honestly once determinism no longer depended on execution strategy
With ranking now deterministic regardless of arrival order, the per-request `ProcessPoolExecutor` (engaged by default above 500 candidates) could finally be measured on its own performance merits rather than being entangled with the determinism question. At 6000 patterns / 6000 candidates, identical corpus and configuration:
- ProcessPool engaged: **3378 ms median**
- ProcessPool disabled (ThreadPool only): **1231 ms median**
- Prediction payloads byte-identical between the two runs.

The premise for the process pool (bypass the GIL for the matching loop) does not survive contact with the actual implementation: a fresh pool is constructed and torn down on *every single request* — spinning up to four interpreters plus pickling each batch across the process boundary — and RapidFuzz (the actual matching library) already releases the GIL during its C-extension calls, so the existing `ThreadPoolExecutor` path already had real parallelism without any of that overhead. The process pool was pure pessimisation for this workload.

**Resolution**: disabled by default via new `PROCESS_POOL_CANDIDATE_THRESHOLD` setting (default `0` = off), documented in `docs/reference/configuration-vars.md`. Not deleted — kept as an opt-in tunable per the user's stated standing position that performance-affecting knobs (as with `filter_pipeline`) should stay configurable per application rather than be removed outright.

### Related bug found and fixed: metadata-lookup chunking, introduced by Remediation Pass 1's own metadata-batch hoist
While profiling this work at 6000-pattern scale, ClickHouse began rejecting metadata lookups over `max_query_size` (262144 bytes; ~6000 quoted SHA1 names at ~42 bytes each lands right around that limit). Root cause: Remediation Pass 1 hoisted `get_metadata_batch()` above the `asyncio.gather` batch split — a genuine win on its own, since it removed N serialized ClickHouse+Redis round trips down to one — but that put the *entire* matched-pattern result set into a single ClickHouse `IN` list. **The failure was silent to the caller**: `ClickHouseWriter` logged the oversized-query error and returned `{}`, so every prediction silently fell back to `frequency=1` and default metrics rather than surfacing an error. It was found by reading container logs during this performance profiling session, not by the test suite — the suite's corpora are far below the size threshold that triggers it.

**Fix**: chunk the lookup at 500 (`METADATA_CHUNK_SIZE`), matching the existing convention already used by `FilterPipelineExecutor._execute_chunked_query`. Guarded by new `tests/tests/unit/test_metadata_batch_chunking.py` (5 tests), confirmed to fail with chunking removed.

**Also fixed alongside**: `shutdown_event` called `OptimizedConnectionManager.get_instance()`, a method that does not exist. The resulting `AttributeError` was swallowed by the surrounding `except`, so database connections were never actually being closed on service shutdown — a separate, unrelated defect found in the same area of code.

### Cost breakdown — record this, it redirects future performance work
Measured at 6000 patterns / 6000 candidates on the default `filter_pipeline=[]` path (~1271 ms total after all of the above fixes):
- ClickHouse full-corpus `SELECT`: ~12 ms (1%)
- Result parse + `patterns_cache` build: ~80 ms (6%)
- Pattern metadata lookup (12 chunks of 500): ~430 ms (35%)
- Matching + metrics + ranking: ~700 ms (57%)

Scan scaling measured separately (sub-linear, not the bottleneck): 5.7 ms at 500 patterns, 9.7 ms at 2000, 11.8 ms at 6000 (50 KB → 604 KB transferred). **The full-corpus scan is NOT the bottleneck and is not worth optimising** — this should redirect the still-open "default `filter_pipeline` is `[]`" backlog item toward being evaluated on correctness/filtering-value grounds, not performance grounds, since the performance case for changing it does not hold up at this scale.

**Next opportunity identified, NOT implemented**: metadata is currently fetched for every matched pattern even though only `max_predictions` ultimately survive ranking. Pruning to top-K before the metadata lookup (rather than after, as today) would proportionally cut the 35% metadata-lookup cost — but this is only safe once it's confirmed the top-K prune metrics themselves (`_pre_potential`: evidence, confidence, snr, fragmentation) don't need metadata as an input; if they do, pruning first would starve the prune step. Filed as a new Backlog entry in `planning-docs/SPRINT_BACKLOG.md`.

**Separate finding, unrelated to prediction latency**: ingestion is O(N²) when `process_predictions` is left on (the default), because every `observe` call runs a full-corpus prediction. Building a corpus collapsed to ~8 patterns/min across 8 concurrent writers by ~700 patterns accumulated; with `process_predictions: false` set on the loading session, throughput was ~428 patterns/min per worker with no quadratic collapse observed. Not a bug — working as designed — but an easy footgun for anyone bulk-loading a corpus. Filed as a new Backlog documentation item.

---

## Verification (combined, this session)
Full suite: **603 passed / 3 skipped / 1 xfailed / 0 failed (681.79s)**, up from 591 (+12: 7 new ranking tests, 5 new metadata-chunking tests). ruff and bandit clean. Benchmark corpora created during this session's measurements (`test_scanbench`, `test_tie_determinism`) were cleared afterward; verified zero residue in ClickHouse and Redis.

## Remaining Open Items for the User
1. **A full dependency upgrade** (the rejected `pip-compile` result from Part 1, item 4) — needs its own scheduled pass with per-package changelog review.
2. **Set `REDIS_PASSWORD`**, after which `protected-mode` can be safely re-enabled (Part 2).
3. **Dashboard hardening** — still ships default credentials `admin`/`changeme`, a read-write Docker socket mount, and publishes port 3001 on all interfaces. Flagged in the original comprehensive review, untouched by any pass to date.
4. **The re-assess/deferred list from DECISION-030** — otherwise unchanged, minus the `ProcessPoolExecutor` item, now done. The `filter_pipeline` default stays `[]` deliberately — confirmed by the user as a user-facing configurable parameter chosen per application, not a default to change; the cost-breakdown finding above (the scan itself is not the bottleneck) further weakens any performance-based case for changing it.
5. **The `sort_symbols` bug from DECISION-030** is still open and unfixed — unrelated to this session's work.
6. **v5.0.3 (or later) release** — the released v5.0.2 image now lacks `e0ee17d` (DECISION-028), `34910a70` (DECISION-029), all of Remediation Pass 1 (`df9a76a`/`7233155`), the protected-mode correction (`8deab2c`), and DECISION-031 (`7bae726`). This gap has grown large enough (a real SQL-injection fix and a real determinism fix both sitting unreleased) to warrant prioritizing over further deferral — see `pending-updates.md`.

## Related
- DECISION-030 (`planning-docs/DECISIONS.md`) — Remediation Pass 1, with a correction note added this session for the protected-mode claim.
- DECISION-031 (`planning-docs/DECISIONS.md`) — the deterministic-ranking fix and ProcessPool removal, new this session.
- `planning-docs/completed/features/2026-09-16-remediation-pass-1.md` — the original Remediation Pass 1 archive entry this work follows on from.
- `planning-docs/project-manager/patterns.md` — new Testing Strategy Patterns entry on cross-worker nondeterminism and the shared HTTP fixture.
- `planning-docs/project-manager/pending-updates.md` — four items resolved, four new items filed.
