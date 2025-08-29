#!/usr/bin/env python3
import os
import re
from pathlib import Path

test_dir = Path(__file__).parent.parent / 'tests'

vector_tests = []
emotives_tests = []
all_tests = []

for test_file in test_dir.rglob('test_*.py'):
    with open(test_file, 'r') as f:
        content = f.read()
        matches = re.findall(r'def (test_\w+)', content)
        
        for test_name in matches:
            all_tests.append((test_file.name, test_name))
            
            if 'vector' in test_name.lower():
                vector_tests.append((test_file.name, test_name))
            
            if 'emotive' in test_name.lower():
                emotives_tests.append((test_file.name, test_name))

print(f"Total tests: {len(all_tests)}")
print(f"\nVector tests (to ignore): {len(vector_tests)}")
for f, t in vector_tests:
    print(f"  - {f}: {t}")

print(f"\nEmotives tests: {len(emotives_tests)}")
for f, t in emotives_tests:
    print(f"  - {f}: {t}")