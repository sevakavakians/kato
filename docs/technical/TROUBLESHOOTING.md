# KATO Troubleshooting Guide

Comprehensive guide for diagnosing and resolving common KATO issues.

## Quick Diagnostics

### System Health Check

```bash
# Check if KATO is running
./kato-manager.sh status

# Check API health
curl http://localhost:8000/kato-api/ping

# Check specific processor
curl http://localhost:8000/p46b6b076c/ping

# View recent logs
./kato-manager.sh logs kato --tail 50
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
./kato-manager.sh start --id my-processor
```

3. Specify unique port manually:
```bash
./kato-manager.sh start --id my-processor --port 8005
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
curl http://localhost:8001/{processor-id}/ping
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
./kato-manager.sh start --id new-processor
```

3. Stop conflicting instance:
```bash
./kato-manager.sh list
./kato-manager.sh stop conflicting-processor  # By ID or name
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
./kato-manager.sh stop processor-1
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

### ZeroMQ Communication Issues

#### Timeout Errors with REQ/REP Pattern

**Symptoms:**
- "Resource temporarily unavailable" errors
- Tests timing out after 2 minutes
- `/connect` endpoint hanging

**Solutions:**

1. Switch to improved ROUTER/DEALER implementation (default):
```bash
export KATO_ZMQ_IMPLEMENTATION=improved
./kato-manager.sh restart
```

2. If issues persist, check ZMQ server status:
```bash
docker exec kato-api-${USER}-1 ps aux | grep zmq
docker logs kato-api-${USER}-1 --tail 20 | grep "ZMQ"
```

3. Restart container to clear connection state:
```bash
./kato-manager.sh restart
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
./kato-manager.sh build
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
./kato-manager.sh start --port 9000
```

3. Rebuild image:
```bash
./kato-manager.sh clean
./kato-manager.sh build --no-cache
./kato-manager.sh start
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
- `curl: (7) Failed to connect to localhost port 8000`
- Browser shows "Unable to connect"

**Solutions:**

1. Verify container is running:
```bash
docker ps | grep kato
```

2. Check port mapping:
```bash
docker port kato-api-${USER}-1
```

3. Test internal connectivity:
```bash
docker exec kato-api-${USER}-1 curl localhost:8000/kato-api/ping
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

2. Use correct processor ID in URLs:
```bash
# Wrong
curl http://localhost:8000/wrong-id/observe

# Right
curl http://localhost:8000/p46b6b076c/observe
```

3. Check API base path:
```bash
# Some endpoints need /kato-api prefix
curl http://localhost:8000/kato-api/ping
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
./kato-manager.sh restart \
  --indexer-type VI \
  --max-predictions 50 \
  --recall-threshold 0.3
```

3. Check connection pool:
```bash
# Look for connection pool issues in logs
docker logs kato-api-${USER}-1 | grep -i pool
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
curl -X POST http://localhost:8000/p46b6b076c/memory/clear-all
```

2. Limit pattern length:
```bash
./kato-manager.sh restart --max-seq-length 100
```

3. Reduce pattern count:
```python
# Periodically clear old patterns
# Implement pattern rotation
```

### ZeroMQ Issues

#### Resource Temporarily Unavailable

**Symptoms:**
- Error: "Resource temporarily unavailable"
- ZMQ timeout errors

**Solutions:**

1. Check ZMQ server:
```bash
docker exec kato-api-${USER}-1 ps aux | grep zmq
```

2. Test ZMQ connectivity:
```bash
docker exec kato-api-${USER}-1 python3 -c "
import zmq
ctx = zmq.Context()
sock = ctx.socket(zmq.REQ)
sock.connect('tcp://localhost:5555')
print('Connected successfully')
"
```

3. Restart with fresh connections:
```bash
./kato-manager.sh restart
```

#### Connection Pool Exhaustion

**Symptoms:**
- "No available connections" errors
- Increasing latency over time

**Solutions:**

1. Check pool statistics:
```bash
docker logs kato-api-${USER}-1 | grep "Connection pool"
```

2. Increase pool size or restart:
```bash
./kato-manager.sh restart
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

### Testing Issues

#### Tests Failing

**Symptoms:**
- pytest failures
- Import errors in tests

**Solutions:**

1. Check test environment:
```bash
cd tests
./test-harness.sh shell
# Then inside container:
python -m pytest --version
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Run specific test:
```bash
./test-harness.sh test tests/tests/unit/test_observations.py -v
```

4. Check KATO is running:
```bash
./kato-manager.sh status
```

#### Auto-Learning Tests Failing

**Symptoms:**
- `test_max_pattern_length` tests fail
- Short-term memory doesn't clear when reaching max_pattern_length
- Auto-learning not triggered

**Root Causes and Solutions:**

1. **Method Name Mismatch in REST Gateway**

*Problem:* REST gateway calls wrong ZMQ method name (`gene_change` instead of `change_gene`).

*Symptoms:*
```bash
# Gene updates fail silently
curl -X POST http://localhost:8000/p5f2b9323c3/genes/change \
  -d '{"data": {"max_pattern_length": 3}}'
# Returns success but gene value unchanged
```

*Solution:* Fixed in `kato/workers/rest_gateway.py:463-466`:
```python
# OLD (incorrect)
response = pool.execute('gene_change', gene_name, gene_value)

# NEW (correct)  
response = pool.execute('change_gene', gene_name, gene_value)
```

2. **Docker Container Not Including Code Changes**

*Problem:* Modified code not appearing in running container due to Docker layer caching.

*Symptoms:*
- Code changes don't take effect after restart
- Debug logs missing from container output
- Gene updates work locally but not in container

*Solution:* Rebuild Docker image from scratch:
```bash
/usr/local/bin/docker system prune -f
/usr/local/bin/docker rmi kato:latest
/usr/local/bin/docker build --no-cache -t kato:latest /Users/sevakavakians/PROGRAMMING/kato
./kato-manager.sh restart
```

3. **Test Isolation Issues with Gene Values**

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

And updated problematic tests:
```python
def test_max_pattern_length(kato_fixture):
    # Clear memory first, then set gene (don't call clear_all_memory after)
    kato_fixture.clear_short_term_memory()  # Only clear STM, not genes
    kato_fixture.update_genes({"max_pattern_length": 3})
    # ... rest of test
```

4. **ZMQ Communication Failures**

*Problem:* "Resource temporarily unavailable" errors preventing processor communication.

*Symptoms:*
```bash
curl http://localhost:8000/p5f2b9323c3/ping
# Returns HTML error page instead of JSON
```

*Solution:* Restart KATO with proper processor ID:
```bash
PROCESSOR_ID=p5f2b9323c3 PROCESSOR_NAME=P1 ./kato-manager.sh restart
```

#### Verification Commands

After fixing auto-learning issues, verify with:

```bash
# 1. Test gene updates work
curl -X POST http://localhost:8000/p5f2b9323c3/genes/change \
  -d '{"data": {"max_pattern_length": 3}}'

# 2. Verify gene value changed  
curl http://localhost:8000/p5f2b9323c3/gene/max_pattern_length

# 3. Test auto-learning behavior
python3 test_p1_processor.py

# 4. Run specific auto-learning tests
./test-harness.sh test tests/ -k "test_max_pattern_length" -v
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
./kato-manager.sh start --max-predictions 50

# Wrong: uses underscores
./kato-manager.sh start --max_predictions 50
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
./kato-manager.sh stop
./kato-manager.sh clean
./kato-manager.sh build
./kato-manager.sh start
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
echo -n "KATO Container: "
docker ps | grep -q kato-api && echo "Running" || echo "Not Running"

echo -n "MongoDB Container: "
docker ps | grep -q mongo-kb && echo "Running" || echo "Not Running"

# Check API
echo -n "API Health: "
curl -s http://localhost:8000/kato-api/ping > /dev/null 2>&1 && echo "OK" || echo "FAIL"

# Check disk space
echo "Disk Usage:"
df -h / | tail -1

# Check memory
echo "Memory Usage:"
docker stats --no-stream kato-api-${USER}-1 2>/dev/null || echo "Container not running"
```

### Performance Check Script

```python
#!/usr/bin/env python3
# save as check-kato-performance.py

import time
import requests
from statistics import mean, stdev

BASE_URL = "http://localhost:8000"
PROCESSOR_ID = "p46b6b076c"

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
    requests.get(f"{BASE_URL}/kato-api/ping")

def test_observe():
    requests.post(f"{BASE_URL}/{PROCESSOR_ID}/observe",
                  json={"strings": ["test"], "vectors": [], "emotives": {}})

def test_predictions():
    requests.get(f"{BASE_URL}/{PROCESSOR_ID}/predictions")

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
docker logs kato-api-${USER}-1 --tail 1000 > kato.log

# MongoDB logs
docker logs mongo-kb-${USER}-1 --tail 1000 > mongo.log

# Container details
docker inspect kato-api-${USER}-1 > container.json

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
./kato-manager.sh stop
docker system prune -a --volumes
./kato-manager.sh start
```

3. **Update regularly**
```bash
git pull
./kato-manager.sh build
./kato-manager.sh restart
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