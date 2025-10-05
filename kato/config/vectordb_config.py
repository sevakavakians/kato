"""
Vector Database Configuration Module for KATO

This module provides configuration management for vector database backends,
supporting multiple implementations with various optimization options.
"""

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Literal, Optional

logger = logging.getLogger('kato.config.vectordb')

# Type definitions for configuration options
VectorDBBackend = Literal["qdrant", "faiss", "milvus", "weaviate"]
QuantizationType = Literal["none", "scalar", "product", "binary"]
SimilarityMetric = Literal["euclidean", "cosine", "dot", "manhattan"]
IndexType = Literal["hnsw", "flat", "ivf", "lsh", "annoy"]


@dataclass
class QuantizationConfig:
    """Configuration for vector quantization"""
    enabled: bool = False
    type: QuantizationType = "scalar"
    parameters: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        # Set default parameters based on quantization type
        if self.type == "scalar" and not self.parameters:
            self.parameters = {
                "type": "int8",
                "quantile": 0.99,
                "always_ram": False
            }
        elif self.type == "product" and not self.parameters:
            self.parameters = {
                "compression": "x16",
                "always_ram": False
            }
        elif self.type == "binary" and not self.parameters:
            self.parameters = {
                "always_ram": True
            }


@dataclass
class IndexConfig:
    """Configuration for vector index"""
    type: IndexType = "hnsw"
    parameters: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        # Set default parameters based on index type
        if self.type == "hnsw" and not self.parameters:
            self.parameters = {
                "m": 16,
                "ef_construct": 128,
                "ef_search": 100,
                "max_elements": 1000000
            }
        elif self.type == "ivf" and not self.parameters:
            self.parameters = {
                "nlist": 1024,
                "nprobe": 8
            }
        elif self.type == "flat" and not self.parameters:
            self.parameters = {}  # Flat index has no parameters


@dataclass
class CacheConfig:
    """Configuration for vector caching"""
    enabled: bool = True
    backend: Literal["redis", "memory"] = "redis"
    size: int = 10000  # Number of vectors to cache
    ttl: int = 3600  # Time to live in seconds
    host: str = "localhost"
    port: int = 6379

    def get_redis_url(self) -> str:
        """Get Redis connection URL"""
        return f"redis://{self.host}:{self.port}/0"


@dataclass
class GPUConfig:
    """Configuration for GPU acceleration"""
    enabled: bool = False
    device_ids: list = field(default_factory=lambda: [0])  # GPU device IDs
    force_half_precision: bool = False  # Use FP16 for memory efficiency
    indexing: bool = True  # Use GPU for index building
    search: bool = True  # Use GPU for search operations


@dataclass
class QdrantConfig:
    """Qdrant-specific configuration"""
    host: str = "localhost"
    port: int = 6333
    grpc_port: int = 6334
    collection_name: str = "kato_vectors"
    vector_size: int = 512
    distance: SimilarityMetric = "euclidean"
    on_disk_payload: bool = True
    optimizers: Dict[str, Any] = field(default_factory=lambda: {
        "deleted_threshold": 0.2,
        "vacuum_min_vector_number": 1000,
        "default_segment_number": 4,
        "max_segment_size": 500000,
        "memmap_threshold": 20000,
        "indexing_threshold": 10000,
        "flush_interval_sec": 5,
        "max_optimization_threads": 1
    })

    def get_url(self) -> str:
        """Get Qdrant connection URL"""
        return f"http://{self.host}:{self.port}"

    def get_grpc_url(self) -> str:
        """Get Qdrant gRPC connection URL"""
        return f"{self.host}:{self.grpc_port}"


