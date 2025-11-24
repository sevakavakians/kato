# Design Patterns in KATO

Comprehensive guide to design patterns used throughout the KATO codebase.

## Overview

KATO leverages proven design patterns to achieve:
- **Maintainability**: Clear separation of concerns
- **Testability**: Easy to mock and test components
- **Scalability**: Components can be replaced or extended
- **Reliability**: Consistent error handling and state management

## Core Design Patterns

### 1. Dependency Injection

**Pattern**: Constructor-based dependency injection for loose coupling.

**Location**: Throughout `workers/` and `api/`

**Implementation**:
```python
# workers/kato_processor.py
class KatoProcessor:
    def __init__(
        self,
        name: str,
        processor_id: str,
        settings: Settings = None,  # Injected dependency
        **genome_manifest
    ):
        # Accept settings via dependency injection
        if settings is None:
            settings = get_settings()  # Fallback for compatibility
        self.settings = settings

        # Inject settings into sub-components
        self.pattern_processor = PatternProcessor(settings=self.settings)
        self.vector_processor = VectorProcessor(settings=self.settings)
```

**Benefits**:
- Easy testing with mock objects
- Configuration flexibility
- No global state dependencies

**Example Test**:
```python
def test_processor_with_custom_settings():
    """Test processor with injected settings."""
    mock_settings = Mock(spec=Settings)
    mock_settings.learning.recall_threshold = 0.5

    processor = KatoProcessor(
        name="test",
        processor_id="test_123",
        settings=mock_settings
    )

    assert processor.settings.learning.recall_threshold == 0.5
```

### 2. Adapter Pattern

**Pattern**: Unified interface for different storage backends.

**Location**: `storage/` module

**Implementation**:
```python
# storage/clickhouse_writer.py
class ClickHouseWriter:
    """Adapter for ClickHouse pattern storage."""

    def __init__(self, kb_id: str, settings: Settings):
        self.kb_id = kb_id
        self.client = Client(
            host=settings.clickhouse.host,
            port=settings.clickhouse.port,
            database=settings.clickhouse.database
        )

    async def store_pattern(self, pattern: Pattern) -> None:
        """Store pattern (unified interface)."""
        await self.patterns_table.insert([pattern.to_dict()])

    async def get_pattern(self, pattern_name: str) -> Optional[Pattern]:
        """Retrieve pattern (unified interface)."""
        result = await self.patterns_table.select_one(
            where=f"name = '{pattern_name}' AND kb_id = '{self.kb_id}'"
        )
        return Pattern.from_dict(result) if result else None

# storage/qdrant_manager.py
class QdrantManager:
    """Adapter for Qdrant vector storage."""

    def __init__(self, settings: Settings):
        self.client = QdrantClient(
            host=settings.database.qdrant_host,
            port=settings.database.qdrant_port
        )

    def store_vector(self, collection: str, vector: list[float], payload: dict):
        """Store vector (unified interface)."""
        self.client.upsert(
            collection_name=collection,
            points=[PointStruct(id=str(uuid4()), vector=vector, payload=payload)]
        )

    def search_vectors(self, collection: str, query: list[float], limit: int):
        """Search vectors (unified interface)."""
        return self.client.search(collection_name=collection, query_vector=query, limit=limit)
```

**Benefits**:
- Easy to swap storage backends
- Consistent API across different databases
- Simplified testing with mock adapters

**Usage**:
```python
# Workers don't care about storage implementation
pattern_processor.storage.store_pattern(pattern)  # Could be ClickHouse, Redis, etc.
vector_processor.storage.store_vector(vector)     # Could be Qdrant, Pinecone, etc.
```

### 3. Strategy Pattern

**Pattern**: Configurable algorithms for pattern matching.

**Location**: `searches/pattern_search.py`

**Implementation**:
```python
class SimilarityStrategy(ABC):
    """Abstract strategy for similarity calculation."""

    @abstractmethod
    def calculate_similarity(
        self,
        pattern_event: list[str],
        query_event: list[str]
    ) -> float:
        pass

class TokenLevelStrategy(SimilarityStrategy):
    """Token-level matching (default, 9x faster)."""

    def calculate_similarity(
        self,
        pattern_event: list[str],
        query_event: list[str]
    ) -> float:
        pattern_set = set(pattern_event)
        query_set = set(query_event)
        intersection = pattern_set & query_set
        union = pattern_set | query_set
        return len(intersection) / len(union) if union else 0.0

class CharacterLevelStrategy(SimilarityStrategy):
    """Character-level matching (fuzzy text)."""

    def calculate_similarity(
        self,
        pattern_event: list[str],
        query_event: list[str]
    ) -> float:
        from rapidfuzz import fuzz
        pattern_str = " ".join(pattern_event)
        query_str = " ".join(query_event)
        return fuzz.ratio(pattern_str, query_str) / 100.0

class PatternSearcher:
    """Context that uses strategy."""

    def __init__(self, use_token_matching: bool = True):
        # Select strategy based on configuration
        if use_token_matching:
            self.similarity_strategy = TokenLevelStrategy()
        else:
            self.similarity_strategy = CharacterLevelStrategy()

    def search_patterns(self, query_stm: list[list[str]]) -> list[Pattern]:
        for pattern in candidates:
            # Delegate to strategy
            similarity = self.similarity_strategy.calculate_similarity(
                pattern.events[0],
                query_stm[0]
            )
```

