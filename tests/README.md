# KATO Test Suite

This directory contains the complete test suite for KATO. For comprehensive testing documentation, please refer to the main testing documentation:

**📖 [Complete Testing Documentation](../docs/development/TESTING.md)**

## Quick Start

### Using Container-Based Testing (Recommended)

```bash
# Build and run all tests
./test-harness.sh build
./test-harness.sh test

# OR use kato-manager
../kato-manager.sh test
```

### Run Specific Test Categories

```bash
# Run specific test suites
./test-harness.sh suite unit          # Unit tests only
./test-harness.sh suite integration   # Integration tests only
./test-harness.sh suite api           # API tests only
./test-harness.sh suite performance   # Performance tests

# Run specific test file
./test-harness.sh test tests/tests/unit/test_observations.py

# Run with pytest options
./test-harness.sh test tests/ -v -x   # Verbose, stop on first failure
```

## Test Statistics

**Current Coverage**: 128 tests (100% passing)
- 83 unit tests
- 19 integration tests  
- 21 API tests
- 5 performance tests
- Execution time: ~45 seconds

## Directory Structure

```
tests/
├── tests/
│   ├── fixtures/          # Shared test fixtures and helpers
│   ├── unit/              # Unit tests (83 tests)
│   ├── integration/       # Integration tests (19 tests)
│   ├── api/              # API endpoint tests (21 tests)
│   └── performance/      # Performance tests (5 tests)
├── scripts/              # Utility scripts for testing
├── test-harness.sh      # Container-based test runner
├── Dockerfile.test      # Test container definition
├── requirements-test.txt # Test dependencies
├── pytest.ini           # Pytest configuration
├── conftest.py          # Pytest fixtures configuration
└── TEST_ORGANIZATION.md # Test organization details
```

## Key KATO Behaviors to Remember

When writing or debugging tests, keep these behaviors in mind:

1. **Alphanumeric Sorting**: Strings are sorted within events
   - Input: `['zebra', 'apple']` → Stored: `['apple', 'zebra']`

2. **Empty Events**: Observations with empty strings are ignored

3. **Deterministic Hashing**: All patterns use `PTRN|<sha1_hash>` format

4. **Temporal Fields in Predictions**:
   - `past`: Events before present
   - `present`: Current matching events
   - `future`: Events after present
   - `missing`: Expected but not observed
   - `extras`: Observed but not expected

## Writing New Tests

```python
from fixtures.kato_fixtures import kato_fixture
from fixtures.test_helpers import sort_event_strings

def test_example(kato_fixture):
    """Test description."""
    kato_fixture.clear_all_memory()
    
    # Remember: strings will be sorted within the event
    result = kato_fixture.observe({
        'strings': ['zebra', 'apple'],  # Will be stored as ['apple', 'zebra']
        'vectors': [],
        'emotives': {}
    })
    assert result['status'] == 'observed'
```

## More Information

For detailed information about:
- Running tests in different modes
- Understanding test fixtures
- Debugging test failures
- Adding new test categories
- CI/CD integration

Please see **[docs/development/TESTING.md](../docs/development/TESTING.md)**