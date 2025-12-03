# Frequently Asked Questions (FAQ)

Common questions about KATO and their answers.

## General Questions

### What is KATO?

KATO (Knowledge Abstraction for Traceable Outcomes) is a deterministic memory and prediction system for transparent, explainable AI. It learns patterns from multi-modal observations (text, vectors, emotions) and makes temporal predictions while maintaining complete transparency.

### What makes KATO different from other ML systems?

1. **Deterministic**: Same inputs always produce same outputs (no randomness)
2. **Transparent**: All predictions are traceable to learned patterns
3. **Explainable**: Every prediction shows what, why, and how
4. **Multi-modal**: Processes text, vectors, and emotions together
5. **Temporal**: Understands sequences and time-ordered patterns

### When should I use KATO?

**Good Use Cases**:
- Chatbots and conversational AI
- Sequence prediction (workflows, user journeys)
- Pattern recognition in temporal data
- Recommendation systems
- Error diagnosis and resolution
- Context-aware applications

**Not Ideal For**:
- Image classification (use CNNs)
- Regression/continuous prediction (use traditional ML)
- Large-scale real-time inference (optimize first)

## Installation and Setup

### What are the minimum system requirements?

- **CPU**: 2+ cores
- **RAM**: 4GB available
- **Disk**: 10GB free space
- **Docker Desktop**: Latest stable version
- **OS**: macOS, Linux, or Windows with WSL2

See [Installation Guide](installation.md) for details.

### Do I need GPU for KATO?

No. KATO is CPU-optimized and runs efficiently without GPU.

### How do I install KATO?

```bash
git clone https://github.com/your-org/kato.git
cd kato
./start.sh
```

See [Installation Guide](installation.md) for complete instructions.

### Can I run KATO in production?

Yes. KATO supports:
- Docker Compose deployment
- Kubernetes deployment
- Multi-instance scaling
- Production monitoring

See [Docker Deployment](../operations/docker-deployment.md).

## Sessions and Data

### What's the difference between session_id and node_id?

| Aspect | session_id | node_id |
|--------|------------|---------|
| **Lifetime** | Temporary (hours) | Permanent |
| **Storage** | Redis (volatile) | Persistent database (patterns & vectors) |
| **Contains** | STM, emotives | Patterns, vectors |
| **Expires** | Yes (TTL) | No |

**Key Point**: `node_id` identifies your knowledge base, `session_id` is just a temporary connection to it.

### Do my patterns persist when session expires?

**Yes!** Patterns are permanently stored persistently.

- ✅ **Patterns (LTM)**: Preserved forever
- ✅ **Vectors**: Preserved
- ❌ **STM**: Lost (unless learned)
- ❌ **Current emotives**: Lost

Create a new session with same `node_id` to reconnect to your patterns.

### How long do sessions last?

Default: 1 hour (3600 seconds), configurable via `SESSION_TTL`.

**Auto-extend** (default): Each API call resets TTL
**Absolute timeout**: Disable auto-extend for fixed expiration

See [Session Management](session-management.md).

### Can multiple sessions share the same node_id?

**Yes!** Multiple sessions can connect to the same `node_id`:
- **Shared**: Learned patterns (LTM)
- **Isolated**: STM, emotives, configuration

Use case: Multi-user app where all users share trained patterns.

### How do I backup my data?

Contact your system administrator to backup pattern data. KATO stores patterns and vectors in persistent databases that should be included in regular backup procedures.

### How do I delete all data?

```bash
# Delete ALL data (WARNING: permanent)
docker compose down -v
```

For more granular data deletion, contact your system administrator.

## Patterns and Learning

### What's a pattern?

A **pattern** is a learned sequence of observations. It represents knowledge captured from your training data.

Example:
```
Pattern: [["morning", "coffee"], ["work", "code"], ["evening", "relax"]]
```

See [Pattern Learning](pattern-learning.md).

### How does KATO learn patterns?

1. Send observations to build STM
2. Call `/learn` endpoint (or auto-learn)
3. KATO converts STM to pattern
4. Pattern stored persistently with unique hash name

See [Pattern Learning](pattern-learning.md).

### What's the minimum pattern length?

