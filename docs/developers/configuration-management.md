# Configuration Management System

## Overview

KATO's configuration management system provides a robust, type-safe way to configure all aspects of the system. Built with Pydantic v2 and implementing the Application Startup Pattern, it ensures proper configuration loading in containerized environments while maintaining flexibility for development and production deployments.

## Architecture

### Design Principles

1. **Type Safety**: All configuration validated with Pydantic models
2. **Hierarchical Organization**: Logical grouping of related settings
3. **Environment-First**: Environment variables take precedence
4. **Fail-Fast**: Invalid configuration causes immediate startup failure
5. **Zero Module-Level State**: Prevents Docker timing issues

### Configuration Sections

```
Settings (Main Configuration Class)
├── ServiceConfig        # Service name identifier
├── LoggingConfig        # Logging levels, formats, and outputs
├── DatabaseConfig       # ClickHouse, Qdrant, and Redis connections
├── LearningConfig       # Pattern learning and memory parameters
├── ProcessingConfig     # Prediction and pattern processing
├── PerformanceConfig    # Optimization and tuning settings
└── SessionConfig        # Session TTL and auto-extension
```

Two configuration readers live outside this model and read `os.environ`
directly: `kato/config/vectordb_config.py` (vector database `KATO_*`
variables) and the hot paths in `kato/searches/pattern_search.py` and
`kato/storage/clickhouse_writer.py`. `kato/env_loader.py` populates
`os.environ` from `.env` before any of the three run, so all of them observe
the same values.

## Implementation Details

### Application Startup Pattern

The system uses FastAPI's lifespan context manager to ensure configuration is loaded at the correct time:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Create fresh settings instance at startup
    settings = Settings()  # Reads current environment variables
    
    # 2. Store in app.state for global access
    app.state.settings = settings
    
    # 3. Initialize components with settings
    processor = KatoProcessor(manifest, settings=settings)
    app.state.processor = processor
    
    yield  # Application runs
    
    # 4. Cleanup on shutdown
    del app.state.processor
    del app.state.settings
```

### Dependency Injection

All routes receive configuration through FastAPI's dependency injection:

```python
async def get_processor(request: Request) -> KatoProcessor:
    """Dependency to get processor from app state."""
    return request.app.state.processor

async def get_settings(request: Request) -> Settings:
    """Dependency to get settings from app state."""
    return request.app.state.settings

# Routes use dependencies
@app.post("/observe")
async def observe(
    data: ObservationData,
    processor: KatoProcessor = Depends(get_processor),
    settings: Settings = Depends(get_settings)
):
    # Both processor and settings available with correct configuration
```

### Pydantic v2 Compatibility

The system handles Pydantic v2's requirement that field names match environment variable names:

```python
class DatabaseConfig(BaseSettings):
    # Field name MUST match env var for pydantic-settings v2
    CLICKHOUSE_HOST: str = Field(
        'localhost',
        description="ClickHouse host address"
    )

    @property
    def clickhouse_host(self) -> str:
        """Lower-case accessor for call sites."""
        return self.CLICKHOUSE_HOST
```

Fields whose names differ from their environment variable use
`validation_alias=AliasChoices(...)`, which is how both `USE_TOKEN_MATCHING`
and `KATO_USE_TOKEN_MATCHING` resolve to the same setting.

## Configuration Sources

### 1. Environment Variables (Primary)

Environment variables are the primary configuration source:

```bash
export LOG_LEVEL=DEBUG
export CLICKHOUSE_HOST=clickhouse
export REDIS_URL=redis://redis:6379/0
export RECALL_THRESHOLD=0.5
```

### 2. Configuration Files (Secondary)

YAML or JSON configuration files can be loaded:

```yaml
# config.yaml
database:
  CLICKHOUSE_HOST: "clickhouse-server"
  QDRANT_HOST: "qdrant-server"

learning:
  max_pattern_length: 10
  recall_threshold: 0.2
  persistence: 7
```

Load via environment variable:
```bash
export KATO_CONFIG_FILE=/path/to/config.yaml
```

Unknown keys in this file fail loudly — the `Settings` model keeps Pydantic's
default `extra='forbid'`.

### 2b. `.env` File

`kato/env_loader.py` loads a `.env` file into `os.environ` before any
configuration is read. Related variables:

```bash
export KATO_ENV_FILE=/path/to/.env   # Explicit file instead of discovery
export KATO_SKIP_DOTENV=1            # Disable .env loading entirely
```

### 3. Docker Compose (Production)

Docker Compose provides environment variables to containers:

```yaml
services:
  kato:
    image: kato:latest
    environment:
      - SERVICE_NAME=kato
      - CLICKHOUSE_HOST=clickhouse
      - REDIS_URL=redis://redis:6379/0
      - QDRANT_HOST=qdrant
      - LOG_LEVEL=INFO
      - MAX_PATTERN_LENGTH=0
      - RECALL_THRESHOLD=0.1
```

### 4. Programmatic (Testing/Development)

Create configuration programmatically for testing:

```python
from kato.config.settings import DatabaseConfig, LearningConfig, Settings

