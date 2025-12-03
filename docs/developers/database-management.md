# Database Management Guide

Comprehensive guide to managing KATO databases: ClickHouse, Redis, and Qdrant.

## Overview

KATO uses three databases for different purposes:
- **ClickHouse** - Pattern storage with multi-stage filter pipeline (source of truth)
- **Redis** - Session state, pattern metadata (frequency, emotives), and caching
- **Qdrant** - Vector embeddings (similarity search)

## ClickHouse Management

### Database Structure

```
ClickHouse Server (localhost:8123 HTTP / localhost:9000 Native)
├── kato (database)
│   ├── patterns                     # Pattern data with kb_id partitioning
│   ├── pattern_metadata             # Pattern statistics (optional)
│   └── system tables                # ClickHouse internal tables
```

### Connecting to ClickHouse

**Docker Environment**:
```bash
# Connect via docker exec (native protocol)
docker exec -it kato-clickhouse clickhouse-client

# Connect via HTTP
curl 'http://localhost:8123/?query=SELECT+1'

# Query patterns for specific kb_id
docker exec -it kato-clickhouse clickhouse-client --query="
  SELECT name, length, kb_id FROM kato.patterns
  WHERE kb_id = 'my_node_id' LIMIT 10"
```

**Local Development**:
```bash
# Install ClickHouse client
# macOS: brew install clickhouse
# Ubuntu: apt-get install clickhouse-client

# Connect via native protocol
clickhouse-client --host localhost --port 9000
```

**Python Connection**:
```python
from clickhouse_driver import Client

# Sync connection (native protocol - faster)
client = Client(
    host='localhost',
    port=9000,
    database='kato'
)

# Query patterns for kb_id
patterns = client.execute(
    '''
    SELECT name, length, events
    FROM patterns
    WHERE kb_id = %(kb_id)s
    ORDER BY created_at DESC
    LIMIT 100
    ''',
    {'kb_id': 'my_node_id'}
)
```

### Common ClickHouse Operations

**View Database**:
```sql
-- Show all databases
SHOW DATABASES;

-- Use kato database
USE kato;

-- Show tables
SHOW TABLES;

-- Describe patterns table structure
DESCRIBE patterns;
```

**Query Patterns**:
```sql
-- Find all patterns for kb_id
SELECT * FROM patterns
WHERE kb_id = 'my_node_id'
FORMAT PrettyCompact;

-- Find specific pattern
SELECT * FROM patterns
WHERE name = '7729f0ed56a13a9373fc1b1c17e34f61d4512ab4'
  AND kb_id = 'my_node_id';

-- Find patterns by length
SELECT name, length, kb_id
FROM patterns
WHERE kb_id = 'my_node_id' AND length BETWEEN 3 AND 10;

-- Count patterns per kb_id
SELECT kb_id, COUNT(*) as pattern_count
FROM patterns
GROUP BY kb_id;

-- Find recently created patterns
SELECT name, created_at, kb_id
FROM patterns
WHERE kb_id = 'my_node_id'
ORDER BY created_at DESC
LIMIT 10;
```

**Delete Operations**:
```sql
-- Delete specific pattern
ALTER TABLE patterns DELETE
WHERE name = '7729f0ed56a13a9373fc1b1c17e34f61d4512ab4'
  AND kb_id = 'my_node_id';

-- Delete all patterns for kb_id
ALTER TABLE patterns DELETE WHERE kb_id = 'my_node_id';

-- Drop entire table (careful!)
DROP TABLE IF EXISTS patterns;
```

**Note**: ClickHouse uses `ALTER TABLE ... DELETE` for mutations, not standard `DELETE FROM`.

### Indexing and Performance

**Primary Key**: ClickHouse automatically creates primary key on `(kb_id, name)` for fast lookups.

**Partitioning**: Table is partitioned by `kb_id` for query isolation and performance.

**View Table Definition**:
```sql
SHOW CREATE TABLE patterns;
```

**Optimize Table** (merge parts):
```sql
OPTIMIZE TABLE patterns FINAL;
```

