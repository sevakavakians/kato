#!/usr/bin/env python3
"""
Simple test runner to verify test structure without Docker dependencies.
This validates that the test files are properly structured and can be imported.
"""

import sys
import os
import importlib.util

# Add paths
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'tests'))

def check_test_file(filepath):
    """Check if a test file can be imported and has test functions."""
    print(f"\nChecking {filepath}...")
    
    # Load the module
    spec = importlib.util.spec_from_file_location("test_module", filepath)
    if spec is None:
        print(f"  ❌ Could not load spec for {filepath}")
        return False
    
    module = importlib.util.module_from_spec(spec)
    
    try:
        spec.loader.exec_module(module)
        print(f"  ✅ Module imported successfully")
    except Exception as e:
        print(f"  ❌ Import error: {e}")
        return False
    
    # Find test functions
    test_functions = [name for name in dir(module) if name.startswith('test_')]
    print(f"  Found {len(test_functions)} test functions:")
    for func in test_functions[:5]:  # Show first 5
        print(f"    - {func}")
    if len(test_functions) > 5:
        print(f"    ... and {len(test_functions) - 5} more")
    
    return True

def main():
    print("=" * 60)
    print("KATO Test Suite Structure Validator")
    print("=" * 60)
    
    test_dirs = {
        'Unit Tests': 'tests/unit',
        'Integration Tests': 'tests/integration',
        'API Tests': 'tests/api'
    }
    
    all_valid = True
    
    for category, test_dir in test_dirs.items():
        print(f"\n{category}:")
        print("-" * 40)
        
        if not os.path.exists(test_dir):
            print(f"  ❌ Directory {test_dir} does not exist")
            all_valid = False
            continue
        
        test_files = [f for f in os.listdir(test_dir) if f.startswith('test_') and f.endswith('.py')]
        
        if not test_files:
            print(f"  ❌ No test files found in {test_dir}")
            all_valid = False
            continue
        
        for test_file in test_files:
            filepath = os.path.join(test_dir, test_file)
            if not check_test_file(filepath):
                all_valid = False
    
    print("\n" + "=" * 60)
    if all_valid:
        print("✅ All test files are properly structured!")
        print("\nTo run the actual tests, you'll need:")
        print("1. Docker running properly")
        print("2. KATO container started")
        print("3. Run: pytest <test_file>")
    else:
        print("❌ Some issues found with test structure")
    
    return 0 if all_valid else 1

if __name__ == "__main__":
    sys.exit(main())