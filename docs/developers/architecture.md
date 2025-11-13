# KATO Architecture Overview

Comprehensive architectural guide for KATO developers.

## System Overview

KATO (Knowledge Abstraction for Traceable Outcomes) is a deterministic memory and prediction system built on modern async Python with FastAPI. It processes multi-modal observations (text, vectors, emotions) and makes temporal predictions while maintaining complete transparency.

### Key Architectural Principles

1. **Deterministic**: Same inputs always produce same outputs
2. **Transparent**: All predictions traceable to learned patterns
3. **Isolated**: Sessions and nodes completely separated
4. **Scalable**: Horizontal scaling via multiple instances
5. **Async**: Non-blocking I/O throughout

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────┐
│                      HTTP Clients                        │
│              (curl, Python, JavaScript, etc.)            │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│                   FastAPI Service                        │
│  ┌──────────────────────────────────────────────────┐  │
│  │  REST Endpoints  │  WebSocket  │  Middleware     │  │
│  │  /sessions       │  /ws        │  CORS/Logging   │  │
│  └──────────────────────────────────────────────────┘  │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│              KatoProcessor (Per Session)                 │
│  ┌──────────────┬──────────────┬──────────────┐        │
│  │ Memory       │ Pattern      │ Vector       │        │
│  │ Manager      │ Processor    │ Processor    │        │
│  └──────────────┴──────────────┴──────────────┘        │
└────────┬───────────────────┬───────────────────────────┘
         │                   │
         ▼                   ▼
┌─────────────────┐  ┌─────────────────┐  ┌──────────────┐
│   MongoDB       │  │    Qdrant       │  │    Redis     │
│   (Patterns)    │  │   (Vectors)     │  │  (Sessions)  │
└─────────────────┘  └─────────────────┘  └──────────────┘
```

## Component Details

### 1. API Layer (FastAPI)

**Location**: `kato/api/`

#### FastAPI Application

```python
# kato/api/main.py
app = FastAPI(
    title="KATO API",
    version="3.0",
    docs_url="/docs",
    redoc_url="/redoc"
)
```

**Features**:
- Automatic OpenAPI documentation
- Async request handlers
- Pydantic request/response validation
- CORS middleware
- Request logging with trace IDs

#### Endpoints

**Session Management** (`api/endpoints/sessions.py`):
```
POST   /sessions                    # Create session
GET    /sessions/{session_id}       # Get session info
DELETE /sessions/{session_id}       # Delete session
PUT    /sessions/{session_id}/config # Update config
```

**Operations** (`api/endpoints/sessions.py`):
```
POST   /sessions/{session_id}/observe    # Send observation
POST   /sessions/{session_id}/learn      # Learn pattern
GET    /sessions/{session_id}/predictions # Get predictions
GET    /sessions/{session_id}/stm        # View STM
POST   /sessions/{session_id}/clear-stm  # Clear STM
```

**Utility** (`api/endpoints/kato_ops.py`):
```
GET    /health                      # Health check
GET    /status                      # System status
```

#### Request Flow

```python
@app.post("/sessions/{session_id}/observe")
async def observe(
    session_id: str,
    observation: ObservationRequest
) -> ObservationResponse:
    """Process observation."""
    # 1. Validate request (Pydantic)
    # 2. Get or create processor
    processor = await get_processor(session_id)
    # 3. Process observation
    result = processor.observe(observation.dict())
    # 4. Return response
    return ObservationResponse(**result)
```

### 2. Core Processing Layer

**Location**: `kato/workers/`

#### KatoProcessor

**File**: `kato/workers/kato_processor.py`

Main controller coordinating all operations:

```python
class KatoProcessor:
    """Main KATO processing engine."""

    def __init__(self, node_id: str, config: SessionConfig):
        self.node_id = node_id
        self.config = config
        self.memory_manager = MemoryManager()
        self.pattern_processor = PatternProcessor(...)
        self.vector_processor = VectorProcessor(...)

    def observe(self, data: dict) -> dict:
        """Process observation."""
        # 1. Validate input
        # 2. Process strings/vectors/emotives
        # 3. Update STM
        # 4. Check auto-learn trigger
        # 5. Return response

    def learn(self) -> Pattern:
        """Learn pattern from STM."""
        # 1. Get STM contents
        # 2. Create pattern
        # 3. Store in LTM
        # 4. Update indices
        # 5. Return pattern

    def get_predictions(self) -> list[dict]:
        """Get predictions from STM."""
        # 1. Search patterns matching STM
        # 2. Calculate metrics
        # 3. Rank results
        # 4. Format predictions
        # 5. Return top N
