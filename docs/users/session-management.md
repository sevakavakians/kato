# Session Management Guide

Complete guide to managing KATO sessions, understanding session lifecycle, and data persistence.

## Session Fundamentals

### What is a Session?

A **session** is a temporary workspace that contains:
- **Short-term memory (STM)**: Current sequence of observations
- **Emotive state**: Rolling window of emotional values
- **Configuration**: Session-specific settings
- **Context**: Metadata and runtime state

### What is a Node?

A **node_id** is a permanent identifier that links to:
- **Long-term memory (LTM)**: Learned patterns in persistent storage
- **Vector embeddings**: Stored in vector database
- **Pattern metadata**: Training history, statistics

### Session vs Node Comparison

| Aspect | Session (session_id) | Node (node_id) |
|--------|---------------------|---------------|
| **Lifetime** | Temporary (hours) | Permanent |
| **Storage** | Redis (volatile) | Persistent database (patterns & vectors) |
| **Contains** | STM, emotives, config | Patterns, vectors, LTM |
| **Unique** | Per connection | Shared across sessions |
| **Expires** | Yes (configurable TTL) | Never (until deleted) |
| **Use Case** | Active conversation | Knowledge base |

## Creating Sessions

### Basic Session Creation

```bash
curl -X POST http://localhost:8000/sessions \
  -H "Content-Type: application/json" \
  -d '{
    "node_id": "my_application"
  }'
```

**Response**:
```json
{
  "session_id": "session-abc123def456",
  "node_id": "my_application",
  "created_at": "2025-11-13T10:00:00Z",
  "ttl": 3600,
  "config": {
    "recall_threshold": 0.1,
    "max_predictions": 100,
    "sort_symbols": true
  }
}
```

### Session with Configuration

```bash
curl -X POST http://localhost:8000/sessions \
  -H "Content-Type: application/json" \
  -d '{
    "node_id": "chatbot_v2",
    "config": {
      "recall_threshold": 0.3,
      "max_predictions": 50,
      "use_token_matching": true
    },
    "ttl": 7200
  }'
```

### Python Example

```python
kato = KATOClient()
session_id = kato.create_session(
    node_id="my_app",
    config={"recall_threshold": 0.3},
    ttl=7200  # 2 hours
)
```

## Session Lifecycle

### Lifecycle States

```
Created → Active → Extended → Expired → Deleted
   ↓        ↓         ↓
  TTL    Activity   Auto-extend
```

### 1. Created

Session is created with initial TTL (default: 3600 seconds).

```bash
# Create session
POST /sessions
Response: {
  "session_id": "...",
  "created_at": "2025-11-13T10:00:00Z",
  "ttl": 3600
}
```

### 2. Active

Session accepts operations while TTL > 0.

```bash
# Operations reset TTL if auto-extend enabled
POST /sessions/{session_id}/observe
GET  /sessions/{session_id}/predictions
```

### 3. Extended (Auto-Extend Enabled)

Each operation resets TTL to original value.

**Global Configuration**:
```bash
# .env
SESSION_AUTO_EXTEND=true  # Default
```

**Behavior**:
- User sends observation at 10:00 AM (TTL = 3600s)
- Session expires at 11:00 AM
- User sends observation at 10:30 AM
- **TTL resets**: Session now expires at 11:30 AM

### 4. Expired

Session becomes inaccessible after TTL elapses.

**Symptoms**:
- API returns 404: "Session not found"
- Need to create new session

**Data Loss**:
- ✅ **Patterns (LTM)**: Preserved in persistent storage
- ✅ **Vectors**: Preserved in vector database
- ❌ **STM**: Lost (not stored in LTM until learned)
- ❌ **Current emotives**: Lost
- ❌ **Session config**: Lost (revert to defaults)

### 5. Deleted

Session explicitly deleted via API.

```bash
DELETE /sessions/{session_id}
```

**Effect**: Same as expiry - only session state lost.

## Session TTL Management

