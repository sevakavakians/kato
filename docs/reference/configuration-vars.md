# Environment Variables Reference

Complete reference for all KATO environment variables.

Variables are read in three ways, all of which see values loaded from `.env` by
`kato/env_loader.py`:

1. The Pydantic settings model (`kato/config/settings.py`) — field names map to
   uppercase env var names, case-insensitively.
2. Raw `os.environ` reads in hot paths (pattern search, ClickHouse writer,
   endpoint caches).
3. `kato/config/vectordb_config.py`, which builds the vector database config
   from `KATO_*` variables.

Where both a bare and a `KATO_`-prefixed spelling are listed, prefer the
`KATO_`-prefixed one: the hot paths in `kato/searches/pattern_search.py` read
that spelling directly from the environment.

## Service Configuration

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `SERVICE_NAME` | string | `kato` | Service name identifier |

## Logging Configuration

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `LOG_LEVEL` | string | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL) |
| `LOG_FORMAT` | string | `human` | Log output format: `json` or `human`. `json` emits structured records including `trace_id` and `duration_ms` |
| `LOG_OUTPUT` | string | `stdout` | Log destination: `stdout`, `stderr`, or a file path |

> **Behaviour change**: logs now go to **stdout** by default. Previously logging
> was initialized via `logging.basicConfig`, which wrote to stderr. Set
> `LOG_OUTPUT=stderr` to restore the old destination.

## Database Configuration

### ClickHouse

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `CLICKHOUSE_HOST` | string | `localhost` | ClickHouse host address |
| `CLICKHOUSE_PORT` | integer | `8123` | ClickHouse HTTP port (8123) or native port (9000) |
| `CLICKHOUSE_DB` | string | `kato` | ClickHouse database name |
| `CLICKHOUSE_USER` | string | `default` | ClickHouse username |
| `CLICKHOUSE_PASSWORD` | string | `` | ClickHouse password (optional) |
| `CLICKHOUSE_SECURE` | boolean | `false` | Use HTTPS for ClickHouse connection |

### Qdrant

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `QDRANT_HOST` | string | `localhost` | Qdrant host address |
| `QDRANT_PORT` | integer | `6333` | Qdrant HTTP port (1-65535) |
| `QDRANT_GRPC_PORT` | integer | `6334` | Qdrant gRPC port (1-65535) |
| `QDRANT_API_KEY` | string | None | Qdrant API key for authentication |
| `QDRANT_HTTPS` | boolean | `false` | Use HTTPS for Qdrant connection |

Collection names are not configurable: KATO always uses
`vectors_{processor_id}`.

