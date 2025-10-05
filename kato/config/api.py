"""
API Configuration Module for KATO

Provides comprehensive API service configuration including endpoints,
middleware, security, rate limiting, and service discovery.
"""

from typing import Any, Dict, List, Literal, Optional

from pydantic import Field, HttpUrl, validator

try:
    from pydantic_settings import BaseSettings
except ImportError:
    # Fallback for older Pydantic versions
    from pydantic import BaseSettings


class CORSConfig(BaseSettings):
    """CORS (Cross-Origin Resource Sharing) configuration."""

    enabled: bool = Field(True, env='CORS_ENABLED')
    allow_origins: List[str] = Field(['*'], env='CORS_ALLOW_ORIGINS')
    allow_methods: List[str] = Field(['*'], env='CORS_ALLOW_METHODS')
    allow_headers: List[str] = Field(['*'], env='CORS_ALLOW_HEADERS')
    allow_credentials: bool = Field(True, env='CORS_ALLOW_CREDENTIALS')
    expose_headers: List[str] = Field([], env='CORS_EXPOSE_HEADERS')
    max_age: int = Field(3600, env='CORS_MAX_AGE')

    @validator('allow_origins', 'allow_methods', 'allow_headers', 'expose_headers', pre=True)
    def parse_list(cls, v):
        """Parse comma-separated string to list."""
        if isinstance(v, str):
            return [item.strip() for item in v.split(',') if item.strip()]
        return v

    class Config:
        env_prefix = 'CORS_'


class RateLimitConfig(BaseSettings):
    """Rate limiting configuration."""

    enabled: bool = Field(False, env='RATE_LIMIT_ENABLED')
    default_limit: str = Field('100/minute', env='RATE_LIMIT_DEFAULT')

    # Specific endpoint limits
    observe_limit: str = Field('1000/minute', env='RATE_LIMIT_OBSERVE')
    predict_limit: str = Field('500/minute', env='RATE_LIMIT_PREDICT')
    learn_limit: str = Field('10/minute', env='RATE_LIMIT_LEARN')

    # Storage backend
    storage_backend: Literal['memory', 'redis'] = Field('memory', env='RATE_LIMIT_STORAGE')
    redis_url: Optional[str] = Field(None, env='RATE_LIMIT_REDIS_URL')

    # Headers
    header_limit: str = Field('X-RateLimit-Limit', env='RATE_LIMIT_HEADER_LIMIT')
    header_remaining: str = Field('X-RateLimit-Remaining', env='RATE_LIMIT_HEADER_REMAINING')
    header_reset: str = Field('X-RateLimit-Reset', env='RATE_LIMIT_HEADER_RESET')

    class Config:
        env_prefix = ''


class AuthenticationConfig(BaseSettings):
    """Authentication configuration."""

    enabled: bool = Field(False, env='AUTH_ENABLED')
    type: Literal['none', 'api_key', 'jwt', 'oauth2'] = Field('none', env='AUTH_TYPE')

    # API Key authentication
    api_key_header: str = Field('X-API-Key', env='AUTH_API_KEY_HEADER')
    api_keys: List[str] = Field([], env='AUTH_API_KEYS')

    # JWT authentication
    jwt_secret: Optional[str] = Field(None, env='AUTH_JWT_SECRET')
    jwt_algorithm: str = Field('HS256', env='AUTH_JWT_ALGORITHM')
    jwt_expiration: int = Field(3600, env='AUTH_JWT_EXPIRATION')

    # OAuth2 configuration
    oauth2_provider: Optional[str] = Field(None, env='AUTH_OAUTH2_PROVIDER')
    oauth2_client_id: Optional[str] = Field(None, env='AUTH_OAUTH2_CLIENT_ID')
    oauth2_client_secret: Optional[str] = Field(None, env='AUTH_OAUTH2_CLIENT_SECRET')
    oauth2_redirect_uri: Optional[str] = Field(None, env='AUTH_OAUTH2_REDIRECT_URI')

    @validator('api_keys', pre=True)
    def parse_api_keys(cls, v):
        """Parse API keys from string or list."""
        if isinstance(v, str):
            return [key.strip() for key in v.split(',') if key.strip()]
        return v

    class Config:
        env_prefix = ''


class WebSocketConfig(BaseSettings):
    """WebSocket configuration."""

    enabled: bool = Field(True, env='WEBSOCKET_ENABLED')
    path: str = Field('/ws', env='WEBSOCKET_PATH')
    ping_interval: int = Field(30, env='WEBSOCKET_PING_INTERVAL')
    ping_timeout: int = Field(10, env='WEBSOCKET_PING_TIMEOUT')
    max_connections: int = Field(100, env='WEBSOCKET_MAX_CONNECTIONS')
    max_message_size: int = Field(1024 * 1024, env='WEBSOCKET_MAX_MESSAGE_SIZE')  # 1MB

    class Config:
        env_prefix = ''


