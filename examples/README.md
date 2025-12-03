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
- Session management (create, configure, extend, delete)
- Observation processing (text, vectors, emotives, metadata)
- Pattern learning and prediction retrieval
- Error handling and retry logic
- Async/await support with httpx

**Usage**:
```python
from kato_client import KatoClient

# Initialize client
client = KatoClient(base_url="http://localhost:8000", processor_id="demo")

# Create session
session = await client.create_session()

# Observe sequences
await client.observe(session_id, [["hello", "world"]])

# Get predictions
predictions = await client.get_predictions(session_id)
```

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
- [docs/KB_ID_ISOLATION.md](../docs/KB_ID_ISOLATION.md)

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

# 4. Trigger learning (if AUTO_LEARN_THRESHOLD = 0)
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
