"""
Database Configuration Module for KATO

Provides specialized database configurations with connection management,
pooling, and optimization settings for ClickHouse, Qdrant, and Redis.
"""

from typing import Any, Optional

from pydantic import Field, SecretStr, validator

try:
    from pydantic_settings import BaseSettings
except ImportError:
    # Fallback for older Pydantic versions
    from pydantic import BaseSettings
import logging
from dataclasses import dataclass

logger = logging.getLogger('kato.config.database')


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

    def get_client_config(self) -> dict[str, Any]:
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

    def get_collection_config(self) -> dict[str, Any]:
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
        auth = f":{self.password.get_secret_value()}@" if self.password else ""
        return f"redis://{auth}{self.host}:{self.port}/{self.db}"

    def get_connection_pool_config(self) -> dict[str, Any]:
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

    # Qdrant cluster
    qdrant_nodes: list[str] = Field([], env='QDRANT_NODES')
    qdrant_load_balancing: str = Field('round_robin', env='QDRANT_LOAD_BALANCING')

    # Redis cluster
    redis_nodes: list[str] = Field([], env='REDIS_NODES')
    redis_cluster_enabled: bool = Field(False, env='REDIS_CLUSTER_ENABLED')

    @validator('qdrant_nodes', 'redis_nodes', pre=True)
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


