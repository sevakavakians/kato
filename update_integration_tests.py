#!/usr/bin/env python3
"""
Script to update integration test files to use the FastAPI fixture conditionally.
"""

import os

# Files to update
test_files = [
    "tests/tests/integration/test_pattern_learning.py",
    "tests/tests/integration/test_vector_e2e.py", 
    "tests/tests/integration/test_vector_simplified.py"
]

# Pattern to find and replace
OLD_PATTERN = """sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from fixtures.kato_fixtures import kato_fixture"""

NEW_PATTERN = """sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Use FastAPI fixture if available, otherwise fall back to old fixture
if os.environ.get('USE_FASTAPI', 'false').lower() == 'true':
    from fixtures.kato_fastapi_fixtures import kato_fastapi_existing as kato_fixture
else:
    from fixtures.kato_fixtures import kato_fixture"""

def update_file(filepath):
    """Update a test file."""
    try:
        with open(filepath, 'r') as f:
            content = f.read()
        
        if 'USE_FASTAPI' in content:
            print(f"  ✓ Already updated: {filepath}")
            return False
            
        if OLD_PATTERN in content:
            updated = content.replace(OLD_PATTERN, NEW_PATTERN)
            with open(filepath, 'w') as f:
                f.write(updated)
            print(f"  ✓ Updated: {filepath}")
            return True
        else:
            print(f"  ⚠ Pattern not found in: {filepath}")
            return False
    except Exception as e:
        print(f"  ✗ Error updating {filepath}: {e}")
        return False

def main():
    print("Updating integration test fixtures...\n")
    
    updated = 0
    for filepath in test_files:
        if update_file(filepath):
            updated += 1
    
    print(f"\n✅ Updated {updated} integration test files")

if __name__ == "__main__":
    main()