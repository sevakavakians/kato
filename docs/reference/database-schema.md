# Database Schema Reference

Complete field-level reference for all data stored across KATO's three databases. For architectural context, see [Hybrid Architecture](../developers/hybrid-architecture.md).

**Version**: KATO 3.8.0+

---

## ClickHouse

Database: `kato`. All tables partitioned by `kb_id` for node isolation.

### `patterns_data` (main pattern storage)

Engine: `MergeTree()`, partitioned by `kb_id`, ordered by `(kb_id, length, name)`, granularity 8192.

| Field | Type | Description | Example |
|---|---|---|---|
| `kb_id` | String | Knowledge base / node identifier (partition key) | `"node_weather_bot"` |
| `name` | String | Pattern identifier (SHA1 hash, no `PTRN\|` prefix) | `"7729f0ed56a13a9373fc1b1c17e34f61d4512ab4"` |
| `pattern_data` | Array(Array(String)) | Nested array of token events (the learned sequence) | `[["hello","world"], ["how","are","you"]]` |
| `length` | UInt32 | Total token count across all events (precomputed) | `5` |
| `token_set` | Array(String) | Flattened unique tokens (for Jaccard similarity) | `["are","hello","how","world","you"]` |
| `token_count` | UInt32 | Distinct token count (precomputed) | `5` |
| `minhash_sig` | Array(UInt32) | MinHash signature (100 hash values for LSH) | `[283741, 9182, 44012, ...]` |
| `lsh_bands` | Array(UInt64) | LSH band hashes (20 bands x 5 rows each) | `[8827361, 1923847, ...]` |
| `first_token` | String | First token in the pattern (prefix filtering) | `"hello"` |
| `last_token` | String | Last token in the pattern (suffix filtering) | `"you"` |
| `created_at` | DateTime | Creation timestamp (default: `now()`) | `2026-03-27 10:00:00` |
| `updated_at` | DateTime | Last update timestamp (default: `now()`) | `2026-03-27 10:00:00` |

**Secondary indexes:**

| Index | Column | Type | Granularity |
|---|---|---|---|
| `idx_length` | `length` | MinMax | 4 |
| `idx_token_bloom` | `token_set` | Bloom filter (0.01 FPR) | 4 |
| `idx_token_count` | `token_count` | MinMax | 4 |

**Source**: [`config/clickhouse/init.sql`](../../config/clickhouse/init.sql)

---

### `lsh_buckets` (LSH lookup optimization)

Engine: `MergeTree()`, partitioned by `kb_id`, ordered by `(kb_id, band_hash, pattern_name)`.

| Field | Type | Description | Example |
|---|---|---|---|
| `kb_id` | String | Knowledge base / node identifier (partition key) | `"node_weather_bot"` |
| `band_index` | UInt8 | Band number (0-19) | `3` |
| `band_hash` | UInt64 | Hash of the band (for quick LSH lookups) | `8827361` |
| `pattern_name` | String | Pattern name (reference to `patterns_data.name`) | `"7729f0ed..."` |

---

### `pattern_stats` (monitoring)

Engine: `MergeTree()`, partitioned by `kb_id`, ordered by `(kb_id, date)`.

| Field | Type | Description | Example |
|---|---|---|---|
| `kb_id` | String | Knowledge base / node identifier (partition key) | `"node_weather_bot"` |
| `date` | Date | Statistics date | `2026-03-27` |
| `total_patterns` | UInt64 | Total pattern count for this kb_id | `1542` |
| `avg_length` | Float64 | Average pattern length | `4.7` |
| `avg_token_count` | Float64 | Average distinct token count per pattern | `3.2` |
| `min_length` | UInt32 | Minimum pattern length | `2` |
| `max_length` | UInt32 | Maximum pattern length | `18` |

---

## Redis

All keys are namespaced by `kb_id` (except sessions and caches). Keys without explicit TTL are persistent.

### Pattern metadata

Stored per pattern at learn time. No TTL (persistent).

| Key pattern | Redis type | Fields / Value | Example |
|---|---|---|---|
| `{kb_id}:frequency:{pattern_name}` | STRING | Integer count of pattern observations | `"42"` |
| `{kb_id}:emotives:{pattern_name}` | STRING (JSON) | List of emotive context dicts from observations | `[{"joy": 0.8, "surprise": 0.3}]` |
| `{kb_id}:metadata:{pattern_name}` | STRING (JSON) | Arbitrary metadata dict (tags, source, etc.) | `{"source": "chat", "tags": ["greeting"]}` |

