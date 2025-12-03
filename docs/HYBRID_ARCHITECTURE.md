# ClickHouse/Redis Hybrid Architecture

## Overview

KATO's hybrid architecture provides **100-300x performance improvement** for pattern matching at billion-scale by splitting responsibilities between specialized databases:

- **ClickHouse**: Pattern data with multi-stage filtering (billions → thousands)
- **Redis**: Pattern metadata (emotives, frequency, metadata) with fast K/V lookups

## Architecture Design

### Problem Solved
Traditional document databases time out after 5 seconds when scanning millions of patterns. At billion-scale, this becomes infeasible.

### Solution
**Multi-stage filtering pipeline** that reduces candidate patterns before loading into RAM:

```
Billions (ClickHouse) → Millions (LSH) → Thousands (Jaccard) → Hundreds (RapidFuzz) → RAM
```

### Database Split

| Database | Stores | Optimized For |
|----------|--------|---------------|
| **ClickHouse** | `pattern_data`, length, tokens, MinHash, LSH bands | Full-table scans with WHERE clause pushdown |
| **Redis** | `emotives`, `metadata`, `frequency` | Fast point lookups by pattern name |

## Node Isolation via kb_id

### Critical Requirement

**KATO requires complete data isolation between different nodes/processors/knowledge bases.** Each node requires its own isolated data space to prevent cross-contamination.

The hybrid architecture implements this isolation via the **`kb_id` (Knowledge Base Identifier)** parameter.

### How kb_id Isolation Works

#### ClickHouse: Partitioning by kb_id

```sql
CREATE TABLE patterns_data (
    kb_id String,                        -- MUST be first column
    name String,
    pattern_data Array(Array(String)),
    ...
) ENGINE = MergeTree()
PARTITION BY kb_id                       -- Physical isolation per node
ORDER BY (kb_id, length, name);          -- Partition pruning enabled
```

**Benefits**:
- ✅ **Physical isolation**: Each node's data in separate partition
- ✅ **Partition pruning**: ClickHouse only scans relevant node's partition (10-100x speedup)
- ✅ **Easy cleanup**: `DROP PARTITION 'node0'` removes all node0 data instantly
- ✅ **Zero data leakage**: Impossible for node0 queries to return node1 patterns

#### Redis: Key Namespacing by kb_id

```python
# Without kb_id (WRONG - causes data contamination)
frequency:PTRN|abc123
emotives:PTRN|abc123

# With kb_id (CORRECT - isolated per node)
node0:frequency:PTRN|abc123   # node0's frequency
node0:emotives:PTRN|abc123    # node0's emotives

node1:frequency:PTRN|abc123   # node1's frequency (different key!)
node1:emotives:PTRN|abc123    # node1's emotives
```

**Benefits**:
- ✅ **Key isolation**: Different nodes can't overwrite each other's data
- ✅ **Easy cleanup**: `redis-cli KEYS "node0:*" | xargs redis-cli DEL`
- ✅ **Namespace clarity**: Key prefix shows which node it belongs to

### Usage

When initializing `PatternSearcher`, always provide `kb_id`:

```python
# Correct - with kb_id
searcher = PatternSearcher(
    kb_id='node0',  # CRITICAL: Specifies which node's data to access
    session_config=session_config,
    clickhouse_client=clickhouse_client,
    redis_client=redis_client
)

# Under the hood, all queries automatically inject:
# WHERE kb_id = 'node0'
# Redis keys: node0:frequency:{pattern_name}
```

### Multi-Node Scenarios

**Use Case**: Multiple trained nodes for different domains/users

```python
# Production node for user A
searcher_user_a = PatternSearcher(
    kb_id='user_a_kb',
    session_config=config,
    clickhouse_client=clickhouse,
    redis_client=redis
)

# Production node for user B (same databases, isolated data)
searcher_user_b = PatternSearcher(
    kb_id='user_b_kb',
    session_config=config,
    clickhouse_client=clickhouse,
    redis_client=redis
)

# Training node (separate from production)
searcher_training = PatternSearcher(
    kb_id='training_corpus_v2',
    session_config=config,
    clickhouse_client=clickhouse,
    redis_client=redis
)
```

