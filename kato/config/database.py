"""
Database Configuration Module for KATO

Provides specialized database configurations with connection management,
pooling, and optimization settings for MongoDB, Qdrant, and Redis.
"""

from typing import Optional, Dict, Any, List
from pydantic import Field, validator, SecretStr
try:
    from pydantic_settings import BaseSettings
except ImportError:
    # Fallback for older Pydantic versions
    from pydantic import BaseSettings
from dataclasses import dataclass
import logging

logger = logging.getLogger('kato.config.database')


class MongoDBConfig(BaseSettings):
    """MongoDB-specific configuration with advanced options."""
    
    # Connection settings
    host: str = Field('localhost', env='MONGO_HOST')
    port: int = Field(27017, env='MONGO_PORT', ge=1, le=65535)
    username: Optional[str] = Field(None, env='MONGO_USERNAME')
    password: Optional[SecretStr] = Field(None, env='MONGO_PASSWORD')
    database: str = Field('kato', env='MONGO_DATABASE')
    auth_source: str = Field('admin', env='MONGO_AUTH_SOURCE')
    
    # Connection pool settings
    min_pool_size: int = Field(1, env='MONGO_MIN_POOL_SIZE', ge=0)
    max_pool_size: int = Field(100, env='MONGO_MAX_POOL_SIZE', ge=1)
    max_idle_time_ms: int = Field(10000, env='MONGO_MAX_IDLE_TIME', ge=0)
    wait_queue_timeout_ms: int = Field(10000, env='MONGO_WAIT_QUEUE_TIMEOUT', ge=0)
    
    # Timeout settings
    connect_timeout_ms: int = Field(10000, env='MONGO_CONNECT_TIMEOUT', ge=0)
    socket_timeout_ms: int = Field(30000, env='MONGO_SOCKET_TIMEOUT', ge=0)
    server_selection_timeout_ms: int = Field(30000, env='MONGO_SERVER_SELECTION_TIMEOUT', ge=0)
    
    # Write concern
    write_concern_w: str = Field('majority', env='MONGO_WRITE_CONCERN_W')
    write_concern_j: bool = Field(True, env='MONGO_WRITE_CONCERN_J')
    write_concern_timeout: int = Field(10000, env='MONGO_WRITE_CONCERN_TIMEOUT', ge=0)
    
    # Read preference
    read_preference: str = Field('primary', env='MONGO_READ_PREFERENCE')
    
    # Replica set
    replica_set: Optional[str] = Field(None, env='MONGO_REPLICA_SET')
    
    # SSL/TLS
    tls: bool = Field(False, env='MONGO_TLS')
    tls_allow_invalid_certificates: bool = Field(False, env='MONGO_TLS_ALLOW_INVALID')
    tls_ca_file: Optional[str] = Field(None, env='MONGO_TLS_CA_FILE')
    
    # Compression
    compressors: List[str] = Field(['snappy', 'zlib'], env='MONGO_COMPRESSORS')
    
    @property
    def connection_string(self) -> str:
        """Build MongoDB connection string."""
        if self.username and self.password:
            auth = f"{self.username}:{self.password.get_secret_value()}@"
        else:
            auth = ""
        
        base_url = f"mongodb://{auth}{self.host}:{self.port}"
        
        # Add database and options
        params = []
        if self.replica_set:
            params.append(f"replicaSet={self.replica_set}")
        if self.auth_source != 'admin':
            params.append(f"authSource={self.auth_source}")
        if self.tls:
            params.append("tls=true")
        if self.read_preference != 'primary':
            params.append(f"readPreference={self.read_preference}")
        
        if params:
            return f"{base_url}/?{'&'.join(params)}"
        return base_url
    
    def get_client_options(self) -> Dict[str, Any]:
        """Get PyMongo client options."""
        options = {
            'minPoolSize': self.min_pool_size,
            'maxPoolSize': self.max_pool_size,
            'maxIdleTimeMS': self.max_idle_time_ms,
            'waitQueueTimeoutMS': self.wait_queue_timeout_ms,
            'connectTimeoutMS': self.connect_timeout_ms,
            'socketTimeoutMS': self.socket_timeout_ms,
            'serverSelectionTimeoutMS': self.server_selection_timeout_ms,
            'w': self.write_concern_w,
            'j': self.write_concern_j,
            'wtimeout': self.write_concern_timeout,
            'readPreference': self.read_preference,
            'compressors': self.compressors,
        }
        
        if self.replica_set:
            options['replicaset'] = self.replica_set
        
        if self.tls:
            options['tls'] = True
            options['tlsAllowInvalidCertificates'] = self.tls_allow_invalid_certificates
            if self.tls_ca_file:
                options['tlsCAFile'] = self.tls_ca_file
        
        return options
    
    class Config:
        env_prefix = ''