**Benefits**:
- Easy to add new matching algorithms
- Runtime algorithm selection
- Clear separation of algorithm logic

### 4. Repository Pattern

**Pattern**: Abstraction over data access logic.

**Location**: `storage/` and `informatics/knowledge_base.py`

**Implementation**:
```python
# informatics/knowledge_base.py
class KnowledgeBaseRepository:
    """Repository for pattern data access."""

    def __init__(self, storage: ClickHouseWriter):
        self.storage = storage

    async def find_by_length(self, min_length: int, max_length: int) -> list[Pattern]:
        """Find patterns by length range."""
        return await self.storage.find_patterns(
            where=f"length >= {min_length} AND length <= {max_length}"
        )

    async def find_by_observation_count(self, min_count: int) -> list[Pattern]:
        """Find frequently observed patterns."""
        return await self.storage.find_patterns(
            where=f"observation_count >= {min_count}"
        )

    async def increment_observation_count(self, pattern_name: str) -> None:
        """Increment pattern observation counter."""
        await self.storage.update_pattern(
            pattern_name,
            updates={"observation_count": "observation_count + 1"}
        )
```

**Benefits**:
- Business logic separated from storage details
- Easy to change query strategies
- Simplified testing with repository mocks

### 5. Singleton Pattern

**Pattern**: Single shared instance for configuration and connections.

**Location**: `config/settings.py`

**Implementation**:
```python
# config/settings.py
from functools import lru_cache

@lru_cache()
def get_settings() -> Settings:
    """Get singleton Settings instance."""
    return Settings()

# Usage throughout codebase
settings = get_settings()  # Always returns same instance
```

**Benefits**:
- Single source of truth for configuration
- Environment variables parsed only once
- Reduced memory footprint

**Note**: Thread-safe due to Python's GIL and `lru_cache`.

### 6. Factory Pattern

**Pattern**: Object creation abstraction for sessions and processors.

**Location**: `sessions/session_manager.py`

**Implementation**:
```python
# sessions/session_manager.py
class SessionManager:
    """Factory for creating and managing sessions."""

    async def create_session(
        self,
        node_id: str,
        config: dict = None,
        metadata: dict = None,
        ttl_seconds: int = 3600
    ) -> Session:
        """Factory method for session creation."""

        # Generate unique session ID
        session_id = f"session_{uuid4().hex}"

        # Create configuration
        session_config = SessionConfiguration(config or {})

        # Create KatoProcessor
        processor = KatoProcessor(
            name=node_id,
            processor_id=session_id,
            settings=self.settings
        )

        # Create session object
        session = Session(
            session_id=session_id,
            node_id=node_id,
            processor=processor,
            session_config=session_config,
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds),
            metadata=metadata or {}
        )

        # Store in Redis
        await self._store_session(session)

        return session
```

**Benefits**:
- Centralized creation logic
- Consistent initialization
- Easy to add creation hooks (logging, monitoring)

### 7. Observer Pattern

**Pattern**: Event-driven updates for pattern observation counts.

**Location**: `workers/pattern_processor.py`

**Implementation**:
```python
class PatternObserver(ABC):
    """Abstract observer for pattern events."""

    @abstractmethod
    def on_pattern_observed(self, pattern_name: str) -> None:
        pass

class ObservationCountUpdater(PatternObserver):
    """Updates observation counts in database."""

    def __init__(self, storage: ClickHouseWriter):
        self.storage = storage

    def on_pattern_observed(self, pattern_name: str) -> None:
        self.storage.increment_observation_count(pattern_name)

class MetricsCacheUpdater(PatternObserver):
    """Updates metrics cache for analytics."""

    def __init__(self, cache: MetricsCache):
        self.cache = cache

    def on_pattern_observed(self, pattern_name: str) -> None:
        self.cache.increment_pattern_frequency(pattern_name)

class PatternProcessor:
    """Subject that notifies observers."""

    def __init__(self):
        self.observers: list[PatternObserver] = []

    def add_observer(self, observer: PatternObserver) -> None:
        self.observers.append(observer)

    def _notify_pattern_observed(self, pattern_name: str) -> None:
        for observer in self.observers:
            observer.on_pattern_observed(pattern_name)

    def match_pattern(self, pattern: Pattern) -> None:
        # ... matching logic ...
        self._notify_pattern_observed(pattern.pattern_name)
```

