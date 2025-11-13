# Code Style Guide

KATO code style standards and conventions.

## Overview

KATO follows Python community standards with project-specific conventions. We use automated tools to enforce consistency.

## Core Principles

1. **Readability**: Code is read more than written
2. **Consistency**: Follow existing patterns
3. **Simplicity**: Prefer straightforward solutions
4. **Documentation**: Explain why, not what
5. **Type Safety**: Use type hints extensively

## Python Version

**Minimum**: Python 3.10

**Features Used**:
- Type hints with `|` union syntax
- Structural pattern matching
- `dataclasses` and `@dataclass`
- `async`/`await` extensively
- Walrus operator `:=` where appropriate

## Code Formatting

### Black (Code Formatter)

**Configuration** (pyproject.toml):
```toml
[tool.black]
line-length = 100
target-version = ['py310']
include = '\.pyi?$'
```

**Usage**:
```bash
# Format all code
black kato/ tests/

# Check without modifying
black --check kato/

# Format specific file
black kato/api/endpoints/sessions.py
```

### Line Length

**Maximum**: 100 characters (enforced by Black)

**Exceptions**:
- Long URLs in comments
- Import statements (use parentheses for multi-line)

```python
# Good - multi-line imports
from kato.workers import (
    KatoProcessor,
    MemoryManager,
    PatternProcessor,
    VectorProcessor,
)

# Avoid - exceeds 100 chars
from kato.workers import KatoProcessor, MemoryManager, PatternProcessor, VectorProcessor
```

## Naming Conventions

### Modules and Packages

- **Style**: `lowercase_with_underscores`
- **Examples**: `kato_processor.py`, `pattern_search.py`, `session_manager.py`

```python
# Good
from kato.workers.pattern_processor import PatternProcessor

# Avoid
from kato.workers.PatternProcessor import PatternProcessor
```

### Classes

- **Style**: `PascalCase`
- **Examples**: `KatoProcessor`, `MemoryManager`, `PatternSearcher`

```python
class KatoProcessor:
    """Main KATO processing engine."""
    pass

class SuperKnowledgeBase:
    """MongoDB knowledge base manager."""
    pass
```

### Functions and Methods

- **Style**: `lowercase_with_underscores`
- **Examples**: `observe_sequence()`, `learn_pattern()`, `get_predictions()`

```python
def observe_sequence(strings: list[str]) -> dict:
    """Process observation sequence."""
    pass

async def learn_pattern(self) -> Pattern:
    """Learn pattern from STM."""
    pass
```

### Variables

- **Style**: `lowercase_with_underscores`
- **Constants**: `UPPERCASE_WITH_UNDERSCORES`

```python
# Variables
session_id = "session-123"
pattern_name = "PTN|abc123"
recall_threshold = 0.3

# Constants
MAX_PATTERN_LENGTH = 10000
DEFAULT_RECALL_THRESHOLD = 0.1
VECTOR_DIMENSION = 768
```

### Private Members

- **Prefix**: Single underscore `_`
- **Convention**: Not part of public API

```python
class KatoProcessor:
    def __init__(self):
        self.session_id = "public"
        self._internal_state = {}  # Private
        self.__very_private = []   # Name mangling (rare)

    def process(self):
        """Public method."""
        return self._internal_process()

    def _internal_process(self):
        """Private helper method."""
        pass
```

## Type Hints

### Always Use Type Hints

```python
# Good
def process_observation(
    strings: list[str],
    vectors: list[list[float]],
    emotives: dict[str, float]
) -> dict[str, Any]:
    """Process observation with type hints."""
    pass

# Avoid - no type hints
def process_observation(strings, vectors, emotives):
    pass
```

### Modern Syntax (Python 3.10+)

```python
from typing import Optional, Any

# Good - Python 3.10+ union syntax
def get_pattern(pattern_id: str) -> dict | None:
    pass

# Also acceptable - typing.Optional
def get_pattern(pattern_id: str) -> Optional[dict]:
    pass

# Good - built-in generics
patterns: list[dict] = []
config: dict[str, Any] = {}

# Old style (avoid)
from typing import List, Dict
patterns: List[dict] = []
config: Dict[str, Any] = {}
```

### Complex Types

```python
from typing import TypeAlias, Protocol

# Type aliases for clarity
PatternName: TypeAlias = str
NodeID: TypeAlias = str
SessionID: TypeAlias = str

# Protocols for structural typing
class HasObserve(Protocol):
    def observe(self, data: dict) -> None: ...

# Generic types
from typing import TypeVar, Generic

T = TypeVar('T')

class Cache(Generic[T]):
    def get(self, key: str) -> T | None:
        pass
```

## Docstrings

### Style: Google Format

