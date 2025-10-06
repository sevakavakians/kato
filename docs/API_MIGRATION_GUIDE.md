# KATO API Migration Guide: Direct to Session-Based Endpoints

**🗂️ HISTORICAL DOCUMENT - MIGRATION COMPLETE**

As of Phase 3 (2025-10-06), all deprecated direct endpoints have been **permanently removed**.
This document is kept for historical reference and to help understand the migration path that was provided.

---

## Overview

KATO has completed the migration from direct (header-based) API endpoints to session-based endpoints.
All core operations now **require** session-based endpoints.

## Why Migrate?

Session-based endpoints provide:
- ✅ **Better state persistence** with Redis backing
- ✅ **Explicit session locking** for thread safety and concurrency
- ✅ **Proper TTL and lifecycle management**
- ✅ **Stronger multi-user isolation guarantees**
- ✅ **State survives processor cache evictions**

Direct endpoints (now deprecated):
- ❌ No session persistence layer
- ❌ No explicit locking mechanisms
- ❌ State can be lost on processor eviction
- ❌ Less robust for multi-user scenarios

## Migration Timeline

- **Phase 1** (✅ Complete - 2025-10-06): Deprecation warnings added, both APIs functional
- **Phase 2** (✅ Complete - 2025-10-06): Auto-session middleware for transparent backward compatibility
- **Phase 3** (✅ **COMPLETE - 2025-10-06**): **Direct endpoints removed entirely**

## ⚠️ Breaking Changes (Phase 3)

The following endpoints have been **permanently removed** and will return `404 Not Found`:

- `POST /observe` ❌
- `GET /stm` ❌
- `GET /short-term-memory` ❌
- `POST /learn` ❌
- `POST /clear-stm` ❌
- `POST /clear-short-term-memory` ❌
- `POST /clear-all` ❌
- `POST /clear-all-memory` ❌
- `GET /predictions` ❌
- `POST /predictions` ❌
- `POST /observe-sequence` ❌

**All code must now use session-based endpoints.**

## Phase 2: Automatic Migration (No Code Changes Required!)

**Good News**: As of Phase 2, your existing code will continue to work without any changes!

The Auto-Session Middleware automatically:
- ✅ Intercepts calls to deprecated endpoints
- ✅ Creates sessions transparently in the background
- ✅ Maps your `processor_id` to a persistent session
- ✅ Maintains state across requests
- ✅ Provides all the benefits of session-based endpoints

### How It Works

When you call a deprecated endpoint like:
```python
client.observe(strings=["hello"], processor_id="my_processor")
```

The middleware automatically:
1. Checks if a session exists for `processor_id="my_processor"`
2. Creates a new session if needed (or reuses existing one)
3. Rewrites the request to use the session-based endpoint
4. Returns the response with backward-compatible format

**Your code works unchanged, but gains session benefits!**

### Monitoring Auto-Migration

Check if your app is using auto-migration:
```bash
# View metrics to see deprecated endpoint usage
curl http://localhost:8000/metrics | grep deprecated

# Look for these metrics:
# - kato_deprecated_endpoint_calls_total: How many deprecated calls
# - kato_auto_session_created_total: How many auto-sessions created
```

Response headers also indicate auto-migration:
```python
response = client.observe(strings=["test"], processor_id="my_processor")
# Check response headers:
# - X-Auto-Session-Used: true
# - X-Session-ID: session-abc123...
```

### Migration Recommendation

While Phase 2 provides automatic compatibility, we **strongly recommend** migrating to session-based endpoints explicitly for:
- Better control over session lifecycle
- Explicit configuration management
- Future-proof code (Phase 3 will remove deprecated endpoints)

## Quick Migration Reference

### Observation

**OLD (Deprecated):**
```python
from sample_kato_client import KATOClient

client = KATOClient(base_url="http://localhost:8000")

# Direct endpoint with processor_id
result = client.observe(
    strings=["hello", "world"],
    processor_id="my_processor"
)
```

**NEW (Recommended):**
```python
from sample_kato_client import KATOClient

client = KATOClient(base_url="http://localhost:8000")

# 1. Create a session first
session = client.create_session(
    node_id="user123",
    config={
        "max_pattern_length": 5,
        "recall_threshold": 0.5
    }
)
session_id = session['session_id']

# 2. Use session-based observation
result = client.observe_in_session(
    session_id=session_id,
    strings=["hello", "world"]
)
```

### Getting Short-Term Memory

**OLD (Deprecated):**
```python
stm_data = client.get_stm(processor_id="my_processor")
print(stm_data['stm'])
```

**NEW (Recommended):**
```python
stm_data = client.get_session_stm(session_id=session_id)
print(stm_data['stm'])
```

### Learning Patterns

