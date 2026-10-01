"""Tests for the pattern purge endpoint.

    POST /sessions/{id}/patterns/purge

Purge is the irreversible half of the retirement lifecycle: it deletes the
pattern's rows from both stores and subtracts its share of the node's symbol,
affinity and global counters. The properties worth pinning at this level are the
ones that span the stack and so cannot be caught by the Redis-level arithmetic
tests in tests/integration/test_pattern_purge_redis.py:

 - erasure really is reachable only through retirement
 - a purged pattern is gone from predictions *and* from the corpus, not merely
   hidden, while patterns sharing its symbols keep predicting
 - the node's counters settle back to what they would have been
 - the operation is resumable and idempotent at the request level
 - the tombstone survives, so the same sequence is not silently re-learned

Request-level, because the failure that motivated the driver redesign was an
ordering one between the two stores, which only shows up end to end.
"""

import os
import sys
import uuid

import pytest
import requests

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

VALID_HASH = 'a' * 40


def _base_url():
    return os.environ.get("KATO_BASE_URL", "http://localhost:8000")


def _create_session(node_id=None, ttl=180):
    if node_id is None:
        node_id = f"test_purge_{uuid.uuid4().hex[:8]}"
    resp = requests.post(f"{_base_url()}/sessions", json={
        "node_id": node_id, "config": {}, "metadata": {}, "ttl_seconds": ttl,
    }, timeout=15)
    resp.raise_for_status()
    return resp.json()["session_id"], node_id


def _learn(session_id, *tokens, emotives=None):
    base = _base_url()
    for token in tokens:
        payload = {"strings": [token]}
        if emotives:
            payload["emotives"] = emotives
        requests.post(f"{base}/sessions/{session_id}/observe",
                      json=payload, timeout=20).raise_for_status()
    name = requests.post(f"{base}/sessions/{session_id}/learn",
                         json={}, timeout=20).json()["pattern_name"]
    requests.post(f"{base}/sessions/{session_id}/clear-stm", json={}, timeout=15)
    # /learn reports the human-readable 'PTRN|' form; everything stored and
    # reported by retire/purge is the bare hash. Compare on the stored form.
    return name.removeprefix("PTRN|")


def _predictions_for(session_id, symbol):
    base = _base_url()
    requests.post(f"{base}/sessions/{session_id}/clear-stm", json={}, timeout=15)
    requests.post(f"{base}/sessions/{session_id}/observe",
                  json={"strings": [symbol]}, timeout=20)
    return requests.get(f"{base}/sessions/{session_id}/predictions",
                        timeout=20).json()["predictions"]


def _retire(session_id, pattern_ids):
    return requests.post(f"{_base_url()}/sessions/{session_id}/patterns/retire",
                         json={"pattern_ids": pattern_ids}, timeout=20)


def _purge(session_id, payload=None):
    return requests.post(f"{_base_url()}/sessions/{session_id}/patterns/purge",
                         json=payload if payload is not None else {}, timeout=60)


def _gene(session_id, gene):
    """Read one of the node's counters through the API."""
    resp = requests.get(f"{_base_url()}/sessions/{session_id}/cognition-data", timeout=20)
    resp.raise_for_status()
    return resp.json().get(gene)


# ------------------------------------------------------------------ gating


def test_purge_requires_retirement_first():
    """Erasure must be reachable only through the reversible step.

    This is the safety property of the whole design: there is no way to delete a
    pattern without first retiring it, observing the effect, and deciding to go on.
    """
    session_id, _ = _create_session()
    name = _learn(session_id, "pg_a_head", "pg_a_tail")

    resp = _purge(session_id, {"pattern_ids": [name]})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["purged"] == []
    assert body["status"] == "partial"
    assert body["failed"][name] == "not retired"

    # Still fully intact.
    assert len(_predictions_for(session_id, "pg_a_head")) > 0


def test_purge_removes_pattern_from_corpus_not_just_predictions():
    """The distinction from retirement: the pattern is gone, not hidden."""
    session_id, _ = _create_session()
    name = _learn(session_id, "pg_b_head", "pg_b_tail")
    before = _gene(session_id, "total_unique_patterns") or _gene(session_id, "num_patterns")

    assert _retire(session_id, [name]).status_code == 200
    resp = _purge(session_id, {"pattern_ids": [name]})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "completed", body
    assert body["purged"] == [name]
    assert body["failed"] == {}

    assert _predictions_for(session_id, "pg_b_head") == []
    after = _gene(session_id, "total_unique_patterns") or _gene(session_id, "num_patterns")
    if before is not None and after is not None:
        assert after == before - 1, f"pattern count did not drop: {before} -> {after}"


