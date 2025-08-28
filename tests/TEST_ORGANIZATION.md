# Test Organization

## Directory Structure

All test files are organized under `tests/tests/` with the following subdirectories:

### `/tests/tests/api/`
- **test_rest_endpoints.py** - Tests for REST API endpoints

### `/tests/tests/unit/`
- **test_determinism_preservation.py** - Tests for deterministic behavior
- **test_memory_management.py** - Tests for memory operations (short-term memory, learning)
- **test_model_hashing.py** - Tests for model hash generation
- **test_observations.py** - Tests for observation processing
- **test_prediction_edge_cases.py** - Tests for prediction edge cases
- **test_prediction_fields.py** - Tests for prediction field structure
- **test_predictions.py** - Tests for prediction functionality
- **test_sorting_behavior.py** - Tests for alphanumeric sorting within events

### `/tests/tests/integration/`
- **test_sequence_learning.py** - Tests for sequence learning workflows
- **test_vector_e2e.py** - End-to-end tests for vector functionality
- **test_vector_simplified.py** - Simplified integration tests for vector operations

### `/tests/tests/performance/`
- **test_vector_stress.py** - Stress tests for vector operations (performance, scalability, accuracy)

### `/tests/tests/fixtures/`
- **kato_fixtures.py** - Shared test fixtures for KATO setup/teardown
- **test_helpers.py** - Helper functions for tests

### `/tests/scripts/`
Utility scripts (not actual tests):
- **analyze_tests.py** - Analyze test files
- **check_tests.py** - Check test status
- **run_simple_test.py** - Simple test runner
- **run_tests_direct.py** - Direct test runner
- **setup_venv.py** - Virtual environment setup
- **simple_analyze.py** - Simple test analysis

### `/tests/`
Root directory files:
- **conftest.py** - Pytest configuration (must remain in root)
- **pytest.ini** - Pytest settings
- **Dockerfile.test** - Test container definition
- **requirements-test.txt** - Test dependencies

## Test Count Summary
- Total: **128 tests**
  - API tests: 21
  - Unit tests: 83  
  - Integration tests: 19
  - Performance tests: 5

## Running Tests

### Run all tests:
```bash
./test-harness.sh test
```

### Run specific category:
```bash
./test-harness.sh test tests/tests/unit/      # Unit tests only
./test-harness.sh test tests/tests/integration/ # Integration tests only
./test-harness.sh test tests/tests/api/        # API tests only
./test-harness.sh test tests/tests/performance/ # Performance tests only
```

### Run specific test file:
```bash
./test-harness.sh test tests/tests/unit/test_memory_management.py
```

### Run specific test:
```bash
./test-harness.sh test tests/tests/unit/test_memory_management.py::test_clear_all_memory
```

## Notes
- All test files follow the pattern `test_*.py`
- Tests use the shared `kato_fixture` from `fixtures/kato_fixtures.py`
- Tests run in Docker containers via `test-harness.sh` for consistency
- The test harness automatically detects and uses running KATO instances