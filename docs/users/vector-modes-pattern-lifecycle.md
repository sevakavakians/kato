# Vector modes and pattern lifecycle

These additions build on KATO 5.2.0 and retain its ClickHouse metadata facade,
stateless observation pipeline, parameterized search queries, and deterministic
prediction ranking.

## Session configuration

Set these fields in the session configuration when creating or updating a session:

| Field | Default | Meaning |
| --- | --- | --- |
| `vector_event_mode` | `neighbors_plus_self` | Nearest vector IDs plus the query vector's own ID. `self_only` emits only the own ID and skips neighbor search. Both modes queue the vector for learning. |
| `vector_search_limit` | `20` | Integer from 1 through 100. The upstream default was 3; set 3 explicitly to preserve that candidate count. |
| `return_vector_search_results` | `false` | Include vector search diagnostics in an individual observation response. |
| `single_symbol_match_mode` | `first_token` | `first_event_contains` also matches a single queried symbol when it is a nonleading member of the first event. |

Diagnostics include the query vector ID, requested limit, search status, metric,
score direction, and ranked matches. An appended self ID has a null score and
`source=self_appended`; it is not an additional retrieved neighbor. Diagnostics
are returned with the request and are not stored in session state or learned
pattern events. Scores keep the vector store's native meaning.

## Retirement and purge

Both endpoints operate on the session's node and accept a batch of 1 to 1000
pattern IDs in `{"pattern_ids": ["<hash>"]}`. IDs may have a `PTRN|` prefix.

- `POST /sessions/{session_id}/patterns/retire` adds durable tombstones and
  filters the IDs out of prediction paths. It does not delete learned rows.
- `POST /sessions/{session_id}/patterns/purge-retired` physically removes only
  already-retired patterns and reports per-pattern success, skips, and failures.

Purge stores the counter/affinity cleanup snapshot before deleting ClickHouse
rows. It deletes pattern data, metadata sidecar rows, and LSH entries, applies
idempotent Redis counter cleanup, invalidates affected caches and finalized
metrics, and verifies absence before marking a tombstone `purged`. Tombstones
remain, so the same hash cannot be learned again through the normal learning
path. A replacement pattern needs a different identity.

A failure leaves the tombstone and recovery state in place. Retrying is supported;
an HTTP response alone does not establish success: inspect `status`, `purged`,
and `failed`. Legacy emotive contributions without an exact per-pattern ledger
are refused. Do not train or finalize the same node concurrently with a purge;
the multi-store operation is resumable but is not a transaction across stores.

## Process-level controls

- `KATO_DISTRIBUTED_STM_ENABLED=false` disables initialization of the optional
  distributed STM mirror. The default remains enabled.
- `KATO_REPAIR_REDIS_ONLY_PATTERNS=true` enables guarded repair for an isolated
  recovery worker. It verifies the exact single-learn record and uses the
  metadata facade. Missing, unreadable, or unmigrated metadata is rejected when
  absence cannot be proven. This is not an automatic metadata migration.

Normal learning waits for durable ClickHouse inserts before updating metadata
and counters. Metric cache invalidation uses a shared generation token; cached
values from older generations expire through their existing TTL.