def test_purge_leaves_patterns_sharing_symbols_predicting():
    """The counter arithmetic must not damage a pattern that shares a symbol.

    A purge that deleted shared symbol state instead of decrementing it would
    leave this pattern in the corpus but unable to match.
    """
    session_id, _ = _create_session()
    doomed = _learn(session_id, "pg_shared", "pg_doomed_tail")
    survivor = _learn(session_id, "pg_shared", "pg_survivor_tail")
    assert doomed != survivor

    assert _retire(session_id, [doomed]).status_code == 200
    body = _purge(session_id, {"pattern_ids": [doomed]}).json()
    assert body["purged"] == [doomed], body

    names = {p["name"].removeprefix("PTRN|") for p in _predictions_for(session_id, "pg_shared")}
    assert survivor in names, f"survivor stopped predicting; got {names}"
    assert doomed not in names


def test_purge_is_idempotent_and_resumable():
    """Re-issuing a completed purge must be a no-op, not a second subtraction."""
    session_id, _ = _create_session()
    name = _learn(session_id, "pg_c_head", "pg_c_tail")
    _retire(session_id, [name])

    first = _purge(session_id, {"pattern_ids": [name]}).json()
    assert first["purged"] == [name], first

    second = _purge(session_id, {"pattern_ids": [name]}).json()
    assert second["purged"] == []
    assert second["failed"] == {}
    assert second["status"] in ("completed", "nothing_to_purge"), second


def test_purge_without_ids_drains_the_retirement_backlog():
    """The operational case: finish erasing everything already retired."""
    session_id, _ = _create_session()
    names = [
        _learn(session_id, f"pg_d{i}_head", f"pg_d{i}_tail") for i in range(3)
    ]
    keeper = _learn(session_id, "pg_keeper_head", "pg_keeper_tail")

    assert _retire(session_id, names).status_code == 200
    body = _purge(session_id).json()
    assert body["status"] == "completed", body
    assert sorted(body["purged"]) == sorted(names)
    assert body["remaining"] == 0

    # The unretired pattern is untouched.
    assert keeper not in body["purged"]
    assert len(_predictions_for(session_id, "pg_keeper_head")) > 0


def test_purged_pattern_is_not_silently_relearned():
    """The tombstone must survive the purge.

    Dropping it would make purge self-undoing: the next observation of the same
    sequence re-learns the same hash, because a pattern's identity is the SHA1 of
    its data. Learning must refuse with 409 until the caller un-retires.
    """
    base = _base_url()
    session_id, _ = _create_session()
    name = _learn(session_id, "pg_e_head", "pg_e_tail")
    _retire(session_id, [name])
    assert _purge(session_id, {"pattern_ids": [name]}).json()["purged"] == [name]

    for token in ("pg_e_head", "pg_e_tail"):
        requests.post(f"{base}/sessions/{session_id}/observe",
                      json={"strings": [token]}, timeout=20)
    resp = requests.post(f"{base}/sessions/{session_id}/learn", json={}, timeout=20)
    assert resp.status_code == 409, f"expected 409, got {resp.status_code}: {resp.text}"

    # And un-retire restores learnability, so this is not a dead end.
    requests.post(f"{base}/sessions/{session_id}/patterns/un-retire",
                  json={"pattern_ids": [name]}, timeout=20).raise_for_status()
    resp = requests.post(f"{base}/sessions/{session_id}/learn", json={}, timeout=20)
    assert resp.status_code == 200, resp.text
    assert resp.json()["pattern_name"].removeprefix("PTRN|") == name


# ------------------------------------------------------------------ isolation


def test_purge_accepts_both_id_forms():
    """Callers may pass what /learn printed or what the registry stores."""
    for prefix in ("", "PTRN|"):
        session_id, _ = _create_session()
        name = _learn(session_id, f"pg_form_{len(prefix)}_head", "pg_form_tail")
        _retire(session_id, [prefix + name])
        body = _purge(session_id, {"pattern_ids": [prefix + name]}).json()
        # Reported bare either way, so a caller can compare without normalising.
        assert body["purged"] == [name], (prefix, body)


def test_purge_is_scoped_to_its_own_node():
    """A purge on one node must leave an identical pattern on another intact."""
    session_a, _ = _create_session()
    session_b, _ = _create_session()
    name_a = _learn(session_a, "pg_iso_head", "pg_iso_tail")
    name_b = _learn(session_b, "pg_iso_head", "pg_iso_tail")
    assert name_a == name_b, "same sequence must hash the same on both nodes"

    _retire(session_a, [name_a])
    assert _purge(session_a, {"pattern_ids": [name_a]}).json()["purged"] == [name_a]

    assert _predictions_for(session_a, "pg_iso_head") == []
    assert len(_predictions_for(session_b, "pg_iso_head")) > 0, "neighbour node lost its pattern"


