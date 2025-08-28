# KATO Test Documentation

## Overview

The KATO test suite provides comprehensive testing coverage for all aspects of the KATO system, including unit tests, integration tests, and API endpoint tests. The suite is designed to validate KATO's deterministic behavior, memory management, sequence learning, and unique features like alphanumeric sorting, deterministic hashing, and sophisticated temporal prediction segmentation.

**Current Coverage**: 128 tests total (100% passing)
- 83 unit tests
- 19 integration tests  
- 21 API tests
- 5 performance/stress tests
- Execution time: ~45 seconds

## Test Structure

```
kato/tests/
├── tests/
│   ├── fixtures/          # Test fixtures and helpers
│   │   ├── hash_helpers.py    # Hash verification utilities
│   │   ├── test_helpers.py    # Sorting and assertion helpers
│   │   └── kato_fixtures.py   # KATO test fixtures
│   ├── unit/              # Unit tests (83 tests)
│   │   ├── test_observations.py
│   │   ├── test_memory_management.py
│   │   ├── test_model_hashing.py
│   │   ├── test_predictions.py
│   │   ├── test_sorting_behavior.py
│   │   ├── test_determinism_preservation.py
│   │   ├── test_prediction_edge_cases.py
│   │   └── test_prediction_fields.py
│   ├── integration/       # Integration tests (19 tests)
│   │   ├── test_sequence_learning.py
│   │   ├── test_vector_e2e.py
│   │   └── test_vector_simplified.py
│   ├── api/              # API endpoint tests (21 tests)
│   │   └── test_rest_endpoints.py
│   └── performance/      # Performance tests (5 tests)
│       └── test_vector_stress.py
├── scripts/             # Utility scripts
│   ├── analyze_tests.py
│   ├── check_tests.py
│   ├── run_simple_test.py
│   ├── run_tests_direct.py
│   ├── setup_venv.py
│   └── simple_analyze.py
├── test-harness.sh      # Container-based test runner (preferred)
├── Dockerfile.test      # Test container definition
├── requirements-test.txt # Python test dependencies
├── pytest.ini           # Pytest configuration
├── conftest.py          # Pytest fixtures configuration
└── TEST_ORGANIZATION.md # Test structure documentation
```

## Running Tests

### Container-Based Testing (Preferred Method)

KATO uses a containerized test harness to ensure consistent test environments without requiring local Python dependencies:

```bash
# Build test harness container (first time or after dependency changes)
./test-harness.sh build

# Run all tests using kato-manager
./kato-manager.sh test

# OR run directly with test-harness
./test-harness.sh test
```

### Running Specific Test Categories

```bash
# Run specific test suites
./test-harness.sh suite unit          # Unit tests only
./test-harness.sh suite integration   # Integration tests only
./test-harness.sh suite api           # API tests only
./test-harness.sh suite performance   # Performance tests
./test-harness.sh suite determinism   # Determinism verification
./test-harness.sh suite optimizations # Optimization tests

# Run specific test path
./test-harness.sh test tests/tests/unit/test_observations.py

# Run with pytest options
./test-harness.sh test tests/ -v -x   # Verbose, stop on first failure
./test-harness.sh test tests/ -k "pattern" # Run tests matching pattern

# Development mode (live code updates)
./test-harness.sh dev tests/tests/unit/ -v

# Interactive shell for debugging
./test-harness.sh shell

# Generate coverage report
./test-harness.sh report
```

### Benefits of Container-Based Testing

- **No local dependencies**: All test dependencies are in the container
- **Consistency**: Same environment across all developers and CI/CD
- **Isolation**: Tests don't affect your host system
- **Reproducibility**: Guaranteed same test results
- **Easy cleanup**: Just remove the container

### Using Pytest Directly (Legacy Method)

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

### Unit Tests (83 tests)

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
Tests for short-term memory and long-term memory management:
- Clearing all memory
- Clearing short-term memory only
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

### Integration Tests (19 tests)

#### test_sequence_learning.py (11 tests)
End-to-end tests for sequence learning and recall

#### test_vector_e2e.py (5 tests)
End-to-end tests for vector functionality with new vector database architecture

#### test_vector_simplified.py (3 tests)
Simplified integration tests for basic vector operations

### Performance Tests (5 tests)

#### test_vector_stress.py
Stress and performance tests for vector operations:
- Vector operation performance at different dimensions
- Scalability with large numbers of vectors
- Accuracy of vector similarity search
- Vector persistence across learning cycles
- Edge cases with empty, large, and negative vectors
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
- Short-term memory endpoints (formerly working memory)
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
- **`missing`**: Symbols expected within the `present` state but not observed in short-term memory  
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
- Models survive short-term memory clears

### 4. Multi-Modal Processing
KATO processes multiple data types simultaneously:
- Strings (symbolic data)
- Vectors (numeric arrays)
- Emotives (key-value pairs for emotional context)

### 5. Empty Events
KATO ignores empty events - they do not change short-term memory or affect predictions:
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
- `assert_short_term_memory_equals()`: Assert with automatic sorting

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
    wm = kato_fixture.get_short_term_memory()
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
    from fixtures.test_helpers import assert_short_term_memory_equals
    
    kato_fixture.clear_all_memory()
    kato_fixture.observe({'strings': ['z', 'a', 'm'], 'vectors': [], 'emotives': {}})
    
    wm = kato_fixture.get_short_term_memory()
    # Automatically handles sorting: ['z', 'a', 'm'] -> ['a', 'm', 'z']
    assert_short_term_memory_equals(wm, [['z', 'a', 'm']])
