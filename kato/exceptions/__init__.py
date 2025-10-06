"""
KATO Exception Hierarchy
Provides specific exception types for better error handling and debugging.
"""

import time
from typing import Any, Optional


class KatoBaseException(Exception):
    """
    Base exception class for all KATO-specific exceptions.
    Provides context and trace ID tracking.
    """

    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        context: Optional[dict[str, Any]] = None,
        trace_id: Optional[str] = None
    ):
        """
        Initialize a KATO exception with context.

        Args:
            message: Human-readable error message
            error_code: Machine-readable error code for categorization
            context: Additional context about the error
            trace_id: Request trace ID for correlation
        """
        super().__init__(message)
        self.message = message
        self.error_code = error_code or self.__class__.__name__
        self.context = context or {}
        self.trace_id = trace_id

    def to_dict(self) -> dict[str, Any]:
        """
        Convert exception to dictionary for API responses.

        Returns:
            Dictionary representation of the exception
        """
        result = {
            'error': self.error_code,
            'message': self.message,
            'type': self.__class__.__name__
        }

        if self.context:
            result['context'] = self.context

        if self.trace_id:
            result['trace_id'] = self.trace_id

        return result

    def __str__(self) -> str:
        """String representation of the exception."""
        parts = [f"{self.error_code}: {self.message}"]

        if self.context:
            parts.append(f"Context: {self.context}")

        if self.trace_id:
            parts.append(f"Trace ID: {self.trace_id}")

        return " | ".join(parts)


class KatoV2Exception(KatoBaseException):
    """Base exception for all KATO v2.0 errors - extends KatoBaseException"""

    def __init__(
        self,
        message: str,
        error_code: str = "KATO_V2_ERROR",
        context: Optional[dict[str, Any]] = None,
        recoverable: bool = True,
        **kwargs
    ):
        """
        Initialize KATO v2.0 exception.

        Args:
            message: Human-readable error message
            error_code: Machine-readable error code
            context: Additional error context
            recoverable: Whether this error can be recovered from
            **kwargs: Additional arguments for base exception
        """
        # Call parent constructor with unified interface
        super().__init__(
            message=message,
            error_code=error_code,
            context=context,
            **kwargs
        )
        self.recoverable = recoverable
        self.timestamp = time.time()

    def to_dict(self) -> dict[str, Any]:
        """Convert exception to dictionary for API responses - enhanced format"""
        # Create nested error structure as expected by tests
        result = {
            'error': {
                'type': self.__class__.__name__,
                'message': self.message,
                'code': self.error_code,
                'recoverable': self.recoverable
            }
        }

        # Add optional fields
        if self.context:
            result['error']['context'] = self.context

        if hasattr(self, 'trace_id') and self.trace_id:
            result['error']['trace_id'] = self.trace_id

        result['timestamp'] = self.timestamp

        return result


class PatternProcessingError(KatoBaseException):
    """
    Raised when pattern processing fails.
    """

    def __init__(
        self,
        message: str,
        pattern_name: Optional[str] = None,
        pattern_data: Optional[Any] = None,
        **kwargs
    ):
        """
        Initialize pattern processing error.

        Args:
            message: Error message
            pattern_name: Name of the pattern that failed
            pattern_data: Pattern data that caused the error
            **kwargs: Additional arguments for base exception
        """
        context = kwargs.pop('context', {})

        if pattern_name:
            context['pattern_name'] = pattern_name
        if pattern_data is not None:
            context['pattern_data'] = str(pattern_data)[:500]  # Limit size

        super().__init__(
            message=message,
            error_code='PATTERN_PROCESSING_ERROR',
            context=context,
            **kwargs
        )


