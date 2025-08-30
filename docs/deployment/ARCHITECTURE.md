# KATO System Architecture

## Overview

KATO uses a distributed architecture with centralized REST gateway that maintains sticky routing to ensure requests for specific processors always go to the same KATO instance, preserving stateful sequence processing.

## Current Architecture (ZeroMQ-based)

```
                    ┌─────────────────┐
                    │   REST Client   │
                    └────────┬────────┘
                             │ HTTP/REST
                             ▼ Port 8000
                ┌────────────────────────────────┐
                │    REST API Gateway            │
                │   (Embedded in KATO)           │
                │                                │
                │ • HTTP to ZMQ Translation      │
                │ • Connection Pool Management   │
                │ • Thread-Local Connections     │
                │ • Health Monitoring            │
                └────────────┬───────────────────┘
                             │
                             ▼ ZMQ Port 5555
                ┌────────────────────────────────┐
                │      ZeroMQ Server             │
                │                                │
                │ • REQ/REP Pattern              │
                │ • MessagePack Serialization    │
                │ • Method Dispatch              │
                └────────────┬───────────────────┘
                             │
                             ▼
                ┌────────────────────────────────┐
                │     KATO Processor             │
                │                                │
                │ • Sequence Learning            │
                │ • Prediction Generation        │
                │ • Memory Management            │
                │ • Multi-Modal Processing       │
                └────────────────────────────────┘
```

## Multi-Instance Architecture (Planned)

```
                    ┌─────────────────┐
                    │   REST Client   │
                    └────────┬────────┘
                             │ HTTP/REST
                             ▼ Port 8000
                ┌────────────────────────────────┐
                │    REST API Gateway            │
                │   (Separate Container)         │
                │                                │
                │ • Processor Registry           │
                │ • Sticky Routing (by ID)       │
                │ • Connection Pool Management   │
                │ • Health Monitoring            │
                └───┬────────┬───────────────┬───┘
                    │        │               │
              processor_id   processor_id    processor_id
              "p46b6b076c"   "pd5d9e6c4c"   "p847675347"
                    │        │               │
                    ▼        ▼               ▼
            ┌──────────┐ ┌──────────┐ ┌──────────┐
            │  KATO    │ │  KATO    │ │  KATO    │
            │Instance 1│ │Instance 2│ │Instance 3│
            │ZMQ:5555  │ │ZMQ:5556  │ │ZMQ:5557  │
            └──────────┘ └──────────┘ └──────────┘
```

## Component Details

### 1. REST API Gateway

The gateway provides HTTP/REST interface for clients:

- **Location**: Currently embedded in KATO, planned as separate service
- **Port**: 8000 (configurable)
- **Protocol**: HTTP/REST with JSON payloads
- **Threading**: ThreadedHTTPServer for concurrent requests

#### Key Features:
- HTTP to ZeroMQ translation
- Connection pooling with thread-local storage
- Automatic health checks and reconnection
- Request routing based on processor ID

### 2. ZeroMQ Server

High-performance message handling layer:

- **Port**: 5555 (configurable via ZMQ_PORT)
- **Pattern**: REQ/REP (Request/Reply)
- **Serialization**: MessagePack binary format
- **Threading**: Runs in separate thread

#### Supported Methods:
- `observe` - Process observations
- `learn` - Trigger learning
- `get_predictions` - Retrieve predictions
- `clear_all_memory` / `clear_short_term_memory`
- `get_gene` / `change_gene` - Parameter management
- `get_short_term_memory` - Access current memory

### 3. Connection Pool

Thread-safe connection management:

- **Pattern**: One ZMQ client per thread
- **Health Checks**: Every 30 seconds
- **Auto-reconnection**: On connection failure
- **Statistics**: Tracks requests, failures, reconnections

### 4. KATO Processor

Core AI engine:

- **Memory**: Short-term memory + long-term storage
- **Learning**: Sequence pattern recognition
- **Predictions**: Temporal segmentation (past/present/future)
- **Multi-modal**: Strings, vectors, emotives

## Data Flow

### 1. Observation Flow
```
Client → REST API → ZMQ Client → ZMQ Server → Processor → Short-Term Memory
```

### 2. Learning Flow
```
Client → REST API → ZMQ → Processor → Model Creation → MongoDB Storage
```

### 3. Prediction Flow
```
Short-Term Memory → Pattern Matching → Temporal Segmentation → Predictions → Client
```

## Deployment Configurations

### Single Instance (Current)

```yaml
version: '3.8'
services:
  kato:
    image: kato:latest
    ports:
      - "8000:8000"  # REST API
      - "5555:5555"  # ZMQ (internal)
    environment:
      - PROCESSOR_ID=p46b6b076c
      - PROCESSOR_NAME=MainProcessor
```

### Multi-Instance with Gateway (Planned)

```yaml
version: '3.8'
services:
  gateway:
    image: kato-gateway:latest
    ports:
      - "8000:8000"
    environment:
      - PROCESSORS=p001:kato-1:5555,p002:kato-2:5555
  
  kato-1:
    image: kato:latest
    environment:
      - PROCESSOR_ID=p001
      - ZMQ_PORT=5555
  
  kato-2:
    image: kato:latest
    environment:
      - PROCESSOR_ID=p002
      - ZMQ_PORT=5555
```

## Communication Protocols

### REST API Protocol

