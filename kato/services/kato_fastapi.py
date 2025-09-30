"""
KATO FastAPI Service with Session Management - Refactored Version

This service provides multi-user support with complete session isolation.
Each user maintains their own STM without any data collision.

Refactored to use modular endpoint structure for better maintainability.
"""

import asyncio
import logging
import os
import time
import uuid
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

# Import v2 components
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from kato.sessions.session_manager import get_session_manager
from kato.sessions.redis_session_manager import get_redis_session_manager
from kato.sessions.session_middleware_simple import (
    SessionMiddleware
)
from kato.processors.processor_manager import ProcessorManager

from kato.workers.kato_processor import KatoProcessor
from kato.config.settings import get_settings
from kato.config.configuration_service import get_configuration_service
from kato.monitoring.metrics import get_metrics_collector
from kato.errors.handlers import setup_error_handlers
from kato.storage.pattern_cache import get_cache_manager
from kato.exceptions import (
    ObservationError, ValidationError, DatabaseConnectionError,
    PredictionError, LearningError, PatternProcessingError,
    ResourceNotFoundError, MetricCalculationError
)
from kato.utils.logging import get_logger, trace_context, generate_trace_id

# Import modular API endpoints
from kato.api.endpoints import (
    sessions_router,
    monitoring_router,
    health_router,
    kato_ops_router
)

# Use enhanced logger with trace ID support
kato_logger = get_logger('kato.fastapi')
logger = logging.getLogger('kato.fastapi')  # Keep for compatibility

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
    
    # Setup error handlers
    setup_error_handlers(app)
    
    logger.info("KATO FastAPI service started successfully")


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

def get_user_id_from_request(request: Request) -> str:
    """Extract user ID from request (used by legacy endpoints)"""
    return request.headers.get('X-User-ID', 'default_user')


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
# WebSocket Support (if needed)
# ============================================================================

from fastapi import WebSocket, WebSocketDisconnect

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time communication"""
    await websocket.accept()
    logger.info("WebSocket connection established")
    
    try:
        while True:
            # Receive message from client
            data = await websocket.receive_text()
            logger.debug(f"Received WebSocket message: {data}")
            
            # Echo back for now (can be enhanced for real-time observations)
            await websocket.send_text(f"Echo: {data}")
            
    except WebSocketDisconnect:
        logger.info("WebSocket connection closed")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        await websocket.close()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)