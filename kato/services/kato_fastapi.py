"""
KATO FastAPI Service with Session Management

This service provides multi-user support with complete session isolation.
Each user maintains their own STM without any data collision.

Critical improvements:
- Session-based isolation (no more shared STM)
- Database connection pooling
- Write concern = majority (no more data loss)
- Circuit breakers for fault tolerance
- Structured error handling
"""

import asyncio
import logging
import os
import time
import uuid
from typing import Dict, List, Optional, Any
from datetime import datetime

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

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

logger = logging.getLogger('kato.fastapi')

# ============================================================================
# Pydantic Models for v2 API
# ============================================================================

class CreateSessionRequest(BaseModel):
    """Request to create a new session"""
    user_id: str = Field(..., description="User identifier (required for processor isolation)")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Session metadata")
    ttl_seconds: Optional[int] = Field(None, description="Session TTL in seconds (uses default if not specified)")


class SessionResponse(BaseModel):
    """Session creation/info response"""
    session_id: str = Field(..., description="Unique session identifier")
    user_id: str = Field(..., description="Associated user ID")
    created_at: datetime = Field(..., description="Session creation time")
    expires_at: datetime = Field(..., description="Session expiration time")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Session metadata")
    session_config: Dict[str, Any] = Field(default_factory=dict, description="Session configuration")


class ObservationData(BaseModel):
    """Input data for observations"""
    strings: List[str] = Field(default_factory=list, description="String symbols to observe")
    vectors: List[List[float]] = Field(default_factory=list, description="Vector embeddings")
    emotives: Dict[str, float] = Field(default_factory=dict, description="Emotional values")


class ObservationResult(BaseModel):
    """Result of an observation"""
    status: str = Field(..., description="Status of the operation")
    session_id: Optional[str] = Field(None, description="Session ID")
    processor_id: Optional[str] = Field(None, description="Processor ID for v1 compatibility")
    stm_length: Optional[int] = Field(None, description="Current STM length")
    time: int = Field(..., description="Session time counter")
    unique_id: Optional[str] = Field(None, description="Unique observation ID")
    auto_learned_pattern: Optional[str] = Field(None, description="Auto-learned pattern name if any")


class STMResponse(BaseModel):
    """Short-term memory response"""
    stm: List[List[str]] = Field(..., description="Current STM state")
    session_id: Optional[str] = Field(None, description="Session ID")
    length: Optional[int] = Field(None, description="Number of events in STM")


class LearnResult(BaseModel):
    """Result of learning operation"""
    status: str = Field(..., description="Status of the learning operation (learned/insufficient_data)")
    pattern_name: str = Field(..., description="Name of the learned pattern (empty if not learned)")
    session_id: Optional[str] = Field(None, description="Session ID")
    processor_id: Optional[str] = Field(None, description="Processor ID for v1 compatibility")
    message: Optional[str] = Field(None, description="Human-readable message")
    status: Optional[str] = Field('learned', description="Operation status")


class PredictionsResponse(BaseModel):
    """Predictions response"""
    predictions: List[Dict] = Field(default_factory=list, description="List of predictions")
    future_potentials: Optional[List[Dict]] = Field(None, description="Aggregated future potentials")
    session_id: Optional[str] = Field(None, description="Session ID")
    processor_id: Optional[str] = Field(None, description="Processor ID for v1 compatibility")
    count: int = Field(..., description="Number of predictions")
    time: Optional[int] = Field(None, description="Time counter")
    unique_id: Optional[str] = Field(None, description="Unique ID if provided")


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
            logger.error(f"!!! AppState.session_manager creating new instance (id: {id(self)}) !!!")
            logger.error(f"!!! Call stack:\n{''.join(traceback.format_stack()[-5:])}")
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
    
    # Setup v2 error handlers
    setup_error_handlers(app)
    
    logger.info(f"KATO service started with ProcessorManager (base: {service_name}) and monitoring")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("Shutting down KATO service...")
    
    # Stop metrics collection
    if hasattr(app_state, 'metrics_collector'):
        await app_state.metrics_collector.stop_collection()
    
    # Shutdown processor manager
    if app_state.processor_manager:
        await app_state.processor_manager.shutdown()
    
    await app_state.session_manager.shutdown()


# ============================================================================
# Session Management Endpoints
# ============================================================================

@app.get("/test/{test_id}")
async def test_endpoint(test_id: str):
    """Simple test endpoint to verify routing works"""
    logger.debug(f"Test endpoint called: {test_id}")
    return {"test_id": test_id, "message": "endpoint works"}

