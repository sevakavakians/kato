"""
Session-related Pydantic models for KATO API
"""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


class CreateSessionRequest(BaseModel):
    """Request to create a new session"""
    node_id: str = Field(..., description="Node identifier (required for processor isolation)")
    metadata: Optional[dict[str, Any]] = Field(default_factory=dict, description="Session metadata")
    ttl_seconds: Optional[int] = Field(None, description="Session TTL in seconds (uses default if not specified)")
    config: Optional[dict[str, Any]] = Field(None, description="Initial session configuration (optional)")


class SessionResponse(BaseModel):
    """Session creation/info response"""
    session_id: str = Field(..., description="Unique session identifier")
    node_id: str = Field(..., description="Associated node ID")
    created_at: datetime = Field(..., description="Session creation time")
    expires_at: datetime = Field(..., description="Session expiration time")
    ttl_seconds: int = Field(..., description="Session TTL in seconds")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Session metadata")
    session_config: dict[str, Any] = Field(default_factory=dict, description="Session configuration")


class PatternBatchRequest(BaseModel):
    """Bounded batch of pattern IDs, with or without the PTRN| prefix."""
    pattern_ids: list[str] = Field(..., min_length=1, max_length=1000)

    @field_validator('pattern_ids')
    @classmethod
    def validate_pattern_ids(cls, pattern_ids: list[str]) -> list[str]:
        if any(not value.strip() or value.strip() == 'PTRN|' for value in pattern_ids):
            raise ValueError('pattern IDs cannot be empty')
        return pattern_ids


class RetirePatternsResponse(BaseModel):
    status: str
    session_id: str
    node_id: str
    requested: int
    retired: list[str] = Field(default_factory=list)
    already_retired: list[str] = Field(default_factory=list)


class PurgeRetiredPatternsResponse(BaseModel):
    status: str
    session_id: str
    node_id: str
    requested: int
    purged: list[str] = Field(default_factory=list)
    already_purged: list[str] = Field(default_factory=list)
    skipped_not_retired: list[str] = Field(default_factory=list)
    failed: dict[str, str] = Field(default_factory=dict)
    prediction_records_updated: int = 0
    precomputed_metrics_deleted: int = 0
    tombstones_retained: bool = True