settings = Settings(
    database=DatabaseConfig(
        CLICKHOUSE_HOST="clickhouse-test"
    ),
    learning=LearningConfig(
        recall_threshold=0.5
    )
)
```

## Configuration Precedence

Configuration sources are applied in this order (later overrides earlier):

1. Default values in Pydantic models
2. Configuration file (if KATO_CONFIG_FILE is set)
3. Environment variables
4. Programmatic settings (if provided)

## Validation

### Automatic Validation

Pydantic automatically validates:
- Type correctness (int, float, str, bool, etc.)
- Value ranges (using Field constraints)
- Required vs optional fields
- Custom validators

Example validators:
```python
class LearningConfig(BaseSettings):
    max_pattern_length: int = Field(0, ge=0)

    @field_validator('max_pattern_length')
    @classmethod
    def validate_pattern_length(cls, v):
        """Validate pattern length configuration."""
        if v < 0:
            raise ValueError("max_pattern_length must be non-negative")
        return v
```

### Runtime Warnings

The system checks for configuration issues at startup:

```python
def validate_configuration(self) -> list[str]:
    """Validate configuration and return warnings."""
    warnings = []

    if self.environment == 'production':
        if self.debug:
            warnings.append("Debug mode enabled in production environment")

    return warnings
```

## Runtime Updates

Some configuration can be updated at runtime through the API:

### Update Session Config

```bash
# Update recall threshold
curl -X POST http://localhost:8000/sessions/{session_id}/config \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "recall_threshold": 0.5,
      "max_predictions": 50
    }
  }'
```

### Query Current Config

```bash
# Get session configuration
curl http://localhost:8000/sessions/{session_id}/config

# Get full status including configuration
curl http://localhost:8000/status
```

## Configuration Reference

### ServiceConfig

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| SERVICE_NAME | str | "kato" | Service name identifier |

### LoggingConfig

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| LOG_LEVEL | str | "INFO" | Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL) |
| LOG_FORMAT | str | "human" | Output format ("json" or "human") |
| LOG_OUTPUT | str | "stdout" | Output destination (stdout, stderr, or file path) |

`LOG_FORMAT=json` emits structured records including `trace_id` and
`duration_ms`. Logs default to **stdout**; earlier versions initialized logging
with `logging.basicConfig` and therefore wrote to stderr.

### DatabaseConfig

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| CLICKHOUSE_HOST | str | "localhost" | ClickHouse host address |
| CLICKHOUSE_PORT | int | 8123 | ClickHouse HTTP port |
| CLICKHOUSE_DB | str | "kato" | ClickHouse database name |
| CLICKHOUSE_USER | str | "default" | ClickHouse username |
| CLICKHOUSE_PASSWORD | str | None | ClickHouse password |
| CLICKHOUSE_SECURE | bool | false | Use HTTPS for ClickHouse |
| QDRANT_HOST | str | "localhost" | Qdrant host address |
| QDRANT_PORT | int | 6333 | Qdrant HTTP port |
| QDRANT_GRPC_PORT | int | 6334 | Qdrant gRPC port |
| QDRANT_API_KEY | str | None | Qdrant API key |
| QDRANT_HTTPS | bool | false | Use HTTPS for Qdrant |
| REDIS_URL | str | None | Redis connection URL (preferred) |
| REDIS_ENABLED | bool | false | Enable Redis caching |
| REDIS_HOST | str | None | Redis host (deprecated, use REDIS_URL) |
| REDIS_PORT | int | 6379 | Redis port (deprecated) |
| REDIS_TLS | bool | false | Use TLS for Redis |

Qdrant collection names are not configurable; KATO always uses
`vectors_{processor_id}`.

### LearningConfig

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| MAX_PATTERN_LENGTH | int | 0 | Auto-learn after N observations (0 = manual) |
| PERSISTENCE | int | 5 | Rolling window size for emotive values per pattern |
| RECALL_THRESHOLD | float | 0.1 | Pattern matching threshold (>0.0-1.0) |
| STM_MODE | str | "CLEAR" | STM mode after auto-learn (CLEAR or ROLLING) |

Auto-learning is driven solely by `MAX_PATTERN_LENGTH`: any value above `0`
enables it.

### ProcessingConfig

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| INDEXER_TYPE | str | "VI" | Type of vector indexer |
| MAX_PREDICTIONS | int | 100 | Maximum predictions to return |
| SORT_SYMBOLS | bool | true | Sort symbols alphabetically |
| PROCESS_PREDICTIONS | bool | true | Enable prediction processing |
| USE_TOKEN_MATCHING / KATO_USE_TOKEN_MATCHING | bool | true | Token-level vs character-level matching |
| FUZZY_TOKEN_THRESHOLD / KATO_FUZZY_TOKEN_THRESHOLD | float | 0.0 | Fuzzy token threshold (0.0 = disabled) |
| RANK_SORT_ALGO | str | "potential" | Prediction ranking metric |

### PerformanceConfig

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| USE_FAST_MATCHING / KATO_USE_FAST_MATCHING | bool | true | Use optimized matching algorithms |
| USE_INDEXING / KATO_USE_INDEXING | bool | true | Use pattern indexing |
| KATO_USE_BLOOM_FILTER | bool | true | Bloom filter pre-screening in pattern search |
| KATO_USE_REDIS_CACHE | bool | true | Redis-backed pattern cache in pattern search |
| CONNECTION_POOL_SIZE | int | 200 | Max Redis connections per worker |
| REQUEST_TIMEOUT | float | 30.0 | ClickHouse send/receive timeout in seconds |
| MINHASH_HASH_FUNC | str | "sha1" | MinHash hash function ("sha1" or "xxhash") |

`REQUEST_TIMEOUT` applies to the ClickHouse client only; Qdrant and Redis have
their own timeouts. There is no batch-size setting: ClickHouse batching is
server-side via `async_insert`, and the client-side write buffer is
deliberately disabled because per-worker buffers orphaned rows across uvicorn
workers.

Switching `MINHASH_HASH_FUNC` to `xxhash` is faster but changes the hashes, so
existing patterns must be reindexed.

### SessionConfig

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| SESSION_TTL | int | 3600 | Session time-to-live in seconds |
| SESSION_AUTO_EXTEND | bool | true | Extend TTL on each access |

### Worker and Concurrency

Read by the uvicorn command in the Dockerfile and by the `/concurrency`
endpoint. There is no `APIConfig`: host, port and worker count come from the
uvicorn command line, and CORS is applied unconditionally with
`allow_origins=["*"]`.

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| KATO_WORKERS | int | 4 | uvicorn worker processes |
| KATO_LIMIT_CONCURRENCY | int | 100 | Max concurrent connections per worker |

## Troubleshooting

### Common Issues

#### 1. Environment Variables Not Loading

**Problem**: Settings use default values despite environment variables being set.

**Solution**: Ensure environment variables are set before container starts:
```yaml
# docker compose.yml
environment:
  - CLICKHOUSE_HOST=clickhouse  # Use service name, not localhost
