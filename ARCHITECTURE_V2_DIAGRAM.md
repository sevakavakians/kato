# KATO v2.0 System Architecture

## Major Architectural Changes from v1.0 to v2.0

### Key Improvements:
1. **Multi-User Session Isolation**: Complete STM isolation per user session
2. **Redis Integration**: Session state management with TTL support
3. **Connection Pooling**: Production-grade database connection management
4. **Write Durability**: MongoDB write concern changed from w=0 to w=majority
5. **Modular Architecture**: Refactored processors with clear separation of concerns
6. **Session Middleware**: Automatic session handling in API layer

## Complete v2.0 Architecture Diagram

```mermaid
graph TB
    %% External Layer
    subgraph "External Clients"
        CLIENT1[User 1 - HTTP Client]
        CLIENT2[User 2 - HTTP Client]
        CLIENT3[User N - HTTP Client]
        WS_CLIENT[WebSocket Clients]
        TEST[Test Runners]
    end

    %% Docker Infrastructure Layer
    subgraph "Docker Infrastructure v2.0"
        subgraph "KATO v2 Instances"
            KATO1[KATO Primary v2<br/>Port: 8001<br/>processor_id: primary-v2]
            KATO2[KATO Testing v2<br/>Port: 8002<br/>processor_id: testing-v2]
            KATO3[KATO Analytics v2<br/>Port: 8003<br/>processor_id: analytics-v2]
        end

        subgraph "Database Services"
            MONGO[(MongoDB 4.4<br/>Port: 27017<br/>Write Concern majority)]
            QDRANT[(Qdrant<br/>Port: 6333<br/>Vector Storage)]
            REDIS[(Redis 7<br/>Port: 6379<br/>Session Store)]
        end

        NETWORK[Docker Network v2<br/>kato-network-v2]
    end

    %% v2.0 Application Layer
    subgraph "KATO v2.0 Application Architecture"
        %% API Layer with Session Management
        subgraph "API Layer v2.0"
            FASTAPI_V2[FastAPI v2 Service<br/>Session Middleware<br/>CORS + Logging]
            
            subgraph "v2.0 Endpoints"
                SESSION_EP[Session Management<br/>/v2/sessions]
                OBSERVE_EP[Isolated Observations<br/>/v2/sessions/id/observe]
                LEARN_EP[Session Learning<br/>/v2/sessions/id/learn]
                PRED_EP[Session Predictions<br/>/v2/sessions/id/predictions]
                COMPAT_EP[Legacy Support<br/>/v1 Compatibility]
            end
        end

        %% Session Management Layer (NEW)
        subgraph "Session Management (NEW)"
            SESSION_MGR[SessionManager<br/>User Isolation]
            SESSION_STATE[SessionState<br/>Per-User STM/Emotives]
            SESSION_MW[SessionMiddleware<br/>Auto Session Handling]
            SESSION_STORE[Session Storage<br/>Redis Backend]
        end

        %% Connection Pool Layer (NEW)
        subgraph "Resilience Layer (NEW)"
            MONGO_POOL[MongoConnectionPool<br/>Connection Pooling<br/>Write Concern majority<br/>Health Checks]
            QDRANT_POOL[QdrantConnectionPool<br/>Connection Management<br/>Auto-reconnect]
        end

        %% Refactored Core Processing
        subgraph "Core Processing (Refactored)"
            KATO_PROC[KatoProcessor<br/>Orchestrator]
            
            subgraph "Modular Components"
                MEM_MGR[MemoryManager<br/>STM LTM Session State]
                PAT_PROC[PatternProcessor<br/>Pattern Recognition]
                VEC_PROC[VectorProcessor<br/>Vector Operations]
                OBS_PROC[ObservationProcessor<br/>Input Processing]
                PAT_OPS[PatternOperations<br/>Pattern CRUD]
            end
        end

        %% Search & Storage (Enhanced)
        subgraph "Search & Storage"
            PAT_SEARCH[PatternSearcher]
            VEC_ENGINE[VectorSearchEngine<br/>Modern Search]
            SUPER_KB[SuperKnowledgeBase<br/>Write Concern majority]
            QDRANT_STORE[QdrantStore]
        end

        %% Configuration (Enhanced)
        subgraph "Configuration v2.0"
            SETTINGS[Settings v2<br/>Session Config<br/>Pool Config]
            API_CONFIG[APIServiceConfig v2]
            DB_CONFIG[DatabaseManager v2<br/>Connection Pools]
        end
    end

    %% Data Flow - Session Isolated
    subgraph "Session-Isolated Data Flow"
        FLOW1[User 1 Request to Session 1 to STM 1]
        FLOW2[User 2 Request to Session 2 to STM 2]
        FLOW3[User N Request to Session N to STM N]
    end

    %% Communication Flows
    CLIENT1 -->|HTTP + Session ID| FASTAPI_V2
    CLIENT2 -->|HTTP + Session ID| FASTAPI_V2
    CLIENT3 -->|HTTP + Session ID| FASTAPI_V2
    
    FASTAPI_V2 --> SESSION_MW
    SESSION_MW --> SESSION_MGR
    SESSION_MGR --> SESSION_STATE
    SESSION_STATE -->|Store/Retrieve| REDIS
    
    FASTAPI_V2 --> SESSION_EP
    FASTAPI_V2 --> OBSERVE_EP
    FASTAPI_V2 --> LEARN_EP
    FASTAPI_V2 --> PRED_EP
    
    SESSION_EP -->|async| KATO_PROC
    OBSERVE_EP -->|with session state| KATO_PROC
    LEARN_EP -->|with session state| KATO_PROC
    
    KATO_PROC -->|set/get STM| MEM_MGR
    MEM_MGR -->|session isolation| SESSION_STATE
    
    KATO_PROC --> PAT_PROC
    KATO_PROC --> VEC_PROC
    KATO_PROC --> OBS_PROC
    KATO_PROC --> PAT_OPS
    
    PAT_PROC --> SUPER_KB
    SUPER_KB --> MONGO_POOL
    MONGO_POOL -->|pooled connections| MONGO
    
    VEC_ENGINE --> QDRANT_STORE
    QDRANT_STORE --> QDRANT_POOL
    QDRANT_POOL -->|pooled connections| QDRANT
    
    %% Network Connections
    KATO1 ---|Docker Network| NETWORK
    KATO2 ---|Docker Network| NETWORK
    KATO3 ---|Docker Network| NETWORK
    MONGO ---|Docker Network| NETWORK
    QDRANT ---|Docker Network| NETWORK
    REDIS ---|Docker Network| NETWORK
    
    %% Styling
    classDef newComponent fill:#c8e6c9,stroke:#2e7d32,stroke-width:3px
    classDef refactored fill:#fff3e0,stroke:#ef6c00,stroke-width:2px
    classDef api fill:#e1f5fe,stroke:#01579b,stroke-width:2px
    classDef storage fill:#f3e5f5,stroke:#4a148c,stroke-width:2px
    classDef session fill:#ffecb3,stroke:#ff6f00,stroke-width:3px
    
    class SESSION_MGR,SESSION_STATE,SESSION_MW,SESSION_STORE,MONGO_POOL,QDRANT_POOL,REDIS newComponent
    class MEM_MGR,PAT_PROC,VEC_PROC,OBS_PROC,PAT_OPS refactored
    class FASTAPI_V2,SESSION_EP,OBSERVE_EP,LEARN_EP,PRED_EP api
    class MONGO,QDRANT,SUPER_KB,QDRANT_STORE storage
    class FLOW1,FLOW2,FLOW3 session
```

