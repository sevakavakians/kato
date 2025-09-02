# ARCHITECTURE.md - KATO Technical Architecture
*Living Document - Last Updated: 2025-08-29*

## System Overview
```
┌─────────────┐     HTTP      ┌──────────────┐     ZMQ       ┌──────────────┐
│ REST Client │ ──────────▶   │ REST Gateway │ ──────────▶   │  ZMQ Server  │
└─────────────┘   Port 8000   └──────────────┘   Port 5555   └──────────────┘
                                      │                              │
                                      ▼                              ▼
                               ┌──────────────┐              ┌──────────────┐
                               │   FastAPI    │              │ ROUTER/DEALER│
                               │   Handlers   │              │   Pattern    │
                               └──────────────┘              └──────────────┘
                                                                     │
                                                                     ▼
                                                            ┌──────────────┐
                                                            │     KATO     │
                                                            │  Processor   │
                                                            └──────────────┘
                                                                     │
                                                    ┌────────────────┼────────────────┐
                                                    ▼                ▼                ▼
                                            ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
                                            │   Working    │ │    Qdrant    │ │    Redis     │
                                            │   Memory     │ │   Vector DB  │ │    Cache     │
                                            └──────────────┘ └──────────────┘ └──────────────┘
```

## Core Components

### 1. REST Gateway (`kato/workers/rest_gateway.py`)
**Purpose**: HTTP to ZMQ translation layer
**Key Features**:
- FastAPI-based asynchronous server
- Request validation and sanitization
- Response formatting and error handling
- Health check endpoints

**Endpoints**:
- `POST /observe`: Submit observations for processing
- `POST /predict`: Request predictions based on context
- `GET /ping`: Health check and status
- `GET /processor/ping/{processor_id}`: Processor-specific health

**Configuration**:
```python
REST_PORT = 8000  # Configurable via environment
ZMQ_ENDPOINT = "tcp://localhost:5555"
```

### 2. ZMQ Communication Layer
**Components**:
- `zmq_server.py`: Base ZMQ server implementation
- `zmq_pool_improved.py`: Connection pooling and load balancing
- `zmq_switcher.py`: Implementation switcher based on environment

**Pattern**: ROUTER/DEALER for non-blocking operations
**Protocol**: JSON-encoded messages with correlation IDs
**Features**:
- Automatic reconnection on failure
- Request timeout handling
- Connection pooling for high throughput

**Message Format**:
```json
{
  "action": "observe|predict|ping",
  "params": {},
  "correlation_id": "uuid",
  "timestamp": "ISO-8601"
}
```

### 3. KATO Processor (`kato/workers/kato_processor.py`)
**Core Responsibilities**:
- Observation processing and storage
- Prediction generation
- Memory management (STM/LTM)
- Model identification via SHA1 hashing

**Key Methods**:
- `observe()`: Process and store observations
- `predict()`: Generate temporal predictions
- `get_model_hash()`: Deterministic model identification
- `manage_memory()`: Handle memory transitions

**Memory Architecture**:
```python
# Short-Term Memory (Working Memory)
self.working_memory = {
    "observations": [],
    "timestamps": [],
    "context": {}
}

# Long-Term Memory Pattern
"PTRN|<sha1_hash>": {
    "observations": [...],
    "predictions": [...],
    "metadata": {...}
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

### Observation Flow
1. Client sends observation to REST endpoint
2. REST Gateway validates and forwards to ZMQ
3. ZMQ Server routes to available processor
4. Processor stores in working memory
5. Vector representation stored in Qdrant
6. Response sent back through chain

### Prediction Flow
1. Client requests prediction with context
2. Context used to search similar vectors
3. Historical patterns retrieved from Qdrant
4. Temporal segmentation applied (past/present/future)
5. Prediction generated and returned

## Deployment Architecture

### Container Structure
```yaml
services:
  kato-api:
    image: kato:latest
    ports:
      - "8000:8000"  # REST
      - "5555:5555"  # ZMQ
    environment:
      - PROCESSOR_ID
      - PROCESSOR_NAME
      
  qdrant:
    image: qdrant/qdrant
    ports:
      - "6333:6333"
    volumes:
      - qdrant_storage:/qdrant/storage
```

### Multi-Instance Deployment
- Each instance has unique PROCESSOR_ID
- Separate Qdrant collections per processor
- Shared Redis cache with key namespacing
- No cross-processor communication

## Performance Optimizations

### Current Optimizations
1. **Connection Pooling**: Reuse ZMQ connections
2. **Vector Indexing**: HNSW for O(log n) search
3. **Batch Processing**: Group vector operations
4. **Async I/O**: Non-blocking request handling

### Planned Optimizations
1. **GPU Acceleration**: CUDA for vector operations
2. **Quantization**: Reduce vector precision for speed
3. **Streaming**: WebSocket support for real-time
4. **Sharding**: Distribute vectors across nodes

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
3. Update model hash if behavior changes
4. Test with multi-instance scenarios
5. Benchmark performance impact

## Technical Debt & Future Work

### Identified Debt
- [ ] Centralize configuration management
- [ ] Improve error message consistency
- [ ] Add request tracing across components
- [ ] Implement circuit breakers

### Architectural Evolution
- Consider event sourcing for audit trail
- Explore CQRS for read/write separation
- Investigate GraphQL for flexible querying
- Plan for horizontal scaling strategy