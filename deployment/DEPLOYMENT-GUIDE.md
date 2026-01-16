# KATO Deployment Guide

## Quick Start (Recommended Method)

### 1. Clone the Repository
```bash
git clone https://github.com/your-org/kato.git
cd kato/deployment
```

### 2. Start KATO Services
```bash
./kato-manager.sh start
```

### 3. Verify Configuration (Before Training)
```bash
./kato-manager.sh verify
```

**Expected output:**
```
✓ Docker Memory Configuration
  Memory Limit: 8GB (recommended for training)
  ClickHouse Limit: 6GB (90% of container)

✓ System Log Configuration
  trace_log: Disabled or minimal activity ✓
  text_log: Disabled or minimal activity ✓

✓ Query Logging Filter
  Only logs queries > 1000ms ✓

✓ Redis Configuration
  Docker Memory Limit: 8GB ✓
  Redis maxmemory: 8GB ✓
  Eviction policy: allkeys-lru ✓
  AOF persistence: Enabled ✓

✓ Configuration optimized for training
```

If you see any warnings, the repository already includes the correct configuration files - they're automatically applied when you use `./kato-manager.sh`.

---

## Why Use kato-manager.sh?

The `kato-manager.sh` script ensures:
- ✅ **Correct memory limits** (8GB for both ClickHouse and Redis)
- ✅ **Disabled expensive logs** (text_log, trace_log, processors_profile_log, asynchronous_metric_log)
- ✅ **Query duration filtering** (only logs queries >1 second)
- ✅ **Redis eviction policy** (LRU eviction prevents crashes)
- ✅ **Proper configuration mounting** (from ./config/ directory)
- ✅ **Unified monitoring** (ClickHouse + Redis memory tracking)

**Without kato-manager.sh**, you may encounter:
- ❌ Memory exhaustion during training sessions
- ❌ Redis OOM crashes (no memory limits)
- ❌ Data loss (emotives, metadata unrecoverable)
- ❌ Rapid log accumulation (text_log: 379 MiB/hour, asynchronous_metric_log: 3.14M rows/hour)
- ❌ Training failures after ~20,000 observations

---

## Available Commands

```bash
./kato-manager.sh start              # Start all services
./kato-manager.sh status             # Check service health
./kato-manager.sh verify             # Verify memory config (run before training!)
./kato-manager.sh memory             # Check memory usage (one-time snapshot)
./kato-manager.sh monitor            # Watch memory in real-time (updates every 5s)
./kato-manager.sh clean-logs         # Clear system logs if memory is low
./kato-manager.sh logs kato 100      # View KATO logs
./kato-manager.sh restart clickhouse # Restart specific service
./kato-manager.sh stop               # Stop all services
./kato-manager.sh help               # Show all commands
```

---

## Upgrading KATO

### Option 1: Update Everything (Container + Configs)
```bash
cd kato/deployment
git pull origin main           # Get latest configs
./kato-manager.sh pull         # Pull latest container image
./kato-manager.sh restart      # Apply changes
./kato-manager.sh verify       # Verify config
```

### Option 2: Update Just KATO Container
```bash
./kato-manager.sh update       # Pulls latest image and restarts KATO
```

---

## Troubleshooting

### Memory Errors During Training

**Symptom:**
```
DatabaseError: memory limit exceeded: would use 3.60 GiB
```

**Solution:**
```bash
# 1. Check current configuration
./kato-manager.sh verify

# 2. If issues found, pull latest config
cd kato/deployment
git pull origin main

# 3. Restart services
./kato-manager.sh restart clickhouse

# 4. Verify fix
./kato-manager.sh verify
```

### Logs Filling Up Rapidly

**Symptom:**
- System logs growing >500 MiB during training
- text_log showing 100K+ debug messages per hour

**Solution:**
```bash
# 1. Verify logging configuration
./kato-manager.sh verify

# 2. If text_log is active, update configs
cd kato/deployment
git pull origin main  # Gets disabled text_log config

# 3. Restart ClickHouse
./kato-manager.sh restart clickhouse

# 4. Verify logs are disabled
./kato-manager.sh verify
```

---

## Memory Monitoring During Training

### Real-Time Monitoring

**Monitor memory usage during long training sessions:**
```bash
# In a separate terminal window
./kato-manager.sh monitor
```

**Output shows:**
- **ClickHouse**: Current RAM usage vs 8GB limit
- **ClickHouse**: Pattern data size on disk
- **ClickHouse**: System log accumulation
- **ClickHouse**: Active queries
- **Redis**: Memory usage, key count, evicted keys
- Updates every 5 seconds

### One-Time Memory Check

**Quick memory snapshot:**
```bash
./kato-manager.sh memory
```

**Shows:**
- **ClickHouse**: RAM usage with headroom percentage
- **ClickHouse**: Pattern data storage
- **ClickHouse**: System log sizes
- **ClickHouse**: Disk space available
- **ClickHouse**: Top 5 tables by size
- **Redis**: Memory usage, evicted keys, cache hit rate
- **Training recommendations** for both services

### Memory Headroom Indicators

- **Green (>50% available)**: Safe to continue training
- **Yellow (20-50% available)**: Monitor closely during training
- **Red (<20% available)**: Clear logs or training may fail

### When Memory is Low

**If memory headroom drops below 20%:**
```bash
./kato-manager.sh clean-logs
```

This clears ClickHouse system logs **without affecting pattern data**.

