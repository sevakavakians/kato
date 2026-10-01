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
    """A bounded batch of pattern IDs, accepted with or without the PTRN| prefix.

    Validation is strict here rather than deeper in the stack. The storage layer
    requires a 40-character lowercase SHA1 before a name can reach statement text,
    and a retirement is a durable tombstone: an unvalidated id becomes a permanent
    entry naming a pattern that cannot exist, which nothing would ever match and
    which would otherwise be indistinguishable from a real retirement. Rejecting
    at the edge turns that into a 422 the caller can act on.
    """
    pattern_ids: list[str] = Field(..., min_length=1, max_length=1000)

    @field_validator('pattern_ids')
    @classmethod
    def validate_pattern_ids(cls, pattern_ids: list[str]) -> list[str]:
        from kato.storage.identifiers import is_valid_pattern_name

        cleaned: list[str] = []
        invalid: list[str] = []
        for value in pattern_ids:
            if not isinstance(value, str):
                invalid.append(repr(value))
                continue
            candidate = value.strip()
            bare = candidate[5:] if candidate.startswith('PTRN|') else candidate
            if not is_valid_pattern_name(bare):
                invalid.append(value)
                continue
            # Store the stripped form: whitespace would otherwise be preserved in
            # the tombstone and never match the pattern it was meant to name.
            cleaned.append(candidate)

        if invalid:
            shown = ', '.join(repr(v) for v in invalid[:5])
            more = f" (and {len(invalid) - 5} more)" if len(invalid) > 5 else ""
            raise ValueError(
                f"pattern IDs must be a 40-character SHA1 hex digest, optionally "
                f"prefixed with 'PTRN|'. Rejected: {shown}{more}"
            )
        return cleaned


class RetirePatternsResponse(BaseModel):
    """Result of retiring a batch.

    retired and already_retired are reported separately so a caller can tell a
    change from a no-op; retirement is idempotent.
    """
    status: str
    session_id: str
    node_id: str
    requested: int
    retired: list[str] = Field(default_factory=list)
    already_retired: list[str] = Field(default_factory=list)


class UnRetirePatternsResponse(BaseModel):
    """Result of removing tombstones."""
    status: str
    session_id: str
    node_id: str
    requested: int
    un_retired: list[str] = Field(default_factory=list)
    not_retired: list[str] = Field(default_factory=list)
