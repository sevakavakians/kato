# Database Management Guide

Comprehensive guide to managing KATO databases: MongoDB, Qdrant, and Redis.

## Overview

KATO uses three databases for different purposes:
- **MongoDB** - Pattern storage (source of truth)
- **Qdrant** - Vector embeddings (similarity search)
- **Redis** - Session state and caching

## MongoDB Management

### Database Structure

```
MongoDB Server (localhost:27017)
├── node_{node_id}_kato/              # Database per node_id
│   ├── patterns                      # Learned patterns
│   ├── pattern_metadata              # Pattern statistics
│   ├── global_metadata               # Node-level metadata
│   └── system.profile                # Query profiling (if enabled)
└── admin/                            # MongoDB admin database
```

### Connecting to MongoDB

**Docker Environment**:
```bash
# Connect via docker exec
docker exec -it kato-mongodb mongosh

# Connect with specific database
docker exec -it kato-mongodb mongosh node_my_app_kato
```

**Local Development**:
```bash
# Install MongoDB shell
brew install mongosh  # macOS
apt-get install mongodb-mongosh  # Ubuntu

# Connect
mongosh mongodb://localhost:27017
```

**Python Connection**:
```python
from motor.motor_asyncio import AsyncIOMotorClient

# Async connection
client = AsyncIOMotorClient('mongodb://localhost:27017')
db = client['node_my_app_kato']
patterns_collection = db['patterns']

# Query patterns
async def get_pattern_count():
    count = await patterns_collection.count_documents({})
    return count
```

### Common MongoDB Operations

**View Databases**:
```javascript
// Show all databases
show dbs

// Switch to database
use node_my_app_kato

// Show collections
show collections
```

**Query Patterns**:
```javascript
// Find all patterns
db.patterns.find({}).pretty()

// Find specific pattern
db.patterns.findOne({"_id": "PTN|abc123"})

// Find patterns by length
db.patterns.find({"length": {"$gte": 3, "$lte": 10}})

// Find recently created patterns
db.patterns.find({}).sort({"created_at": -1}).limit(10)

// Find frequently observed patterns
db.patterns.find({"observation_count": {"$gte": 100}}).sort({"observation_count": -1})

// Count patterns
db.patterns.countDocuments({})

// Aggregate statistics
db.patterns.aggregate([
  {
    $group: {
      _id: "$length",
      count: { $sum: 1 },
      avg_observations: { $avg: "$observation_count" }
    }
  },
  { $sort: { _id: 1 } }
])
```

**Update Operations**:
```javascript
// Increment observation count
db.patterns.updateOne(
  {"_id": "PTN|abc123"},
  {"$inc": {"observation_count": 1}}
)

// Update metadata
db.patterns.updateOne(
  {"_id": "PTN|abc123"},
  {
    "$set": {
      "updated_at": new Date(),
      "metadata.tagged": true
    }
  }
)

// Bulk update
db.patterns.updateMany(
  {"length": 2},
  {"$set": {"metadata.short_pattern": true}}
)
```

**Delete Operations**:
```javascript
// Delete specific pattern
db.patterns.deleteOne({"_id": "PTN|abc123"})

// Delete patterns by criteria
db.patterns.deleteMany({"observation_count": {"$lt": 5}})

// Delete all patterns for node
db.patterns.deleteMany({})

// Drop collection
db.patterns.drop()

// Drop entire database
db.dropDatabase()
```

### Indexing

**View Indices**:
```javascript
db.patterns.getIndexes()
```

**Create Indices**:
```javascript
// Single field index
db.patterns.createIndex({"length": 1})

// Compound index
db.patterns.createIndex({"length": 1, "observation_count": -1})

// Descending index
db.patterns.createIndex({"created_at": -1})

// Unique index
db.patterns.createIndex({"_id": 1}, {unique: true})

// Sparse index (only documents with field)
db.patterns.createIndex({"metadata.tag": 1}, {sparse: true})

// Text index (full-text search)
db.patterns.createIndex({"events": "text"})

// Array index (for event queries)
db.patterns.createIndex({"events.0": 1})
```

**Drop Indices**:
```javascript
// Drop specific index
db.patterns.dropIndex("length_1")

// Drop all indices except _id
db.patterns.dropIndexes()
```

