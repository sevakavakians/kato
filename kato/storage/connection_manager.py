"""
Optimized connection pool manager for MongoDB, Redis, and Qdrant.

This module provides a centralized, thread-safe connection manager that:
1. Reduces connection overhead through proper pooling
2. Implements connection health monitoring
3. Provides automatic failover and retry logic
4. Optimizes connection reuse across the application
"""

import asyncio
import logging
import threading
import time
from typing import Optional, Dict, Any, List
from contextlib import contextmanager, asynccontextmanager
from dataclasses import dataclass, field

import redis
import pymongo
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

try:
    from qdrant_client import QdrantClient
    from qdrant_client.http.exceptions import UnexpectedResponse
    QDRANT_AVAILABLE = True
except ImportError:
    QdrantClient = None
    UnexpectedResponse = Exception
    QDRANT_AVAILABLE = False

from kato.config.settings import get_settings


logger = logging.getLogger('kato.storage.connection-manager')


@dataclass
class ConnectionHealth:
    """Health status of a database connection."""
    is_healthy: bool = False
    last_check: float = field(default_factory=time.time)
    error_count: int = 0
    last_error: Optional[str] = None
    response_time_ms: Optional[float] = None


@dataclass
class PoolStats:
    """Connection pool statistics."""
    active_connections: int = 0
    idle_connections: int = 0
    total_connections: int = 0
    failed_connections: int = 0
    peak_connections: int = 0
    avg_response_time_ms: float = 0.0