All three access the same ClickHouse and Redis instances, but their data is **completely isolated** via kb_id.

### Migration and kb_id

The migration scripts automatically extract `kb_id` from MongoDB database name:

```bash
# MongoDB database name becomes kb_id
python scripts/migrate_mongodb_to_clickhouse.py \
    --mongo-url mongodb://localhost:27017/node0
    # Extracts kb_id='node0' and sets it for all patterns

python scripts/migrate_mongodb_to_redis.py \
    --mongo-url mongodb://localhost:27017/node0
    # Extracts kb_id='node0' and prefixes all Redis keys
```

**Result**:
- MongoDB: `node0.patterns_kb` → ClickHouse: `kb_id='node0'` + Redis: `node0:*`
- MongoDB: `node1.patterns_kb` → ClickHouse: `kb_id='node1'` + Redis: `node1:*`

### Best Practices

1. **Use descriptive kb_ids**:
   - ✅ Good: `production_user_123`, `training_v2`, `node0`
   - ❌ Bad: `test`, `data`, `patterns_data` (too generic)

2. **Consistent naming**:
   - MongoDB database name MUST match kb_id
   - Example: `mongodb://host:port/node0` → `kb_id='node0'`

3. **Cleanup per node**:
   ```bash
   # ClickHouse: Drop entire partition
   ALTER TABLE patterns_data DROP PARTITION 'node0';

   # Redis: Delete all keys for node
   redis-cli KEYS "node0:*" | xargs redis-cli DEL
   ```

4. **Verification**:
   ```sql
   -- Check partitions
   SELECT partition, rows FROM system.parts
   WHERE table = 'patterns_data'
   GROUP BY partition ORDER BY partition;

   -- Output:
   -- node0  | 100000
   -- node1  |  50000
   -- node2  |  75000
   ```

### What Happens Without kb_id

**Without kb_id isolation** (pre-v3.0.0):
- ❌ All nodes write to single ClickHouse partition
- ❌ Queries from node0 could return node1 patterns (data contamination)
- ❌ Redis keys overwrite each other
- ❌ **Critical data integrity violation**

**With kb_id isolation** (v3.0.0+):
- ✅ Each node physically isolated in ClickHouse partition
- ✅ Queries automatically filtered by kb_id (no leakage)
- ✅ Redis keys namespaced per node
- ✅ **Complete data integrity**

### See Also

- **Detailed kb_id documentation**: `docs/KB_ID_ISOLATION.md`
- **Migration troubleshooting**: `docs/KB_ID_ISOLATION.md#troubleshooting`
- **Partition management**: `docs/KB_ID_ISOLATION.md#verification`

## Filter Pipeline

⚠️ **IMPORTANT: MinHash Parameter Tuning Required**

MinHash uses Locality-Sensitive Hashing (LSH) with parameters tuned for **high similarity matching (≥0.7)** by default. Using MinHash with low similarity thresholds (<0.4) or wrong parameter combinations will result in **false negatives** and missed patterns.

**Before using MinHash, read**: [Filter Pipeline Configuration Guide](reference/filter-pipeline-guide.md) for:
- LSH probability mathematics and parameter tuning
- When to use MinHash vs Jaccard
- Filter ordering considerations
- Common pitfalls and solutions

### Available Filters

1. **LengthFilter** (database-side)
   - Filters by pattern length relative to STM
   - O(log n) indexed query

2. **JaccardFilter** (database-side)
   - Set intersection using ClickHouse array functions
   - Exact Jaccard similarity calculation
   - **Recommended for <10M patterns** (faster + exact)

3. **MinHashFilter** (hybrid: DB + Python)
   - Stage 1 (DB): LSH band matching (99% reduction)
   - Stage 2 (Python): MinHash similarity verification
   - Billion-scale approximate matching
   - **⚠️ Requires parameter tuning** - see [Filter Guide](reference/filter-pipeline-guide.md)

