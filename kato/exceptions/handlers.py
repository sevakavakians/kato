"""
KATO v2.0 Error Handlers

Provides structured error handling for FastAPI applications with
consistent response formats and logging.
"""

import logging
import time
from typing import Any, Union

from fastapi import HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

# Import from unified exceptions module
from kato.exceptions import (
    CircuitBreakerOpenError,
    ConcurrencyError,
    ConfigurationError,
    DatabaseConnectionError,
    DataConsistencyError,
    KatoV2Exception,
    RateLimitExceededError,
    ResourceExhaustedError,
    SessionExpiredError,
    SessionLimitExceededError,
    SessionNotFoundError,
    StorageError,
    TimeoutError,
    ValidationError,
)

logger = logging.getLogger('kato.exceptions.handlers')


def create_error_response(
    error_code: str,
    message: str,
    status_code: int,
    details: dict[str, Any] = None,
    context: dict[str, Any] = None
) -> JSONResponse:
    """
    Create standardized error response.

    Args:
        error_code: Machine-readable error code
        message: Human-readable error message
        status_code: HTTP status code
        details: Additional error details
        context: Error context information

    Returns:
        JSONResponse with structured error data
    """
    response_data = {
        "error": {
            "code": error_code,
            "message": message,
            "details": details or {},
            "context": context or {}
        }
    }

    return JSONResponse(
        status_code=status_code,
        content=response_data
    )


