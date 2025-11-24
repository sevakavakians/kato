# Your First KATO Session

Complete tutorial for creating your first KATO session and understanding core workflows.

## Prerequisites

- KATO installed and running (see [Installation Guide](installation.md))
- `curl` and `jq` installed (or use Python examples)
- Basic understanding of REST APIs

## Overview

In this tutorial, you'll:
1. Create a session with a `node_id`
2. Send observations to build short-term memory
3. Learn a pattern
4. Get predictions from partial input
5. Understand data persistence

**Time Required**: ~10 minutes

## Step 1: Verify KATO is Running

```bash
# Check KATO health
curl http://localhost:8000/health

# Expected response:
# {"status": "healthy", "message": "KATO API is running"}
```

If this fails, ensure services are running:
```bash
./start.sh
docker-compose ps  # All services should show "Up"
```

## Step 2: Create a Session

Every interaction with KATO requires a session. Sessions have:
- **session_id**: Temporary identifier (expires after TTL)
- **node_id**: Permanent identifier linking to trained patterns

```bash
# Create session with node_id
curl -X POST http://localhost:8000/sessions \
  -H "Content-Type: application/json" \
  -d '{
    "node_id": "tutorial_morning_routine",
    "config": {
      "recall_threshold": 0.1,
      "max_predictions": 50
    }
  }' | jq .
```

**Response**:
```json
{
  "session_id": "session-abc123def456",
  "node_id": "tutorial_morning_routine",
  "created_at": "2025-11-13T10:00:00Z",
  "ttl": 3600,
  "config": {
    "recall_threshold": 0.1,
    "max_predictions": 50,
    "sort_symbols": true,
    "use_token_matching": true
  }
}
```

**Save the session_id**:
```bash
export SESSION_ID="session-abc123def456"  # Use your actual session_id
```

**Key Concepts**:
- **session_id**: Temporary - expires after 1 hour (default)
- **node_id**: Permanent - links to database namespace `node_{node_id}_kato`
- Same **node_id** = Same trained patterns (always)

## Step 3: Send Observations

Build up short-term memory by sending observations representing a morning routine.

### Observation 1: Wake Up

```bash
curl -X POST http://localhost:8000/sessions/$SESSION_ID/observe \
  -H "Content-Type: application/json" \
  -d '{
    "strings": ["alarm", "wake_up"],
    "vectors": [],
    "emotives": {"energy": -0.3}
  }' | jq .
```

**Response**:
```json
{
  "strings": ["alarm", "wake_up"],
  "emotives": {"energy": -0.3},
  "sorted": ["alarm", "wake_up"],
  "stm_length": 1
}
```

**Note**: Strings are automatically sorted alphabetically within each event.

### Observation 2: Shower

```bash
curl -X POST http://localhost:8000/sessions/$SESSION_ID/observe \
  -H "Content-Type: application/json" \
  -d '{
    "strings": ["shower", "get_dressed"],
    "vectors": [],
    "emotives": {"energy": 0.2}
  }' | jq .
```

### Observation 3: Breakfast

```bash
curl -X POST http://localhost:8000/sessions/$SESSION_ID/observe \
  -H "Content-Type: application/json" \
  -d '{
    "strings": ["breakfast", "coffee"],
    "vectors": [],
    "emotives": {"energy": 0.5, "joy": 0.8}
  }' | jq .
```

### Observation 4: Leave

```bash
curl -X POST http://localhost:8000/sessions/$SESSION_ID/observe \
  -H "Content-Type: application/json" \
  -d '{
    "strings": ["leave_home", "drive_to_work"],
    "vectors": [],
    "emotives": {"energy": 0.6}
  }' | jq .
```

## Step 4: View Short-Term Memory

```bash
curl http://localhost:8000/sessions/$SESSION_ID/stm | jq .
```

**Response**:
```json
{
  "stm": [
    ["alarm", "wake_up"],
    ["get_dressed", "shower"],
    ["breakfast", "coffee"],
    ["drive_to_work", "leave_home"]
  ],
  "session_id": "session-abc123def456",
  "length": 4
}
```

**Key Observations**:
- Each event contains sorted strings
- STM preserves temporal order of events
- 4 events = pattern length of 4

## Step 5: Learn the Pattern

Convert short-term memory into a long-term pattern.

```bash
curl -X POST http://localhost:8000/sessions/$SESSION_ID/learn | jq .
```

**Response**:
```json
{
  "pattern_name": "PTN|a1b2c3d4e5f6",
  "length": 4,
  "events": [
    ["alarm", "wake_up"],
    ["get_dressed", "shower"],
    ["breakfast", "coffee"],
    ["drive_to_work", "leave_home"]
  ],
  "emotive_profile": {
    "energy": [[-0.3], [0.2], [0.5], [0.6]],
    "joy": [[null], [null], [0.8], [null]]
  },
  "stored_in": "node_tutorial_morning_routine_kato",
  "message": "Pattern learned successfully"
}
```

