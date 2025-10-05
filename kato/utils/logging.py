"""
Centralized logging utilities for KATO

Provides standardized logging patterns and reduces boilerplate code
throughout the application. Includes trace ID support for request tracking.
"""

import logging
import time
import traceback
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from typing import Optional

# Context variable for trace ID
_trace_id: ContextVar[Optional[str]] = ContextVar('trace_id', default=None)


def get_trace_id() -> Optional[str]:
    """Get the current trace ID from context."""
    return _trace_id.get()


def set_trace_id(trace_id: str) -> None:
    """Set the trace ID in current context."""
    _trace_id.set(trace_id)


def generate_trace_id() -> str:
    """Generate a new trace ID."""
    return str(uuid.uuid4())[:8]


@contextmanager
def trace_context(trace_id: Optional[str] = None):
    """Context manager for trace ID."""
    if trace_id is None:
        trace_id = generate_trace_id()

    token = _trace_id.set(trace_id)
    try:
        yield trace_id
    finally:
        _trace_id.reset(token)


class KatoLogger:
    """Enhanced logger with structured logging support."""

    def __init__(self, name: str, level: Optional[str] = None):
        """
        Initialize logger with consistent formatting.
        
        Args:
            name: Logger name (usually module name)
            level: Optional log level override
        """
        self.logger = logging.getLogger(name)

        if level:
            self.logger.setLevel(getattr(logging, level.upper()))

        # Ensure we have a handler if none exists
        if not self.logger.handlers and self.logger.parent is logging.root:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

    def debug(self, msg: str, **kwargs):
        """Debug log with optional structured data."""
        self._log(logging.DEBUG, msg, **kwargs)

    def info(self, msg: str, **kwargs):
        """Info log with optional structured data."""
        self._log(logging.INFO, msg, **kwargs)

    def warning(self, msg: str, **kwargs):
        """Warning log with optional structured data."""
        self._log(logging.WARNING, msg, **kwargs)

    def error(self, msg: str, error: Optional[Exception] = None, **kwargs):
        """Error log with optional exception details."""
        if error:
            kwargs['error_type'] = type(error).__name__
            kwargs['error_message'] = str(error)
            if self.logger.isEnabledFor(logging.DEBUG):
                kwargs['traceback'] = traceback.format_exc()
        self._log(logging.ERROR, msg, **kwargs)

    def critical(self, msg: str, **kwargs):
        """Critical log with optional structured data."""
        self._log(logging.CRITICAL, msg, **kwargs)

    def _log(self, level: int, msg: str, **kwargs):
        """Internal logging method with structured data support."""
        # Add trace ID if available
        trace_id = get_trace_id()
        if trace_id:
            kwargs['trace_id'] = trace_id

        if kwargs:
            # Format structured data as key=value pairs
            structured = ' '.join(f'{k}={v}' for k, v in kwargs.items())
            full_msg = f'{msg} | {structured}'
        else:
            full_msg = msg

        self.logger.log(level, full_msg)


def get_logger(name: str, level: Optional[str] = None) -> KatoLogger:
    """
    Get a standardized logger instance.
    
    Args:
        name: Logger name (usually __name__)
        level: Optional log level override
        
    Returns:
        KatoLogger instance
    """
    return KatoLogger(name, level)


def log_execution_time(logger: Optional[KatoLogger] = None):
    """
    Decorator to log execution time of functions.
    
    Args:
        logger: Optional logger instance
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            _logger = logger or get_logger(func.__module__)
            start_time = time.time()

            try:
                result = func(*args, **kwargs)
                execution_time = time.time() - start_time
                _logger.debug(
                    f"{func.__name__} completed",
                    execution_time_ms=round(execution_time * 1000, 2)
                )
                return result
            except Exception as e:
                execution_time = time.time() - start_time
                _logger.error(
                    f"{func.__name__} failed",
                    error=e,
                    execution_time_ms=round(execution_time * 1000, 2)
                )
                raise

        return wrapper
    return decorator


def log_method_calls(logger: Optional[KatoLogger] = None):
    """
    Decorator to log method entry/exit with arguments.
    
    Args:
        logger: Optional logger instance
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            _logger = logger or get_logger(func.__module__)

            # Don't log sensitive parameters
            safe_kwargs = {k: v for k, v in kwargs.items()
                          if k not in ['password', 'token', 'secret', 'key']}

            _logger.debug(
                f"Entering {func.__name__}",
                args_count=len(args),
                kwargs=safe_kwargs
            )

            try:
                result = func(*args, **kwargs)
                _logger.debug(f"Exiting {func.__name__}", success=True)
                return result
            except Exception as e:
                _logger.error(f"Error in {func.__name__}", error=e)
                raise

        return wrapper
    return decorator


# Convenience functions for backward compatibility
def get_standard_logger(module_name: str) -> logging.Logger:
    """
    Get a standard Python logger with consistent formatting.
    
    Args:
        module_name: Usually __name__
        
    Returns:
        Standard logging.Logger instance
    """
    logger = logging.getLogger(module_name)

    # Add handler if none exists
    if not logger.handlers and logger.parent is logging.root:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger
