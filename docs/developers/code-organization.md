# Code Organization Guide

Complete guide to KATO codebase structure and module organization.

## Project Structure

```
kato/
├── kato/                      # Main package
│   ├── api/                  # FastAPI endpoints and routing
│   ├── config/               # Configuration management
│   ├── exceptions/           # Custom exception classes
│   ├── filters/              # Pattern filtering logic
│   ├── gpu/                  # GPU acceleration (experimental)
│   ├── informatics/          # Information theory utilities
│   ├── representations/      # Data representations
│   ├── searches/             # Pattern search algorithms
│   ├── sessions/             # Session management
│   ├── storage/              # Database adapters
│   ├── utils/                # General utilities
│   ├── websocket/            # WebSocket handlers
│   └── workers/              # Core processing logic
├── tests/                    # Test suite
│   ├── fixtures/            # Test fixtures and helpers
│   ├── unit/                # Unit tests
│   ├── integration/         # Integration tests
│   └── api/                 # API endpoint tests
├── docs/                     # Documentation
├── scripts/                  # Utility scripts
├── docker-compose.yml        # Docker services
├── Dockerfile               # KATO container image
├── requirements.txt         # Python dependencies
├── requirements.lock        # Locked dependencies
├── pyproject.toml           # Python project config
└── start.sh                # Service startup script
```

## Core Modules

### kato/api/ - API Layer

FastAPI application and endpoint definitions.

```
api/
├── __init__.py
├── main.py                  # FastAPI app initialization
├── dependencies.py          # Dependency injection
├── middleware.py            # Custom middleware
└── endpoints/
    ├── __init__.py
    ├── sessions.py          # Session management endpoints
    └── kato_ops.py          # Utility endpoints
```

**Key Files**:
- **main.py**: App creation, CORS, middleware setup
- **sessions.py**: `/sessions/*` endpoints
- **kato_ops.py**: `/health`, `/status` endpoints

**Example**:
```python
# api/main.py
app = FastAPI(title="KATO API", version="3.0")
app.include_router(sessions_router, prefix="/sessions")
app.include_router(ops_router)
```

### kato/workers/ - Core Processing

Main processing logic and orchestration.

```
workers/
├── __init__.py
├── kato_processor.py        # Main controller
├── memory_manager.py        # STM/LTM management
├── pattern_processor.py     # Pattern learning/matching
├── vector_processor.py      # Vector operations
├── observation_processor.py # Input processing
└── pattern_operations.py    # Pattern utilities
```

**Key Files**:
- **kato_processor.py**: Orchestrates all operations, main entry point
- **memory_manager.py**: Manages short-term and long-term memory
- **pattern_processor.py**: Pattern learning, matching, prediction
- **vector_processor.py**: Vector embedding processing
- **observation_processor.py**: Input validation and processing

**Relationships**:
```
KatoProcessor
├─> MemoryManager (STM operations)
├─> PatternProcessor (learning/matching)
├─> VectorProcessor (vector handling)
└─> ObservationProcessor (input processing)
```

### kato/storage/ - Storage Layer

Database adapters and storage abstractions.

```
storage/
├── __init__.py
├── super_knowledge_base.py  # MongoDB adapter
├── qdrant_manager.py        # Qdrant adapter
├── redis_writer.py          # Redis adapter (sessions)
├── aggregation_pipelines.py # MongoDB aggregations
├── clickhouse_client.py     # ClickHouse adapter (hybrid)
└── metrics_cache.py         # Metrics caching
```

**Key Files**:
- **super_knowledge_base.py**: Pattern storage in MongoDB
- **qdrant_manager.py**: Vector storage in Qdrant
- **redis_writer.py**: Session and cache management
- **clickhouse_client.py**: Read-optimized pattern queries (hybrid architecture)

**Pattern**:
All storage modules follow adapter pattern with consistent interfaces.

### kato/searches/ - Search and Matching

Pattern search algorithms and vector similarity.

```
searches/
├── __init__.py
├── pattern_search.py        # Main pattern search
├── similarity_calculator.py # Similarity metrics
└── vector_search.py         # Vector similarity search
```

**Key Files**:
- **pattern_search.py**: RapidFuzz-based pattern matching
- **similarity_calculator.py**: Token/character-level similarity
- **vector_search.py**: Qdrant integration for vector search

