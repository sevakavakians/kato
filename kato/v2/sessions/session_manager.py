"""
KATO v2.0 Session Management Implementation

This module provides multi-user session isolation to prevent STM collision.
Each user/session maintains completely isolated state.

Critical requirement: Multiple users must be able to maintain separate STM
sequences without any data collision.
"""

import asyncio
import time
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
import logging

logger = logging.getLogger('kato.v2.sessions.manager')


@dataclass
class SessionState:
    """State for a user session - lightweight connection to user's processor"""
    session_id: str
    user_id: str  # Now required - each user has their own processor
    created_at: datetime
    last_accessed: datetime
    expires_at: datetime
    
    # Session-specific STM state (user's LTM is in their processor)
    stm: List[List[str]] = field(default_factory=list)
    emotives_accumulator: List[Dict[str, float]] = field(default_factory=list)
    time: int = 0
    
    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    access_count: int = 0
    
    # Resource limits
    max_stm_size: int = 1000
    max_emotives_size: int = 1000
    
    def is_expired(self) -> bool:
        """Check if session has expired"""
        return datetime.utcnow() > self.expires_at
    
    def update_access(self):
        """Update last access time and count"""
        self.last_accessed = datetime.utcnow()
        self.access_count += 1
    
    def enforce_limits(self):
        """Enforce resource limits on session data"""
        # Trim STM if too large (keep most recent)
        if len(self.stm) > self.max_stm_size:
            self.stm = self.stm[-self.max_stm_size:]
            logger.warning(f"Session {self.session_id} STM trimmed to {self.max_stm_size} events")
        
        # Trim emotives if too large
        if len(self.emotives_accumulator) > self.max_emotives_size:
            self.emotives_accumulator = self.emotives_accumulator[-self.max_emotives_size:]


class SessionManager:
    """
    Manages user sessions with complete isolation.
    
    This is the core component that enables multiple users to use KATO
    simultaneously without data collision.
    """
    
    def __init__(self, default_ttl_seconds: int = 3600):
        """
        Initialize session manager.
        
        Args:
            default_ttl_seconds: Default session TTL (1 hour)
        """
        self.sessions: Dict[str, SessionState] = {}
        self.default_ttl = default_ttl_seconds
        self.session_locks: Dict[str, asyncio.Lock] = {}
        self._cleanup_task = None
        self._cleanup_interval = 300  # 5 minutes
        
        logger.info(f"SessionManager initialized with {default_ttl_seconds}s default TTL")
    
    async def create_session(
        self,
        user_id: str,  # Now required for processor isolation
        metadata: Optional[Dict[str, Any]] = None,
        ttl_seconds: Optional[int] = None
    ) -> SessionState:
        """
        Create a new isolated session.
        
        Args:
            user_id: User identifier (required for processor isolation)
            metadata: Optional session metadata
            ttl_seconds: Session TTL (uses default if not specified)
        
        Returns:
            New SessionState with unique session_id
        """
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
        
        # Store session
        self.sessions[session_id] = session
        
        # Create session-specific lock
        self.session_locks[session_id] = asyncio.Lock()
        
        logger.info(f"Created session {session_id} for user {user_id} (user has dedicated processor)")
        
        # Start cleanup task if not running
        if not self._cleanup_task:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        
        return session
    
    async def get_session(self, session_id: str) -> Optional[SessionState]:
        """
        Retrieve session by ID.
        
        Args:
            session_id: Session identifier
        
        Returns:
            SessionState if found and not expired, None otherwise
        """
        session = self.sessions.get(session_id)
        
        if not session:
            logger.debug(f"Session {session_id} not found")
            return None
        
        if session.is_expired():
            logger.info(f"Session {session_id} has expired")
            await self.delete_session(session_id)
            return None
        
        # Update access time
        session.update_access()
        
        return session
    
    async def get_session_lock(self, session_id: str) -> Optional[asyncio.Lock]:
        """
        Get the lock for a specific session.
        
        Args:
            session_id: Session identifier
        
        Returns:
            asyncio.Lock for the session, None if session doesn't exist
        """
        if session_id not in self.sessions:
            return None
        
        if session_id not in self.session_locks:
            self.session_locks[session_id] = asyncio.Lock()
        
        return self.session_locks[session_id]
    
    async def update_session(self, session: SessionState) -> bool:
        """
        Update session state.
        
        Args:
            session: Updated SessionState
        
        Returns:
            True if updated, False if session not found
        """
        if session.session_id not in self.sessions:
            return False
        
        # Enforce limits before saving
        session.enforce_limits()
        
        self.sessions[session.session_id] = session
        return True
    
    async def delete_session(self, session_id: str) -> bool:
        """
        Delete a session and cleanup resources.
        
        Args:
            session_id: Session identifier
        
        Returns:
            True if deleted, False if not found
        """
        if session_id not in self.sessions:
            return False
        
        # Remove session
        del self.sessions[session_id]
        
        # Remove lock
        if session_id in self.session_locks:
            del self.session_locks[session_id]
        
        logger.info(f"Deleted session {session_id}")
        return True
    
    async def extend_session(self, session_id: str, ttl_seconds: int) -> bool:
        """
        Extend session expiration.
        
        Args:
            session_id: Session identifier
            ttl_seconds: New TTL from now
        
        Returns:
            True if extended, False if session not found
        """
        session = await self.get_session(session_id)
        if not session:
            return False
        
        session.expires_at = datetime.utcnow() + timedelta(seconds=ttl_seconds)
        logger.info(f"Extended session {session_id} by {ttl_seconds}s")
        return True
    
    async def cleanup_expired_sessions(self) -> int:
        """
        Remove all expired sessions.
        
        Returns:
            Number of sessions cleaned up
        """
        now = datetime.utcnow()
        expired_ids = [
            sid for sid, session in self.sessions.items()
            if session.expires_at < now
        ]
        
        for session_id in expired_ids:
            await self.delete_session(session_id)
        
        if expired_ids:
            logger.info(f"Cleaned up {len(expired_ids)} expired sessions")
        
        return len(expired_ids)
    
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
        """Get count of active (non-expired) sessions"""
        now = datetime.utcnow()
        return sum(
            1 for session in self.sessions.values()
            if session.expires_at > now
        )
    
    def get_session_stats(self) -> Dict[str, Any]:
        """Get statistics about current sessions"""
        now = datetime.utcnow()
        active_sessions = [s for s in self.sessions.values() if s.expires_at > now]
        
        return {
            "total_sessions": len(self.sessions),
            "active_sessions": len(active_sessions),
            "expired_sessions": len(self.sessions) - len(active_sessions),
            "users_with_sessions": len(set(s.user_id for s in active_sessions if s.user_id)),
            "average_stm_size": sum(len(s.stm) for s in active_sessions) / max(len(active_sessions), 1),
            "total_stm_events": sum(len(s.stm) for s in active_sessions)
        }
    
    async def clear_session_stm(self, session_id: str) -> bool:
        """
        Clear the STM for a specific session.
        
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
        logger.info(f"Cleared STM for session {session_id}")
        return True
    
    async def shutdown(self):
        """Cleanup resources on shutdown"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        # Clear all sessions
        self.sessions.clear()
        self.session_locks.clear()
        
        logger.info("SessionManager shutdown complete")


# Global session manager instance (singleton pattern)
_session_manager: Optional[SessionManager] = None


def get_session_manager() -> SessionManager:
    """Get or create the global session manager instance"""
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager


async def cleanup_session_manager():
    """Cleanup the global session manager"""
    global _session_manager
    if _session_manager:
        await _session_manager.shutdown()
        _session_manager = None