**Query Performance**:
```sql
-- Analyze query plan
EXPLAIN SELECT * FROM patterns
WHERE kb_id = 'my_node_id' AND length = 5;

-- View query statistics
SELECT * FROM system.query_log
WHERE query LIKE '%patterns%'
ORDER BY event_time DESC
LIMIT 10;
```

### Backup and Restore

**Backup Patterns**:
```bash
# Export to CSV
docker exec kato-clickhouse clickhouse-client --query="
  SELECT * FROM kato.patterns WHERE kb_id = 'my_node_id'
  FORMAT CSV" > patterns_backup.csv

# Export to JSON
docker exec kato-clickhouse clickhouse-client --query="
  SELECT * FROM kato.patterns WHERE kb_id = 'my_node_id'
  FORMAT JSONEachRow" > patterns_backup.jsonl

# Compressed export
docker exec kato-clickhouse clickhouse-client --query="
  SELECT * FROM kato.patterns WHERE kb_id = 'my_node_id'
  FORMAT Native" | gzip > patterns_backup.native.gz
```

**Restore Patterns**:
```bash
# From CSV
cat patterns_backup.csv | docker exec -i kato-clickhouse \
  clickhouse-client --query="INSERT INTO kato.patterns FORMAT CSV"

# From JSON
cat patterns_backup.jsonl | docker exec -i kato-clickhouse \
  clickhouse-client --query="INSERT INTO kato.patterns FORMAT JSONEachRow"

# From compressed native
gunzip -c patterns_backup.native.gz | docker exec -i kato-clickhouse \
  clickhouse-client --query="INSERT INTO kato.patterns FORMAT Native"
```

**Automated Backup Script**:
```bash
#!/bin/bash
# backup_clickhouse.sh

BACKUP_DIR="/backups/clickhouse"
DATE=$(date +%Y%m%d_%H%M%S)
KB_ID="${1:-all}"  # Optionally filter by kb_id

mkdir -p ${BACKUP_DIR}

if [ "$KB_ID" = "all" ]; then
  docker exec kato-clickhouse clickhouse-client --query="
    SELECT * FROM kato.patterns FORMAT Native
  " | gzip > ${BACKUP_DIR}/patterns_all_${DATE}.native.gz
else
  docker exec kato-clickhouse clickhouse-client --query="
    SELECT * FROM kato.patterns WHERE kb_id = '${KB_ID}' FORMAT Native
  " | gzip > ${BACKUP_DIR}/patterns_${KB_ID}_${DATE}.native.gz
fi

# Keep last 7 backups
find ${BACKUP_DIR} -name "patterns_*.native.gz" -mtime +7 -delete

echo "Backup completed: ${BACKUP_DIR}/patterns_*_${DATE}.native.gz"
```

## Redis Management

### Data Structure

```
Redis (localhost:6379)
├── session:{session_id}              # Session data (hash)
├── session:{session_id}:stm          # STM snapshot (string)
├── session:{session_id}:emotives     # Emotive state (string)
├── pattern:{kb_id}:{name}:frequency  # Pattern frequency (string)
├── pattern:{kb_id}:{name}:emotives   # Pattern emotives (hash)
└── prediction_cache:{hash}           # Prediction cache (string with TTL)
```

### Connecting to Redis

**Docker Environment**:
```bash
# Connect via docker exec
docker exec -it kato-redis redis-cli

# Or with password (if configured)
docker exec -it kato-redis redis-cli -a your_password
```

### Common Redis Operations

**Session Management**:
```bash
# List all session keys
KEYS session:*

# Get session data
GET session:abc123

# Get session hash
HGETALL session:abc123

# Check TTL
TTL session:abc123

# Extend TTL
EXPIRE session:abc123 3600

# Delete session
DEL session:abc123

# Delete all sessions
EVAL "return redis.call('del', unpack(redis.call('keys', 'session:*')))" 0
```

