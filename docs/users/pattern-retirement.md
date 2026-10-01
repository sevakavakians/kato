# Pattern retirement and purging

Remove a learned pattern from a node, in two steps: retire it to hide it, purge it
to erase it.

Retirement writes a tombstone. The learned row stays exactly where it was, and
every read path filters the pattern out. Nothing is destroyed, so the operation is
reversible and safe to get wrong. Purging then deletes the row and unwinds the
pattern's contribution to the node's statistics; it is irreversible, and only a
retired pattern can be purged.

## Scope

A tombstone belongs to the **node**, like the learned patterns it hides — not to
the session that created it. So:

- every session sharing that `node_id` stops seeing the pattern, immediately;
- a session on a different `node_id` is unaffected, even if it learned the same
  sequence;
- the tombstone outlives the session, as learned patterns do.

## Retiring

```bash
curl -X POST http://localhost:8000/sessions/$SESSION/patterns/retire \
  -H "Content-Type: application/json" \
  -d '{"pattern_ids": ["7729f0ed56a13a9373fc1b1c17e34f61d4512ab4"]}'
```

A batch of 1 to 1000 IDs. Each must be a 40-character lowercase SHA1, optionally
`PTRN|`-prefixed — predictions report the prefixed form, the databases store the
bare hash, and both are accepted. Anything else is a `422`: a tombstone is durable
and is consulted on every read, so an ID that cannot name a real pattern would sit
in the registry indefinitely, indistinguishable from a deliberate retirement.

```json
{
  "status": "okay",
  "session_id": "session-…",
  "node_id": "alice",
  "requested": 1,
  "retired": ["7729f0ed56a13a9373fc1b1c17e34f61d4512ab4"],
  "already_retired": []
}
```

`retired` and `already_retired` are reported separately, so re-sending a batch
tells you what actually changed. Retiring is idempotent; it never resets the state
of an ID already retired.

A well-formed hash that names no pattern is accepted. Retirement is a statement
about a hash rather than a lookup — requiring the pattern to exist first would be
racy against concurrent learning, and an unused tombstone is harmless and
removable.

## Where it takes effect

Everywhere a pattern can surface:

| | |
| --- | --- |
| `GET /sessions/{id}/predictions` | filtered |
| observe-time predictions | filtered |
| `GET /sessions/{id}/cognition-data` | filtered, including a snapshot captured before the retirement |
| single-symbol fast path | filtered before `max_predictions` truncation, so a retired pattern cannot consume a slot and leave you short |

## Re-learning a retired pattern

A pattern's identity is the SHA1 of its data, so observing the same sequence again
produces the same hash. Learning it would therefore resurrect it, and retirement
could be undone by accident. Instead, `/learn` returns **409 Conflict**:

```json
{
  "error": {
    "code": "RETIRED_PATTERN",
    "recoverable": true,
    "message": "Pattern 7729f0ed… is retired on this node and cannot be learned again. Un-retire it first if it should exist."
  }
}
```

This is a conflict rather than a failure: you retired it, and you can undo that.
If the sequence genuinely should exist again, un-retire it first. If you want a
different pattern, it needs different data — the same symbols in the same order
will always hash the same way.

## Un-retiring

```bash
curl -X POST http://localhost:8000/sessions/$SESSION/patterns/un-retire \
  -H "Content-Type: application/json" \
  -d '{"pattern_ids": ["7729f0ed56a13a9373fc1b1c17e34f61d4512ab4"]}'
```

```json
{
  "status": "okay",
  "requested": 1,
  "un_retired": ["7729f0ed56a13a9373fc1b1c17e34f61d4512ab4"],
  "not_retired": []
}
```

The pattern becomes visible and learnable again. `not_retired` lists IDs that had
no tombstone, so a no-op is distinguishable from a real change.

## Cost

On a node that has never retired anything — the default — each read path does one
Redis `EXISTS` against a key that does not exist, and then nothing. Once
tombstones exist, it is one `HMGET` scoped to the candidates in hand. Prediction
output is unchanged when nothing is retired.

## What this is not

Retirement does not reclaim storage. The learned row, its metadata and its symbol
statistics all remain, and the pattern still counts toward the corpus. To erase a
pattern, purge it — see below.

## Purging

Purge is the irreversible half of the lifecycle. It deletes the pattern's rows
from ClickHouse and subtracts its share of the node's symbol, affinity and global
counters, leaving the node as if the pattern had never been learned.

Only a retired pattern can be purged. That is deliberate: erasure always goes
through a reversible step first, so you can retire, confirm the effect on
predictions, and only then decide to erase.

```bash
# Erase specific patterns
curl -X POST http://localhost:8000/sessions/$SESSION/patterns/purge \
  -H 'Content-Type: application/json' \
  -d '{"pattern_ids": ["7729f0ed56a13a9373fc1b1c17e34f61d4512ab4"]}'

# Or finish erasing everything already retired on this node
curl -X POST http://localhost:8000/sessions/$SESSION/patterns/purge \
  -H 'Content-Type: application/json' -d '{}'
```

```json
{
  "status": "completed",
  "session_id": "...",
  "node_id": "my-node",
  "purged": ["7729f0ed56a13a9373fc1b1c17e34f61d4512ab4"],
  "failed": {},
  "remaining": 0
}
```

`status` is `partial` when some IDs could not be purged, with a reason per ID in
`failed`; `remaining` counts retired patterns still awaiting a purge, so you can
drive a backlog to zero with repeated calls. `max_patterns` (default 1000) bounds
one call.

Purge is resumable. If it is interrupted — a restart, a store becoming briefly
unavailable — the patterns it did not finish are reported in `failed`, and calling
it again continues from where it stopped. It never applies a subtraction twice,
and it never records a pattern as purged until both stores confirm the pattern is
gone.

### The tombstone outlives the purge

Purging keeps the tombstone. Without it, purge would undo itself: a pattern's
identity is the SHA1 of its data, so the next observation of the same sequence
would re-learn the same ID. Learning that sequence therefore still returns `409`
until you un-retire it.

### Precomputed metrics are invalidated

Two of the stored entropy metrics are derived from node-wide statistics —
`normalized_entropy` uses the node's unique-symbol count, and
`global_normalized_entropy` uses its symbol probabilities — so a purge makes them
wrong for *every* remaining pattern, including ones that shared no symbol with
what was purged. Purge clears them for the node.

Predictions stay correct either way: they fall back to computing these per
request, which is the same path a node takes before `finalize-training` has ever
run. Re-run `finalize-training` to restore the precomputation.

### Cost

Purge is much heavier than retirement. It issues ClickHouse mutations and waits
for them to apply, so it is an administrative operation, not something to put on
a request path. Prefer one call with many IDs over many calls with one.

### What purge cannot recover

If a pattern carried emotives and was learned before this version, its exact
contribution to per-symbol affinity was not recorded at the time, and purge
reverses a best estimate instead of an exact figure. Affinity accumulates
*averaged* emotives, and the average shifts with the rolling persistence window on
every learn, so the figure cannot be recomputed after the fact. For a pattern
learned once whose emotives are still within the window the estimate is exact;
beyond that it is approximate. Patterns learned by this version onward record the
figure and are reversed exactly. The subtraction is clamped either way, so an
over-estimate cannot drive a shared symbol's affinity negative.

## Related

- [Session management](../operations/session-management.md) — sessions versus nodes
- [Core concepts](concepts.md) — how pattern identity is derived
- [Emotives processing](../research/emotives-processing.md) — how affinity accumulates
