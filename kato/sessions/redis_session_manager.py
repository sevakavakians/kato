"""
Redis-backed Session Manager for KATO

Provides persistent session storage using Redis, enabling:
- Session persistence across service restarts
- Horizontal scaling with shared session state
- Automatic expiration using Redis TTL
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import redis.asyncio as redis

# Import SessionManager as base class only when needed
import kato.sessions.session_manager as session_manager_module
from kato.config.session_config import SessionConfiguration

from .session_manager import SessionState
import contextlib

# Import event broadcaster for WebSocket notifications
from kato.websocket import get_event_broadcaster

logger = logging.getLogger('kato.sessions.redis')


class RedisSessionManager(session_manager_module.SessionManager):
    """
    Redis-backed session manager for persistent, scalable session storage.

    This manager stores sessions in Redis instead of memory, providing:
    - Persistence across service restarts
    - Shared state across multiple KATO instances
    - Automatic expiration using Redis TTL features
    - Better scalability for high session counts
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        default_ttl_seconds: int = 3600,
        key_prefix: str = "kato:session:",
        auto_extend: bool = True
    ):
        """
        Initialize Redis session manager.

        Args:
            redis_url: Redis connection URL
            default_ttl_seconds: Default session TTL
            key_prefix: Prefix for Redis keys
            auto_extend: Automatically extend session TTL on access (sliding window)
        """
        super().__init__(default_ttl_seconds)
        self.redis_url = redis_url
        self.key_prefix = key_prefix
        self.auto_extend = auto_extend
        self.redis_client: Optional[redis.Redis] = None
        self._connected = False
        self._init_lock = asyncio.Lock()  # CRITICAL FIX: Lock for thread-safe initialization

        logger.info(f"RedisSessionManager initialized with URL: {redis_url}, auto_extend: {auto_extend}")

    def _serialize_session_config(self, session_config: SessionConfiguration) -> dict[str, Any]:
        """
        Serialize SessionConfiguration for JSON storage.

        Args:
            session_config: SessionConfiguration instance

        Returns:
            Dictionary with JSON-serializable values
        """
        config_dict = session_config.to_dict()
        # Convert datetime fields to ISO strings
        if 'created_at' in config_dict and config_dict['created_at'] and hasattr(config_dict['created_at'], 'isoformat'):
            config_dict['created_at'] = config_dict['created_at'].isoformat()
        if 'updated_at' in config_dict and config_dict['updated_at'] and hasattr(config_dict['updated_at'], 'isoformat'):
            config_dict['updated_at'] = config_dict['updated_at'].isoformat()
        return config_dict

    def _deserialize_session(self, session_dict: dict[str, Any]) -> SessionState:
        """
        Deserialize a session from a dictionary.

        Args:
            session_dict: Dictionary representation of session

        Returns:
            SessionState instance
        """
        # Convert datetime strings back to datetime objects
        session_dict['created_at'] = datetime.fromisoformat(session_dict['created_at'])
        session_dict['last_accessed'] = datetime.fromisoformat(session_dict['last_accessed'])
        session_dict['expires_at'] = datetime.fromisoformat(session_dict['expires_at'])

        # Handle SessionConfiguration if present
        if 'session_config' in session_dict and session_dict['session_config']:
            if isinstance(session_dict['session_config'], dict):
                session_dict['session_config'] = SessionConfiguration.from_dict(session_dict['session_config'])
        else:
            # Create default session config if not present
            session_dict['session_config'] = SessionConfiguration()

        # Ensure metadata_accumulator exists (for backward compatibility)
        if 'metadata_accumulator' not in session_dict:
            session_dict['metadata_accumulator'] = []

        # Ensure max_metadata_size exists (for backward compatibility)
        if 'max_metadata_size' not in session_dict:
            session_dict['max_metadata_size'] = 1000

        # Ensure ttl_seconds exists (for backward compatibility)
        if 'ttl_seconds' not in session_dict:
            session_dict['ttl_seconds'] = self.default_ttl

        return SessionState(**session_dict)

    async def initialize(self):
        """Initialize Redis connection with thread-safe locking"""
        # CRITICAL FIX: Use lock to prevent race condition when multiple concurrent
        # requests try to initialize the Redis client simultaneously
        async with self._init_lock:
            # Double-check pattern: recheck after acquiring lock
            if self._connected:
                return

            try:
                # Create Redis client with connection pool
                self.redis_client = redis.from_url(
                    self.redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                    max_connections=50
                )

                # Test connection
                await self.redis_client.ping()
                self._connected = True

                logger.info("Redis connection established")

                # Start cleanup task
                if not self._cleanup_task:
                    self._cleanup_task = asyncio.create_task(self._cleanup_loop())

            except Exception as e:
                logger.error(f"Failed to connect to Redis: {e}")
                raise

    async def get_or_create_session(
        self,
        node_id: str,
        config: Optional[dict[str, Any]] = None,
        metadata: Optional[dict[str, Any]] = None,
        ttl_seconds: Optional[int] = None
    ) -> SessionState:
        """
        Get existing session for a node or create a new one.

        This enables session persistence across requests from the same node.

        Args:
            node_id: Node identifier (required for processor isolation)
            config: Optional session configuration parameters
            metadata: Optional session metadata
            ttl_seconds: Session TTL (uses default if not specified)

        Returns:
            SessionState for this node (existing or newly created)
        """
        if not self._connected:
            await self.initialize()

        # Use a node-specific key to track their active session
        node_session_key = f"{self.key_prefix}node:{node_id}:active"

        # Check if node has an active session
        session_id = await self.redis_client.get(node_session_key)

        if session_id:
            # Try to get the existing session
            session = await self.get_session(session_id)
            if session and not session.is_expired():
                session.update_access()
                await self.update_session(session)
                logger.info(f"Returning existing session {session.session_id} for node {node_id}")
                return session
            else:
                # Session expired or not found, clear the reference
                await self.redis_client.delete(node_session_key)

        # No existing session, create new one
        session = await self.create_session(node_id, config, metadata, ttl_seconds)

        # Store the session ID for this node
        ttl = ttl_seconds or self.default_ttl
        await self.redis_client.setex(node_session_key, ttl, session.session_id)

        logger.info(f"Created new session {session.session_id} for node {node_id}")
        return session

    async def create_session(
        self,
        node_id: str,
        config: Optional[dict[str, Any]] = None,
        metadata: Optional[dict[str, Any]] = None,
        ttl_seconds: Optional[int] = None
    ) -> SessionState:
        """
        Create a new session and store in Redis.

        Args:
            node_id: Node identifier (required for processor isolation)
            config: Optional session configuration parameters
            metadata: Optional session metadata
            ttl_seconds: Session TTL (uses default if not specified)

        Returns:
            New SessionState instance
        """
        if not self._connected:
            await self.initialize()

        session_id = f"session-{uuid.uuid4().hex}-{int(datetime.now(timezone.utc).timestamp() * 1000)}"
        logger.debug(f"Starting create_session for session_id: {session_id}, node_id: {node_id}")
        ttl = ttl_seconds or self.default_ttl

        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=ttl)

        # Initialize session configuration
        session_config = SessionConfiguration(session_id=session_id, node_id=node_id)

        # Apply config if provided
        if config:
            session_config.update(config)

        session = SessionState(
            session_id=session_id,
            node_id=node_id,
            created_at=now,
            last_accessed=now,
            expires_at=expires_at,
            ttl_seconds=ttl,  # Store session-specific TTL for auto-extension
            stm=[],
            emotives_accumulator=[],
            metadata_accumulator=[],
            time=0,
            metadata=metadata or {},
            access_count=0,
            session_config=session_config
        )

        logger.debug(f"About to save session {session_id} to Redis with TTL {ttl}s")
        # Store in Redis with TTL
        await self._save_session(session, ttl)
        logger.debug(f"Session {session_id} saved successfully")

        # Create lock for this session (use setdefault for safety)
        self.session_locks.setdefault(session_id, asyncio.Lock())

        logger.info(f"Created session {session_id} for node {node_id} with {ttl}s TTL")

        # Broadcast session.created event to WebSocket clients
        try:
            broadcaster = get_event_broadcaster()
            event = {
                "event_type": "session.created",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "data": {
                    "session_id": session_id,
                    "node_id": node_id,
                    "created_at": session.created_at.isoformat()
                }
            }
            await broadcaster.broadcast_event(event)
            logger.debug(f"Broadcasted session.created event for {session_id}")
        except Exception as e:
            # Don't fail session creation if broadcast fails
            logger.warning(f"Failed to broadcast session.created event: {e}")

        return session

    async def get_session(self, session_id: str, check_only: bool = False) -> Optional[SessionState]:
        """
        Get session from Redis.

        Args:
            session_id: Session identifier
            check_only: If True, retrieve without auto-extending (for testing expiration)

        Returns:
            SessionState if found and not expired, None otherwise
        """
        logger.debug(f"Starting get_session for session_id: {session_id}")
        logger.info(f"Getting session {session_id}, connected: {self._connected}")
        if not self._connected:
            logger.info("Not connected, initializing Redis connection")
            await self.initialize()

        key = f"{self.key_prefix}{session_id}"
        logger.debug(f"Looking for Redis key: {key}")
        logger.info(f"Looking for Redis key: {key}")

        try:
            # Get session data from Redis
            logger.debug(f"Calling Redis GET for {key}")
            session_data = await self.redis_client.get(key)
            logger.debug(f"Redis GET returned: {'DATA' if session_data else 'NULL'} for {key}")
            logger.info(f"Redis returned data: {session_data is not None}")

            if not session_data:
                logger.debug(f"Session {session_id} NOT FOUND in Redis")
                return None

            # Deserialize session
            try:
                session_dict = json.loads(session_data)
                logger.info(f"Loaded session dict for {session_id}: {list(session_dict.keys())}")
            except json.JSONDecodeError as e:
                logger.error(f"Failed to decode JSON for session {session_id}: {e}")
                logger.error(f"Raw data: {session_data}")
                return None
            except Exception as e:
                logger.error(f"Unexpected error loading JSON for session {session_id}: {e}")
                import traceback
                logger.error(f"Traceback: {traceback.format_exc()}")
                return None
            try:
                session = self._deserialize_session(session_dict)
                logger.info(f"Successfully deserialized session {session_id}")
            except Exception as e:
                logger.error(f"Failed to deserialize session {session_id}: {e}")
                logger.error(f"Session dict: {session_dict}")
                import traceback
                logger.error(f"Traceback: {traceback.format_exc()}")
                return None

            # Check if expired
            if session.is_expired():
                logger.info(f"Session {session_id} expired, deleting")
                await self.delete_session(session_id)
                return None

            logger.info(f"Session {session_id} is valid, updating access time")

            # Update access time and expiration (unless check_only mode)
            if not check_only:
                session.update_access()

                # Auto-extend session TTL on access (sliding window)
                if self.auto_extend:
                    # Reset expiration to now + session's TTL (sliding window)
                    session.expires_at = datetime.now(timezone.utc) + timedelta(seconds=session.ttl_seconds)
                    logger.debug(f"Auto-extending session {session_id} by {session.ttl_seconds}s (TTL-only update)")

                    # CRITICAL FIX: Extend TTL immediately without overwriting session data
                    # This prevents session expiration during long-running operations while avoiding race conditions
                    # Uses EXPIRE command which only updates TTL, not the entire session state
                    try:
                        key = f"{self.key_prefix}{session_id}"
                        await self.redis_client.expire(key, session.ttl_seconds)
                        logger.debug(f"Session {session_id} TTL extended to {session.ttl_seconds}s in Redis")
                    except Exception as expire_error:
                        logger.error(f"Failed to extend TTL for {session_id}: {expire_error}")
                        # Don't fail the request - session will retry on next access

            # Ensure lock exists (atomic operation)
            self.session_locks.setdefault(session_id, asyncio.Lock())

            return session

        except Exception as e:
            logger.error(f"Error getting session {session_id}: {e}")
            return None

    async def update_session(self, session: SessionState) -> bool:
        """
        Update session in Redis.

        Args:
            session: SessionState to update

        Returns:
            True if updated successfully
        """
        if not self._connected:
            await self.initialize()

        try:
            # Auto-extend session on update if enabled
            if self.auto_extend:
                # Reset expiration to now + session's TTL (sliding window)
                session.expires_at = datetime.now(timezone.utc) + timedelta(seconds=session.ttl_seconds)
                ttl = session.ttl_seconds
                logger.debug(f"Auto-extending session {session.session_id} on update with {ttl}s TTL")
            else:
                # Calculate remaining TTL (fixed expiration)
                ttl = int((session.expires_at - datetime.now(timezone.utc)).total_seconds())

                if ttl <= 0:
                    # Session expired
                    await self.delete_session(session.session_id)
                    return False

            # Enforce limits before saving
            session.enforce_limits()

            # Save to Redis
            await self._save_session(session, ttl)
            return True

        except Exception as e:
            logger.error(f"Error updating session {session.session_id}: {e}")
            return False

    async def delete_session(self, session_id: str) -> bool:
        """
        Delete session from Redis and clean up node tracking key.

        Args:
            session_id: Session identifier

        Returns:
            True if deleted or session was found, False if not found
        """
        if not self._connected:
            await self.initialize()

        # Get session first to find node_id for cleanup
        session = await self.get_session(session_id)

        key = f"{self.key_prefix}{session_id}"

        # Delete session from Redis
        deleted = await self.redis_client.delete(key)

        # If session existed, also delete node tracking key
        if session:
            node_session_key = f"{self.key_prefix}node:{session.node_id}:active"
            await self.redis_client.delete(node_session_key)
            logger.info(f"Deleted session {session_id} and node tracking key for {session.node_id}")

        # Remove lock
        if session_id in self.session_locks:
            del self.session_locks[session_id]

        # Broadcast session.destroyed event to WebSocket clients if session existed
        if session:
            try:
                broadcaster = get_event_broadcaster()
                event = {
                    "event_type": "session.destroyed",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "data": {
                        "session_id": session_id,
                        "destroyed_at": datetime.now(timezone.utc).isoformat(),
                        "reason": "explicit_delete"
                    }
                }
                await broadcaster.broadcast_event(event)
                logger.debug(f"Broadcasted session.destroyed event for {session_id}")
            except Exception as e:
                # Don't fail session deletion if broadcast fails
                logger.warning(f"Failed to broadcast session.destroyed event: {e}")

        # Return True if we cleaned up a session (even if Redis key didn't exist)
        if deleted or session:
            logger.info(f"Deleted session {session_id}")
            return True

        return False

    async def extend_session(self, session_id: str, ttl_seconds: int) -> bool:
        """
        Extend session TTL in Redis.

        Args:
            session_id: Session identifier
            ttl_seconds: New TTL from now

        Returns:
            True if extended, False if session not found
        """
        if not self._connected:
            await self.initialize()

        key = f"{self.key_prefix}{session_id}"

        # Check if session exists
        if not await self.redis_client.exists(key):
            return False

        # Set new TTL
        result = await self.redis_client.expire(key, ttl_seconds)

        if result:
            # Update session expires_at if we have it in memory
            session = await self.get_session(session_id)
            if session:
                session.expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
                await self._save_session(session, ttl_seconds)

            logger.info(f"Extended session {session_id} by {ttl_seconds}s")
            return True

        return False

    async def clear_session_stm(self, session_id: str) -> bool:
        """
        Clear STM for a session.

        Args:
            session_id: Session identifier

        Returns:
            True if cleared, False if session not found
        """
        session = await self.get_session(session_id)
        if not session:
            return False

        session.stm = []
        session.emotives_accumulator = []

        return await self.update_session(session)

    def get_active_session_count(self) -> int:
        """
        Get count of active sessions.

        Note: This is an approximation in Redis-backed mode.
        For exact count, use get_all_sessions().
        """
        # In Redis mode, count all session keys
        if self.redis_client:
            try:
                # Count only actual session keys (not node tracking keys)
                # Actual sessions have pattern: kato:session:session-{uuid}-{timestamp}
                keys = self.redis_client.keys(f"{self.key_prefix}session-*")
                return len(keys)
            except Exception:
                # Fallback to local locks count
                return len(self.session_locks)
        return len(self.session_locks)  # Approximate based on local locks

    async def get_active_session_count_async(self) -> int:
        """
        Async version - Get count of active sessions.

        Note: This is an approximation in Redis-backed mode.
        For exact count, use get_all_sessions().
        """
        # Ensure we're connected
        await self.initialize()

        # In Redis mode, count all session keys
        if self.redis_client:
            try:
                # Count only actual session keys (not node tracking keys)
                # Actual sessions have pattern: kato:session:session-{uuid}-{timestamp}
                keys = await self.redis_client.keys(f"{self.key_prefix}session-*")
                return len(keys)
            except Exception as e:
                logger.warning(f"Failed to count Redis keys, using fallback: {e}")
                # Fallback to local locks count
                return len(self.session_locks)
        return len(self.session_locks)  # Approximate based on local locks

    async def get_session_lock(self, session_id: str) -> Optional[asyncio.Lock]:
        """
        Get the lock for a specific session.

        Args:
            session_id: Session identifier

        Returns:
            asyncio.Lock for the session, None if session doesn't exist
        """
        logger.debug(f"Getting lock for session: {session_id}")
        # For Redis sessions, check if session exists first
        # Check Redis directly without calling get_session to avoid recursion
        if not self._connected:
            await self.initialize()

        key = f"{self.key_prefix}{session_id}"
        logger.debug(f"Calling Redis EXISTS for key: {key}")
        session_exists = await self.redis_client.exists(key)
        logger.debug(f"Redis EXISTS returned: {session_exists} for {key}")
        if not session_exists:
            logger.debug(f"Session {session_id} NOT FOUND - returning None")
            return None

        # Ensure lock exists for this session (atomic operation)
        return self.session_locks.setdefault(session_id, asyncio.Lock())

    async def get_all_sessions(self) -> list[SessionState]:
        """
        Get all sessions from Redis.

        Returns:
            List of all non-expired sessions
        """
        if not self._connected:
            await self.initialize()

        sessions = []

        # Scan for all session keys
        pattern = f"{self.key_prefix}*"
        cursor = 0

        while True:
            cursor, keys = await self.redis_client.scan(
                cursor, match=pattern, count=100
            )

            for key in keys:
                session_id = key.replace(self.key_prefix, "")
                session = await self.get_session(session_id)
                if session:
                    sessions.append(session)

            if cursor == 0:
                break

        return sessions

    def get_session_stats(self) -> dict[str, Any]:
        """
        Get session statistics.

        Note: This is synchronous for compatibility but returns
        approximate values in Redis mode.
        """
        # Return approximate stats based on local state
        return {
            "total_sessions": len(self.session_locks),
            "active_sessions": len(self.session_locks),
            "expired_sessions": 0,  # Unknown in Redis mode
            "backend": "redis",
            "redis_url": self.redis_url
        }

    async def get_session_stats_async(self) -> dict[str, Any]:
        """
        Get detailed session statistics (async version).

        Returns:
            Detailed statistics about sessions
        """
        sessions = await self.get_all_sessions()
        active_sessions = [s for s in sessions if not s.is_expired()]

        return {
            "total_sessions": len(sessions),
            "active_sessions": len(active_sessions),
            "expired_sessions": len(sessions) - len(active_sessions),
            "nodes_with_sessions": len({s.node_id for s in active_sessions if s.node_id}),
            "average_stm_size": sum(len(s.stm) for s in active_sessions) / max(len(active_sessions), 1),
            "total_stm_events": sum(len(s.stm) for s in active_sessions),
            "backend": "redis",
            "redis_url": self.redis_url
        }

    async def shutdown(self):
        """Clean shutdown of Redis connection"""
        logger.info("Shutting down RedisSessionManager...")

        # Cancel cleanup task
        if self._cleanup_task:
            self._cleanup_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._cleanup_task

        # Close Redis connection
        if self.redis_client:
            await self.redis_client.close()
            self._connected = False

        logger.info("RedisSessionManager shutdown complete")

    async def _save_session(self, session: SessionState, ttl_seconds: int):
        """
        Save session to Redis with TTL.

        Args:
            session: Session to save
            ttl_seconds: TTL in seconds
        """
        key = f"{self.key_prefix}{session.session_id}"
        logger.debug(f"Saving session {session.session_id} to Redis key: {key}")

        # Convert session to dict for serialization
        session_dict = {
            'session_id': session.session_id,
            'node_id': session.node_id,
            'created_at': session.created_at.isoformat(),
            'last_accessed': session.last_accessed.isoformat(),
            'expires_at': session.expires_at.isoformat(),
            'ttl_seconds': session.ttl_seconds,
            'stm': session.stm,
            'emotives_accumulator': session.emotives_accumulator,
            'metadata_accumulator': session.metadata_accumulator,
            'time': session.time,
            'metadata': session.metadata,
            'access_count': session.access_count,
            'max_stm_size': session.max_stm_size,
            'max_emotives_size': session.max_emotives_size,
            'max_metadata_size': session.max_metadata_size,
            'session_config': self._serialize_session_config(session.session_config) if session.session_config else None
        }

        # Serialize to JSON
        session_data = json.dumps(session_dict)
        logger.debug(f"Serialized session {session.session_id}, JSON length: {len(session_data)}")

        # Save with TTL
        logger.debug(f"Calling Redis SETEX for {key} with TTL {ttl_seconds}s")
        await self.redis_client.setex(key, ttl_seconds, session_data)
        logger.debug(f"Redis SETEX completed for {key}")

        # CRITICAL FIX: Verify write completed with EXISTS check
        # This ensures the key is actually in Redis before we return
        logger.debug(f"Verifying write with EXISTS for {key}")
        exists = await self.redis_client.exists(key)
        logger.debug(f"EXISTS verification returned: {exists} for {key}")
        if not exists:
            raise RuntimeError(f"Session write verification failed - key {key} not found after SETEX")

    async def _cleanup_loop(self):
        """
        Background cleanup task.

        Note: Redis handles expiration automatically, but this can
        clean up local locks for expired sessions.
        """
        while True:
            try:
                await asyncio.sleep(self._cleanup_interval)

                # Clean up locks for non-existent sessions
                for session_id in list(self.session_locks.keys()):
                    key = f"{self.key_prefix}{session_id}"
                    if not await self.redis_client.exists(key):
                        del self.session_locks[session_id]
                        logger.debug(f"Cleaned up lock for expired session {session_id}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")


# Singleton instance management
_redis_session_manager: Optional[RedisSessionManager] = None


def get_redis_session_manager(
    redis_url: Optional[str] = None,
    **kwargs
) -> RedisSessionManager:
    """
    Get or create the singleton Redis session manager.

    Args:
        redis_url: Redis connection URL
        **kwargs: Additional arguments for RedisSessionManager

    Returns:
        RedisSessionManager singleton instance
    """
    global _redis_session_manager

    if _redis_session_manager is None:
        import traceback
        logger.debug("Creating new RedisSessionManager in get_redis_session_manager()")
        logger.debug(f"Call stack:\n{''.join(traceback.format_stack()[-5:])}")
        redis_url = redis_url or "redis://localhost:6379"
        _redis_session_manager = RedisSessionManager(redis_url=redis_url, **kwargs)
    else:
        logger.debug("Returning cached RedisSessionManager")

    return _redis_session_manager
