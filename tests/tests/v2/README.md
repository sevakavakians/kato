# KATO v2.0 Test Suites

## Overview

This directory contains comprehensive test suites that validate the KATO v2.0 specifications, particularly focusing on:

1. **Session Management** - Multi-user isolation with separate STMs
2. **Database Reliability** - Connection pooling, write guarantees, circuit breakers
3. **Error Handling** - Structured errors, graceful degradation, recovery patterns
4. **Multi-User Scenarios** - End-to-end integration tests with concurrent users
5. **Migration Validation** - Backward compatibility and safe migration paths

## Test Files

### Core Test Suites

#### `test_session_management.py`
Validates the critical requirement that multiple users can maintain separate STM sequences without collision.

**Key Test Classes:**
- `TestSessionIsolation` - Verifies complete data isolation between sessions
- `TestSessionLifecycle` - Tests session creation, expiration, and cleanup
- `TestSessionPersistence` - Validates STM persistence across requests
- `TestSessionLoadAndPerformance` - Load testing with 100+ concurrent sessions
- `TestBackwardCompatibility` - v1.0 API compatibility
- `TestSessionErrorHandling` - Error scenarios and recovery

**Critical Tests:**
- `test_basic_session_isolation` - Proves User A and User B maintain separate STMs
- `test_concurrent_session_operations` - 10 users building sequences concurrently
- `test_many_concurrent_sessions` - 100+ sessions active simultaneously

#### `test_database_reliability.py`
Ensures the database layer can handle production issues without data loss or crashes.

**Key Test Classes:**
- `TestConnectionPooling` - Connection pool limits and behavior
- `TestWriteConcerns` - Write guarantees (w=majority vs w=0)
- `TestCircuitBreaker` - Circuit breaker activation and recovery
- `TestRetryLogic` - Exponential backoff retry patterns
- `TestDatabaseFailureRecovery` - Graceful handling of outages
- `TestHealthMonitoring` - Database health detection and alerting

**Critical Tests:**
- `test_write_concern_majority` - Verifies writes use w=majority (not w=0)
- `test_circuit_breaker_opens_on_failures` - Circuit breaker prevents cascading failures
- `test_chaos_random_failures` - System handles 30% failure rate gracefully

#### `test_multi_user_scenarios.py`
End-to-end integration tests validating complex multi-user workflows.

**Key Test Classes:**
- `TestMultiUserIsolation` - Complete isolation validation
- `TestSessionHandoff` - Session migration between devices
- `TestPerformanceUnderLoad` - Performance with many users
- `TestEdgeCases` - Boundary conditions and special cases

**Critical Tests:**
- `test_concurrent_users_no_collision` - 10 users with unique sequences, no mixing
- `test_100_concurrent_active_users` - Performance benchmark with heavy load
- `test_burst_traffic_handling` - Response to sudden traffic spikes

## Running the Tests

### Prerequisites

1. **Install test dependencies:**
```bash
pip install -r tests/requirements.txt
```

2. **Start KATO services (for integration tests):**
```bash
./kato-manager.sh start
```

### Run All v2 Tests

```bash
# Run all v2.0 test suites
python -m pytest tests/tests/v2/ -v

# With coverage report
python -m pytest tests/tests/v2/ --cov=kato --cov-report=html
```

### Run Specific Test Suites

```bash
# Session management tests only
python -m pytest tests/tests/v2/test_session_management.py -v

# Database reliability tests only
python -m pytest tests/tests/v2/test_database_reliability.py -v

# Multi-user integration tests
python -m pytest tests/tests/v2/test_multi_user_scenarios.py -v
```

### Run by Test Category

```bash
# Unit tests only (fast, no external dependencies)
python -m pytest tests/tests/v2/ -m "not integration and not performance" -v

# Integration tests (requires running services)
python -m pytest tests/tests/v2/ -m integration -v

# Performance tests (may take longer)
python -m pytest tests/tests/v2/ -m performance -v

# Stress tests (heavy load, use with caution)
python -m pytest tests/tests/v2/ -m stress -v

# Chaos tests (inject failures)
python -m pytest tests/tests/v2/ -m chaos -v
```

### Run Specific Test Cases

