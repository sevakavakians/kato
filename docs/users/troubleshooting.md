# KATO Troubleshooting Guide

Comprehensive guide for diagnosing and resolving common KATO issues.

## Quick Diagnostics

### System Health Check

```bash
# Check if KATO is running
docker compose ps

# Check API health
curl http://localhost:8000/health

# Check processor status
curl http://localhost:8000/status

# View recent logs
docker compose logs kato --tail 50
```

## Common Issues and Solutions

### Service Won't Start

**Symptoms:**
- `Address already in use` / `Port already in use`
- `docker compose ps` shows `kato` absent or restarting
- `curl http://localhost:8000/health` refuses the connection

**Note on older guidance**: KATO used to run one container per configuration,
each on its own port, tracked in `~/.kato/instances.json`. That is gone. A single
service now serves every session, and per-session configuration replaces the
per-instance flags. `./start.sh` no longer accepts `--id`, `--port`,
`--recall-threshold` or similar; it takes a command (`start`, `stop`, `restart`,
`status`, `logs`, ...) and an optional service name. A bare `./start.sh` prints
help and starts nothing.

**Solutions:**

1. Check what is actually running:
```bash
docker compose ps
./start.sh status
curl -s http://localhost:8000/health
```

2. Find what holds port 8000:
```bash
lsof -i :8000
# Linux:
netstat -tulpn | grep 8000
```

   Usually it is an existing KATO. One service is all you need, so prefer
   restarting it over starting a second:
```bash
./start.sh restart kato
```

3. If you genuinely need a different port, change the published port in
   `docker-compose.yml` (the `ports:` entry for the `kato` service). There is no
   command-line flag for it.

4. Read the startup logs. A service that starts and exits usually says why:
```bash
docker compose logs kato --tail 50
```

   `Redis client is required but not available` means the dependencies are not up
   or `REDIS_ENABLED` is unset — start the whole stack with `./start.sh start`
   rather than the `kato` service alone.

5. Clean restart, keeping data:
```bash
./start.sh restart
```

   Or a full reset that **destroys all learned patterns**:
```bash
./start.sh clean-data   # empties Qdrant, Redis and ClickHouse
./start.sh clean-all    # the above, plus volumes, then restarts
```

#### Stale containers

```bash
# What exists, running or not
docker ps -a | grep kato

# Stop and remove this project's containers
./start.sh stop

# Remove exited containers if any linger
docker rm $(docker ps -a -q -f name=kato -f status=exited)
```

### Session Issues

#### `404` on a session that worked a moment ago

Sessions expire after `SESSION_TTL` (default 3600s). With
`SESSION_AUTO_EXTEND=true`, activity pushes the expiry out, so this normally means
the session sat idle.

```bash
# Does it still exist?
curl http://localhost:8000/sessions/$SESSION/exists
```

Treat it as recoverable: create a new session. Learned patterns are unaffected —
they belong to the `node_id`, not the session.

#### `400` creating a session or updating config

A parameter failed validation and the response names the field. Two that catch
people out: `recall_threshold` must be greater than zero (as of 6.0.0), and
`filter_pipeline` accepts only `minhash`, `jaccard`, `bloom`, `rapidfuzz`.

```bash
# What is actually in effect
curl http://localhost:8000/sessions/$SESSION/config
```

#### Updates to a session go missing

Two writers are sharing one `session_id`. A session supports **one concurrent
writer**; under multi-worker uvicorn the serialisation lock is per process and the
session is persisted whole, so concurrent writes can lose an update. Use one
session per concurrent writer — several sessions on the same `node_id` run
concurrently and still share learned patterns. See
[session management](../operations/session-management.md).

#### How many sessions are open?

```bash
curl http://localhost:8000/sessions/count
```

There is no endpoint that lists them; `GET /sessions` returns `405`.

### FastAPI Communication Issues

#### Timeout Errors

**Symptoms:**
- Request timeouts
- Slow API responses
- Connection refused errors

**Solutions:**

1. Check FastAPI service status:
```bash
docker logs kato --tail 20
docker logs kato-testing --tail 20
```

2. Restart container to reset state:
```bash
docker compose restart
```

3. Verify service health:
```bash
curl http://localhost:8000/health
curl http://localhost:8000/health
```

