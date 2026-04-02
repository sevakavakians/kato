"""Root endpoint response model."""

from pydantic import BaseModel


class RootResponse(BaseModel):
    service: str
    version: str
    description: str
    docs: str
    health: str
    status: str
    uptime_seconds: float
    architecture: str
    session_support: bool
