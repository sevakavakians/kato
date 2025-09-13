# KATO v2.0 Session Management Specification

## Version Information
- **Version**: 2.0.0
- **Status**: Proposed  
- **Date**: 2025-01-11
- **Priority**: CRITICAL

## Executive Summary

This specification defines the multi-user session management system for KATO v2.0, addressing the critical requirement that multiple users must be able to maintain separate Short-Term Memory (STM) sequences without collision. The current v1.0 architecture has a single shared STM that causes data corruption when multiple users interact with the same KATO instance.

## Problem Statement

### Current v1.0 Limitations
1. **Single Shared STM**: All users share one STM in the processor
2. **Data Collision**: User observations intermingle unpredictably
3. **No User Isolation**: No concept of user sessions or contexts
4. **Corruption Risk**: One user's data corrupts another's sequences

### Example of Current Problem
```
User1: POST /observe {"strings": ["A"]} → STM: [["A"]]
User2: POST /observe {"strings": ["X"]} → STM: [["A"], ["X"]] ← COLLISION!
User1: POST /observe {"strings": ["B"]} → STM: [["A"], ["X"], ["B"]] ← CORRUPTED!
User1: GET /predictions → Predictions based on corrupted ["A", "X", "B"] sequence
```

## Solution Architecture

### Core Concept: Session-Isolated STM

Each user session maintains its own isolated STM, emotives accumulator, and processing context. Sessions are identified by unique session IDs and managed through a session store abstraction that supports both in-memory and distributed backends.

### Architectural Overview

```
┌─────────────────────────────────────────────────┐
│                   Client Requests                │
└─────────────────────┬───────────────────────────┘
                      │
              ┌───────▼───────┐
              │Session Manager│
              └───────┬───────┘
                      │
        ┌─────────────┼─────────────┐
        │             │             │
   ┌────▼────┐  ┌────▼────┐  ┌────▼────┐
   │Session 1│  │Session 2│  │Session N│
   │  STM: A  │  │  STM: X  │  │  STM: P  │
   │  Lock: ✓ │  │  Lock: ✓ │  │  Lock: ✓ │
   └─────────┘  └─────────┘  └─────────┘
        │             │             │
        └─────────────┼─────────────┘
                      │
              ┌───────▼───────┐
              │KATO Processor │
              │  (Stateless)  │
              └───────┬───────┘
                      │
        ┌─────────────┼─────────────┐
        │             │             │
   ┌────▼────┐  ┌────▼────┐  ┌────▼────┐
   │ MongoDB │  │ Qdrant  │  │  Redis  │
   └─────────┘  └─────────┘  └─────────┘
```

## Implementation Specifications

### 1. Session Data Model

```python
from dataclasses import dataclass
from datetime import datetime
from typing import List, Dict, Any, Optional
import asyncio

@dataclass
class SessionState:
    """Complete state for a user session"""
    session_id: str
    user_id: Optional[str]  # Optional user identifier
    created_at: datetime
    last_accessed: datetime
    expires_at: datetime
    
    # Core KATO state
    stm: List[List[str]]  # Short-term memory
    emotives_accumulator: List[Dict[str, float]]  # Accumulated emotives
    time: int  # Processor time counter for this session
    
    # Metadata
    metadata: Dict[str, Any]  # Custom session metadata
    access_count: int  # Number of requests in session
    
    # Concurrency control
    lock: asyncio.Lock  # Session-specific lock
    
    # Resource limits
    max_stm_size: int = 1000
    max_emotives_size: int = 1000
```

### 2. Session Manager Interface

```python
from abc import ABC, abstractmethod
from typing import Optional

class ISessionManager(ABC):
    """Abstract interface for session management"""
    
    @abstractmethod
    async def create_session(
        self, 
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        ttl_seconds: int = 3600
    ) -> SessionState:
        """Create a new session"""
        pass
    
    @abstractmethod
    async def get_session(self, session_id: str) -> Optional[SessionState]:
        """Retrieve existing session"""
        pass
    
    @abstractmethod
    async def update_session(self, session: SessionState) -> None:
        """Update session state"""
        pass
    
    @abstractmethod
    async def delete_session(self, session_id: str) -> None:
        """Delete session and cleanup resources"""
        pass
    
    @abstractmethod
    async def extend_session(self, session_id: str, ttl_seconds: int) -> None:
        """Extend session expiration"""
        pass
    
    @abstractmethod
    async def cleanup_expired_sessions(self) -> int:
        """Remove expired sessions, return count cleaned"""
        pass
    
    @abstractmethod
    async def get_active_session_count(self) -> int:
        """Get count of active sessions"""
        pass
```

