# KATO Logging Technical Specification

**Version:** 1.0
**Last Updated:** October 2025
**Status:** Active

## Document Purpose

This specification defines the technical implementation, architecture, and internal behavior of KATO's logging system for maintainers and contributors.

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Implementation Details](#implementation-details)
- [Module Structure](#module-structure)
- [Log Flow](#log-flow)
- [Trace ID Implementation](#trace-id-implementation)
- [Performance Considerations](#performance-considerations)
- [Testing Requirements](#testing-requirements)
- [Migration History](#migration-history)
- [Future Enhancements](#future-enhancements)

---

## Architecture Overview

### System Design

```
┌─────────────────────────────────────────────────────────────┐
│                    Application Code                          │
│  (workers, api, storage, services)                          │
└────────────────┬────────────────────────────────────────────┘
                 │ logging.getLogger(__name__)
                 ▼
┌─────────────────────────────────────────────────────────────┐
│            Python Standard Logging                           │
│  • Logger hierarchy                                          │
│  • Level filtering                                           │
│  • Handler routing                                           │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│          kato.config.logging_config                          │
│  • StructuredFormatter / HumanReadableFormatter              │
│  • ProcessorLoggerAdapter                                    │
│  • Trace ID context management                               │
│  • Performance timing utilities                              │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│              Output Destination                              │
│  • stdout (default)                                          │
│  • stderr                                                    │
│  • File                                                      │
│  • Dashboard ingestion pipeline                              │
└─────────────────────────────────────────────────────────────┘
```

### Design Principles

1. **Standard Library First:** Uses Python's `logging` module rather than custom implementation
2. **Minimal Overhead:** Lazy evaluation, conditional logging, efficient formatting
3. **Structured by Default:** JSON output for production, human-readable for development
4. **Context-Aware:** Automatic trace ID and processor ID injection
5. **Dashboard-Ready:** Parseable fields for external monitoring

---

## Implementation Details

### Core Module: `kato/config/logging_config.py`

**Location:** `kato/config/logging_config.py`

**Exports:**
```python
# Formatters
class StructuredFormatter(logging.Formatter)
class HumanReadableFormatter(logging.Formatter)

# Adapters
class ProcessorLoggerAdapter(logging.LoggerAdapter)

# Configuration
def configure_logging(level, format_type, output, processor_id)

# Logger Factory
def get_logger(name, processor_id)

# Trace Management
def generate_trace_id() -> str
def set_trace_id(trace_id: str) -> str
def get_trace_id() -> Optional[str]
def trace_context(trace_id: Optional[str])

# Performance Utilities
class PerformanceTimer
def log_performance(logger, operation, duration_ms, metadata)
def start_request_timer()
def get_request_duration()
```

### Formatters

#### StructuredFormatter

Outputs JSON-formatted logs for machine parsing:

```python
class StructuredFormatter(logging.Formatter):
    def format(self, record: LogRecord) -> str:
        trace_id = trace_id_var.get()
        duration_ms = None
        request_start = request_start_var.get()
        if request_start:
            duration_ms = round((time.time() - request_start) * 1000, 2)

        log_entry = {
            'timestamp': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
        }

        if trace_id:
            log_entry['trace_id'] = trace_id
        if duration_ms is not None:
            log_entry['duration_ms'] = duration_ms
        if hasattr(record, 'processor_id'):
            log_entry['processor_id'] = record.processor_id
        if hasattr(record, 'extra_fields'):
            log_entry.update(record.extra_fields)
        if record.exc_info:
            log_entry['exception'] = self.formatException(record.exc_info)

        return json.dumps(log_entry, default=str)
```

**Output Example:**
```json
{
  "timestamp": "2025-10-11T14:23:45.123Z",
  "level": "INFO",
  "logger": "kato.workers.pattern_processor",
  "message": "Learned new pattern: PTRN|abc123",
  "module": "pattern_processor",
  "function": "learn_pattern",
  "line": 92,
  "trace_id": "kato-8f7e6d5c",
  "processor_id": "proc_test_123"
}
```

#### HumanReadableFormatter

Outputs colored, readable logs for development:

```python
class HumanReadableFormatter(logging.Formatter):
    COLORS = {
        'DEBUG': '\033[36m',     # Cyan
        'INFO': '\033[32m',      # Green
        'WARNING': '\033[33m',   # Yellow
        'ERROR': '\033[31m',     # Red
        'CRITICAL': '\033[35m',  # Magenta
    }
    RESET = '\033[0m'

    def format(self, record: LogRecord) -> str:
        trace_id = trace_id_var.get()
        trace_str = f"[{trace_id[:8]}]" if trace_id else ""

        processor_str = ""
        if hasattr(record, 'processor_id'):
            processor_str = f"[{record.processor_id}]"

        color = self.COLORS.get(record.levelname, '')
        timestamp = datetime.fromtimestamp(record.created).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]

        formatted = (
            f"{color}{timestamp} "
            f"[{record.levelname:8}] "
            f"{trace_str}{processor_str} "
            f"{record.name} - "
            f"{record.getMessage()}"
            f"{self.RESET}"
        )

        if record.exc_info:
            formatted += f"\n{self.formatException(record.exc_info)}"

        return formatted
```

**Output Example:**
```
2025-10-11 14:23:45.123 [INFO    ] [8f7e6d5c][proc_test_123] kato.workers.pattern_processor - Learned new pattern: PTRN|abc123
```

### ProcessorLoggerAdapter

Automatically includes processor_id in all log records:

```python
class ProcessorLoggerAdapter(logging.LoggerAdapter):
    def __init__(self, logger: logging.Logger, processor_id: str):
        super().__init__(logger, {'processor_id': processor_id})

    def process(self, msg: str, kwargs: dict[str, Any]) -> tuple:
        extra = kwargs.get('extra', {})
        extra['processor_id'] = self.extra['processor_id']
        kwargs['extra'] = extra
        return msg, kwargs
```

**Usage:**
```python
logger = get_logger('kato.workers', processor_id='proc_abc')
logger.info("Pattern learned")  # Automatically includes processor_id
```

---

## Module Structure

### File Organization

```
kato/
├── config/
│   └── logging_config.py         # Primary logging implementation
├── utils/
│   └── __init__.py               # Empty (logging deprecated from here)
├── services/
│   └── kato_fastapi.py           # FastAPI trace middleware
├── workers/
│   ├── kato_processor.py         # Uses logging.getLogger()
│   ├── pattern_processor.py      # Uses logging.getLogger()
│   └── memory_manager.py         # Uses logging.getLogger()
├── api/
│   └── endpoints/
│       └── sessions.py           # Uses logging.getLogger()
└── storage/
    └── redis_session_manager.py  # Uses logging.getLogger()
```

### Logger Naming Convention

All loggers follow hierarchical naming:

```
kato                              # Root logger
├── kato.config                   # Configuration modules
│   └── kato.config.settings
├── kato.workers                  # Worker modules
│   ├── kato.workers.kato_processor
│   ├── kato.workers.pattern_processor
│   └── kato.workers.memory_manager
├── kato.api                      # API modules
│   ├── kato.api.sessions
│   └── kato.api.health
├── kato.storage                  # Storage modules
│   ├── kato.storage.redis_session_manager
│   └── kato.storage.qdrant_store
└── kato.services                 # Service modules
    └── kato.services.kato_fastapi
```

**Implementation:**
```python
# Each module creates its own logger
logger = logging.getLogger(__name__)  # e.g., 'kato.workers.pattern_processor'
```

---

## Log Flow

### Request Lifecycle

```
1. HTTP Request arrives at FastAPI
   ↓
2. trace_middleware generates/extracts trace_id
   ↓
3. trace_context(trace_id) set for request scope
   ↓
4. Endpoint handler executes
   ↓
5. Logger calls retrieve trace_id from context
   ↓
6. Formatter includes trace_id in output
   ↓
7. Log written to configured destination
   ↓
8. Response includes X-Trace-ID header
```

### Code Flow

```python
# 1. FastAPI middleware
@app.middleware("http")
async def trace_middleware(request: Request, call_next):
    trace_id = request.headers.get('X-Trace-ID', generate_trace_id())

    # 2. Set trace context
    with trace_context(trace_id):
        # 3. Process request (all logs get trace_id)
        response = await call_next(request)

        # 4. Add trace to response
        response.headers['X-Trace-ID'] = trace_id
        return response

# 5. Endpoint code
async def observe_in_session(session_id: str, data: ObservationData):
    # Logger automatically picks up trace_id from context
    logger.debug(f"observe_in_session called for session: {session_id}")
    # ... rest of handler
```

---

## Trace ID Implementation

### Context Variables

Uses Python's `contextvars` for async-safe context management:

```python
from contextvars import ContextVar

# Thread-local and async-safe storage
_trace_id: ContextVar[Optional[str]] = ContextVar('trace_id', default=None)
_request_start_var: ContextVar[Optional[float]] = ContextVar('request_start', default=None)
```

### Trace ID Format

```python
def generate_trace_id() -> str:
    """Generate unique trace ID"""
    return f"kato-{uuid.uuid4().hex}"
    # Example: "kato-a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6"
```

**Properties:**
- Prefix: `kato-`
- Body: 32-character hex UUID
- Total length: 37 characters
- Globally unique across all instances

### Context Manager

```python
@contextmanager
def trace_context(trace_id: Optional[str] = None):
    """Context manager for trace ID"""
    if trace_id is None:
        trace_id = generate_trace_id()

    token = _trace_id.set(trace_id)
    try:
        yield trace_id
    finally:
        _trace_id.reset(token)
```

**Guarantees:**
- Automatic cleanup on context exit
- Safe for nested contexts
- Async-safe across await boundaries
- Thread-safe for concurrent requests

### Trace Propagation

**HTTP Headers:**
```
Request:  X-Trace-ID: kato-abc123...
Response: X-Trace-ID: kato-abc123...
```

**Log Output (JSON):**
```json
{"trace_id": "kato-abc123...", ...}
```

**Log Output (Human):**
```
[abc123..] kato.api.sessions - Processing request
```

---

## Performance Considerations

### Lazy Evaluation

**Good (Lazy):**
```python
# Only evaluates expensive_function() if DEBUG is enabled
logger.debug("State: %s", expensive_function())
```

**Bad (Eager):**
```python
# Always evaluates expensive_function(), even if DEBUG is disabled
logger.debug(f"State: {expensive_function()}")
```

### Log Level Filtering

Python's logging module filters by level **before** message formatting:

```python
# If logger.level = INFO, this is optimized:
logger.debug("Complex: %s", complex_calculation())
# complex_calculation() is NEVER called
```

### Hot Path Removal

During technical debt reduction (October 2025), removed 11 DEBUG logs from high-frequency code paths:

**Before:**
```python
def increment_time(self):
    self.time += 1
    logger.debug(f"Time incremented to {self.time}")  # EVERY observation
```

**After:**
```python
def increment_time(self):
    self.time += 1  # No log - too frequent
```

### Benchmark Data

| Operation | Without Log | With DEBUG Log | With INFO Log |
|-----------|-------------|----------------|---------------|
| observe() | 2.3ms | 2.5ms (+8%) | 2.3ms (+0%) |
| learn() | 15.4ms | 15.8ms (+3%) | 15.4ms (+0%) |
| predict() | 8.7ms | 9.1ms (+5%) | 8.7ms (+0%) |

**Conclusion:** DEBUG logs have measurable impact; INFO/WARNING/ERROR are negligible.

### Dashboard Impact

External dashboards parse logs in real-time. Excessive logging can:
- Overwhelm log ingestion pipelines
- Increase storage costs
- Reduce query performance
- Impact dashboard responsiveness

**Mitigation:**
- Use appropriate log levels (DEBUG only when needed)
- Remove logs from tight loops
- Use sampling for high-frequency events

---

## Testing Requirements

### Unit Tests

**Required coverage:**
- `test_structured_formatter()` - JSON output format
- `test_human_readable_formatter()` - Console output format
- `test_processor_logger_adapter()` - Context injection
- `test_trace_context()` - Context management
- `test_generate_trace_id()` - ID generation
- `test_configure_logging()` - Configuration

### Integration Tests

**Scenarios:**
- HTTP request → trace_id in logs → trace_id in response
- Nested trace contexts
- Concurrent requests with different trace_ids
- Async operations preserve trace_id
- Logger hierarchy and level inheritance

### Manual Verification

```bash
# 1. Start KATO
./start.sh

# 2. Send request with trace ID
curl -H "X-Trace-ID: test-trace-123" \
     http://localhost:8000/health

# 3. Check logs for trace ID
docker logs kato 2>&1 | grep "test-trace-123"

# 4. Verify response includes trace ID
# Should see: X-Trace-ID: test-trace-123
```

---

## Migration History

### Phase 1: Dual Logger Cleanup (October 2025)

**Problem:** Multiple files used both `kato.utils.logging.get_logger()` and `logging.getLogger()`

**Resolution:**
- Standardized on `logging.getLogger(__name__)`
- Removed duplicate logger instances
- Migrated trace utilities to `kato.config.logging_config`

**Files affected:**
- `kato/services/kato_fastapi.py`
- `kato/workers/pattern_processor.py`

### Phase 2: Print Statement Removal (October 2025)

**Problem:** 24 print() statements bypassed logging system

**Resolution:**
- Converted to `logger.debug()` calls
- Maintained same information output
- Now respects log level configuration

**Files affected:**
- `kato/sessions/redis_session_manager.py` (18 prints)
- `kato/api/endpoints/sessions.py` (6 prints)

### Phase 3: Useless Log Removal (October 2025)

**Problem:** Noise logs with no diagnostic value

**Resolution:**
- Removed "logging initiated" messages (4 occurrences)
- Removed high-frequency DEBUG logs (11 occurrences)
- Kept only meaningful diagnostic logs

**Files affected:**
- `kato/workers/kato_processor.py`
- `kato/workers/pattern_processor.py`
- `kato/workers/memory_manager.py`
- `kato/workers/pattern_operations.py`
- `kato/informatics/knowledge_base.py`
- `kato/informatics/metrics.py`

### Phase 4: Full Deprecation (October 2025)

**Problem:** `kato/utils/logging.py` was redundant with `kato/config/logging_config.py`

**Resolution:**
- Deleted `kato/utils/logging.py`
- Updated `kato/utils/__init__.py` to remove exports
- Added migration notice

**Migration path:**
```python
# Old (deprecated)
from kato.utils.logging import get_logger

# New (current)
import logging
logger = logging.getLogger(__name__)

# Or with processor context
from kato.config.logging_config import get_logger
logger = get_logger(__name__, processor_id='proc_123')
```

---

## Future Enhancements

### Planned Improvements

1. **Sampling Support**
   ```python
   # Log 1% of DEBUG messages to reduce volume
   @sampling_logger(rate=0.01)
   def high_frequency_operation():
       logger.debug("Frequent operation")
   ```

2. **Log Aggregation**
   ```python
   # Aggregate similar logs
   logger.info("Pattern learned", aggregate_key="pattern_learned", window_seconds=60)
   # Output: "Pattern learned (x247 times in last 60s)"
   ```

3. **Dynamic Log Levels**
   ```python
   # Change log levels without restart
   POST /admin/log-level
   {"logger": "kato.workers", "level": "DEBUG"}
   ```

4. **Structured Context**
   ```python
   # Automatic context inclusion
   with log_context(session_id='sess_123', user='alice'):
       logger.info("Operation")
       # Includes session_id and user automatically
   ```

5. **Performance Profiling**
   ```python
   # Built-in operation timing
   with PerformanceTimer(logger, "database_query"):
       result = db.query()
   # Automatically logs duration with percentile tracking
   ```

### Backward Compatibility

All future changes must maintain:
- Existing logger names and hierarchy
- JSON output format for dashboard compatibility
- Trace ID format and propagation
- Standard logging module compatibility

---

## Appendix A: Configuration Reference

### Environment Variables

| Variable | Values | Default | Description |
|----------|--------|---------|-------------|
| `LOG_LEVEL` | DEBUG, INFO, WARNING, ERROR, CRITICAL | INFO | Minimum log level |
| `LOG_FORMAT` | json, human | human | Output format |
| `LOG_OUTPUT` | stdout, stderr, filepath | stdout | Output destination |

### Programmatic API

```python
from kato.config.logging_config import configure_logging

configure_logging(
    level="INFO",           # str or int (logging.INFO)
    format_type="json",     # "json" or "human"
    output="stdout",        # "stdout", "stderr", or file path
    processor_id=None       # Optional default processor_id
)
```

---

## Appendix B: Dashboard Integration

### Recommended Log Queries

**Error Rate Over Time:**
```sql
SELECT count(*) as errors, bucket(timestamp, 1m) as time
FROM logs
WHERE level IN ('ERROR', 'CRITICAL')
GROUP BY time
ORDER BY time DESC
```

**Top Error Messages:**
```sql
SELECT message, count(*) as occurrences
FROM logs
WHERE level = 'ERROR'
GROUP BY message
ORDER BY occurrences DESC
LIMIT 10
```

**Request Tracing:**
```sql
SELECT timestamp, logger, message
FROM logs
WHERE trace_id = 'kato-abc123...'
ORDER BY timestamp ASC
```

**Processor Performance:**
```sql
SELECT processor_id, avg(duration_ms) as avg_duration
FROM logs
WHERE message LIKE '%completed%' AND duration_ms IS NOT NULL
GROUP BY processor_id
```

---

## Appendix C: Contributing Guidelines

### Adding New Logs

1. **Choose appropriate level:**
   - DEBUG: Detailed diagnostics
   - INFO: Significant events
   - WARNING: Unexpected but handled
   - ERROR: Operation failures
   - CRITICAL: Service-level failures

2. **Include context:**
   ```python
   # Good
   logger.info(f"Session {session_id} created for node {node_id}")

   # Bad
   logger.info("Session created")
   ```

3. **Use structured logging for metrics:**
   ```python
   logger.info(
       "Request completed",
       extra={
           'operation': 'observe',
           'duration_ms': 45.2,
           'status': 'success'
       }
   )
   ```

4. **Avoid high-frequency paths:**
   - Never log in tight loops
   - Never log on every observation/prediction
   - Consider aggregation or sampling

5. **Test dashboard compatibility:**
   - Verify JSON output is valid
   - Check dashboard can parse new fields
   - Confirm queries still work

---

## Document Maintenance

**Review Cycle:** Quarterly
**Last Review:** October 2025
**Next Review:** January 2026
**Owner:** KATO Core Team
**Approvers:** Technical Lead, DevOps Lead

**Change Log:**
- 2025-10-11: Initial version after logging technical debt reduction
- (Future changes will be recorded here)
