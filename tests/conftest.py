"""
Pytest configuration and shared fixtures.
This file is automatically loaded by pytest.
"""

import os
import sys

# Get the absolute path to the tests directory
test_root = os.path.dirname(os.path.abspath(__file__))

# Add the tests directory to Python path for imports
sys.path.insert(0, test_root)
sys.path.insert(0, os.path.join(test_root, 'tests'))

# Import all fixtures to make them available to all tests
from tests.fixtures.kato_fixtures import kato_fixture

# Make fixtures available
__all__ = ['kato_fixture']
