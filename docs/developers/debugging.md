# Debugging Guide for KATO

Comprehensive guide to debugging KATO during development.

## Overview

Effective debugging strategies for KATO:
1. **Structured Logging** - Trace execution with detailed logs
2. **Interactive Debugging** - Use pdb/debugger for step-through
3. **Service Inspection** - Monitor Docker containers and databases
4. **Request Tracing** - Follow requests through the system
5. **Performance Profiling** - Identify bottlenecks

## Logging

### Log Levels

KATO uses Python's standard logging with configurable levels:

```python
# Environment variable
LOG_LEVEL=DEBUG  # DEBUG, INFO, WARNING, ERROR, CRITICAL

# In code
import logging
logger = logging.getLogger('kato.workers.pattern_processor')
logger.debug("Detailed debug information")
logger.info("General information")
logger.warning("Warning message")
logger.error("Error occurred", exc_info=True)  # Include traceback
```

### Structured Logging

**Location**: Throughout codebase

```python
# Good logging with context
logger.info(
    "Pattern learned",
    extra={
        "pattern_name": pattern.pattern_name,
        "node_id": self.node_id,
        "length": pattern.length,
        "observation_count": pattern.observation_count,
        "trace_id": trace_id  # Request correlation
    }
)

# Search logs with jq
docker logs kato | jq 'select(.pattern_name == "PTN|abc123")'
```

### Viewing Logs

**Container Logs**:
```bash
# View KATO service logs
docker logs kato --tail 100 -f

# View specific service
docker logs kato-clickhouse --tail 50
docker logs kato-qdrant --tail 50
docker logs kato-redis --tail 50

# Filter logs by level
docker logs kato 2>&1 | grep ERROR
docker logs kato 2>&1 | grep "Pattern learned"

# Save logs to file
docker logs kato > kato_logs.txt
```

**Application Logs**:
```bash
# Inside container
docker exec -it kato cat /var/log/kato.log

# Stream logs
docker exec -it kato tail -f /var/log/kato.log
```

### Custom Logger Setup

```python
# config/logging_config.py
import logging.config

LOGGING_CONFIG = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'detailed': {
            'format': '[%(asctime)s] %(levelname)s [%(name)s:%(lineno)d] %(message)s',
            'datefmt': '%Y-%m-%d %H:%M:%S'
        },
        'json': {
            'class': 'pythonjsonlogger.jsonlogger.JsonFormatter',
            'format': '%(asctime)s %(name)s %(levelname)s %(message)s'
        }
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'detailed',
            'stream': 'ext://sys.stdout'
        },
        'file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'formatter': 'json',
            'filename': '/var/log/kato.log',
            'maxBytes': 10485760,  # 10MB
            'backupCount': 5
        }
    },
    'root': {
        'level': 'INFO',
        'handlers': ['console', 'file']
    },
    'loggers': {
        'kato': {
            'level': 'DEBUG',
            'handlers': ['console', 'file'],
            'propagate': False
        }
    }
}

# Use in application
logging.config.dictConfig(LOGGING_CONFIG)
```

## Interactive Debugging

### Using pdb (Python Debugger)

**In Tests** (recommended for development):
```python
def test_pattern_learning(kato_fixture):
    """Test pattern learning with debugging."""
    kato_fixture.clear_all_memory()

    # Add observations
    kato_fixture.observe({'strings': ['hello', 'world'], 'vectors': [], 'emotives': {}})

    # Start debugger
    import pdb; pdb.set_trace()

    # Learn pattern
    pattern = kato_fixture.learn()

    assert pattern['pattern_name'].startswith('PTN|')

# Run test
pytest tests/tests/unit/test_patterns.py::test_pattern_learning -s
```

**In Source Code** (temporary debugging):
```python
# workers/pattern_processor.py
def learn_pattern(self, stm: list[list[str]], emotives: dict) -> Pattern:
    """Learn pattern from STM."""

    # Temporary breakpoint
    import pdb; pdb.set_trace()

    pattern_hash = self._hash_pattern(stm)
    # ... rest of method

    return pattern
```

### pdb Commands

```
# Navigation
n        # Next line
s        # Step into function
c        # Continue execution
r        # Return from function
q        # Quit debugger

# Inspection
p var    # Print variable
pp var   # Pretty-print variable
l        # List source code
w        # Show stack trace
a        # Show function arguments

# Breakpoints
b 42              # Set breakpoint at line 42
b function_name   # Set breakpoint at function
b                 # List all breakpoints
cl 1              # Clear breakpoint 1
```

### VS Code Debugger

**Configuration** (`.vscode/launch.json`):
```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "KATO Tests",
      "type": "python",
      "request": "launch",
      "module": "pytest",
      "args": [
        "tests/tests/unit/test_patterns.py",
        "-v",
        "-s"
      ],
      "console": "integratedTerminal",
      "env": {
        "PYTHONPATH": "${workspaceFolder}"
      }
    },
    {
      "name": "KATO Service",
      "type": "python",
      "request": "attach",
      "connect": {
        "host": "localhost",
        "port": 5678
      },
      "pathMappings": [
        {
          "localRoot": "${workspaceFolder}",
          "remoteRoot": "/app"
        }
      ]
    }
  ]
}
```

