"""
Centralized Configuration Management for KATO

This module provides a unified configuration system using Pydantic for validation
and type safety. All environment variables and configuration options are consolidated
here for easier management and documentation.
"""

import logging
import os
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import ConfigDict, Field, field_validator, model_validator
from pydantic_settings import BaseSettings


class ServiceConfig(BaseSettings):
    """Service-level configuration."""

    service_name: str = Field(
        'kato',
        json_schema_extra={'env': 'SERVICE_NAME'},
        description="Service name identifier"
    )
    service_version: str = Field(
        '2.0',
        json_schema_extra={'env': 'SERVICE_VERSION'},
        description="Service version"
    )

    model_config = ConfigDict(env_prefix='')


class LoggingConfig(BaseSettings):
    """Logging configuration."""

    log_level: Literal['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'] = Field(
        'INFO',
        json_schema_extra={'env': 'LOG_LEVEL'},
        description="Logging level"
    )
    log_format: Literal['json', 'human'] = Field(
        'human',
        json_schema_extra={'env': 'LOG_FORMAT'},
        description="Log output format"
    )
    log_output: str = Field(
        'stdout',
        json_schema_extra={'env': 'LOG_OUTPUT'},
        description="Log output destination (stdout, stderr, or file path)"
    )

    model_config = ConfigDict(env_prefix='')