@app.post("/sessions", response_model=SessionResponse)
async def create_session(request: CreateSessionRequest):
    """
    Create a new isolated session for a user.
    
    This enables multiple users to use KATO simultaneously
    without any data collision.
    """
    logger.info(f"Creating session with manager id: {id(app_state.session_manager)}")
    session = await app_state.session_manager.get_or_create_session(
        user_id=request.user_id,
        metadata=request.metadata,
        ttl_seconds=request.ttl_seconds
    )
    
    return SessionResponse(
        session_id=session.session_id,
        user_id=session.user_id,
        created_at=session.created_at,
        expires_at=session.expires_at,
        metadata=session.metadata,
        session_config=session.session_config.get_config_only() if hasattr(session, 'session_config') else {}
    )


@app.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session_info(session_id: str):
    """Get information about a session"""
    logger.info(f"Getting session info for: {session_id}")
    session = await app_state.session_manager.get_session(session_id)
    
    if not session:
        raise HTTPException(404, detail=f"Session {session_id} not found or expired")
    
    return SessionResponse(
        session_id=session.session_id,
        user_id=session.user_id,
        created_at=session.created_at,
        expires_at=session.expires_at,
        metadata=session.metadata,
        session_config=session.session_config.get_config_only() if hasattr(session, 'session_config') else {}
    )