**Attach to Running Container**:
```python
# Install debugpy in container
pip install debugpy

# Add to kato/api/main.py
import debugpy
debugpy.listen(("0.0.0.0", 5678))
# debugpy.wait_for_client()  # Optional: pause until debugger attaches

# In docker-compose.yml, expose port
services:
  kato:
    ports:
      - "8000:8000"
      - "5678:5678"  # Debugger port
```

### PyCharm Debugger

1. **Set Breakpoint**: Click left gutter in editor
2. **Run Test in Debug Mode**: Right-click test → Debug
3. **Attach to Process**: Run → Attach to Process → Select Python process

## Request Tracing

### Trace ID Propagation

**Implementation**:
```python
# api/middleware.py
import uuid
from starlette.middleware.base import BaseHTTPMiddleware

class TraceIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        # Generate or extract trace ID
        trace_id = request.headers.get('X-Trace-ID', str(uuid.uuid4()))

        # Add to request state
        request.state.trace_id = trace_id

        # Log request start
        logger.info(
            f"Request started: {request.method} {request.url.path}",
            extra={"trace_id": trace_id}
        )

        # Process request
        response = await call_next(request)

        # Add trace ID to response headers
        response.headers['X-Trace-ID'] = trace_id

        # Log request end
        logger.info(
            f"Request completed: {response.status_code}",
            extra={"trace_id": trace_id}
        )

        return response

# Use in all log statements
logger.info("Pattern learned", extra={"trace_id": request.state.trace_id})
```

**Usage**:
```bash
# Make request with trace ID
curl -H "X-Trace-ID: my-debug-trace" \
  http://localhost:8000/sessions/abc/observe \
  -d '{"strings": ["test"]}'

# Search logs for this trace
docker logs kato | grep "my-debug-trace"
```

## Database Debugging

### ClickHouse Inspection

```bash
# Connect to ClickHouse
docker exec -it kato-clickhouse clickhouse-client

# Use database
USE kato

# Show tables
SHOW TABLES

# Query patterns
SELECT * FROM patterns LIMIT 5

# Find specific pattern
SELECT * FROM patterns WHERE name = 'abc123'

# Count patterns
SELECT count() FROM patterns

# Show table structure
DESCRIBE patterns

# Explain query (performance debugging)
EXPLAIN SELECT * FROM patterns WHERE length = 3

# View query log
SELECT * FROM system.query_log ORDER BY event_time DESC LIMIT 10
```

### Qdrant Inspection

```bash
# Check collections
curl http://localhost:6333/collections

# Get collection info
curl http://localhost:6333/collections/vectors_test_app

# Count vectors
curl http://localhost:6333/collections/vectors_test_app

# Search vectors (debugging)
curl -X POST http://localhost:6333/collections/vectors_test_app/points/search \
  -H 'Content-Type: application/json' \
  -d '{
    "vector": [0.1, 0.2, ...],
    "limit": 5,
    "with_payload": true
  }'

# Get specific point
curl http://localhost:6333/collections/vectors_test_app/points/{point_id}
```

### Redis Inspection

```bash
# Connect to Redis
docker exec -it kato-redis redis-cli

# List all keys
KEYS *

# List session keys
KEYS session:*

# Get session data
GET session:abc123
HGETALL session:abc123

# Check TTL
TTL session:abc123

# Monitor all commands (debugging)
MONITOR

# Get info
INFO
INFO memory
INFO stats
```

## Common Issues and Solutions

### Issue: Request Timeout

**Symptoms**:
- HTTP 504 Gateway Timeout
- Slow response times

**Debug Steps**:
```python
# Add timing logs
import time

def get_predictions(self, threshold: float):
    start = time.time()

    # Candidate retrieval
    t1 = time.time()
    candidates = self._get_candidates()
    logger.debug(f"Candidate retrieval: {time.time() - t1:.3f}s")

    # Similarity calculation
    t2 = time.time()
    scored = self._calculate_similarities(candidates)
    logger.debug(f"Similarity calculation: {time.time() - t2:.3f}s")

    # Ranking
    t3 = time.time()
    ranked = self._rank_patterns(scored)
    logger.debug(f"Ranking: {time.time() - t3:.3f}s")

    logger.info(f"Total prediction time: {time.time() - start:.3f}s")
    return ranked
```

**Solutions**:
- Add database indices
- Enable query caching
- Use ClickHouse for read-heavy workloads
- Reduce `max_predictions` limit

### Issue: Memory Leak

**Symptoms**:
- Increasing memory usage over time
- OOM (Out of Memory) errors

