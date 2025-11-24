# Kubernetes Deployment Guide

Complete guide to deploying KATO on Kubernetes for production environments.

## Overview

KATO can be deployed on Kubernetes for enterprise-scale deployments with features like:
- Automatic scaling and self-healing
- Rolling updates with zero downtime
- Resource management and isolation
- Service discovery and load balancing
- Persistent storage management

## Prerequisites

- Kubernetes cluster 1.24+ (EKS, GKE, AKS, or self-managed)
- kubectl CLI configured
- Helm 3.0+ (optional, for chart deployment)
- 16GB+ available cluster memory
- 50GB+ persistent storage
- Container registry access (Docker Hub, GHCR, etc.)

## Architecture

```
┌─────────────────────────────────────────┐
│         Ingress Controller              │
│    (nginx/traefik + TLS termination)    │
└──────────────┬──────────────────────────┘
               │
┌──────────────┴──────────────────────────┐
│        KATO Service (ClusterIP)         │
│         Load Balancer for Pods          │
└──────────────┬──────────────────────────┘
               │
   ┌───────────┴───────────┐
   │                       │
┌──▼────┐  ┌─────────┐  ┌─▼─────┐
│ KATO  │  │  KATO   │  │ KATO  │
│ Pod-1 │  │  Pod-2  │  │ Pod-3 │
└───┬───┘  └────┬────┘  └───┬───┘
    │           │            │
    └───────────┴────────────┘
                │
    ┌───────────┴───────────────────┐
    │                               │
┌───▼─────────┐  ┌──────────┐  ┌──▼─────┐
│ ClickHouse  │  │  Qdrant  │  │ Redis  │
│ StatefulSet │  │StatefulSet │StatefulSet
└─────────────┘  └──────────┘  └────────┘
```

## Quick Start with Manifests

### 1. Namespace Setup

```yaml
# namespace.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: kato
  labels:
    name: kato
    environment: production
```

```bash
kubectl apply -f namespace.yaml
```

### 2. ConfigMap

```yaml
# configmap.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: kato-config
  namespace: kato
data:
  ENVIRONMENT: "production"
  LOG_LEVEL: "INFO"
  LOG_FORMAT: "json"
  MAX_PATTERN_LENGTH: "10"
  RECALL_THRESHOLD: "0.3"
  STM_MODE: "CLEAR"
  SESSION_TTL: "7200"
  SESSION_AUTO_EXTEND: "true"
  KATO_USE_FAST_MATCHING: "true"
  KATO_USE_INDEXING: "true"
  # Database hosts use service DNS
  CLICKHOUSE_HOST: "kato-clickhouse"
  CLICKHOUSE_PORT: "8123"
  CLICKHOUSE_DB: "kato"
  QDRANT_HOST: "qdrant-kb"
  REDIS_URL: "redis://redis-kb:6379/0"
```

```bash
kubectl apply -f configmap.yaml
```

### 3. Secrets

```yaml
# secrets.yaml
apiVersion: v1
kind: Secret
metadata:
  name: kato-secrets
  namespace: kato
type: Opaque
stringData:
  CLICKHOUSE_USER: "kato_user"
  CLICKHOUSE_PASSWORD: "secure_password_here"
  API_KEY: "your_api_key_here"
```

```bash
kubectl apply -f secrets.yaml
```

### 4. ClickHouse StatefulSet

```yaml
# clickhouse-statefulset.yaml
apiVersion: v1
kind: Service
metadata:
  name: kato-clickhouse
  namespace: kato
spec:
  ports:
  - port: 8123
    targetPort: 8123
    name: http
  - port: 9000
    targetPort: 9000
    name: native
  clusterIP: None
  selector:
    app: kato-clickhouse
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: kato-clickhouse
  namespace: kato
spec:
  serviceName: kato-clickhouse
  replicas: 1
  selector:
    matchLabels:
      app: kato-clickhouse
  template:
    metadata:
      labels:
        app: kato-clickhouse
    spec:
      containers:
      - name: clickhouse
        image: clickhouse/clickhouse-server:latest
        ports:
        - containerPort: 8123
          name: http
        - containerPort: 9000
          name: native
        env:
        - name: CLICKHOUSE_DB
          value: "kato"
        - name: CLICKHOUSE_USER
          valueFrom:
            secretKeyRef:
              name: kato-secrets
              key: CLICKHOUSE_USER
        - name: CLICKHOUSE_PASSWORD
          valueFrom:
            secretKeyRef:
              name: kato-secrets
              key: CLICKHOUSE_PASSWORD
        resources:
          requests:
            memory: "2Gi"
            cpu: "1"
          limits:
            memory: "4Gi"
            cpu: "2"
        volumeMounts:
        - name: clickhouse-data
          mountPath: /var/lib/clickhouse
  volumeClaimTemplates:
  - metadata:
      name: clickhouse-data
    spec:
      accessModes: [ "ReadWriteOnce" ]
      resources:
        requests:
          storage: 20Gi
```

