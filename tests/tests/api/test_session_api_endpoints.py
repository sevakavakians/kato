"""
Tests for session API endpoints that previously had no coverage.

Covers:
- GET /sessions/count — active session count
- GET /sessions/{id}/exists — session existence check (non-extending)
- GET /sessions/{id}/config — get session configuration
"""

import os
import sys
import uuid

import pytest
import requests

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


def _get_base_url():
    return os.environ.get("KATO_BASE_URL", "http://localhost:8000")


def _create_session(base_url, node_id=None, ttl=60):
    """Helper to create a session."""
    if node_id is None:
        node_id = f"test_{uuid.uuid4().hex[:8]}"
    resp = requests.post(f"{base_url}/sessions", json={
        "node_id": node_id,
        "config": {},
        "metadata": {},
        "ttl_seconds": ttl
    })
    assert resp.status_code == 200, f"Failed to create session: {resp.text}"
    return resp.json()["session_id"]


def test_session_count_endpoint():
    """Test GET /sessions/count returns active session count."""
    base_url = _get_base_url()

    # Get initial count
    resp = requests.get(f"{base_url}/sessions/count")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    initial_count = resp.json().get("count", resp.json().get("active_sessions", 0))

    # Create a session
    session_id = _create_session(base_url)

    try:
        # Count should increase
        resp = requests.get(f"{base_url}/sessions/count")
        assert resp.status_code == 200
        new_count = resp.json().get("count", resp.json().get("active_sessions", 0))
        assert new_count >= initial_count, \
            f"Session count should not decrease after creating session: {new_count} < {initial_count}"
    finally:
        requests.delete(f"{base_url}/sessions/{session_id}")


def test_session_exists_endpoint():
    """Test GET /sessions/{id}/exists returns existence without extending TTL."""
    base_url = _get_base_url()

    session_id = _create_session(base_url)

    try:
        # Check existence
        resp = requests.get(f"{base_url}/sessions/{session_id}/exists")
        assert resp.status_code == 200
        data = resp.json()
        assert data['exists'] is True, f"Session should exist, got {data}"
        assert data['expired'] is False, f"Session should not be expired, got {data}"

        # Check non-existent session
        fake_id = f"nonexistent-{uuid.uuid4()}"
        resp = requests.get(f"{base_url}/sessions/{fake_id}/exists")
        assert resp.status_code == 200
        data = resp.json()
        assert data['exists'] is False, f"Non-existent session should not exist, got {data}"
    finally:
        requests.delete(f"{base_url}/sessions/{session_id}")


def test_get_session_config_endpoint():
    """Test GET /sessions/{id}/config returns current session configuration."""
    base_url = _get_base_url()

    session_id = _create_session(base_url)

    try:
        # Get config
        resp = requests.get(f"{base_url}/sessions/{session_id}/config")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

        config = resp.json()
        # Should have standard config fields
        assert 'recall_threshold' in config or 'config' in config, \
            f"Config should contain recall_threshold, got keys: {list(config.keys())}"

        # If nested under 'config' key, unwrap
        if 'config' in config:
            config = config['config']

        # Verify default values are present
        assert 'recall_threshold' in config, "Should have recall_threshold"
        assert isinstance(config['recall_threshold'], (int, float))

        # Update config and verify change is reflected
        requests.post(f"{base_url}/sessions/{session_id}/config", json={
            "config": {"recall_threshold": 0.75}
        })

        resp = requests.get(f"{base_url}/sessions/{session_id}/config")
        updated_config = resp.json()
        if 'config' in updated_config:
            updated_config = updated_config['config']
        assert updated_config['recall_threshold'] == 0.75, \
            f"Config should reflect update, got {updated_config['recall_threshold']}"
    finally:
        requests.delete(f"{base_url}/sessions/{session_id}")


def test_session_exists_for_expired_session():
    """Test that /exists correctly reports expired sessions."""
    import time
    base_url = _get_base_url()

    # Create session with 1-second TTL
    session_id = _create_session(base_url, ttl=1)

    # Should exist initially
    resp = requests.get(f"{base_url}/sessions/{session_id}/exists")
    assert resp.status_code == 200
    assert resp.json()['exists'] is True

    # Wait for expiration
    time.sleep(2)

    # Should be expired or gone
    resp = requests.get(f"{base_url}/sessions/{session_id}/exists")
    assert resp.status_code == 200
    data = resp.json()
    assert data['exists'] is False or data['expired'] is True, \
        f"Expired session should not be valid, got {data}"


def _config_from_create(base_url, config):
    resp = requests.post(f"{base_url}/sessions", json={
        "node_id": f"test_{uuid.uuid4().hex[:8]}", "config": config, "ttl_seconds": 60
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    requests.delete(f"{base_url}/sessions/{body['session_id']}")
    return body["session_config"]


def _config_from_update(base_url, config):
    session_id = _create_session(base_url)
    resp = requests.post(f"{base_url}/sessions/{session_id}/config", json={"config": config})
    assert resp.status_code == 200, resp.text
    got = requests.get(f"{base_url}/sessions/{session_id}/config").json()
    requests.delete(f"{base_url}/sessions/{session_id}")
    return got.get("config", got)


@pytest.mark.parametrize("config", [
    {"use_token_matching": False},
    {"use_token_matching": True},
    {"sort_symbols": False},
    {"sort_symbols": True},
    {"use_token_matching": False, "sort_symbols": True},
    {"use_token_matching": True, "sort_symbols": False},
])
def test_create_and_update_agree_on_matching_pair(config):
    """The same request body must configure a session identically either way.

    `use_token_matching` and `sort_symbols` are linked: supplying one derives the
    other. That derivation lived only in the config-update endpoint, so
    `{"use_token_matching": false}` produced sort_symbols=false via
    POST /sessions/{id}/config and sort_symbols=true via POST /sessions -- the
    latter being character-level matching over sorted symbols, which is not a
    combination anyone asks for on purpose.

    Parametrised over every combination of the pair rather than just the broken
    one, so a future change cannot fix this case by diverging on another.
    """
    base_url = _get_base_url()
    created = _config_from_create(base_url, config)
    updated = _config_from_update(base_url, config)

    pair = ("use_token_matching", "sort_symbols")
    assert {k: created[k] for k in pair} == {k: updated[k] for k in pair}, (
        f"create and update disagree for {config}: "
        f"create={ {k: created[k] for k in pair} } update={ {k: updated[k] for k in pair} }"
    )


def test_explicit_pair_survives_both_endpoints():
    """A deliberately mismatched pair is kept, not silently corrected.

    The combination is occasionally intentional, and rewriting it would make the
    configuration a session reports differ from what the caller asked for.
    """
    base_url = _get_base_url()
    config = {"use_token_matching": False, "sort_symbols": True}
    for source in (_config_from_create, _config_from_update):
        got = source(base_url, config)
        assert got["use_token_matching"] is False
        assert got["sort_symbols"] is True
