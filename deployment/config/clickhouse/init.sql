-- KATO Pattern Data Storage Schema
-- ClickHouse table for billion-scale pattern matching
--
-- Every table is database-qualified and there is no `USE kato`: the HTTP
-- interface runs one statement per request with no session carried between
-- them, so any applier that sends statements individually (scripts/
-- apply_clickhouse_schema.py, the Helm bootstrap Job) would otherwise create
-- these tables in `default`.

CREATE DATABASE IF NOT EXISTS kato;

-- Main patterns_data table with node isolation via kb_id partitioning
CREATE TABLE IF NOT EXISTS kato.patterns_data (
    -- Node isolation (MUST be first for partition pruning)
    kb_id String,                         -- Knowledge base / node / processor identifier

    -- Core pattern fields
    name String,                          -- SHA1 hash (unique identifier)
    pattern_data Array(Array(String)),    -- Nested array of token events
    length UInt32,                        -- Total token count (precomputed)

    -- Optimization fields for filtering
    token_set Array(String),              -- Flattened unique tokens
    token_count UInt32,                   -- Distinct token count

    -- MinHash/LSH fields
    minhash_sig Array(UInt32),            -- MinHash signature (100 hashes)
    lsh_bands Array(UInt64),              -- LSH band hashes (20 bands × 5 rows)

    -- Optional: Additional optimizations
    first_token String,                   -- First token (prefix filtering)
    last_token String,                    -- Last token (suffix filtering)

    -- Metadata
    created_at DateTime DEFAULT now(),
    updated_at DateTime DEFAULT now()

) ENGINE = MergeTree()
PARTITION BY kb_id                        -- Physical isolation per node (enables DROP PARTITION)
ORDER BY (kb_id, length, name)            -- Partition pruning + range queries
SETTINGS index_granularity = 8192;

-- Secondary indexes for fast filtering
ALTER TABLE kato.patterns_data
    ADD INDEX IF NOT EXISTS idx_length length TYPE minmax GRANULARITY 4;

ALTER TABLE kato.patterns_data
    ADD INDEX IF NOT EXISTS idx_token_bloom token_set TYPE bloom_filter(0.01) GRANULARITY 4;

ALTER TABLE kato.patterns_data
    ADD INDEX IF NOT EXISTS idx_token_count token_count TYPE minmax GRANULARITY 4;

-- LSH buckets table (optional, for more efficient LSH lookups) with node isolation
CREATE TABLE IF NOT EXISTS kato.lsh_buckets (
    kb_id String,                         -- Knowledge base / node identifier (for isolation)
    band_index UInt8,                     -- Band number (0-19)
    band_hash UInt64,                     -- Hash of the band
    pattern_name String                   -- Pattern name
) ENGINE = MergeTree()
PARTITION BY kb_id                        -- Physical isolation per node
ORDER BY (kb_id, band_hash, pattern_name);

-- Statistics table for monitoring (per kb_id for node-specific metrics)
CREATE TABLE IF NOT EXISTS kato.pattern_stats (
    kb_id String,                         -- Knowledge base / node identifier
    date Date,
    total_patterns UInt64,
    avg_length Float64,
    avg_token_count Float64,
    min_length UInt32,
    max_length UInt32
) ENGINE = MergeTree()
PARTITION BY kb_id                        -- Partition by node for independent metrics
ORDER BY (kb_id, date);

-- Pattern metadata sidecar (per-pattern KV data offloaded from Redis to bound RAM use)
-- ReplacingMergeTree dedupes by (kb_id, name) on background merges using `version` as the
-- version column. Readers MUST use argMax(field, version) GROUP BY name (not the FINAL
-- modifier) to retrieve the latest values without depending on merge timing.
-- `version` is a strictly-monotonic time.time_ns() stamp from the writer, so a later write
-- to the same (kb_id, name) always wins — even within the same wall-clock second. (The prior
-- DateTime `updated_at` version tied at 1-second resolution and could return a stale row.)
CREATE TABLE IF NOT EXISTS kato.patterns_metadata (
    kb_id                     String,                    -- Knowledge base / node identifier
    name                      String,                    -- Pattern SHA1 hash
    emotives                  String  DEFAULT '[]',      -- JSON list of dicts (rolling window)
    metadata                  String  DEFAULT '{}',      -- JSON dict, set-union accumulator
    entropy                   Nullable(Float64),         -- Pre-computed Shannon entropy
    normalized_entropy        Nullable(Float64),         -- Pre-computed normalized entropy
    global_normalized_entropy Nullable(Float64),         -- Pre-computed global normalized entropy
    tf_vector                 String  DEFAULT '{}',      -- JSON dict (token → frequency)
    version                   UInt64,                    -- Monotonic version (time.time_ns) for ReplacingMergeTree
    updated_at                DateTime64(3) DEFAULT now64(3) -- Informational only (not the version)
) ENGINE = ReplacingMergeTree(version)
PARTITION BY kb_id                        -- Physical isolation per node (matches patterns_data)
ORDER BY (kb_id, name);                   -- Point-lookup ordering for batch WHERE name IN (...)
