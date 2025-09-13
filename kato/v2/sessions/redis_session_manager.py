"""
Redis-backed Session Manager for KATO v2.0

Provides persistent session storage using Redis, enabling:
- Session persistence across service restarts
- Horizontal scaling with shared session state
- Automatic expiration using Redis TTL
"""

import asyncio
import json
import uuid
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
try:
    # Try modern redis with async support
    import redis.asyncio as redis
except ImportError:
    # Fallback to aioredis
    import aioredis as redis
from dataclasses import dataclass, asdict

from .session_manager import SessionState, SessionManager

logger = logging.getLogger('kato.v2.sessions.redis')


class RedisSessionManager(SessionManager):
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
        key_prefix: str = "kato:session:"
    ):
        """
        Initialize Redis session manager.
        
        Args:
            redis_url: Redis connection URL
            default_ttl_seconds: Default session TTL
            key_prefix: Prefix for Redis keys
        """
        super().__init__(default_ttl_seconds)
        self.redis_url = redis_url
        self.key_prefix = key_prefix
        self.redis_client: Optional[redis.Redis] = None
        self._connected = False
        
        logger.info(f"RedisSessionManager initialized with URL: {redis_url}")
    
    async def initialize(self):
        """Initialize Redis connection"""
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
    
    async def create_session(
        self,
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        ttl_seconds: Optional[int] = None
    ) -> SessionState:
        """
        Create a new session and store in Redis.
        
        Args:
            user_id: Optional user identifier
            metadata: Optional session metadata
            ttl_seconds: Session TTL (uses default if not specified)
        
        Returns:
            New SessionState instance
        """
        if not self._connected:
            await self.initialize()
        
        session_id = f"session-{uuid.uuid4().hex}-{int(datetime.utcnow().timestamp() * 1000)}"
        ttl = ttl_seconds or self.default_ttl
        
        now = datetime.utcnow()
        expires_at = now + timedelta(seconds=ttl)
        
        session = SessionState(
            session_id=session_id,
            user_id=user_id,
            created_at=now,
            last_accessed=now,
            expires_at=expires_at,
            stm=[],
            emotives_accumulator=[],
            time=0,
            metadata=metadata or {},
            access_count=0
        )
        
        # Store in Redis with TTL
        await self._save_session(session, ttl)
        
        # Create lock for this session
        self.session_locks[session_id] = asyncio.Lock()
        
        logger.info(f"Created session {session_id} for user {user_id} with {ttl}s TTL")
        return session
    
    async def get_session(self, session_id: str) -> Optional[SessionState]:
        """
        Get session from Redis.
        
        Args:
            session_id: Session identifier
        
        Returns:
            SessionState if found and not expired, None otherwise
        """
        logger.info(f"Getting session {session_id}, connected: {self._connected}")
        if not self._connected:
            logger.info(f"Not connected, initializing Redis connection")
            await self.initialize()
        
        key = f"{self.key_prefix}{session_id}"
        logger.info(f"Looking for Redis key: {key}")
        
        try:
            # Get session data from Redis
            session_data = await self.redis_client.get(key)
            logger.info(f"Redis returned data: {session_data is not None}")
            
            if not session_data:
                return None
            
            # Deserialize session
            session_dict = json.loads(session_data)
            
            # Convert datetime strings back to datetime objects
            session_dict['created_at'] = datetime.fromisoformat(session_dict['created_at'])
            session_dict['last_accessed'] = datetime.fromisoformat(session_dict['last_accessed'])
            session_dict['expires_at'] = datetime.fromisoformat(session_dict['expires_at'])
            
            session = SessionState(**session_dict)
            
            # Check if expired
            if session.is_expired():
                await self.delete_session(session_id)
                return None
            
            # Update access time
            session.update_access()
            
            # Get remaining TTL
            ttl = await self.redis_client.ttl(key)
            if ttl > 0:
                await self._save_session(session, ttl)
            
            # Ensure lock exists
            if session_id not in self.session_locks:
                self.session_locks[session_id] = asyncio.Lock()
            
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
            # Calculate remaining TTL
            remaining_ttl = int((session.expires_at - datetime.utcnow()).total_seconds())
            
            if remaining_ttl <= 0:
                # Session expired
                await self.delete_session(session.session_id)
                return False
            
            # Enforce limits before saving
            session.enforce_limits()
            
            # Save to Redis
            await self._save_session(session, remaining_ttl)
            return True
            
        except Exception as e:
            logger.error(f"Error updating session {session.session_id}: {e}")
            return False
    
    async def delete_session(self, session_id: str) -> bool:
        """
        Delete session from Redis.
        
        Args:
            session_id: Session identifier
        
        Returns:
            True if deleted, False if not found
        """
        if not self._connected:
            await self.initialize()
        
        key = f"{self.key_prefix}{session_id}"
        
        # Delete from Redis
        deleted = await self.redis_client.delete(key)
        
        # Remove lock
        if session_id in self.session_locks:
            del self.session_locks[session_id]
        
        if deleted:
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
                session.expires_at = datetime.utcnow() + timedelta(seconds=ttl_seconds)
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
        # In Redis mode, we can't easily count without scanning
        # Return cached count or estimate
        return len(self.session_locks)  # Approximate based on local locks
    
    async def get_session_lock(self, session_id: str) -> Optional[asyncio.Lock]:
        """
        Get the lock for a specific session.
        
        Args:
            session_id: Session identifier
        
        Returns:
            asyncio.Lock for the session, None if session doesn't exist
        """
        # For Redis sessions, check if session exists first
        session = await self.get_session(session_id)
        if not session:
            return None
            
        # Ensure lock exists for this session
        if session_id not in self.session_locks:
            self.session_locks[session_id] = asyncio.Lock()
            
        return self.session_locks[session_id]

    async def get_all_sessions(self) -> List[SessionState]:
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
    
    def get_session_stats(self) -> Dict[str, Any]:
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
    
    async def get_session_stats_async(self) -> Dict[str, Any]:
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
            "users_with_sessions": len(set(s.user_id for s in active_sessions if s.user_id)),
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
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
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
        
        # Convert session to dict for serialization
        session_dict = {
            'session_id': session.session_id,
            'user_id': session.user_id,
            'created_at': session.created_at.isoformat(),
            'last_accessed': session.last_accessed.isoformat(),
            'expires_at': session.expires_at.isoformat(),
            'stm': session.stm,
            'emotives_accumulator': session.emotives_accumulator,
            'time': session.time,
            'metadata': session.metadata,
            'access_count': session.access_count,
            'max_stm_size': session.max_stm_size,
            'max_emotives_size': session.max_emotives_size
        }
        
        # Serialize to JSON
        session_data = json.dumps(session_dict)
        
        # Save with TTL
        await self.redis_client.setex(key, ttl_seconds, session_data)
    
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
        redis_url = redis_url or "redis://localhost:6379"
        _redis_session_manager = RedisSessionManager(redis_url=redis_url, **kwargs)
    
    return _redis_session_manager