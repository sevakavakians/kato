"""
Centralized Configuration Management for KATO

This module provides a unified configuration system using Pydantic for validation
and type safety. All environment variables and configuration options are consolidated
here for easier management and documentation.
"""

import os
from pathlib import Path
from typing import Optional, Literal, Dict, Any, List
from pydantic import BaseSettings, Field, validator, root_validator
from pydantic.types import SecretStr


class ProcessorConfig(BaseSettings):
    """Processor-specific configuration."""
    
    processor_id: Optional[str] = Field(
        None,
        env='PROCESSOR_ID',
        description="Unique identifier for processor instance"
    )
    processor_name: str = Field(
        'KatoProcessor',
        env='PROCESSOR_NAME',
        description="Display name for the processor"
    )
    
    @validator('processor_id', pre=True, always=True)
    def generate_processor_id(cls, v):
        """Generate processor ID if not provided."""
        if not v:
            import uuid
            import time
            return f"kato-{uuid.uuid4().hex[:8]}-{int(time.time())}"
        return v
    
    class Config:
        env_prefix = ''


class LoggingConfig(BaseSettings):
    """Logging configuration."""
    
    log_level: Literal['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'] = Field(
        'INFO',
        env='LOG_LEVEL',
        description="Logging level"
    )
    log_format: Literal['json', 'human'] = Field(
        'human',
        env='LOG_FORMAT',
        description="Log output format"
    )
    log_output: str = Field(
        'stdout',
        env='LOG_OUTPUT',
        description="Log output destination (stdout, stderr, or file path)"
    )
    
    class Config:
        env_prefix = ''


class DatabaseConfig(BaseSettings):
    """Database configuration for MongoDB and Qdrant."""
    
    # MongoDB settings
    mongo_url: str = Field(
        'mongodb://localhost:27017',
        env='MONGO_BASE_URL',
        description="MongoDB connection URL"
    )
    mongo_timeout: int = Field(
        5000,
        env='MONGO_TIMEOUT',
        ge=1000,
        le=30000,
        description="MongoDB connection timeout in milliseconds"
    )
    
    # Qdrant settings
    qdrant_host: str = Field(
        'localhost',
        env='QDRANT_HOST',
        description="Qdrant host address"
    )
    qdrant_port: int = Field(
        6333,
        env='QDRANT_PORT',
        ge=1,
        le=65535,
        description="Qdrant port number"
    )
    qdrant_grpc_port: int = Field(
        6334,
        env='QDRANT_GRPC_PORT',
        ge=1,
        le=65535,
        description="Qdrant gRPC port number"
    )
    qdrant_collection_prefix: str = Field(
        'vectors',
        env='QDRANT_COLLECTION_PREFIX',
        description="Prefix for Qdrant collection names"
    )
    
    # Redis settings (optional, for caching)
    redis_host: Optional[str] = Field(
        None,
        env='REDIS_HOST',
        description="Redis host for caching (optional)"
    )
    redis_port: int = Field(
        6379,
        env='REDIS_PORT',
        ge=1,
        le=65535,
        description="Redis port number"
    )
    redis_enabled: bool = Field(
        False,
        env='REDIS_ENABLED',
        description="Enable Redis caching"
    )
    
    @property
    def qdrant_url(self) -> str:
        """Get Qdrant connection URL."""
        return f"http://{self.qdrant_host}:{self.qdrant_port}"
    
    @property
    def qdrant_grpc_url(self) -> str:
        """Get Qdrant gRPC connection URL."""
        return f"{self.qdrant_host}:{self.qdrant_grpc_port}"
    
    @property
    def redis_url(self) -> Optional[str]:
        """Get Redis connection URL if enabled."""
        if self.redis_enabled and self.redis_host:
            return f"redis://{self.redis_host}:{self.redis_port}/0"
        return None
    
    class Config:
        env_prefix = ''


class LearningConfig(BaseSettings):
    """Learning and pattern processing configuration."""
    
    max_pattern_length: int = Field(
        0,
        env='MAX_PATTERN_LENGTH',
        ge=0,
        description="Maximum pattern length (0 = unlimited)"
    )
    persistence: int = Field(
        5,
        env='PERSISTENCE',
        ge=1,
        le=100,
        description="Number of events to retain in memory"
    )
    recall_threshold: float = Field(
        0.1,
        env='RECALL_THRESHOLD',
        ge=0.0,
        le=1.0,
        description="Minimum similarity threshold for pattern matching"
    )
    smoothness: int = Field(
        3,
        env='SMOOTHNESS',
        ge=1,
        le=10,
        description="Smoothing factor for pattern matching"
    )
    quiescence: int = Field(
        3,
        env='QUIESCENCE',
        ge=0,
        le=100,
        description="Quiescence period for pattern stabilization"
    )
    auto_learn_enabled: bool = Field(
        False,
        env='AUTO_LEARN_ENABLED',
        description="Enable automatic pattern learning"
    )
    auto_learn_threshold: int = Field(
        50,
        env='AUTO_LEARN_THRESHOLD',
        ge=1,
        description="Number of observations before auto-learning"
    )
    
    @validator('max_pattern_length')
    def validate_pattern_length(cls, v):
        """Validate pattern length configuration."""
        if v < 0:
            raise ValueError("max_pattern_length must be non-negative")
        return v
    
    class Config:
        env_prefix = ''