#### Test Runner Timeout

**Symptoms:**
- `./run_tests.sh` times out
- Tests rebuild Docker image every time
- Virtual environment hangs

**Solutions:**

1. Use optimized test runner:
```bash
cd tests
./test-harness.sh test  # Runs tests in container, no local dependencies needed
```

2. Ensure Docker image exists before testing:
```bash
docker images | grep kato
# If missing, build once:
docker compose build
```

3. Skip virtual environment if causing issues:
```bash
# Tests now use system Python3 directly
./test-harness.sh test tests/
```

### Container Issues

#### Container Won't Start

**Symptoms:**
- `docker ps` shows no KATO containers
- Error messages about container creation

**Solutions:**

1. Check Docker is running:
```bash
docker version
# If error, start Docker Desktop
```

2. Check for port conflicts:
```bash
lsof -i :8000
# Usually this is an existing KATO. Restart it rather than starting a second:
./start.sh restart kato
# To publish a different port, edit the `ports:` entry for the kato service in
# docker-compose.yml -- there is no command-line flag for it.
```

3. Rebuild image:
```bash
docker compose build --no-cache kato
./start.sh restart kato
```

4. Check disk space:
```bash
df -h
docker system df
# Clean if needed
docker system prune -a --volumes
```

#### Container Keeps Restarting

**Symptoms:**
- Container status shows "Restarting"
- Logs show repeated startup attempts

**Solutions:**

1. Check logs for errors:
```bash
docker logs kato --tail 100
```

2. Check memory limits:
```bash
docker stats kato
# Increase if needed in docker compose.yml
```

3. Verify database connections:
```bash
# Check database services are running
docker compose ps
docker compose logs
```

### API Issues

#### Connection Refused

**Symptoms:**
- `curl: (7) Failed to connect to localhost port 8001`
- Browser shows "Unable to connect"

**Solutions:**

1. Verify container is running:
```bash
docker ps | grep kato
```

2. Check port mapping:
```bash
docker port kato
docker port kato-testing
```

3. Test internal connectivity:
```bash
docker exec kato curl localhost:8000/health
```

4. Check firewall:
```bash
# macOS
sudo pfctl -s rules
# Linux
sudo iptables -L
```

#### 404 Errors

**Symptoms:**
- API returns 404 for valid endpoints
- "Processor not found" errors

**Solutions:**

1. Verify processor ID:
```bash
# Check environment
docker exec kato env | grep PROCESSOR
```

2. Use correct endpoint URLs. Observation, STM and prediction endpoints are
   session-scoped -- there are no top-level `/observe`, `/stm` or `/predictions`
   routes, and requesting them returns `404`:
```bash
SESSION=$(curl -s -X POST http://localhost:8000/sessions \
  -H "Content-Type: application/json" -d '{"node_id": "my_node"}' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["session_id"])')

curl -X POST http://localhost:8000/sessions/$SESSION/observe \
  -H "Content-Type: application/json" -d '{"strings": ["hello"]}'
curl http://localhost:8000/sessions/$SESSION/stm
curl http://localhost:8000/sessions/$SESSION/predictions
```

   The full route list is at http://localhost:8000/docs.

3. Check service health:
```bash
# Health check endpoints
curl http://localhost:8000/health
curl http://localhost:8000/health
```

### Performance Issues

#### High Latency

**Symptoms:**
- Slow API responses (>100ms)
- Timeouts on requests

**Solutions:**

1. Check resource usage:
```bash
docker stats kato
```

2. Optimize configuration:
```bash
docker compose restart \
  --indexer-type VI \
  --max-predictions 50 \
  --recall-threshold 0.3
```

3. Check async processing:
```bash
# Look for processing issues in logs
docker logs kato | grep -i "error\|warning"
```

4. Reduce load:
```python
# Batch observations instead of individual calls
# Use session/connection reuse
```

#### High Memory Usage

**Symptoms:**
- Container using >2GB RAM
- Out of memory errors

**Solutions:**

1. Clear memory:
```bash
curl -X POST http://localhost:8000/clear-all
```

2. Limit pattern length:
```bash
docker compose restart --max-seq-length 100
```

3. Reduce pattern count:
```python
# Periodically clear old patterns
# Implement pattern rotation
```

### FastAPI Performance Issues

