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

from pydantic import AliasChoices, ConfigDict, Field, field_validator, model_validator
from pydantic_settings import BaseSettings


class ServiceConfig(BaseSettings):
    """Service-level configuration."""

    service_name: str = Field(
        'kato',
        json_schema_extra={'env': 'SERVICE_NAME'},
        description="Service name identifier"
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

    @property
    def qdrant_host(self) -> str:
        return self.QDRANT_HOST

    @property
    def qdrant_port(self) -> int:
        return self.QDRANT_PORT

    @property
    def qdrant_grpc_port(self) -> int:
        return self.QDRANT_GRPC_PORT


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
        scheme = "https" if self.QDRANT_HTTPS else "http"
        return f"{scheme}://{self.qdrant_host}:{self.qdrant_port}"

    @property
    def qdrant_grpc_url(self) -> str:
        """Get Qdrant gRPC connection URL."""
        return f"{self.qdrant_host}:{self.qdrant_grpc_port}"

    @property
    def redis_url(self) -> Optional[str]:
        """Get Redis connection URL if enabled."""
        # Prefer REDIS_URL env var if set
        if self.REDIS_URL:
            url = self.REDIS_URL
            # Upgrade to TLS scheme if REDIS_TLS is enabled
            if self.REDIS_TLS and url.startswith("redis://"):
                url = "rediss://" + url[len("redis://"):]
            return url
        # Fallback to constructing from host/port for backwards compatibility
        if self.redis_enabled and self.redis_host:
            scheme = "rediss" if self.REDIS_TLS else "redis"
            return f"{scheme}://{self.redis_host}:{self.redis_port}/0"
        return None

    # ClickHouse settings (for hybrid architecture)
    CLICKHOUSE_HOST: str = Field(
        'localhost',
        description="ClickHouse host address"
    )
    CLICKHOUSE_PORT: int = Field(
        8123,
        ge=1,
        le=65535,
        description="ClickHouse HTTP port number"
    )
    CLICKHOUSE_DB: str = Field(
        'kato',
        description="ClickHouse database name"
    )
    CLICKHOUSE_USER: str = Field(
        'default',
        description="ClickHouse username"
    )
    CLICKHOUSE_PASSWORD: Optional[str] = Field(
        None,
        description="ClickHouse password"
    )
    CLICKHOUSE_SECURE: bool = Field(
        False,
        description="Use HTTPS for ClickHouse connection"
    )

    # Redis TLS
    REDIS_TLS: bool = Field(
        False,
        description="Use TLS for Redis connection (upgrades redis:// to rediss:// scheme)"
    )

    # Qdrant authentication
    QDRANT_API_KEY: Optional[str] = Field(
        None,
        description="Qdrant API key for authentication"
    )
    QDRANT_HTTPS: bool = Field(
        False,
        description="Use HTTPS for Qdrant connection (auto-set by qdrant-client when api_key is provided; explicitly set False for local Docker)"
    )

    @property
    def clickhouse_host(self) -> str:
        return self.CLICKHOUSE_HOST

    @property
    def clickhouse_port(self) -> int:
        return self.CLICKHOUSE_PORT

    @property
    def clickhouse_db(self) -> str:
        return self.CLICKHOUSE_DB

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
        description="Sort symbols alphabetically within events"
    )
    process_predictions: bool = Field(
        True,
        json_schema_extra={'env': 'PROCESS_PREDICTIONS'},
        description="Enable prediction processing"
    )
    use_token_matching: bool = Field(
        True,
        validation_alias=AliasChoices('use_token_matching', 'KATO_USE_TOKEN_MATCHING'),
        description="Use token-level matching (True) vs character-level matching (False)"
    )
    fuzzy_token_threshold: float = Field(
        0.0,
        validation_alias=AliasChoices('fuzzy_token_threshold', 'KATO_FUZZY_TOKEN_THRESHOLD'),
        description="Fuzzy token matching threshold (0.0-1.0, 0.0=disabled). Tokens above threshold are fuzzy matched."
    )
    rank_sort_algo: str = Field(
        'potential',
        json_schema_extra={'env': 'RANK_SORT_ALGO'},
        description="Metric to use for ranking predictions (potential, similarity, evidence, confidence, snr, etc.)"
    )

    model_config = ConfigDict(env_prefix='')


class PerformanceConfig(BaseSettings):
    """Performance optimization configuration."""

    use_fast_matching: bool = Field(
        True,
        validation_alias=AliasChoices('use_fast_matching', 'KATO_USE_FAST_MATCHING'),
        description="Use optimized fast matching algorithms"
    )
    use_indexing: bool = Field(
        True,
        validation_alias=AliasChoices('use_indexing', 'KATO_USE_INDEXING'),
        description="Use pattern indexing for faster lookups"
    )
    connection_pool_size: int = Field(
        200,
        ge=1,
        le=1000,
        description=(
            "Max Redis connections per worker. Default 200 matches the value "
            "previously hardcoded in connection_manager.py."
        )
    )
    request_timeout: float = Field(
        30.0,
        ge=1.0,
        le=300.0,
        description=(
            "ClickHouse send/receive timeout in seconds. Default 30.0 matches "
            "the value previously hardcoded in connection_manager.py. Does not "
            "affect the Qdrant or Redis clients, which have their own timeouts."
        )
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
        validation_alias=AliasChoices('config_file', 'KATO_CONFIG_FILE'),
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

        if self.environment == 'production' and self.debug:
            warnings.append("Debug mode enabled in production environment")

        return warnings

    # NOTE: do NOT add env_file= here. pydantic-settings' DotEnvSettingsSource
    # enumerates every key in the file and forwards the ones it cannot match onto
    # this model; with extra='forbid' (the BaseSettings default) any key that is
    # not one of the fields above raises extra_forbidden. That crashed every
    # non-Docker start on REDIS_PERSISTENCE, a docker-compose-only variable.
    #
    # .env is loaded into os.environ by kato/env_loader.py instead. That is also
    # the only way the nested configs above (each built via default_factory and
    # reading os.environ independently) and the raw os.environ readers elsewhere
    # in kato/ can see it.
    #
    # extra stays 'forbid': it is what makes an unknown key in a KATO_CONFIG_FILE
    # YAML/JSON fail loudly in load_from_file() above.
    model_config = ConfigDict(
        env_prefix='',
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
