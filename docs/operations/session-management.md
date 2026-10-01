# KATO Session Management Guide

## Overview

KATO runs as a **single service** that serves many isolated sessions. A session
carries its own short-term memory (STM) and its own configuration, so two callers
can observe different things, at different recall thresholds, against the same
service at the same time without interfering.

This replaced an earlier approach of running one container per configuration, each
on its own port. If you are looking for `./start.sh --id` / `--port` /
`--recall-threshold`, those flags no longer exist: per-session configuration is
how you get the behaviour they used to provide, and it is cheaper — no extra
container, no port to allocate, and the configuration can change at runtime.

### Sessions vs nodes

Two identifiers matter, and conflating them is the usual source of confusion:

- **`session_id`** — scopes **short-term memory**. Issued by the service when you
  create a session. Expires.
- **`node_id`** — scopes **long-term memory**: learned patterns, symbol
  statistics, metadata. You choose it. It is durable and outlives every session.

Several sessions may share one `node_id`. They each keep a private STM while
reading and writing the *same* learned patterns. That is the normal way to have
several workers contribute to one body of knowledge. Give them different
`node_id`s instead and they share nothing.

## Quick Start

```bash
# Start the stack (bare `./start.sh` prints help and starts nothing)
./start.sh start
```

```bash
# Create a session. node_id picks the long-term memory it reads and writes.
curl -X POST http://localhost:8000/sessions \
  -H "Content-Type: application/json" \
  -d '{"node_id": "alice", "config": {"max_predictions": 50}}'
```

The response carries the `session_id`, its `expires_at`, and the fully resolved
`session_config` — every parameter, including the ones you did not set. Use that
to confirm what the session is actually running with rather than assuming.

```bash
SESSION=$(curl -s -X POST http://localhost:8000/sessions \
  -H "Content-Type: application/json" \
  -d '{"node_id": "alice"}' | python3 -c 'import json,sys; print(json.load(sys.stdin)["session_id"])')

# Observe, learn, predict
curl -X POST http://localhost:8000/sessions/$SESSION/observe \
  -H "Content-Type: application/json" -d '{"strings": ["hello"]}'
curl -X POST http://localhost:8000/sessions/$SESSION/observe \
  -H "Content-Type: application/json" -d '{"strings": ["world"]}'
curl -X POST http://localhost:8000/sessions/$SESSION/learn -d '{}'

curl -X POST http://localhost:8000/sessions/$SESSION/clear-stm -d '{}'
curl -X POST http://localhost:8000/sessions/$SESSION/observe \
  -H "Content-Type: application/json" -d '{"strings": ["hello"]}'
curl http://localhost:8000/sessions/$SESSION/predictions
```

## Managing Sessions

```bash
# Inspect one session (config, STM length, expiry)
curl http://localhost:8000/sessions/$SESSION

# Does it still exist? Cheaper than fetching it.
curl http://localhost:8000/sessions/$SESSION/exists

# How many sessions are active service-wide
curl http://localhost:8000/sessions/count

# Push the expiry out
curl -X POST http://localhost:8000/sessions/$SESSION/extend \
  -H "Content-Type: application/json" -d '{"ttl_seconds": 7200}'

# Clear STM, keeping learned patterns
curl -X POST http://localhost:8000/sessions/$SESSION/clear-stm -d '{}'

# Clear STM *and* every learned pattern for this node_id. Destructive, and it
# affects every session sharing the node, not just this one.
curl -X POST http://localhost:8000/sessions/$SESSION/clear-all -d '{}'

# Delete the session. Learned patterns survive -- they belong to the node_id.
curl -X DELETE http://localhost:8000/sessions/$SESSION

# Service health
curl http://localhost:8000/health
docker compose ps
```

There is **no endpoint that lists every session**. `GET /sessions` is not a
listing — it returns `405`. Use `/sessions/count` for the total, and keep your own
record of the ids you created; the service treats a `session_id` as a capability,
not a directory entry.

### Expiry

