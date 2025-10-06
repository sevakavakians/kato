#!/usr/bin/env python3
"""
Performance monitoring module for KATO stress tests.
Collects, analyzes, and reports performance metrics during test execution.
"""

import csv
import json
import statistics
import subprocess
import threading
import time
from collections import defaultdict, deque
from dataclasses import asdict, dataclass, field
from typing import Any, Optional


# Use pure Python statistics for compatibility
def calculate_percentile(data, p):
    """Calculate percentile using pure Python."""
    if not data:
        return 0
    data_sorted = sorted(data)
    k = (len(data_sorted) - 1) * (p / 100.0)
    floor = int(k)
    ceil = floor + 1
    if ceil >= len(data_sorted):
        return data_sorted[floor]
    return data_sorted[floor] * (ceil - k) + data_sorted[ceil] * (k - floor)


@dataclass
class PerformanceMetrics:
    """Container for performance metrics."""
    timestamp: float = field(default_factory=time.time)
    response_time_ms: float = 0.0
    success: bool = True
    operation_type: str = ""
    error_message: str = ""
    status_code: int = 200

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


@dataclass
class ResourceMetrics:
    """Container for resource usage metrics."""
    timestamp: float = field(default_factory=time.time)
    cpu_percent: float = 0.0
    memory_mb: float = 0.0
    memory_percent: float = 0.0
    network_bytes_sent: int = 0
    network_bytes_recv: int = 0
    active_connections: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