@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete a session and cleanup resources"""
    deleted = await app_state.session_manager.delete_session(session_id)
    
    if not deleted:
        raise HTTPException(404, detail=f"Session {session_id} not found")
    
    return {"status": "deleted", "session_id": session_id}


@app.post("/sessions/{session_id}/config")
async def update_session_config(session_id: str, request_data: Dict[str, Any]):
    """Update session configuration (genes/parameters)"""
    logger.error(f"!!! DEBUG: update_session_config called for {session_id} with: {request_data}")
    logger.info(f"Updating config for session {session_id} with data: {request_data}")
    
    session = await app_state.session_manager.get_session(session_id)
    
    if not session:
        raise HTTPException(404, detail=f"Session {session_id} not found")
    
    # Extract config from request - it comes as {"config": {...}}
    config = request_data.get('config', request_data)
    logger.info(f"Extracted config: {config}")
    
    # Update the session's config - using SessionConfiguration's update method
    for key, value in config.items():
        if hasattr(session.session_config, key):
            setattr(session.session_config, key, value)
            logger.info(f"Updated session config {key} = {value}")
        else:
            logger.warning(f"Session config does not have attribute {key}")
    
    # Save the updated session back to Redis
    logger.info(f"Saving updated session to Redis")
    await app_state.session_manager.update_session(session)
    logger.info(f"Session saved successfully")
    
    # Try to get processor if it exists, otherwise it will be created with new config on next observation
    processor = None
    try:
        processor = await app_state.processor_manager.get_processor(session.user_id, session.session_config)
    except Exception as e:
        # Processor doesn't exist yet, will be created with new config on next observation
        logger.info(f"Processor not yet created for user {session.user_id}, config will be applied on first observation: {e}")
    
    if processor:
        # Apply configuration dynamically to processor
        for key, value in config.items():
            if key == 'max_pattern_length':
                processor.genome_manifest['MAX_PATTERN_LENGTH'] = value
                processor.MAX_PATTERN_LENGTH = value  # Update the processor's attribute directly
                # Also update the observation processor's max_pattern_length for auto-learning
                if hasattr(processor, 'observation_processor'):
                    processor.observation_processor.max_pattern_length = value
                    logger.info(f"Updated observation_processor.max_pattern_length to {value}")
                # And update the pattern processor's max_pattern_length
                if hasattr(processor, 'pattern_processor'):
                    processor.pattern_processor.max_pattern_length = value
                    logger.info(f"Updated pattern_processor.max_pattern_length to {value}")
            elif key == 'persistence':
                processor.genome_manifest['PERSISTENCE'] = value
            elif key == 'recall_threshold':
                processor.genome_manifest['RECALL_THRESHOLD'] = value
            elif key == 'indexer_type':
                processor.genome_manifest['INDEXER_TYPE'] = value
            elif key == 'max_predictions':
                processor.genome_manifest['MAX_PREDICTIONS'] = value
            elif key == 'sort_symbols':
                processor.genome_manifest['SORT'] = value
            elif key == 'process_predictions':
                processor.genome_manifest['PROCESS_PREDICTIONS'] = value
    
    # Log session config after update
    logger.info(f"Session config after update: {session.session_config.get_config_only()}")
    
    # Save the updated session
    await app_state.session_manager.update_session(session)
    
    return {"status": "okay", "message": "Configuration updated", "session_id": session_id}


@app.post("/sessions/{session_id}/extend")
async def extend_session(session_id: str, ttl_seconds: int = 3600):
    """Extend session expiration"""
    extended = await app_state.session_manager.extend_session(session_id, ttl_seconds)
    
    if not extended:
        raise HTTPException(404, detail=f"Session {session_id} not found")
    
    return {"status": "extended", "session_id": session_id, "ttl_seconds": ttl_seconds}


# ============================================================================
# Session-Scoped KATO Operations
# ============================================================================

@app.post("/sessions/{session_id}/observe", response_model=ObservationResult)
async def observe_in_session(
    session_id: str,
    data: ObservationData,
    request: Request
):
    """
    Process an observation in a specific session context.
    
    This is the core endpoint that enables multi-user support.
    Each session maintains its own isolated STM.
    """
    # Get session
    session = await app_state.session_manager.get_session(session_id)
    if not session:
        raise HTTPException(404, detail=f"Session {session_id} not found or expired")
    
    # Get user's processor (isolated per user) with session configuration
    logger.info(f"Getting processor for user {session.user_id} with session config: {session.session_config.get_config_only()}")
    processor = await app_state.processor_manager.get_processor(session.user_id, session.session_config)
    
    # Get session lock to ensure sequential processing within session
    lock = await app_state.session_manager.get_session_lock(session_id)
    
    async with lock:
        # Set processor state to session's state
        processor.set_stm(session.stm)
        processor.set_emotives_accumulator(session.emotives_accumulator)
        processor.time = session.time
        
        # Process observation
        observation = {
            'strings': data.strings,
            'vectors': data.vectors,
            'emotives': data.emotives,
            'unique_id': f"obs-{uuid.uuid4().hex}",
            'source': 'session'
        }
        
        result = processor.observe(observation)
        
        # Update session state with results
        session.stm = processor.get_stm()
        session.emotives_accumulator = processor.get_emotives_accumulator()
        session.time = processor.time
        
        # Save updated session
        await app_state.session_manager.update_session(session)
    
    return ObservationResult(
        status="ok",
        session_id=session_id,
        processor_id=session.user_id,  # For v1 compatibility
        stm_length=len(session.stm),
        time=session.time,
        unique_id=result.get('unique_id', ''),
        auto_learned_pattern=result.get('auto_learned_pattern')
    )


@app.get("/sessions/{session_id}/stm", response_model=STMResponse)
async def get_session_stm(session_id: str):
    """Get the short-term memory for a specific session"""
    logger.debug(f"Getting STM for session: {session_id}")
    
    session = await app_state.session_manager.get_session(session_id)
    
    if not session:
        logger.warning(f"Session {session_id} not found")
        raise HTTPException(404, detail=f"Session {session_id} not found or expired")
    
    logger.debug(f"Successfully retrieved session {session_id}")
    return STMResponse(
        stm=session.stm,
        session_id=session_id,
        length=len(session.stm)
    )


@app.post("/sessions/{session_id}/learn", response_model=LearnResult)
async def learn_in_session(session_id: str):
    """Learn a pattern from the session's current STM"""
    session = await app_state.session_manager.get_session(session_id)
    
    if not session:
        raise HTTPException(404, detail=f"Session {session_id} not found or expired")
    
    if not session.stm:
        raise HTTPException(400, detail="Cannot learn from empty STM")
    
    # Get user's processor (isolated per user) with session configuration
    processor = await app_state.processor_manager.get_processor(session.user_id, session.session_config)
    
    lock = await app_state.session_manager.get_session_lock(session_id)
    
    async with lock:
        # Set processor state
        processor.set_stm(session.stm)
        processor.set_emotives_accumulator(session.emotives_accumulator)
        
        # Learn pattern
        pattern_name = processor.learn()
        
        # Update session state
        session.stm = processor.get_stm()
        session.emotives_accumulator = processor.get_emotives_accumulator()
        
        await app_state.session_manager.update_session(session)
    
    return LearnResult(
        pattern_name=pattern_name,
        session_id=session_id,
        message=f"Learned pattern {pattern_name} from {len(session.stm)} events"
    )


@app.post("/sessions/{session_id}/clear-stm")
async def clear_session_stm(session_id: str):
    """Clear the STM for a specific session"""
    cleared = await app_state.session_manager.clear_session_stm(session_id)
    
    if not cleared:
        raise HTTPException(404, detail=f"Session {session_id} not found")
    
    return {"status": "cleared", "session_id": session_id}


@app.get("/sessions/{session_id}/predictions", response_model=PredictionsResponse)
async def get_session_predictions(session_id: str):
    """Get predictions based on the session's current STM"""
    session = await app_state.session_manager.get_session(session_id)
    
    if not session:
        raise HTTPException(404, detail=f"Session {session_id} not found or expired")
    
    # Get user's processor (isolated per user) with session configuration
    processor = await app_state.processor_manager.get_processor(session.user_id, session.session_config)
    
    lock = await app_state.session_manager.get_session_lock(session_id)
    
    async with lock:
        # Set processor state
        processor.set_stm(session.stm)
        
        # Get predictions
        predictions = processor.get_predictions()
        
        # Get future_potentials from the pattern processor if available
        future_potentials = None
        if hasattr(processor.pattern_processor, 'future_potentials'):
            future_potentials = processor.pattern_processor.future_potentials
    
    return PredictionsResponse(
        predictions=predictions,
        future_potentials=future_potentials,
        session_id=session_id,
        count=len(predictions)
    )