#### High Latency

**Symptoms:**
- Slow API responses (>100ms)
- Request timeouts

**Solutions:**

1. Check resource usage:
```bash
docker stats kato
docker stats kato-testing
```

2. Monitor async processing:
```bash
docker logs kato | grep "Processing time"
```

3. Restart to clear state:
```bash
docker compose restart
```

#### Memory Issues

**Symptoms:**
- Container using excessive memory
- Out of memory errors

**Solutions:**

1. Check memory usage:
```bash
docker stats --no-stream
```

2. Clear processor memory:
```bash
curl -X POST http://localhost:8000/clear-all
```

### Testing Issues (Clustered Test Harness)

#### Clustered Tests Not Running

**Symptoms:**
- "0 passed, 0 failed, 0 skipped" despite tests existing
- Tests not being discovered by clusters
- "No cluster definitions found" error

**Solutions:**

1. Check test cluster configuration:
```bash
# Verify test_clusters.py has correct paths
cat tests/tests/fixtures/test_clusters.py | grep test_patterns
```

2. Rebuild test harness container:
```bash
./test-harness.sh build
```

3. Run with verbose output to see cluster execution:
```bash
./test-harness.sh --verbose test
# OR for direct console output:
./test-harness.sh --no-redirect test
```

4. Check specific cluster is working:
```bash
# Test default cluster only
./test-harness.sh test tests/tests/unit/test_observations.py
```

#### Database Connection Issues in Tests

**Symptoms:**
- Tests timeout connecting to databases
- "Connection refused" errors
- Tests hang at database operations

**Solutions:**

1. Ensure Docker network exists:
```bash
docker network create kato-network
```

2. Check containers are on same network:
```bash
docker inspect kato-cluster_default_<id> | grep NetworkMode
```

3. Verify database containers are running:
```bash
docker ps | grep cluster
docker compose ps
```

4. Check environment variables in test container:
```bash
docker exec <test-container> env | grep -E "(QDRANT|REDIS|CLICKHOUSE)"
```

#### Result Aggregation Shows Zero

**Symptoms:**
- Individual tests pass but totals show "0 passed"
- "No tests passed. Check test configuration" warning

**Solutions:**

1. Update to latest test harness scripts:
```bash
git pull
./test-harness.sh build
```

2. Check cluster-orchestrator.sh is using process substitution:
```bash
grep "while.*read.*cluster_json" cluster-orchestrator.sh
# Should see: done < <(echo "$clusters_json" ...)
# NOT: done | while read
```

3. Run single test to verify aggregation:
```bash
./test-harness.sh --no-redirect test tests/tests/unit/test_observations.py::test_observe_single_string
```

#### Tests Failing Due to Contamination

**Symptoms:**
- Tests pass individually but fail when run together
- Unpredictable test failures
- "Pattern already exists" errors

**Solutions:**

1. Verify cluster isolation is working:
```bash
# Each cluster should have unique session_id
./test-harness.sh --verbose test 2>&1 | grep "Processor ID:"
```

2. Check test fixtures are using unique processor IDs:
```bash
grep "session_id" tests/tests/fixtures/kato_fixtures.py
# Should generate unique IDs per test
```

3. Clear all test data and retry:
```bash
./test-harness.sh stop  # Stop all test instances
docker rm $(docker ps -aq -f name=cluster_)  # Remove test containers
./test-harness.sh test
```

#### Cluster Configuration Not Applied

**Symptoms:**
- Tests fail with wrong recall_threshold
- Configuration changes not taking effect
- Tests in wrong cluster

**Solutions:**

1. Verify test is in correct cluster:
```bash
grep -n "your_test.py" tests/tests/fixtures/test_clusters.py
```

2. Add test to appropriate cluster:
```python
# In test_clusters.py
TestCluster(
    name="custom_config",
    config={"recall_threshold": 0.5},
    test_patterns=["tests/unit/your_test.py"],
    description="Tests requiring custom config"
)
```

3. Check cluster configuration is applied:
```bash
./test-harness.sh --verbose test 2>&1 | grep "Configuration:"
```

#### Auto-Learning Tests Failing

**Symptoms:**
- `test_max_pattern_length` tests fail
- Short-term memory doesn't clear when reaching max_pattern_length
- Auto-learning not triggered

