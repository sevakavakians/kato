# KATO System Architecture

## Overview
KATO (Knowledge Abstraction for Traceable Outcomes) is a deterministic memory and prediction system for transparent, explainable AI. This document provides a comprehensive architectural diagram showing all components and their communication patterns.

## Architecture Diagram

```mermaid
graph TB
    %% External Layer
    subgraph "External Clients"
        CLIENT[HTTP Clients]
        WS_CLIENT[WebSocket Clients]
        TEST[Test Runner]
    end

    %% Docker Infrastructure Layer
    subgraph "Docker Infrastructure"
        subgraph "KATO Instances"
            KATO1[KATO Primary<br/>Port: 8001<br/>processor_id: primary]
            KATO2[KATO Testing<br/>Port: 8002<br/>processor_id: testing]
            KATO3[KATO Analytics<br/>Port: 8003<br/>processor_id: analytics]
        end

        subgraph "Database Services"
            CLICKHOUSE[(ClickHouse<br/>Port: 8123/9000)]
            QDRANT[(Qdrant<br/>Port: 6333/6334)]
        end

        NETWORK[Docker Network<br/>172.28.0.0/16]
    end

    %% Application Layer - Inside Each KATO Instance
    subgraph "KATO Application (Per Instance)"
        %% API Layer
        subgraph "API Layer"
            FASTAPI[FastAPI Service<br/>+ CORS Middleware<br/>+ Request Logger]
            REST[REST Endpoints]
            WEBSOCKET[WebSocket Handler]
        end

        %% Core Processing Layer
        subgraph "Core Processing"
            KATO_PROC[KatoProcessor<br/>Main Controller]
            
            subgraph "Processor Components"
                MEM_MGR[MemoryManager<br/>STM/LTM Operations]
                PAT_PROC[PatternProcessor<br/>Pattern Recognition]
                VEC_PROC[VectorProcessor<br/>Vector Operations]
                OBS_PROC[ObservationProcessor<br/>Input Processing]
                PAT_OPS[PatternOperations<br/>Pattern Manipulation]
            end
        end

        %% Search & Indexing Layer
        subgraph "Search & Indexing"
            PAT_SEARCH[PatternSearcher<br/>Pattern Matching]
            VEC_INDEX[VectorIndexer<br/>Vector Search]
            VEC_ENGINE[VectorSearchEngine<br/>Modern Search]
        end

        %% Storage Abstraction Layer
        subgraph "Storage Abstraction"
            CH_WRITER[ClickHouseWriter<br/>Pattern Storage]
            REDIS_WRITER[RedisWriter<br/>Metadata Cache]
            QDRANT_STORE[QdrantStore<br/>Vector Store]
            VEC_STORE[VectorStore Interface]
        end

        %% Configuration Layer
        subgraph "Configuration"
            SETTINGS[Settings<br/>ProcessorConfig<br/>DatabaseConfig<br/>LearningConfig]
            API_CONFIG[APIServiceConfig]
            DB_CONFIG[DatabaseManager]
        end
    end

    %% Middleware Components
    subgraph "Middleware & Utils"
        METRICS[Metrics Calculator<br/>Normalized Entropy, ITFDF, etc.]
        LOGGING[Structured Logging<br/>Trace IDs]
        EXCEPTION[Exception Handlers<br/>KatoBaseException]
        CACHE[Result Caching<br/>LRU Cache]
    end

    %% Data Models
    subgraph "Data Models"
        PATTERN[Pattern<br/>Representation]
        VECTOR_OBJ[VectorObject<br/>768-dim embeddings]
        PYDANTIC[Pydantic Models<br/>Request/Response]
    end

    %% Communication Flows
    CLIENT -->|HTTP/HTTPS| FASTAPI
    WS_CLIENT -->|WebSocket| WEBSOCKET
    TEST -->|HTTP| FASTAPI

    FASTAPI --> REST
    FASTAPI --> WEBSOCKET
    REST -->|async| KATO_PROC
    WEBSOCKET -->|async| KATO_PROC

    KATO_PROC --> MEM_MGR
    KATO_PROC --> PAT_PROC
    KATO_PROC --> VEC_PROC
    KATO_PROC --> OBS_PROC
    KATO_PROC --> PAT_OPS

    OBS_PROC --> VEC_PROC
    OBS_PROC --> MEM_MGR
    PAT_OPS --> PAT_PROC
    PAT_OPS --> VEC_PROC

    PAT_PROC --> PAT_SEARCH
    VEC_PROC --> VEC_INDEX
    VEC_INDEX --> VEC_ENGINE

    PAT_PROC --> CH_WRITER
    PAT_PROC --> REDIS_WRITER
    VEC_ENGINE --> VEC_STORE
    VEC_STORE --> QDRANT_STORE

    CH_WRITER -->|kb_id partitioning| CLICKHOUSE
    REDIS_WRITER -->|metadata cache| REDIS
    QDRANT_STORE -->|collection per kb_id| QDRANT

    KATO_PROC --> METRICS
    FASTAPI --> LOGGING
    FASTAPI --> EXCEPTION

    %% Configuration Dependencies
    SETTINGS -.->|inject| KATO_PROC
    SETTINGS -.->|inject| CH_WRITER
    API_CONFIG -.->|inject| FASTAPI
    DB_CONFIG -.->|manage| CLICKHOUSE
    DB_CONFIG -.->|manage| QDRANT
    DB_CONFIG -.->|manage| REDIS

    %% Network Connections
    KATO1 ---|Docker Network| NETWORK
    KATO2 ---|Docker Network| NETWORK
    KATO3 ---|Docker Network| NETWORK
    CLICKHOUSE ---|Docker Network| NETWORK
    QDRANT ---|Docker Network| NETWORK
    REDIS ---|Docker Network| NETWORK

    %% Styling
    classDef api fill:#e1f5fe,stroke:#01579b,stroke-width:2px
    classDef processor fill:#fff3e0,stroke:#e65100,stroke-width:2px
    classDef storage fill:#f3e5f5,stroke:#4a148c,stroke-width:2px
    classDef config fill:#e8f5e9,stroke:#1b5e20,stroke-width:2px
    classDef middleware fill:#fce4ec,stroke:#880e4f,stroke-width:2px
    classDef database fill:#fff9c4,stroke:#f57f17,stroke-width:2px
    
    class FASTAPI,REST,WEBSOCKET api
    class KATO_PROC,MEM_MGR,PAT_PROC,VEC_PROC,OBS_PROC,PAT_OPS processor
    class SUPER_KB,QDRANT_STORE,VEC_STORE storage
    class SETTINGS,API_CONFIG,DB_CONFIG config
    class METRICS,LOGGING,EXCEPTION,CACHE middleware
    class CLICKHOUSE,QDRANT,REDIS database
```