```

#### 2. Pydantic Validation Errors

**Problem**: Application fails to start with validation errors.

**Solution**: Check that all required fields are provided and values are within valid ranges:
```bash
# Example: RECALL_THRESHOLD must be greater than 0.0 and at most 1.0
export RECALL_THRESHOLD=0.5  # Valid
export RECALL_THRESHOLD=1.5  # Invalid - will cause error
```

#### 3. Configuration Not Updating

**Problem**: Changes to environment variables don't take effect.

**Solution**: Restart the service - configuration is loaded at startup:
```bash
docker compose restart
```

#### 4. Docker Network Issues

**Problem**: Services can't connect to databases.

**Solution**: Use Docker service names, not localhost:
```yaml
# Correct for Docker
CLICKHOUSE_HOST: "clickhouse"
REDIS_URL: "redis://redis:6379/0"
QDRANT_HOST: "qdrant"

# Wrong for Docker (only works locally)
CLICKHOUSE_HOST: "localhost"
REDIS_URL: "redis://localhost:6379/0"
QDRANT_HOST: "localhost"
```

## Best Practices

1. **Environment-Specific Files**: Use separate `.env` files for development, testing, and production
2. **Secrets Management**: Never commit sensitive configuration to version control
3. **Validation Testing**: Test configuration changes in development before production
4. **Documentation**: Document any custom configuration requirements for your deployment
5. **Monitoring**: Log configuration warnings and monitor for issues
6. **Defaults**: Use sensible defaults that work for most cases
7. **Gradual Changes**: Make configuration changes incrementally and test each change

## Migration Guide

### From Module-Level Settings (Old)

```python
# OLD: Module-level singleton (problematic in Docker)
settings = Settings()  # Created at import time

@app.post("/observe")
async def observe(data: ObservationData):
    # Uses module-level settings
    processor.observe(data)
```

### To Application Startup Pattern (New)

```python
# NEW: Created at startup with lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings()  # Created at startup
    app.state.settings = settings
    yield

@app.post("/observe")
async def observe(
    data: ObservationData,
    processor: KatoProcessor = Depends(get_processor)
):
    # Uses injected processor with correct settings
    processor.observe(data)
```

### Benefits of New Approach

1. **Correct Timing**: Settings read after Docker environment is ready
2. **Testability**: Easy to inject test configurations
3. **Clarity**: Explicit dependencies in function signatures
4. **Flexibility**: Different settings per route if needed
5. **Thread-Safety**: No shared mutable state

## Future Enhancements

Planned improvements to the configuration system:

1. **Hot Reload**: Support configuration updates without restart
2. **Validation CLI**: Command-line tool to validate configuration files
3. **Configuration UI**: Web interface for configuration management
4. **Encrypted Secrets**: Support for encrypted configuration values
5. **Configuration History**: Track configuration changes over time
6. **A/B Testing**: Support multiple configurations for experimentation