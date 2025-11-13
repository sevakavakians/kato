# KATO Event-Driven Architecture Guide

## Table of Contents
1. [Overview](#overview)
2. [Message Queue Integration](#message-queue-integration)
3. [Event Sourcing Patterns](#event-sourcing-patterns)
4. [Asynchronous Processing](#asynchronous-processing)
5. [Kafka Integration](#kafka-integration)
6. [RabbitMQ Integration](#rabbitmq-integration)
7. [Redis Streams](#redis-streams)
8. [Real-World Examples](#real-world-examples)

## Overview

KATO integrates seamlessly into event-driven architectures, enabling asynchronous pattern learning and prediction. This guide covers integration with popular message brokers, event sourcing patterns, and async processing strategies.

### Event-Driven Benefits

1. **Decoupling**: Services communicate via events, not direct calls
2. **Scalability**: Process high-throughput event streams
3. **Resilience**: Messages persist until processed
4. **Flexibility**: Add new consumers without changing producers
5. **Replay**: Event sourcing enables historical analysis

## Message Queue Integration

### Architecture Pattern

```
┌──────────────┐         ┌─────────────┐         ┌──────────────┐
│   Producer   │─events─>│Message Queue│─consume─>│KATO Consumer │
│  (Your App)  │         │(Kafka/RMQ)  │         │   Service    │
└──────────────┘         └─────────────┘         └──────┬───────┘
                                                         │
                                                         v
                                                  ┌─────────────┐
                                                  │    KATO     │
                                                  │   Service   │
                                                  └─────────────┘
```

### Event Schema

**Standard KATO Event**:
```json
{
  "event_type": "observation",
  "session_id": "user-123",
  "node_id": "user-123",
  "timestamp": "2025-11-13T10:30:00Z",
  "observation": {
    "strings": ["action:login", "page:dashboard"],
    "vectors": [],
    "emotives": {"sentiment": 0.8}
  },
  "metadata": {
    "source": "web-app",
    "correlation_id": "req-456"
  }
}
```

## Kafka Integration

### Producer: Publishing Events to Kafka

```python
from kafka import KafkaProducer
import json
from datetime import datetime
from typing import Optional

class KatoKafkaProducer:
    """Publish KATO observations to Kafka"""

    def __init__(self, bootstrap_servers: list[str], topic: str = "kato-observations"):
        self.producer = KafkaProducer(
            bootstrap_servers=bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            key_serializer=lambda k: k.encode("utf-8") if k else None,
            acks="all",  # Wait for all replicas
            compression_type="gzip"
        )
        self.topic = topic

    def publish_observation(
        self,
        session_id: str,
        observation: dict,
        metadata: Optional[dict] = None
    ):
        """Publish observation event to Kafka"""
        event = {
            "event_type": "observation",
            "session_id": session_id,
            "timestamp": datetime.utcnow().isoformat(),
            "observation": observation,
            "metadata": metadata or {}
        }

        # Use session_id as partition key for ordering
        self.producer.send(
            self.topic,
            key=session_id,
            value=event
        )

    def flush(self):
        """Ensure all messages are sent"""
        self.producer.flush()

# Usage
producer = KatoKafkaProducer(["localhost:9092"])
producer.publish_observation(
    session_id="user-123",
    observation={
        "strings": ["login", "dashboard"],
        "vectors": [],
        "emotives": {}
    },
    metadata={"source": "web-app"}
)
producer.flush()
```

### Consumer: Processing Kafka Events with KATO

```python
from kafka import KafkaConsumer
import httpx
import json
from typing import Callable

class KatoKafkaConsumer:
    """Consume Kafka events and process with KATO"""

    def __init__(
        self,
        bootstrap_servers: list[str],
        topic: str,
        kato_url: str,
        group_id: str = "kato-consumer-group"
    ):
        self.consumer = KafkaConsumer(
            topic,
            bootstrap_servers=bootstrap_servers,
            group_id=group_id,
            value_deserializer=lambda m: json.loads(m.decode("utf-8")),
            auto_offset_reset="earliest",  # Start from beginning if no offset
            enable_auto_commit=False,  # Manual commit after processing
            max_poll_records=10
        )
        self.kato_client = httpx.Client(base_url=kato_url, timeout=30.0)

    def process_event(self, event: dict) -> bool:
        """Process single event with KATO"""
        try:
            session_id = event["session_id"]
            observation = event["observation"]

            # Send to KATO
            response = self.kato_client.post(
                f"/sessions/{session_id}/observe",
                json=observation
            )
            response.raise_for_status()

            print(f"Processed event for session {session_id}")
            return True
        except Exception as e:
            print(f"Error processing event: {e}")
            return False

    def run(self):
        """Start consuming and processing events"""
        try:
            for message in self.consumer:
                event = message.value

                if self.process_event(event):
                    # Commit offset after successful processing
                    self.consumer.commit()
                else:
                    print(f"Failed to process event, will retry")
                    # Don't commit - message will be reprocessed

        except KeyboardInterrupt:
            print("Shutting down consumer...")
        finally:
            self.consumer.close()

# Usage
consumer = KatoKafkaConsumer(
    bootstrap_servers=["localhost:9092"],
    topic="kato-observations",
    kato_url="http://localhost:8000"
)
consumer.run()
```

### Kafka Streams for Complex Processing

```python
from kafka import KafkaProducer, KafkaConsumer
import httpx
import json
from typing import Dict, List

class KatoKafkaStreamProcessor:
    """Process Kafka stream with KATO and publish predictions"""

    def __init__(
        self,
        bootstrap_servers: list[str],
        input_topic: str,
        output_topic: str,
        kato_url: str
    ):
        self.consumer = KafkaConsumer(
            input_topic,
            bootstrap_servers=bootstrap_servers,
            group_id="kato-stream-processor",
            value_deserializer=lambda m: json.loads(m.decode("utf-8"))
        )
        self.producer = KafkaProducer(
            bootstrap_servers=bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode("utf-8")
        )
        self.output_topic = output_topic
        self.kato = httpx.Client(base_url=kato_url)

    def process_stream(self):
        """Process observation stream and publish predictions"""
        for message in self.consumer:
            event = message.value
            session_id = event["session_id"]

            # Send observation to KATO
            self.kato.post(
                f"/sessions/{session_id}/observe",
                json=event["observation"]
            )

            # Get predictions
            predictions_response = self.kato.get(
                f"/sessions/{session_id}/predictions"
            )
            predictions = predictions_response.json()

            # Publish prediction event
            prediction_event = {
                "event_type": "prediction",
                "session_id": session_id,
                "timestamp": event["timestamp"],
                "predictions": predictions,
                "original_event": event
            }

            self.producer.send(
                self.output_topic,
                key=session_id.encode("utf-8"),
                value=prediction_event
            )

# Usage
processor = KatoKafkaStreamProcessor(
    bootstrap_servers=["localhost:9092"],
    input_topic="user-events",
    output_topic="user-predictions",
    kato_url="http://localhost:8000"
)
processor.process_stream()
```

## RabbitMQ Integration

### Publishing to RabbitMQ Exchange

```python
import pika
import json
from datetime import datetime
from typing import Optional

class KatoRabbitMQPublisher:
    """Publish KATO events to RabbitMQ"""

    def __init__(self, rabbitmq_url: str, exchange: str = "kato-events"):
        self.connection = pika.BlockingConnection(
            pika.URLParameters(rabbitmq_url)
        )
        self.channel = self.connection.channel()

        # Declare topic exchange
        self.channel.exchange_declare(
            exchange=exchange,
            exchange_type="topic",
            durable=True
        )
        self.exchange = exchange

    def publish_observation(
        self,
        session_id: str,
        observation: dict,
        routing_key: Optional[str] = None
    ):
        """Publish observation to RabbitMQ"""
        event = {
            "event_type": "observation",
            "session_id": session_id,
            "timestamp": datetime.utcnow().isoformat(),
            "observation": observation
        }

        # Routing key format: observations.{node_id}
        routing_key = routing_key or f"observations.{session_id}"

        self.channel.basic_publish(
            exchange=self.exchange,
            routing_key=routing_key,
            body=json.dumps(event),
            properties=pika.BasicProperties(
                delivery_mode=2,  # Persistent
                content_type="application/json"
            )
        )

    def close(self):
        self.connection.close()

# Usage
publisher = KatoRabbitMQPublisher("amqp://localhost")
publisher.publish_observation(
    session_id="user-123",
    observation={"strings": ["action"], "vectors": [], "emotives": {}}
)
publisher.close()
```

### Consuming from RabbitMQ

```python
import pika
import httpx
import json
from typing import Callable

class KatoRabbitMQConsumer:
    """Consume RabbitMQ messages and process with KATO"""

    def __init__(
        self,
        rabbitmq_url: str,
        kato_url: str,
        queue: str = "kato-observations",
        exchange: str = "kato-events",
        routing_keys: list[str] = ["observations.*"]
    ):
        self.connection = pika.BlockingConnection(
            pika.URLParameters(rabbitmq_url)
        )
        self.channel = self.connection.channel()

        # Declare exchange and queue
        self.channel.exchange_declare(
            exchange=exchange,
            exchange_type="topic",
            durable=True
        )
        self.channel.queue_declare(queue=queue, durable=True)

        # Bind queue to routing keys
        for routing_key in routing_keys:
            self.channel.queue_bind(
                exchange=exchange,
                queue=queue,
                routing_key=routing_key
            )

        self.queue = queue
        self.kato = httpx.Client(base_url=kato_url)

    def callback(self, ch, method, properties, body):
        """Process message callback"""
        try:
            event = json.loads(body)
            session_id = event["session_id"]
            observation = event["observation"]

            # Send to KATO
            response = self.kato.post(
                f"/sessions/{session_id}/observe",
                json=observation
            )
            response.raise_for_status()

            # Acknowledge message
            ch.basic_ack(delivery_tag=method.delivery_tag)
            print(f"Processed message for session {session_id}")

        except Exception as e:
            print(f"Error processing message: {e}")
            # Reject and requeue
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

    def start(self):
        """Start consuming messages"""
        self.channel.basic_qos(prefetch_count=10)
        self.channel.basic_consume(
            queue=self.queue,
            on_message_callback=self.callback
        )
        print("Started consuming messages...")
        self.channel.start_consuming()

# Usage
consumer = KatoRabbitMQConsumer(
    rabbitmq_url="amqp://localhost",
    kato_url="http://localhost:8000"
)
consumer.start()
```

## Redis Streams

Redis Streams provides lightweight event streaming.

### Publishing to Redis Stream

```python
import redis
import json
from datetime import datetime

class KatoRedisStreamPublisher:
    """Publish KATO events to Redis Stream"""

    def __init__(self, redis_url: str, stream_key: str = "kato:observations"):
        self.redis = redis.from_url(redis_url)
        self.stream_key = stream_key

    def publish_observation(self, session_id: str, observation: dict) -> str:
        """Publish observation to Redis Stream"""
        event = {
            "event_type": "observation",
            "session_id": session_id,
            "timestamp": datetime.utcnow().isoformat(),
            "observation": json.dumps(observation)
        }

        # Add to stream with automatic ID
        message_id = self.redis.xadd(self.stream_key, event)
        return message_id.decode("utf-8")

# Usage
publisher = KatoRedisStreamPublisher("redis://localhost:6379")
message_id = publisher.publish_observation(
    session_id="user-123",
    observation={"strings": ["login"], "vectors": [], "emotives": {}}
)
```

### Consuming from Redis Stream

```python
import redis
import httpx
import json
from typing import Optional

class KatoRedisStreamConsumer:
    """Consume Redis Stream and process with KATO"""

    def __init__(
        self,
        redis_url: str,
        kato_url: str,
        stream_key: str = "kato:observations",
        consumer_group: str = "kato-processors",
        consumer_name: str = "consumer-1"
    ):
        self.redis = redis.from_url(redis_url)
        self.stream_key = stream_key
        self.consumer_group = consumer_group
        self.consumer_name = consumer_name
        self.kato = httpx.Client(base_url=kato_url)

        # Create consumer group if not exists
        try:
            self.redis.xgroup_create(
                self.stream_key,
                self.consumer_group,
                id="0",
                mkstream=True
            )
        except redis.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise

    def process_messages(self, count: int = 10, block: int = 5000):
        """Process messages from stream"""
        while True:
            # Read from consumer group
            messages = self.redis.xreadgroup(
                groupname=self.consumer_group,
                consumername=self.consumer_name,
                streams={self.stream_key: ">"},
                count=count,
                block=block
            )

            for stream_name, stream_messages in messages:
                for message_id, fields in stream_messages:
                    self.process_message(message_id, fields)

    def process_message(self, message_id: bytes, fields: dict):
        """Process single message"""
        try:
            session_id = fields[b"session_id"].decode("utf-8")
            observation = json.loads(fields[b"observation"].decode("utf-8"))

            # Send to KATO
            response = self.kato.post(
                f"/sessions/{session_id}/observe",
                json=observation
            )
            response.raise_for_status()

            # Acknowledge message
            self.redis.xack(
                self.stream_key,
                self.consumer_group,
                message_id
            )
            print(f"Processed message {message_id.decode('utf-8')}")

        except Exception as e:
            print(f"Error processing message: {e}")

# Usage
consumer = KatoRedisStreamConsumer(
    redis_url="redis://localhost:6379",
    kato_url="http://localhost:8000"
)
consumer.process_messages()
```

## Event Sourcing Patterns

### Event Store with KATO

```python
from typing import List, Dict
import httpx
from datetime import datetime

class KatoEventStore:
    """Event sourcing with KATO pattern learning"""

    def __init__(self, kato_url: str, event_store_db):
        self.kato = httpx.Client(base_url=kato_url)
        self.event_store = event_store_db

    def append_event(self, aggregate_id: str, event_type: str, data: dict):
        """Append event to store and learn pattern"""
        # Store event
        event = {
            "aggregate_id": aggregate_id,
            "event_type": event_type,
            "timestamp": datetime.utcnow().isoformat(),
            "data": data
        }
        self.event_store.append(event)

        # Send to KATO for pattern learning
        self.kato.post(
            f"/sessions/{aggregate_id}/observe",
            json={
                "strings": [event_type],
                "vectors": [],
                "emotives": {}
            }
        )

    def replay_events(self, aggregate_id: str):
        """Replay all events to rebuild KATO patterns"""
        events = self.event_store.get_events(aggregate_id)

        # Create new session
        session_response = self.kato.post(
            "/sessions",
            json={"node_id": aggregate_id}
        )
        session_id = session_response.json()["session_id"]

        # Replay events in order
        for event in events:
            self.kato.post(
                f"/sessions/{session_id}/observe",
                json={
                    "strings": [event["event_type"]],
                    "vectors": [],
                    "emotives": {}
                }
            )

        return session_id
```

## Asynchronous Processing

### Celery Task Queue Integration

```python
from celery import Celery
import httpx

app = Celery("kato_tasks", broker="redis://localhost:6379")

@app.task(bind=True, max_retries=3)
def process_observation_async(self, session_id: str, observation: dict):
    """Async task to process observation with KATO"""
    try:
        client = httpx.Client(base_url="http://localhost:8000")
        response = client.post(
            f"/sessions/{session_id}/observe",
            json=observation
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        # Retry with exponential backoff
        raise self.retry(exc=e, countdown=2 ** self.request.retries)

# Usage
result = process_observation_async.delay(
    session_id="user-123",
    observation={"strings": ["action"], "vectors": [], "emotives": {}}
)
```

## Real-World Examples

### Example 1: Real-Time Analytics Pipeline

```python
from kafka import KafkaConsumer, KafkaProducer
import httpx
import json

class RealTimeAnalyticsPipeline:
    """Real-time user behavior analytics with KATO"""

    def __init__(self):
        self.consumer = KafkaConsumer(
            "user-events",
            bootstrap_servers=["localhost:9092"],
            value_deserializer=lambda m: json.loads(m.decode("utf-8"))
        )
        self.producer = KafkaProducer(
            bootstrap_servers=["localhost:9092"],
            value_serializer=lambda v: json.dumps(v).encode("utf-8")
        )
        self.kato = httpx.Client(base_url="http://localhost:8000")

    def run(self):
        for message in self.consumer:
            event = message.value
            user_id = event["user_id"]

            # Send to KATO
            self.kato.post(
                f"/sessions/{user_id}/observe",
                json={
                    "strings": [event["action"], event["page"]],
                    "vectors": [],
                    "emotives": {}
                }
            )

            # Get predictions
            predictions = self.kato.get(
                f"/sessions/{user_id}/predictions"
            ).json()

            # Publish analytics
            self.producer.send(
                "user-analytics",
                value={
                    "user_id": user_id,
                    "current_action": event["action"],
                    "predicted_actions": predictions
                }
            )
```

### Example 2: IoT Sensor Pattern Detection

```python
import pika
import httpx
import json

class IoTPatternDetector:
    """Detect patterns in IoT sensor data"""

    def __init__(self, rabbitmq_url: str, kato_url: str):
        self.connection = pika.BlockingConnection(
            pika.URLParameters(rabbitmq_url)
        )
        self.channel = self.connection.channel()
        self.channel.queue_declare(queue="sensor-data")
        self.kato = httpx.Client(base_url=kato_url)

    def process_sensor_data(self, ch, method, properties, body):
        """Process sensor reading"""
        data = json.loads(body)
        sensor_id = data["sensor_id"]
        reading = data["reading"]

        # Categorize reading
        category = self.categorize_reading(reading)

        # Send to KATO
        self.kato.post(
            f"/sessions/{sensor_id}/observe",
            json={
                "strings": [category],
                "vectors": [],
                "emotives": {"value": reading / 100.0}  # Normalize
            }
        )

        # Check for anomalies via predictions
        predictions = self.kato.get(
            f"/sessions/{sensor_id}/predictions"
        ).json()

        if not predictions or category not in str(predictions):
            print(f"ANOMALY DETECTED: {sensor_id} - {category}")

        ch.basic_ack(delivery_tag=method.delivery_tag)

    def categorize_reading(self, value: float) -> str:
        """Categorize sensor reading"""
        if value < 20:
            return "low"
        elif value < 80:
            return "normal"
        else:
            return "high"
```

## Best Practices

1. **Idempotency**: Design consumers to handle duplicate messages
2. **Error Handling**: Implement retry logic with exponential backoff
3. **Dead Letter Queues**: Route failed messages to DLQ for investigation
4. **Ordering**: Use partition keys (Kafka) or routing keys (RabbitMQ) for ordering
5. **Monitoring**: Track message lag, processing time, and error rates
6. **Schema Evolution**: Version your event schemas
7. **Backpressure**: Limit consumer batch sizes to prevent overload
8. **Testing**: Test with message replay and failure scenarios

## Related Documentation

- [Microservices Integration](microservices-integration.md)
- [Session Management](session-management.md)
- [Load Balancing](load-balancing.md)

---

**Last Updated**: November 2025
**KATO Version**: 3.0+
