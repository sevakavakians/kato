"""
Database Connection Pooling for KATO v2.0

Provides reliable connection pooling for MongoDB and Qdrant with:
- Connection pool management
- Health checks
- Automatic reconnection
- Proper write concerns
"""

import asyncio
import logging
import time
from typing import Optional, Dict, Any
from pymongo import MongoClient, WriteConcern
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
from dataclasses import dataclass

logger = logging.getLogger('kato.v2.resilience.connection_pool')


@dataclass
class PoolConfig:
    """Configuration for connection pools"""
    # MongoDB settings
    mongo_url: str = "mongodb://localhost:27017"
    mongo_max_pool_size: int = 50
    mongo_min_pool_size: int = 10
    mongo_max_idle_time_ms: int = 30000
    mongo_wait_queue_timeout_ms: int = 5000
    mongo_server_selection_timeout_ms: int = 5000
    
    # Qdrant settings
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_pool_size: int = 20
    qdrant_timeout: int = 10
    
    # Health check settings
    health_check_interval: int = 5  # seconds


class MongoConnectionPool:
    """
    Production-grade MongoDB connection pool with reliability features.
    
    Key improvements over v1.0:
    - Connection pooling instead of single connection
    - Write concern = majority (not 0)
    - Health checks and automatic reconnection
    - Proper timeouts and error handling
    """
    
    def __init__(self, config: PoolConfig):
        """
        Initialize MongoDB connection pool.
        
        Args:
            config: Pool configuration
        """
        self.config = config
        self.client: Optional[MongoClient] = None
        self.last_health_check = 0
        self.connection_failures = 0
        self._initialize_client()
    
    def _initialize_client(self):
        """Initialize MongoDB client with production settings"""
        try:
            self.client = MongoClient(
                self.config.mongo_url,
                
                # Connection Pool Settings
                maxPoolSize=self.config.mongo_max_pool_size,
                minPoolSize=self.config.mongo_min_pool_size,
                maxIdleTimeMS=self.config.mongo_max_idle_time_ms,
                waitQueueTimeoutMS=self.config.mongo_wait_queue_timeout_ms,
                
                # Connection Settings
                connectTimeoutMS=5000,
                socketTimeoutMS=10000,
                serverSelectionTimeoutMS=self.config.mongo_server_selection_timeout_ms,
                heartbeatFrequencyMS=10000,
                
                # Retry Settings
                retryWrites=True,
                retryReads=True,
                
                # CRITICAL: Write Concern for data durability
                w='majority',  # Ensure majority acknowledgment
                wtimeout=5000,
                journal=True,  # Ensure write to journal
                
                # Read Preference
                readPreference='primaryPreferred',
                
                # Application identification
                appname='kato-v2',
                
                # Compression
                compressors=['zstd', 'snappy', 'zlib']
            )
            
            # Test connection
            self.client.admin.command('ping')
            self.connection_failures = 0
            logger.info("MongoDB connection pool initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize MongoDB connection pool: {e}")
            self.connection_failures += 1
            raise
    
    def get_database(self, name: str, ensure_healthy: bool = True):
        """
        Get database instance with optional health check.
        
        Args:
            name: Database name
            ensure_healthy: Whether to check health before returning
        
        Returns:
            MongoDB database instance
        
        Raises:
            ConnectionFailure: If connection is unhealthy
        """
        if ensure_healthy:
            self._ensure_healthy()
        
        if not self.client:
            raise ConnectionFailure("MongoDB client not initialized")
        
        return self.client[name]
    
    def _ensure_healthy(self):
        """Ensure connection is healthy, attempt reconnection if needed"""
        now = time.time()
        
        # Check if we need a health check
        if now - self.last_health_check < self.config.health_check_interval:
            return
        
        try:
            # Ping to check connection
            if self.client:
                self.client.admin.command('ping')
                self.last_health_check = now
                self.connection_failures = 0
        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            logger.warning(f"MongoDB health check failed: {e}")
            self.connection_failures += 1
            
            # Attempt reconnection
            if self.connection_failures > 3:
                logger.info("Attempting MongoDB reconnection...")
                self._reconnect()
    
    def _reconnect(self):
        """Attempt to reconnect to MongoDB"""
        try:
            # Close existing connection if any
            if self.client:
                try:
                    self.client.close()
                except:
                    pass
            
            # Reinitialize
            self._initialize_client()
            logger.info("MongoDB reconnection successful")
            
        except Exception as e:
            logger.error(f"MongoDB reconnection failed: {e}")
            raise ConnectionFailure(f"Cannot reconnect to MongoDB: {e}")
    
    def get_write_concern(self, level: str = "majority") -> WriteConcern:
        """
        Get appropriate write concern for operation type.
        
        Args:
            level: Write concern level ('majority', 'acknowledged', 'unacknowledged')
        
        Returns:
            WriteConcern object
        """
        if level == "majority":
            # Critical data - wait for majority
            return WriteConcern(w='majority', j=True, wtimeout=5000)
        elif level == "acknowledged":
            # Normal data - wait for primary
            return WriteConcern(w=1, j=True, wtimeout=3000)
        else:
            # Metrics/logs - can be fire-and-forget
            return WriteConcern(w=0)
    
    def get_pool_stats(self) -> Dict[str, Any]:
        """Get connection pool statistics"""
        if not self.client:
            return {"status": "disconnected"}
        
        try:
            # Get server info
            server_info = self.client.server_info()
            
            return {
                "status": "connected",
                "version": server_info.get('version'),
                "connections": {
                    "max_pool_size": self.config.mongo_max_pool_size,
                    "min_pool_size": self.config.mongo_min_pool_size
                },
                "failures": self.connection_failures,
                "last_health_check": self.last_health_check
            }
        except:
            return {"status": "unhealthy", "failures": self.connection_failures}
    
    def close(self):
        """Close all connections in the pool"""
        if self.client:
            try:
                self.client.close()
                logger.info("MongoDB connection pool closed")
            except Exception as e:
                logger.error(f"Error closing MongoDB connection pool: {e}")


