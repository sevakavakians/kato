# Exception Types Reference

Python exception hierarchy for KATO errors.

## Exception Hierarchy

```
KatoBaseException
├── ConfigurationError
│   ├── InvalidConfigurationError
│   └── MissingConfigurationError
├── ProcessingError
│   ├── ObservationError
│   ├── PatternError
│   └── PredictionError
├── StorageError
│   ├── DatabaseError
│   ├── VectorStoreError
│   └── CacheError
└── ValidationError
    ├── VectorDimensionError
    └── ParameterValidationError
```

## Base Exception

### KatoBaseException

**Description**: Base class for all KATO exceptions

**Attributes**:
- `message`: Error message
- `context`: Additional context dictionary

**Usage**:

```python
class KatoBaseException(Exception):
    def __init__(self, message: str, context: dict = None):
        self.message = message
        self.context = context or {}
        super().__init__(self.message)
```

## Configuration Exceptions

### ConfigurationError

**Description**: Base for configuration-related errors

**Subclasses**:
- `InvalidConfigurationError`: Invalid configuration value
- `MissingConfigurationError`: Required configuration missing

**Example**:

```python
raise InvalidConfigurationError(
    "recall_threshold must be between 0.0 and 1.0",
    context={"value": 1.5}
)
```

## Processing Exceptions

### ProcessingError

**Description**: Base for processing-related errors

**Subclasses**:
- `ObservationError`: Observation processing failed
- `PatternError`: Pattern creation/retrieval failed
- `PredictionError`: Prediction generation failed

**Example**:

```python
raise ObservationError(
    "Failed to process observation",
    context={"observation_id": "obs_123"}
)
```

## Storage Exceptions

### StorageError

**Description**: Base for storage-related errors

**Subclasses**:
- `DatabaseError`: MongoDB operations failed
- `VectorStoreError`: Qdrant operations failed
- `CacheError`: Redis operations failed

**Example**:

```python
raise DatabaseError(
    "Failed to connect to MongoDB",
    context={"url": "mongodb://localhost:27017"}
)
```

## Validation Exceptions

### ValidationError

**Description**: Base for validation errors

**Subclasses**:
- `VectorDimensionError`: Vector dimension mismatch
- `ParameterValidationError`: Invalid parameter value

### VectorDimensionError

**Description**: Vector dimension mismatch (expected: 768)

**Attributes**:
- `expected_dimension`: Expected dimension (768)
- `actual_dimension`: Actual dimension
- `vector_name`: Vector symbol name

**Example**:

```python
raise VectorDimensionError(
    "Vector dimension mismatch",
    context={
        "expected_dimension": 768,
        "actual_dimension": 512,
        "vector_name": "VCTR|abc123..."
    }
)
```

**HTTP Response** (400):

```json
{
  "detail": {
    "error": "VectorDimensionError",
    "message": "Vector dimension mismatch",
    "expected_dimension": 768,
    "actual_dimension": 512,
    "vector_name": "VCTR|abc123..."
  }
}
```

## Exception Handling

### Catching Specific Exceptions

```python
from kato.exceptions import VectorDimensionError, ConfigurationError

try:
    processor.observe(observation)
except VectorDimensionError as e:
    print(f"Vector dimension error: {e.message}")
    print(f"Expected: {e.context['expected_dimension']}")
    print(f"Got: {e.context['actual_dimension']}")
except ConfigurationError as e:
    print(f"Configuration error: {e.message}")
except Exception as e:
    print(f"Unexpected error: {e}")
```

### Logging with Context

```python
import logging

logger = logging.getLogger(__name__)

try:
    pattern_name = learn_pattern(stm)
except PatternError as e:
    logger.error(
        f"Pattern error: {e.message}",
        extra={"context": e.context}
    )
    raise
```

### Converting to HTTP Errors

```python
from fastapi import HTTPException
from kato.exceptions import VectorDimensionError

try:
    result = await processor.observe(observation)
except VectorDimensionError as e:
    raise HTTPException(
        status_code=400,
        detail={
            "error": "VectorDimensionError",
            "message": e.message,
            **e.context
        }
    )
```

## See Also

- [Error Codes](error-codes.md) - HTTP error codes
- [API Reference](api/README.md) - API error responses
- [Troubleshooting](../users/troubleshooting.md) - Common issues

---

**Last Updated**: November 2025
**KATO Version**: 3.0+