**Root Causes and Solutions:**

1. **Docker Container Not Including Code Changes**

*Problem:* Modified code not appearing in running container due to Docker layer caching.

*Symptoms:*
- Code changes don't take effect after restart
- Debug logs missing from container output
- Config updates work locally but not in container

*Solution:* Rebuild Docker image from scratch:
```bash
docker system prune -f
docker rmi kato:latest
docker compose build --no-cache
docker compose restart
```

2. **Test Isolation Issues with Config Values**

*Problem:* Config values persist between tests, causing unpredictable failures.

*Symptoms:*
- Tests pass individually but fail when run together
- Config values from previous tests affect subsequent tests
- Intermittent test failures

*Solution:* Modified `kato_fixtures.py` to handle config isolation:
```python
def clear_all_memory(self, reset_config: bool = True) -> str:
    """Clear all memory and optionally reset config to defaults."""
    if reset_config:
        self.reset_config_to_defaults()
    # ... rest of method
```

#### Verification Commands

After fixing auto-learning issues, verify with:

```bash
# 1. Test config updates work
curl -X POST http://localhost:8000/sessions/{session_id}/config \
  -H "Content-Type: application/json" \
  -d '{"config": {"max_pattern_length": 3}}'

# 2. Verify config value changed  
curl http://localhost:8000/sessions/{session_id}/config

# 3. Run specific auto-learning tests
./run_tests.sh --no-start --no-stop tests/tests/unit/ -k "test_max_pattern_length" -v
```

#### Sorting Assertions Fail

**Symptoms:**
- Tests fail on string order assertions
- "Expected ['a', 'b'] but got ['b', 'a']"

**Solutions:**

Use test helpers:
```python
from fixtures.test_helpers import assert_short_term_memory_equals

# This handles sorting automatically
assert_short_term_memory_equals(actual, expected)
```

### Configuration Issues

#### Parameters Not Taking Effect

**Symptoms:**
- Configuration changes don't affect behavior
- Default values being used

**Solutions:**

1. Set the parameter in the right place. Processing parameters are per session,
   not command-line flags -- `./start.sh` does not accept `--max-predictions` or
   any other configuration flag:
```bash
# Per session, at creation
curl -X POST http://localhost:8000/sessions \
  -H "Content-Type: application/json" \
  -d '{"node_id": "my_node", "config": {"max_predictions": 50}}'

# Or on an existing session (POST, not PUT)
curl -X POST http://localhost:8000/sessions/$SESSION/config \
  -H "Content-Type: application/json" \
  -d '{"config": {"max_predictions": 50}}'
```

   An unknown or out-of-range value is rejected with `400` naming the field, so a
   typo fails at the call rather than silently reverting to a default.

2. Verify what is actually in effect:
```bash
curl http://localhost:8000/sessions/$SESSION/config
```

   For the service-wide defaults behind it, see
   [configuration-vars.md](../reference/configuration-vars.md).

3. Check environment variables:
```bash
docker exec kato env | grep KATO
```

## Debug Commands

### Container Inspection

```bash
# Full container details
docker inspect kato

# Check mounts
docker inspect kato | jq '.[0].Mounts'

# Check environment
docker inspect kato | jq '.[0].Config.Env'

# Check networking
docker inspect kato | jq '.[0].NetworkSettings'
```

### Process Investigation

```bash
# Check running processes
docker exec kato ps aux

# Check open files
docker exec kato lsof

# Check network connections
docker exec kato netstat -an
```

### Log Analysis

```bash
# Search for errors
docker logs kato 2>&1 | grep -i error

# Check recent activity
docker logs kato --since 5m

# Follow logs in real-time
docker logs kato -f

# Save logs for analysis
docker logs kato > kato-debug.log 2>&1
```

## Recovery Procedures

### Clean Restart

```bash
# Complete cleanup and restart. clean-all removes volumes, so every learned
# pattern is destroyed; use `./start.sh restart` if you only need a bounce.
./start.sh clean-all
```

### Data Recovery

Contact your system administrator to restore data from backups. KATO's persistent databases should be included in regular backup procedures.

### Emergency Shutdown

```bash
# Force stop all KATO containers
docker stop $(docker ps -q --filter "name=kato")

# Remove all KATO containers
docker rm -f $(docker ps -aq --filter "name=kato")

# Or use docker compose
docker compose down
```

