# KATO WebSocket Integration Requirements

**Document Version:** 1.0
**Last Updated:** 2025-10-11
**Status:** Requirements Specification
**Target:** KATO core project team

---

## Executive Summary

This document specifies the WebSocket and event-driven API requirements for KATO to support enhanced real-time monitoring in the KATO Dashboard. The dashboard team has identified specific data streams and events that would significantly improve monitoring capabilities and user experience.

**Key Requirement:** KATO should provide real-time event notifications for session lifecycle changes and system events, either via WebSocket or HTTP callbacks.

**Priority:** MEDIUM (Dashboard can work with current HTTP API + polling, but real-time events would be optimal)

**Effort Estimate:** 2-3 weeks for full implementation

---

## Table of Contents

1. [Background & Motivation](#background--motivation)
2. [Current State Analysis](#current-state-analysis)
3. [Proposed Solutions](#proposed-solutions)
4. [Option 1: WebSocket Event Stream](#option-1-websocket-event-stream-recommended)
5. [Option 2: HTTP Webhook Callbacks](#option-2-http-webhook-callbacks)
6. [Option 3: Enhanced HTTP API](#option-3-enhanced-http-api-fallback)
7. [Implementation Phases](#implementation-phases)
8. [Message Format Specifications](#message-format-specifications)
9. [Testing Requirements](#testing-requirements)
10. [Backwards Compatibility](#backwards-compatibility)

---

## Background & Motivation

### Current Limitations

The KATO Dashboard currently relies on HTTP polling for all data:
- Session data polled every 10 seconds
- Metrics polled every 5 seconds
- Analytics polled every 15-30 seconds

**Problems:**
1. **Latency:** 5-10 second delay before dashboard reflects changes
2. **Server Load:** Unnecessary polling when no changes occurred
3. **Missed Events:** Short-lived sessions may not be captured
4. **User Experience:** Dashboard feels sluggish during rapid changes

### Benefits of Real-Time Events

**For KATO:**
- Reduced HTTP request load (~50% reduction)
- Better visibility into dashboard monitoring
- Improved system observability

**For Dashboard:**
- Instant session creation/destruction notifications
- Proactive error alerting
- Better user experience
- More accurate monitoring

**For Users:**
- Real-time session monitoring
- Immediate error visibility
- Better system awareness

---

## Current State Analysis

### What Dashboard Currently Polls

| Endpoint | Frequency | Data Size | Ideal Approach |
|----------|-----------|-----------|----------------|
| `/metrics` | 5s | ~2KB | WebSocket broadcast ✅ (dashboard handles) |
| `/sessions/count` | 10s | ~200B | **Event notification needed** |
| `/sessions` (list) | 10s | ~5-20KB | HTTP polling OK (pagination) |
| `/sessions/{id}` | 10s | ~1-2KB | HTTP polling OK (details) |
| `/stats` | 10s | ~10KB | HTTP polling OK (historical) |

### Where KATO Could Help

**High Priority:**
1. ✅ **Session Events** - Notify when sessions created/destroyed
2. ✅ **Error Events** - Notify when errors occur in KATO
3. ⚖️ **Metrics Stream** - Real-time metrics (dashboard can handle via current /metrics endpoint)

**Low Priority:**
4. ❌ **Session Details** - Dashboard can poll when needed
5. ❌ **Historical Data** - Dashboard can poll for charts

---

## Proposed Solutions

### Comparison Matrix

| Approach | Complexity | Performance | Flexibility | Backwards Compat |
|----------|-----------|-------------|-------------|-----------------|
| WebSocket Event Stream | HIGH | EXCELLENT | EXCELLENT | GOOD |
| HTTP Webhooks | MEDIUM | GOOD | GOOD | EXCELLENT |
| Enhanced HTTP API | LOW | MODERATE | LIMITED | EXCELLENT |

### Recommendation

**Primary:** Option 1 (WebSocket) for real-time events
**Fallback:** Option 3 (Enhanced HTTP) for backwards compatibility

---

## Option 1: WebSocket Event Stream (RECOMMENDED)

### Overview

KATO exposes a WebSocket endpoint that clients can connect to for receiving real-time events about session lifecycle, errors, and system state changes.

### Architecture

```
┌─────────────────┐
│  KATO Dashboard │
│   (WebSocket    │
│     Client)     │
└────────┬────────┘
         │
         │ ws://kato:8000/ws/events
         │
         ▼
┌─────────────────┐
│  KATO Service   │
│   (WebSocket    │
│    Server)      │
└────────┬────────┘
         │
         ├──► Session Manager ──► Session Events
         ├──► Error Handler   ──► Error Events
         └──► Metrics System  ──► Metrics Updates (optional)
```

### Endpoint Specification

#### WebSocket Endpoint

```
ws://kato:8000/ws/events
```

**Authentication:**
- Use same auth as HTTP API (JWT token in query param or header)
- Example: `ws://kato:8000/ws/events?token=<jwt_token>`

**Connection Lifecycle:**
1. Client connects to `/ws/events`
2. Server sends initial state snapshot (optional)
3. Server pushes events as they occur
4. Client sends heartbeat/ping every 30s
5. Server responds with pong
6. Either side can close connection

### Event Types

#### 1. Session Created Event

**When:** New session is created via `/sessions` endpoint

```json
{
  "event_type": "session.created",
  "timestamp": "2025-10-11T15:30:45.123Z",
  "data": {
    "session_id": "sess_abc123",
    "user_id": "user_xyz789",
    "created_at": "2025-10-11T15:30:45.123Z"
  }
}
```

#### 2. Session Destroyed Event

**When:** Session is deleted or expires

```json
{
  "event_type": "session.destroyed",
  "timestamp": "2025-10-11T15:35:22.456Z",
  "data": {
    "session_id": "sess_abc123",
    "destroyed_at": "2025-10-11T15:35:22.456Z",
    "reason": "explicit_delete" | "expired" | "error"
  }
}
```

#### 3. Session Updated Event (Optional)

**When:** Session STM or metadata changes

```json
{
  "event_type": "session.updated",
  "timestamp": "2025-10-11T15:32:10.789Z",
  "data": {
    "session_id": "sess_abc123",
    "updated_fields": ["short_term_memory", "last_accessed"],
    "stm_size": 1024
  }
}
```

#### 4. Error Event

**When:** Critical errors occur in KATO

```json
{
  "event_type": "system.error",
  "timestamp": "2025-10-11T15:40:00.000Z",
  "data": {
    "error_type": "database_connection" | "pattern_matching" | "memory_limit",
    "severity": "error" | "warning" | "critical",
    "message": "MongoDB connection lost",
    "affected_component": "session_manager",
    "metadata": {}
  }
}
```

#### 5. Metrics Update Event (Optional)

**When:** Key metrics change significantly

```json
{
  "event_type": "metrics.update",
  "timestamp": "2025-10-11T15:41:00.000Z",
  "data": {
    "active_sessions": 127,
    "requests_per_second": 15.3,
    "cpu_percent": 45.2,
    "memory_percent": 62.1
  }
}
```

#### 6. Heartbeat/Ping

**When:** Periodic keep-alive (every 30s)

```json
{
  "event_type": "heartbeat",
  "timestamp": "2025-10-11T15:42:00.000Z"
}
```

### Implementation Guide

#### Python FastAPI Example

```python
# kato/app/api/websocket.py

from fastapi import WebSocket, WebSocketDisconnect, Depends
from typing import List
import asyncio
import json
from datetime import datetime

class EventBroadcaster:
    """Manages WebSocket connections and event broadcasting"""

    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        """Accept new WebSocket connection"""
        await websocket.accept()
        self.active_connections.append(websocket)

        # Send initial state (optional)
        await self.send_initial_state(websocket)

    def disconnect(self, websocket: WebSocket):
        """Remove WebSocket connection"""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast_event(self, event: dict):
        """Broadcast event to all connected clients"""
        message = json.dumps(event)
        disconnected = []

        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                disconnected.append(connection)

        # Clean up disconnected clients
        for conn in disconnected:
            self.disconnect(conn)

    async def send_initial_state(self, websocket: WebSocket):
        """Send current state snapshot to newly connected client"""
        state = {
            "event_type": "state.snapshot",
            "timestamp": datetime.now().isoformat(),
            "data": {
                "active_sessions": await get_active_session_count(),
                "system_status": "healthy"
            }
        }
        await websocket.send_text(json.dumps(state))


# Global broadcaster instance
broadcaster = EventBroadcaster()


@app.websocket("/ws/events")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(...)  # JWT token for auth
):
    """
    WebSocket endpoint for real-time event streaming

    Query params:
        token: JWT authentication token

    Events emitted:
        - session.created
        - session.destroyed
        - session.updated
        - system.error
        - heartbeat
    """
    # Authenticate
    user = await authenticate_token(token)
    if not user:
        await websocket.close(code=1008, reason="Unauthorized")
        return

    # Connect
    await broadcaster.connect(websocket)

    try:
        while True:
            # Receive messages (ping/pong, commands)
            data = await websocket.receive_text()

            if data == "ping":
                await websocket.send_text("pong")

    except WebSocketDisconnect:
        broadcaster.disconnect(websocket)


# Hook into session manager to broadcast events
class SessionManager:
    def __init__(self):
        self.broadcaster = broadcaster

    async def create_session(self, user_id: str) -> Session:
        """Create session and broadcast event"""
        session = await self._create_session_internal(user_id)

        # Broadcast event
        event = {
            "event_type": "session.created",
            "timestamp": datetime.now().isoformat(),
            "data": {
                "session_id": session.id,
                "user_id": user_id,
                "created_at": session.created_at.isoformat()
            }
        }
        await self.broadcaster.broadcast_event(event)

        return session

    async def delete_session(self, session_id: str):
        """Delete session and broadcast event"""
        await self._delete_session_internal(session_id)

        # Broadcast event
        event = {
            "event_type": "session.destroyed",
            "timestamp": datetime.now().isoformat(),
            "data": {
                "session_id": session_id,
                "destroyed_at": datetime.now().isoformat(),
                "reason": "explicit_delete"
            }
        }
        await self.broadcaster.broadcast_event(event)
```

### Error Handling

#### Client-Side Reconnection

The dashboard will handle automatic reconnection, but KATO should:
- Accept multiple connections from same client
- Deduplicate events if needed
- Maintain event history buffer (optional, 60s)

#### Server-Side Connection Limits

Recommend limits:
- Max 100 concurrent WebSocket connections
- Max 1000 events queued per connection
- Disconnect idle clients after 5 minutes of no pings

### Security Considerations

1. **Authentication:** Require JWT token in query param or header
2. **Authorization:** Only allow authenticated users to connect
3. **Rate Limiting:** Max 1 connection per user (or reasonable limit)
4. **Input Validation:** Validate all incoming messages
5. **DoS Protection:** Limit message size and frequency

---

## Option 2: HTTP Webhook Callbacks

### Overview

KATO calls back to dashboard via HTTP POST when events occur.

### Architecture

```
┌─────────────────┐                    ┌─────────────────┐
│  KATO Dashboard │◄───HTTP POST───────│  KATO Service   │
│   (Webhook      │                    │                 │
│    Receiver)    │                    │                 │
└─────────────────┘                    └─────────────────┘
                                              │
                                              ├──► Session Event ──► POST /webhook
                                              └──► Error Event   ──► POST /webhook
```

### Configuration

Dashboard registers webhook URL with KATO:

```http
POST /webhooks/register
Authorization: Bearer <token>

{
  "url": "http://dashboard:8080/api/v1/webhooks/kato-events",
  "events": ["session.created", "session.destroyed", "system.error"],
  "secret": "webhook_secret_key"
}
```

### Webhook Payload

```http
POST http://dashboard:8080/api/v1/webhooks/kato-events
Content-Type: application/json
X-KATO-Signature: sha256=<hmac_signature>

{
  "event_id": "evt_abc123",
  "event_type": "session.created",
  "timestamp": "2025-10-11T15:30:45.123Z",
  "data": {
    "session_id": "sess_abc123",
    "user_id": "user_xyz789"
  }
}
```

### Advantages

- ✅ Simpler than WebSocket
- ✅ Works through firewalls
- ✅ Easy to debug (HTTP logs)
- ✅ Stateless (no connection management)

### Disadvantages

- ❌ Dashboard must expose HTTP endpoint
- ❌ Requires webhook registration/management
- ❌ Higher latency than WebSocket
- ❌ More complex error handling (retry logic)

---

## Option 3: Enhanced HTTP API (FALLBACK)

### Overview

Enhance existing HTTP endpoints to make polling more efficient.

### Changes to Existing Endpoints

#### 1. Add `If-Modified-Since` Support

```http
GET /sessions/count
If-Modified-Since: Wed, 11 Oct 2025 15:30:00 GMT

# Response if not modified
304 Not Modified

# Response if modified
200 OK
{
  "active_sessions": 127,
  "total_sessions": 5432,
  "last_modified": "2025-10-11T15:35:00.000Z"
}
```

#### 2. Add Event Log Endpoint

```http
GET /events?since=2025-10-11T15:30:00.000Z&types=session.created,session.destroyed

{
  "events": [
    {
      "event_id": "evt_abc123",
      "event_type": "session.created",
      "timestamp": "2025-10-11T15:32:45.123Z",
      "data": {
        "session_id": "sess_abc123"
      }
    }
  ],
  "cursor": "2025-10-11T15:35:00.000Z"
}
```

Dashboard polls `/events` endpoint and tracks cursor.

#### 3. Add Long Polling Support

```http
GET /sessions/count/subscribe?timeout=30

# Blocks for up to 30s until count changes, then returns
{
  "active_sessions": 128,
  "changed": true
}
```

### Advantages

- ✅ Minimal changes to KATO
- ✅ No new protocols (just HTTP)
- ✅ Backwards compatible
- ✅ Easy to implement

### Disadvantages

- ❌ Still polling (just more efficient)
- ❌ Higher latency than WebSocket
- ❌ More complex client logic
- ❌ Limited to HTTP request/response model

---

## Implementation Phases

### Phase 0: Planning (Week 1)
**KATO Team:**
- [ ] Review requirements document
- [ ] Choose implementation option (1, 2, or 3)
- [ ] Identify integration points in codebase
- [ ] Assign developers

**Dashboard Team:**
- [ ] Prepare WebSocket client implementation
- [ ] Design event handling architecture
- [ ] Set up development environment

### Phase 1: Core Event Infrastructure (Week 2-3)
**KATO Team:**
- [ ] Implement event broadcasting system
- [ ] Add WebSocket endpoint (Option 1) OR
- [ ] Add webhook support (Option 2) OR
- [ ] Enhance HTTP endpoints (Option 3)
- [ ] Unit tests for event system

**Dashboard Team:**
- [ ] Implement event receiver
- [ ] Test with mock events
- [ ] Update UI components

### Phase 2: Session Events (Week 4)
**KATO Team:**
- [ ] Hook session creation to event system
- [ ] Hook session deletion to event system
- [ ] Add session update events (optional)
- [ ] Integration tests

**Dashboard Team:**
- [ ] Integrate session events into Sessions page
- [ ] Update session count displays
- [ ] End-to-end testing

### Phase 3: Error Events (Week 5)
**KATO Team:**
- [ ] Hook error handling to event system
- [ ] Define error event types
- [ ] Configure error thresholds
- [ ] Testing and validation

**Dashboard Team:**
- [ ] Implement alert notification UI
- [ ] Add error event handling
- [ ] User acceptance testing

### Phase 4: Production Rollout (Week 6)
**Both Teams:**
- [ ] Deploy to staging
- [ ] Load testing
- [ ] Performance validation
- [ ] Deploy to production (gradual rollout)
- [ ] Monitor and optimize

---

## Message Format Specifications

### Standard Event Envelope

All events follow this structure:

```typescript
interface KATOEvent {
  event_id?: string              // Optional: Unique event ID for deduplication
  event_type: string             // Required: Event type (dot notation)
  timestamp: string              // Required: ISO-8601 timestamp
  data: Record<string, any>      // Required: Event-specific payload
  metadata?: Record<string, any> // Optional: Additional context
}
```

### Event Type Naming Convention

Use dot notation: `<category>.<action>`

**Categories:**
- `session.*` - Session lifecycle events
- `system.*` - System-level events
- `error.*` - Error events (deprecated, use system.error)
- `metrics.*` - Metrics updates
- `state.*` - State snapshots

**Actions:**
- `created` - Resource created
- `updated` - Resource modified
- `destroyed` - Resource deleted
- `error` - Error occurred
- `snapshot` - Current state

**Examples:**
- `session.created`
- `session.updated`
- `session.destroyed`
- `system.error`
- `metrics.update`
- `state.snapshot`

### Timestamp Format

Always use ISO-8601 format with timezone:

```
2025-10-11T15:30:45.123Z
```

### Data Payload Guidelines

1. **Keep payloads small** (< 1KB if possible)
2. **Include only essential data** (IDs, not full objects)
3. **Use consistent field names** (snake_case)
4. **Provide context** (user_id, session_id, etc.)
5. **Include links** to full resource if needed

**Good Example:**
```json
{
  "event_type": "session.created",
  "data": {
    "session_id": "sess_abc123",
    "user_id": "user_xyz789",
    "url": "/sessions/sess_abc123"
  }
}
```

**Bad Example (too much data):**
```json
{
  "event_type": "session.created",
  "data": {
    "session": {
      "id": "sess_abc123",
      "short_term_memory": [...], // Large array
      "patterns": [...],          // Another large array
      // ... many more fields
    }
  }
}
```

---

## Testing Requirements

### Unit Tests

**KATO Side:**
```python
def test_broadcast_session_created_event():
    """Test that session creation triggers event broadcast"""
    manager = SessionManager()
    session = await manager.create_session("user_123")

    # Assert event was broadcast
    assert last_broadcast_event["event_type"] == "session.created"
    assert last_broadcast_event["data"]["session_id"] == session.id
```

### Integration Tests

**Full Flow Test:**
```python
async def test_websocket_event_flow():
    """Test end-to-end WebSocket event flow"""
    # Connect to WebSocket
    async with websockets.connect("ws://kato:8000/ws/events") as ws:
        # Create session via HTTP
        session = requests.post("http://kato:8000/sessions", ...)

        # Receive event via WebSocket
        message = await ws.recv()
        event = json.loads(message)

        assert event["event_type"] == "session.created"
        assert event["data"]["session_id"] == session["id"]
```

### Load Tests

**Requirements:**
- Support 100 concurrent WebSocket connections
- Handle 1000 events/second broadcast
- Latency < 100ms for event delivery
- No memory leaks over 24h operation

---

## Backwards Compatibility

### Versioning Strategy

**Option A: Separate Endpoints**
- Old: `GET /metrics` (HTTP only)
- New: `ws://kato:8000/ws/events` (WebSocket events)
- Both supported simultaneously

**Option B: API Version Parameter**
```
ws://kato:8000/ws/events?version=v2
```

### Deprecation Timeline

If replacing existing APIs:
1. **Month 1-3:** Both old and new APIs supported
2. **Month 4-6:** Old API marked deprecated (warnings in logs)
3. **Month 7+:** Old API removed (breaking change)

### Feature Detection

Dashboard should detect if WebSocket events are available:

```python
# Health check endpoint
GET /health

{
  "status": "healthy",
  "features": {
    "websocket_events": true,
    "webhook_callbacks": false,
    "long_polling": false
  }
}
```

---

## Security Considerations

### Authentication

**WebSocket:**
```
ws://kato:8000/ws/events?token=<jwt_token>
```

**Webhook:**
```
X-KATO-Signature: sha256=<hmac_signature>
```

### Authorization

- Only allow authenticated clients to connect
- Scope events by user permissions (if multi-tenant)
- Don't send events about resources user can't access

### Rate Limiting

- Max 1-5 WebSocket connections per user
- Max 100 events/second per connection
- Disconnect abusive clients

### Data Privacy

- Don't include sensitive data in events
- Provide links to full resources instead
- Audit log WebSocket connections

---

## FAQ

### Q: Is WebSocket required, or can we use HTTP only?

**A:** WebSocket is **recommended** but not strictly required. Dashboard can work with current HTTP API + polling. However, WebSocket provides:
- 10x better latency (50ms vs 500ms)
- 50% less server load
- Better user experience

If WebSocket is too complex, consider Option 2 (Webhooks) or Option 3 (Enhanced HTTP).

### Q: How many concurrent WebSocket connections should we support?

**A:** For typical deployments:
- **Small:** 10-50 connections (enough for dashboard instances)
- **Medium:** 50-100 connections (multiple dashboards + monitoring tools)
- **Large:** 100+ connections (if exposing to many clients)

Start with 100 max connections. Monitor and adjust.

### Q: What happens if client misses events (disconnected)?

**A:** Three approaches:

1. **Event History Buffer** (recommended)
   - Keep last 100 events in memory
   - Client requests missed events on reconnect

2. **State Snapshot**
   - Send full state on reconnect
   - Client reconciles with local state

3. **HTTP Fallback**
   - Client polls HTTP API to catch up
   - Resumes WebSocket when current

### Q: How do we test WebSocket events in development?

**A:** Use a WebSocket testing tool:

```bash
# wscat
wscat -c "ws://localhost:8000/ws/events?token=test_token"

# or websocat
websocat "ws://localhost:8000/ws/events?token=test_token"
```

Or write a simple Python test client:

```python
import asyncio
import websockets

async def test_events():
    uri = "ws://localhost:8000/ws/events?token=test_token"
    async with websockets.connect(uri) as ws:
        while True:
            message = await ws.recv()
            print(f"Received: {message}")

asyncio.run(test_events())
```

### Q: What if KATO is behind a load balancer?

**A:** For WebSocket to work through load balancer:

1. **Enable sticky sessions** (session affinity)
2. **Use L7 load balancing** (not L4)
3. **Configure WebSocket timeout** (5+ minutes)
4. **Enable health checks** for WebSocket endpoints

OR use Redis pub/sub for event distribution:
```python
# All KATO instances publish to Redis
# Dashboard subscribes to Redis channel
redis.publish("kato:events", event)
```

### Q: How do we monitor WebSocket performance?

**A:** Track these metrics:

- Active connection count
- Events broadcast per second
- Average broadcast latency
- Connection errors/disconnections
- Memory usage per connection

Add to existing monitoring (Prometheus, Grafana, etc.):

```python
# Metrics
websocket_connections = Gauge('websocket_connections', 'Active connections')
websocket_events_sent = Counter('websocket_events_sent', 'Events broadcast')
websocket_latency = Histogram('websocket_latency_seconds', 'Broadcast latency')
```

---

## References

### WebSocket Resources

- [RFC 6455: The WebSocket Protocol](https://tools.ietf.org/html/rfc6455)
- [FastAPI WebSocket Documentation](https://fastapi.tiangolo.com/advanced/websockets/)
- [WebSocket Security Best Practices](https://owasp.org/www-community/attacks/Websocket_Security)

### Similar Implementations

- [Stripe Webhooks](https://stripe.com/docs/webhooks)
- [GitHub Webhooks](https://docs.github.com/en/developers/webhooks-and-events/webhooks/about-webhooks)
- [Discord Gateway (WebSocket)](https://discord.com/developers/docs/topics/gateway)

---

## Appendix A: Quick Start Guide for KATO Developers

### Minimal WebSocket Implementation (30 minutes)

```python
# 1. Install dependencies
# pip install fastapi websockets

# 2. Add WebSocket endpoint
from fastapi import WebSocket
from typing import List
import json

class Broadcaster:
    def __init__(self):
        self.connections: List[WebSocket] = []

    async def broadcast(self, event: dict):
        for ws in self.connections:
            await ws.send_text(json.dumps(event))

broadcaster = Broadcaster()

@app.websocket("/ws/events")
async def events_endpoint(websocket: WebSocket):
    await websocket.accept()
    broadcaster.connections.append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except:
        broadcaster.connections.remove(websocket)

# 3. Broadcast events from your code
async def create_session(...):
    session = ...  # your logic
    await broadcaster.broadcast({
        "event_type": "session.created",
        "data": {"session_id": session.id}
    })
    return session
```

That's it! Dashboard can now receive real-time events.

---

## Appendix B: Dashboard Integration Example

```typescript
// Dashboard connects to KATO WebSocket
const ws = new WebSocket('ws://kato:8000/ws/events?token=jwt_token')

ws.onmessage = (event) => {
  const katoEvent = JSON.parse(event.data)

  switch (katoEvent.event_type) {
    case 'session.created':
      console.log('New session:', katoEvent.data.session_id)
      updateSessionCount(+1)
      break

    case 'session.destroyed':
      console.log('Session ended:', katoEvent.data.session_id)
      updateSessionCount(-1)
      break

    case 'system.error':
      showAlert(katoEvent.data.message)
      break
  }
}
```

---

## Contact & Support

**Questions about this document?**
- Dashboard Team Lead: [contact info]
- KATO Architecture Team: [contact info]

**Feedback?**
- File an issue in kato-dashboard repo
- Join #kato-dashboard Slack channel

---

**Document Status:** Ready for Review
**Review Date:** 2025-10-11
**Next Steps:** KATO team review and choose implementation option