class VectorDimensionError(KatoBaseException):
    """
    Raised when vector dimensions are incorrect or mismatched.
    """

    def __init__(
        self,
        message: str,
        expected_dim: Optional[int] = None,
        actual_dim: Optional[int] = None,
        vector_name: Optional[str] = None,
        **kwargs
    ):
        """
        Initialize vector dimension error.

        Args:
            message: Error message
            expected_dim: Expected vector dimension
            actual_dim: Actual vector dimension received
            vector_name: Name or ID of the vector
            **kwargs: Additional arguments for base exception
        """
        context = kwargs.pop('context', {})

        if expected_dim is not None:
            context['expected_dimension'] = expected_dim
        if actual_dim is not None:
            context['actual_dimension'] = actual_dim
        if vector_name:
            context['vector_name'] = vector_name

        super().__init__(
            message=message,
            error_code='VECTOR_DIMENSION_ERROR',
            context=context,
            **kwargs
        )


class DatabaseConnectionError(KatoV2Exception):
    """
    Raised when database connection or operation fails.
    """

    def __init__(
        self,
        database_type: str,
        connection_string: Optional[str] = None,
        operation: Optional[str] = None,
        message: Optional[str] = None,
        context: Optional[dict[str, Any]] = None
    ):
        """
        Initialize database connection error.

        Args:
            database_type: Type of database (mongodb, qdrant, redis, etc.)
            connection_string: Database connection string
            operation: Operation that failed
            message: Optional custom error message
            context: Additional error context
        """
        if message is None:
            if operation:
                message = f"Database connection error for {database_type} during {operation}"
            else:
                message = f"Failed to connect to {database_type} database"

        super().__init__(
            message=message,
            error_code='DATABASE_CONNECTION_ERROR',
            context={
                "database_type": database_type,
                "connection_string": connection_string,
                "operation": operation,
                **(context or {})
            },
            recoverable=True  # Connection issues are often transient
        )
        self.database_type = database_type
        self.connection_string = connection_string
        self.operation = operation


class ConfigurationError(KatoBaseException):
    """
    Raised when configuration is invalid or missing.
    """

    def __init__(
        self,
        message: str,
        config_key: Optional[str] = None,
        config_value: Optional[Any] = None,
        valid_values: Optional[list] = None,
        **kwargs
    ):
        """
        Initialize configuration error.

        Args:
            message: Error message
            config_key: Configuration key that has the error
            config_value: Invalid configuration value
            valid_values: List of valid values if applicable
            **kwargs: Additional arguments for base exception
        """
        context = kwargs.pop('context', {})

        if config_key:
            context['config_key'] = config_key
        if config_value is not None:
            context['config_value'] = str(config_value)
        if valid_values:
            context['valid_values'] = valid_values

        super().__init__(
            message=message,
            error_code='CONFIGURATION_ERROR',
            context=context,
            **kwargs
        )


class ObservationError(KatoBaseException):
    """
    Raised when observation processing fails.
    """

    def __init__(
        self,
        message: str,
        observation_id: Optional[str] = None,
        observation_data: Optional[dict[str, Any]] = None,
        **kwargs
    ):
        """
        Initialize observation error.

        Args:
            message: Error message
            observation_id: ID of the observation
            observation_data: Observation data that caused the error
            **kwargs: Additional arguments for base exception
        """
        context = kwargs.pop('context', {})

        if observation_id:
            context['observation_id'] = observation_id
        if observation_data:
            # Limit the size of observation data in context
            context['observation_data'] = {
                k: str(v)[:100] if isinstance(v, (list, dict)) else v
                for k, v in observation_data.items()
            }

        super().__init__(
            message=message,
            error_code='OBSERVATION_ERROR',
            context=context,
            **kwargs
        )


class PredictionError(KatoBaseException):
    """
    Raised when prediction generation fails.
    """

    def __init__(
        self,
        message: str,
        stm_state: Optional[list] = None,
        recall_threshold: Optional[float] = None,
        **kwargs
    ):
        """
        Initialize prediction error.

        Args:
            message: Error message
            stm_state: Current STM state
            recall_threshold: Recall threshold used
            **kwargs: Additional arguments for base exception
        """
        context = kwargs.pop('context', {})

        if stm_state is not None:
            context['stm_length'] = len(stm_state)
            # Include limited STM preview
            if stm_state:
                context['stm_preview'] = str(stm_state[:2])[:200]
        if recall_threshold is not None:
            context['recall_threshold'] = recall_threshold

        super().__init__(
            message=message,
            error_code='PREDICTION_ERROR',
            context=context,
            **kwargs
        )