class ProcessingConfig(BaseSettings):
    """Processing and prediction configuration."""
    
    indexer_type: str = Field(
        'VI',
        env='INDEXER_TYPE',
        description="Type of vector indexer to use"
    )
    auto_act_method: Literal['none', 'threshold', 'adaptive'] = Field(
        'none',
        env='AUTO_ACT_METHOD',
        description="Automatic action method"
    )
    auto_act_threshold: float = Field(
        0.8,
        env='AUTO_ACT_THRESHOLD',
        ge=0.0,
        le=1.0,
        description="Threshold for automatic actions"
    )
    always_update_frequencies: bool = Field(
        False,
        env='ALWAYS_UPDATE_FREQUENCIES',
        description="Always update pattern frequencies on re-observation"
    )
    max_predictions: int = Field(
        100,
        env='MAX_PREDICTIONS',
        ge=1,
        le=10000,
        description="Maximum number of predictions to return"
    )
    search_depth: int = Field(
        10,
        env='SEARCH_DEPTH',
        ge=1,
        le=100,
        description="Depth for pattern searching"
    )
    sort_symbols: bool = Field(
        True,
        env='SORT',
        description="Sort symbols alphabetically within events"
    )
    process_predictions: bool = Field(
        True,
        env='PROCESS_PREDICTIONS',
        description="Enable prediction processing"
    )
    
    class Config:
        env_prefix = ''


class PerformanceConfig(BaseSettings):
    """Performance optimization configuration."""
    
    use_fast_matching: bool = Field(
        True,
        env='KATO_USE_FAST_MATCHING',
        description="Use optimized fast matching algorithms"
    )
    use_indexing: bool = Field(
        True,
        env='KATO_USE_INDEXING',
        description="Use pattern indexing for faster lookups"
    )
    use_optimized: bool = Field(
        True,
        env='KATO_USE_OPTIMIZED',
        description="Use general optimizations"
    )
    batch_size: int = Field(
        1000,
        env='KATO_BATCH_SIZE',
        ge=1,
        le=100000,
        description="Batch size for bulk operations"
    )
    vector_batch_size: int = Field(
        1000,
        env='KATO_VECTOR_BATCH_SIZE',
        ge=1,
        le=100000,
        description="Batch size for vector operations"
    )
    vector_search_limit: int = Field(
        100,
        env='KATO_VECTOR_SEARCH_LIMIT',
        ge=1,
        le=10000,
        description="Maximum vector search results"
    )
    connection_pool_size: int = Field(
        10,
        env='CONNECTION_POOL_SIZE',
        ge=1,
        le=100,
        description="Database connection pool size"
    )
    request_timeout: float = Field(
        30.0,
        env='REQUEST_TIMEOUT',
        ge=1.0,
        le=300.0,
        description="Request timeout in seconds"
    )
    
    class Config:
        env_prefix = ''


class APIConfig(BaseSettings):
    """API service configuration."""
    
    host: str = Field(
        '0.0.0.0',
        env='HOST',
        description="API host address"
    )
    port: int = Field(
        8000,
        env='PORT',
        ge=1,
        le=65535,
        description="API port number"
    )
    workers: int = Field(
        1,
        env='WORKERS',
        ge=1,
        le=16,
        description="Number of worker processes"
    )
    cors_enabled: bool = Field(
        True,
        env='CORS_ENABLED',
        description="Enable CORS support"
    )
    cors_origins: List[str] = Field(
        ['*'],
        env='CORS_ORIGINS',
        description="Allowed CORS origins"
    )
    docs_enabled: bool = Field(
        True,
        env='DOCS_ENABLED',
        description="Enable API documentation endpoints"
    )
    max_request_size: int = Field(
        100 * 1024 * 1024,  # 100MB
        env='MAX_REQUEST_SIZE',
        ge=1024,
        description="Maximum request size in bytes"
    )
    
    @validator('cors_origins', pre=True)
    def parse_cors_origins(cls, v):
        """Parse CORS origins from string or list."""
        if isinstance(v, str):
            return v.split(',')
        return v
    
    class Config:
        env_prefix = ''


