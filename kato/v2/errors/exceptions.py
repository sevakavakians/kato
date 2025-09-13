"""
KATO v2.0 Structured Error Classes

Provides comprehensive error handling for v2.0 features with detailed
context and recovery suggestions.
"""

from typing import Optional, Dict, Any
import time


class KatoV2Exception(Exception):
    """Base exception for all KATO v2.0 errors"""
    
    def __init__(
        self, 
        message: str, 
        error_code: str = "KATO_V2_ERROR",
        context: Optional[Dict[str, Any]] = None,
        recoverable: bool = True
    ):
        """
        Initialize KATO v2.0 exception.
        
        Args:
            message: Human-readable error message
            error_code: Machine-readable error code
            context: Additional error context
            recoverable: Whether this error can be recovered from
        """
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.context = context or {}
        self.recoverable = recoverable
        self.timestamp = time.time()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for API responses"""
        return {
            "error": {
                "type": self.__class__.__name__,
                "message": self.message,
                "code": self.error_code,
                "context": self.context,
                "recoverable": self.recoverable,
                "timestamp": self.timestamp
            }
        }


# Session Management Errors

class SessionNotFoundError(KatoV2Exception):
    """Raised when a session is not found or has expired"""
    
    def __init__(
        self, 
        session_id: str, 
        message: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
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
        context: Optional[Dict[str, Any]] = None
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
        context: Optional[Dict[str, Any]] = None
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
        context: Optional[Dict[str, Any]] = None
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
        context: Optional[Dict[str, Any]] = None
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


# Database and Storage Errors

class DatabaseConnectionError(KatoV2Exception):
    """Raised when database connections fail"""
    
    def __init__(
        self, 
        database_type: str,
        connection_string: Optional[str] = None,
        message: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        if message is None:
            message = f"Failed to connect to {database_type} database"
        
        super().__init__(
            message=message,
            error_code="DATABASE_CONNECTION_ERROR",
            context={
                "database_type": database_type,
                "connection_string": connection_string,
                **(context or {})
            },
            recoverable=True  # Connection might recover
        )
        self.database_type = database_type
        self.connection_string = connection_string


class StorageError(KatoV2Exception):
    """Raised when storage operations fail"""
    
    def __init__(
        self, 
        storage_type: str,
        operation: str,
        resource_id: Optional[str] = None,
        message: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
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
        context: Optional[Dict[str, Any]] = None
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
        context: Optional[Dict[str, Any]] = None
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


# Validation and Input Errors

class ValidationError(KatoV2Exception):
    """Raised when input validation fails"""
    
    def __init__(
        self, 
        field_name: str,
        field_value: Any,
        validation_rule: str,
        message: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        if message is None:
            message = f"Validation failed for field '{field_name}': {validation_rule}"
        
        super().__init__(
            message=message,
            error_code="VALIDATION_ERROR",
            context={
                "field_name": field_name,
                "field_value": field_value,
                "validation_rule": validation_rule,
                **(context or {})
            },
            recoverable=True  # Client can fix input and retry
        )
        self.field_name = field_name
        self.field_value = field_value
        self.validation_rule = validation_rule


class ConfigurationError(KatoV2Exception):
    """Raised when configuration is invalid"""
    
    def __init__(
        self, 
        config_key: str,
        config_value: Any,
        expected_type: Optional[str] = None,
        message: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        if message is None:
            message = f"Invalid configuration for '{config_key}': {config_value}"
        
        super().__init__(
            message=message,
            error_code="CONFIGURATION_ERROR",
            context={
                "config_key": config_key,
                "config_value": config_value,
                "expected_type": expected_type,
                **(context or {})
            },
            recoverable=False  # Usually requires admin intervention
        )
        self.config_key = config_key
        self.config_value = config_value
        self.expected_type = expected_type


# Resource and Performance Errors

class ResourceExhaustedError(KatoV2Exception):
    """Raised when system resources are exhausted"""
    
    def __init__(
        self, 
        resource_type: str,
        current_usage: float,
        max_capacity: float,
        message: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
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
        context: Optional[Dict[str, Any]] = None
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


# Convenience functions for common error patterns

def session_not_found(session_id: str, additional_context: Optional[Dict[str, Any]] = None):
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