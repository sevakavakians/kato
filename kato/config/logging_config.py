"""
Structured Logging Configuration for KATO
Provides centralized logging setup with trace IDs, structured output, and performance tracking.
"""

import json
import logging
import sys
import time
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from logging import LogRecord
from typing import Any, Optional, Union

# Context variable for storing trace ID across async boundaries
trace_id_var: ContextVar[Optional[str]] = ContextVar('trace_id', default=None)
request_start_var: ContextVar[Optional[float]] = ContextVar('request_start', default=None)


class StructuredFormatter(logging.Formatter):
    """
    Custom formatter that outputs structured JSON logs with trace IDs and timing.
    """

    def format(self, record: LogRecord) -> str:
        """
        Format log record as structured JSON.

        Args:
            record: The log record to format

        Returns:
            JSON-formatted log string
        """
        # Get trace ID from context
        trace_id = trace_id_var.get()

        # Calculate request duration if available
        duration_ms = None
        request_start = request_start_var.get()
        if request_start:
            duration_ms = round((time.time() - request_start) * 1000, 2)

        # Build structured log entry
        log_entry = {
            'timestamp': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
        }

        # Add optional fields
        if trace_id:
            log_entry['trace_id'] = trace_id

        if duration_ms is not None:
            log_entry['duration_ms'] = duration_ms

        # Add processor_id if available
        if hasattr(record, 'processor_id'):
            log_entry['processor_id'] = record.processor_id

        # Add any extra fields from the record
        if hasattr(record, 'extra_fields'):
            log_entry.update(record.extra_fields)

        # Add exception info if present
        if record.exc_info:
            log_entry['exception'] = self.formatException(record.exc_info)

        return json.dumps(log_entry, default=str)


class HumanReadableFormatter(logging.Formatter):
    """
    Human-readable formatter with color coding and trace IDs.
    """

    # Color codes for different log levels
    COLORS = {
        'DEBUG': '\033[36m',     # Cyan
        'INFO': '\033[32m',      # Green
        'WARNING': '\033[33m',   # Yellow
        'ERROR': '\033[31m',     # Red
        'CRITICAL': '\033[35m',  # Magenta
    }
    RESET = '\033[0m'

    def format(self, record: LogRecord) -> str:
        """
        Format log record for human reading with colors.

        Args:
            record: The log record to format

        Returns:
            Formatted log string with colors
        """
        # Get trace ID from context
        trace_id = trace_id_var.get()
        trace_str = f"[{trace_id[:8]}]" if trace_id else ""

        # Get processor_id if available
        processor_str = ""
        if hasattr(record, 'processor_id'):
            processor_str = f"[{record.processor_id}]"

        # Apply color based on level
        color = self.COLORS.get(record.levelname, '')

        # Format the message
        timestamp = datetime.fromtimestamp(record.created).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]

        formatted = (
            f"{color}{timestamp} "
            f"[{record.levelname:8}] "
            f"{trace_str}{processor_str} "
            f"{record.name} - "
            f"{record.getMessage()}"
            f"{self.RESET}"
        )

        # Add exception info if present
        if record.exc_info:
            formatted += f"\n{self.formatException(record.exc_info)}"

        return formatted


def generate_trace_id() -> str:
    """
    Generate a unique trace ID for request tracking.

    Returns:
        A unique trace ID string
    """
    return f"kato-{uuid.uuid4().hex}"


def set_trace_id(trace_id: Optional[str] = None) -> str:
    """
    Set a trace ID in the context.

    Args:
        trace_id: Optional trace ID to set. If None, generates a new one.

    Returns:
        The trace ID that was set
    """
    if trace_id is None:
        trace_id = generate_trace_id()
    trace_id_var.set(trace_id)
    return trace_id


def get_trace_id() -> Optional[str]:
    """
    Get the current trace ID from context.

    Returns:
        The current trace ID or None
    """
    return trace_id_var.get()


def start_request_timer() -> None:
    """Start timing for the current request."""
    request_start_var.set(time.time())


def get_request_duration() -> Optional[float]:
    """
    Get the duration of the current request in milliseconds.

    Returns:
        Duration in milliseconds or None if timer not started
    """
    request_start = request_start_var.get()
    if request_start:
        return (time.time() - request_start) * 1000
    return None