## Detailed Component Changes

### 1. New Session Management Layer
**Purpose**: Enable multiple users to maintain completely isolated STM sequences

- **SessionManager**: Central coordinator for all user sessions
  - Creates unique session IDs
  - Manages session lifecycle (TTL, expiration)
  - Enforces resource limits per session
  
- **SessionState**: Isolated state container per user
  - Separate STM for each session
  - Isolated emotives accumulator
  - Session-specific time counter
  - Metadata and access tracking
  
- **SessionMiddleware**: Automatic session handling
  - Extracts session ID from requests
  - Loads/saves session state
  - Handles session creation and expiration
  
- **Redis Integration**: Persistent session storage
  - Fast in-memory session retrieval
  - TTL-based automatic cleanup
  - Distributed session support

### 2. New Resilience Layer
**Purpose**: Production-grade reliability and performance

- **MongoConnectionPool**:
  - Connection pooling (10-50 connections)
  - **CRITICAL**: Write concern changed from w=0 to w=majority
  - Automatic reconnection on failure
  - Health checks every 5 seconds
  - Retry logic for reads and writes
  
- **QdrantConnectionPool**:
  - Managed connection pool
  - Automatic failover
  - Request timeout handling

### 3. Refactored Core Processing
**Purpose**: Better modularity and separation of concerns

