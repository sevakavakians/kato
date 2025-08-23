# KATO Test Documentation

## Overview

The KATO test suite provides comprehensive testing coverage for all aspects of the KATO system, including unit tests, integration tests, and API endpoint tests. The suite is designed to validate KATO's deterministic behavior, memory management, sequence learning, and unique features like alphanumeric sorting, deterministic hashing, and sophisticated temporal prediction segmentation.

**Current Coverage**: 98 tests total (66 unit, 11 integration, 21 API)

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
├── run_tests.sh          # Test runner script
├── requirements.txt      # Python dependencies
├── pytest.ini           # Pytest configuration
└── conftest.py          # Pytest fixtures configuration
```

## Running Tests

### Quick Start

```bash
cd kato-tests
./run_tests.sh
```

### Running Specific Test Categories

```bash
# Unit tests only
./run_tests.sh --unit

# Integration tests only
./run_tests.sh --integration

# API tests only
./run_tests.sh --api

# With verbose output
./run_tests.sh --verbose

# Run tests in parallel
./run_tests.sh --parallel
```

### Using Pytest Directly

```bash
# Install dependencies
pip install -r requirements.txt

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

## Understanding KATO's Core Behaviors

Before writing or modifying tests, it's essential to understand these key behaviors:

1. **Alphanumeric Sorting**: Strings are sorted within events, but event order is preserved
2. **Empty Events**: Observations with empty strings are ignored completely
3. **Prediction Temporal Fields**: 
   - `past`: Events before the present state
   - `present`: All contiguous matching events (partial matches supported)
   - `future`: Events after the present state
   - `missing`: Expected symbols not observed within present events
   - `extras`: Observed symbols not expected in present events
4. **Deterministic Hashing**: MODEL| and VECTOR| prefixes with SHA1 hashes

For detailed behavior documentation, see [KATO_BEHAVIOR.md](KATO_BEHAVIOR.md).

## Test Categories

### Unit Tests (66 tests)

#### test_observations.py (11 tests)
Tests for observation processing with strings, vectors, and emotives:
- Single and multiple string observations
- Vector observations
- Emotive observations
- Mixed modality observations
- Special characters and numeric strings
- Empty observations
- Sequence observations

#### test_memory_management.py (9 tests)
Tests for working memory and long-term memory management:
- Clearing all memory
- Clearing working memory only
- Working memory accumulation
- Manual learning
- Memory persistence
- Max sequence length enforcement
- Memory with emotives and vectors
- Interleaved memory operations

#### test_model_hashing.py (11 tests)
Tests for deterministic MODEL| prefix and SHA1 hashing:
- Model name format verification
- Identical sequences producing same hash
- Different sequences producing different hashes
- Sequence order affecting hash
- Hash consistency across sessions
- Complex multi-modal sequence hashing

#### test_predictions.py (13 tests)
Tests for prediction generation and scoring:
- No predictions initially
- Predictions after observations
- Prediction matches and misses
- Temporal components (past, present, future)
- Similarity scores
- Frequency tracking
- Entropy calculations
- Hamiltonian calculations
- Confidence scores
- Multiple model predictions

#### test_sorting_behavior.py (10 tests)
Tests specifically for KATO's alphanumeric sorting:
- Alphanumeric sorting within events
- Event order preservation
- Single string handling
- Mixed case sorting
- Numeric string sorting (as strings, not numbers)
- Special character sorting
- Empty string handling
- Unicode character sorting
- Sorting consistency

#### test_prediction_fields.py (11 tests)
Comprehensive tests for prediction field semantics:
- Past field with events before present
- Missing symbols within present events
- Extra symbols not in learned sequence
- Multi-event present states
- Contiguous event matching
- Partial matches at sequence start/end
- Mixed missing and extras
- Multiple past events
- Single event with missing symbols

#### test_prediction_edge_cases.py (10 tests)
Edge cases and boundary conditions:
- Empty events ignored
- No past at sequence start
- No future at sequence end
- All extras with no matches
- Partial overlap with multiple sequences
- Very long sequences
- Repeated symbols
- Case sensitivity
- Observation longer than learned
- Single symbol sequences
Tests specifically for KATO's alphanumeric sorting:
- Alphanumeric sorting within events
- Event order preservation
- Single string handling
- Mixed case sorting
- Numeric string sorting (as strings, not numbers)
- Special character sorting
- Empty string handling
- Unicode character sorting
- Sorting consistency

### Integration Tests (11 tests)

#### test_sequence_learning.py
End-to-end tests for sequence learning and recall:
- Simple sequence learning
- Multiple sequence learning and disambiguation
- Sequence completion
- Cyclic sequence learning
- Sequences with repetition
- Interleaved sequence learning
- Context switching
- Max sequence length auto-learning
- Sequences with time gaps
- Multi-modal sequence learning
- Branching sequences

