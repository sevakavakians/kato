"""
KATO v2.0 FastAPI Service with Session Management

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
import time
import uuid
from typing import Dict, List, Optional, Any
from datetime import datetime

from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Import v2 components
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from kato.v2.sessions.session_manager import get_session_manager, SessionState
from kato.v2.sessions.redis_session_manager import get_redis_session_manager
from kato.v2.sessions.session_middleware_simple import (
    SessionMiddleware, get_session, get_session_id, 
    get_optional_session, mark_session_modified
)
from kato.v2.processors.processor_manager import ProcessorManager

from kato.workers.kato_processor import KatoProcessor
from kato.config.settings import get_settings
from kato.v2.monitoring.metrics import get_metrics_collector, MetricsCollector
from kato.v2.errors.handlers import setup_error_handlers

logger = logging.getLogger('kato.v2.fastapi')

# ============================================================================
# Pydantic Models for v2 API
# ============================================================================

class CreateSessionRequest(BaseModel):
    """Request to create a new session"""
    user_id: str = Field(..., description="User identifier (required for processor isolation)")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Session metadata")
    ttl_seconds: Optional[int] = Field(3600, description="Session TTL in seconds")


class SessionResponse(BaseModel):
    """Session creation/info response"""
    session_id: str = Field(..., description="Unique session identifier")
    user_id: str = Field(..., description="Associated user ID")
    created_at: datetime = Field(..., description="Session creation time")
    expires_at: datetime = Field(..., description="Session expiration time")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Session metadata")


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
    pattern_name: str = Field(..., description="Name of the learned pattern")
    session_id: Optional[str] = Field(None, description="Session ID")
    processor_id: Optional[str] = Field(None, description="Processor ID for v1 compatibility")
    message: Optional[str] = Field(None, description="Human-readable message")
    status: Optional[str] = Field('learned', description="Operation status")


class PredictionsResponse(BaseModel):
    """Predictions response"""
    predictions: List[Dict] = Field(default_factory=list, description="List of predictions")
    session_id: Optional[str] = Field(None, description="Session ID")
    processor_id: Optional[str] = Field(None, description="Processor ID for v1 compatibility")
    count: int = Field(..., description="Number of predictions")
    time: Optional[int] = Field(None, description="Time counter")
    unique_id: Optional[str] = Field(None, description="Unique ID if provided")


# ============================================================================
# FastAPI Application Setup
# ============================================================================

app = FastAPI(
    title="KATO v2.0 API",
    description="Knowledge Abstraction for Traceable Outcomes - v2.0 with Multi-User Support",
    version="2.0.0"
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
        self.startup_time = time.time()
        self._session_manager = None
    
    @property
    def session_manager(self):
        """Get session manager singleton"""
        if self._session_manager is None:
            # Use Redis session manager if Redis is configured
            redis_url = os.environ.get('REDIS_URL')
            if redis_url:
                logger.info(f"Using Redis session manager with URL: {redis_url}")
                self._session_manager = get_redis_session_manager(redis_url=redis_url)
            else:
                logger.info("Using in-memory session manager")
                self._session_manager = get_session_manager()
        return self._session_manager


app_state = AppState()


@app.on_event("startup")
async def startup_event():
    """Initialize application on startup"""
    logger.info("Starting KATO v2.0 FastAPI service...")
    
    # Initialize Redis session manager if using Redis
    if hasattr(app_state.session_manager, 'initialize'):
        await app_state.session_manager.initialize()
        logger.info("Redis session manager initialized")
    
    # Initialize ProcessorManager for per-user isolation
    settings = app_state.settings
    base_processor_id = settings.processor.processor_id
    app_state.processor_manager = ProcessorManager(
        base_processor_id=base_processor_id,
        max_processors=100,
        eviction_ttl_seconds=3600
    )
    
    # Initialize v2 monitoring
    metrics_collector = get_metrics_collector()
    app_state.metrics_collector = metrics_collector
    await metrics_collector.start_collection()
    
    # Setup v2 error handlers
    setup_error_handlers(app)
    
    logger.info(f"KATO v2.0 service started with ProcessorManager (base: {base_processor_id}) and monitoring")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("Shutting down KATO v2.0 service...")
    
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

@app.get("/v2/test/{test_id}")
async def test_endpoint(test_id: str):
    """Simple test endpoint to verify routing works"""
    print(f"*** TEST ENDPOINT CALLED: {test_id}")
    logger.error(f"*** TEST ENDPOINT CALLED: {test_id}")
    return {"test_id": test_id, "message": "endpoint works"}

@app.post("/v2/sessions", response_model=SessionResponse)
async def create_session(request: CreateSessionRequest):
    """
    Create a new isolated session for a user.
    
    This enables multiple users to use KATO simultaneously
    without any data collision.
    """
    logger.info(f"Creating session with manager id: {id(app_state.session_manager)}")
    session = await app_state.session_manager.create_session(
        user_id=request.user_id,
        metadata=request.metadata,
        ttl_seconds=request.ttl_seconds
    )
    
    return SessionResponse(
        session_id=session.session_id,
        user_id=session.user_id,
        created_at=session.created_at,
        expires_at=session.expires_at,
        metadata=session.metadata
    )


@app.get("/v2/sessions/{session_id}", response_model=SessionResponse)
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
        metadata=session.metadata
    )


@app.delete("/v2/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete a session and cleanup resources"""
    deleted = await app_state.session_manager.delete_session(session_id)
    
    if not deleted:
        raise HTTPException(404, detail=f"Session {session_id} not found")
    
    return {"status": "deleted", "session_id": session_id}


