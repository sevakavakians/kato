"""
Shared pytest fixtures for KATO tests.
"""

import pytest
import pytest_asyncio
import asyncio
import uuid
from typing import Dict, Any

from fixtures.kato_session_client import KatoSessionClient


@pytest_asyncio.fixture
async def kato_current_client():
    """Fixture that provides an async KATO session client."""
    # Use testing service if available, else primary
    base_url = "http://localhost:8002"  # Testing service
    
    # Check if testing service is available
    import aiohttp
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(f"{base_url}/health", timeout=aiohttp.ClientTimeout(total=0.5)) as resp:
                if resp.status != 200:
                    base_url = "http://localhost:8001"  # Fall back to primary
        except:
            base_url = "http://localhost:8001"  # Fall back to primary
    
    # Create and yield the client
    async with KatoSessionClient(base_url) as client:
        yield client


@pytest_asyncio.fixture
async def isolated_session(kato_current_client):
    """Fixture that creates an isolated session for testing."""
    # Create a unique session for this test
    test_id = str(uuid.uuid4())[:8]
    session = await kato_current_client.create_session(
        user_id=f"test_user_{test_id}",
        ttl_seconds=60,  # Short TTL for tests
        metadata={"test": True, "test_id": test_id}
    )
    
    # Yield the session for the test to use
    yield session
    
    # Cleanup: Try to delete the session
    try:
        await kato_current_client.delete_session(session["session_id"])
    except:
        pass  # Ignore cleanup errors


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()