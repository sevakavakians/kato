"""
Pytest configuration and shared fixtures.
This file is automatically loaded by pytest.
"""

import os
import sys
import pytest

# Get the absolute path to the tests directory
test_root = os.path.dirname(os.path.abspath(__file__))

# Add the tests directory to Python path for imports
sys.path.insert(0, test_root)
sys.path.insert(0, os.path.join(test_root, 'tests'))

# Import all fixtures to make them available to all tests
from tests.fixtures.kato_fixtures import kato_fixture  # noqa: E402

# Make fixtures available
__all__ = ['kato_fixture']


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers",
        "gpu: marks tests as requiring GPU (CuPy/CUDA) - skipped if GPU not available"
    )


def pytest_collection_modifyitems(config, items):
    """Skip GPU tests if GPU not available."""
    try:
        from kato.gpu import GPU_AVAILABLE
    except ImportError:
        GPU_AVAILABLE = False

    if not GPU_AVAILABLE:
        skip_gpu = pytest.mark.skip(reason="GPU not available (CuPy/CUDA required)")
        for item in items:
            if "gpu" in item.keywords:
                item.add_marker(skip_gpu)