Sessions expire after `SESSION_TTL` seconds (default **3600**). With
`SESSION_AUTO_EXTEND=true` (the default) activity pushes the expiry out, so a
session in continuous use does not lapse underneath you. An idle one will, and
requests against it return `404` — treat that as recoverable and create a new
session rather than as a fault.

## Per-Session Configuration

Set configuration when creating a session, or change it at runtime:

```bash
# At creation
curl -X POST http://localhost:8000/sessions \
  -H "Content-Type: application/json" \
  -d '{"node_id": "bob", "config": {"recall_threshold": 0.3, "max_pattern_length": 10}}'

# At runtime -- POST, not PUT (PUT returns 405)
curl -X POST http://localhost:8000/sessions/$SESSION/config \
  -H "Content-Type: application/json" \
  -d '{"config": {"recall_threshold": 0.5}}'

# Read back what is in effect
curl http://localhost:8000/sessions/$SESSION/config
```

An invalid value is rejected with `400` and a message naming the field, so a
typo fails loudly at the call rather than silently falling back to a default.

### Parameters

Every field below is optional; omitted fields take the system default. These are
the resolved defaults a session reports when you set nothing.

| Parameter | Default | Notes |
|---|---|---|
| `recall_threshold` | `0.1` | Must be **> 0**. Zero accepted every pattern regardless of similarity and is rejected as of 6.0.0. |
| `max_predictions` | `100` | 1–10000. |
| `max_pattern_length` | `0` | `0` means manual learning only; above zero auto-learns at that length. |
| `persistence` | `5` | Emotive rolling-window size, 1–100. |
| `stm_mode` | `CLEAR` | `CLEAR` or `ROLLING`, applied after auto-learn. |
| `indexer_type` | `VI` | |
| `use_token_matching` | `True` | Token-level (exact difflib parity) vs character-level. See the note below about `sort_symbols`. |
| `sort_symbols` | `True` | |
| `fuzzy_token_threshold` | `0.0` | `0.0` disables fuzzy token matching. |
| `rank_sort_algo` | `'potential'` | Prediction ranking metric. |
| `process_predictions` | `True` | |
| `vector_event_mode` | `'neighbors_plus_self'` | Or `self_only`, which skips the neighbour search. |
| `vector_search_limit` | `3` | 1–100. See the warning below before changing it. |
| `return_vector_search_results` | `False` | Adds request-local vector search diagnostics to an observation's response. |
| `filter_pipeline` | `[]` | Ordered filter names from `minhash`, `jaccard`, `bloom`, `rapidfuzz`. |
| `jaccard_threshold` | `0.3` | |
| `jaccard_min_overlap` | `2` | |
| `minhash_threshold` | `0.7` | |
| `minhash_bands` | `20` | |
| `minhash_rows` | `5` | |
| `minhash_num_hashes` | `100` | |
| `bloom_false_positive_rate` | `0.01` | |
| `max_candidates_per_stage` | `100000` | |
| `enable_filter_metrics` | `True` | |

> **`use_token_matching` and `sort_symbols` are only linked on the update path.**
> `POST /sessions/{id}/config` auto-sets `sort_symbols` to match
> `use_token_matching` when you supply one and not the other, and warns if you
> supply both with conflicting values. `POST /sessions` does **not** — creating a
> session with `use_token_matching: false` leaves `sort_symbols` at `true`, which
> is character-level matching over sorted symbols, probably not what was intended.
> Until that is reconciled, set **both** explicitly at creation:
> `{"use_token_matching": false, "sort_symbols": false}`.

> **`vector_search_limit` is not a free tuning knob.** The vector IDs it
> retrieves become symbols in the STM event, so they feed the learned pattern's
> SHA1. Change it and patterns learned afterwards have different identities from
> those learned before — a corpus built at one limit is not comparable with one
> built at another. Pick a value before you start training, not during.

See [configuration-vars.md](../reference/configuration-vars.md) for the
service-wide environment variables behind these defaults.

## Isolation Model

| | Scope | Shared between sessions on one `node_id`? |
|---|---|---|
| Short-term memory | session | No |
| Session configuration | session | No |
| Learned patterns | `node_id` | **Yes** |
| Symbol statistics, metadata | `node_id` | **Yes** |

