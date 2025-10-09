"""
Observation-related Pydantic models for KATO API
"""

from typing import Any, Optional

from pydantic import BaseModel, Field


class ObservationData(BaseModel):
    """Input data for observations"""
    strings: list[str] = Field(default_factory=list, description="String symbols to observe")
    vectors: list[list[float]] = Field(default_factory=list, description="Vector embeddings")
    emotives: dict[str, float] = Field(default_factory=dict, description="Emotional values")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Pattern metadata (stored as unique string lists)")


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
    stm: list[list[str]] = Field(..., description="Current STM state")
    session_id: Optional[str] = Field(None, description="Session ID")
    length: Optional[int] = Field(None, description="Number of events in STM")


class ObservationDataItem(ObservationData):
    unique_id: Optional[str] = None

class ObservationSequenceRequest(BaseModel):
    """Request for processing multiple observations in sequence"""
    observations: list[ObservationDataItem] = Field(..., description="List of observations to process")
    learn_after_each: bool = Field(default=False, description="Whether to learn after each observation")
    learn_at_end: bool = Field(default=False, description="Whether to learn from final STM state")
    clear_stm_between: bool = Field(default=False, description="Whether to clear STM between each observation")




class ObservationSequenceResult(BaseModel):
    """Result of processing an observation sequence"""
    status: str = Field(..., description="Status of the sequence operation")
    processor_id: str = Field(..., description="Processor ID that handled the sequence")
    observations_processed: int = Field(..., description="Number of observations processed")
    initial_stm_length: int = Field(..., description="STM length before processing")
    final_stm_length: int = Field(..., description="STM length after processing")
    results: list[dict[str, Any]] = Field(..., description="Individual observation results")
    auto_learned_patterns: list[str] = Field(default_factory=list, description="Patterns learned during auto-learning")
    final_learned_pattern: Optional[str] = Field(None, description="Pattern learned from final STM state")
    isolated: bool = Field(..., description="Whether isolation was used")