@app.post("/v2/sessions/{session_id}/extend")
async def extend_session(session_id: str, ttl_seconds: int = 3600):
    """Extend session expiration"""
    extended = await app_state.session_manager.extend_session(session_id, ttl_seconds)
    
    if not extended:
        raise HTTPException(404, detail=f"Session {session_id} not found")
    
    return {"status": "extended", "session_id": session_id, "ttl_seconds": ttl_seconds}


# ============================================================================
# Session-Scoped KATO Operations
# ============================================================================

@app.post("/v2/sessions/{session_id}/observe", response_model=ObservationResult)
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
    
    # Get user's processor (isolated per user)
    processor = await app_state.processor_manager.get_processor(session.user_id)
    
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
            'source': 'v2_session'
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


@app.get("/v2/sessions/{session_id}/stm", response_model=STMResponse)
async def get_session_stm(session_id: str):
    """Get the short-term memory for a specific session"""
    print(f"*** ENDPOINT CALLED: Getting STM for session: {session_id}")
    logger.error(f"*** ENDPOINT CALLED: Getting STM for session: {session_id}")
    logger.info(f"Getting STM for session: {session_id}")
    logger.info(f"Session manager type: {type(app_state.session_manager)}")
    logger.info(f"Session manager id: {id(app_state.session_manager)}")
    logger.info(f"Session manager connected: {getattr(app_state.session_manager, '_connected', 'N/A')}")
    
    session = await app_state.session_manager.get_session(session_id)
    
    if not session:
        logger.error(f"Session {session_id} not found")
        raise HTTPException(404, detail=f"Session {session_id} not found or expired")
    
    logger.info(f"Successfully retrieved session {session_id}")
    return STMResponse(
        stm=session.stm,
        session_id=session_id,
        length=len(session.stm)
    )


@app.post("/v2/sessions/{session_id}/learn", response_model=LearnResult)
async def learn_in_session(session_id: str):
    """Learn a pattern from the session's current STM"""
    session = await app_state.session_manager.get_session(session_id)
    
    if not session:
        raise HTTPException(404, detail=f"Session {session_id} not found or expired")
    
    if not session.stm:
        raise HTTPException(400, detail="Cannot learn from empty STM")
    
    # Get user's processor (isolated per user)
    processor = await app_state.processor_manager.get_processor(session.user_id)
    
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


@app.post("/v2/sessions/{session_id}/clear-stm")
async def clear_session_stm(session_id: str):
    """Clear the STM for a specific session"""
    cleared = await app_state.session_manager.clear_session_stm(session_id)
    
    if not cleared:
        raise HTTPException(404, detail=f"Session {session_id} not found")
    
    return {"status": "cleared", "session_id": session_id}


@app.get("/v2/sessions/{session_id}/predictions", response_model=PredictionsResponse)
async def get_session_predictions(session_id: str):
    """Get predictions based on the session's current STM"""
    session = await app_state.session_manager.get_session(session_id)
    
    if not session:
        raise HTTPException(404, detail=f"Session {session_id} not found or expired")
    
    # Get user's processor (isolated per user)
    processor = await app_state.processor_manager.get_processor(session.user_id)
    
    lock = await app_state.session_manager.get_session_lock(session_id)
    
    async with lock:
        # Set processor state
        processor.set_stm(session.stm)
        
        # Get predictions
        predictions = processor.get_predictions()
    
    return PredictionsResponse(
        predictions=predictions,
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
        "base_processor_id": app_state.settings.processor.processor_id,
        "uptime_seconds": time.time() - app_state.startup_time,
        "sessions": session_stats,
        "processors": processor_stats,
        "version": "2.0.0"
    }


