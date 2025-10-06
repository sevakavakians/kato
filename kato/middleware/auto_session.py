"""
Auto-Session Middleware for Backward Compatibility

Automatically creates sessions for deprecated direct endpoint calls,
providing transparent backward compatibility while tracking usage metrics.

Phase 2 of API Endpoint Deprecation project.
"""

import logging
import os
from typing import Optional
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

logger = logging.getLogger('kato.middleware.auto_session')


class AutoSessionMiddleware(BaseHTTPMiddleware):
    """
    Middleware to automatically create sessions for deprecated direct endpoint calls.

    This middleware intercepts requests to deprecated endpoints (e.g., /observe?processor_id=X)
    and transparently converts them to session-based endpoints (e.g., /sessions/{session_id}/observe).

    Workflow:
    1. Detect deprecated endpoint request
    2. Extract processor_id from query params or X-Node-ID header
    3. Check Redis for existing processor_id → session_id mapping
    4. Create session if no mapping exists
    5. Rewrite request path to session-based endpoint
    6. Add X-Auto-Session-Created header for tracking
    7. Increment deprecation metrics
    """

    # Mapping of deprecated endpoints to their session-based equivalents
    ENDPOINT_MAPPINGS = {
        '/observe': '/sessions/{session_id}/observe',
        '/stm': '/sessions/{session_id}/stm',
        '/short-term-memory': '/sessions/{session_id}/stm',
        '/learn': '/sessions/{session_id}/learn',
        '/clear-stm': '/sessions/{session_id}/clear-stm',
        '/clear-short-term-memory': '/sessions/{session_id}/clear-stm',
        '/predictions': '/sessions/{session_id}/predictions',
        '/observe-sequence': '/sessions/{session_id}/observe-sequence',
    }

    def __init__(self, app, session_manager, metrics_collector=None, enabled: bool = True):
        """
        Initialize Auto-Session Middleware.

        Args:
            app: FastAPI application
            session_manager: Session manager instance (for creating sessions)
            metrics_collector: Optional metrics collector for tracking
            enabled: Enable/disable middleware (default: True)
        """
        super().__init__(app)
        self.session_manager = session_manager
        self.metrics_collector = metrics_collector
        self.enabled = enabled
        self.redis_key_prefix = "kato:auto_session:processor:"

        logger.info(f"AutoSessionMiddleware initialized (enabled={enabled})")

    async def dispatch(self, request: Request, call_next):
        """
        Process request and convert deprecated endpoints to session-based.

        Args:
            request: Incoming request
            call_next: Next middleware/handler in chain

        Returns:
            Response from handler
        """
        # Skip if middleware disabled
        if not self.enabled:
            return await call_next(request)

        # Check if this is a deprecated endpoint
        path = request.url.path

        if path not in self.ENDPOINT_MAPPINGS:
            # Not a deprecated endpoint, pass through
            return await call_next(request)

        # This is a deprecated endpoint - handle auto-session creation
        try:
            # Extract processor_id
            processor_id = await self._extract_processor_id(request)

            if not processor_id:
                logger.warning(f"Deprecated endpoint {path} called without processor_id")
                # Let the endpoint handle this (will fail with appropriate error)
                return await call_next(request)

            # Get or create session for this processor_id
            session_id = await self._get_or_create_session(processor_id)

            if not session_id:
                logger.error(f"Failed to create auto-session for processor_id={processor_id}")
                # Let the endpoint handle this (will fail appropriately)
                return await call_next(request)

            # Rewrite request to session-based endpoint
            new_path = self.ENDPOINT_MAPPINGS[path].format(session_id=session_id)

            # Modify the request scope in place
            request.scope['path'] = new_path

            # Remove processor_id from query params
            query_params = dict(request.query_params)
            auto_session_created = False

            if 'processor_id' in query_params:
                del query_params['processor_id']
                auto_session_created = True

            # Rebuild query string
            request.scope['query_string'] = urlencode(query_params).encode()

            # Add headers to track auto-session creation
            # Note: Headers are tuples, so we need to create a new list
            headers = list(request.scope.get('headers', []))
            headers.append((b'x-auto-session-created', b'true'))
            headers.append((b'x-original-path', path.encode()))
            headers.append((b'x-processor-id', processor_id.encode()))
            request.scope['headers'] = headers

            # Increment metrics
            if self.metrics_collector:
                self.metrics_collector.increment(
                    'kato_deprecated_endpoint_calls_total',
                    labels={'endpoint': path, 'method': request.method}
                )

                if auto_session_created:
                    self.metrics_collector.increment(
                        'kato_auto_session_created_total',
                        labels={'endpoint': path}
                    )

            logger.info(
                f"Auto-session: {path} → {new_path} "
                f"(processor_id={processor_id}, session_id={session_id})"
            )

            # Process the request with modified scope
            response = await call_next(request)

            # Add headers to response for debugging
            response.headers['X-Auto-Session-Used'] = 'true'
            response.headers['X-Session-ID'] = session_id

            return response

        except Exception as e:
            logger.error(f"Error in auto-session middleware for {path}: {e}", exc_info=True)
            # On error, pass through to original endpoint
            return await call_next(request)

    async def _extract_processor_id(self, request: Request) -> Optional[str]:
        """
        Extract processor_id from request query params or headers.

        Args:
            request: Incoming request

        Returns:
            processor_id if found, None otherwise
        """
        # Try query parameter first
        processor_id = request.query_params.get('processor_id')
        if processor_id:
            return processor_id

        # Try X-Node-ID header (legacy support)
        processor_id = request.headers.get('x-node-id')
        if processor_id:
            return processor_id

        # Try X-Test-ID header (for tests)
        test_id = request.headers.get('x-test-id')
        if test_id:
            return test_id if test_id.startswith('test_') else f'test_{test_id}'

        return None

    async def _get_or_create_session(self, processor_id: str) -> Optional[str]:
        """
        Get existing session for processor_id or create new one.

        Uses Redis to store processor_id → session_id mapping with TTL.

        Args:
            processor_id: Processor identifier

        Returns:
            session_id if successful, None on error
        """
        try:
            # Check if session manager has Redis client
            if not hasattr(self.session_manager, 'redis_client'):
                logger.error("Session manager does not have Redis client")
                return None

            redis_client = self.session_manager.redis_client

            # Check Redis for existing mapping
            mapping_key = f"{self.redis_key_prefix}{processor_id}"
            session_id = await redis_client.get(mapping_key)

            if session_id:
                # Verify session still exists
                session = await self.session_manager.get_session(session_id)
                if session and not session.is_expired():
                    logger.debug(f"Reusing existing session {session_id} for processor {processor_id}")
                    return session_id
                else:
                    # Session expired or deleted, clean up mapping
                    await redis_client.delete(mapping_key)
                    logger.debug(f"Cleaned up expired session mapping for processor {processor_id}")

            # Create new session for this processor_id
            # Use processor_id as node_id to maintain database isolation
            session = await self.session_manager.create_session(
                node_id=processor_id,
                metadata={'auto_created': True, 'source': 'auto_session_middleware'}
            )

            session_id = session.session_id

            # Store mapping in Redis with TTL matching session TTL
            ttl = self.session_manager.default_ttl
            await redis_client.setex(mapping_key, ttl, session_id)

            logger.info(
                f"Created auto-session {session_id} for processor {processor_id} "
                f"(TTL={ttl}s)"
            )

            # Increment auto-session creation metric
            if self.metrics_collector:
                self.metrics_collector.increment('kato_auto_session_created_total')

            return session_id

        except Exception as e:
            logger.error(f"Error getting/creating session for processor {processor_id}: {e}", exc_info=True)
            return None