**2 events** (observations). Single-event patterns are not meaningful for prediction.

### Can I learn non-sequential patterns?

Yes! Use single-event patterns for non-temporal associations:

```python
# User preference profile (non-temporal)
kato.observe(["user:alice", "theme:dark", "lang:python", "editor:vim"])
kato.learn()

# Later query by user
kato.observe(["user:alice"])
# Returns associated preferences
```

### Do patterns deduplicate automatically?

**Yes!** Patterns are content-addressed by hash. Learning the same pattern multiple times:
- Stores only once (same hash)
- Increments observation count
- Updates emotive rolling windows

### How many patterns can KATO handle?

**Tested up to billions**. Performance:
- **1K patterns**: Instant
- **100K patterns**: <100ms
- **1M+ patterns**: Requires optimization (indexing)

See [Performance Tuning](../operations/performance-tuning.md).

## Predictions

### How does KATO make predictions?

1. You send observations (current STM)
2. KATO searches LTM for matching patterns
3. Returns matches with context (past, present, future)
4. Ranked by information value (potential)

See [Predictions Guide](predictions.md).

### What's the difference between past, present, and future?

- **past**: What came before in the pattern
- **present**: Current matching events (complete)
- **future**: What's expected next
- **missing**: Expected but not observed
- **extras**: Observed but not expected

