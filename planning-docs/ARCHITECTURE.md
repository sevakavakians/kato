# ARCHITECTURE.md - KATO Technical Architecture
*Living Document - Last Updated: 2025-09-04*

## System Overview - FastAPI Architecture (Current)
```
┌─────────────┐     HTTP      ┌───────────────────────────────────────┐
│ REST Client │ ──────────▶   │         FastAPI Service              │
└─────────────┘  Port 8001-3  │  (Direct KATO Processor Embedding)   │
                               │                                       │
                               │  ┌──────────────┐                    │
                               │  │   FastAPI    │                    │
                               │  │   Handlers   │                    │
                               │  │              │                    │
                               │  └──────────────┘                    │
                               │          │                           │
                               │          ▼                           │
                               │  ┌──────────────┐                    │
                               │  │     KATO     │                    │
                               │  │  Processor   │                    │
                               │  │   (Embedded) │                    │
                               │  └──────────────┘                    │
                               └───────────────────────────────────────┘
                                          │
                         ┌────────────────┼────────────────┐
                         ▼                ▼                ▼
                 ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
                 │   MongoDB    │ │    Qdrant    │ │    Redis     │
                 │   Storage    │ │   Vector DB  │ │    Cache     │
                 └──────────────┘ └──────────────┘ └──────────────┘
```

### Legacy Architecture (Deprecated)
The previous REST/ZMQ architecture has been fully migrated to FastAPI as of 2025-09-04.
See `/planning-docs/completed/features/2025-09-04-fastapi-migration-milestone.md` for migration details.

## Core Components

### 1. FastAPI Service (`kato/services/kato_fastapi.py`)
**Purpose**: Modern web service with direct KATO processor embedding
**Key Features**:
- FastAPI-based asynchronous server
- Direct processor integration (no ZMQ layer)
- Request validation and sanitization
- Response formatting and error handling
- WebSocket support for real-time communication
- Automatic API documentation (OpenAPI/Swagger)

**Endpoints**:
- `POST /observe`: Submit observations for processing
- `POST /predict`: Request predictions based on context
- `POST /learn`: Trigger learning process
- `GET /health`: Health check and status
- `WebSocket /ws`: Real-time communication channel

**Service Ports**:
- **Primary**: Port 8001 (Manual learning mode)
- **Testing**: Port 8002 (Debug logging enabled)
- **Analytics**: Port 8003 (Auto-learn after 50 observations)

**Configuration**:
```python
PROCESSOR_ID = "unique_instance_id"
PROCESSOR_NAME = "display_name"  
LOG_LEVEL = "INFO"  # DEBUG for testing instance
MAX_PATTERN_LENGTH = 0  # Manual learning (primary), 50 (analytics)
```

### 2. Direct Processing Architecture
**Migration Completed**: REST/ZMQ → FastAPI Direct Embedding (2025-09-04)
**Benefits**:
- Reduced latency (no ZMQ overhead)
- Simplified deployment (single service)
- Better error handling and debugging
- Enhanced async capabilities
- Reduced operational complexity

**Legacy Components Removed**:
- `zmq_server.py`, `zmq_pool_improved.py`, `zmq_switcher.py`
- Connection pooling and ZMQ message routing
- Complex inter-process communication

### 3. KATO Processor (`kato/workers/kato_processor.py`)
**Integration**: Directly embedded in FastAPI service (no ZMQ)
**Core Responsibilities**:
- Multi-modal observation processing (strings, vectors, emotions)
- Temporal prediction generation
- Short-term and long-term memory management
- Pattern identification via SHA1 hashing
- Vector database coordination

**Key Methods**:
- `observe()`: Process and store multi-modal observations
- `predict()`: Generate temporal predictions with recall threshold
- `learn()`: Transfer STM patterns to long-term storage
- `get_pattern_hash()`: Deterministic pattern identification
- Pattern processing with temporal segmentation (past/present/future)

