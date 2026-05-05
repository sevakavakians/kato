# Minimum Database Grants for KATO

This is the exact set of permissions the KATO runtime user needs in each backing store. Two ClickHouse profiles are listed, depending on whether you let KATO bootstrap its own schema or have the DBA pre-create it.

## ClickHouse

KATO uses ClickHouse's HTTP interface (port 8123/8443). The runtime user runs queries against the `kato` database (configurable via `clickhouse.database`).

### Profile A: KATO bootstraps its own schema (`bootstrap.enabled=true`, the default)

```sql
-- Run as a user with CREATE DATABASE permission, once:
CREATE DATABASE IF NOT EXISTS kato;

-- Grants for the KATO runtime user:
CREATE USER kato_user IDENTIFIED WITH sha256_password BY 'CHANGEME';
GRANT CREATE TABLE, ALTER, INSERT, SELECT, OPTIMIZE ON kato.* TO kato_user;
```

The bootstrap Job applies the table DDL (`patterns_data`, `lsh_buckets`, `pattern_stats` plus secondary indexes) idempotently on every install/upgrade. `CREATE TABLE IF NOT EXISTS` and `ADD INDEX IF NOT EXISTS` make repeat runs harmless.

### Profile B: DBA pre-creates the schema (`bootstrap.enabled=false`)

The DBA runs the full `config/clickhouse/init.sql` once. The runtime user then needs only data-plane grants:

```sql
GRANT INSERT, SELECT, ALTER UPDATE, ALTER DELETE, OPTIMIZE ON kato.* TO kato_user;
```

This profile is appropriate for environments with strict separation of duties (the team installing the Helm chart does not have DDL privileges).

## Redis

KATO uses Redis for sessions, cache, pattern metadata, and metrics indices. Default DB number is 0; configurable via `redis.database`.

Minimum ACL (Redis 6+):

```
ACL SETUSER kato_user on >CHANGEME ~* &* +@all -@dangerous -DEBUG -CLUSTER -CONFIG -SHUTDOWN
```

Stricter (read/write/connect/scripting only):

```
ACL SETUSER kato_user on >CHANGEME ~* &* \
  +@read +@write +@connection +@scripting +PING +EVAL +EVALSHA +SCRIPT
```

KATO uses these command groups:
- Strings: `GET`, `SET`, `DEL`, `EXPIRE`, `INCR`, `EXISTS`
- Hashes: `HGET`, `HSET`, `HDEL`, `HMGET`, `HSCAN`, `HINCRBY`
- Sets: `SADD`, `SREM`, `SCARD`, `SMEMBERS`, `SINTER`, `SDIFF`
- Pub/Sub: not used as of 3.10.x
- Scripting: `EVAL`/`EVALSHA` for atomic compound operations
- Server: `PING`

`KEYS` is not used by the application path (eliminated in commit `8726829`). It may appear in `redis-cli` debugging.

## Qdrant

KATO uses gRPC by default (port 6334) with HTTP fallback (port 6333). API key auth is recommended whenever Qdrant is reachable beyond a private network.

### Required collection-level operations

KATO creates one collection per knowledge base / node identifier (`{collectionPrefix}_<hash>`). At minimum the API key must be permitted to:

- `LIST` collections (used by the bootstrap Job's connectivity check)
- `CREATE COLLECTION` for new `kb_id` partitions (or pre-create them as DBA — see below)
- `UPSERT POINTS`, `SEARCH POINTS`, `RETRIEVE POINTS`, `DELETE POINTS`
- `CREATE PAYLOAD INDEX`

If your Qdrant build supports per-collection API keys (Qdrant ≥ 1.9 with the role-based auth plugin), you can scope the runtime key to `vectors_*` (substituting your `qdrant.collectionPrefix`) and grant a separate, narrower key to the bootstrap Job.

### Pre-creating collections (strict separation of duties)

If your Qdrant policy prohibits dynamic collection creation:

1. DBA pre-creates collections matching the pattern `{collectionPrefix}_<known_kb_ids>` with vector size 768 and `Distance: Euclid` (or `Cosine`/`Dot` per your `KATO_SIMILARITY_METRIC`).
2. Runtime API key only needs read/write on those collections.
3. Note: this requires you to know all `kb_id` values in advance. Most KATO deployments create `kb_id` values dynamically per node, so this profile is rarely practical.

## TLS material

If you connect to ClickHouse / Redis / Qdrant over TLS with a private CA, mount the CA bundle:

```yaml
tls:
  caBundle:
    existingConfigMap: enterprise-ca-bundle   # data key: ca.crt
```

The chart exports `SSL_CERT_FILE` and `REQUESTS_CA_BUNDLE` so both Python's stdlib SSL and `requests`-based ClickHouse connectors trust it. No application-level changes needed.

## Sample combined manifest

A minimal-grant ClickHouse user, Redis ACL, and Qdrant API-key generation script lives in [`config/clickhouse/users.xml`](../../config/clickhouse/users.xml) (ClickHouse profile reference) and [`config/redis.conf`](../../config/redis.conf) (Redis defaults). For Qdrant, generate API keys via your Qdrant operator UI or the management API.