```bash
kubectl apply -f clickhouse-statefulset.yaml
```

### 5. Qdrant StatefulSet

```yaml
# qdrant-statefulset.yaml
apiVersion: v1
kind: Service
metadata:
  name: qdrant-kb
  namespace: kato
spec:
  ports:
  - port: 6333
    targetPort: 6333
    name: http
  - port: 6334
    targetPort: 6334
    name: grpc
  clusterIP: None
  selector:
    app: qdrant-kb
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: qdrant-kb
  namespace: kato
spec:
  serviceName: qdrant-kb
  replicas: 1
  selector:
    matchLabels:
      app: qdrant-kb
  template:
    metadata:
      labels:
        app: qdrant-kb
    spec:
      containers:
      - name: qdrant
        image: qdrant/qdrant:latest
        ports:
        - containerPort: 6333
          name: http
        - containerPort: 6334
          name: grpc
        resources:
          requests:
            memory: "1Gi"
            cpu: "500m"
          limits:
            memory: "2Gi"
            cpu: "1"
        volumeMounts:
        - name: qdrant-data
          mountPath: /qdrant/storage
  volumeClaimTemplates:
  - metadata:
      name: qdrant-data
    spec:
      accessModes: [ "ReadWriteOnce" ]
      resources:
        requests:
          storage: 10Gi
```

```bash
kubectl apply -f qdrant-statefulset.yaml
```

### 6. Redis StatefulSet

```yaml
# redis-statefulset.yaml
apiVersion: v1
kind: Service
metadata:
  name: redis-kb
  namespace: kato
spec:
  ports:
  - port: 6379
    targetPort: 6379
  clusterIP: None
  selector:
    app: redis-kb
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: redis-kb
  namespace: kato
spec:
  serviceName: redis-kb
  replicas: 1
  selector:
    matchLabels:
      app: redis-kb
  template:
    metadata:
      labels:
        app: redis-kb
    spec:
      containers:
      - name: redis
        image: redis:7-alpine
        ports:
        - containerPort: 6379
        command: ["redis-server", "--appendonly", "yes"]
        resources:
          requests:
            memory: "512Mi"
            cpu: "250m"
          limits:
            memory: "1Gi"
            cpu: "500m"
        volumeMounts:
        - name: redis-data
          mountPath: /data
  volumeClaimTemplates:
  - metadata:
      name: redis-data
    spec:
      accessModes: [ "ReadWriteOnce" ]
      resources:
        requests:
          storage: 5Gi
```

```bash
kubectl apply -f redis-statefulset.yaml
```

### 7. KATO Deployment

```yaml
# kato-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: kato
  namespace: kato
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: kato
  template:
    metadata:
      labels:
        app: kato
        version: "3.0"
    spec:
      containers:
      - name: kato
        image: ghcr.io/your-org/kato:latest
        ports:
        - containerPort: 8000
          name: http
        envFrom:
        - configMapRef:
            name: kato-config
        - secretRef:
            name: kato-secrets
        env:
        - name: PROCESSOR_ID
          valueFrom:
            fieldRef:
              fieldPath: metadata.name
        resources:
          requests:
            memory: "2Gi"
            cpu: "1"
          limits:
            memory: "4Gi"
            cpu: "2"
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
          timeoutSeconds: 5
          failureThreshold: 3
        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 5
          timeoutSeconds: 3
          failureThreshold: 3
---
apiVersion: v1
kind: Service
metadata:
  name: kato
  namespace: kato
spec:
  selector:
    app: kato
  ports:
  - port: 80
    targetPort: 8000
    protocol: TCP
  type: ClusterIP
```

```bash
kubectl apply -f kato-deployment.yaml
```

### 8. Ingress

```yaml
# ingress.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: kato-ingress
  namespace: kato
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
    nginx.ingress.kubernetes.io/proxy-body-size: "10m"
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
spec:
  ingressClassName: nginx
  tls:
  - hosts:
    - kato.yourdomain.com
    secretName: kato-tls
  rules:
  - host: kato.yourdomain.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: kato
            port:
              number: 80
```

```bash
kubectl apply -f ingress.yaml
```

## Helm Chart Deployment

### Chart Structure