class QdrantConfig(BaseSettings):
    """Qdrant vector database configuration."""
    
    # Connection settings
    host: str = Field('localhost', env='QDRANT_HOST')
    port: int = Field(6333, env='QDRANT_PORT', ge=1, le=65535)
    grpc_port: int = Field(6334, env='QDRANT_GRPC_PORT', ge=1, le=65535)
    api_key: Optional[SecretStr] = Field(None, env='QDRANT_API_KEY')
    
    # Performance settings
    prefer_grpc: bool = Field(True, env='QDRANT_PREFER_GRPC')
    timeout: int = Field(10, env='QDRANT_TIMEOUT', ge=1)
    
    # Collection settings
    collection_prefix: str = Field('vectors', env='QDRANT_COLLECTION_PREFIX')
    vector_size: int = Field(768, env='QDRANT_VECTOR_SIZE', ge=1)
    distance_metric: str = Field('Cosine', env='QDRANT_DISTANCE')
    
    # Index settings
    index_type: str = Field('hnsw', env='QDRANT_INDEX_TYPE')
    hnsw_m: int = Field(16, env='QDRANT_HNSW_M', ge=4)
    hnsw_ef_construct: int = Field(100, env='QDRANT_HNSW_EF_CONSTRUCT', ge=4)
    hnsw_ef: int = Field(100, env='QDRANT_HNSW_EF', ge=1)
    
    # Storage settings
    on_disk_payload: bool = Field(True, env='QDRANT_ON_DISK_PAYLOAD')
    
    # Optimization settings
    optimizer_deleted_threshold: float = Field(0.2, env='QDRANT_OPTIMIZER_DELETED_THRESHOLD')
    optimizer_vacuum_min_vector_number: int = Field(1000, env='QDRANT_OPTIMIZER_VACUUM_MIN')
    
    @property
    def url(self) -> str:
        """Get Qdrant HTTP URL."""
        return f"http://{self.host}:{self.port}"
    
    @property
    def grpc_url(self) -> str:
        """Get Qdrant gRPC URL."""
        return f"{self.host}:{self.grpc_port}"
    
    def get_client_config(self) -> Dict[str, Any]:
        """Get Qdrant client configuration."""
        config = {
            'host': self.host,
            'port': self.port,
            'grpc_port': self.grpc_port,
            'prefer_grpc': self.prefer_grpc,
            'timeout': self.timeout,
        }
        
        if self.api_key:
            config['api_key'] = self.api_key.get_secret_value()
        
        return config
    
    def get_collection_config(self) -> Dict[str, Any]:
        """Get Qdrant collection configuration."""
        return {
            'size': self.vector_size,
            'distance': self.distance_metric,
            'hnsw_config': {
                'm': self.hnsw_m,
                'ef_construct': self.hnsw_ef_construct,
                'full_scan_threshold': 10000,
            },
            'optimizers_config': {
                'deleted_threshold': self.optimizer_deleted_threshold,
                'vacuum_min_vector_number': self.optimizer_vacuum_min_vector_number,
            },
            'on_disk_payload': self.on_disk_payload,
        }
    
    class Config:
        env_prefix = ''


class RedisConfig(BaseSettings):
    """Redis cache configuration."""
    
    # Connection settings
    host: str = Field('localhost', env='REDIS_HOST')
    port: int = Field(6379, env='REDIS_PORT', ge=1, le=65535)
    db: int = Field(0, env='REDIS_DB', ge=0, le=15)
    password: Optional[SecretStr] = Field(None, env='REDIS_PASSWORD')
    
    # Connection pool settings
    max_connections: int = Field(50, env='REDIS_MAX_CONNECTIONS', ge=1)
    
    # Timeout settings
    socket_connect_timeout: float = Field(5.0, env='REDIS_CONNECT_TIMEOUT')
    socket_timeout: float = Field(5.0, env='REDIS_SOCKET_TIMEOUT')
    
    # Cache settings
    default_ttl: int = Field(3600, env='REDIS_DEFAULT_TTL', ge=0)
    max_cache_size: int = Field(10000, env='REDIS_MAX_CACHE_SIZE', ge=0)
    
    # Serialization
    serializer: str = Field('json', env='REDIS_SERIALIZER')
    
    @property
    def url(self) -> str:
        """Get Redis connection URL."""
        if self.password:
            auth = f":{self.password.get_secret_value()}@"
        else:
            auth = ""
        return f"redis://{auth}{self.host}:{self.port}/{self.db}"
    
    def get_connection_pool_config(self) -> Dict[str, Any]:
        """Get Redis connection pool configuration."""
        config = {
            'host': self.host,
            'port': self.port,
            'db': self.db,
            'max_connections': self.max_connections,
            'socket_connect_timeout': self.socket_connect_timeout,
            'socket_timeout': self.socket_timeout,
        }
        
        if self.password:
            config['password'] = self.password.get_secret_value()
        
        return config
    
    class Config:
        env_prefix = ''