### API Tests (21 tests)

#### test_rest_endpoints.py
Tests for all REST API endpoints:
- Health check (`/kato-api/ping`)
- Connect endpoint (`/connect`)
- Processor ping (`/{processor_id}/ping`)
- Status endpoint (`/{processor_id}/status`)
- Observe endpoint (`/{processor_id}/observe`)
- Working memory endpoints
- Memory clearing endpoints
- Learn endpoint
- Predictions endpoint
- Percept and cognition data endpoints
- Gene manipulation endpoints
- Model information endpoint
- Error handling (404, invalid JSON)
- Response timing verification

## Key KATO Behaviors Tested

### Prediction Field Structure

KATO's predictions contain temporal fields that segment sequences:

- **`past`**: Events that came before the present state in the predicted sequence
- **`present`**: All contiguous events identified by matching strings/symbols (not all symbols need to match)
- **`missing`**: Symbols expected within the `present` state but not observed in working memory  
- **`extras`**: Additional symbols observed that aren't expected in the `present` state
- **`future`**: Events that come after the present state in the predicted sequence

#### Example 1: Simple Sequence
Learned: [['a'], ['b'], ['c']]  
Observed: [['b']]  
Result:
- `past`: [['a']]
- `present`: [['b']]
- `future`: [['c']]
- `missing`: []
- `extras`: []

#### Example 2: Missing Symbols Within Present
Learned: [['hello', 'world'], ['test']]  
Observed: [['hello']]  
Result:
- `present`: [['hello', 'world']]  (the full learned event)
- `missing`: ['world']  (expected but not observed)
- `future`: [['test']]

#### Example 3: Extra Symbols
Learned: [['alpha'], ['beta']]  
Observed: [['alpha', 'gamma']]  
Result:
- `present`: [['alpha']]
- `extras`: ['gamma']  (observed but not expected)
- `future`: [['beta']]

## Key KATO Behaviors Tested

### 1. Alphanumeric Sorting
KATO sorts strings alphanumerically within each event but preserves the order of events:
- Input: `['hello', 'world', 'apple']`
- Stored: `['apple', 'hello', 'world']`

### 2. Deterministic Hashing
All models and vectors receive deterministic hash-based names:
- Models: `MODEL|<sha1_hash>`
- Vectors: `VECTOR|<sha1_hash>`
- Same sequence always produces same hash

### 3. Stateful Learning
KATO maintains state across observations:
- Working memory accumulates observations
- Learning creates persistent models
- Models survive working memory clears

### 4. Multi-Modal Processing
KATO processes multiple data types simultaneously:
- Strings (symbolic data)
- Vectors (numeric arrays)
- Emotives (key-value pairs for emotional context)

### 5. Empty Events
KATO ignores empty events - they do not change working memory or affect predictions:
- Observing `[]` has no effect on state
- Empty events in sequences are skipped
KATO processes multiple data types simultaneously:
- Strings (symbolic data)
- Vectors (numeric arrays)
- Emotives (key-value pairs for emotional context)

## Test Fixtures and Helpers

### KATOTestFixture
Main fixture for test setup and teardown:
- Starts/stops KATO instances
- Handles Docker container management
- Provides common operations (observe, learn, clear memory)
- Manages processor IDs and base URLs

### Hash Helpers
Utilities for hash verification:
- `calculate_model_hash()`: Generate expected hash for sequence
- `verify_model_name()`: Verify MODEL| prefix and hash
- `extract_hash_from_name()`: Extract hash from prefixed name
- `verify_hash_consistency()`: Check hash consistency across names

### Test Helpers
Utilities for KATO-specific behaviors:
- `sort_event_strings()`: Sort strings as KATO does
- `assert_working_memory_equals()`: Assert with automatic sorting

## Test Configuration

### pytest.ini
```ini
[pytest]
testpaths = tests
python_files = test_*.py
addopts = -v --tb=short --strict-markers
timeout = 60
```

### Environment Variables
```bash
PROCESSOR_ID=p123456789  # Processor identifier
PROCESSOR_NAME=P1        # Processor name
```

## Common Test Patterns

### Important: Account for Alphanumeric Sorting
Always remember that KATO sorts strings within events:

```python
# Input
observe({'strings': ['zebra', 'apple', 'monkey']})

# Stored as
[['apple', 'monkey', 'zebra']]  # Sorted alphanumerically
```

### Basic Observation Test
```python
def test_observation(kato_fixture):
    kato_fixture.clear_all_memory()
    
    result = kato_fixture.observe({
        'strings': ['test'],
        'vectors': [],
        'emotives': {}
    })
    
    assert result['status'] == 'observed'
    wm = kato_fixture.get_working_memory()
    assert wm == [['test']]
```