**Benefits**:
- Decoupled event handling
- Easy to add new event listeners
- Clear separation of concerns

### 8. Facade Pattern

**Pattern**: Simplified interface over complex subsystems.

**Location**: `workers/kato_processor.py`

**Implementation**:
```python
class KatoProcessor:
    """Facade providing simplified API over complex subsystems."""

    def __init__(self, name: str, processor_id: str, settings: Settings = None):
        # Initialize complex subsystems
        self.memory_manager = MemoryManager(...)
        self.pattern_processor = PatternProcessor(...)
        self.vector_processor = VectorProcessor(...)
        self.observation_processor = ObservationProcessor(...)
        self.pattern_operations = PatternOperations(...)

    def observe(self, data: dict) -> dict:
        """Simplified observation API (hides subsystem complexity)."""
        # Delegates to multiple subsystems
        processed = self.observation_processor.process_observation(data)
        self.memory_manager.add_to_stm(processed['event'])

        # Auto-learn trigger
        if self._should_auto_learn():
            self.learn()

        return {"observed": True, "stm_length": len(self.memory_manager.stm)}

    def learn(self) -> Pattern:
        """Simplified learning API."""
        stm = self.memory_manager.get_stm()
        emotives = self.memory_manager.get_emotives()
        return self.pattern_processor.learn_pattern(stm, emotives)

    def get_predictions(self, threshold: float = None) -> list[dict]:
        """Simplified prediction API."""
        stm = self.memory_manager.get_stm()
        threshold = threshold or self.settings.learning.recall_threshold
        return self.pattern_processor.search_patterns(stm, threshold)
```

**Benefits**:
- Simple API for external consumers
- Internal complexity hidden
- Easy to refactor subsystems without breaking API

### 9. Command Pattern

**Pattern**: Encapsulate operations as objects.

**Location**: `api/endpoints/sessions.py`

**Implementation**:
```python
class Command(ABC):
    """Abstract command."""

    @abstractmethod
    async def execute(self) -> dict:
        pass

class ObserveCommand(Command):
    """Command to observe data."""

    def __init__(self, processor: KatoProcessor, data: dict):
        self.processor = processor
        self.data = data

    async def execute(self) -> dict:
        return self.processor.observe(self.data)

class LearnCommand(Command):
    """Command to learn pattern."""

    def __init__(self, processor: KatoProcessor):
        self.processor = processor

    async def execute(self) -> dict:
        pattern = self.processor.learn()
        return pattern.to_dict()

class PredictCommand(Command):
    """Command to get predictions."""

    def __init__(self, processor: KatoProcessor, threshold: float):
        self.processor = processor
        self.threshold = threshold

    async def execute(self) -> dict:
        predictions = self.processor.get_predictions(self.threshold)
        return {"predictions": predictions}

# API endpoint as command invoker
@router.post("/sessions/{session_id}/observe")
async def observe(session_id: str, data: ObservationData):
    processor = await get_processor(session_id)
    command = ObserveCommand(processor, data.dict())
    return await command.execute()
```

**Benefits**:
- Operations can be queued, logged, or undone
- Easy to add middleware (logging, validation)
- Consistent error handling

### 10. Builder Pattern

**Pattern**: Step-by-step construction of complex objects.

**Location**: `representations/prediction.py`

**Implementation**:
```python
class PredictionBuilder:
    """Builder for Prediction objects."""

    def __init__(self):
        self._past = []
        self._present = []
        self._future = []
        self._missing = []
        self._extras = []
        self._metrics = {}

    def set_past(self, events: list[list[str]]) -> 'PredictionBuilder':
        self._past = events
        return self

    def set_present(self, events: list[list[str]]) -> 'PredictionBuilder':
        self._present = events
        return self

    def set_future(self, events: list[list[str]]) -> 'PredictionBuilder':
        self._future = events
        return self

    def calculate_missing(self, pattern_events: list[list[str]], stm: list[list[str]]):
        """Calculate missing symbols."""
        self._missing = self._calculate_missing_impl(pattern_events, stm)
        return self

    def calculate_extras(self, stm: list[list[str]], pattern_events: list[list[str]]):
        """Calculate extra symbols."""
        self._extras = self._calculate_extras_impl(stm, pattern_events)
        return self

    def set_metrics(
        self,
        similarity: float,
        potential: float,
        confidence: float,
        evidence: float
    ) -> 'PredictionBuilder':
        self._metrics = {
            "similarity": similarity,
            "potential": potential,
            "confidence": confidence,
            "evidence": evidence
        }
        return self

    def build(self) -> Prediction:
        """Construct final Prediction object."""
        return Prediction(
            past=self._past,
            present=self._present,
            future=self._future,
            missing=self._missing,
            extras=self._extras,
            **self._metrics
        )

# Usage
prediction = (PredictionBuilder()
    .set_past(past_events)
    .set_present(present_events)
    .set_future(future_events)
    .calculate_missing(pattern.events, stm)
    .calculate_extras(stm, pattern.events)
    .set_metrics(similarity=0.85, potential=0.72, confidence=0.91, evidence=0.15)
    .build()
)
```