@dataclass
class VectorDBConfig:
    """Main vector database configuration"""
    backend: VectorDBBackend = "qdrant"
    vector_dim: Optional[int] = None  # Auto-detected if None
    similarity_metric: SimilarityMetric = "euclidean"

    # Backend-specific configurations
    qdrant: QdrantConfig = field(default_factory=QdrantConfig)

    # Optimization configurations
    gpu: GPUConfig = field(default_factory=GPUConfig)
    quantization: QuantizationConfig = field(default_factory=QuantizationConfig)
    index: IndexConfig = field(default_factory=IndexConfig)
    cache: CacheConfig = field(default_factory=CacheConfig)

    # Performance tuning
    batch_size: int = 1000  # Batch size for bulk operations
    search_limit: int = 100  # Maximum search results
    search_timeout: float = 10.0  # Search timeout in seconds
    connection_pool_size: int = 10  # Connection pool size

    # Feature flags
    enable_filtering: bool = True  # Enable metadata filtering
    enable_payload: bool = True  # Store additional payload with vectors
    enable_async: bool = True  # Use async operations where possible
    auto_create_collection: bool = True  # Auto-create collections if missing

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary"""
        return asdict(self)

    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> 'VectorDBConfig':
        """Create configuration from dictionary"""
        # Handle nested dataclass fields
        if 'qdrant' in config_dict and isinstance(config_dict['qdrant'], dict):
            config_dict['qdrant'] = QdrantConfig(**config_dict['qdrant'])
        if 'gpu' in config_dict and isinstance(config_dict['gpu'], dict):
            config_dict['gpu'] = GPUConfig(**config_dict['gpu'])
        if 'quantization' in config_dict and isinstance(config_dict['quantization'], dict):
            config_dict['quantization'] = QuantizationConfig(**config_dict['quantization'])
        if 'index' in config_dict and isinstance(config_dict['index'], dict):
            config_dict['index'] = IndexConfig(**config_dict['index'])
        if 'cache' in config_dict and isinstance(config_dict['cache'], dict):
            config_dict['cache'] = CacheConfig(**config_dict['cache'])

        return cls(**config_dict)

    @classmethod
    def from_env(cls) -> 'VectorDBConfig':
        """Create configuration from environment variables"""
        config = cls()

        # Backend selection
        if backend := os.getenv('KATO_VECTOR_DB_BACKEND'):
            config.backend = backend

        # Vector dimensions
        if vector_dim := os.getenv('KATO_VECTOR_DIM'):
            config.vector_dim = int(vector_dim)

        # Similarity metric
        if metric := os.getenv('KATO_SIMILARITY_METRIC'):
            config.similarity_metric = metric

        # Qdrant configuration
        if config.backend == "qdrant":
            if host := os.getenv('QDRANT_HOST'):
                config.qdrant.host = host
            if port := os.getenv('QDRANT_PORT'):
                config.qdrant.port = int(port)
            if collection := os.getenv('QDRANT_COLLECTION'):
                config.qdrant.collection_name = collection

        # GPU configuration
        if gpu_enabled := os.getenv('KATO_GPU_ENABLED'):
            config.gpu.enabled = gpu_enabled.lower() in ('true', '1', 'yes')
        if gpu_devices := os.getenv('KATO_GPU_DEVICES'):
            config.gpu.device_ids = [int(d) for d in gpu_devices.split(',')]

        # Quantization configuration
        if quant_enabled := os.getenv('KATO_QUANTIZATION_ENABLED'):
            config.quantization.enabled = quant_enabled.lower() in ('true', '1', 'yes')
        if quant_type := os.getenv('KATO_QUANTIZATION_TYPE'):
            config.quantization.type = quant_type

        # Cache configuration
        if cache_enabled := os.getenv('KATO_CACHE_ENABLED'):
            config.cache.enabled = cache_enabled.lower() in ('true', '1', 'yes')
        if redis_host := os.getenv('REDIS_HOST'):
            config.cache.host = redis_host
        if redis_port := os.getenv('REDIS_PORT'):
            config.cache.port = int(redis_port)

        # Performance tuning
        if batch_size := os.getenv('KATO_VECTOR_BATCH_SIZE'):
            config.batch_size = int(batch_size)
        if search_limit := os.getenv('KATO_VECTOR_SEARCH_LIMIT'):
            config.search_limit = int(search_limit)

        return config

    @classmethod
    def from_file(cls, filepath: str) -> 'VectorDBConfig':
        """Load configuration from JSON or YAML file"""
        with open(filepath) as f:
            if filepath.endswith('.json'):
                config_dict = json.load(f)
            elif filepath.endswith(('.yml', '.yaml')):
                import yaml
                config_dict = yaml.safe_load(f)
            else:
                raise ValueError(f"Unsupported file format: {filepath}")

        return cls.from_dict(config_dict)

    def save(self, filepath: str) -> None:
        """Save configuration to file.
        
        Args:
            filepath: Path to save configuration file (JSON or YAML).
            
        Raises:
            ValueError: If file format is not supported.
        """
        config_dict = self.to_dict()

        with open(filepath, 'w') as f:
            if filepath.endswith('.json'):
                json.dump(config_dict, f, indent=2)
            elif filepath.endswith(('.yml', '.yaml')):
                import yaml
                yaml.safe_dump(config_dict, f, default_flow_style=False)
            else:
                raise ValueError(f"Unsupported file format: {filepath}")

        logger.info(f"Configuration saved to {filepath}")

    def validate(self) -> bool:
        """Validate configuration settings"""
        errors = []

        # Validate backend
        valid_backends = ["qdrant", "faiss", "milvus", "weaviate"]
        if self.backend not in valid_backends:
            errors.append(f"Invalid backend: {self.backend}")

        # Validate vector dimensions if specified
        if self.vector_dim is not None and self.vector_dim <= 0:
            errors.append(f"Invalid vector dimension: {self.vector_dim}")

        # Validate batch size
        if self.batch_size <= 0:
            errors.append(f"Invalid batch size: {self.batch_size}")

        # Validate search limit
        if self.search_limit <= 0:
            errors.append(f"Invalid search limit: {self.search_limit}")

        # Backend-specific validation
        if self.backend == "qdrant":
            if self.qdrant.port <= 0 or self.qdrant.port > 65535:
                errors.append(f"Invalid Qdrant port: {self.qdrant.port}")
            if self.qdrant.vector_size <= 0:
                errors.append(f"Invalid vector size: {self.qdrant.vector_size}")

        if errors:
            for error in errors:
                logger.error(error)
            return False

        return True


# Global configuration instance
_global_config: Optional[VectorDBConfig] = None


def get_vector_db_config() -> VectorDBConfig:
    """Get global vector database configuration"""
    global _global_config

    if _global_config is None:
        # Try loading from environment first
        _global_config = VectorDBConfig.from_env()

        # Try loading from config file if exists
        config_file = os.getenv('KATO_VECTOR_CONFIG_FILE')
        if config_file and os.path.exists(config_file):
            try:
                _global_config = VectorDBConfig.from_file(config_file)
                logger.info(f"Loaded vector DB config from {config_file}")
            except Exception as e:
                logger.warning(f"Failed to load config from {config_file}: {e}")

        # Validate configuration
        if not _global_config.validate():
            logger.warning("Configuration validation failed, using defaults")
            _global_config = VectorDBConfig()

        logger.info(f"Using vector database backend: {_global_config.backend}")

    return _global_config


def set_vector_db_config(config: VectorDBConfig) -> None:
    """Set global vector database configuration.
    
    Args:
        config: Vector database configuration to set globally.
        
    Raises:
        ValueError: If configuration validation fails.
    """
    global _global_config

    if not config.validate():
        raise ValueError("Invalid configuration")

    _global_config = config
    logger.info(f"Vector DB configuration updated: backend={config.backend}")


# Example configurations for different use cases
EXAMPLE_CONFIGS = {
    "development": VectorDBConfig(
        backend="qdrant",
        quantization=QuantizationConfig(enabled=False),
        cache=CacheConfig(enabled=False),
        gpu=GPUConfig(enabled=False)
    ),

    "production": VectorDBConfig(
        backend="qdrant",
        quantization=QuantizationConfig(enabled=True, type="scalar"),
        cache=CacheConfig(enabled=True, size=50000, ttl=7200),
        gpu=GPUConfig(enabled=False),
        batch_size=5000,
        connection_pool_size=20
    ),

    "gpu_accelerated": VectorDBConfig(
        backend="qdrant",
        gpu=GPUConfig(enabled=True, device_ids=[0, 1]),
        quantization=QuantizationConfig(enabled=True, type="product"),
        index=IndexConfig(type="hnsw", parameters={"m": 32, "ef_construct": 200}),
        cache=CacheConfig(enabled=True, size=100000)
    ),

    "memory_optimized": VectorDBConfig(
        backend="qdrant",
        quantization=QuantizationConfig(enabled=True, type="binary"),
        index=IndexConfig(type="flat"),  # Simple but memory-efficient
        cache=CacheConfig(enabled=False),  # Disable cache to save memory
        batch_size=500
    ),

}
