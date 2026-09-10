"""
Remove test-created session state from a shared Redis without touching live clients.

The test suite runs against whatever Redis the stack points at, which is
frequently shared with live workloads (a training notebook, the dashboard,
other people's test runs). Session keys carry the session's node_id, and
every node the suite creates is named with a recognisable prefix, so cleanup
can be selective: a session is deleted only if its node_id looks test-created.
Everything else - live sessions, their node pointers, their STM streams,
and the shared stm:global stream - is left exactly as it was.

Key shapes (RedisSessionManager, kato/sessions/redis_session_manager.py):
    kato:session:session-<id>        JSON blob with "node_id"
    kato:session:node:<node_id>:active  pointer to that node's active session
    kato:session:_active_index       SET of live session ids
Distributed STM (kato/storage/redis_streams.py):
    stm:events:<processor_id>        per-processor stream; processor_id = "<node_id>_<service>"
    stm:global                       shared - never deleted here
"""

import json
import os

SESSION_PREFIX = "kato:session:"
SESSION_KEY_PATTERN = f"{SESSION_PREFIX}session-*"
NODE_POINTER_PATTERN = f"{SESSION_PREFIX}node:*:active"
ACTIVE_INDEX_KEY = f"{SESSION_PREFIX}_active_index"
STM_STREAM_PATTERN = "stm:events:*"

# node_id prefixes the suite uses for the nodes it creates. Override with a
# comma-separated KATO_TEST_NODE_PREFIXES. Deliberately NOT "node": production
# nodes are named node0..node3.
DEFAULT_TEST_NODE_PREFIXES = ("test", "topology_", "perf_", "load_test")


def test_node_prefixes() -> tuple[str, ...]:
    raw = os.environ.get("KATO_TEST_NODE_PREFIXES")
    if raw:
        return tuple(p.strip() for p in raw.split(",") if p.strip())
    return DEFAULT_TEST_NODE_PREFIXES


def is_test_node(node_id: str, prefixes: tuple[str, ...] | None = None) -> bool:
    return bool(node_id) and node_id.startswith(prefixes or test_node_prefixes())


def _delete_in_batches(client, keys: list[str], batch: int = 1000) -> int:
    deleted = 0
    for i in range(0, len(keys), batch):
        deleted += client.delete(*keys[i:i + batch])
    return deleted


def clear_test_session_state(client, prefixes: tuple[str, ...] | None = None) -> dict:
    """Delete session records, node pointers and STM streams that belong to test nodes.

    Returns counts: sessions_deleted, sessions_kept, pointers_deleted,
    streams_deleted, index_removed.
    """
    prefixes = prefixes or test_node_prefixes()

    # Session blobs: read node_id from each record, keep the ones that aren't ours.
    session_keys = list(client.scan_iter(match=SESSION_KEY_PATTERN, count=1000))
    doomed_keys: list[str] = []
    doomed_ids: list[str] = []
    kept = 0
    for i in range(0, len(session_keys), 500):
        chunk = session_keys[i:i + 500]
        pipe = client.pipeline(transaction=False)
        for key in chunk:
            pipe.get(key)
        for key, raw in zip(chunk, pipe.execute()):
            try:
                node_id = json.loads(raw).get("node_id", "") if raw else ""
            except (TypeError, ValueError):
                node_id = ""  # unreadable: leave it alone
            if is_test_node(node_id, prefixes):
                doomed_keys.append(key)
                doomed_ids.append(key[len(SESSION_PREFIX):])
            else:
                kept += 1

    # Per-node active-session pointers for test nodes.
    pointer_keys = [
        key for key in client.scan_iter(match=NODE_POINTER_PATTERN, count=1000)
        if is_test_node(key[len(SESSION_PREFIX) + len("node:"):-len(":active")], prefixes)
    ]

    # Distributed STM streams for test processors (processor_id starts with the node_id).
    stream_keys = [
        key for key in client.scan_iter(match=STM_STREAM_PATTERN, count=1000)
        if is_test_node(key[len("stm:events:"):], prefixes)
    ]

    sessions_deleted = _delete_in_batches(client, doomed_keys)
    pointers_deleted = _delete_in_batches(client, pointer_keys)
    streams_deleted = _delete_in_batches(client, stream_keys)
    index_removed = 0
    for i in range(0, len(doomed_ids), 1000):
        index_removed += client.srem(ACTIVE_INDEX_KEY, *doomed_ids[i:i + 1000])

    return {
        "sessions_deleted": sessions_deleted,
        "sessions_kept": kept,
        "pointers_deleted": pointers_deleted,
        "streams_deleted": streams_deleted,
        "index_removed": index_removed,
    }