**Request Format:**
```json
{
  "strings": ["hello", "world"],
  "vectors": [[1.0, 2.0]],
  "emotives": {"joy": 0.8}
}
```

**Response Format:**
```json
{
  "status": "okay",
  "message": "observed",
  "short_term_memory": [["hello", "world"]]
}
```

### ZeroMQ Protocol

**Request Format (MessagePack):**
```python
{
  "method": "observe",
  "params": {
    "strings": ["hello", "world"],
    "vectors": [],
    "emotives": {}
  }
}
```

**Response Format (MessagePack):**
```python
{
  "status": "okay",
  "message": "observed",
  "short_term_memory": [["hello", "world"]]
}
```

## Scaling Strategies

### Horizontal Scaling

1. **Multiple Processors**: Each with unique ID
2. **Sticky Sessions**: Processor affinity for sequences
3. **Shared Storage**: MongoDB for persistence
4. **Load Balancing**: Round-robin or least-connections

### Vertical Scaling

1. **Increase Resources**: More CPU/RAM per instance
2. **Optimize Parameters**: Tune for performance
3. **Cache Optimization**: Memory-based caching
4. **Connection Pooling**: Reuse connections

## State Management

### Processor State

Each processor maintains:
- **Short-Term Memory**: Current observation sequence
- **Long-term Memory**: Learned models
- **Predictions Cache**: Current predictions
- **Emotives State**: Aggregated emotional context

### State Persistence

- **MongoDB**: Long-term model storage
- **In-Memory**: Short-term memory and caches
- **Checkpointing**: Periodic state snapshots (planned)

## Network Architecture

### Docker Network

```
kato-network (bridge)
├── REST Gateway (port 8000 exposed)
├── KATO Instances (internal)
├── MongoDB (internal)
└── ZeroMQ Communication (internal)
```

### Port Mappings

| Service | External Port | Internal Port | Protocol |
|---------|--------------|---------------|----------|
| REST API | 8000 | 8000 | HTTP |
| ZeroMQ | - | 5555 | TCP |
| MongoDB | - | 27017 | TCP |

## Security Considerations

### Network Security

1. **Internal Communication**: ZMQ on private network
2. **External Access**: Only REST API exposed
3. **TLS Support**: Planned for production
4. **API Authentication**: Optional API key

### Data Security

1. **No Encryption**: Currently plain text
2. **Access Control**: Network-level isolation
3. **Audit Logging**: All operations logged
4. **Data Validation**: Input sanitization

## Performance Characteristics

### Latency

- **REST to ZMQ**: ~0.1ms overhead
- **ZMQ Round-trip**: ~0.5ms
- **Prediction Generation**: 1-10ms
- **Learning Operation**: 10-100ms

### Throughput

- **Requests/second**: 10,000+ per processor
- **Concurrent Connections**: 1000+
- **Message Size**: Up to 16MB
- **Batch Operations**: Supported

### Resource Usage

- **Memory**: 500MB-2GB per processor
- **CPU**: 0.5-2 cores per processor
- **Network**: 10-100 Mbps typical
- **Storage**: 100MB-10GB MongoDB

## Monitoring Points

### Health Checks

```bash
# REST API Health
GET /kato-api/ping

# Processor Health
GET /{processor_id}/ping

# ZMQ Server Status
Internal health check every 30s
```

### Metrics Collection

- Request count and latency
- Memory usage and GC stats
- Prediction accuracy metrics
- Connection pool statistics

## Future Enhancements

### Planned Features

1. **Separate Gateway Service**: Decoupled architecture
2. **Service Discovery**: Dynamic processor registration
3. **WebSocket Support**: Real-time predictions
4. **GraphQL API**: Alternative query interface
5. **Kubernetes Support**: Cloud-native deployment

### Performance Improvements

1. **Caching Layer**: Redis for predictions
2. **Async Processing**: Non-blocking operations
3. **GPU Acceleration**: Vector operations
4. **Compression**: Message compression

## Migration Path

### From Current to Multi-Instance

1. **Phase 1**: Current embedded gateway
2. **Phase 2**: External gateway with single instance
3. **Phase 3**: Multiple instances with routing
4. **Phase 4**: Full distributed system

## Development vs Production

### Development Setup
```bash
./kato-manager.sh start --log-level DEBUG
```

### Production Setup
```bash
./kato-manager.sh start \
  --classifier DVC \
  --max-predictions 200 \
  --persistence 10 \
  --api-key $SECRET_KEY
```

## Troubleshooting Architecture

### Common Issues

1. **Connection Refused**: Check ZMQ server status
2. **Timeout Errors**: Verify network connectivity
3. **State Inconsistency**: Check processor affinity
4. **Performance Degradation**: Monitor connection pool

### Debug Tools

```bash
# Check connectivity
docker exec kato-api netstat -an | grep 5555

# Monitor ZMQ traffic
docker exec kato-api tcpdump -i lo port 5555

# Connection pool stats
curl http://localhost:8000/stats
```

## Related Documentation

- [ZeroMQ Architecture](../technical/ZEROMQ_ARCHITECTURE.md) - Detailed ZMQ implementation
- [Docker Deployment](DOCKER.md) - Container configuration
- [Configuration Guide](CONFIGURATION.md) - System parameters
- [API Reference](../API_REFERENCE.md) - REST endpoints