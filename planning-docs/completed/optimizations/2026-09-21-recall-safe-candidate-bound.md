# Optimization: Recall-Safe Candidate Bound (ClickHouse-Side Pruning Without Running the Scorer There)

**Completed**: 2026-09-21
**Branch**: `perf/recall-safe-candidate-bound` — merged to `main` same day as commit `51f8213` and **released as KATO v6.0.0**, patched same day as **v6.0.1**. See `planning-docs/completed/features/2026-09-21-kato-v6.0.0-release.md` and `planning-docs/completed/features/2026-09-21-kato-v6.0.1-release.md` (DECISION-035/DECISION-036/DECISION-037). *(This section originally read "NOT merged to `main`, NOT released" — corrected same day once the merge/release happened; the technical detail below is unchanged.)*
**Type**: Performance (candidate-set bounding) + Correctness safety mechanism + Bug Fix (`recall_threshold=0` validation gaps) + Dead-code/unsafe-code removal (`LengthFilter`)
**Impact**: Resolves the candidate-set-bounding discussion deferred at DECISION-033/`pending-updates.md` (2026-09-18) — the default `filter_pipeline=[]` full-corpus pull into Python is now bounded at the ClickHouse query itself via a provably lossless necessary-condition predicate, with predictions verified byte-identical.
**Decision**: DECISION-034 in `planning-docs/DECISIONS.md`

## Summary

KATO's default candidate path (`filter_pipeline=[]`) pulls every pattern in the node into Python before any pruning happens — O(N) time and memory in corpus size, not bounded by `max_predictions`. This was flagged as the highest-priority open item after v5.2.0 shipped (DECISION-033), with the user asking to discuss it before deciding an approach.

The obvious approach — push the scorer itself into ClickHouse — is not available: KATO's scorer is `_lcs_ratio_scorer` (`kato/searches/pattern_search.py:50`), `similarity = 2*LCS(pattern, state) / (len(pattern) + len(state))`, and ClickHouse 26.2 has no longest-common-subsequence function. Its `arrayLevenshteinDistance` is a genuinely different metric — verified live that one token substitution costs 1 under Levenshtein but 2 under LCS (a delete plus an insert), and `arrayLevenshteinDistance(['a','b'],['c','d'])` returns 2 where LCS-distance is 4. Using it as the decision function would silently change which patterns match.

Instead, this work pushes down a **necessary condition** — a quantity ClickHouse can compute by counting that is provably never smaller than the true similarity. If even the upper bound is below `recall_threshold`, the pattern cannot pass and is dropped without ever running LCS. The real Python scorer still runs unchanged on every survivor. ClickHouse never decides a pattern MATCHES — only that it CANNOT. That is why prediction output is byte-identical before and after.

## The Bound

From `LCS <= min(P, L)` (pattern length `P`, live-state length `L`): a length window `r*L/(2-r) <= P <= L*(2-r)/r`.