```

**Lifecycle**:
1. Created per session (on-demand)
2. Cached in memory while session active
3. Released when session expires

#### MemoryManager

**File**: `kato/workers/memory_manager.py`

Manages STM and LTM operations:

```python
class MemoryManager:
    """Manages short and long-term memory."""

    def __init__(self):
        self.stm: deque[list[str]] = deque()  # Efficient FIFO
        self.emotives: dict[str, list[float]] = {}

    def add_to_stm(self, event: list[str]) -> None:
        """Add event to STM."""
        self.stm.append(event)

    def clear_stm(self) -> None:
        """Clear short-term memory."""
        self.stm.clear()

    def get_stm(self) -> list[list[str]]:
        """Get STM contents."""
        return list(self.stm)
```

**STM Structure**:
```python
# Example STM
stm = [
    ["coffee", "morning"],      # Event 1
    ["commute", "train"],       # Event 2
    ["arrive", "work"]          # Event 3
]
```

#### PatternProcessor

**File**: `kato/workers/pattern_processor.py`

Handles pattern learning and matching:

```python
class PatternProcessor:
    """Pattern recognition and matching."""

    def learn_pattern(self, stm: list[list[str]]) -> Pattern:
        """Learn pattern from STM."""
        # 1. Validate STM (min 2 events)
        # 2. Generate pattern hash
        # 3. Create Pattern object
        # 4. Store in MongoDB
        # 5. Update indices
        return pattern

    def search_patterns(
        self,
        query: list[list[str]],
        threshold: float
    ) -> list[Pattern]:
        """Find matching patterns."""
        # 1. Query MongoDB for candidates
        # 2. Calculate similarity scores
        # 3. Filter by threshold
        # 4. Rank by potential
        # 5. Return matches
```

#### VectorProcessor

**File**: `kato/workers/vector_processor.py`

Processes vector embeddings:

```python
class VectorProcessor:
    """Vector embedding operations."""

    def process_vectors(
        self,
        vectors: list[list[float]]
    ) -> list[str]:
        """Convert vectors to symbol names."""
        # 1. Validate dimensions (768)
        # 2. Generate hash-based names
        # 3. Store in Qdrant
        # 4. Return vector names (VCTR|hash)

    def search_similar(
        self,
        query_vector: list[float],
        limit: int = 100
    ) -> list[tuple[str, float]]:
        """Find similar vectors."""
        # 1. Query Qdrant
        # 2. Get top N by cosine similarity
        # 3. Return (vector_name, score) tuples
```

### 3. Storage Layer

**Location**: `kato/storage/`

#### MongoDB (SuperKnowledgeBase)

**File**: `kato/storage/super_knowledge_base.py`

**Database Structure**:
```
MongoDB Server
├── node_my_app_kato/          # Database per node_id
│   ├── patterns               # Learned patterns
│   ├── pattern_metadata       # Pattern statistics
│   └── global_metadata        # Node metadata
└── node_other_app_kato/
    └── ...
```

**Pattern Document**:
```javascript
{
  _id: "PTN|a1b2c3d4e5f6",
  length: 3,
  events: [
    ["coffee", "morning"],
    ["commute", "train"],
    ["arrive", "work"]
  ],
  emotive_profile: {
    energy: [[-0.2], [0.0], [0.5]]
  },
  metadata: {},
  created_at: ISODate("2025-11-13T10:00:00Z"),
  updated_at: ISODate("2025-11-13T10:30:00Z"),
  observation_count: 15
}
```

**Key Operations**:
```python
# Store pattern
kb.store_pattern(pattern)

# Find patterns by ID
pattern = kb.get_pattern("PTN|abc123")

# Query patterns
patterns = kb.find_patterns({"length": {"$lte": 10}})

