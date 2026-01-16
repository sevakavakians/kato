# Memory Monitoring Guide

## Overview

New memory monitoring commands have been added to `kato-manager.sh` to help track ClickHouse memory usage during training sessions.

## Available Commands

### 1. One-Time Memory Check
```bash
./kato-manager.sh memory
```

**Shows:**
- **RAM Usage**: Current memory vs 8GB limit
- **Headroom**: Available memory percentage with color coding
  - Green (>50%): Safe to continue training
  - Yellow (20-50%): Monitor closely
  - Red (<20%): Approaching limit, clear logs
- **Disk Usage**: Pattern data, system logs, total storage
- **Top 5 Tables**: Largest tables by disk usage
- **Training Guidance**: Real-time recommendations

**Example Output:**
```
RAM Usage (Operations):
  Current: 1.38GiB / 7.655GiB
  Container Limit: 8GB
  ClickHouse Limit: 6GB (90% of container)
  ClickHouse Tracked: 293.32 MiB

  Headroom: 81% available (healthy)

Disk Usage (Storage):
  Pattern Data: 34.18 MiB (47.62 thousand patterns)
  System Logs: 51.16 MiB
  Total ClickHouse: 85.34 MiB
  Available Disk: 59.22 GiB

Training Session Guidance:
  ✓ Memory headroom is healthy - safe to continue training
```

### 2. Continuous Monitoring
```bash
./kato-manager.sh monitor
```

**Features:**
- Updates every 5 seconds
- Real-time RAM usage tracking
- Pattern data growth monitoring
- System log accumulation tracking
- Active query count
- Press Ctrl+C to stop

**Use Case:** Run in a separate terminal window during long training sessions to watch memory usage in real-time.

### 3. Clear System Logs
```bash
./kato-manager.sh clean-logs
```

**What it does:**
- Truncates ClickHouse system logs (query_log, metric_log, trace_log, etc.)
- **Does NOT affect pattern data** (your training data is safe)
- Frees up RAM when memory headroom is low
- Requires confirmation (`yes` to proceed)

**When to use:**
- Memory headroom drops below 20%
- System logs exceed 500 MiB
- Memory warnings during training

## Training Workflow

### Before Training
```bash
./kato-manager.sh verify
```
Verify configuration is optimized (8GB memory, disabled logs, etc.)

### During Training
```bash
# Terminal 1: Run your training
python train.py

# Terminal 2: Monitor memory
./kato-manager.sh monitor
```

### If Memory Gets Low
```bash
./kato-manager.sh clean-logs
```

## Memory vs Disk

### ClickHouse RAM (8GB Limit)
- Used for: Query processing, write buffers, indexes
- Monitored by: `./kato-manager.sh memory`
- Limited to: 8GB per docker-compose.yml

### ClickHouse Disk (Unlimited)
- Used for: Pattern data storage
- Grows automatically via Docker volumes
- Your training data can exceed 8GB (stored on disk, not RAM)

### Redis RAM (8GB Limit)
- Used for: Pattern metadata, emotives, frequencies, session state
- Monitored by: `./kato-manager.sh memory`
- Limited to: 8GB per docker-compose.yml
- **Eviction**: When limit reached, least-recently-used keys are removed
- **Growth Pattern**: Proportional to pattern count (~208 bytes per pattern)

## Understanding the Output

### Memory Headroom
```
Headroom: 81% available (healthy)
```
- **81%**: This much RAM is still available for operations
- **Green**: Memory is healthy, safe to continue
- **Yellow**: Memory is moderate, monitor closely
- **Red**: Memory is low, consider clearing logs

### Pattern Data
```
Pattern Data: 34.18 MiB (47.62 thousand patterns)
```
- This is **disk storage**, not RAM
- Can grow to many gigabytes without issues
- ClickHouse compresses patterns efficiently

### System Logs
```
System Logs: 51.16 MiB
```
- This uses **both** disk and RAM
- Should stay under 100 MiB with optimized config
- Clear with `./kato-manager.sh clean-logs` if needed

### Redis Memory Usage
```
Redis Memory Usage:
  Used Memory: 15.23M
  Max Memory: 8.00G
  Memory Fragmentation: 1.05
  Total Keys: 47620
  Evicted Keys: 0
  Cache Hit Rate: 98%
```

**Understanding Redis Metrics:**
- **Used Memory**: Current RAM usage by Redis (pattern metadata, emotives, frequencies)
- **Max Memory**: Configured limit (8GB = 8.00G)
- **Memory Fragmentation**: Ratio of actual vs used memory (ideal: ~1.0)
  - <1.0: Good (memory is efficiently used)
  - 1.0-1.5: Normal
  - >1.5: High fragmentation (consider MEMORY PURGE or restart)
- **Total Keys**: Number of Redis keys (each pattern has ~4-5 keys)
- **Evicted Keys**: Keys removed due to memory limit
  - 0: Good (no memory pressure)
  - >0: Memory limit reached, old data being evicted
- **Cache Hit Rate**: Percentage of successful lookups
  - >90%: Excellent
  - 70-90%: Good
  - <70%: Poor (data being evicted too aggressively or cold cache)

## Troubleshooting