class Settings(BaseSettings):
    """Main settings class combining all configuration sections."""
    
    # Configuration sections
    processor: ProcessorConfig = Field(default_factory=ProcessorConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    learning: LearningConfig = Field(default_factory=LearningConfig)
    processing: ProcessingConfig = Field(default_factory=ProcessingConfig)
    performance: PerformanceConfig = Field(default_factory=PerformanceConfig)
    api: APIConfig = Field(default_factory=APIConfig)
    
    # Environment and deployment
    environment: Literal['development', 'testing', 'production'] = Field(
        'development',
        env='ENVIRONMENT',
        description="Deployment environment"
    )
    debug: bool = Field(
        False,
        env='DEBUG',
        description="Enable debug mode"
    )
    config_file: Optional[Path] = Field(
        None,
        env='KATO_CONFIG_FILE',
        description="Path to configuration file (YAML or JSON)"
    )
    
    @root_validator(pre=True)
    def load_from_file(cls, values):
        """Load configuration from file if specified."""
        config_file = values.get('config_file') or os.getenv('KATO_CONFIG_FILE')
        
        if config_file and os.path.exists(config_file):
            import json
            import yaml
            
            with open(config_file, 'r') as f:
                if config_file.endswith('.json'):
                    file_config = json.load(f)
                elif config_file.endswith(('.yml', '.yaml')):
                    file_config = yaml.safe_load(f)
                else:
                    raise ValueError(f"Unsupported config file format: {config_file}")
            
            # Merge file config with environment variables (env vars take precedence)
            for key, value in file_config.items():
                if key not in values or values[key] is None:
                    values[key] = value
        
        return values
    
    @validator('debug', always=True)
    def set_debug_from_environment(cls, v, values):
        """Set debug mode based on environment."""
        if values.get('environment') == 'development':
            return True
        return v
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert settings to dictionary."""
        return self.dict(exclude_unset=False)
    
    def to_yaml(self) -> str:
        """Export settings to YAML format."""
        import yaml
        return yaml.safe_dump(self.to_dict(), default_flow_style=False)
    
    def to_json(self) -> str:
        """Export settings to JSON format."""
        import json
        return json.dumps(self.to_dict(), indent=2)
    
    def save(self, filepath: Path) -> None:
        """Save configuration to file."""
        filepath = Path(filepath)
        
        with open(filepath, 'w') as f:
            if filepath.suffix == '.json':
                f.write(self.to_json())
            elif filepath.suffix in ['.yml', '.yaml']:
                f.write(self.to_yaml())
            else:
                raise ValueError(f"Unsupported file format: {filepath.suffix}")
        
        print(f"Configuration saved to {filepath}")
    
    def validate_configuration(self) -> List[str]:
        """Validate configuration and return any warnings."""
        warnings = []
        
        # Check database connectivity settings
        if self.environment == 'production':
            if self.database.mongo_url == 'mongodb://localhost:27017':
                warnings.append("Using localhost MongoDB in production environment")
            if self.debug:
                warnings.append("Debug mode enabled in production environment")
            if self.api.cors_origins == ['*']:
                warnings.append("CORS allows all origins in production environment")
        
        # Check learning configuration consistency
        if self.learning.auto_learn_enabled and self.learning.max_pattern_length == 0:
            warnings.append("Auto-learning enabled with unlimited pattern length")
        
        # Check performance settings
        if self.performance.batch_size > 10000:
            warnings.append(f"Large batch size ({self.performance.batch_size}) may cause memory issues")
        
        return warnings
    
    class Config:
        env_prefix = ''
        env_file = '.env'
        env_file_encoding = 'utf-8'
        case_sensitive = False


# Global settings instance
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get global settings instance (singleton pattern)."""
    global _settings
    
    if _settings is None:
        _settings = Settings()
        
        # Log configuration warnings
        warnings = _settings.validate_configuration()
        if warnings:
            import logging
            logger = logging.getLogger(__name__)
            for warning in warnings:
                logger.warning(f"Configuration warning: {warning}")
    
    return _settings


def reload_settings() -> Settings:
    """Force reload of settings from environment."""
    global _settings
    _settings = None
    return get_settings()


# Export commonly used settings for backward compatibility
def get_processor_config() -> ProcessorConfig:
    """Get processor configuration."""
    return get_settings().processor


def get_database_config() -> DatabaseConfig:
    """Get database configuration."""
    return get_settings().database


def get_learning_config() -> LearningConfig:
    """Get learning configuration."""
    return get_settings().learning


def get_api_config() -> APIConfig:
    """Get API configuration."""
    return get_settings().api