class DatabaseCluster(BaseSettings):
    """Database cluster configuration for high availability."""
    
    # MongoDB cluster
    mongodb_nodes: List[str] = Field([], env='MONGODB_NODES')
    mongodb_read_preference: str = Field('primaryPreferred', env='MONGODB_READ_PREFERENCE')
    
    # Qdrant cluster
    qdrant_nodes: List[str] = Field([], env='QDRANT_NODES')
    qdrant_load_balancing: str = Field('round_robin', env='QDRANT_LOAD_BALANCING')
    
    # Redis cluster
    redis_nodes: List[str] = Field([], env='REDIS_NODES')
    redis_cluster_enabled: bool = Field(False, env='REDIS_CLUSTER_ENABLED')
    
    @validator('mongodb_nodes', 'qdrant_nodes', 'redis_nodes', pre=True)
    def parse_nodes(cls, v):
        """Parse node list from string or list."""
        if isinstance(v, str):
            return [node.strip() for node in v.split(',') if node.strip()]
        return v
    
    class Config:
        env_prefix = ''


@dataclass
class DatabaseHealthCheck:
    """Database health check configuration."""
    
    enabled: bool = True
    interval_seconds: int = 30
    timeout_seconds: int = 5
    failure_threshold: int = 3
    success_threshold: int = 1


class DatabaseManager:
    """Database connection manager with health checks and failover."""
    
    def __init__(self, 
                 mongodb_config: MongoDBConfig,
                 qdrant_config: QdrantConfig,
                 redis_config: Optional[RedisConfig] = None,
                 cluster_config: Optional[DatabaseCluster] = None):
        """Initialize database manager."""
        self.mongodb_config = mongodb_config
        self.qdrant_config = qdrant_config
        self.redis_config = redis_config
        self.cluster_config = cluster_config
        
        self._mongodb_client = None
        self._qdrant_client = None
        self._redis_client = None
    
    @property
    def mongodb(self):
        """Get MongoDB client (lazy initialization)."""
        if self._mongodb_client is None:
            from pymongo import MongoClient
            self._mongodb_client = MongoClient(
                self.mongodb_config.connection_string,
                **self.mongodb_config.get_client_options()
            )
        return self._mongodb_client
    
    @property
    def qdrant(self):
        """Get Qdrant client (lazy initialization)."""
        if self._qdrant_client is None:
            try:
                from qdrant_client import QdrantClient
                self._qdrant_client = QdrantClient(
                    **self.qdrant_config.get_client_config()
                )
            except ImportError:
                logger.warning("Qdrant client not installed")
        return self._qdrant_client
    
    @property
    def redis(self):
        """Get Redis client (lazy initialization)."""
        if self._redis_client is None and self.redis_config:
            try:
                import redis
                pool = redis.ConnectionPool(
                    **self.redis_config.get_connection_pool_config()
                )
                self._redis_client = redis.Redis(connection_pool=pool)
            except ImportError:
                logger.warning("Redis client not installed")
        return self._redis_client
    
    def health_check(self) -> Dict[str, bool]:
        """Check health of all database connections."""
        health = {}
        
        # Check MongoDB
        try:
            self.mongodb.admin.command('ping')
            health['mongodb'] = True
        except Exception as e:
            logger.error(f"MongoDB health check failed: {e}")
            health['mongodb'] = False
        
        # Check Qdrant
        if self.qdrant:
            try:
                self.qdrant.get_collections()
                health['qdrant'] = True
            except Exception as e:
                logger.error(f"Qdrant health check failed: {e}")
                health['qdrant'] = False
        
        # Check Redis
        if self.redis:
            try:
                self.redis.ping()
                health['redis'] = True
            except Exception as e:
                logger.error(f"Redis health check failed: {e}")
                health['redis'] = False
        
        return health
    
    def close(self):
        """Close all database connections."""
        if self._mongodb_client:
            self._mongodb_client.close()
            self._mongodb_client = None
        
        if self._qdrant_client:
            self._qdrant_client = None
        
        if self._redis_client:
            self._redis_client.close()
            self._redis_client = None