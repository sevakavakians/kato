"""
Session Middleware for FastAPI v2.0

This middleware handles session management for all requests,
enabling multi-user support with complete isolation.
"""

import logging
from typing import Optional, Callable
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from .session_manager import get_session_manager, SessionState

logger = logging.getLogger('kato.sessions.middleware')


class SessionMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware for session management.
    
    Handles:
    - Session extraction from headers
    - Session validation
    - Automatic session creation for v2 endpoints
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
        self.session_manager = get_session_manager()
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with session management"""
        
        # Extract session ID from header or cookie
        session_id = self._extract_session_id(request)
        
        # Handle v2 endpoints that require sessions
        path = str(request.url.path)
        if path.startswith('/v2/sessions/') and path != '/v2/sessions':
            # Extract session ID from path for v2 session endpoints
            parts = path.split('/')
            if len(parts) >= 4:
                path_session_id = parts[3]
                if path_session_id:
                    session_id = path_session_id
        
        # Handle v2 endpoints that need session validation
        if path.startswith('/v2/') and path != '/v2/sessions' and path != '/v2/health' and path != '/v2/status':
            if not session_id and path.startswith('/v2/sessions/'):
                # Session ID should be in the path
                return JSONResponse(
                    status_code=400,
                    content={
                        "error": {
                            "code": "INVALID_SESSION_PATH",
                            "message": "Invalid session path format"
                        }
                    }
                )
            elif not session_id:
                if self.auto_create and request.method in ['POST', 'PUT']:
                    # Auto-create session for v2 endpoints
                    session = await self.session_manager.create_session()
                    session_id = session.session_id
                    logger.info(f"Auto-created session {session_id} for {path}")
                # For non-session endpoints, we don't require a session
        
        # Validate and attach session if provided
        if session_id:
            # For session-specific endpoints, validate the session exists
            if path.startswith('/v2/sessions/') and path != '/v2/sessions':
                session = await self.session_manager.get_session(session_id)
                
                if not session:
                    # Session not found or expired
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
                
                # Attach session to request state
                request.state.session = session
                request.state.session_id = session_id
                request.state.session_lock = await self.session_manager.get_session_lock(session_id)
            else:
                # For backward compatibility endpoints with X-Session-ID header
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
        3. Path parameter for /v2/sessions/{session_id}/* endpoints
        
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