### Redis

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `REDIS_URL` | string | None | Redis connection URL (preferred) |
| `REDIS_HOST` | string | None | Redis host (deprecated, use REDIS_URL) |
| `REDIS_PORT` | integer | `6379` | Redis port (deprecated) |
| `REDIS_ENABLED` | boolean | `false` | Enable Redis caching |
| `REDIS_TLS` | boolean | `false` | Use TLS for Redis (upgrades redis:// to rediss://) |

## Learning Configuration

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `MAX_PATTERN_LENGTH` | integer | `0` | Auto-learn when STM reaches this length (0 = manual learning only) |
| `PERSISTENCE` | integer | `5` | Emotive rolling window size (1-100) |
| `RECALL_THRESHOLD` | float | `0.1` | Pattern matching sensitivity (0.0-1.0) |
| `STM_MODE` | string | `CLEAR` | STM mode after auto-learn (CLEAR or ROLLING) |

Auto-learning is driven solely by `MAX_PATTERN_LENGTH`. Any value greater than
`0` enables it; `0` means patterns are only learned when `/learn` is called.

## Processing Configuration

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `INDEXER_TYPE` | string | `VI` | Vector indexer type |
| `MAX_PREDICTIONS` | integer | `100` | Maximum predictions to return (1-10000) |
| `SORT_SYMBOLS` | boolean | `true` | Sort symbols alphabetically within events |
| `PROCESS_PREDICTIONS` | boolean | `true` | Enable prediction processing |
| `USE_TOKEN_MATCHING` / `KATO_USE_TOKEN_MATCHING` | boolean | `true` | Token-level (true) vs character-level (false) matching |
| `FUZZY_TOKEN_THRESHOLD` / `KATO_FUZZY_TOKEN_THRESHOLD` | float | `0.0` | Fuzzy token matching threshold (0.0-1.0, 0.0=disabled) |
| `RANK_SORT_ALGO` | string | `potential` | Prediction ranking metric |

## Performance Configuration

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `USE_FAST_MATCHING` / `KATO_USE_FAST_MATCHING` | boolean | `true` | Use optimized matching algorithms |
| `USE_INDEXING` / `KATO_USE_INDEXING` | boolean | `true` | Use pattern indexing for faster lookups |
| `KATO_USE_BLOOM_FILTER` | boolean | `true` | Bloom filter pre-screening in pattern search |
| `KATO_USE_REDIS_CACHE` | boolean | `true` | Redis-backed pattern cache in pattern search |
| `CONNECTION_POOL_SIZE` | integer | `200` | Max Redis connections **per worker** |
| `REQUEST_TIMEOUT` | float | `30.0` | ClickHouse send/receive timeout in seconds. Does **not** affect Qdrant or Redis, which have their own timeouts |
| `MINHASH_HASH_FUNC` | string | `sha1` | MinHash hash function: `sha1` or `xxhash` (faster). Changing this requires reindexing existing patterns |

There is no user-facing batch-size knob. ClickHouse batching is handled
server-side via `async_insert` (`async_insert=1`, `wait_for_async_insert=0`);
the client-side write buffer is deliberately disabled (`DEFAULT_BATCH_SIZE=1`)
because per-worker buffers orphaned rows across uvicorn workers.

## Worker and Concurrency Configuration

These are expanded by the `uvicorn` command in the Dockerfile, and are also read
by the `/concurrency` endpoint to report real capacity.

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `KATO_WORKERS` | integer | `4` | uvicorn worker processes |
| `KATO_LIMIT_CONCURRENCY` | integer | `100` | Max concurrent connections per worker |

Total capacity reported by `/concurrency` is `KATO_LIMIT_CONCURRENCY × KATO_WORKERS`.
Host, port and worker count come from the uvicorn command line — there are no
`HOST`, `PORT` or `WORKERS` environment variables.

## Session Configuration

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `SESSION_TTL` | integer | `3600` | Default session TTL in seconds (60-86400) |
| `SESSION_AUTO_EXTEND` | boolean | `true` | Auto-extend session TTL on access |
| `SESSION_COUNT_CACHE_TTL_SECONDS` | float | `5` | Cache TTL for the session-count endpoint |
| `METRICS_CACHE_TTL_SECONDS` | float | `5` | Cache TTL for the metrics endpoint |

## Configuration Loading

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `KATO_ENV_FILE` | string | None | Explicit path to a `.env` file |
| `KATO_SKIP_DOTENV` | string | None | Set to `1` to disable `.env` loading entirely |
| `KATO_CONFIG_FILE` | string | None | Path to a YAML/JSON configuration file merged into settings (env vars win) |
| `ENVIRONMENT` | string | `development` | Deployment environment (development, testing, production) |
| `DEBUG` | boolean | `false` | Enable debug mode (forced to true when `ENVIRONMENT=development`) |

## Vector Database Configuration

Read by `kato/config/vectordb_config.py`.

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `KATO_VECTOR_DB_BACKEND` | string | `qdrant` | Vector database backend |
| `KATO_VECTOR_DIM` | integer | auto | Embedding dimensionality (auto-detected when unset) |
| `KATO_SIMILARITY_METRIC` | string | `euclidean` | Similarity metric for vector search |
| `KATO_QUANTIZATION_ENABLED` | boolean | `false` | Enable Qdrant quantization |
| `KATO_QUANTIZATION_TYPE` | string | `scalar` | Quantization type (scalar, product, binary) |
| `KATO_CACHE_ENABLED` | boolean | `true` | Enable the vector search cache |
| `KATO_VECTOR_CONFIG_FILE` | string | None | Path to a JSON/YAML vector DB config file (overrides the env-derived config) |

## Session-Level Configuration (not environment variables)

Some settings exist only as per-session configuration fields, set through
`POST /sessions/{session_id}/config`. `affinity_emotive` is one of them — there
is no `AFFINITY_EMOTIVE` environment variable.

### Affinity-Weighted Matching

When `affinity_emotive` is set in the session configuration, KATO uses per-symbol affinity values to weight the pattern matching similarity calculation. Symbols with high absolute affinity for the chosen emotive are treated as signal; symbols with low or zero affinity are treated as noise and discounted.

**Weight formula**: `w(t) = |aff(t, e)| / freq(t) + epsilon`

Where `aff(t, e)` is the cumulative affinity of symbol `t` for emotive `e`, `freq(t)` is the symbol's learn frequency, and `epsilon = 0.01` is a floor weight. This yields the average emotive intensity per observation — scale-invariant across symbol frequencies.

**Effect on predictions**: When active, the following weighted metrics are added to each prediction:
- `weighted_similarity` — affinity-weighted Dice-Sorensen coefficient
- `weighted_evidence`, `weighted_confidence`, `weighted_snr` — weighted versions of standard metrics

The `potential` ranking formula uses the weighted metrics, so predictions with strong emotive signal are ranked higher.

**Configuration via API**:
```bash
POST /sessions/{session_id}/config
{"config": {"affinity_emotive": "cost"}}
```

Set to `null` to disable and revert to standard unweighted matching.

## Example Configuration

### Development

```bash
# .env.development
LOG_LEVEL=DEBUG
LOG_FORMAT=human
CLICKHOUSE_HOST=localhost
CLICKHOUSE_PORT=8123
CLICKHOUSE_DB=kato
QDRANT_HOST=localhost
REDIS_URL=redis://localhost:6379/0
MAX_PATTERN_LENGTH=0
RECALL_THRESHOLD=0.1
```

### Production

```bash
# .env.production
LOG_LEVEL=INFO
LOG_FORMAT=json
CLICKHOUSE_HOST=clickhouse-cluster
CLICKHOUSE_PORT=8123
CLICKHOUSE_DB=kato
QDRANT_HOST=qdrant-cluster
REDIS_URL=redis://redis-cluster:6379/0
MAX_PATTERN_LENGTH=10
RECALL_THRESHOLD=0.3
SESSION_TTL=7200
CONNECTION_POOL_SIZE=200
KATO_WORKERS=8
KATO_LIMIT_CONCURRENCY=200
```

---

**Last Updated**: September 2026
**KATO Version**: 3.0+