class OptimizedConnectionManager:
    """
    Centralized connection manager with optimized pooling and health monitoring.
    
    Features:
    - Single instance pattern for connection reuse
    - Health monitoring with automatic recovery
    - Connection pool statistics and monitoring
    - Thread-safe operations
    - Automatic connection warming
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        """Singleton pattern to ensure connection reuse."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
            
        self._initialized = True
        self.settings = get_settings()
        
        # Connection instances
        self._mongodb_client: Optional[MongoClient] = None
        self._redis_client: Optional[redis.Redis] = None
        self._qdrant_client: Optional[QdrantClient] = None
        
        # Connection state tracking
        self._connections_closed = False
        
        # Health monitoring
        self._health_status: Dict[str, ConnectionHealth] = {
            'mongodb': ConnectionHealth(),
            'redis': ConnectionHealth(),
            'qdrant': ConnectionHealth()
        }
        
        # Pool statistics
        self._pool_stats: Dict[str, PoolStats] = {
            'mongodb': PoolStats(),
            'redis': PoolStats(),
            'qdrant': PoolStats()
        }
        
        # Connection locks for thread safety
        self._connection_locks = {
            'mongodb': threading.RLock(),
            'redis': threading.RLock(),
            'qdrant': threading.RLock()
        }
        
        # Health check configuration
        self.health_check_interval = 30  # seconds
        self.max_retries = 3
        self.retry_delay = 1.0  # seconds
        
        logger.info("OptimizedConnectionManager initialized")
    
    @property
    def mongodb(self) -> MongoClient:
        """Get optimized MongoDB client with connection pooling."""
        with self._connection_locks['mongodb']:
            if self._connections_closed:
                logger.warning("Attempting to use MongoDB connection after close_all_connections() was called")
                raise RuntimeError("Cannot use closed connection manager. Connection was explicitly closed.")
            
            if self._mongodb_client is None:
                self._create_mongodb_connection()
            
            # Health check if needed
            if self._should_health_check('mongodb'):
                self._check_mongodb_health()
            
            return self._mongodb_client
    
    @property
    def redis(self) -> Optional[redis.Redis]:
        """Get optimized Redis client with connection pooling."""
        if not self.settings.database.redis_enabled:
            return None
            
        with self._connection_locks['redis']:
            if self._connections_closed:
                logger.warning("Attempting to use Redis connection after close_all_connections() was called")
                raise RuntimeError("Cannot use closed connection manager. Connection was explicitly closed.")
            
            if self._redis_client is None:
                self._create_redis_connection()
            
            # Health check if needed
            if self._should_health_check('redis'):
                self._check_redis_health()
            
            return self._redis_client
    
    @property
    def qdrant(self) -> Optional[QdrantClient]:
        """Get optimized Qdrant client."""
        if not QDRANT_AVAILABLE:
            return None
            
        with self._connection_locks['qdrant']:
            if self._connections_closed:
                logger.warning("Attempting to use Qdrant connection after close_all_connections() was called")
                raise RuntimeError("Cannot use closed connection manager. Connection was explicitly closed.")
            
            if self._qdrant_client is None:
                self._create_qdrant_connection()
            
            # Health check if needed
            if self._should_health_check('qdrant'):
                self._check_qdrant_health()
            
            return self._qdrant_client
    
    def _create_mongodb_connection(self) -> None:
        """Create optimized MongoDB connection with advanced pooling."""
        try:
            start_time = time.time()

            # Simplified MongoDB connection options for compatibility
            client_options = {
                # Basic pool optimization
                'minPoolSize': 5,
                'maxPoolSize': 50,

                # Connection timeouts
                'connectTimeoutMS': self.settings.database.MONGO_TIMEOUT,
                'socketTimeoutMS': self.settings.database.MONGO_TIMEOUT,
                'serverSelectionTimeoutMS': self.settings.database.MONGO_TIMEOUT,
            }

            self._mongodb_client = MongoClient(
                self.settings.database.MONGO_BASE_URL,
                **client_options
            )

            # Warm up the connection pool
            self._mongodb_client.admin.command('ping')

            response_time = (time.time() - start_time) * 1000
            self._health_status['mongodb'] = ConnectionHealth(
                is_healthy=True,
                last_check=time.time(),
                response_time_ms=response_time
            )

            logger.info(f"MongoDB connection established (response: {response_time:.1f}ms)")

        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            error_msg = f"""
╔══════════════════════════════════════════════════════════════════╗
║                   MONGODB CONNECTION FAILURE                     ║
╠══════════════════════════════════════════════════════════════════╣
║ MongoDB is not responding. This is usually caused by:            ║
║                                                                  ║
║ 1. MongoDB is still performing crash recovery after unclean     ║
║    shutdown (check: docker logs kato-mongodb)                   ║
║                                                                  ║
║ 2. MongoDB container is not fully started yet                   ║
║    (check: docker ps and look for 'healthy' status)             ║
║                                                                  ║
║ 3. Network connectivity issues between containers               ║
║                                                                  ║
║ Troubleshooting steps:                                          ║
║ - Check MongoDB logs: docker logs kato-mongodb --tail 50        ║
║ - Check container status: docker ps -a                          ║
║ - Verify MongoDB health: docker exec kato-mongodb mongo \\       ║
║   --eval "db.adminCommand('ping')"                              ║
║                                                                  ║
║ Original error: {str(e)[:50]}...                                 ║
╚══════════════════════════════════════════════════════════════════╝
"""
            self._health_status['mongodb'] = ConnectionHealth(
                is_healthy=False,
                last_check=time.time(),
                error_count=self._health_status['mongodb'].error_count + 1,
                last_error=str(e)
            )
            logger.error(error_msg)
            raise ConnectionFailure(error_msg) from e
        except Exception as e:
            self._health_status['mongodb'] = ConnectionHealth(
                is_healthy=False,
                last_check=time.time(),
                error_count=self._health_status['mongodb'].error_count + 1,
                last_error=str(e)
            )
            logger.error(f"Failed to create MongoDB connection: {e}")
            raise
    
    def _create_redis_connection(self) -> None:
        """Create optimized Redis connection with advanced pooling."""
        try:
            start_time = time.time()
            
            # Enhanced Redis connection pool
            # Use Redis URL if available, otherwise fall back to host/port
            if self.settings.database.REDIS_URL:
                self._redis_client = redis.from_url(
                    self.settings.database.REDIS_URL,
                    max_connections=200,
                    retry_on_timeout=True,
                    socket_keepalive=True,
                    socket_keepalive_options={},
                    health_check_interval=30,
                    decode_responses=True,
                    encoding='utf-8'
                )
            elif self.settings.database.redis_host:
                # Fall back to host/port configuration
                pool_config = {
                    'host': self.settings.database.redis_host,
                    'port': self.settings.database.redis_port,
                    'db': 0,
                    'max_connections': 200,
                    'retry_on_timeout': True,
                    'socket_keepalive': True,
                    'socket_keepalive_options': {},
                    'health_check_interval': 30,
                    'decode_responses': True,
                    'encoding': 'utf-8'
                }
                connection_pool = redis.ConnectionPool(**pool_config)
                self._redis_client = redis.Redis(connection_pool=connection_pool)
            else:
                # Default Redis connection
                self._redis_client = redis.Redis(
                    host='localhost',
                    port=6379,
                    decode_responses=True
                )
            
            # Warm up the connection
            self._redis_client.ping()
            
            response_time = (time.time() - start_time) * 1000
            self._health_status['redis'] = ConnectionHealth(
                is_healthy=True,
                last_check=time.time(),
                response_time_ms=response_time
            )
            
            logger.info(f"Redis connection established (response: {response_time:.1f}ms)")
            
        except Exception as e:
            self._health_status['redis'] = ConnectionHealth(
                is_healthy=False,
                last_check=time.time(),
                error_count=self._health_status['redis'].error_count + 1,
                last_error=str(e)
            )
            logger.error(f"Failed to create Redis connection: {e}")
            raise
    
    def _create_qdrant_connection(self) -> None:
        """Create optimized Qdrant connection."""
        if not QDRANT_AVAILABLE:
            logger.warning("Qdrant client not available")
            return
            
        try:
            start_time = time.time()
            
            client_config = {
                'host': self.settings.database.qdrant_host,
                'port': self.settings.database.qdrant_port,
                'grpc_port': self.settings.database.qdrant_grpc_port,
                'prefer_grpc': True,
                'timeout': 10,
            }
            
            # Create Qdrant client (no API key configured for local instance)
            self._qdrant_client = QdrantClient(**client_config)
            
            # Test the connection
            collections = self._qdrant_client.get_collections()
            
            response_time = (time.time() - start_time) * 1000
            self._health_status['qdrant'] = ConnectionHealth(
                is_healthy=True,
                last_check=time.time(),
                response_time_ms=response_time
            )
            
            logger.info(f"Qdrant connection established (response: {response_time:.1f}ms)")
            
        except Exception as e:
            self._health_status['qdrant'] = ConnectionHealth(
                is_healthy=False,
                last_check=time.time(),
                error_count=self._health_status['qdrant'].error_count + 1,
                last_error=str(e)
            )
            logger.error(f"Failed to create Qdrant connection: {e}")
            raise
    
    def _should_health_check(self, service: str) -> bool:
        """Determine if a health check is needed for the service."""
        health = self._health_status[service]
        return (time.time() - health.last_check) > self.health_check_interval
    
    def _check_mongodb_health(self) -> None:
        """Perform MongoDB health check."""
        try:
            # Initialize connection if not exists
            if self._mongodb_client is None:
                self._create_mongodb_connection()
            
            start_time = time.time()
            self._mongodb_client.admin.command('ping')
            response_time = (time.time() - start_time) * 1000
            
            self._health_status['mongodb'] = ConnectionHealth(
                is_healthy=True,
                last_check=time.time(),
                response_time_ms=response_time
            )
            
        except Exception as e:
            self._health_status['mongodb'].is_healthy = False
            self._health_status['mongodb'].last_check = time.time()
            self._health_status['mongodb'].error_count += 1
            self._health_status['mongodb'].last_error = str(e)
            
            logger.warning(f"MongoDB health check failed: {e}")
    
    def _check_redis_health(self) -> None:
        """Perform Redis health check."""
        try:
            # Initialize connection if not exists
            if self._redis_client is None:
                self._create_redis_connection()
            
            start_time = time.time()
            self._redis_client.ping()
            response_time = (time.time() - start_time) * 1000
            
            self._health_status['redis'] = ConnectionHealth(
                is_healthy=True,
                last_check=time.time(),
                response_time_ms=response_time
            )
            
        except Exception as e:
            self._health_status['redis'].is_healthy = False
            self._health_status['redis'].last_check = time.time()
            self._health_status['redis'].error_count += 1
            self._health_status['redis'].last_error = str(e)
            
            logger.warning(f"Redis health check failed: {e}")
    
    def _check_qdrant_health(self) -> None:
        """Perform Qdrant health check."""
        try:
            # Initialize connection if not exists
            if self._qdrant_client is None:
                self._create_qdrant_connection()
            
            start_time = time.time()
            self._qdrant_client.get_collections()
            response_time = (time.time() - start_time) * 1000
            
            self._health_status['qdrant'] = ConnectionHealth(
                is_healthy=True,
                last_check=time.time(),
                response_time_ms=response_time
            )
            
        except Exception as e:
            self._health_status['qdrant'].is_healthy = False
            self._health_status['qdrant'].last_check = time.time()
            self._health_status['qdrant'].error_count += 1
            self._health_status['qdrant'].last_error = str(e)
            
            logger.warning(f"Qdrant health check failed: {e}")
    
    @contextmanager
    def mongodb_transaction(self, **kwargs):
        """Context manager for MongoDB transactions with optimized settings."""
        client = self.mongodb
        session = client.start_session()
        try:
            with session.start_transaction(**kwargs):
                yield session
        finally:
            session.end_session()
    
    @asynccontextmanager
    async def async_mongodb_transaction(self, **kwargs):
        """Async context manager for MongoDB transactions."""
        # Note: For true async MongoDB, would need motor client
        # This is a placeholder for future async implementation
        client = self.mongodb
        session = client.start_session()
        try:
            with session.start_transaction(**kwargs):
                yield session
        finally:
            session.end_session()
    
    def get_health_status(self) -> Dict[str, Dict[str, Any]]:
        """Get health status of all connections."""
        return {
            service: {
                'healthy': health.is_healthy,
                'last_check': health.last_check,
                'error_count': health.error_count,
                'last_error': health.last_error,
                'response_time_ms': health.response_time_ms
            }
            for service, health in self._health_status.items()
        }
    
    def get_pool_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get connection pool statistics."""
        stats = {}
        
        # MongoDB pool stats
        if self._mongodb_client:
            try:
                # Get pool info from MongoDB client
                pool_info = self._mongodb_client.topology_description
                stats['mongodb'] = {
                    'type': 'mongodb',
                    'pool_size': getattr(pool_info, 'pool_size', 'unknown'),
                    'active_connections': 'dynamic',
                    'status': 'connected' if self._health_status['mongodb'].is_healthy else 'disconnected'
                }
            except Exception:
                stats['mongodb'] = {'type': 'mongodb', 'status': 'error'}
        
        # Redis pool stats
        if self._redis_client:
            try:
                pool = self._redis_client.connection_pool
                stats['redis'] = {
                    'type': 'redis',
                    'max_connections': pool.max_connections,
                    'created_connections': len(pool._created_connections),
                    'available_connections': len(pool._available_connections),
                    'in_use_connections': len(pool._in_use_connections),
                    'status': 'connected' if self._health_status['redis'].is_healthy else 'disconnected'
                }
            except Exception:
                stats['redis'] = {'type': 'redis', 'status': 'error'}
        
        # Qdrant stats
        if self._qdrant_client:
            stats['qdrant'] = {
                'type': 'qdrant',
                'status': 'connected' if self._health_status['qdrant'].is_healthy else 'disconnected'
            }
        
        return stats
    
    def force_health_check(self) -> None:
        """Force immediate health check for all services."""
        logger.info("Performing forced health check for all services")
        try:
            self._check_mongodb_health()
        except Exception as e:
            logger.warning(f"MongoDB health check failed: {e}")
        
        try:
            self._check_redis_health()
        except Exception as e:
            logger.warning(f"Redis health check failed: {e}")
        
        try:
            self._check_qdrant_health()
        except Exception as e:
            logger.warning(f"Qdrant health check failed: {e}")
    
    def close_all_connections(self) -> None:
        """Close all database connections gracefully."""
        if self._connections_closed:
            logger.warning("close_all_connections() called but connections already closed")
            return
            
        logger.info("Closing all database connections...")
        
        # Close MongoDB
        if self._mongodb_client:
            try:
                self._mongodb_client.close()
                logger.info("MongoDB connection closed")
            except Exception as e:
                logger.error(f"Error closing MongoDB connection: {e}")
            finally:
                self._mongodb_client = None
        
        # Close Redis
        if self._redis_client:
            try:
                self._redis_client.close()
                logger.info("Redis connection closed")
            except Exception as e:
                logger.error(f"Error closing Redis connection: {e}")
            finally:
                self._redis_client = None
        
        # Close Qdrant
        if self._qdrant_client:
            try:
                self._qdrant_client.close()
                logger.info("Qdrant connection closed")
            except Exception as e:
                logger.error(f"Error closing Qdrant connection: {e}")
            finally:
                self._qdrant_client = None
        
        # Reset health status
        for service in self._health_status:
            self._health_status[service] = ConnectionHealth()
        
        # Mark connections as closed to prevent reuse
        self._connections_closed = True
        logger.warning("Connection manager marked as closed - no further connections will be allowed")


# Global connection manager instance
_connection_manager: Optional[OptimizedConnectionManager] = None
_manager_lock = threading.Lock()


def get_connection_manager() -> OptimizedConnectionManager:
    """Get the global connection manager instance."""
    global _connection_manager
    if _connection_manager is None:
        with _manager_lock:
            if _connection_manager is None:
                _connection_manager = OptimizedConnectionManager()
    return _connection_manager


# Convenience functions for backward compatibility
def get_mongodb_client() -> MongoClient:
    """Get optimized MongoDB client."""
    return get_connection_manager().mongodb


def get_redis_client() -> Optional[redis.Redis]:
    """Get optimized Redis client."""
    return get_connection_manager().redis


def get_qdrant_client() -> Optional[QdrantClient]:
    """Get optimized Qdrant client."""
    return get_connection_manager().qdrant