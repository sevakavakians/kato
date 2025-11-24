# Database Persistence Guide

## Overview

KATO provides **persistent long-term memory** that survives across sessions and service restarts. Understanding how data persists is critical for production use and training scenarios.

## Key Concepts

### Two Types of State

**1. Session State (Temporary - Redis)**
- Short-term memory (STM)
- Emotives accumulator
- Session metadata
- **Expires**: When session TTL expires (default: 1 hour)

**2. Long-Term Knowledge (Permanent - Pattern Database + Vector Database)**
- Learned patterns
- Symbol frequencies
- Vector embeddings
- **Persists**: Forever (until explicitly deleted)

## Database Naming Convention

### The Persistence Model

Your `node_id` determines which database namespace and Qdrant collection store your trained data:

```python
# Formula
processor_id = sanitize(node_id) + "_" + SERVICE_NAME

# Database namespace
database_namespace = processor_id

# Qdrant collection name
collection_name = "vectors_" + processor_id
```

### Example Transformations

```bash
# Default SERVICE_NAME='kato'
node_id: "alice"
→ processor_id: "alice_kato"
→ Database namespace: "alice_kato"
→ Qdrant collection: "vectors_alice_kato"

node_id: "project-x"
→ processor_id: "project_x_kato"  # Hyphens replaced with underscores
→ Database namespace: "project_x_kato"
→ Qdrant collection: "vectors_project_x_kato"

node_id: "user/123"
→ processor_id: "user_123_kato"  # Special characters sanitized
→ Database namespace: "user_123_kato"
→ Qdrant collection: "vectors_user_123_kato"
```

### Character Sanitization

The following characters are replaced with underscores for database compatibility:
- Forward slash: `/` → `_`
- Backslash: `\` → `_`
- Period: `.` → `_`
- Quote: `"` → `_`
- Dollar: `$` → `_`
- Asterisk: `*` → `_`
- Angle brackets: `<`, `>` → `_`
- Colon: `:` → `_`
- Pipe: `|` → `_`
- Question mark: `?` → `_`
- Hyphen: `-` → `_`
- Space: ` ` → `_`

## Reconnecting to Trained Data

### Basic Pattern

**The same `node_id` always accesses the same trained database:**

```bash
# Day 1: Initial training
curl -X POST http://localhost:8000/sessions \
  -H "Content-Type: application/json" \
  -d '{"node_id": "alice"}'

# Returns: {"session_id": "session-abc123...", "node_id": "alice"}

# Train patterns...
curl -X POST http://localhost:8000/sessions/session-abc123/observe \
  -d '{"strings": ["wake", "up"]}'
curl -X POST http://localhost:8000/sessions/session-abc123/observe \
  -d '{"strings": ["drink", "coffee"]}'
curl -X POST http://localhost:8000/sessions/session-abc123/learn

# Session expires after TTL...
```

```bash
# Day 7: Reconnect to same training
curl -X POST http://localhost:8000/sessions \
  -H "Content-Type: application/json" \
  -d '{"node_id": "alice"}'  # SAME node_id

# Returns: NEW session ID, but SAME node_id
# {"session_id": "session-xyz789...", "node_id": "alice"}

# ALL PREVIOUS PATTERNS ARE AVAILABLE!
curl -X POST http://localhost:8000/sessions/session-xyz789/observe \
  -d '{"strings": ["wake", "up"]}'
curl http://localhost:8000/sessions/session-xyz789/predictions
# KATO predicts: ["drink", "coffee"] from Day 1 training!
```

### What Happens Behind the Scenes

```
User creates session with node_id="alice"
    ↓
ProcessorManager generates: processor_id = "alice_kato"
    ↓
Database namespace "alice_kato" is accessed (or created if new)
    ↓
All learned patterns from this node_id are immediately available
```

## Critical: SERVICE_NAME Stability

### ⚠️ WARNING: Changing SERVICE_NAME Breaks Access to Data

The `SERVICE_NAME` environment variable is part of the database naming formula. **Changing it will prevent access to previously trained data.**

### Example of What Goes Wrong

```bash
# Initial training with default SERVICE_NAME='kato'
docker-compose up -d
# Creates namespace: "alice_kato"
# User trains patterns...
```

```bash
# Later, someone changes docker-compose.yml
environment:
  - SERVICE_NAME=production  # ❌ CHANGED!
docker-compose restart
```

```bash
# User tries to reconnect
curl -X POST http://localhost:8000/sessions -d '{"node_id": "alice"}'
# Now looks for namespace: "alice_production" ← DIFFERENT NAMESPACE!
# Previous training in "alice_kato" is no longer accessible!
```

### How to Prevent Data Loss

**1. Set SERVICE_NAME Once (Recommended: Use Default)**

