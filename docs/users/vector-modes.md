# Vector event modes and search diagnostics

Session-scoped control over what a vector observation emits, and an opt-in view
of the scores the nearest-neighbour search already computes.

## Session configuration

Set these when creating a session or via `POST /sessions/{session_id}/config`.

| Field | Default | Meaning |
| --- | --- | --- |
| `vector_event_mode` | `neighbors_plus_self` | Nearest vector IDs plus the query vector's own ID. `self_only` emits only the own ID and skips the neighbour search entirely. Both modes queue the vector for learning. |
| `vector_search_limit` | `3` | Integer from 1 through 100. |
| `return_vector_search_results` | `false` | Include vector search diagnostics in the response to an individual observation. |

`vector_search_limit` defaults to 3 deliberately. The retrieved IDs become
symbols in the STM event, so they feed the learned pattern's SHA1 — raising the
limit changes the identity of patterns learned from vector input, and a corpus
learned at one limit is not comparable with one learned at another. Raise it per
session when you want broader retrieval; do not treat it as a global tuning knob
part-way through a corpus.

`self_only` is useful when you want each vector observation to mint its own
symbol rather than collide with earlier vectors — it never returns a neighbour,
so successive observations of similar vectors stay distinct.

## Diagnostics

With `return_vector_search_results` enabled, an observation response carries a
`vector_search` object: the query vector ID, the requested limit, whether a
search ran, the metric, the score direction, and the ranked matches.

Scores keep the vector store's native meaning — for a distance metric, lower is
closer. An appended self ID is reported with a null score and
`source=self_appended`, so it is not mistaken for a retrieved neighbour; a
retrieved neighbour whose score the store cannot express as a finite number also
reports null, but keeps `source=vector_index`.

Diagnostics are returned with the request and are not stored in session state or
in learned pattern events. They are absent from the response unless the session
opted in.

## Process-level controls

`KATO_DISTRIBUTED_STM_ENABLED=false` skips initialising the optional distributed
STM mirror. The mirror is a cross-worker event log, not session STM and not
learned pattern storage, so a single-worker deployment can disable it rather than
accumulate a log nothing consumes. The default remains enabled.

## Metric cache invalidation

Metric cache invalidation rotates a shared generation token rather than scanning
and deleting the Redis keyspace. Values from an older generation become
unreachable immediately and lapse on their existing TTL instead of being deleted.
