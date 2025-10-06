"""
KATO Middleware Components

Middleware for request processing, session management, and backward compatibility.
"""

from .auto_session import AutoSessionMiddleware

__all__ = ['AutoSessionMiddleware']
