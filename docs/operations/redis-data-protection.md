# Redis Data Protection & Recovery

## ⚠️ CRITICAL: Unrecoverable Data in Redis

**IMPORTANT**: The following data types are **ONLY** stored in Redis and **CANNOT** be recovered from ClickHouse if lost:

| Data Type | Stored In | Recoverable from ClickHouse? |
|-----------|-----------|------------------------------|
| **Emotives** | Redis only | ❌ NO - Permanently lost |
| **Pattern Metadata** (custom tags/annotations) | Redis only | ❌ NO - Permanently lost |
| **Pattern Frequency** (match counts) | Redis only | ❌ NO - Dynamic counter |
| Symbol Frequencies | Redis only | ✅ YES - Can rebuild from ClickHouse |
| Symbol PMF | Redis only | ✅ YES - Can rebuild from ClickHouse |
| Pattern Sequences | ClickHouse | ✅ YES - Primary storage |

---

## Current Persistence Configuration

### Redis Persistence (Dual Layer)

**RDB Snapshots** (Point-in-time backups):
```
save 60 1000       # Every 60s if ≥1000 keys changed
save 300 10        # Every 5m if ≥10 keys changed
save 900 1         # Every 15m if ≥1 key changed
```

**AOF (Append-Only File)** (Write-ahead log):
```
appendonly yes
appendfsync everysec          # Fsync every second
aof-use-rdb-preamble yes     # Hybrid mode: RDB + AOF
```

**Volume Mount**:
```yaml
volumes:
  - redis-data:/data
```

---

## How Data Loss Can Occur

### 1. Container Removal with -v Flag ❌
```bash
docker compose down -v   # DANGER: Deletes volumes!
```
**Prevention**: NEVER use `-v` flag in production.

### 2. Manual Data Flush ❌
```bash
redis-cli FLUSHALL
redis-cli FLUSHDB
```
**Prevention**: Disable dangerous commands in production or require authentication.

### 3. Corrupted AOF File (Rare)
- Redis fails to start due to corrupted AOF
- User manually deletes/truncates AOF to recover
- Data loss from last RDB snapshot to corruption point

**Prevention**: Regular backups, AOF auto-repair on startup.

### 4. Volume Misconfiguration ❌
```bash
# Mounting wrong volume
docker run -v new_empty_volume:/data ...
```

**Prevention**: Use named volumes consistently, verify mounts before starting.

###  5. Hardware Failure (Without Backups)
- Disk failure
- No offsite backups

**Prevention**: Automated offsite backups (see below).

---

## Backup Strategy

### Automated Daily Backups

**Script**: `/scripts/backup_redis.sh`

**Usage**:
```bash
# Manual backup
./scripts/backup_redis.sh

# Automated via cron (daily at 2 AM)
0 2 * * * cd /path/to/kato && ./scripts/backup_redis.sh >> /var/log/kato_backup.log 2>&1
```

**What Gets Backed Up**:
- RDB snapshot (dump.rdb or kato_patterns.rdb)
- AOF files (appendonlydir or appendonly.aof)
- Redis INFO (metadata)
- DBSIZE (key count)
- Manifest file

**Retention**: 30 days by default (configurable via `BACKUP_RETENTION_DAYS`)

**Backup Location**: `./backups/redis/<timestamp>/`

---

## Recovery Procedures

### Scenario 1: Complete Data Loss (Redis Empty)

**Symptoms**:
- KATO reports 0 patterns despite ClickHouse having data
- `redis-cli DBSIZE` returns 0
- Emotives/metadata missing

**Recovery Steps**:

1. **Restore from backup** (if available):
   ```bash
   ./scripts/restore_redis.sh 20260115_120000
   ```

2. **Rebuild symbol frequencies** from ClickHouse:
   ```bash
   python3 scripts/populate_redis_symbols_from_clickhouse.py \
     --clickhouse-host localhost \
     --redis-url redis://localhost:6379
   ```

3. **Verify restoration**:
   ```bash
   docker exec kato-redis redis-cli DBSIZE
   docker exec kato-redis redis-cli --scan --pattern "*:emotives:*" | wc -l
   docker exec kato-redis redis-cli --scan --pattern "*:metadata:*" | wc -l
   ```

**Data Loss**:
- ✅ Patterns: Fully restored
- ✅ Symbol frequencies: Rebuilt from ClickHouse
- ❌ Emotives: Lost if not in backup
- ❌ Metadata: Lost if not in backup
- ❌ Pattern frequencies: Lost (will reset to 1)

