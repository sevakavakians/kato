# Architecture Mode Switching

## Overview

KATO v3.0+ uses a ClickHouse + Redis hybrid architecture. This document describes the filter pipeline configuration and optimization options.

## Quick Start

### Check Current Configuration
```bash
./start.sh status
```

Output:
```
[INFO] KATO v3.0+ - ClickHouse/Redis Hybrid Architecture

Services:
  ✓ ClickHouse - Pattern storage with multi-stage filtering
  ✓ Redis - Session management and metadata caching
  ✓ Qdrant - Vector embeddings

Performance: 100-300x improvement over previous architectures
```

### Switch to Hybrid Mode
```bash
./start.sh mode hybrid
```

Output:
```
[INFO] Switching to hybrid mode...
[INFO] ✓ Mode set to: hybrid
[INFO] Restarting KATO service to apply changes...
[INFO] Waiting for service to be ready...
[INFO] ✓ KATO service restarted successfully

⚠️  Hybrid mode requires:
  1. ClickHouse and Redis services running
  2. Data migrated to ClickHouse/Redis
  3. SessionConfig with filter_pipeline configured

Run migrations if not done:
  python scripts/migrate_mongodb_to_clickhouse.py
  python scripts/migrate_mongodb_to_redis.py

See docs/HYBRID_ARCHITECTURE.md for setup guide
```

### Switch to MongoDB Mode
```bash
./start.sh mode mongodb
```

Output:
```
[INFO] Switching to mongodb mode...
[INFO] ✓ Mode set to: mongodb
[INFO] Restarting KATO service to apply changes...
[INFO] Waiting for service to be ready...
[INFO] ✓ KATO service restarted successfully

[INFO] MongoDB mode active - no additional setup required
```

## How It Works

### 1. Environment Variable

The command updates a `.env` file with:
```env
KATO_ARCHITECTURE_MODE=hybrid
```

Docker-compose automatically reads this file and passes the variable to the KATO container.

### 2. Automatic Configuration

When KATO starts, it reads `KATO_ARCHITECTURE_MODE` and automatically configures:

**MongoDB Mode** (`mongodb` or unset):
```python
PatternSearcher(
    kb_id='kb',
    max_predictions=100,
    recall_threshold=0.1,
    use_token_matching=True
)
# Uses MongoDB for all operations
```

**Hybrid Mode** (`hybrid`):
```python
PatternSearcher(
    kb_id='kb',
    max_predictions=100,
    recall_threshold=0.1,
    use_token_matching=True,
    session_config=SessionConfiguration(
        filter_pipeline=['minhash', 'length', 'jaccard', 'rapidfuzz'],
        minhash_threshold=0.7,
        length_min_ratio=0.5,
        length_max_ratio=2.0,
        jaccard_threshold=0.3,
        enable_filter_metrics=True
    ),
    clickhouse_client=clickhouse,
    redis_client=redis
)
# Uses ClickHouse/Redis for filtering, MongoDB for fallback
```

### 3. Graceful Fallback

If hybrid mode is enabled but ClickHouse/Redis are not available:
- System logs warning
- Automatically falls back to MongoDB mode
- No errors or service disruption

## Complete Workflow for Testing

### Initial Setup (One Time)
```bash
# 1. Start all services
./start.sh start

# 2. Wait for services to be healthy
./start.sh status

# 3. Verify MongoDB mode (default)
./start.sh mode
```

### Migrate to Hybrid (One Time)
```bash
# 1. Switch to hybrid mode
./start.sh mode hybrid

# 2. Run migrations
python scripts/migrate_mongodb_to_clickhouse.py \
    --mongo-url mongodb://localhost:27017 \
    --clickhouse-host localhost \
    --clickhouse-port 8123

python scripts/migrate_mongodb_to_redis.py \
    --mongo-url mongodb://localhost:27017 \
    --redis-host localhost \
    --redis-port 6379

# 3. Verify hybrid mode is active
./start.sh logs kato | grep -i "hybrid"
# Should see: "Hybrid architecture mode enabled"
# Should see: "✓ Hybrid architecture configured successfully"
```

### Performance Testing
```bash
# Test MongoDB mode
./start.sh mode mongodb
# Run benchmarks...

# Test hybrid mode
./start.sh mode hybrid
# Run benchmarks...

# Compare results
```

