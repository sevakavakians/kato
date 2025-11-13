# KATO Multi-Instance Integration Patterns

## Overview

This document covers integration patterns for working with multiple KATO instances in distributed systems.

For operational guidance on deploying and managing multiple KATO instances, see:
- **[Multi-Instance Deployment (Operations)](/docs/operations/multi-instance.md)** - Complete deployment and orchestration guide

## Integration Architecture

### Service Discovery Pattern

```python
import httpx
from typing import List, Dict

class MultiInstanceClient:
    """Client for managing multiple KATO instances"""

    def __init__(self, instance_urls: List[str]):
        self.instances = instance_urls
        self.clients = {url: httpx.Client(base_url=url) for url in instance_urls}

    def create_session_on_instance(
        self,
        instance_url: str,
        node_id: str
    ) -> str:
        """Create session on specific instance"""
        client = self.clients[instance_url]
        response = client.post("/sessions", json={"node_id": node_id})
        return response.json()["session_id"]

    def broadcast_observation(
        self,
        node_id: str,
        observation: dict
    ) -> Dict[str, dict]:
        """Send observation to all instances"""
        results = {}
        for url, client in self.clients.items():
            try:
                # Create session if needed
                session_response = client.post(
                    "/sessions",
                    json={"node_id": node_id}
                )
                session_id = session_response.json()["session_id"]

                # Send observation
                result = client.post(
                    f"/sessions/{session_id}/observe",
                    json=observation
                )
                results[url] = result.json()
            except Exception as e:
                results[url] = {"error": str(e)}

        return results

# Usage
client = MultiInstanceClient([
    "http://kato-1:8000",
    "http://kato-2:8000",
    "http://kato-3:8000"
])
```

### Partitioned Data Pattern

Partition users/data across instances for horizontal scaling.

```python
import hashlib

class PartitionedKatoClient:
    """Route users to specific instances via consistent hashing"""

    def __init__(self, instances: List[str]):
        self.instances = sorted(instances)  # Consistent ordering

    def get_instance_for_user(self, user_id: str) -> str:
        """Determine instance for user via hash"""
        hash_value = int(hashlib.md5(user_id.encode()).hexdigest(), 16)
        index = hash_value % len(self.instances)
        return self.instances[index]

    def create_session(self, user_id: str) -> tuple[str, str]:
        """Create session on appropriate instance"""
        instance_url = self.get_instance_for_user(user_id)
        client = httpx.Client(base_url=instance_url)

        response = client.post("/sessions", json={"node_id": user_id})
        session_id = response.json()["session_id"]

        return instance_url, session_id

# Usage
partitioned = PartitionedKatoClient([
    "http://kato-1:8000",
    "http://kato-2:8000",
    "http://kato-3:8000"
])

instance, session = partitioned.create_session("user-123")
print(f"User routed to: {instance}")
```

### Federated Learning Pattern

Aggregate patterns learned across multiple instances.

```python
class FederatedKatoManager:
    """Coordinate learning across multiple KATO instances"""

    def __init__(self, instances: List[str]):
        self.instances = instances

    def get_aggregated_predictions(
        self,
        node_id: str
    ) -> List[Dict]:
        """Get predictions from all instances and aggregate"""
        all_predictions = []

        for instance_url in self.instances:
            try:
                client = httpx.Client(base_url=instance_url)

                # Create session
                session_response = client.post(
                    "/sessions",
                    json={"node_id": node_id}
                )
                session_id = session_response.json()["session_id"]

                # Get predictions
                predictions = client.get(
                    f"/sessions/{session_id}/predictions"
                ).json()

                all_predictions.extend(predictions)
            except Exception as e:
                print(f"Failed to get predictions from {instance_url}: {e}")

        # Simple aggregation by frequency
        prediction_counts = {}
        for pred in all_predictions:
            if pred.get("future"):
                future_key = str(pred["future"])
                prediction_counts[future_key] = prediction_counts.get(future_key, 0) + 1

        # Return most common predictions
        sorted_predictions = sorted(
            prediction_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )

        return [{"future": eval(pred), "count": count} for pred, count in sorted_predictions[:10]]
```

## Coordination Patterns

### Master-Worker Pattern

Coordinate multiple worker instances from master.

```python
class MasterCoordinator:
    """Coordinate multiple KATO worker instances"""

    def __init__(self, worker_urls: List[str]):
        self.workers = worker_urls
        self.next_worker = 0

    def get_next_worker(self) -> str:
        """Round-robin worker selection"""
        worker = self.workers[self.next_worker]
        self.next_worker = (self.next_worker + 1) % len(self.workers)
        return worker

    def distribute_observations(
        self,
        observations: List[Dict]
    ) -> Dict[str, List]:
        """Distribute observations across workers"""
        worker_assignments = {worker: [] for worker in self.workers}

        for obs in observations:
            worker = self.get_next_worker()
            worker_assignments[worker].append(obs)

        # Send to each worker
        results = {}
        for worker_url, worker_obs in worker_assignments.items():
            client = httpx.Client(base_url=worker_url)
            worker_results = []

            for obs in worker_obs:
                try:
                    response = client.post(
                        f"/sessions/{obs['session_id']}/observe",
                        json=obs["observation"]
                    )
                    worker_results.append(response.json())
                except Exception as e:
                    worker_results.append({"error": str(e)})

            results[worker_url] = worker_results

        return results
```

## Best Practices

1. **Consistent Hashing**: Use for user-to-instance routing
2. **Service Discovery**: Implement dynamic instance discovery
3. **Load Balancing**: Distribute traffic evenly (see [load-balancing.md](load-balancing.md))
4. **Health Checks**: Monitor all instances continuously
5. **Failover**: Route to healthy instances when failures occur
6. **Session Affinity**: Keep user sessions on same instance when possible
7. **Data Locality**: Minimize cross-instance data transfer
8. **Monitoring**: Track metrics per instance

## Related Documentation

- **[Multi-Instance Deployment (Operations)](/docs/operations/multi-instance.md)** - Deployment guide
- [Load Balancing](load-balancing.md) - Load balancing strategies
- [Session Management](session-management.md) - Session lifecycle
- [Database Isolation](database-isolation.md) - Data partitioning
- [Microservices Integration](microservices-integration.md) - Service patterns

---

**Last Updated**: November 2025
**KATO Version**: 3.0+