**OLD (Deprecated):**
```python
result = client.learn(processor_id="my_processor")
pattern_name = result['pattern_name']
```

**NEW (Recommended):**
```python
result = client.learn_in_session(session_id=session_id)
pattern_name = result['pattern_name']
```

### Getting Predictions

**OLD (Deprecated):**
```python
predictions = client.get_predictions(processor_id="my_processor")
for pred in predictions['predictions']:
    print(pred['future'])
```

**NEW (Recommended):**
```python
predictions = client.get_session_predictions(session_id=session_id)
for pred in predictions['predictions']:
    print(pred['future'])
```

### Clearing STM

**OLD (Deprecated):**
```python
client.clear_stm(processor_id="my_processor")
```

**NEW (Recommended):**
```python
client.clear_session_stm(session_id=session_id)
```

### Bulk Observation Sequence

**OLD (Deprecated):**
```python
result = client.observe_sequence(
    observations=[
        {'strings': ['A', 'B']},
        {'strings': ['C', 'D']}
    ],
    learn_at_end=True,
    processor_id="my_processor"
)
```

**NEW (Recommended):**
```python
result = client.observe_sequence_in_session(
    session_id=session_id,
    observations=[
        {'strings': ['A', 'B']},
        {'strings': ['C', 'D']}
    ],
    learn_at_end=True
)
```

## Complete Example Migration

### Before (Direct Endpoints - Deprecated)

```python
from sample_kato_client import KATOClient

client = KATOClient()
processor_id = "my_app_processor"

# Configure processor
client.update_genes(
    {"max_pattern_length": 5, "recall_threshold": 0.5},
    processor_id=processor_id
)

# Observe data
client.observe(strings=["A", "B"], processor_id=processor_id)
client.observe(strings=["C", "D"], processor_id=processor_id)

# Learn pattern
pattern = client.learn(processor_id=processor_id)

# Clear and observe again
client.clear_stm(processor_id=processor_id)
client.observe(strings=["A", "B"], processor_id=processor_id)

# Get predictions
predictions = client.get_predictions(processor_id=processor_id)
```

### After (Session-Based - Recommended)

```python
from sample_kato_client import KATOClient

client = KATOClient()

# Create session with configuration
session = client.create_session(
    node_id="user_alice",
    config={
        "max_pattern_length": 5,
        "recall_threshold": 0.5
    }
)
session_id = session['session_id']

# Observe data
client.observe_in_session(session_id, strings=["A", "B"])
client.observe_in_session(session_id, strings=["C", "D"])

# Learn pattern
pattern = client.learn_in_session(session_id)

# Clear and observe again
client.clear_session_stm(session_id)
client.observe_in_session(session_id, strings=["A", "B"])

# Get predictions
predictions = client.get_session_predictions(session_id)

# Clean up when done (optional - sessions auto-expire)
client.delete_session(session_id)
```

## Session Management Best Practices

### 1. Session Lifecycle

```python
# Create session at user login or application start
session = client.create_session(
    node_id=f"user_{user_id}",
    ttl_seconds=3600  # 1 hour
)

# Store session_id for subsequent requests
user_session_id = session['session_id']

# Extend session if needed
client.extend_session(user_session_id, ttl_seconds=3600)

# Delete session on logout or cleanup
client.delete_session(user_session_id)
```

### 2. Configuration Updates

```python
# Update session configuration at any time
client.update_session_config(
    session_id,
    config={
        "recall_threshold": 0.7,
        "max_pattern_length": 10
    }
)
```

### 3. Multi-User Applications

```python
# Each user gets their own session
alice_session = client.create_session(node_id="alice")
bob_session = client.create_session(node_id="bob")

# Complete isolation between users
client.observe_in_session(alice_session['session_id'], strings=["A"])
client.observe_in_session(bob_session['session_id'], strings=["B"])

# Alice and Bob have separate STM, patterns, and predictions
alice_stm = client.get_session_stm(alice_session['session_id'])
bob_stm = client.get_session_stm(bob_session['session_id'])
```

## API Endpoint Mapping

| Old Endpoint (Deprecated) | New Endpoint (Recommended) |
|---------------------------|----------------------------|
| `POST /observe` | `POST /sessions/{session_id}/observe` |
| `GET /stm` | `GET /sessions/{session_id}/stm` |
| `GET /short-term-memory` | `GET /sessions/{session_id}/stm` |
| `POST /learn` | `POST /sessions/{session_id}/learn` |
| `POST /clear-stm` | `POST /sessions/{session_id}/clear-stm` |
| `GET /predictions` | `GET /sessions/{session_id}/predictions` |
| `POST /predictions` | `GET /sessions/{session_id}/predictions` |
| `POST /observe-sequence` | `POST /sessions/{session_id}/observe-sequence` |
| `POST /genes/update` | `POST /sessions/{session_id}/config` |

