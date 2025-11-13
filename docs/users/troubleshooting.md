# KATO Troubleshooting Guide

Comprehensive guide for diagnosing and resolving common KATO issues.

## Quick Diagnostics

### System Health Check

```bash
# Check if KATO is running
docker-compose ps

# Check API health
curl http://localhost:8000/health

# Check processor status
curl http://localhost:8000/status

# View recent logs
docker-compose logs kato --tail 50
```

## Common Issues and Solutions

### Multi-Instance Issues

#### Instance Won't Start

**Symptoms:**
- Error: "Port already in use"
- Container name conflicts
- Instance not appearing in list

**Solutions:**

1. Check existing instances:
```bash
./kato-manager.sh list
docker ps | grep kato
```

2. Use automatic port allocation:
```bash
# Don't specify port - let KATO find available one
./start.sh --id my-processor
```

3. Specify unique port manually:
```bash
./start.sh --id my-processor --port 8005
```

4. Clean up orphaned instances:
```bash
# Remove from registry if container doesn't exist
rm ~/.kato/instances.json
./kato-manager.sh list  # Recreates clean registry
```

#### Instance Not Found

**Symptoms:**
- Instance disappeared from list
- API calls return 404

**Solutions:**

1. Check registry file:
```bash
cat ~/.kato/instances.json
```

2. Re-register running container:
```bash
# Container exists but not in registry
docker ps | grep kato-my-processor
# Restart to re-register
docker restart kato-my-processor
```

3. Verify processor ID in API calls:
```bash
# Ensure using correct ID
curl http://localhost:8000/{processor-id}/ping
```

#### Port Conflicts

**Symptoms:**
- "Address already in use" error
- Can't start new instance

**Solutions:**

1. Find what's using the port:
```bash
lsof -i :8000
# Or on Linux:
netstat -tulpn | grep 8000
```

2. Use next available port:
```bash
# KATO automatically finds free port
./start.sh --id new-processor
```

3. Stop conflicting instance:
```bash
./kato-manager.sh list
docker-compose down conflicting-processor  # By ID or name
```

#### Stopped Containers Not Removed

**Note**: This issue should not occur with the updated stop command, which automatically removes containers.

**Symptoms:**
- Containers remain after stopping
- `docker ps -a` shows stopped KATO containers

**Solutions:**

1. Use the updated stop command:
```bash
# New stop command removes containers automatically
docker-compose down processor-1
```

2. Clean up old stopped containers manually:
```bash
# Remove all stopped KATO containers
docker rm $(docker ps -a -q -f name=kato- -f status=exited)
```

3. Reset registry to match actual containers:
```bash
rm ~/.kato/instances.json
./kato-manager.sh list  # Rebuilds registry
```

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
docker-compose restart
```

3. Verify service health:
```bash
curl http://localhost:8000/health
curl http://localhost:8000/health
```

#### Test Runner Timeout

**Symptoms:**
- `./kato-manager.sh test` times out
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
docker-compose build
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
# Kill conflicting process or use different port
./start.sh --port 9000
```

3. Rebuild image:
```bash
./kato-manager.sh clean
docker-compose build --no-cache
./start.sh
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
docker logs kato-api-${USER}-1 --tail 100
```

2. Check memory limits:
```bash
docker stats kato-api-${USER}-1
# Increase if needed in docker-compose.yml
```

3. Verify MongoDB connection:
```bash
docker logs mongo-kb-${USER}-1
docker exec mongo-kb-${USER}-1 mongo --eval "db.adminCommand('ping')"
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
docker exec kato-api-${USER}-1 env | grep PROCESSOR
```

2. Use correct endpoint URLs:
```bash
# FastAPI endpoints (no processor ID in URL)
curl http://localhost:8000/observe
curl http://localhost:8000/predictions
curl http://localhost:8000/stm
```

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
docker stats kato-api-${USER}-1
```

2. Optimize configuration:
```bash
docker-compose restart \
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
docker-compose restart --max-seq-length 100
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
docker-compose restart
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

### MongoDB Issues

#### Connection Failed

**Symptoms:**
- "MongoDB connection refused"
- "Unable to connect to database"

**Solutions:**

1. Check MongoDB container:
```bash
docker ps | grep mongo
docker logs mongo-kb-${USER}-1
```

2. Test connection:
```bash
docker exec mongo-kb-${USER}-1 mongo --eval "db.version()"
```

3. Restart MongoDB:
```bash
docker restart mongo-kb-${USER}-1
```

4. Check data volume:
```bash
docker volume ls | grep mongo
docker volume inspect kato-mongo-data
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
- Tests timeout connecting to MongoDB/Qdrant
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
docker ps | grep -E "(mongo|qdrant|redis)-cluster"
```

4. Check environment variables in test container:
```bash
docker exec <test-container> env | grep -E "(MONGO|QDRANT|REDIS)"
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
- Gene updates work locally but not in container

*Solution:* Rebuild Docker image from scratch:
```bash
docker system prune -f
docker rmi kato:latest
docker-compose build --no-cache
docker-compose restart
```

2. **Test Isolation Issues with Gene Values**

*Problem:* Gene values persist between tests, causing unpredictable failures.

*Symptoms:*
- Tests pass individually but fail when run together
- Gene values from previous tests affect subsequent tests
- Intermittent test failures

*Solution:* Modified `kato_fixtures.py` to handle gene isolation:
```python
def clear_all_memory(self, reset_genes: bool = True) -> str:
    """Clear all memory and optionally reset genes to defaults."""
    if reset_genes:
        self.reset_genes_to_defaults()
    # ... rest of method
```

#### Verification Commands

After fixing auto-learning issues, verify with:

```bash
# 1. Test gene updates work
curl -X POST http://localhost:8000/genes/update \
  -H "Content-Type: application/json" \
  -d '{"genes": {"max_pattern_length": 3}}'

# 2. Verify gene value changed  
curl http://localhost:8000/gene/max_pattern_length

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

1. Check parameter spelling:
```bash
# Correct: uses hyphens
./start.sh --max-predictions 50

# Wrong: uses underscores
./start.sh --max_predictions 50
```

2. Verify configuration:
```bash
./kato-manager.sh config
```

3. Check environment variables:
```bash
docker exec kato-api-${USER}-1 env | grep KATO
```

## Debug Commands

### Container Inspection

```bash
# Full container details
docker inspect kato-api-${USER}-1

# Check mounts
docker inspect kato-api-${USER}-1 | jq '.[0].Mounts'

# Check environment
docker inspect kato-api-${USER}-1 | jq '.[0].Config.Env'

# Check networking
docker inspect kato-api-${USER}-1 | jq '.[0].NetworkSettings'
```

### Process Investigation

```bash
# Check running processes
docker exec kato-api-${USER}-1 ps aux

# Check open files
docker exec kato-api-${USER}-1 lsof

# Check network connections
docker exec kato-api-${USER}-1 netstat -an
```

### Log Analysis

```bash
# Search for errors
docker logs kato-api-${USER}-1 2>&1 | grep -i error

# Check recent activity
docker logs kato-api-${USER}-1 --since 5m

# Follow logs in real-time
docker logs kato-api-${USER}-1 -f

# Save logs for analysis
docker logs kato-api-${USER}-1 > kato-debug.log 2>&1
```

## Recovery Procedures

### Clean Restart

```bash
# Complete cleanup and restart
docker-compose down
./kato-manager.sh clean
docker-compose build
./start.sh
```

### Data Recovery

```bash
# Backup MongoDB data
docker exec mongo-kb-${USER}-1 mongodump --out /backup
docker cp mongo-kb-${USER}-1:/backup ./mongo-backup

# Restore MongoDB data
docker cp ./mongo-backup mongo-kb-${USER}-1:/restore
docker exec mongo-kb-${USER}-1 mongorestore /restore
```

### Emergency Shutdown

```bash
# Force stop all KATO containers
docker stop $(docker ps -q --filter "name=kato")
docker stop $(docker ps -q --filter "name=mongo-kb")

# Remove all KATO containers
docker rm -f $(docker ps -aq --filter "name=kato")
docker rm -f $(docker ps -aq --filter "name=mongo-kb")
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

echo -n "MongoDB Container: "
docker ps | grep -q kato-mongodb && echo "Running" || echo "Not Running"

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
docker-compose version

# KATO logs
docker logs kato --tail 1000 > kato.log
docker logs kato-testing --tail 1000 > kato-testing.log

# MongoDB logs
docker logs kato-mongodb --tail 1000 > mongo.log

# Container details
docker inspect kato > container-primary.json
docker inspect kato-testing > container-testing.json

# Configuration
./kato-manager.sh config > config.json
```

### Where to Get Help

1. Check this troubleshooting guide
2. Review [System Overview](../SYSTEM_OVERVIEW.md)
3. Search existing GitHub issues
4. Open new issue with diagnostic information
5. Include logs and configuration

## Preventive Measures

### Regular Maintenance

1. **Monitor logs regularly**
```bash
# Set up log rotation
docker logs kato-api-${USER}-1 2>&1 | rotatelogs -n 5 /var/log/kato.log 86400
```

2. **Clear old data periodically**
```bash
# Weekly cleanup script
docker-compose down
docker system prune -a --volumes
./start.sh
```

3. **Update regularly**
```bash
git pull
docker-compose build
docker-compose restart
```

### Monitoring Setup

1. **Health check endpoint monitoring**
2. **Resource usage alerts**
3. **Error rate tracking**
4. **Performance baseline establishment**

## Related Documentation

- [Docker Deployment](../deployment/DOCKER.md) - Container management
- [Configuration](../deployment/CONFIGURATION.md) - Parameter tuning
- [Performance](PERFORMANCE.md) - Optimization strategies
- [Testing](../development/TESTING.md) - Test troubleshooting