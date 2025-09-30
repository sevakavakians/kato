"""
Observation-related Pydantic models for KATO API
"""

from typing import List, Optional, Dict
from pydantic import BaseModel, Field


class ObservationData(BaseModel):
    """Input data for observations"""
    strings: List[str] = Field(default_factory=list, description="String symbols to observe")
    vectors: List[List[float]] = Field(default_factory=list, description="Vector embeddings")
    emotives: Dict[str, float] = Field(default_factory=dict, description="Emotional values")


class ObservationResult(BaseModel):
    """Result of an observation"""
    status: str = Field(..., description="Status of the operation")
    session_id: Optional[str] = Field(None, description="Session ID")
    processor_id: Optional[str] = Field(None, description="Processor ID for v1 compatibility")
    stm_length: Optional[int] = Field(None, description="Current STM length")
    time: int = Field(..., description="Session time counter")
    unique_id: Optional[str] = Field(None, description="Unique observation ID")
    auto_learned_pattern: Optional[str] = Field(None, description="Auto-learned pattern name if any")


class STMResponse(BaseModel):
    """Short-term memory response"""
    stm: List[List[str]] = Field(..., description="Current STM state")
    session_id: Optional[str] = Field(None, description="Session ID")
    length: Optional[int] = Field(None, description="Number of events in STM")