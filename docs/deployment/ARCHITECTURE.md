# KATO System Architecture

## Overview

KATO uses a distributed architecture with FastAPI services that provide direct access to embedded processors. Each instance maintains its own state, isolated by session_id.

## Current Architecture (FastAPI Direct Embedding)

```
                    ┌─────────────────┐
                    │   HTTP Client   │
                    └────────┬────────┘
                             │ HTTP/WebSocket
                             ▼ Port 8000
                ┌────────────────────────────────┐
                │    FastAPI Service             │
                │      (uvicorn)                 │
                │                                │
                │ • Async Request Handling       │
                │ • WebSocket Support            │
                │ • JSON Serialization           │
                │ • Health Monitoring            │
                └────────────┬───────────────────┘
                             │ Direct Call
                             ▼
                ┌────────────────────────────────┐
                │  KATO Processor (Embedded)     │
                │                                │
                │ • Pattern Learning             │
                │ • Prediction Generation        │
                │ • Memory Management            │
                │ • Multi-Modal Processing       │
                └────────────────────────────────┘
```

## Multi-Instance Architecture

```
                    ┌─────────────────┐
                    │   REST Client   │
                    └────────┬────────┘
                             │
        ┌────────────────────┼────────────────────┐
        ▼                    ▼                    ▼
 ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
 │ KATO Instance│    │ KATO Instance│    │ KATO Instance│
 │  Primary     │    │  Testing     │    │  Analytics   │
 │              │    │              │    │              │
 │ FastAPI:8001 │    │ FastAPI:8002 │    │ FastAPI:8003 │
 │              │    │              │    │              │
 │ Processor ID:│    │ Processor ID:│    │ Processor ID:│
 │   primary    │    │   testing    │    │   analytics  │
 └──────┬───────┘    └──────┬───────┘    └──────┬───────┘
        │                    │                    │
        └────────────────────┼────────────────────┘
                             ▼
                 ┌──────────────────────┐
                 │  ClickHouse (Shared) │
                 │     Redis (Shared)   │
                 │    Qdrant (Shared)   │
                 └──────────────────────┘
```

## Component Details

### 1. FastAPI Service

**Purpose**: HTTP/WebSocket API interface
**Implementation**: `kato/services/kato_fastapi.py`
**Responsibilities**:
- Async request handling with native async/await
- WebSocket support for real-time communication
- Direct embedding of KATO processor
- JSON request/response serialization
- Health monitoring and status endpoints

### 2. KATO Processor

**Purpose**: Core AI processing engine  
**Implementation**: `kato/workers/kato_processor.py`
**Responsibilities**:
- Pattern learning and recognition
- Prediction generation  
- Short-term memory management
- Multi-modal observation processing
- Deterministic hashing

### 3. Pattern Processor

**Purpose**: Pattern data structure management
**Implementation**: `kato/workers/pattern_processor.py`
**Responsibilities**:
- Pattern creation and validation
- Temporal segmentation
- Frequency tracking
- Pattern retrieval

### 4. Storage Layer

**ClickHouse** (Required):
- Pattern data storage with multi-stage filter pipeline
- Billion-scale performance via MinHash/LSH filtering
- SHA1 hash-based pattern indexing
- Node isolation via `kb_id` partitioning

**Redis** (Required):
- Session management and TTL tracking
- Pattern metadata (frequency, emotives)
- Caching layer for performance
- Key namespacing for isolation

**Qdrant** (Required):
- Vector similarity search with HNSW indexing
- 768-dimensional embeddings
- Collection-level isolation

## Data Flow

### Observation Flow
```
Client → FastAPI → KATO Processor → Short-Term Memory
                           ↓
                    Vector Processing → Qdrant
```

### Learning Flow
```
Client → FastAPI → Processor → Pattern Creation → ClickHouse Storage
                        ↓                            + Redis Metadata
                 Frequency Updates
```

### Prediction Flow
```
Client → FastAPI → Processor → Pattern Search → ClickHouse + Redis + Qdrant
                        ↓                         (Multi-stage filtering)
                 Temporal Segmentation
                        ↓
                 Ranked Predictions
```

## Container Configuration

### Docker Compose Structure