```bash
# Test session isolation specifically
python -m pytest tests/tests/v2/test_session_management.py::TestSessionIsolation::test_basic_session_isolation -v

# Test database circuit breaker
python -m pytest tests/tests/v2/test_database_reliability.py::TestCircuitBreaker -v
```

## Test Markers

Tests are marked with categories for selective execution:

- `@pytest.mark.integration` - Requires running KATO services
- `@pytest.mark.performance` - Performance benchmarks
- `@pytest.mark.stress` - Heavy load tests
- `@pytest.mark.chaos` - Failure injection tests
- `@pytest.mark.asyncio` - Async test functions

## Expected Results

### Session Management
- ✅ Multiple users maintain completely separate STMs
- ✅ No data collision between concurrent sessions
- ✅ Sessions persist across requests
- ✅ Support for 100+ concurrent sessions
- ✅ Backward compatibility with v1.0 API

### Database Reliability
- ✅ Connection pooling with 50+ connections
- ✅ Write concern = majority (not 0)
- ✅ Circuit breaker opens after 5 failures
- ✅ Retry with exponential backoff
- ✅ Graceful degradation during outages

### Performance Targets
- ✅ 500+ operations per second
- ✅ <50ms session creation time
- ✅ <5x slowdown during traffic bursts
- ✅ <1% error rate under sustained load

## Debugging Failed Tests

### Session Isolation Failures

If session isolation tests fail:
1. Check that session IDs are unique
2. Verify session storage backend (Redis/memory)
3. Check for shared state in processor
4. Enable debug logging: `LOG_LEVEL=DEBUG pytest ...`

### Database Reliability Failures

If database tests fail:
1. Verify MongoDB is running: `docker ps | grep mongo`
2. Check connection string in settings
3. Verify write concern configuration
4. Check circuit breaker thresholds

### Performance Test Failures

If performance tests fail:
1. Check system resources (CPU, memory)
2. Verify no other heavy processes running
3. Adjust performance thresholds for your hardware
4. Run with profiling: `python -m cProfile -o profile.stats pytest ...`

## Continuous Integration

### GitHub Actions Workflow

```yaml
name: KATO v2.0 Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v2
    
    - name: Set up Python
      uses: actions/setup-python@v2
      with:
        python-version: '3.9'
    
    - name: Install dependencies
      run: |
        pip install -r requirements.txt
        pip install -r tests/requirements.txt
    
    - name: Start services
      run: |
        docker-compose up -d
        ./kato-manager.sh start
        sleep 10  # Wait for services
    
    - name: Run v2.0 tests
      run: |
        python -m pytest tests/tests/v2/ -v --tb=short
    
    - name: Stop services
      if: always()
      run: |
        ./kato-manager.sh stop
        docker-compose down
```

## Test Coverage Goals

Target coverage for v2.0 components:

- Session Management: >95%
- Database Layer: >90%
- Error Handling: >90%
- API Endpoints: >95%
- Integration Flows: >85%

## Contributing

When adding new tests:

1. Follow existing test patterns
2. Use appropriate markers (@pytest.mark.xxx)
3. Include docstrings explaining what's being tested
4. Verify tests pass in isolation and in suite
5. Update this README if adding new test categories

## Troubleshooting

### Common Issues

**Issue: "Session not found" errors**
- Solution: Ensure session creation completed before use
- Check session TTL settings

**Issue: "Connection pool exhausted"**
- Solution: Increase pool size in configuration
- Check for connection leaks in tests

**Issue: "Circuit breaker open"**
- Solution: Wait for recovery timeout (30s default)
- Check database connectivity

**Issue: Performance tests timeout**
- Solution: Increase timeout values for slower systems
- Reduce number of concurrent operations

## References

- [KATO v2.0 Architecture Specification](../../../docs/specifications/v2.0/ARCHITECTURE_SPEC_V2.md)
- [Session Management Specification](../../../docs/specifications/v2.0/SESSION_MANAGEMENT_SPEC.md)
- [Database Reliability Specification](../../../docs/specifications/v2.0/DATABASE_RELIABILITY_SPEC.md)
- [Migration Plan](../../../docs/specifications/v2.0/MIGRATION_PLAN.md)