#!/usr/bin/env python3
"""
Test script to verify emotives tests are fixed.
"""

import sys
import os

# Add paths
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'tests'))

def main():
    """Run only the emotives tests."""
    try:
        import pytest
        
        # Run specific emotives tests
        test_files = [
            'tests/unit/test_observations.py::test_observe_with_emotives',
            'tests/unit/test_predictions.py::test_prediction_with_emotives', 
            'tests/unit/test_memory_management.py::test_memory_with_emotives'
        ]
        
        print("Running emotives tests...")
        print("=" * 60)
        
        for test in test_files:
            print(f"\nRunning: {test}")
            result = pytest.main([test, '-v', '--tb=short'])
            if result == 0:
                print(f"✓ {test} PASSED")
            else:
                print(f"✗ {test} FAILED")
        
        print("\n" + "=" * 60)
        print("Emotives tests completed")
        
    except ImportError:
        print("Error: pytest not installed")
        print("Please install: pip install pytest")
        return 1

if __name__ == '__main__':
    main()