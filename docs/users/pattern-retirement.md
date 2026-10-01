# Pattern retirement

Hide a learned pattern from predictions without deleting it, and put it back.

Retirement writes a tombstone. The learned row stays exactly where it was, and
every read path filters the pattern out. Nothing is destroyed, so the operation is
reversible and safe to get wrong.

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
statistics all remain, and the pattern still counts toward the corpus. Physical
deletion is a separate operation and is not yet available.

## Related

- [Session management](../operations/session-management.md) — sessions versus nodes
- [Core concepts](concepts.md) — how pattern identity is derived
