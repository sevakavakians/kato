"""
Integration Tests for WebSocket Event Notifications

Tests the real-time event streaming functionality per KATO_WEBSOCKET_REQUIREMENTS.md.
These tests verify:
- WebSocket connection lifecycle
- Heartbeat/ping-pong mechanism
- Disconnect cleanup

Event delivery (session.created / session.destroyed reaching every connected
client) depends on which uvicorn worker holds the connection versus which one
serves the HTTP request, so it is covered per worker count in
test_worker_topology.py rather than against the shared service here.
"""

import asyncio
import json
import logging

import pytest
import requests
import websockets

logger = logging.getLogger(__name__)

# KATO service URL for testing - use environment variable or default
import os

KATO_BASE_URL = os.environ.get("KATO_BASE_URL", "http://localhost:8000")
KATO_WS_URL = KATO_BASE_URL.replace("http://", "ws://").replace("https://", "wss://")


@pytest.mark.asyncio
class TestWebSocketEvents:
    """Test WebSocket event streaming functionality"""

    async def test_websocket_connection(self):
        """Test basic WebSocket connection and initial state snapshot"""
        async with websockets.connect(f"{KATO_WS_URL}/ws/events") as websocket:
            # Should receive initial state snapshot
            data = await websocket.recv()
            event = json.loads(data)

            assert event["event_type"] == "state.snapshot"
            assert "timestamp" in event
            assert "data" in event
            assert "active_sessions" in event["data"]
            assert "system_status" in event["data"]
            assert event["data"]["system_status"] == "healthy"

            logger.info(f"Initial state: {event}")

    async def test_websocket_ping_pong(self):
        """Test heartbeat/ping-pong mechanism"""
        async with websockets.connect(f"{KATO_WS_URL}/ws/events") as websocket:
            # Receive initial state
            await websocket.recv()

            # Send ping
            await websocket.send("ping")

            # Should receive pong
            response = await websocket.recv()
            assert response == "pong"

            logger.info("Ping-pong successful")

    async def test_websocket_disconnect_cleanup(self):
        """Test that disconnected clients are properly cleaned up"""
        # Connect and immediately disconnect
        async with websockets.connect(f"{KATO_WS_URL}/ws/events") as websocket:
            # Receive initial state
            await websocket.recv()
            # Connection will be closed when exiting context

        # Wait a bit for cleanup
        await asyncio.sleep(0.5)

        # Create a session - should not error even though client disconnected
        response = requests.post(f"{KATO_BASE_URL}/sessions", json={
            "node_id": "test_disconnect",
            "config": {},
            "metadata": {},
            "ttl_seconds": 60
        })
        assert response.status_code == 200
        session_id = response.json()["session_id"]

        logger.info("✅ Session creation succeeded after client disconnect")

        # Cleanup
        requests.delete(f"{KATO_BASE_URL}/sessions/{session_id}")