class MetricsConfig(BaseSettings):
    """Metrics and monitoring configuration."""

    enabled: bool = Field(True, env='METRICS_ENABLED')
    endpoint: str = Field('/metrics', env='METRICS_ENDPOINT')

    # Prometheus metrics
    prometheus_enabled: bool = Field(False, env='PROMETHEUS_ENABLED')
    prometheus_port: int = Field(9090, env='PROMETHEUS_PORT')

    # Custom metrics
    track_request_duration: bool = Field(True, env='METRICS_REQUEST_DURATION')
    track_request_size: bool = Field(True, env='METRICS_REQUEST_SIZE')
    track_response_size: bool = Field(True, env='METRICS_RESPONSE_SIZE')
    track_error_rate: bool = Field(True, env='METRICS_ERROR_RATE')

    # Performance profiling
    profiling_enabled: bool = Field(False, env='PROFILING_ENABLED')
    profiling_endpoint: str = Field('/profile', env='PROFILING_ENDPOINT')

    class Config:
        env_prefix = ''


class HealthCheckConfig(BaseSettings):
    """Health check configuration."""

    enabled: bool = Field(True, env='HEALTH_CHECK_ENABLED')
    endpoint: str = Field('/health', env='HEALTH_CHECK_ENDPOINT')
    detailed_endpoint: str = Field('/health/detailed', env='HEALTH_CHECK_DETAILED_ENDPOINT')

    # Liveness and readiness probes
    liveness_endpoint: str = Field('/health/live', env='LIVENESS_ENDPOINT')
    readiness_endpoint: str = Field('/health/ready', env='READINESS_ENDPOINT')

    # Health check components
    check_database: bool = Field(True, env='HEALTH_CHECK_DATABASE')
    check_vector_db: bool = Field(True, env='HEALTH_CHECK_VECTOR_DB')
    check_cache: bool = Field(True, env='HEALTH_CHECK_CACHE')
    check_disk_space: bool = Field(True, env='HEALTH_CHECK_DISK_SPACE')
    check_memory: bool = Field(True, env='HEALTH_CHECK_MEMORY')

    # Thresholds
    disk_space_threshold: float = Field(0.9, env='HEALTH_DISK_THRESHOLD')  # 90% usage
    memory_threshold: float = Field(0.9, env='HEALTH_MEMORY_THRESHOLD')  # 90% usage

    class Config:
        env_prefix = ''


class DocumentationConfig(BaseSettings):
    """API documentation configuration."""

    enabled: bool = Field(True, env='DOCS_ENABLED')
    title: str = Field('KATO API', env='DOCS_TITLE')
    description: str = Field(
        'Knowledge Abstraction for Traceable Outcomes - FastAPI Service',
        env='DOCS_DESCRIPTION'
    )
    version: str = Field('1.0.0', env='DOCS_VERSION')

    # Endpoints
    openapi_url: str = Field('/openapi.json', env='DOCS_OPENAPI_URL')
    docs_url: str = Field('/docs', env='DOCS_URL')
    redoc_url: str = Field('/redoc', env='DOCS_REDOC_URL')

    # Contact info
    contact_name: Optional[str] = Field(None, env='DOCS_CONTACT_NAME')
    contact_email: Optional[str] = Field(None, env='DOCS_CONTACT_EMAIL')
    contact_url: Optional[HttpUrl] = Field(None, env='DOCS_CONTACT_URL')

    # License info
    license_name: Optional[str] = Field(None, env='DOCS_LICENSE_NAME')
    license_url: Optional[HttpUrl] = Field(None, env='DOCS_LICENSE_URL')

    # Security
    include_schemas: bool = Field(True, env='DOCS_INCLUDE_SCHEMAS')

    class Config:
        env_prefix = ''


class EndpointConfig(BaseSettings):
    """Individual endpoint configuration."""

    # Core endpoints
    observe_enabled: bool = Field(True, env='ENDPOINT_OBSERVE_ENABLED')
    observe_sequence_enabled: bool = Field(True, env='ENDPOINT_OBSERVE_SEQUENCE_ENABLED')
    learn_enabled: bool = Field(True, env='ENDPOINT_LEARN_ENABLED')
    predict_enabled: bool = Field(True, env='ENDPOINT_PREDICT_ENABLED')

    # Memory endpoints
    stm_enabled: bool = Field(True, env='ENDPOINT_STM_ENABLED')
    clear_stm_enabled: bool = Field(True, env='ENDPOINT_CLEAR_STM_ENABLED')
    clear_all_enabled: bool = Field(True, env='ENDPOINT_CLEAR_ALL_ENABLED')

    # Advanced endpoints
    pattern_enabled: bool = Field(True, env='ENDPOINT_PATTERN_ENABLED')
    genes_enabled: bool = Field(True, env='ENDPOINT_GENES_ENABLED')
    percept_enabled: bool = Field(True, env='ENDPOINT_PERCEPT_ENABLED')
    cognition_enabled: bool = Field(True, env='ENDPOINT_COGNITION_ENABLED')

    # Batch processing
    batch_size_limit: int = Field(1000, env='ENDPOINT_BATCH_SIZE_LIMIT')
    batch_timeout: int = Field(30, env='ENDPOINT_BATCH_TIMEOUT')

    class Config:
        env_prefix = ''


