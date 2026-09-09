"""
Unit tests for EventBroadcaster transport selection.

The cross-worker behaviour itself is covered end-to-end per KATO_WORKERS in
tests/tests/integration/test_worker_topology.py. These tests pin the transport
rules with fakes, without Redis or a server:

- No Redis configured → events go straight to local connections.
- Redis active → `broadcast_event` publishes exactly once and does NOT also
  deliver locally (the listener does that, so clients never see duplicates).
- Publish failure → falls back to local delivery.
- Whatever the listener receives is delivered to local connections.
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from kato.websocket.event_broadcaster import EventBroadcaster

EVENT = {"event_type": "session.created", "timestamp": "t", "data": {"session_id": "s1"}}


class FakeWebSocket:
    def __init__(self, fail=False):
        self.sent = []
        self.fail = fail

    async def send_text(self, message):
        if self.fail:
            raise ConnectionError("gone")
        self.sent.append(json.loads(message))


class FakeRedis:
    def __init__(self, fail=False):
        self.published = []
        self.fail = fail

    async def publish(self, channel, payload):
        if self.fail:
            raise ConnectionError("redis down")
        self.published.append((channel, json.loads(payload)))


@pytest.fixture
def broadcaster():
    return EventBroadcaster()


async def test_local_delivery_without_redis(broadcaster):
    ws = FakeWebSocket()
    broadcaster.active_connections.append(ws)

    assert broadcaster.transport == 'local'
    await broadcaster.broadcast_event(EVENT)

    assert ws.sent == [EVENT]


async def test_publishes_once_and_does_not_double_deliver_with_redis(broadcaster):
    ws = FakeWebSocket()
    broadcaster.active_connections.append(ws)
    fake_redis = FakeRedis()
    broadcaster._redis = fake_redis

    assert broadcaster.transport == 'redis'
    await broadcaster.broadcast_event(EVENT)

    assert fake_redis.published == [(broadcaster._channel, EVENT)]
    # Delivery to this worker's clients happens via the listener, not here
    assert ws.sent == []


async def test_falls_back_to_local_delivery_when_publish_fails(broadcaster):
    ws = FakeWebSocket()
    broadcaster.active_connections.append(ws)
    broadcaster._redis = FakeRedis(fail=True)

    await broadcaster.broadcast_event(EVENT)

    assert ws.sent == [EVENT]


async def test_listener_side_delivery_reaches_all_local_clients(broadcaster):
    ws1, ws2 = FakeWebSocket(), FakeWebSocket()
    broadcaster.active_connections.extend([ws1, ws2])

    await broadcaster._deliver_locally(EVENT)

    assert ws1.sent == [EVENT]
    assert ws2.sent == [EVENT]


async def test_dead_connections_are_pruned_on_delivery(broadcaster):
    alive, dead = FakeWebSocket(), FakeWebSocket(fail=True)
    broadcaster.active_connections.extend([dead, alive])

    await broadcaster._deliver_locally(EVENT)

    assert alive.sent == [EVENT]
    assert broadcaster.active_connections == [alive]


async def test_start_without_url_stays_local(broadcaster):
    await broadcaster.start(None)
    assert broadcaster.transport == 'local'
    await broadcaster.stop()  # must be safe when nothing was started