class ProcessorLoggerAdapter(logging.LoggerAdapter):
    """
    Logger adapter that automatically includes processor_id in all log messages.
    """

    def __init__(self, logger: logging.Logger, processor_id: str):
        """
        Initialize the adapter with a processor ID.

        Args:
            logger: The underlying logger
            processor_id: The processor ID to include in logs
        """
        super().__init__(logger, {'processor_id': processor_id})

    def process(self, msg: str, kwargs: dict[str, Any]) -> tuple:
        """
        Process the logging call to add processor_id.

        Args:
            msg: The log message
            kwargs: Additional keyword arguments

        Returns:
            Processed message and kwargs
        """
        # Add processor_id to the record
        extra = kwargs.get('extra', {})
        extra['processor_id'] = self.extra['processor_id']
        kwargs['extra'] = extra
        return msg, kwargs


def configure_logging(
    level: Union[str, int] = "INFO",
    format_type: str = "human",
    output: str = "stdout",
    processor_id: Optional[str] = None
) -> None:
    """
    Configure the logging system with structured output.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        format_type: Output format ('json' or 'human')
        output: Output destination ('stdout', 'stderr', or file path)
        processor_id: Optional processor ID to include in all logs
    """
    # Convert string level to logging level
    if isinstance(level, str):
        level = getattr(logging, level.upper(), logging.INFO)

    # Choose formatter based on format type
    if format_type == 'json':
        formatter = StructuredFormatter()
    else:
        formatter = HumanReadableFormatter()

    # Configure output handler
    if output == 'stdout':
        handler = logging.StreamHandler(sys.stdout)
    elif output == 'stderr':
        handler = logging.StreamHandler(sys.stderr)
    else:
        # Assume it's a file path
        handler = logging.FileHandler(output)

    handler.setFormatter(formatter)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.handlers = []  # Clear existing handlers
    root_logger.addHandler(handler)

    # Set specific log levels for noisy libraries
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('requests').setLevel(logging.WARNING)
    logging.getLogger('qdrant_client').setLevel(logging.WARNING)

    # Log initial configuration
    logger = logging.getLogger('kato.config.logging')
    logger.info(
        f"Logging configured: level={logging.getLevelName(level)}, "
        f"format={format_type}, output={output}"
    )


def get_logger(name: str, processor_id: Optional[str] = None) -> Union[logging.Logger, ProcessorLoggerAdapter]:
    """
    Get a logger instance with optional processor_id adapter.

    Args:
        name: Logger name (typically __name__)
        processor_id: Optional processor ID to include in logs

    Returns:
        Logger instance or ProcessorLoggerAdapter if processor_id provided
    """
    logger = logging.getLogger(name)

    if processor_id:
        return ProcessorLoggerAdapter(logger, processor_id)

    return logger


# Performance logging utilities
def log_performance(logger: logging.Logger, operation: str, duration_ms: float,
                    metadata: Optional[dict[str, Any]] = None) -> None:
    """
    Log performance metrics for an operation.

    Args:
        logger: Logger to use
        operation: Name of the operation
        duration_ms: Duration in milliseconds
        metadata: Optional additional metadata
    """
    extra_fields = {
        'operation': operation,
        'duration_ms': round(duration_ms, 2),
        'performance_log': True
    }

    if metadata:
        extra_fields.update(metadata)

    # Determine log level based on duration
    if duration_ms > 1000:  # > 1 second
        level = logging.WARNING
        message = f"Slow operation '{operation}' took {duration_ms:.2f}ms"
    elif duration_ms > 100:  # > 100ms
        level = logging.INFO
        message = f"Operation '{operation}' took {duration_ms:.2f}ms"
    else:
        level = logging.DEBUG
        message = f"Operation '{operation}' completed in {duration_ms:.2f}ms"

    logger.log(level, message, extra={'extra_fields': extra_fields})


class PerformanceTimer:
    """
    Context manager for timing operations.

    Usage:
        with PerformanceTimer(logger, 'database_query'):
            # perform operation
            pass
    """

    def __init__(self, logger: logging.Logger, operation: str,
                 metadata: Optional[dict[str, Any]] = None):
        """
        Initialize the performance timer.

        Args:
            logger: Logger to use
            operation: Name of the operation
            metadata: Optional additional metadata
        """
        self.logger = logger
        self.operation = operation
        self.metadata = metadata or {}
        self.start_time = None

    def __enter__(self):
        """Start the timer."""
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, _exc_tb):
        """Stop the timer and log performance."""
        if self.start_time:
            duration_ms = (time.time() - self.start_time) * 1000
            log_performance(self.logger, self.operation, duration_ms, self.metadata)
