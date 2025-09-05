#!/usr/bin/env python3
"""
Cluster-based test runner for KATO.
Runs tests in clusters with shared configuration to minimize instance creation
while maintaining complete isolation between clusters.
"""

import os
import sys
import subprocess
import json
import time
import uuid
from typing import Dict, List, Tuple, Any
from dataclasses import dataclass
import requests

# Add fixtures to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'tests'))
from fixtures.test_clusters import TEST_CLUSTERS, KatoTestCluster, get_tests_for_cluster


@dataclass
class ClusterResult:
    """Results from running a test cluster."""
    cluster_name: str
    processor_id: str
    passed: int
    failed: int
    skipped: int
    errors: List[str]
    duration: float


class ClusterTestRunner:
    """Manages cluster-based test execution with isolation."""
    
    def __init__(self, kato_manager_path: str, test_dir: str, verbose: bool = False):
        self.kato_manager = kato_manager_path
        self.test_dir = test_dir
        self.results = []
        self.current_processor_id = None
        self.base_url = "http://localhost:8000"
        self.verbose = verbose or os.environ.get('VERBOSE_OUTPUT') == 'true'
        
    def generate_processor_id(self, cluster_name: str) -> str:
        """Generate unique processor ID for a cluster."""
        timestamp = int(time.time() * 1000)
        unique = str(uuid.uuid4())[:8]
        return f"cluster_{cluster_name}_{timestamp}_{unique}"
    
    def start_kato_instance(self, cluster: TestCluster) -> str:
        """Start a KATO instance for a cluster."""
        processor_id = self.generate_processor_id(cluster.name)
        print(f"\n{'='*60}")
        print(f"Starting KATO instance for cluster: {cluster.name}")
        print(f"Processor ID: {processor_id}")
        print(f"Configuration: {cluster.config}")
        print(f"{'='*60}")
        
        # Set environment variables
        env = os.environ.copy()
        env['PROCESSOR_ID'] = processor_id
        env['PROCESSOR_NAME'] = f"ClusterProcessor_{cluster.name}"
        
        # Start KATO using manager script (it reads processor ID from env)
        result = subprocess.run(
            [self.kato_manager, 'start'],
            env=env,
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"Failed to start KATO: {result.stderr}")
            raise RuntimeError(f"Failed to start KATO for cluster {cluster.name}")
        
        # Wait for KATO to be ready
        self.wait_for_kato_ready(processor_id)
        
        # Apply cluster configuration
        self.apply_configuration(processor_id, cluster.config)
        
        self.current_processor_id = processor_id
        return processor_id
    
    def stop_kato_instance(self, processor_id: str):
        """Stop a KATO instance."""
        print(f"\nStopping KATO instance: {processor_id}")
        
        # Stop using manager script
        subprocess.run(
            [self.kato_manager, 'stop'],
            capture_output=True,
            text=True
        )
        
        # Also try to stop specific container
        subprocess.run(
            ['docker', 'stop', f'kato-{processor_id}'],
            capture_output=True,
            text=True
        )
        
        self.current_processor_id = None
    
    def wait_for_kato_ready(self, processor_id: str, timeout: int = 30):
        """Wait for KATO instance to be ready."""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                # Check API gateway
                response = requests.get(f"{self.base_url}/kato-api/ping", timeout=2)
                if response.status_code == 200:
                    # Check processor endpoint
                    response = requests.get(f"{self.base_url}/{processor_id}/ping", timeout=2)
                    if response.status_code == 200:
                        print(f"KATO instance {processor_id} is ready")
                        return
            except requests.exceptions.RequestException:
                pass
            
            time.sleep(1)
        
        raise TimeoutError(f"KATO instance {processor_id} did not become ready in {timeout} seconds")
    
    def apply_configuration(self, processor_id: str, config: Dict[str, Any]):
        """Apply configuration to KATO instance."""
        print(f"Applying configuration: {config}")
        
        # Update genes with configuration
        response = requests.post(
            f"{self.base_url}/{processor_id}/genes/change",
            json={"data": config}
        )
        
        if response.status_code != 200:
            print(f"Warning: Failed to apply configuration: {response.text}")
    
    def clear_all_memory(self, processor_id: str):
        """Clear all memory for the instance."""
        try:
            response = requests.post(
                f"{self.base_url}/{processor_id}/clear-all-memory",
                json={}
            )
            if response.status_code == 200:
                print(f"Cleared memory for {processor_id}")
        except Exception as e:
            print(f"Warning: Failed to clear memory: {e}")
    
    def run_test(self, test_path: str, processor_id: str) -> Tuple[int, int, int, List[str]]:
        """
        Run a single test or test file.
        
        Returns:
            Tuple of (passed, failed, skipped, errors)
        """
        if self.verbose:
            print(f"  Running: {test_path}")
        else:
            # Show minimal progress indicator
            print(".", end="", flush=True)
        
        # Build pytest command
        cmd = [
            sys.executable, '-m', 'pytest',
            os.path.join(self.test_dir, test_path),
            '-v' if self.verbose else '-q',
            '--tb=short',
            '--color=no'
        ]
        
        # Set environment for test
        env = os.environ.copy()
        env['KATO_CLUSTER_MODE'] = 'true'
        env['KATO_TEST_MODE'] = 'container'
        env['KATO_PROCESSOR_ID'] = processor_id
        env['KATO_API_URL'] = self.base_url
        
        # Run test
        result = subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            text=True,
            cwd=self.test_dir
        )
        
        # Parse results
        output = result.stdout + result.stderr
        passed = output.count(' PASSED')
        failed = output.count(' FAILED')
        skipped = output.count(' SKIPPED')
        
        errors = []
        if failed > 0:
            # Extract failure messages
            for line in output.split('\n'):
                if 'FAILED' in line or 'AssertionError' in line:
                    errors.append(line.strip())
        
        return passed, failed, skipped, errors
    
    def run_cluster(self, cluster: KatoTestCluster) -> ClusterResult:
        """Run all tests in a cluster."""
        if self.verbose:
            print(f"\n{'#'*60}")
            print(f"# Running Cluster: {cluster.name}")
            print(f"# Description: {cluster.description}")
            print(f"# Tests: {len(cluster.test_patterns)}")
            print(f"{'#'*60}")
        else:
            print(f"\n[{cluster.name}]", end="", flush=True)
        
        start_time = time.time()
        
        # Start KATO instance for this cluster
        processor_id = self.start_kato_instance(cluster)
        
        # Get all test files for this cluster
        test_files = get_tests_for_cluster(cluster, self.test_dir)
        
        total_passed = 0
        total_failed = 0
        total_skipped = 0
        all_errors = []
        
        # Run each test
        for test_path in test_files:
            # Clear memory before each test for isolation
            self.clear_all_memory(processor_id)
            
            # Run the test
            passed, failed, skipped, errors = self.run_test(test_path, processor_id)
            
            total_passed += passed
            total_failed += failed
            total_skipped += skipped
            all_errors.extend(errors)
        
        # Stop KATO instance
        self.stop_kato_instance(processor_id)
        
        duration = time.time() - start_time
        
        result = ClusterResult(
            cluster_name=cluster.name,
            processor_id=processor_id,
            passed=total_passed,
            failed=total_failed,
            skipped=total_skipped,
            errors=all_errors,
            duration=duration
        )
        
        # Print cluster summary
        print(f"\nCluster {cluster.name} Results:")
        print(f"  Passed: {total_passed}")
        print(f"  Failed: {total_failed}")
        print(f"  Skipped: {total_skipped}")
        print(f"  Duration: {duration:.2f}s")
        
        return result
    
    def run_all_clusters(self) -> List[ClusterResult]:
        """Run all test clusters."""
        print("\n" + "="*60)
        print("KATO CLUSTERED TEST EXECUTION")
        print("="*60)
        print(f"Found {len(TEST_CLUSTERS)} test clusters")
        
        if not self.verbose:
            print("Progress: ", end="", flush=True)
        
        results = []
        
        for cluster in TEST_CLUSTERS:
            try:
                result = self.run_cluster(cluster)
                results.append(result)
            except Exception as e:
                print(f"\nERROR running cluster {cluster.name}: {e}")
                # Create error result
                results.append(ClusterResult(
                    cluster_name=cluster.name,
                    processor_id="error",
                    passed=0,
                    failed=0,
                    skipped=0,
                    errors=[str(e)],
                    duration=0
                ))
        
        self.results = results
        return results
    
    def print_summary(self):
        """Print overall test summary."""
        print("\n" + "="*60)
        print("OVERALL TEST SUMMARY")
        print("="*60)
        
        total_passed = sum(r.passed for r in self.results)
        total_failed = sum(r.failed for r in self.results)
        total_skipped = sum(r.skipped for r in self.results)
        total_duration = sum(r.duration for r in self.results)
        
        print(f"\nTotal Results:")
        print(f"  Passed: {total_passed}")
        print(f"  Failed: {total_failed}")
        print(f"  Skipped: {total_skipped}")
        print(f"  Duration: {total_duration:.2f}s")
        
        if total_failed > 0:
            print("\nFailed Tests by Cluster:")
            for result in self.results:
                if result.failed > 0:
                    print(f"\n  {result.cluster_name} ({result.failed} failures):")
                    for error in result.errors[:5]:  # Show first 5 errors
                        print(f"    - {error}")
        
        return total_failed == 0


def main():
    """Main entry point for cluster runner."""
    # Get paths
    script_dir = os.path.dirname(os.path.abspath(__file__))
    kato_manager = os.path.join(os.path.dirname(script_dir), 'kato-manager.sh')
    test_dir = script_dir
    
    # Check if kato-manager exists
    if not os.path.exists(kato_manager):
        print(f"ERROR: kato-manager.sh not found at {kato_manager}")
        sys.exit(1)
    
    # Check for verbose flag
    verbose = os.environ.get('VERBOSE_OUTPUT') == 'true' or '--verbose' in sys.argv
    
    # Create runner
    runner = ClusterTestRunner(kato_manager, test_dir, verbose=verbose)
    
    # Run all clusters
    try:
        runner.run_all_clusters()
        success = runner.print_summary()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nTest execution interrupted by user")
        if runner.current_processor_id:
            runner.stop_kato_instance(runner.current_processor_id)
        sys.exit(130)
    except Exception as e:
        print(f"\n\nFATAL ERROR: {e}")
        if runner.current_processor_id:
            runner.stop_kato_instance(runner.current_processor_id)
        sys.exit(1)


if __name__ == "__main__":
    main()