async def kato_v2_exception_handler(request: Request, exc: KatoV2Exception) -> JSONResponse:
    """
    Handle all KATO v2.0 custom exceptions.

    Args:
        request: FastAPI request object
        exc: KATO v2.0 exception instance

    Returns:
        Structured JSON error response
    """
    # Log the error with appropriate level
    if exc.recoverable:
        logger.warning(f"Recoverable error in {request.url.path}: {exc.message}",
                      extra={"error_code": exc.error_code, "context": exc.context})
    else:
        logger.error(f"Non-recoverable error in {request.url.path}: {exc.message}",
                    extra={"error_code": exc.error_code, "context": exc.context})

    # Map exception types to HTTP status codes
    status_mapping = {
        SessionNotFoundError: status.HTTP_404_NOT_FOUND,
        SessionExpiredError: status.HTTP_410_GONE,
        SessionLimitExceededError: status.HTTP_429_TOO_MANY_REQUESTS,
        ConcurrencyError: status.HTTP_409_CONFLICT,
        DataConsistencyError: status.HTTP_500_INTERNAL_SERVER_ERROR,
        DatabaseConnectionError: status.HTTP_503_SERVICE_UNAVAILABLE,
        StorageError: status.HTTP_503_SERVICE_UNAVAILABLE,
        CircuitBreakerOpenError: status.HTTP_503_SERVICE_UNAVAILABLE,
        RateLimitExceededError: status.HTTP_429_TOO_MANY_REQUESTS,
        ValidationError: status.HTTP_422_UNPROCESSABLE_ENTITY,
        ConfigurationError: status.HTTP_500_INTERNAL_SERVER_ERROR,
        ResourceExhaustedError: status.HTTP_507_INSUFFICIENT_STORAGE,
        TimeoutError: status.HTTP_504_GATEWAY_TIMEOUT,
    }

    # Get appropriate status code
    http_status = status_mapping.get(type(exc), status.HTTP_500_INTERNAL_SERVER_ERROR)

    # Add recovery suggestions for specific error types
    recovery_suggestions = get_recovery_suggestions(exc)

    response_data = {
        "error": {
            "type": exc.__class__.__name__,
            "code": exc.error_code,
            "message": exc.message,
            "recoverable": exc.recoverable,
            "context": exc.context,
            "timestamp": exc.timestamp
        }
    }

    if recovery_suggestions:
        response_data["error"]["recovery_suggestions"] = recovery_suggestions

    # Add specific headers for certain error types
    headers = {}
    if isinstance(exc, RateLimitExceededError) and exc.retry_after:
        headers["Retry-After"] = str(int(exc.retry_after))
    elif isinstance(exc, CircuitBreakerOpenError) and exc.recovery_time:
        headers["Retry-After"] = str(int(exc.recovery_time))

    return JSONResponse(
        status_code=http_status,
        content=response_data,
        headers=headers
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """
    Handle FastAPI validation errors.

    Args:
        request: FastAPI request object
        exc: Validation error instance

    Returns:
        Structured JSON error response
    """
    logger.warning(f"Validation error in {request.url.path}: {exc.errors()}")

    # Extract detailed validation errors
    validation_details = []
    for error in exc.errors():
        validation_details.append({
            "field": ".".join(str(x) for x in error["loc"]),
            "message": error["msg"],
            "type": error["type"],
            "input": error.get("input")
        })

    return create_error_response(
        error_code="VALIDATION_ERROR",
        message="Request validation failed",
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        details={"validation_errors": validation_details}
    )


async def http_exception_handler(request: Request, exc: Union[HTTPException, StarletteHTTPException]) -> JSONResponse:
    """
    Handle standard HTTP exceptions.

    Args:
        request: FastAPI request object
        exc: HTTP exception instance

    Returns:
        Structured JSON error response
    """
    logger.info(f"HTTP error {exc.status_code} in {request.url.path}: {exc.detail}")

    # Map common HTTP status codes to error codes
    error_code_mapping = {
        400: "BAD_REQUEST",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        405: "METHOD_NOT_ALLOWED",
        409: "CONFLICT",
        429: "TOO_MANY_REQUESTS",
        500: "INTERNAL_SERVER_ERROR",
        502: "BAD_GATEWAY",
        503: "SERVICE_UNAVAILABLE",
        504: "GATEWAY_TIMEOUT"
    }

    error_code = error_code_mapping.get(exc.status_code, "HTTP_ERROR")

    return create_error_response(
        error_code=error_code,
        message=str(exc.detail),
        status_code=exc.status_code
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Handle unexpected exceptions.

    Args:
        request: FastAPI request object
        exc: Exception instance

    Returns:
        Generic error response
    """
    logger.error(f"Unexpected error in {request.url.path}: {str(exc)}", exc_info=True)

    return create_error_response(
        error_code="INTERNAL_ERROR",
        message="An unexpected error occurred",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        context={"exception_type": exc.__class__.__name__}
    )


def get_recovery_suggestions(exc: KatoV2Exception) -> dict[str, Any]:
    """
    Get recovery suggestions for specific error types.

    Args:
        exc: KATO v2.0 exception instance

    Returns:
        Dictionary with recovery suggestions
    """
    if isinstance(exc, SessionNotFoundError):
        return {
            "actions": [
                "Use observe endpoint with unique processor_id for isolation",
                "Check if the processor_id is correct",
                "Ensure consistent processor_id across related operations"
            ],
            "retry_recommended": False
        }

    elif isinstance(exc, SessionExpiredError):
        return {
            "actions": [
                "Use a new processor_id to start fresh",
                "Clear all memory if needed with /clear-all endpoint",
                "Check processor eviction TTL configuration"
            ],
            "retry_recommended": False
        }

    elif isinstance(exc, ConcurrencyError):
        return {
            "actions": [
                "Retry the operation after a short delay",
                "Use exponential backoff for retries",
                "Consider using optimistic locking"
            ],
            "retry_recommended": True,
            "retry_delay_seconds": 1.0
        }

    elif isinstance(exc, DatabaseConnectionError):
        return {
            "actions": [
                "Check database connectivity",
                "Verify database configuration",
                "Wait for database recovery"
            ],
            "retry_recommended": True,
            "retry_delay_seconds": 30.0
        }

    elif isinstance(exc, RateLimitExceededError):
        return {
            "actions": [
                "Reduce request rate",
                "Implement client-side rate limiting",
                "Use batch operations where possible"
            ],
            "retry_recommended": True,
            "retry_delay_seconds": exc.retry_after or 60.0
        }

    elif isinstance(exc, CircuitBreakerOpenError):
        return {
            "actions": [
                "Wait for service recovery",
                "Check service health endpoints",
                "Use fallback mechanisms if available"
            ],
            "retry_recommended": True,
            "retry_delay_seconds": exc.recovery_time or 60.0
        }

    elif isinstance(exc, ValidationError):
        return {
            "actions": [
                f"Fix the '{exc.field_name}' field value",
                f"Ensure value meets requirement: {exc.validation_rule}",
                "Check API documentation for valid formats"
            ],
            "retry_recommended": False
        }

    elif isinstance(exc, ResourceExhaustedError):
        return {
            "actions": [
                "Wait for resources to become available",
                "Reduce resource usage",
                "Contact administrator for capacity increases"
            ],
            "retry_recommended": True,
            "retry_delay_seconds": 30.0
        }

    elif isinstance(exc, TimeoutError):
        return {
            "actions": [
                "Retry with increased timeout",
                "Break operation into smaller chunks",
                "Check network connectivity"
            ],
            "retry_recommended": True,
            "retry_delay_seconds": 5.0
        }

    return {}


def setup_error_handlers(app):
    """
    Setup all error handlers for a FastAPI application.

    Args:
        app: FastAPI application instance
    """
    # KATO v2.0 custom exceptions
    app.add_exception_handler(KatoV2Exception, kato_v2_exception_handler)

    # FastAPI validation errors
    app.add_exception_handler(RequestValidationError, validation_exception_handler)

    # Standard HTTP exceptions
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)

    # Catch-all for unexpected exceptions
    app.add_exception_handler(Exception, generic_exception_handler)

    logger.info("Error handlers configured for KATO v2.0")


# Context managers for error handling

class ErrorContext:
    """Context manager for enriched error handling"""

    def __init__(self, operation: str, resource_id: str = None, **kwargs):
        self.operation = operation
        self.resource_id = resource_id
        self.context = kwargs
        self.start_time = None

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, _exc_tb):
        if exc_type and issubclass(exc_type, KatoV2Exception):
            # Enrich existing KATO exception with context
            exc_val.context.update({
                "operation": self.operation,
                "resource_id": self.resource_id,
                "duration_seconds": time.time() - self.start_time,
                **self.context
            })
        elif exc_type and not issubclass(exc_type, KatoV2Exception):
            # Wrap non-KATO exceptions
            logger.error(f"Non-KATO exception in {self.operation}: {exc_val}", exc_info=True)

        return False  # Don't suppress exceptions
