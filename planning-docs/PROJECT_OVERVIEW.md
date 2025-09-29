# PROJECT_OVERVIEW.md - KATO Master Reference
*Last Updated: 2025-08-30*

## Project Identity
**Name**: KATO (Knowledge Abstraction for Traceable Outcomes)
**Vision**: Deterministic memory and prediction system for transparent, explainable AI
**Current Phase**: Phase 2 - API Feature Development

## Core Purpose
KATO processes multi-modal observations (text, vectors, emotions) and makes temporal predictions while maintaining complete transparency and traceability. Every decision is deterministic and explainable.

## Tech Stack
### Core Technologies
- **Language**: Python 3.9+
- **Container**: Docker (required for deployment)
- **API Framework**: FastAPI with uvicorn
- **Vector Database**: Qdrant with HNSW indexing
- **Cache**: Redis (for vector caching)
- **Database**: MongoDB for pattern storage
- **Testing**: pytest with fixtures

### Infrastructure
- **FastAPI Service**: Ports 8001-8003 (Primary/Testing/Analytics)
- **Vector DB**: Qdrant (Docker container)
- **MongoDB**: Pattern and metadata storage
- **Deployment**: Docker Compose orchestration

## Core Architecture (3-Sentence Overview)
1. HTTP clients communicate with FastAPI services that have embedded KATO processors for direct processing
2. Each processor maintains working memory and coordinates with MongoDB for patterns and Qdrant for vector similarity searches
3. All processing is deterministic with SHA1-based pattern identification, ensuring reproducible predictions and complete traceability

## Success Metrics
- **Determinism**: 100% reproducible outputs for identical inputs ✅
- **Performance**: ~291x improvement with optimized pattern matching ✅
- **Test Coverage**: Stress test performance issues resolved - 7/9 integration tests now passing ✅
- **Latency**: ~10ms average response time for standard observations ✅
- **Scalability**: Multi-instance support with processor isolation ✅

## Key Integrations
### External Dependencies
- **Qdrant**: Vector similarity search and storage
- **Redis**: High-speed vector caching layer
- **Docker**: Container orchestration and deployment

### Internal Interfaces
- **FastAPI Endpoints**: `/observe`, `/predictions`, `/learn`, `/health`, `/observe-sequence`
- **WebSocket**: Real-time communication at `/ws`
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
- **Data Integrity**: SHA1 hashing for pattern verification
- **Error Recovery**: Automatic reconnection and retry logic

## Recent Achievements
- **Stress Test Performance Fix**: Resolved "Server disconnected" errors in concurrent session tests with enhanced connection pooling and semaphore-based concurrency control (December 2024)
- **Session Architecture Phase 1**: Complete legacy code removal and direct configuration architecture
- **Configuration Centralization**: New ConfigurationService eliminates code duplication and provides unified configuration management
- **FastAPI Migration**: Complete migration from REST/ZMQ to FastAPI direct embedding
- **Vector DB Migration**: Successfully migrated from MongoDB to Qdrant
- **Performance Optimization**: Achieved ~291x speedup in pattern matching operations
- **Technical Debt Reduction**: Removed all legacy ZMQ/REST gateway components and genome_manifest dependencies
- **Code Cleanup**: Removed model.py, modeler.py, extraction_workers, legacy test scripts

## Development Phases

### Phase 1: COMPLETED ✅ - System Stabilization & Performance Optimization
- **Duration**: Multiple sessions over 2-3 days
- **Key Achievements**: 100% test pass rate, ~291x performance improvement, infrastructure stability
- **Status**: Production-ready foundation established

### Session Architecture Transformation: IN PROGRESS 🔄
- **Phase 1 COMPLETED ✅**: Legacy code removal and direct configuration architecture
  - **Duration**: 1 session
  - **Key Achievements**: Removed genome_manifest dependencies, centralized configuration management, maintained backward compatibility
  - **Technical Impact**: ConfigurationService created, processor_id handling simplified, code duplication eliminated
- **Phase 2 UPCOMING**: Update API Endpoints for session-aware request handling
- **Phase 3 PLANNED**: Multi-user session management with isolation
- **Phase 4 PLANNED**: Session persistence and restoration capabilities

### Phase 2: UPDATED - API Feature Development  
- **Focus**: observe-sequence endpoint for bulk processing and session-aware API endpoints
- **Timeline**: Estimated 2-3 days for full implementation
- **Goal**: Enable efficient batch operations and multi-user session support while maintaining KATO principles
- **Requirements**: Vector processing, alphanumeric sorting, session isolation, comprehensive testing

### Phase 3: PLANNED - Advanced Features
- **Future Focus**: Additional API endpoints, enhanced processing capabilities
- **Dependencies**: Successful completion of Phase 2
- **Timeline**: TBD based on Phase 2 outcomes

## Current Focus Areas
1. **API Development**: observe-sequence endpoint design and implementation
2. **Batch Processing**: Efficient multi-sequence handling
3. **Test Coverage**: Comprehensive testing for new features
4. **Documentation**: API specification updates

## Development Philosophy
- **Determinism First**: Reproducibility over performance
- **Transparency**: Every decision must be traceable
- **Test-Driven**: Comprehensive test coverage before features
- **Container-Native**: All development assumes Docker environment