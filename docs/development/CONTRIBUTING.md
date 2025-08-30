# Contributing to KATO

Thank you for your interest in contributing to KATO! This guide will help you get started with development.

## Development Setup

### Prerequisites

- Python 3.8+
- Docker Desktop
- Git
- Make (optional)

### Clone and Setup

```bash
# Clone the repository
git clone https://github.com/your-org/kato.git
cd kato

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
pip install -e .  # Install KATO in development mode

# Install test dependencies
pip install -r tests/requirements.txt
```

## Code Structure

```
kato/
├── kato/                   # Main package
│   ├── workers/           # Core processors and servers
│   ├── representations/  # Data structures
│   ├── searches/         # Search algorithms
│   ├── informatics/      # Metrics and analysis
│   └── scripts/          # Entry points
├── tests/                 # Test suite
│   ├── unit/             # Unit tests
│   ├── integration/      # Integration tests
│   └── api/              # API tests
└── docs/                  # Documentation
```

## Development Workflow

### 1. Create a Branch

```bash
git checkout -b feature/your-feature-name
# or
git checkout -b fix/issue-description
```

### 2. Make Changes

Follow these guidelines:
- Write clean, readable code
- Follow Python PEP 8 style guide
- Add docstrings to functions and classes
- Maintain KATO's deterministic behavior

### 3. Write Tests

Every new feature or bug fix should include tests:

```python
# tests/unit/test_your_feature.py
def test_new_feature(kato_fixture):
    """Test description"""
    # Arrange
    kato_fixture.clear_all_memory()
    
    # Act
    result = kato_fixture.your_new_method()
    
    # Assert
    assert result == expected_value
```

### 4. Run Tests

```bash
# Build test harness (first time)
./test-harness.sh build

# Run all tests in container
./kato-manager.sh test
# OR
./test-harness.sh test

# Run specific test suite
./test-harness.sh suite unit

# Run specific test file
./test-harness.sh test tests/tests/unit/test_your_feature.py

# Generate coverage report
./test-harness.sh report
```

### 5. Update Documentation

- Update relevant .md files in docs/
- Add docstrings to new code
- Update CHANGELOG.md if applicable

### 6. Commit Changes

```bash
git add .
git commit -m "Type: Brief description

Detailed explanation of what changed and why.
Fixes #123"
```

Commit message types:
- `feat:` New feature
- `fix:` Bug fix
- `docs:` Documentation changes
- `test:` Test additions/changes
- `refactor:` Code refactoring
- `perf:` Performance improvements
- `chore:` Maintenance tasks

### 7. Push and Create PR

```bash
git push origin feature/your-feature-name
```

Then create a Pull Request on GitHub.

## Code Guidelines

### Python Style

```python
# Good
def calculate_similarity(self, vector_a: np.ndarray, vector_b: np.ndarray) -> float:
    """
    Calculate cosine similarity between two vectors.
    
    Args:
        vector_a: First vector
        vector_b: Second vector
        
    Returns:
        Similarity score between 0 and 1
    """
    # Implementation
```

### KATO-Specific Guidelines

1. **Maintain Determinism**: Same inputs must always produce same outputs
2. **Preserve Sorting**: Strings are sorted alphanumerically within events
3. **Handle Empty Events**: Empty observations should be ignored
4. **Use MODEL| Prefix**: All model names must start with MODEL|
5. **Test Helpers**: Use provided test helpers for assertions

### Error Handling

```python
# Good
try:
    result = process_observation(data)
except ValueError as e:
    logger.error(f"Invalid observation data: {e}")
    return {"status": "error", "message": str(e)}
```

## Testing Guidelines

### Unit Tests

Test individual components in isolation:

```python
def test_alphanumeric_sorting():
    """Test that strings are sorted within events"""
    input_strings = ['zebra', 'apple', 'banana']
    expected = ['apple', 'banana', 'zebra']
    result = sort_event_strings(input_strings)
    assert result == expected
```

### Integration Tests

Test component interactions:

```python
def test_sequence_learning_and_recall(kato_fixture):
    """Test end-to-end sequence learning"""
    # Learn sequence
    for item in ['a', 'b', 'c']:
        kato_fixture.observe({'strings': [item]})
    kato_fixture.learn()
    
    # Test recall
    kato_fixture.clear_short_term_memory()
    kato_fixture.observe({'strings': ['a']})
    predictions = kato_fixture.get_predictions()
    assert len(predictions) > 0
```

### Test Coverage

Aim for:
- 80%+ code coverage
- 100% coverage for critical paths
- Edge case testing

## Documentation

### Docstring Format

Use Google-style docstrings:

```python
def process_emotives(self, emotives: Dict[str, float]) -> Dict[str, float]:
    """Process and aggregate emotional values.
    
    Args:
        emotives: Dictionary of emotive names to values (0.0-1.0)
        
    Returns:
        Aggregated emotives dictionary
        
    Raises:
        ValueError: If emotive values are outside 0.0-1.0 range
    """
```

### Updating Documentation

When adding features:
1. Update relevant docs/*.md files
2. Add examples to GETTING_STARTED.md if user-facing
3. Update API_REFERENCE.md for new endpoints
4. Document configuration in CONFIGURATION.md

## Performance Considerations

### Profiling

```python
import cProfile
import pstats

def profile_function():
    profiler = cProfile.Profile()
    profiler.enable()
    
    # Your code here
    
    profiler.disable()
    stats = pstats.Stats(profiler)
    stats.sort_stats('cumulative')
    stats.print_stats(10)
```

### Optimization Guidelines

1. Profile before optimizing
2. Maintain readability
3. Document performance-critical sections
4. Add benchmarks for optimizations

## Debugging

### Local Debugging

```python
# Add debug logging
import logging
logger = logging.getLogger(__name__)
logger.debug(f"Short-term memory state: {short_term_memory}")
```

### Docker Debugging

```bash
# Run with debug logging
./kato-manager.sh start --log-level DEBUG

# Open shell in container
./kato-manager.sh shell

# View logs
./kato-manager.sh logs kato -f
```

## Pull Request Process

### PR Checklist

- [ ] Tests pass locally
- [ ] Code follows style guidelines
- [ ] Documentation updated
- [ ] Commit messages are clear
- [ ] PR description explains changes
- [ ] No merge conflicts

### PR Template

```markdown
## Description
Brief description of changes

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## Testing
- [ ] Unit tests pass
- [ ] Integration tests pass
- [ ] Manual testing completed

## Checklist
- [ ] Code follows project style
- [ ] Self-review completed
- [ ] Documentation updated
- [ ] Tests added/updated
```

## Release Process

1. Update version in setup.py
2. Update CHANGELOG.md
3. Create release branch
4. Run full test suite with `./test-harness.sh test`
5. Create GitHub release
6. Tag Docker images

## Getting Help

### Resources

- [System Overview](../SYSTEM_OVERVIEW.md) - Architecture understanding
- [Core Concepts](../CONCEPTS.md) - KATO behavior reference
- [Testing Guide](TESTING.md) - Test writing help
- GitHub Issues - Bug reports and features

### Communication

- Open an issue for bugs
- Discuss features before implementing
- Ask questions in discussions
- Join development meetings (if applicable)

## Code of Conduct

- Be respectful and inclusive
- Welcome newcomers
- Provide constructive feedback
- Focus on what's best for the project
- Show empathy towards others

## License

By contributing, you agree that your contributions will be licensed under the same license as KATO (see LICENSE file).

## Recognition

Contributors are recognized in:
- CHANGELOG.md for specific features
- GitHub contributors page
- Project documentation

Thank you for contributing to KATO!