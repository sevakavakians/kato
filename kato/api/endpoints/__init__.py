"""
API Endpoints Module

Contains FastAPI route handlers organized by functionality.
"""

print("DEBUG: endpoints/__init__.py is being imported")

from .sessions import router as sessions_router
from .monitoring import router as monitoring_router
from .health import router as health_router

print("DEBUG: About to import kato_ops router")
from .kato_ops import router as kato_ops_router
print("DEBUG: kato_ops router imported successfully")

__all__ = [
    'sessions_router',
    'monitoring_router', 
    'health_router',
    'kato_ops_router'
]