---

### Scenario 2: Partial Data Loss (Missing Emotives/Metadata)

**Symptoms**:
- Symbol frequencies exist
- Emotives/metadata missing for specific kb_ids

**Recovery**:
```bash
# Check which kb_ids have emotives
docker exec kato-redis redis-cli --scan --pattern "*:emotives:*" | \
  cut -d':' -f1 | sort -u

# Restore from backup if available
./scripts/restore_redis.sh <timestamp>
```

**If no backup**: Emotives and metadata are **permanently lost** for those kb_ids.

---

### Scenario 3: Corrupted AOF File

**Symptoms**:
- Redis fails to start
- Logs show: "Bad file format reading the append only file"

**Recovery**:
```bash
# 1. Try auto-repair
docker exec kato-redis redis-check-aof --fix /data/appendonly.aof

# 2. If repair fails, restore from backup
./scripts/restore_redis.sh <timestamp>

# 3. If no backup, delete AOF and load from RDB (data loss)
docker exec kato-redis rm /data/appendonly.aof
docker restart kato-redis
```

---

## Best Practices

### 1. Automated Backups ✅
```bash
# Add to crontab
0 2 * * * cd /path/to/kato && ./scripts/backup_redis.sh
```

### 2. Offsite Backup Storage ✅
```bash
# Copy backups to S3/NAS after creation
aws s3 sync ./backups/redis/ s3://my-bucket/kato-redis-backups/
```

### 3. Test Restores Monthly ✅
```bash
# Verify backups are restorable
./scripts/restore_redis.sh <recent_backup>
```

### 4. Monitor Backup Health ✅
```bash
# Check last backup age
find ./backups/redis -maxdepth 1 -type d -mtime +1 | wc -l
```

### 5. Pre-Training Backups ✅
```bash
# Before major training sessions
./scripts/backup_redis.sh
```

---

## Future Improvements (Proposed)

### Option 1: Store Emotives/Metadata in ClickHouse (Redundancy)

**Pros**:
- Emotives/metadata become recoverable
- ClickHouse provides long-term durability
- Can rebuild Redis from ClickHouse completely

**Cons**:
- Schema change required
- Migration needed for existing data
- Slightly higher write latency

**Implementation**: See `docs/proposals/clickhouse-emotives-metadata.md`

### Option 2: Redis Cluster with Replication

**Pros**:
- High availability
- Automatic failover
- No single point of failure

**Cons**:
- More complex setup
- Higher resource usage
- Requires 3+ Redis instances

### Option 3: Redis Persistence to Cloud Storage

**Pros**:
- Offsite durability
- Automated cloud backups
- Point-in-time recovery

**Cons**:
- Vendor lock-in
- Network dependency
- Additional cost

---

## Monitoring

### Key Metrics to Track

```bash
# Last save time (should be recent)
docker exec kato-redis redis-cli INFO persistence | grep rdb_last_save_time

# AOF status
docker exec kato-redis redis-cli INFO persistence | grep aof_enabled

# Key count (should not drop unexpectedly)
docker exec kato-redis redis-cli DBSIZE

# Memory usage
docker exec kato-redis redis-cli INFO memory | grep used_memory_human
```

### Alerts to Configure

1. **No backup in 24 hours** → Critical
2. **Redis key count drops >10%** → Warning
3. **AOF rewrite failures** → Warning
4. **Memory usage >90%** → Critical

---

## Emergency Contacts & Resources

**Documentation**:
- This file: `docs/operations/redis-data-protection.md`
- Backup script: `scripts/backup_redis.sh`
- Restore script: `scripts/restore_redis.sh`
- Rebuild script: `scripts/populate_redis_symbols_from_clickhouse.py`

**When to Panic** 🚨:
- Redis has 0 keys AND no recent backup exists
- Emotives/metadata missing for critical kb_ids
- Cannot restore from any backup

**What Can Be Recovered**:
- ✅ Pattern sequences (from ClickHouse)
- ✅ Symbol frequencies (rebuilt from ClickHouse)
- ❌ Emotives (lost forever without backup)
- ❌ Metadata (lost forever without backup)
- ❌ Pattern frequency counts (lost forever)

---

## Conclusion

**Redis data loss is preventable** with proper backup practices, but **emotives and metadata are unrecoverable** without backups.

**Required Actions**:
1. Set up automated daily backups
2. Test restore procedures quarterly
3. Monitor backup health continuously
4. Consider implementing ClickHouse redundancy for emotives/metadata

**Last Updated**: January 15, 2026
