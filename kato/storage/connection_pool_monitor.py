"""
Enhanced Connection Pool Monitoring and Optimization

Provides advanced monitoring and auto-tuning capabilities for database connections.
"""

import asyncio
import logging
import time
import threading
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from collections import deque
import statistics

logger = logging.getLogger('kato.storage.connection_pool_monitor')


@dataclass
class ConnectionMetrics:
    """Detailed connection pool metrics."""
    timestamp: float = field(default_factory=time.time)
    active_connections: int = 0
    idle_connections: int = 0
    total_connections: int = 0
    failed_connections: int = 0
    response_time_ms: float = 0.0
    errors_per_minute: float = 0.0
    throughput_ops_per_second: float = 0.0


@dataclass
class PoolOptimizationSettings:
    """Settings for connection pool auto-tuning."""
    enable_auto_tuning: bool = True
    min_pool_size: int = 5
    max_pool_size: int = 100
    target_response_time_ms: float = 10.0
    scale_up_threshold: float = 0.8  # Scale up when utilization > 80%
    scale_down_threshold: float = 0.3  # Scale down when utilization < 30%
    optimization_interval_seconds: float = 60.0  # Check every minute


class ConnectionPoolMonitor:
    """
    Advanced connection pool monitor with auto-tuning capabilities.
    
    Features:
    - Real-time pool metrics collection
    - Automatic pool size optimization
    - Performance trend analysis
    - Alert generation for anomalies
    """
    
    def __init__(self, optimization_settings: Optional[PoolOptimizationSettings] = None):
        """Initialize the connection pool monitor."""
        self.settings = optimization_settings or PoolOptimizationSettings()
        
        # Metrics storage (keep last 1000 data points)
        self._metrics_history: Dict[str, deque] = {
            'mongodb': deque(maxlen=1000),
            'redis': deque(maxlen=1000), 
            'qdrant': deque(maxlen=1000)
        }
        
        # Current metrics
        self._current_metrics: Dict[str, ConnectionMetrics] = {}
        
        # Monitoring state
        self._monitoring_active = False
        self._monitor_task: Optional[asyncio.Task] = None
        self._lock = threading.Lock()
        
        # Performance baselines
        self._performance_baselines: Dict[str, Dict[str, float]] = {
            'mongodb': {'response_time_ms': 5.0, 'throughput_ops_per_second': 100.0},
            'redis': {'response_time_ms': 1.0, 'throughput_ops_per_second': 1000.0},
            'qdrant': {'response_time_ms': 10.0, 'throughput_ops_per_second': 50.0}
        }
    
    async def start_monitoring(self):
        """Start the connection pool monitoring."""
        if self._monitoring_active:
            logger.warning("Connection pool monitoring already active")
            return
        
        self._monitoring_active = True
        self._monitor_task = asyncio.create_task(self._monitoring_loop())
        logger.info("Connection pool monitoring started")
    
    async def stop_monitoring(self):
        """Stop the connection pool monitoring."""
        self._monitoring_active = False
        
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            self._monitor_task = None
        
        logger.info("Connection pool monitoring stopped")
    
    def record_metrics(self, db_type: str, metrics: ConnectionMetrics):
        """Record metrics for a specific database type."""
        with self._lock:
            self._current_metrics[db_type] = metrics
            self._metrics_history[db_type].append(metrics)
        
        # Check for performance anomalies
        self._check_performance_anomalies(db_type, metrics)
    
    def get_current_metrics(self) -> Dict[str, ConnectionMetrics]:
        """Get current metrics for all database types."""
        with self._lock:
            return self._current_metrics.copy()
    
    def get_metrics_history(self, db_type: str, minutes: int = 60) -> List[ConnectionMetrics]:
        """Get metrics history for a specific database type."""
        cutoff_time = time.time() - (minutes * 60)
        
        with self._lock:
            return [
                metric for metric in self._metrics_history[db_type]
                if metric.timestamp >= cutoff_time
            ]
    
    def get_performance_summary(self, db_type: str, minutes: int = 60) -> Dict[str, Any]:
        """Get performance summary for a database type."""
        history = self.get_metrics_history(db_type, minutes)
        
        if not history:
            return {"error": "No metrics available"}
        
        response_times = [m.response_time_ms for m in history]
        throughput = [m.throughput_ops_per_second for m in history]
        utilization = [
            m.active_connections / max(m.total_connections, 1) 
            for m in history
        ]
        
        return {
            "time_range_minutes": minutes,
            "data_points": len(history),
            "response_time": {
                "avg_ms": statistics.mean(response_times),
                "min_ms": min(response_times),
                "max_ms": max(response_times),
                "p95_ms": statistics.quantiles(response_times, n=20)[18] if len(response_times) > 20 else max(response_times)
            },
            "throughput": {
                "avg_ops_per_second": statistics.mean(throughput),
                "peak_ops_per_second": max(throughput)
            },
            "utilization": {
                "avg_percent": statistics.mean(utilization) * 100,
                "peak_percent": max(utilization) * 100
            },
            "current_pool_size": history[-1].total_connections if history else 0,
            "optimization_opportunities": self._identify_optimization_opportunities(db_type, history)
        }
    
    async def _monitoring_loop(self):
        """Main monitoring loop."""
        while self._monitoring_active:
            try:
                await self._collect_pool_metrics()
                
                if self.settings.enable_auto_tuning:
                    await self._auto_tune_pools()
                
                await asyncio.sleep(self.settings.optimization_interval_seconds)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(5)  # Brief pause before retrying
    
    async def _collect_pool_metrics(self):
        """Collect metrics from all connection pools."""
        try:
            from .connection_manager import get_connection_manager
            
            connection_manager = get_connection_manager()
            health_status = connection_manager.get_health_status()
            pool_stats = connection_manager.get_pool_stats()
            
            # Convert to our metrics format
            for db_type in ['mongodb', 'redis', 'qdrant']:
                if db_type in pool_stats:
                    stats = pool_stats[db_type]
                    health = health_status.get(db_type, {})
                    
                    metrics = ConnectionMetrics(
                        active_connections=stats.get('active_connections', 0),
                        idle_connections=stats.get('idle_connections', 0),
                        total_connections=stats.get('total_connections', 0),
                        failed_connections=stats.get('failed_connections', 0),
                        response_time_ms=health.get('response_time_ms', 0.0),
                        errors_per_minute=self._calculate_error_rate(db_type),
                        throughput_ops_per_second=self._calculate_throughput(db_type)
                    )
                    
                    self.record_metrics(db_type, metrics)
        
        except Exception as e:
            logger.error(f"Failed to collect pool metrics: {e}")
    
    async def _auto_tune_pools(self):
        """Automatically tune connection pool sizes based on metrics."""
        for db_type in ['mongodb', 'redis', 'qdrant']:
            try:
                await self._tune_pool_size(db_type)
            except Exception as e:
                logger.error(f"Failed to tune {db_type} pool: {e}")
    
    async def _tune_pool_size(self, db_type: str):
        """Tune the pool size for a specific database type."""
        current_metrics = self._current_metrics.get(db_type)
        if not current_metrics:
            return
        
        # Calculate current utilization
        utilization = (
            current_metrics.active_connections / 
            max(current_metrics.total_connections, 1)
        )
        
        # Get recent performance data
        recent_metrics = self.get_metrics_history(db_type, minutes=5)
        if len(recent_metrics) < 5:
            return  # Need more data
        
        avg_response_time = statistics.mean([m.response_time_ms for m in recent_metrics])
        baseline_response_time = self._performance_baselines[db_type]['response_time_ms']
        
        # Decision logic for scaling
        should_scale_up = (
            utilization > self.settings.scale_up_threshold or
            avg_response_time > baseline_response_time * 2
        )
        
        should_scale_down = (
            utilization < self.settings.scale_down_threshold and
            avg_response_time < baseline_response_time * 1.5 and
            current_metrics.total_connections > self.settings.min_pool_size
        )
        
        if should_scale_up and current_metrics.total_connections < self.settings.max_pool_size:
            new_size = min(
                current_metrics.total_connections + 5,
                self.settings.max_pool_size
            )
            logger.info(f"Auto-tuning: Scaling up {db_type} pool to {new_size} connections")
            # Note: Actual pool scaling would require integration with specific database clients
            
        elif should_scale_down:
            new_size = max(
                current_metrics.total_connections - 2,
                self.settings.min_pool_size
            )
            logger.info(f"Auto-tuning: Scaling down {db_type} pool to {new_size} connections")
            # Note: Actual pool scaling would require integration with specific database clients
    
    def _calculate_error_rate(self, db_type: str) -> float:
        """Calculate error rate for the last minute."""
        recent_metrics = self.get_metrics_history(db_type, minutes=1)
        if len(recent_metrics) < 2:
            return 0.0
        
        # Simple error rate calculation
        total_failed = sum(m.failed_connections for m in recent_metrics)
        return total_failed
    
    def _calculate_throughput(self, db_type: str) -> float:
        """Estimate throughput based on active connections and response time."""
        current_metrics = self._current_metrics.get(db_type)
        if not current_metrics or current_metrics.response_time_ms == 0:
            return 0.0
        
        # Rough estimate: throughput = active_connections / (response_time_seconds)
        response_time_seconds = current_metrics.response_time_ms / 1000.0
        estimated_throughput = current_metrics.active_connections / max(response_time_seconds, 0.001)
        
        return estimated_throughput
    
    def _check_performance_anomalies(self, db_type: str, metrics: ConnectionMetrics):
        """Check for performance anomalies and log warnings."""
        baseline = self._performance_baselines[db_type]
        
        # Check response time anomaly
        if metrics.response_time_ms > baseline['response_time_ms'] * 5:
            logger.warning(
                f"Performance anomaly detected in {db_type}: "
                f"Response time {metrics.response_time_ms:.1f}ms is much higher than baseline "
                f"{baseline['response_time_ms']:.1f}ms"
            )
        
        # Check connection pool exhaustion
        utilization = metrics.active_connections / max(metrics.total_connections, 1)
        if utilization > 0.95:
            logger.warning(
                f"Connection pool near exhaustion for {db_type}: "
                f"{metrics.active_connections}/{metrics.total_connections} connections in use"
            )
    
    def _identify_optimization_opportunities(self, db_type: str, history: List[ConnectionMetrics]) -> List[str]:
        """Identify optimization opportunities based on metrics history."""
        opportunities = []
        
        if not history:
            return opportunities
        
        # Check for consistently high utilization
        avg_utilization = statistics.mean([
            m.active_connections / max(m.total_connections, 1) for m in history
        ])
        if avg_utilization > 0.8:
            opportunities.append(f"Pool size increase recommended (utilization: {avg_utilization:.1%})")
        
        # Check for consistently high response times
        avg_response_time = statistics.mean([m.response_time_ms for m in history])
        baseline_response_time = self._performance_baselines[db_type]['response_time_ms']
        if avg_response_time > baseline_response_time * 2:
            opportunities.append(f"Performance optimization needed (avg response: {avg_response_time:.1f}ms)")
        
        # Check for low utilization
        if avg_utilization < 0.2 and history[-1].total_connections > self.settings.min_pool_size:
            opportunities.append(f"Pool size reduction possible (utilization: {avg_utilization:.1%})")
        
        return opportunities


# Global monitor instance
_pool_monitor: Optional[ConnectionPoolMonitor] = None


def get_connection_pool_monitor() -> ConnectionPoolMonitor:
    """Get or create the connection pool monitor instance."""
    global _pool_monitor
    
    if _pool_monitor is None:
        _pool_monitor = ConnectionPoolMonitor()
        logger.info("Connection pool monitor initialized")
    
    return _pool_monitor