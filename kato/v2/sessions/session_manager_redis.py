"""
KATO v2.0 Session Management Implementation with Redis Backend

This module provides multi-user session isolation using Redis for persistence.
Sessions survive service restarts and can be shared across multiple instances.
"""

import asyncio
import time
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import logging
import os

from .session_manager import SessionState  # Import the dataclass
from .redis_session_store import RedisSessionStore, get_redis_session_store

logger = logging.getLogger('kato.v2.sessions.manager')


class RedisSessionManager:
    """
    Session manager with Redis persistence.
    
    Key improvements over in-memory version:
    - Persistent storage survives service restarts
    - Horizontal scaling across multiple instances
    - Automatic TTL-based expiration
    - Better resource management
    """
    
    def __init__(
        self,
        default_ttl_seconds: int = 3600,
        redis_url: Optional[str] = None,
        serialization: str = "pickle"
    ):
        """
        Initialize Redis-backed session manager.
        
        Args:
            default_ttl_seconds: Default session TTL (1 hour)
            redis_url: Redis connection URL (defaults to env var or localhost)
            serialization: Serialization method ("json" or "pickle")
        """
        self.default_ttl = default_ttl_seconds
        
        # Get Redis URL from environment or use default
        if redis_url is None:
            redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379')
        
        # Initialize Redis store
        self.store = get_redis_session_store(
            redis_url=redis_url,
            serialization=serialization
        )
        
        # In-memory locks for session concurrency (not persisted)
        self.session_locks: Dict[str, asyncio.Lock] = {}
        
        # Background cleanup task
        self._cleanup_task = None
        self._cleanup_interval = 300  # 5 minutes
        self._connected = False
        
        logger.info(f"RedisSessionManager initialized with {default_ttl_seconds}s default TTL")
    
    async def _ensure_connected(self):
        """Ensure Redis connection is established"""
        if not self._connected:
            await self.store.connect()
            self._connected = True
    
    async def create_session(
        self,
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        ttl_seconds: Optional[int] = None
    ) -> SessionState:
        """
        Create a new isolated session with Redis persistence.
        
        Args:
            user_id: Optional user identifier
            metadata: Optional session metadata
            ttl_seconds: Session TTL (uses default if not specified)
        
        Returns:
            New SessionState with unique session_id
        """
        await self._ensure_connected()
        
        # Generate cryptographically secure session ID
        session_id = f"session-{uuid.uuid4().hex}-{int(time.time() * 1000)}"
        
        now = datetime.utcnow()
        ttl = ttl_seconds or self.default_ttl
        
        session = SessionState(
            session_id=session_id,
            user_id=user_id,
            created_at=now,
            last_accessed=now,
            expires_at=now + timedelta(seconds=ttl),
            metadata=metadata or {}
        )
        
        # Store session in Redis
        success = await self.store.store_session(session)
        if not success:
            raise RuntimeError(f"Failed to create session {session_id} in Redis")
        
        # Create session-specific lock (in-memory only)
        self.session_locks[session_id] = asyncio.Lock()
        
        logger.info(f"Created session {session_id} for user {user_id}")
        
        # Start cleanup task if not running
        if not self._cleanup_task:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        
        return session
    
    async def get_session(self, session_id: str) -> Optional[SessionState]:
        """
        Retrieve session by ID from Redis.
        
        Args:
            session_id: Session identifier
        
        Returns:
            SessionState if found and not expired, None otherwise
        """
        await self._ensure_connected()
        
        session = await self.store.get_session(session_id)
        
        if not session:
            logger.debug(f"Session {session_id} not found")
            return None
        
        # Update access time and store back to Redis
        session.update_access()
        await self.store.store_session(session)
        
        return session
    
    async def get_session_lock(self, session_id: str) -> Optional[asyncio.Lock]:
        """
        Get the lock for a specific session.
        
        Args:
            session_id: Session identifier
        
        Returns:
            asyncio.Lock for the session, None if session doesn't exist
        """
        await self._ensure_connected()
        
        # Check if session exists in Redis
        session = await self.store.get_session(session_id)
        if not session:
            return None
        
        # Create lock if it doesn't exist (in-memory only)
        if session_id not in self.session_locks:
            self.session_locks[session_id] = asyncio.Lock()
        
        return self.session_locks[session_id]
    
    async def update_session(self, session: SessionState) -> bool:
        """
        Update session state in Redis.
        
        Args:
            session: Updated SessionState
        
        Returns:
            True if updated, False if session not found
        """
        await self._ensure_connected()
        
        # Check if session exists first
        existing = await self.store.get_session(session.session_id)
        if not existing:
            logger.warning(f"Attempted to update non-existent session {session.session_id}")
            return False
        
        # Enforce limits before saving
        session.enforce_limits()
        
        # Store updated session
        success = await self.store.store_session(session)
        if success:
            logger.debug(f"Updated session {session.session_id}")
        
        return success
    
    async def delete_session(self, session_id: str) -> bool:
        """
        Delete a session from Redis and cleanup resources.
        
        Args:
            session_id: Session identifier
        
        Returns:
            True if deleted, False if not found
        """
        await self._ensure_connected()
        
        # Delete from Redis
        success = await self.store.delete_session(session_id)
        
        # Remove in-memory lock
        if session_id in self.session_locks:
            del self.session_locks[session_id]
        
        if success:
            logger.info(f"Deleted session {session_id}")
        
        return success
    
    async def extend_session(self, session_id: str, ttl_seconds: int) -> bool:
        """
        Extend session expiration in Redis.
        
        Args:
            session_id: Session identifier
            ttl_seconds: New TTL from now
        
        Returns:
            True if extended, False if session not found
        """
        await self._ensure_connected()
        
        # Get session, update expiration, and store back
        session = await self.store.get_session(session_id)
        if not session:
            return False
        
        session.expires_at = datetime.utcnow() + timedelta(seconds=ttl_seconds)
        success = await self.store.store_session(session)
        
        if success:
            logger.info(f"Extended session {session_id} by {ttl_seconds}s")
        
        return success
    
    async def cleanup_expired_sessions(self) -> int:
        """
        Remove expired sessions from Redis.
        
        Returns:
            Number of sessions cleaned up
        """
        await self._ensure_connected()
        
        # Redis handles TTL automatically, but clean up any stragglers
        cleaned_count = await self.store.cleanup_expired_sessions()
        
        # Also clean up orphaned locks
        if cleaned_count > 0:
            session_ids = await self.store.list_active_sessions()
            active_set = set(session_ids)
            
            # Remove locks for sessions that no longer exist
            orphaned_locks = [
                sid for sid in self.session_locks.keys()
                if sid not in active_set
            ]
            
            for session_id in orphaned_locks:
                del self.session_locks[session_id]
            
            if orphaned_locks:
                logger.info(f"Cleaned up {len(orphaned_locks)} orphaned locks")
        
        return cleaned_count
    
    async def _cleanup_loop(self):
        """Background task to periodically cleanup expired sessions"""
        while True:
            try:
                await asyncio.sleep(self._cleanup_interval)
                await self.cleanup_expired_sessions()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")
    
    def get_active_session_count(self) -> int:
        """
        Get count of active sessions.
        
        Note: This is an async operation but made sync for compatibility.
        Consider using get_active_session_count_async() for new code.
        """
        # This is a bit of a hack for sync compatibility
        try:
            loop = asyncio.get_running_loop()
            task = asyncio.create_task(self._get_active_session_count())
            # This will only work if called from within an async context
            # For true sync operation, we'd need to use asyncio.run()
            return loop.run_until_complete(task)
        except RuntimeError:
            # No event loop running, return 0 as fallback
            logger.warning("get_active_session_count called without event loop")
            return 0
    
    async def get_active_session_count_async(self) -> int:
        """Get count of active sessions (async version)"""
        await self._ensure_connected()
        return await self.store.get_session_count()
    
    async def _get_active_session_count(self) -> int:
        """Internal async helper for sync method"""
        await self._ensure_connected()
        return await self.store.get_session_count()
    
    async def get_session_stats(self) -> Dict[str, Any]:
        """Get statistics about current sessions"""
        await self._ensure_connected()
        
        session_ids = await self.store.list_active_sessions()
        total_sessions = len(session_ids)
        
        # Sample some sessions to calculate averages (for performance)
        sample_size = min(50, total_sessions)
        sample_ids = session_ids[:sample_size]
        
        users_with_sessions = set()
        total_stm_events = 0
        total_stm_size = 0
        
        for session_id in sample_ids:
            session = await self.store.get_session(session_id)
            if session:
                if session.user_id:
                    users_with_sessions.add(session.user_id)
                total_stm_events += len(session.stm)
                total_stm_size += len(session.stm)
        
        # Extrapolate averages
        avg_stm_size = total_stm_size / max(sample_size, 1)
        total_estimated_events = int((total_stm_events / max(sample_size, 1)) * total_sessions)
        
        # Get Redis info
        redis_info = await self.store.get_redis_info()
        
        return {
            "total_sessions": total_sessions,
            "active_sessions": total_sessions,  # All sessions in Redis are active
            "expired_sessions": 0,  # Redis handles cleanup automatically
            "users_with_sessions": len(users_with_sessions),
            "average_stm_size": avg_stm_size,
            "estimated_total_stm_events": total_estimated_events,
            "redis_info": redis_info,
            "in_memory_locks": len(self.session_locks)
        }
    
    async def clear_session_stm(self, session_id: str) -> bool:
        """
        Clear the STM for a specific session.
        
        Args:
            session_id: Session identifier
        
        Returns:
            True if cleared, False if session not found
        """
        await self._ensure_connected()
        
        session = await self.store.get_session(session_id)
        if not session:
            return False
        
        session.stm = []
        session.emotives_accumulator = []
        
        success = await self.store.store_session(session)
        if success:
            logger.info(f"Cleared STM for session {session_id}")
        
        return success
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Check health of session manager and Redis.
        
        Returns:
            Dictionary with health status
        """
        try:
            await self._ensure_connected()
            redis_healthy = await self.store.health_check()
            session_count = await self.store.get_session_count()
            
            return {
                "status": "healthy" if redis_healthy else "unhealthy",
                "redis_connected": redis_healthy,
                "session_count": session_count,
                "in_memory_locks": len(self.session_locks),
                "cleanup_task_running": self._cleanup_task is not None and not self._cleanup_task.done()
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "redis_connected": False
            }
    
    async def shutdown(self):
        """Cleanup resources on shutdown"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        # Disconnect from Redis
        if self._connected:
            await self.store.disconnect()
            self._connected = False
        
        # Clear in-memory resources
        self.session_locks.clear()
        
        logger.info("RedisSessionManager shutdown complete")


# Global Redis session manager instance (singleton pattern)
_redis_session_manager: Optional[RedisSessionManager] = None


def get_redis_session_manager(
    redis_url: Optional[str] = None,
    **kwargs
) -> RedisSessionManager:
    """Get or create the global Redis session manager instance"""
    global _redis_session_manager
    
    if _redis_session_manager is None:
        _redis_session_manager = RedisSessionManager(redis_url=redis_url, **kwargs)
    
    return _redis_session_manager


async def cleanup_redis_session_manager():
    """Cleanup the global Redis session manager"""
    global _redis_session_manager
    
    if _redis_session_manager:
        await _redis_session_manager.shutdown()
        _redis_session_manager = None