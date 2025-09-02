#!/usr/bin/env python3
"""
Simple test runner for clustered execution.
Runs inside container and executes pytest with proper environment.
"""

import os
import sys
import subprocess
import argparse
import re


def run_tests(cluster_name: str, processor_id: str, test_paths: str, verbose: bool = False):
    """
    Run tests for a cluster.
    
    Args:
        cluster_name: Name of the test cluster
        processor_id: KATO processor ID to use
        test_paths: Space-separated test paths
        verbose: Whether to show detailed output
    """
    # Set up environment
    env = os.environ.copy()
    env['KATO_CLUSTER_MODE'] = 'true'
    env['KATO_TEST_MODE'] = 'container'
    env['KATO_PROCESSOR_ID'] = processor_id
    
    # Ensure KATO_API_URL is set (should be passed from orchestrator)
    if 'KATO_API_URL' not in env:
        env['KATO_API_URL'] = 'http://localhost:8000'
    
    # Debug: Print environment for troubleshooting
    if verbose:
        print(f"Environment: KATO_API_URL={env.get('KATO_API_URL')}")
        print(f"Environment: KATO_PROCESSOR_ID={env.get('KATO_PROCESSOR_ID')}")
    
    # Split test paths
    tests = test_paths.split()
    
    # Build pytest command
    cmd = [sys.executable, '-m', 'pytest']
    
    # Track which tests we're running
    test_files = []
    
    # Add test paths
    for test in tests:
        # Handle both file paths and specific test functions
        if '::' in test:
            # Specific test function
            test_file, test_func = test.split('::', 1)
            
            # If test_file already contains path (e.g., tests/unit/test.py), use it directly
            if '/' in test_file:
                abs_path = os.path.join('/tests', test_file)
                if os.path.exists(abs_path):
                    cmd.append(f"{test_file}::{test_func}")
                    test_files.append(f"{test_file}::{test_func}")
                else:
                    print(f"Warning: Test file not found: {test_file}")
                    cmd.append(test)  # Try as-is
                    test_files.append(test)
            else:
                # Look for test file in various locations (use relative paths)
                possible_paths = [
                    os.path.join('tests/unit', test_file),
                    os.path.join('tests/integration', test_file),
                    os.path.join('tests/api', test_file),
                    os.path.join('tests/performance', test_file),
                    os.path.join('tests/determinism', test_file),
                    os.path.join('tests', test_file),
                ]
                found = False
                for rel_path in possible_paths:
                    abs_path = os.path.join('/tests', rel_path)
                    if os.path.exists(abs_path):
                        full_path = f"{rel_path}::{test_func}"
                        cmd.append(full_path)
                        test_files.append(full_path)
                        found = True
                        break
                if not found:
                    print(f"Warning: Test file not found: {test_file}")
                    # Try anyway with default location
                    rel_path = os.path.join('tests', test_file)
                    full_path = f"{rel_path}::{test_func}"
                    cmd.append(full_path)
                    test_files.append(full_path)
        else:
            # Full test file
            # If test already contains path (e.g., tests/unit/test.py), use it directly
            if '/' in test:
                abs_path = os.path.join('/tests', test)
                if os.path.exists(abs_path):
                    cmd.append(test)
                    test_files.append(test)
                else:
                    print(f"Warning: Test file not found: {test}")
                    cmd.append(test)  # Try as-is
                    test_files.append(test)
            else:
                # Search for test file in various locations
                # Just filename, need to find it
                possible_paths = [
                    os.path.join('tests/unit', test),
                    os.path.join('tests/integration', test),
                    os.path.join('tests/api', test),
                    os.path.join('tests/performance', test),
                    os.path.join('tests/determinism', test),
                    os.path.join('tests', test),
                ]
                found = False
                for rel_path in possible_paths:
                    abs_path = os.path.join('/tests', rel_path)
                    if os.path.exists(abs_path):
                        cmd.append(rel_path)  # Use relative path for pytest
                        test_files.append(rel_path)
                        found = True
                        break
                if not found:
                    print(f"Warning: Test file not found: {test}")
                    # Try anyway with default location
                    rel_path = os.path.join('tests', test)
                    cmd.append(rel_path)
                    test_files.append(rel_path)
    
    # Add pytest options
    if verbose:
        cmd.extend(['-v', '--tb=short'])
    else:
        cmd.extend(['-q', '--tb=line'])
    
    cmd.append('--color=no')
    
    # Add timeout per test to prevent hanging
    cmd.extend(['--timeout=30', '--timeout-method=thread'])
    
    # Run pytest
    print(f"Running tests for cluster '{cluster_name}' with processor '{processor_id}'")
    if verbose:
        print(f"Command: {' '.join(cmd)}")
        print(f"Test files: {', '.join(test_files)}")
    
    try:
        result = subprocess.run(
            cmd,
            env=env,
            capture_output=not verbose,
            text=True,
            cwd='/tests',
            timeout=300  # 5 minute timeout for all tests
        )
        
        if verbose:
            # Output was shown directly
            return result.returncode
        else:
            # Parse and show results
            output = result.stdout + result.stderr
            lines = output.split('\n')
            
            # Look for the summary line (e.g., "===== 1 passed, 2 failed in 0.5s =====")
            summary_line = None
            for line in lines:
                if '=====' in line and (' passed' in line or ' failed' in line or ' skipped' in line):
                    summary_line = line
                    break
            
            if summary_line:
                # Extract counts from summary line
                passed = 0
                failed = 0 
                skipped = 0
                errors = 0
                
                match = re.search(r'(\d+) passed', summary_line)
                if match:
                    passed = int(match.group(1))
                match = re.search(r'(\d+) failed', summary_line)
                if match:
                    failed = int(match.group(1))
                match = re.search(r'(\d+) skipped', summary_line)
                if match:
                    skipped = int(match.group(1))
                match = re.search(r'(\d+) error', summary_line)
                if match:
                    errors = int(match.group(1))
            else:
                # Fallback to counting occurrences
                passed = output.count(' passed')
                failed = output.count(' failed')
                skipped = output.count(' skipped')
                errors = output.count(' error')
            
            # Show summary
            print(f"Results: {passed} passed, {failed} failed, {skipped} skipped, {errors} errors")
            
            # Show failures if any
            if failed > 0 or errors > 0:
                print("\nFailures/Errors:")
                for line in lines:
                    if 'FAILED' in line or 'ERROR' in line:
                        # Only show the actual failure lines, not stack traces
                        if line.strip().startswith('FAILED') or line.strip().startswith('ERROR'):
                            print(f"  {line.strip()}")
            
            # Output the summary for parsing
            print(f"\n{passed} passed, {failed} failed, {skipped} skipped")
            
            return result.returncode
            
    except subprocess.TimeoutExpired:
        print(f"ERROR: Tests timed out after 5 minutes")
        return 1
    except Exception as e:
        print(f"ERROR: Failed to run tests: {e}")
        return 1


def main():
    parser = argparse.ArgumentParser(description='Run tests in cluster mode')
    parser.add_argument('--cluster', required=True, help='Cluster name')
    parser.add_argument('--processor-id', required=True, help='Processor ID')
    parser.add_argument('--tests', required=True, help='Space-separated test paths')
    parser.add_argument('--verbose', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    exit_code = run_tests(
        args.cluster,
        args.processor_id,
        args.tests,
        args.verbose
    )
    
    sys.exit(exit_code)


if __name__ == '__main__':
    main()