```python
def learn_pattern(
    self,
    stm: list[list[str]],
    emotives: dict[str, list[float]] | None = None
) -> Pattern:
    """Learn pattern from short-term memory.

    Creates a new pattern from current STM contents and stores in LTM.
    Pattern name is derived from content hash.

    Args:
        stm: Short-term memory contents (list of events)
        emotives: Optional emotive values per event

    Returns:
        Pattern: Learned pattern object with metadata

    Raises:
        ValueError: If STM has fewer than 2 events
        PatternExistsError: If pattern already exists (rare)

    Example:
        >>> processor = KatoProcessor()
        >>> stm = [["hello"], ["world"]]
        >>> pattern = processor.learn_pattern(stm)
        >>> print(pattern.pattern_name)
        PTN|abc123...
    """
    pass
```

### Class Docstrings

```python
class KatoProcessor:
    """Main KATO processing engine.

    Coordinates pattern learning, matching, and prediction across
    all KATO components. Each processor instance is isolated by
    processor_id.

    Attributes:
        processor_id: Unique identifier for this processor
        memory_manager: Manages STM and LTM operations
        pattern_processor: Handles pattern learning and matching
        vector_processor: Processes vector embeddings

    Example:
        >>> processor = KatoProcessor(processor_id="my_app")
        >>> processor.observe({"strings": ["hello"]})
        >>> pattern = processor.learn()
    """
```

### Module Docstrings

```python
"""Pattern search and matching functionality.

This module provides efficient pattern matching using RapidFuzz
for token-level and character-level similarity calculations.

Typical usage:
    searcher = PatternSearcher(patterns)
    results = searcher.search(query, threshold=0.3)
"""
```

## Code Organization

### Imports

**Order**:
1. Standard library
2. Third-party packages
3. KATO modules

**Style**:
```python
# Standard library
import os
import sys
from collections import defaultdict
from typing import Any, Optional

# Third-party
import pymongo
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

# KATO modules
from kato.config import settings
from kato.workers.kato_processor import KatoProcessor
from kato.storage.super_knowledge_base import SuperKnowledgeBase
```

**Use isort**:
```bash
isort kato/ tests/
```

### Class Organization

**Order**:
1. Class docstring
2. Class variables
3. `__init__`
4. Properties
5. Public methods
6. Private methods
7. Static methods
8. Class methods

```python
class KatoProcessor:
    """Processor docstring."""

    # Class variables
    DEFAULT_THRESHOLD = 0.1

    def __init__(self, processor_id: str):
        """Initialize processor."""
        self.processor_id = processor_id
        self._state = {}

    @property
    def session_count(self) -> int:
        """Number of active sessions."""
        return len(self._state)

    def observe(self, data: dict) -> None:
        """Public method."""
        self._internal_process(data)

    def _internal_process(self, data: dict) -> None:
        """Private helper."""
        pass

    @staticmethod
    def validate_pattern_name(name: str) -> bool:
        """Static utility."""
        return name.startswith("PTN|")

    @classmethod
    def from_config(cls, config: dict) -> "KatoProcessor":
        """Factory constructor."""
        return cls(config['processor_id'])
```

## Error Handling

### Custom Exceptions

```python
# Define in kato/exceptions.py
class KatoException(Exception):
    """Base exception for all KATO errors."""
    pass

class PatternNotFoundError(KatoException):
    """Pattern does not exist in LTM."""
    pass

class SessionExpiredError(KatoException):
    """Session has expired or doesn't exist."""
    pass

# Usage
def get_pattern(self, pattern_id: str) -> Pattern:
    """Get pattern by ID."""
    pattern = self.db.find_one({"_id": pattern_id})
    if not pattern:
        raise PatternNotFoundError(
            f"Pattern {pattern_id} not found in node {self.node_id}"
        )
    return Pattern.from_dict(pattern)
```

### Exception Context

```python
# Good - provide context
try:
    pattern = self.learn_pattern(stm)
except ValueError as e:
    raise PatternLearningError(
        f"Failed to learn pattern from {len(stm)} events"
    ) from e

# Avoid - swallowing errors
try:
    pattern = self.learn_pattern(stm)
except:
    pass
```

## Async/Await

### Async Functions

```python
# Use async for I/O operations
async def fetch_patterns(
    self,
    query: dict
) -> list[Pattern]:
    """Fetch patterns from database."""
    cursor = self.collection.find(query)
    patterns = await cursor.to_list(length=100)
    return [Pattern.from_dict(p) for p in patterns]

# Sync for CPU-bound operations
def calculate_similarity(
    self,
    pattern1: Pattern,
    pattern2: Pattern
) -> float:
    """Calculate pattern similarity."""
    return difflib.SequenceMatcher(
        None,
        pattern1.events,
        pattern2.events
    ).ratio()
```

### Async Context Managers

```python
# Good
async with self.db_session() as session:
    await session.commit()

# Implementation
from contextlib import asynccontextmanager

@asynccontextmanager
async def db_session(self):
    """Provide database session."""
    session = await self.create_session()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
```

## Configuration

### Pydantic Settings