class PerformanceMonitor:
    """
    Monitors and analyzes performance metrics during stress tests.

    Features:
    - Real-time metric collection
    - Statistical analysis (percentiles, throughput, error rates)
    - Resource monitoring (CPU, memory, network)
    - Trend detection and alerting
    """

    def __init__(self, sample_interval: float = 1.0,
                 window_size: int = 1000,
                 container_name: Optional[str] = None):
        """
        Initialize the performance monitor.

        Args:
            sample_interval: Seconds between metric samples
            window_size: Size of sliding window for metrics
            container_name: Docker container to monitor (optional)
        """
        self.sample_interval = sample_interval
        self.window_size = window_size
        self.container_name = container_name

        # Metrics storage
        self.performance_metrics = deque(maxlen=window_size)
        self.resource_metrics = deque(maxlen=window_size)
        self.operation_metrics = defaultdict(lambda: deque(maxlen=window_size))

        # Aggregate statistics
        self.total_requests = 0
        self.total_successes = 0
        self.total_failures = 0
        self.start_time = None
        self.end_time = None

        # Threading control
        self.monitoring = False
        self.monitor_thread = None
        self.lock = threading.Lock()

        # Alert thresholds
        self.alert_thresholds = {
            'response_time_p99': 100,  # ms
            'error_rate': 0.01,  # 1%
            'cpu_percent': 80,
            'memory_percent': 80
        }

        # Alert callbacks
        self.alert_callbacks = []

    def start(self):
        """Start monitoring."""
        self.monitoring = True
        self.start_time = time.time()
        self.monitor_thread = threading.Thread(target=self._monitor_loop)
        self.monitor_thread.daemon = True
        self.monitor_thread.start()

    def stop(self):
        """Stop monitoring."""
        self.monitoring = False
        self.end_time = time.time()
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)

    def record_request(self, response_time_ms: float, success: bool,
                       operation_type: str = "unknown",
                       error_message: str = "", status_code: int = 200):
        """
        Record a request metric.

        Args:
            response_time_ms: Response time in milliseconds
            success: Whether the request succeeded
            operation_type: Type of operation (observe, learn, etc.)
            error_message: Error message if failed
            status_code: HTTP status code
        """
        metric = PerformanceMetrics(
            timestamp=time.time(),
            response_time_ms=response_time_ms,
            success=success,
            operation_type=operation_type,
            error_message=error_message,
            status_code=status_code
        )

        with self.lock:
            self.performance_metrics.append(metric)
            self.operation_metrics[operation_type].append(metric)

            self.total_requests += 1
            if success:
                self.total_successes += 1
            else:
                self.total_failures += 1

        # Check thresholds
        self._check_thresholds()

    def _monitor_loop(self):
        """Background monitoring loop."""
        while self.monitoring:
            try:
                # Collect resource metrics
                if self.container_name:
                    resource_metric = self._collect_container_metrics()
                else:
                    resource_metric = self._collect_system_metrics()

                with self.lock:
                    self.resource_metrics.append(resource_metric)

            except Exception as e:
                print(f"Error collecting metrics: {e}")

            time.sleep(self.sample_interval)

    def _collect_container_metrics(self) -> ResourceMetrics:
        """Collect Docker container metrics."""
        metric = ResourceMetrics()

        try:
            # Get container stats
            cmd = f"docker stats {self.container_name} --no-stream --format json"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

            if result.returncode == 0:
                stats = json.loads(result.stdout)

                # Parse CPU percentage
                cpu_str = stats.get('CPUPerc', '0%').strip('%')
                metric.cpu_percent = float(cpu_str) if cpu_str else 0.0

                # Parse memory usage
                mem_str = stats.get('MemUsage', '0MiB / 0MiB')
                if '/' in mem_str:
                    used_str = mem_str.split('/')[0].strip()
                    # Convert to MB
                    if 'GiB' in used_str:
                        metric.memory_mb = float(used_str.replace('GiB', '')) * 1024
                    elif 'MiB' in used_str:
                        metric.memory_mb = float(used_str.replace('MiB', ''))

                # Parse memory percentage
                mem_perc_str = stats.get('MemPerc', '0%').strip('%')
                metric.memory_percent = float(mem_perc_str) if mem_perc_str else 0.0

                # Network I/O (if available)
                net_str = stats.get('NetIO', '0B / 0B')
                if '/' in net_str:
                    sent_str, recv_str = net_str.split('/')
                    metric.network_bytes_sent = self._parse_bytes(sent_str.strip())
                    metric.network_bytes_recv = self._parse_bytes(recv_str.strip())

        except Exception as e:
            print(f"Error collecting container metrics: {e}")

        return metric

    def _collect_system_metrics(self) -> ResourceMetrics:
        """Collect system-wide metrics."""
        metric = ResourceMetrics()

        try:
            import psutil

            # CPU usage
            metric.cpu_percent = psutil.cpu_percent(interval=0.1)

            # Memory usage
            mem = psutil.virtual_memory()
            metric.memory_mb = mem.used / (1024 * 1024)
            metric.memory_percent = mem.percent

            # Network I/O
            net = psutil.net_io_counters()
            metric.network_bytes_sent = net.bytes_sent
            metric.network_bytes_recv = net.bytes_recv

            # Active connections (approximate)
            connections = psutil.net_connections()
            metric.active_connections = len([c for c in connections
                                            if c.status == 'ESTABLISHED'])

        except ImportError:
            print("psutil not installed - system metrics unavailable")
        except Exception as e:
            print(f"Error collecting system metrics: {e}")

        return metric

    def _parse_bytes(self, byte_str: str) -> int:
        """Parse byte string to integer."""
        byte_str = byte_str.strip()

        multipliers = {
            'B': 1,
            'kB': 1024,
            'MB': 1024**2,
            'GB': 1024**3,
            'TB': 1024**4
        }

        for suffix, multiplier in multipliers.items():
            if suffix in byte_str:
                value = float(byte_str.replace(suffix, '').strip())
                return int(value * multiplier)

        return 0

    def _check_thresholds(self):
        """Check if any thresholds are exceeded."""
        stats = self.get_current_statistics()

        alerts = []

        # Check response time
        if stats['response_time_p99'] > self.alert_thresholds['response_time_p99']:
            alerts.append(f"High response time: p99={stats['response_time_p99']:.1f}ms")

        # Check error rate
        if stats['error_rate'] > self.alert_thresholds['error_rate']:
            alerts.append(f"High error rate: {stats['error_rate']*100:.2f}%")

        # Check resources
        if self.resource_metrics:
            latest_resource = self.resource_metrics[-1]

            if latest_resource.cpu_percent > self.alert_thresholds['cpu_percent']:
                alerts.append(f"High CPU usage: {latest_resource.cpu_percent:.1f}%")

            if latest_resource.memory_percent > self.alert_thresholds['memory_percent']:
                alerts.append(f"High memory usage: {latest_resource.memory_percent:.1f}%")

        # Trigger alert callbacks
        for alert in alerts:
            self._trigger_alert(alert)

    def _trigger_alert(self, message: str):
        """Trigger alert callbacks."""
        for callback in self.alert_callbacks:
            try:
                callback(message)
            except Exception as e:
                print(f"Error in alert callback: {e}")

    def add_alert_callback(self, callback):
        """Add an alert callback function."""
        self.alert_callbacks.append(callback)

    def get_current_statistics(self) -> dict[str, Any]:
        """Get current performance statistics."""
        with self.lock:
            if not self.performance_metrics:
                return self._empty_statistics()

            # Calculate response time statistics
            response_times = [m.response_time_ms for m in self.performance_metrics]

            # Calculate percentiles
            percentiles = {}
            for p in [50, 75, 90, 95, 99, 99.9]:
                p_int = int(p) if isinstance(p, float) and p.is_integer() else p
                percentiles[f'p{p_int}'] = (
                    calculate_percentile(response_times, p) if response_times else 0
                )

            # Calculate throughput
            if self.start_time and len(self.performance_metrics) > 1:
                time_range = (self.performance_metrics[-1].timestamp -
                            self.performance_metrics[0].timestamp)
                throughput = len(self.performance_metrics) / time_range if time_range > 0 else 0
            else:
                throughput = 0

            # Calculate error rate
            error_rate = self.total_failures / self.total_requests if self.total_requests > 0 else 0

            # Operation breakdown
            operation_stats = {}
            for op_type, metrics in self.operation_metrics.items():
                if metrics:
                    op_times = [m.response_time_ms for m in metrics]
                    operation_stats[op_type] = {
                        'count': len(metrics),
                        'mean_ms': statistics.mean(op_times),
                        'p99_ms': calculate_percentile(op_times, 99)
                    }

            # Resource statistics
            resource_stats = {}
            if self.resource_metrics:
                cpu_values = [m.cpu_percent for m in self.resource_metrics]
                memory_values = [m.memory_mb for m in self.resource_metrics]

                resource_stats = {
                    'cpu_mean': statistics.mean(cpu_values),
                    'cpu_max': max(cpu_values),
                    'memory_mean_mb': statistics.mean(memory_values),
                    'memory_max_mb': max(memory_values)
                }

            return {
                'total_requests': self.total_requests,
                'total_successes': self.total_successes,
                'total_failures': self.total_failures,
                'error_rate': error_rate,
                'throughput_rps': throughput,
                'response_time_mean': statistics.mean(response_times) if response_times else 0,
                'response_time_min': min(response_times) if response_times else 0,
                'response_time_max': max(response_times) if response_times else 0,
                'response_time_p50': percentiles.get('p50', 0),
                'response_time_p95': percentiles.get('p95', 0),
                'response_time_p99': percentiles.get('p99', 0),
                'response_time_p99.9': percentiles.get('p99.9', 0),
                'operation_stats': operation_stats,
                'resource_stats': resource_stats,
                'duration_seconds': (self.end_time or time.time()) - self.start_time if self.start_time else 0
            }

    def _empty_statistics(self) -> dict[str, Any]:
        """Return empty statistics structure."""
        return {
            'total_requests': 0,
            'total_successes': 0,
            'total_failures': 0,
            'error_rate': 0,
            'throughput_rps': 0,
            'response_time_mean': 0,
            'response_time_min': 0,
            'response_time_max': 0,
            'response_time_p50': 0,
            'response_time_p95': 0,
            'response_time_p99': 0,
            'response_time_p99.9': 0,
            'operation_stats': {},
            'resource_stats': {},
            'duration_seconds': 0
        }

    def export_metrics(self, filepath: str, format: str = 'json'):
        """
        Export collected metrics to file.

        Args:
            filepath: Output file path
            format: Export format (json, csv)
        """
        stats = self.get_current_statistics()

        if format == 'json':
            with open(filepath, 'w') as f:
                json.dump(stats, f, indent=2)

        elif format == 'csv':
            # Export performance metrics
            perf_file = filepath.replace('.csv', '_performance.csv')
            with open(perf_file, 'w', newline='') as f:
                if self.performance_metrics:
                    fieldnames = self.performance_metrics[0].to_dict().keys()
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    for metric in self.performance_metrics:
                        writer.writerow(metric.to_dict())

            # Export resource metrics
            resource_file = filepath.replace('.csv', '_resources.csv')
            with open(resource_file, 'w', newline='') as f:
                if self.resource_metrics:
                    fieldnames = self.resource_metrics[0].to_dict().keys()
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    for metric in self.resource_metrics:
                        writer.writerow(metric.to_dict())

    def print_summary(self):
        """Print performance summary to console."""
        stats = self.get_current_statistics()

        print("\n" + "="*60)
        print("PERFORMANCE TEST SUMMARY")
        print("="*60)

        print(f"\nTest Duration: {stats['duration_seconds']:.1f} seconds")
        print(f"Total Requests: {stats['total_requests']:,}")
        print(f"Successful: {stats['total_successes']:,}")
        print(f"Failed: {stats['total_failures']:,}")
        print(f"Error Rate: {stats['error_rate']*100:.2f}%")
        print(f"Throughput: {stats['throughput_rps']:.1f} req/sec")

        print("\nResponse Times (ms):")
        print(f"  Min: {stats['response_time_min']:.1f}")
        print(f"  Mean: {stats['response_time_mean']:.1f}")
        print(f"  P50: {stats['response_time_p50']:.1f}")
        print(f"  P95: {stats['response_time_p95']:.1f}")
        print(f"  P99: {stats['response_time_p99']:.1f}")
        print(f"  P99.9: {stats['response_time_p99.9']:.1f}")
        print(f"  Max: {stats['response_time_max']:.1f}")

        if stats['operation_stats']:
            print("\nOperation Breakdown:")
            for op_type, op_stats in stats['operation_stats'].items():
                print(f"  {op_type}:")
                print(f"    Count: {op_stats['count']:,}")
                print(f"    Mean: {op_stats['mean_ms']:.1f} ms")
                print(f"    P99: {op_stats['p99_ms']:.1f} ms")

        if stats['resource_stats']:
            print("\nResource Usage:")
            print(f"  CPU Mean: {stats['resource_stats']['cpu_mean']:.1f}%")
            print(f"  CPU Max: {stats['resource_stats']['cpu_max']:.1f}%")
            print(f"  Memory Mean: {stats['resource_stats']['memory_mean_mb']:.1f} MB")
            print(f"  Memory Max: {stats['resource_stats']['memory_max_mb']:.1f} MB")

        print("="*60)