**Index Performance**:
```javascript
// Analyze index usage
db.patterns.aggregate([
  { $indexStats: {} }
])

// Explain query plan
db.patterns.find({"length": 3}).explain("executionStats")

// Look for:
// - "stage": "IXSCAN" (good - using index)
// - "stage": "COLLSCAN" (bad - full collection scan)
// - "executionTimeMillis": < 100ms
```

### Backup and Restore

**Backup Single Database**:
```bash
# Backup using mongodump
docker exec kato-mongodb mongodump \
  --db=node_my_app_kato \
  --out=/backup

# Copy backup from container
docker cp kato-mongodb:/backup ./mongodb_backup

# Compressed backup
docker exec kato-mongodb mongodump \
  --db=node_my_app_kato \
  --archive=/backup/kato_$(date +%Y%m%d).archive \
  --gzip
```

**Restore Database**:
```bash
# Copy backup to container
docker cp ./mongodb_backup kato-mongodb:/restore

# Restore using mongorestore
docker exec kato-mongodb mongorestore \
  --db=node_my_app_kato \
  /restore/node_my_app_kato

# Restore from archive
docker exec kato-mongodb mongorestore \
  --archive=/backup/kato_20251113.archive \
  --gzip
```

**Automated Backup Script**:
```bash
#!/bin/bash
# backup_mongodb.sh

BACKUP_DIR="/backups/mongodb"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="kato_backup_${DATE}.archive"

# Create backup directory
mkdir -p ${BACKUP_DIR}

# Perform backup
docker exec kato-mongodb mongodump \
  --archive=/tmp/${BACKUP_FILE} \
  --gzip

# Copy from container
docker cp kato-mongodb:/tmp/${BACKUP_FILE} ${BACKUP_DIR}/

# Clean old backups (keep last 7 days)
find ${BACKUP_DIR} -name "kato_backup_*.archive" -mtime +7 -delete

echo "Backup completed: ${BACKUP_DIR}/${BACKUP_FILE}"
```

**Schedule with cron**:
```bash
# Edit crontab
crontab -e

# Add daily backup at 2 AM
0 2 * * * /path/to/backup_mongodb.sh >> /var/log/kato_backup.log 2>&1
```

### Migrations

**Example Migration Script**:
```python
# scripts/migrate_add_version_field.py
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def migrate():
    """Add version field to all patterns."""
    client = AsyncIOMotorClient('mongodb://localhost:27017')

    # Get all KATO databases
    db_names = await client.list_database_names()
    kato_dbs = [name for name in db_names if name.startswith('node_') and name.endswith('_kato')]

    for db_name in kato_dbs:
        db = client[db_name]
        patterns = db['patterns']

        # Update all patterns without version field
        result = await patterns.update_many(
            {"version": {"$exists": False}},
            {"$set": {"version": "3.0"}}
        )

        print(f"Updated {result.modified_count} patterns in {db_name}")

    client.close()

if __name__ == "__main__":
    asyncio.run(migrate())
```

**Run Migration**:
```bash
python scripts/migrate_add_version_field.py
```

## Qdrant Management

### Collection Structure

```
Qdrant Server (localhost:6333)
├── vectors_{node_id}              # Collection per node_id
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
curl http://localhost:6333/collections/vectors_my_app

# Count vectors
curl http://localhost:6333/collections/vectors_my_app
```

**Search Vectors**:
```bash
# Search similar vectors
curl -X POST http://localhost:6333/collections/vectors_my_app/points/search \
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
curl http://localhost:6333/collections/vectors_my_app/points/{point_id}

# Delete point
curl -X DELETE http://localhost:6333/collections/vectors_my_app/points/{point_id}

# Delete collection
curl -X DELETE http://localhost:6333/collections/vectors_my_app
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
    collection_name="vectors_my_app",
    vectors_config=VectorParams(
        size=768,
        distance=Distance.COSINE
    )
)

# Upsert vectors
client.upsert(
    collection_name="vectors_my_app",
    points=[
        PointStruct(
            id=str(uuid.uuid4()),
            vector=[0.1, 0.2, ...],  # 768 dimensions
            payload={
                "pattern_name": "PTN|abc123",
                "event_index": 0,
                "vector_name": "VCTR|xyz789"
            }
        )
    ]
)

# Search
results = client.search(
    collection_name="vectors_my_app",
    query_vector=[0.1, 0.2, ...],
    limit=100
)

for result in results:
    print(f"Score: {result.score}, Payload: {result.payload}")

# Delete collection
client.delete_collection("vectors_my_app")
```