### 3. Session Store Implementations

#### 3.1 In-Memory Store (Development/Testing)

```python
class InMemorySessionStore(ISessionManager):
    """In-memory session store for single-instance deployments"""
    
    def __init__(self):
        self.sessions: Dict[str, SessionState] = {}
        self.cleanup_task = None
    
    async def create_session(self, **kwargs) -> SessionState:
        session_id = generate_session_id()
        session = SessionState(
            session_id=session_id,
            created_at=datetime.now(),
            stm=[],
            emotives_accumulator=[],
            lock=asyncio.Lock(),
            **kwargs
        )
        self.sessions[session_id] = session
        return session
```

#### 3.2 Redis Store (Production)

```python
class RedisSessionStore(ISessionManager):
    """Redis-backed session store for distributed deployments"""
    
    def __init__(self, redis_url: str, pool_size: int = 30):
        self.redis = aioredis.from_url(
            redis_url,
            max_connections=pool_size,
            decode_responses=False  # Store binary for efficiency
        )
        self.local_locks: Dict[str, asyncio.Lock] = {}
    
    async def create_session(self, **kwargs) -> SessionState:
        session_id = generate_session_id()
        session_data = {
            'session_id': session_id,
            'created_at': datetime.now().isoformat(),
            'stm': [],
            'emotives_accumulator': [],
            **kwargs
        }
        
        # Store in Redis with TTL
        await self.redis.setex(
            f"session:{session_id}",
            kwargs.get('ttl_seconds', 3600),
            pickle.dumps(session_data)
        )
        
        # Create local lock for this session
        self.local_locks[session_id] = asyncio.Lock()
        
        return self._deserialize_session(session_data)
    
    async def get_session(self, session_id: str) -> Optional[SessionState]:
        data = await self.redis.get(f"session:{session_id}")
        if not data:
            return None
        
        session_data = pickle.loads(data)
        session = self._deserialize_session(session_data)
        
        # Ensure local lock exists
        if session_id not in self.local_locks:
            self.local_locks[session_id] = asyncio.Lock()
        session.lock = self.local_locks[session_id]
        
        return session
```

### 4. Session-Aware Request Processing

#### 4.1 Session Middleware

```python
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse

class SessionMiddleware:
    """FastAPI middleware for session management"""
    
    def __init__(self, app, session_manager: ISessionManager):
        self.app = app
        self.session_manager = session_manager
    
    async def __call__(self, request: Request, call_next):
        # Extract session ID from header or create new session
        session_id = request.headers.get('X-Session-ID')
        
        if not session_id and request.url.path.startswith('/v2/'):
            # Auto-create session for v2 endpoints without session
            session = await self.session_manager.create_session()
            session_id = session.session_id
            
        if session_id:
            # Validate session exists
            session = await self.session_manager.get_session(session_id)
            if not session:
                return JSONResponse(
                    status_code=404,
                    content={
                        "error": {
                            "code": "SESSION_NOT_FOUND",
                            "message": f"Session {session_id} not found or expired"
                        }
                    }
                )
            
            # Attach session to request state
            request.state.session = session
            request.state.session_id = session_id
        
        # Process request
        response = await call_next(request)
        
        # Add session ID to response headers
        if session_id:
            response.headers['X-Session-ID'] = session_id
        
        return response
```

#### 4.2 Session-Scoped Endpoints

