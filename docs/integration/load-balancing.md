# KATO Load Balancing Guide

## Table of Contents
1. [Overview](#overview)
2. [Load Balancing Strategies](#load-balancing-strategies)
3. [Sticky Sessions](#sticky-sessions)
4. [Health Checks](#health-checks)
5. [Failover Strategies](#failover-strategies)
6. [Kubernetes Load Balancing](#kubernetes-load-balancing)
7. [Real-World Examples](#real-world-examples)

## Overview

KATO supports horizontal scaling with multiple instances behind a load balancer. This guide covers load balancing strategies, sticky session management, health checks, and failover configurations.

### Key Considerations

- **Session Affinity**: Same session_id should route to same instance
- **Health Monitoring**: Detect unhealthy instances quickly
- **Failover**: Handle instance failures gracefully
- **Distribution**: Balance load evenly across instances
- **State**: Sessions are Redis-backed for fault tolerance

## Load Balancing Strategies

### Round Robin

Simplest strategy - distribute requests evenly across instances.

**Nginx Configuration**:
```nginx
upstream kato_backend {
    server kato-1:8000;
    server kato-2:8000;
    server kato-3:8000;
}

server {
    listen 80;
    server_name kato.example.com;

    location / {
        proxy_pass http://kato_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;

        # Timeouts
        proxy_connect_timeout 10s;
        proxy_send_timeout 30s;
        proxy_read_timeout 30s;
    }
}
```

### Least Connections

Route to instance with fewest active connections.

**Nginx Configuration**:
```nginx
upstream kato_backend {
    least_conn;
    server kato-1:8000;
    server kato-2:8000;
    server kato-3:8000;
}
```

### IP Hash

Routes client to same instance based on IP address.

**Nginx Configuration**:
```nginx
upstream kato_backend {
    ip_hash;
    server kato-1:8000;
    server kato-2:8000;
    server kato-3:8000;
}
```

### Weighted Round Robin

Distribute based on instance capacity.

**Nginx Configuration**:
```nginx
upstream kato_backend {
    server kato-1:8000 weight=3;  # High capacity
    server kato-2:8000 weight=2;  # Medium capacity
    server kato-3:8000 weight=1;  # Low capacity
}
```

## Sticky Sessions

### Session-Based Affinity with Nginx

Route requests by session_id to maintain affinity.

**Nginx Configuration**:
```nginx
upstream kato_backend {
    hash $session_id consistent;
    server kato-1:8000;
    server kato-2:8000;
    server kato-3:8000;
}

map $request_uri $session_id {
    ~^/sessions/(?<sid>[^/]+) $sid;
    default "";
}

server {
    listen 80;

    location / {
        proxy_pass http://kato_backend;
        proxy_set_header X-Session-ID $session_id;
    }
}
```

### Cookie-Based Sticky Sessions

**Nginx Configuration**:
```nginx
upstream kato_backend {
    server kato-1:8000;
    server kato-2:8000;
    server kato-3:8000;
}

server {
    listen 80;

    location / {
        proxy_pass http://kato_backend;

        # Enable sticky sessions
        sticky cookie kato_route expires=1h domain=.example.com path=/;
    }
}
```

### HAProxy Sticky Sessions

```haproxy
frontend kato_front
    bind *:80
    default_backend kato_servers

backend kato_servers
    balance roundrobin
    cookie SERVERID insert indirect nocache
    server kato1 kato-1:8000 check cookie kato1
    server kato2 kato-2:8000 check cookie kato2
    server kato3 kato-3:8000 check cookie kato3
```

## Health Checks

### Passive Health Checks

Monitor responses and mark unhealthy instances.

**Nginx Configuration**:
```nginx
upstream kato_backend {
    server kato-1:8000 max_fails=3 fail_timeout=30s;
    server kato-2:8000 max_fails=3 fail_timeout=30s;
    server kato-3:8000 max_fails=3 fail_timeout=30s;
}
```

### Active Health Checks

Proactively check instance health.

**Nginx Plus Configuration**:
```nginx
upstream kato_backend {
    zone kato 64k;
    server kato-1:8000;
    server kato-2:8000;
    server kato-3:8000;
}

server {
    listen 80;

    location / {
        proxy_pass http://kato_backend;
        health_check interval=10s fails=3 passes=2 uri=/health;
    }
}
```

### HAProxy Health Checks

```haproxy
backend kato_servers
    balance roundrobin
    option httpchk GET /health
    http-check expect status 200

    server kato1 kato-1:8000 check inter 5s rise 2 fall 3
    server kato2 kato-2:8000 check inter 5s rise 2 fall 3
    server kato3 kato-3:8000 check inter 5s rise 2 fall 3
```

### Custom Health Check Script

```python
import httpx
import time
from typing import List

class HealthChecker:
    """Monitor KATO instance health"""

    def __init__(self, instances: List[str]):
        self.instances = instances
        self.health_status = {url: True for url in instances}

    def check_instance(self, url: str) -> bool:
        """Check single instance health"""
        try:
            response = httpx.get(f"{url}/health", timeout=5.0)
            return response.status_code == 200
        except:
            return False

    def run_checks(self):
        """Check all instances"""
        for url in self.instances:
            is_healthy = self.check_instance(url)
            self.health_status[url] = is_healthy
            print(f"{url}: {'healthy' if is_healthy else 'unhealthy'}")

    def get_healthy_instances(self) -> List[str]:
        """Get list of healthy instances"""
        return [url for url, healthy in self.health_status.items() if healthy]

# Usage
checker = HealthChecker([
    "http://kato-1:8000",
    "http://kato-2:8000",
    "http://kato-3:8000"
])
checker.run_checks()
healthy = checker.get_healthy_instances()
```

## Failover Strategies

### Automatic Failover with Backup Servers

**Nginx Configuration**:
```nginx
upstream kato_backend {
    server kato-1:8000;
    server kato-2:8000;
    server kato-3:8000 backup;  # Only used if primary servers fail
}
```

### Client-Side Failover

```python
import httpx
from typing import List, Optional

class FailoverClient:
    """KATO client with automatic failover"""

    def __init__(self, instances: List[str]):
        self.instances = instances
        self.current_index = 0

    def _get_next_instance(self) -> str:
        """Get next instance in rotation"""
        instance = self.instances[self.current_index]
        self.current_index = (self.current_index + 1) % len(self.instances)
        return instance

    def request_with_failover(
        self,
        method: str,
        path: str,
        **kwargs
    ) -> httpx.Response:
        """Make request with automatic failover"""
        attempts = len(self.instances)
        last_error = None

        for _ in range(attempts):
            instance = self._get_next_instance()
            try:
                response = httpx.request(
                    method,
                    f"{instance}{path}",
                    timeout=10.0,
                    **kwargs
                )
                response.raise_for_status()
                return response
            except Exception as e:
                last_error = e
                print(f"Failed to connect to {instance}: {e}")
                continue

        raise Exception(f"All instances failed: {last_error}")

    def create_session(self, node_id: str) -> str:
        """Create session with failover"""
        response = self.request_with_failover(
            "POST",
            "/sessions",
            json={"node_id": node_id}
        )
        return response.json()["session_id"]

# Usage
client = FailoverClient([
    "http://kato-1:8000",
    "http://kato-2:8000",
    "http://kato-3:8000"
])
session_id = client.create_session("user-123")
```

### Circuit Breaker Pattern

```python
from pybreaker import CircuitBreaker
import httpx

class CircuitBreakerLoadBalancer:
    """Load balancer with circuit breakers per instance"""

    def __init__(self, instances: List[str]):
        self.instances = instances
        self.breakers = {
            url: CircuitBreaker(fail_max=5, timeout_duration=60)
            for url in instances
        }
        self.current_index = 0

    def get_available_instance(self) -> Optional[str]:
        """Get next available instance (not open circuit)"""
        for _ in range(len(self.instances)):
            instance = self.instances[self.current_index]
            self.current_index = (self.current_index + 1) % len(self.instances)

            if self.breakers[instance].current_state == "closed":
                return instance

        return None  # All circuits open

    def request(self, method: str, path: str, **kwargs):
        """Make request through circuit breaker"""
        instance = self.get_available_instance()
        if not instance:
            raise Exception("No available instances")

        breaker = self.breakers[instance]

        @breaker
        def make_request():
            return httpx.request(method, f"{instance}{path}", **kwargs)

        return make_request()
```

## Kubernetes Load Balancing

### Service Configuration

```yaml
apiVersion: v1
kind: Service
metadata:
  name: kato
spec:
  selector:
    app: kato
  ports:
  - port: 8000
    targetPort: 8000
    name: http
  type: ClusterIP
  sessionAffinity: ClientIP  # Sticky sessions based on client IP
  sessionAffinityConfig:
    clientIP:
      timeoutSeconds: 3600

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
  template:
    metadata:
      labels:
        app: kato
    spec:
      containers:
      - name: kato
        image: ghcr.io/sevakavakians/kato:3.0.0
        ports:
        - containerPort: 8000
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

### Ingress with Session Affinity

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: kato
  annotations:
    nginx.ingress.kubernetes.io/affinity: "cookie"
    nginx.ingress.kubernetes.io/session-cookie-name: "kato-session"
    nginx.ingress.kubernetes.io/session-cookie-expires: "3600"
    nginx.ingress.kubernetes.io/session-cookie-max-age: "3600"
spec:
  rules:
  - host: kato.example.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: kato
            port:
              number: 8000
```

### Horizontal Pod Autoscaler

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: kato-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: kato
  minReplicas: 3
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
```

## Real-World Examples

### Example 1: Global Load Balancer with GeoDNS

```python
class GeoLoadBalancer:
    """Route to nearest KATO cluster"""

    def __init__(self):
        self.regions = {
            "us-east": "http://kato-us-east.example.com",
            "us-west": "http://kato-us-west.example.com",
            "eu-west": "http://kato-eu-west.example.com",
            "ap-south": "http://kato-ap-south.example.com"
        }

    def get_instance_for_region(self, region: str) -> str:
        """Get KATO instance for region"""
        return self.regions.get(region, self.regions["us-east"])

    def create_session(self, node_id: str, region: str) -> str:
        """Create session in regional instance"""
        instance = self.get_instance_for_region(region)
        response = httpx.post(
            f"{instance}/sessions",
            json={"node_id": node_id}
        )
        return response.json()["session_id"]
```

### Example 2: Weighted Load Balancing Based on Metrics

```python
import random
from typing import Dict

class MetricsBasedLoadBalancer:
    """Load balance based on instance metrics"""

    def __init__(self, instances: List[str]):
        self.instances = instances
        self.metrics = {url: {"load": 0.0, "latency": 0.0} for url in instances}

    def update_metrics(self, url: str, load: float, latency: float):
        """Update instance metrics"""
        self.metrics[url] = {"load": load, "latency": latency}

    def get_weighted_instance(self) -> str:
        """Select instance based on inverse load"""
        # Calculate weights (inverse of load)
        weights = {}
        for url, metrics in self.metrics.items():
            # Lower load = higher weight
            weight = 1.0 / (metrics["load"] + 0.1)  # Avoid division by zero
            weights[url] = weight

        # Weighted random selection
        total = sum(weights.values())
        rand = random.uniform(0, total)
        cumulative = 0.0

        for url, weight in weights.items():
            cumulative += weight
            if rand <= cumulative:
                return url

        return self.instances[0]  # Fallback
```

## Best Practices

1. **Session Affinity**: Use consistent hashing for session routing
2. **Health Checks**: Implement both active and passive health monitoring
3. **Gradual Rollout**: Use weighted routing for canary deployments
4. **Monitoring**: Track request distribution and instance health
5. **Timeouts**: Set appropriate timeouts for health checks
6. **Backup Servers**: Configure backup instances for failover
7. **Circuit Breakers**: Prevent cascading failures
8. **Graceful Shutdown**: Drain connections before stopping instances

## Related Documentation

- [Multi-Instance Deployment](multi-instance.md)
- [Session Management](session-management.md)
- [Kubernetes Deployment](/docs/operations/kubernetes-deployment.md)
- [Monitoring](/docs/operations/monitoring.md)

---

**Last Updated**: November 2025
**KATO Version**: 3.0+
