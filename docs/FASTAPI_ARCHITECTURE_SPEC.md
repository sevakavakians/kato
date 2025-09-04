# KATO FastAPI Architecture Specification

## Executive Summary

This specification defines the new KATO architecture that replaces the problematic REST/ZMQ gateway with a direct FastAPI implementation. Each KATO instance runs as a self-contained FastAPI application in its own Docker container, providing true isolation, horizontal scalability, and simplified state management.

## Architecture Overview

```
                    ┌─────────────────────────┐
                    │   Nginx/Traefik         │
                    │   (Optional Router)     │
                    └──────────┬──────────────┘
                               │
        ┌──────────────────────┼──────────────────────┐
        │                      │                      │
   ┌────▼─────┐         ┌─────▼────┐         ┌──────▼────┐
   │  KATO-1  │         │  KATO-2  │         │  KATO-3  │
   │ FastAPI  │         │ FastAPI  │         │ FastAPI  │
   │Container │         │Container │         │Container │
   └──────────┘         └──────────┘         └───────────┘
        │                      │                      │
        └──────────────────────┼──────────────────────┘
                               │
                    ┌──────────▼──────────┐
                    │     MongoDB          │
                    │  (Shared Storage)    │
                    └──────────────────────┘
```

## Core Design Principles

1. **Single Responsibility**: Each container runs exactly one KATO processor instance
2. **Direct Access**: Containers accessible directly via HTTP without intermediate gateways
3. **State Isolation**: Each processor maintains its own STM and database isolation
4. **Sequential Processing**: Async locks ensure observations are processed in order
5. **Horizontal Scalability**: New containers can be spawned on demand

## Component Specifications

### 1. KATO FastAPI Service

**Location**: `kato/services/kato_fastapi.py`

**Responsibilities**:
- Embed a single KatoProcessor instance per container
- Expose REST API endpoints for all KATO operations
- Maintain processor state across requests
- Ensure sequential processing with async locks
- Provide WebSocket support for real-time communication

**Key Features**:
- Uses FastAPI lifespan context manager for initialization/cleanup
- Processor lock ensures sequential observation processing
- Automatic API documentation via OpenAPI/Swagger
- Type validation with Pydantic models
- Async/await for non-blocking I/O

### 2. API Endpoints

#### Core Operations

| Method | Endpoint | Description | Request Body | Response |
|--------|----------|-------------|--------------|----------|
| POST | `/observe` | Process observation | `ObservationData` | `ObservationResult` |
| GET | `/stm` | Get short-term memory | - | `STMResponse` |
| POST | `/learn` | Learn from STM | - | `LearnResult` |
| POST | `/clear-stm` | Clear short-term memory | - | `StatusResponse` |
| POST | `/clear-all` | Clear all memory | - | `StatusResponse` |
| GET | `/predictions` | Get predictions | - | `PredictionsResponse` |
| GET | `/status` | Get processor status | - | `ProcessorStatus` |

#### Advanced Operations

| Method | Endpoint | Description | Request Body | Response |
|--------|----------|-------------|--------------|----------|
| GET | `/pattern/{pattern_id}` | Get pattern by ID | - | `PatternData` |
| POST | `/genes/update` | Update gene values | `GeneUpdates` | `StatusResponse` |
| GET | `/gene/{gene_name}` | Get gene value | - | `GeneValue` |
| GET | `/percept-data` | Get percept data | - | `PerceptData` |
| GET | `/cognition-data` | Get cognition data | - | `CognitionData` |

#### WebSocket Endpoint

| Endpoint | Description | Message Format |
|----------|-------------|----------------|
| `/ws` | Bidirectional real-time communication | JSON with `type` and `payload` |

### 3. Data Models (Pydantic)

```python
class ObservationData(BaseModel):
    strings: List[str]
    vectors: List[List[float]] = []
    emotives: Dict[str, float] = {}
    unique_id: Optional[str] = None

class ObservationResult(BaseModel):
    status: str
    processor_id: str
    auto_learned_pattern: Optional[str]
    time: int

class STMResponse(BaseModel):
    stm: List[List[str]]
    processor_id: str

class PredictionsResponse(BaseModel):
    predictions: List[Dict]
    processor_id: str

class LearnResult(BaseModel):
    pattern_name: str
    processor_id: str
```

### 4. Container Configuration

#### Environment Variables

| Variable | Description | Default | Example |
|----------|-------------|---------|---------|
| `PROCESSOR_ID` | Unique processor identifier | required | `user-123-session-456` |
| `PROCESSOR_NAME` | Human-readable processor name | `KatoProcessor` | `UserSession` |
| `MONGO_URL` | MongoDB connection string | `mongodb://localhost:27017` | `mongodb://mongodb:27017` |
| `MAX_PATTERN_LENGTH` | Auto-learn threshold | `0` | `10` |
| `PERSISTENCE` | Pattern persistence | `5` | `5` |
| `RECALL_THRESHOLD` | Pattern recall threshold | `0.1` | `0.5` |
| `LOG_LEVEL` | Logging level | `INFO` | `DEBUG` |
| `PORT` | FastAPI port | `8000` | `8000` |

