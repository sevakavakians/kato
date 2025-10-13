"""
KATO FastAPI Service with Session Management - Refactored Version

This service provides multi-user support with complete session isolation.
Each user maintains their own STM without any data collision.

Refactored to use modular endpoint structure for better maintainability.
"""

import logging
import os

# Import v2 components
import sys
import time
from typing import Optional

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

# Import modular API endpoints
from kato.api.endpoints import health_router, kato_ops_router, monitoring_router, sessions_router, websocket_events_router
from kato.config.configuration_service import get_configuration_service
from kato.config.settings import get_settings
from kato.exceptions.handlers import setup_error_handlers
from kato.monitoring.metrics import get_metrics_collector
from kato.processors.processor_manager import ProcessorManager
from kato.sessions.redis_session_manager import get_redis_session_manager
from kato.sessions.session_manager import get_session_manager
from kato.sessions.session_middleware_simple import SessionMiddleware
from kato.config.logging_config import generate_trace_id, trace_context

# Standard logger configuration
logger = logging.getLogger('kato.fastapi')

# ============================================================================
# FastAPI Application Setup
# ============================================================================

app = FastAPI(
    title="KATO API",
    description="Knowledge Abstraction for Traceable Outcomes with Multi-User Support",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add session middleware
app.add_middleware(SessionMiddleware, auto_create=False)

# Concurrency monitoring
import asyncio
from contextvars import ContextVar

# Track concurrent requests per worker
_concurrent_requests = ContextVar('concurrent_requests', default=0)
_concurrent_count = 0
_concurrent_lock = asyncio.Lock()
_max_concurrent_seen = 0

# Configuration from uvicorn CMD (--limit-concurrency 100)
CONCURRENCY_LIMIT = int(os.getenv('UVICORN_LIMIT_CONCURRENCY', '100'))
CONCURRENCY_WARNING_THRESHOLD = int(CONCURRENCY_LIMIT * 0.8)  # Warn at 80%
CONCURRENCY_CRITICAL_THRESHOLD = int(CONCURRENCY_LIMIT * 0.95)  # Critical at 95%

@app.middleware("http")
async def concurrency_monitor_middleware(request: Request, call_next):
    """
    Monitor concurrent requests and log warnings when approaching limits.

    This helps diagnose connection pool exhaustion and uvicorn overload.
    """
    global _concurrent_count, _max_concurrent_seen

    async with _concurrent_lock:
        _concurrent_count += 1
        current_count = _concurrent_count

        # Track maximum concurrent requests seen
        if current_count > _max_concurrent_seen:
            _max_concurrent_seen = current_count
            if current_count >= CONCURRENCY_CRITICAL_THRESHOLD:
                logger.error(
                    f"🚨 CRITICAL: Concurrent requests ({current_count}) >= {CONCURRENCY_CRITICAL_THRESHOLD} "
                    f"({CONCURRENCY_CRITICAL_THRESHOLD}/{CONCURRENCY_LIMIT} = 95% of limit). "
                    f"Requests may be dropped! Consider increasing --limit-concurrency or --workers."
                )
            elif current_count >= CONCURRENCY_WARNING_THRESHOLD:
                logger.warning(
                    f"⚠️  WARNING: High concurrent requests: {current_count}/{CONCURRENCY_LIMIT} "
                    f"({int(current_count/CONCURRENCY_LIMIT*100)}%). "
                    f"Approaching uvicorn --limit-concurrency limit."
                )

    try:
        # Process request
        response = await call_next(request)
        return response
    finally:
        # Decrement counter
        async with _concurrent_lock:
            _concurrent_count -= 1

# Add metrics collection middleware
@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    """Middleware to collect request metrics"""
    start_time = time.time()

    try:
        # Process request
        response = await call_next(request)

        # Record metrics if collector is available
        if hasattr(app_state, 'metrics_collector') and app_state.metrics_collector:
            try:
                duration_seconds = time.time() - start_time
                app_state.metrics_collector.record_request(
                    path=request.url.path,
                    method=request.method,
                    status_code=response.status_code,
                    duration=duration_seconds
                )
            except Exception as e:
                # Don't let metrics recording break the request
                logger.warning(f"Failed to record request metrics: {e}")

        return response

    except Exception as e:
        # Record error metrics if collector is available
        if hasattr(app_state, 'metrics_collector') and app_state.metrics_collector:
            try:
                duration_seconds = time.time() - start_time
                app_state.metrics_collector.record_request(
                    endpoint=request.url.path,
                    method=request.method,
                    status_code=500,  # Default error status
                    duration=duration_seconds,
                    error=str(e)
                )
            except Exception as metrics_error:
                # Don't let metrics recording break the request
                logger.warning(f"Failed to record error metrics: {metrics_error}")

        # Re-raise the original exception
        raise


# Add trace ID middleware
@app.middleware("http")
async def trace_middleware(request: Request, call_next):
    """Middleware to handle trace ID generation and header management"""
    # Get or generate trace ID
    trace_id = request.headers.get('X-Trace-ID', generate_trace_id())

    # Set trace context for the request
    with trace_context(trace_id):
        response = await call_next(request)

        # Add trace ID to response headers for debugging
        response.headers['X-Trace-ID'] = trace_id

        return response


# ============================================================================
# Application State Management
# ============================================================================

class AppState:
    """Application state container"""
    def __init__(self):
        self.processor_manager: Optional[ProcessorManager] = None
        self.settings = get_settings()
        self.config_service = get_configuration_service(self.settings)
        self.startup_time = time.time()
        self._session_manager = None

    @property
    def session_manager(self):
        """Get session manager singleton"""
        if self._session_manager is None:
            import traceback
            logger.debug(f"AppState.session_manager creating new instance (id: {id(self)})")
            logger.debug(f"Call stack:\n{''.join(traceback.format_stack()[-5:])}")
            # Use Redis session manager if Redis is configured
            redis_url = os.environ.get('REDIS_URL')
            if redis_url:
                logger.info(f"Using Redis session manager with URL: {redis_url}")
                self._session_manager = get_redis_session_manager(redis_url=redis_url)
            else:
                logger.info("Using in-memory session manager")
                self._session_manager = get_session_manager()
        else:
            logger.debug(f"AppState.session_manager returning cached instance (id: {id(self)})")
        return self._session_manager


app_state = AppState()


@app.on_event("startup")
async def startup_event():
    """Initialize application on startup"""
    logger.info("Starting KATO FastAPI service...")

    # Log uvicorn configuration for debugging concurrency issues
    logger.info("=" * 80)
    logger.info("UVICORN CONFIGURATION")
    logger.info("=" * 80)
    logger.info(f"Workers: {os.getenv('UVICORN_WORKERS', 'Not set (default: 1)')}")
    logger.info(f"Limit Concurrency: {CONCURRENCY_LIMIT} per worker")
    logger.info(f"  → Warning threshold: {CONCURRENCY_WARNING_THRESHOLD} concurrent requests (80%)")
    logger.info(f"  → Critical threshold: {CONCURRENCY_CRITICAL_THRESHOLD} concurrent requests (95%)")
    logger.info(f"Limit Max Requests: {os.getenv('UVICORN_LIMIT_MAX_REQUESTS', 'Not set (default: unlimited)')}")
    logger.info(f"Timeout Keep-Alive: {os.getenv('UVICORN_TIMEOUT_KEEP_ALIVE', 'Not set (default: 5s)')}")
    logger.info(f"Backlog: {os.getenv('UVICORN_BACKLOG', 'Not set (default: 2048)')}")
    logger.info(f"")
    logger.info(f"CAPACITY ESTIMATES (per worker):")
    logger.info(f"  → Safe concurrent: {CONCURRENCY_WARNING_THRESHOLD} requests")
    logger.info(f"  → Total with {os.getenv('UVICORN_WORKERS', '1')} workers: {CONCURRENCY_WARNING_THRESHOLD * int(os.getenv('UVICORN_WORKERS', '1'))} concurrent")
    logger.info("=" * 80)

    # Initialize Redis session manager if using Redis
    if hasattr(app_state.session_manager, 'initialize'):
        await app_state.session_manager.initialize()
        logger.info("Redis session manager initialized")

    # Initialize ProcessorManager for per-user isolation
    settings = app_state.settings
    # Use service name instead of processor_id
    service_name = os.environ.get('SERVICE_NAME', 'kato')
    app_state.processor_manager = ProcessorManager(
        base_processor_id=service_name,
        max_processors=100,
        eviction_ttl_seconds=settings.session.session_ttl
    )

    # Initialize v2 monitoring
    metrics_collector = get_metrics_collector()
    app_state.metrics_collector = metrics_collector
    await metrics_collector.start_collection()

    # Start concurrency monitoring task
    asyncio.create_task(_concurrency_reporter())

    # Setup error handlers
    setup_error_handlers(app)

    logger.info("KATO FastAPI service started successfully")


async def _concurrency_reporter():
    """Periodically report max concurrency for capacity planning"""
    global _max_concurrent_seen
    last_reported = 0

    while True:
        await asyncio.sleep(60)  # Report every minute
        if _max_concurrent_seen > last_reported:
            utilization = int(_max_concurrent_seen / CONCURRENCY_LIMIT * 100)
            logger.info(
                f"📊 Concurrency Stats: Peak {_max_concurrent_seen} concurrent requests "
                f"({utilization}% of limit) in last minute"
            )
            last_reported = _max_concurrent_seen


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("Shutting down KATO FastAPI service...")

    # Stop metrics collection
    if hasattr(app_state, 'metrics_collector') and app_state.metrics_collector:
        try:
            await app_state.metrics_collector.stop_collection()
            logger.info("Metrics collection stopped")
        except Exception as e:
            logger.error(f"Error stopping metrics collection: {e}")

    # Close session manager if needed
    if hasattr(app_state.session_manager, 'close'):
        try:
            await app_state.session_manager.close()
            logger.info("Session manager closed")
        except Exception as e:
            logger.error(f"Error closing session manager: {e}")

    logger.info("KATO FastAPI service shutdown complete")


# ============================================================================
# Utility Functions for Endpoint Modules
# ============================================================================

def get_node_id_from_request(request: Request) -> str:
    """Generate a node ID from request for automatic session management."""
    logger.debug(f"get_node_id_from_request: headers = {dict(request.headers)}")

    # Check for test isolation header first
    test_id = request.headers.get("x-test-id")
    if test_id:
        # If test_id already starts with "test_", don't add another prefix
        result = test_id if test_id.startswith("test_") else f"test_{test_id}"
        logger.debug(f"Using test ID: {result}")
        return result

    # Check for explicit node ID header
    node_id_header = request.headers.get("x-node-id")
    if node_id_header:
        logger.debug(f"Using x-node-id: {node_id_header}")
        return node_id_header

    logger.debug("Using default_node")
    return 'default_node'


# ============================================================================
# Include Modular Routers
# ============================================================================

# Include session management endpoints
app.include_router(sessions_router)

# Include monitoring and metrics endpoints
app.include_router(monitoring_router)

# Include health check endpoints
app.include_router(health_router)

# Include primary KATO operation endpoints
app.include_router(kato_ops_router)

# Include WebSocket events endpoint
app.include_router(websocket_events_router)


# ============================================================================
# Root Endpoint
# ============================================================================

@app.get("/")
async def root():
    """Root endpoint with service information"""
    return {
        "service": "KATO API",
        "version": "1.0.0",
        "description": "Knowledge Abstraction for Traceable Outcomes with Multi-User Support",
        "docs": "/docs",
        "health": "/health",
        "status": "running",
        "uptime_seconds": time.time() - app_state.startup_time,
        "architecture": "modular",
        "session_support": True
    }


# ============================================================================
# Note: WebSocket event streaming is now handled by /ws/events endpoint
# See kato/api/endpoints/websocket_events.py for implementation
# ============================================================================


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