```python
from fastapi import Depends

async def get_session(request: Request) -> SessionState:
    """Dependency to get session from request"""
    if not hasattr(request.state, 'session'):
        raise HTTPException(
            status_code=400,
            detail="Session required for this endpoint"
        )
    return request.state.session

@app.post("/v2/sessions")
async def create_session(
    data: CreateSessionRequest,
    session_manager: ISessionManager = Depends(get_session_manager)
):
    """Create a new session"""
    session = await session_manager.create_session(
        user_id=data.user_id,
        metadata=data.metadata,
        ttl_seconds=data.ttl_seconds or 3600
    )
    
    return {
        "session_id": session.session_id,
        "created_at": session.created_at,
        "expires_at": session.expires_at
    }

@app.post("/v2/sessions/{session_id}/observe")
async def observe_in_session(
    session_id: str,
    data: ObservationData,
    session_manager: ISessionManager = Depends(get_session_manager),
    processor: KatoProcessor = Depends(get_processor)
):
    """Process observation in specific session context"""
    
    # Get session
    session = await session_manager.get_session(session_id)
    if not session:
        raise HTTPException(404, detail="Session not found")
    
    # Lock session for processing
    async with session.lock:
        # Set processor state to session state
        processor.set_stm(session.stm)
        processor.set_emotives_accumulator(session.emotives_accumulator)
        processor.time = session.time
        
        # Process observation
        result = processor.observe({
            'strings': data.strings,
            'vectors': data.vectors,
            'emotives': data.emotives
        })
        
        # Update session state
        session.stm = processor.get_stm()
        session.emotives_accumulator = processor.get_emotives_accumulator()
        session.time = processor.time
        session.last_accessed = datetime.now()
        
        # Persist session state
        await session_manager.update_session(session)
    
    return {
        "status": "ok",
        "session_id": session_id,
        "time": session.time,
        "stm_length": len(session.stm)
    }
```

### 5. Session Lifecycle Management

#### 5.1 Session Creation Flow

```
1. Client: POST /v2/sessions
2. Server: Generate unique session_id (UUID v4)
3. Server: Initialize empty STM and state
4. Server: Store in session store with TTL
5. Server: Return session_id to client
6. Client: Use session_id in subsequent requests
```

#### 5.2 Session Usage Flow

```
1. Client: POST /v2/sessions/{id}/observe with data
2. Server: Retrieve session from store
3. Server: Acquire session-specific lock
4. Server: Load session STM into processor
5. Server: Process observation
6. Server: Update session STM from processor
7. Server: Persist updated session
8. Server: Release lock
9. Server: Return result
```

#### 5.3 Session Expiration

```python
class SessionCleanupService:
    """Background service for session cleanup"""
    
    def __init__(self, session_manager: ISessionManager):
        self.session_manager = session_manager
        self.cleanup_interval = 300  # 5 minutes
    
    async def start(self):
        """Start cleanup background task"""
        while True:
            try:
                expired_count = await self.session_manager.cleanup_expired_sessions()
                if expired_count > 0:
                    logger.info(f"Cleaned up {expired_count} expired sessions")
            except Exception as e:
                logger.error(f"Session cleanup error: {e}")
            
            await asyncio.sleep(self.cleanup_interval)
```

### 6. Backward Compatibility

#### 6.1 Default Session Mode

For v1.0 API compatibility, requests without session ID use a "default" session:

```python
@app.post("/observe")  # v1.0 endpoint
async def observe_v1(
    data: ObservationData,
    processor: KatoProcessor = Depends(get_processor),
    session_manager: ISessionManager = Depends(get_session_manager)
):
    """v1.0 compatible endpoint with automatic session"""
    
    # Use default session for backward compatibility
    DEFAULT_SESSION_ID = f"default-{processor.id}"
    
    session = await session_manager.get_session(DEFAULT_SESSION_ID)
    if not session:
        session = await session_manager.create_session(
            session_id=DEFAULT_SESSION_ID,
            ttl_seconds=86400  # 24 hours for default session
        )
    
    # Process with session context
    return await observe_in_session(
        session_id=DEFAULT_SESSION_ID,
        data=data,
        session_manager=session_manager,
        processor=processor
    )
```

#### 6.2 Header-Based Session Routing

Support session ID in headers for existing clients:

