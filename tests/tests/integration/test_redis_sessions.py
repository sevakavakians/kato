"""
Test Redis-based session storage for KATO current.0
Tests persistence, serialization, and Redis integration
"""

import pytest
import asyncio
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch, AsyncMock

from kato.sessions.session_manager import SessionState
from kato.sessions.redis_session_store import RedisSessionStore
from kato.sessions.session_manager_redis import RedisSessionManager


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
        
        # Create test session
        now = datetime.now(timezone.utc)
        session = SessionState(
            session_id="test-session",
            user_id="test-user",
            created_at=now,
            last_accessed=now,
            expires_at=now + timedelta(hours=1),
            stm=[["hello", "world"]],
            metadata={"test": True}
        )
        
        # Serialize and deserialize
        serialized = store._serialize_session(session)
        assert isinstance(serialized, bytes)
        
        deserialized = store._deserialize_session(serialized)
        
        # Check that data survived round trip
        assert deserialized.session_id == session.session_id
        assert deserialized.user_id == session.user_id
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
            user_id="test-user",
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
            user_id="test-user",
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
            user_id="test-user",
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
        assert retrieved.user_id == session.user_id
        
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
        assert manager.store is not None
    
    @patch('kato.sessions.session_manager_redis.get_redis_session_store')
    async def test_create_session_mock(self, mock_get_store):
        """Test session creation with mocked Redis store"""
        # Mock Redis store
        mock_store = AsyncMock()
        mock_store.connect = AsyncMock()
        mock_store.store_session = AsyncMock(return_value=True)
        mock_get_store.return_value = mock_store
        
        manager = RedisSessionManager()
        
        # Create session
        session = await manager.create_session(
            user_id="test-user",
            metadata={"test": True}
        )
        
        # Verify session properties
        assert session.session_id.startswith("session-")
        assert session.user_id == "test-user"
        assert session.metadata == {"test": True}
        assert session.stm == []
        
        # Verify Redis operations
        mock_store.connect.assert_called_once()
        mock_store.store_session.assert_called_once()
        
        # Verify lock creation
        assert session.session_id in manager.session_locks
    
    @patch('kato.sessions.session_manager_redis.get_redis_session_store')
    async def test_get_session_mock(self, mock_get_store):
        """Test session retrieval with mocked Redis store"""
        # Create test session
        now = datetime.now(timezone.utc)
        session = SessionState(
            session_id="test-session",
            user_id="test-user",
            created_at=now,
            last_accessed=now - timedelta(minutes=5),
            expires_at=now + timedelta(hours=1)
        )
        
        # Mock Redis store
        mock_store = AsyncMock()
        mock_store.connect = AsyncMock()
        mock_store.get_session = AsyncMock(return_value=session)
        mock_store.store_session = AsyncMock(return_value=True)  # For access time update
        mock_get_store.return_value = mock_store
        
        manager = RedisSessionManager()
        
        # Get session
        retrieved = await manager.get_session("test-session")
        
        # Verify
        assert retrieved is not None
        assert retrieved.session_id == "test-session"
        assert retrieved.user_id == "test-user"
        
        # Verify access time was updated (or at least not older)
        # Note: The mock returns the same object which gets updated in place
        assert retrieved.last_accessed >= session.last_accessed
        
        # Verify Redis operations
        mock_store.connect.assert_called_once()
        mock_store.get_session.assert_called_with("test-session")
        mock_store.store_session.assert_called()  # Access time update
    
    @patch('kato.sessions.session_manager_redis.get_redis_session_store')
    async def test_session_operations_mock(self, mock_get_store):
        """Test various session operations with mocked store"""
        # Mock Redis store
        mock_store = AsyncMock()
        mock_store.connect = AsyncMock()
        mock_store.get_session = AsyncMock()
        mock_store.store_session = AsyncMock(return_value=True)
        mock_store.delete_session = AsyncMock(return_value=True)
        mock_store.get_session_count = AsyncMock(return_value=5)
        mock_store.list_active_sessions = AsyncMock(return_value=["s1", "s2", "s3"])
        mock_get_store.return_value = mock_store
        
        manager = RedisSessionManager()
        
        # Test session count
        count = await manager.get_active_session_count_async()
        assert count == 5
        mock_store.get_session_count.assert_called_once()
        
        # Test delete session
        result = await manager.delete_session("test-session")
        assert result is True
        mock_store.delete_session.assert_called_with("test-session")
        
        # Test cleanup
        mock_store.cleanup_expired_sessions = AsyncMock(return_value=2)
        cleaned = await manager.cleanup_expired_sessions()
        assert cleaned == 2
    
    @patch('kato.sessions.session_manager_redis.get_redis_session_store')
    async def test_health_check_mock(self, mock_get_store):
        """Test health check with mocked store"""
        # Mock healthy Redis store
        mock_store = AsyncMock()
        mock_store.connect = AsyncMock()
        mock_store.health_check = AsyncMock(return_value=True)
        mock_store.get_session_count = AsyncMock(return_value=3)
        mock_get_store.return_value = mock_store
        
        manager = RedisSessionManager()
        
        health = await manager.health_check()
        
        assert health["status"] == "healthy"
        assert health["redis_connected"] is True
        assert health["session_count"] == 3
        assert "in_memory_locks" in health
    
    @patch('kato.sessions.session_manager_redis.get_redis_session_store')
    async def test_health_check_unhealthy_mock(self, mock_get_store):
        """Test health check with unhealthy Redis"""
        # Mock unhealthy Redis store
        mock_store = AsyncMock()
        mock_store.connect = AsyncMock(side_effect=Exception("Connection failed"))
        mock_get_store.return_value = mock_store
        
        manager = RedisSessionManager()
        
        health = await manager.health_check()
        
        assert health["status"] == "unhealthy"
        assert health["redis_connected"] is False
        assert "error" in health


if __name__ == "__main__":
    pytest.main([__file__, "-v"])