# KATO v2.0 Architecture Specification

## Version Information
- **Version**: 2.0.0
- **Status**: Proposed
- **Date**: 2025-01-11
- **Supersedes**: v1.0 (FastAPI Architecture Spec)

## Executive Summary

KATO v2.0 represents a complete architectural overhaul addressing critical production requirements discovered during v1.0 deployment analysis. The primary focus is on multi-user session management, database reliability, proper concurrency control, and production-grade error handling. This specification defines a scalable, fault-tolerant architecture suitable for enterprise deployment.

## Core Architectural Principles

### 1. Multi-Tenancy First
- Every user/session has completely isolated state
- No shared mutable state between sessions
- Session-scoped resource management

### 2. Reliability by Design
- Connection pooling for all external services
- Circuit breakers prevent cascading failures
- Automatic retry with exponential backoff
- Graceful degradation under load

### 3. Observable and Debuggable
- Structured logging with trace IDs
- Prometheus metrics for all operations
- Health checks for all dependencies
- Distributed tracing support

### 4. Horizontally Scalable
- Stateless service design
- Redis-backed session state
- Database sharding support
- Load balancer ready

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Load Balancer                         │
│                  (Nginx/HAProxy/ALB)                    │
└────────────────────┬────────────────────────────────────┘
                     │
     ┌───────────────┼───────────────┬──────────────┐
     │               │               │              │
┌────▼────┐    ┌────▼────┐    ┌────▼────┐    ┌────▼────┐
│ KATO-1  │    │ KATO-2  │    │ KATO-3  │    │ KATO-N  │
│FastAPI  │    │FastAPI  │    │FastAPI  │    │FastAPI  │
│Instance │    │Instance │    │Instance │    │Instance │
└────┬────┘    └────┬────┘    └────┬────┘    └────┬────┘
     │               │               │              │
     └───────────────┼───────────────┼──────────────┘
                     │               │
            ┌────────▼───────┐ ┌────▼────┐
            │     Redis      │ │ MongoDB │
            │Session Store   │ │  Pool   │
            └────────────────┘ └────┬────┘
                                    │
                              ┌─────▼─────┐
                              │  Qdrant   │
                              │   Pool    │
                              └───────────┘
```

## Component Specifications

### 1. FastAPI Service Layer

**Location**: `kato/services/kato_fastapi_v2.py`

**Key Changes from v1.0**:
- Session-aware request handling
- Fine-grained locking per session
- Connection pooling for all databases
- Circuit breaker integration
- Structured error responses

**Core Responsibilities**:
- HTTP request handling
- Session management
- Request validation
- Response serialization
- WebSocket support
- Metrics collection

### 2. Session Management Layer

**Location**: `kato/sessions/`

**Components**:
```python
kato/sessions/
├── session_manager.py      # Core session orchestration
├── session_store.py        # Abstract session storage interface
├── redis_store.py          # Redis-backed session storage
├── memory_store.py         # In-memory session storage (dev/test)
├── session_models.py       # Session data models
└── session_middleware.py   # FastAPI middleware for sessions
```

**Session Data Structure**:
```python
class Session:
    session_id: str
    user_id: Optional[str]
    created_at: datetime
    last_accessed: datetime
    expires_at: datetime
    stm: List[List[str]]  # Short-term memory
    emotives_accumulator: List[Dict[str, float]]
    metadata: Dict[str, Any]
    lock: asyncio.Lock  # Session-specific lock
```

**Session Lifecycle**:
1. **Creation**: Generate unique session ID, initialize empty STM
2. **Usage**: Route requests to session-specific processor state
3. **Expiration**: TTL-based expiration with configurable timeout
4. **Cleanup**: Automatic cleanup of expired sessions

### 3. Database Reliability Layer

**Location**: `kato/resilience/`

**Components**:
```python
kato/resilience/
├── connection_pool.py      # Database connection pooling
├── circuit_breaker.py      # Circuit breaker pattern
├── retry_policy.py         # Exponential backoff retry
├── health_checker.py       # Service health monitoring
└── resilience_config.py    # Configuration settings
```

**MongoDB Connection Pool**:
```python
class MongoPoolManager:
    def __init__(self, url: str, pool_size: int = 50):
        self.client = MongoClient(
            url,
            maxPoolSize=pool_size,
            minPoolSize=10,
            maxIdleTimeMS=30000,
            waitQueueTimeoutMS=5000,
            retryWrites=True,
            retryReads=True,
            w='majority',  # Write concern: majority
            readPreference='primaryPreferred',
            serverSelectionTimeoutMS=5000
        )
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=5,
            recovery_timeout=30,
            expected_exception=PyMongoError
        )