#### Docker Image

**Dockerfile.fastapi**:
```dockerfile
FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt
RUN pip install fastapi uvicorn[standard]

COPY kato/ ./kato/

ENV PORT=8000
EXPOSE 8000

CMD ["uvicorn", "kato.services.kato_fastapi:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 5. Container Management

#### Static Deployment (docker-compose.yml)

```yaml
version: '3.8'

services:
  mongodb:
    image: mongo:4.4
    container_name: kato-mongodb
    networks:
      - kato-network

  kato-primary:
    build:
      context: .
      dockerfile: Dockerfile.fastapi
    container_name: kato-primary
    environment:
      - PROCESSOR_ID=primary
      - PROCESSOR_NAME=Primary
      - MONGO_URL=mongodb://mongodb:27017
    ports:
      - "8001:8000"
    networks:
      - kato-network
    depends_on:
      - mongodb

networks:
  kato-network:
    driver: bridge
```

#### Dynamic Container Creation

The Container Manager provides programmatic container lifecycle management:

```python
manager = KatoContainerManager()

# Create new processor
info = manager.create_processor(
    user_id="user-123",
    session_id="session-456",
    config={"max_pattern_length": 10}
)
# Returns: {
#   'processor_id': 'kato-user-123-session-456-1234567890',
#   'container_name': 'kato-user-123-session-456-1234567890',
#   'port': 8001,
#   'internal_url': 'http://kato-user-123-session-456-1234567890:8000',
#   'external_url': 'http://localhost:8001'
# }

# Remove processor
manager.remove_processor('kato-user-123-session-456-1234567890')
```

### 6. Session Management (Optional)

For multi-user applications, an optional Session Manager service provides:

- Session creation with dedicated containers
- Request routing to correct processor
- Session lifecycle management
- Resource cleanup for idle sessions

**Endpoints**:
- `POST /session/create` - Create new session with processor
- `POST /session/{id}/observe` - Route observation to processor
- `GET /session/{id}/stm` - Get STM from processor
- `DELETE /session/{id}` - Terminate session and remove container

## Usage Patterns

### Pattern 1: Direct Container Access

Applications directly communicate with specific KATO containers:

```python
# Python client example
import httpx

async def interact_with_kato():
    async with httpx.AsyncClient() as client:
        # Direct access to specific container
        response = await client.post(
            "http://kato-primary:8000/observe",
            json={
                "strings": ["hello", "world"],
                "vectors": [],
                "emotives": {}
            }
        )
        result = response.json()
```

### Pattern 2: Session-Based Access

Applications use the Session Manager for automatic container management:

```python
# Create session
session = await client.post("/session/create", json={"user_id": "user-123"})
session_id = session.json()["session_id"]

# Use session
await client.post(f"/session/{session_id}/observe", json=observation_data)
stm = await client.get(f"/session/{session_id}/stm")
```

### Pattern 3: WebSocket Streaming

Real-time bidirectional communication:

```python
import websockets
import json

async def stream_observations():
    uri = "ws://kato-primary:8000/ws"
    async with websockets.connect(uri) as websocket:
        # Send observation
        await websocket.send(json.dumps({
            "type": "observe",
            "payload": {
                "strings": ["real", "time", "data"],
                "vectors": [],
                "emotives": {}
            }
        }))
        
        # Receive response
        response = await websocket.recv()
        data = json.loads(response)
```

## Testing Strategy

### Unit Tests

Test individual KATO processors in isolated containers:

```python
@pytest.fixture
async def kato_container():
    """Create isolated KATO container for testing"""
    manager = KatoContainerManager()
    info = manager.create_processor(
        user_id="test",
        session_id=str(uuid.uuid4())
    )
    yield info
    manager.remove_processor(info['processor_id'])

async def test_observation_sequence(kato_container):
    """Test sequential observations maintain STM state"""
    client = httpx.AsyncClient(base_url=kato_container['external_url'])
    
    # First observation
    await client.post("/observe", json={"strings": ["first"]})
    
    # Second observation
    await client.post("/observe", json={"strings": ["second"]})
    
    # Check STM
    stm = await client.get("/stm")
    assert stm.json()["stm"] == [["first"], ["second"]]
```

### Integration Tests

Test multi-container scenarios:

```python
async def test_container_isolation():
    """Test that containers are truly isolated"""
    container1 = create_container("test1")
    container2 = create_container("test2")
    
    # Observe in container1
    await observe(container1, ["data1"])
    
    # Observe in container2
    await observe(container2, ["data2"])
    
    # Verify isolation
    stm1 = await get_stm(container1)
    stm2 = await get_stm(container2)
    
    assert stm1 == [["data1"]]
    assert stm2 == [["data2"]]