def test_purge_with_emotives_keeps_other_predictions_sane():
    """Affinity reversal must not break prediction for a symbol it shared."""
    session_id, _ = _create_session()
    doomed = _learn(session_id, "pg_emo_shared", "pg_emo_doomed",
                    emotives={"joy": 0.7})
    survivor = _learn(session_id, "pg_emo_shared", "pg_emo_survivor",
                      emotives={"joy": 0.2})

    _retire(session_id, [doomed])
    assert _purge(session_id, {"pattern_ids": [doomed]}).json()["purged"] == [doomed]

    predictions = _predictions_for(session_id, "pg_emo_shared")
    names = {p["name"].removeprefix("PTRN|") for p in predictions}
    assert names == {survivor}, names
    # Still a well-formed prediction, with its own emotives intact.
    assert predictions[0]["emotives"].get("joy") == pytest.approx(0.2, abs=1e-6)


# ------------------------------------------------------------------ validation


def test_purge_rejects_malformed_pattern_ids():
    """Malformed ids are a 422, not a 500 and not a tombstone.

    A purge id reaches ALTER ... DELETE statement text, so the SHA1 shape is
    enforced at the edge.
    """
    session_id, _ = _create_session()
    for bad in (["not-a-hash"], [""], ["PTRN|"], ["A" * 40], [123]):
        resp = _purge(session_id, {"pattern_ids": bad})
        assert resp.status_code == 422, f"{bad!r} -> {resp.status_code}: {resp.text}"


def test_purge_rejects_an_explicitly_empty_list():
    """[] must not be read as "purge everything" -- omitting the field means that."""
    session_id, _ = _create_session()
    resp = _purge(session_id, {"pattern_ids": []})
    assert resp.status_code == 422, resp.text


def test_purge_rejects_an_oversized_batch():
    session_id, _ = _create_session()
    resp = _purge(session_id, {"pattern_ids": [VALID_HASH] * 1001})
    assert resp.status_code == 422, resp.text


def test_purge_honours_max_patterns():
    """The bound exists so a large backlog cannot hold a request open."""
    session_id, _ = _create_session()
    names = [_learn(session_id, f"pg_f{i}_head", f"pg_f{i}_tail") for i in range(3)]
    _retire(session_id, names)

    body = _purge(session_id, {"max_patterns": 1}).json()
    assert len(body["purged"]) == 1, body
    assert body["remaining"] == 2, body

    rest = _purge(session_id, {"max_patterns": 10}).json()
    assert len(rest["purged"]) == 2, rest
    assert rest["remaining"] == 0


def test_purge_rejects_invalid_max_patterns():
    session_id, _ = _create_session()
    assert _purge(session_id, {"max_patterns": 0}).status_code == 422
    assert _purge(session_id, {"max_patterns": 10001}).status_code == 422


def test_purge_on_missing_session_is_404():
    """Not a 500: get_session_lock returns None for an unknown session, and
    `async with None` would otherwise surface as an internal error."""
    resp = _purge(f"nonexistent-{uuid.uuid4().hex}", {"pattern_ids": [VALID_HASH]})
    assert resp.status_code == 404, f"{resp.status_code}: {resp.text}"


def test_purge_of_unknown_but_wellformed_id_reports_per_id():
    """One unusable id must be reported, not raised, and not abort a batch."""
    session_id, _ = _create_session()
    real = _learn(session_id, "pg_g_head", "pg_g_tail")
    _retire(session_id, [real])

    body = _purge(session_id, {"pattern_ids": [VALID_HASH, real]}).json()
    assert body["purged"] == [real], body
    assert body["failed"] == {VALID_HASH: "not retired"}, body
    assert body["status"] == "partial"


def test_purge_refuses_a_pattern_whose_row_is_missing():
    """A store desync must be reported per id, not purged and not a 500.

    The symbol counts to reverse come from the stored pattern, so if the
    ClickHouse row is gone while Redis still holds the frequency counter, there is
    no way to subtract the pattern's per-symbol share. Purging anyway would move
    the global counters only, and marking it purged discards the snapshot, so the
    difference becomes unrecoverable. Refusing keeps it fixable.
    """
    import clickhouse_connect

    session_id, node_id = _create_session()
    name = _learn(session_id, "pg_desync_head", "pg_desync_tail")
    _retire(session_id, [name])

    # Remove the row behind the service's back, leaving Redis intact.
    client = clickhouse_connect.get_client(
        host=os.environ.get("KATO_TEST_CLICKHOUSE_HOST", "localhost"),
        port=8123, database="kato")
    client.command(
        f"ALTER TABLE kato.patterns_data DELETE WHERE kb_id = '{node_id}_kato' "
        f"AND name = '{name}'", settings={'mutations_sync': 2})

    resp = _purge(session_id, {"pattern_ids": [name]})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["purged"] == [], body
    assert body["status"] == "partial"
    assert "patterns_data" in body["failed"][name], body["failed"]
