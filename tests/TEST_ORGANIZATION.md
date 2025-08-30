# Test Organization

## Standalone Tests (No KATO Services Required)

These tests can run without KATO services:

1. **tests/test_optimizations_standalone.py**
   - Tests for optimization modules (FastSequenceMatcher, RollingHash, NGramIndex, InvertedIndex)
   - Performance comparisons
   - No API or database dependencies

## KATO-Dependent Tests (Require Running Services)

These tests require KATO services (MongoDB, Redis, Qdrant, KATO API):

### Unit Tests (tests/tests/unit/)
- test_memory_management.py
- test_observations.py
- test_predictions.py
- test_prediction_edge_cases.py
- test_prediction_fields.py
- test_sorting_behavior.py
- test_determinism_preservation.py
- test_model_hashing.py
- test_recall_threshold_values.py
- test_recall_threshold_sequences.py
- test_recall_threshold_edge_cases.py

### Integration Tests (tests/tests/integration/)
- test_sequence_learning.py
- test_multimodal_processing.py
- test_learning_patterns.py
- test_model_transitions.py
- test_vector_processing.py

### API Tests (tests/tests/api/)
- test_rest_endpoints.py
- test_processor_state.py
- test_api_error_handling.py

### Performance Tests (tests/tests/performance/)
- test_stress_tests.py
- test_large_scale_operations.py

## Test Execution Strategies

### Run All Tests (Default)
```bash
./test-harness.sh test  # Automatically starts/stops services
```

### Run Only Standalone Tests
```bash
./test-harness.sh --standalone test
```

### Run Tests Without Service Management
```bash
./test-harness.sh --no-start --no-stop test
```

### Keep Services Running After Tests
```bash
./test-harness.sh --no-stop test
```

## Service Requirements

### Required Services
1. **MongoDB** (mongo-kb) - For long-term memory storage
2. **Redis** (redis-cache) - For caching and fast lookups
3. **Qdrant** (qdrant) - For vector similarity search
4. **KATO API** (kato-api) - The main KATO service

### Service Management Commands
```bash
./test-harness.sh start-services   # Start all services
./test-harness.sh stop-services    # Stop all services
./test-harness.sh check-services   # Check service status
```
EOF < /dev/null
