#!/usr/bin/env python3
"""
Direct test runner for KATO tests.
Runs tests using the system Python without virtual environment complications.
"""

import sys
import os
import subprocess

# Add the kato-tests directory to Python path
test_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, test_dir)
sys.path.insert(0, os.path.join(test_dir, 'tests'))

def main():
    """Run KATO tests directly."""
    print("KATO Direct Test Runner")
    print("=======================\n")
    
    # Check if pytest is installed
    try:
        import pytest
    except ImportError:
        print("Error: pytest not installed")
        print("Please install: pip3 install pytest pytest-timeout pytest-xdist requests")
        return 1
    
    # Parse command line arguments
    args = sys.argv[1:]
    
    # Set Python path environment variable
    os.environ['PYTHONPATH'] = f"{test_dir}:{os.path.join(test_dir, 'tests')}:{os.environ.get('PYTHONPATH', '')}"
    
    # Default pytest arguments
    pytest_args = ['-v', '--tb=short']
    
    # Add test directory or specific test type
    if '--unit' in args:
        pytest_args.append('tests/unit/')
    elif '--integration' in args:
        pytest_args.append('tests/integration/')
    elif '--api' in args:
        pytest_args.append('tests/api/')
    else:
        pytest_args.append('tests/')
    
    # Add verbose flag if requested
    if '--verbose' in args or '-v' in args:
        pytest_args[0] = '-vv'
    
    # Add parallel flag if requested
    if '--parallel' in args or '-n' in args:
        pytest_args.append('-n')
        pytest_args.append('auto')
    
    print(f"Running: pytest {' '.join(pytest_args)}\n")
    
    # Run pytest
    return pytest.main(pytest_args)

if __name__ == '__main__':
    sys.exit(main())