"""
Prediction-related Pydantic models for KATO API
"""

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class LearnResult(BaseModel):
    """Result of learning operation"""
    status: str = Field(..., description="Status of the learning operation (learned/insufficient_data)")
    pattern_name: str = Field(..., description="Name of the learned pattern (empty if not learned)")
    session_id: Optional[str] = Field(None, description="Session ID")
    processor_id: Optional[str] = Field(None, description="Processor ID for v1 compatibility")
    message: Optional[str] = Field(None, description="Human-readable message")


class PredictionsResponse(BaseModel):
    """Predictions response"""
    predictions: List[Dict] = Field(default_factory=list, description="List of predictions")
    future_potentials: Optional[List[Dict]] = Field(None, description="Aggregated future potentials")
    session_id: Optional[str] = Field(None, description="Session ID")
    processor_id: Optional[str] = Field(None, description="Processor ID for v1 compatibility")
    count: int = Field(..., description="Number of predictions")
    time: Optional[int] = Field(None, description="Time counter")
    unique_id: Optional[str] = Field(None, description="Unique ID if provided")
