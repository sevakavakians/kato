# PROJECT_OVERVIEW.md - KATO Master Reference
*Last Updated: 2025-08-29*

## Project Identity
**Name**: KATO (Knowledge Abstraction for Traceable Outcomes)
**Vision**: Deterministic memory and prediction system for transparent, explainable AI
**Current Phase**: Production/Maintenance (Post-Modernization)

## Core Purpose
KATO processes multi-modal observations (text, vectors, emotions) and makes temporal predictions while maintaining complete transparency and traceability. Every decision is deterministic and explainable.

## Tech Stack
### Core Technologies
- **Language**: Python 3.9+
- **Container**: Docker (required for deployment)
- **Message Queue**: ZeroMQ (ROUTER/DEALER pattern)
- **Vector Database**: Qdrant with HNSW indexing
- **Cache**: Redis (for vector caching)
- **API Framework**: FastAPI
- **Testing**: pytest with fixtures

### Infrastructure
- **REST Gateway**: Port 8000 (FastAPI)
- **ZMQ Server**: Port 5555 (Internal communication)
- **Vector DB**: Qdrant (Docker container)
- **Deployment**: Docker Compose orchestration

## Core Architecture (3-Sentence Overview)
1. REST clients communicate with a FastAPI gateway that translates HTTP requests to ZeroMQ messages
2. The ZMQ server distributes work to KATO processors which maintain working memory and coordinate with Qdrant for vector similarity searches
3. All processing is deterministic with SHA1-based model identification, ensuring reproducible predictions and complete traceability

## Success Metrics
- **Determinism**: 100% reproducible outputs for identical inputs
- **Performance**: 10-100x improvement with Qdrant vs linear search
- **Test Coverage**: 128 tests with 100% pass rate
- **Latency**: Sub-second response for standard observations
- **Scalability**: Multi-instance support with processor isolation

## Key Integrations
### External Dependencies
- **Qdrant**: Vector similarity search and storage
- **Redis**: High-speed vector caching layer
- **Docker**: Container orchestration and deployment

### Internal Interfaces
- **REST API**: `/observe`, `/predict`, `/ping` endpoints
- **ZMQ Protocol**: Request/Reply pattern with JSON payloads
- **Vector Operations**: 768-dimensional embeddings support

## Performance Targets
### Speed
- **Observation Processing**: < 100ms for text observations
- **Vector Search**: < 50ms for 100k vectors (Qdrant HNSW)
- **Prediction Generation**: < 500ms end-to-end

### Scale
- **Vector Capacity**: 1M+ vectors per processor
- **Concurrent Processors**: Unlimited with unique IDs
- **Request Throughput**: 1000+ req/s with pooling

### Reliability
- **Uptime Target**: 99.9% availability
- **Data Integrity**: SHA1 hashing for model verification
- **Error Recovery**: Automatic reconnection and retry logic

## Recent Achievements
- **Vector DB Migration**: Successfully migrated from MongoDB to Qdrant
- **Architecture Modernization**: Replaced gRPC with ZeroMQ for better multiprocessing
- **Performance Optimization**: Achieved 10-100x speedup in vector operations
- **Technical Debt Reduction**: Removed legacy code, improved documentation

## Current Focus Areas
1. **Stability**: Ensuring production reliability post-modernization
2. **Documentation**: Comprehensive planning and development guides
3. **Testing**: Maintaining 100% test pass rate
4. **Performance**: Further optimization opportunities

## Development Philosophy
- **Determinism First**: Reproducibility over performance
- **Transparency**: Every decision must be traceable
- **Test-Driven**: Comprehensive test coverage before features
- **Container-Native**: All development assumes Docker environment