```yaml
# docker-compose.yml
environment:
  - SERVICE_NAME=kato  # ✅ Use default, never change
```

**2. If You Must Change SERVICE_NAME**

Avoid changing SERVICE_NAME as it requires complex data migration. Contact support or see migration documentation if absolutely necessary.

## Database Lifecycle

### What Persists

**Stored in Pattern Database (`{node_id}_{SERVICE_NAME}`):**
- All learned patterns with frequencies
- Symbol frequencies and metadata
- Pattern statistics

**Stored in Vector Database (`vectors_{node_id}_{SERVICE_NAME}`):**
- Vector embeddings (768-dimensional)
- Vector similarity indices

### What Expires

**Stored in Redis (expires with session TTL):**
- Session ID mappings
- Short-term memory (STM)
- Emotives accumulator
- Session configuration overrides

### Clearing Trained Data

**To clear only session state:**

```bash
# Clear STM only (keeps LTM)
curl -X POST http://localhost:8000/sessions/{session_id}/clear-stm
```

**Note**: Clearing all trained data for a node requires direct database access. Contact your system administrator or see deployment documentation.

## Multi-Node Isolation

### Complete Isolation Between Nodes

Each `node_id` gets completely isolated databases:

```bash
# Node alice
node_id: "alice"
→ Pattern Database: "alice_kato" (isolated patterns)
→ Vector Database: "vectors_alice_kato" (isolated vectors)

# Node bob
node_id: "bob"
→ Pattern Database: "bob_kato" (completely separate patterns)
→ Vector Database: "vectors_bob_kato" (completely separate vectors)
```

**Alice and Bob can train simultaneously without any data collision.**

## Production Best Practices

### 1. Use Consistent node_id Values

```python
# Good: Deterministic identifiers
node_id = f"user_{user_id}"  # e.g., "user_12345"
node_id = f"project_{project_name}"  # e.g., "project_chatbot"

# Bad: Random or timestamp-based
node_id = f"user_{uuid.uuid4()}"  # Different every time!
node_id = f"session_{timestamp}"  # Can't reconnect!
```

### 2. Never Change SERVICE_NAME in Production

```yaml
# Set once at deployment
environment:
  - SERVICE_NAME=kato  # ✅ Lock this value
```

### 3. Document Your node_id Scheme

```python
# Document the mapping
# node_id format: "tenant_{tenant_id}"
# Examples:
#   - "tenant_acme" → Database: "tenant_acme_kato"
#   - "tenant_globex" → Database: "tenant_globex_kato"
```

### 4. Plan for Long-Term Storage

Pattern databases grow with training. Monitor disk usage and implement backup strategies according to your deployment configuration. See deployment documentation for backup procedures.

### 5. Test Persistence Before Production

```python
# Test script
def test_persistence():
    # Day 1: Train
    session1 = create_session(node_id="test_user")
    observe(session1, ["hello", "world"])
    learn(session1)

    # Delete session
    delete_session(session1)

    # Day 2: Reconnect
    session2 = create_session(node_id="test_user")  # Same node_id
    observe(session2, ["hello"])
    predictions = get_predictions(session2)

    # Verify: Should predict "world" from Day 1
    assert "world" in predictions[0]['future']
```

## Troubleshooting

### "My trained data disappeared!"

**Check:**
1. Are you using the same `node_id`?
2. Did `SERVICE_NAME` change?
3. Did database containers restart with data loss? (Ensure named volumes are configured!)

```bash
# Check current SERVICE_NAME
docker exec kato env | grep SERVICE_NAME
```

### "I want to share training between environments"

**Option 1: Use same node_id and SERVICE_NAME**
```bash
# Production
SERVICE_NAME=kato node_id=shared_bot

# Staging (points to same database)
SERVICE_NAME=kato node_id=shared_bot
```

**Option 2: Export/import patterns**

Pattern export/import requires direct database access. See deployment documentation for migration procedures.

### "How do I migrate to a new node_id?"

```python
# Unfortunately, you must re-train or migrate databases
# No built-in migration - databases are named by node_id

# Workaround: Keep using old node_id for compatibility
old_node_id = "legacy_user_123"
create_session(node_id=old_node_id)  # Accesses old database
```

## Summary

**Remember:**
- ✅ Same `node_id` → Same database → Same training (always)
- ✅ `SERVICE_NAME` should never change in production
- ✅ Sessions are temporary, patterns are permanent
- ✅ Use deterministic `node_id` values for reconnection
- ⚠️ Changing `SERVICE_NAME` breaks access to all trained data
- ⚠️ Random `node_id` values prevent reconnection

**For more information:**
- [Getting Started Guide](quick-start.md)
- [Configuration Guide](../operations/configuration.md)
- [API Reference](api-reference.md)
