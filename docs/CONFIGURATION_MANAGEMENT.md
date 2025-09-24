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
├── ProcessorConfig      # Instance identification and naming
├── LoggingConfig        # Logging levels, formats, and outputs
├── DatabaseConfig       # MongoDB, Qdrant, and Redis connections
├── LearningConfig       # Pattern learning and memory parameters
├── ProcessingConfig     # Prediction and pattern processing
├── PerformanceConfig    # Optimization and tuning settings
└── APIConfig           # Web service configuration
```

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
    MONGO_BASE_URL: str = Field(
        'mongodb://localhost:27017',
        description="MongoDB connection URL"
    )
    
    @property
    def mongo_url(self) -> str:
        """Backward compatibility property."""
        return self.MONGO_BASE_URL
```

## Configuration Sources

### 1. Environment Variables (Primary)

Environment variables are the primary configuration source:

```bash
export PROCESSOR_ID=my-processor
export LOG_LEVEL=DEBUG
export MONGO_BASE_URL=mongodb://custom:27017
export RECALL_THRESHOLD=0.5
```

### 2. Configuration Files (Secondary)

YAML or JSON configuration files can be loaded:

```yaml
# config.yaml
processor:
  processor_id: "my-processor"
  processor_name: "Custom Processor"

database:
  MONGO_BASE_URL: "mongodb://custom:27017"
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

### 3. Docker Compose (Production)

Docker Compose provides environment variables to containers:

```yaml
services:
  kato-primary:
    image: kato:latest
    environment:
      - PROCESSOR_ID=primary
      - PROCESSOR_NAME=Primary
      - MONGO_BASE_URL=mongodb://mongodb:27017
      - QDRANT_HOST=qdrant
      - LOG_LEVEL=INFO
      - MAX_PATTERN_LENGTH=0
      - RECALL_THRESHOLD=0.1
```

### 4. Programmatic (Testing/Development)

Create configuration programmatically for testing:

```python
from kato.config.settings import Settings, ProcessorConfig, DatabaseConfig

