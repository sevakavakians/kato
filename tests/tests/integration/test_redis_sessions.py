"""
Test Redis-based session storage for KATO v3.0+
Tests persistence, serialization, and real Redis integration.

These tests connect to the running Redis instance (not mocked) to verify
actual session persistence behavior.
"""


import pytest

from kato.sessions.redis_session_manager import RedisSessionManager


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