## Diagnostic Scripts

### Health Check Script

```bash
#!/bin/bash
# save as check-kato-health.sh

echo "=== KATO Health Check ==="

# Check Docker
echo -n "Docker: "
docker version > /dev/null 2>&1 && echo "OK" || echo "FAIL"

# Check containers
echo -n "KATO Primary: "
docker ps | grep -q kato && echo "Running" || echo "Not Running"

echo -n "KATO Testing: "
docker ps | grep -q kato-testing && echo "Running" || echo "Not Running"

# Check API
echo -n "API Health: "
curl -s http://localhost:8000/health > /dev/null 2>&1 && echo "OK" || echo "FAIL"

# Check disk space
echo "Disk Usage:"
df -h / | tail -1

# Check memory
echo "Memory Usage:"
docker stats --no-stream kato kato-testing 2>/dev/null || echo "Containers not running"
```

### Performance Check Script

```python
#!/usr/bin/env python3
# save as check-kato-performance.py

import time
import requests
from statistics import mean, stdev

BASE_URL = "http://localhost:8000"

def time_operation(func, iterations=10):
    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        try:
            func()
            duration = (time.perf_counter() - start) * 1000
            times.append(duration)
        except:
            times.append(-1)
    
    valid_times = [t for t in times if t > 0]
    if not valid_times:
        return {"error": "All operations failed"}
    
    return {
        "mean": mean(valid_times),
        "stdev": stdev(valid_times) if len(valid_times) > 1 else 0,
        "min": min(valid_times),
        "max": max(valid_times),
        "success_rate": len(valid_times) / len(times) * 100
    }

# Test operations
def test_ping():
    requests.get(f"{BASE_URL}/health")

def test_observe():
    requests.post(f"{BASE_URL}/observe",
                  json={"strings": ["test"], "vectors": [], "emotives": {}})

def test_predictions():
    requests.get(f"{BASE_URL}/predictions")

# Run tests
print("KATO Performance Check")
print("=" * 40)

for name, func in [("Ping", test_ping), 
                   ("Observe", test_observe), 
                   ("Predictions", test_predictions)]:
    stats = time_operation(func)
    if "error" in stats:
        print(f"{name}: {stats['error']}")
    else:
        print(f"{name}: {stats['mean']:.2f}ms ± {stats['stdev']:.2f}ms "
              f"(success: {stats['success_rate']:.0f}%)")
```

## Getting Help

### Log Collection for Support

When reporting issues, collect:

```bash
# System info
uname -a
docker version
docker compose version

# KATO logs
docker logs kato --tail 1000 > kato.log
docker logs kato-testing --tail 1000 > kato-testing.log

# Database logs
docker compose logs --tail 1000 > database.log

# Container details
docker inspect kato > container-primary.json
docker inspect kato-testing > container-testing.json

# Configuration (service-wide env, and one session's resolved config)
docker exec kato env | grep -E 'KATO|REDIS|CLICKHOUSE|QDRANT' > env.txt
curl -s http://localhost:8000/sessions/$SESSION/config > session-config.json
```

### Where to Get Help

1. Check this troubleshooting guide
2. Review [System Overview](../developers/architecture.md)
3. Search existing GitHub issues
4. Open new issue with diagnostic information
5. Include logs and configuration

## Preventive Measures

### Regular Maintenance

1. **Monitor logs regularly**
```bash
# Set up log rotation
docker logs kato 2>&1 | rotatelogs -n 5 /var/log/kato.log 86400
```

2. **Clear old data periodically**
```bash
# Weekly cleanup script
docker compose down
docker system prune -a --volumes
./start.sh start
```

3. **Update regularly**
```bash
git pull
docker compose build
docker compose restart
```

### Monitoring Setup

1. **Health check endpoint monitoring**
2. **Resource usage alerts**
3. **Error rate tracking**
4. **Performance baseline establishment**

## Related Documentation

- [Docker Deployment](../operations/docker-deployment.md) - Container management
- [Configuration](../operations/configuration.md) - Parameter tuning
- [Performance](../reference/performance-guide.md) - Optimization strategies
- [Testing](../developers/testing.md) - Test troubleshooting