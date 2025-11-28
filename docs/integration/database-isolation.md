# KATO Database Isolation Guide

## Table of Contents
1. [Overview](#overview)
2. [Multi-Tenancy Patterns](#multi-tenancy-patterns)
3. [Node ID Isolation](#node-id-isolation)
4. [Data Security](#data-security)
5. [MongoDB Isolation Strategies](#mongodb-isolation-strategies)
6. [Redis Isolation](#redis-isolation)
7. [Qdrant Vector Isolation](#qdrant-vector-isolation)
8. [Best Practices](#best-practices)

## Overview

KATO ensures data isolation through node_id-based partitioning and session isolation. This guide covers multi-tenancy patterns, database isolation strategies, and data security best practices.

### Isolation Levels

1. **Session-Level**: Complete STM isolation per session
2. **Node-Level**: Pattern storage isolated by node_id
3. **Tenant-Level**: Organization/tenant-wide data separation
4. **Database-Level**: Separate databases per environment

## Multi-Tenancy Patterns

### Pattern 1: Node ID as Tenant Identifier

```python
class TenantIsolation:
    """Tenant isolation using node_id prefix"""

    def __init__(self, kato_url: str):
        self.kato = httpx.Client(base_url=kato_url)

    def create_tenant_session(self, tenant_id: str, user_id: str) -> str:
        """Create session with tenant isolation"""
        node_id = f"tenant-{tenant_id}:user-{user_id}"

        response = self.kato.post(
            "/sessions",
            json={"node_id": node_id}
        )
        return response.json()["session_id"]

    def get_tenant_patterns(self, tenant_id: str) -> list:
        """Get all patterns for tenant"""
        # Query MongoDB directly for patterns with node_id prefix
        from pymongo import MongoClient

        client = MongoClient("mongodb://localhost:27017")
        db = client["kato"]
        patterns = db["patterns"].find({
            "node_id": {"$regex": f"^tenant-{tenant_id}:"}
        })
        return list(patterns)

# Usage
isolation = TenantIsolation("http://localhost:8000")
session_id = isolation.create_tenant_session("acme-corp", "user-123")
```

### Pattern 2: Isolated KATO Instance Per Tenant

```python
class InstancePerTenant:
    """Separate KATO instance per tenant"""

    def __init__(self, kato_base_url: str, clickhouse_host: str):
        self.kato_base_url = kato_base_url
        self.clickhouse_host = clickhouse_host
        self.tenant_configs = {}

    def configure_tenant(self, tenant_id: str, kb_id: str):
        """Configure KATO instance for tenant"""
        # Start KATO instance with tenant-specific kb_id
        import subprocess

        env = {
            "PROCESSOR_ID": f"kato-{tenant_id}",
            "CLICKHOUSE_HOST": self.clickhouse_host,
            "KB_ID": kb_id,
            "API_PORT": str(8000 + hash(tenant_id) % 1000)
        }

        # Would typically use docker-compose or k8s to start instance
        # This is conceptual example
        self.tenant_configs[tenant_id] = {
            "kb_id": kb_id,
            "port": env["API_PORT"]
        }

    def get_tenant_url(self, tenant_id: str) -> str:
        """Get KATO URL for tenant"""
        config = self.tenant_configs.get(tenant_id)
        if not config:
            raise ValueError(f"Tenant {tenant_id} not configured")
        return f"http://localhost:{config['port']}"
```

## Node ID Isolation

### Node ID Design Patterns

```python
class NodeIDStrategy:
    """Design node_id for isolation and organization"""

    @staticmethod
    def user_isolation(user_id: str) -> str:
        """One node per user"""
        return f"user:{user_id}"

    @staticmethod
    def tenant_user_isolation(tenant_id: str, user_id: str) -> str:
        """Tenant + user isolation"""
        return f"tenant:{tenant_id}:user:{user_id}"

    @staticmethod
    def application_context(app_id: str, context: str, user_id: str) -> str:
        """Application + context + user"""
        return f"app:{app_id}:ctx:{context}:user:{user_id}"

    @staticmethod
    def shared_team_patterns(team_id: str) -> str:
        """Shared patterns across team"""
        return f"team:{team_id}:shared"

    @staticmethod
    def hierarchical(org_id: str, dept_id: str, user_id: str) -> str:
        """Hierarchical organization"""
        return f"org:{org_id}:dept:{dept_id}:user:{user_id}"

# Usage examples
strategy = NodeIDStrategy()

# Individual user
node_id = strategy.user_isolation("alice")
# Result: "user:alice"

# Tenant isolation
node_id = strategy.tenant_user_isolation("acme-corp", "bob")
# Result: "tenant:acme-corp:user:bob"

# Complex hierarchy
node_id = strategy.hierarchical("bigco", "engineering", "charlie")
# Result: "org:bigco:dept:engineering:user:charlie"
```

### Querying by Node ID Pattern

```python
import clickhouse_connect
from typing import List, Dict

class NodeIDQueryManager:
    """Query patterns by kb_id prefix"""

    def __init__(self, clickhouse_host: str, clickhouse_port: int = 8123):
        self.client = clickhouse_connect.get_client(
            host=clickhouse_host,
            port=clickhouse_port
        )

    def get_patterns_for_tenant(self, tenant_id: str) -> List[Dict]:
        """Get all patterns for tenant"""
        result = self.client.query(
            "SELECT * FROM kato.patterns_data WHERE kb_id LIKE %(prefix)s",
            {"prefix": f"tenant:{tenant_id}:%"}
        )
        return [dict(zip(result.column_names, row)) for row in result.result_rows]

    def get_patterns_for_team(self, team_id: str) -> List[Dict]:
        """Get team's shared patterns"""
        result = self.client.query(
            "SELECT * FROM kato.patterns_data WHERE kb_id = %(kb_id)s",
            {"kb_id": f"team:{team_id}:shared"}
        )
        return [dict(zip(result.column_names, row)) for row in result.result_rows]

    def get_user_patterns_across_tenants(self, user_id: str) -> Dict[str, List]:
        """Get user's patterns grouped by tenant"""
        result = self.client.query(
            "SELECT * FROM kato.patterns_data WHERE kb_id LIKE %(suffix)s",
            {"suffix": f"%:user:{user_id}"}
        )

        grouped = {}
        for row in result.result_rows:
            row_dict = dict(zip(result.column_names, row))
            # Extract tenant from kb_id
            parts = row_dict["kb_id"].split(":")
            if len(parts) >= 2 and parts[0] == "tenant":
                tenant_id = parts[1]
                if tenant_id not in grouped:
                    grouped[tenant_id] = []
                grouped[tenant_id].append(row_dict)

        return grouped

    def delete_tenant_data(self, tenant_id: str):
        """Delete all data for tenant"""
        # Delete patterns (use ALTER DELETE for ClickHouse)
        result = self.client.command(
            f"ALTER TABLE kato.patterns_data DELETE WHERE kb_id LIKE 'tenant:{tenant_id}:%'"
        )
        return result
```

## Data Security

### Encryption at Rest

```python
from cryptography.fernet import Fernet
import json

class EncryptedSessionManager:
    """Encrypt sensitive session data"""

    def __init__(self, kato_url: str, encryption_key: bytes):
        self.kato = httpx.Client(base_url=kato_url)
        self.cipher = Fernet(encryption_key)

    def create_encrypted_session(
        self,
        node_id: str,
        sensitive_data: dict
    ) -> str:
        """Create session with encrypted metadata"""
        # Encrypt sensitive data
        encrypted = self.cipher.encrypt(
            json.dumps(sensitive_data).encode()
        )

        # Store encrypted data in session metadata
        response = self.kato.post(
            "/sessions",
            json={
                "node_id": node_id,
                "config": {
                    "metadata": {
                        "encrypted_data": encrypted.decode()
                    }
                }
            }
        )
        return response.json()["session_id"]

    def decrypt_session_data(self, session_id: str) -> dict:
        """Retrieve and decrypt session data"""
        response = self.kato.get(f"/sessions/{session_id}")
        session = response.json()

        encrypted_data = session["config"]["metadata"]["encrypted_data"]
        decrypted = self.cipher.decrypt(encrypted_data.encode())
        return json.loads(decrypted)
```

### Access Control

```python
from typing import Optional
import jwt

class AccessControlledKatoClient:
    """KATO client with role-based access control"""

    def __init__(self, kato_url: str, jwt_secret: str):
        self.kato = httpx.Client(base_url=kato_url)
        self.jwt_secret = jwt_secret

    def verify_access(self, token: str, required_role: str) -> dict:
        """Verify JWT token and role"""
        try:
            payload = jwt.decode(token, self.jwt_secret, algorithms=["HS256"])
            if payload.get("role") != required_role:
                raise PermissionError("Insufficient permissions")
            return payload
        except jwt.InvalidTokenError:
            raise PermissionError("Invalid token")

    def create_session(
        self,
        token: str,
        node_id: str
    ) -> str:
        """Create session with access control"""
        # Verify user has permission
        user = self.verify_access(token, "user")

        # Ensure node_id matches user's tenant
        expected_prefix = f"tenant:{user['tenant_id']}:"
        if not node_id.startswith(expected_prefix):
            raise PermissionError("Cannot access other tenant's data")

        response = self.kato.post(
            "/sessions",
            json={"node_id": node_id},
            headers={"Authorization": f"Bearer {token}"}
        )
        return response.json()["session_id"]
```

## ClickHouse Isolation Strategies

### KB_ID Partitioning

```python
class KBIDIsolation:
    """Use kb_id partitioning for tenant isolation"""

    def __init__(self, clickhouse_host: str, clickhouse_port: int = 8123):
        self.client = clickhouse_connect.get_client(
            host=clickhouse_host,
            port=clickhouse_port
        )

    def store_pattern(self, tenant_id: str, pattern: dict):
        """Store pattern with tenant kb_id"""
        kb_id = f"tenant_{tenant_id}"
        self.client.insert(
            "kato.patterns_data",
            [[
                pattern["name"],
                kb_id,
                pattern["length"],
                pattern["observation_count"],
                # ... other fields
            ]],
            column_names=["name", "kb_id", "length", "observation_count"]
        )

    def get_patterns(self, tenant_id: str) -> list:
        """Get all patterns for tenant"""
        kb_id = f"tenant_{tenant_id}"
        result = self.client.query(
            "SELECT * FROM kato.patterns_data WHERE kb_id = %(kb_id)s",
            {"kb_id": kb_id}
        )
        return result.result_rows
```

### Filter Pipeline Optimization

```python
class OptimizedIsolation:
    """Optimize queries with multi-stage filter pipeline"""

    def __init__(self, clickhouse_host: str, clickhouse_port: int = 8123):
        self.client = clickhouse_connect.get_client(
            host=clickhouse_host,
            port=clickhouse_port
        )

    def query_tenant_patterns(self, tenant_id: str, limit: int = 100):
        """Efficiently query tenant patterns using filter pipeline"""
        kb_id = f"tenant_{tenant_id}"

        # ClickHouse uses multi-stage filtering automatically
        result = self.client.query(
            """
            SELECT * FROM kato.patterns_data
            WHERE kb_id = %(kb_id)s
            ORDER BY created_at DESC
            LIMIT %(limit)s
            """,
            {"kb_id": kb_id, "limit": limit}
        )
        return result.result_rows
```

## Redis Isolation

### Key Namespace Isolation

```python
import redis

class RedisIsolation:
    """Isolate Redis keys by tenant"""

    def __init__(self, redis_url: str):
        self.redis = redis.from_url(redis_url)

    def get_tenant_key(self, tenant_id: str, key: str) -> str:
        """Generate tenant-specific key"""
        return f"tenant:{tenant_id}:{key}"

    def set_session(self, tenant_id: str, session_id: str, data: dict, ttl: int):
        """Store session data with tenant isolation"""
        key = self.get_tenant_key(tenant_id, f"session:{session_id}")
        self.redis.setex(key, ttl, json.dumps(data))

    def get_session(self, tenant_id: str, session_id: str) -> Optional[dict]:
        """Retrieve session data"""
        key = self.get_tenant_key(tenant_id, f"session:{session_id}")
        data = self.redis.get(key)
        return json.loads(data) if data else None

    def delete_tenant_data(self, tenant_id: str):
        """Delete all Redis data for tenant"""
        pattern = f"tenant:{tenant_id}:*"
        cursor = 0
        while True:
            cursor, keys = self.redis.scan(cursor, match=pattern, count=100)
            if keys:
                self.redis.delete(*keys)
            if cursor == 0:
                break
```

## Qdrant Vector Isolation

### Collection Per Tenant

```python
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

class QdrantIsolation:
    """Isolate vectors in Qdrant by collection"""

    def __init__(self, qdrant_url: str):
        self.client = QdrantClient(url=qdrant_url)

    def create_tenant_collection(self, tenant_id: str, vector_size: int = 768):
        """Create collection for tenant"""
        collection_name = f"kato_tenant_{tenant_id}"

        self.client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE)
        )

    def upsert_vectors(self, tenant_id: str, vectors: list, payloads: list):
        """Store vectors in tenant collection"""
        collection_name = f"kato_tenant_{tenant_id}"
        self.client.upsert(
            collection_name=collection_name,
            points=[
                {"id": i, "vector": vec, "payload": payload}
                for i, (vec, payload) in enumerate(zip(vectors, payloads))
            ]
        )

    def search_vectors(self, tenant_id: str, query_vector: list, limit: int = 10):
        """Search vectors within tenant collection"""
        collection_name = f"kato_tenant_{tenant_id}"
        return self.client.search(
            collection_name=collection_name,
            query_vector=query_vector,
            limit=limit
        )

    def delete_tenant_collection(self, tenant_id: str):
        """Delete tenant's vector collection"""
        collection_name = f"kato_tenant_{tenant_id}"
        self.client.delete_collection(collection_name=collection_name)
```

### Payload-Based Filtering

```python
class QdrantPayloadIsolation:
    """Isolate using payload filtering instead of separate collections"""

    def __init__(self, qdrant_url: str):
        self.client = QdrantClient(url=qdrant_url)
        self.collection_name = "kato_vectors"

    def search_with_tenant_filter(
        self,
        tenant_id: str,
        query_vector: list,
        limit: int = 10
    ):
        """Search with tenant filter"""
        from qdrant_client.models import Filter, FieldCondition, MatchValue

        return self.client.search(
            collection_name=self.collection_name,
            query_vector=query_vector,
            query_filter=Filter(
                must=[
                    FieldCondition(
                        key="tenant_id",
                        match=MatchValue(value=tenant_id)
                    )
                ]
            ),
            limit=limit
        )
```

## Best Practices

1. **Node ID Prefix**: Use consistent prefix patterns for tenant isolation
2. **Database Indexes**: Create compound indexes on node_id for performance
3. **Collection Strategy**: Use separate collections for large tenants
4. **Data Encryption**: Encrypt sensitive data at rest and in transit
5. **Access Control**: Implement JWT or OAuth for authentication
6. **Audit Logging**: Log all data access for compliance
7. **Data Retention**: Implement TTL policies for automated cleanup
8. **Backup Strategy**: Separate backup schedules per tenant
9. **Testing**: Test cross-tenant isolation thoroughly
10. **Monitoring**: Track resource usage per tenant

## Related Documentation

- [Session Management](session-management.md)
- [Multi-Instance Deployment](multi-instance.md)
- [Security Guidelines](/docs/maintenance/security.md)
- [Database Persistence](/docs/users/database-persistence.md)

---

**Last Updated**: November 2025
**KATO Version**: 3.0+
