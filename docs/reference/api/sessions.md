# Session Management API

Session endpoints for creating, managing, and deleting isolated user sessions.

## Overview

Sessions provide isolated workspaces for users with:
- Independent short-term memory (STM)
- Shared long-term memory (LTM) per `node_id`
- Per-session configuration
- Automatic TTL-based expiration
- Redis-backed persistence

## Endpoints

### Create Session

Create a new isolated session for a user or application.

```http
POST /sessions
```

**Request Body**:

```json
{
  "node_id": "user_alice",              // Required: Node identifier
  "config": {                            // Optional: Session-specific configuration
    "recall_threshold": 0.5,
    "max_predictions": 100,
    "use_token_matching": true,
    "sort_symbols": true
  },
  "ttl_seconds": 3600,                   // Optional: Session TTL (default: 3600)
  "metadata": {                          // Optional: Custom metadata
    "user_id": "alice@example.com",
    "app_version": "1.0.0"
  }
}
```

**Response** (`200 OK`):

```json
{
  "session_id": "session-abc123def456...",
  "node_id": "user_alice",
  "created_at": "2025-11-13T12:00:00Z",
  "expires_at": "2025-11-13T13:00:00Z",
  "ttl_seconds": 3600,
  "metadata": {
    "user_id": "alice@example.com",
    "app_version": "1.0.0"
  },
  "session_config": {
    "recall_threshold": 0.5,
    "max_predictions": 100,
    "use_token_matching": true,
    "sort_symbols": true
  }
}
```

**Parameters**:

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `node_id` | string | Yes | - | Node identifier for shared LTM |
| `config` | object | No | {} | Session-specific configuration |
| `ttl_seconds` | integer | No | 3600 | Time-to-live in seconds |
| `metadata` | object | No | {} | Custom metadata dictionary |

**Example**:

```bash
curl -X POST http://localhost:8000/sessions \
  -H "Content-Type: application/json" \
  -d '{
    "node_id": "user_alice",
    "ttl_seconds": 7200,
    "config": {"recall_threshold": 0.3}
  }'
```

---

### Get Session Information

Retrieve information about an existing session.

```http
GET /sessions/{session_id}
```

**Parameters**:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `session_id` | string (path) | Yes | Session identifier |

**Response** (`200 OK`):

```json
{
  "session_id": "session-abc123...",
  "node_id": "user_alice",
  "created_at": "2025-11-13T12:00:00Z",
  "expires_at": "2025-11-13T13:00:00Z",
  "ttl_seconds": 3600,
  "metadata": {},
  "session_config": {
    "recall_threshold": 0.3
  }
}
```

**Errors**:

- `404 Not Found`: Session not found or expired

**Example**:

```bash
curl http://localhost:8000/sessions/session-abc123...
```

---

### Check Session Exists

Check if a session exists without extending its TTL.

```http
GET /sessions/{session_id}/exists
```

**Use Case**: Testing expiration behavior without triggering auto-extension.

**Parameters**:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `session_id` | string (path) | Yes | Session identifier |

**Response** (`200 OK`):

```json
{
  "exists": true,
  "expired": false,
  "session_id": "session-abc123..."
}
```

**Possible States**:

| exists | expired | Meaning |
|--------|---------|---------|
| true | false | Session exists and is valid |
| false | false | Session never existed |
| false | true | Session existed but expired (now deleted) |

**Example**:

```bash
curl http://localhost:8000/sessions/session-abc123.../exists
```

---

### Delete Session

Delete a session and cleanup associated resources.

```http
DELETE /sessions/{session_id}
```

**Parameters**:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `session_id` | string (path) | Yes | Session identifier |

**Response** (`200 OK`):

```json
{
  "status": "deleted",
  "session_id": "session-abc123..."
}
```

**Errors**:

- `404 Not Found`: Session not found

**Example**:

```bash
curl -X DELETE http://localhost:8000/sessions/session-abc123...
```

---

### Extend Session TTL

Extend the expiration time of a session.

```http
POST /sessions/{session_id}/extend?ttl_seconds=3600
```

**Parameters**:

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `session_id` | string (path) | Yes | - | Session identifier |
| `ttl_seconds` | integer (query) | No | 3600 | Additional seconds to add |

**Response** (`200 OK`):

```json
{
  "status": "extended",
  "session_id": "session-abc123...",
  "ttl_seconds": 3600
}
```

**Errors**:

- `404 Not Found`: Session not found

**Example**:

```bash
curl -X POST "http://localhost:8000/sessions/session-abc123.../extend?ttl_seconds=7200"
```

**Note**: If `SESSION_AUTO_EXTEND=true` (default), sessions are automatically extended on each access.

---

### Get Active Session Count

Get the count of currently active sessions.

```http
GET /sessions/count
```

**Response** (`200 OK`):

```json
{
  "active_session_count": 42
}
```

**Example**:

```bash
curl http://localhost:8000/sessions/count
```

**Use Cases**:
- Monitoring system usage
- Capacity planning
- Debugging session leaks

---

## Session Lifecycle

### 1. Creation

```
POST /sessions → session_id (TTL starts)
```

### 2. Active Usage

```
Session operations (observe, learn, predictions)
↓
TTL auto-extended (if SESSION_AUTO_EXTEND=true)
```

### 3. Expiration

```
No activity for TTL seconds
↓
Session automatically deleted from Redis
↓
404 Not Found on next access
```

### 4. Manual Cleanup

```
DELETE /sessions/{session_id}
↓
Immediate deletion
```

## Configuration Management

Sessions can have custom configuration that overrides system defaults.

**See**: [configuration.md](configuration.md) for configuration endpoint details.

**Example Configuration**:

```json
{
  "recall_threshold": 0.5,           // Pattern matching threshold
  "max_predictions": 100,             // Prediction limit
  "use_token_matching": true,         // Token vs character matching
  "sort_symbols": true,               // Symbol sorting
  "max_pattern_length": 10,           // Auto-learning trigger
  "stm_mode": "CLEAR",                // STM mode after learning
  "persistence": 20                   // Emotive window size
}
```

## Data Isolation

### Per-Session (Isolated)
- Short-term memory (STM)
- Emotives accumulator
- Metadata accumulator
- Time counter
- Percept data
- Predictions

### Per-Node (Shared)
- Learned patterns (LTM)
- Pattern frequency
- Pattern emotives/metadata

### Example

```
user_alice creates session_1 → STM_1 (isolated)
user_alice creates session_2 → STM_2 (isolated)
user_bob creates session_3   → STM_3 (isolated)

All sessions for node_id="app" share LTM patterns.
```

## Best Practices

### 1. Choose Appropriate TTL

```json
{
  "ttl_seconds": 300     // 5 min - Chatbot conversation
  "ttl_seconds": 3600    // 1 hour - Web session (default)
  "ttl_seconds": 86400   // 24 hours - Long-running analysis
}
```

### 2. Set Meaningful Node IDs

```json
{
  "node_id": "chatbot_user_alice",      // User-specific chatbot
  "node_id": "analytics_dashboard",     // Shared analytics
  "node_id": "app_v1.0"                 // Application version
}
```

### 3. Clean Up Sessions

```javascript
try {
  // ... use session ...
} finally {
  await fetch(`/sessions/${sessionId}`, {method: 'DELETE'});
}
```

### 4. Handle Expiration Gracefully

```javascript
async function apiCall(sessionId) {
  const response = await fetch(`/sessions/${sessionId}/observe`, {...});

  if (response.status === 404) {
    // Session expired, create new one
    const newSession = await createSession();
    return apiCall(newSession.session_id);
  }

  return response.json();
}
```

## Error Handling

### Session Not Found (404)

**Causes**:
- Session expired (TTL reached)
- Session never existed
- Session was manually deleted

**Solution**: Create a new session

### Session Already Exists (Rare)

UUID collision is extremely unlikely but handle it:

```javascript
let session;
let retries = 3;

while (retries > 0) {
  try {
    session = await createSession();
    break;
  } catch (error) {
    retries--;
  }
}
```

## Monitoring

### Active Sessions

```bash
curl http://localhost:8000/sessions/count
```

### Session Details

```bash
curl http://localhost:8000/sessions/{session_id}
```

### System Status

```bash
curl http://localhost:8000/status
```

Returns:

```json
{
  "status": "healthy",
  "sessions": {
    "active": 42,
    "total_created": 1234,
    "total_deleted": 1192
  }
}
```

## See Also

- [Observations API](observations.md) - Process data in sessions
- [Predictions API](predictions.md) - Get predictions from sessions
- [Learning API](learning.md) - Learn patterns from sessions
- [Configuration API](configuration.md) - Update session config
- [Session Configuration Reference](../session-configuration.md)

---

**Last Updated**: November 2025
**KATO Version**: 3.0+