```

**Qdrant Connection Pool**:
```python
class QdrantPoolManager:
    def __init__(self, host: str, port: int, pool_size: int = 20):
        self.pool = AsyncQdrantClientPool(
            host=host,
            port=port,
            pool_size=pool_size,
            timeout=10,
            grpc_options={
                'grpc.keepalive_time_ms': 10000,
                'grpc.keepalive_timeout_ms': 5000,
            }
        )
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=3,
            recovery_timeout=20
        )
```

### 4. Concurrency Control

**Fine-Grained Locking Strategy**:
```python
class LockManager:
    def __init__(self):
        self.session_locks: Dict[str, asyncio.Lock] = {}
        self.operation_locks = {
            'learn': asyncio.Lock(),
            'vector_index': asyncio.Lock(),
            'pattern_search': asyncio.Semaphore(10),  # Allow 10 concurrent searches
        }
        self.lock_cleanup_task = None
    
    async def get_session_lock(self, session_id: str) -> asyncio.Lock:
        if session_id not in self.session_locks:
            self.session_locks[session_id] = asyncio.Lock()
        return self.session_locks[session_id]
    
    async def cleanup_expired_locks(self):
        # Periodic cleanup of unused locks
        pass
```

### 5. Error Handling Architecture

**Error Response Format**:
```json
{
    "error": {
        "code": "KATO_ERROR_CODE",
        "message": "Human-readable error message",
        "details": {
            "field": "value",
            "trace_id": "uuid-v4"
        },
        "timestamp": "2025-01-11T10:00:00Z"
    },
    "status": 400
}
```

**Error Categories**:
- **400-499**: Client errors (validation, not found, unauthorized)
- **500-599**: Server errors (internal, database, service unavailable)

**Circuit Breaker States**:
1. **CLOSED**: Normal operation, requests pass through
2. **OPEN**: Failure threshold exceeded, requests fail fast
3. **HALF_OPEN**: Testing if service recovered

### 6. Monitoring & Observability

**Metrics Collection**:
```python
# Prometheus metrics
kato_requests_total = Counter('kato_requests_total', 'Total requests', ['method', 'endpoint', 'status'])
kato_request_duration_seconds = Histogram('kato_request_duration_seconds', 'Request duration', ['method', 'endpoint'])
kato_active_sessions = Gauge('kato_active_sessions', 'Number of active sessions')
kato_stm_size = Histogram('kato_stm_size', 'STM size distribution', ['session_id'])
kato_database_connections = Gauge('kato_database_connections', 'Database connection pool size', ['database'])
kato_circuit_breaker_state = Gauge('kato_circuit_breaker_state', 'Circuit breaker state', ['service'])
```

**Health Check Endpoints**:
- `/health/live` - Liveness probe (is service running?)
- `/health/ready` - Readiness probe (can service handle requests?)
- `/health/startup` - Startup probe (is service initialized?)

### 7. Configuration Management

**Environment-Based Configuration**:
```yaml
# config/production.yaml
database:
  mongodb:
    url: ${MONGO_URL}
    pool_size: 50
    write_concern: majority
  qdrant:
    host: ${QDRANT_HOST}
    port: 6333
    pool_size: 20
  redis:
    url: ${REDIS_URL}
    pool_size: 30
    
session:
  store_type: redis  # redis | memory
  ttl_seconds: 3600
  max_stm_size: 1000
  cleanup_interval: 300

resilience:
  circuit_breaker:
    failure_threshold: 5
    recovery_timeout: 30
  retry:
    max_attempts: 3
    backoff_factor: 2
    max_delay: 10

monitoring:
  metrics_enabled: true
  tracing_enabled: true
  log_level: INFO