```
kato-chart/
├── Chart.yaml
├── values.yaml
├── templates/
│   ├── namespace.yaml
│   ├── configmap.yaml
│   ├── secrets.yaml
│   ├── clickhouse.yaml
│   ├── qdrant.yaml
│   ├── redis.yaml
│   ├── deployment.yaml
│   ├── service.yaml
│   ├── ingress.yaml
│   └── hpa.yaml
```

### Chart.yaml

```yaml
apiVersion: v2
name: kato
description: KATO - Knowledge Abstraction for Traceable Outcomes
type: application
version: 3.0.0
appVersion: "3.0"
maintainers:
  - name: KATO Team
    email: team@kato.ai
```

### values.yaml

```yaml
# KATO Configuration
kato:
  replicaCount: 3
  image:
    repository: ghcr.io/your-org/kato
    tag: "latest"
    pullPolicy: IfNotPresent

  resources:
    requests:
      memory: "2Gi"
      cpu: "1"
    limits:
      memory: "4Gi"
      cpu: "2"

  config:
    environment: production
    logLevel: INFO
    logFormat: json
    maxPatternLength: 10
    recallThreshold: 0.3
    sessionTTL: 7200

# ClickHouse Configuration
clickhouse:
  enabled: true
  replicas: 1
  persistence:
    size: 20Gi
  resources:
    requests:
      memory: "2Gi"
      cpu: "1"
    limits:
      memory: "4Gi"
      cpu: "2"

# Qdrant Configuration
qdrant:
  enabled: true
  replicas: 1
  persistence:
    size: 10Gi
  resources:
    requests:
      memory: "1Gi"
      cpu: "500m"
    limits:
      memory: "2Gi"
      cpu: "1"

# Redis Configuration
redis:
  enabled: true
  replicas: 1
  persistence:
    size: 5Gi
  resources:
    requests:
      memory: "512Mi"
      cpu: "250m"
    limits:
      memory: "1Gi"
      cpu: "500m"

# Ingress Configuration
ingress:
  enabled: true
  className: nginx
  host: kato.yourdomain.com
  tls:
    enabled: true
    secretName: kato-tls

# Autoscaling
autoscaling:
  enabled: true
  minReplicas: 3
  maxReplicas: 10
  targetCPUUtilizationPercentage: 70
  targetMemoryUtilizationPercentage: 80
```

### Deploy with Helm

```bash
# Add KATO Helm repository (if published)
helm repo add kato https://charts.kato.ai
helm repo update

# Install KATO
helm install kato kato/kato \
  --namespace kato \
  --create-namespace \
  --values values.yaml

# Or install from local chart
helm install kato ./kato-chart \
  --namespace kato \
  --create-namespace \
  --values values.yaml

# Upgrade existing deployment
helm upgrade kato kato/kato \
  --namespace kato \
  --values values.yaml

# Rollback if needed
helm rollback kato 1 --namespace kato
```

## Horizontal Pod Autoscaler

```yaml
# hpa.yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: kato-hpa
  namespace: kato
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
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
      - type: Percent
        value: 50
        periodSeconds: 60
    scaleUp:
      stabilizationWindowSeconds: 60
      policies:
      - type: Percent
        value: 100
        periodSeconds: 30
```

```bash
kubectl apply -f hpa.yaml
```

## Resource Quotas

```yaml
# resource-quota.yaml
apiVersion: v1
kind: ResourceQuota
metadata:
  name: kato-quota
  namespace: kato
spec:
  hard:
    requests.cpu: "20"
    requests.memory: "40Gi"
    limits.cpu: "40"
    limits.memory: "80Gi"
    persistentvolumeclaims: "10"
```

## Network Policies

```yaml
# network-policy.yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: kato-network-policy
  namespace: kato
spec:
  podSelector:
    matchLabels:
      app: kato
  policyTypes:
  - Ingress
  - Egress
  ingress:
  - from:
    - namespaceSelector:
        matchLabels:
          name: ingress-nginx
    ports:
    - protocol: TCP
      port: 8000
  egress:
  - to:
    - podSelector:
        matchLabels:
          app: kato-clickhouse
    ports:
    - protocol: TCP
      port: 8123
    - protocol: TCP
      port: 9000
  - to:
    - podSelector:
        matchLabels:
          app: qdrant-kb
    ports:
    - protocol: TCP
      port: 6333
    - protocol: TCP
      port: 6334
  - to:
    - podSelector:
        matchLabels:
          app: redis-kb
    ports:
    - protocol: TCP
      port: 6379
```

## Persistent Volume Claims