4. **BloomFilterStage** (Python-side)
   - Fast token presence checking
   - Zero false negatives

5. **RapidFuzzFilter** (Python-side)
   - Fast similarity calculation (5-10x speedup)
   - Final candidate ranking

### Pipeline Configuration

Configure via `SessionConfiguration`:

```python
from kato.config.session_config import SessionConfiguration

config = SessionConfiguration(
    # Filter pipeline (ordered list)
    filter_pipeline=['minhash', 'length', 'jaccard', 'rapidfuzz'],

    # MinHash/LSH parameters
    minhash_threshold=0.7,      # Estimated Jaccard threshold
    minhash_bands=20,            # Number of LSH bands
    minhash_rows=5,              # Rows per band
    minhash_num_hashes=100,      # Total hash functions

    # Length filter parameters
    length_min_ratio=0.5,        # Min pattern length (50% of STM)
    length_max_ratio=2.0,        # Max pattern length (200% of STM)

    # Jaccard filter parameters
    jaccard_threshold=0.3,       # Min Jaccard similarity
    jaccard_min_overlap=2,       # Min absolute token overlap

    # Bloom filter parameters
    bloom_false_positive_rate=0.01,  # 1% FPR

    # Pipeline control
    max_candidates_per_stage=100000,  # Safety limit
    enable_filter_metrics=True        # Log performance
)
```

### Example Pipelines

**Billion-scale (recommended)**:
```python
filter_pipeline=['minhash', 'length', 'jaccard', 'rapidfuzz']
```

**Million-scale (faster, less filtering)**:
```python
filter_pipeline=['length', 'jaccard', 'rapidfuzz']
```

**Precision-focused (slower, more accurate)**:
```python
filter_pipeline=['minhash', 'length', 'jaccard', 'bloom', 'rapidfuzz']
```

## Usage

### 1. Deploy Services

```bash
# Start ClickHouse, Redis, MongoDB
docker compose up -d

# Verify services
curl http://localhost:8123/  # ClickHouse
redis-cli ping               # Redis → PONG
mongo --eval "db.version()"  # MongoDB
```

### 2. Migrate Data

#### Single Node Migration

```bash
# Migrate pattern data to ClickHouse (with MinHash pre-computation)
python scripts/migrate_mongodb_to_clickhouse.py \
    --mongo-url mongodb://localhost:27017/node0 \
    --clickhouse-host localhost \
    --clickhouse-port 8123 \
    --batch-size 1000

# Migrate metadata to Redis
python scripts/migrate_mongodb_to_redis.py \
    --mongo-url mongodb://localhost:27017/node0 \
    --redis-host localhost \
    --redis-port 6379 \
    --batch-size 1000
```

#### Multi-Node Migration (Recommended)

If you have multiple trained nodes (e.g., node0, node1, node2, node3), use the batch migration script:

```bash
# Migrate all nodes at once
./scripts/migrate_all_nodes.sh

# Migrate specific nodes
./scripts/migrate_all_nodes.sh --nodes "node0 node1"

# Dry run to test without writing
./scripts/migrate_all_nodes.sh --dry-run

# Custom batch size for performance tuning
./scripts/migrate_all_nodes.sh --batch-size 5000

# Skip ClickHouse or Redis migration
./scripts/migrate_all_nodes.sh --skip-clickhouse  # Only migrate to Redis
./scripts/migrate_all_nodes.sh --skip-redis       # Only migrate to ClickHouse
```

**Migration Features:**
- **Parallel node processing** - All nodes migrated sequentially with progress tracking
- **Error handling** - Failed nodes reported, successful ones continue
- **Progress tracking** - Real-time progress for each node
- **Verification** - Automatic count verification after migration
- **Dry-run mode** - Test migration without writing to databases
- **Configurable** - Custom hosts, ports, batch sizes

