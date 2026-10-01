"""Tests for the pattern retirement endpoints.

    POST /sessions/{id}/patterns/retire
    POST /sessions/{id}/patterns/un-retire

Retirement hides a learned pattern from every read path without deleting it. The
properties worth pinning are the ones that are easy to get subtly wrong: that the
tombstone reaches *every* path a pattern can surface on, that it is scoped to the
node rather than the session, that it is reversible, and that re-learning the same
sequence does not quietly resurrect it.

These are API-level: the ported branch arrived with eight unit test files and no
request-level coverage at all, so nothing exercised the endpoints, the status
codes, or the interaction between a tombstone and a stored prediction snapshot.
"""

import os
import sys
import uuid

import requests

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

VALID_HASH = 'a' * 40


def _base_url():
    return os.environ.get("KATO_BASE_URL", "http://localhost:8000")


def _create_session(node_id=None, ttl=120):
    """A session on a test-prefixed node, so its corpus is reclaimable."""
    if node_id is None:
        node_id = f"test_retire_{uuid.uuid4().hex[:8]}"
    resp = requests.post(f"{_base_url()}/sessions", json={
        "node_id": node_id, "config": {}, "metadata": {}, "ttl_seconds": ttl,
    }, timeout=15)
    resp.raise_for_status()
    return resp.json()["session_id"], node_id


def _learn(session_id, head, tail):
    """Learn a two-event pattern and return its name."""
    base = _base_url()
    for token in (head, tail):
        requests.post(f"{base}/sessions/{session_id}/observe",
                      json={"strings": [token]}, timeout=20).raise_for_status()
    name = requests.post(f"{base}/sessions/{session_id}/learn",
                         json={}, timeout=20).json()["pattern_name"]
    requests.post(f"{base}/sessions/{session_id}/clear-stm", json={}, timeout=15)
    return name


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


def _un_retire(session_id, pattern_ids):
    return requests.post(f"{_base_url()}/sessions/{session_id}/patterns/un-retire",
                         json={"pattern_ids": pattern_ids}, timeout=20)


def test_retire_hides_pattern_from_predictions():
    """The basic contract, and the response shape callers depend on."""
    session_id, _ = _create_session()
    name = _learn(session_id, "ret_head", "ret_tail")

    assert len(_predictions_for(session_id, "ret_head")) > 0, "should predict before retiring"

    resp = _retire(session_id, [name])
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "okay"
    assert body["requested"] == 1
    assert len(body["retired"]) == 1
    assert body["already_retired"] == []
    # Reported without the PTRN| prefix, as stored.
    assert not body["retired"][0].startswith("PTRN|")

    assert _predictions_for(session_id, "ret_head") == [], "retired pattern should be hidden"

    requests.delete(f"{_base_url()}/sessions/{session_id}", timeout=10)


def test_retire_is_idempotent():
    """A repeated retire reports already_retired rather than retired.

    HSETNX rather than HSET, so a caller re-sending a batch can tell which ids it
    actually changed instead of having the state silently reset.
    """
    session_id, _ = _create_session()
    name = _learn(session_id, "idem_head", "idem_tail")

    first = _retire(session_id, [name]).json()
    second = _retire(session_id, [name]).json()

    assert len(first["retired"]) == 1 and first["already_retired"] == []
    assert second["retired"] == [] and len(second["already_retired"]) == 1

    requests.delete(f"{_base_url()}/sessions/{session_id}", timeout=10)


def test_retirement_applies_to_cognition_data_too():
    """A tombstone must reach every path a pattern can surface on.

    cognition-data serves session.predictions, a snapshot captured at observe
    time, which can predate the retirement. Serving it unfiltered would surface a
    pattern the caller has already retired, on one endpoint but not another.
    """
    base = _base_url()
    session_id, _ = _create_session()
    name = _learn(session_id, "cog_head", "cog_tail")
    _retire(session_id, [name])

    requests.post(f"{base}/sessions/{session_id}/clear-stm", json={}, timeout=15)
    requests.post(f"{base}/sessions/{session_id}/observe",
                  json={"strings": ["cog_head"]}, timeout=20)
    cognition = requests.get(f"{base}/sessions/{session_id}/cognition-data",
                             timeout=20).json()

    assert cognition.get("predictions", []) == [], \
        "retired pattern leaked through cognition-data"

    requests.delete(f"{base}/sessions/{session_id}", timeout=10)


