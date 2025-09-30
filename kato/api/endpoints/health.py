"""
Health and Status Endpoints

Handles system health checks and status reporting.
"""

import time
import logging
from datetime import datetime, timezone

from fastapi import APIRouter

router = APIRouter(tags=["health"])
logger = logging.getLogger('kato.api.health')


@router.get("/status")
async def get_system_status():
    """Get overall system status including session statistics"""
    from kato.services.kato_fastapi import app_state
    
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


@router.get("/health")
async def health_check():
    """Enhanced health check endpoint for v2 with metrics integration"""
    from kato.services.kato_fastapi import app_state
    
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
                "active_sessions": await app_state.session_manager.get_active_session_count_async(),
                "timestamp": datetime.now(timezone.utc).isoformat()
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
                "active_sessions": await app_state.session_manager.get_active_session_count_async(),
                "timestamp": datetime.now(timezone.utc).isoformat()
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
            "timestamp": datetime.now(timezone.utc).isoformat()
        }