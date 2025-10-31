"""
Pytest fixtures for GPU tests.

Provides isolated test fixtures for:
- MongoDB connection and cleanup
- SymbolVocabularyEncoder instances
- Test data generation
"""

import pytest
from pymongo import MongoClient

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


@pytest.fixture
def mongodb():
    """
    MongoDB test database with automatic cleanup.

    Provides a fresh MongoDB database for each test with complete isolation.
    Database is cleared before and after each test.

    Yields:
        MongoDB database object

    Example:
        def test_something(mongodb):
            collection = mongodb.test_collection
            collection.insert_one({'test': 'data'})
    """
    # Use unique database name per test to avoid conflicts
    import time
    import uuid
    db_name = f"test_gpu_{int(time.time()*1000)}_{str(uuid.uuid4())[:8]}"

    client = MongoClient("mongodb://localhost:27017")
    db = client[db_name]

    # Clear before test (shouldn't be necessary for unique DB, but safe)
    db.metadata.delete_many({})

    yield db

    # Cleanup after test
    db.metadata.delete_many({})
    client.drop_database(db_name)
    client.close()


@pytest.fixture
def encoder(mongodb):
    """
    Fresh SymbolVocabularyEncoder instance for each test.

    Provides an encoder connected to isolated MongoDB database.
    Vocabulary is empty at start of each test.

    Args:
        mongodb: MongoDB fixture (auto-injected)

    Returns:
        SymbolVocabularyEncoder instance

    Example:
        def test_encoder(encoder):
            symbol_id = encoder.encode_symbol('test')
            assert symbol_id == 0
    """
    return SymbolVocabularyEncoder(mongodb.metadata)


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