**Algorithms**:
- Token-level matching (default, 9x faster)
- Character-level matching (fuzzy text)
- Vector cosine similarity

### kato/sessions/ - Session Management

Session lifecycle and state management.

```
sessions/
├── __init__.py
├── session_manager.py       # Session CRUD operations
└── session_config.py        # Session configuration
```

**Key Files**:
- **session_manager.py**: Create, retrieve, update, delete sessions
- **session_config.py**: Per-session configuration management

**Storage**: Redis with TTL-based expiration.

### kato/config/ - Configuration

Centralized configuration using Pydantic.

```
config/
├── __init__.py
├── settings.py              # Main settings (Pydantic)
└── session_config.py        # Session-specific config
```

**Key Files**:
- **settings.py**: All environment variables and configuration
  - `ServiceConfig`, `LoggingConfig`, `DatabaseConfig`
  - `LearningConfig`, `ProcessingConfig`, `PerformanceConfig`
  - `SessionConfig`, `APIConfig`

**Usage**:
```python
from kato.config import get_settings

settings = get_settings()
mongo_url = settings.database.mongo_url
threshold = settings.learning.recall_threshold
```

### kato/informatics/ - Information Theory

Information-theoretic calculations and metrics.

```
informatics/
├── __init__.py
├── knowledge_base.py        # Knowledge base operations
├── normalized_entropy.py    # Entropy calculations
├── potential_function.py    # Predictive information
└── metrics.py              # Various metrics
```

**Key Files**:
- **normalized_entropy.py**: Shannon entropy, information content
- **potential_function.py**: Predictive potential calculations
- **metrics.py**: Similarity, confidence, evidence metrics

**Usage**:
```python
from kato.informatics import calculate_potential

potential = calculate_potential(
    past_entropy=0.5,
    future_entropy=0.8,
    evidence=0.9
)
```

### kato/representations/ - Data Models

Core data structures and representations.

```
representations/
├── __init__.py
├── pattern.py               # Pattern class
├── vector_object.py         # Vector representation
└── prediction.py            # Prediction structure
```

**Key Classes**:
```python
# Pattern representation
class Pattern:
    pattern_name: str
    length: int
    events: list[list[str]]
    emotive_profile: dict
    metadata: dict

# Prediction structure
class Prediction:
    past: list[list[str]]
    present: list[list[str]]
    future: list[list[str]]
    missing: list[list[str]]
    extras: list[list[str]]
    similarity: float
    metrics: dict
```

### kato/exceptions/ - Exception Hierarchy

Custom exception classes.

```
exceptions/
├── __init__.py
└── kato_exceptions.py       # All custom exceptions
```

**Hierarchy**:
```python
KatoException (base)
├── PatternNotFoundError
├── SessionExpiredError
├── InvalidInputError
├── StorageError
│   ├── MongoDBError
│   ├── QdrantError
│   └── RedisError
└── ProcessingError
    ├── LearningError
    └── PredictionError
```

### kato/utils/ - Utilities

General-purpose utility functions.

```
utils/
├── __init__.py
├── hashing.py               # SHA1 hashing for pattern names
├── sorting.py               # Alphanumeric sorting
├── validation.py            # Input validation
└── logging_utils.py         # Logging helpers
```

### kato/filters/ - Pattern Filtering

Pattern filtering and selection logic.

```
filters/
├── __init__.py
├── threshold_filter.py      # Threshold-based filtering
└── ranking_filter.py        # Ranking and sorting
```

### kato/websocket/ - WebSocket Support

Real-time communication handlers (optional feature).

```
websocket/
├── __init__.py
└── handler.py               # WebSocket connection handler
```

## Test Organization

### tests/ Structure

```
tests/
├── __init__.py
├── conftest.py              # Pytest configuration
├── fixtures/
│   ├── __init__.py
│   ├── kato_fixtures.py    # KATO test fixtures
│   └── test_helpers.py     # Test helper functions
├── unit/                    # Unit tests (fast, isolated)
│   ├── test_observations.py
│   ├── test_patterns.py
│   ├── test_predictions.py
│   ├── test_memory.py
│   └── test_sessions.py
├── integration/             # Integration tests (full stack)
│   ├── test_workflow.py
│   ├── test_persistence.py
│   └── test_multi_modal.py
└── api/                     # API endpoint tests
    ├── test_session_endpoints.py
    ├── test_observation_endpoints.py
    └── test_prediction_endpoints.py
```

