# KATO Testing Guide

## Overview

KATO uses a simplified testing architecture where tests run in local Python and connect to running KATO services. This approach provides fast feedback, easy debugging, and complete isolation through unique processor IDs.

## Prerequisites

### 1. Start KATO Services
```bash
# Build and start all services (MongoDB, Qdrant, 3 KATO instances)
./kato-manager.sh build  # Only needed first time or after code changes
./kato-manager.sh start

# Verify services are running
./kato-manager.sh status

# Check health
curl http://localhost:8001/health  # Should return {"status": "healthy", ...}
```

### 2. Set Up Python Environment
```bash
# Create virtual environment (one-time setup)
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install -r tests/requirements.txt
```

## Running Tests

### Quick Start
```bash
# Run all tests (services must be running)
./run_simple_tests.sh --no-start --no-stop

# The --no-start flag skips starting KATO (already running)
# The --no-stop flag keeps KATO running after tests
```

### Running Specific Tests
```bash
# Run unit tests only
./run_simple_tests.sh --no-start --no-stop tests/tests/unit/

# Run integration tests only
./run_simple_tests.sh --no-start --no-stop tests/tests/integration/

# Run API tests only
./run_simple_tests.sh --no-start --no-stop tests/tests/api/

# Run a specific test file
./run_simple_tests.sh --no-start --no-stop tests/tests/unit/test_sorting_behavior.py

# Run with verbose output
./run_simple_tests.sh --no-start --no-stop -v tests/tests/unit/
```

### Direct pytest Usage
```bash
# Activate virtual environment
source venv/bin/activate

# Run all tests
python -m pytest tests/tests/ -v

# Run with specific options
python -m pytest tests/tests/unit/ -v --tb=short  # Short traceback
python -m pytest tests/tests/unit/ -v --tb=long   # Full traceback
python -m pytest tests/tests/unit/ -x             # Stop on first failure
python -m pytest tests/tests/unit/ --lf           # Run last failed tests

# Run specific test by name
python -m pytest tests/tests/unit/ -k "test_alphanumeric_sorting"

# Run tests in parallel (requires pytest-xdist)
python -m pytest tests/tests/unit/ -n auto
```

## Test Architecture

### How It Works

1. **Services Run in Docker**: MongoDB, Qdrant, and 3 KATO instances run in containers
2. **Tests Run Locally**: Python tests execute in your local environment
3. **Connection via HTTP**: Tests connect to KATO services on ports 8001-8003
4. **Automatic Isolation**: Each test gets a unique processor_id for complete database isolation

### Test Isolation

Each test automatically receives a unique processor_id that ensures:
- **MongoDB Isolation**: Database name = processor_id
- **Qdrant Isolation**: Collection name = `vectors_{processor_id}`
- **No Cross-Contamination**: Tests cannot affect each other
- **Parallel Safety**: Tests can run concurrently without issues

Example processor_id format: `test_sorting_behavior_1699123456789_a1b2c3d4`

### Test Fixture

The main test fixture (`kato_fixture`) provides a clean interface:

```python
def test_example(kato_fixture):
    # Clear all memory for this processor
    kato_fixture.clear_all_memory()
    
    # Send observation
    result = kato_fixture.observe({
        'strings': ['hello', 'world'],
        'vectors': [],
        'emotives': {'joy': 0.8}
    })
    
    # Learn pattern
    pattern = kato_fixture.learn()
    
    # Get predictions
    predictions = kato_fixture.get_predictions()
```

## Test Organization

```
tests/tests/
├── unit/                 # Unit tests for individual components
│   ├── test_observations.py
│   ├── test_predictions.py
│   ├── test_sorting_behavior.py
│   └── ...
├── integration/          # End-to-end workflow tests
│   ├── test_pattern_learning.py
│   ├── test_vector_e2e.py
│   └── ...
├── api/                  # REST API endpoint tests
│   └── test_rest_endpoints.py
├── performance/          # Performance and stress tests
│   └── test_high_load.py
└── fixtures/            # Test fixtures and helpers
    ├── kato_fixtures.py
    └── test_helpers.py
```

## Writing Tests

