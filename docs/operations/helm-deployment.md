# Helm Deployment Guide

This guide is for enterprise operators installing KATO into a Kubernetes cluster while pointing it at **externally-managed** ClickHouse, Redis, and Qdrant instances.

## Prerequisites

- Kubernetes ≥ 1.24
- Helm ≥ 3.8 (OCI registry support)
- A namespace where KATO will run (`kubectl create ns kato` or use an existing one)
- Network reachability from the namespace to your ClickHouse/Redis/Qdrant endpoints
- Credentials for each backing store

KATO does **not** ship its own ClickHouse, Redis, or Qdrant. The chart is deliberately app-only so the enterprise can use existing managed services or platform-provided clusters.

## Step 1 — Pre-create credentials Secrets

The chart references Secrets you create yourself. Three Secrets are needed (names are configurable; defaults shown):

| Secret name        | Required keys                                                |
|--------------------|--------------------------------------------------------------|
| `kato-clickhouse`  | `clickhouse-user`, `clickhouse-password`                     |
| `kato-redis`       | `redis-url` (e.g., `redis://:password@host:6379/0`)          |
| `kato-qdrant`      | `qdrant-api-key`                                             |

Use whichever Secret-management workflow your platform supports.

### Option A: External Secrets Operator (preferred)

```yaml
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: kato-clickhouse
  namespace: kato
spec:
  secretStoreRef:
    name: vault-backend
    kind: ClusterSecretStore
  target:
    name: kato-clickhouse
  data:
    - secretKey: clickhouse-user
      remoteRef: { key: secret/kato/prod, property: clickhouse_user }
    - secretKey: clickhouse-password
      remoteRef: { key: secret/kato/prod, property: clickhouse_password }
```

### Option B: Sealed Secrets

```bash
echo -n 'kato_user' | kubectl create secret generic kato-clickhouse \
  --dry-run=client --from-file=clickhouse-user=/dev/stdin -o json \
  | kubeseal -o yaml > sealedsecret-clickhouse.yaml
# repeat for clickhouse-password, redis-url, qdrant-api-key
kubectl apply -f sealedsecret-clickhouse.yaml
```

### Option C: Plain `kubectl` (lab/dev)

```bash
kubectl -n kato create secret generic kato-clickhouse \
  --from-literal=clickhouse-user=kato_user \
  --from-literal=clickhouse-password='REDACTED'

kubectl -n kato create secret generic kato-redis \
  --from-literal=redis-url='redis://:REDACTED@redis.data.svc.cluster.local:6379/0'

kubectl -n kato create secret generic kato-qdrant \
  --from-literal=qdrant-api-key='REDACTED'
```

## Step 2 — Prepare your `values.yaml`

Minimum viable production values:

```yaml
# values.yaml
clickhouse:
  host: clickhouse.data.svc.cluster.local
  port: 8123              # 8443 if secure: true
  database: kato
  secure: false           # true for HTTPS to ClickHouse
  auth:
    existingSecret: kato-clickhouse

redis:
  enabled: true
  urlExistingSecret: kato-redis    # Secret holds redis://:pw@host:port/0

qdrant:
  host: qdrant.data.svc.cluster.local
  port: 6333
  grpcPort: 6334
  https: false
  auth:
    existingSecret: kato-qdrant

# OPTIONAL: TLS via custom CA bundle (for private/internal CAs)
# tls:
#   caBundle:
#     existingConfigMap: enterprise-ca-bundle    # data key: ca.crt

# OPTIONAL: Run schema bootstrap as pre-install/pre-upgrade hook
bootstrap:
  enabled: true                    # Default; set false for DBA-managed schema

replicaCount: 3
resources:
  requests: { cpu: "1", memory: 2Gi }
  limits:   { cpu: "2", memory: 4Gi }

kato:
  logLevel: INFO
  logFormat: json
  recallThreshold: 0.1            # Tune for your workload
  sessionTtl: 3600
```

See [helm-grants.md](./helm-grants.md) for the exact ClickHouse/Redis/Qdrant grants required.

## Step 3 — Install

From the OCI registry (recommended):

```bash
helm install kato oci://ghcr.io/sevakavakians/charts/kato \
  --version 0.1.0 \
  --namespace kato --create-namespace \
  -f values.yaml \
  --atomic --timeout 5m
```

From a local `.tgz` (air-gapped — see [helm-air-gapped.md](./helm-air-gapped.md)):

```bash
helm install kato ./kato-0.1.0.tgz \
  --namespace kato --create-namespace \
  -f values.yaml \
  --atomic --timeout 5m
```

## Step 4 — Verify

```bash
# Check the bootstrap Job ran
kubectl logs -n kato job/kato-bootstrap

# Check pods are healthy
kubectl get pods -n kato -l app.kubernetes.io/name=kato

# Hit /health
kubectl port-forward -n kato svc/kato 8000:8000 &
curl -f http://localhost:8000/health | jq .
curl -f http://localhost:8000/docs >/dev/null && echo "API docs reachable"

# Run helm test (curls /health and /docs from inside the cluster)
helm test kato -n kato
```

## Step 5 — Day-2 operations

### Upgrade

```bash
helm upgrade kato oci://ghcr.io/sevakavakians/charts/kato \
  --version 0.2.0 \
  --namespace kato \
  -f values.yaml \
  --atomic --timeout 5m
```

The `pre-upgrade` bootstrap hook runs first; if it fails, `--atomic` rolls back.

### Rollback

```bash
helm rollback kato <revision> -n kato --wait
```

### Scale

Set `replicaCount` (with `autoscaling.enabled=false`) or enable HPA:

```yaml
autoscaling:
  enabled: true
  minReplicas: 3
  maxReplicas: 12
  targetCPUUtilizationPercentage: 70
```

### Observability

- Prometheus text format at `/metrics-prom` — set `serviceMonitor.enabled=true` to register a `ServiceMonitor` with the Prometheus Operator.
- Custom JSON dashboard metrics at `/metrics`.
- Logs in JSON format on stdout (kubelet captures them; ship via Fluent Bit / Vector / etc.).

### Uninstall

```bash
helm uninstall kato -n kato
```

KATO data in ClickHouse, Redis, and Qdrant is **not** removed by `helm uninstall` — those are externally managed. Use the appropriate database tooling to clean up if desired.

## Troubleshooting

| Symptom                                                  | Likely cause                                                 |
|----------------------------------------------------------|--------------------------------------------------------------|
| Bootstrap Job fails with "required env var CLICKHOUSE_HOST is not set" | `clickhouse.host` not set in values, or ConfigMap rendered after Job |
| Bootstrap Job fails with "Authentication failed"          | Wrong key names in your Secret. Check `auth.userKey`/`passwordKey` |
| Bootstrap Job fails with "Code: 497 Not enough privileges" | DB user lacks DDL grants. Either grant them, or set `bootstrap.enabled=false` and apply `init.sql` as DBA |
| Pods crash-loop with `ConnectionRefusedError`            | KATO can't reach ClickHouse/Redis/Qdrant. Check `NetworkPolicy` and DNS |
| Admission rejected: "container has runAsNonRoot=true but image will run as root" | Image is older than 3.10.2. Upgrade `image.tag`. |
| `/health` returns 200 but real requests 5xx              | Backing store outage. `/health` doesn't probe DBs. Check pod logs and DB status |

For deeper troubleshooting, see [troubleshooting.md](./troubleshooting.md).