### Configuring TTL

**Global Default** (.env):
```bash
SESSION_TTL=3600  # 1 hour
```

**Per-Session** (API):
```bash
curl -X POST http://localhost:8000/sessions \
  -d '{
    "node_id": "my_app",
    "ttl": 7200
  }'
```

### Auto-Extend Behavior

**Enabled (Default)**:
```bash
# .env
SESSION_AUTO_EXTEND=true

# Every API call resets TTL
10:00 - Create session (expires 11:00)
10:30 - Observe (expires 11:30) ← TTL reset
10:45 - Predictions (expires 11:45) ← TTL reset
```

**Disabled**:
```bash
# .env
SESSION_AUTO_EXTEND=false

# TTL is absolute from creation
10:00 - Create session (expires 11:00)
10:30 - Observe (still expires 11:00) ← No change
10:45 - Predictions (still expires 11:00) ← No change
```

### Checking Session Status

```bash
# Get session info including TTL
curl http://localhost:8000/sessions/{session_id}
```

**Response**:
```json
{
  "session_id": "session-abc123",
  "node_id": "my_app",
  "created_at": "2025-11-13T10:00:00Z",
  "last_accessed": "2025-11-13T10:30:00Z",
  "ttl": 3600,
  "remaining_ttl": 1800,
  "auto_extend": true,
  "config": {...}
}
```

## Handling Session Expiry

### Detecting Expiry

```python
try:
    kato.observe(["hello"])
except KATOSessionError as e:
    if "not found" in str(e):
        # Session expired
        kato.reconnect()
```

### Auto-Reconnect Pattern

```python
class ResilientKATOClient(KATOClient):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.last_node_id = None

    def create_session(self, node_id, **kwargs):
        self.last_node_id = node_id
        return super().create_session(node_id, **kwargs)

    def _auto_reconnect(self, func, *args, **kwargs):
        """Wrapper that auto-reconnects on session expiry."""
        try:
            return func(*args, **kwargs)
        except KATOSessionError:
            if self.last_node_id:
                print(f"Session expired - reconnecting to {self.last_node_id}")
                self.create_session(self.last_node_id)
                return func(*args, **kwargs)
            raise

    def observe(self, *args, **kwargs):
        return self._auto_reconnect(super().observe, *args, **kwargs)

# Usage
kato = ResilientKATOClient()
kato.create_session("my_app")

# Works even if session expires mid-operation
kato.observe(["test"])  # May auto-reconnect transparently
```

## Node Management

### Understanding node_id

The `node_id` determines which database namespace is used:

```
node_id: "chatbot_production"
↓
Database namespace: "node_chatbot_production_kato"
↓
Stored data:
  - patterns
  - pattern_metadata
  - global_metadata
```

### Multi-Tenant Isolation

Each `node_id` gets isolated database:

```python
# User 1's session
kato1 = KATOClient()
kato1.create_session("user_alice")  # DB: node_user_alice_kato

# User 2's session
kato2 = KATOClient()
kato2.create_session("user_bob")    # DB: node_user_bob_kato

# Completely isolated - no cross-contamination
```

### Node Naming Conventions

**Recommended Patterns**:
- **Per-User**: `user_{user_id}` (e.g., `user_12345`)
- **Per-App**: `app_{app_name}` (e.g., `app_chatbot`)
- **Per-Environment**: `{env}_{app}` (e.g., `prod_chatbot`)
- **Per-Tenant**: `tenant_{org_id}_{app}` (e.g., `tenant_acme_bot`)

**Avoid**:
- Special characters (use `_` not `-`)
- Very long names (database name limits)
- Spaces or unicode

### Listing Nodes

Node listing requires direct database access or monitoring tools. See deployment documentation for database inspection procedures.

## Multiple Sessions Same Node

You can have multiple active sessions sharing the same `node_id`:

```python
# Session 1
kato1 = KATOClient()
kato1.create_session("shared_knowledge")
kato1.observe(["event_a"])

# Session 2 (different connection, same node)
kato2 = KATOClient()
kato2.create_session("shared_knowledge")
kato2.observe(["event_b"])

# Both sessions:
# - Share LTM patterns in persistent storage
# - Have independent STM
# - Have independent emotives
# - Can have different configurations
```

### Use Cases

1. **Multi-User Application**: All users share learned patterns
2. **Distributed Workers**: Each worker has session, shares knowledge
3. **Development + Production**: Separate sessions, shared training
4. **A/B Testing**: Different configs, same patterns

### Isolation Guarantees

**Shared Across Sessions (same node_id)**:
- ✅ Learned patterns (LTM)
- ✅ Vector embeddings
- ✅ Pattern statistics

**Isolated Per Session**:
- ❌ Short-term memory (STM)
- ❌ Current emotive state
- ❌ Session configuration
- ❌ Metadata (until learned into pattern)

## Session Configuration Management

### Updating Configuration

```bash
# Update configuration mid-session
curl -X PUT http://localhost:8000/sessions/{session_id}/config \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "recall_threshold": 0.5,
      "max_predictions": 200
    }
  }'
```

### Configuration Persistence

Session configuration is **not persistent**:
- Lost when session expires
- Not stored in database
- Must be re-specified when creating new session

**Workaround**:
```python
# Store preferred config in your application
APP_CONFIG = {
    "recall_threshold": 0.3,
    "max_predictions": 50
}

# Reuse for all sessions
kato.create_session("my_app", config=APP_CONFIG)
```

## Session Cleanup

### Manual Deletion

```bash
# Delete specific session
curl -X DELETE http://localhost:8000/sessions/{session_id}
```

### Automatic Cleanup

Redis automatically removes expired sessions based on TTL.

**No manual cleanup needed** for expired sessions.

### Deleting Node Data

To completely remove a node's patterns, contact your system administrator or see deployment documentation for data deletion procedures.

**WARNING**: Deleting node data permanently removes all learned patterns!

## Best Practices

### Session Management

1. **Use meaningful node_ids** that reflect isolation boundaries
2. **Set appropriate TTLs** based on usage patterns:
   - Interactive apps: 1-2 hours
   - Background workers: 8-24 hours
3. **Enable auto-extend** for interactive applications
4. **Implement reconnect logic** for long-running applications
5. **Store node_id** in your application state

### Configuration Management

1. **Define default configs** in your application
2. **Don't rely on session config persistence**
3. **Document config requirements** for your use case
4. **Test with different thresholds** to find optimal values

### Multi-Tenancy

1. **One node_id per tenant** for isolation
2. **Prefix node_ids** with tenant identifier
3. **Monitor database sizes** per node
4. **Implement node cleanup** for deleted tenants

### Error Handling

1. **Always handle session expiry** gracefully
2. **Implement automatic reconnection** for resilience
3. **Log session lifecycle events** for debugging
4. **Monitor session creation rate** for anomalies

## Monitoring and Debugging

### Check Active Sessions

```bash
# Redis CLI
docker exec redis-kb-$USER-1 redis-cli KEYS "session:*"
```

### Session Metrics

```bash
# Count active sessions
docker exec redis-kb-$USER-1 redis-cli DBSIZE

# Get session data
docker exec redis-kb-$USER-1 redis-cli GET "session:{session_id}"
```

### Debug Session Issues

```python
# Get full session details
info = kato.get_session_info()
print(f"Session: {info['session_id']}")
print(f"Node: {info['node_id']}")
print(f"Remaining TTL: {info['remaining_ttl']}s")
print(f"Config: {info['config']}")
print(f"STM length: {kato.get_stm()['length']}")
```

## Related Documentation

- [First Session Tutorial](first-session.md)
- [Configuration Guide](configuration.md)
- [Database Persistence](database-persistence.md)
- [API Reference](../reference/api/)

---

**Last Updated**: November 2025
**KATO Version**: 3.0+
