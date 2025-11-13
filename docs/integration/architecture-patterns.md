# KATO Integration Architecture Patterns

## Table of Contents
1. [Overview](#overview)
2. [Sidecar Pattern](#sidecar-pattern)
3. [API Gateway Pattern](#api-gateway-pattern)
4. [Event-Driven Integration](#event-driven-integration)
5. [Microservices Integration](#microservices-integration)
6. [Hybrid Agent Pattern](#hybrid-agent-pattern)
7. [Pattern Selection Guide](#pattern-selection-guide)
8. [Real-World Examples](#real-world-examples)

## Overview

KATO integrates into existing systems through several well-established architectural patterns. This document provides guidance on selecting and implementing the appropriate pattern for your use case.

### Integration Principles

1. **Loose Coupling**: KATO as independent service
2. **API-First**: RESTful interfaces for all operations
3. **Stateful**: Session-based interaction model
4. **Scalable**: Horizontal scaling support
5. **Observable**: Comprehensive logging and metrics

## Sidecar Pattern

### Architecture

```
┌─────────────────────────────────────┐
│      Application Container          │
│  ┌─────────────────────────────┐   │
│  │  Main Application           │   │
│  │  (Your Code)                │   │
│  └────────────┬────────────────┘   │
│               │ localhost:8000      │
│  ┌────────────▼────────────────┐   │
│  │  KATO Sidecar               │   │
│  │  (Memory & Prediction)      │   │
│  └─────────────────────────────┘   │
└─────────────────────────────────────┘
```

### Implementation

**Docker Compose**:
```yaml
version: '3.8'
services:
  app:
    image: your-app:latest
    depends_on:
      - kato
    environment:
      KATO_URL: http://kato:8000

  kato:
    image: ghcr.io/sevakavakians/kato:latest
    environment:
      PROCESSOR_ID: app-kato
```

**Kubernetes**:
```yaml
apiVersion: v1
kind: Pod
metadata:
  name: app-with-kato
spec:
  containers:
  - name: app
    image: your-app:latest
    env:
    - name: KATO_URL
      value: "http://localhost:8000"

  - name: kato
    image: ghcr.io/sevakavakians/kato:latest
    ports:
    - containerPort: 8000
```

### Use Cases

- Single application needs memory/prediction
- Co-located deployment preferred
- Low latency required
- Simple service discovery

### Pros/Cons

**Advantages**:
- Minimal network latency
- Simple configuration
- Isolated per application
- Easy to reason about

**Disadvantages**:
- Resource duplication (one KATO per app)
- Scaling complexity
- No sharing across applications

## API Gateway Pattern

### Architecture

```
┌──────────────────┐
│   API Gateway    │
│   (Kong/Nginx)   │
└────────┬─────────┘
         │
    ┌────┴────┬────────┬────────┐
    │         │        │        │
┌───▼───┐ ┌──▼──┐ ┌──▼───┐ ┌──▼───┐
│ App 1 │ │App 2│ │App 3 │ │ KATO │
└───────┘ └─────┘ └──────┘ └──────┘
```

### Implementation

**Kong API Gateway**:
```bash
# Register KATO service
curl -X POST http://kong:8001/services \
  --data 'name=kato' \
  --data 'url=http://kato:8000'

# Create route
curl -X POST http://kong:8001/services/kato/routes \
  --data 'paths[]=/kato' \
  --data 'strip_path=true'

# Add authentication
curl -X POST http://kong:8001/services/kato/plugins \
  --data 'name=key-auth'
```

**Nginx**:
```nginx
upstream kato {
    server kato1:8000;
    server kato2:8000;
    server kato3:8000;
}

location /kato/ {
    proxy_pass http://kato/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
}
```

### Use Cases

- Multiple applications share KATO
- Centralized authentication/authorization
- Rate limiting needed
- Request transformation required

### Pros/Cons

**Advantages**:
- Centralized access control
- Request/response transformation
- Monitoring and analytics
- Load balancing included

**Disadvantages**:
- Additional infrastructure component
- Potential bottleneck
- Increased complexity

## Event-Driven Integration

### Architecture

```
┌────────────┐   ┌──────────┐   ┌──────────┐
│   App 1    │──▶│  Kafka   │◀──│  App 2   │
└────────────┘   └────┬─────┘   └──────────┘
                      │
                 ┌────▼──────┐
                 │   KATO    │
                 │ Consumer  │
                 └───────────┘
```

### Implementation

**Kafka Consumer**:
```python
from kafka import KafkaConsumer
import requests

consumer = KafkaConsumer(
    'observations',
    bootstrap_servers=['kafka:9092'],
    value_deserializer=lambda m: json.loads(m.decode('utf-8'))
)

kato_url = "http://kato:8000"
session_id = "kafka-consumer-session"

for message in consumer:
    observation = message.value

    # Send to KATO
    response = requests.post(
        f"{kato_url}/sessions/{session_id}/observe",
        json=observation
    )

    # Get predictions
    predictions = requests.get(
        f"{kato_url}/sessions/{session_id}/predictions"
    ).json()

    # Publish predictions
    producer.send('predictions', predictions)
```

### Use Cases

- Asynchronous processing
- High-throughput systems
- Decoupled architectures
- Event sourcing systems

### Pros/Cons

**Advantages**:
- Loose coupling
- High scalability
- Fault tolerance (message replay)
- Time decoupling

**Disadvantages**:
- Eventual consistency
- More complex debugging
- Requires message broker

## Microservices Integration

### Architecture

```
┌─────────────────────────────────────────┐
│          Service Mesh (Istio)           │
└────┬─────────┬─────────┬─────────┬──────┘
     │         │         │         │
┌────▼───┐ ┌──▼────┐ ┌──▼────┐ ┌──▼────┐
│ Auth   │ │ Orders│ │ Users │ │ KATO  │
│ Service│ │Service│ │Service│ │Service│
└────────┘ └───────┘ └───────┘ └───────┘
```

### Implementation

**Service Registration (Consul)**:
```bash
# Register KATO service
curl -X PUT http://consul:8500/v1/agent/service/register \
  -d '{
    "name": "kato",
    "id": "kato-1",
    "address": "kato",
    "port": 8000,
    "check": {
      "http": "http://kato:8000/health",
      "interval": "10s"
    }
  }'
```

**Service Discovery (Python)**:
```python
import consul

# Connect to Consul
c = consul.Consul(host='consul', port=8500)

# Discover KATO service
index, services = c.health.service('kato', passing=True)

# Get healthy instance
kato_service = services[0]
kato_url = f"http://{kato_service['Service']['Address']}:{kato_service['Service']['Port']}"

# Use KATO
response = requests.post(f"{kato_url}/sessions/{session_id}/observe", json=data)
```

### Use Cases

- Large microservices architecture
- Service mesh deployed
- Dynamic service discovery needed
- Complex routing requirements

### Pros/Cons

**Advantages**:
- Dynamic discovery
- Health checking
- Load balancing
- Consistent with architecture

**Disadvantages**:
- Requires service mesh
- Operational complexity
- Learning curve

## Hybrid Agent Pattern

### Architecture

Combines KATO with LLMs for intelligent decision-making:

```
┌─────────────────────────────────────────┐
│           Request (Natural Language)     │
└───────────────────┬─────────────────────┘
                    │
        ┌───────────▼──────────┐
        │    LLM/SLM           │
        │ (Structured Output)  │
        └───────────┬──────────┘
                    │
        ┌───────────▼──────────┐
        │    KATO Core         │
        │ (Pattern Matching)   │
        └───────────┬──────────┘
                    │
        ┌───────────▼──────────┐
        │  Decision Engine     │
        │ (Weighted Selection) │
        └───────────┬──────────┘
                    │
        ┌───────────▼──────────┐
        │  Action Execution    │
        │  (MCP/API Calls)     │
        └──────────────────────┘
```

### Implementation

```python
class HybridAgent:
    def __init__(self, llm_client, kato_url, session_id):
        self.llm = llm_client
        self.kato = kato_url
        self.session = session_id

    async def process_request(self, user_input):
        # Step 1: LLM processes natural language
        structured = await self.llm.create_completion(
            prompt=f"Extract entities and intent from: {user_input}",
            response_format={"type": "json_object"}
        )

        symbols = structured["entities"]
        intent = structured["intent"]

        # Step 2: Send to KATO
        observation = {"strings": symbols + [intent]}
        await requests.post(
            f"{self.kato}/sessions/{self.session}/observe",
            json=observation
        )

        # Step 3: Get predictions
        predictions = await requests.get(
            f"{self.kato}/sessions/{self.session}/predictions"
        ).json()

        # Step 4: Decision making
        if predictions:
            # Use KATO predictions
            action = self.select_action(predictions)
        else:
            # Fallback to LLM reasoning
            action = await self.llm_fallback(user_input, symbols)

        # Step 5: Execute action
        result = await self.execute_action(action)

        return result
```

### Use Cases

- Chatbots with memory
- Intelligent agents
- Decision support systems
- Recommendation engines

See [docs/integration/hybrid-agents-analysis.md](hybrid-agents-analysis.md) for detailed analysis.

## Pattern Selection Guide

### Decision Matrix

| Pattern | Complexity | Scalability | Latency | Best For |
|---------|------------|-------------|---------|----------|
| Sidecar | Low | Medium | Lowest | Single app, simple deployment |
| API Gateway | Medium | High | Low | Multi-app, centralized control |
| Event-Driven | High | Highest | Variable | Async processing, high throughput |
| Microservices | High | High | Low | Service mesh, complex systems |
| Hybrid Agent | High | Medium | Medium | AI applications, decision-making |

### Selection Flowchart

```
Start
  │
  ▼
Single application? ──Yes──▶ Sidecar Pattern
  │
  No
  │
  ▼
Async processing? ──Yes──▶ Event-Driven Pattern
  │
  No
  │
  ▼
Service mesh exists? ──Yes──▶ Microservices Integration
  │
  No
  │
  ▼
Need centralized control? ──Yes──▶ API Gateway Pattern
  │
  No
  │
  ▼
AI/LLM integration? ──Yes──▶ Hybrid Agent Pattern
  │
  No
  │
  ▼
Default: Sidecar or API Gateway
```

## Real-World Examples

### Example 1: E-Commerce Recommendation

**Pattern**: API Gateway + Microservices

```python
# Product service observes user behavior
@app.post("/product/view/{product_id}")
async def view_product(product_id: str, user_id: str):
    # Record view in KATO
    await kato.observe(
        session_id=user_id,
        strings=["product_view", product_id, get_category(product_id)]
    )

    # Get recommendations
    predictions = await kato.get_predictions(session_id=user_id)

    # Extract future products
    recommended_products = [
        symbol for prediction in predictions
        for symbol in prediction["future"]
        if symbol.startswith("product_")
    ]

    return {"recommendations": recommended_products}
```

### Example 2: IoT Sensor Monitoring

**Pattern**: Event-Driven Integration

```python
# Kafka consumer processes sensor data
async def process_sensor_data(message):
    sensor_id = message["sensor_id"]
    readings = message["readings"]

    # Observe in KATO
    await kato.observe(
        session_id=f"sensor_{sensor_id}",
        strings=[f"sensor_{sensor_id}"],
        emotives={"temperature": readings["temp"], "pressure": readings["pressure"]}
    )

    # Check for anomalies
    predictions = await kato.get_predictions(session_id=f"sensor_{sensor_id}")

    if not predictions or predictions[0]["potential"] < 0.5:
        # Anomaly detected
        await send_alert(sensor_id, readings)
```

### Example 3: Chatbot with Memory

**Pattern**: Hybrid Agent

```python
# Chatbot combines LLM + KATO
async def handle_message(user_id, message):
    # LLM extracts intent
    intent = await llm.extract_intent(message)

    # KATO maintains conversation memory
    await kato.observe(
        session_id=user_id,
        strings=[intent["action"], intent["entity"]]
    )

    # Get context-aware predictions
    predictions = await kato.get_predictions(session_id=user_id)

    # LLM generates response using predictions as context
    response = await llm.generate_response(
        message=message,
        context=predictions
    )

    return response
```

## Related Documentation

- [Hybrid Agents](hybrid-agents-analysis.md) - Detailed hybrid agent framework
- [Microservices Integration](microservices-integration.md) - Microservices patterns
- [Event-Driven Architecture](event-driven-architecture.md) - Event-driven details
- [Session Management](session-management.md) - Session handling

---

**Last Updated**: November 2025
**KATO Version**: 3.0+
