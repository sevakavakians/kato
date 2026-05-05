-- KATO Pattern Data Storage Schema
-- ClickHouse table for billion-scale pattern matching

CREATE DATABASE IF NOT EXISTS kato;

USE kato;

-- Main patterns_data table with node isolation via kb_id partitioning
CREATE TABLE IF NOT EXISTS patterns_data (
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
ALTER TABLE patterns_data
    ADD INDEX IF NOT EXISTS idx_length length TYPE minmax GRANULARITY 4;

ALTER TABLE patterns_data
    ADD INDEX IF NOT EXISTS idx_token_bloom token_set TYPE bloom_filter(0.01) GRANULARITY 4;

ALTER TABLE patterns_data
    ADD INDEX IF NOT EXISTS idx_token_count token_count TYPE minmax GRANULARITY 4;

-- LSH buckets table (optional, for more efficient LSH lookups) with node isolation
CREATE TABLE IF NOT EXISTS lsh_buckets (
    kb_id String,                         -- Knowledge base / node identifier (for isolation)
    band_index UInt8,                     -- Band number (0-19)
    band_hash UInt64,                     -- Hash of the band
    pattern_name String                   -- Pattern name
) ENGINE = MergeTree()
PARTITION BY kb_id                        -- Physical isolation per node
ORDER BY (kb_id, band_hash, pattern_name);

-- Statistics table for monitoring (per kb_id for node-specific metrics)
CREATE TABLE IF NOT EXISTS pattern_stats (
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