```yaml
# pvc.yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: kato-shared-storage
  namespace: kato
spec:
  accessModes:
    - ReadWriteMany
  storageClassName: efs-sc
  resources:
    requests:
      storage: 100Gi
```

## Monitoring and Observability

### ServiceMonitor for Prometheus

```yaml
# servicemonitor.yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: kato-metrics
  namespace: kato
spec:
  selector:
    matchLabels:
      app: kato
  endpoints:
  - port: http
    path: /metrics
    interval: 30s
```

## Deployment Commands

```bash
# Apply all manifests
kubectl apply -f namespace.yaml
kubectl apply -f configmap.yaml
kubectl apply -f secrets.yaml
kubectl apply -f clickhouse-statefulset.yaml
kubectl apply -f qdrant-statefulset.yaml
kubectl apply -f redis-statefulset.yaml
kubectl apply -f kato-deployment.yaml
kubectl apply -f ingress.yaml
kubectl apply -f hpa.yaml

# Check deployment status
kubectl get all -n kato
kubectl get pods -n kato -w

# View logs
kubectl logs -f deployment/kato -n kato

# Scale manually
kubectl scale deployment/kato --replicas=5 -n kato

# Rolling restart
kubectl rollout restart deployment/kato -n kato

# Check rollout status
kubectl rollout status deployment/kato -n kato

# Rollback deployment
kubectl rollout undo deployment/kato -n kato
```

## Backup and Restore

### Backup Script

```bash
#!/bin/bash
# backup-kato.sh

NAMESPACE="kato"
BACKUP_DIR="/backups/kato-$(date +%Y%m%d)"
mkdir -p $BACKUP_DIR

# Backup ClickHouse
kubectl exec -n $NAMESPACE statefulset/kato-clickhouse -- \
  clickhouse-client --query "BACKUP DATABASE kato TO Disk('backups', 'backup.zip')"

kubectl cp $NAMESPACE/kato-clickhouse-0:/var/lib/clickhouse/backups/backup.zip \
  $BACKUP_DIR/clickhouse-backup.zip

# Backup Qdrant
kubectl exec -n $NAMESPACE statefulset/qdrant-kb -- \
  tar czf /tmp/qdrant-backup.tar.gz /qdrant/storage

kubectl cp $NAMESPACE/qdrant-kb-0:/tmp/qdrant-backup.tar.gz \
  $BACKUP_DIR/qdrant-backup.tar.gz

# Backup Redis
kubectl exec -n $NAMESPACE statefulset/redis-kb -- \
  redis-cli --rdb /tmp/redis-backup.rdb

kubectl cp $NAMESPACE/redis-kb-0:/tmp/redis-backup.rdb \
  $BACKUP_DIR/redis-backup.rdb

echo "Backup completed: $BACKUP_DIR"
```

## Troubleshooting

### Pod Not Starting

```bash
# Describe pod
kubectl describe pod <pod-name> -n kato

# Check events
kubectl get events -n kato --sort-by='.lastTimestamp'

# Check logs
kubectl logs <pod-name> -n kato --previous
```

### Database Connection Issues

```bash
# Test ClickHouse connectivity
kubectl exec -it deployment/kato -n kato -- \
  curl http://kato-clickhouse:8123/?query=SELECT%201

# Test Qdrant connectivity
kubectl exec -it deployment/kato -n kato -- \
  curl http://qdrant-kb:6333/

# Test Redis connectivity
kubectl exec -it deployment/kato -n kato -- \
  redis-cli -h redis-kb ping
```

### Performance Issues

```bash
# Check resource usage
kubectl top pods -n kato
kubectl top nodes

# Check HPA status
kubectl get hpa -n kato

# View metrics
kubectl describe hpa kato-hpa -n kato
```

## Production Best Practices

1. **Use StatefulSets for databases** - Stable network identity and persistent storage
2. **Enable Pod Disruption Budgets** - Maintain availability during maintenance
3. **Configure resource limits** - Prevent resource starvation
4. **Use namespaces** - Logical isolation and resource quotas
5. **Enable network policies** - Restrict traffic flow
6. **Implement health checks** - Automatic recovery from failures
7. **Use secrets management** - Never commit secrets to git
8. **Configure autoscaling** - Handle variable load automatically
9. **Enable monitoring** - Prometheus/Grafana for observability
10. **Regular backups** - Automated backup strategy

## Related Documentation

- [Docker Deployment](docker-deployment.md)
- [Production Checklist](production-checklist.md)
- [Security Configuration](security-configuration.md)
- [Monitoring](monitoring.md)
- [Scaling](scaling.md)

---

**Last Updated**: November 2025
**KATO Version**: 3.0+