@app.get("/health")
@app.get("/v2/health")  # Alias for v2 compatibility
async def health_check():
    """Enhanced health check endpoint for v2 with metrics integration"""
    print("*** HEALTH CHECK ENDPOINT CALLED ***")
    logger.error("*** HEALTH CHECK ENDPOINT CALLED ***")
    try:
        if hasattr(app_state, 'metrics_collector'):
            health_status = app_state.metrics_collector.get_health_status()
            processor_status = "healthy" if app_state.processor_manager else "unhealthy"
            
            return {
                "status": health_status["status"],
                "processor_status": processor_status,
                "base_processor_id": app_state.settings.processor.processor_id,
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
                "base_processor_id": app_state.settings.processor.processor_id,
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
            "base_processor_id": app_state.settings.processor.processor_id,
            "uptime_seconds": time.time() - app_state.startup_time,
            "issues": [f"Health check error: {str(e)}"],
            "metrics_collected": 0,
            "last_collection": app_state.startup_time,
            "active_sessions": 0,
            "timestamp": datetime.utcnow().isoformat()
        }


# ============================================================================
# V2 Monitoring Endpoints
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
        summary_metrics = app_state.metrics_collector.get_summary_metrics()
        rates = app_state.metrics_collector.calculate_rates()
        
        # Enhance with processor-specific and session data
        session_count = app_state.session_manager.get_active_session_count()
        
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
    session = await app_state.session_manager.create_session(
        user_id=user_id,
        metadata={"type": "auto_created", "endpoint": "observe"}
    )
    
    # Process the observation using the session
    processor = await app_state.processor_manager.get_processor(session.user_id)
    
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
        
        # Update session STM
        new_event = observation_dict.get('strings', [])
        if new_event:  # Only add non-empty events
            session.stm.append(new_event)
            await app_state.session_manager.update_session(session)
        
        return ObservationResult(
            status=result.get('status', 'okay'),
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
    session = await app_state.session_manager.create_session(
        user_id=user_id,
        metadata={"type": "auto_created", "endpoint": request.url.path}
    )
    return STMResponse(stm=session.stm, length=len(session.stm))


@app.post("/learn", response_model=LearnResult)
async def learn_primary(request: Request):
    """Primary learn endpoint with automatic session management."""
    user_id = get_user_id_from_request(request)
    session = await app_state.session_manager.create_session(
        user_id=user_id,
        metadata={"type": "auto_created", "endpoint": request.url.path}
    )
    processor = await app_state.processor_manager.get_processor(session.user_id)
    
    try:
        if not session.stm:
            raise HTTPException(status_code=400, detail="No observations in STM to learn")
        
        # Set processor STM to session STM
        processor.set_stm(session.stm)
        
        # Learn the current STM sequence
        pattern_name = processor.learn()
        
        # Clear STM after learning
        session.stm = []
        await app_state.session_manager.update_session(session)
        
        return LearnResult(
            status='learned',
            pattern_name=pattern_name or '',
            processor_id=processor.processor_id
        )
        
    except Exception as e:
        logger.error(f"Learning failed: {e}")
        raise HTTPException(status_code=500, detail=f"Learning failed: {str(e)}")


@app.post("/clear-stm")
@app.post("/clear-short-term-memory")  # Alias
async def clear_stm_primary(request: Request):
    """Primary clear STM endpoint with automatic session management."""
    user_id = get_user_id_from_request(request)
    session = await app_state.session_manager.create_session(
        user_id=user_id,
        metadata={"type": "auto_created", "endpoint": request.url.path}
    )
    session.stm = []
    await app_state.session_manager.update_session(session)
    return {"message": "STM cleared", "status": "cleared"}


@app.post("/clear-all")
@app.post("/clear-all-memory")  # Alias
async def clear_all_primary(request: Request):
    """Primary clear all endpoint with automatic session management."""
    user_id = get_user_id_from_request(request)
    session = await app_state.session_manager.create_session(
        user_id=user_id,
        metadata={"type": "auto_created", "endpoint": request.url.path}
    )
    processor = await app_state.processor_manager.get_processor(session.user_id)
    
    try:
        # Clear STM
        session.stm = []
        await app_state.session_manager.update_session(session)
        
        # Clear all memory in processor (this is per-user isolated)
        processor.clear_all_memory()
        
        return {"message": "All memory cleared", "status": "all-cleared"}
        
    except Exception as e:
        logger.error(f"Clear all failed: {e}")
        raise HTTPException(status_code=500, detail=f"Clear all failed: {str(e)}")


@app.get("/predictions", response_model=PredictionsResponse)
@app.post("/predictions", response_model=PredictionsResponse)  # Some tests use POST
async def get_predictions_primary(request: Request, unique_id: Optional[str] = None):
    """Primary predictions endpoint with automatic session management."""
    user_id = get_user_id_from_request(request)
    session = await app_state.session_manager.create_session(
        user_id=user_id,
        metadata={"type": "auto_created", "endpoint": request.url.path}
    )
    processor = await app_state.processor_manager.get_processor(session.user_id)
    
    try:
        # Set STM in processor to match session
        if hasattr(processor.pattern_processor, 'superkb'):
            processor.pattern_processor.superkb.stm = session.stm
        
        predictions = processor.get_predictions(unique_id=unique_id)
        
        return PredictionsResponse(
            predictions=predictions,
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
async def get_gene_primary(gene_name: str):
    """Get a gene value."""
    # In v2, genes are set at processor creation time
    processor_genes = {
        "recall_threshold": app_state.settings.learning.recall_threshold,
        "persistence": app_state.settings.learning.persistence,
        "max_pattern_length": app_state.settings.learning.max_pattern_length,
        "smoothness": app_state.settings.learning.smoothness,
    }
    
    if gene_name not in processor_genes:
        raise HTTPException(status_code=404, detail=f"Gene '{gene_name}' not found")
    
    return {"gene": gene_name, "value": processor_genes[gene_name]}


@app.post("/genes/update")
async def update_genes_primary(genes: dict):
    """Update genes - no-op in v2 (genes are set at processor creation)."""
    return {"status": "genes-not-updateable-in-v2", "message": "Genes are configured per user at processor creation"}


@app.get("/pattern/{pattern_id}")
async def get_pattern_primary(request: Request, pattern_id: str):
    """Get a pattern by ID."""
    user_id = get_user_id_from_request(request)
    session = await app_state.session_manager.create_session(
        user_id=user_id,
        metadata={"type": "auto_created", "endpoint": request.url.path}
    )
    processor = await app_state.processor_manager.get_processor(session.user_id)
    
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
    session = await app_state.session_manager.create_session(
        user_id=user_id,
        metadata={"type": "auto_created", "endpoint": request.url.path}
    )
    processor = await app_state.processor_manager.get_processor(session.user_id)
    
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
    session = await app_state.session_manager.create_session(
        user_id=user_id,
        metadata={"type": "auto_created", "endpoint": request.url.path}
    )
    processor = await app_state.processor_manager.get_processor(session.user_id)
    
    try:
        cognition_data = processor.get_cognition_data()
        return {"cognition_data": cognition_data}
        
    except Exception as e:
        logger.error(f"Get cognition data failed: {e}")
        raise HTTPException(status_code=500, detail=f"Cognition data retrieval failed: {str(e)}")


# Bulk endpoint
@app.post("/observe-sequence")
async def observe_sequence_primary(request: Request, batch_request: dict):
    """Primary bulk observe endpoint."""
    user_id = get_user_id_from_request(request)
    session = await app_state.session_manager.create_session(
        user_id=user_id,
        metadata={"type": "auto_created", "endpoint": request.url.path}
    )
    processor = await app_state.processor_manager.get_processor(session.user_id)
    
    try:
        observations = batch_request.get('observations', [])
        options = batch_request.get('options', {})
        
        # Set initial processor STM to match session
        processor.set_stm(session.stm)
        
        results = []
        for idx, obs in enumerate(observations):
            # processor.observe expects a dict with unique_id
            import uuid
            obs_dict = {
                'strings': obs.get('strings', []),
                'vectors': obs.get('vectors', []),
                'emotives': obs.get('emotives', {}),
                'unique_id': obs.get('unique_id', str(uuid.uuid4()))  # Generate if not provided
            }
            
            result = processor.observe(obs_dict)
            results.append(result)
            
            # Add to session STM
            new_event = obs.get('strings', [])
            if new_event:
                session.stm.append(new_event)
        
        # Update processor STM to match final session state
        processor.set_stm(session.stm)
        await app_state.session_manager.update_session(session)
        
        # Get final predictions after all observations
        predictions = processor.get_predictions()
        
        # Format response to match test expectations
        return {
            "status": "okay",  # Tests expect 'okay'
            "processor_id": session.user_id,  # Use user_id as processor_id in v2
            "observations_processed": len(results),
            "individual_results": results,
            "final_predictions": predictions
        }
        
    except Exception as e:
        logger.error(f"Observe sequence failed: {e}")
        raise HTTPException(status_code=500, detail=f"Observe sequence failed: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)