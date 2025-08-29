# Test Organization

This document provides a quick reference for the test suite organization. For complete testing documentation, see [docs/development/TESTING.md](../docs/development/TESTING.md).

## Test Statistics
- **Total**: 128 tests (100% passing)
  - API: 21 tests
  - Unit: 83 tests  
  - Integration: 19 tests
  - Performance: 5 tests

## Directory Structure

```
tests/
├── tests/
│   ├── api/              # REST API endpoint tests (21)
│   ├── unit/             # Unit tests (83)
│   ├── integration/      # Integration tests (19)
│   ├── performance/      # Performance/stress tests (5)
│   └── fixtures/         # Shared test fixtures and helpers
├── scripts/              # Utility scripts
├── test-harness.sh       # Container-based test runner
└── Dockerfile.test       # Test container definition
```

## Test Files by Category

### API Tests (`tests/api/`)
- `test_rest_endpoints.py` - All REST API endpoint tests

### Unit Tests (`tests/unit/`)
- `test_determinism_preservation.py` - Deterministic behavior validation
- `test_memory_management.py` - Memory operations (working/long-term)
- `test_model_hashing.py` - Model hash generation
- `test_observations.py` - Observation processing
- `test_prediction_edge_cases.py` - Edge case handling
- `test_prediction_fields.py` - Prediction field structure
- `test_predictions.py` - Prediction functionality
- `test_sorting_behavior.py` - Alphanumeric sorting behavior

### Integration Tests (`tests/integration/`)
- `test_sequence_learning.py` - Sequence learning workflows
- `test_vector_e2e.py` - Vector functionality end-to-end
- `test_vector_simplified.py` - Simplified vector operations

### Performance Tests (`tests/performance/`)
- `test_vector_stress.py` - Stress tests for vector operations

## Running Tests

### Quick Commands

```bash
# Run all tests (recommended)
./test-harness.sh test

# Run specific category
./test-harness.sh suite unit
./test-harness.sh suite integration
./test-harness.sh suite api
./test-harness.sh suite performance

# Run specific file
./test-harness.sh test tests/tests/unit/test_memory_management.py

# Run specific test
./test-harness.sh test tests/tests/unit/test_memory_management.py::test_clear_all_memory
```

## Key Testing Concepts

1. **Container-Based Testing**: All tests run in Docker containers for consistency
2. **Fixtures**: Shared fixtures in `tests/fixtures/kato_fixtures.py`
3. **Alphanumeric Sorting**: KATO sorts strings within events
4. **Deterministic Hashing**: Models use `MODEL|<sha1_hash>` format
5. **Temporal Fields**: Predictions include past/present/future/missing/extras

For detailed information about writing tests, debugging, and CI/CD integration, see the [main testing documentation](../docs/development/TESTING.md).