### High Memory Usage During Training
1. Check current usage: `./kato-manager.sh memory`
2. If headroom <20%, clear logs: `./kato-manager.sh clean-logs`
3. Verify config: `./kato-manager.sh verify`

### System Logs Growing Rapidly
**Check if expensive logs are enabled:**
```bash
./kato-manager.sh verify
```

**If text_log or trace_log are active:**
1. Update config files (already done in repository)
2. Restart ClickHouse: `./kato-manager.sh restart clickhouse`
3. Clear existing logs: `./kato-manager.sh clean-logs`

### Pattern Data vs Available RAM
**Pattern data on disk can exceed RAM limit!**

Example with 50GB of patterns:
- **Disk**: Stores 50GB of compressed pattern data
- **RAM**: Uses only ~2-3GB for active operations
- **Query Processing**: Loads data from disk as needed

The 8GB RAM limit is for operations, not data storage.

### Redis Evictions During Training

**Symptom:**
```
Evicted Keys: 15234
Cache Hit Rate: 65%
```

**Meaning:**
- Redis reached 8GB memory limit
- Started evicting least-recently-used pattern metadata
- Performance degraded (more ClickHouse queries needed)

**Solutions:**
1. **Increase Redis memory limit** (if host has available RAM):
   ```yaml
   # In docker-compose.yml
   redis:
     deploy:
       resources:
         limits:
           memory: 16G  # Increase from 8G
   ```
   Also update `config/redis.conf`:
   ```conf
   maxmemory 16gb
   ```

2. **Accept evictions** (old pattern metadata removed):
   - Training continues successfully
   - Older patterns have metadata recomputed on access
   - Normal behavior for very large datasets (50M+ patterns)

3. **Monitor eviction rate** during training:
   ```bash
   ./kato-manager.sh monitor
   ```
   If evictions spike suddenly, investigate pattern count growth.

### Redis High Memory Fragmentation

**Symptom:**
```
Memory Fragmentation: 2.35
```

**Meaning:**
- Redis allocated more memory than it's using
- Happens after many deletions/updates
- Not critical but wastes memory

**Solutions:**
1. **Restart Redis** (quickest):
   ```bash
   ./kato-manager.sh restart redis
   ```
   Note: Safe because data is persisted (RDB + AOF)

2. **Run MEMORY PURGE** (if restart not desired):
   ```bash
   docker exec kato-redis redis-cli MEMORY PURGE
   ```

### Redis Data Loss After Restart

**Symptom:**
- Redis shows 0 keys after container restart
- KATO can't see pattern metadata/emotives

**Causes:**
- Volume not mounted correctly
- AOF/RDB files corrupted
- `docker compose down -v` removed volumes

**Recovery:**
1. **Check if volume exists**:
   ```bash
   docker volume ls | grep redis
   ```

2. **Restore from backup**:
   ```bash
   ../scripts/restore_redis.sh /path/to/backup
   ```

3. **Rebuild from ClickHouse** (partial recovery):
   ```bash
   # Only rebuilds symbol frequencies
   # Emotives and metadata permanently lost
   python scripts/populate_redis_symbols_from_clickhouse.py --kb-id your_kb_id
   ```

## Disabled System Logs

KATO disables several ClickHouse system logs that would otherwise consume excessive resources during training:

### Disabled Logs
- **asynchronous_metric_log**: Would log 873 metrics/second (3.14M rows/hour, ~30 MiB/hour)
- **text_log**: Would log debug/trace messages (379 MiB/hour during training)
- **trace_log**: Would log query tracing data (2.81 GiB during training)
- **processors_profile_log**: Would log query profiling (348 MiB during training)

### Why Disabled
During training sessions with millions of pattern insertions:
- These logs would grow to multiple GiBs
- Background merge operations would consume memory
- No actionable debugging value for KATO operations
- TTL cleanup creates additional write load

### What You Still Have
- **query_log**: Slow queries (>1000ms) for performance debugging
- **metric_log**: System health metrics (memory, CPU, disk)
- **part_log**: Table merge operations
- **error_log**: Error messages
- **Live metrics**: `system.asynchronous_metrics` table (current values, not historical)

## Best Practices

1. **Always run verify before training:**
   ```bash
   ./kato-manager.sh verify
   ```

2. **Monitor during long sessions:**
   ```bash
   ./kato-manager.sh monitor  # In separate terminal
   ```

3. **Set thresholds:**
   - Green (>50%): Continue training
   - Yellow (20-50%): Watch closely, prepare to clear logs
   - Red (<20%): Clear logs immediately

4. **Regular log cleanup:**
   - Clear logs between training sessions
   - System logs don't contain pattern data (safe to delete)
   - Pattern data is stored separately (never auto-deleted)

5. **Check after config changes:**
   ```bash
   ./kato-manager.sh restart clickhouse
   ./kato-manager.sh verify
   ./kato-manager.sh memory
   ```

## Summary

The new memory monitoring commands provide real-time visibility into:
- RAM usage for operations (limited to 8GB)
- Disk usage for pattern storage (unlimited)
- System log accumulation
- Training session safety

Use `./kato-manager.sh monitor` during training to ensure you stay within memory limits and never lose training data.