settings = Settings(
    processor=ProcessorConfig(
        processor_id="test-123",
        processor_name="Test Processor"
    ),
    database=DatabaseConfig(
        MONGO_BASE_URL="mongodb://test:27017"
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
class ProcessorConfig(BaseSettings):
    processor_id: Optional[str] = Field(None, env='PROCESSOR_ID')
    
    @validator('processor_id', pre=True, always=True)
    def generate_processor_id(cls, v):
        """Generate processor ID if not provided."""
        if not v:
            import uuid
            import time
            return f"kato-{uuid.uuid4().hex[:8]}-{int(time.time())}"
        return v
```

### Runtime Warnings

The system checks for configuration issues at startup:

```python
def validate_configuration(self) -> List[str]:
    """Validate configuration and return warnings."""
    warnings = []
    
    if self.environment == 'production':
        if self.database.mongo_url == 'mongodb://localhost:27017':
            warnings.append("Using localhost MongoDB in production")
        if self.debug:
            warnings.append("Debug mode enabled in production")
        if self.api.cors_origins == ['*']:
            warnings.append("CORS allows all origins in production")
    
    return warnings
```

## Runtime Updates

Some configuration can be updated at runtime through the API:

### Update Gene Values

```bash
# Update recall threshold
curl -X POST http://localhost:8001/genes/update \
  -H "Content-Type: application/json" \
  -d '{
    "genes": {
      "recall_threshold": 0.5,
      "max_predictions": 50
    }
  }'
```

### Query Current Values

```bash
# Get specific gene value
curl http://localhost:8001/gene/recall_threshold

# Get full status including configuration
curl http://localhost:8001/status
```

## Configuration Reference

### ProcessorConfig

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| PROCESSOR_ID | str | auto-generated | Unique identifier for processor instance |
| PROCESSOR_NAME | str | "KatoProcessor" | Display name for the processor |

### LoggingConfig

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| LOG_LEVEL | str | "INFO" | Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL) |
| LOG_FORMAT | str | "human" | Output format ("json" or "human") |
| LOG_OUTPUT | str | "stdout" | Output destination (stdout, stderr, or file path) |

### DatabaseConfig

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| MONGO_BASE_URL | str | "mongodb://localhost:27017" | MongoDB connection URL |
| MONGO_TIMEOUT | int | 5000 | Connection timeout in milliseconds |
| QDRANT_HOST | str | "localhost" | Qdrant host address |
| QDRANT_PORT | int | 6333 | Qdrant HTTP port |
| QDRANT_GRPC_PORT | int | 6334 | Qdrant gRPC port |
| QDRANT_COLLECTION_PREFIX | str | "vectors" | Collection name prefix |
| REDIS_ENABLED | bool | false | Enable Redis caching |
| REDIS_HOST | str | None | Redis host (if enabled) |
| REDIS_PORT | int | 6379 | Redis port |

### LearningConfig

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| MAX_PATTERN_LENGTH | int | 0 | Auto-learn after N observations (0 = manual) |
| PERSISTENCE | int | 5 | Rolling window size for emotive values per pattern |
| RECALL_THRESHOLD | float | 0.1 | Pattern matching threshold (0.0-1.0) |
| AUTO_LEARN_ENABLED | bool | false | Enable automatic learning |
| AUTO_LEARN_THRESHOLD | int | 50 | Observations before auto-learning |

### ProcessingConfig

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| INDEXER_TYPE | str | "VI" | Type of vector indexer |
| MAX_PREDICTIONS | int | 100 | Maximum predictions to return |
| SORT | bool | true | Sort symbols alphabetically |
| PROCESS_PREDICTIONS | bool | true | Enable prediction processing |

### PerformanceConfig

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| KATO_USE_FAST_MATCHING | bool | true | Use optimized matching algorithms |
| KATO_USE_INDEXING | bool | true | Use pattern indexing |
| KATO_USE_OPTIMIZED | bool | true | Enable general optimizations |
| KATO_BATCH_SIZE | int | 1000 | Batch size for bulk operations |
| KATO_VECTOR_BATCH_SIZE | int | 1000 | Batch size for vector operations |
| KATO_VECTOR_SEARCH_LIMIT | int | 100 | Maximum vector search results |
| CONNECTION_POOL_SIZE | int | 10 | Database connection pool size |
| REQUEST_TIMEOUT | float | 30.0 | Request timeout in seconds |

### APIConfig

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| HOST | str | "0.0.0.0" | API host address |
| PORT | int | 8000 | API port number |
| WORKERS | int | 1 | Number of worker processes |
| CORS_ENABLED | bool | true | Enable CORS support |
| CORS_ORIGINS | str | "*" | Allowed origins (comma-separated) |
| DOCS_ENABLED | bool | true | Enable API documentation |
| MAX_REQUEST_SIZE | int | 104857600 | Maximum request size (bytes) |

## Troubleshooting

### Common Issues

#### 1. Environment Variables Not Loading

**Problem**: Settings use default values despite environment variables being set.

**Solution**: Ensure environment variables are set before container starts:
```yaml
# docker-compose.yml
environment:
  - MONGO_BASE_URL=mongodb://mongodb:27017  # Use service name, not localhost
```

#### 2. Pydantic Validation Errors

**Problem**: Application fails to start with validation errors.

**Solution**: Check that all required fields are provided and values are within valid ranges:
```bash
# Example: RECALL_THRESHOLD must be between 0.0 and 1.0
export RECALL_THRESHOLD=0.5  # Valid
export RECALL_THRESHOLD=1.5  # Invalid - will cause error
```

#### 3. Configuration Not Updating

**Problem**: Changes to environment variables don't take effect.

**Solution**: Restart the service - configuration is loaded at startup:
```bash
./kato-manager.sh restart
```

#### 4. Docker Network Issues

**Problem**: Services can't connect to databases.

**Solution**: Use Docker service names, not localhost:
```yaml
# Correct for Docker
MONGO_BASE_URL: "mongodb://mongodb:27017"
QDRANT_HOST: "qdrant"

# Wrong for Docker (only works locally)
MONGO_BASE_URL: "mongodb://localhost:27017"
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