```python
from pydantic import Field
from pydantic_settings import BaseSettings

class ProcessorConfig(BaseSettings):
    """Processor configuration."""

    processor_id: str = Field(
        ...,
        description="Unique processor identifier"
    )
    recall_threshold: float = Field(
        0.1,
        ge=0.0,
        le=1.0,
        description="Pattern matching threshold"
    )
    max_patterns: int = Field(
        10000,
        gt=0,
        description="Maximum patterns to load"
    )

    class Config:
        env_prefix = "KATO_"
        case_sensitive = False
```

## Logging

### Standard Format

```python
import logging

logger = logging.getLogger(__name__)

# Info for normal operations
logger.info(
    "Pattern learned",
    extra={
        "pattern_name": pattern.name,
        "length": pattern.length,
        "processor_id": self.processor_id
    }
)

# Warning for recoverable issues
logger.warning(
    "Low similarity match",
    extra={"similarity": 0.15, "threshold": 0.3}
)

# Error for failures
logger.error(
    "Failed to store pattern",
    exc_info=True,
    extra={"pattern_name": pattern.name}
)

# Debug for development
logger.debug(
    "Processing observation",
    extra={"event_count": len(stm)}
)
```

## Testing

### Test Function Names

```python
# Pattern: test_<function>_<scenario>_<expected>

def test_observe_single_string_succeeds():
    """Test observing single string."""
    pass

def test_learn_empty_stm_raises_error():
    """Test learning from empty STM raises ValueError."""
    pass

def test_predict_partial_match_returns_results():
    """Test prediction with partial match."""
    pass
```

### Fixtures

```python
import pytest

@pytest.fixture
def kato_processor():
    """Create isolated KATO processor."""
    processor = KatoProcessor(processor_id=f"test_{uuid.uuid4()}")
    yield processor
    # Cleanup
    processor.clear_all()

# Usage
def test_observe_adds_to_stm(kato_processor):
    """Test observe adds event to STM."""
    kato_processor.observe({"strings": ["test"]})
    assert len(kato_processor.get_stm()) == 1
```

## Comments

### When to Comment

```python
# Good - explain why
# Use exponential backoff to avoid overwhelming MongoDB during bulk inserts
retry_delay = min(base_delay * (2 ** attempt), max_delay)

# Good - clarify complex logic
# Pattern similarity calculated as:
# (2 * matched_symbols) / (len(pattern) + len(query))
similarity = (2 * matches) / (pattern_len + query_len)

# Avoid - stating the obvious
# Increment counter by 1
counter += 1
```

### TODO Comments

```python
# TODO(username): Short description
# TODO: Add support for multi-modal pattern matching
# FIXME: Race condition when clearing STM during learning
# NOTE: This assumes patterns are pre-sorted
# HACK: Temporary workaround for MongoDB connection pool issue
```

## Code Smells to Avoid

### Magic Numbers

```python
# Bad
if similarity > 0.3:
    pass

# Good
SIMILARITY_THRESHOLD = 0.3
if similarity > SIMILARITY_THRESHOLD:
    pass
```

### Long Functions

```python
# Bad - 200 line function

# Good - break into smaller functions
def process_observation(self, data: dict) -> dict:
    """Process observation."""
    validated = self._validate_input(data)
    processed = self._process_strings(validated)
    stored = self._store_in_stm(processed)
    return self._format_response(stored)
```

### Deep Nesting

```python
# Bad - 4+ levels of nesting
if condition1:
    if condition2:
        if condition3:
            if condition4:
                do_something()

# Good - early returns
if not condition1:
    return
if not condition2:
    return
if not condition3:
    return
if not condition4:
    return
do_something()
```

## Tooling

### Pre-commit Configuration

`.pre-commit-config.yaml`:
```yaml
repos:
  - repo: https://github.com/psf/black
    rev: 23.10.0
    hooks:
      - id: black

  - repo: https://github.com/pycqa/isort
    rev: 5.12.0
    hooks:
      - id: isort

  - repo: https://github.com/charliermarsh/ruff-pre-commit
    rev: v0.1.0
    hooks:
      - id: ruff
        args: [--fix]

  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.5.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
```

### Ruff Configuration

`pyproject.toml`:
```toml
[tool.ruff]
line-length = 100
target-version = "py310"

select = [
    "E",   # pycodestyle errors
    "W",   # pycodestyle warnings
    "F",   # pyflakes
    "I",   # isort
    "N",   # pep8-naming
    "UP",  # pyupgrade
]

ignore = [
    "E501",  # line too long (handled by black)
]

[tool.ruff.per-file-ignores]
"__init__.py" = ["F401"]  # Allow unused imports in __init__
```

## References

- **PEP 8**: https://pep8.org/
- **Google Python Style**: https://google.github.io/styleguide/pyguide.html
- **Black**: https://black.readthedocs.io/
- **Ruff**: https://beta.ruff.rs/docs/

---

**Last Updated**: November 2025
**KATO Version**: 3.0+