# ============================================================================
# System Status Endpoints
# ============================================================================

@app.get("/status")
async def get_system_status():
    """Get overall system status including session statistics"""
    session_stats = app_state.session_manager.get_session_stats()
    processor_stats = app_state.processor_manager.get_stats()
    
    return {
        "status": "healthy",
        "base_processor_id": app_state.processor_manager.base_processor_id,
        "uptime_seconds": time.time() - app_state.startup_time,
        "sessions": session_stats,
        "processors": processor_stats,
        "version": "1.0.0"
    }


@app.get("/health")
async def health_check():
    """Enhanced health check endpoint for v2 with metrics integration"""
    logger.debug("Health check endpoint called")
    try:
        if hasattr(app_state, 'metrics_collector'):
            health_status = app_state.metrics_collector.get_health_status()
            processor_status = "healthy" if app_state.processor_manager else "unhealthy"
            
            return {
                "status": health_status["status"],
                "processor_status": processor_status,
                "service_name": app_state.settings.service.service_name,
                "uptime_seconds": time.time() - app_state.startup_time,
                "issues": health_status.get("issues", []),
                "metrics_collected": len(app_state.metrics_collector.metrics),
                "last_collection": app_state.startup_time,
                "active_sessions": app_state.session_manager.get_active_session_count(),
                "timestamp": datetime.utcnow().isoformat()
            }
        else:
            # Fallback if metrics collector not available
            return {
                "status": "healthy",
                "processor_status": "healthy" if app_state.processor_manager else "unhealthy", 
                "service_name": app_state.settings.service.service_name,
                "uptime_seconds": time.time() - app_state.startup_time,
                "issues": [],
                "metrics_collected": 0,
                "last_collection": app_state.startup_time,
                "active_sessions": app_state.session_manager.get_active_session_count(),
                "timestamp": datetime.utcnow().isoformat()
            }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "processor_status": "unknown",
            "service_name": app_state.settings.service.service_name,
            "uptime_seconds": time.time() - app_state.startup_time,
            "issues": [f"Health check error: {str(e)}"],
            "metrics_collected": 0,
            "last_collection": app_state.startup_time,
            "active_sessions": 0,
            "timestamp": datetime.utcnow().isoformat()
        }


# ============================================================================
# Monitoring Endpoints
# ============================================================================

@app.get("/metrics")
async def get_comprehensive_metrics():
    """Get comprehensive v2 metrics including system resources and performance"""
    try:
        if not hasattr(app_state, 'metrics_collector'):
            # Return basic metrics if collector not available
            return {
                "error": "Metrics collector not available",
                "timestamp": time.time(),
                "processor_manager": app_state.processor_manager.get_stats() if app_state.processor_manager else {},
                "uptime_seconds": time.time() - app_state.startup_time,
                "active_sessions": app_state.session_manager.get_active_session_count()
            }
        
        # Get comprehensive metrics from collector
        try:
            summary_metrics = app_state.metrics_collector.get_summary_metrics()
            rates = app_state.metrics_collector.calculate_rates()
        except Exception as e:
            logger.error(f"Error getting metrics: {e}")
            # Return fallback metrics with basic structure for compatibility
            return {
                "timestamp": time.time(),
                "sessions": {"total_created": 0, "total_deleted": 0, "active": 0, "operations_total": 0},
                "performance": {"total_requests": 0, "total_errors": 0, "error_rate": 0.0, "average_response_time": 0.0},
                "resources": {"cpu_percent": 0.0, "memory_percent": 0.0, "disk_percent": 0.0},
                "databases": {
                    "mongodb": {"operations": 0, "errors": 0, "avg_response_time": 0.0},
                    "qdrant": {"operations": 0, "errors": 0, "avg_response_time": 0.0},
                    "redis": {"operations": 0, "errors": 0, "avg_response_time": 0.0}
                },
                "rates": {},
                "processor_manager": app_state.processor_manager.get_stats() if app_state.processor_manager else {},
                "uptime_seconds": time.time() - app_state.startup_time,
                "active_sessions": app_state.session_manager.get_active_session_count() or 0
            }
        
        # Enhance with processor-specific and session data
        session_count = app_state.session_manager.get_active_session_count() or 0
        
        # Merge processor manager data into summary
        summary_metrics["processor_manager"] = app_state.processor_manager.get_stats() if app_state.processor_manager else {}
        
        # Add session information
        summary_metrics["sessions"]["active"] = session_count
        summary_metrics["rates"] = rates
        
        return summary_metrics
    except Exception as e:
        logger.error(f"Failed to get v2 metrics: {e}")
        # Return basic fallback metrics
        return {
            "error": f"Metrics collection failed: {str(e)}",
            "timestamp": time.time(),
            "processor_manager": app_state.processor_manager.get_stats() if app_state.processor_manager else {},
            "uptime_seconds": time.time() - app_state.startup_time,
            "active_sessions": app_state.session_manager.get_active_session_count()
        }


