# KATO Test Suite

This directory contains the complete test suite for KATO. For comprehensive testing documentation, please refer to the main testing documentation:

**📖 [Complete Testing Documentation](../docs/development/TESTING.md)**

## Quick Start

### Using Local Python Testing

```bash
# Set up virtual environment (first time only)
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -r tests/requirements.txt

# Run all tests
./run_simple_tests.sh

# OR use pytest directly
python -m pytest tests/ -v
```

### Run Specific Test Categories

```bash
# Run specific test suites
./run_simple_tests.sh tests/tests/unit/          # Unit tests only
./run_simple_tests.sh tests/tests/integration/   # Integration tests only
./run_simple_tests.sh tests/tests/api/          # API tests only
./run_simple_tests.sh tests/tests/performance/  # Performance tests

# Run specific test file
python -m pytest tests/tests/unit/test_observations.py -v

# Run with pytest options
python -m pytest tests/ -v -x   # Verbose, stop on first failure
python -m pytest tests/ -s       # Show print output
python -m pytest tests/ --pdb    # Drop into debugger on failure
```

## Test Statistics

**Current Coverage**: 185 test functions across 19 test files
- Unit tests: tests/tests/unit/ (143 tests)
- Integration tests: tests/tests/integration/ (19 tests)
- API tests: tests/tests/api/ (18 tests)
- Performance tests: tests/tests/performance/ (5 tests)
- **Pass Rate**: 184/185 passing (99.5%)
- **Skipped**: 1 test (cyclic pattern test - feature out of scope)
- Execution time: ~100 seconds (full suite)

## Directory Structure

```
tests/
├── tests/
│   ├── fixtures/          # Shared test fixtures and helpers
│   │   ├── kato_fixtures.py   # KATO test fixtures
│   │   ├── hash_helpers.py    # Hash verification utilities
│   │   └── test_helpers.py    # Sorting and assertion helpers
│   ├── unit/              # Unit tests
│   ├── integration/       # Integration tests
│   ├── api/              # API endpoint tests
│   └── performance/      # Performance tests
├── scripts/              # Utility scripts for testing
│   └── run_tests_direct.py   # Direct Python test runner
├── run_simple_tests.sh      # Simple test runner script
├── requirements-test.txt     # Test dependencies
├── pytest.ini               # Pytest configuration
├── conftest.py          # Pytest fixtures configuration
└── TEST_ORGANIZATION.md # Test organization details
```

## Key KATO Behaviors to Remember

When writing or debugging tests, keep these behaviors in mind:

1. **Alphanumeric Sorting**: Strings are sorted within events
   - Input: `['zebra', 'apple']` → Stored: `['apple', 'zebra']`

2. **Minimum Pattern Length**: At least 2 strings total required for predictions

3. **Deterministic Hashing**: All patterns use `PTRN|<sha1_hash>` format

4. **Temporal Fields in Predictions**:
   - `past`: Events before first match
   - `present`: ALL events containing matching symbols (complete events included)
   - `future`: Events after last match
   - `missing`: Symbols in present events but not observed
   - `extras`: Observed symbols not in pattern

5. **Recall Threshold**: Heuristic filter (0.0-1.0)
   - 0.0 = Return all patterns
   - 1.0 = Perfect matches only
   - Default: 0.1 (permissive)

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
    
    # Test gets unique processor_id for isolation
    # MongoDB: test_example_<timestamp>_<uuid>
    # Qdrant: vectors_test_example_<timestamp>_<uuid>
```

## Debugging Tips

```bash
# Run single test with verbose output
python -m pytest tests/tests/unit/test_observations.py::test_observe_single_string -vv

# Drop into debugger on failure
python -m pytest tests/tests/unit/ --pdb

# Show all print statements
python -m pytest tests/tests/unit/ -s

# Check KATO logs during test
docker logs kato-api-$(whoami)-1 --tail 20

# Run tests without starting/stopping KATO
./run_simple_tests.sh --no-start --no-stop tests/
```

## More Information

For detailed information about:
- Setting up your environment
- Understanding test fixtures
- Debugging test failures
- Adding new test categories
- CI/CD integration

Please see **[docs/development/TESTING.md](../docs/development/TESTING.md)**