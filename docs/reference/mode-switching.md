# Architecture Mode

## There Is No Mode Switch

KATO v3.0+ runs on the ClickHouse + Redis hybrid architecture, and that is the
only supported architecture. MongoDB has been removed, and there is nothing to
switch between.

The `KATO_ARCHITECTURE_MODE` and `KATO_STRICT_MODE` environment variables no
longer exist. Setting them has no effect.

```bash
./start.sh mode      # Prints the (fixed) architecture and its service requirements
```

## Required Services

All three services must be reachable or KATO fails to start with an explicit
error:

- **ClickHouse** — pattern storage and the multi-stage filter pipeline
- **Redis** — session management, pattern metadata, caching
- **Qdrant** — vector embeddings

```bash
curl http://localhost:8123/ping             # ClickHouse -> Ok.
docker exec kato-redis redis-cli ping       # Redis -> PONG
curl http://localhost:6333/                 # Qdrant
```

If a connection fails, check the corresponding service logs
(`docker compose logs clickhouse` / `redis` / `qdrant`) and the connection
variables in [Environment Variables Reference](configuration-vars.md).

## What Is Actually Configurable

The filter pipeline — not the architecture — is what you tune, and it is tuned
per session rather than by environment variable:

```json
POST /sessions
{
    "node_id": "my_node",
    "config": {
        "filter_pipeline": ["jaccard"],
        "jaccard_threshold": 0.5
    }
}
```

## See Also

- **[Filter Pipeline Guide](filter-pipeline-guide.md)** - MinHash/LSH tuning and pipeline defaults
- **[Hybrid Architecture](../developers/hybrid-architecture.md)** - How ClickHouse and Redis are used
- **[Environment Variables Reference](configuration-vars.md)** - Every variable KATO actually reads

---

**Last Updated**: September 2026
**KATO Version**: 3.0+