class LearningError(KatoBaseException):
    """
    Raised when pattern learning fails.
    """

    def __init__(
        self,
        message: str,
        stm_state: Optional[list] = None,
        auto_learn: bool = False,
        **kwargs
    ):
        """
        Initialize learning error.

        Args:
            message: Error message
            stm_state: Current STM state when learning failed
            auto_learn: Whether this was an auto-learn attempt
            **kwargs: Additional arguments for base exception
        """
        context = kwargs.pop('context', {})

        if stm_state is not None:
            context['stm_length'] = len(stm_state)
        context['auto_learn'] = auto_learn

        super().__init__(
            message=message,
            error_code='LEARNING_ERROR',
            context=context,
            **kwargs
        )


class ValidationError(KatoV2Exception):
    """
    Raised when input validation fails.
    """

    def __init__(
        self,
        field_name: str,
        field_value: Optional[Any] = None,
        validation_rule: Optional[str] = None,
        message: Optional[str] = None,
        context: Optional[dict[str, Any]] = None
    ):
        """
        Initialize validation error.

        Args:
            field_name: Name of the field that failed validation
            field_value: Value that failed validation
            validation_rule: Description of the validation rule
            message: Optional custom error message
            context: Additional error context
        """
        if message is None:
            if validation_rule:
                message = f"Validation failed for field '{field_name}': {validation_rule}"
            else:
                message = f"Validation failed for field '{field_name}'"

        super().__init__(
            message=message,
            error_code='VALIDATION_ERROR',
            context={
                "field_name": field_name,
                "field_value": str(field_value)[:100] if field_value is not None else None,
                "validation_rule": validation_rule,
                **(context or {})
            },
            recoverable=True  # Client can fix the input and retry
        )
        self.field_name = field_name
        self.field_value = field_value
        self.validation_rule = validation_rule


class ResourceNotFoundError(KatoBaseException):
    """
    Raised when a requested resource cannot be found.
    """

    def __init__(
        self,
        message: str,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        **kwargs
    ):
        """
        Initialize resource not found error.

        Args:
            message: Error message
            resource_type: Type of resource (pattern, vector, etc.)
            resource_id: ID of the resource
            **kwargs: Additional arguments for base exception
        """
        context = kwargs.pop('context', {})

        if resource_type:
            context['resource_type'] = resource_type
        if resource_id:
            context['resource_id'] = resource_id

        super().__init__(
            message=message,
            error_code='RESOURCE_NOT_FOUND',
            context=context,
            **kwargs
        )


class MemoryError(KatoBaseException):
    """
    Raised when memory operations fail (STM/LTM).
    """

    def __init__(
        self,
        message: str,
        memory_type: Optional[str] = None,
        operation: Optional[str] = None,
        **kwargs
    ):
        """
        Initialize memory error.

        Args:
            message: Error message
            memory_type: Type of memory (STM or LTM)
            operation: Operation that failed
            **kwargs: Additional arguments for base exception
        """
        context = kwargs.pop('context', {})

        if memory_type:
            context['memory_type'] = memory_type
        if operation:
            context['operation'] = operation

        super().__init__(
            message=message,
            error_code='MEMORY_ERROR',
            context=context,
            **kwargs
        )


# Alias for consistency with new module naming
MemoryOperationError = MemoryError


class MetricCalculationError(KatoBaseException):
    """
    Raised when metric calculations fail.
    """

    def __init__(
        self,
        message: str,
        metric_name: Optional[str] = None,
        calculation_context: Optional[dict[str, Any]] = None,
        **kwargs
    ):
        """
        Initialize metric calculation error.

        Args:
            message: Error message
            metric_name: Name of the metric that failed
            calculation_context: Context of the calculation
            **kwargs: Additional arguments for base exception
        """
        context = kwargs.pop('context', {})

        if metric_name:
            context['metric_name'] = metric_name
        if calculation_context:
            context['calculation_context'] = calculation_context

        super().__init__(
            message=message,
            error_code='METRIC_CALCULATION_ERROR',
            context=context,
            **kwargs
        )


