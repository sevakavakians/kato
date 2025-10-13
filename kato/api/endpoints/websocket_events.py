"""
WebSocket Events Endpoint

Provides real-time event streaming for KATO Dashboard and other clients.
Implements the WebSocket event specification from KATO_WEBSOCKET_REQUIREMENTS.md.
"""

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from kato.websocket import get_event_broadcaster

router = APIRouter(tags=["websocket"])
logger = logging.getLogger('kato.api.websocket_events')


@router.websocket("/ws/events")
async def websocket_events_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time event streaming.

    This endpoint allows clients to receive real-time notifications about:
    - Session creation/destruction events
    - System errors
    - Metrics updates (optional)

    Connection Lifecycle:
    1. Client connects to ws://kato:8000/ws/events
    2. Server sends initial state snapshot
    3. Server pushes events as they occur
    4. Client sends heartbeat/ping every 30s
    5. Server responds with pong
    6. Either side can close connection

    Event Format:
    {
        "event_type": "session.created|session.destroyed|system.error|heartbeat",
        "timestamp": "2025-10-11T15:30:45.123Z",
        "data": {...}
    }

    Query Parameters:
        token: Optional JWT authentication token (not implemented yet)

    Based on requirements specification lines 146-162, 323-360.
    """
    broadcaster = get_event_broadcaster()

    # Accept and register the connection
    await broadcaster.connect(websocket)

    logger.info(f"WebSocket client connected. Active connections: {broadcaster.get_connection_count()}")

    try:
        # Keep connection alive and handle client messages
        while True:
            # Receive messages from client (ping/pong, commands)
            data = await websocket.receive_text()

            # Handle ping/pong for keep-alive
            if data == "ping":
                await websocket.send_text("pong")
                logger.debug("Responded to ping with pong")

            # Can extend this to handle other commands later
            # e.g., subscription filtering, authentication refresh, etc.

    except WebSocketDisconnect:
        broadcaster.disconnect(websocket)
        logger.info(f"WebSocket client disconnected. Active connections: {broadcaster.get_connection_count()}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        broadcaster.disconnect(websocket)
        try:
            await websocket.close()
        except Exception:
            pass
