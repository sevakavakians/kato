# KATO Clustered Test Documentation

## Overview

KATO uses a sophisticated clustered test harness that provides complete isolation between test runs. Each test cluster gets its own KATO instance with dedicated databases (MongoDB, Qdrant, Redis), ensuring deterministic execution and preventing cross-contamination between tests.

**Current Coverage**: 188 test functions across 21 test files
- Unit tests: tests/tests/unit/
- Integration tests: tests/tests/integration/
- API tests: tests/tests/api/
- Performance tests: tests/tests/performance/
- Execution time: ~30-60 seconds (depending on cluster configuration)

## Clustered Test Architecture

### Key Concepts

**Test Clustering**: Tests are automatically grouped based on their configuration requirements. Each cluster runs with its own isolated KATO instance and databases.

**Complete Isolation**: Every test cluster gets:
- Unique processor ID: `cluster_<name>_<timestamp>_<uuid>`
- Dedicated MongoDB database
- Dedicated Qdrant vector collection
- Dedicated Redis cache namespace
- Isolated network environment

**Benefits**:
- **No Cross-Contamination**: Tests cannot affect each other
- **Deterministic Execution**: Same results every time
- **Parallel Capability**: Clusters can run concurrently
- **Configuration Flexibility**: Different clusters can have different settings
- **Automatic Cleanup**: Resources are cleaned up after each cluster

### Test Cluster Configuration

Test clusters are defined in `tests/tests/fixtures/test_clusters.py`:

```python
TEST_CLUSTERS = [
    TestCluster(
        name="default",
        config={
            "recall_threshold": 0.1,
            "max_pattern_length": 0
        },
        test_patterns=[
            "tests/unit/test_observations.py",
            "tests/unit/test_predictions.py",
            # ... more tests
        ],
        description="Tests using default KATO configuration"
    ),
    
    TestCluster(
        name="recall_high",
        config={
            "recall_threshold": 0.7,
            "max_pattern_length": 0
        },
        test_patterns=[
            "tests/unit/test_recall_threshold_values.py::test_threshold_point_seven_high",
            # ... specific tests requiring high recall
        ],
        description="Tests requiring high recall threshold"
    ),
    # ... more clusters
]
```

## Running Tests

### Quick Start

```bash
# Build test harness container (first time or after dependency changes)
./test-harness.sh build

# Run all tests with automatic clustering
./kato-manager.sh test

# OR run directly
./test-harness.sh test
```

### Running Specific Tests

```bash
# Run specific test suites (automatically clustered)
./test-harness.sh suite unit          # Unit tests only
./test-harness.sh suite integration   # Integration tests only
./test-harness.sh suite api           # API tests only
./test-harness.sh suite performance   # Performance tests

# Run specific test file (finds appropriate cluster)
./test-harness.sh test tests/tests/unit/test_observations.py

# Run specific test function
./test-harness.sh test tests/tests/unit/test_observations.py::test_observe_single_string

# Run with options
./test-harness.sh --verbose test      # Show detailed cluster execution
./test-harness.sh --no-redirect test  # Direct console output
./test-harness.sh test tests/ -v -x   # Verbose, stop on first failure
```

### Advanced Options

```bash
# Development mode (live code updates)
./test-harness.sh dev tests/tests/unit/ -v

# Interactive shell for debugging
./test-harness.sh shell

# Generate coverage report
./test-harness.sh report

# Stop all test instances
./test-harness.sh stop
```

## Test Execution Flow

### 1. Test Discovery
When you run tests, the harness:
- Analyzes which tests to run based on your command
- Identifies which cluster each test belongs to
- Groups tests by their cluster configuration

### 2. Cluster Execution
For each cluster:
1. **Generate unique processor ID**: `cluster_<name>_<timestamp>_<uuid>`
2. **Start KATO instance**: Launch with processor-specific configuration
3. **Start databases**: MongoDB, Qdrant, and Redis with processor-specific namespaces
4. **Apply configuration**: Set recall_threshold, max_pattern_length, etc.
5. **Run tests**: Execute all tests in the cluster
6. **Cleanup**: Stop instance and remove all containers