---

## ClickHouse System Logs Configuration

**Disabled Logs** (prevent excessive growth during training):
- ❌ **text_log**: Debug/trace messages (379 MiB/hour if enabled)
- ❌ **trace_log**: Query tracing data (2.81 GiB during training if enabled)
- ❌ **processors_profile_log**: Query profiling (348 MiB during training if enabled)
- ❌ **asynchronous_metric_log**: System metrics every second (3.14M rows/hour if enabled)

**Enabled Logs** (essential for monitoring and debugging):
- ✅ **query_log**: Slow queries (>1000ms only) with 7-day TTL
- ✅ **metric_log**: System metrics summary with 7-day TTL
- ✅ **part_log**: Table part operations with 3-day TTL
- ✅ **error_log**: Error messages

**Why These Choices:**
- Training sessions generate intensive write operations
- Disabled logs would consume GBs of memory and disk during training
- Enabled logs provide essential debugging without overhead
- TTL ensures automatic cleanup after retention period

---

## Important Files

The repository includes optimized configuration files:

```
deployment/
├── kato-manager.sh              # 🔧 Management script (USE THIS!)
├── docker-compose.yml           # ✅ 8GB memory limit configured
└── config/
    ├── clickhouse/
    │   ├── logging.xml          # ✅ Expensive logs disabled
    │   ├── users.xml            # ✅ Query duration filter
    │   └── init.sql             # Database schema
    └── redis.conf               # ✅ Enhanced persistence
```

**These files are NOT in container images** - you MUST use the repository deployment method.

---

## Container-Only Deployment (NOT RECOMMENDED)

If you try to deploy using only container images:

```bash
# ❌ INCOMPLETE DEPLOYMENT (missing configs)
docker pull ghcr.io/your-org/kato:latest
docker run ghcr.io/your-org/kato:latest
```

**Problems:**
- No ClickHouse memory limits → Memory errors during training
- Default logging enabled → Rapid log accumulation
- No Redis, Qdrant, or ClickHouse → KATO won't work

**Instead, use:**
```bash
# ✅ COMPLETE DEPLOYMENT (includes configs)
git clone https://github.com/your-org/kato.git
cd kato/deployment
./kato-manager.sh start
./kato-manager.sh verify
```

---

## For CI/CD / Automated Deployments

### Kubernetes / Docker Swarm

You'll need to:
1. Create ConfigMaps from repository config files
2. Mount ConfigMaps to ClickHouse container
3. Set memory limits in pod/service specs

Example ConfigMap:
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: clickhouse-config
data:
  logging.xml: |
    # Content from deployment/config/clickhouse/logging.xml
  users.xml: |
    # Content from deployment/config/clickhouse/users.xml
```

### Terraform / Ansible

Include configuration files as part of deployment:
```hcl
resource "local_file" "clickhouse_logging" {
  filename = "/opt/kato/config/clickhouse/logging.xml"
  content  = file("${path.module}/config/clickhouse/logging.xml")
}
```

---

## Production Checklist

Before running training sessions in production:

**ClickHouse:**
- [ ] Deployed using repository (not container-only)
- [ ] Ran `./kato-manager.sh verify` - all checks passed
- [ ] Docker memory limit: 8GB
- [ ] text_log disabled
- [ ] trace_log disabled
- [ ] asynchronous_metric_log disabled
- [ ] processors_profile_log disabled
- [ ] Query duration filter: 1000ms
- [ ] System logs < 2 MiB (after initial startup)

**Redis:**
- [ ] Docker memory limit: 8GB
- [ ] Redis maxmemory: 8GB (set in config/redis.conf)
- [ ] Eviction policy: allkeys-lru
- [ ] AOF persistence enabled
- [ ] Redis backups configured (see docs/operations/redis-data-protection.md)
- [ ] config/redis.conf mounted in docker-compose.yml

During training sessions:

- [ ] Run `./kato-manager.sh monitor` in separate terminal
- [ ] Check ClickHouse memory headroom remains >20%
- [ ] Monitor Redis evicted keys count (should be 0 initially)
- [ ] Check Redis cache hit rate (should be >90%)
- [ ] If ClickHouse memory low, run `./kato-manager.sh clean-logs`
- [ ] If Redis evictions spike, consider increasing Redis memory limit

---

## Getting Help

**Documentation:**
- Memory optimization: `docs/operations/redis-data-protection.md`
- API Reference: http://localhost:8000/docs (when running)
- Dashboard: http://localhost:3001 (when running)

**Commands:**
```bash
./kato-manager.sh help     # Show all commands
./kato-manager.sh verify   # Check configuration
./kato-manager.sh memory   # Check memory usage
./kato-manager.sh monitor  # Watch memory in real-time
./kato-manager.sh status   # Check service health
```

**Issues:**
- Check logs: `./kato-manager.sh logs kato`
- Verify config: `./kato-manager.sh verify`
- Check memory: `./kato-manager.sh memory`
- Report issue: https://github.com/your-org/kato/issues

---

## Summary

✅ **DO**: Use `./kato-manager.sh` for deployment
✅ **DO**: Run `verify` before training sessions
✅ **DO**: Keep repository configs updated with `git pull`

❌ **DON'T**: Deploy using container images only
❌ **DON'T**: Skip the `verify` step before training
❌ **DON'T**: Modify configs without understanding impact

**The kato-manager.sh script ensures your deployment is optimized for training workloads.**
