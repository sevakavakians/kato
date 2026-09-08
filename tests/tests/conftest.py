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

# Redis key namespaces that hold ephemeral session/STM state. Clearing these
# gives tests a clean slate; nothing durable lives here.
#   kato:session:*  - session records, active index, per-node active pointers
#                     (RedisSessionManager key_prefix, see redis_session_manager.py:47)
#   stm:events:*    - per-processor distributed STM streams (redis_streams.py:92)
#   stm:global      - global STM stream (redis_streams.py:93)
EPHEMERAL_KEY_PATTERNS = ("kato:session:*", "stm:events:*", "stm:global")

# Durable pattern metadata is always namespaced under the kb_id -
# "<kb_id>:frequency:*", ":symbols:freq", ":symbols:pmf", ":symbol_to_patterns:*",
# ":affinity:*", ":global:*", ":prediction:*" (see kato/storage/redis_writer.py).
# None of those can match the patterns above, so a scoped delete cannot touch them.


@pytest.fixture(scope="session", autouse=True)
def flush_redis_before_tests():
    """Clear stale session/STM state from Redis before the test session.

    This prevents old session data from previous test runs from
    interfering with current tests.

    Deliberately scoped: only the ephemeral namespaces in
    EPHEMERAL_KEY_PATTERNS are deleted. This fixture used to run FLUSHALL,
    which also destroyed durable pattern metadata (frequencies, symbol stats,
    affinities, global counters) for every kb_id in the instance - including
    live non-test data whenever tests point at a shared Redis. Pattern data
    itself survives in ClickHouse, but those Redis-only metrics are not
    recoverable (see scripts/rehydrate_redis.py limitations).

    Set KATO_TEST_REDIS_FLUSHALL=1 to opt back into a full FLUSHALL. Only do
    that against a Redis dedicated to testing.
    """
    host = os.environ.get("REDIS_HOST", "localhost")
    port = int(os.environ.get("REDIS_PORT", "6379"))

    try:
        client = redis.Redis(host=host, port=port, decode_responses=True)

        if os.environ.get("KATO_TEST_REDIS_FLUSHALL") == "1":
            client.flushall()
            print("\n⚠ Redis FLUSHALL (KATO_TEST_REDIS_FLUSHALL=1) - all keys destroyed")
        else:
            deleted = 0
            for pattern in EPHEMERAL_KEY_PATTERNS:
                batch = []
                for key in client.scan_iter(match=pattern, count=1000):
                    batch.append(key)
                    if len(batch) >= 1000:
                        deleted += client.delete(*batch)
                        batch = []
                if batch:
                    deleted += client.delete(*batch)
            print(f"\n✓ Cleared {deleted} stale session/STM Redis keys - clean test state ensured")
    except Exception as e:
        # Redis may not be running for some tests, which is okay.
        print(f"\n⚠ Warning: Could not clear Redis session state: {e}")
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