@app.get("/stats")
async def get_stats(minutes: int = 10):
    """Get time-series statistics for the last N minutes"""
    try:
        if not hasattr(app_state, 'metrics_collector'):
            return {
                "error": "Metrics collector not available",
                "time_range_minutes": minutes,
                "timestamp": time.time(),
                "processor_manager": app_state.processor_manager.get_stats() if app_state.processor_manager else {}
            }
        
        # Available time series metrics
        available_metrics = [
            "cpu_percent", "memory_percent", "memory_used_mb", 
            "disk_percent", "load_average_1m", "requests_total", 
            "response_time", "errors_total", "sessions_created", 
            "sessions_deleted", "session_operations",
            "mongodb_operations", "mongodb_response_time", "mongodb_errors",
            "qdrant_operations", "qdrant_response_time", "qdrant_errors",
            "redis_operations", "redis_response_time", "redis_errors"
        ]
        
        # Collect time series data for all metrics
        time_series_data = {}
        for metric_name in available_metrics:
            time_series_data[metric_name] = app_state.metrics_collector.get_time_series(metric_name, minutes)
        
        # Summary statistics
        current_status = app_state.metrics_collector.get_health_status()
        summary = app_state.metrics_collector.get_summary_metrics()
        
        return {
            "time_range_minutes": minutes,
            "timestamp": time.time(),
            "processor_manager": app_state.processor_manager.get_stats() if app_state.processor_manager else {},
            "current_status": current_status,
            "time_series": time_series_data,
            "summary": {
                "sessions": summary["sessions"],
                "performance": summary["performance"],
                "resources": summary["resources"],
                "databases": summary["databases"]
            }
        }
    except Exception as e:
        logger.error(f"Failed to get v2 stats: {e}")
        return {
            "error": f"Stats collection failed: {str(e)}",
            "time_range_minutes": minutes,
            "timestamp": time.time(),
            "processor_manager": app_state.processor_manager.get_stats() if app_state.processor_manager else {}
        }