## Component Descriptions

### 1. API Layer (FastAPI)
The API layer provides the external interface for KATO:

- **FastAPI Service**: Modern async Python web framework with automatic OpenAPI documentation
- **REST Endpoints**: 
  - `/observe` - Process observations
  - `/learn` - Learn patterns from STM
  - `/predictions` - Get predictions
  - `/stm` - View short-term memory
  - `/clear-stm` - Clear short-term memory
  - `/pattern/{id}` - Get specific pattern
  - `/sessions/{session_id}/config` - Update session configuration
  - `/metrics` - System metrics
- **WebSocket Handler**: Real-time bidirectional communication at `/ws`
- **Middleware**:
  - CORS for cross-origin requests
  - Request logging with trace IDs
  - Performance timing

### 2. Core Processing Layer
The heart of KATO's AI processing:

- **KatoProcessor**: Main controller that orchestrates all operations
  - Manages processor lifecycle
  - Coordinates between components
  - Maintains processor state
  
- **MemoryManager**: Handles memory operations
  - Short-Term Memory (STM) management
  - Long-Term Memory (LTM) operations
  - Emotives accumulation
  - State variable management
  
- **PatternProcessor**: Core pattern recognition
  - Pattern learning from STM
  - Pattern matching and prediction
  - Temporal and non-temporal patterns
  - Frequency and emotives tracking
  
- **VectorProcessor**: Vector embedding operations
  - 768-dimensional vector processing
  - Vector similarity search
  - Vector-to-symbol conversion
  
- **ObservationProcessor**: Input processing
  - String symbol processing
  - Vector data handling
  - Emotives processing
  - Auto-learning triggers
  
- **PatternOperations**: Pattern utilities
  - Pattern manipulation
  - Pattern comparison
  - Pattern merging

### 3. Search & Indexing Layer
High-performance search capabilities:

- **PatternSearcher**: Pattern matching engine
  - Recall threshold filtering
  - Partial pattern matching
  - Frequency-based ranking
  
- **VectorIndexer**: Legacy vector search
  - Parallel search workers
  - Round-robin distribution
  
- **VectorSearchEngine**: Modern vector search
  - Qdrant integration
  - HNSW indexing
  - Result caching
  - Batch processing

### 4. Storage Layer
Database abstraction and management:

- **ClickHouseWriter**: ClickHouse pattern storage
  - Pattern data with SHA1 hashing
  - Multi-stage filter pipeline (MinHash/LSH/Bloom)
  - Partitioning by kb_id for isolation
  - Billion-scale performance

- **RedisWriter**: Redis metadata caching
  - Pattern frequency counters
  - Emotive profiles (rolling window)
  - Fast metadata access
  - Session state management

- **QdrantStore**: Vector database implementation
  - HNSW index configuration
  - Quantization support
  - GPU acceleration ready
  - Collection management

