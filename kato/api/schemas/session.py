"""
Session-related Pydantic models for KATO API
"""

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class CreateSessionRequest(BaseModel):
    """Request to create a new session"""
    node_id: str = Field(..., description="Node identifier (required for processor isolation)")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Session metadata")
    ttl_seconds: Optional[int] = Field(None, description="Session TTL in seconds (uses default if not specified)")


class SessionResponse(BaseModel):
    """Session creation/info response"""
    session_id: str = Field(..., description="Unique session identifier")
    node_id: str = Field(..., description="Associated node ID")
    created_at: datetime = Field(..., description="Session creation time")
    expires_at: datetime = Field(..., description="Session expiration time")
    ttl_seconds: int = Field(..., description="Session TTL in seconds")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Session metadata")
    session_config: Dict[str, Any] = Field(default_factory=dict, description="Session configuration")