### Switching During Development
```bash
# Working on MongoDB code
./start.sh mode mongodb
# ... test changes ...

# Working on hybrid code
./start.sh mode hybrid
# ... test changes ...

# Check current mode anytime
./start.sh mode
```

## Default Configuration (Hybrid Mode)

When hybrid mode is enabled, the system uses these default filter settings:

```python
SessionConfiguration(
    filter_pipeline=['minhash', 'length', 'jaccard', 'rapidfuzz'],

    # MinHash/LSH
    minhash_threshold=0.7,       # 70% estimated Jaccard similarity
    minhash_bands=20,             # 20 LSH bands
    minhash_rows=5,               # 5 rows per band
    minhash_num_hashes=100,       # 100 total hash functions

    # Length filter
    length_min_ratio=0.5,         # Min 50% of STM length
    length_max_ratio=2.0,         # Max 200% of STM length

    # Jaccard filter
    jaccard_threshold=0.3,        # 30% minimum overlap
    jaccard_min_overlap=2,        # At least 2 tokens overlap

    # Pipeline control
    enable_filter_metrics=True    # Log performance metrics
)
```

These defaults are optimized for billion-scale pattern matching with good precision/recall balance.

## Customizing Hybrid Mode

To use custom filter settings, you can either:

### Option 1: Modify Code
Edit `kato/workers/pattern_processor.py` line 120-130 to change default SessionConfiguration values.

### Option 2: Per-Session Config (Recommended)
Use session-based configuration API:
```python
# Create session with custom config
POST /sessions
{
    "node_id": "my_node",
    "config": {
        "filter_pipeline": ["length", "jaccard"],  # Skip MinHash for faster but less scalable
        "length_min_ratio": 0.7,
        "jaccard_threshold": 0.5
    }
}
```

## Troubleshooting

### Mode Not Applying
```bash
# 1. Check .env file was created
cat .env
# Should show: KATO_ARCHITECTURE_MODE=hybrid

# 2. Restart service
./start.sh restart kato

# 3. Check logs for mode message
./start.sh logs kato | grep -i "architecture mode"
```

### Hybrid Mode Falls Back to MongoDB
```bash
# Check ClickHouse availability
curl http://localhost:8123/ping
# Should return: Ok.

# Check Redis availability
docker exec kato-redis redis-cli ping
# Should return: PONG

# Check logs for specific error
./start.sh logs kato | grep -i "hybrid"
```

### Data Not Migrated
```bash
# Check ClickHouse has data
docker exec kato-clickhouse clickhouse-client --query "SELECT COUNT(*) FROM default.patterns_data"

# Check Redis has data
docker exec kato-redis redis-cli DBSIZE

# Re-run migrations if needed
python scripts/migrate_mongodb_to_clickhouse.py
python scripts/migrate_mongodb_to_redis.py
```

## Strict Mode (Development)

For development and troubleshooting, enable strict mode to **fail hard** instead of gracefully falling back:

```bash
# Add to .env file
echo "KATO_STRICT_MODE=true" >> .env

# Restart service
./start.sh restart kato

# Or set inline for one-time testing
KATO_STRICT_MODE=true docker compose up -d kato
```

**Strict Mode Behavior:**
- ❌ Hybrid mode initialization errors → **Service fails to start**
- ❌ ClickHouse unavailable → **RuntimeError raised**
- ❌ Redis unavailable → **RuntimeError raised**
- ❌ Empty patterns_data table → **RuntimeError raised**
- ✅ Forces you to fix issues immediately
- ✅ No silent fallbacks hiding problems

**When to Use:**
- ✅ Development and testing
- ✅ Troubleshooting hybrid mode issues
- ✅ CI/CD validation
- ❌ Production (use default graceful fallback)

## Detailed Error Messages

### ClickHouse Connection Failed

```
============================================================
HYBRID ARCHITECTURE INITIALIZATION FAILED
============================================================
Error: ClickHouse client is None!
Possible causes:
  1. ClickHouse service not running (check: docker ps | grep clickhouse)
  2. Connection failed (check: curl http://localhost:8123/ping)
  3. Environment variables incorrect (CLICKHOUSE_HOST, CLICKHOUSE_PORT)
  4. clickhouse-connect library not installed
Run: docker compose logs clickhouse
============================================================
```

**How to Fix:**
```bash
# Check ClickHouse is running
docker ps | grep clickhouse

# Check ClickHouse responds
curl http://localhost:8123/ping
# Expected: Ok.

# Check logs
docker compose logs clickhouse

# Restart if needed
./start.sh restart clickhouse
```