**Source**: [`kato/storage/redis_writer.py`](../../kato/storage/redis_writer.py)

---

### Symbol statistics

Per-symbol aggregates updated at learn time. No TTL (persistent).

| Key pattern | Redis type | Fields / Value | Description | Example |
|---|---|---|---|---|
| `{kb_id}:symbols:freq` | HASH | `{symbol}` -> total occurrences | Frequency-weighted: if symbol appears 3x in pattern with freq=2, increments by 6 | `{"hello": "156", "world": "89"}` |
| `{kb_id}:symbols:pmf` | HASH | `{symbol}` -> pattern count | How many patterns contain this symbol (counted once per pattern) | `{"hello": "12", "world": "8"}` |
| `{kb_id}:symbol_to_patterns:{symbol}` | SET | Pattern name members | Fast lookup: which patterns contain this symbol | `{"7729f0ed...", "a3b1c2d4..."}` |
| `{kb_id}:affinity:{symbol}` | HASH | `{emotive}` -> cumulative sum | Running sum of averaged emotive values across all learns containing this symbol. Updated atomically via `HINCRBYFLOAT`. Accumulates on re-learn (not idempotent). | `{"joy": "3.6", "fear": "1.2", "utility": "25.0"}` |

---

### Global counters

Aggregate statistics per knowledge base. No TTL (persistent).

| Key pattern | Redis type | Description | Example |
|---|---|---|---|
| `{kb_id}:global:total_symbols_in_patterns_frequencies` | STRING | Sum of all symbol frequency values | `"4821"` |
| `{kb_id}:global:total_pattern_frequencies` | STRING | Frequency-weighted total pattern count | `"1542"` |
| `{kb_id}:global:total_unique_patterns` | STRING | Count of unique (non-frequency-weighted) patterns | `"387"` |

---

### Pre-computed metrics

