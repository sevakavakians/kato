"""
Event Broadcasting System for KATO WebSocket Events

This module provides real-time event streaming to connected WebSocket clients.
It implements the broadcaster pattern to efficiently send events to multiple clients.
"""

import json
import logging
from datetime import datetime
from typing import Any, List

from fastapi import WebSocket

logger = logging.getLogger('kato.websocket.broadcaster')


class EventBroadcaster:
    """
    Manages WebSocket connections and event broadcasting.

    This class maintains a list of active WebSocket connections and provides
    methods to broadcast events to all connected clients. It handles connection
    lifecycle, disconnections, and ensures reliable event delivery.

    Based on KATO WebSocket Requirements specification (lines 272-320).
    """

    def __init__(self):
        """Initialize the broadcaster with an empty connection list"""
        self.active_connections: List[WebSocket] = []
        logger.info("EventBroadcaster initialized")

    async def connect(self, websocket: WebSocket) -> None:
        """
        Accept and register a new WebSocket connection.

        Args:
            websocket: The WebSocket connection to register
        """
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket connected. Active connections: {len(self.active_connections)}")

        # Send initial state snapshot (optional)
        await self.send_initial_state(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        """
        Remove a WebSocket connection from the active list.

        Args:
            websocket: The WebSocket connection to remove
        """
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"WebSocket disconnected. Active connections: {len(self.active_connections)}")

    async def broadcast_event(self, event: dict[str, Any]) -> None:
        """
        Broadcast an event to all connected clients.

        This method sends the event to all active WebSocket connections.
        Connections that fail to receive the event are automatically disconnected.

        Args:
            event: Event dictionary following the KATOEvent schema:
                {
                    "event_type": "session.created|session.destroyed|...",
                    "timestamp": "2025-10-11T15:30:45.123Z",
                    "data": {...}
                }
        """
        if not self.active_connections:
            logger.debug(f"No active connections to broadcast event: {event.get('event_type')}")
            return

        message = json.dumps(event)
        disconnected = []

        logger.debug(f"Broadcasting event '{event.get('event_type')}' to {len(self.active_connections)} clients")

        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception as e:
                logger.warning(f"Failed to send event to connection: {e}")
                disconnected.append(connection)

        # Clean up disconnected clients
        for conn in disconnected:
            self.disconnect(conn)

        logger.debug(f"Event broadcast complete. Removed {len(disconnected)} dead connections")

    async def send_initial_state(self, websocket: WebSocket) -> None:
        """
        Send current state snapshot to newly connected client.

        This provides the client with initial system state upon connection,
        allowing them to sync their view before receiving incremental updates.

        Args:
            websocket: The newly connected WebSocket
        """
        try:
            # Import here to avoid circular dependency
            from kato.services.kato_fastapi import app_state

            # Get current active session count
            session_count = await app_state.session_manager.get_active_session_count_async()

            state = {
                "event_type": "state.snapshot",
                "timestamp": datetime.now().isoformat(),
                "data": {
                    "active_sessions": session_count,
                    "system_status": "healthy"
                }
            }
            await websocket.send_text(json.dumps(state))
            logger.debug(f"Sent initial state snapshot: {session_count} active sessions")
        except Exception as e:
            logger.warning(f"Failed to send initial state: {e}")

    def get_connection_count(self) -> int:
        """
        Get the number of active WebSocket connections.

        Returns:
            Number of active connections
        """
        return len(self.active_connections)


# Global broadcaster instance (singleton pattern)
_broadcaster_instance: EventBroadcaster | None = None


def get_event_broadcaster() -> EventBroadcaster:
    """
    Get or create the global EventBroadcaster singleton.

    This ensures all parts of the application use the same broadcaster instance,
    maintaining a single list of WebSocket connections.

    Returns:
        The global EventBroadcaster instance
    """
    global _broadcaster_instance
    if _broadcaster_instance is None:
        _broadcaster_instance = EventBroadcaster()
        logger.info("Created global EventBroadcaster instance")
    return _broadcaster_instance