## REST API Examples

### Direct Endpoint (Deprecated)

```bash
# Deprecated approach with processor_id
curl -X POST http://localhost:8000/observe \
  -H "Content-Type: application/json" \
  -d '{
    "strings": ["hello", "world"],
    "vectors": [],
    "emotives": {}
  }' \
  -G --data-urlencode "processor_id=my_processor"
```

### Session-Based Endpoint (Recommended)

```bash
# 1. Create session
SESSION_RESPONSE=$(curl -X POST http://localhost:8000/sessions \
  -H "Content-Type: application/json" \
  -d '{
    "node_id": "user123",
    "ttl_seconds": 3600
  }')

SESSION_ID=$(echo $SESSION_RESPONSE | jq -r '.session_id')

# 2. Use session for observation
curl -X POST http://localhost:8000/sessions/$SESSION_ID/observe \
  -H "Content-Type: application/json" \
  -d '{
    "strings": ["hello", "world"],
    "vectors": [],
    "emotives": {}
  }'
```

## Common Migration Patterns

### Pattern 1: Single User Application

```python
# Initialize once at startup
session = client.create_session(
    node_id="single_user_app",
    config={"max_pattern_length": 5}
)

# Store globally or in app state
app.kato_session_id = session['session_id']

# Use throughout application
def process_observation(data):
    return client.observe_in_session(
        app.kato_session_id,
        strings=data
    )
```

### Pattern 2: Web API with User Sessions

```python
from flask import Flask, session

app = Flask(__name__)

@app.route('/api/observe', methods=['POST'])
def observe():
    # Get or create KATO session for this user
    if 'kato_session_id' not in session:
        kato_session = kato_client.create_session(
            node_id=f"user_{session['user_id']}"
        )
        session['kato_session_id'] = kato_session['session_id']

    # Use session-based endpoint
    result = kato_client.observe_in_session(
        session['kato_session_id'],
        strings=request.json['strings']
    )
    return jsonify(result)
```

### Pattern 3: Background Worker

```python
import threading

class KATOWorker:
    def __init__(self, worker_id):
        self.client = KATOClient()
        session = self.client.create_session(
            node_id=f"worker_{worker_id}"
        )
        self.session_id = session['session_id']

    def process(self, data):
        self.client.observe_in_session(
            self.session_id,
            strings=data
        )
        return self.client.get_session_predictions(self.session_id)

# Each worker gets isolated session
workers = [KATOWorker(i) for i in range(5)]
```

## Troubleshooting

### Issue: "Session not found" errors

**Cause:** Session expired (default TTL is 3600 seconds)

**Solution:**
```python
# Extend session before it expires
client.extend_session(session_id, ttl_seconds=3600)

# Or create new session if expired
try:
    client.get_session_info(session_id)
except SessionNotFoundError:
    session = client.create_session(node_id="user123")
    session_id = session['session_id']
```

### Issue: Performance concerns with session creation

**Cause:** Creating too many sessions

**Solution:**
```python
# Reuse sessions - don't create one per request
# Cache session_id in your application state
# Only create new session when needed
```

### Issue: Need to maintain processor_id compatibility

**Solution:**
```python
# Use processor_id as node_id during migration
session = client.create_session(
    node_id=legacy_processor_id  # Same as old processor_id
)
# This maintains database isolation compatibility
```

## Disabling Auto-Session Middleware

If you need to disable the automatic migration (not recommended):

```bash
# Set environment variable
export ENABLE_AUTO_SESSION_MIDDLEWARE=false

# Or in docker-compose.yml
environment:
  - ENABLE_AUTO_SESSION_MIDDLEWARE=false
```

When disabled, deprecated endpoints will fail with appropriate errors directing you to migrate.

## Phase 3: Future Endpoint Removal

**Timeline**: 2-3 releases after Phase 2 (when metrics show <1% usage)

What will happen:
- Direct endpoints (`/observe`, `/stm`, `/learn`, etc.) will be removed
- Auto-session middleware will be removed
- Only session-based endpoints will remain
- Breaking change for any code still using deprecated endpoints

**Action Required Before Phase 3**:
Migrate to session-based endpoints using the examples in this guide.

## Need Help?

- Check the [CLAUDE.md](../CLAUDE.md) for KATO architecture details
- Review the [sample-kato-client.py](../sample-kato-client.py) for complete API examples
- Open an issue on GitHub for migration questions

## Summary

The migration from direct to session-based endpoints is straightforward:

1. **Replace processor_id with session_id**
2. **Create sessions at application/user initialization**
3. **Use `*_in_session()` methods instead of direct methods**
4. **Optionally manage session lifecycle (extend, delete)**

Session-based endpoints provide better reliability, state management, and multi-user support. Migration is recommended for all production applications.
