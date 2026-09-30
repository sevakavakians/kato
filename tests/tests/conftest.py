"""
Shared pytest fixtures for KATO tests.
"""

import asyncio
import contextlib
import os
import uuid

import pytest
import pytest_asyncio
import redis
from fixtures.kato_session_client import KatoSessionClient
from fixtures.redis_test_cleanup import clear_test_session_state, test_node_prefixes
from fixtures.store_test_cleanup import purge_test_patterns


@pytest.fixture(scope="session", autouse=True)
def flush_redis_before_tests():
    """Clear stale test-created session state from Redis before the test session.

    Deletes only sessions (plus their node pointers, active-index entries and
    distributed-STM streams) whose node_id carries a test prefix - see
    fixtures/redis_test_cleanup.py. Sessions belonging to live clients on the
    same Redis are left untouched, so running the suite next to a training
    notebook, or two suites at once, no longer destroys their sessions.

    Also purges learned patterns from earlier runs. Sessions are transient but
    patterns are durable by design, so nothing used to remove them and a shared
    stack accumulated them without limit - 16,821 patterns on the stack examined
    while this was written, mostly from `stress_200_*` runs long since finished.
    Corpus size feeds total_unique_patterns, the symbol statistics behind
    prediction metrics, and the number of candidates reaching the filter
    pipeline, so the pile made the suite progressively slower and its
    timing-sensitive tests less reproducible. Only kb_ids carrying a test node
    prefix are dropped; see fixtures/store_test_cleanup.py. Set
    KATO_TEST_KEEP_PATTERNS=1 to keep them.

    History: this fixture once ran FLUSHALL (destroying durable pattern
    metadata for every kb_id), then deleted every kato:session:* key
    (destroying every live session). Set KATO_TEST_REDIS_FLUSHALL=1 to opt
    back into a full FLUSHALL - only against a Redis dedicated to testing.
    """
    host = os.environ.get("REDIS_HOST", "localhost")
    port = int(os.environ.get("REDIS_PORT", "6379"))

    try:
        client = redis.Redis(host=host, port=port, decode_responses=True)

        if os.environ.get("KATO_TEST_REDIS_FLUSHALL") == "1":
            client.flushall()
            print("\n⚠ Redis FLUSHALL (KATO_TEST_REDIS_FLUSHALL=1) - all keys destroyed")
        else:
            counts = clear_test_session_state(client)
            print(f"\n✓ Cleared {counts['sessions_deleted']} stale test sessions "
                  f"(node prefixes {', '.join(test_node_prefixes())}); "
                  f"left {counts['sessions_kept']} live session(s) untouched")
    except Exception as e:
        # Redis may not be running for some tests, which is okay.
        print(f"\n⚠ Warning: Could not clear Redis session state: {e}")
        client = None

    if os.environ.get("KATO_TEST_KEEP_PATTERNS") == "1":
        print("✓ Keeping learned patterns from earlier runs (KATO_TEST_KEEP_PATTERNS=1)")
    else:
        # Never raises; a cleanup that cannot run must not fail the suite.
        purged = purge_test_patterns(redis_client=client)
        if purged["kb_ids"]:
            print(f"✓ Purged learned patterns from {purged['kb_ids']} stale test kb_id(s): "
                  f"{purged['partitions_dropped']} ClickHouse partition(s), "
                  f"{purged['redis_keys_deleted']} Redis key(s)"
                  + (f", {purged['failures']} failure(s)" if purged["failures"] else ""))
        else:
            print("✓ No stale test patterns to purge")
    yield


@pytest_asyncio.fixture
async def kato_client():
    """Fixture that provides an async KATO session client."""
    # Use single KATO instance on port 8000
    base_url = "http://localhost:8000"

    # Create and yield the client
    async with KatoSessionClient(base_url) as client:
        yield client


@pytest_asyncio.fixture
async def isolated_session(kato_client):
    """Fixture that creates an isolated session for testing."""
    # Create a unique session for this test
    test_id = str(uuid.uuid4())[:8]
    session = await kato_client.create_session(
        node_id=f"test_node_{test_id}",
        ttl_seconds=60,  # Short TTL for tests
        metadata={"test": True, "test_id": test_id}
    )

    # Yield the session for the test to use
    yield session

    # Cleanup: Try to delete the session
    with contextlib.suppress(Exception):
        await kato_client.delete_session(session["session_id"])


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