```

## API Specification

### Session Management Endpoints

| Method | Endpoint | Description | Request | Response |
|--------|----------|-------------|---------|----------|
| POST | `/v2/sessions` | Create session | `CreateSessionRequest` | `SessionResponse` |
| GET | `/v2/sessions/{id}` | Get session info | - | `SessionResponse` |
| DELETE | `/v2/sessions/{id}` | Delete session | - | `StatusResponse` |
| POST | `/v2/sessions/{id}/observe` | Observe in session | `ObservationData` | `ObservationResult` |
| GET | `/v2/sessions/{id}/stm` | Get session STM | - | `STMResponse` |
| POST | `/v2/sessions/{id}/learn` | Learn from session | - | `LearnResult` |
| POST | `/v2/sessions/{id}/clear-stm` | Clear session STM | - | `StatusResponse` |
| GET | `/v2/sessions/{id}/predictions` | Get predictions | - | `PredictionsResponse` |

### Backward Compatibility

All v1.0 endpoints remain available with automatic session creation:
- Requests without session use a "default" session
- `X-Session-ID` header for explicit session routing
- JWT tokens with embedded session claims

## Performance Targets

| Metric | Current (v1.0) | Target (v2.0) | Improvement |
|--------|---------------|---------------|-------------|
| Request latency (p50) | 10ms | 2ms | 5x |
| Request latency (p99) | 100ms | 20ms | 5x |
| Concurrent sessions | 1 | 10,000+ | 10,000x |
| Requests per second | 100 | 5,000 | 50x |
| Database connection failures | Crash | Graceful retry | ∞ |
| Memory per session | Unbounded | 10MB max | Bounded |
| Session isolation | None | Complete | ∞ |

## Security Considerations

### Authentication & Authorization
- JWT-based authentication
- API key support for service accounts
- Role-based access control (RBAC)
- Session-scoped permissions

### Rate Limiting
- Per-session rate limits
- Global rate limits
- Adaptive rate limiting based on load

### Input Validation
- Pydantic models for all inputs
- Size limits on vectors and strings
- SQL injection prevention
- XSS protection

### Data Protection
- TLS for all communications
- Encryption at rest for sensitive data
- Session data encryption in Redis
- Audit logging for all operations

## Migration Strategy

### Phase 1: Foundation (Week 1-2)
1. Implement session management layer
2. Add Redis integration
3. Create session middleware
4. Update API endpoints

### Phase 2: Reliability (Week 3-4)
1. Implement connection pooling
2. Add circuit breakers
3. Implement retry logic
4. Add health checks

### Phase 3: Observability (Week 5)
1. Add Prometheus metrics
2. Implement structured logging
3. Add distributed tracing
4. Create Grafana dashboards

### Phase 4: Production (Week 6)
1. Security hardening
2. Performance optimization
3. Load testing
4. Documentation

## Testing Strategy

### Unit Tests
- Session management logic
- Circuit breaker behavior
- Connection pool management
- Error handling

### Integration Tests
- Multi-session scenarios
- Database failure recovery
- Circuit breaker integration
- End-to-end workflows

### Load Tests
- 10,000 concurrent sessions
- 5,000 requests per second
- Database connection exhaustion
- Memory pressure scenarios

### Chaos Tests
- Random database failures
- Network partitions
- Service crashes
- Resource exhaustion

## Success Criteria

1. ✅ Multiple users maintain separate STM sequences
2. ✅ No data collision between sessions
3. ✅ Database failures don't crash service
4. ✅ Automatic recovery from transient failures
5. ✅ Comprehensive monitoring in place
6. ✅ Horizontal scaling demonstrated
7. ✅ Performance targets achieved
8. ✅ Security requirements met
9. ✅ Zero-downtime deployments
10. ✅ Backward compatibility maintained

## Appendices

### A. Error Codes
- `KATO_SESSION_NOT_FOUND`: Session does not exist
- `KATO_SESSION_EXPIRED`: Session has expired
- `KATO_DATABASE_ERROR`: Database operation failed
- `KATO_CIRCUIT_OPEN`: Circuit breaker is open
- `KATO_VALIDATION_ERROR`: Input validation failed

### B. Metrics Reference
- See `docs/specifications/v2.0/METRICS_REFERENCE.md`

### C. API Examples
- See `docs/specifications/v2.0/API_EXAMPLES.md`

## References

- [Circuit Breaker Pattern](https://martinfowler.com/bliki/CircuitBreaker.html)
- [Database Connection Pooling Best Practices](https://www.mongodb.com/docs/manual/administration/connection-pool-overview/)
- [Redis Session Management](https://redis.io/docs/manual/patterns/distributed-locks/)
- [Prometheus Best Practices](https://prometheus.io/docs/practices/naming/)