- **KatoProcessor**: Now acts as pure orchestrator
  - Delegates all operations to specialized modules
  - Manages session state injection/extraction
  - v2.0 methods: `set_stm()`, `get_emotives_accumulator()`
  
- **MemoryManager**: Enhanced for session support
  - Manages both global and session-specific state
  - `emotives_accumulator` for session isolation
  - Clean separation of STM/LTM operations
  
- **ObservationProcessor**: Modularized observation handling
  - Processes strings, vectors, emotives
  - Handles auto-learning triggers
  - Session-aware processing
  
- **PatternOperations**: CRUD operations for patterns
  - `get_pattern()`, `delete_pattern()`, `update_pattern()`
  - Centralized pattern manipulation

### 4. v2.0 API Endpoints

#### Session Management Endpoints (NEW)
- `POST /v2/sessions` - Create new session
- `GET /v2/sessions/{id}` - Get session info
- `DELETE /v2/sessions/{id}` - Delete session
- `GET /v2/sessions` - List active sessions

#### Session-Scoped Operations (NEW)
- `POST /v2/sessions/{id}/observe` - Observe in session context
- `POST /v2/sessions/{id}/learn` - Learn from session STM
- `GET /v2/sessions/{id}/stm` - Get session's STM
- `GET /v2/sessions/{id}/predictions` - Get session predictions
- `POST /v2/sessions/{id}/clear-stm` - Clear session STM

#### Backward Compatibility
- All `/v1/*` endpoints maintained for legacy support
- Default session creation for v1 endpoints

### 5. Data Isolation Architecture

```
User 1 → Session A → STM[['hello'], ['world']] → Predictions A
User 2 → Session B → STM[['foo'], ['bar']]    → Predictions B
User 3 → Session C → STM[['test'], ['data']]   → Predictions C

All sessions share:
- Same MongoDB (different processor_id namespaces)
- Same Qdrant collections
- Same KATO instance

But maintain complete isolation through:
- Session-specific STM
- Session-specific emotives
- Session-specific time counters
```

### 6. Configuration Changes

#### New Environment Variables
- `ENABLE_V2_FEATURES=true` - Enable v2.0 features
- `SESSION_TTL=3600` - Default session TTL in seconds
- `REDIS_URL=redis://localhost:6379` - Redis connection
- `MONGO_POOL_SIZE=50` - Connection pool size
- `HEALTH_CHECK_INTERVAL=5` - Health check frequency

#### Database Configuration
- MongoDB write concern: `w=majority, j=true` (was `w=0`)
- Connection pooling: 10-50 connections (was single)
- Retry logic: Enabled for reads and writes
- Compression: snappy, zlib enabled

### 7. Docker Infrastructure v2.0

#### New Services
- **Redis**: Session state storage
- Health checks on all services
- Restart policies: unless-stopped

#### Updated Images
- `Dockerfile.v2`: Includes v2.0 dependencies
- Additional packages: aioredis, connection pool libraries
- Health check endpoints: `/v2/health`

### 8. Testing Infrastructure v2.0

#### Session-Aware Testing
- Each test creates isolated session
- No cross-test contamination
- Parallel test execution with session isolation

#### New Test Categories
- `tests/v2/test_session_management.py`
- `tests/v2/test_multi_user_scenarios.py`
- `tests/v2/test_database_reliability.py`

## Migration Path from v1 to v2

1. **Database Migration**:
   - No schema changes required
   - Update write concern in existing deployments
   - Add connection pooling gradually

2. **API Migration**:
   - v1 endpoints remain functional
   - Gradually migrate to v2 session-based endpoints
   - Use session IDs for user isolation

3. **Infrastructure Migration**:
   - Add Redis for session storage
   - Update Docker images to v2
   - Configure connection pools

## Performance Improvements

1. **Connection Pooling**: 10-50x reduction in connection overhead
2. **Session Caching**: Sub-millisecond session retrieval from Redis
3. **Write Durability**: No data loss with w=majority
4. **Parallel Processing**: Multiple users truly concurrent
5. **Resource Limits**: Prevent memory exhaustion per session

## Security Enhancements

1. **Session Isolation**: Complete data isolation between users
2. **TTL Enforcement**: Automatic session expiration
3. **Resource Limits**: Per-session STM size limits
4. **Write Confirmation**: Guaranteed data persistence
5. **Health Monitoring**: Automatic failure detection

This v2.0 architecture provides production-ready multi-user support with complete session isolation, ensuring that KATO can serve multiple users simultaneously without any data collision or performance degradation.