**Debug Steps**:
```python
# Track memory usage
import tracemalloc
import psutil

# Start tracking
tracemalloc.start()

# ... run operations ...

# Get memory snapshot
snapshot = tracemalloc.take_snapshot()
top_stats = snapshot.statistics('lineno')

for stat in top_stats[:10]:
    print(stat)

# Check process memory
process = psutil.Process()
print(f"Memory: {process.memory_info().rss / 1024 / 1024:.2f} MB")
```

**Solutions**:
- Clear STM after learning (if `stm_mode == "CLEAR"`)
- Limit cache sizes
- Use Redis for session state (not in-memory)
- Profile with `memory_profiler`

### Issue: Database Connection Lost

**Symptoms**:
- `clickhouse_driver.errors.NetworkError`
- `QdrantException: Connection failed`

**Debug Steps**:
```bash
# Check if services are running
docker-compose ps

# Check service logs
docker logs kato-clickhouse --tail 50
docker logs kato-qdrant --tail 50

# Test connections manually
# ClickHouse
docker exec -it kato-clickhouse clickhouse-client --query "SELECT 1"

# Qdrant
curl http://localhost:6333/collections

# Redis
docker exec -it kato-redis redis-cli PING
```

**Solutions**:
```python
# Add connection retry logic
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10)
)
def connect_to_clickhouse():
    from clickhouse_driver import Client
    client = Client(host=clickhouse_host, port=clickhouse_port)
    # Verify connection
    client.execute('SELECT 1')
    return client
```

### Issue: Inconsistent Test Results

**Symptoms**:
- Tests pass sometimes, fail other times
- Different results on different runs

**Debug Steps**:
```python
# Add deterministic sorting
def test_predictions_are_deterministic(kato_fixture):
    """Ensure predictions are deterministic."""
    kato_fixture.clear_all_memory()

    # Setup
    for _ in range(3):
        kato_fixture.observe({'strings': ['a', 'b'], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()

    # Get predictions twice
    kato_fixture.clear_stm()
    kato_fixture.observe({'strings': ['a', 'b'], 'vectors': [], 'emotives': {}})

    predictions1 = kato_fixture.get_predictions()
    predictions2 = kato_fixture.get_predictions()

    # Should be identical
    assert predictions1 == predictions2, "Predictions are non-deterministic!"
```

**Solutions**:
- Use deterministic sorting (alphanumeric)
- Seed random number generators
- Clear databases between tests
- Use unique `session_id` per test

## Performance Debugging

### Enable Query Profiling

**ClickHouse**:
```sql
-- Enable query logging
SET log_queries = 1;

-- View query log
SELECT * FROM system.query_log
WHERE query_duration_ms > 100
ORDER BY event_time DESC
LIMIT 10;

-- Check slow queries
SELECT query, query_duration_ms
FROM system.query_log
WHERE type = 'QueryFinish'
ORDER BY query_duration_ms DESC
LIMIT 10;
```

### Benchmark Specific Operations

```python
# Use pytest-benchmark
def test_pattern_matching_performance(benchmark, kato_fixture):
    """Benchmark pattern matching."""
    # Setup
    for i in range(100):
        kato_fixture.observe({'strings': [f'token_{i}'], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()

    kato_fixture.clear_stm()
    kato_fixture.observe({'strings': ['token_0'], 'vectors': [], 'emotives': {}})

    # Benchmark
    result = benchmark(kato_fixture.get_predictions)

    assert len(result['predictions']) > 0
    print(f"Median time: {benchmark.stats.median:.4f}s")

# Run
pytest tests/test_performance.py --benchmark-only
```

### Profile with cProfile

```python
import cProfile
import pstats

# Profile code
profiler = cProfile.Profile()
profiler.enable()

# Run operation
processor.get_predictions()

profiler.disable()

# Print stats
stats = pstats.Stats(profiler)
stats.sort_stats('cumulative')
stats.print_stats(20)  # Top 20 functions
```

## Debugging Tools

### HTTPie for API Testing

```bash
# Install
pip install httpie

# Create session
http POST localhost:8000/sessions node_id=test_app

# Observe
http POST localhost:8000/sessions/abc123/observe \
  strings:='["hello", "world"]' \
  vectors:='[]' \
  emotives:='{}'

# Get predictions
http GET localhost:8000/sessions/abc123/predictions
```

### jq for Log Parsing

```bash
# Filter JSON logs
docker logs kato | jq 'select(.level == "ERROR")'

# Extract specific fields
docker logs kato | jq '{timestamp: .timestamp, message: .message, pattern: .pattern_name}'

# Count errors by type
docker logs kato | jq -r '.error_type' | sort | uniq -c
```

### Watch for Live Updates

```bash
# Watch active sessions
watch -n 1 'curl -s localhost:8000/sessions/count | jq'

# Monitor MongoDB queries
watch -n 2 'docker exec kato-mongodb mongosh --quiet --eval "db.currentOp()"'
```

## Related Documentation

- [Testing Guide](testing.md)
- [Performance Profiling](performance-profiling.md)
- [Architecture Overview](architecture.md)
- [Code Organization](code-organization.md)

---

**Last Updated**: November 2025
**KATO Version**: 3.0+
