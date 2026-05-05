# kato

KATO (Knowledge Abstraction for Traceable Outcomes) — deterministic memory and prediction system. This chart installs the KATO API service only. **ClickHouse, Redis, and Qdrant must be provided externally** and configured via values; the chart never bundles them.

| Field        | Value                                        |
|--------------|----------------------------------------------|
| Type         | `application`                                |
| Chart version | `0.1.0`                                     |
| App version  | `3.10.1`                                     |
| Source       | <https://github.com/intelligent-artifacts/kato> |
| Container    | `ghcr.io/sevakavakians/kato`                 |

## TL;DR

```bash
# 1. Pre-create Secrets via your normal pipeline (External Secrets Operator,
#    Vault CSI, sealed-secrets). Example with raw kubectl:
kubectl create secret generic kato-clickhouse \
  --from-literal=clickhouse-user=kato_user \
  --from-literal=clickhouse-password='changeme'
kubectl create secret generic kato-redis \
  --from-literal=redis-url='redis://:pw@redis.data.svc:6379/0'
kubectl create secret generic kato-qdrant \
  --from-literal=qdrant-api-key='qdrant-token'

# 2. Install the chart from the OCI registry
helm install kato oci://ghcr.io/sevakavakians/charts/kato --version 0.1.0 \
  --set clickhouse.host=clickhouse.data.svc.cluster.local \
  --set clickhouse.auth.existingSecret=kato-clickhouse \
  --set redis.urlExistingSecret=kato-redis \
  --set qdrant.host=qdrant.data.svc.cluster.local \
  --set qdrant.auth.existingSecret=kato-qdrant \
  --atomic --timeout 5m
```

## Prerequisites

- Kubernetes ≥ 1.24
- Helm ≥ 3.8 (OCI support)
- ClickHouse, Redis, and Qdrant reachable from your cluster
- Secrets containing credentials pre-created in the same namespace as the release (or referenced via `*.auth.existingSecret`)

## What this chart installs

- A `Deployment` running the KATO API on port 8000 (multi-worker uvicorn, `KATO_WORKERS=4` by default)
- A `Service` (ClusterIP, no session affinity — KATO is stateless)
- A `ConfigMap` for non-secret env vars
- A `ServiceAccount` (so the enterprise can attach IRSA / Workload Identity / Azure WI annotations)
- An optional pre-install/pre-upgrade `Job` that creates the ClickHouse schema and verifies Redis/Qdrant connectivity (`bootstrap.enabled=true`)
- Optional: `Ingress`, `HorizontalPodAutoscaler`, `PodDisruptionBudget`, `NetworkPolicy`, `ServiceMonitor`

## Choosing a connection mode

| Path                     | When to use                                             |
|--------------------------|---------------------------------------------------------|
| `clickhouse.auth.existingSecret` | Production. Always.                            |
| `redis.urlExistingSecret`  | Production. Stores the full `REDIS_URL` (incl. password) in a Secret. |
| `redis.host` + `redis.auth.existingSecret` | Fallback when your secret pipeline can't generate a full URL. |
| `qdrant.auth.existingSecret` | Production whenever Qdrant has API-key auth (recommended). |
| `secrets.create=true` + inline credentials | Evaluation only. Renders a Secret from values. |

## TLS to backing stores

If your ClickHouse/Redis/Qdrant use private CAs, mount the CA bundle:

```yaml
tls:
  caBundle:
    existingConfigMap: enterprise-ca-bundle  # key: ca.crt
```

The chart mounts it at `/etc/ssl/kato-ca/` and exports `SSL_CERT_FILE` and `REQUESTS_CA_BUNDLE` so both stdlib SSL and `requests`-based connectors trust it. Then enable TLS per backend:

```yaml
clickhouse: { secure: true, port: 8443 }
redis: { tls: true, urlExistingSecret: ... }   # Secret value should be rediss://:pw@host:6380/0
qdrant: { https: true, port: 6443, grpcPort: 6444 }
```

## Schema bootstrap

By default (`bootstrap.enabled=true`), a Helm `pre-install` and `pre-upgrade` Job runs a small Python script that:

1. Connects to ClickHouse and applies the schema (idempotent `CREATE … IF NOT EXISTS` from `config/clickhouse/init.sql`)
2. PINGs Redis and round-trips a probe key
3. Calls `qdrant_client.get_collections()` to verify auth

The Job uses the **same image** and **same secrets** as the runtime pod. Required ClickHouse grants: `CREATE TABLE, ALTER, INSERT, SELECT ON kato.*`.

For DBA-managed-schema environments where the runtime user doesn't have DDL privileges, set `bootstrap.enabled=false` and have your DBA apply the SQL from `config/clickhouse/init.sql` manually beforehand. Required runtime grants in this mode: `INSERT, SELECT, ALTER UPDATE, ALTER DELETE ON kato.*`.

