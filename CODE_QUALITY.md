# Code Quality & Testing Guide

This document describes the code quality tools and processes for the KATO project.

## Quick Start

```bash
# Install development dependencies
make install-dev

# Run all quality checks
make quality

# Run tests with coverage
make test-cov
```

## Code Quality Tools

### 1. Ruff - Fast Python Linter & Formatter

**Purpose**: Combines functionality of flake8, isort, pyupgrade, and more in a single fast tool.

**Configuration**: See `[tool.ruff]` in `pyproject.toml`

**Usage**:
```bash
# Check code
make lint
# or
ruff check kato/ tests/

# Auto-fix issues
make format
# or
ruff check --fix kato/
ruff format kato/
```

**Rules Enabled**:
- E/W: pycodestyle errors and warnings
- F: pyflakes
- I: isort (import sorting)
- N: pep8-naming
- UP: pyupgrade (modern Python syntax)
- B: flake8-bugbear (common bugs)
- C4: flake8-comprehensions
- SIM: flake8-simplify

### 2. Bandit - Security Scanner

**Purpose**: Identifies common security issues in Python code.

**Configuration**: See `[tool.bandit]` in `pyproject.toml`

**Usage**:
```bash
make security
# or
bandit -r kato/ -c pyproject.toml
```

**What it checks**:
- SQL injection vulnerabilities
- Shell injection risks
- Insecure cryptography usage
- Hard-coded passwords
- Insecure deserialization
- And more...

### 3. Vulture - Dead Code Detector

**Purpose**: Finds unused code (functions, variables, imports).

**Configuration**: See `[tool.vulture]` in `pyproject.toml`

**Usage**:
```bash
make dead-code
# or
vulture kato/ --min-confidence 80
```

**Note**: Some "unused" code may be intentional (e.g., API endpoints, callbacks). Review findings carefully.

### 4. pytest-cov - Test Coverage

**Purpose**: Measures test coverage and identifies untested code.

**Configuration**: See `[tool.coverage.*]` in `pyproject.toml`

**Usage**:
```bash
# Run with coverage report
make test-cov

# View HTML report (opens in browser)
open htmlcov/index.html
```

**Coverage Targets**:
- Overall: 80%+ (aspirational)
- Critical modules: 90%+
- New code: Should not decrease coverage

## Pre-commit Hooks

Pre-commit hooks run automatically before each commit to catch issues early.

**Setup** (one-time):
```bash
make install-dev
# or manually:
pip install pre-commit
pre-commit install
```

**Hooks Configured**:
1. **Ruff linter** - Auto-fixes common issues
2. **Ruff formatter** - Formats code consistently
3. **Bandit** - Security checks
4. **Trailing whitespace** - Removes trailing spaces
5. **End of file fixer** - Ensures newline at EOF
6. **YAML/JSON checker** - Validates syntax
7. **Large file checker** - Prevents large file commits
8. **Merge conflict checker** - Detects merge markers
9. **Debug statement checker** - Finds debug imports

**Skip hooks when needed**:
```bash
# Skip specific hook
SKIP=ruff git commit -m "message"

# Skip all hooks (use sparingly!)
git commit --no-verify -m "message"
```

## Testing Commands

```bash
# Run unit tests only
make test

# Run integration tests
make test-integration

# Run API tests
make test-api

# Run all tests
make test-all

# Run with coverage
make test-cov
```

## CI/CD Integration

### GitHub Actions (Future)

The quality checks can be integrated into GitHub Actions:

```yaml
# .github/workflows/quality.yml
name: Code Quality

on: [push, pull_request]

jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.9'
      - run: pip install -r requirements-dev.txt
      - run: make quality
      - run: make test-cov
```

## Common Workflows

### Before Committing
```bash
# Quick check
make quality

# Full check with tests
make quality && make test-cov
```

### Before Pull Request
```bash
# Format code
make format

# Run all checks
make quality

# Run full test suite
make test-all

# Generate coverage report
make test-cov
```

### Fixing Issues

#### Import Sorting
```bash
ruff check --fix --select I kato/
```

#### Security Issues
```bash
# Review bandit findings
bandit -r kato/ -c pyproject.toml

# Fix manually based on severity
```

#### Dead Code
```bash
# Find unused code
vulture kato/ --min-confidence 80

# Review and remove or mark as intentional
# Add '# noqa: vulture' comment if intentional
```

## Configuration Files

- `pyproject.toml` - All tool configurations (ruff, bandit, vulture, pytest, coverage)
- `.pre-commit-config.yaml` - Pre-commit hook configuration
- `requirements-dev.txt` - Development dependencies
- `Makefile` - Convenient command shortcuts

## Best Practices

1. **Run checks locally** before pushing
2. **Address all security findings** from Bandit
3. **Maintain or improve coverage** with each PR
4. **Fix linting issues** before review
5. **Use pre-commit hooks** to catch issues early
6. **Review dead code findings** - some may be false positives
7. **Keep tools updated** - run `pip install -U -r requirements-dev.txt` monthly

## Troubleshooting

### Pre-commit hook failures
```bash
# Update hooks
pre-commit autoupdate

# Clear cache and retry
pre-commit clean
pre-commit run --all-files
```

### Ruff false positives
```bash
# Ignore specific line
# ruff: noqa: E501

# Ignore specific rule for file
# See [tool.ruff.per-file-ignores] in pyproject.toml
```

### Coverage not detecting tests
```bash
# Ensure tests are in correct directory
pytest tests/tests/ --collect-only

# Check coverage config in pyproject.toml
```

## Resources

- [Ruff Documentation](https://docs.astral.sh/ruff/)
- [Bandit Documentation](https://bandit.readthedocs.io/)
- [Vulture Documentation](https://github.com/jendrikseipp/vulture)
- [pytest-cov Documentation](https://pytest-cov.readthedocs.io/)
- [Pre-commit Documentation](https://pre-commit.com/)
