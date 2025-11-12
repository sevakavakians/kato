# KATO API Migration Guide: Direct to Session-Based Endpoints

**🗂️ MIGRATION COMPLETE (2025-10-06)**

This document provides a quick reference for the completed migration from direct endpoints to session-based endpoints.

---

## Summary

As of Phase 3 (2025-10-06), KATO exclusively uses **session-based endpoints**. All direct endpoints have been permanently removed.

### Why Sessions?

- ✅ Better state persistence with Redis
- ✅ Thread safety and concurrency support
- ✅ Proper TTL and lifecycle management
- ✅ Multi-user isolation
- ✅ Per-session configuration

## Quick Migration Reference

### Create a Session First

```bash
# Create session
SESSION_ID=$(curl -s -X POST http://localhost:8000/sessions \
  -H "Content-Type: application/json" \
  -d '{
    "node_id": "user_alice",
    "config": {
      "recall_threshold": 0.5,
      "max_predictions": 100
    },
    "ttl_seconds": 3600
  }' | jq -r '.session_id')

echo "Session ID: $SESSION_ID"
```

### Endpoint Mapping

| Old Endpoint (Removed) | New Endpoint (Current) |
|------------------------|------------------------|
| `POST /observe` | `POST /sessions/{session_id}/observe` |
| `GET /stm` | `GET /sessions/{session_id}/stm` |
| `POST /learn` | `POST /sessions/{session_id}/learn` |
| `GET /predictions` | `GET /sessions/{session_id}/predictions` |
| `POST /clear-stm` | `POST /sessions/{session_id}/clear-stm` |
| `POST /clear-all` | `POST /sessions/{session_id}/clear-all` |
| `POST /observe-sequence` | `POST /sessions/{session_id}/observe-sequence` |
| `POST /genes/update` | `POST /sessions/{session_id}/config` |

### Example: Complete Workflow

```bash
# 1. Create session
SESSION=$(curl -s -X POST http://localhost:8000/sessions \
  -H "Content-Type: application/json" \
  -d '{"node_id": "user_alice"}')
SESSION_ID=$(echo $SESSION | jq -r '.session_id')

# 2. Observe
curl -X POST http://localhost:8000/sessions/$SESSION_ID/observe \
  -H "Content-Type: application/json" \
  -d '{"strings": ["hello", "world"], "vectors": [], "emotives": {}}'

# 3. Learn
curl -X POST http://localhost:8000/sessions/$SESSION_ID/learn

# 4. Get predictions
curl http://localhost:8000/sessions/$SESSION_ID/predictions

# 5. Update configuration
curl -X POST http://localhost:8000/sessions/$SESSION_ID/config \
  -H "Content-Type: application/json" \
  -d '{"config": {"recall_threshold": 0.7}}'
```

### Python Client Example

```python
import requests

class KATOClient:
    def __init__(self, base_url="http://localhost:8000"):
        self.base_url = base_url
        self.session_id = None

    def create_session(self, node_id, config=None):
        response = requests.post(
            f"{self.base_url}/sessions",
            json={"node_id": node_id, "config": config or {}}
        )
        self.session_id = response.json()['session_id']
        return self.session_id

    def observe(self, strings, vectors=None, emotives=None):
        return requests.post(
            f"{self.base_url}/sessions/{self.session_id}/observe",
            json={
                "strings": strings,
                "vectors": vectors or [],
                "emotives": emotives or {}
            }
        ).json()

    def learn(self):
        return requests.post(
            f"{self.base_url}/sessions/{self.session_id}/learn"
        ).json()

    def get_predictions(self):
        return requests.get(
            f"{self.base_url}/sessions/{self.session_id}/predictions"
        ).json()

# Usage
client = KATOClient()
client.create_session("user_alice")
client.observe(["hello", "world"])
client.learn()
predictions = client.get_predictions()
```

## Key Differences

### Session Lifecycle

- **Create**: `POST /sessions` with `node_id`
- **Use**: All operations require `session_id` in path
- **Expire**: Sessions auto-expire after TTL (default: 1 hour)
- **Extend**: Access automatically extends TTL (if `SESSION_AUTO_EXTEND=true`)
- **Delete**: `DELETE /sessions/{session_id}` (optional, auto-expires)

### Configuration

**Old**: Global processor configuration via `/genes/update`
**New**: Per-session configuration via `/sessions/{session_id}/config`

Each session maintains independent configuration.

### Data Isolation

**Old**: Single processor state per node
**New**: Each session has isolated STM, shared LTM per node

- **STM**: Isolated per session
- **LTM**: Shared across sessions with same `node_id`
- **Config**: Independent per session

## Need Help?

- **API Reference**: See [API Reference](../api-reference.md)
- **Getting Started**: See [Quick Start Guide](../quick-start.md)
- **Configuration**: See [Configuration Guide](../../operations/configuration.md)
