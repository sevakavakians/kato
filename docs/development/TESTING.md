# KATO Test Documentation

## Overview

KATO uses a simple local Python testing approach with pytest. Tests run directly on your local machine using a virtual environment, making debugging straightforward and eliminating Docker complexity.

**Current Coverage**: 185 test functions across 19 test files
- Unit tests: tests/tests/unit/ (143 tests)
- Integration tests: tests/tests/integration/ (19 tests)
- API tests: tests/tests/api/ (18 tests)
- Performance tests: tests/tests/performance/ (5 tests)
- **Pass Rate**: 184/185 passing (99.5%)
- **Skipped**: 1 test (cyclic pattern test - feature out of scope)
- Execution time: ~100 seconds (full suite)

## Test Architecture

### Key Concepts

**Local Execution**: Tests run directly using Python and pytest, no containers needed.

**Test Isolation**: Each test gets:
- Unique processor ID: `test_<name>_<timestamp>_<uuid>`
- Dedicated MongoDB database namespace
- Dedicated Qdrant vector collection
- Clean state via fixture setup/teardown

**Benefits**:
- **Simple Debugging**: Use standard Python debugging tools
- **Fast Iteration**: No container rebuild delays
- **Easy Setup**: Just Python virtual environment
- **Direct Access**: Inspect databases and logs directly
- **IDE Integration**: Full debugger support

## Running Tests

### Quick Start

```bash
# Set up virtual environment (first time only)
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -r tests/requirements.txt

# Run all tests
./run_simple_tests.sh

# OR run directly with pytest
python -m pytest tests/tests/ -v
```

### Running Specific Tests

```bash
# Run specific test suites
./run_simple_tests.sh tests/tests/unit/          # Unit tests only
./run_simple_tests.sh tests/tests/integration/   # Integration tests only
./run_simple_tests.sh tests/tests/api/          # API tests only
./run_simple_tests.sh tests/tests/performance/  # Performance tests

# Run specific test file
python -m pytest tests/tests/unit/test_observations.py -v

# Run specific test function
python -m pytest tests/tests/unit/test_observations.py::test_observe_single_string -v

# Run with options
python -m pytest tests/tests/ -v -x    # Verbose, stop on first failure
python -m pytest tests/tests/ -vv      # Extra verbose output
python -m pytest tests/tests/ --tb=short  # Short traceback format
```

### Advanced Options

```bash
# Run tests without starting/stopping KATO
./run_simple_tests.sh --no-start --no-stop tests/tests/

# Run tests with verbose output
./run_simple_tests.sh -v tests/tests/

# Generate coverage report
python -m pytest tests/tests/ --cov=kato --cov-report=html

# Run tests in parallel (if pytest-xdist installed)
python -m pytest tests/tests/ -n auto
```

## Test Execution Flow

### 1. Setup Phase
When you run tests:
- Virtual environment is activated
- KATO services are started (if not already running)
- Test discovery finds all test files

### 2. Test Execution
For each test:
1. **Generate unique processor ID**: `test_<name>_<timestamp>_<uuid>`
2. **Clear all memory**: Reset to clean state
3. **Run test**: Execute test function
4. **Verify results**: Check assertions
5. **Cleanup**: Clear memory for next test

### 3. Result Reporting
After all tests complete:
- Total passed/failed/skipped counts displayed
- Detailed pytest output with tracebacks
- KATO services stopped (if requested)

## Test Organization

### Directory Structure
```
tests/
├── tests/
│   ├── fixtures/          # Test fixtures and helpers
│   │   ├── kato_fixtures.py   # KATO test fixtures
│   │   ├── hash_helpers.py    # Hash verification utilities
│   │   └── test_helpers.py    # Sorting and assertion helpers
│   ├── unit/              # Unit tests
│   │   ├── test_observations.py
│   │   ├── test_memory_management.py
│   │   ├── test_pattern_hashing.py
│   │   ├── test_predictions.py
│   │   └── ...
│   ├── integration/       # Integration tests
│   │   ├── test_pattern_learning.py
│   │   └── test_vector_e2e.py
│   ├── api/              # API endpoint tests
│   │   └── test_rest_endpoints.py
│   └── performance/      # Performance tests
│       └── test_vector_stress.py
├── requirements-test.txt     # Test dependencies
├── run_simple_tests.sh      # Simple test runner script
├── scripts/
│   └── run_tests_direct.py  # Direct Python test runner
└── pytest.ini               # Pytest configuration
```

