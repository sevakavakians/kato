#!/usr/bin/env python3
"""Analyze test files to identify potential failing tests."""

import os
import re
from pathlib import Path

def find_test_functions(file_path):
    """Find all test functions in a file."""
    tests = []
    with open(file_path, 'r') as f:
        content = f.read()
        # Find all test function definitions
        pattern = r'def (test_\w+)\([^)]*\):'
        matches = re.findall(pattern, content)
        
        for test_name in matches:
            # Check if it's vector-related
            is_vector = 'vector' in test_name.lower() or 'vector' in content[content.find(f'def {test_name}'):content.find(f'def {test_name}') + 500].lower()
            
            # Check if it's emotives-related
            is_emotives = 'emotive' in test_name.lower()
            
            # Check for specific patterns that might fail
            test_block = content[content.find(f'def {test_name}'):content.find(f'def {test_name}') + 1000]
            
            potential_issues = []
            
            # Check for assertions that might fail
            if 'assert len(wm) == 1' in test_block and 'vectors' in test_block:
                potential_issues.append("Vector observation assertion")
            
            if 'emotives' in test_block and 'assert' in test_block:
                potential_issues.append("Emotives assertion")
                
            if 'VECTOR|' in test_block:
                potential_issues.append("Vector hash assertion")
                
            if 'get_predictions()' in test_block and ('emotives' in test_block or 'vectors' in test_block):
                potential_issues.append("Predictions with emotives/vectors")
            
            tests.append({
                'name': test_name,
                'file': file_path.name,
                'is_vector': is_vector,
                'is_emotives': is_emotives,
                'potential_issues': potential_issues
            })
    
    return tests

def main():
    """Analyze all test files."""
    test_dir = Path(__file__).parent.parent / 'tests'
    
    all_tests = []
    
    # Find all test files
    for test_file in test_dir.rglob('test_*.py'):
        tests = find_test_functions(test_file)
        all_tests.extend(tests)
    
    # Categorize tests
    vector_tests = [t for t in all_tests if t['is_vector']]
    emotives_tests = [t for t in all_tests if t['is_emotives']]
    potentially_failing = [t for t in all_tests if t['potential_issues']]
    
    print("=" * 70)
    print("TEST ANALYSIS REPORT")
    print("=" * 70)
    print(f"\nTotal tests found: {len(all_tests)}")
    print(f"Vector-related tests: {len(vector_tests)}")
    print(f"Emotives-related tests: {len(emotives_tests)}")
    print(f"Tests with potential issues: {len(potentially_failing)}")
    
    print("\n" + "=" * 70)
    print("VECTOR-RELATED TESTS (to ignore per user request):")
    print("-" * 70)
    for test in vector_tests:
        print(f"  - {test['file']}: {test['name']}")
    
    print("\n" + "=" * 70)
    print("EMOTIVES-RELATED TESTS:")
    print("-" * 70)
    for test in emotives_tests:
        print(f"  - {test['file']}: {test['name']}")
        if test['potential_issues']:
            print(f"    Issues: {', '.join(test['potential_issues'])}")
    
    print("\n" + "=" * 70)
    print("TESTS WITH POTENTIAL ISSUES (excluding pure vector tests):")
    print("-" * 70)
    non_vector_issues = [t for t in potentially_failing if not t['is_vector']]
    for test in non_vector_issues:
        print(f"  - {test['file']}: {test['name']}")
        print(f"    Issues: {', '.join(test['potential_issues'])}")
    
    print("\n" + "=" * 70)
    print("PATTERN ANALYSIS:")
    print("-" * 70)
    
    # Count issue patterns
    issue_counts = {}
    for test in potentially_failing:
        for issue in test['potential_issues']:
            issue_counts[issue] = issue_counts.get(issue, 0) + 1
    
    print("Common issues found:")
    for issue, count in sorted(issue_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"  - {issue}: {count} tests")
    
    print("\n" + "=" * 70)
    print("RECOMMENDATIONS:")
    print("-" * 70)
    print("1. Vector tests should be ignored (4 tests identified)")
    print("2. Emotives tests may need review (4 tests identified)")
    print("3. Mixed modality tests may have issues")
    print("4. Focus on fixing emotives handling and predictions")

if __name__ == '__main__':
    main()