### Basic Test Structure
```python
import pytest
from fixtures.kato_fixtures import kato_fixture

def test_my_feature(kato_fixture):
    """Test description."""
    # Setup
    kato_fixture.clear_all_memory()
    
    # Execute
    kato_fixture.observe({'strings': ['test'], 'vectors': [], 'emotives': {}})
    
    # Assert
    stm = kato_fixture.get_short_term_memory()
    assert len(stm) == 1
    assert stm[0] == ['test']
```

### Testing Best Practices

1. **Always Clear Memory**: Start each test with `clear_all_memory()`
2. **Use Unique Data**: Avoid reusing test data across tests
3. **Test One Thing**: Each test should verify a single behavior
4. **Descriptive Names**: Use clear, descriptive test function names
5. **Document Edge Cases**: Add comments explaining non-obvious test cases

## Debugging Tests

### Local Debugging
```python
def test_with_debugging(kato_fixture):
    # Add print statements
    print(f"Processor ID: {kato_fixture.processor_id}")
    
    # Use breakpoints
    import pdb; pdb.set_trace()
    
    # Inspect responses
    result = kato_fixture.observe({'strings': ['test'], 'vectors': [], 'emotives': {}})
    print(f"Observation result: {result}")
```

### View Service Logs
```bash
# View KATO service logs
docker logs kato-primary --tail 50
docker logs kato-testing --tail 50

# View MongoDB logs
docker logs kato-mongodb --tail 50

# Follow logs in real-time
docker logs -f kato-primary
```

### Common Issues and Solutions

#### Services Not Running
```bash
# Check if services are up
./kato-manager.sh status

# If not running, start them
./kato-manager.sh start

# Check health
curl http://localhost:8001/health
```

#### Port Conflicts
```bash
# Check if ports are in use
lsof -i :8001
lsof -i :8002
lsof -i :8003

# Stop conflicting services or change ports in docker-compose.yml
```

#### Test Failures After Code Changes
```bash
# Rebuild Docker image after code changes
./kato-manager.sh build

# Restart services
./kato-manager.sh restart

# Then run tests
./run_simple_tests.sh --no-start --no-stop
```

#### Database Issues
```bash
# Clean restart with fresh databases
./kato-manager.sh stop
docker volume prune -f  # WARNING: Removes all unused volumes
./kato-manager.sh start
```

## Performance Testing

### Running Performance Tests
```bash
# Run performance test suite
./run_simple_tests.sh --no-start --no-stop tests/tests/performance/

# Monitor resource usage during tests
docker stats
```

### Load Testing Example
```python
def test_high_throughput(kato_fixture):
    """Test KATO can handle high request volume."""
    import time
    
    start = time.time()
    for i in range(1000):
        kato_fixture.observe({
            'strings': [f'test_{i}'],
            'vectors': [],
            'emotives': {}
        })
    
    elapsed = time.time() - start
    requests_per_second = 1000 / elapsed
    
    assert requests_per_second > 100  # Expect > 100 req/s
    print(f"Throughput: {requests_per_second:.2f} req/s")
```

## Continuous Integration

### GitHub Actions Example
```yaml
name: Tests
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      
      - name: Build and start services
        run: |
          ./kato-manager.sh build
          ./kato-manager.sh start
          
      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.9'
          
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r tests/requirements.txt
          
      - name: Run tests
        run: |
          ./run_simple_tests.sh --no-start --no-stop
          
      - name: Stop services
        if: always()
        run: ./kato-manager.sh stop
```

## Test Coverage

### Current Status
- **Total Tests**: 143+ unit tests
- **Test Categories**: Unit, Integration, API, Performance
- **Key Areas Covered**:
  - Pattern learning and recall
  - Temporal segmentation
  - Vector operations
  - Multi-modal processing
  - Recall threshold behavior
  - Edge cases and error handling

### Running Coverage Report
```bash
# Install coverage tool
pip install pytest-cov

# Run tests with coverage
python -m pytest tests/tests/unit/ --cov=kato --cov-report=html

# View coverage report
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
```

## Summary

The KATO testing system provides:
- **Fast Feedback**: Local Python execution for quick iteration
- **Easy Debugging**: Direct access with print/breakpoint debugging
- **Complete Isolation**: Each test gets its own processor_id
- **Parallel Execution**: Tests can run concurrently
- **No Container Overhead**: Tests run directly, containers only for services

Remember: Always start services with `./kato-manager.sh start` before running tests!