### Test Categories

#### Unit Tests (tests/unit/)
Test individual KATO components in isolation:
- **test_observations.py**: Observation processing with strings, vectors, emotives
- **test_memory_management.py**: Short-term and long-term memory operations
- **test_pattern_hashing.py**: Deterministic pattern hashing (PTRN|<hash>)
- **test_predictions.py**: Prediction generation and scoring
- **test_sorting_behavior.py**: Alphanumeric sorting within events
- **test_prediction_fields.py**: Temporal segmentation (past/present/future)
- **test_recall_threshold_values.py**: Recall threshold behavior

#### Integration Tests (tests/integration/)
Test end-to-end workflows:
- **test_pattern_learning.py**: Complete learning and recall cycles
- **test_vector_e2e.py**: Vector functionality with Qdrant
- **test_sequence_learning.py**: Temporal pattern learning

#### API Tests (tests/api/)
Test REST endpoints:
- **test_rest_endpoints.py**: All REST API endpoints including observe, predict, learn

#### Performance Tests (tests/performance/)
Stress and benchmark tests:
- **test_vector_stress.py**: Vector operation performance and scalability

## Database Isolation

### MongoDB Isolation
Each cluster uses its processor_id as the database name:
- Patterns: `{processor_id}.patterns_kb`
- Symbols: `{processor_id}.symbols_kb`
- Predictions: `{processor_id}.predictions_kb`
- Metadata: `{processor_id}.metadata`

### Qdrant Isolation
Each cluster has its own vector collection:
- Collection name: `vectors_{processor_id}`
- Complete HNSW index per cluster
- No shared embeddings

### Redis Isolation
Each cluster uses namespaced keys:
- Key pattern: `{processor_id}:*`
- Isolated cache per instance

## Writing Tests

### Using Test Fixtures

```python
from fixtures.kato_fixtures import kato_fixture
from fixtures.test_helpers import assert_short_term_memory_equals

def test_observation(kato_fixture):
    """Test basic observation."""
    kato_fixture.clear_all_memory()
    
    result = kato_fixture.observe({
        'strings': ['test'],
        'vectors': [],
        'emotives': {}
    })
    
    assert result['status'] == 'observed'
    stm = kato_fixture.get_short_term_memory()
    assert stm == [['test']]
```

### Important: Alphanumeric Sorting

KATO automatically sorts strings within events alphanumerically:

```python
def test_sorting(kato_fixture):
    kato_fixture.clear_all_memory()
    
    # Input: unsorted
    kato_fixture.observe({'strings': ['zebra', 'apple', 'monkey']})
    
    # Stored: sorted
    stm = kato_fixture.get_short_term_memory()
    assert stm == [['apple', 'monkey', 'zebra']]
```

### Testing Prediction Fields

```python
def test_temporal_segmentation(kato_fixture):
    # Learn pattern
    for item in ['start', 'middle', 'end']:
        kato_fixture.observe({'strings': [item]})
    kato_fixture.learn()
    
    # Test prediction
    kato_fixture.clear_short_term_memory()
    kato_fixture.observe({'strings': ['middle']})
    predictions = kato_fixture.get_predictions()
    
    pred = predictions[0]
    assert pred['past'] == [['start']]
    assert pred['present'] == [['middle']]
    assert pred['future'] == [['end']]
```

### Test Configuration

Tests can configure KATO settings using the fixture's `update_genes` method:

```python
def test_with_custom_config(kato_fixture):
    """Test with specific recall threshold."""
    kato_fixture.clear_all_memory()
    
    # Set custom configuration
    kato_fixture.set_recall_threshold(0.7)
    kato_fixture.update_genes({"max_pattern_length": 10})
    
    # Run test with custom settings
    result = kato_fixture.observe({'strings': ['test']})
    assert result['status'] == 'observed'
```

## Troubleshooting

### Common Issues

#### KATO Not Running
- **Issue**: Connection refused on port 8000
- **Solution**: Start KATO with `./kato-manager.sh start`
- **Solution**: Check if KATO is running: `docker ps | grep kato`

#### Import Errors
- **Issue**: ModuleNotFoundError for test modules
- **Solution**: Activate virtual environment: `source venv/bin/activate`
- **Solution**: Install dependencies: `pip install -r tests/requirements.txt`

#### Database Connection Issues
- **Issue**: Tests timeout connecting to MongoDB/Qdrant
- **Solution**: Check KATO logs: `docker logs kato-api-$(whoami)-1`
- **Solution**: Restart KATO: `./kato-manager.sh restart`

#### Test Isolation Issues
- **Issue**: Tests affect each other
- **Solution**: Ensure each test calls `kato_fixture.clear_all_memory()`
- **Solution**: Check that fixtures use scope="function"

### Debugging Tests

```bash
# Run single test with verbose output
python -m pytest tests/tests/unit/test_observations.py::test_observe_single_string -vv

# Run with Python debugger
python -m pytest tests/tests/unit/test_observations.py --pdb

# Check KATO logs during test
docker logs kato-api-$(whoami)-1 --tail 20

# Run tests with print output visible
python -m pytest tests/tests/ -s

# Run specific test with full traceback
python -m pytest tests/tests/unit/test_observations.py --tb=long
```

## Performance Considerations

### Test Speed
- Virtual environment setup: One-time ~30 seconds
- KATO startup: ~5-10 seconds
- Individual test: ~0.1-1 second
- Full suite: ~30-60 seconds

### Optimization Tips
1. **Keep KATO running**: Use `--no-start --no-stop` to avoid restart overhead
2. **Run specific tests**: Target only tests you're working on
3. **Use pytest markers**: Group and run related tests
4. **Parallel execution**: Use `pytest-xdist` with `-n auto` for parallel runs

## Continuous Integration

The test suite is CI/CD ready:

```yaml
# Example GitHub Actions workflow
- name: Set up Python
  uses: actions/setup-python@v4
  with:
    python-version: '3.9'

- name: Install dependencies
  run: |
    pip install -r requirements.txt
    pip install -r tests/requirements.txt

- name: Start KATO
  run: ./kato-manager.sh start

- name: Run tests
  run: python -m pytest tests/tests/ -v --junit-xml=test-results.xml

- name: Upload test results
  if: always()
  uses: actions/upload-artifact@v2
  with:
    name: test-results
    path: test-results.xml
```

## Key KATO Behaviors to Test

### 1. Alphanumeric Sorting
- Strings sorted within events
- Event order preserved
- Case-sensitive sorting

### 2. Pattern Hashing
- Deterministic PTRN|<sha1_hash> format
- Same pattern → same hash
- Different patterns → different hashes

### 3. Temporal Segmentation
- **past**: Events before present
- **present**: Events with matching symbols
- **future**: Events after present
- **missing**: Expected but not observed
- **extras**: Observed but not expected

### 4. Minimum Requirements
- At least 2 strings total for predictions
- Empty events are ignored
- Vectors contribute string names

### 5. Database Isolation
- Each test gets fresh database state
- No contamination between tests
- Automatic cleanup

## Setting Up Your Environment

### Prerequisites
- Python 3.8 or later
- Running KATO instance (via `./kato-manager.sh start`)
- Virtual environment with dependencies

### Initial Setup
```bash
# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install -r tests/requirements.txt
```

### Environment Variables
```bash
# Disable any container mode (set automatically by run_simple_tests.sh)
export KATO_TEST_MODE=local
export KATO_CLUSTER_MODE=false

# Optional: Set custom API URL if not using default port 8000
export KATO_API_URL=http://localhost:8000
```