```python
@app.post("/observe")
async def observe_with_header(
    request: Request,
    data: ObservationData,
    processor: KatoProcessor = Depends(get_processor),
    session_manager: ISessionManager = Depends(get_session_manager)
):
    """Support X-Session-ID header for session routing"""
    
    session_id = request.headers.get('X-Session-ID')
    if session_id:
        return await observe_in_session(
            session_id=session_id,
            data=data,
            session_manager=session_manager,
            processor=processor
        )
    else:
        # Fall back to default session
        return await observe_v1(data, processor, session_manager)
```

### 7. Resource Management

#### 7.1 Session Limits

```python
class SessionLimits:
    """Resource limits per session"""
    MAX_STM_SIZE = 1000  # Maximum events in STM
    MAX_EMOTIVES_SIZE = 1000  # Maximum emotives entries
    MAX_SESSION_AGE = 86400  # 24 hours maximum
    MAX_IDLE_TIME = 3600  # 1 hour idle timeout
    MAX_SESSIONS_PER_USER = 10  # Per user_id if provided
    MAX_TOTAL_SESSIONS = 10000  # Global limit
```

#### 7.2 Resource Enforcement

```python
async def enforce_session_limits(session: SessionState):
    """Enforce resource limits on session"""
    
    # Trim STM if too large
    if len(session.stm) > SessionLimits.MAX_STM_SIZE:
        session.stm = session.stm[-SessionLimits.MAX_STM_SIZE:]
    
    # Trim emotives if too large
    if len(session.emotives_accumulator) > SessionLimits.MAX_EMOTIVES_SIZE:
        session.emotives_accumulator = session.emotives_accumulator[-SessionLimits.MAX_EMOTIVES_SIZE:]
    
    # Check idle timeout
    idle_time = datetime.now() - session.last_accessed
    if idle_time.seconds > SessionLimits.MAX_IDLE_TIME:
        raise SessionExpiredError(f"Session {session.session_id} idle timeout")
```

### 8. Security Considerations

#### 8.1 Session ID Generation

```python
import secrets
import uuid

def generate_session_id() -> str:
    """Generate cryptographically secure session ID"""
    # UUID v4 + random token for extra entropy
    return f"{uuid.uuid4().hex}-{secrets.token_hex(8)}"
```

#### 8.2 Session Validation

```python
def validate_session_id(session_id: str) -> bool:
    """Validate session ID format"""
    import re
    pattern = r'^[a-f0-9]{32}-[a-f0-9]{16}$'
    return bool(re.match(pattern, session_id))
```

#### 8.3 Rate Limiting Per Session

```python
from collections import defaultdict
import time

class SessionRateLimiter:
    """Rate limiting per session"""
    
    def __init__(self, requests_per_minute: int = 60):
        self.requests_per_minute = requests_per_minute
        self.session_requests = defaultdict(list)
    
    async def check_rate_limit(self, session_id: str) -> bool:
        """Check if session exceeded rate limit"""
        now = time.time()
        minute_ago = now - 60
        
        # Clean old requests
        self.session_requests[session_id] = [
            t for t in self.session_requests[session_id]
            if t > minute_ago
        ]
        
        # Check limit
        if len(self.session_requests[session_id]) >= self.requests_per_minute:
            return False
        
        # Record request
        self.session_requests[session_id].append(now)
        return True
```

## Testing Strategy

### Unit Tests

```python
@pytest.mark.asyncio
async def test_session_isolation():
    """Test that sessions maintain isolated STM"""
    manager = InMemorySessionStore()
    processor = create_test_processor()
    
    # Create two sessions
    session1 = await manager.create_session()
    session2 = await manager.create_session()
    
    # Process in session 1
    async with session1.lock:
        processor.set_stm([])
        processor.observe({'strings': ['A']})
        session1.stm = processor.get_stm()
    
    # Process in session 2
    async with session2.lock:
        processor.set_stm([])
        processor.observe({'strings': ['X']})
        session2.stm = processor.get_stm()
    
    # Verify isolation
    assert session1.stm == [['A']]
    assert session2.stm == [['X']]
```

### Integration Tests