# Update observation count
kb.increment_observation_count("PTN|abc123")
```

#### Qdrant (Vector Store)

**File**: `kato/storage/qdrant_manager.py`

**Collection Structure**:
```
Qdrant Server
├── vectors_my_app             # Collection per node_id
│   ├── Point 1 (vector + payload)
│   ├── Point 2
│   └── ...
└── vectors_other_app
    └── ...
```

**Vector Point**:
```python
{
    "id": "uuid-...",
    "vector": [0.1, 0.2, ..., 0.768],  # 768 dimensions
    "payload": {
        "pattern_name": "PTN|abc123",
        "event_index": 0,
        "vector_name": "VCTR|x1y2z3"
    }
}
```

**Key Operations**:
```python
# Store vector
qdrant.upsert(collection_name, points=[
    PointStruct(
        id=str(uuid.uuid4()),
        vector=embedding.tolist(),
        payload={"pattern_name": pattern_name}
    )
])

# Search similar
results = qdrant.search(
    collection_name=f"vectors_{node_id}",
    query_vector=query_embedding,
    limit=100
)
```

#### Redis (Session Store)

**File**: `kato/sessions/session_manager.py`

**Data Structure**:
```
Redis Key-Value Store
├── session:{session_id}       # Session data (JSON)
├── session:{session_id}:stm   # STM snapshot
└── session:{session_id}:emotives  # Emotive state
```

**Session Data**:
```python
{
    "session_id": "session-abc123",
    "node_id": "my_app",
    "created_at": "2025-11-13T10:00:00Z",
    "last_accessed": "2025-11-13T10:30:00Z",
    "ttl": 3600,
    "config": {
        "recall_threshold": 0.3,
        "max_predictions": 100
    }
}
```

**Key Operations**:
```python
# Create session
session_manager.create_session(node_id, config, ttl)

# Get session
session = session_manager.get_session(session_id)

# Update TTL
session_manager.extend_session(session_id)

# Delete session
session_manager.delete_session(session_id)
```

### 4. Search and Matching

**Location**: `kato/searches/`

#### Pattern Search

**File**: `kato/searches/pattern_search.py`

**Algorithm**:
1. **Candidate Retrieval**: Query MongoDB for potential matches
2. **Similarity Calculation**: Token-level or character-level matching
3. **Threshold Filtering**: Filter by `recall_threshold`
4. **Ranking**: Sort by `potential`, `similarity`, or `evidence`
5. **Result Formatting**: Convert to prediction structure

**Token-Level Matching** (Default):
```python
def token_similarity(pattern_event, query_event):
    """Calculate token overlap."""
    pattern_set = set(pattern_event)
    query_set = set(query_event)
    intersection = pattern_set & query_set
    union = pattern_set | query_set
    return len(intersection) / len(union) if union else 0
```

**Character-Level Matching** (Fuzzy):
```python
from rapidfuzz import fuzz

def character_similarity(pattern_str, query_str):
    """Calculate string similarity."""
    return fuzz.ratio(pattern_str, query_str) / 100.0
```

### 5. Configuration System

**Location**: `kato/config/`

#### Settings Hierarchy

**File**: `kato/config/settings.py`

```python
class Settings(BaseSettings):
    """Main configuration."""
    service: ServiceConfig
    logging: LoggingConfig
    database: DatabaseConfig
    learning: LearningConfig
    processing: ProcessingConfig
    performance: PerformanceConfig
    session: SessionConfig
    api: APIConfig
```

**Loading Priority**:
1. Environment variables (highest)
2. `.env` file
3. Default values (lowest)

**Example**:
```python
from kato.config import get_settings

settings = get_settings()
print(settings.database.mongo_url)  # mongodb://localhost:27017
print(settings.learning.recall_threshold)  # 0.1
```

## Data Flow

### Observation Flow

```
1. Client sends observation
   ↓
2. FastAPI validates request (Pydantic)
   ↓
3. SessionManager retrieves session
   ↓
4. KatoProcessor.observe()
   ├─→ ObservationProcessor validates input
   ├─→ Sort strings alphabetically
   ├─→ VectorProcessor handles vectors
   ├─→ MemoryManager adds to STM
   └─→ Check auto-learn trigger
   ↓
5. Response returned to client
```

### Learning Flow

```
1. Client calls /learn
   ↓