class PatternHashingError(KatoBaseException):
    """
    Raised when pattern hashing or identification fails.
    """

    def __init__(
        self,
        message: str,
        pattern_data: Optional[Any] = None,
        hash_value: Optional[str] = None,
        **kwargs
    ):
        """
        Initialize pattern hashing error.

        Args:
            message: Error message
            pattern_data: Pattern data that caused the error
            hash_value: Hash value if available
            **kwargs: Additional arguments for base exception
        """
        context = kwargs.pop('context', {})

        if pattern_data is not None:
            context['pattern_data'] = str(pattern_data)[:500]  # Limit size
        if hash_value:
            context['hash_value'] = hash_value

        super().__init__(
            message=message,
            error_code='PATTERN_HASHING_ERROR',
            context=context,
            **kwargs
        )


class VectorSearchError(KatoBaseException):
    """
    Raised when vector database search operations fail.
    """

    def __init__(
        self,
        message: str,
        search_type: Optional[str] = None,
        vector_dimension: Optional[int] = None,
        collection: Optional[str] = None,
        **kwargs
    ):
        """
        Initialize vector search error.

        Args:
            message: Error message
            search_type: Type of search operation
            vector_dimension: Dimension of vectors involved
            collection: Vector collection name
            **kwargs: Additional arguments for base exception
        """
        context = kwargs.pop('context', {})

        if search_type:
            context['search_type'] = search_type
        if vector_dimension is not None:
            context['vector_dimension'] = vector_dimension
        if collection:
            context['collection'] = collection

        super().__init__(
            message=message,
            error_code='VECTOR_SEARCH_ERROR',
            context=context,
            **kwargs
        )


# ============================================================================
# KATO v2.0 Exception Classes (migrated from kato.errors)
# ============================================================================

# Session Management Errors

class SessionNotFoundError(KatoV2Exception):
    """Raised when a session is not found or has expired"""

    def __init__(
        self,
        session_id: str,
        message: Optional[str] = None,
        context: Optional[dict[str, Any]] = None
    ):
        if message is None:
            message = f"Session '{session_id}' not found or has expired"

        super().__init__(
            message=message,
            error_code="SESSION_NOT_FOUND",
            context={
                "session_id": session_id,
                **(context or {})
            },
            recoverable=True  # Client can create a new session
        )
        self.session_id = session_id


class SessionExpiredError(KatoV2Exception):
    """Raised when a session has explicitly expired"""

    def __init__(
        self,
        session_id: str,
        expired_at: Optional[float] = None,
        message: Optional[str] = None,
        context: Optional[dict[str, Any]] = None
    ):
        if message is None:
            message = f"Session '{session_id}' has expired"

        super().__init__(
            message=message,
            error_code="SESSION_EXPIRED",
            context={
                "session_id": session_id,
                "expired_at": expired_at,
                **(context or {})
            },
            recoverable=True  # Client can extend or recreate session
        )
        self.session_id = session_id
        self.expired_at = expired_at


class SessionLimitExceededError(KatoV2Exception):
    """Raised when session limits are exceeded"""

    def __init__(
        self,
        limit_type: str,
        current_value: int,
        limit_value: int,
        message: Optional[str] = None,
        context: Optional[dict[str, Any]] = None
    ):
        if message is None:
            message = f"{limit_type} limit exceeded: {current_value} > {limit_value}"

        super().__init__(
            message=message,
            error_code="SESSION_LIMIT_EXCEEDED",
            context={
                "limit_type": limit_type,
                "current_value": current_value,
                "limit_value": limit_value,
                **(context or {})
            },
            recoverable=True  # Client can reduce usage or request higher limits
        )
        self.limit_type = limit_type
        self.current_value = current_value
        self.limit_value = limit_value


