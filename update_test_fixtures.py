#!/usr/bin/env python3
"""
Script to update all test files to use the FastAPI fixture conditionally.
"""

import os
import glob

# Pattern to find and replace
OLD_IMPORT = """import pytest
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from fixtures.kato_fixtures import kato_fixture"""

NEW_IMPORT = """import pytest
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Use FastAPI fixture if available, otherwise fall back to old fixture
if os.environ.get('USE_FASTAPI', 'false').lower() == 'true':
    from fixtures.kato_fastapi_fixtures import kato_fastapi_existing as kato_fixture
else:
    from fixtures.kato_fixtures import kato_fixture"""

def update_test_file(filepath):
    """Update a single test file to use conditional import."""
    with open(filepath, 'r') as f:
        content = f.read()
    
    # Check if already updated
    if 'USE_FASTAPI' in content:
        print(f"  ✓ Already updated: {filepath}")
        return False
    
    # Check if it has the old import pattern
    if OLD_IMPORT in content:
        updated_content = content.replace(OLD_IMPORT, NEW_IMPORT)
        with open(filepath, 'w') as f:
            f.write(updated_content)
        print(f"  ✓ Updated: {filepath}")
        return True
    else:
        print(f"  ⚠ Pattern not found, skipping: {filepath}")
        return False

def main():
    """Update all unit test files."""
    test_dir = "tests/tests/unit"
    test_files = glob.glob(os.path.join(test_dir, "test_*.py"))
    
    print(f"Found {len(test_files)} test files in {test_dir}")
    print("\nUpdating test fixtures...\n")
    
    updated_count = 0
    for filepath in sorted(test_files):
        if update_test_file(filepath):
            updated_count += 1
    
    print(f"\n✅ Updated {updated_count} test files")
    print(f"All test files now support FastAPI fixture via USE_FASTAPI=true environment variable")

if __name__ == "__main__":
    main()