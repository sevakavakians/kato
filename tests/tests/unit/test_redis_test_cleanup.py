"""
The suite's Redis cleanup must remove test-created session state and nothing else.
"""

import json
import os
import sys
import uuid

import pytest
import redis

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from fixtures.redis_test_cleanup import (  # noqa: E402
    ACTIVE_INDEX_KEY,
    SESSION_PREFIX,
    clear_test_session_state,
    is_test_node,
)

REDIS_URL = os.environ.get("KATO_TEST_REDIS_URL", "redis://localhost:6379/0")


@pytest.mark.parametrize("node_id,expected", [
    ("test_node_ab12", True), ("test_learn_endpoint_1_x_y", True), ("test", True),
    ("topology_interleave_1", True), ("perf_4w_deadbeef", True), ("load_test_node_3", True),
    ("node0", False), ("node3", False), ("prod_customer_42", False), ("", False), ("testing_prod", True),
])
def test_is_test_node(node_id, expected):
    assert is_test_node(node_id) is expected


def test_cleanup_removes_only_test_sessions():
    r = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    tag = uuid.uuid4().hex[:8]
    live_id, test_id = f"session-live{tag}-1", f"session-test{tag}-1"
    live_node, test_node = f"prod_live_{tag}", f"test_cleanup_{tag}"
    keys = {
        f"{SESSION_PREFIX}{live_id}": json.dumps({"session_id": live_id, "node_id": live_node, "stm": []}),
        f"{SESSION_PREFIX}{test_id}": json.dumps({"session_id": test_id, "node_id": test_node, "stm": []}),
        f"{SESSION_PREFIX}node:{live_node}:active": live_id,
        f"{SESSION_PREFIX}node:{test_node}:active": test_id,
        f"stm:events:{live_node}_kato": "x",
        f"stm:events:{test_node}_kato": "x",
    }
    try:
        for k, v in keys.items():
            r.set(k, v, ex=120)
        r.sadd(ACTIVE_INDEX_KEY, live_id, test_id)
        had_global = r.exists("stm:global")

        counts = clear_test_session_state(r)

        assert counts["sessions_deleted"] >= 1 and counts["pointers_deleted"] >= 1 and counts["streams_deleted"] >= 1
        # test-created state is gone
        assert not r.exists(f"{SESSION_PREFIX}{test_id}")
        assert not r.exists(f"{SESSION_PREFIX}node:{test_node}:active")
        assert not r.exists(f"stm:events:{test_node}_kato")
        assert not r.sismember(ACTIVE_INDEX_KEY, test_id)
        # live state is untouched
        assert r.get(f"{SESSION_PREFIX}{live_id}") == keys[f"{SESSION_PREFIX}{live_id}"]
        assert r.get(f"{SESSION_PREFIX}node:{live_node}:active") == live_id
        assert r.exists(f"stm:events:{live_node}_kato")
        assert r.sismember(ACTIVE_INDEX_KEY, live_id)
        assert r.exists("stm:global") == had_global
    finally:
        r.delete(*keys.keys())
        r.srem(ACTIVE_INDEX_KEY, live_id, test_id)