### Redis Connection Failed

```
Redis client is None!
Possible causes:
  1. Redis service not running (check: docker ps | grep redis)
  2. Connection failed (check: docker exec kato-redis redis-cli ping)
  3. Environment variables incorrect (REDIS_URL)
  4. redis library not installed
Run: docker compose logs redis
```

**How to Fix:**
```bash
# Check Redis is running
docker ps | grep redis

# Test Redis connection
docker exec kato-redis redis-cli ping
# Expected: PONG

# Check logs
docker compose logs redis

# Restart if needed
./start.sh restart redis
```

### Empty ClickHouse Table

```
⚠️  WARNING: patterns_data table is EMPTY!
  Hybrid mode will return no results until data is migrated.
  Run: python scripts/migrate_mongodb_to_clickhouse.py
```

**How to Fix:**
```bash
# Run migration script
python scripts/migrate_mongodb_to_clickhouse.py \
    --mongo-url mongodb://localhost:27017 \
    --clickhouse-host localhost \
    --clickhouse-port 8123

# Verify data migrated
docker exec kato-clickhouse clickhouse-client \
    --query "SELECT COUNT(*) FROM default.patterns_data"
```

### Query Execution Failed

```
ClickHouse connection test failed: <error details>
  Host: clickhouse
  Port: 9000
Run: docker exec kato-clickhouse clickhouse-client --query 'SELECT 1'
```

**How to Fix:**
```bash
# Test query manually
docker exec kato-clickhouse clickhouse-client --query "SELECT 1"
# Expected: 1

# Check if table exists
docker exec kato-clickhouse clickhouse-client \
    --query "SHOW TABLES FROM default"
# Should show: patterns_data

# Check table schema
docker exec kato-clickhouse clickhouse-client \
    --query "DESCRIBE default.patterns_data"
```

## Logs to Watch During Development

### Successful Hybrid Initialization
```bash
./start.sh logs kato | grep -A 10 "HYBRID ARCHITECTURE"
```

**Expected Output:**
```
============================================================
HYBRID ARCHITECTURE MODE ENABLED
============================================================
Initializing ClickHouse/Redis connections...
✓ ClickHouse connection verified
✓ Redis connection verified
ClickHouse patterns_data table: 1,234,567 rows
============================================================
✓ HYBRID ARCHITECTURE CONFIGURED SUCCESSFULLY
============================================================
Filter pipeline: ['minhash', 'length', 'jaccard', 'rapidfuzz']
Performance: 100-300x improvement expected
============================================================
```

### Failed Hybrid Initialization (Graceful Fallback)
```bash
./start.sh logs kato | grep -A 5 "FALLING BACK"
```

**Expected Output:**
```
⚠️  FALLING BACK TO MONGODB MODE
Set KATO_STRICT_MODE=true to fail instead of fallback
MongoDB architecture mode active
```

### Failed Hybrid Initialization (Strict Mode)
```bash
./start.sh logs kato | tail -50
```

**Expected Output:**
```
============================================================
HYBRID ARCHITECTURE INITIALIZATION FAILED
============================================================
Error: ClickHouse required in strict mode but not available
Full traceback:
  [stack trace...]
============================================================
STRICT MODE: Failing hard instead of falling back
RuntimeError: Hybrid mode required but initialization failed
```

## Environment Variable Reference

| Variable | Values | Default | Description |
|----------|--------|---------|-------------|
| `KATO_ARCHITECTURE_MODE` | `mongodb`, `hybrid` | `mongodb` | Architecture mode selection |
| `KATO_STRICT_MODE` | `true`, `false` | `false` | Fail hard on hybrid errors (development) |

## Benefits of Mode Switching

### For Development
- Test both implementations easily
- Compare performance side-by-side
- Debug mode-specific issues
- No code changes required

### For Production
- Start with stable MongoDB mode
- Migrate to hybrid incrementally
- Roll back instantly if issues
- Run A/B tests

### For Benchmarking
- Fair performance comparisons
- Isolate infrastructure changes
- Validate optimization claims
- Generate comparison reports

## See Also

- **HYBRID_ARCHITECTURE.md** - Complete hybrid mode documentation
- **start.sh** - Service management script
- **scripts/migrate_mongodb_to_clickhouse.py** - ClickHouse migration
- **scripts/migrate_mongodb_to_redis.py** - Redis migration