def test_retirement_is_node_scoped_not_session_scoped():
    """Tombstones belong to the node, like the learned patterns they hide.

    Two sessions on one node_id share long-term memory, so a retire by one must be
    visible to the other. A session on a different node must be unaffected.
    """
    base = _base_url()
    shared_node = f"test_retire_shared_{uuid.uuid4().hex[:8]}"
    session_a, _ = _create_session(node_id=shared_node)
    session_b, _ = _create_session(node_id=shared_node)
    session_other, _ = _create_session()

    name = _learn(session_a, "node_head", "node_tail")
    # The sibling session sees the shared pattern before any retirement.
    assert len(_predictions_for(session_b, "node_head")) > 0

    # An independent node learns the same sequence; same symbols, its own corpus.
    _learn(session_other, "node_head", "node_tail")
    assert len(_predictions_for(session_other, "node_head")) > 0

    _retire(session_a, [name])

    assert _predictions_for(session_b, "node_head") == [], \
        "a sibling session on the same node should see the retirement"
    assert len(_predictions_for(session_other, "node_head")) > 0, \
        "a different node must not be affected"

    for sid in (session_a, session_b, session_other):
        requests.delete(f"{base}/sessions/{sid}", timeout=10)


def test_other_patterns_are_untouched():
    """Retirement is subtractive and targeted, not a blanket filter."""
    session_id, _ = _create_session()
    doomed = _learn(session_id, "keep_a_head", "keep_a_tail")
    _learn(session_id, "keep_b_head", "keep_b_tail")

    _retire(session_id, [doomed])

    assert _predictions_for(session_id, "keep_a_head") == []
    assert len(_predictions_for(session_id, "keep_b_head")) > 0

    requests.delete(f"{_base_url()}/sessions/{session_id}", timeout=10)


def test_relearning_a_retired_pattern_is_a_conflict():
    """409, not 500, and not a silent resurrection.

    A pattern's identity is the SHA1 of its data, so re-observing the sequence
    produces the same hash. Without the guard the pattern would come back and
    retirement could be undone by accident. With it, the condition is the caller's
    to resolve -- hence a conflict carrying the un-retire hint, rather than an
    opaque server error.
    """
    base = _base_url()
    session_id, _ = _create_session()
    name = _learn(session_id, "conf_head", "conf_tail")
    _retire(session_id, [name])

    requests.post(f"{base}/sessions/{session_id}/clear-stm", json={}, timeout=15)
    for token in ("conf_head", "conf_tail"):
        requests.post(f"{base}/sessions/{session_id}/observe",
                      json={"strings": [token]}, timeout=20)
    resp = requests.post(f"{base}/sessions/{session_id}/learn", json={}, timeout=20)

    assert resp.status_code == 409, f"expected 409 Conflict, got {resp.status_code}: {resp.text}"
    error = resp.json()["error"]
    assert error["code"] == "RETIRED_PATTERN"
    assert error["recoverable"] is True
    assert "un-retire" in error["message"].lower()

    requests.delete(f"{base}/sessions/{session_id}", timeout=10)


def test_un_retire_restores_visibility_and_learnability():
    """Retirement has to be reversible.

    Nothing else removes a tombstone, and the learn-side guard refuses a
    tombstoned hash, so without this one mistaken retire would permanently prevent
    the sequence from being learned on the node.
    """
    base = _base_url()
    session_id, _ = _create_session()
    name = _learn(session_id, "undo_head", "undo_tail")
    _retire(session_id, [name])
    assert _predictions_for(session_id, "undo_head") == []

    resp = _un_retire(session_id, [name])
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["un_retired"]) == 1
    assert body["not_retired"] == []

    assert len(_predictions_for(session_id, "undo_head")) > 0, "should be visible again"

    # And learnable again, which is the half a visibility check alone would miss.
    requests.post(f"{base}/sessions/{session_id}/clear-stm", json={}, timeout=15)
    for token in ("undo_head", "undo_tail"):
        requests.post(f"{base}/sessions/{session_id}/observe",
                      json={"strings": [token]}, timeout=20)
    assert requests.post(f"{base}/sessions/{session_id}/learn",
                         json={}, timeout=20).status_code == 200

    requests.delete(f"{base}/sessions/{session_id}", timeout=10)


