"""
Session Middleware for FastAPI

This middleware handles session management for all requests,
enabling multi-user support with complete isolation.
"""

import logging
from typing import Optional
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse

from .session_manager import get_session_manager, SessionState

logger = logging.getLogger('kato.v2.sessions.middleware')


class SessionMiddleware:
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
        self.app = app
        self.auto_create = auto_create
        self.session_manager = get_session_manager()
    
    async def __call__(self, scope, receive, send):
        """ASGI3 middleware interface"""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        
        # For HTTP requests, we need to handle them specially
        # But for now, just pass through to the app
        await self.app(scope, receive, send)
        return
    
    async def process_request_old(self, request: Request, call_next):
        """Process request with session management"""
        
        # Extract session ID from header or cookie
        session_id = self._extract_session_id(request)
        
        # Handle v2 endpoints that require sessions
        if request.url.path.startswith('/v2/') and request.url.path != '/v2/sessions':
            if not session_id:
                if self.auto_create and request.method in ['POST', 'PUT']:
                    # Auto-create session for v2 endpoints
                    session = await self.session_manager.create_session()
                    session_id = session.session_id
                    logger.info(f"Auto-created session {session_id} for {request.url.path}")
                else:
                    # Session required but not provided
                    return JSONResponse(
                        status_code=400,
                        content={
                            "error": {
                                "code": "SESSION_REQUIRED",
                                "message": "Session ID required for v2 endpoints. Create a session first or provide X-Session-ID header."
                            }
                        }
                    )
        
        # Validate and attach session if provided
        if session_id:
            session = await self.session_manager.get_session(session_id)
            
            if not session and request.url.path.startswith('/v2/'):
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
        
        return response
    
    def _extract_session_id(self, request: Request) -> Optional[str]:
        """
        Extract session ID from request.
        
        Checks in order:
        1. X-Session-ID header
        2. session_id cookie
        3. session_id query parameter
        
        Args:
            request: FastAPI request
        
        Returns:
            Session ID if found, None otherwise
        """
        # Check header first (preferred)
        session_id = request.headers.get('X-Session-ID')
        if session_id:
            return session_id
        
        # Check cookie
        session_id = request.cookies.get('session_id')
        if session_id:
            return session_id
        
        # Check query parameter (least preferred)
        session_id = request.query_params.get('session_id')
        if session_id:
            return session_id
        
        return None


async def get_session(request: Request) -> SessionState:
    """
    FastAPI dependency to get session from request.
    
    Args:
        request: FastAPI request
    
    Returns:
        SessionState from request
    
    Raises:
        HTTPException: If session not found in request
    """
    if not hasattr(request.state, 'session'):
        raise HTTPException(
            status_code=400,
            detail="Session required for this endpoint"
        )
    
    return request.state.session


async def get_session_id(request: Request) -> str:
    """
    FastAPI dependency to get session ID from request.
    
    Args:
        request: FastAPI request
    
    Returns:
        Session ID from request
    
    Raises:
        HTTPException: If session ID not found in request
    """
    if not hasattr(request.state, 'session_id'):
        raise HTTPException(
            status_code=400,
            detail="Session ID required for this endpoint"
        )
    
    return request.state.session_id


async def get_optional_session(request: Request) -> Optional[SessionState]:
    """
    FastAPI dependency to get optional session from request.
    
    Args:
        request: FastAPI request
    
    Returns:
        SessionState if present, None otherwise
    """
    return getattr(request.state, 'session', None)


def mark_session_modified(request: Request):
    """
    Mark session as modified so it will be saved.
    
    Args:
        request: FastAPI request
    """
    request.state.session_modified = True