**Memory Architecture**:
```python
# Short-Term Memory (Working Memory)
self.short_term_memory = {
    "events": [["string1", "string2"], ["string3"]],  # Alphanumerically sorted
    "timestamps": ["2025-09-04T10:30:00", "2025-09-04T10:31:00"],
    "vectors": [...],  # 768-dimensional embeddings
    "emotives": {...}  # Emotional context
}

# Long-Term Memory Pattern (MongoDB)
"PTRN|<sha1_hash>": {
    "pattern": [["sorted", "strings"], ["more", "strings"]],
    "frequency": 5,  # Minimum 1, increments on re-learning
    "metadata": {...},
    "created_at": "2025-09-04T10:30:00"
}
```

### 4. Vector Storage Layer (`kato/storage/`)
**Primary**: Qdrant Vector Database
- **Manager**: `qdrant_manager.py`
- **Collections**: One per processor ID
- **Indexing**: HNSW for fast similarity search
- **Dimensions**: 768 (transformer embeddings)

**Caching**: Redis Integration
- **Purpose**: Frequently accessed vector caching
- **Pattern**: Write-through cache
- **TTL**: Configurable based on access patterns

**Abstraction Layer**:
```python
class VectorStorageInterface:
    def store_vector(vector, metadata)
    def search_similar(vector, top_k)
    def batch_operations(operations)
```

## Data Flow Patterns

### Observation Flow (FastAPI Architecture)
1. Client sends observation to FastAPI endpoint
2. FastAPI service validates request directly
3. Embedded KATO processor processes immediately
4. Multi-modal data (strings, vectors, emotions) stored in STM
5. Vector representations stored in Qdrant
6. Response returned directly from FastAPI

### Prediction Flow (FastAPI Architecture)
1. Client requests prediction with recall threshold
2. STM context used to search MongoDB patterns
3. Vector similarity search in Qdrant
4. Temporal segmentation applied (past/present/future)
5. Prediction metrics calculated (hamiltonian, confidence, etc.)
6. Structured prediction returned with missing/extras/matches fields

### Learning Flow
1. Client triggers learn endpoint (or auto-triggered)
2. STM patterns transferred to MongoDB long-term storage
3. Pattern frequency incremented if already exists
4. Deterministic SHA1 hash prevents duplicates
5. STM cleared after successful learning

## Deployment Architecture

### Container Structure (FastAPI)
```yaml
services:
  kato-primary:
    image: kato:latest
    ports:
      - "8001:8000"  # FastAPI Primary
    environment:
      - PROCESSOR_ID=primary
      - PROCESSOR_NAME=Primary KATO
      - LOG_LEVEL=INFO
      - MAX_PATTERN_LENGTH=0  # Manual learning
      
  kato-testing:
    image: kato:latest  
    ports:
      - "8002:8000"  # FastAPI Testing
    environment:
      - PROCESSOR_ID=testing
      - PROCESSOR_NAME=Testing KATO
      - LOG_LEVEL=DEBUG
      - MAX_PATTERN_LENGTH=0
      
  kato-analytics:
    image: kato:latest
    ports:
      - "8003:8000"  # FastAPI Analytics
    environment:
      - PROCESSOR_ID=analytics
      - PROCESSOR_NAME=Analytics KATO
      - LOG_LEVEL=INFO
      - MAX_PATTERN_LENGTH=50  # Auto-learn
      - RECALL_THRESHOLD=0.5   # Higher threshold

  mongodb:
    image: mongo:latest
    ports:
      - "27017:27017"
    volumes:
      - mongodb_data:/data/db
      
  qdrant:
    image: qdrant/qdrant
    ports:
      - "6333:6333"
    volumes:
      - qdrant_storage:/qdrant/storage
```

### Multi-Instance Isolation
- **Database Isolation**: Each instance uses processor_id as database name
- **Vector Isolation**: Separate Qdrant collections per processor (`vectors_{processor_id}`)
- **Memory Isolation**: Independent STM and processing per instance
- **No Cross-Instance Communication**: Complete isolation for testing and production

## Performance Optimizations

### Current Optimizations (FastAPI)
1. **Direct Embedding**: Eliminated ZMQ overhead (~10ms response time maintained)
2. **Vector Indexing**: HNSW for O(log n) search in Qdrant
3. **Async I/O**: Native FastAPI async for non-blocking request handling
4. **Database Efficiency**: MongoDB with proper indexing on pattern hashes
5. **Simplified Architecture**: Reduced latency with direct processor access

