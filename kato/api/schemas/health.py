"""Health and status endpoint response models."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class StatusResponse(BaseModel):
    status: str
    base_processor_id: str
    uptime_seconds: float
    sessions: Dict[str, Any]
    processors: Dict[str, Any]
    version: str


class HealthResponse(BaseModel):
    status: str
    processor_status: str
    service_name: str
    uptime_seconds: float
    issues: List[str]
    metrics_collected: int
    last_collection: float
    active_sessions: int
    timestamp: str