```yaml
services:
  # Primary KATO instance
  kato:
    image: kato:latest
    ports:
      - "8001:8000"  # API
    environment:
      - PROCESSOR_ID=primary
      - PROCESSOR_NAME=Primary
      - CLICKHOUSE_HOST=clickhouse
      - CLICKHOUSE_PORT=8123
      - REDIS_HOST=redis
      - REDIS_PORT=6379
      - QDRANT_HOST=qdrant
      - QDRANT_PORT=6333
      - LOG_LEVEL=INFO
    
  # Testing instance  
  kato-testing:
    image: kato:latest
    ports:
      - "8002:8000"  # API
    environment:
      - PROCESSOR_ID=testing
      - PROCESSOR_NAME=Testing
      - LOG_LEVEL=DEBUG
  
  # Analytics instance
  kato-analytics:
    image: kato:latest
    ports:
      - "8003:8000"  # API
    environment:
      - PROCESSOR_ID=analytics
      - PROCESSOR_NAME=Analytics
      - MAX_PATTERN_LENGTH=50
```

## API Endpoints

Core endpoints:
- `POST /observe` - Process observation
- `POST /learn` - Trigger learning
- `GET /predictions` - Get predictions
- `GET /health` - Service health
- `GET /status` - Detailed status

Advanced endpoints:
- `GET /pattern/{id}` - Get specific pattern
- `GET /cognition-data` - Cognitive metrics
- `GET /metrics` - Performance metrics
- `POST /observe-sequence` - Bulk observations
- `GET /stm` - Short-term memory state

## Port Configuration

Standard port allocations:
- **8001**: Primary instance
- **8002**: Testing instance
- **8003**: Analytics instance
- **8123**: ClickHouse HTTP
- **9000**: ClickHouse Native (optional)
- **6379**: Redis
- **6333**: Qdrant

## Network Architecture

```
┌────────────────────────────────────────┐
│         Docker Network: kato-network   │
│                                        │
├── FastAPI Services (HTTP/WebSocket)    │
│   └── Direct processor embedding       │
│                                        │
├── ClickHouse Container                 │
│   └── Database isolation by kb_id      │
│                                        │
├── Redis Container                      │
│   └── Key namespacing for isolation    │
│                                        │
└── Qdrant Container                     │
    └── Collection isolation by kb_id    │
```

## Security Considerations

| Layer | Protection |
|-------|------------|
| API | Rate limiting, input validation |
| Processor | Isolated by session_id |
| ClickHouse | Database-level isolation via kb_id |
| Redis | Key namespacing isolation |
| Qdrant | Collection-level isolation via kb_id |
| Network | Docker network isolation |

## Performance Characteristics

| Metric | Value | Notes |
|--------|-------|-------|
| Request Latency | 1-5ms | Direct embedding advantage |
| Throughput | 5000+ req/s | Async processing |
| Memory per Instance | 200-500MB | Depends on patterns |
| Startup Time | 2-5s | FastAPI initialization |

## Scaling Strategy

### Vertical Scaling
- Increase container resources
- Optimize processor configuration
- Enable GPU acceleration

### Horizontal Scaling
- Multiple KATO instances
- Load balancer distribution
- Processor_id based routing

## Monitoring

### Health Endpoints
```bash
# Check instance health
curl http://localhost:8000/health

# Get detailed status
curl http://localhost:8000/status
```

### Logs
```bash
# View container logs
docker logs kato --tail 50

# Monitor in real-time
docker logs -f kato
```

### Metrics
```bash
# Get performance metrics
curl http://localhost:8000/metrics
```

## Troubleshooting

### Common Issues

1. **Connection Refused**: Check service status
   ```bash
   docker ps
   docker-compose ps
   ```

2. **Database Connection**: Verify storage services are running
   ```bash
   docker exec clickhouse clickhouse-client --query "SELECT 1"
   docker exec redis redis-cli ping
   docker exec qdrant curl -f http://localhost:6333/health
   ```

3. **Port Conflicts**: Check port usage
   ```bash
   lsof -i :8001
   ```

## Related Documentation

- [Configuration Guide](CONFIGURATION.md) - Environment variables
- [Docker Setup](DOCKER.md) - Container management
- [Architecture Complete](../ARCHITECTURE_COMPLETE.md) - Detailed architecture
- [Troubleshooting](../technical/TROUBLESHOOTING.md) - Problem resolution