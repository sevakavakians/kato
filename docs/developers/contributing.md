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

# Build test harness container (includes all dependencies)
./test-harness.sh build
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

KATO uses clustered testing for complete isolation:

```bash
# Build test harness (first time)
./test-harness.sh build

# Run all tests with automatic clustering
./kato-manager.sh test
# OR
./test-harness.sh test

# Run specific test suite (automatically clustered)
./test-harness.sh suite unit

# Run specific test file (finds appropriate cluster)
./test-harness.sh test tests/tests/unit/test_your_feature.py

# Run with detailed output
./test-harness.sh --verbose test      # Show cluster execution
./test-harness.sh --no-redirect test  # Direct console output

# Generate coverage report
./test-harness.sh report
```

**Important**: Tests are automatically grouped into clusters based on configuration requirements. Each cluster runs with its own KATO instance and isolated databases to prevent contamination.

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
4. **Use PTRN| Prefix**: All pattern names must start with PTRN|
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
def test_pattern_learning_and_recall(kato_fixture):
    """Test end-to-end pattern learning"""
    # Learn pattern
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
2. Add examples to docs/users/quick-start.md if user-facing
3. Update docs/users/api-reference.md for new endpoints
4. Document configuration in docs/operations/configuration.md

### Keep documentation evergreen

**Release versions live in `CHANGELOG.md` and `planning-docs/`. Nowhere else.**

Every version number written into a guide is a line that silently goes stale: it
is correct on the day it is written and wrong from the next release onward, and
nothing fails when it rots. A reader following an install snippet that names a
release three majors old gets a working command and the wrong software, which is
worse than an error. This had happened in eleven files at once, spanning eight
different versions, before the rule was written down.

So, outside `CHANGELOG.md` and `planning-docs/`:

- **Do not name a release.** Not in prose, not in a heading, not in a snippet.
- **Container images** use `:latest` when the example only needs to run the image.
  When the point of the example *is* pinning, write the placeholder
  `ghcr.io/sevakavakians/kato:<version>` and link to
  [releases](https://github.com/sevakavakians/kato/releases) for the current
  number. Keep the advice, drop the digits.
- **No `Last Updated` or `KATO Version` footers.** Git history already records
  when a file changed, and it cannot fall out of date.

There is one exception, and it is about the reader, not the writer:

- **Availability markers.** Write "available as of v6.3" only where a reader on an
  earlier version would need to act differently — a feature that is simply absent
  for them, or behaviour that changed under them. If every supported reader sees
  the same thing, the version adds nothing and goes.

Documents that define the release process itself — `docs/maintenance/releasing.md`,
`version-management.md`, `changelog-guidelines.md` — necessarily discuss version
numbers. Use obvious placeholders (`X.Y.Z`) for the scheme, and clearly
hypothetical numbers for worked examples, so neither can be mistaken for a current
release.

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
# Run with debug logging. LOG_LEVEL is an environment variable, not a flag --
# set it in docker-compose.yml (or .env) and restart the service.
LOG_LEVEL=DEBUG docker compose up -d kato

# Open a shell in the container
docker exec -it kato /bin/bash

# View logs
docker compose logs kato -f
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
4. Run full clustered test suite with `./test-harness.sh test`
5. Create GitHub release
6. Tag Docker images

## Getting Help

### Resources

- [System Overview](../SYSTEM_OVERVIEW.md) - Architecture understanding
- [Core Concepts](../CONCEPTS.md) - KATO behavior reference
- [Testing Guide](../developers/testing.md) - Test writing help
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

By contributing, you agree that your contributions will be licensed under the Apache License, Version 2.0 — the same license as KATO. See the [LICENSE](../../LICENSE) file for the full text.

## Recognition

Contributors are recognized in:
- CHANGELOG.md for specific features
- GitHub contributors page
- Project documentation

Thank you for contributing to KATO!