# Concurrency and Data Consistency Errors

class ConcurrencyError(KatoV2Exception):
    """Raised when concurrent operations conflict"""

    def __init__(
        self,
        resource_id: str,
        operation: str,
        message: Optional[str] = None,
        context: Optional[dict[str, Any]] = None
    ):
        if message is None:
            message = f"Concurrent access conflict for {resource_id} during {operation}"

        super().__init__(
            message=message,
            error_code="CONCURRENCY_ERROR",
            context={
                "resource_id": resource_id,
                "operation": operation,
                **(context or {})
            },
            recoverable=True  # Client can retry with backoff
        )
        self.resource_id = resource_id
        self.operation = operation


class DataConsistencyError(KatoV2Exception):
    """Raised when data consistency checks fail"""

    def __init__(
        self,
        resource_id: str,
        consistency_type: str,
        expected_value: Any = None,
        actual_value: Any = None,
        message: Optional[str] = None,
        context: Optional[dict[str, Any]] = None
    ):
        if message is None:
            message = f"Data consistency violation for {resource_id}: {consistency_type}"

        super().__init__(
            message=message,
            error_code="DATA_CONSISTENCY_ERROR",
            context={
                "resource_id": resource_id,
                "consistency_type": consistency_type,
                "expected_value": expected_value,
                "actual_value": actual_value,
                **(context or {})
            },
            recoverable=False  # Usually indicates serious data corruption
        )
        self.resource_id = resource_id
        self.consistency_type = consistency_type
        self.expected_value = expected_value
        self.actual_value = actual_value


# Circuit Breaker and Resilience Errors

class CircuitBreakerOpenError(KatoV2Exception):
    """Raised when circuit breaker is open"""

    def __init__(
        self,
        service_name: str,
        failure_count: int,
        failure_threshold: int,
        recovery_time: Optional[float] = None,
        message: Optional[str] = None,
        context: Optional[dict[str, Any]] = None
    ):
        if message is None:
            message = f"Circuit breaker open for {service_name} ({failure_count}/{failure_threshold} failures)"

        super().__init__(
            message=message,
            error_code="CIRCUIT_BREAKER_OPEN",
            context={
                "service_name": service_name,
                "failure_count": failure_count,
                "failure_threshold": failure_threshold,
                "recovery_time": recovery_time,
                **(context or {})
            },
            recoverable=True  # Circuit breaker will eventually close
        )
        self.service_name = service_name
        self.failure_count = failure_count
        self.failure_threshold = failure_threshold
        self.recovery_time = recovery_time


class RateLimitExceededError(KatoV2Exception):
    """Raised when rate limits are exceeded"""

    def __init__(
        self,
        resource_type: str,
        current_rate: float,
        rate_limit: float,
        window_seconds: int,
        retry_after: Optional[float] = None,
        message: Optional[str] = None,
        context: Optional[dict[str, Any]] = None
    ):
        if message is None:
            message = f"Rate limit exceeded for {resource_type}: {current_rate}/{rate_limit} per {window_seconds}s"

        super().__init__(
            message=message,
            error_code="RATE_LIMIT_EXCEEDED",
            context={
                "resource_type": resource_type,
                "current_rate": current_rate,
                "rate_limit": rate_limit,
                "window_seconds": window_seconds,
                "retry_after": retry_after,
                **(context or {})
            },
            recoverable=True  # Client can wait and retry
        )
        self.resource_type = resource_type
        self.current_rate = current_rate
        self.rate_limit = rate_limit
        self.window_seconds = window_seconds
        self.retry_after = retry_after


# Resource and Performance Errors

