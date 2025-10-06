"""
Simple Session Middleware for FastAPI

This middleware handles session management for all requests,
enabling multi-user support with complete isolation.
"""

import logging
from typing import Callable, Optional

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from .session_manager import SessionState

logger = logging.getLogger('kato.sessions.middleware')


class SessionMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware for session management.

    Handles:
    - Session extraction from headers
    - Session validation
    - Session attachment to request state
    """

    def __init__(self, app, auto_create: bool = False):
        """
        Initialize session middleware.

        Args:
            app: FastAPI application
            auto_create: Automatically create sessions for requests without one
        """
        super().__init__(app)
        self.auto_create = auto_create
        # Don't initialize session_manager here - let it be configured by the app
        self.session_manager = None

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with session management"""

        # Get session manager from app state if not set
        if self.session_manager is None:
            # Access the app state through the app instance
            from kato.services.kato_fastapi import app_state
            self.session_manager = app_state.session_manager

        path = str(request.url.path)
        session_id = None

        # For session-specific endpoints, extract session ID from path
        # BUT exclude GET /sessions/{session_id} which is for session info retrieval
        if path.startswith('/sessions/') and path != '/sessions':
            parts = path.split('/')
            if len(parts) >= 3 and parts[2]:
                session_id = parts[2]

                # Skip validation for GET session info endpoint - let the endpoint handle it
                if len(parts) == 3 and request.method == 'GET':
                    session_id = None  # Don't validate, let endpoint handle it
                else:
                    # Validate the session exists for session-scoped operations
                    session = await self.session_manager.get_session(session_id)
                    if not session:
                        return JSONResponse(
                            status_code=404,
                            content={
                                "error": {
                                    "code": "SESSION_NOT_FOUND",
                                    "message": f"Session {session_id} not found or expired",
                                    "session_id": session_id
                                }
                            }
                        )

                # Attach session to request state (only if session_id is set)
                if session_id:
                    request.state.session = session
                    request.state.session_id = session_id
                    request.state.session_lock = await self.session_manager.get_session_lock(session_id)
        else:
            # For other endpoints, check for session ID in headers
            session_id = self._extract_session_id(request)
            if session_id:
                session = await self.session_manager.get_session(session_id)
                if session:
                    request.state.session = session
                    request.state.session_id = session_id
                    request.state.session_lock = await self.session_manager.get_session_lock(session_id)

        # Process request
        response = await call_next(request)

        # Add session ID to response headers if we have one
        if session_id:
            response.headers['X-Session-ID'] = session_id

        # Update session if it was modified
        if hasattr(request.state, 'session') and hasattr(request.state, 'session_modified'):
            if request.state.session_modified:
                await self.session_manager.update_session(request.state.session)
                logger.debug(f"Updated modified session {session_id}")

        return response

    def _extract_session_id(self, request: Request) -> Optional[str]:
        """
        Extract session ID from request.

        Checks:
        1. X-Session-ID header
        2. session_id cookie

        Args:
            request: FastAPI request

        Returns:
            Session ID if found, None otherwise
        """
        # Check header
        session_id = request.headers.get('X-Session-ID')
        if session_id:
            return session_id

        # Check cookie
        session_id = request.cookies.get('session_id')
        if session_id:
            return session_id

        return None


# Dependency injection helpers for route handlers
async def get_session(request: Request) -> SessionState:
    """
    Get the current session from request state.

    Raises HTTPException if no session.
    """
    if not hasattr(request.state, 'session'):
        from fastapi import HTTPException
        raise HTTPException(
            status_code=400,
            detail="No session found. Create a session first or provide X-Session-ID header."
        )
    return request.state.session


async def get_optional_session(request: Request) -> Optional[SessionState]:
    """Get the current session from request state, or None if not present."""
    return getattr(request.state, 'session', None)


async def get_session_id(request: Request) -> str:
    """Get the current session ID from request state."""
    if not hasattr(request.state, 'session_id'):
        from fastapi import HTTPException
        raise HTTPException(
            status_code=400,
            detail="No session ID found"
        )
    return request.state.session_id


def mark_session_modified(request: Request):
    """Mark the session as modified so it will be saved."""
    request.state.session_modified = True
