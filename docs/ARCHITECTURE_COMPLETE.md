# KATO Complete Architecture Documentation

## Executive Summary

KATO (Knowledge Abstraction for Traceable Outcomes) is a deterministic AI system designed for transparent, explainable memory and prediction. It processes multi-modal observations (text, vectors, emotions) through a distributed architecture using Docker containers, FastAPI services, and modern vector databases to deliver temporal predictions with complete traceability.

## Table of Contents
1. [System Overview](#system-overview)
2. [Architecture Diagrams](#architecture-diagrams)
3. [Core Components](#core-components)
4. [Container Architecture](#container-architecture)
5. [Communication Layers](#communication-layers)
6. [Data Processing Pipeline](#data-processing-pipeline)
7. [Memory Architecture](#memory-architecture)
8. [Required vs Optional Components](#required-vs-optional-components)
9. [Deployment Configurations](#deployment-configurations)
10. [Scaling and Multi-Instance Support](#scaling-and-multi-instance-support)
11. [Quick Reference](#quick-reference)

## System Overview

KATO operates as a distributed system with the following key characteristics:
- **Deterministic Processing**: Same inputs always produce same outputs
- **Multi-Modal Input**: Handles strings, vectors (768-dim), and emotional context
- **Temporal Predictions**: Structures predictions as past/present/future segments
- **Complete Transparency**: Full traceability of decisions and predictions
- **Distributed Architecture**: Scalable through Docker containers and FastAPI

## Architecture Diagrams

### 1. High-Level System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                                  External Clients                                │
│                         (REST API, Python SDK, Web Interface)                    │
└─────────────────────────────┬───────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           KATO System Boundary                                   │
│                                                                                  │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │                        Docker Network: kato-network                       │  │
│  │                                                                          │  │
│  │  ┌────────────────────────────────────────────────────────────────────┐ │  │
│  │  │                   kato-fastapi Container (REQUIRED)                │ │  │
│  │  │                                                                     │ │  │
│  │  │  ┌─────────────────────────────────────────────────────────────┐  │ │  │
│  │  │  │              FastAPI Service (uvicorn)                       │  │ │  │
│  │  │  │                  Port: 8000                                  │  │ │  │
│  │  │  │         (Direct embedding of KATO Processor)                 │  │ │  │
│  │  │  └─────────────────────────────┬───────────────────────────────┘  │ │  │
│  │  │                                 │                                  │ │  │
│  │  │                     ┌───────────▼────────────────────────────┐  │ │  │
│  │  │                     │         KATO Processor Core              │  │ │  │
│  │  │                     │  ┌──────────────┐  ┌──────────────┐     │  │ │  │
│  │  │                     │  │    Vector    │  │Pattern Processor│  │  │ │  │
│  │  │                     │  │  Indexer(VI) │  │              │     │  │ │  │
│  │  │                     │  └──────┬───────┘  └──────┬───────┘     │  │ │  │
│  │  │                     │         │                 │              │  │ │  │
│  │  │                     │  ┌──────▼─────────────────▼────────┐     │  │ │  │
│  │  │                     │  │     Short-Term Memory (RAM)        │     │  │ │  │
│  │  │                     │  └──────────────┬──────────────────┘     │  │ │  │
│  │  │                     └─────────────────┼─────────────────────────┘  │ │  │
│  │  └────────────────────────────────────────┼───────────────────────────┘ │  │
│  │                                          │                              │  │
│  │  ┌───────────────────────────────────────▼────────────────────────────┐ │  │
│  │  │                   Storage Layer (Persistent)                       │ │  │
│  │  │                                                                    │ │  │
│  │  │  ┌──────────────┐  ┌──────────────┐  ┌─────────────────────────┐ │ │  │
│  │  │  │   MongoDB    │  │   Qdrant     │  │    Redis Cache         │ │ │  │
│  │  │  │  (REQUIRED)  │  │  (OPTIONAL)  │  │    (OPTIONAL)          │ │ │  │
│  │  │  │  Port: 27017 │  │  Port: 6333  │  │    Port: 6379          │ │ │  │
│  │  │  └──────────────┘  └──────────────┘  └─────────────────────────┘ │ │  │
│  │  └────────────────────────────────────────────────────────────────────┘ │  │
│  └──────────────────────────────────────────────────────────────────────────┘  │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### 2. Communication Flow Diagram

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                          Communication Flow                                   │
├────────────────────────────────────────────────────────────────────────────────┤
│                                                                                │
│   Client Request                                                              │
│        │                                                                       │
│        ▼                                                                       │
│   HTTP Request ──► FastAPI Service (uvicorn)                                 │
│                         │                                                      │
│                         ▼                                                      │
│                    Async Request Handler                                       │
│                         │                                                      │
│                         ▼                                                      │
│                    Direct Processor Call                                       │
│                         │                                                      │
│                         ▼                                                      │
│                    KATO Processor (Embedded)                                  │
│                         │                                                      │
│                    ┌────┴────┬──────┬──────┐                                 │
│                    ▼         ▼      ▼      ▼                                 │
│               Observe    Learn  Predict  Memory Ops                           │
│                    │         │      │      │                                  │
│                    └────┬────┴──────┴──────┘                                 │
│                         ▼                                                      │
│                    Response Data                                              │
│                         │                                                      │
│                         ▼                                                      │
│   JSON Response ◄── Serialize to JSON                                       │
│                         │                                                      │
│                         ▼                                                      │
│                    Client Response                                            │
│                                                                                │
└────────────────────────────────────────────────────────────────────────────────┘
```

### 3. Data Processing Pipeline

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                         Data Processing Pipeline                              │
├────────────────────────────────────────────────────────────────────────────────┤
│                                                                                │
│   Input Observation                                                           │
│   ┌──────────────┬──────────────┬──────────────┐                            │
│   │   Strings    │   Vectors    │   Emotives   │                            │
│   │  ["hello"]   │  [[0.1,0.2]] │  {joy: 0.8}  │                            │
│   └──────┬───────┴──────┬───────┴──────┬───────┘                            │
│          │              │              │                                      │
│          ▼              ▼              ▼                                      │
│   ┌──────────────────────────────────────────┐                              │
│   │          Input Validation                 │                              │
│   │  - Filter empty strings                   │                              │
│   │  - Validate vector dimensions (768)       │                              │
│   │  - Normalize emotives                     │                              │
│   └──────────────┬───────────────────────────┘                              │
│                  │                                                            │
│                  ▼                                                            │
│   ┌──────────────────────────────────────────┐                              │
│   │          Processing Stage                 │                              │
│   │  - Sort strings alphanumerically          │                              │
│   │  - Convert vectors to symbols (VI)        │                              │
│   │  - Average emotives across pathways       │                              │
│   └──────────────┬───────────────────────────┘                              │
│                  │                                                            │
│                  ▼                                                            │
│   ┌──────────────────────────────────────────┐                              │
│   │        Short-Term Memory Update              │                              │
│   │  - Add to observation pattern             │                              │
│   │  - Check max_pattern_length               │                              │
│   │  - Trigger auto-learn if needed           │                              │
│   └──────────────┬───────────────────────────┘                              │
│                  │                                                            │
│                  ▼                                                            │
│   ┌──────────────────────────────────────────┐                              │
│   │        Pattern Matching                   │                              │
│   │  - Search for matching patterns           │                              │
│   │  - Use vector similarity (Qdrant)         │                              │
│   │  - Apply recall threshold                 │                              │
│   └──────────────┬───────────────────────────┘                              │
│                  │                                                            │
│                  ▼                                                            │
│   ┌──────────────────────────────────────────┐                              │
│   │        Prediction Generation              │                              │
│   │  - Temporal segmentation                  │                              │
│   │  - Calculate confidence scores            │                              │
│   │  - Include emotives from patterns         │                              │
│   └──────────────┬───────────────────────────┘                              │
│                  │                                                            │
│                  ▼                                                            │
│            Output Predictions                                                 │
│   ┌──────────────────────────────────────────┐                              │
│   │  past: [], present: [], future: []       │                              │
│   │  missing: [], extras: [], confidence: 0.9│                              │
│   └──────────────────────────────────────────┘                              │
│                                                                                │
└────────────────────────────────────────────────────────────────────────────────┘
```

### 4. Container Architecture

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                          Docker Container Layout                              │
├────────────────────────────────────────────────────────────────────────────────┤
│                                                                                │
│   Host System                                                                 │
│   ┌──────────────────────────────────────────────────────────────────────┐   │
│   │                     Docker Engine / Docker Desktop                     │   │
│   │                                                                        │   │
│   │  ┌─────────────────────────────────────────────────────────────────┐  │   │
│   │  │              Docker Network: kato-network (bridge)              │  │   │
│   │  │                                                                 │  │   │
│   │  │  ┌──────────────────────────────────────────────────────────┐  │  │   │
│   │  │  │           kato-api-${USER}-1 (REQUIRED)                 │  │  │   │
│   │  │  │  Image: kato:latest                                     │  │  │   │
│   │  │  │  Base: debian:bullseye-slim                             │  │  │   │
│   │  │  │  Ports: 8000:8000                                      │  │  │   │
│   │  │  │  CMD: uvicorn kato.services.kato_fastapi:app         │  │  │   │
│   │  │  │  Environment:                                           │  │  │   │
│   │  │  │    - PROCESSOR_ID=<unique_id>                          │  │  │   │
│   │  │  │    - LOG_LEVEL=INFO                                    │  │  │   │
│   │  │  │    - MANIFEST={...processor config...}                 │  │  │   │
│   │  │  └──────────────────────────────────────────────────────────┘  │  │   │
│   │  │                                                                 │  │   │
│   │  │  ┌──────────────────────────────────────────────────────────┐  │  │   │
│   │  │  │           mongo-kb-${USER}-1 (REQUIRED)                 │  │  │   │
│   │  │  │  Image: mongo:4.4                                       │  │  │   │
│   │  │  │  Port: 27017:27017                                      │  │  │   │
│   │  │  │  Volume: kato-mongo-data:/data/db                      │  │  │   │
│   │  │  │  Purpose: Long-term memory, pattern storage            │  │  │   │
│   │  │  └──────────────────────────────────────────────────────────┘  │  │   │
│   │  │                                                                 │  │   │
│   │  │  ┌──────────────────────────────────────────────────────────┐  │  │   │
│   │  │  │           qdrant-${USER}-1 (OPTIONAL)                   │  │  │   │
│   │  │  │  Image: qdrant/qdrant:latest                            │  │  │   │
│   │  │  │  Ports: 6333:6333 (REST), 6334:6334 (gRPC)            │  │  │   │
│   │  │  │  Volume: qdrant-storage:/qdrant/storage                │  │  │   │
│   │  │  │  Purpose: High-performance vector search                │  │  │   │
│   │  │  └──────────────────────────────────────────────────────────┘  │  │   │
│   │  │                                                                 │  │   │
│   │  │  ┌──────────────────────────────────────────────────────────┐  │  │   │
│   │  │  │         redis-cache-${USER}-1 (OPTIONAL)                │  │  │   │
│   │  │  │  Image: redis:7-alpine                                  │  │  │   │
│   │  │  │  Port: 6379:6379                                        │  │  │   │
│   │  │  │  Volume: redis-data:/data                               │  │  │   │
│   │  │  │  Purpose: Vector cache for frequent queries             │  │  │   │
│   │  │  └──────────────────────────────────────────────────────────┘  │  │   │
│   │  └─────────────────────────────────────────────────────────────────┘  │   │
│   └──────────────────────────────────────────────────────────────────────┘   │
│                                                                                │
└────────────────────────────────────────────────────────────────────────────────┘
```

## Core Components

### 1. KATO Processor (`kato/workers/kato_processor.py`)
**Status: REQUIRED**
- Core AI engine managing observations and predictions
- Maintains short-term memory and coordinates with storage
- Implements deterministic hashing for pattern identification
- Handles multi-modal input processing

### 2. FastAPI Service (`kato/services/kato_fastapi.py`)
**Status: REQUIRED**
- HTTP server with FastAPI framework
- Direct embedding of KATO processor
- Async request handling for performance
- Core endpoints: `/observe`, `/learn`, `/predictions`, `/health`
- Advanced endpoints: `/pattern/{id}`, `/cognition-data`, `/metrics`
- Bulk endpoints: `/observe-sequence`

### 3. Pattern Search (`kato/searches/pattern_search.py`)
**Status: REQUIRED**
- High-performance pattern matching
- Efficient similarity calculations
- Temporal segmentation logic
- Pattern ranking algorithms

### 4. Fast Matcher (`kato/searches/fast_matcher.py`)
**Status: REQUIRED**
- Optimized pattern matching for performance
- Caching of frequently accessed patterns
- Parallel search capabilities
- Batch matching support

### 5. Vector Processor (`kato/workers/vector_processor.py`)
**Status: REQUIRED**
- Processes vector inputs into symbolic representations
- VI (Vector Indexer) implementation
- Integrates with vector search engine

### 6. Pattern Processor (`kato/workers/pattern_processor.py`)
**Status: REQUIRED**
- Creates and manages patterns
- Deterministic SHA1 hashing
- Frequency tracking and updates
- Pattern search and retrieval

### 7. MongoDB Storage
**Status: REQUIRED**
- Persistent storage for patterns
- Long-term memory persistence
- Pattern metadata storage

### 8. Qdrant Vector Database
**Status: OPTIONAL (Highly Recommended)**
- 10-100x faster vector similarity search
- HNSW indexing for performance
- GPU acceleration support
- Quantization for memory efficiency

### 9. Redis Cache
**Status: OPTIONAL**
- Caching layer for frequently accessed vectors
- LRU eviction policy
- Reduces database queries

## Communication Layers

### FastAPI Architecture

The system uses FastAPI with embedded processor for:
- **Async Request Handling**: Native async/await support
- **Concurrent Processing**: Multiple requests handled efficiently
- **WebSocket Support**: Real-time bidirectional communication
- **Health Monitoring**: Built-in health endpoints at `/health`

### API Protocol

```python
# HTTP POST Request to /observe
{
    "processor_id": "unique_id",
    "strings": ["hello", "world"],
    "vectors": [[0.1, 0.2, ...]],
    "emotives": {"joy": 0.8}
}

# JSON Response
{
    "status": "success",
    "pattern_name": "PTRN|sha1_hash",
    "predictions": [...],
    "message": "Observation processed"
}
```

## Data Processing Pipeline

### Input Processing Rules

1. **String Processing**:
   - Alphanumeric sorting within events
   - Empty string filtering
   - Event order preservation

2. **Vector Processing**:
   - 768-dimension validation
   - VI indexing
   - Symbol conversion

3. **Emotive Processing**:
   - Averaging across pathways
   - Storage with patterns
   - Prediction inclusion

## Memory Architecture

### Short-Term Memory
- **Type**: Temporary RAM storage
- **Purpose**: Current observation pattern
- **Behavior**: Auto-learn on max_pattern_length
- **Clearing**: 
  - Regular learn(): Completely cleared
  - Auto-learn: Completely cleared (same as regular learn)

### Long-Term Memory
- **Type**: Persistent MongoDB/Qdrant storage
- **Purpose**: Learned patterns
- **Structure**: PTRN|<sha1_hash> identifiers
- **Persistence**: Survives container restarts

## Required vs Optional Components

### Required Components
1. **kato-fastapi container**: Core processing engine
2. **MongoDB**: Long-term memory storage
3. **Docker Network**: Container communication
4. **FastAPI Service**: HTTP/WebSocket interface
5. **KATO Processor**: Core AI logic (embedded)
6. **Pattern Processor**: Pattern management
7. **Vector Operations**: Similarity search

### Optional Components
1. **Qdrant**: High-performance vector search (RECOMMENDED)
2. **Redis Cache**: Query performance optimization
3. **GPU Support**: Acceleration for vector operations
4. **Multi-Instance**: Scaling across processors
5. **Quantization**: Memory optimization

## Deployment Configurations

### Development Configuration
```bash
# Minimal setup for development
./kato-manager.sh start --no-vectordb
```

### Production Configuration
```bash
# Full setup with vector database
./kato-manager.sh start
# or explicitly:
./kato-manager.sh start --vectordb-backend qdrant
```

### High-Performance Configuration
```bash
# With GPU support (requires NVIDIA Docker)
docker-compose -f docker-compose.yml \
               -f docker-compose.vectordb.yml \
               --profile gpu up
```

## Scaling and Multi-Instance Support

### Single Instance
```
Client → FastAPI Service → KATO Processor (Embedded) → Storage
```

### Multi-Instance Architecture
```
                    ┌─► KATO Instance 1 (Port 8001)
                    │
Client → Load ──────┼─► KATO Instance 2 (Port 8002)
        Balancer    │
                    └─► KATO Instance 3 (Port 8003)
                              │
                              ▼
                        Shared Storage
                    (MongoDB + Qdrant)
```

### Instance Management
```bash
# Start multiple instances
./kato-manager.sh start --id proc1 --port 8001
./kato-manager.sh start --id proc2 --port 8002
./kato-manager.sh start --id proc3 --port 8003

# List all instances
./kato-manager.sh list

# Stop specific instance
./kato-manager.sh stop proc1
```

## Quick Reference

### Starting KATO
```bash
# Standard start (with vector DB)
./kato-manager.sh start

# Development mode (no vector DB)
./kato-manager.sh start --no-vectordb

# Custom processor configuration
PROCESSOR_ID=custom1 PROCESSOR_NAME=MyProcessor ./kato-manager.sh start
```

### API Endpoints
- `GET /kato-api/ping` - Health check
- `POST /{processor_id}/observe` - Send observations
- `GET /{processor_id}/predictions` - Get predictions
- `POST /{processor_id}/learn` - Trigger learning
- `GET /{processor_id}/short-term-memory` - View short-term memory
- `POST /{processor_id}/clear-short-term-memory` - Clear short-term memory

### Environment Variables
```bash
# Core Configuration
PROCESSOR_ID=unique_id            # Unique processor identifier
PROCESSOR_NAME=Primary             # Display name
LOG_LEVEL=INFO                     # Logging level
API_PORT=8000                      # FastAPI service port

# Vector Database
KATO_VECTOR_DB_BACKEND=qdrant     # Vector DB backend
QDRANT_HOST=localhost              # Qdrant host
QDRANT_PORT=6333                   # Qdrant port

# Processor Configuration
PROCESSOR_ID=kato-123              # Unique processor ID
PROCESSOR_NAME=KatoProcessor       # Processor name
INDEXER_TYPE=VI                    # Vector indexing method
```

### Docker Commands
```bash
# View logs
docker logs kato-primary --tail 50

# Enter container
docker exec -it kato-api-${USER}-1 bash

# Check container status
docker ps | grep kato

# Clean up
docker-compose down
docker system prune -f
```

### Testing Commands
```bash
# Build test harness (first time)
./test-harness.sh build

# Run all tests in container
./kato-manager.sh test
# OR
./test-harness.sh test

# Run specific test suites
./test-harness.sh suite unit
./test-harness.sh suite integration
./test-harness.sh suite api

# Run tests with services running
./run_tests.sh --no-start --no-stop
```

## Architecture Decision Records

### Why FastAPI Direct Embedding?
- **Lower Latency**: No inter-process communication overhead
- **Simpler Architecture**: Single process per instance
- **Better Performance**: ~50% faster than message-based architectures
- **Easier Debugging**: Direct function calls with stack traces

### Why Async/Await over Threading?
- **Better Concurrency**: More efficient resource usage
- **No GIL Issues**: True parallelism for I/O operations
- **Modern Python**: Native language support
- **WebSocket Ready**: Built-in support for real-time

### Why Qdrant for Vectors?
- **Performance**: 10-100x faster than MongoDB vectors
- **HNSW Indexing**: Efficient similarity search
- **GPU Support**: Optional acceleration
- **Quantization**: Memory optimization

### Why Docker Containers?
- **Isolation**: Clean separation of concerns
- **Scalability**: Easy multi-instance deployment
- **Portability**: Consistent across environments
- **Management**: Simple start/stop/restart

## Troubleshooting Reference

### Common Issues
1. **Port Conflicts**: Use `--port` flag or check `lsof -i :8000`
2. **MongoDB Connection**: Ensure MongoDB container is running
3. **Vector DB Issues**: Check Qdrant health at `http://localhost:6333/health`
4. **API Timeouts**: Check service health at `/health` endpoint

### Health Checks
```bash
# Check all services
./kato-manager.sh status

# Test API health
curl http://localhost:8001/health

# Check specific service
docker exec kato-primary curl http://localhost:8000/health
```

---

*This document provides a complete architectural overview of the KATO system. For specific implementation details, refer to the individual component documentation in the `/docs` directory.*