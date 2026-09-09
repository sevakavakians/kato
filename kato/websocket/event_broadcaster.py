"""
Event Broadcasting System for KATO WebSocket Events

This module provides real-time event streaming to connected WebSocket clients.
It implements the broadcaster pattern to efficiently send events to multiple clients.

Cross-worker delivery
---------------------
KATO runs several uvicorn worker processes. Each worker holds only the WebSocket
connections it accepted, so an event raised in one worker (e.g. a session created
by an HTTP request it served) must reach the clients held by every other worker.

When Redis is configured, `broadcast_event` publishes the event to a Redis
pub/sub channel and every worker — including the publishing one — delivers what
it receives on that channel to its own local connections. This gives exactly-one
delivery per client regardless of which worker served the request. Without Redis
(single-process or Redis-less deployments) events are delivered locally, which
is complete for a single worker.
"""

import asyncio
import contextlib
import json
import logging
import os
from datetime import datetime
from typing import Any, Optional

from fastapi import WebSocket

try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:  # pragma: no cover - redis is a hard dependency in practice
    redis = None
    REDIS_AVAILABLE = False

logger = logging.getLogger('kato.websocket.broadcaster')

# Redis pub/sub channel carrying WebSocket events between worker processes.
EVENTS_CHANNEL = os.environ.get('KATO_WS_EVENTS_CHANNEL', 'kato:ws_events')

