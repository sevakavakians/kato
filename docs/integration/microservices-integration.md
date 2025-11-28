# KATO Microservices Integration Guide

## Table of Contents
1. [Overview](#overview)
2. [Service Mesh Integration](#service-mesh-integration)
3. [Service Discovery](#service-discovery)
4. [API Communication Patterns](#api-communication-patterns)
5. [Circuit Breakers and Resilience](#circuit-breakers-and-resilience)
6. [Distributed Tracing](#distributed-tracing)
7. [Configuration Management](#configuration-management)
8. [Real-World Examples](#real-world-examples)

## Overview

KATO integrates seamlessly into microservices architectures as a specialized memory and prediction service. This guide covers best practices for deploying KATO within service mesh environments, implementing service discovery, and building resilient inter-service communication.

### Key Principles

1. **Service Independence**: KATO as autonomous microservice
2. **API Contracts**: Well-defined REST interfaces
3. **Fault Tolerance**: Graceful degradation when KATO unavailable
4. **Observability**: Full tracing and monitoring integration
5. **Scalability**: Horizontal scaling with load balancing

## Service Mesh Integration

### Istio Integration

KATO works seamlessly with Istio service mesh for traffic management, security, and observability.

**Deployment YAML**:
```yaml
apiVersion: v1
kind: Service
metadata:
  name: kato
  labels:
    app: kato
    version: v3.0.0
spec:
  ports:
  - port: 8000
    name: http
  selector:
    app: kato

---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: kato
spec:
  replicas: 3
  selector:
    matchLabels:
      app: kato
      version: v3.0.0
  template:
    metadata:
      labels:
        app: kato
        version: v3.0.0
    spec:
      containers:
      - name: kato
        image: ghcr.io/sevakavakians/kato:3.0.0
        ports:
        - containerPort: 8000
        env:
        - name: PROCESSOR_ID
          valueFrom:
            fieldRef:
              fieldPath: metadata.name
        - name: CLICKHOUSE_HOST
          value: "clickhouse.default.svc.cluster.local"
        - name: CLICKHOUSE_PASSWORD
          valueFrom:
            secretKeyRef:
              name: kato-secrets
              key: clickhouse-password
        - name: REDIS_HOST
          value: "redis.default.svc.cluster.local"
        - name: QDRANT_HOST
          value: "qdrant.default.svc.cluster.local"
        resources:
          requests:
            cpu: 100m
            memory: 256Mi
          limits:
            cpu: 500m
            memory: 512Mi
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /ready
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 5
```

**Virtual Service for Traffic Management**:
```yaml
apiVersion: networking.istio.io/v1beta1
kind: VirtualService
metadata:
  name: kato
spec:
  hosts:
  - kato
  http:
  - match:
    - headers:
        x-user-id:
          regex: "premium-.*"
    route:
    - destination:
        host: kato
        subset: high-performance
      weight: 100
  - route:
    - destination:
        host: kato
        subset: standard
      weight: 100
    timeout: 30s
    retries:
      attempts: 3
      perTryTimeout: 10s
      retryOn: 5xx,reset,connect-failure

---
apiVersion: networking.istio.io/v1beta1
kind: DestinationRule
metadata:
  name: kato
spec:
  host: kato
  trafficPolicy:
    connectionPool:
      tcp:
        maxConnections: 100
      http:
        http1MaxPendingRequests: 50
        maxRequestsPerConnection: 5
    outlierDetection:
      consecutiveErrors: 5
      interval: 30s
      baseEjectionTime: 30s
  subsets:
  - name: standard
    labels:
      version: v3.0.0
  - name: high-performance
    labels:
      version: v3.0.0
      tier: premium
```

### Linkerd Integration

For simpler service mesh requirements, Linkerd provides automatic mTLS and observability.

**Deployment with Linkerd Annotations**:
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: kato
  annotations:
    linkerd.io/inject: enabled
spec:
  replicas: 3
  selector:
    matchLabels:
      app: kato
  template:
    metadata:
      labels:
        app: kato
      annotations:
        linkerd.io/inject: enabled
        config.linkerd.io/proxy-cpu-request: "0.1"
        config.linkerd.io/proxy-memory-request: "64Mi"
    spec:
      containers:
      - name: kato
        image: ghcr.io/sevakavakians/kato:3.0.0
        ports:
        - containerPort: 8000
```

### Consul Service Mesh

KATO integrates with Consul for service discovery and mesh networking.

**Consul Service Registration**:
```hcl
service {
  name = "kato"
  id   = "kato-1"
  port = 8000

  tags = ["v3", "memory-service", "prediction"]

  check {
    http     = "http://localhost:8000/health"
    interval = "10s"
    timeout  = "2s"
  }

  connect {
    sidecar_service {
      proxy {
        upstreams = [
          {
            destination_name = "clickhouse"
            local_bind_port  = 9000
          },
          {
            destination_name = "redis"
            local_bind_port  = 6379
          },
          {
            destination_name = "qdrant"
            local_bind_port  = 6333
          }
        ]
      }
    }
  }
}
```

## Service Discovery

### Kubernetes DNS

KATO leverages Kubernetes native service discovery.

**Client Code Example**:
```python
import requests
from typing import Optional

class KatoClient:
    """Client for KATO service in Kubernetes"""

    def __init__(self, namespace: str = "default"):
        # Kubernetes DNS format: <service>.<namespace>.svc.cluster.local
        self.base_url = f"http://kato.{namespace}.svc.cluster.local:8000"
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json"
        })

    def create_session(self, node_id: str, config: Optional[dict] = None) -> str:
        """Create KATO session"""
        response = self.session.post(
            f"{self.base_url}/sessions",
            json={"node_id": node_id, "config": config or {}}
        )
        response.raise_for_status()
        return response.json()["session_id"]

    def observe(self, session_id: str, observation: dict) -> dict:
        """Send observation to KATO"""
        response = self.session.post(
            f"{self.base_url}/sessions/{session_id}/observe",
            json=observation
        )
        response.raise_for_status()
        return response.json()

# Usage
client = KatoClient(namespace="production")
session_id = client.create_session("user-123")
```

### Consul Service Discovery

**Python Client with Consul**:
```python
import consul
import requests
from typing import List, Optional

class ConsulKatoClient:
    """KATO client with Consul service discovery"""

    def __init__(self, consul_host: str = "localhost", consul_port: int = 8500):
        self.consul = consul.Consul(host=consul_host, port=consul_port)
        self.session = requests.Session()

    def _discover_kato_instances(self) -> List[dict]:
        """Discover healthy KATO instances"""
        index, services = self.consul.health.service("kato", passing=True)
        return [
            {
                "address": s["Service"]["Address"],
                "port": s["Service"]["Port"],
                "id": s["Service"]["ID"]
            }
            for s in services
        ]

    def get_kato_url(self) -> str:
        """Get URL for healthy KATO instance"""
        instances = self._discover_kato_instances()
        if not instances:
            raise RuntimeError("No healthy KATO instances found")

        # Simple round-robin (use proper load balancing in production)
        instance = instances[0]
        return f"http://{instance['address']}:{instance['port']}"

    def create_session(self, node_id: str) -> str:
        """Create session on discovered KATO instance"""
        url = self.get_kato_url()
        response = self.session.post(
            f"{url}/sessions",
            json={"node_id": node_id}
        )
        response.raise_for_status()
        return response.json()["session_id"]
```

## API Communication Patterns

### Synchronous REST API

Standard request-response pattern for immediate results.

**FastAPI Microservice Integration**:
```python
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
import httpx
from typing import Optional

app = FastAPI()

class KatoService:
    """KATO service client"""

    def __init__(self, base_url: str):
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=30.0)

    async def create_session(self, node_id: str) -> str:
        response = await self.client.post(
            f"{self.base_url}/sessions",
            json={"node_id": node_id}
        )
        response.raise_for_status()
        return response.json()["session_id"]

    async def observe(self, session_id: str, observation: dict):
        response = await self.client.post(
            f"{self.base_url}/sessions/{session_id}/observe",
            json=observation
        )
        response.raise_for_status()
        return response.json()

    async def get_predictions(self, session_id: str):
        response = await self.client.get(
            f"{self.base_url}/sessions/{session_id}/predictions"
        )
        response.raise_for_status()
        return response.json()

# Dependency injection
async def get_kato_service() -> KatoService:
    return KatoService(base_url="http://kato:8000")

class ObservationRequest(BaseModel):
    user_id: str
    strings: list[str]
    vectors: list[list[float]]
    emotives: dict

@app.post("/api/process")
async def process_observation(
    request: ObservationRequest,
    kato: KatoService = Depends(get_kato_service)
):
    """Process observation with KATO memory"""
    try:
        # Create or reuse session
        session_id = await kato.create_session(request.user_id)

        # Send observation
        result = await kato.observe(
            session_id,
            {
                "strings": request.strings,
                "vectors": request.vectors,
                "emotives": request.emotives
            }
        )

        # Get predictions
        predictions = await kato.get_predictions(session_id)

        return {
            "observation_result": result,
            "predictions": predictions
        }
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail=f"KATO error: {str(e)}")
```

### Asynchronous Message Queue

For decoupled, event-driven communication.

**RabbitMQ Integration** (see [event-driven-architecture.md](event-driven-architecture.md)):
```python
import pika
import json
from typing import Callable

class KatoMessageConsumer:
    """Consume observations from message queue and process with KATO"""

    def __init__(self, rabbitmq_url: str, kato_url: str):
        self.connection = pika.BlockingConnection(
            pika.URLParameters(rabbitmq_url)
        )
        self.channel = self.connection.channel()
        self.kato_url = kato_url

        # Declare queues
        self.channel.queue_declare(queue="observations", durable=True)
        self.channel.queue_declare(queue="predictions", durable=True)

    def process_observation(self, ch, method, properties, body):
        """Process observation message"""
        try:
            data = json.loads(body)

            # Send to KATO
            response = requests.post(
                f"{self.kato_url}/sessions/{data['session_id']}/observe",
                json=data["observation"]
            )

            # Publish predictions to output queue
            predictions = requests.get(
                f"{self.kato_url}/sessions/{data['session_id']}/predictions"
            ).json()

            self.channel.basic_publish(
                exchange="",
                routing_key="predictions",
                body=json.dumps({
                    "session_id": data["session_id"],
                    "predictions": predictions
                })
            )

            ch.basic_ack(delivery_tag=method.delivery_tag)
        except Exception as e:
            print(f"Error processing observation: {e}")
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

    def start(self):
        """Start consuming messages"""
        self.channel.basic_qos(prefetch_count=1)
        self.channel.basic_consume(
            queue="observations",
            on_message_callback=self.process_observation
        )
        self.channel.start_consuming()
```

## Circuit Breakers and Resilience

### Pybreaker Integration

Prevent cascading failures when KATO is unavailable.

```python
from pybreaker import CircuitBreaker, CircuitBreakerError
import httpx
from typing import Optional

# Configure circuit breaker
kato_breaker = CircuitBreaker(
    fail_max=5,           # Open after 5 failures
    timeout_duration=60,   # Try again after 60 seconds
    exclude=[httpx.HTTPStatusError]  # Don't count HTTP errors as failures
)

class ResilientKatoClient:
    """KATO client with circuit breaker"""

    def __init__(self, base_url: str):
        self.base_url = base_url
        self.client = httpx.Client(timeout=10.0)

    @kato_breaker
    def observe(self, session_id: str, observation: dict) -> Optional[dict]:
        """Send observation with circuit breaker protection"""
        try:
            response = self.client.post(
                f"{self.base_url}/sessions/{session_id}/observe",
                json=observation
            )
            response.raise_for_status()
            return response.json()
        except httpx.RequestError as e:
            print(f"KATO connection error: {e}")
            raise  # Triggers circuit breaker

    def observe_with_fallback(
        self,
        session_id: str,
        observation: dict
    ) -> dict:
        """Observe with graceful fallback"""
        try:
            return self.observe(session_id, observation)
        except CircuitBreakerError:
            print("Circuit breaker open - KATO unavailable")
            return {"predictions": [], "status": "degraded"}
        except Exception as e:
            print(f"Observation failed: {e}")
            return {"predictions": [], "status": "error"}

# Usage
client = ResilientKatoClient("http://kato:8000")
result = client.observe_with_fallback("session-123", {...})
```

### Tenacity Retry Logic

```python
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type
)
import httpx

class RetryableKatoClient:
    """KATO client with exponential backoff"""

    def __init__(self, base_url: str):
        self.base_url = base_url
        self.client = httpx.Client()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(httpx.RequestError)
    )
    def create_session(self, node_id: str) -> str:
        """Create session with retry"""
        response = self.client.post(
            f"{self.base_url}/sessions",
            json={"node_id": node_id}
        )
        response.raise_for_status()
        return response.json()["session_id"]
```

## Distributed Tracing

### OpenTelemetry Integration

```python
from opentelemetry import trace
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
import httpx

# Instrument httpx client
HTTPXClientInstrumentor().instrument()

tracer = trace.get_tracer(__name__)

class TracedKatoClient:
    """KATO client with distributed tracing"""

    def __init__(self, base_url: str):
        self.base_url = base_url
        self.client = httpx.AsyncClient()

    async def observe(self, session_id: str, observation: dict):
        """Traced observation"""
        with tracer.start_as_current_span("kato.observe") as span:
            span.set_attribute("kato.session_id", session_id)
            span.set_attribute("kato.observation_size", len(observation.get("strings", [])))

            response = await self.client.post(
                f"{self.base_url}/sessions/{session_id}/observe",
                json=observation
            )

            span.set_attribute("http.status_code", response.status_code)
            response.raise_for_status()

            return response.json()
```

## Configuration Management

### Kubernetes ConfigMap

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: kato-config
data:
  LOG_LEVEL: "INFO"
  SESSION_TTL: "3600"
  SESSION_AUTO_EXTEND: "true"
  MAX_PATTERN_LENGTH: "0"
  RECALL_THRESHOLD: "0.1"
  USE_TOKEN_MATCHING: "true"

---
apiVersion: v1
kind: Secret
metadata:
  name: kato-secrets
type: Opaque
stringData:
  clickhouse-host: "clickhouse"
  clickhouse-password: "secure-password-here"
  redis-password: "secure-password-here"
```

## Real-World Examples

### Example 1: E-Commerce Recommendation Service

```python
from fastapi import FastAPI, Depends
import httpx

app = FastAPI()

class RecommendationService:
    """Product recommendations powered by KATO"""

    def __init__(self, kato_url: str):
        self.kato = httpx.AsyncClient(base_url=kato_url)

    async def track_view(self, user_id: str, product_id: str):
        """Track product view"""
        session_id = f"user-{user_id}"

        await self.kato.post(
            f"/sessions/{session_id}/observe",
            json={
                "strings": [f"view:{product_id}"],
                "vectors": [],
                "emotives": {}
            }
        )

    async def get_recommendations(self, user_id: str) -> list[str]:
        """Get product recommendations"""
        session_id = f"user-{user_id}"

        response = await self.kato.get(
            f"/sessions/{session_id}/predictions"
        )
        predictions = response.json()

        # Extract product IDs from predictions
        recommendations = []
        for pred in predictions[:5]:  # Top 5
            if pred["future"]:
                for event in pred["future"][0]:
                    if event.startswith("view:"):
                        recommendations.append(event.split(":")[1])

        return recommendations
```

### Example 2: Chatbot Memory Service

```python
class ChatbotMemoryService:
    """Conversational memory with KATO"""

    def __init__(self, kato_url: str):
        self.kato_url = kato_url
        self.client = httpx.AsyncClient()

    async def process_message(
        self,
        user_id: str,
        message: str,
        intent: str,
        sentiment: float
    ) -> dict:
        """Process chat message with memory"""
        session_id = f"chat-{user_id}"

        # Observe message
        await self.client.post(
            f"{self.kato_url}/sessions/{session_id}/observe",
            json={
                "strings": [intent, message[:50]],  # Intent + message snippet
                "vectors": [],
                "emotives": {"sentiment": sentiment}
            }
        )

        # Get context predictions
        predictions = await self.client.get(
            f"{self.kato_url}/sessions/{session_id}/predictions"
        )

        return {
            "message_processed": True,
            "conversation_context": predictions.json()
        }
```

## Best Practices

1. **Health Checks**: Always implement readiness and liveness probes
2. **Circuit Breakers**: Protect against cascading failures
3. **Timeouts**: Set reasonable timeouts for all KATO calls
4. **Retry Logic**: Use exponential backoff for transient failures
5. **Service Mesh**: Leverage mesh features for observability
6. **Resource Limits**: Set CPU and memory limits in Kubernetes
7. **Session Management**: Use consistent session_id strategies
8. **Monitoring**: Track KATO latency, error rates, and throughput

## Related Documentation

- [Event-Driven Architecture](event-driven-architecture.md)
- [Load Balancing Strategies](load-balancing.md)
- [Session Management](session-management.md)
- [Multi-Instance Deployment](multi-instance.md)

---

**Last Updated**: November 2025
**KATO Version**: 3.0+