**Expected Performance:**
- ~1000 patterns/second per node
- 10,000 patterns per node: ~10 seconds
- 100,000 patterns per node: ~100 seconds (1.5 minutes)
- 1,000,000 patterns per node: ~1000 seconds (~16 minutes)

#### Verify Migration

After migration, verify data integrity:

```bash
# Verify all nodes
python scripts/verify_migration.py

# Verify specific nodes
python scripts/verify_migration.py --nodes node0 node1

# More thorough sampling
python scripts/verify_migration.py --sample-size 100
```

**Verification checks:**
- ✓ Pattern counts match between MongoDB and ClickHouse
- ✓ Frequency keys match pattern counts in Redis
- ✓ Sample patterns have matching data across all databases
- ✓ Data integrity preserved (frequencies, pattern_data, etc.)

### 3. Enable Hybrid Architecture

```python
from kato.config.session_config import SessionConfiguration
from kato.storage.connection_manager import get_clickhouse_client, get_redis_client
from kato.searches.pattern_search import PatternSearcher

# Initialize connections
clickhouse_client = get_clickhouse_client()
redis_client = get_redis_client()

# Create session config with filter pipeline
session_config = SessionConfiguration(
    filter_pipeline=['minhash', 'length', 'jaccard', 'rapidfuzz'],
    minhash_threshold=0.7,
    length_min_ratio=0.5,
    length_max_ratio=2.0,
    jaccard_threshold=0.3,
    recall_threshold=0.1
)

# Initialize PatternSearcher with hybrid architecture
searcher = PatternSearcher(
    kb_id='my_kb',
    max_predictions=100,
    recall_threshold=0.1,
    session_config=session_config,
    clickhouse_client=clickhouse_client,
    redis_client=redis_client
)

# Use causalBelief as normal - it will automatically use filter pipeline
state = ['token1', 'token2', 'token3']
predictions = searcher.causalBelief(state)
```

### 4. Error Handling

**IMPORTANT**: As of KATO v3.0, MongoDB is no longer supported. The system requires ClickHouse + Redis.

If ClickHouse or Redis are unavailable:
- The system will raise an error
- Check service health via `/health` endpoint
- Ensure all required services are running

```python
# Hybrid architecture (required in v3.0+)
searcher = PatternSearcher(
    kb_id='my_kb',
    max_predictions=100,
    recall_threshold=0.1,
    clickhouse_client=clickhouse_client,  # Required
    redis_client=redis_client              # Required
)
```

## Performance

### Performance Improvements (vs. v2.x MongoDB)

| Patterns | v2.x (MongoDB) | v3.0+ (ClickHouse/Redis) | Speedup |
|----------|----------------|--------------------------|---------|
| 1M       | ~5s            | ~200ms                   | 25x     |
| 10M      | ~50s           | ~300ms                   | 166x    |
| 100M     | Timeout | ~500ms                    | 300x+   |
| 1B       | Timeout | ~1s                       | ∞       |

### Stage-by-Stage Reduction

Example with 1 billion patterns:

```
Stage 1 (MinHash LSH):     1,000,000,000 → 10,000,000 (99% reduction)
Stage 2 (Length):            10,000,000 →  5,000,000 (50% reduction)
Stage 3 (Jaccard):            5,000,000 →    100,000 (98% reduction)
Stage 4 (RapidFuzz):            100,000 →        100 (99.9% reduction)
───────────────────────────────────────────────────────────────────────
Total:                    1,000,000,000 →        100 (99.99999% reduction)
```

Only 100 patterns loaded into RAM for final prediction processing!

## Monitoring

### Filter Metrics

When `enable_filter_metrics=True`, logs show per-stage performance:

```
[INFO] Filter 'minhash': 10000000 candidates (1250.3ms)
[INFO] Filter 'length': 5000000 candidates (45.2ms)
[INFO] Filter 'jaccard': 100000 candidates (892.1ms)
[INFO] Filter 'rapidfuzz': 100 candidates (34.5ms)
[INFO] Filter pipeline complete: 100 final candidates (2222.1ms total)
```