# Seconds to wait for Redis to confirm the channel subscription at startup.
_SUBSCRIBE_TIMEOUT = 5.0
# Backoff between listener reconnect attempts after a Redis error.
_RECONNECT_DELAY = 1.0


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
        self.active_connections: list[WebSocket] = []
        self._redis: Optional[Any] = None  # redis.asyncio.Redis when started
        self._pubsub = None
        self._listener_task: Optional[asyncio.Task] = None
        self._channel = EVENTS_CHANNEL
        logger.info("EventBroadcaster initialized")

    # ------------------------------------------------------------------
    # Transport lifecycle
    # ------------------------------------------------------------------

    @property
    def transport(self) -> str:
        """'redis' when events fan out across workers, 'local' otherwise."""
        return 'redis' if self._redis is not None else 'local'

    async def start(self, redis_url: Optional[str]) -> None:
        """
        Enable cross-worker delivery through Redis pub/sub.

        Subscribes this process to the events channel and starts the listener
        that delivers received events to local connections. Returns only once
        Redis has confirmed the subscription, so no event published after
        startup can be missed. Without a URL (or if Redis is unreachable) the
        broadcaster stays in local mode and logs why.

        Args:
            redis_url: Redis connection URL, or None for local-only delivery.
        """
        if self._redis is not None:
            return
        if not redis_url:
            logger.info("EventBroadcaster: no REDIS_URL, events delivered to local connections only")
            return
        if not REDIS_AVAILABLE:
            logger.warning("EventBroadcaster: redis.asyncio unavailable, events delivered to local connections only")
            return

        client = redis.from_url(redis_url, encoding="utf-8", decode_responses=True)
        pubsub = client.pubsub()
        try:
            await client.ping()
            await pubsub.subscribe(self._channel)
            await self._await_subscription_ack(pubsub)
        except Exception as e:
            logger.error(f"EventBroadcaster: Redis pub/sub unavailable ({e}); "
                         "events delivered to local connections only")
            await self._close_transport(client, pubsub)
            return

        self._redis = client
        self._pubsub = pubsub
        self._listener_task = asyncio.create_task(self._listen(), name="ws-events-listener")
        logger.info(f"EventBroadcaster: cross-worker delivery enabled on channel '{self._channel}' (pid {os.getpid()})")

    async def stop(self) -> None:
        """Stop the listener and release the Redis connections."""
        task, self._listener_task = self._listener_task, None
        if task:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        client, pubsub = self._redis, self._pubsub
        self._redis, self._pubsub = None, None
        await self._close_transport(client, pubsub)

    async def _await_subscription_ack(self, pubsub) -> None:
        """Block until Redis acknowledges the SUBSCRIBE, so the listener is live."""
        deadline = asyncio.get_running_loop().time() + _SUBSCRIBE_TIMEOUT
        while asyncio.get_running_loop().time() < deadline:
            message = await pubsub.get_message(ignore_subscribe_messages=False, timeout=1.0)
            if message and message.get('type') == 'subscribe':
                return
        raise TimeoutError(f"no subscribe acknowledgement for '{self._channel}' within {_SUBSCRIBE_TIMEOUT}s")

    async def _close_transport(self, client, pubsub) -> None:
        if pubsub is not None:
            with contextlib.suppress(Exception):
                await pubsub.unsubscribe(self._channel)
            with contextlib.suppress(Exception):
                await pubsub.aclose()
        if client is not None:
            with contextlib.suppress(Exception):
                await client.aclose()

    async def _listen(self) -> None:
        """Deliver every event published on the channel to local connections.

        Runs for the life of the worker. A Redis error drops the subscription;
        the loop re-subscribes after a short delay rather than leaving this
        worker's clients silently cut off.
        """
        while True:
            try:
                while True:
                    message = await self._pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                    if message is None:
                        continue
                    try:
                        event = json.loads(message['data'])
                    except (TypeError, ValueError) as e:
                        logger.warning(f"EventBroadcaster: ignoring malformed event on '{self._channel}': {e}")
                        continue
                    await self._deliver_locally(event)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning(f"EventBroadcaster: listener lost Redis subscription ({e}); reconnecting")
                await asyncio.sleep(_RECONNECT_DELAY)
                with contextlib.suppress(Exception):
                    await self._pubsub.subscribe(self._channel)

    # ------------------------------------------------------------------
    # Connections
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Broadcasting
    # ------------------------------------------------------------------

    async def broadcast_event(self, event: dict[str, Any]) -> None:
        """
        Broadcast an event to all connected clients on every worker.

        With Redis, the event is published once and each worker's listener
        (this one included) delivers it to the connections it holds — so the
        publishing worker must not also deliver locally, or its clients would
        see the event twice. If publishing fails, fall back to local delivery
        so at least this worker's clients are served.

        Args:
            event: Event dictionary following the KATOEvent schema:
                {
                    "event_type": "session.created|session.destroyed|...",
                    "timestamp": "2025-10-11T15:30:45.123Z",
                    "data": {...}
                }
        """
        if self._redis is None:
            await self._deliver_locally(event)
            return

        try:
            await self._redis.publish(self._channel, json.dumps(event))
            logger.debug(f"Published event '{event.get('event_type')}' to '{self._channel}'")
        except Exception as e:
            logger.warning(f"EventBroadcaster: publish failed ({e}); delivering to local connections only")
            await self._deliver_locally(event)

    async def _deliver_locally(self, event: dict[str, Any]) -> None:
        """Send an event to every connection held by this worker process."""
        if not self.active_connections:
            logger.debug(f"No active connections to deliver event: {event.get('event_type')}")
            return

        message = json.dumps(event)
        disconnected = []

        logger.debug(f"Delivering event '{event.get('event_type')}' to {len(self.active_connections)} clients")

        for connection in list(self.active_connections):
            try:
                await connection.send_text(message)
            except Exception as e:
                logger.warning(f"Failed to send event to connection: {e}")
                disconnected.append(connection)

        # Clean up disconnected clients
        for conn in disconnected:
            self.disconnect(conn)

        logger.debug(f"Event delivery complete. Removed {len(disconnected)} dead connections")

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
                    "system_status": "healthy",
                    # Which uvicorn worker process owns this connection. Lets
                    # clients (and tests) reason about cross-worker delivery.
                    "worker_pid": os.getpid()
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