@app.get("/metrics/{metric_name}")
async def get_specific_metric_history(metric_name: str, minutes: int = 10):
    """Get time series data for a specific metric"""
    try:
        if not hasattr(app_state, 'metrics_collector'):
            raise HTTPException(status_code=503, detail="Metrics collector not available")
        
        time_series_data = app_state.metrics_collector.get_time_series(metric_name, minutes)
        
        if not time_series_data:
            raise HTTPException(
                status_code=404, 
                detail=f"No data available for metric '{metric_name}' in the last {minutes} minutes"
            )
        
        # Calculate basic statistics
        values = [point["value"] for point in time_series_data]
        stats = {
            "count": len(values),
            "min": min(values) if values else 0,
            "max": max(values) if values else 0,
            "avg": sum(values) / len(values) if values else 0
        }
        
        return {
            "metric_name": metric_name,
            "time_range_minutes": minutes,
            "timestamp": time.time(),
            "statistics": stats,
            "data_points": time_series_data
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get metric {metric_name}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve metric: {str(e)}")


# ============================================================================
# PRIMARY ENDPOINTS - Automatic Session Management
# ============================================================================

def get_user_id_from_request(request: Request) -> str:
    """Generate a user ID from request for automatic session management."""
    # Check for test isolation header first
    test_id = request.headers.get("x-test-id")
    if test_id:
        return f"test_{test_id}"
    
    # Check for explicit user ID header
    user_id_header = request.headers.get("x-user-id")
    if user_id_header:
        return user_id_header
    
    # Fall back to IP + user agent based ID
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")[:50]  # Limit length
    
    # Create a stable user_id for this client
    import hashlib
    user_key = f"{client_ip}_{user_agent}"
    user_id = f"default_{hashlib.md5(user_key.encode()).hexdigest()[:16]}"
    
    return user_id




@app.post("/observe", response_model=ObservationResult)  
async def observe_primary(request: Request, observation: ObservationData):
    """Primary observe endpoint with automatic session management."""
    user_id = get_user_id_from_request(request)
    session = await app_state.session_manager.get_or_create_session(
        user_id=user_id,
        metadata={"type": "auto_created", "endpoint": "observe"}
    )
    
    # Process the observation using the session
    processor = await app_state.processor_manager.get_processor(session.user_id, session.session_config)
    
    try:
        # Convert observation to required format
        observation_dict = observation.dict()
        
        # Add unique_id if not present
        if 'unique_id' not in observation_dict or not observation_dict.get('unique_id'):
            import uuid
            observation_dict['unique_id'] = str(uuid.uuid4())
        
        # Set processor STM to match session
        processor.set_stm(session.stm)
        
        # Observe and get results
        result = processor.observe(observation_dict)
        
        # Always sync session STM with processor STM after observation
        # This ensures consistency between session and processor state
        session.stm = processor.get_stm()
        
        await app_state.session_manager.update_session(session)
        
        return ObservationResult(
            status='okay',  # Always return 'okay' for v1 compatibility
            processor_id=processor.id,
            time=result.get('time', int(time.time())),
            unique_id=result.get('unique_id', ''),
            auto_learned_pattern=result.get('auto_learned_pattern')
        )
        
    except Exception as e:
        logger.error(f"Observation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Observation failed: {str(e)}")


@app.get("/stm", response_model=STMResponse)
@app.get("/short-term-memory", response_model=STMResponse)  # Alias
async def get_stm_primary(request: Request):
    """Primary STM endpoint with automatic session management."""
    user_id = get_user_id_from_request(request)
    session = await app_state.session_manager.get_or_create_session(
        user_id=user_id,
        metadata={"type": "auto_created", "endpoint": request.url.path}
    )
    processor = await app_state.processor_manager.get_processor(session.user_id, session.session_config)
    
    # Ensure processor STM matches session state
    processor.set_stm(session.stm)
    stm = processor.get_stm()
    
    return STMResponse(
        stm=stm,
        processor_id=processor.id,
        length=len(stm)
    )


@app.post("/learn", response_model=LearnResult)
async def learn_primary(request: Request):
    """Primary learn endpoint with automatic session management."""
    user_id = get_user_id_from_request(request)
    session = await app_state.session_manager.get_or_create_session(
        user_id=user_id,
        metadata={"type": "auto_created", "endpoint": request.url.path}
    )
    processor = await app_state.processor_manager.get_processor(session.user_id, session.session_config)
    
    try:
        # Check if STM has sufficient data for learning
        # Pattern requires at least 2 symbols total across all events
        total_symbols = sum(len(event) for event in session.stm) if session.stm else 0
        
        if total_symbols < 2:
            # Don't clear STM if learning wasn't attempted
            return LearnResult(
                status='insufficient_data',
                pattern_name='',
                processor_id=processor.id,
                message=f'Cannot learn pattern: STM requires at least 2 symbols, found {total_symbols}'
            )
        
        # Set processor STM to session STM
        processor.set_stm(session.stm)
        
        # Learn the current STM sequence
        pattern_name = processor.learn()
        
        # Clear STM after successful learning
        session.stm = []
        await app_state.session_manager.update_session(session)
        
        return LearnResult(
            status='learned',
            pattern_name=pattern_name or '',
            processor_id=processor.id,
            message='Pattern learned successfully'
        )
        
    except Exception as e:
        logger.error(f"Learning failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Learning failed: {str(e)}")


@app.post("/clear-stm")
@app.post("/clear-short-term-memory")  # Alias
async def clear_stm_primary(request: Request):
    """Primary clear STM endpoint with automatic session management."""
    user_id = get_user_id_from_request(request)
    session = await app_state.session_manager.get_or_create_session(
        user_id=user_id,
        metadata={"type": "auto_created", "endpoint": request.url.path}
    )
    session.stm = []
    await app_state.session_manager.update_session(session)
    return {"status": "okay", "message": "stm-cleared"}


@app.post("/clear-all")
@app.post("/clear-all-memory")  # Alias
async def clear_all_primary(request: Request):
    """Primary clear all endpoint with automatic session management."""
    user_id = get_user_id_from_request(request)
    session = await app_state.session_manager.get_or_create_session(
        user_id=user_id,
        metadata={"type": "auto_created", "endpoint": request.url.path}
    )
    processor = await app_state.processor_manager.get_processor(session.user_id, session.session_config)
    
    try:
        # Clear STM
        session.stm = []
        await app_state.session_manager.update_session(session)
        
        # Clear all memory in processor (this is per-user isolated)
        processor.clear_all_memory()
        
        return {"status": "okay", "message": "all-cleared"}
        
    except Exception as e:
        logger.error(f"Clear all failed: {e}")
        raise HTTPException(status_code=500, detail=f"Clear all failed: {str(e)}")




@app.get("/predictions", response_model=PredictionsResponse)
@app.post("/predictions", response_model=PredictionsResponse)  # Some tests use POST
async def get_predictions_primary(request: Request, unique_id: Optional[str] = None):
    """Primary predictions endpoint with automatic session management."""
    user_id = get_user_id_from_request(request)
    session = await app_state.session_manager.get_or_create_session(
        user_id=user_id,
        metadata={"type": "auto_created", "endpoint": request.url.path}
    )
    processor = await app_state.processor_manager.get_processor(session.user_id, session.session_config)
    
    try:
        # Set STM in processor to match session
        if hasattr(processor.pattern_processor, 'superkb'):
            processor.pattern_processor.superkb.stm = session.stm
        
        predictions = processor.get_predictions(unique_id=unique_id)
        
        # Add pattern_name field for v1 compatibility
        # V1 expects 'pattern_name' but v2 returns 'name'
        for pred in predictions:
            if 'name' in pred and 'pattern_name' not in pred:
                pred['pattern_name'] = f"PTRN|{pred['name']}"
        
        # Get future_potentials from the pattern processor if available
        future_potentials = None
        if hasattr(processor.pattern_processor, 'future_potentials'):
            future_potentials = processor.pattern_processor.future_potentials
        
        return PredictionsResponse(
            predictions=predictions,
            future_potentials=future_potentials,
            count=len(predictions),
            processor_id=processor.id,
            time=int(time.time()),
            unique_id=unique_id
        )
        
    except Exception as e:
        logger.error(f"Get predictions failed: {e}")
        raise HTTPException(status_code=500, detail=f"Predictions failed: {str(e)}")


# Gene and pattern endpoints (simplified, no dynamic updates in v2)
@app.get("/gene/{gene_name}")
async def get_gene_primary(request: Request, gene_name: str):
    """Get a gene value for the current user."""
    user_id = get_user_id_from_request(request)
    session = await app_state.session_manager.get_or_create_session(
        user_id=user_id,
        metadata={"type": "auto_created", "endpoint": request.url.path}
    )
    
    # Use ConfigurationService to resolve configuration
    resolved_config = app_state.config_service.resolve_configuration(
        session_config=session.session_config,
        session_id=session.session_id,
        user_id=session.user_id
    )
    user_genes = resolved_config.to_genes_dict()
    
    if gene_name not in user_genes:
        raise HTTPException(status_code=404, detail=f"Gene '{gene_name}' not found")
    
    return {"gene": gene_name, "value": user_genes[gene_name]}


@app.post("/genes/update")
async def update_genes_primary(request: Request, genes: dict):
    """Update genes for the current user's configuration."""
    user_id = get_user_id_from_request(request)
    session = await app_state.session_manager.get_or_create_session(
        user_id=user_id,
        metadata={"type": "auto_created", "endpoint": request.url.path}
    )
    
    # Extract the actual gene updates from the nested structure
    # The input is {"genes": {"recall_threshold": 0.5}} but we need just {"recall_threshold": 0.5}
    gene_updates = genes.get('genes', genes)
    
    # Update user configuration
    if session.session_config.update(gene_updates):
        # Apply configuration to processor
        success = await app_state.processor_manager.update_processor_config(
            user_id, session.session_config
        )
        
        if success:
            # Save updated session
            await app_state.session_manager.update_session(session)
            return {"status": "okay", "message": "genes-updated", "genes": gene_updates}
        else:
            return {"status": "error", "message": "Failed to apply configuration"}
    else:
        return {"status": "error", "message": "Invalid gene values"}


@app.get("/pattern/{pattern_id}")
async def get_pattern_primary(request: Request, pattern_id: str):
    """Get a pattern by ID."""
    user_id = get_user_id_from_request(request)
    session = await app_state.session_manager.get_or_create_session(
        user_id=user_id,
        metadata={"type": "auto_created", "endpoint": request.url.path}
    )
    processor = await app_state.processor_manager.get_processor(session.user_id, session.session_config)
    
    try:
        pattern = processor.get_pattern(pattern_id)
        if not pattern:
            raise HTTPException(status_code=404, detail=f"Pattern '{pattern_id}' not found")
        
        return {"pattern": pattern}
        
    except Exception as e:
        logger.error(f"Get pattern failed: {e}")
        raise HTTPException(status_code=500, detail=f"Pattern retrieval failed: {str(e)}")


@app.get("/percept-data")
async def get_percept_data_primary(request: Request):
    """Get percept data."""
    user_id = get_user_id_from_request(request)
    session = await app_state.session_manager.get_or_create_session(
        user_id=user_id,
        metadata={"type": "auto_created", "endpoint": request.url.path}
    )
    processor = await app_state.processor_manager.get_processor(session.user_id, session.session_config)
    
    try:
        percept_data = processor.get_percept_data()
        return {"percept_data": percept_data}
        
    except Exception as e:
        logger.error(f"Get percept data failed: {e}")
        raise HTTPException(status_code=500, detail=f"Percept data retrieval failed: {str(e)}")


@app.get("/cognition-data")  
async def get_cognition_data_primary(request: Request):
    """Get cognition data."""
    user_id = get_user_id_from_request(request)
    session = await app_state.session_manager.get_or_create_session(
        user_id=user_id,
        metadata={"type": "auto_created", "endpoint": request.url.path}
    )
    processor = await app_state.processor_manager.get_processor(session.user_id, session.session_config)
    
    try:
        cognition_data = processor.cognition_data
        return {"cognition_data": cognition_data}
        
    except Exception as e:
        logger.error(f"Get cognition data failed: {e}")
        raise HTTPException(status_code=500, detail=f"Cognition data retrieval failed: {str(e)}")


# Bulk endpoint
@app.post("/observe-sequence")
async def observe_sequence_primary(request: Request, batch_request: dict):
    """Primary bulk observe endpoint."""
    user_id = get_user_id_from_request(request)
    session = await app_state.session_manager.get_or_create_session(
        user_id=user_id,
        metadata={"type": "auto_created", "endpoint": request.url.path}
    )
    processor = await app_state.processor_manager.get_processor(session.user_id, session.session_config)
    
    # Validate input structure first (outside try-except to let HTTPException propagate)
    observations = batch_request.get('observations')
    if observations is None:
        raise HTTPException(status_code=422, detail="Missing required field: observations")
    if not isinstance(observations, list):
        raise HTTPException(status_code=422, detail="Field 'observations' must be a list")
    
    try:
        
        # Extract learning options
        learn_after_each = batch_request.get('learn_after_each', False)
        learn_at_end = batch_request.get('learn_at_end', False)
        clear_stm_between = batch_request.get('clear_stm_between', False)
        
        # Clear session STM for batch processing (v1 compatibility - each batch starts fresh)
        session.stm = []
        
        # Set initial processor STM to empty for batch
        processor.set_stm([])
        
        results = []
        patterns_learned = []
        
        for idx, obs in enumerate(observations):
            # Clear STM between observations if requested
            if clear_stm_between and idx > 0:
                processor.set_stm([])
                session.stm = []
            
            # processor.observe expects a dict with unique_id
            import uuid
            # Sort strings alphanumerically for consistency
            sorted_strings = sorted(obs.get('strings', []))
            obs_dict = {
                'strings': sorted_strings,
                'vectors': obs.get('vectors', []),
                'emotives': obs.get('emotives', {}),
                'unique_id': obs.get('unique_id', str(uuid.uuid4()))  # Generate if not provided
            }
            
            result = processor.observe(obs_dict)
            # Transform result to match v1 API format
            formatted_result = {
                'status': 'okay',  # v1 compatibility
                'processor_id': processor.id,
                'unique_id': result.get('unique_id', obs_dict['unique_id']),
                'time': result.get('time', 0),
                'auto_learned_pattern': result.get('auto_learned_pattern')
            }
            results.append(formatted_result)
            
            # Add to session STM - use the combined symbols (includes vector names)
            # The processor.observe returns symbols that include both strings and vector names
            combined_symbols = result.get('symbols', sorted_strings)
            if combined_symbols:
                session.stm.append(combined_symbols)
            
            # Learn after each observation if requested
            if learn_after_each:
                # Update processor STM before learning
                processor.set_stm(session.stm)
                pattern_name = processor.learn()
                if pattern_name:
                    patterns_learned.append(pattern_name)
                # Clear STM after learning (auto-learn behavior)
                processor.set_stm([])
                session.stm = []
        
        # Learn at end if requested (and not already learning after each)
        if learn_at_end and not learn_after_each:
            # Update processor STM to match final session state
            processor.set_stm(session.stm)
            pattern_name = processor.learn()
            if pattern_name:
                patterns_learned.append(pattern_name)
            # Clear STM after learning (auto-learn behavior)
            processor.set_stm([])
            session.stm = []
        
        # Update processor STM to match final session state (if no learning happened)
        if not learn_after_each and not learn_at_end:
            processor.set_stm(session.stm)
        
        await app_state.session_manager.update_session(session)
        
        # Get final predictions after all observations
        predictions = processor.get_predictions()
        
        # Add pattern_name field for v1 compatibility
        for pred in predictions:
            if 'name' in pred and 'pattern_name' not in pred:
                pred['pattern_name'] = f"PTRN|{pred['name']}"
        
        # Format response to match test expectations
        return {
            "status": "okay",  # Tests expect 'okay'
            "processor_id": session.user_id,  # Use user_id as processor_id in v2
            "observations_processed": len(results),
            "patterns_learned": patterns_learned,
            "individual_results": results,
            "final_predictions": predictions
        }
        
    except Exception as e:
        logger.error(f"Observe sequence failed: {e}")
        raise HTTPException(status_code=500, detail=f"Observe sequence failed: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)