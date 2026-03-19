"""
Pytest fixtures for GPU tests.

Provides isolated test fixtures for:
- In-memory mock storage for vocabulary
- SymbolVocabularyEncoder instances
- Test data generation
"""

import pytest

from kato.gpu.encoder import SymbolVocabularyEncoder

# Check GPU availability and skip entire module if not available
try:
    from kato.gpu import GPU_AVAILABLE
except ImportError:
    GPU_AVAILABLE = False

# Skip entire GPU test directory if GPU not available
if not GPU_AVAILABLE:
    pytest.skip(
        "GPU tests require CuPy/CUDA - skipping entire directory",
        allow_module_level=True
    )


class InMemoryCollection:
    """In-memory mock for a MongoDB-like collection interface used by SymbolVocabularyEncoder."""

    def __init__(self):
        self._data = {}

    def find_one(self, query):
        key = tuple(sorted(query.items()))
        return self._data.get(key)

    def update_one(self, query, update, upsert=False):
        key = tuple(sorted(query.items()))
        if key in self._data:
            self._data[key].update(update.get('$set', {}))
        elif upsert:
            self._data[key] = {**dict(key), **update.get('$set', {})}
        return type('UpdateResult', (), {'matched_count': 1 if key in self._data else 0, 'modified_count': 1})()


@pytest.fixture
def mock_metadata():
    """
    In-memory mock metadata collection with automatic cleanup.

    Provides a fresh in-memory collection for each test with complete isolation.

    Yields:
        InMemoryCollection object
    """
    return InMemoryCollection()


@pytest.fixture
def encoder(mock_metadata):
    """
    Fresh SymbolVocabularyEncoder instance for each test.

    Provides an encoder connected to in-memory storage.
    Vocabulary is empty at start of each test.

    Args:
        mock_metadata: In-memory collection fixture (auto-injected)

    Returns:
        SymbolVocabularyEncoder instance

    Example:
        def test_encoder(encoder):
            symbol_id = encoder.encode_symbol('test')
            assert symbol_id == 0
    """
    return SymbolVocabularyEncoder(mock_metadata)


@pytest.fixture
def encoder_with_vocab(encoder):
    """
    Encoder pre-loaded with test vocabulary.

    Provides an encoder with 100 pre-defined symbols for testing
    scenarios that require existing vocabulary.

    Args:
        encoder: Encoder fixture (auto-injected)

    Returns:
        SymbolVocabularyEncoder with 100 symbols

    Example:
        def test_with_vocab(encoder_with_vocab):
            assert encoder_with_vocab.vocab_size == 100
            assert encoder_with_vocab.encode_symbol('sym0') == 0
    """
    # Pre-load symbols
    for i in range(100):
        encoder.encode_symbol(f"sym{i}")

    return encoder