### Sequence Learning Test
```python
def test_sequence(kato_fixture):
    kato_fixture.clear_all_memory()
    
    # Learn sequence
    for item in ['a', 'b', 'c']:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    
    model_name = kato_fixture.learn()
    assert model_name.startswith('MODEL|')
    
    # Test recall
    kato_fixture.observe({'strings': ['a'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()
    assert len(predictions) > 0
```

### Sorting-Aware Test
```python
def test_with_sorting(kato_fixture):
    from fixtures.test_helpers import assert_working_memory_equals
    
    kato_fixture.clear_all_memory()
    kato_fixture.observe({'strings': ['z', 'a', 'm'], 'vectors': [], 'emotives': {}})
    
    wm = kato_fixture.get_working_memory()
    # Automatically handles sorting: ['z', 'a', 'm'] -> ['a', 'm', 'z']
    assert_working_memory_equals(wm, [['z', 'a', 'm']])
```

### Testing Prediction Fields
```python
def test_prediction_temporal_fields(kato_fixture):
    # Learn: [['start'], ['middle'], ['end']]
    for item in ['start', 'middle', 'end']:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()
    
    # Observe middle
    kato_fixture.clear_working_memory()
    kato_fixture.observe({'strings': ['middle'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()
    
    for pred in predictions:
        if 'middle' in pred.get('matches', []):
            assert pred['past'] == [['start']]     # Before present
            assert pred['present'] == [['middle']]  # Current state
            assert pred['future'] == [['end']]      # After present
            assert pred['missing'] == []            # Nothing missing
            assert pred['extras'] == []             # No extras
```

### Testing Missing and Extras
```python
def test_missing_and_extras(kato_fixture):
    # Learn: [['a', 'b'], ['c', 'd']]
    kato_fixture.observe({'strings': ['a', 'b'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['c', 'd'], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()
    
    # Observe with missing 'b', 'd' and extras 'x', 'y'
    kato_fixture.clear_working_memory()
    kato_fixture.observe({'strings': ['a', 'x'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['c', 'y'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()
    
    for pred in predictions:
        if pred.get('frequency', 0) > 0:
            assert 'b' in pred['missing'] or 'd' in pred['missing']
            assert 'x' in pred['extras'] or 'y' in pred['extras']
```

## Troubleshooting

### Docker Issues
- **Container not starting**: Check Docker Desktop is running
- **Port conflicts**: Ensure port 8000 is available
- **Build failures**: Try `docker system prune -a` and rebuild

### Test Failures
- **Timeout errors**: Increase timeout in pytest.ini
- **Import errors**: Check PYTHONPATH includes parent directories
- **Sorting mismatches**: Use `assert_working_memory_equals()` helper

### Common Errors
1. **ModuleNotFoundError: fixtures**
   - Solution: Run from kato-tests directory
   - Ensure conftest.py is present

2. **Docker filesystem errors**
   - Solution: Restart Docker Desktop
   - Clear Docker cache: `docker system prune -a`

3. **Assertion failures on string order**
   - Remember KATO sorts strings alphanumerically within events
   - Use test helpers for automatic sorting
   - Event order in sequences is preserved

4. **Prediction field confusion**
   - `future`: Events that come after present (not individual symbols)
   - `missing`: Symbols expected in present events but not observed
   - `extras`: Symbols observed but not expected in present
   - `present`: Can span multiple events with partial matches

## Adding New Tests

1. **Choose appropriate directory**:
   - `unit/` for isolated component tests
   - `integration/` for multi-component tests
   - `api/` for endpoint tests

2. **Use existing fixtures**:
   ```python
   from fixtures.kato_fixtures import kato_fixture
   from fixtures.test_helpers import assert_working_memory_equals
   ```

3. **Follow naming conventions**:
   - Files: `test_*.py`
   - Functions: `test_*`
   - Descriptive names: `test_observe_with_emotives`

4. **Account for KATO behaviors**:
   - Alphanumeric sorting within events
   - Deterministic hashing
   - Stateful operations

## Performance Considerations

- Tests use Docker containers (startup overhead)
- Parallel execution with `pytest-xdist` reduces total time
- Module-scoped fixtures minimize container restarts
- Timeout of 60 seconds per test (configurable)

## Continuous Integration

The test suite is designed for CI/CD integration:
- Exit codes: 0 for success, non-zero for failures
- JSON output: `pytest --json-report`
- Coverage reports: `pytest --cov=kato`
- Parallel execution for faster CI runs

## Version Compatibility

- Python: 3.8+ required
- Docker: 20.10+ recommended
- pytest: 7.0+ required
- Dependencies: See requirements.txt