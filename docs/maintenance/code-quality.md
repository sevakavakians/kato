# KATO Code Quality Standards

## Overview

This document defines code quality standards, metrics, and tools for maintaining KATO's codebase health.

## Table of Contents
1. [Quality Metrics](#quality-metrics)
2. [Linting and Formatting](#linting-and-formatting)
3. [Type Checking](#type-checking)
4. [Code Complexity](#code-complexity)
5. [Test Coverage](#test-coverage)
6. [Documentation Standards](#documentation-standards)
7. [CI/CD Quality Gates](#cicd-quality-gates)

## Quality Metrics

### Target Metrics

| Metric | Target | Current | Tool |
|--------|--------|---------|------|
| Test Coverage | >80% | ~85% | pytest-cov |
| Test Pass Rate | 100% | 99.5% | pytest |
| Lint Errors | 0 | 0 | ruff |
| Type Coverage | >90% | ~75% | mypy |
| Complexity | <10 | <15 | radon |
| Duplicates | <3% | <2% | duplicate-code-detection-tool |

### Monitoring

```bash
# Run all quality checks
./scripts/quality-check.sh

# Individual checks
ruff check kato/                    # Linting
mypy kato/                          # Type checking
pytest --cov=kato tests/            # Coverage
radon cc kato/ -a                   # Complexity
```

## Linting and Formatting

### Ruff Configuration

**pyproject.toml:**
```toml
[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = [
    "E",   # pycodestyle errors
    "W",   # pycodestyle warnings
    "F",   # pyflakes
    "I",   # isort
    "N",   # pep8-naming
    "UP",  # pyupgrade
    "B",   # flake8-bugbear
    "C4",  # flake8-comprehensions
    "SIM", # flake8-simplify
]

ignore = [
    "E501",  # line too long (handled by formatter)
    "B008",  # do not perform function calls in argument defaults
]

[tool.ruff.lint.per-file-ignores]
"__init__.py" = ["F401"]  # Allow unused imports in __init__
"tests/**/*.py" = ["S101"]  # Allow assert in tests
```

### Running Linter

```bash
# Check for issues
ruff check kato/

# Auto-fix issues
ruff check --fix kato/

# Format code
ruff format kato/

# Check specific file
ruff check kato/workers/kato_processor.py
```

### Pre-Commit Hook

**.pre-commit-config.yaml:**
```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.1.9
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
```

Install:
```bash
pip install pre-commit
pre-commit install
```

## Type Checking

### MyPy Configuration

**pyproject.toml:**
```toml
[tool.mypy]
python_version = "3.11"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true
disallow_incomplete_defs = true
check_untyped_defs = true
no_implicit_optional = true

[[tool.mypy.overrides]]
module = "tests.*"
disallow_untyped_defs = false
```

### Type Hints Standard

```python
# Good: Fully typed function
def process_observation(
    observation: dict[str, Any],
    session_id: str,
    config: SessionConfig
) -> PredictionResult:
    """Process observation and return predictions."""
    ...

# Good: Type hints for complex structures
from typing import TypedDict

class ObservationData(TypedDict):
    strings: list[str]
    vectors: list[list[float]]
    emotives: dict[str, float]

def observe(data: ObservationData) -> None:
    ...

# Good: Generic types
from typing import TypeVar, Generic

T = TypeVar('T')

class Cache(Generic[T]):
    def get(self, key: str) -> Optional[T]:
        ...

# Bad: No type hints
def process_data(data):
    return do_something(data)
```

### Running Type Checker

```bash
# Check all files
mypy kato/

# Check specific module
mypy kato/workers/

# Generate coverage report
mypy --html-report ./mypy-report kato/
```

## Code Complexity

### Cyclomatic Complexity

**Target:** <10 per function

```bash
# Check complexity
radon cc kato/ -a -nb

# Show only high complexity (>10)
radon cc kato/ -n C

# Generate JSON report
radon cc kato/ -j > complexity-report.json
```

### Reducing Complexity

❌ **Bad: High complexity (CC=15)**
```python
def process_prediction(prediction, config, stm, ltm, filters):
    if prediction is None:
        return []

    if config.use_filters:
        if filters.token_filter:
            prediction = apply_token_filter(prediction)
        if filters.fuzzy_filter:
            prediction = apply_fuzzy_filter(prediction)

    if config.use_threshold:
        if prediction.score < config.threshold:
            return []

    if stm.has_context():
        if stm.matches(prediction):
            return process_with_stm(prediction, stm)
        else:
            if ltm.has_patterns():
                return process_with_ltm(prediction, ltm)

    return [prediction]
```

✅ **Good: Lower complexity (CC=5)**
```python
def process_prediction(prediction, config, stm, ltm, filters):
    if prediction is None:
        return []

    prediction = _apply_filters(prediction, config, filters)

    if not _meets_threshold(prediction, config):
        return []

    return _process_with_memory(prediction, stm, ltm)

def _apply_filters(prediction, config, filters):
    if not config.use_filters:
        return prediction

    if filters.token_filter:
        prediction = apply_token_filter(prediction)
    if filters.fuzzy_filter:
        prediction = apply_fuzzy_filter(prediction)

    return prediction

def _meets_threshold(prediction, config):
    return not config.use_threshold or prediction.score >= config.threshold

def _process_with_memory(prediction, stm, ltm):
    if stm.has_context() and stm.matches(prediction):
        return process_with_stm(prediction, stm)
    if ltm.has_patterns():
        return process_with_ltm(prediction, ltm)
    return [prediction]
```

## Test Coverage

### Coverage Configuration

**pyproject.toml:**
```toml
[tool.coverage.run]
source = ["kato"]
omit = [
    "*/tests/*",
    "*/__init__.py",
    "*/migrations/*"
]

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "raise AssertionError",
    "raise NotImplementedError",
    "if __name__ == .__main__.:",
    "if TYPE_CHECKING:",
]
```

### Running Coverage

```bash
# Run with coverage
pytest --cov=kato --cov-report=html tests/

# View report
open htmlcov/index.html

# Show missing lines
pytest --cov=kato --cov-report=term-missing tests/

# Fail if coverage below threshold
pytest --cov=kato --cov-fail-under=80 tests/
```

### Coverage Standards

- **Overall:** >80%
- **Core modules:** >90%
- **New code:** 100%
- **Critical paths:** 100%

```python
# Mark code that shouldn't be covered
def debug_only_function():
    if not DEBUG:
        return  # pragma: no cover
    ...

# Type checking blocks
if TYPE_CHECKING:  # pragma: no cover
    from typing import SomeType
```

## Documentation Standards

### Docstring Format

Use Google-style docstrings:

```python
def predict_next(
    session_id: str,
    limit: int = 10,
    threshold: float = 0.1
) -> list[Prediction]:
    """Generate predictions for session.

    Analyzes current STM state and LTM patterns to predict likely
    next observations based on learned temporal patterns.

    Args:
        session_id: Unique session identifier
        limit: Maximum number of predictions to return
        threshold: Minimum confidence threshold (0.0-1.0)

    Returns:
        List of predictions sorted by confidence score

    Raises:
        SessionNotFoundError: If session_id doesn't exist
        ValueError: If threshold not in valid range

    Example:
        >>> predictions = predict_next("session-123", limit=5)
        >>> for pred in predictions:
        ...     print(pred.future)
    """
    ...
```

### Module Documentation

```python
"""Pattern matching module for KATO.

This module provides pattern matching algorithms including token-level
and character-level matching with configurable similarity thresholds.

Classes:
    PatternMatcher: Main pattern matching interface
    TokenMatcher: Token-level matching (faster, exact)
    FuzzyMatcher: Character-level matching (slower, fuzzy)

Example:
    >>> matcher = PatternMatcher(mode="token")
    >>> matches = matcher.find_matches(pattern, candidates)
"""
```

### Documentation Coverage

```bash
# Check docstring coverage
pydocstyle kato/

# Generate documentation
sphinx-build -b html docs/ docs/_build/
```

## CI/CD Quality Gates

### GitHub Actions Workflow

**.github/workflows/quality.yml:**
```yaml
name: Code Quality

on: [push, pull_request]

jobs:
  quality:
    runs-on: ubuntu-latest

    steps:
    - uses: actions/checkout@v3

    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'

    - name: Install dependencies
      run: |
        pip install -r requirements.txt
        pip install ruff mypy pytest pytest-cov radon

    - name: Lint with Ruff
      run: ruff check kato/

    - name: Type check with MyPy
      run: mypy kato/

    - name: Check complexity
      run: radon cc kato/ -n C --total-average

    - name: Run tests with coverage
      run: pytest --cov=kato --cov-fail-under=80 tests/

    - name: Upload coverage
      uses: codecov/codecov-action@v3
```

### Pull Request Checklist

Before merging:

- [ ] All tests pass
- [ ] No linting errors
- [ ] Type checking passes
- [ ] Coverage >80% (or unchanged)
- [ ] Complexity acceptable (<10)
- [ ] Documentation updated
- [ ] CHANGELOG.md updated
- [ ] Code reviewed

## Best Practices

1. **Write tests first** - TDD approach
2. **Keep functions small** - <50 lines
3. **Single responsibility** - One purpose per function
4. **Type everything** - Full type coverage
5. **Document public APIs** - Comprehensive docstrings
6. **Review complexity** - Refactor if >10
7. **Monitor coverage** - Never decrease
8. **Run quality checks** - Before every commit
9. **Fix warnings** - Zero-warning policy
10. **Automate** - CI/CD enforces standards

## Tools Summary

| Tool | Purpose | Command |
|------|---------|---------|
| ruff | Linting & formatting | `ruff check kato/` |
| mypy | Type checking | `mypy kato/` |
| pytest | Testing | `pytest tests/` |
| coverage.py | Test coverage | `pytest --cov=kato` |
| radon | Complexity | `radon cc kato/` |
| pre-commit | Git hooks | `pre-commit run` |

## Related Documentation

- [Code Review Guidelines](code-review.md)
- [Testing Standards](testing-standards.md)
- [Contributing Guide](/docs/developers/contributing.md)

---

**Last Updated**: November 2025
**KATO Version**: 3.0+