Populated by the [`POST /sessions/{session_id}/finalize-training`](api/learning.md#finalize-training) endpoint. Call once after training completes to pre-compute Shannon entropy and TF vectors for all patterns. If not populated, these metrics are computed at runtime during predictions (slower). No TTL (persistent).

| Key pattern | Redis type | Description | Example |
|---|---|---|---|
| `{kb_id}:entropy:{pattern_name}` | STRING | Pre-computed entropy value | `"2.317"` |
| `{kb_id}:normalized_entropy:{pattern_name}` | STRING | Pre-computed normalized entropy | `"0.891"` |
| `{kb_id}:global_normalized_entropy:{pattern_name}` | STRING | Pre-computed global normalized entropy | `"0.654"` |
| `{kb_id}:tf_vector:{pattern_name}` | STRING (JSON) | Pre-computed term frequency vector | `{"hello": 0.5, "world": 0.5}` |
| `{kb_id}:prediction:{id}` | STRING (JSON) | Stored prediction results | `[{"pattern": "7729...", "score": 0.85}]` |

---

### Sessions

Managed by `RedisSessionManager`. TTL-based (default 3600s, auto-extended on access).

| Key pattern | Redis type | TTL | Description | Example |
|---|---|---|---|---|
| `kato:session:{session_id}` | STRING (JSON) | Session TTL | Complete session state (see fields below) | *(see below)* |
| `kato:session:node:{node_id}:active` | STRING | Session TTL | Active session ID for this node (enables session reuse) | `"session-abc123-1711540800"` |

**Session state fields** (JSON in `kato:session:{session_id}`):

| Field | Type | Description |
|---|---|---|
| `session_id` | string | Unique identifier (`session-{uuid}-{timestamp}`) |
| `node_id` | string | Associated node/processor |
| `created_at` | string | ISO timestamp |
| `last_accessed` | string | ISO timestamp |
| `expires_at` | string | ISO timestamp |
| `ttl_seconds` | int | Session timeout |
| `stm` | array | Short-term memory (list of event arrays) |
| `emotives_accumulator` | array | Accumulated emotive observations |
| `metadata_accumulator` | array | Accumulated metadata observations |
| `time` | int | Observation counter |
| `percept_data` | object | Session-isolated percept (v3.0+) |
| `predictions` | array | Session-isolated predictions (v3.0+) |
| `metadata` | object | Session metadata |
| `access_count` | int | Number of accesses |
| `max_stm_size` | int | STM capacity limit |
| `max_emotives_size` | int | Emotives window size |
| `max_metadata_size` | int | Metadata window size |
| `session_config` | object | Per-session configuration overrides |

**Source**: [`kato/sessions/redis_session_manager.py`](../../kato/sessions/redis_session_manager.py)

---

### Distributed STM (Redis Streams)

Event streams for distributed STM coordination.

| Key pattern | Redis type | Entry fields | Description |
|---|---|---|---|
| `stm:events:{processor_id}` | STREAM | `event_type`, `processor_id`, `timestamp`, `data` (JSON), `sequence_id` | Processor-specific STM event stream |
| `stm:global` | STREAM | *(same)* | Global ordering across all processors |

`event_type` values: `observe`, `clear`, `learn`, `autolearn`, `rollback`

Consumer group: `stm_group_{processor_id}`

**Source**: [`kato/storage/redis_streams.py`](../../kato/storage/redis_streams.py)

---

### Caches

TTL-based, automatically evicted.

| Key pattern | Redis type | TTL | Description |
|---|---|---|---|
| `patterns:top:{session_id}:{limit}` | STRING (JSON) | 3600s | Top patterns by frequency |
| `patterns:name:{pattern_name}` | STRING (JSON) | 3600s | Individual pattern document |
| `symbols:probabilities` | STRING (JSON) | 1800s | Symbol probability map |
| `kato:metrics:{metric_type}:{md5_hash}` | STRING | 3600s | Cached metric computations (entropy, conditional probability, ITFDF, potential) |

**Source**: [`kato/storage/pattern_cache.py`](../../kato/storage/pattern_cache.py), [`kato/storage/metrics_cache.py`](../../kato/storage/metrics_cache.py)

---

## Qdrant

Vector embedding storage. One collection per deployment (default: `kato_vectors`).

### Collection configuration

| Setting | Default | Description |
|---|---|---|
| Collection name | `kato_vectors` | Configurable via `QDRANT_COLLECTION` env var |
| Vector dimensions | 512 | Auto-detected at first insertion; configurable via `KATO_VECTOR_DIM` |
| Distance metric | Euclidean | Also supports: `cosine`, `dot`, `manhattan` |
| On-disk payload | `true` | Payloads stored on disk |
| HNSW `m` | 16 | Number of neighbors in HNSW graph |
| HNSW `ef_construct` | 128 | Construction parameter |
| HNSW `full_scan_threshold` | 10000 | When to abandon index for full scan |

**Source**: [`kato/config/vectordb_config.py`](../../kato/config/vectordb_config.py)

### Point structure

Each stored vector is a Qdrant `PointStruct`:

| Component | Type | Description | Example |
|---|---|---|---|
| `id` | UUID (v5) | Deterministic UUID derived from `vctr_name` via `uuid5(NAMESPACE_DNS, vctr_name)` | `"f47ac10b-58cc-4372-a567-0e02b2c3d479"` |
| `vector` | list[float] | Embedding vector (dimension locked at first insertion) | `[0.123, -0.456, 0.789, ...]` |

### Payload fields

| Field | Type | Description | Example |
|---|---|---|---|
| `vctr_name` | string | Original vector identifier (`VCTR\|{SHA1}` format) | `"VCTR\|7729f0ed56a13a9373fc1b1c17e34f61d4512ab4"` |
| *(custom)* | any | Optional user-provided metadata merged into payload | `{"source": "embedding_model_v2"}` |

**Source**: [`kato/searches/vector_search_engine.py`](../../kato/searches/vector_search_engine.py), [`kato/storage/qdrant_store.py`](../../kato/storage/qdrant_store.py)

---

## Data flow summary

```
Observation -> KatoProcessor
  |-- Pattern learned      -> ClickHouse (pattern_data, minhash, LSH)
  |                        -> Redis (frequency, emotives, metadata, symbol maps)
  |                        -> Redis (affinity: averaged emotives -> each symbol)
  |-- Vector input         -> Qdrant (embedding + VCTR|hash payload)
  |-- Session state        -> Redis (STM, accumulators, config)
  '-- Finalize training    -> Redis (entropy, normalized_entropy, tf_vector per pattern)
```

## See also

- [Hybrid Architecture](../developers/hybrid-architecture.md) - Design rationale, filter pipeline, migration
- [KB ID Isolation](../developers/kb-id-isolation.md) - Node isolation details
- [Configuration Variables](configuration-vars.md) - Environment variables
- [Filter Pipeline Guide](filter-pipeline-guide.md) - MinHash/LSH tuning
- [ClickHouse init.sql](../../config/clickhouse/init.sql) - Raw DDL