### Performance Achievements
- **Response Time**: ~10ms average (maintained through migration)
- **Test Execution**: 183/185 tests passing (98.9% reliability)
- **Deployment Simplicity**: Single service vs complex multi-service architecture
- **Development Speed**: Faster iteration with direct debugging

### Planned Optimizations
1. **GPU Acceleration**: CUDA for vector operations
2. **Quantization**: Reduce vector precision for speed
3. **WebSocket Streaming**: Real-time communication (already implemented)
4. **Horizontal Scaling**: Multiple FastAPI instances with load balancing

## Security Considerations

### Current Measures
- Input validation at REST layer
- No direct database access from clients
- Processor isolation via Docker
- Deterministic hashing for integrity

### Future Enhancements
- Authentication/Authorization layer
- Rate limiting per client
- Encrypted ZMQ communication
- Audit logging for compliance

## Monitoring Points

### Key Metrics
- Request latency (REST, ZMQ, Processing)
- Vector search performance
- Memory usage (Working, Qdrant, Redis)
- Error rates by component

### Health Checks
- REST: `/ping` endpoint
- ZMQ: Connection status monitoring
- Qdrant: Collection statistics
- Redis: Connection pool health

## Configuration Management

### Environment Variables
```bash
# Core Configuration
MANIFEST='{"processor_id": "...", "name": "..."}'
LOG_LEVEL=INFO
KATO_ZMQ_IMPLEMENTATION=improved

# Service Endpoints
REST_PORT=8000
ZMQ_PORT=5555
QDRANT_URL=http://localhost:6333
REDIS_URL=redis://localhost:6379

# Performance Tuning
CONNECTION_POOL_SIZE=10
VECTOR_BATCH_SIZE=100
CACHE_TTL=3600
```

### Feature Flags
- `KATO_USE_FAST_MATCHING`: Use accelerated pattern matching algorithms (default: true)
- `KATO_USE_INDEXING`: Enable advanced indexing features (default: true)

## Development Guidelines

### Adding New Components
1. Follow existing patterns in `kato/workers/`
2. Implement interface contracts
3. Add comprehensive logging
4. Include unit and integration tests
5. Update this architecture document

### Modifying Core Logic
1. Preserve deterministic behavior
2. Maintain backwards compatibility
3. Update pattern hash if behavior changes
4. Test with multi-instance scenarios
5. Benchmark performance impact

## FastAPI Migration Status

### Completed (2025-09-04)
✅ **Architecture Migration**: Complete system migration from REST/ZMQ to FastAPI  
✅ **Test Suite Restoration**: Fixed all 43 failing tests (183/185 passing)  
✅ **Performance Validation**: Maintained ~10ms response time  
✅ **Database Compatibility**: Resolved Qdrant and MongoDB integration issues  
✅ **Async/Sync Boundaries**: Fixed complex synchronization problems  
✅ **API Consistency**: Updated endpoint formats and response fields  
✅ **WebSocket Support**: Added websocket-client dependency  
✅ **Deployment Simplification**: Single service architecture  

### Migration Benefits Realized
- **Reduced Complexity**: Eliminated ZMQ layer and connection pooling
- **Better Debugging**: Direct access to processor for development
- **Faster Iteration**: No container rebuilds for code changes during testing
- **Modern Framework**: Industry-standard FastAPI with automatic docs
- **Simplified Ops**: Single service deployment vs multi-service coordination

## Technical Debt & Future Work

### Migration-Related Debt Resolved
- [x] Complex ZMQ communication layer (removed)
- [x] Connection pooling complexity (eliminated)
- [x] Multi-service coordination (simplified to single service)
- [x] Test infrastructure compatibility (fixed)

### Remaining Technical Debt
- [ ] Centralize configuration management across instances
- [ ] Improve error message consistency
- [ ] Add request tracing for debugging
- [ ] Implement health check monitoring

### Future Architectural Evolution
- **Event Sourcing**: Consider for audit trail and replay capability
- **Horizontal Scaling**: FastAPI instances behind load balancer
- **GraphQL**: Explore for flexible querying of patterns and predictions
- **Microservices**: Potential future decomposition based on usage patterns