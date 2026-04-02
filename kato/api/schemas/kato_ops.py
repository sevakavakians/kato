"""KATO operations endpoint response models."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class PatternResponse(BaseModel):
    pattern: Any
    node_id: str


class DeprecatedPerceptDataResponse(BaseModel):
    percept_data: Dict[str, Any]
    node_id: str
    warning: str


class DeprecatedCognitionDataResponse(BaseModel):
    cognition_data: Dict[str, Any]
    node_id: str
    warning: str


class SymbolAffinitiesResponse(BaseModel):
    affinities: Dict[str, Any]
    node_id: str


class SymbolStatsResponse(BaseModel):
    symbols: Dict[str, Any]
    node_id: str


class SymbolAffinityResponse(BaseModel):
    symbol: str
    affinity: Any
    node_id: str
