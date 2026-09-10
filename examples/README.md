# KATO Examples

This directory contains practical examples demonstrating various KATO features and use cases.

## Prerequisites

Ensure KATO services are running:
```bash
./start.sh
```

Verify services are available:
- KATO API: http://localhost:8000
- API Documentation: http://localhost:8000/docs

## Available Examples

### 1. python-client.py

**Purpose**: Complete Python client library for KATO API

**Features**:
- Synchronous, built on `requests` (no async/await)
- Transparent session management: one client == one session, created for you
- Session recovery: auto-recreates and replays STM if the session expires
- Observation processing (text, vectors, emotives, metadata)
- Pattern learning and prediction retrieval
- Node-scoped pattern and symbol introspection
- Monitoring, metrics and health endpoints
- Retry with exponential backoff on 502/503/504

Not covered: the WebSocket event stream (`ws://<host>/ws/events`). `requests`
cannot speak WebSocket - use `websockets` or `websocket-client` for that.

**Usage**:
```python
# The file name is hyphenated, so load it by path rather than importing it.
import importlib.util

spec = importlib.util.spec_from_file_location("kato_client", "examples/python-client.py")
kato_client = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kato_client)

# node_id is required; the session is created automatically
with kato_client.KATOClient(base_url="http://localhost:8000", node_id="demo") as client:
    client.observe(strings=["hello", "world"])
    client.learn()
    predictions = client.get_predictions()
# leaving the `with` block deletes the session
```

**Method groups**:

| Group | Methods |
|---|---|
| Session | `get_session_info`, `get_session_config`, `update_session_config`, `extend_session`, `check_session_exists`, `get_active_session_count`, `close` |
| Observation & learning | `observe`, `observe_sequence`, `get_stm`, `learn`, `finalize_training`, `get_predictions`, `clear_stm`, `clear_all` |
| Session data | `get_percept_data`, `get_cognition_data` |
| Patterns | `get_pattern`, `get_pattern_count` |
| Symbols | `get_symbol_affinities`, `get_symbol_stats`, `get_symbol_affinity` |
| Monitoring | `get_concurrency_stats`, `get_cache_stats`, `invalidate_cache`, `get_distributed_stm_stats`, `get_metrics`, `get_metric_history`, `get_stats`, `get_connection_pools_status`, `get_prometheus_metrics` |
| Health | `health_check`, `get_status`, `get_root_info` |

`clear_all()` is destructive and node-scoped: it wipes learned patterns shared
by every session on the same `node_id`, not just this client's STM.

`get_node_percept_data()` / `get_node_cognition_data()` wrap the deprecated
node-scoped routes, which the server answers with an empty payload. Use
`get_percept_data()` / `get_cognition_data()` instead.

**Run Example**:
```bash
python examples/python-client.py
```

**Documentation**: See inline docstrings and [docs/users/api-reference.md](../docs/users/api-reference.md)

---

### 2. token-matching-example.py

**Purpose**: Demonstrates token-level vs character-level matching behavior

**Features**:
- Token-level matching (default, faster)
- Character-level matching (for document chunks)
- Performance comparison
- Matching mode configuration

**Usage**:
```bash
python examples/token-matching-example.py
```

**Key Concepts**:
- **Token-level**: Exact difflib compatibility, 9x faster, recommended for tokenized text
- **Character-level**: Fuzzy string matching, 75x faster than v2.x, use for document chunks only

**Configuration**:
```python
# Set matching mode via session config
config = {
    "use_token_matching": True  # or False for character-level
}
```

**Documentation**: [docs/research/pattern-matching.md](../docs/research/pattern-matching.md)

---

### 3. hierarchical-training.py

**Purpose**: Long-running session with hierarchical training patterns

**Features**:
- Session TTL and auto-extension behavior
- Multi-level abstraction (learning from predictions)
- Session longevity testing
- Progress tracking for extended training sessions

**Use Case**:
Training sessions that learn patterns over extended periods (hours/days), such as:
- Hierarchical learning systems (kato-notebooks project)
- Long-form conversation modeling
- Temporal pattern discovery across large datasets

**Usage**:
```bash
python examples/hierarchical-training.py
```