class ServiceDiscoveryConfig(BaseSettings):
    """Service discovery and registration configuration."""

    enabled: bool = Field(False, env='SERVICE_DISCOVERY_ENABLED')
    type: Literal['consul', 'etcd', 'kubernetes', 'dns'] = Field('consul', env='SERVICE_DISCOVERY_TYPE')

    # Service registration
    service_name: str = Field('kato-api', env='SERVICE_NAME')
    service_id: Optional[str] = Field(None, env='SERVICE_ID')
    service_tags: List[str] = Field(['kato', 'api'], env='SERVICE_TAGS')

    # Consul configuration
    consul_host: str = Field('localhost', env='CONSUL_HOST')
    consul_port: int = Field(8500, env='CONSUL_PORT')
    consul_token: Optional[str] = Field(None, env='CONSUL_TOKEN')

    # Health check registration
    register_health_check: bool = Field(True, env='REGISTER_HEALTH_CHECK')
    health_check_interval: str = Field('10s', env='HEALTH_CHECK_INTERVAL')
    health_check_timeout: str = Field('5s', env='HEALTH_CHECK_TIMEOUT')

    @validator('service_tags', pre=True)
    def parse_tags(cls, v):
        """Parse service tags from string or list."""
        if isinstance(v, str):
            return [tag.strip() for tag in v.split(',') if tag.strip()]
        return v

    class Config:
        env_prefix = ''


class APIServiceConfig(BaseSettings):
    """Main API service configuration."""

    # Server settings
    host: str = Field('0.0.0.0', env='API_HOST')
    port: int = Field(8000, env='API_PORT', ge=1, le=65535)
    workers: int = Field(1, env='API_WORKERS', ge=1)
    reload: bool = Field(False, env='API_RELOAD')

    # Request/Response settings
    max_request_size: int = Field(100 * 1024 * 1024, env='MAX_REQUEST_SIZE')  # 100MB
    request_timeout: int = Field(30, env='REQUEST_TIMEOUT')
    keep_alive: int = Field(5, env='KEEP_ALIVE')

    # Middleware configuration
    cors: CORSConfig = Field(default_factory=CORSConfig)
    rate_limit: RateLimitConfig = Field(default_factory=RateLimitConfig)
    authentication: AuthenticationConfig = Field(default_factory=AuthenticationConfig)

    # Feature configuration
    websocket: WebSocketConfig = Field(default_factory=WebSocketConfig)
    metrics: MetricsConfig = Field(default_factory=MetricsConfig)
    health_check: HealthCheckConfig = Field(default_factory=HealthCheckConfig)
    documentation: DocumentationConfig = Field(default_factory=DocumentationConfig)
    endpoints: EndpointConfig = Field(default_factory=EndpointConfig)
    service_discovery: ServiceDiscoveryConfig = Field(default_factory=ServiceDiscoveryConfig)

    # Logging
    access_log: bool = Field(True, env='ACCESS_LOG')
    access_log_format: str = Field(
        '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"',
        env='ACCESS_LOG_FORMAT'
    )

    @property
    def url(self) -> str:
        """Get API service URL."""
        return f"http://{self.host}:{self.port}"

    def get_uvicorn_config(self) -> Dict[str, Any]:
        """Get Uvicorn server configuration."""
        return {
            'host': self.host,
            'port': self.port,
            'workers': self.workers,
            'reload': self.reload,
            'access_log': self.access_log,
            'use_colors': True,
            'limit_max_requests': 10000,
            'timeout_keep_alive': self.keep_alive,
        }

    def validate_security(self) -> List[str]:
        """Validate security configuration."""
        warnings = []

        # Check CORS settings
        if self.cors.enabled and '*' in self.cors.allow_origins:
            warnings.append("CORS allows all origins - consider restricting in production")

        # Check authentication
        if not self.authentication.enabled:
            warnings.append("Authentication is disabled - API is publicly accessible")
        elif self.authentication.type == 'api_key' and not self.authentication.api_keys:
            warnings.append("API key authentication enabled but no keys configured")

        # Check rate limiting
        if not self.rate_limit.enabled:
            warnings.append("Rate limiting is disabled - API may be vulnerable to abuse")

        # Check documentation in production
        if self.documentation.enabled:
            warnings.append("API documentation is enabled - consider disabling in production")

        return warnings

    class Config:
        env_prefix = ''


# Convenience functions
def get_api_config() -> APIServiceConfig:
    """Get API service configuration."""
    return APIServiceConfig()


def get_cors_config() -> CORSConfig:
    """Get CORS configuration."""
    return get_api_config().cors


def get_auth_config() -> AuthenticationConfig:
    """Get authentication configuration."""
    return get_api_config().authentication