### Test Patterns

**Unit Test Example**:
```python
# tests/unit/test_observations.py
def test_observe_single_string(kato_processor):
    """Test observing single string."""
    result = kato_processor.observe({"strings": ["test"]})
    assert result["strings"] == ["test"]
    assert kato_processor.get_stm_length() == 1
```

**Integration Test Example**:
```python
# tests/integration/test_workflow.py
def test_full_learn_predict_workflow(kato_client):
    """Test complete workflow."""
    # Observe
    kato_client.observe(["hello", "world"])
    kato_client.observe(["foo", "bar"])

    # Learn
    pattern = kato_client.learn()
    assert pattern["pattern_name"].startswith("PTN|")

    # Predict
    kato_client.clear_stm()
    kato_client.observe(["hello", "world"])
    predictions = kato_client.get_predictions()
    assert len(predictions["predictions"]) > 0
```

## Module Dependencies

### Import Graph

```
api/
 └─> workers/ (KatoProcessor)
      └─> storage/ (SuperKnowledgeBase, QdrantManager)
      └─> searches/ (PatternSearcher)
      └─> informatics/ (metrics)
      └─> representations/ (Pattern, Prediction)
      └─> config/ (Settings)
```

**Rules**:
1. API layer depends on workers
2. Workers depend on storage and searches
3. Storage modules are independent
4. No circular dependencies

### Import Best Practices

```python
# Good - absolute imports
from kato.workers.kato_processor import KatoProcessor
from kato.storage.super_knowledge_base import SuperKnowledgeBase

# Good - module-level imports
from kato.workers import KatoProcessor
from kato.storage import SuperKnowledgeBase

# Avoid - relative imports for clarity
from ..workers import KatoProcessor  # Less clear
```

## Configuration Files

### Project-Level Config

**pyproject.toml**:
```toml
[tool.black]
line-length = 100
target-version = ['py310']

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]

[tool.ruff]
line-length = 100
select = ["E", "F", "I"]
```

**requirements.txt**:
```
fastapi==0.104.1
uvicorn[standard]==0.24.0
pymongo==4.5.0
qdrant-client==1.6.4
redis==5.0.1
pydantic==2.5.0
rapidfuzz==3.5.2
```

## Naming Conventions

### Files and Modules

- **Modules**: `lowercase_with_underscores.py`
- **Classes**: `PascalCase`
- **Functions**: `lowercase_with_underscores()`
- **Constants**: `UPPERCASE_WITH_UNDERSCORES`

### Directory Structure Patterns

- **Plural for collections**: `workers/`, `searches/`, `exceptions/`
- **Singular for singletons**: `config/`, `utils/`
- **Verb-based for operations**: `filters/`, `searches/`

## Extension Points

### Adding New Functionality

**New API Endpoint**:
1. Add endpoint to `api/endpoints/`
2. Create request/response models (Pydantic)
3. Implement logic in `workers/`
4. Add tests in `tests/api/`

**New Storage Backend**:
1. Create adapter in `storage/`
2. Implement storage interface
3. Update configuration in `config/`
4. Add connection management

**New Search Algorithm**:
1. Create module in `searches/`
2. Implement search interface
3. Integrate with `PatternProcessor`
4. Add performance tests

## Code Navigation Tips

### Finding Functionality

**Want to understand...**
- Pattern learning → `workers/pattern_processor.py::learn_pattern()`
- Pattern matching → `searches/pattern_search.py::search()`
- Session creation → `sessions/session_manager.py::create_session()`
- API routing → `api/main.py` + `api/endpoints/`
- Configuration → `config/settings.py`

### IDE Navigation

**VS Code**:
- `Cmd+P`: Quick file open
- `Cmd+Shift+O`: Symbol in file
- `F12`: Go to definition
- `Shift+F12`: Find all references

**PyCharm**:
- `Cmd+Shift+O`: Find file
- `Cmd+O`: Find class
- `Cmd+B`: Go to declaration
- `Cmd+Alt+F7`: Find usages

## Related Documentation

- [Architecture Overview](architecture.md)
- [Development Setup](development-setup.md)
- [Code Style Guide](code-style.md)
- [Adding Endpoints](adding-endpoints.md)

---

**Last Updated**: November 2025
**KATO Version**: 3.0+
