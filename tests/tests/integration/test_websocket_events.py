"""
Integration Tests for WebSocket Event Notifications

Tests the real-time event streaming functionality per KATO_WEBSOCKET_REQUIREMENTS.md.
These tests verify:
- WebSocket connection lifecycle
- Session created events
- Session destroyed events
- Heartbeat/ping-pong mechanism
- Multiple concurrent connections
"""

import asyncio
import json
import logging

import pytest
import requests
import websockets

logger = logging.getLogger(__name__)

# KATO service URL for testing
KATO_BASE_URL = "http://localhost:8000"
KATO_WS_URL = "ws://localhost:8000"


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

    async def test_session_created_event(self):
        """Test that session.created event is broadcast when session is created"""
        # Connect to WebSocket first
        async with websockets.connect(f"{KATO_WS_URL}/ws/events") as websocket:
            # Receive initial state
            initial_state = await websocket.recv()
            logger.info(f"Initial state received: {initial_state}")

            # Create a session via HTTP
            response = requests.post(f"{KATO_BASE_URL}/sessions", json={
                "node_id": "test_ws_node",
                "config": {},
                "metadata": {"test": "websocket_event"},
                "ttl_seconds": 60
            })
            assert response.status_code == 200
            session_data = response.json()
            session_id = session_data["session_id"]

            logger.info(f"Created session: {session_id}")

            # Should receive session.created event via WebSocket
            try:
                # Set a reasonable timeout for event delivery
                event_data = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                event = json.loads(event_data)

                logger.info(f"Received event: {event}")

                assert event["event_type"] == "session.created"
                assert "timestamp" in event
                assert "data" in event
                assert event["data"]["session_id"] == session_id
                assert event["data"]["node_id"] == "test_ws_node"
                assert "created_at" in event["data"]

                logger.info(f"✅ session.created event received for {session_id}")

            except asyncio.TimeoutError:
                pytest.fail("Did not receive session.created event within 5 seconds")

            # Cleanup: delete the session
            delete_response = requests.delete(f"{KATO_BASE_URL}/sessions/{session_id}")
            assert delete_response.status_code == 200

    async def test_session_destroyed_event(self):
        """Test that session.destroyed event is broadcast when session is deleted"""
        # Create a session first
        response = requests.post(f"{KATO_BASE_URL}/sessions", json={
            "node_id": "test_ws_delete",
            "config": {},
            "metadata": {},
            "ttl_seconds": 60
        })
        assert response.status_code == 200
        session_data = response.json()
        session_id = session_data["session_id"]

        logger.info(f"Created session for deletion test: {session_id}")

        # Connect to WebSocket
        async with websockets.connect(f"{KATO_WS_URL}/ws/events") as websocket:
            # Receive initial state
            await websocket.recv()

            # Delete the session via HTTP
            delete_response = requests.delete(f"{KATO_BASE_URL}/sessions/{session_id}")
            assert delete_response.status_code == 200

            logger.info(f"Deleted session: {session_id}")

            # Should receive session.destroyed event via WebSocket
            try:
                event_data = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                event = json.loads(event_data)

                logger.info(f"Received event: {event}")

                assert event["event_type"] == "session.destroyed"
                assert "timestamp" in event
                assert "data" in event
                assert event["data"]["session_id"] == session_id
                assert "destroyed_at" in event["data"]
                assert event["data"]["reason"] == "explicit_delete"

                logger.info(f"✅ session.destroyed event received for {session_id}")

            except asyncio.TimeoutError:
                pytest.fail("Did not receive session.destroyed event within 5 seconds")

    async def test_multiple_websocket_connections(self):
        """Test that events are broadcast to multiple connected clients"""
        # Create two WebSocket connections
        async with websockets.connect(f"{KATO_WS_URL}/ws/events") as ws1, \
                   websockets.connect(f"{KATO_WS_URL}/ws/events") as ws2:

            # Receive initial states
            await ws1.recv()
            await ws2.recv()

            # Create a session
            response = requests.post(f"{KATO_BASE_URL}/sessions", json={
                "node_id": "test_multi_ws",
                "config": {},
                "metadata": {},
                "ttl_seconds": 60
            })
            assert response.status_code == 200
            session_id = response.json()["session_id"]

            logger.info(f"Created session for multi-client test: {session_id}")

            # Both connections should receive the event
            event1_data = await asyncio.wait_for(ws1.recv(), timeout=5.0)
            event1 = json.loads(event1_data)

            event2_data = await asyncio.wait_for(ws2.recv(), timeout=5.0)
            event2 = json.loads(event2_data)

            # Both should receive the same event
            assert event1["event_type"] == "session.created"
            assert event2["event_type"] == "session.created"
            assert event1["data"]["session_id"] == session_id
            assert event2["data"]["session_id"] == session_id

            logger.info("✅ Event broadcast to multiple clients successful")

            # Cleanup
            requests.delete(f"{KATO_BASE_URL}/sessions/{session_id}")

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


@pytest.mark.asyncio
class TestQuickStartExample:
    """
    Test the Quick Start Guide example from requirements (lines 957-1000)

    This is a minimal implementation example that developers can use.
    """

    async def test_quick_start_websocket_example(self):
        """
        Test the minimal WebSocket implementation from Quick Start Guide.

        This demonstrates the basic usage pattern for dashboard integration.
        """
        async with websockets.connect(f"{KATO_WS_URL}/ws/events") as ws:
            # 1. Connect and receive initial state
            initial = json.loads(await ws.recv())
            assert initial["event_type"] == "state.snapshot"

            # 2. Create session
            session_response = requests.post(f"{KATO_BASE_URL}/sessions", json={
                "node_id": "quickstart_node",
                "config": {},
                "metadata": {},
                "ttl_seconds": 60
            })
            session_id = session_response.json()["session_id"]

            # 3. Receive session.created event
            created_event = json.loads(await asyncio.wait_for(ws.recv(), timeout=5.0))
            assert created_event["event_type"] == "session.created"
            assert created_event["data"]["session_id"] == session_id

            # 4. Delete session
            requests.delete(f"{KATO_BASE_URL}/sessions/{session_id}")

            # 5. Receive session.destroyed event
            destroyed_event = json.loads(await asyncio.wait_for(ws.recv(), timeout=5.0))
            assert destroyed_event["event_type"] == "session.destroyed"
            assert destroyed_event["data"]["session_id"] == session_id

            logger.info("✅ Quick Start Guide example completed successfully")