**Pattern Metadata Management**:
```bash
# Get pattern frequency
GET pattern:my_node:7729f0ed56a13a9373fc1b1c17e34f61d4512ab4:frequency

# Get pattern emotives
HGETALL pattern:my_node:7729f0ed56a13a9373fc1b1c17e34f61d4512ab4:emotives

# List all patterns for kb_id
KEYS pattern:my_node:*

# Delete pattern metadata
DEL pattern:my_node:7729f0ed56a13a9373fc1b1c17e34f61d4512ab4:frequency
DEL pattern:my_node:7729f0ed56a13a9373fc1b1c17e34f61d4512ab4:emotives
```

**Cache Management**:
```bash
# View cache keys
KEYS prediction_cache:*

# Get cache value
GET prediction_cache:abc123

# Clear all cache
FLUSHDB

# Clear specific pattern
EVAL "return redis.call('del', unpack(redis.call('keys', 'prediction_cache:*')))" 0
```

**Monitoring**:
```bash
# Monitor all commands in real-time
MONITOR

# Get server info
INFO
INFO memory
INFO stats

# Get connected clients
CLIENT LIST

# Memory usage of key
MEMORY USAGE session:abc123
```

### Redis Persistence

**Configure Persistence** (docker compose.yml):
```yaml
redis:
  image: redis:7-alpine
  command: redis-server --appendonly yes --save 60 1000
  volumes:
    - redis_data:/data
```

**Backup Redis**:
```bash
# Trigger save
docker exec kato-redis redis-cli SAVE

# Copy RDB file
docker cp kato-redis:/data/dump.rdb ./redis_backup_$(date +%Y%m%d).rdb

# Append-only file
docker cp kato-redis:/data/appendonly.aof ./redis_backup_$(date +%Y%m%d).aof
```

**Restore Redis**:
```bash
# Stop Redis
docker compose stop redis

# Copy backup to container
docker cp redis_backup.rdb kato-redis:/data/dump.rdb

# Start Redis
docker compose start redis
```

## Qdrant Management

### Collection Structure

```
Qdrant Server (localhost:6333)
├── vectors_{kb_id}              # Collection per kb_id
│   ├── Point 1 (UUID)
│   │   ├── vector: [768 floats]
│   │   └── payload: {pattern_name, event_index, vector_name}
│   ├── Point 2
│   └── ...
└── _system                        # Qdrant metadata
```

### REST API Access

**View Collections**:
```bash
# List all collections
curl http://localhost:6333/collections

# Get collection info
curl http://localhost:6333/collections/vectors_my_node

# Count vectors
curl http://localhost:6333/collections/vectors_my_node
```

**Search Vectors**:
```bash
# Search similar vectors
curl -X POST http://localhost:6333/collections/vectors_my_node/points/search \
  -H 'Content-Type: application/json' \
  -d '{
    "vector": [0.1, 0.2, ..., 0.768],
    "limit": 10,
    "with_payload": true
  }'
```

**Manage Points**:
```bash
# Get specific point
curl http://localhost:6333/collections/vectors_my_node/points/{point_id}

# Delete point
curl -X DELETE http://localhost:6333/collections/vectors_my_node/points/{point_id}

# Delete collection
curl -X DELETE http://localhost:6333/collections/vectors_my_node
```

### Python Client

```python
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
import uuid

# Connect
client = QdrantClient(host='localhost', port=6333)

# Create collection
client.create_collection(
    collection_name="vectors_my_node",
    vectors_config=VectorParams(
        size=768,
        distance=Distance.COSINE
    )
)

# Upsert vectors
client.upsert(
    collection_name="vectors_my_node",
    points=[
        PointStruct(
            id=str(uuid.uuid4()),
            vector=[0.1, 0.2, ...],  # 768 dimensions
            payload={
                "pattern_name": "7729f0ed56a13a9373fc1b1c17e34f61d4512ab4",
                "event_index": 0,
                "vector_name": "VCTR|xyz789"
            }
        )
    ]
)

# Search
results = client.search(
    collection_name="vectors_my_node",
    query_vector=[0.1, 0.2, ...],
    limit=100
)

for result in results:
    print(f"Score: {result.score}, Payload: {result.payload}")

# Delete collection
client.delete_collection("vectors_my_node")
```

### Backup and Restore