### Backup and Restore

**Create Snapshot**:
```bash
# Create snapshot via API
curl -X POST http://localhost:6333/collections/vectors_my_app/snapshots

# Response: {"snapshot_name": "vectors_my_app-2025-11-13-14-30-00.snapshot"}

# Download snapshot
curl http://localhost:6333/collections/vectors_my_app/snapshots/vectors_my_app-2025-11-13-14-30-00.snapshot \
  --output vectors_my_app_backup.snapshot
```

**Restore Snapshot**:
```bash
# Upload snapshot
curl -X PUT http://localhost:6333/collections/vectors_my_app/snapshots/upload \
  -H 'Content-Type: application/octet-stream' \
  --data-binary @vectors_my_app_backup.snapshot

# Restore from snapshot
curl -X PUT http://localhost:6333/collections/vectors_my_app/snapshots/vectors_my_app-2025-11-13-14-30-00.snapshot/recover
```

### Collection Optimization

**Reindex Collection**:
```python
# Optimize index parameters
client.update_collection(
    collection_name="vectors_my_app",
    hnsw_config=HnswConfigDiff(
        m=16,              # Links per layer
        ef_construct=100,  # Build-time parameter
        ef=128            # Search-time parameter
    )
)
```

**Vacuum Collection** (remove deleted points):
```bash
curl -X POST http://localhost:6333/collections/vectors_my_app/vacuum
```

## Redis Management

### Data Structure

```
Redis (localhost:6379)
├── session:{session_id}              # Session data (hash)
├── session:{session_id}:stm          # STM snapshot (string)
├── session:{session_id}:emotives     # Emotive state (string)
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

**Configure Persistence** (docker-compose.yml):
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
docker-compose stop redis

# Copy backup to container
docker cp redis_backup.rdb kato-redis:/data/dump.rdb

# Start Redis
docker-compose start redis
```

### Redis Configuration

**Memory Limits** (docker-compose.yml):
```yaml
redis:
  image: redis:7-alpine
  command: >
    redis-server
    --maxmemory 2gb
    --maxmemory-policy allkeys-lru
    --appendonly yes
```

**Eviction Policies**:
- `allkeys-lru` - Evict least recently used keys
- `allkeys-lfu` - Evict least frequently used keys
- `volatile-ttl` - Evict keys with shortest TTL
- `noeviction` - Return errors when memory limit reached

## Database Monitoring

### MongoDB Monitoring

```javascript
// Current operations
db.currentOp()

// Server status
db.serverStatus()

// Collection stats
db.patterns.stats()

// Slow query log
db.setProfilingLevel(1, {slowms: 100})
db.system.profile.find().sort({ts: -1}).limit(10)
```

### Qdrant Monitoring

```bash
# Cluster info
curl http://localhost:6333/cluster

# Telemetry
curl http://localhost:6333/telemetry
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

## Troubleshooting

### MongoDB Connection Issues

```bash
# Check if MongoDB is running
docker ps | grep mongodb

# View MongoDB logs
docker logs kato-mongodb --tail 100

# Test connection
docker exec kato-mongodb mongosh --eval "db.runCommand({ping: 1})"

# Restart MongoDB
docker-compose restart mongodb
```

### Qdrant Issues

```bash
# Check Qdrant status
curl http://localhost:6333/

# View logs
docker logs kato-qdrant --tail 100

# Restart Qdrant
docker-compose restart qdrant
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
docker-compose restart redis
```

### Database Cleanup

**Clean All KATO Data**:
```bash
# WARNING: This deletes ALL data

# Stop services
docker-compose down

# Remove volumes
docker volume rm kato_mongodb_data
docker volume rm kato_qdrant_data
docker volume rm kato_redis_data

# Restart services (fresh databases)
./start.sh
```

## Database Scaling

### MongoDB Scaling

**Replica Sets** (high availability):
```yaml
# docker-compose.yml
mongodb:
  image: mongo:7
  command: --replSet rs0
  deploy:
    replicas: 3
```

**Sharding** (horizontal scaling):
- Shard by `node_id` for data partitioning
- Use MongoDB Atlas for managed sharding

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
