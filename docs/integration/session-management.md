# KATO Session Management in Integrated Systems

## Table of Contents
1. [Overview](#overview)
2. [Session Lifecycle](#session-lifecycle)
3. [State Sharing Strategies](#state-sharing-strategies)
4. [TTL Management](#ttl-management)
5. [Session Persistence](#session-persistence)
6. [Multi-User Sessions](#multi-user-sessions)
7. [Session Migration](#session-migration)
8. [Best Practices](#best-practices)

## Overview

KATO's session-based architecture provides complete isolation for short-term memory and configuration. This guide covers session lifecycle management, state sharing strategies, and best practices for integrated systems.

### Session Fundamentals

- **Session ID**: Unique identifier for isolated memory space
- **Node ID**: Logical identifier for pattern storage (can be shared)
- **TTL**: Time-to-live for automatic cleanup
- **Auto-Extend**: Sliding window session expiration
- **State**: STM, configuration, and session metadata

## Session Lifecycle

### Creating Sessions

```python
import httpx
from typing import Optional

class SessionManager:
    """Manage KATO session lifecycle"""

    def __init__(self, kato_url: str):
        self.kato = httpx.Client(base_url=kato_url, timeout=30.0)

    def create_session(
        self,
        node_id: str,
        config: Optional[dict] = None,
        ttl: Optional[int] = None
    ) -> str:
        """Create new KATO session"""
        payload = {"node_id": node_id}

        if config:
            payload["config"] = config

        if ttl:
            payload["ttl"] = ttl

        response = self.kato.post("/sessions", json=payload)
        response.raise_for_status()

        session_data = response.json()
        return session_data["session_id"]

    def get_session(self, session_id: str) -> dict:
        """Get session information"""
        response = self.kato.get(f"/sessions/{session_id}")
        response.raise_for_status()
        return response.json()

    def delete_session(self, session_id: str):
        """Delete session and clear memory"""
        response = self.kato.delete(f"/sessions/{session_id}")
        response.raise_for_status()

# Usage
manager = SessionManager("http://localhost:8000")
session_id = manager.create_session(
    node_id="user-123",
    config={"recall_threshold": 0.3},
    ttl=7200  # 2 hours
)
```

### Session States

```python
from enum import Enum
from datetime import datetime, timedelta

class SessionState(Enum):
    """Session lifecycle states"""
    ACTIVE = "active"
    IDLE = "idle"
    EXPIRING = "expiring"
    EXPIRED = "expired"

class SessionTracker:
    """Track session states in your application"""

    def __init__(self):
        self.sessions = {}

    def track_session(self, session_id: str, ttl: int):
        """Start tracking session"""
        self.sessions[session_id] = {
            "state": SessionState.ACTIVE,
            "created_at": datetime.utcnow(),
            "last_activity": datetime.utcnow(),
            "ttl": ttl
        }

    def update_activity(self, session_id: str):
        """Update last activity timestamp"""
        if session_id in self.sessions:
            self.sessions[session_id]["last_activity"] = datetime.utcnow()
            self.sessions[session_id]["state"] = SessionState.ACTIVE

    def get_session_state(self, session_id: str) -> SessionState:
        """Get current session state"""
        if session_id not in self.sessions:
            return SessionState.EXPIRED

        session = self.sessions[session_id]
        idle_time = (datetime.utcnow() - session["last_activity"]).seconds

        if idle_time > session["ttl"]:
            return SessionState.EXPIRED
        elif idle_time > session["ttl"] * 0.8:
            return SessionState.EXPIRING
        elif idle_time > 300:  # 5 minutes
            return SessionState.IDLE
        else:
            return SessionState.ACTIVE
```

## State Sharing Strategies

### Strategy 1: Session Per User (Isolated)

Each user gets independent session with isolated memory.

```python
class UserSessionManager:
    """One session per user - complete isolation"""

    def __init__(self, kato_url: str):
        self.kato = httpx.Client(base_url=kato_url)
        self.user_sessions = {}  # user_id -> session_id

    def get_or_create_session(self, user_id: str) -> str:
        """Get existing session or create new one"""
        if user_id in self.user_sessions:
            # Verify session still exists
            try:
                response = self.kato.get(
                    f"/sessions/{self.user_sessions[user_id]}"
                )
                if response.status_code == 200:
                    return self.user_sessions[user_id]
            except:
                pass

        # Create new session
        response = self.kato.post(
            "/sessions",
            json={"node_id": user_id}
        )
        session_id = response.json()["session_id"]
        self.user_sessions[user_id] = session_id
        return session_id

    def observe(self, user_id: str, observation: dict):
        """Send observation for user"""
        session_id = self.get_or_create_session(user_id)
        self.kato.post(
            f"/sessions/{session_id}/observe",
            json=observation
        )
```

### Strategy 2: Session Per Conversation (Contextual)

Separate sessions for different contexts (e.g., different chat conversations).

```python
class ConversationSessionManager:
    """One session per conversation"""

    def __init__(self, kato_url: str):
        self.kato = httpx.Client(base_url=kato_url)
        self.conversation_sessions = {}  # conversation_id -> session_id

    def get_session(self, user_id: str, conversation_id: str) -> str:
        """Get session for specific conversation"""
        key = f"{user_id}:{conversation_id}"

        if key not in self.conversation_sessions:
            # Create session with conversation-specific node_id
            response = self.kato.post(
                "/sessions",
                json={
                    "node_id": f"user-{user_id}-conv-{conversation_id}",
                    "config": {"session_ttl": 3600}
                }
            )
            self.conversation_sessions[key] = response.json()["session_id"]

        return self.conversation_sessions[key]
```

### Strategy 3: Shared Node, Multiple Sessions (Collaborative)

Multiple sessions share same node_id for collaborative pattern learning.

```python
class CollaborativeSessionManager:
    """Multiple users share patterns via same node_id"""

    def __init__(self, kato_url: str):
        self.kato = httpx.Client(base_url=kato_url)

    def create_user_session(self, user_id: str, team_id: str) -> str:
        """Create session that shares team patterns"""
        response = self.kato.post(
            "/sessions",
            json={
                "node_id": f"team-{team_id}",  # Shared node_id
                "config": {
                    "recall_threshold": 0.2,
                    "max_predictions": 50
                }
            }
        )
        return response.json()["session_id"]

    def observe_team_activity(
        self,
        session_id: str,
        user_id: str,
        activity: dict
    ):
        """Observe activity that contributes to team patterns"""
        self.kato.post(
            f"/sessions/{session_id}/observe",
            json={
                "strings": [f"user:{user_id}", activity["action"]],
                "vectors": [],
                "emotives": {},
                "metadata": {"team_activity": True}
            }
        )
```

## TTL Management

### Auto-Extension Configuration

```python
class TTLManager:
    """Manage session TTL and auto-extension"""

    def __init__(self, kato_url: str):
        self.kato = httpx.Client(base_url=kato_url)

    def create_session_with_ttl(
        self,
        node_id: str,
        ttl_seconds: int,
        auto_extend: bool = True
    ) -> str:
        """Create session with specific TTL"""
        response = self.kato.post(
            "/sessions",
            json={
                "node_id": node_id,
                "config": {
                    "session_ttl": ttl_seconds,
                    "session_auto_extend": auto_extend
                }
            }
        )
        return response.json()["session_id"]

    def refresh_session(self, session_id: str):
        """Manually refresh session TTL"""
        # Any API call to session will auto-extend if enabled
        self.kato.get(f"/sessions/{session_id}")

# Usage examples
manager = TTLManager("http://localhost:8000")

# Short-lived session (5 minutes)
quick_session = manager.create_session_with_ttl("temp-user", 300, auto_extend=False)

# Long-lived session with auto-extend (1 hour base, extends on activity)
long_session = manager.create_session_with_ttl("active-user", 3600, auto_extend=True)
```

### Proactive TTL Renewal

```python
import asyncio
from datetime import datetime, timedelta

class SessionKeepAlive:
    """Keep sessions alive with periodic refresh"""

    def __init__(self, kato_url: str, refresh_interval: int = 300):
        self.kato = httpx.AsyncClient(base_url=kato_url)
        self.refresh_interval = refresh_interval
        self.active_sessions = set()
        self.running = False

    async def register_session(self, session_id: str):
        """Register session for keep-alive"""
        self.active_sessions.add(session_id)

    async def unregister_session(self, session_id: str):
        """Stop keeping session alive"""
        self.active_sessions.discard(session_id)

    async def refresh_loop(self):
        """Background task to refresh sessions"""
        self.running = True
        while self.running:
            await asyncio.sleep(self.refresh_interval)

            for session_id in list(self.active_sessions):
                try:
                    await self.kato.get(f"/sessions/{session_id}")
                except Exception as e:
                    print(f"Failed to refresh session {session_id}: {e}")
                    self.active_sessions.discard(session_id)

    async def start(self):
        """Start keep-alive background task"""
        asyncio.create_task(self.refresh_loop())

    def stop(self):
        """Stop keep-alive"""
        self.running = False
```

## Session Persistence

### Exporting Session State

```python
class SessionExporter:
    """Export and restore session state"""

    def __init__(self, kato_url: str):
        self.kato = httpx.Client(base_url=kato_url)

    def export_session(self, session_id: str) -> dict:
        """Export complete session state"""
        # Get session info
        session_info = self.kato.get(f"/sessions/{session_id}").json()

        # Get STM state
        stm_state = self.kato.get(f"/sessions/{session_id}/stm").json()

        # Get patterns (if needed)
        patterns = self.kato.get(
            f"/sessions/{session_id}/patterns"
        ).json()

        return {
            "session_id": session_id,
            "node_id": session_info["node_id"],
            "config": session_info["config"],
            "stm": stm_state,
            "patterns": patterns,
            "exported_at": datetime.utcnow().isoformat()
        }

    def import_session(self, state: dict) -> str:
        """Restore session from exported state"""
        # Create new session
        response = self.kato.post(
            "/sessions",
            json={
                "node_id": state["node_id"],
                "config": state["config"]
            }
        )
        new_session_id = response.json()["session_id"]

        # Restore STM by replaying observations
        for event in state["stm"]["events"]:
            self.kato.post(
                f"/sessions/{new_session_id}/observe",
                json=event
            )

        return new_session_id
```

### Database-Backed Session Store

```python
from sqlalchemy import create_engine, Column, String, JSON, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

Base = declarative_base()

class SessionSnapshot(Base):
    """Store session snapshots in database"""
    __tablename__ = "kato_sessions"

    session_id = Column(String, primary_key=True)
    node_id = Column(String, nullable=False)
    state = Column(JSON, nullable=False)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)

class PersistentSessionManager:
    """Manage sessions with database persistence"""

    def __init__(self, kato_url: str, db_url: str):
        self.kato = httpx.Client(base_url=kato_url)
        self.engine = create_engine(db_url)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def save_snapshot(self, session_id: str):
        """Save session snapshot to database"""
        # Export session state
        exporter = SessionExporter(str(self.kato.base_url))
        state = exporter.export_session(session_id)

        # Save to database
        db_session = self.Session()
        snapshot = SessionSnapshot(
            session_id=session_id,
            node_id=state["node_id"],
            state=state,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db_session.merge(snapshot)
        db_session.commit()
        db_session.close()

    def restore_session(self, session_id: str) -> str:
        """Restore session from database snapshot"""
        db_session = self.Session()
        snapshot = db_session.query(SessionSnapshot).filter_by(
            session_id=session_id
        ).first()
        db_session.close()

        if not snapshot:
            raise ValueError(f"No snapshot found for {session_id}")

        # Restore session
        exporter = SessionExporter(str(self.kato.base_url))
        return exporter.import_session(snapshot.state)
```

## Multi-User Sessions

### Session Pool Management

```python
from queue import Queue
import threading

class SessionPool:
    """Pool of reusable sessions for high-traffic applications"""

    def __init__(self, kato_url: str, pool_size: int, node_id: str):
        self.kato = httpx.Client(base_url=kato_url)
        self.pool = Queue(maxsize=pool_size)
        self.node_id = node_id
        self.lock = threading.Lock()

        # Pre-create sessions
        for _ in range(pool_size):
            session_id = self._create_session()
            self.pool.put(session_id)

    def _create_session(self) -> str:
        """Create new session"""
        response = self.kato.post(
            "/sessions",
            json={"node_id": self.node_id}
        )
        return response.json()["session_id"]

    def acquire(self, timeout: float = 5.0) -> str:
        """Acquire session from pool"""
        try:
            return self.pool.get(timeout=timeout)
        except:
            # Pool exhausted - create new session
            return self._create_session()

    def release(self, session_id: str):
        """Return session to pool"""
        try:
            # Clear STM before returning to pool
            self.kato.post(f"/sessions/{session_id}/clear_stm")
            self.pool.put(session_id, block=False)
        except:
            # Pool full - let session expire
            pass

# Usage with context manager
from contextlib import contextmanager

@contextmanager
def pooled_session(pool: SessionPool):
    """Context manager for pooled sessions"""
    session_id = pool.acquire()
    try:
        yield session_id
    finally:
        pool.release(session_id)

# Example
pool = SessionPool("http://localhost:8000", pool_size=10, node_id="app")

with pooled_session(pool) as session_id:
    # Use session
    pass
```

## Session Migration

### Migrating Sessions Between Instances

```python
class SessionMigrator:
    """Migrate sessions between KATO instances"""

    def __init__(self, source_url: str, target_url: str):
        self.source = httpx.Client(base_url=source_url)
        self.target = httpx.Client(base_url=target_url)

    def migrate_session(self, session_id: str) -> str:
        """Migrate session to new instance"""
        # Export from source
        exporter = SessionExporter(str(self.source.base_url))
        state = exporter.export_session(session_id)

        # Import to target
        target_exporter = SessionExporter(str(self.target.base_url))
        new_session_id = target_exporter.import_session(state)

        # Delete from source (optional)
        # self.source.delete(f"/sessions/{session_id}")

        return new_session_id

    def migrate_all_sessions(self) -> dict:
        """Migrate all sessions"""
        # Get all sessions from source
        sessions = self.source.get("/sessions").json()

        results = {}
        for session in sessions:
            session_id = session["session_id"]
            try:
                new_id = self.migrate_session(session_id)
                results[session_id] = {"status": "success", "new_id": new_id}
            except Exception as e:
                results[session_id] = {"status": "failed", "error": str(e)}

        return results
```

## Best Practices

### 1. Session Naming Convention

```python
def generate_session_id(user_id: str, context: str, timestamp: str) -> str:
    """Generate descriptive session identifier"""
    return f"{user_id}:{context}:{timestamp}"

# Examples
session_id = generate_session_id("user123", "checkout", "20251113-103000")
# Result: "user123:checkout:20251113-103000"
```

### 2. Graceful Session Cleanup

```python
import atexit

class SessionCleanup:
    """Ensure sessions are cleaned up on shutdown"""

    def __init__(self, kato_url: str):
        self.kato = httpx.Client(base_url=kato_url)
        self.active_sessions = set()
        atexit.register(self.cleanup_all)

    def register(self, session_id: str):
        self.active_sessions.add(session_id)

    def cleanup_all(self):
        """Cleanup all registered sessions"""
        for session_id in self.active_sessions:
            try:
                self.kato.delete(f"/sessions/{session_id}")
            except:
                pass
```

### 3. Session Health Monitoring

```python
import time
from collections import defaultdict

class SessionHealthMonitor:
    """Monitor session health metrics"""

    def __init__(self):
        self.metrics = defaultdict(lambda: {
            "requests": 0,
            "errors": 0,
            "last_activity": None
        })

    def record_request(self, session_id: str, success: bool):
        """Record session request"""
        self.metrics[session_id]["requests"] += 1
        if not success:
            self.metrics[session_id]["errors"] += 1
        self.metrics[session_id]["last_activity"] = time.time()

    def get_error_rate(self, session_id: str) -> float:
        """Calculate error rate for session"""
        metrics = self.metrics[session_id]
        if metrics["requests"] == 0:
            return 0.0
        return metrics["errors"] / metrics["requests"]

    def get_idle_sessions(self, idle_threshold: int = 300) -> list:
        """Find sessions idle for more than threshold"""
        current_time = time.time()
        idle_sessions = []

        for session_id, metrics in self.metrics.items():
            if metrics["last_activity"]:
                idle_time = current_time - metrics["last_activity"]
                if idle_time > idle_threshold:
                    idle_sessions.append(session_id)

        return idle_sessions
```

## Related Documentation

- [Multi-Instance Setup](multi-instance.md)
- [Load Balancing](load-balancing.md)
- [Architecture Patterns](architecture-patterns.md)
- [API Reference](/docs/reference/api/sessions.md)

---

**Last Updated**: November 2025
**KATO Version**: 3.0+