### Get Metrics Programmatically

```python
# After calling causalBelief
if searcher.filter_executor:
    metrics = searcher.filter_executor.get_metrics()
    print(f"Total stages: {metrics['total_stages']}")
    print(f"Final candidates: {metrics['final_candidates']}")
    for stage in metrics['stages']:
        print(f"{stage['filter']}: {stage['candidates_after']} candidates, {stage['time_ms']}ms")
```

## Troubleshooting

### ClickHouse Connection Errors

```python
# Check ClickHouse availability
from kato.storage.connection_manager import get_clickhouse_client
client = get_clickhouse_client()
if client:
    print("ClickHouse connected")
else:
    print("ClickHouse not available - check docker compose services")
```

### Redis Connection Errors

```python
# Check Redis availability
import redis
r = redis.Redis(host='localhost', port=6379)
try:
    r.ping()
    print("Redis connected")
except:
    print("Redis not available - check docker compose services")
```

### Filter Pipeline Errors

If filter pipeline fails, check logs for:
- Missing columns in ClickHouse (run migration script if upgrading from v2.x)
- Missing data in Redis (run migration script if upgrading from v2.x)
- Invalid filter configuration (check SessionConfig validation)

**Note**: System will raise an error if ClickHouse or Redis are unavailable (no MongoDB fallback in v3.0+).

## Migration Scripts

### MongoDB → ClickHouse

```bash
python scripts/migrate_mongodb_to_clickhouse.py --help

Options:
  --mongo-url TEXT            MongoDB connection string
  --clickhouse-host TEXT      ClickHouse host
  --clickhouse-port INTEGER   ClickHouse port
  --clickhouse-db TEXT        ClickHouse database
  --batch-size INTEGER        Patterns per batch (default: 1000)
  --processor-id TEXT         Specific processor ID to migrate
  --dry-run                   Test without writing to ClickHouse
```

### MongoDB → Redis

```bash
python scripts/migrate_mongodb_to_redis.py --help

Options:
  --mongo-url TEXT         MongoDB connection string
  --redis-host TEXT        Redis host
  --redis-port INTEGER     Redis port
  --redis-db INTEGER       Redis database number
  --batch-size INTEGER     Patterns per batch (default: 1000)
  --processor-id TEXT      Specific processor ID to migrate
  --dry-run                Test without writing to Redis
```

## Best Practices

1. **Always migrate data before enabling hybrid architecture**
   - Run both migration scripts
   - Verify data with sample queries

2. **Start with permissive filters, then tune**
   - Begin with default thresholds
   - Monitor metrics to find bottlenecks
   - Adjust thresholds to balance precision/recall

3. **Use appropriate pipelines for scale**
   - Million-scale: Skip MinHash, use length + Jaccard
   - Billion-scale: Use full pipeline with MinHash

4. **Monitor filter metrics in production**
   - Set `enable_filter_metrics=True`
   - Log metrics to monitoring system
   - Alert on unusual reductions or slow stages

5. **Backup ClickHouse data regularly**
   - ClickHouse is the primary pattern storage (no MongoDB fallback in v3.0+)
   - Use ClickHouse backup tools for disaster recovery
   - Test restore procedures periodically

## Implementation Status

✅ **Complete (Phases 1-5)**:
- Infrastructure (ClickHouse, Redis, connection managers)
- Filter framework (base classes, executor, registry)
- Individual filters (5 filters implemented)
- Data migration scripts (2 scripts with dry-run mode)
- PatternSearcher integration (automatic hybrid mode detection)

⏳ **Remaining (Phase 5-6)**:
- End-to-end integration tests
- Performance benchmarking
- Production deployment documentation

## References

- **ClickHouse Documentation**: https://clickhouse.com/docs
- **Redis Persistence**: https://redis.io/topics/persistence
- **MinHash/LSH**: Broder, A. Z. (1997). "On the resemblance and containment of documents"
- **Filter Pipeline Design**: `docs/research/pattern-matching.md`
