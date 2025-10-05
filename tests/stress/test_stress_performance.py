#!/usr/bin/env python3
"""
KATO Stress Performance Tests
Comprehensive stress testing for KATO under various load scenarios.
"""

import concurrent.futures
import json
import logging
import os
import sys
import time
from datetime import datetime
from typing import Any, Dict, Optional

import requests
import yaml

# Add parent directories to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from load_generator import BurstLoadGenerator, LoadGenerator, LoadPattern, LoadProfile, VirtualUser
from performance_monitor import PerformanceMonitor

# Import test fixtures
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../tests/fixtures')))
from kato_fixtures import KATOFastAPIFixture as KATOTestFixture

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class StressTestRunner:
    """Main stress test runner for KATO."""

    def __init__(self, config_file: str = "stress_config.yaml"):
        """
        Initialize the stress test runner.
        
        Args:
            config_file: Path to configuration file
        """
        # Load configuration
        with open(config_file) as f:
            self.config = yaml.safe_load(f)

        self.base_url = self.config['environment']['kato_base_url']
        self.processor_id = self.config['environment']['kato_processor_id']

        # Initialize components
        self.monitor = None
        self.kato_fixture = None
        self.results = {}

    def setup(self):
        """Setup test environment."""
        logger.info("Setting up stress test environment")

        # Start KATO if needed
        self.kato_fixture = KATOTestFixture(processor_name="StressTest")
        self.kato_fixture.setup()

        # Update processor ID from running instance
        self.processor_id = self.kato_fixture.processor_id

        # Clear memory for clean test
        self.kato_fixture.clear_all_memory()

        # Initialize performance monitor
        container_name = self.config['environment'].get('docker_container_name')
        self.monitor = PerformanceMonitor(
            sample_interval=self.config['monitoring']['metrics_sample_interval_seconds'],
            container_name=container_name
        )

        # Add alert callback
        self.monitor.add_alert_callback(self._handle_alert)

        logger.info(f"Test environment ready. Processor ID: {self.processor_id}")

    def teardown(self):
        """Cleanup test environment."""
        logger.info("Cleaning up stress test environment")

        if self.monitor:
            self.monitor.stop()

        if self.kato_fixture:
            self.kato_fixture.teardown()

    def _handle_alert(self, message: str):
        """Handle performance alerts."""
        logger.warning(f"Performance Alert: {message}")

    def _make_request(self, operation: str, data: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Make a request to KATO and record metrics.
        
        Args:
            operation: Operation type (observe, learn, predictions, etc.)
            data: Request data
            
        Returns:
            Response data
        """
        start_time = time.time()
        success = False
        error_message = ""
        status_code = 0

        try:
            if operation == "observe":
                url = f"{self.base_url}/{self.processor_id}/observe"
                response = requests.post(url, json=data or {},
                                        timeout=self.config['test_parameters']['request_timeout_seconds'])

            elif operation == "learn":
                url = f"{self.base_url}/{self.processor_id}/learn"
                response = requests.post(url, json={},
                                        timeout=self.config['test_parameters']['request_timeout_seconds'])

            elif operation == "predictions":
                url = f"{self.base_url}/{self.processor_id}/predictions"
                response = requests.get(url,
                                       timeout=self.config['test_parameters']['request_timeout_seconds'])

            elif operation == "short_term_memory":
                url = f"{self.base_url}/{self.processor_id}/working-memory"
                response = requests.get(url,
                                       timeout=self.config['test_parameters']['request_timeout_seconds'])

            elif operation == "clear_short_term_memory":
                url = f"{self.base_url}/{self.processor_id}/clear-working-memory"
                response = requests.post(url, json={},
                                        timeout=self.config['test_parameters']['request_timeout_seconds'])
            else:
                raise ValueError(f"Unknown operation: {operation}")

            status_code = response.status_code
            response.raise_for_status()
            success = True
            return response.json()

        except requests.exceptions.Timeout:
            error_message = "Request timeout"
        except requests.exceptions.ConnectionError:
            error_message = "Connection error"
        except requests.exceptions.HTTPError as e:
            error_message = f"HTTP error: {e}"
        except Exception as e:
            error_message = str(e)

        finally:
            # Record metrics
            response_time_ms = (time.time() - start_time) * 1000
            self.monitor.record_request(
                response_time_ms=response_time_ms,
                success=success,
                operation_type=operation,
                error_message=error_message,
                status_code=status_code
            )

        return {"error": error_message}

    def test_concurrent_requests(self, num_users: int = 100, duration: int = 60):
        """
        Test concurrent requests from multiple users.
        
        Args:
            num_users: Number of concurrent users
            duration: Test duration in seconds
        """
        logger.info(f"Starting concurrent requests test: {num_users} users for {duration}s")

        # Start monitoring
        self.monitor.start()

        # Create test data generator
        data_generator = TestDataGenerator(self.config['test_data'])

        # Create virtual users
        users = []
        for i in range(num_users):
            user = VirtualUser(
                user_id=i,
                request_func=self._make_request,
                data_generator=data_generator,
                operations_mix=self.config['operations_mix'],
                requests_per_second=1.0,
                think_time_ms=100
            )
            users.append(user)

        # Start users
        for user in users:
            user.start()

        # Run for specified duration
        logger.info("Test running...")
        time.sleep(duration)

        # Stop users
        logger.info("Stopping virtual users...")
        for user in users:
            user.stop()

        # Stop monitoring
        self.monitor.stop()

        # Get statistics
        stats = self.monitor.get_current_statistics()
        self.results['concurrent_requests'] = stats

        logger.info(f"Concurrent requests test completed: {stats['total_requests']} requests")
        return stats

    def test_sustained_load(self, profile_name: str = "moderate"):
        """
        Test sustained load with a specific profile.
        
        Args:
            profile_name: Load profile name from config
        """
        profile_config = self.config['load_profiles'][profile_name]
        logger.info(f"Starting sustained load test with profile: {profile_name}")

        # Start monitoring
        self.monitor.start()

        # Create load profile
        profile = LoadProfile(
            pattern=LoadPattern.RAMP_UP,
            duration_seconds=profile_config['duration_seconds'],
            initial_users=1,
            peak_users=profile_config['concurrent_users'],
            requests_per_user_per_second=profile_config['requests_per_user_per_second'],
            think_time_ms=profile_config['think_time_ms'],
            ramp_time_seconds=profile_config['ramp_up_seconds']
        )

        # Create load generator
        generator = LoadGenerator(
            profile=profile,
            request_func=self._make_request,
            data_config=self.config['test_data'],
            operations_mix=self.config['operations_mix']
        )

        # Run load test
        generator.start()

        # Monitor progress
        report_interval = self.config['monitoring']['report_interval_seconds']
        elapsed = 0

        while elapsed < profile.duration_seconds:
            time.sleep(report_interval)
            elapsed += report_interval

            stats = self.monitor.get_current_statistics()
            gen_stats = generator.get_statistics()

            logger.info(f"Progress [{elapsed}/{profile.duration_seconds}s]: "
                       f"Users: {gen_stats['active_users']}, "
                       f"Requests: {stats['total_requests']}, "
                       f"Error rate: {stats['error_rate']*100:.2f}%, "
                       f"P99: {stats['response_time_p99']:.1f}ms")

        # Stop generator
        generator.stop()
        self.monitor.stop()

        # Get final statistics
        stats = self.monitor.get_current_statistics()
        self.results[f'sustained_load_{profile_name}'] = stats

        logger.info(f"Sustained load test completed: {stats['total_requests']} requests")
        return stats

    def test_burst_traffic(self, burst_size: int = 1000, burst_count: int = 5,
                          interval_seconds: int = 10):
        """
        Test burst traffic patterns.
        
        Args:
            burst_size: Number of requests per burst
            burst_count: Number of bursts
            interval_seconds: Seconds between bursts
        """
        logger.info(f"Starting burst traffic test: {burst_count} bursts of {burst_size} requests")

        # Start monitoring
        self.monitor.start()

        # Create burst generator
        data_generator = TestDataGenerator(self.config['test_data'])
        burst_generator = BurstLoadGenerator(
            request_func=self._make_request,
            data_generator=data_generator,
            burst_size=burst_size,
            burst_duration_ms=100
        )

        # Generate bursts
        for i in range(burst_count):
            logger.info(f"Generating burst {i+1}/{burst_count}")
            burst_generator.generate_burst()

            if i < burst_count - 1:
                time.sleep(interval_seconds)

        # Stop monitoring
        self.monitor.stop()

        # Get statistics
        stats = self.monitor.get_current_statistics()
        self.results['burst_traffic'] = stats

        logger.info(f"Burst traffic test completed: {stats['total_requests']} requests")
        return stats

    def test_connection_pool_exhaustion(self):
        """Test behavior when connection pool is exhausted."""
        logger.info("Starting connection pool exhaustion test")

        # Start monitoring
        self.monitor.start()

        pool_size = self.config['test_parameters']['connection_pool_size']
        overflow = self.config['test_parameters']['connection_pool_overflow']
        total_connections = pool_size + overflow

        # Create more concurrent requests than pool can handle
        num_requests = total_connections * 2

        def make_slow_request(request_id):
            """Make a request that holds the connection."""
            try:
                # Create a large observation to slow down processing
                data = {
                    "strings": ["test"] * 100,
                    "vectors": [0.5] * 1000
                }
                return self._make_request("observe", data)
            except Exception as e:
                return {"error": str(e)}

        # Launch concurrent requests
        with concurrent.futures.ThreadPoolExecutor(max_workers=num_requests) as executor:
            futures = [executor.submit(make_slow_request, i) for i in range(num_requests)]
            results = [f.result(timeout=30) for f in concurrent.futures.as_completed(futures)]

        # Stop monitoring
        self.monitor.stop()

        # Analyze results
        errors = [r for r in results if "error" in r]
        stats = self.monitor.get_current_statistics()

        stats['pool_exhaustion_errors'] = len(errors)
        stats['pool_exhaustion_rate'] = len(errors) / num_requests

        self.results['connection_pool_exhaustion'] = stats

        logger.info(f"Connection pool exhaustion test completed: "
                   f"{len(errors)}/{num_requests} requests failed")
        return stats

    def test_memory_leak(self, duration_minutes: int = 10):
        """
        Test for memory leaks under sustained load.
        
        Args:
            duration_minutes: Test duration in minutes
        """
        logger.info(f"Starting memory leak test for {duration_minutes} minutes")

        # Start monitoring with higher sample rate for memory
        self.monitor.start()

        # Create sustained load
        profile = LoadProfile(
            pattern=LoadPattern.CONSTANT,
            duration_seconds=duration_minutes * 60,
            initial_users=10,
            peak_users=10,
            requests_per_user_per_second=2.0,
            think_time_ms=500
        )

        generator = LoadGenerator(
            profile=profile,
            request_func=self._make_request,
            data_config=self.config['test_data'],
            operations_mix=self.config['operations_mix']
        )

        # Track memory over time
        memory_samples = []
        sample_interval = 30  # Sample every 30 seconds

        generator.start()

        for i in range(duration_minutes * 2):  # Sample twice per minute
            time.sleep(sample_interval)

            stats = self.monitor.get_current_statistics()
            if 'resource_stats' in stats and 'memory_mean_mb' in stats['resource_stats']:
                memory_samples.append({
                    'time': i * sample_interval,
                    'memory_mb': stats['resource_stats']['memory_mean_mb']
                })
                logger.info(f"Memory at {i*sample_interval}s: "
                           f"{stats['resource_stats']['memory_mean_mb']:.1f}MB")

        generator.stop()
        self.monitor.stop()

        # Analyze memory trend
        if len(memory_samples) > 2:
            initial_memory = memory_samples[0]['memory_mb']
            final_memory = memory_samples[-1]['memory_mb']
            memory_increase = final_memory - initial_memory
            memory_increase_pct = (memory_increase / initial_memory) * 100

            stats = self.monitor.get_current_statistics()
            stats['memory_leak_analysis'] = {
                'initial_memory_mb': initial_memory,
                'final_memory_mb': final_memory,
                'increase_mb': memory_increase,
                'increase_percent': memory_increase_pct,
                'samples': memory_samples
            }

            self.results['memory_leak'] = stats

            logger.info(f"Memory leak test completed: "
                       f"Memory increased by {memory_increase:.1f}MB ({memory_increase_pct:.1f}%)")
        else:
            logger.warning("Insufficient memory samples for leak analysis")

        return stats

    def test_error_recovery(self):
        """Test system recovery from errors."""
        logger.info("Starting error recovery test")

        # Start monitoring
        self.monitor.start()

        # Phase 1: Normal load
        logger.info("Phase 1: Establishing baseline...")
        data_generator = TestDataGenerator(self.config['test_data'])

        users = []
        for i in range(10):
            user = VirtualUser(
                user_id=i,
                request_func=self._make_request,
                data_generator=data_generator,
                operations_mix=self.config['operations_mix'],
                requests_per_second=1.0,
                think_time_ms=100
            )
            user.start()
            users.append(user)

        time.sleep(30)
        baseline_stats = self.monitor.get_current_statistics()

        # Phase 2: Induce errors (invalid requests)
        logger.info("Phase 2: Inducing errors...")

        def make_invalid_request():
            """Make an invalid request."""
            try:
                # Send invalid data
                response = requests.post(
                    f"{self.base_url}/{self.processor_id}/observe",
                    json={"invalid": "data" * 10000},  # Large invalid payload
                    timeout=5
                )
                return response.status_code
            except:
                return 0

        # Send burst of invalid requests
        with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
            futures = [executor.submit(make_invalid_request) for _ in range(100)]
            [f.result() for f in concurrent.futures.as_completed(futures)]

        time.sleep(10)
        error_stats = self.monitor.get_current_statistics()

        # Phase 3: Recovery
        logger.info("Phase 3: Monitoring recovery...")
        time.sleep(30)
        recovery_stats = self.monitor.get_current_statistics()

        # Stop users
        for user in users:
            user.stop()

        self.monitor.stop()

        # Analyze recovery
        self.results['error_recovery'] = {
            'baseline': baseline_stats,
            'during_errors': error_stats,
            'after_recovery': recovery_stats,
            'recovery_time_estimate': 30  # seconds
        }

        logger.info("Error recovery test completed")
        return self.results['error_recovery']

    def run_all_tests(self):
        """Run all stress tests."""
        logger.info("Starting comprehensive stress test suite")

        test_results = {}

        try:
            # Setup environment
            self.setup()

            # Run tests
            tests = [
                ('concurrent_requests', lambda: self.test_concurrent_requests(50, 60)),
                ('sustained_load_light', lambda: self.test_sustained_load('light')),
                ('sustained_load_moderate', lambda: self.test_sustained_load('moderate')),
                ('burst_traffic', lambda: self.test_burst_traffic(500, 3, 10)),
                ('connection_pool', lambda: self.test_connection_pool_exhaustion()),
                ('error_recovery', lambda: self.test_error_recovery()),
            ]

            for test_name, test_func in tests:
                try:
                    logger.info(f"\n{'='*60}")
                    logger.info(f"Running: {test_name}")
                    logger.info('='*60)

                    result = test_func()
                    test_results[test_name] = {
                        'status': 'completed',
                        'results': result
                    }

                    # Cool down between tests
                    cooldown = self.config['environment']['cooldown_duration_seconds']
                    logger.info(f"Cooling down for {cooldown} seconds...")
                    time.sleep(cooldown)

                    # Clear memory for next test
                    self.kato_fixture.clear_short_term_memory()

                except Exception as e:
                    logger.error(f"Test {test_name} failed: {e}")
                    test_results[test_name] = {
                        'status': 'failed',
                        'error': str(e)
                    }

        finally:
            # Cleanup
            self.teardown()

        # Save results
        self._save_results(test_results)

        # Print summary
        self._print_summary(test_results)

        return test_results

    def _save_results(self, results: Dict[str, Any]):
        """Save test results to file."""
        output_dir = self.config['reporting']['output_directory']
        os.makedirs(output_dir, exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        # Save JSON results
        json_file = os.path.join(output_dir, f'stress_test_results_{timestamp}.json')
        with open(json_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)

        logger.info(f"Results saved to: {json_file}")

        # Export detailed metrics if available
        if self.monitor:
            metrics_file = os.path.join(output_dir, f'metrics_{timestamp}')
            self.monitor.export_metrics(metrics_file, format='json')
            self.monitor.export_metrics(metrics_file, format='csv')

    def _print_summary(self, results: Dict[str, Any]):
        """Print test summary."""
        print("\n" + "="*80)
        print("STRESS TEST SUMMARY")
        print("="*80)

        for test_name, test_result in results.items():
            print(f"\n{test_name}:")
            print(f"  Status: {test_result['status']}")

            if test_result['status'] == 'completed' and 'results' in test_result:
                stats = test_result['results']
                if isinstance(stats, dict):
                    if 'total_requests' in stats:
                        print(f"  Total Requests: {stats.get('total_requests', 0):,}")
                        print(f"  Success Rate: {(1-stats.get('error_rate', 0))*100:.2f}%")
                    if 'response_time_p99' in stats:
                        print(f"  P99 Response Time: {stats.get('response_time_p99', 0):.1f}ms")
                    if 'throughput_rps' in stats:
                        print(f"  Throughput: {stats.get('throughput_rps', 0):.1f} req/s")

        print("="*80)

        # Check against thresholds
        self._check_thresholds(results)

    def _check_thresholds(self, results: Dict[str, Any]):
        """Check results against performance thresholds."""
        thresholds = self.config['performance_thresholds']
        violations = []

        for test_name, test_result in results.items():
            if test_result['status'] == 'completed' and 'results' in test_result:
                stats = test_result['results']
                if isinstance(stats, dict):
                    # Check response time thresholds
                    if stats.get('response_time_p99', 0) > thresholds['response_time_p99_max']:
                        violations.append(f"{test_name}: P99 response time "
                                        f"({stats['response_time_p99']:.1f}ms) exceeds threshold "
                                        f"({thresholds['response_time_p99_max']}ms)")

                    # Check error rate
                    if stats.get('error_rate', 0) > thresholds['max_error_rate']:
                        violations.append(f"{test_name}: Error rate "
                                        f"({stats['error_rate']*100:.2f}%) exceeds threshold "
                                        f"({thresholds['max_error_rate']*100:.2f}%)")

        if violations:
            print("\nThreshold Violations:")
            for violation in violations:
                print(f"  ⚠️  {violation}")
        else:
            print("\n✅ All performance thresholds met!")


def main():
    """Main entry point for stress tests."""
    import argparse

    parser = argparse.ArgumentParser(description='KATO Stress Performance Tests')
    parser.add_argument('--config', default='stress_config.yaml',
                       help='Configuration file path')
    parser.add_argument('--test', choices=[
        'concurrent', 'sustained', 'burst', 'pool', 'memory', 'recovery', 'all'
    ], default='all', help='Test to run')
    parser.add_argument('--profile', default='moderate',
                       help='Load profile for sustained test')

    args = parser.parse_args()

    # Create runner
    runner = StressTestRunner(config_file=args.config)

    try:
        if args.test == 'all':
            runner.run_all_tests()
        else:
            runner.setup()

            if args.test == 'concurrent':
                runner.test_concurrent_requests()
            elif args.test == 'sustained':
                runner.test_sustained_load(args.profile)
            elif args.test == 'burst':
                runner.test_burst_traffic()
            elif args.test == 'pool':
                runner.test_connection_pool_exhaustion()
            elif args.test == 'memory':
                runner.test_memory_leak()
            elif args.test == 'recovery':
                runner.test_error_recovery()

            runner.teardown()

            # Print results
            if runner.monitor:
                runner.monitor.print_summary()

    except KeyboardInterrupt:
        logger.info("Test interrupted by user")
        runner.teardown()
    except Exception as e:
        logger.error(f"Test failed: {e}")
        runner.teardown()
        raise


if __name__ == "__main__":
    main()