- **VectorStore Interface**: Storage abstraction
  - Backend agnostic interface
  - Async operations
  - Batch processing

### 5. Database Services

#### ClickHouse
- **Purpose**: Pattern data storage with high-performance filtering
- **Table Structure**:
  - `patterns` - Learned patterns partitioned by kb_id
  - Columns: name, kb_id, length, events, emotive_profile, metadata, observation_count
- **Indexing**: Primary key on (kb_id, name) with Bloom filter
- **Partitioning**: By kb_id for node isolation
- **Performance**: Billion-scale with multi-stage filter pipeline

#### Redis
- **Purpose**: Pattern metadata caching and session state
- **Data Structures**:
  - Pattern frequency counters (per kb_id)
  - Emotive profiles (rolling windows)
  - Session state (TTL-based)
- **Key Namespacing**: By session_id and kb_id for isolation

#### Qdrant
- **Purpose**: High-performance vector similarity search
- **Features**:
  - HNSW indexing for fast search
  - Collection per kb_id
  - Cosine similarity metric
  - Optional quantization

### 6. Configuration System
Comprehensive configuration management:

- **Settings**: Central configuration using Pydantic
  - ProcessorConfig - Instance identification
  - LearningConfig - Learning parameters
  - DatabaseConfig - Database connections
  - ProcessingConfig - Processing behavior
  
- **APIServiceConfig**: API-specific settings
  - Uvicorn configuration
  - Port and host settings
  - Worker configuration
  
- **DatabaseManager**: Connection management
  - Connection pooling
  - Health checks
  - Failover support

### 7. Middleware & Utilities

- **Metrics Calculator**:
  - Normalized entropy calculations
  - ITFDF similarity metrics
  - Confidence and evidence scoring
  - Confluence probability
  
- **Structured Logging**:
  - JSON or human-readable formats
  - Trace ID propagation
  - Performance timing
  - Request/response logging
  
- **Exception Handling**:
  - Hierarchical exception classes
  - Structured error responses
  - Trace ID in errors
  
- **Result Caching**:
  - LRU cache for predictions
  - Vector search result caching
  - Configurable cache sizes

### 8. Test Infrastructure

- **Fixture-based Testing**:
  - Automatic processor_id isolation
  - Per-test database isolation
  - Parallel test execution
  
- **Local Python Execution**:
  - Tests run locally, connect to Docker
  - Fast debugging with print/breakpoints
  - No container rebuilds for tests

## Communication Patterns

### Synchronous Communication
1. **HTTP REST**: Client → FastAPI → KatoProcessor → Response
2. **Database Queries**: Processors → ClickHouse/Qdrant/Redis → Results

### Asynchronous Communication
1. **WebSocket**: Bidirectional real-time updates
2. **Async Processing**: FastAPI async handlers with processor locks

### Isolation Mechanisms
1. **Processor ID Isolation**: Each instance has unique processor_id
2. **Database Isolation**: Separate collections/databases per processor
3. **Lock-based Synchronization**: Processing lock ensures sequential operations

## Deployment Architecture

### Docker Composition
- **ClickHouse**: Shared database service (partitioned by kb_id)
- **Redis**: Shared cache and session service
- **Qdrant**: Shared vector database
- **KATO Instances**: Multiple isolated processors
- **Docker Network**: Bridge network for inter-service communication

### Scaling Strategy
1. **Horizontal Scaling**: Add more KATO instances with unique kb_id values
2. **Database Scaling**: ClickHouse distributed tables, Qdrant clustering, Redis cluster
3. **Load Balancing**: Optional Nginx for distribution

## Security Considerations

1. **Database Security**:
   - ClickHouse authentication and access control
   - Redis authentication (optional)
   - Network isolation

2. **API Security**:
   - CORS configuration
   - Optional API keys
   - Rate limiting ready

3. **Data Isolation**:
   - Complete kb_id isolation via partitioning
   - No cross-contamination between nodes
   - Audit trail via trace IDs

## Performance Optimizations

1. **Multi-Stage Filter Pipeline**:
   - MinHash for billion-scale similarity at O(1)
   - LSH bucketing for candidate reduction
   - Bloom filters for fast existence checks
   - ClickHouse partitioning for kb_id isolation

2. **Vector Search**:
   - HNSW indexing for O(log n) search
   - Result caching in Redis
   - Batch processing

3. **Pattern Matching**:
   - ClickHouse partitioned queries
   - Parallel search workers
   - Frequency-based pruning from Redis

4. **Memory Management**:
   - Deque for efficient STM
   - Redis metadata caching
   - Connection pooling

## Monitoring & Observability

1. **Metrics Endpoint**: `/metrics` for system stats
2. **Health Checks**: `/health` for liveness
3. **Structured Logging**: JSON logs with trace IDs
4. **Performance Timing**: Request duration tracking

This architecture provides a robust, scalable, and transparent AI system with complete explainability and traceability of all operations.