2. KatoProcessor.learn()
   ├─→ Get STM from MemoryManager
   ├─→ Validate (min 2 events)
   ├─→ PatternProcessor.learn_pattern()
   │   ├─→ Generate pattern hash
   │   ├─→ Create Pattern object
   │   └─→ Store in MongoDB
   ├─→ VectorProcessor stores vectors (if any)
   └─→ Update indices
   ↓
3. Pattern returned to client
```

### Prediction Flow

```
1. Client calls /predictions
   ↓
2. KatoProcessor.get_predictions()
   ├─→ Get current STM
   ├─→ PatternSearcher.search(stm, threshold)
   │   ├─→ Query MongoDB for candidates
   │   ├─→ Calculate similarities
   │   └─→ Filter and rank
   ├─→ Format predictions (past/present/future)
   ├─→ Calculate metrics (potential, confidence)
   └─→ Aggregate emotive statistics
   ↓
3. Predictions returned to client
```

## Scaling Architecture

### Horizontal Scaling

**Multiple KATO Instances**:
```
┌─────────────┐
│ Load        │
│ Balancer    │
└──────┬──────┘
       │
   ┌───┴───┬───────┬───────┐
   ▼       ▼       ▼       ▼
┌──────┐┌──────┐┌──────┐┌──────┐
│KATO 1││KATO 2││KATO 3││KATO 4│
└──┬───┘└──┬───┘└──┬───┘└──┬───┘
   └───┬───┴───┬───┴───┬───┘
       ▼       ▼       ▼
   ┌────────────────────────┐
   │  Shared MongoDB/Qdrant │
   └────────────────────────┘
```

**Session Affinity**:
- Use sticky sessions (session_id → instance)
- Or store session state in Redis (stateless instances)

### Database Scaling

**MongoDB**:
- Replica sets for read scaling
- Sharding by `node_id` for write scaling

**Qdrant**:
- Clustering for capacity
- Sharding by collection

**Redis**:
- Redis Cluster for capacity
- Sentinel for high availability

## Security Architecture

### Data Isolation

**Node-Level Isolation**:
- Each `node_id` gets separate MongoDB database
- Separate Qdrant collections
- No cross-node data leakage

**Session-Level Isolation**:
- Redis key namespacing
- TTL-based automatic cleanup

### API Security

```python
# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.api.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"]
)

# Rate limiting (optional)
# API key authentication (optional)
```

## Performance Considerations

### Optimization Points

1. **MongoDB Indexing**:
   ```javascript
   db.patterns.createIndex({"_id": 1})  // Pattern ID
   db.patterns.createIndex({"length": 1})  // Length queries
   db.patterns.createIndex({"updated_at": -1})  // Recency
   ```

2. **Qdrant HNSW**:
   ```python
   # Configured for fast search
   hnsw_config = HnswConfig(
       m=16,  # Links per layer
       ef_construct=100  # Construction parameter
   )
   ```

3. **Connection Pooling**:
   ```python
   # MongoDB pool
   client = AsyncIOMotorClient(
       mongo_url,
       maxPoolSize=50
   )

   # Qdrant reuse
   qdrant_client = QdrantClient(
       host=qdrant_host,
       port=qdrant_port
   )
   ```

4. **Caching**:
   - LRU cache for frequent predictions
   - Vector search result caching

## Monitoring and Observability

### Structured Logging

```python
logger.info(
    "Pattern learned",
    extra={
        "pattern_name": pattern.name,
        "node_id": self.node_id,
        "length": pattern.length,
        "trace_id": trace_id
    }
)
```

### Metrics Endpoint

```
GET /metrics

{
  "patterns_count": 1234,
  "sessions_active": 56,
  "memory_usage_mb": 512,
  "requests_per_second": 45
}
```

### Health Checks

```
GET /health

{
  "status": "healthy",
  "mongodb": "connected",
  "qdrant": "connected",
  "redis": "connected"
}
```

## Related Documentation

- **Full Architecture Diagram**: [ARCHITECTURE_DIAGRAM.md](../../ARCHITECTURE_DIAGRAM.md)
- **Code Organization**: [code-organization.md](code-organization.md)
- **Data Flow**: [data-flow.md](data-flow.md)
- **Design Patterns**: [design-patterns.md](design-patterns.md)

---

**Last Updated**: November 2025
**KATO Version**: 3.0+