def test_un_retire_of_a_live_pattern_is_a_no_op():
    """Reported as not_retired rather than invented as a change."""
    session_id, _ = _create_session()
    name = _learn(session_id, "noop_head", "noop_tail")

    body = _un_retire(session_id, [name]).json()
    assert body["un_retired"] == []
    assert len(body["not_retired"]) == 1

    assert len(_predictions_for(session_id, "noop_head")) > 0

    requests.delete(f"{_base_url()}/sessions/{session_id}", timeout=10)


def test_prefixed_and_bare_hashes_are_both_accepted():
    """Callers see PTRN|-prefixed names in prediction output but the databases
    store the bare hash, so both forms have to work."""
    session_id, _ = _create_session()
    name = _learn(session_id, "pfx_head", "pfx_tail")
    bare = name[5:] if name.startswith("PTRN|") else name

    assert len(_retire(session_id, [f"PTRN|{bare}"]).json()["retired"]) == 1
    assert _predictions_for(session_id, "pfx_head") == []
    assert len(_un_retire(session_id, [bare]).json()["un_retired"]) == 1
    assert len(_predictions_for(session_id, "pfx_head")) > 0

    requests.delete(f"{_base_url()}/sessions/{session_id}", timeout=10)


def test_malformed_pattern_ids_are_rejected():
    """Rejected at the edge, because a tombstone is durable and unmatched.

    An id that is not a real pattern hash can never match anything, so it would
    sit in the registry indefinitely, indistinguishable from a real retirement.
    """
    session_id, _ = _create_session()

    for bad in (["abc"],                   # too short
                ["A" * 40],                # uppercase; uuid4().hex is lowercase
                ["a" * 39],                # off by one
                ["a" * 41],                # off by one the other way
                ["PTRN|"],                 # prefix with nothing after it
                [""],                      # empty
                ["  "],                    # whitespace only
                ["g" * 40]):               # right length, not hex
        resp = _retire(session_id, bad)
        assert resp.status_code == 422, f"{bad!r} should be rejected, got {resp.status_code}"

    requests.delete(f"{_base_url()}/sessions/{session_id}", timeout=10)


def test_batch_bounds_are_enforced():
    """1 to 1000 ids, so neither an empty call nor an unbounded one gets through."""
    session_id, _ = _create_session()

    assert _retire(session_id, []).status_code == 422
    assert _retire(session_id, [VALID_HASH] * 1001).status_code == 422
    # The upper bound itself is allowed.
    assert _retire(session_id, [VALID_HASH] * 1000).status_code == 200

    requests.delete(f"{_base_url()}/sessions/{session_id}", timeout=10)


def test_whitespace_around_an_id_is_stripped():
    """Otherwise the tombstone stores a padded key that never matches."""
    session_id, _ = _create_session()
    name = _learn(session_id, "strip_head", "strip_tail")
    bare = name[5:] if name.startswith("PTRN|") else name

    assert len(_retire(session_id, [f"  {bare}  "]).json()["retired"]) == 1
    assert _predictions_for(session_id, "strip_head") == [], \
        "a stripped id should have retired the real pattern"

    requests.delete(f"{_base_url()}/sessions/{session_id}", timeout=10)


def test_unknown_session_returns_404():
    """And a 404 rather than the 500 an unguarded session lock would produce."""
    for path in ("retire", "un-retire"):
        resp = requests.post(
            f"{_base_url()}/sessions/session-does-not-exist-{uuid.uuid4().hex}/patterns/{path}",
            json={"pattern_ids": [VALID_HASH]}, timeout=10)
        assert resp.status_code == 404, f"{path}: got {resp.status_code}"


def test_retiring_an_unknown_but_valid_hash_succeeds():
    """A well-formed hash that names no pattern is accepted.

    Retirement is a statement about a hash, not a lookup, and the registry is
    consulted before the pattern store on every read. Requiring the pattern to
    exist would make the endpoint racy against concurrent learning, and the
    tombstone is harmless and removable.
    """
    session_id, _ = _create_session()
    body = _retire(session_id, ["b" * 40]).json()
    assert len(body["retired"]) == 1
    # And it can be taken back out again.
    assert len(_un_retire(session_id, ["b" * 40]).json()["un_retired"]) == 1

    requests.delete(f"{_base_url()}/sessions/{session_id}", timeout=10)