**Configuration**:
- `SESSION_TTL`: Session timeout (default: 3600 seconds)
- `SESSION_AUTO_EXTEND`: Auto-extend TTL on access (default: true)

**Documentation**:
- Session management: [docs/users/api-reference.md](../docs/users/api-reference.md)
- Hierarchical training: See kato-notebooks project

---

### 4. multi-instance-config.yaml

**Purpose**: Configuration template for multi-instance KATO deployment

**Features**:
- Multiple processor instances with different configurations
- Node isolation via `kb_id` parameter
- Independent configuration per instance
- Load balancing and routing patterns

**Usage**:
```bash
# Deploy with docker-compose
docker-compose -f docker-compose.yml -f examples/multi-instance-config.yaml up
```

**Documentation**:
- [docs/integration/multi-instance.md](../docs/integration/multi-instance.md)
- [docs/developers/kb-id-isolation.md](../docs/developers/kb-id-isolation.md)

---

## Integration Patterns

### Basic Workflow
```python
# 1. Create session
session = await client.create_session()

# 2. Configure session (optional)
await client.update_session_config(session_id, {
    "recall_threshold": 0.5,
    "max_predictions": 100,
    "use_token_matching": True
})

# 3. Observe sequences
await client.observe(session_id, [
    ["event1_symbol1", "event1_symbol2"],
    ["event2_symbol1"]
])

# 4. Trigger learning (needed when MAX_PATTERN_LENGTH = 0, i.e. manual learning)
await client.auto_learn(session_id)

# 5. Get predictions
predictions = await client.get_predictions(session_id)

# 6. Clean up
await client.delete_session(session_id)
```

### Multi-Modal Observations
```python
# Include vectors, emotives, and metadata
await client.observe(
    session_id=session_id,
    events=[["hello", "world"]],
    vectors=[[embedding_vector_768dim]],  # Optional
    emotives=[[0.8]],  # Optional: -1 to +1
    metadata=[[{"source": "user", "confidence": 0.95}]]  # Optional
)
```

## Common Patterns

### Pattern Learning Modes

**Manual Learning** (recommended for control):
```bash
# Set MAX_PATTERN_LENGTH=0 (default)
# Call auto_learn() explicitly when ready
await client.auto_learn(session_id)
```

**Auto Learning** (for streaming use cases):
```bash
# Set MAX_PATTERN_LENGTH=5 (or desired trigger length)
# Learning happens automatically when STM reaches threshold
```

### Session Management

**Session TTL**:
- Default: 3600 seconds (1 hour)
- Auto-extends on API access if `SESSION_AUTO_EXTEND=true`
- Manually extend: `await client.extend_session_ttl(session_id, ttl_seconds)`

**Session Isolation**:
- Each session has isolated STM (short-term memory)
- Sessions share LTM (long-term memory) within same `processor_id`/`kb_id`

## Troubleshooting

### Common Issues

1. **Connection Refused**
   - Ensure services are running: `./start.sh`
   - Check logs: `docker-compose logs kato`

2. **Session Not Found**
   - Check session TTL hasn't expired
   - Enable auto-extension: `SESSION_AUTO_EXTEND=true`

3. **No Predictions Returned**
   - Ensure patterns are learned: call `auto_learn()` if manual mode
   - Check STM has minimum 2 events
   - Lower `recall_threshold` if too restrictive

4. **Slow Performance**
   - Use token-level matching for tokenized text
   - Reduce `max_predictions` if returning too many results
   - Check filter pipeline configuration (MinHash/LSH)

## Additional Resources

- **User Guide**: [docs/users/quick-start.md](../docs/users/quick-start.md)
- **API Reference**: [docs/users/api-reference.md](../docs/users/api-reference.md)
- **Architecture**: [docs/developers/architecture.md](../docs/developers/architecture.md)
- **Integration Patterns**: [docs/integration/README.md](../docs/integration/README.md)

## Contributing Examples

Have a useful KATO integration pattern? Contribute an example:

1. Create well-documented script with clear docstrings
2. Include usage instructions and prerequisites
3. Add entry to this README
4. Submit pull request

---

**Last Updated**: December 2024
**KATO Version**: 3.0+