See [Predictions Guide](predictions.md#prediction-components).

### Why are my predictions empty?

Common causes:
1. **No matching patterns**: Nothing learned yet or wrong `node_id`
2. **Threshold too high**: Lower `recall_threshold` (default: 0.1)
3. **STM empty**: Send observations first
4. **Patterns missing**: Check database has patterns

**Debug**:
```bash
# Lower threshold
curl -X POST .../sessions -d '{"node_id": "...", "config": {"recall_threshold": 0.1}}'

# Check patterns via API
curl http://localhost:8000/sessions/{session_id}/patterns
```

### How do I improve prediction accuracy?

1. **Train more**: More observations = better patterns
2. **Adjust threshold**: Higher `recall_threshold` = stricter matching
3. **Use token matching**: Enable `use_token_matching: true` (default)
4. **Filter by confidence**: Use `predictions[i]['metrics']['confidence']`
5. **Provide more context**: Longer STM = better matching

### What's a good recall_threshold?

Depends on use case:
- **0.1** (default): Very permissive, fuzzy matching
- **0.3**: Balanced, partial matches OK
- **0.5**: Strict, majority overlap required
- **0.7+**: Very strict, near-exact matches

See [Configuration Guide](configuration.md#recall_threshold).

## Configuration

### How do I configure KATO?

Three levels:
1. **Environment variables** (.env file) - global
2. **Session config** (at creation) - per-session
3. **Runtime parameters** (API calls) - per-operation

See [Configuration Guide](configuration.md).

### What configuration should I use for production?

```bash
# .env
LOG_LEVEL=INFO
LOG_FORMAT=json
RECALL_THRESHOLD=0.3
SESSION_TTL=7200
SESSION_AUTO_EXTEND=true
KATO_USE_FAST_MATCHING=true
KATO_USE_INDEXING=true
```

See [Configuration Guide](configuration.md#production-configuration).

### Can I change configuration after session creation?

**Yes!**
```bash
curl -X PUT http://localhost:8000/sessions/{session_id}/config \
  -d '{"config": {"recall_threshold": 0.5}}'
```

**But**: Configuration is not persistent - lost when session expires.

## Performance

### How fast is KATO?

**Typical latencies** (1000 patterns, token matching):
- **Observe**: <10ms
- **Learn**: <50ms
- **Predictions**: <100ms

**At scale** (1M+ patterns):
- Enable indexing
- Use ClickHouse hybrid architecture
- Optimize `recall_threshold`

See [Performance Tuning](../operations/performance-tuning.md).

### Why are predictions slow?

Common causes:
1. **Too many patterns**: Enable indexing
2. **Low threshold**: Raises `recall_threshold`
3. **Character matching**: Switch to `use_token_matching: true`
4. **Large max_predictions**: Lower `max_predictions`

### Can KATO scale horizontally?

**Yes!** Multiple KATO instances can:
- Share persistent storage (read-only patterns)
- Have isolated sessions (Redis)
- Load balance via reverse proxy

See [Multi-Instance Architecture](../integration/multi-instance.md).

## Troubleshooting

### Session expired - how do I reconnect?

```python
try:
    kato.observe(["test"])
except KATOSessionError:
    # Reconnect with same node_id
    kato.create_session("my_app")
```

See [Session Management](session-management.md#handling-session-expiry).

### Container won't start

```bash
# Check logs
docker compose logs kato

# Common fixes:
# 1. Ensure databases running
docker compose up -d

# 2. Rebuild without cache
docker compose build --no-cache kato
./start.sh
```

See [Troubleshooting Guide](troubleshooting.md).

### Tests are failing

```bash
# Ensure services running
./start.sh
docker compose ps  # All should be "Up"

# Run tests
./run_tests.sh --no-start --no-stop

# Check specific test
python -m pytest tests/tests/unit/test_observations.py -v
```

See [Testing Guide](../developers/testing.md).

## Integration

### How do I integrate KATO with my app?

1. **Install KATO**: Docker Compose or Kubernetes
2. **Create Python client**: See [Python Client Guide](python-client.md)
3. **Create session**: Use unique `node_id` per tenant/user
4. **Send observations**: As events occur
5. **Get predictions**: When needed
6. **Learn patterns**: Periodically or auto-learn

### Can I use KATO with JavaScript/TypeScript?

Yes! KATO is REST API - use any HTTP client:

```javascript
// Create session
const response = await fetch('http://localhost:8000/sessions', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({node_id: 'my_app'})
});
const {session_id} = await response.json();

// Send observation
await fetch(`http://localhost:8000/sessions/${session_id}/observe`, {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({
    strings: ['hello', 'world'],
    vectors: [],
    emotives: {}
  })
});
```

### Does KATO support GraphQL?

No, REST API only. Use a GraphQL wrapper if needed.

### Can I run KATO serverless?

Not recommended. KATO requires:
- Persistent databases
- Stateful sessions (Redis)
- Continuous availability

Use containerized deployment instead.

## Advanced Topics

### What's the hybrid architecture?

KATO uses a hybrid architecture for billion-scale patterns with optimized read and write paths.

See [Hybrid Architecture](../HYBRID_ARCHITECTURE.md) for details.

### Can I use KATO for streaming data?

**Yes!** Enable auto-learning:

```bash
# .env
MAX_PATTERN_LENGTH=50  # Auto-learn every 50 events
STM_MODE=ROLLING       # Sliding window
```

### How do emotives work?

**Emotives** are key-value pairs representing emotional/contextual state:

```python
kato.observe(
    ["error", "timeout"],
    emotives={"urgency": 0.9, "confidence": 0.3}
)
```

Stored as rolling windows, returned as statistics in predictions.

See [Emotives Processing](../research/emotives-processing.md).

### What are vectors used for?

**Vectors** (embeddings) enable:
- Semantic similarity matching
- Image/audio pattern learning
- Hybrid symbolic+neural approaches

Example:
```python
import numpy as np
embedding = model.encode("hello world")  # [768-dim vector]
kato.observe(strings=["greeting"], vectors=[embedding.tolist()])
```

See [Vector Embeddings](../research/vector-embeddings.md).

## Getting Help

### Where can I find more documentation?

- **Start Here**: [docs/00-START-HERE.md](../00-START-HERE.md)
- **Quick Start**: [quick-start.md](quick-start.md)
- **API Reference**: [docs/reference/api/](../reference/api/)
- **GitHub Issues**: https://github.com/your-org/kato/issues

### How do I report a bug?

1. Check [Troubleshooting Guide](troubleshooting.md)
2. Search existing GitHub issues
3. Create new issue with:
   - KATO version
   - Steps to reproduce
   - Expected vs actual behavior
   - Logs (`docker compose logs kato`)

### How do I request a feature?

Open GitHub issue with:
- Use case description
- Desired behavior
- Example code/workflow

### Is KATO open source?

Check the repository license. Typically MIT or Apache 2.0.

---

**Last Updated**: November 2025
**KATO Version**: 3.0+