**Benefits**:
- Clear construction steps
- Immutable final object
- Fluent interface for readability

## Architectural Patterns

### Layered Architecture

**Pattern**: Clear separation of concerns across layers.

```
┌─────────────────────────────────────┐
│  API Layer (FastAPI)                │  ← HTTP requests
│  - Request validation               │
│  - Response formatting              │
│  - Error handling                   │
└──────────────┬──────────────────────┘
               │
┌──────────────▼──────────────────────┐
│  Service Layer (KatoProcessor)      │  ← Business logic
│  - Orchestration                    │
│  - Workflow coordination            │
│  - Transaction management           │
└──────────────┬──────────────────────┘
               │
┌──────────────▼──────────────────────┐
│  Domain Layer (Workers)             │  ← Core logic
│  - Pattern processing               │
│  - Memory management                │
│  - Vector operations                │
└──────────────┬──────────────────────┘
               │
┌──────────────▼──────────────────────┐
│  Data Access Layer (Storage)        │  ← Database operations
│  - ClickHouse adapter               │
│  - Qdrant adapter                   │
│  - Redis adapter                    │
└─────────────────────────────────────┘
```

### Hexagonal Architecture (Ports and Adapters)

**Pattern**: Application core independent of external systems.

```
         ┌─────────────────────────┐
         │   Application Core      │
         │   (workers/)            │
         │                         │
         │  - KatoProcessor        │
         │  - PatternProcessor     │
         │  - MemoryManager        │
         └───────────┬─────────────┘
                     │
        ┌────────────┼────────────┐
        │            │            │
   ┌────▼───┐   ┌───▼────┐   ┌───▼────┐
   │ HTTP   │   │Storage │   │Vector  │
   │ Port   │   │ Port   │   │ Port   │
   └────┬───┘   └───┬────┘   └───┬────┘
        │           │            │
   ┌────▼───┐   ┌───▼────────┐   ┌───▼────┐
   │FastAPI │   │ClickHouse  │   │Qdrant  │
   │Adapter │   │  Adapter   │   │Adapter │
   └────────┘   └────────────┘   └────────┘
```

## Anti-Patterns to Avoid

### ❌ God Object
**Bad**: Single class doing everything
```python
class KatoProcessor:
    def observe(self): ...
    def learn(self): ...
    def predict(self): ...
    def store_in_clickhouse(self): ...  # ❌ Storage responsibility
    def search_vectors(self): ...       # ❌ Vector search responsibility
    def calculate_metrics(self): ...    # ❌ Metrics responsibility
```

**Good**: Separation of concerns
```python
class KatoProcessor:
    def __init__(self):
        self.storage = StorageAdapter()       # Delegate storage
        self.vector_search = VectorSearcher() # Delegate vector ops
        self.metrics = MetricsCalculator()    # Delegate metrics
```

### ❌ Tight Coupling
**Bad**: Direct dependencies on concrete classes
```python
class PatternProcessor:
    def __init__(self):
        self.storage = ClickHouseStorage()  # ❌ Concrete dependency
```

**Good**: Depend on abstractions
```python
class PatternProcessor:
    def __init__(self, storage: StorageInterface):  # ✓ Abstract interface
        self.storage = storage
```

### ❌ Circular Dependencies
**Bad**: Modules importing each other
```python
# workers/pattern_processor.py
from workers.memory_manager import MemoryManager  # ❌

# workers/memory_manager.py
from workers.pattern_processor import PatternProcessor  # ❌ Circular!
```

**Good**: Introduce abstraction layer
```python
# workers/interfaces.py
class MemoryInterface(ABC): ...

# workers/pattern_processor.py
from workers.interfaces import MemoryInterface  # ✓
```

## Related Documentation

- [Code Organization](code-organization.md)
- [Architecture Overview](architecture.md)
- [Adding Endpoints](adding-endpoints.md)
- [Testing Guide](testing.md)

---

**Last Updated**: November 2025
**KATO Version**: 3.0+
