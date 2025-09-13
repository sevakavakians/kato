"""
Pytest configuration and fixtures for KATO v2.0 tests.
Provides session-aware fixtures for testing v2 features.
"""

import asyncio
import aiohttp
import pytest
import pytest_asyncio
import uuid
import time
from typing import Dict, Any, Optional, List


class KatoV2Client:
    """Client for testing KATO v2.0 session endpoints"""
    
    def __init__(self, base_url: str = "http://localhost:8001"):
        self.base_url = base_url
        self.session = None
        
    async def __aenter__(self):
        """Async context manager entry"""
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30)
        )
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.session:
            await self.session.close()
    
    async def create_session(self, user_id: str = None, metadata: Dict = None, 
                           ttl_seconds: int = 3600) -> Dict:
        """Create a new session"""
        # user_id is required for v2
        if not user_id:
            user_id = f"test_user_{uuid.uuid4().hex[:8]}"
        
        payload = {"user_id": user_id}
        if metadata:
            payload["metadata"] = metadata
        if ttl_seconds != 3600:
            payload["ttl_seconds"] = ttl_seconds
            
        async with self.session.post(
            f"{self.base_url}/v2/sessions",
            json=payload
        ) as response:
            if response.status == 404:
                pytest.skip("v2 session endpoints not available")
            response.raise_for_status()
            return await response.json()
    
    async def observe_in_session(self, session_id: str, observation: Dict) -> Dict:
        """Process observation in session context"""
        async with self.session.post(
            f"{self.base_url}/v2/sessions/{session_id}/observe",
            json=observation
        ) as response:
            if response.status == 404:
                raise SessionNotFoundError(f"Session {session_id} not found")
            response.raise_for_status()
            return await response.json()
    
    async def get_session_stm(self, session_id: str) -> Dict:
        """Get STM for session"""
        async with self.session.get(
            f"{self.base_url}/v2/sessions/{session_id}/stm"
        ) as response:
            if response.status == 404:
                raise SessionNotFoundError(f"Session {session_id} not found")
            response.raise_for_status()
            return await response.json()
    
    async def delete_session(self, session_id: str) -> None:
        """Delete session"""
        async with self.session.delete(
            f"{self.base_url}/v2/sessions/{session_id}"
        ) as response:
            if response.status != 404:  # OK if already deleted
                response.raise_for_status()
    
    async def clear_session_stm(self, session_id: str) -> None:
        """Clear STM in session"""
        async with self.session.post(
            f"{self.base_url}/v2/sessions/{session_id}/clear-stm"
        ) as response:
            if response.status == 404:
                raise SessionNotFoundError(f"Session {session_id} not found")
            response.raise_for_status()
    
    async def learn_in_session(self, session_id: str) -> Dict:
        """Learn pattern from session STM"""
        async with self.session.post(
            f"{self.base_url}/v2/sessions/{session_id}/learn"
        ) as response:
            if response.status == 404:
                raise SessionNotFoundError(f"Session {session_id} not found")
            response.raise_for_status()
            return await response.json()
    
    async def get_session_predictions(self, session_id: str) -> Dict:
        """Get predictions for session"""
        async with self.session.get(
            f"{self.base_url}/v2/sessions/{session_id}/predictions"
        ) as response:
            if response.status == 404:
                raise SessionNotFoundError(f"Session {session_id} not found")
            response.raise_for_status()
            return await response.json()
    
    async def get_active_session_count(self) -> int:
        """Get count of active sessions"""
        async with self.session.get(
            f"{self.base_url}/v2/health"
        ) as response:
            response.raise_for_status()
            health_data = await response.json()
            return health_data.get("active_sessions", 0)
    
    async def extend_session(self, session_id: str, ttl_seconds: int) -> None:
        """Extend session TTL"""
        async with self.session.put(
            f"{self.base_url}/v2/sessions/{session_id}/extend",
            json={"ttl_seconds": ttl_seconds}
        ) as response:
            if response.status == 404:
                raise SessionNotFoundError(f"Session {session_id} not found")
            response.raise_for_status()
    
    # V1 compatibility methods removed - v2 session-based APIs only
    
    async def check_service_health(self) -> bool:
        """Check if v2 service is available"""
        try:
            async with self.session.get(
                f"{self.base_url}/v2/health"
            ) as response:
                return response.status == 200
        except:
            return False


class SessionNotFoundError(Exception):
    """Raised when session is not found"""
    pass


@pytest_asyncio.fixture
async def kato_v2_client():
    """Fixture providing KATO v2 client for testing"""
    # Try different service ports
    client = None
    for port in [8001, 8002, 8003]:
        base_url = f"http://localhost:{port}"
        test_client = KatoV2Client(base_url)
        await test_client.__aenter__()
        
        try:
            if await test_client.check_service_health():
                client = test_client
                break
        except:
            await test_client.__aexit__(None, None, None)
    
    if client is None:
        # If no service found, skip test
        pytest.skip("No KATO v2.0 services available. Start with: ./start_v2.sh")
    
    try:
        yield client
    finally:
        await client.__aexit__(None, None, None)


@pytest_asyncio.fixture
async def kato_v2_system(kato_v2_client):
    """Alias for kato_v2_client to support multi-user test scenarios"""
    # For now, just pass through the client
    # In future this could add system-level functionality
    return kato_v2_client


@pytest.fixture
def test_session_id():
    """Generate unique session ID for test isolation"""
    timestamp = int(time.time() * 1000)
    unique = str(uuid.uuid4())[:8]
    return f"test_session_{timestamp}_{unique}"


@pytest_asyncio.fixture
async def isolated_session(kato_v2_client, test_session_id):
    """Create an isolated test session and clean up afterwards"""
    session = await kato_v2_client.create_session(
        user_id=f"test_user_{test_session_id}",
        metadata={"test": True, "session_type": "isolated_test"}
    )
    
    yield session
    
    # Cleanup
    try:
        await kato_v2_client.delete_session(session["session_id"])
    except:
        pass  # Session might already be expired/deleted


@pytest_asyncio.fixture
async def multiple_sessions(kato_v2_client):
    """Create multiple test sessions for concurrent testing"""
    sessions = []
    
    for i in range(5):
        session = await kato_v2_client.create_session(
            user_id=f"multi_test_user_{i}",
            metadata={"test": True, "session_type": "multi_test", "index": i}
        )
        sessions.append(session)
    
    yield sessions
    
    # Cleanup
    cleanup_tasks = []
    for session in sessions:
        try:
            cleanup_tasks.append(
                kato_v2_client.delete_session(session["session_id"])
            )
        except:
            pass
    
    if cleanup_tasks:
        await asyncio.gather(*cleanup_tasks, return_exceptions=True)


# Configuration for async tests
def pytest_configure(config):
    """Configure pytest for async tests"""
    config.addinivalue_line(
        "markers", "asyncio: mark test to run with asyncio"
    )
    config.addinivalue_line(
        "markers", "integration: mark test as integration test"
    )
    config.addinivalue_line(
        "markers", "performance: mark test as performance test"
    )
    config.addinivalue_line(
        "markers", "stress: mark test as stress test"
    )
    config.addinivalue_line(
        "markers", "chaos: mark test as chaos engineering test"
    )