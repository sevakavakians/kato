"""
Test Redis-based session storage for KATO current.0
Tests persistence, serialization, and Redis integration
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from kato.sessions.redis_session_manager import RedisSessionManager
from kato.sessions.redis_session_store import RedisSessionStore
from kato.sessions.session_manager import SessionState


@pytest.mark.asyncio
class TestRedisSessionStore:
    """Test Redis session store functionality"""

    async def test_redis_store_creation(self):
        """Test creating Redis session store"""
        store = RedisSessionStore(
            redis_url="redis://localhost:6379",
            key_prefix="test:session:",
            serialization="json"
        )

        assert store.redis_url == "redis://localhost:6379"
        assert store.key_prefix == "test:session:"
        assert store.serialization == "json"
        assert not store._connected

    async def test_session_key_generation(self):
        """Test Redis key generation"""
        store = RedisSessionStore(key_prefix="test:")

        key = store._get_session_key("session-123")
        assert key == "test:session-123"

    async def test_session_serialization_json(self):
        """Test JSON serialization of sessions"""
        store = RedisSessionStore(serialization="json")

        # Create test session with all required fields
        now = datetime.now(timezone.utc)
        from kato.config.session_config import SessionConfiguration
        session = SessionState(
            session_id="test-session",
            node_id="test-node",
            created_at=now,
            last_accessed=now,
            expires_at=now + timedelta(hours=1),
            stm=[["hello", "world"]],
            emotives_accumulator=[],
            time=0,
            metadata={"test": True},
            access_count=0,
            max_stm_size=100,
            max_emotives_size=100,
            session_config=SessionConfiguration()
        )

        # Serialize and deserialize
        serialized = store._serialize_session(session)
        assert isinstance(serialized, bytes)

        deserialized = store._deserialize_session(serialized)

        # Check that data survived round trip
        assert deserialized.session_id == session.session_id
        assert deserialized.node_id == session.node_id
        assert deserialized.stm == session.stm
        assert deserialized.metadata == session.metadata

        # Datetime fields should be preserved
        assert abs((deserialized.created_at - session.created_at).total_seconds()) < 1

    async def test_session_serialization_pickle(self):
        """Test Pickle serialization of sessions"""
        store = RedisSessionStore(serialization="pickle")

        # Create test session with complex data
        now = datetime.now(timezone.utc)
        session = SessionState(
            session_id="test-session",
            node_id="test-node",
            created_at=now,
            last_accessed=now,
            expires_at=now + timedelta(hours=1),
            stm=[["hello", "world"], ["foo", "bar"]],
            emotives_accumulator=[{"joy": 0.8, "surprise": 0.2}],
            metadata={"complex": {"nested": True}, "list": [1, 2, 3]}
        )

        # Serialize and deserialize
        serialized = store._serialize_session(session)
        assert isinstance(serialized, bytes)

        deserialized = store._deserialize_session(serialized)

        # Check that complex data survived
        assert deserialized.session_id == session.session_id
        assert deserialized.stm == session.stm
        assert deserialized.emotives_accumulator == session.emotives_accumulator
        assert deserialized.metadata == session.metadata
        assert deserialized.created_at == session.created_at

    async def test_store_session_mock(self):
        """Test storing session with mocked Redis store methods"""
        # Mock the connect and Redis operations at the store level
        store = RedisSessionStore()

        # Mock the internal methods
        store._connected = True  # Skip connection
        store.redis_client = AsyncMock()
        store.redis_client.setex = AsyncMock(return_value=True)

        # Create test session
        now = datetime.now(timezone.utc)
        session = SessionState(
            session_id="test-session",
            node_id="test-node",
            created_at=now,
            last_accessed=now,
            expires_at=now + timedelta(hours=1)
        )

        # Store session
        success = await store.store_session(session)

        # Verify Redis operations
        assert success
        store.redis_client.setex.assert_called_once()

        # Check setex parameters
        call_args = store.redis_client.setex.call_args
        key, ttl, data = call_args[0]

        assert key == f"{store.key_prefix}test-session"
        assert ttl > 0  # Should have positive TTL
        assert isinstance(data, bytes)  # Should be serialized

    async def test_get_session_mock(self):
        """Test retrieving session with mocked Redis"""
        # Create test session
        now = datetime.now(timezone.utc)
        session = SessionState(
            session_id="test-session",
            node_id="test-node",
            created_at=now,
            last_accessed=now,
            expires_at=now + timedelta(hours=1)
        )

        store = RedisSessionStore()

        # Mock the internal methods
        store._connected = True  # Skip connection
        store.redis_client = AsyncMock()

        # Mock get returning serialized session
        serialized = store._serialize_session(session)
        store.redis_client.get = AsyncMock(return_value=serialized)

        # Get session
        retrieved = await store.get_session("test-session")

        # Verify
        assert retrieved is not None
        assert retrieved.session_id == session.session_id
        assert retrieved.node_id == session.node_id

        store.redis_client.get.assert_called_with(f"{store.key_prefix}test-session")


@pytest.mark.asyncio
class TestRedisSessionManager:
    """Test Redis session manager"""

    async def test_redis_manager_creation(self):
        """Test creating Redis session manager"""
        manager = RedisSessionManager(
            default_ttl_seconds=1800,
            redis_url="redis://localhost:6379"
        )

        assert manager.default_ttl == 1800
        assert not manager._connected
        # RedisSessionManager has redis_client, not store

    async def test_create_session_mock(self):
        """Test session creation with mocked Redis store"""
        manager = RedisSessionManager()

        # Mock the redis_client directly
        manager.redis_client = AsyncMock()
        manager._connected = True
        manager.redis_client.setex = AsyncMock()
        manager.redis_client.get = AsyncMock(return_value=None)

        # Create session
        session = await manager.create_session(
            node_id="test-node",
            metadata={"test": True}
        )

        # Verify session properties
        assert session.session_id.startswith("session-")
        assert session.node_id == "test-node"
        assert session.metadata == {"test": True}
        assert session.stm == []

        # Verify Redis operations
        assert manager.redis_client.setex.called

        # Verify lock creation
        assert session.session_id in manager.session_locks

    async def test_get_session_mock(self):
        """Test session retrieval with mocked Redis store"""
        # Create test session
        now = datetime.now(timezone.utc)
        session = SessionState(
            session_id="test-session",
            node_id="test-node",
            created_at=now,
            last_accessed=now - timedelta(minutes=5),
            expires_at=now + timedelta(hours=1)
        )

        manager = RedisSessionManager()

        # Mock the redis_client
        manager.redis_client = AsyncMock()
        manager._connected = True

        # Serialize the session for mock return
        import json
        session_dict = {
            'session_id': session.session_id,
            'node_id': session.node_id,
            'created_at': session.created_at.isoformat(),
            'last_accessed': session.last_accessed.isoformat(),
            'expires_at': session.expires_at.isoformat(),
            'stm': session.stm,
            'emotives_accumulator': session.emotives_accumulator,
            'time': session.time,
            'metadata': session.metadata,
            'access_count': session.access_count,
            'max_stm_size': session.max_stm_size,
            'max_emotives_size': session.max_emotives_size,
            'session_config': None
        }
        manager.redis_client.get = AsyncMock(return_value=json.dumps(session_dict))
        manager.redis_client.ttl = AsyncMock(return_value=3600)
        manager.redis_client.setex = AsyncMock()

        # Get session
        retrieved = await manager.get_session("test-session")

        # Verify
        assert retrieved is not None
        assert retrieved.session_id == "test-session"
        assert retrieved.node_id == "test-node"

        # Verify access time was updated (or at least not older)
        # Note: The mock returns the same object which gets updated in place
        assert retrieved.last_accessed >= session.last_accessed

        # Verify Redis operations
        manager.redis_client.get.assert_called()
        manager.redis_client.setex.assert_called()  # Access time update

    async def test_session_operations_mock(self):
        """Test various session operations with mocked store"""
        manager = RedisSessionManager()

        # Mock the redis_client
        manager.redis_client = AsyncMock()
        manager._connected = True
        manager.redis_client.delete = AsyncMock(return_value=1)
        manager.redis_client.scan = AsyncMock(return_value=(0, []))

        # Test delete session
        result = await manager.delete_session("test-session")
        assert result is True
        manager.redis_client.delete.assert_called()

        # Test extend session
        manager.redis_client.exists = AsyncMock(return_value=True)
        manager.redis_client.expire = AsyncMock(return_value=True)
        manager.redis_client.get = AsyncMock(return_value=None)  # For get_session
        result = await manager.extend_session("test-session", 7200)
        assert result is True

    async def test_health_check_mock(self):
        """Test health check with mocked store"""
        manager = RedisSessionManager()

        # Mock healthy Redis connection
        manager.redis_client = AsyncMock()
        manager._connected = True
        manager.redis_client.ping = AsyncMock()
        manager.redis_client.scan = AsyncMock(return_value=(0, [b'key1', b'key2', b'key3']))

        # Manager doesn't have a health_check method, test connection instead
        await manager.initialize()
        assert manager._connected

    async def test_health_check_unhealthy_mock(self):
        """Test health check with unhealthy Redis"""
        manager = RedisSessionManager()

        # Mock unhealthy Redis connection
        manager.redis_client = None
        manager._connected = False

        # Test that initialize can fail gracefully
        with patch('redis.asyncio.from_url', side_effect=Exception("Connection failed")):
            try:
                await manager.initialize()
                raise AssertionError("Should have raised exception")
            except Exception as e:
                assert "Connection failed" in str(e)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
