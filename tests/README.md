# KATO Test Suite

Comprehensive test suite for KATO with deterministic hashing validation, stateful sequence testing, and sophisticated prediction field verification.

## Current Status
- **98 Total Tests**: 66 unit, 11 integration, 21 API
- **Full Coverage**: Core behaviors, edge cases, and protocol compliance
- **Validated Behaviors**: Alphanumeric sorting, temporal segmentation, empty event handling

## Quick Start

```bash
# Run all tests
./run_tests.sh

# Run specific test categories
./run_tests.sh --unit          # Unit tests only
./run_tests.sh --integration   # Integration tests only
./run_tests.sh --api           # API tests only

# Run with options
./run_tests.sh --verbose       # Verbose output
./run_tests.sh --parallel      # Run tests in parallel
```

## Manual Setup

1. **Install dependencies:**
```bash
pip install -r requirements.txt
```

2. **Build KATO Docker image:**
```bash
../kato-manager.sh build
```

3. **Run tests with pytest:**
```bash
# Run all tests
pytest

# Run specific test file
pytest tests/unit/test_observations.py

# Run specific test
pytest tests/unit/test_observations.py::test_observe_single_string

# Run with verbose output
pytest -v

# Run in parallel (requires pytest-xdist)
pytest -n auto
```

## Test Structure

```
kato-tests/
├── tests/
│   ├── fixtures/          # Test fixtures and helpers
│   │   ├── hash_helpers.py    # Hash verification utilities
│   │   ├── test_helpers.py    # Sorting and assertion helpers
│   │   └── kato_fixtures.py   # KATO test fixtures
│   ├── unit/              # Unit tests
│   │   ├── test_observations.py
│   │   ├── test_memory_management.py
│   │   ├── test_model_hashing.py
│   │   ├── test_predictions.py
│   │   └── test_sorting_behavior.py
│   ├── integration/       # Integration tests
│   │   └── test_sequence_learning.py
│   └── api/              # API endpoint tests
│       └── test_rest_endpoints.py
```

## Test Categories

### Unit Tests (66 tests)
- **Observations** (11 tests): String, vector, and emotive observation processing, empty event handling
- **Memory Management** (9 tests): Working memory, learning, and memory limits
- **Model Hashing** (11 tests): Deterministic MODEL| prefix and SHA1 hashing
- **Predictions** (13 tests): Hamiltonian calculations, confidence scores, temporal fields
- **Sorting Behavior** (10 tests): Alphanumeric sorting within events
- **Prediction Fields** (11 tests): Past/present/future segmentation, missing/extras detection
- **Prediction Edge Cases** (10 tests): Boundary conditions and unusual scenarios

### Integration Tests (11 tests)
- **Sequence Learning**: End-to-end sequence learning and recall
- Context switching, branching sequences, multimodal data
- Temporal prediction validation
- Max sequence length auto-learning

### API Tests (21 tests)
- **REST Endpoints**: All REST API endpoints and error handling
- Protocol compliance and response validation
- Empty event handling via API

## Common pytest Commands

```bash
# Run tests matching a pattern
pytest -k "hash"

# Run with coverage
pytest --cov=kato

# Run and stop on first failure
pytest -x

# Run previously failed tests
pytest --lf

# Show local variables on failure
pytest -l

# Quiet mode (less output)
pytest -q
```

## Debugging Tests

```bash
# Run with Python debugger on failure
pytest --pdb

# Show print statements
pytest -s

# Maximum verbosity
pytest -vv

# Show test durations
pytest --durations=10
```

## Test Markers

Tests can be marked for selective execution:

```python
@pytest.mark.slow
def test_slow_operation():
    pass

@pytest.mark.integration
def test_integration():
    pass
```

Run marked tests:
```bash
pytest -m "slow"           # Run only slow tests
pytest -m "not slow"       # Skip slow tests
pytest -m "integration"    # Run only integration tests
```

## Environment Variables

Set these before running tests:

```bash
export PROCESSOR_ID=p123456789
export PROCESSOR_NAME=P1
```

## Key KATO Behaviors to Remember

### Alphanumeric Sorting
- Strings are sorted within each event: `['z', 'a']` → `['a', 'z']`
- Event order is preserved: `[['z'], ['a']]` stays `[['z'], ['a']]`
- Use `sort_event_strings()` helper for test assertions

### Prediction Fields
- **past**: Events before current state
- **present**: Contiguous matching events (supports partial matches)
- **future**: Events after current state
- **missing**: Expected symbols not observed in present
- **extras**: Observed symbols not expected in present

### Empty Events
- Empty observations `{'strings': []}` are ignored
- Don't change working memory or affect predictions

## Troubleshooting

1. **Docker not running**: Ensure Docker Desktop is running
2. **Port conflicts**: Check port 8000 is available
3. **Timeout errors**: Increase timeout in pytest.ini
4. **Import errors**: Ensure PYTHONPATH includes parent directories
5. **Assertion failures**: Check for alphanumeric sorting
6. **Prediction mismatches**: Verify correct field usage (future vs missing)

## Writing New Tests

1. Create test file in appropriate directory (unit/integration/api)
2. Import fixtures: `from fixtures.kato_fixtures import kato_fixture`
3. Import helpers: `from fixtures.test_helpers import sort_event_strings`
4. Write test functions starting with `test_`
5. Account for KATO behaviors:
   - Alphanumeric sorting within events
   - Empty events are ignored
   - Temporal segmentation in predictions

Example:
```python
def test_my_feature(kato_fixture):
    """Test description."""
    kato_fixture.clear_all_memory()
    
    # Remember: strings will be sorted within the event
    result = kato_fixture.observe({
        'strings': ['zebra', 'apple'],  # Will be stored as ['apple', 'zebra']
        'vectors': [],
        'emotives': {}
    })
    assert result['status'] == 'observed'
    
    # Check working memory with sorted expectation
    wm = kato_fixture.get_working_memory()
    assert wm == [['apple', 'zebra']]
```

### Testing Predictions
```python
def test_prediction_fields(kato_fixture):
    """Test temporal segmentation."""
    # Learn sequence
    for item in ['past', 'present', 'future']:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()
    
    # Observe middle
    kato_fixture.clear_working_memory()
    kato_fixture.observe({'strings': ['present'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()
    
    # Check temporal fields
    for pred in predictions:
        if 'present' in pred.get('matches', []):
            assert pred['past'] == [['past']]
            assert pred['present'] == [['present']]
            assert pred['future'] == [['future']]
            break
```