**Create Snapshot**:
```bash
# Create snapshot via API
curl -X POST http://localhost:6333/collections/vectors_my_node/snapshots

# Response: {"snapshot_name": "vectors_my_node-2025-11-24-14-30-00.snapshot"}

# Download snapshot
curl http://localhost:6333/collections/vectors_my_node/snapshots/vectors_my_node-2025-11-24-14-30-00.snapshot \
  --output vectors_my_node_backup.snapshot
```

**Restore Snapshot**:
```bash
# Upload snapshot
curl -X PUT http://localhost:6333/collections/vectors_my_node/snapshots/upload \
  -H 'Content-Type: application/octet-stream' \
  --data-binary @vectors_my_node_backup.snapshot

# Restore from snapshot
curl -X PUT http://localhost:6333/collections/vectors_my_node/snapshots/vectors_my_node-2025-11-24-14-30-00.snapshot/recover
```

## Database Monitoring

### ClickHouse Monitoring

```sql
-- Current queries
SELECT * FROM system.processes;

-- Database size
SELECT database,
       formatReadableSize(sum(bytes)) AS size
FROM system.parts
WHERE active
GROUP BY database;

-- Table statistics
SELECT table,
       formatReadableSize(sum(bytes)) AS size,
       sum(rows) AS rows
FROM system.parts
WHERE active AND database = 'kato'
GROUP BY table;

-- Slow queries
SELECT type, query_duration_ms, query
FROM system.query_log
WHERE query_duration_ms > 1000
ORDER BY query_duration_ms DESC
LIMIT 10;
```

### Redis Monitoring

```bash
# Real-time stats
redis-cli --stat

# Slow log
redis-cli SLOWLOG GET 10

# Monitor memory
redis-cli INFO memory
```

### Qdrant Monitoring

```bash
# Cluster info
curl http://localhost:6333/cluster

# Telemetry
curl http://localhost:6333/telemetry
```

## Troubleshooting

### ClickHouse Connection Issues

```bash
# Check if ClickHouse is running
docker ps | grep clickhouse

# View ClickHouse logs
docker logs kato-clickhouse --tail 100

# Test connection
docker exec kato-clickhouse clickhouse-client --query "SELECT 1"

# Restart ClickHouse
docker compose restart clickhouse
```

### Redis Issues

```bash
# Check Redis status
docker exec kato-redis redis-cli PING

# View logs
docker logs kato-redis --tail 100

# Check memory usage
docker exec kato-redis redis-cli INFO memory

# Restart Redis
docker compose restart redis
```

### Qdrant Issues

```bash
# Check Qdrant status
curl http://localhost:6333/

# View logs
docker logs kato-qdrant --tail 100

# Restart Qdrant
docker compose restart qdrant
```

### Database Cleanup

**Clean All KATO Data**:
```bash
# WARNING: This deletes ALL data

# Stop services
docker compose down

# Remove volumes
docker volume rm kato_clickhouse_data
docker volume rm kato_qdrant_data
docker volume rm kato_redis_data

# Restart services (fresh databases)
./start.sh
```

## Database Scaling

### ClickHouse Scaling

**Replica Sets** (high availability):
```yaml
# docker compose.yml
clickhouse:
  image: clickhouse/clickhouse-server
  deploy:
    replicas: 3
```

**Sharding** (horizontal scaling):
- Shard by `kb_id` for data partitioning
- Use ClickHouse Keeper for coordination

### Qdrant Scaling

**Clustering**:
```yaml
qdrant:
  image: qdrant/qdrant
  environment:
    QDRANT__CLUSTER__ENABLED: "true"
    QDRANT__CLUSTER__P2P__PORT: "6335"
```

### Redis Scaling

**Redis Cluster**:
```yaml
redis:
  image: redis:7-alpine
  command: redis-server --cluster-enabled yes
  deploy:
    replicas: 6  # Minimum for cluster
```

## Related Documentation

- [Architecture Overview](architecture.md)
- [Performance Profiling](performance-profiling.md)
- [Debugging Guide](debugging.md)
- [Deployment Guide](../operations/docker-deployment.md)

---

**Last Updated**: November 2025
**KATO Version**: 3.0+
