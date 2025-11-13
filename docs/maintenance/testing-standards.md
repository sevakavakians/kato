# KATO Testing Standards

## Overview

This document expands on [/docs/developers/testing.md](/docs/developers/testing.md) with maintainer-specific testing standards, coverage targets, and quality guidelines.

## Table of Contents
1. [Testing Pyramid](#testing-pyramid)
2. [Coverage Targets](#coverage-targets)
3. [Test Types](#test-types)
4. [Test Quality](#test-quality)
5. [Performance Testing](#performance-testing)
6. [Test Infrastructure](#test-infrastructure)

## Testing Pyramid

```
           /\
          /  \          ← E2E (5%)
         /    \
        /------\        ← Integration (20%)
       /        \
      /----------\      ← Unit (75%)
     /            \
```

### Distribution

- **Unit Tests:** 75% - Fast, isolated, comprehensive
- **Integration Tests:** 20% - Component interaction
- **E2E/API Tests:** 5% - Full system workflows

## Coverage Targets

### Overall Targets

| Type | Minimum | Target | Current |
|------|---------|--------|---------|
| Overall | 80% | 90% | ~85% |
| Core Logic | 90% | 100% | ~90% |
| API Layer | 80% | 90% | ~85% |
| Workers | 90% | 100% | ~92% |
| Storage | 80% | 90% | ~80% |

### Per-File Standards

```bash
# Check coverage by file
pytest --cov=kato --cov-report=term-missing tests/

# Enforce minimum
pytest --cov=kato --cov-fail-under=80 tests/
```

### New Code Policy

**All new code must have 100% coverage** unless explicitly justified.

```python
# Mark untestable code
def platform_specific_function():
    if sys.platform == "win32":
        return windows_implementation()  # pragma: no cover
    return unix_implementation()
```

## Test Types

### Unit Tests (tests/tests/unit/)

**Purpose:** Test individual functions/classes in isolation

```python
def test_pattern_matching_exact():
    """Test exact pattern matching."""
    matcher = PatternMatcher(mode="token")
    pattern = ["a", "b", "c"]
    candidates = [
        ["a", "b", "c"],  # Exact match
        ["a", "b", "d"],  # No match
    ]

    matches = matcher.find_matches(pattern, candidates)

    assert len(matches) == 1
    assert matches[0] == ["a", "b", "c"]

def test_session_manager_create():
    """Test session creation."""
    manager = SessionManager(redis_client=mock_redis)

    session_id = manager.create_session("user-123")

    assert session_id.startswith("user-123")
    assert manager.session_exists(session_id)
```

### Integration Tests (tests/tests/integration/)

**Purpose:** Test component interactions

```python
@pytest.mark.integration
async def test_observe_and_predict_workflow():
    """Test complete observe-predict workflow."""
    # Create session
    async with httpx.AsyncClient() as client:
        session_response = await client.post(
            f"{KATO_URL}/sessions",
            json={"node_id": "test-user"}
        )
        session_id = session_response.json()["session_id"]

        # Send observations
        for obs in ["a", "b", "c"]:
            await client.post(
                f"{KATO_URL}/sessions/{session_id}/observe",
                json={"strings": [obs], "vectors": [], "emotives": {}}
            )

        # Get predictions
        pred_response = await client.get(
            f"{KATO_URL}/sessions/{session_id}/predictions"
        )
        predictions = pred_response.json()

        assert len(predictions) > 0
```

### API Tests (tests/tests/api/)

**Purpose:** Test REST API endpoints

```python
def test_create_session_endpoint(client):
    """Test POST /sessions endpoint."""
    response = client.post(
        "/sessions",
        json={"node_id": "test-user"}
    )

    assert response.status_code == 200
    data = response.json()
    assert "session_id" in data
    assert data["node_id"] == "test-user"

def test_observe_endpoint_validation(client, session_id):
    """Test observation validation."""
    # Missing required field
    response = client.post(
        f"/sessions/{session_id}/observe",
        json={"strings": []}  # Missing vectors, emotives
    )

    assert response.status_code == 422
```

### Performance Tests (tests/tests/performance/)

**Purpose:** Verify performance requirements

```python
@pytest.mark.performance
def test_prediction_latency(benchmark, kato_client):
    """Test prediction generation is under 100ms."""
    session_id = kato_client.create_session("perf-test")

    # Warm up
    for i in range(10):
        kato_client.observe(session_id, {"strings": [f"item-{i}"]})

    # Benchmark
    result = benchmark(kato_client.get_predictions, session_id)

    assert benchmark.stats["mean"] < 0.1  # <100ms
```

## Test Quality

### Test Naming

```python
# Good: Descriptive test names
def test_session_manager_creates_unique_session_ids():
    """Verify each session gets unique ID."""
    ...

def test_pattern_matcher_handles_empty_pattern():
    """Test behavior with empty pattern input."""
    ...

# Bad: Vague names
def test_session():
    ...

def test_pattern():
    ...
```

### Arrange-Act-Assert Pattern

```python
def test_example():
    # Arrange: Set up test data
    session_id = "test-123"
    observation = {"strings": ["a", "b"], "vectors": [], "emotives": {}}

    # Act: Execute the code under test
    result = process_observation(session_id, observation)

    # Assert: Verify expectations
    assert result["status"] == "success"
    assert len(result["predictions"]) > 0
```

### Test Independence

```python
# Good: Independent tests
@pytest.fixture
def clean_session():
    """Provide clean session for each test."""
    session_id = create_session()
    yield session_id
    delete_session(session_id)

def test_a(clean_session):
    # Test uses its own session
    ...

def test_b(clean_session):
    # Test uses its own session
    ...

# Bad: Tests depend on each other
def test_create():
    global session_id
    session_id = create_session()

def test_use():
    # Depends on test_create running first!
    use_session(session_id)
```

### Edge Case Coverage

```python
def test_input_validation():
    """Test all edge cases for input validation."""
    # Empty input
    with pytest.raises(ValueError):
        process_data([])

    # None input
    with pytest.raises(TypeError):
        process_data(None)

    # Invalid type
    with pytest.raises(TypeError):
        process_data("not a list")

    # Oversized input
    with pytest.raises(ValueError):
        process_data([1] * 10000)
```

## Performance Testing

### Latency Benchmarks

```python
import pytest

@pytest.mark.benchmark
def test_pattern_matching_performance(benchmark):
    """Verify pattern matching completes in <10ms."""
    matcher = PatternMatcher()
    pattern = ["a"] * 100
    candidates = [["a"] * 100 for _ in range(1000)]

    result = benchmark(matcher.find_matches, pattern, candidates)

    assert benchmark.stats["mean"] < 0.01  # <10ms
```

### Load Testing

```python
@pytest.mark.load
async def test_concurrent_requests():
    """Test 100 concurrent requests."""
    async with httpx.AsyncClient() as client:
        tasks = [
            client.post(f"{KATO_URL}/sessions", json={"node_id": f"user-{i}"})
            for i in range(100)
        ]

        responses = await asyncio.gather(*tasks)

        assert all(r.status_code == 200 for r in responses)
```

### Memory Testing

```python
import tracemalloc

def test_memory_usage():
    """Verify memory usage stays under 100MB."""
    tracemalloc.start()

    # Perform memory-intensive operation
    process_large_dataset()

    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    assert peak < 100 * 1024 * 1024  # <100MB
```

## Test Infrastructure

### Fixtures

```python
@pytest.fixture(scope="session")
def kato_services():
    """Start KATO services once per test session."""
    subprocess.run(["./start.sh"], check=True)
    yield
    subprocess.run(["docker-compose", "down"], check=True)

@pytest.fixture
def unique_processor_id():
    """Provide unique processor ID for test isolation."""
    timestamp = int(time.time())
    uuid = str(uuid4())[:8]
    return f"test_{timestamp}_{uuid}"
```

### Marks

```python
# Register custom marks in pytest.ini
[tool.pytest.ini_options]
markers = [
    "unit: Unit tests",
    "integration: Integration tests",
    "api: API tests",
    "performance: Performance tests",
    "slow: Slow tests (>1s)",
]

# Use in tests
@pytest.mark.unit
def test_unit():
    ...

@pytest.mark.integration
@pytest.mark.slow
def test_integration():
    ...

# Run specific marks
pytest -m unit
pytest -m "not slow"
```

### Parametrize

```python
@pytest.mark.parametrize("input,expected", [
    ([], []),
    (["a"], ["a"]),
    (["a", "b"], ["a", "b"]),
    (["a", "a"], ["a"]),  # Duplicates removed
])
def test_process_strings(input, expected):
    result = process_strings(input)
    assert result == expected
```

## Best Practices

1. **Test behavior, not implementation**
2. **One assertion per test** (when possible)
3. **Use descriptive names**
4. **Keep tests DRY** (fixtures for common setup)
5. **Test edge cases**
6. **Mock external dependencies**
7. **Fast unit tests** (<100ms each)
8. **Reliable tests** (no flakiness)
9. **Maintainable tests** (easy to understand)
10. **Document complex tests**

## Related Documentation

- [Testing Guide (Developers)](/docs/developers/testing.md)
- [Code Quality Standards](code-quality.md)
- [Code Review Guidelines](code-review.md)

---

**Last Updated**: November 2025
**KATO Version**: 3.0+