**What Just Happened**:
1. KATO created a pattern from STM
2. Pattern assigned unique name: `PTN|a1b2c3d4e5f6` (hash-based)
3. Pattern stored in persistent database `node_tutorial_morning_routine_kato`
4. Emotives stored as rolling windows (null = not observed)
5. STM remains unchanged (not cleared)

## Step 6: Clear Short-Term Memory

Prepare for testing recall by clearing STM.

```bash
curl -X POST http://localhost:8000/sessions/$SESSION_ID/clear-stm | jq .
```

**Response**:
```json
{
  "message": "Short-term memory cleared",
  "session_id": "session-abc123def456",
  "stm_length": 0
}
```

## Step 7: Test Pattern Recall

Send partial input and get predictions.

### Partial Input: First Event Only

```bash
curl -X POST http://localhost:8000/sessions/$SESSION_ID/observe \
  -H "Content-Type: application/json" \
  -d '{
    "strings": ["alarm", "wake_up"],
    "vectors": [],
    "emotives": {}
  }' | jq .
```

### Get Predictions

```bash
curl http://localhost:8000/sessions/$SESSION_ID/predictions | jq .
```

**Response**:
```json
{
  "predictions": [
    {
      "past": [],
      "present": [["alarm", "wake_up"]],
      "future": [
        ["get_dressed", "shower"],
        ["breakfast", "coffee"],
        ["drive_to_work", "leave_home"]
      ],
      "missing": [[]],
      "extras": [[]],
      "pattern_name": "PTN|a1b2c3d4e5f6",
      "similarity": 1.0,
      "metrics": {
        "potential": 0.85,
        "evidence": 1.0,
        "confidence": 0.95
      },
      "emotive_predictions": {
        "energy": {"mean": 0.43, "std": 0.34},
        "joy": {"mean": 0.8, "std": 0.0}
      }
    }
  ],
  "count": 1
}
```

**Understanding Predictions**:
- **past**: Events before first match (empty - we matched from beginning)
- **present**: Events containing matches (our input)
- **future**: Events expected after last match (next 3 steps)
- **missing**: Expected symbols not observed (empty - perfect match)
- **extras**: Observed symbols not expected (empty - perfect match)
- **similarity**: 1.0 = perfect match
- **potential**: 0.85 = high predictive value
- **emotive_predictions**: Expected emotional states

## Step 8: Test Partial Recall

Send different starting point.

### Clear and Observe Middle of Pattern

```bash
# Clear STM
curl -X POST http://localhost:8000/sessions/$SESSION_ID/clear-stm

# Observe breakfast (event 3 of 4)
curl -X POST http://localhost:8000/sessions/$SESSION_ID/observe \
  -H "Content-Type: application/json" \
  -d '{
    "strings": ["breakfast", "coffee"],
    "vectors": [],
    "emotives": {}
  }'

# Get predictions
curl http://localhost:8000/sessions/$SESSION_ID/predictions | jq .
```

**Response**:
```json
{
  "predictions": [
    {
      "past": [
        ["alarm", "wake_up"],
        ["get_dressed", "shower"]
      ],
      "present": [["breakfast", "coffee"]],
      "future": [["drive_to_work", "leave_home"]],
      "missing": [[]],
      "extras": [[]],
      "pattern_name": "PTN|a1b2c3d4e5f6",
      "similarity": 1.0,
      "metrics": {
        "potential": 0.25,
        "evidence": 1.0,
        "confidence": 0.95
      }
    }
  ]
}
```

**Key Observations**:
- **past**: Shows 2 events that came before in the pattern
- **future**: Shows 1 event remaining
- **potential**: Lower (0.25) - less future information available
- KATO reconstructs full pattern context from any matching event

## Step 9: Test Fuzzy Matching

KATO can match patterns even with partial/noisy input.

### Observe Similar but Not Exact

```bash
# Clear STM
curl -X POST http://localhost:8000/sessions/$SESSION_ID/clear-stm

# Observe "coffee" only (subset of breakfast event)
curl -X POST http://localhost:8000/sessions/$SESSION_ID/observe \
  -H "Content-Type: application/json" \
  -d '{"strings": ["coffee"], "vectors": [], "emotives": {}}'

# Get predictions
curl http://localhost:8000/sessions/$SESSION_ID/predictions | jq .
```

**Response**:
```json
{
  "predictions": [
    {
      "past": [
        ["alarm", "wake_up"],
        ["get_dressed", "shower"]
      ],
      "present": [["breakfast", "coffee"]],
      "future": [["drive_to_work", "leave_home"]],
      "missing": [["breakfast"]],
      "extras": [[]],
      "pattern_name": "PTN|a1b2c3d4e5f6",
      "similarity": 0.5,
      "metrics": {
        "potential": 0.25,
        "evidence": 0.5,
        "confidence": 0.71
      }
    }
  ]
}
```

**Key Observations**:
- **missing**: Shows "breakfast" was expected but not observed
- **similarity**: 0.5 (1 of 2 symbols matched)
- **confidence**: Lower (0.71) due to incomplete match
- Pattern still recalled despite imperfect match (threshold = 0.1)

## Step 10: Understanding Persistence

Close your terminal, open a new one tomorrow, and your patterns persist!

### Next Day: Create New Session

```bash
# New session, SAME node_id
curl -X POST http://localhost:8000/sessions \
  -H "Content-Type: application/json" \
  -d '{"node_id": "tutorial_morning_routine"}' | jq -r '.session_id'

# Save new session ID
export SESSION_ID="session-xyz789"  # Your new session_id
```

### Test Recall with New Session

```bash
# Observe first event
curl -X POST http://localhost:8000/sessions/$SESSION_ID/observe \
  -H "Content-Type: application/json" \
  -d '{"strings": ["alarm", "wake_up"], "vectors": [], "emotives": {}}'

# Get predictions - still works!
curl http://localhost:8000/sessions/$SESSION_ID/predictions | jq .
```

**Result**: Same predictions! Pattern persists across sessions.

**Why This Works**:
- `node_id` links to persistent database
- Patterns stored permanently in persistent storage
- New session reconnects to same database namespace
- Training is never lost (until you delete the data)

## Key Takeaways

### Session vs Node

| Aspect | session_id | node_id |
|--------|------------|---------|
| **Lifetime** | Temporary (1 hour default) | Permanent |
| **Stores** | STM, emotives, config | LTM patterns, vectors |
| **Isolation** | Per-session unique | Shared across sessions |
| **Persistence** | Redis (volatile) | Persistent database (patterns & vectors) |

### Learning Workflow

```
Observations → STM → Learn → LTM Pattern
                ↓              ↓
            (Temporary)    (Permanent)
                ↓              ↓
         Expires after TTL  Persists forever
```

### Prediction Structure

- **past**: Context before match
- **present**: Matching events (complete events, not partial)
- **future**: Expected next events
- **missing**: Expected but not observed (aligned with present)
- **extras**: Observed but not expected (aligned with STM)

### Pattern Matching Behavior

1. **Exact Match**: `similarity = 1.0` - all symbols match
2. **Partial Match**: `0.0 < similarity < 1.0` - some symbols match
3. **No Match**: `similarity < recall_threshold` - pattern not returned
4. **Default Threshold**: `0.1` (very permissive)

## Common Patterns

### Morning Routine (This Tutorial)
- **Use Case**: Sequential workflow
- **Pattern Type**: Temporal sequence
- **Prediction**: Next steps in routine

### User Preferences
```bash
# Learn user preferences (non-temporal)
# Event 1: User profile
curl -X POST http://localhost:8000/sessions/$SESSION_ID/observe \
  -d '{"strings": ["user:alice", "theme:dark", "lang:python"], ...}'

# Learn preferences
curl -X POST http://localhost:8000/sessions/$SESSION_ID/learn

# Later: Query by user
curl -X POST http://localhost:8000/sessions/$SESSION_ID/observe \
  -d '{"strings": ["user:alice"], ...}'

# Returns: theme:dark, lang:python (associated preferences)
```

### Error Patterns
```bash
# Learn error → solution patterns
# Event 1: Error context
curl -X POST http://localhost:8000/sessions/$SESSION_ID/observe \
  -d '{"strings": ["error:timeout", "service:api", "region:us-east"], ...}'

# Event 2: Solution
curl -X POST http://localhost:8000/sessions/$SESSION_ID/observe \
  -d '{"strings": ["action:retry", "backoff:exponential"], ...}'

curl -X POST http://localhost:8000/sessions/$SESSION_ID/learn

# Later: See error context → predict solution
```

## Next Steps

1. **Explore Configuration**: [Configuration Guide](configuration.md)
2. **Build Python Client**: [Python Client Guide](python-client.md)
3. **Learn Pattern Types**: [Pattern Learning Guide](pattern-learning.md)
4. **Understand Predictions**: [Predictions Guide](predictions.md)
5. **Session Management**: [Session Management Guide](session-management.md)

## Cleanup

To remove tutorial data:

```bash
# Stop KATO
docker-compose down

# Remove tutorial data (requires admin access)
# Contact system administrator to delete node_tutorial_morning_routine_kato namespace

# Or remove all data
docker-compose down -v  # WARNING: Deletes ALL patterns
```

---

**Last Updated**: November 2025
**KATO Version**: 3.0+