### 3. Result Aggregation
After all clusters complete:
- Results are aggregated across clusters
- Total passed/failed/skipped counts are displayed
- Detailed logs are saved to `logs/test-runs/`

## Test Organization

### Directory Structure
```
tests/
├── tests/
│   ├── fixtures/          # Test fixtures and cluster configuration
│   │   ├── test_clusters.py   # Cluster definitions
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
├── test-harness.sh           # Main test runner script
├── test-harness-clustered.sh # Clustered execution logic
├── cluster-orchestrator.sh   # Cluster management
├── run_cluster_tests.py      # Container test runner
├── Dockerfile.test           # Test container definition
├── requirements-test.txt     # Test dependencies
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
    wm = kato_fixture.get_short_term_memory()
    assert wm == [['test']]
```

### Important: Alphanumeric Sorting

KATO automatically sorts strings within events alphanumerically:

```python
def test_sorting(kato_fixture):
    kato_fixture.clear_all_memory()
    
    # Input: unsorted
    kato_fixture.observe({'strings': ['zebra', 'apple', 'monkey']})
    
    # Stored: sorted
    wm = kato_fixture.get_short_term_memory()
    assert wm == [['apple', 'monkey', 'zebra']]
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

### Cluster-Specific Tests

If your test requires specific configuration, add it to the appropriate cluster in `test_clusters.py`:

```python
TestCluster(
    name="custom_config",
    config={
        "recall_threshold": 0.5,
        "max_pattern_length": 10
    },
    test_patterns=[
        "tests/unit/test_your_new_test.py"
    ],
    description="Tests requiring custom configuration"
)
```

## Troubleshooting

### Common Issues

#### Tests Not Running
- **Issue**: "0 passed, 0 failed, 0 skipped"
- **Solution**: Check test paths in test_clusters.py are correct
- **Solution**: Verify test files exist and have test functions

#### Container Build Failures
- **Issue**: Docker build errors
- **Solution**: Run `docker system prune -a` to clean up
- **Solution**: Check Dockerfile.test for syntax errors

#### Database Connection Issues
- **Issue**: Tests timeout connecting to MongoDB/Qdrant
- **Solution**: Ensure Docker network exists: `docker network create kato-network`
- **Solution**: Check containers are on same network

#### Result Aggregation Issues
- **Issue**: Individual tests pass but totals show 0
- **Solution**: Update test-harness scripts to latest version
- **Solution**: Check cluster-orchestrator.sh parsing logic

### Debugging Tests

```bash
# Run with verbose output
./test-harness.sh --verbose test

# Get interactive shell in test container
./test-harness.sh shell

# Check running containers
docker ps | grep kato

# View logs for specific cluster
docker logs kato-cluster_default_<id>

# Check test output logs
ls -la logs/test-runs/
cat logs/test-runs/latest/summary.txt
```

## Performance Considerations

### Cluster Overhead
- Each cluster requires ~2-3 seconds to start/stop
- Tests within a cluster run at normal speed
- Total overhead depends on number of clusters

### Optimization Tips
1. **Group related tests**: Keep tests with same config in same cluster
2. **Use default cluster**: Most tests can use default configuration
3. **Minimize clusters**: Fewer clusters = less overhead
4. **Parallel execution**: Future enhancement for concurrent clusters

## Continuous Integration

The clustered test harness is CI/CD ready:

```yaml
# Example GitHub Actions workflow
- name: Build test harness
  run: ./test-harness.sh build

- name: Run tests
  run: ./test-harness.sh test

- name: Upload test results
  if: always()
  uses: actions/upload-artifact@v2
  with:
    name: test-results
    path: logs/test-runs/
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

## Migration from Non-Clustered Testing

If you have old test commands or scripts:

### Old Approach (Deprecated)
```bash
# Direct pytest - NO LONGER SUPPORTED
pytest tests/unit/test_observations.py

# Shared instance testing - NO LONGER SUPPORTED
python -m pytest tests/
```

### New Clustered Approach
```bash
# All tests now use clustered execution
./test-harness.sh test tests/unit/test_observations.py

# Automatic clustering based on configuration
./test-harness.sh test
```

The clustered approach is now the ONLY supported way to run tests, ensuring complete isolation and deterministic results.