From `LCS <= common` (count of pattern tokens present in the STM's token set): `2*common >= r*(P+L)`.

Both are counting arguments over stored/derivable columns (`length`, `token_set`) — no LCS computation in ClickHouse at any point.

## CRITICAL FINDING: Exact Arithmetic Is Unsafe Here

The natural approach — and the author's own initial written guidance — was to compute these bounds with exact rational arithmetic (`Fraction`) to avoid float error. **This is wrong and causes silent recall loss.**

KATO's reference scorer is floating point, and `float(0.1) > 1/10` exactly (IEEE-754 rounds `0.1` up). An exact `Fraction` comparison is therefore **stricter** than the float scorer it's meant to approximate, and rejects candidates the real scorer would have accepted.

Measured over a sweep of `r ∈ {0.01, 0.1, 1/3, 0.5, 2/3, 0.9, 0.99} × L ∈ [1,40] × P ∈ [2,200] × M`:
- Naive exact `Fraction` bound: **413 recall losses**
- Weakened integer bound: **0**

The fix is to deliberately **weaken** the threshold below the float value: `num = floor(Fraction(recall_threshold) * 1_000_000)`, then compare in integers (`2*common*DEN >= num*(P+L)`). Weakening `r` makes both predicates strictly more permissive, so survivors stay a superset of the true match set.

**Standing rule, recorded here for all future approximating-bound work: a bound approximating a float reference implementation must never be tighter than that reference.**

Concrete example preserved for regression reference: at `r=0.1, L=1, P=19, M=1` the scorer accepts (`2.0*1/20 == 0.1`) but the naive exact form rejects. A second, independent float hazard found in the same investigation: `int(6 * 1.9 / 0.1)` evaluates to `113`, not `114` — a float-computed `max_length` would drop a pattern scoring exactly at the threshold.

## Decisions Made (user-explicit, see DECISION-034 for full rationale)

1. **On by default**, with an env kill-switch `KATO_RECALL_BOUND_ENABLED` (default `true`) — not opt-in. The predicate is lossless, so enabling it by default is not a behavior change; a default-off optimization does nothing for the corpus growth (target 100k-1M+ patterns/node) it's meant to pre-empt.
2. **`LengthFilter` deleted entirely**, not fixed or documented (see below for why).
3. **`recall_threshold = 0` rejected everywhere** — API, session config, and env. `r=0` is the one case with no valid candidate bound (similarity >= 0 always, so everything qualifies) — banning it makes the bound unconditionally rather than conditionally safe.

**Implementation decision — deliberately NOT registered as a `filter_pipeline` entry**: doing so would require flipping the default pipeline from `[]` to non-empty, moving every deployment onto `execute_pipeline()`, which swallows filter exceptions with `continue` (`executor.py:182-185`) — if the failing filter runs first, `candidates` stays `None` and the pipeline returns an empty set: zero predictions, one log line, HTTP 200. Unacceptable for a system whose core guarantee is determinism. The bound is applied intrinsically inside `_get_all_patterns()` instead.

## Why `LengthFilter` Had To Go

It used fixed 0.5x/2.0x length ratios independent of `recall_threshold`. For any `r <= 2/3`, its window is a **strict subset** of the recall-safe one — at `r=0.1` with a 20-token STM it kept only lengths `[10, 40]` where recall-safety requires `[1, 380]`, silently discarding patterns scoring as high as 0.66. It was recall-lossy and always had been — very likely why `filter_pipeline` defaulted to `[]` in the first place.

Removal hazard handled deliberately: unknown filter names are normally skipped with a warning (`executor.py:126-128`), which for a first-stage database filter would leave `candidates=None` and make the *next* filter raise. Dropping `'length'` from `valid_filters` makes a stale config fail **validation** with a clear message instead. Verified: `filter_pipeline=['length']` now validates as `False`.

## `recall_threshold = 0` Rejection — What Changed

Three validation points had to move in lockstep, or zero leaked through one: `settings.py` Pydantic field (`ge` -> `gt`), `SessionConfiguration.validate()`, and `ConfigurationService.validate_configuration_update()`. Also now rejects `bool` (an `int` subclass; previously passed silently as `1.0`).

Two **pre-existing** gaps closed on the way (bugs found, not introduced):
- `POST /sessions` never called `validate_configuration_update()` at all, unlike `POST /sessions/{id}/config` — create-time config was entirely unvalidated.
- Both `session_manager.py` and `redis_session_manager.py` **discarded the boolean return** from `SessionConfiguration.update()`, so a rejected value silently became the default instead of erroring.
- Also fixed `rapidfuzz_filter.py` reading config with `or 0.1` (coerces a legitimate `0.0`) and `getattr(config, 'use_token_matching', True)`, which returns `None` (not `True`) when the attribute exists and is `None` — silently selecting character-level matching.

Rehydration from Redis clamps-with-warning rather than failing, so sessions persisted with `r=0` from before this change survive an upgrade.

**Deliberately left for a follow-up**: the now-unreachable `r=0` branches at `pattern_search.py:1113-1127` and `prediction.py:228-232`. Rationale: removing behavior-bearing code in the same change that adds the validation preventing it from ever running is how regressions happen — retire once the validation has run in production. Filed as a backlog item.

## Measured Results (all verified this session against the live stack)

- Predicate over 1,000,000 synthetic patterns, **no index assistance**: 206ms, 1,000,000 -> 3,925 survivors.
- Selectivity, synthetic wide-vocabulary corpus, `r=0.1`: keeps 0.89% (~112x reduction); 0.42% genuinely match.
- Selectivity, synthetic narrow-vocabulary corpus, `r=0.1`: keeps 82.55%, but 71.95% genuinely match — little waste to recover there.
- Length window **alone**, `r=0.1`: keeps 99.77% — worthless without the token-overlap clause.
- Live 400-pattern corpus (40 sharing probe tokens, 360 disjoint): 400 candidates -> 40, predictions byte-identical.
- Recall violations across 120,000 pattern/STM pairs, both predicates combined: **0**.

**Honest caveat**: selectivity percentages come from synthetic corpora built by the author, not real training data — this ClickHouse instance holds only test corpora (14,034 patterns across 471 `kb_id`s, max length 10). The **losslessness** result is exact and corpus-independent; the **selectivity** numbers are estimates. Real-world benefit will vary entirely with vocabulary diversity: large on diverse corpora, near-none where everything genuinely matches. It never costs correctness either way.

## No Schema Migration Needed

`EXPLAIN indexes=1` against the live instance confirms `kato.patterns_data` already supports this: `ORDER BY (kb_id, length, name)` means the length predicate resolves by primary-key binary search; `INDEX idx_length` (minmax) and `INDEX idx_token_bloom` (bloom_filter on `token_set`) both engage, and `hasAny(token_set, ...)` prunes granules. The schema was already designed for this — the filter was simply never wired up correctly (see `LengthFilter` above).

## Safety Mechanisms (each with a dedicated test)

- **Fails open**: a bounded-query failure retries unbounded rather than returning an empty candidate set behind an HTTP 200.
- **Kill switch**: `KATO_RECALL_BOUND_ENABLED=false` emits the exact pre-bound query.
- **Auto-disabled in character-level mode** (`use_token_matching=False`): the scorer there is `fuzz.ratio` on joined strings — a *character* metric a token bound cannot bound (two strings can share many characters and zero tokens).
- **Degradation ladder**: an oversized STM token payload drops to the length window alone rather than truncating the token list — a partial list under-counts `common` and would make the predicate unsafe.
- **Audit mode**: `KATO_RECALL_BOUND_AUDIT=true` shadow-runs the unbounded query and logs `RECALL BOUND VIOLATION` for anything dropped that was actually reachable. Live result: "360 of 400 patterns dropped, none reachable."
- `recall_threshold` and `use_token_matching` are read from `PatternSearcher`'s **resolved** values, never from session config directly (whose fields default to `None`) — the bound is only safe because these are identical to what the scorer itself uses.

## Two False Comments Corrected

`kato/filters/executor.py` and `kato/filters/base.py` both asserted "Everything is bound server-side — nothing derived from user input is ever interpolated into statement text." **Verified false**: `clickhouse_connect.driver.binding.finalize_query` is `query % {k: format_query_value(v) ...}` — client-side string interpolation. The security conclusion still holds (`format_query_value` escapes quotes/backslashes; verified `a' OR 1=1 --` renders as `'a\' OR 1=1 --'`), but escaped values do land in statement text and count against ClickHouse's `max_query_size` (262144 bytes) — which is why the STM token array needs a byte budget (see degradation ladder above).

## Commits (39 files, +1325/-304)

- `b0626f8` feat(filters): add recall-safe candidate bound (pure, unwired) — new `kato/filters/recall_bounds.py` plus 22 proof tests, no runtime effect.
- `6755dd5` feat(config)!: reject `recall_threshold = 0`.
- `935346d` feat(filters): apply the recall-safe bound to the live candidate query.
- `9148f3b` refactor(filters)!: delete `LengthFilter`, superseded by the recall-safe bound.
- `1313930` test(parity): add a boundary corpus that actually reaches the bound's edge.

## Testing

Suite: **659 passed, 3 skipped, 1 xfailed** (was 625 before this session's additions; +22 `test_recall_bounds.py`, +12 `test_recall_bound_executor.py`).

- `tests/tests/unit/test_recall_bounds.py` (22 tests) — the proof. Exhaustive sweep asserting that whenever the *float* scorer accepts, the bound accepts. Mutation-checked: catches the naive-exact bound (413 violations) and an off-by-one on `max_length` (129 violations). Both sweeps assert their own non-vacuity (guards 324,029 scorer-accepted cases; fails if that drops below 300,000).
- `tests/tests/unit/test_recall_bound_executor.py` (12 tests) — fail-open, kill switch, character mode, audit-leak prevention, and a test that monkeypatches in a deliberately over-aggressive bound to prove the audit actually fires (a clean audit report from a broken audit is indistinguishable from a real one).
- `scripts/check_prediction_parity.py` gained `--boundary`: the default corpus cannot test the bound (patterns top out near 9 tokens; at the default threshold the window is roughly `[1,190]`, so every pattern sits far inside it and the gate passes vacuously). The boundary corpus places patterns exactly on the edge using `sim = 2M/(P+L) = r <=> P = 2M/r - L`, verified against the real scorer (e.g. `P=114/M=6` gives exactly `0.100000000` — the case a float-truncated `max_length` of 113 would wrongly drop). `boundary_self_check` requires at least one prediction sitting exactly at its `recall_threshold`. Parity result: **identical**, with the bound demonstrably pruning 5-6 of 8 candidates.

## Process Pattern — a Fourth (and Fifth) Instance of "A Verification That Could Not Have Failed"

Extends the three instances already logged in `project-manager/patterns.md` (the `.dockerignore` check with no caches present; the chunking test reading its own constant; the parity gate not exercising the pruned path — see the 2026-09-18 archive doc above):

- **Fourth**: `test_config_filter_pipeline_parameters` ended with `assert 'length_min_ratio' in config or 'length_max_ratio' in config or True` — the trailing `or True` made it unconditionally pass.
- **Fifth**: the replacement, written to fix the fourth, asserted against the fixture's `get_config()`, which hard-codes six keys and never returns filter parameters — it could never have passed. Corrected to read `GET /sessions/{id}/config`, the surface that actually carries them.

Full detail logged in `project-manager/patterns.md`.

## Verification

- Full suite: **659 passed / 3 skipped / 1 xfailed / 0 failed**
- Losslessness: 0 recall violations across a 120,000-pair sweep (both predicates)
- Audit mode live run: 360/400 dropped, 0 reachable
- Parity gate (default + `--boundary`): byte-identical predictions, boundary case demonstrably exercises pruning

## Decision Reference

**Decision**: DECISION-034 in `planning-docs/DECISIONS.md`
**Status**: Complete and verified on branch `perf/recall-safe-candidate-bound`. **Merged and released same day** as KATO v6.0.0 (DECISION-035), patched same day as v6.0.1 (DECISION-036/DECISION-037) — see `planning-docs/project-manager/pending-updates.md` for the (now resolved) merge/release item.
**Related Files**: `kato/filters/recall_bounds.py` (new), `kato/filters/executor.py`, `kato/filters/base.py`, `kato/searches/pattern_search.py`, `kato/config/settings.py`, `kato/sessions/session_config.py` (`SessionConfiguration.validate()`), `kato/services/configuration_service.py` (`ConfigurationService.validate_configuration_update()`), `kato/sessions/session_manager.py`, `kato/sessions/redis_session_manager.py`, `kato/filters/rapidfuzz_filter.py`, `scripts/check_prediction_parity.py`, `tests/tests/unit/test_recall_bounds.py` (new), `tests/tests/unit/test_recall_bound_executor.py` (new)