```python
@pytest.mark.asyncio
async def test_concurrent_sessions():
    """Test concurrent session processing"""
    client = TestClient(app)
    
    # Create multiple sessions
    sessions = []
    for i in range(10):
        response = await client.post("/v2/sessions")
        sessions.append(response.json()['session_id'])
    
    # Process concurrently
    async def process_session(session_id, symbol):
        for j in range(10):
            await client.post(
                f"/v2/sessions/{session_id}/observe",
                json={"strings": [f"{symbol}{j}"]}
            )
        return await client.get(f"/v2/sessions/{session_id}/stm")
    
    # Run all sessions in parallel
    results = await asyncio.gather(*[
        process_session(sid, chr(65+i))
        for i, sid in enumerate(sessions)
    ])
    
    # Verify each session has its own sequence
    for i, result in enumerate(results):
        stm = result.json()['stm']
        expected = [[f"{chr(65+i)}{j}"] for j in range(10)]
        assert stm == expected
```

### Load Tests

```python
async def load_test_sessions():
    """Load test with many concurrent sessions"""
    
    # Create 1000 sessions
    sessions = await create_sessions(1000)
    
    # Process 100 requests per session concurrently
    async def session_workload(session_id):
        for _ in range(100):
            await observe_in_session(session_id, random_data())
    
    # Run all concurrently
    start = time.time()
    await asyncio.gather(*[
        session_workload(s) for s in sessions
    ])
    duration = time.time() - start
    
    # Assert performance targets
    assert duration < 60  # Complete in under 1 minute
    assert all_sessions_isolated(sessions)
```

## Performance Implications

### Memory Usage

| Component | Per Session | 1,000 Sessions | 10,000 Sessions |
|-----------|------------|----------------|-----------------|
| STM (1000 events) | 1 MB | 1 GB | 10 GB |
| Emotives | 100 KB | 100 MB | 1 GB |
| Metadata | 10 KB | 10 MB | 100 MB |
| Lock overhead | 1 KB | 1 MB | 10 MB |
| **Total** | ~1.1 MB | ~1.1 GB | ~11 GB |

### Latency Impact

| Operation | v1.0 (Shared) | v2.0 (Session) | Overhead |
|-----------|--------------|----------------|----------|
| Observe | 5ms | 7ms | +2ms (session lookup) |
| Learn | 20ms | 22ms | +2ms |
| Get STM | 1ms | 2ms | +1ms |
| Predictions | 10ms | 12ms | +2ms |

### Scalability

| Metric | In-Memory Store | Redis Store |
|--------|----------------|-------------|
| Max Sessions | 10,000 | 1,000,000+ |
| Lookup Time | O(1) | O(1) + network |
| Persistence | No | Yes |
| Multi-instance | No | Yes |
| Failover | No | Yes |

## Migration Plan

### Phase 1: Add Session Infrastructure (Week 1)
1. Implement session models and interfaces
2. Create in-memory session store
3. Add session middleware
4. Create v2 session endpoints

### Phase 2: Redis Integration (Week 2)
1. Implement Redis session store
2. Add connection pooling
3. Implement session serialization
4. Add cleanup service

### Phase 3: Update Endpoints (Week 3)
1. Update all endpoints for session support
2. Add backward compatibility layer
3. Implement header-based routing
4. Add session limits enforcement

### Phase 4: Testing & Deployment (Week 4)
1. Comprehensive testing
2. Load testing
3. Documentation
4. Gradual rollout

## Success Criteria

1. ✅ Multiple users can maintain completely isolated STM sequences
2. ✅ No data collision between concurrent sessions
3. ✅ Session state persists across requests
4. ✅ Sessions expire and cleanup automatically
5. ✅ Backward compatibility with v1.0 API
6. ✅ Support for 10,000+ concurrent sessions
7. ✅ Session operations add <5ms latency
8. ✅ Redis failover maintains session continuity
9. ✅ Resource limits prevent memory exhaustion
10. ✅ Security: cryptographically secure session IDs

## References

- [FastAPI Sessions](https://fastapi.tiangolo.com/advanced/middleware/)
- [Redis Session Management](https://redis.io/docs/manual/patterns/distributed-locks/)
- [Session Security Best Practices](https://owasp.org/www-project-web-security-testing-guide/latest/4-Web_Application_Security_Testing/06-Session_Management_Testing/README)