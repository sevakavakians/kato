"""
KATO v2.0 Metrics Collection

Provides comprehensive metrics collection for monitoring and observability.
Supports Prometheus-format metrics and custom metrics tracking.
"""

import asyncio
import time
import psutil
import logging
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime, timedelta
from collections import defaultdict, deque
from dataclasses import dataclass, field
import threading

logger = logging.getLogger('kato.v2.monitoring.metrics')


@dataclass
class MetricValue:
    """Single metric value with timestamp"""
    value: float
    timestamp: float
    labels: Dict[str, str] = field(default_factory=dict)


@dataclass 
class Metric:
    """Metric definition with time-series data"""
    name: str
    type: str  # counter, gauge, histogram, summary
    description: str
    unit: str = ""
    values: deque = field(default_factory=lambda: deque(maxlen=1000))
    
    def add_value(self, value: float, labels: Dict[str, str] = None):
        """Add a value to the metric"""
        self.values.append(MetricValue(
            value=value,
            timestamp=time.time(),
            labels=labels or {}
        ))
    
    def get_current(self) -> Optional[float]:
        """Get most recent value"""
        if self.values:
            return self.values[-1].value
        return None
    
    def get_average(self, window_seconds: int = 60) -> float:
        """Get average over time window"""
        if not self.values:
            return 0.0
        
        cutoff = time.time() - window_seconds
        recent_values = [v.value for v in self.values if v.timestamp > cutoff]
        
        if recent_values:
            return sum(recent_values) / len(recent_values)
        return 0.0
    
    def get_rate(self, window_seconds: int = 60) -> float:
        """Get rate of change per second"""
        if len(self.values) < 2:
            return 0.0
        
        cutoff = time.time() - window_seconds
        recent_values = [(v.value, v.timestamp) for v in self.values if v.timestamp > cutoff]
        
        if len(recent_values) < 2:
            return 0.0
        
        # Calculate rate based on first and last values in window
        value_diff = recent_values[-1][0] - recent_values[0][0]
        time_diff = recent_values[-1][1] - recent_values[0][1]
        
        if time_diff > 0:
            return value_diff / time_diff
        return 0.0