## Observability

KATO exposes Prometheus metrics in text format at `/metrics-prom` (added in KATO 3.10.2+). To register a `ServiceMonitor` with the Prometheus Operator:

```yaml
serviceMonitor:
  enabled: true
  labels:
    release: prometheus     # Match your kube-prometheus-stack instance label
```

JSON metrics (richer detail, used by the KATO dashboard) remain at `/metrics`.

## Security posture

The chart ships with PSS-restricted-compatible defaults:

- `runAsNonRoot: true`, `runAsUser: 10001` (matches the non-root user added in the image)
- `allowPrivilegeEscalation: false`, `readOnlyRootFilesystem: true`
- `capabilities.drop: [ALL]`, `seccompProfile: RuntimeDefault`
- `emptyDir` mounts at `/tmp` and `/app/.cache` so `readOnlyRootFilesystem` works

Override per `podSecurityContext` / `securityContext` in values if your environment differs.

## Configuration reference

See [values.yaml](./values.yaml) for the complete, commented reference. Below is the most-used subset.

### Image

| Key                          | Default                              |
|------------------------------|--------------------------------------|
| `image.repository`           | `ghcr.io/sevakavakians/kato`         |
| `image.tag`                  | `""` (defaults to `Chart.AppVersion`) |
| `image.pullPolicy`           | `IfNotPresent`                       |
| `image.pullSecrets`          | `[]`                                 |

### Replication & scaling

| Key                          | Default              |
|------------------------------|----------------------|
| `replicaCount`               | `2`                  |
| `strategy.rollingUpdate.maxSurge` | `1`              |
| `strategy.rollingUpdate.maxUnavailable` | `0`       |
| `autoscaling.enabled`        | `false`              |
| `autoscaling.minReplicas`    | `2`                  |
| `autoscaling.maxReplicas`    | `10`                 |
| `pdb.enabled`                | `false`              |

### Connection — ClickHouse (REQUIRED)

| Key                                | Default              |
|------------------------------------|----------------------|
| `clickhouse.host`                  | `""` (REQUIRED)      |
| `clickhouse.port`                  | `8123` (HTTP)        |
| `clickhouse.database`              | `kato`               |
| `clickhouse.secure`                | `false`              |
| `clickhouse.auth.existingSecret`   | `""`                 |
| `clickhouse.auth.userKey`          | `clickhouse-user`    |
| `clickhouse.auth.passwordKey`      | `clickhouse-password` |

### Connection — Redis

| Key                                | Default              |
|------------------------------------|----------------------|
| `redis.enabled`                    | `true`               |
| `redis.urlExistingSecret`          | `""` (preferred)     |
| `redis.urlKey`                     | `redis-url`          |
| `redis.host`                       | `""` (fallback)      |
| `redis.port`                       | `6379`               |
| `redis.tls`                        | `false`              |
| `redis.auth.existingSecret`        | `""`                 |

### Connection — Qdrant (REQUIRED)

| Key                                | Default              |
|------------------------------------|----------------------|
| `qdrant.host`                      | `""` (REQUIRED)      |
| `qdrant.port`                      | `6333` (HTTP)        |
| `qdrant.grpcPort`                  | `6334` (preferred)   |
| `qdrant.https`                     | `false`              |
| `qdrant.collectionPrefix`          | `vectors`            |
| `qdrant.auth.existingSecret`       | `""`                 |

### KATO tunables

| Key                                | Default              |
|------------------------------------|----------------------|
| `kato.workers`                     | `4`                  |
| `kato.limitConcurrency`            | `100`                |
| `kato.recallThreshold`             | `0.1`                |
| `kato.logLevel`                    | `INFO`               |
| `kato.logFormat`                   | `json`               |
| `kato.sessionTtl`                  | `3600`               |

## Upgrading

```bash
helm upgrade kato oci://ghcr.io/sevakavakians/charts/kato --version 0.2.0 -f my-values.yaml --atomic --timeout 5m
```

The `pre-upgrade` bootstrap hook runs the schema verification step before the rolling update starts. `--atomic` rolls back on failure.

## Uninstalling

```bash
helm uninstall kato
```

The chart does **not** touch your ClickHouse data, Redis state, or Qdrant collections. To remove KATO data, use the appropriate database tooling (e.g., `DROP DATABASE kato` on ClickHouse, `FLUSHDB` on the Redis logical DB, `DELETE COLLECTION` in Qdrant).

## See also

- [docs/operations/helm-deployment.md](../../docs/operations/helm-deployment.md) — full enterprise install walkthrough
- [docs/operations/helm-air-gapped.md](../../docs/operations/helm-air-gapped.md) — offline / mirror install
- [docs/operations/helm-grants.md](../../docs/operations/helm-grants.md) — minimum DB permissions
- [COMPATIBILITY.md](./COMPATIBILITY.md) — chart ↔ KATO version compatibility
