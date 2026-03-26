"""
Test Redis-based session storage for KATO v3.0+
Tests persistence, serialization, and real Redis integration.

These tests connect to the running Redis instance (not mocked) to verify
actual session persistence behavior.
"""

from datetime import datetime, timedelta, timezone

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


@pytest.mark.asyncio
class TestRedisSessionManagerIntegration:
    """Test Redis session manager against running Redis instance."""

    async def test_session_create_and_retrieve(self):
        """Test creating and retrieving a session from real Redis."""
        manager = RedisSessionManager(
            default_ttl_seconds=60,
            redis_url="redis://localhost:6379"
        )

        try:
            await manager.initialize()

            # Create session
            session = await manager.create_session(
                node_id="test-redis-integration",
                metadata={"test": True}
            )

            assert session.session_id.startswith("session-")
            assert session.node_id == "test-redis-integration"
            assert session.metadata == {"test": True}
            assert session.stm == []

            # Retrieve session
            retrieved = await manager.get_session(session.session_id)
            assert retrieved is not None
            assert retrieved.session_id == session.session_id
            assert retrieved.node_id == session.node_id

            # Cleanup
            await manager.delete_session(session.session_id)
        finally:
            await manager.shutdown()

    async def test_session_delete(self):
        """Test deleting a session from real Redis."""
        manager = RedisSessionManager(
            default_ttl_seconds=60,
            redis_url="redis://localhost:6379"
        )

        try:
            await manager.initialize()

            # Create and delete
            session = await manager.create_session(node_id="test-delete")
            result = await manager.delete_session(session.session_id)
            assert result is True

            # Should not exist after delete
            retrieved = await manager.get_session(session.session_id)
            assert retrieved is None
        finally:
            await manager.shutdown()

    async def test_session_extend(self):
        """Test extending a session TTL in real Redis."""
        manager = RedisSessionManager(
            default_ttl_seconds=60,
            redis_url="redis://localhost:6379"
        )

        try:
            await manager.initialize()

            # Create session with short TTL
            session = await manager.create_session(node_id="test-extend")

            # Extend TTL
            result = await manager.extend_session(session.session_id, 7200)
            assert result is True

            # Session should still be accessible
            retrieved = await manager.get_session(session.session_id)
            assert retrieved is not None

            # Cleanup
            await manager.delete_session(session.session_id)
        finally:
            await manager.shutdown()

    async def test_session_update_persists(self):
        """Test that session updates persist to Redis."""
        manager = RedisSessionManager(
            default_ttl_seconds=60,
            redis_url="redis://localhost:6379"
        )

        try:
            await manager.initialize()

            # Create session
            session = await manager.create_session(node_id="test-update")

            # Modify STM
            session.stm = [["hello", "world"], ["foo", "bar"]]
            await manager.update_session(session)

            # Retrieve and verify
            retrieved = await manager.get_session(session.session_id)
            assert retrieved is not None
            assert retrieved.stm == [["hello", "world"], ["foo", "bar"]]

            # Cleanup
            await manager.delete_session(session.session_id)
        finally:
            await manager.shutdown()

    async def test_connection_failure_handling(self):
        """Test that connection to invalid Redis fails gracefully."""
        manager = RedisSessionManager(
            default_ttl_seconds=60,
            redis_url="redis://localhost:19999"  # Non-existent port
        )

        with pytest.raises(Exception):
            await manager.initialize()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
