#!/usr/bin/env python3
"""Check which tests would fail based on current implementation."""

import os
import sys

# Add paths
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'tests'))

# Try to run tests
try:
    import pytest
    # Run with minimal output
    result = pytest.main(['tests/', '--tb=no', '-v', '--co'])
    print(f"\nTests collected. Exit code: {result}")
except ImportError as e:
    print(f"Error: {e}")
    print("Please install pytest: pip install pytest")
except Exception as e:
    print(f"Error running tests: {e}")
