"""
API Endpoints Module

Contains FastAPI route handlers organized by functionality.
"""

from .health import router as health_router
from .kato_ops import router as kato_ops_router
from .monitoring import router as monitoring_router
from .sessions import router as sessions_router
from .websocket_events import router as websocket_events_router

__all__ = [
    'sessions_router',
    'monitoring_router',
    'health_router',
    'kato_ops_router',
    'websocket_events_router'
]