```

### Performance Tests

```python
async def test_concurrent_containers():
    """Test multiple containers handling concurrent requests"""
    containers = [create_container(f"perf{i}") for i in range(10)]
    
    async def process_container(container, data):
        for item in data:
            await observe(container, item)
        return await get_stm(container)
    
    # Process all containers concurrently
    results = await asyncio.gather(*[
        process_container(c, generate_test_data())
        for c in containers
    ])
    
    # Verify all processed independently
    assert len(set(map(str, results))) == 10  # All unique states
```

## Migration Path

### Phase 1: Build New Infrastructure
1. Create `kato/services/kato_fastapi.py`
2. Create `Dockerfile.fastapi`
3. Create `docker-compose.fastapi.yml`
4. Test new architecture in parallel with existing system

### Phase 2: Port Tests
1. Update `kato_fixtures.py` to use new endpoints
2. Run all tests against new architecture
3. Fix any compatibility issues

### Phase 3: Switch Over
1. Update `kato-manager.sh` to use new Docker setup
2. Remove old REST gateway and ZMQ components
3. Update documentation

### Phase 4: Cleanup
1. Remove `kato/workers/rest_gateway.py`
2. Remove `kato/workers/zmq_server.py`
3. Remove `kato/workers/zmq_pool_improved.py`
4. Remove `kato/workers/zmq_switcher.py`
5. Remove old Dockerfile and docker-compose.yml

## Performance Characteristics

### Expected Improvements

| Metric | Current (REST/ZMQ) | New (FastAPI) | Improvement |
|--------|-------------------|---------------|-------------|
| Latency per request | ~10-15ms | ~2-3ms | 5x faster |
| Concurrent containers | Limited by ZMQ pool | Unlimited | ∞ |
| State persistence | Problematic | Guaranteed | 100% reliable |
| Resource overhead | 3 layers | 1 layer | 66% reduction |
| Debugging complexity | High | Low | Much simpler |

### Scalability

- **Vertical**: Increase container resources (CPU/memory)
- **Horizontal**: Spawn more containers (limited only by host resources)
- **Load Balancing**: Use Nginx/Traefik for distribution
- **Auto-scaling**: Kubernetes HPA based on metrics

## Security Considerations

1. **Network Isolation**: Containers communicate only within Docker network
2. **Resource Limits**: Set CPU/memory limits per container
3. **Authentication**: Can add JWT/API keys to FastAPI endpoints
4. **Rate Limiting**: FastAPI middleware for request throttling
5. **Input Validation**: Pydantic models enforce data types

## Monitoring and Observability

### Health Checks

```python
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "processor_id": processor.id,
        "uptime": time.time() - start_time,
        "stm_length": len(processor.get_stm()),
        "memory_usage": get_memory_usage()
    }
```

### Metrics Endpoint

```python
@app.get("/metrics")
async def metrics():
    return {
        "observations_processed": processor.time,
        "patterns_learned": get_pattern_count(),
        "predictions_generated": get_prediction_count(),
        "stm_size": len(processor.get_stm())
    }
```

### Logging

- Structured JSON logging with correlation IDs
- Log aggregation with ELK stack or similar
- Debug mode toggleable via LOG_LEVEL environment variable

## Error Handling

All endpoints return consistent error responses:

```json
{
    "error": {
        "code": "PROCESSOR_NOT_FOUND",
        "message": "Processor with ID 'xyz' not found",
        "details": {
            "processor_id": "xyz",
            "available_processors": ["abc", "def"]
        }
    },
    "status": 404
}
```

## Future Enhancements

1. **GraphQL API**: Alternative query interface
2. **Event Streaming**: Kafka/RabbitMQ integration
3. **Distributed Tracing**: OpenTelemetry support
4. **GPU Acceleration**: CUDA containers for vector operations
5. **Multi-region**: Geographic distribution with data replication

## Acceptance Criteria

The implementation is complete when:

1. ✅ All existing tests pass with new architecture
2. ✅ Each container maintains isolated state
3. ✅ Sequential observations build STM correctly
4. ✅ Multiple containers can run concurrently
5. ✅ WebSocket streaming works for real-time updates
6. ✅ Container creation/deletion is automated
7. ✅ Performance meets or exceeds current system
8. ✅ API documentation is auto-generated
9. ✅ Resource cleanup prevents memory leaks
10. ✅ System handles 100+ concurrent containers

## References

- FastAPI Documentation: https://fastapi.tiangolo.com/
- Docker SDK for Python: https://docker-py.readthedocs.io/
- Pydantic V2: https://docs.pydantic.dev/latest/
- Uvicorn ASGI Server: https://www.uvicorn.org/