Two consequences worth planning around:

**Learning is visible to siblings.** A session that learns a pattern makes it
available to every other session on that `node_id` immediately. That is the point
when several workers build one corpus, and a surprise if you expected a session to
be a sandbox. For genuine isolation, use a different `node_id`.

**`clear-all` is node-wide.** It drops every learned pattern for the `node_id`,
not just the calling session's contributions.

### One writer per session

A session must have **one concurrent writer**. Do not send overlapping
`observe`/`learn` requests for the same `session_id`.

Under multi-worker uvicorn (the default is 4 workers) the serialisation lock is
per process, and the session is persisted as a whole blob, so two concurrent
writes to one session can lose an update. This is a documented limitation rather
than an open bug — see DECISION-024 in `planning-docs/DECISIONS.md`.

Concurrency comes from using **one session per concurrent writer**. Several
sessions on the same `node_id` run concurrently without contention and still
share learned patterns, which is almost always what the multiple-writer instinct
is actually reaching for.

## Patterns of Use

What previously required several containers on several ports is now several
sessions against one service.

### Comparing configurations side by side

```bash
HIGH=$(curl -s -X POST http://localhost:8000/sessions -H "Content-Type: application/json" \
  -d '{"node_id": "shared_corpus", "config": {"recall_threshold": 0.05}}' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["session_id"])')

LOW=$(curl -s -X POST http://localhost:8000/sessions -H "Content-Type: application/json" \
  -d '{"node_id": "shared_corpus", "config": {"recall_threshold": 0.5}}' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["session_id"])')
```

Both read the same learned patterns and apply different thresholds to them, which
is a cleaner comparison than two instances with two separate corpora: the only
variable is the threshold.

### A/B testing a parameter

Create two sessions on the same `node_id` differing in one field, drive the same
observations through both, and compare predictions. Because the corpus is shared,
any difference is attributable to the parameter.

If you need the corpora themselves to differ, give the sessions different
`node_id`s — then each learns its own patterns, and you are comparing two bodies
of knowledge rather than two readings of one.

### Task-specific configuration

A session doing document-chunk matching can set `use_token_matching: false` while
another on the same service keeps token-level matching. No separate deployment is
involved; the setting travels with the session.

## Scaling

Horizontal scale comes from running more KATO replicas behind a load balancer, not
from running differently-configured instances on adjacent ports. Processors are
externally stateless and session state lives in Redis, so any replica can serve
any session.

Within one deployment, `KATO_WORKERS` (default 4) sets the uvicorn worker count,
and `KATO_LIMIT_CONCURRENCY` (default 100) the per-worker connection limit.
`GET /concurrency` reports both along with current and peak usage. See
[docker-deployment.md](docker-deployment.md).

## Troubleshooting

**`404` on a session that used to work.** It expired. Check with
`/sessions/{id}/exists` and create a new one. Learned patterns are unaffected —
they belong to the `node_id`.

**`400` on create or config update.** A parameter failed validation; the response
names the field. Note `recall_threshold` must be greater than zero, and
`filter_pipeline` accepts only `minhash`, `jaccard`, `bloom`, `rapidfuzz`.

**Predictions come back empty.** Check in this order: the STM holds at least one
symbol (`GET /sessions/{id}/stm`); patterns were actually learned for this
`node_id` (`GET /patterns/count`); and `recall_threshold` is not set higher than
the similarity your query can reach.

**Updates to a session seem to go missing.** Two writers are sharing one
`session_id` — see *One writer per session* above.

**Port 8000 already in use.** One service now serves every session, so a second
instance is rarely what you want. Stop the existing one with `./start.sh stop`,
or change the published port in `docker-compose.yml`.

## Related

- [Session management for users](../users/session-management.md) — API-level guide
- [Network topology patterns](network-topology.md) — connecting several KATO
  deployments into pipelines and other topologies
- [Configuration variables](../reference/configuration-vars.md)
- [Docker deployment](docker-deployment.md)
