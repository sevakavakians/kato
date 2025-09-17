"""
Redis-based session storage for KATO v2.0

Provides persistent session storage with serialization/deserialization
that survives service restarts and enables horizontal scaling.
"""

import asyncio
import json
import logging
import pickle
import time
from datetime import datetime
from typing import Dict, List, Optional, Any, Union
from dataclasses import asdict

import redis.asyncio as redis
from redis.asyncio import Redis

from .session_manager import SessionState

logger = logging.getLogger('kato.v2.sessions.redis_store')


class RedisSessionStore:
    """
    Redis-based persistent session storage.
    
    Features:
    - Automatic serialization/deserialization of SessionState objects
    - TTL-based expiration aligned with session expiration
    - Atomic operations for thread safety
    - Connection pooling and reconnection
    - Configurable serialization (JSON for readability, Pickle for performance)
    """
    
    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        key_prefix: str = "kato:session:",
        serialization: str = "pickle",  # "json" or "pickle"
        connection_pool_size: int = 10
    ):
        """
        Initialize Redis session store.
        
        Args:
            redis_url: Redis connection URL
            key_prefix: Prefix for session keys in Redis
            serialization: Serialization method ("json" or "pickle")
            connection_pool_size: Size of Redis connection pool
        """
        self.redis_url = redis_url
        self.key_prefix = key_prefix
        self.serialization = serialization
        self.connection_pool_size = connection_pool_size
        
        # Connection pool and client
        self.pool = None
        self.redis_client: Optional[Redis] = None
        self._connected = False
        
        logger.info(f"RedisSessionStore initialized with {serialization} serialization")
    
    async def connect(self):
        """Establish Redis connection"""
        if self._connected:
            return
        
        try:
            # Create connection pool
            self.pool = redis.ConnectionPool.from_url(
                self.redis_url,
                max_connections=self.connection_pool_size,
                retry_on_timeout=True,
                socket_keepalive=True,
                socket_keepalive_options={},
                health_check_interval=30
            )
            
            # Create client
            self.redis_client = Redis(
                connection_pool=self.pool,
                decode_responses=False  # We'll handle encoding ourselves
            )
            
            # Test connection
            await self.redis_client.ping()
            
            self._connected = True
            logger.info("Redis session store connected successfully")
            
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise
    
    async def disconnect(self):
        """Close Redis connection"""
        if self.redis_client:
            await self.redis_client.close()
        if self.pool:
            await self.pool.disconnect()
        
        self._connected = False
        logger.info("Redis session store disconnected")
    
    def _get_session_key(self, session_id: str) -> str:
        """Generate Redis key for session"""
        return f"{self.key_prefix}{session_id}"
    
    def _serialize_session(self, session: SessionState) -> bytes:
        """Serialize SessionState to bytes"""
        if self.serialization == "json":
            # JSON serialization (human readable but limited types)
            data = asdict(session)
            # Convert datetime objects to ISO strings BEFORE JSON serialization
            for field in ['created_at', 'last_accessed', 'expires_at']:
                if field in data and hasattr(data[field], 'isoformat'):
                    data[field] = data[field].isoformat()
            
            # Also handle datetime in nested user_config
            if 'user_config' in data and isinstance(data['user_config'], dict):
                for field in ['created_at', 'updated_at']:
                    if field in data['user_config'] and hasattr(data['user_config'][field], 'isoformat'):
                        data['user_config'][field] = data['user_config'][field].isoformat()
            
            return json.dumps(data).encode('utf-8')
        else:
            # Pickle serialization (full Python object support)
            return pickle.dumps(session)
    
    def _deserialize_session(self, data: bytes) -> SessionState:
        """Deserialize bytes to SessionState"""
        if self.serialization == "json":
            # JSON deserialization
            data_dict = json.loads(data.decode('utf-8'))
            # Convert ISO strings back to datetime objects
            data_dict['created_at'] = datetime.fromisoformat(data_dict['created_at'])
            data_dict['last_accessed'] = datetime.fromisoformat(data_dict['last_accessed'])
            data_dict['expires_at'] = datetime.fromisoformat(data_dict['expires_at'])
            
            # Also handle datetime in nested user_config
            if 'user_config' in data_dict and isinstance(data_dict['user_config'], dict):
                for field in ['created_at', 'updated_at']:
                    if field in data_dict['user_config'] and isinstance(data_dict['user_config'][field], str):
                        data_dict['user_config'][field] = datetime.fromisoformat(data_dict['user_config'][field])
            
            # Reconstruct SessionState
            return SessionState(**data_dict)
        else:
            # Pickle deserialization
            return pickle.loads(data)
    
    async def store_session(self, session: SessionState) -> bool:
        """
        Store session in Redis with TTL.
        
        Args:
            session: SessionState to store
            
        Returns:
            True if stored successfully
        """
        if not self._connected:
            await self.connect()
        
        try:
            key = self._get_session_key(session.session_id)
            serialized = self._serialize_session(session)
            
            # Calculate TTL in seconds
            now = datetime.utcnow()
            ttl_seconds = max(1, int((session.expires_at - now).total_seconds()))
            
            # Store with TTL
            await self.redis_client.setex(key, ttl_seconds, serialized)
            
            logger.debug(f"Stored session {session.session_id} with TTL {ttl_seconds}s")
            return True
            
        except Exception as e:
            logger.error(f"Failed to store session {session.session_id}: {e}")
            return False
    
    async def get_session(self, session_id: str) -> Optional[SessionState]:
        """
        Retrieve session from Redis.
        
        Args:
            session_id: Session identifier
            
        Returns:
            SessionState if found and not expired, None otherwise
        """
        if not self._connected:
            await self.connect()
        
        try:
            key = self._get_session_key(session_id)
            serialized = await self.redis_client.get(key)
            
            if not serialized:
                logger.debug(f"Session {session_id} not found in Redis")
                return None
            
            session = self._deserialize_session(serialized)
            
            # Double-check expiration (Redis TTL should handle this, but be safe)
            if session.is_expired():
                logger.info(f"Session {session_id} expired, removing")
                await self.delete_session(session_id)
                return None
            
            return session
            
        except Exception as e:
            logger.error(f"Failed to get session {session_id}: {e}")
            return None
    
    async def delete_session(self, session_id: str) -> bool:
        """
        Delete session from Redis.
        
        Args:
            session_id: Session identifier
            
        Returns:
            True if deleted or didn't exist, False on error
        """
        if not self._connected:
            await self.connect()
        
        try:
            key = self._get_session_key(session_id)
            result = await self.redis_client.delete(key)
            
            logger.debug(f"Deleted session {session_id} (existed: {bool(result)})")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete session {session_id}: {e}")
            return False
    
    async def extend_session(self, session_id: str, ttl_seconds: int) -> bool:
        """
        Extend session TTL in Redis.
        
        Args:
            session_id: Session identifier
            ttl_seconds: New TTL from now
            
        Returns:
            True if extended, False if session not found or error
        """
        if not self._connected:
            await self.connect()
        
        try:
            key = self._get_session_key(session_id)
            
            # Check if session exists
            if not await self.redis_client.exists(key):
                return False
            
            # Update TTL
            result = await self.redis_client.expire(key, ttl_seconds)
            
            if result:
                logger.debug(f"Extended session {session_id} TTL to {ttl_seconds}s")
                return True
            else:
                logger.warning(f"Failed to extend session {session_id} - key may have expired")
                return False
                
        except Exception as e:
            logger.error(f"Failed to extend session {session_id}: {e}")
            return False
    
    async def list_active_sessions(self) -> List[str]:
        """
        Get list of active session IDs.
        
        Returns:
            List of session IDs currently in Redis
        """
        if not self._connected:
            await self.connect()
        
        try:
            pattern = f"{self.key_prefix}*"
            session_keys = []
            
            # Use scan for better performance with many keys
            cursor = 0
            while True:
                cursor, keys = await self.redis_client.scan(
                    cursor, match=pattern, count=100
                )
                session_keys.extend(keys)
                if cursor == 0:
                    break
            
            # Extract session IDs from keys
            session_ids = [
                key.decode('utf-8').replace(self.key_prefix, '')
                for key in session_keys
            ]
            
            return session_ids
            
        except Exception as e:
            logger.error(f"Failed to list sessions: {e}")
            return []
    
    async def get_session_count(self) -> int:
        """
        Get count of active sessions.
        
        Returns:
            Number of sessions currently in Redis
        """
        sessions = await self.list_active_sessions()
        return len(sessions)
    
    async def cleanup_expired_sessions(self) -> int:
        """
        Cleanup expired sessions (Redis should handle this automatically via TTL).
        
        Returns:
            Number of sessions cleaned up (usually 0 since Redis handles TTL)
        """
        # Redis handles TTL automatically, but we can scan for any sessions
        # that might have expired but not been cleaned up yet
        if not self._connected:
            await self.connect()
        
        try:
            session_ids = await self.list_active_sessions()
            expired_count = 0
            
            # Check each session for manual expiration (belt and suspenders)
            for session_id in session_ids:
                session = await self.get_session(session_id)
                if session and session.is_expired():
                    await self.delete_session(session_id)
                    expired_count += 1
            
            if expired_count > 0:
                logger.info(f"Manually cleaned up {expired_count} expired sessions")
            
            return expired_count
            
        except Exception as e:
            logger.error(f"Failed to cleanup expired sessions: {e}")
            return 0
    
    async def health_check(self) -> bool:
        """
        Check Redis connection health.
        
        Returns:
            True if Redis is accessible, False otherwise
        """
        try:
            if not self._connected:
                await self.connect()
            
            await self.redis_client.ping()
            return True
            
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            return False
    
    async def get_redis_info(self) -> Dict[str, Any]:
        """
        Get Redis server information for monitoring.
        
        Returns:
            Dictionary with Redis server stats
        """
        if not self._connected:
            await self.connect()
        
        try:
            info = await self.redis_client.info()
            session_count = await self.get_session_count()
            
            return {
                "connected": True,
                "redis_version": info.get("redis_version"),
                "used_memory": info.get("used_memory"),
                "used_memory_human": info.get("used_memory_human"),
                "connected_clients": info.get("connected_clients"),
                "total_commands_processed": info.get("total_commands_processed"),
                "keyspace": info.get("keyspace", {}),
                "session_count": session_count
            }
            
        except Exception as e:
            logger.error(f"Failed to get Redis info: {e}")
            return {"connected": False, "error": str(e)}


# Global Redis session store instance (singleton pattern)
_redis_store: Optional[RedisSessionStore] = None


def get_redis_session_store(
    redis_url: str = "redis://localhost:6379",
    **kwargs
) -> RedisSessionStore:
    """Get or create the global Redis session store instance"""
    global _redis_store
    
    if _redis_store is None:
        _redis_store = RedisSessionStore(redis_url=redis_url, **kwargs)
    
    return _redis_store


async def cleanup_redis_session_store():
    """Cleanup the global Redis session store"""
    global _redis_store
    
    if _redis_store:
        await _redis_store.disconnect()
        _redis_store = None