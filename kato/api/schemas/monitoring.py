"""Monitoring endpoint response models."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class ConcurrencyResponse(BaseModel):
    status: str
    current: Dict[str, Any]
    peak: Dict[str, Any]
    limits: Dict[str, Any]
    configuration: Dict[str, Any]
    recommendations: List[Dict[str, str]]
    timestamp: str


class CacheStatsResponse(BaseModel):
    cache_performance: Dict[str, Any]
    cache_health: Dict[str, Any]
    timestamp: str


class CacheInvalidateResponse(BaseModel):
    status: str
    patterns_invalidated: Optional[int] = None
    symbols_invalidated: Optional[int] = None
    session_id: Optional[str] = None
    reason: Optional[str] = None
    timestamp: str


class DistributedSTMStatsResponse(BaseModel):
    status: str
    distributed_stm_enabled: Optional[bool] = None
    performance_stats: Optional[Dict[str, Any]] = None
    processor_info: Optional[Dict[str, Any]] = None
    expected_improvements: Optional[Dict[str, str]] = None
    reason: Optional[str] = None
    error: Optional[str] = None
    timestamp: str


class MetricsResponse(BaseModel):
    timestamp: float
    sessions: Optional[Dict[str, Any]] = None
    performance: Optional[Dict[str, Any]] = None
    resources: Optional[Dict[str, Any]] = None
    databases: Optional[Dict[str, Any]] = None
    rates: Optional[Dict[str, Any]] = None
    processor_manager: Optional[Dict[str, Any]] = None
    uptime_seconds: Optional[float] = None
    active_sessions: Optional[int] = None
    error: Optional[str] = None


class StatsResponse(BaseModel):
    time_range_minutes: int
    timestamp: float
    processor_manager: Optional[Dict[str, Any]] = None
    current_status: Optional[Dict[str, Any]] = None
    time_series: Optional[Dict[str, Any]] = None
    summary: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class MetricStatistics(BaseModel):
    count: int
    min: float
    max: float
    avg: float


class MetricHistoryResponse(BaseModel):
    metric_name: str
    time_range_minutes: int
    timestamp: float
    statistics: MetricStatistics
    data_points: List[Dict[str, Any]]


class ConnectionPoolsResponse(BaseModel):
    status: str
    health: Optional[Dict[str, Any]] = None
    pool_statistics: Optional[Dict[str, Any]] = None
    connection_optimization: Optional[Dict[str, Any]] = None
    performance_improvements: Optional[Dict[str, str]] = None
    error: Optional[str] = None
    timestamp: str