class QdrantConnectionPool:
    """
    Connection pool for Qdrant vector database.
    
    Provides:
    - Connection pooling
    - Health checks
    - Automatic reconnection
    """
    
    def __init__(self, config: PoolConfig):
        """
        Initialize Qdrant connection pool.
        
        Args:
            config: Pool configuration
        """
        self.config = config
        self.clients = []
        self.available = asyncio.Queue(maxsize=config.qdrant_pool_size)
        self._initialized = False
    
    async def initialize(self):
        """Initialize the connection pool"""
        if self._initialized:
            return
        
        try:
            # Import Qdrant client
            from qdrant_client import QdrantClient
            
            # Create pool of clients
            for i in range(self.config.qdrant_pool_size):
                client = QdrantClient(
                    host=self.config.qdrant_host,
                    port=self.config.qdrant_port,
                    timeout=self.config.qdrant_timeout,
                    grpc_port=6334,
                    prefer_grpc=True,
                    grpc_options={
                        'grpc.keepalive_time_ms': 10000,
                        'grpc.keepalive_timeout_ms': 5000,
                        'grpc.keepalive_permit_without_calls': True,
                    }
                )
                
                self.clients.append(client)
                await self.available.put(client)
            
            self._initialized = True
            logger.info(f"Qdrant connection pool initialized with {self.config.qdrant_pool_size} connections")
            
        except Exception as e:
            logger.error(f"Failed to initialize Qdrant connection pool: {e}")
            raise
    
    async def get_client(self):
        """
        Get a client from the pool.
        
        Returns:
            QdrantClient instance
        
        Raises:
            ConnectionFailure: If client fails health check
        """
        if not self._initialized:
            await self.initialize()
        
        # Get client from pool (will wait if none available)
        client = await self.available.get()
        
        # Health check the client before returning
        try:
            await self._health_check_client(client)
            return client
        except Exception as e:
            logger.warning(f"Qdrant client failed health check: {e}")
            # Try to recreate the client
            try:
                new_client = await self._recreate_client(client)
                return new_client
            except Exception as recreate_error:
                # Return client to pool anyway to avoid pool depletion
                await self.available.put(client)
                raise ConnectionFailure(f"Qdrant client health check failed and recreation failed: {recreate_error}")
    
    async def return_client(self, client):
        """
        Return a client to the pool.
        
        Args:
            client: QdrantClient to return
        """
        await self.available.put(client)
    
    async def _health_check_client(self, client):
        """
        Perform health check on a Qdrant client.
        
        Args:
            client: QdrantClient to check
        
        Raises:
            Exception: If health check fails
        """
        try:
            # Try to get cluster info as a health check
            cluster_info = client.get_cluster_info()
            if not cluster_info:
                raise Exception("No cluster info returned")
        except Exception as e:
            raise Exception(f"Qdrant health check failed: {e}")
    
    async def _recreate_client(self, old_client):
        """
        Recreate a failed Qdrant client.
        
        Args:
            old_client: Failed QdrantClient to replace
        
        Returns:
            New QdrantClient instance
        """
        try:
            # Import Qdrant client
            from qdrant_client import QdrantClient
            
            # Create new client with same configuration
            new_client = QdrantClient(
                host=self.config.qdrant_host,
                port=self.config.qdrant_port,
                timeout=self.config.qdrant_timeout,
                grpc_port=6334,
                prefer_grpc=True,
                grpc_options={
                    'grpc.keepalive_time_ms': 10000,
                    'grpc.keepalive_timeout_ms': 5000,
                    'grpc.keepalive_permit_without_calls': True,
                }
            )
            
            # Test new client
            await self._health_check_client(new_client)
            
            # Replace in clients list
            if old_client in self.clients:
                index = self.clients.index(old_client)
                self.clients[index] = new_client
            
            logger.info("Successfully recreated Qdrant client")
            return new_client
            
        except Exception as e:
            logger.error(f"Failed to recreate Qdrant client: {e}")
            raise
    
    def get_pool_stats(self) -> Dict[str, Any]:
        """Get connection pool statistics"""
        if not self._initialized:
            return {"status": "not_initialized"}
        
        available_count = self.available.qsize()
        total_count = len(self.clients)
        in_use_count = total_count - available_count
        
        return {
            "status": "initialized",
            "pool_size": self.config.qdrant_pool_size,
            "total_connections": total_count,
            "available_connections": available_count,
            "in_use_connections": in_use_count,
            "host": self.config.qdrant_host,
            "port": self.config.qdrant_port
        }
    
    async def close(self):
        """Close all connections in the pool"""
        while not self.available.empty():
            client = await self.available.get()
            # Qdrant client doesn't need explicit close, but we can clear references
            
        self.clients.clear()
        self._initialized = False
        logger.info("Qdrant connection pool closed")


# Global connection pool instances
_mongo_pool: Optional[MongoConnectionPool] = None
_qdrant_pool: Optional[QdrantConnectionPool] = None


def get_mongo_pool(config: Optional[PoolConfig] = None) -> MongoConnectionPool:
    """
    Get or create the global MongoDB connection pool.
    
    Args:
        config: Optional configuration (uses defaults if not provided)
    
    Returns:
        MongoConnectionPool instance
    """
    global _mongo_pool
    
    if _mongo_pool is None:
        if config is None:
            config = PoolConfig()
        _mongo_pool = MongoConnectionPool(config)
    
    return _mongo_pool


async def get_qdrant_pool(config: Optional[PoolConfig] = None) -> QdrantConnectionPool:
    """
    Get or create the global Qdrant connection pool.
    
    Args:
        config: Optional configuration (uses defaults if not provided)
    
    Returns:
        QdrantConnectionPool instance
    """
    global _qdrant_pool
    
    if _qdrant_pool is None:
        if config is None:
            config = PoolConfig()
        _qdrant_pool = QdrantConnectionPool(config)
        await _qdrant_pool.initialize()
    
    return _qdrant_pool


def cleanup_connection_pools():
    """Cleanup all connection pools"""
    global _mongo_pool, _qdrant_pool
    
    if _mongo_pool:
        _mongo_pool.close()
        _mongo_pool = None
    
    if _qdrant_pool:
        # Try to close async pool, but don't fail if no event loop
        try:
            # Check if there's an event loop running
            try:
                loop = asyncio.get_running_loop()
                asyncio.create_task(_qdrant_pool.close())
            except RuntimeError:
                # No event loop running, just clear the reference
                pass
        except:
            pass
        _qdrant_pool = None
    
    logger.info("All connection pools cleaned up")