class ResourceExhaustedError(KatoV2Exception):
    """Raised when system resources are exhausted"""

    def __init__(
        self,
        resource_type: str,
        current_usage: float,
        max_capacity: float,
        message: Optional[str] = None,
        context: Optional[dict[str, Any]] = None
    ):
        if message is None:
            message = f"Resource exhausted: {resource_type} ({current_usage}/{max_capacity})"

        super().__init__(
            message=message,
            error_code="RESOURCE_EXHAUSTED",
            context={
                "resource_type": resource_type,
                "current_usage": current_usage,
                "max_capacity": max_capacity,
                "utilization": current_usage / max_capacity if max_capacity > 0 else 1.0,
                **(context or {})
            },
            recoverable=True  # Resources may become available
        )
        self.resource_type = resource_type
        self.current_usage = current_usage
        self.max_capacity = max_capacity


class TimeoutError(KatoV2Exception):
    """Raised when operations timeout"""

    def __init__(
        self,
        operation: str,
        timeout_seconds: float,
        elapsed_seconds: Optional[float] = None,
        message: Optional[str] = None,
        context: Optional[dict[str, Any]] = None
    ):
        if message is None:
            message = f"Operation '{operation}' timed out after {timeout_seconds}s"

        super().__init__(
            message=message,
            error_code="TIMEOUT_ERROR",
            context={
                "operation": operation,
                "timeout_seconds": timeout_seconds,
                "elapsed_seconds": elapsed_seconds,
                **(context or {})
            },
            recoverable=True  # Client can retry with longer timeout
        )
        self.operation = operation
        self.timeout_seconds = timeout_seconds
        self.elapsed_seconds = elapsed_seconds


# Storage Errors (V2 variant, extends existing DatabaseConnectionError)

class StorageError(KatoV2Exception):
    """Raised when storage operations fail"""

    def __init__(
        self,
        storage_type: str,
        operation: str,
        resource_id: Optional[str] = None,
        message: Optional[str] = None,
        context: Optional[dict[str, Any]] = None
    ):
        if message is None:
            message = f"Storage operation failed: {operation} on {storage_type}"

        super().__init__(
            message=message,
            error_code="STORAGE_ERROR",
            context={
                "storage_type": storage_type,
                "operation": operation,
                "resource_id": resource_id,
                **(context or {})
            },
            recoverable=True  # Storage operations can often be retried
        )
        self.storage_type = storage_type
        self.operation = operation
        self.resource_id = resource_id


# Convenience functions for common error patterns

def session_not_found(session_id: str, additional_context: Optional[dict[str, Any]] = None):
    """Create a SessionNotFoundError with standard context"""
    return SessionNotFoundError(
        session_id=session_id,
        context=additional_context
    )


def session_expired(session_id: str, expired_at: Optional[float] = None):
    """Create a SessionExpiredError with standard context"""
    return SessionExpiredError(
        session_id=session_id,
        expired_at=expired_at
    )


def database_unavailable(database_type: str, connection_string: Optional[str] = None):
    """Create a DatabaseConnectionError for unavailable database"""
    return DatabaseConnectionError(
        database_type=database_type,
        connection_string=connection_string,
        message=f"{database_type} database is currently unavailable"
    )


def validation_failed(field_name: str, field_value: Any, rule: str):
    """Create a ValidationError with standard format"""
    return ValidationError(
        field_name=field_name,
        field_value=field_value,
        validation_rule=rule
    )


def resource_exhausted(resource_type: str, current: float, maximum: float):
    """Create a ResourceExhaustedError with utilization info"""
    return ResourceExhaustedError(
        resource_type=resource_type,
        current_usage=current,
        max_capacity=maximum
    )


# Convenience function for getting trace ID from logging context
def get_current_trace_id() -> Optional[str]:
    """
    Get the current trace ID from logging context.

    Returns:
        Current trace ID or None
    """
    try:
        from kato.config.logging_config import get_trace_id
        return get_trace_id()
    except ImportError:
        return None


def raise_with_trace(exception_class: type, *args, **kwargs) -> None:
    """
    Raise an exception with the current trace ID automatically included.

    Args:
        exception_class: The exception class to raise
        *args: Arguments for the exception
        **kwargs: Keyword arguments for the exception
    """
    trace_id = get_current_trace_id()
    if trace_id and 'trace_id' not in kwargs:
        kwargs['trace_id'] = trace_id
    raise exception_class(*args, **kwargs)
