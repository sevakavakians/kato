"""
A manual learn resets the session's emotives and metadata accumulators.

The learn endpoint used to replace the session's STM and nothing else, so the
emotives and metadata accumulated for one pattern carried into the next pattern
learned in the same session. Only clear-stm reset them. The legacy stateful
learn() reset both after every learn; the stateless rewrite dropped that.

Learning consumes everything accumulated for the pattern, so every session-level
learn (POST /learn, and observe-sequence's learn_after_each / learn_at_end) now
goes through SessionState.apply_learn_result.
"""

import os
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from kato.sessions.session_manager import SessionState


def _session(**overrides) -> SessionState:
    now = datetime.now(timezone.utc)
    state = SessionState(
        session_id='s1',
        node_id='n1',
        created_at=now,
        last_accessed=now,
        expires_at=now + timedelta(hours=1),
        stm=[['a'], ['b']],
        emotives_accumulator=[{'joy': 0.5}, {'joy': 0.7}],
        metadata_accumulator=[{'source': 'x'}],
    )
    for key, value in overrides.items():
        setattr(state, key, value)
    return state


def test_apply_learn_result_replaces_stm_and_resets_accumulators():
    state = _session()
    state.apply_learn_result([['b']])
    assert state.stm == [['b']]
    assert state.emotives_accumulator == []
    assert state.metadata_accumulator == []


def test_apply_learn_result_leaves_other_session_state_alone():
    state = _session(time=7, percept_data={'k': 'v'})
    state.apply_learn_result([])
    assert state.time == 7
    assert state.percept_data == {'k': 'v'}


def test_reset_accumulators_are_fresh_lists_not_shared():
    first, second = _session(), _session()
    first.apply_learn_result([])
    second.apply_learn_result([])
    first.emotives_accumulator.append({'joy': 1.0})
    assert second.emotives_accumulator == []


@pytest.mark.asyncio
async def test_learn_endpoint_resets_accumulators(monkeypatch):
    """POST /sessions/{id}/learn leaves no emotives or metadata behind."""
    from kato.api.endpoints import sessions as sessions_endpoint
    from kato.services import kato_fastapi

    session = _session()
    saved = []

    class FakeProcessor:
        async def learn(self, *, session_state, keep_tail=False):
            return 'PTRN|abc', []

    class FakeLock:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    class FakeSessionManager:
        async def get_session(self, session_id):
            return session

        async def get_session_lock(self, session_id):
            return FakeLock()

        async def update_session(self, state):
            # Snapshot what would be persisted.
            saved.append((list(state.stm),
                          list(state.emotives_accumulator),
                          list(state.metadata_accumulator)))
            return True

    class FakeProcessorManager:
        async def get_processor(self, node_id, config):
            return FakeProcessor()

    monkeypatch.setattr(
        kato_fastapi, 'app_state',
        SimpleNamespace(session_manager=FakeSessionManager(),
                        processor_manager=FakeProcessorManager()),
        raising=False,
    )

    result = await sessions_endpoint.learn_in_session('s1')

    assert result.status == 'learned'
    assert saved == [([], [], [])]
    assert session.emotives_accumulator == []
    assert session.metadata_accumulator == []