class DatabaseConfig(BaseSettings):
    """Database configuration for MongoDB and Qdrant."""

    # MongoDB settings - field name must match env var for pydantic-settings v2
    MONGO_BASE_URL: str = Field(
        'mongodb://localhost:27017',
        description="MongoDB connection URL"
    )
    MONGO_TIMEOUT: int = Field(
        5000,
        ge=1000,
        le=30000,
        description="MongoDB connection timeout in milliseconds"
    )

    @property
    def mongo_url(self) -> str:
        """Backward compatibility property."""
        return self.MONGO_BASE_URL

    @property
    def mongo_timeout(self) -> int:
        """Backward compatibility property."""
        return self.MONGO_TIMEOUT

    # Qdrant settings - field names must match env vars
    QDRANT_HOST: str = Field(
        'localhost',
        description="Qdrant host address"
    )
    QDRANT_PORT: int = Field(
        6333,
        ge=1,
        le=65535,
        description="Qdrant port number"
    )
    QDRANT_GRPC_PORT: int = Field(
        6334,
        ge=1,
        le=65535,
        description="Qdrant gRPC port number"
    )
    QDRANT_COLLECTION_PREFIX: str = Field(
        'vectors',
        description="Prefix for Qdrant collection names"
    )

    @property
    def qdrant_host(self) -> str:
        return self.QDRANT_HOST

    @property
    def qdrant_port(self) -> int:
        return self.QDRANT_PORT

    @property
    def qdrant_grpc_port(self) -> int:
        return self.QDRANT_GRPC_PORT

    @property
    def qdrant_collection_prefix(self) -> str:
        return self.QDRANT_COLLECTION_PREFIX

    # Redis settings (optional, for caching and sessions)
    REDIS_URL: Optional[str] = Field(
        None,
        description="Redis connection URL"
    )
    redis_host: Optional[str] = Field(
        None,
        json_schema_extra={'env': 'REDIS_HOST'},
        description="Redis host (deprecated, use REDIS_URL)"
    )
    redis_port: int = Field(
        6379,
        json_schema_extra={'env': 'REDIS_PORT'},
        ge=1,
        le=65535,
        description="Redis port (deprecated, use REDIS_URL)"
    )
    redis_enabled: bool = Field(
        False,
        json_schema_extra={'env': 'REDIS_ENABLED'},
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
        # Prefer REDIS_URL env var if set
        if self.REDIS_URL:
            return self.REDIS_URL
        # Fallback to constructing from host/port for backwards compatibility
        if self.redis_enabled and self.redis_host:
            return f"redis://{self.redis_host}:{self.redis_port}/0"
        return None

    model_config = ConfigDict(env_prefix='')


class LearningConfig(BaseSettings):
    """Learning and pattern processing configuration."""

    max_pattern_length: int = Field(
        0,
        json_schema_extra={'env': 'MAX_PATTERN_LENGTH'},
        ge=0,
        description="Maximum pattern length (0 = unlimited)"
    )
    persistence: int = Field(
        5,
        json_schema_extra={'env': 'PERSISTENCE'},
        ge=1,
        le=100,
        description="Rolling window size for emotive values per pattern"
    )
    recall_threshold: float = Field(
        0.1,
        json_schema_extra={'env': 'RECALL_THRESHOLD'},
        ge=0.0,
        le=1.0,
        description="Minimum similarity threshold for pattern matching"
    )
    auto_learn_enabled: bool = Field(
        False,
        json_schema_extra={'env': 'AUTO_LEARN_ENABLED'},
        description="Enable automatic pattern learning"
    )
    auto_learn_threshold: int = Field(
        50,
        json_schema_extra={'env': 'AUTO_LEARN_THRESHOLD'},
        ge=1,
        description="Number of observations before auto-learning"
    )
    stm_mode: Literal['CLEAR', 'ROLLING'] = Field(
        'CLEAR',
        json_schema_extra={'env': 'STM_MODE'},
        description="Short-term memory mode: CLEAR (reset after auto-learn) or ROLLING (sliding window)"
    )

    @field_validator('max_pattern_length')
    @classmethod
    def validate_pattern_length(cls, v):
        """Validate pattern length configuration."""
        if v < 0:
            raise ValueError("max_pattern_length must be non-negative")
        return v

    model_config = ConfigDict(env_prefix='')


class ProcessingConfig(BaseSettings):
    """Processing and prediction configuration."""

    indexer_type: str = Field(
        'VI',
        json_schema_extra={'env': 'INDEXER_TYPE'},
        description="Type of vector indexer to use"
    )
    max_predictions: int = Field(
        100,
        json_schema_extra={'env': 'MAX_PREDICTIONS'},
        ge=1,
        le=10000,
        description="Maximum number of predictions to return"
    )
    sort_symbols: bool = Field(
        True,
        json_schema_extra={'env': 'SORT'},
        description="Sort symbols alphabetically within events"
    )
    process_predictions: bool = Field(
        True,
        json_schema_extra={'env': 'PROCESS_PREDICTIONS'},
        description="Enable prediction processing"
    )
    use_token_matching: bool = Field(
        True,
        json_schema_extra={'env': 'KATO_USE_TOKEN_MATCHING'},
        description="Use token-level matching (True) vs character-level matching (False)"
    )

    model_config = ConfigDict(env_prefix='')


class PerformanceConfig(BaseSettings):
    """Performance optimization configuration."""

    use_fast_matching: bool = Field(
        True,
        json_schema_extra={'env': 'KATO_USE_FAST_MATCHING'},
        description="Use optimized fast matching algorithms"
    )
    use_indexing: bool = Field(
        True,
        json_schema_extra={'env': 'KATO_USE_INDEXING'},
        description="Use pattern indexing for faster lookups"
    )
    use_optimized: bool = Field(
        True,
        json_schema_extra={'env': 'KATO_USE_OPTIMIZED'},
        description="Use general optimizations"
    )
    batch_size: int = Field(
        1000,
        json_schema_extra={'env': 'KATO_BATCH_SIZE'},
        ge=1,
        le=100000,
        description="Batch size for bulk operations"
    )
    vector_batch_size: int = Field(
        1000,
        json_schema_extra={'env': 'KATO_VECTOR_BATCH_SIZE'},
        ge=1,
        le=100000,
        description="Batch size for vector operations"
    )
    vector_search_limit: int = Field(
        100,
        json_schema_extra={'env': 'KATO_VECTOR_SEARCH_LIMIT'},
        ge=1,
        le=10000,
        description="Maximum vector search results"
    )
    connection_pool_size: int = Field(
        10,
        json_schema_extra={'env': 'CONNECTION_POOL_SIZE'},
        ge=1,
        le=100,
        description="Database connection pool size"
    )
    request_timeout: float = Field(
        30.0,
        json_schema_extra={'env': 'REQUEST_TIMEOUT'},
        ge=1.0,
        le=300.0,
        description="Request timeout in seconds"
    )

    model_config = ConfigDict(env_prefix='')


class SessionConfig(BaseSettings):
    """Session management configuration."""

    session_ttl: int = Field(
        3600,
        json_schema_extra={'env': 'SESSION_TTL'},
        ge=60,
        le=86400,
        description="Session time-to-live in seconds"
    )

    session_auto_extend: bool = Field(
        True,
        json_schema_extra={'env': 'SESSION_AUTO_EXTEND'},
        description="Automatically extend session TTL on each access (sliding window)"
    )

    model_config = ConfigDict(env_prefix='')


class APIConfig(BaseSettings):
    """API service configuration."""

    host: str = Field(
        '0.0.0.0',
        json_schema_extra={'env': 'HOST'},
        description="API host address"
    )
    port: int = Field(
        8000,
        json_schema_extra={'env': 'PORT'},
        ge=1,
        le=65535,
        description="API port number"
    )
    workers: int = Field(
        1,
        json_schema_extra={'env': 'WORKERS'},
        ge=1,
        le=16,
        description="Number of worker processes"
    )
    cors_enabled: bool = Field(
        True,
        json_schema_extra={'env': 'CORS_ENABLED'},
        description="Enable CORS support"
    )
    cors_origins: list[str] = Field(
        ['*'],
        json_schema_extra={'env': 'CORS_ORIGINS'},
        description="Allowed CORS origins"
    )
    docs_enabled: bool = Field(
        True,
        json_schema_extra={'env': 'DOCS_ENABLED'},
        description="Enable API documentation endpoints"
    )
    max_request_size: int = Field(
        100 * 1024 * 1024,  # 100MB
        json_schema_extra={'env': 'MAX_REQUEST_SIZE'},
        ge=1024,
        description="Maximum request size in bytes"
    )

    @field_validator('cors_origins', mode='before')
    @classmethod
    def parse_cors_origins(cls, v):
        """Parse CORS origins from string or list."""
        if isinstance(v, str):
            return v.split(',')
        return v

    model_config = ConfigDict(env_prefix='')


class Settings(BaseSettings):
    """Main settings class combining all configuration sections."""

    # Configuration sections
    service: ServiceConfig = Field(default_factory=ServiceConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    learning: LearningConfig = Field(default_factory=LearningConfig)
    processing: ProcessingConfig = Field(default_factory=ProcessingConfig)
    performance: PerformanceConfig = Field(default_factory=PerformanceConfig)
    session: SessionConfig = Field(default_factory=SessionConfig)
    api: APIConfig = Field(default_factory=APIConfig)

    # Environment and deployment
    environment: Literal['development', 'testing', 'production'] = Field(
        'development',
        json_schema_extra={'env': 'ENVIRONMENT'},
        description="Deployment environment"
    )
    debug: bool = Field(
        False,
        json_schema_extra={'env': 'DEBUG'},
        description="Enable debug mode"
    )
    config_file: Optional[Path] = Field(
        None,
        json_schema_extra={'env': 'KATO_CONFIG_FILE'},
        description="Path to configuration file (YAML or JSON)"
    )

    @model_validator(mode='before')
    @classmethod
    def load_from_file(cls, values):
        """Load configuration from file if specified."""
        if isinstance(values, dict):
            config_file = values.get('config_file') or os.getenv('KATO_CONFIG_FILE')

            if config_file and os.path.exists(config_file):
                import json

                import yaml

                with open(config_file) as f:
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

    @field_validator('debug')
    @classmethod
    def set_debug_from_environment(cls, v, info):
        """Set debug mode based on environment."""
        if info.data.get('environment') == 'development':
            return True
        return v

    def to_dict(self) -> dict[str, Any]:
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

        logging.info(f"Configuration saved to {filepath}")

    def validate_configuration(self) -> list[str]:
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

    model_config = ConfigDict(
        env_prefix='',
        env_file='.env',
        env_file_encoding='utf-8',
        case_sensitive=False
    )


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
def get_service_config() -> ServiceConfig:
    """Get service configuration."""
    return get_settings().service


def get_database_config() -> DatabaseConfig:
    """Get database configuration."""
    return get_settings().database


def get_learning_config() -> LearningConfig:
    """Get learning configuration."""
    return get_settings().learning


def get_api_config() -> APIConfig:
    """Get API configuration."""
    return get_settings().api
