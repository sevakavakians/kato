# KATO Logging Guide

**Version:** 1.0
**Last Updated:** October 2025
**Target Audience:** Developers, System Administrators

## Overview

KATO uses Python's standard `logging` module with structured logging support for comprehensive observability. This guide covers logging usage, best practices, and configuration for developers working with KATO.

---

## Table of Contents

- [Quick Start](#quick-start)
- [Log Levels](#log-levels)
- [Creating Loggers](#creating-loggers)
- [Request Tracing](#request-tracing)
- [Configuration](#configuration)
- [Best Practices](#best-practices)
- [Dashboard Integration](#dashboard-integration)
- [Troubleshooting](#troubleshooting)

---

## Quick Start

### Basic Logging

```python
import logging

# Create a logger for your module
logger = logging.getLogger('kato.your_module')

# Log at different levels
logger.debug("Detailed debugging information")
logger.info("General informational message")
logger.warning("Warning about potential issues")
logger.error("Error occurred but operation continues")
logger.critical("Critical error, operation cannot continue")
```

### With Processor Context

```python
from kato.config.logging_config import get_logger

# Create logger with processor_id automatically included
logger = get_logger('kato.your_module', processor_id='proc_123')

logger.info("This log will include processor_id automatically")
```

### Request Tracing

```python
from kato.config.logging_config import trace_context, generate_trace_id

# Automatically track related logs across async operations
with trace_context(generate_trace_id()):
    logger.info("This operation")
    await some_async_function()
    logger.info("Will have the same trace_id")
```

---

## Log Levels

KATO follows standard Python logging levels with specific usage guidelines:

### DEBUG (10)
**When to use:**
- Development-only detailed diagnostics
- Variable state dumps
- Entry/exit of complex functions

**Guidelines:**
- ❌ Avoid in high-frequency code paths (every observation/prediction)
- ❌ Never log sensitive data (passwords, tokens, keys)
- ✅ Use for troubleshooting specific issues
- ✅ Include enough context to understand the issue

**Example:**
```python
# Good - useful diagnostic
logger.debug(f"Pattern matching with {len(candidates)} candidates, threshold={threshold}")

# Bad - too frequent, no value
logger.debug(f"Time incremented to {self.time}")
```

### INFO (20)
**When to use:**
- Significant state changes
- Service lifecycle events (startup, shutdown)
- Important business operations (pattern learned, session created)
- Configuration changes

**Guidelines:**
- ✅ Log major operations and milestones
- ✅ Include key identifiers (session_id, pattern_name)
- ❌ Avoid in tight loops or per-request operations

**Example:**
```python
# Good - significant event
logger.info(f"Session {session_id} created for node {node_id} with {ttl}s TTL")

# Good - lifecycle event
logger.info(f"KATO FastAPI service started successfully")
```

### WARNING (30)
**When to use:**
- Recoverable errors
- Deprecated feature usage
- Unexpected but handled conditions
- Performance degradation

**Guidelines:**
- ✅ Include what went wrong and how it was handled
- ✅ Log fallback actions taken
- ✅ Include enough context to investigate

**Example:**
```python
# Good - handled error with context
logger.warning(f"Failed to initialize metrics cache for processor {processor_id}: {e}")

# Good - performance issue
logger.warning(f"High concurrent requests: {count}/{limit} ({percent}% of limit)")
```

### ERROR (40)
**When to use:**
- Operation failures that affect functionality
- Database connection failures
- API errors that return 500-series responses
- Unexpected exceptions in critical paths

**Guidelines:**
- ✅ Always include exception details with traceback
- ✅ Include operation context (what was being attempted)
- ✅ Include resource identifiers (session_id, pattern_name, etc.)
- ✅ Use with exception handling

**Example:**
```python
# Good - comprehensive error logging
try:
    pattern = await processor.learn()
except Exception as e:
    logger.error(f"Failed to learn pattern from STM: {e}", exc_info=True)
    raise
```

### CRITICAL (50)
**When to use:**
- Service-level failures
- Data corruption
- Security breaches
- Unrecoverable errors requiring immediate attention

**Guidelines:**
- ✅ Reserve for true critical failures
- ✅ Include full context and traceback
- ✅ Consider alerting mechanisms

**Example:**
```python
# Good - critical service failure
logger.critical(f"Database connection lost and cannot reconnect: {e}", exc_info=True)
```

---

## Creating Loggers

### Standard Logger

```python
import logging

# Best practice - use module name
logger = logging.getLogger(__name__)
```

### Logger with Processor Context

For code that operates within a processor context:

```python
from kato.config.logging_config import get_logger

# Automatically includes processor_id in all logs
logger = get_logger('kato.workers.pattern_processor', processor_id='proc_abc123')

logger.info("Pattern learned")
# Output: ... [proc_abc123] kato.workers.pattern_processor - Pattern learned
```

### Logger Naming Convention

Follow this hierarchy:

```
kato
├── config
│   └── kato.config.settings
├── workers
│   ├── kato.workers.kato_processor
│   └── kato.workers.pattern_processor
├── api
│   └── kato.api.endpoints.sessions
└── storage
    └── kato.storage.redis_session_manager
```

**Rules:**
- Always start with `kato.`
- Use Python module path structure
- Use hyphens for multi-word module names: `kato.workers.kato-processor`

---

## Request Tracing

KATO supports distributed tracing with trace IDs for correlating logs across async operations and multiple services.

### Automatic Tracing (FastAPI)

The FastAPI service automatically adds trace IDs to all requests:

```python
# Middleware handles this automatically
@app.middleware("http")
async def trace_middleware(request: Request, call_next):
    trace_id = request.headers.get('X-Trace-ID', generate_trace_id())

    with trace_context(trace_id):
        response = await call_next(request)
        response.headers['X-Trace-ID'] = trace_id
        return response
```

### Manual Tracing

For background tasks or non-HTTP operations:

```python
from kato.config.logging_config import trace_context, generate_trace_id

async def background_task():
    # Create new trace context for this operation
    with trace_context(generate_trace_id()):
        logger.info("Starting background task")
        await process_data()
        logger.info("Background task complete")
```

### Retrieving Current Trace ID

```python
from kato.config.logging_config import get_trace_id

current_trace = get_trace_id()
if current_trace:
    logger.info(f"Operating within trace: {current_trace}")
```

---

## Configuration

### Environment Variables

Configure logging behavior via environment variables:

```bash
# Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
export LOG_LEVEL=INFO

# Log format (json, human)
export LOG_FORMAT=human

# Log output (stdout, stderr, or file path)
export LOG_OUTPUT=stdout
```

### Programmatic Configuration

```python
from kato.config.logging_config import configure_logging

# Configure with JSON output for production
configure_logging(
    level="INFO",
    format_type="json",  # or "human" for development
    output="stdout"
)
```

### JSON Format (Production)

Outputs structured logs for parsing by log aggregation systems:

```json
{
  "timestamp": "2025-10-11T14:23:45.123Z",
  "level": "INFO",
  "logger": "kato.api.sessions",
  "message": "Session created successfully",
  "module": "sessions",
  "function": "create_session",
  "line": 257,
  "trace_id": "kato-a1b2c3d4",
  "processor_id": "proc_123"
}
```

### Human Format (Development)

Outputs colored, readable logs for local development:

```
2025-10-11 14:23:45.123 [INFO    ] [a1b2c3d4][proc_123] kato.api.sessions - Session created successfully
```

---

## Best Practices

### DO ✅

1. **Use appropriate log levels**
   ```python
   logger.info("Pattern learned")  # Significant event
   logger.warning("Cache miss, falling back to DB")  # Expected but noteworthy
   logger.error("Database query failed", exc_info=True)  # Error with traceback
   ```

2. **Include context in log messages**
   ```python
   # Good - includes identifiers and counts
   logger.info(f"Learned pattern {pattern_name} from {len(stm)} events")

   # Bad - lacks context
   logger.info("Pattern learned")
   ```

3. **Use structured logging with extra fields**
   ```python
   logger.info(
       "Session created",
       extra={
           'session_id': session_id,
           'node_id': node_id,
           'ttl_seconds': ttl
       }
   )
   ```

4. **Log exceptions with traceback**
   ```python
   try:
       result = process_data()
   except Exception as e:
       logger.error(f"Processing failed: {e}", exc_info=True)
       raise
   ```

5. **Use lazy formatting**
   ```python
   # Good - only formats if DEBUG is enabled
   logger.debug("Processing %d items with threshold %f", len(items), threshold)

   # Bad - always formats even if DEBUG is disabled
   logger.debug(f"Processing {len(items)} items with threshold {threshold}")
   ```

### DON'T ❌

1. **Don't log in tight loops**
   ```python
   # Bad - logs on every iteration
   for item in items:
       logger.debug(f"Processing item {item}")
       process(item)

   # Good - log once before/after
   logger.debug(f"Processing {len(items)} items")
   for item in items:
       process(item)
   logger.debug(f"Processed {len(items)} items successfully")
   ```

2. **Don't log sensitive information**
   ```python
   # Bad - logs sensitive data
   logger.debug(f"User password: {password}")
   logger.info(f"API token: {token}")

   # Good - log safely
   logger.debug(f"User authenticated: {username}")
   logger.info(f"API request authorized")
   ```

3. **Don't use print() statements**
   ```python
   # Bad - bypasses log system
   print(f"Debug: {value}")

   # Good - use logger
   logger.debug(f"Debug: {value}")
   ```

4. **Don't log useless information**
   ```python
   # Bad - no value
   logger.info("logging initiated")
   logger.debug("Function called")

   # Good - meaningful
   logger.info(f"Service initialized with {processor_count} processors")
   ```

5. **Don't duplicate exception info**
   ```python
   # Bad - exception already has traceback
   try:
       result = operation()
   except Exception as e:
       logger.error(f"Operation failed: {e}")
       logger.error(f"Traceback: {traceback.format_exc()}")

   # Good - exc_info=True includes traceback once
   try:
       result = operation()
   except Exception as e:
       logger.error(f"Operation failed: {e}", exc_info=True)
   ```

---

## Dashboard Integration

KATO logs are designed for integration with external monitoring dashboards.

### Log Fields for Parsing

When using JSON format, these fields are available for dashboard queries:

| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | ISO 8601 | UTC timestamp |
| `level` | string | Log level (DEBUG, INFO, etc.) |
| `logger` | string | Logger name |
| `message` | string | Log message |
| `trace_id` | string | Request trace ID (if available) |
| `processor_id` | string | Processor identifier (if available) |
| `module` | string | Python module name |
| `function` | string | Function name |
| `line` | integer | Line number |

### Common Dashboard Queries

**Error Rate:**
```
level:"ERROR" OR level:"CRITICAL"
```

**Specific Processor:**
```
processor_id:"proc_abc123"
```

**Trace Request:**
```
trace_id:"kato-a1b2c3d4"
```

**Performance Issues:**
```
message:"High concurrent requests" OR message:"Slow operation"
```

### Metrics Extraction

KATO logs performance metrics in structured format:

```python
logger.info(
    "Request completed",
    extra={
        'operation': 'observe',
        'duration_ms': 45.2,
        'stm_length': 5
    }
)
```

Dashboard can extract:
- Average request duration
- STM size distribution
- Operation frequency

---

## Troubleshooting

### Logs Not Appearing

**Check log level:**
```python
import logging
logger = logging.getLogger('kato.your_module')
print(f"Current level: {logging.getLevelName(logger.level)}")
```

**Verify LOG_LEVEL environment variable:**
```bash
echo $LOG_LEVEL
```

**Check for handler configuration:**
```python
logger = logging.getLogger('kato')
print(f"Handlers: {logger.handlers}")
```

### Too Many DEBUG Logs

Adjust log level per module:

```python
# Reduce noise from specific module
logging.getLogger('kato.storage.qdrant_store').setLevel(logging.WARNING)
```

Or environment variable:
```bash
export LOG_LEVEL=INFO  # Hide DEBUG logs
```

### Missing Trace IDs

Ensure you're within a trace context:

```python
from kato.config.logging_config import trace_context, generate_trace_id

# Create trace context
with trace_context(generate_trace_id()):
    logger.info("This will have trace_id")
```

### Performance Impact

If logging impacts performance:

1. **Use lazy formatting:**
   ```python
   # Good - only evaluates if level is enabled
   logger.debug("Data: %s", expensive_function())
   ```

2. **Reduce log level:**
   ```bash
   export LOG_LEVEL=WARNING  # Only warnings and above
   ```

3. **Remove DEBUG logs from hot paths** (see Best Practices)

---

## Additional Resources

- **Technical Specification:** `docs/technical/LOGGING_SPECIFICATION.md`
- **Configuration Reference:** `docs/CONFIGURATION.md`
- **Troubleshooting Guide:** `docs/technical/TROUBLESHOOTING.md`
- **Python Logging Docs:** https://docs.python.org/3/library/logging.html

---

## Summary

KATO's logging system provides:
- ✅ Structured logging with JSON support
- ✅ Request tracing across async operations
- ✅ Processor-aware logging with automatic context
- ✅ Dashboard integration with parseable fields
- ✅ Performance-conscious design

Follow the guidelines in this document to maintain clean, useful, and performant logging throughout KATO.