```

### Testing Prediction Fields
```python
def test_prediction_temporal_fields(kato_fixture):
    # Learn: [['start'], ['middle'], ['end']]
    for item in ['start', 'middle', 'end']:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()
    
    # Observe middle
    kato_fixture.clear_short_term_memory()
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
    kato_fixture.clear_short_term_memory()
    kato_fixture.observe({'strings': ['a', 'x'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['c', 'y'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()
    
    for pred in predictions:
        if pred.get('frequency', 0) > 0:
            assert 'b' in pred['missing'] or 'd' in pred['missing']
            assert 'x' in pred['extras'] or 'y' in pred['extras']
```

## Recent Updates

### Test Organization (August 2025)
- Reorganized all test files into proper subdirectories under `tests/tests/`
- Moved vector tests to appropriate categories (integration and performance)
- Created `scripts/` directory for utility scripts
- Fixed all test warnings (DataGenerator class naming, test return values)
- Updated fixture imports for new directory structure
- All 128 tests passing with 0 warnings

## Troubleshooting

### Docker Issues
- **Container not starting**: Check Docker Desktop is running
- **Port conflicts**: Ensure port 8000 is available
- **Build failures**: Try `docker system prune -a` and rebuild

### Test Failures
- **Timeout errors**: Increase timeout in pytest.ini
- **Import errors**: Check PYTHONPATH includes parent directories
- **Sorting mismatches**: Use `assert_short_term_memory_equals()` helper

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

## Auto-Learning Tests

### Overview

Auto-learning tests validate the `max_sequence_length` functionality where KATO automatically learns sequences when short-term memory reaches a specified threshold.

**Key Tests:**
- `test_memory_management.py::test_max_sequence_length` - Core auto-learning behavior
- `test_sequence_learning.py::test_max_sequence_length_auto_learn` - Integration testing

### Test Behavior

When `max_sequence_length` is set to a positive value:

1. **Accumulation**: Working memory accumulates observations normally
2. **Trigger**: At threshold, auto-learning activates
3. **Learning**: Entire sequence is learned as a model
4. **Reset**: Working memory cleared, keeping only last observation

**Example Test Pattern:**
```python
def test_max_sequence_length(kato_fixture):
    # Set up auto-learning threshold
    kato_fixture.clear_short_term_memory()  # Don't reset genes
    kato_fixture.update_genes({"max_sequence_length": 3})
    
    # Accumulate observations
    kato_fixture.observe({'strings': ['a'], 'vectors': [], 'emotives': {}})
    assert len(kato_fixture.get_short_term_memory()) == 1
    
    kato_fixture.observe({'strings': ['b'], 'vectors': [], 'emotives': {}})
    assert len(kato_fixture.get_short_term_memory()) == 2
    
    # Trigger auto-learning
    kato_fixture.observe({'strings': ['c'], 'vectors': [], 'emotives': {}})
    wm = kato_fixture.get_short_term_memory()
    assert wm == [['c']]  # Only last observation remains
    
    # Verify learning occurred
    kato_fixture.clear_short_term_memory()
    kato_fixture.observe({'strings': ['a'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()
    assert len(predictions) > 0  # Should predict learned sequence
```

### Common Issues

**Issue: Gene values persist between tests**
```python
# WRONG: This will reset genes after setting them
kato_fixture.update_genes({"max_sequence_length": 3})
kato_fixture.clear_all_memory()  # Resets genes to default!

# RIGHT: Clear first, then set genes
kato_fixture.clear_short_term_memory()  # Only clear memory, preserve genes
kato_fixture.update_genes({"max_sequence_length": 3})
```

**Issue: Auto-learning not triggering**
- Verify gene update worked: check actual gene value
- Ensure Docker container includes latest code changes
- Check ZMQ communication is working

## Test Isolation

### Gene Value Isolation

The `kato_fixtures.py` provides gene isolation utilities:

**Fixture Methods:**
```python
# Reset specific genes to defaults
fixture.reset_genes_to_defaults()

# Clear memory with optional gene reset
fixture.clear_all_memory(reset_genes=True)  # Default: resets genes
fixture.clear_all_memory(reset_genes=False) # Preserve gene values

# Clear only short-term memory (preserves genes)
fixture.clear_short_term_memory()
```

**Best Practices:**
1. Use `clear_short_term_memory()` when preserving gene settings
2. Use `clear_all_memory()` for complete isolation
3. Set genes AFTER clearing, not before
4. Verify gene values with `update_genes()` return value

### Test Dependencies

**Container State:**
- Tests share the same KATO instance (module-scoped fixture)
- Gene values persist across tests within a module
- Working memory and models are shared

**Safe Testing Pattern:**
```python
def test_with_custom_genes(kato_fixture):
    # Clear state first
    kato_fixture.clear_short_term_memory()
    
    # Set test-specific genes
    kato_fixture.update_genes({"max_sequence_length": 5})
    
    # Perform test
    # ... test logic ...
    
    # Optional: Reset for next test (usually not needed)
    # kato_fixture.reset_genes_to_defaults()
```

## Adding New Tests

1. **Choose appropriate directory**:
   - `unit/` for isolated component tests
   - `integration/` for multi-component tests
   - `api/` for endpoint tests

2. **Use existing fixtures**:
   ```python
   from fixtures.kato_fixtures import kato_fixture
   from fixtures.test_helpers import assert_short_term_memory_equals
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