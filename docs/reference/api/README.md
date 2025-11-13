# KATO API Reference

Complete reference documentation for all KATO REST API endpoints.

## Base URL

```
http://localhost:8000
```

## Interactive Documentation

KATO provides auto-generated interactive API documentation:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## API Categories

### Session Management
Session-based API for multi-user support and state isolation.

**See**: [sessions.md](sessions.md)

**Endpoints**:
- `POST /sessions` - Create a new session
- `GET /sessions/{session_id}` - Get session information
- `DELETE /sessions/{session_id}` - Delete a session
- `POST /sessions/{session_id}/extend` - Extend session TTL
- `GET /sessions/{session_id}/exists` - Check session existence
- `GET /sessions/count` - Get active session count

### Observations
Process observations and manage short-term memory.

**See**: [observations.md](observations.md)

**Endpoints**:
- `POST /sessions/{session_id}/observe` - Process a single observation
- `POST /sessions/{session_id}/observe-sequence` - Process multiple observations
- `GET /sessions/{session_id}/stm` - Get short-term memory state

### Predictions
Retrieve predictions based on learned patterns.

**See**: [predictions.md](predictions.md)

**Endpoints**:
- `GET /sessions/{session_id}/predictions` - Get predictions from current STM

### Learning
Learn patterns from observations.

**See**: [learning.md](learning.md)

**Endpoints**:
- `POST /sessions/{session_id}/learn` - Learn pattern from STM
- `POST /sessions/{session_id}/clear-stm` - Clear short-term memory
- `POST /sessions/{session_id}/clear-all` - Clear all memory (STM + patterns)

### Configuration
Update session-specific configuration.

**See**: [configuration.md](configuration.md)

**Endpoints**:
- `POST /sessions/{session_id}/config` - Update session configuration

### Health & Status
System health and status monitoring.

**See**: [health.md](health.md)

**Endpoints**:
- `GET /health` - Enhanced health check with metrics
- `GET /status` - System status with session statistics

### Monitoring & Metrics
Performance monitoring and operational metrics.

**See**: [monitoring.md](monitoring.md)

**Endpoints**:
- `GET /concurrency` - Real-time concurrency metrics
- `GET /cache/stats` - Redis cache performance statistics
- `POST /cache/invalidate` - Invalidate pattern cache
- `GET /distributed-stm/stats` - Distributed STM statistics
- `GET /metrics` - Comprehensive system metrics
- `GET /stats` - Time-series statistics
- `GET /metrics/{metric_name}` - Specific metric history
- `GET /connection-pools` - Connection pool health

### Utility Operations
Pattern retrieval and processor data access.

**See**: [utility.md](utility.md)

**Endpoints**:
- `GET /pattern/{pattern_id}` - Get specific pattern by ID
- `GET /percept-data` - Get percept data from processor
- `GET /cognition-data` - Get cognition data from processor
- `GET /sessions/{session_id}/percept-data` - Get session percept data
- `GET /sessions/{session_id}/cognition-data` - Get session cognition data

## Authentication

KATO currently does not require authentication. All endpoints are publicly accessible.

**Production Note**: Implement authentication (API keys, OAuth, etc.) before deploying to production.

## Request/Response Format

### Content-Type

All requests and responses use JSON:

```
Content-Type: application/json
```

### Request Body Format

```json
{
  "field_name": "value",
  "nested_object": {
    "key": "value"
  },
  "array_field": ["item1", "item2"]
}
```

### Response Format

Successful responses (2xx):

```json
{
  "status": "okay",
  "data": {...},
  "session_id": "session-abc123..."
}
```

Error responses (4xx/5xx):

```json
{
  "detail": "Error message describing what went wrong"
}
```

## Common HTTP Status Codes

| Code | Meaning | Usage |
|------|---------|-------|
| 200 | OK | Successful GET request |
| 201 | Created | Successful resource creation |
| 400 | Bad Request | Invalid request data (e.g., vector dimension mismatch) |
| 404 | Not Found | Session or resource not found |
| 500 | Internal Server Error | Server-side error |
| 503 | Service Unavailable | Service temporarily unavailable |

## Session-Based API (Required)

**⚠️ IMPORTANT**: As of KATO v3.0+, all core operations require session-based endpoints.

Direct endpoints (`/observe`, `/learn`, `/predictions`) have been **permanently removed**.

### Why Session-Based?

- ✅ **Multi-user support**: Isolated state per session
- ✅ **Concurrent access**: Multiple users simultaneously
- ✅ **Per-session configuration**: Customize behavior per user
- ✅ **Redis-backed persistence**: Sessions survive restarts
- ✅ **TTL management**: Automatic cleanup of inactive sessions

### Basic Workflow

1. **Create a session**:
   ```http
   POST /sessions
   {
     "node_id": "user_alice"
   }
   ```

2. **Process observations**:
   ```http
   POST /sessions/{session_id}/observe
   {
     "strings": ["hello", "world"]
   }
   ```

3. **Get predictions**:
   ```http
   GET /sessions/{session_id}/predictions
   ```

4. **Learn patterns**:
   ```http
   POST /sessions/{session_id}/learn
   ```

5. **Clean up** (optional):
   ```http
   DELETE /sessions/{session_id}
   ```

## Rate Limiting

KATO uses concurrency limiting rather than traditional rate limiting.

**Default Configuration**:
- Per-worker concurrency limit: 1000 concurrent requests
- Warning threshold: 80% (800 concurrent)
- Critical threshold: 95% (950 concurrent)

Monitor concurrency with: `GET /concurrency`

## Versioning

Current API version: **v3.0+**

KATO uses URL-based versioning. The current API is stable and will maintain backward compatibility.

Breaking changes will be released as new API versions (e.g., `/v2/sessions`).

## Data Models

See [../data-specifications.md](../data-specifications.md) for complete data model documentation:

- [Observation Object](../observation-object.md)
- [Prediction Object](../prediction-object.md)
- [Pattern Object](../pattern-object.md)
- [Session Configuration](../session-configuration.md)

## Error Handling

See [../error-codes.md](../error-codes.md) for complete error reference.

### Common Errors

**Session Not Found (404)**:
```json
{
  "detail": "Session {session_id} not found or expired"
}
```

**Vector Dimension Mismatch (400)**:
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

**Empty STM (400)**:
```json
{
  "detail": "Cannot learn from empty STM"
}
```

## Best Practices

### 1. Session Lifecycle Management

- Always delete sessions when done to free resources
- Use `ttl_seconds` appropriate for your use case
- Monitor active sessions with `GET /sessions/count`

### 2. Batch Processing

- Use `observe-sequence` for bulk observations (more efficient)
- Enable session heartbeat for large batches (automatic for >50 observations)

### 3. Error Handling

- Check for 404 (session expired) and recreate if needed
- Handle vector dimension errors gracefully
- Implement retry logic for 500 errors

### 4. Performance

- Reuse sessions across multiple requests
- Monitor `/concurrency` endpoint under load
- Use `/cache/stats` to verify cache effectiveness

## See Also

- [Quick Start Guide](../../users/quick-start.md)
- [Core Concepts](../../users/concepts.md)
- [Configuration Reference](../configuration-vars.md)
- [Troubleshooting](../../users/troubleshooting.md)

---

**Last Updated**: November 2025
**KATO Version**: 3.0+
