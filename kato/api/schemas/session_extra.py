"""Additional session endpoint response models for endpoints without existing schemas."""

from typing import Any, Dict, Optional

from pydantic import BaseModel


class TestResponse(BaseModel):
    test_id: str
    message: str


class SessionCountResponse(BaseModel):
    active_session_count: int


class SessionExistsResponse(BaseModel):
    exists: bool
    expired: bool
    session_id: str


class SessionDeletedResponse(BaseModel):
    status: str
    session_id: str


class SessionConfigResponse(BaseModel):
    session_id: str
    config: Dict[str, Any]


class SessionConfigUpdateResponse(BaseModel):
    status: str
    message: str
    session_id: str


class SessionExtendResponse(BaseModel):
    status: str
    session_id: str
    ttl_seconds: int


class STMClearedResponse(BaseModel):
    status: str
    session_id: str


class AllClearedResponse(BaseModel):
    status: str
    session_id: str
    scope: str


class PerceptDataResponse(BaseModel):
    percept_data: Dict[str, Any]
    session_id: str
    node_id: str


class CognitionDataResponse(BaseModel):
    cognition_data: Dict[str, Any]
    session_id: str
    node_id: str