class MetricsCollector:
    """
    Centralized metrics collector for KATO v2.0.
    
    Collects and exposes metrics in Prometheus format and
    provides APIs for custom metric tracking.
    """
    
    def __init__(self):
        """Initialize metrics collector"""
        self.metrics: Dict[str, Metric] = {}
        self._lock = threading.RLock()
        self._collection_task = None
        self._collection_interval = 10  # seconds
        self._initialized = False
        
        # Initialize core metrics
        self._init_core_metrics()
        
        logger.info("MetricsCollector initialized")
    
    def _init_core_metrics(self):
        """Initialize core system metrics"""
        
        # Session metrics
        self.register_metric(
            "kato_sessions_total",
            "counter",
            "Total number of sessions created"
        )
        self.register_metric(
            "kato_sessions_active",
            "gauge",
            "Current number of active sessions"
        )
        self.register_metric(
            "kato_sessions_expired",
            "counter",
            "Total number of expired sessions"
        )
        
        # Request metrics
        self.register_metric(
            "kato_requests_total",
            "counter",
            "Total number of requests processed"
        )
        self.register_metric(
            "kato_request_duration_seconds",
            "histogram",
            "Request processing duration",
            unit="seconds"
        )
        self.register_metric(
            "kato_requests_failed",
            "counter",
            "Total number of failed requests"
        )
        
        # Performance metrics
        self.register_metric(
            "kato_observations_per_second",
            "gauge",
            "Current observations processing rate",
            unit="ops"
        )
        self.register_metric(
            "kato_predictions_per_second",
            "gauge",
            "Current predictions processing rate",
            unit="ops"
        )
        
        # Resource metrics
        self.register_metric(
            "kato_cpu_usage_percent",
            "gauge",
            "CPU usage percentage",
            unit="percent"
        )
        self.register_metric(
            "kato_memory_usage_bytes",
            "gauge",
            "Memory usage in bytes",
            unit="bytes"
        )
        self.register_metric(
            "kato_memory_usage_percent",
            "gauge",
            "Memory usage percentage",
            unit="percent"
        )
        
        # Database metrics
        self.register_metric(
            "kato_mongodb_connections",
            "gauge",
            "Number of MongoDB connections"
        )
        self.register_metric(
            "kato_qdrant_connections",
            "gauge",
            "Number of Qdrant connections"
        )
        self.register_metric(
            "kato_redis_connections",
            "gauge",
            "Number of Redis connections"
        )
        
        # Error metrics
        self.register_metric(
            "kato_errors_total",
            "counter",
            "Total number of errors"
        )
        self.register_metric(
            "kato_circuit_breaker_opens",
            "counter",
            "Number of circuit breaker open events"
        )
    
    def register_metric(
        self,
        name: str,
        metric_type: str,
        description: str,
        unit: str = ""
    ) -> Metric:
        """
        Register a new metric.
        
        Args:
            name: Metric name (should follow Prometheus naming)
            metric_type: Type of metric (counter, gauge, histogram, summary)
            description: Human-readable description
            unit: Unit of measurement
        
        Returns:
            Registered Metric object
        """
        with self._lock:
            if name not in self.metrics:
                metric = Metric(
                    name=name,
                    type=metric_type,
                    description=description,
                    unit=unit
                )
                self.metrics[name] = metric
                logger.debug(f"Registered metric: {name}")
            return self.metrics[name]
    
    def increment(self, name: str, value: float = 1.0, labels: Dict[str, str] = None):
        """Increment a counter metric"""
        with self._lock:
            if name in self.metrics:
                metric = self.metrics[name]
                current = metric.get_current() or 0
                metric.add_value(current + value, labels)
    
    def set(self, name: str, value: float, labels: Dict[str, str] = None):
        """Set a gauge metric"""
        with self._lock:
            if name in self.metrics:
                self.metrics[name].add_value(value, labels)
    
    def observe(self, name: str, value: float, labels: Dict[str, str] = None):
        """Observe a value for histogram/summary"""
        with self._lock:
            if name in self.metrics:
                self.metrics[name].add_value(value, labels)
    
    def get_metric(self, name: str) -> Optional[Metric]:
        """Get a specific metric"""
        with self._lock:
            return self.metrics.get(name)
    
    def get_all_metrics(self) -> Dict[str, Dict[str, Any]]:
        """
        Get all metrics as a dictionary.
        
        Returns:
            Dictionary of metric data
        """
        with self._lock:
            result = {}
            for name, metric in self.metrics.items():
                result[name] = {
                    "type": metric.type,
                    "description": metric.description,
                    "unit": metric.unit,
                    "current": metric.get_current(),
                    "average_1m": metric.get_average(60),
                    "rate_1m": metric.get_rate(60) if metric.type == "counter" else None
                }
            return result
    
    def get_prometheus_format(self) -> str:
        """
        Get metrics in Prometheus text format.
        
        Returns:
            Prometheus-formatted metrics string
        """
        lines = []
        
        with self._lock:
            for name, metric in self.metrics.items():
                # Add HELP and TYPE comments
                lines.append(f"# HELP {name} {metric.description}")
                lines.append(f"# TYPE {name} {metric.type}")
                
                # Add metric value
                current_value = metric.get_current()
                if current_value is not None:
                    if metric.values and metric.values[-1].labels:
                        # Format with labels
                        labels_str = ",".join(
                            f'{k}="{v}"' for k, v in metric.values[-1].labels.items()
                        )
                        lines.append(f"{name}{{{labels_str}}} {current_value}")
                    else:
                        lines.append(f"{name} {current_value}")
                
                lines.append("")  # Empty line between metrics
        
        return "\n".join(lines)
    
    async def collect_system_metrics(self):
        """Collect system resource metrics"""
        try:
            # CPU metrics
            cpu_percent = psutil.cpu_percent(interval=1)
            self.set("kato_cpu_usage_percent", cpu_percent)
            
            # Memory metrics
            memory = psutil.virtual_memory()
            self.set("kato_memory_usage_bytes", memory.used)
            self.set("kato_memory_usage_percent", memory.percent)
            
            # Disk metrics (optional)
            disk = psutil.disk_usage('/')
            self.register_metric(
                "kato_disk_usage_percent",
                "gauge",
                "Disk usage percentage",
                unit="percent"
            )
            self.set("kato_disk_usage_percent", disk.percent)
            
            # Network metrics (optional)
            net_io = psutil.net_io_counters()
            self.register_metric(
                "kato_network_bytes_sent",
                "counter",
                "Total network bytes sent",
                unit="bytes"
            )
            self.register_metric(
                "kato_network_bytes_recv",
                "counter",
                "Total network bytes received",
                unit="bytes"
            )
            self.set("kato_network_bytes_sent", net_io.bytes_sent)
            self.set("kato_network_bytes_recv", net_io.bytes_recv)
            
        except Exception as e:
            logger.error(f"Error collecting system metrics: {e}")
    
    async def start_collection(self, interval: int = 10):
        """
        Start background metrics collection.
        
        Args:
            interval: Collection interval in seconds
        """
        self._collection_interval = interval
        
        if not self._collection_task:
            self._collection_task = asyncio.create_task(self._collection_loop())
            logger.info(f"Started metrics collection with {interval}s interval")
    
    async def stop_collection(self):
        """Stop background metrics collection"""
        if self._collection_task:
            self._collection_task.cancel()
            try:
                await self._collection_task
            except asyncio.CancelledError:
                pass
            self._collection_task = None
            logger.info("Stopped metrics collection")
    
    async def _collection_loop(self):
        """Background collection loop"""
        while True:
            try:
                await self.collect_system_metrics()
                await asyncio.sleep(self._collection_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in collection loop: {e}")
                await asyncio.sleep(self._collection_interval)
    
    def get_summary_metrics(self) -> Dict[str, Any]:
        """Get comprehensive summary of all metrics"""
        current_time = time.time()
        
        # Get all current metrics
        all_metrics = self.get_all_metrics()
        
        # Organize into categories
        summary = {
            "timestamp": current_time,
            "sessions": {
                "total_created": all_metrics.get("sessions_created", {}).get("current", 0),
                "total_deleted": all_metrics.get("sessions_deleted", {}).get("current", 0),
                "active": all_metrics.get("sessions_active", {}).get("current", 0),
                "operations_total": all_metrics.get("session_operations", {}).get("current", 0)
            },
            "performance": {
                "total_requests": all_metrics.get("requests_total", {}).get("current", 0),
                "total_errors": all_metrics.get("errors_total", {}).get("current", 0),
                "error_rate": (all_metrics.get("errors_total", {}).get("current", 0) / 
                              max(1, all_metrics.get("requests_total", {}).get("current", 0))),
                "average_response_time": all_metrics.get("response_time", {}).get("average_1m", 0)
            },
            "resources": {
                "cpu_percent": all_metrics.get("cpu_percent", {}).get("current", 0),
                "memory_percent": all_metrics.get("memory_percent", {}).get("current", 0),
                "disk_percent": all_metrics.get("disk_percent", {}).get("current", 0)
            },
            "databases": {
                "mongodb": {
                    "operations": all_metrics.get("mongodb_operations", {}).get("current", 0),
                    "errors": all_metrics.get("mongodb_errors", {}).get("current", 0),
                    "avg_response_time": all_metrics.get("mongodb_response_time", {}).get("average_1m", 0)
                },
                "qdrant": {
                    "operations": all_metrics.get("qdrant_operations", {}).get("current", 0),
                    "errors": all_metrics.get("qdrant_errors", {}).get("current", 0),
                    "avg_response_time": all_metrics.get("qdrant_response_time", {}).get("average_1m", 0)
                },
                "redis": {
                    "operations": all_metrics.get("redis_operations", {}).get("current", 0),
                    "errors": all_metrics.get("redis_errors", {}).get("current", 0),
                    "avg_response_time": all_metrics.get("redis_response_time", {}).get("average_1m", 0)
                }
            }
        }
        
        return summary
    
    def calculate_rates(self) -> Dict[str, float]:
        """Calculate rate metrics over different time windows"""
        rates = {}
        
        # Request rates
        if "requests_total" in self.metrics:
            rates["requests_per_second"] = self.metrics["requests_total"].get_rate(60)
            rates["requests_per_minute"] = self.metrics["requests_total"].get_rate(60) * 60
        
        # Error rates
        if "errors_total" in self.metrics:
            rates["errors_per_minute"] = self.metrics["errors_total"].get_rate(60) * 60
        
        # Session rates
        if "sessions_created" in self.metrics:
            rates["sessions_per_minute"] = self.metrics["sessions_created"].get_rate(60) * 60
        
        # Database operation rates
        for db in ["mongodb", "qdrant", "redis"]:
            metric_name = f"{db}_operations"
            if metric_name in self.metrics:
                rates[f"{db}_ops_per_second"] = self.metrics[metric_name].get_rate(60)
        
        return rates
    
    def get_health_status(self) -> Dict[str, Any]:
        """
        Get system health status based on metrics.
        
        Returns:
            Health status dictionary
        """
        with self._lock:
            cpu_usage = self.metrics.get("kato_cpu_usage_percent")
            memory_usage = self.metrics.get("kato_memory_usage_percent")
            error_rate = self.metrics.get("kato_errors_total")
            
            # Determine health status
            issues = []
            status = "healthy"
            
            cpu_current = cpu_usage.get_current() if cpu_usage else None
            memory_current = memory_usage.get_current() if memory_usage else None
            error_rate_current = error_rate.get_rate(60) if error_rate else None
            
            if cpu_current is not None and cpu_current > 80:
                issues.append("High CPU usage")
                status = "degraded"
            
            if memory_current is not None and memory_current > 90:
                issues.append("High memory usage")
                status = "unhealthy"
            
            if error_rate_current is not None and error_rate_current > 10:
                issues.append("High error rate")
                status = "degraded"
            
            return {
                "status": status,
                "issues": issues,
                "metrics": {
                    "cpu_percent": cpu_current,
                    "memory_percent": memory_current,
                    "error_rate_per_min": error_rate_current
                },
                "timestamp": datetime.utcnow().isoformat()
            }
    
    def get_time_series(
        self,
        metric_name: str,
        window_seconds: int = 3600
    ) -> List[Dict[str, Any]]:
        """
        Get time series data for a metric.
        
        Args:
            metric_name: Name of the metric
            window_seconds: Time window in seconds
        
        Returns:
            List of time-series data points
        """
        with self._lock:
            metric = self.metrics.get(metric_name)
            if not metric:
                return []
            
            cutoff = time.time() - window_seconds
            result = []
            
            for value in metric.values:
                if value.timestamp > cutoff:
                    result.append({
                        "timestamp": value.timestamp,
                        "value": value.value,
                        "labels": value.labels
                    })
            
            return result
    
    def record_request(
        self,
        method: str,
        path: str,
        status_code: int,
        duration: float,
        session_id: Optional[str] = None
    ):
        """
        Record HTTP request metrics.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            path: Request path
            status_code: HTTP status code
            duration: Request duration in seconds
            session_id: Optional session ID
        """
        # Increment total requests counter
        self.increment("kato_requests_total", labels={"method": method, "path": path})
        
        # Record request duration
        self.observe("kato_request_duration_seconds", duration, labels={
            "method": method,
            "path": path,
            "status": str(status_code)
        })
        
        # Increment failed requests if status indicates error
        if status_code >= 400:
            self.increment("kato_requests_failed", labels={
                "method": method,
                "path": path,
                "status": str(status_code)
            })


# Singleton instance
_metrics_collector: Optional[MetricsCollector] = None


def get_metrics_collector() -> MetricsCollector:
    """
    Get or create the singleton metrics collector.
    
    Returns:
        MetricsCollector singleton instance
    """
    global _metrics_collector
    
    if _metrics_collector is None:
        _metrics_collector = MetricsCollector()
    
    return _metrics_collector


# Decorator for timing functions
def timed_metric(metric_name: str = None):
    """
    Decorator to time function execution.
    
    Args:
        metric_name: Optional metric name (defaults to function name)
    """
    def decorator(func):
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                return result
            finally:
                duration = time.time() - start_time
                collector = get_metrics_collector()
                name = metric_name or f"kato_function_{func.__name__}_duration"
                collector.observe(name, duration)
        
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                duration = time.time() - start_time
                collector = get_metrics_collector()
                name = metric_name or f"kato_function_{func.__name__}_duration"
                collector.observe(name, duration)
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator