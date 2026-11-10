"""
clear_stm_between drops the emotives and metadata of the events it clears.

observe-sequence's isolation mode emptied the STM before each observation and
left the session's emotives and metadata accumulators alone. The accumulators
hold what was observed with the events in the STM, so the fields of a cleared
observation stayed behind and were stored with the next pattern learned in the
session - a pattern that observation is not part of. learn_after_each hid this,
because each learn resets the accumulators.

Clearing now goes through SessionState.discard_stm, which empties the STM and
both accumulators together. The clear-stm endpoint drops events the same way, so
both session managers call it too.

The endpoint tests run the real observe-sequence endpoint, KatoProcessor.observe
and learn, and ObservationProcessor. Only storage is faked: learn_pattern_from
records what would be stored with each pattern.
"""

import os
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from kato.api.endpoints import sessions as sessions_endpoint
from kato.api.schemas.observation import ObservationDataItem, ObservationSequenceRequest
from kato.config.session_config import SessionConfiguration
from kato.services import kato_fastapi
from kato.sessions.redis_session_manager import RedisSessionManager
from kato.sessions.session_manager import SessionManager, SessionState
from kato.workers.kato_processor import KatoProcessor
from kato.workers.observation_processor import ObservationProcessor

FIRST = {'strings': ['a1', 'a2'], 'emotives': {'alert': 0.0}, 'metadata': {'source': 'A'}}
SECOND = {'strings': ['b1', 'b2'], 'emotives': {'alert': 1.0}, 'metadata': {'source': 'B'}}
THIRD = {'strings': ['c1', 'c2'], 'emotives': {'alert': 0.5}, 'metadata': {'source': 'C'}}


def _session(**overrides) -> SessionState:
    now = datetime.now(timezone.utc)
    state = SessionState(
        session_id='s1',
        node_id='n1',
        created_at=now,
        last_accessed=now,
        expires_at=now + timedelta(hours=1),
        session_config=SessionConfiguration(process_predictions=False),
    )
    for key, value in overrides.items():
        setattr(state, key, value)
    return state


# ── SessionState.discard_stm ───────────────────────────────────────────

def test_discard_stm_empties_stm_and_resets_accumulators():
    state = _session(
        stm=[['a'], ['b']],
        emotives_accumulator=[{'joy': 0.5}, {'joy': 0.7}],
        metadata_accumulator=[{'source': 'x'}],
    )
    state.discard_stm()
    assert state.stm == []
    assert state.emotives_accumulator == []
    assert state.metadata_accumulator == []


def test_discard_stm_leaves_other_session_state_alone():
    state = _session(stm=[['a']], time=7, percept_data={'k': 'v'}, predictions=['p'])
    state.discard_stm()
    assert state.time == 7
    assert state.percept_data == {'k': 'v'}
    assert state.predictions == ['p']


def test_discarded_accumulators_are_fresh_lists_not_shared():
    first, second = _session(), _session()
    first.discard_stm()
    second.discard_stm()
    first.emotives_accumulator.append({'joy': 1.0})
    first.metadata_accumulator.append({'source': 'x'})
    assert second.emotives_accumulator == []
    assert second.metadata_accumulator == []


# ── observe-sequence with clear_stm_between ────────────────────────────

class _RecordingPatternOperations:
    """Stands in for storage: records what would be stored with each pattern."""

    def __init__(self):
        self.stored = []

    def learn_pattern_from(self, stm, emotives, metadata):
        self.stored.append((
            [list(event) for event in stm],
            [dict(entry) for entry in emotives],
            [dict(entry) for entry in metadata],
        ))
        return f'PTRN|{len(self.stored)}'


@pytest.fixture
def isolation_run(monkeypatch):
    """
    A session on a node whose processor runs the real observe and learn code.

    Returns (session, stored): the session the endpoint updates, and the list of
    (events, emotives, metadata) that each learn would have written to storage.
    """
    session = _session()
    pattern_operations = _RecordingPatternOperations()

    pattern_processor = Mock()
    pattern_processor.stm_mode = 'CLEAR'
    pattern_processor.predict_from = AsyncMock(return_value=[])

    processor = object.__new__(KatoProcessor)
    processor.id = 'p'
    processor.distributed_stm_manager = None
    processor.pattern_operations = pattern_operations
    processor.observation_processor = ObservationProcessor(
        vector_processor=Mock(),
        pattern_processor=pattern_processor,
        memory_manager=Mock(),
        pattern_operations=pattern_operations,
        sort_symbols=True,
        max_pattern_length=0,
        process_predictions=False,
    )

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
            return True

    class FakeProcessorManager:
        async def get_processor(self, node_id, config):
            return processor

    monkeypatch.setattr(
        kato_fastapi, 'app_state',
        SimpleNamespace(session_manager=FakeSessionManager(),
                        processor_manager=FakeProcessorManager()),
        raising=False,
    )
    return session, pattern_operations.stored


async def _observe_sequence(observations, **flags):
    return await sessions_endpoint.observe_sequence_in_session(
        's1',
        ObservationSequenceRequest(
            observations=[ObservationDataItem(**observation) for observation in observations],
            **flags,
        ),
    )


@pytest.mark.asyncio
async def test_pattern_learned_after_a_clear_carries_only_its_own_fields(isolation_run):
    """The cleared observation is not in the pattern, so neither are its fields."""
    session, stored = isolation_run

    result = await _observe_sequence([FIRST, SECOND], clear_stm_between=True, learn_at_end=True)

    assert result.isolated is True
    assert stored == [
        ([['b1', 'b2']], [{'alert': 1.0}], [{'source': 'B'}]),
    ]
    assert session.stm == []
    assert session.emotives_accumulator == []
    assert session.metadata_accumulator == []


@pytest.mark.asyncio
async def test_isolation_without_learning_keeps_only_the_last_observations_fields(isolation_run):
    """What the session holds afterwards describes the one event left in the STM."""
    session, stored = isolation_run

    await _observe_sequence([FIRST, SECOND], clear_stm_between=True)

    assert stored == []
    assert session.stm == [['b1', 'b2']]
    assert session.emotives_accumulator == [{'alert': 1.0}]
    assert session.metadata_accumulator == [{'source': 'B'}]
    # The percept reports this observation's emotives, not an average that
    # includes the observation that was cleared.
    assert session.percept_data['emotives'] == {'alert': 1.0}


@pytest.mark.asyncio
async def test_cleared_fields_do_not_reach_a_pattern_learned_by_a_later_request(isolation_run):
    session, stored = isolation_run

    await _observe_sequence([FIRST, SECOND], clear_stm_between=True)
    await _observe_sequence([THIRD], learn_at_end=True)

    # SECOND is still in the STM when THIRD arrives, so both belong to the
    # pattern. FIRST was cleared and contributes nothing.
    assert stored == [
        (
            [['b1', 'b2'], ['c1', 'c2']],
            [{'alert': 1.0}, {'alert': 0.5}],
            [{'source': 'B'}, {'source': 'C'}],
        ),
    ]


@pytest.mark.asyncio
async def test_isolation_with_learn_after_each_gives_each_pattern_its_own_fields(isolation_run):
    session, stored = isolation_run

    await _observe_sequence([FIRST, SECOND], clear_stm_between=True, learn_after_each=True)

    assert stored == [
        ([['a1', 'a2']], [{'alert': 0.0}], [{'source': 'A'}]),
        ([['b1', 'b2']], [{'alert': 1.0}], [{'source': 'B'}]),
    ]
    assert session.emotives_accumulator == []
    assert session.metadata_accumulator == []


@pytest.mark.asyncio
async def test_without_isolation_fields_still_accumulate_across_the_sequence(isolation_run):
    """Nothing is cleared, so the pattern holds both events and both events' fields."""
    session, stored = isolation_run

    result = await _observe_sequence([FIRST, SECOND], learn_at_end=True)

    assert result.isolated is False
    assert stored == [
        (
            [['a1', 'a2'], ['b1', 'b2']],
            [{'alert': 0.0}, {'alert': 1.0}],
            [{'source': 'A'}, {'source': 'B'}],
        ),
    ]


# ── clear-stm ──────────────────────────────────────────────────────────

def _held_session() -> SessionState:
    return _session(
        stm=[['a'], ['b']],
        emotives_accumulator=[{'joy': 0.5}],
        metadata_accumulator=[{'source': 'x'}],
        time=7,
        percept_data={'k': 'v'},
        predictions=['p'],
    )


def _assert_cleared(session: SessionState) -> None:
    assert session.stm == []
    assert session.emotives_accumulator == []
    assert session.metadata_accumulator == []
    assert session.time == 0
    assert session.percept_data == {}
    assert session.predictions == []


@pytest.mark.asyncio
async def test_clear_session_stm_resets_everything_the_session_holds():
    manager = SessionManager()
    session = _held_session()
    manager.sessions[session.session_id] = session

    assert await manager.clear_session_stm(session.session_id) is True
    _assert_cleared(session)
    assert await manager.clear_session_stm('missing') is False


@pytest.mark.asyncio
async def test_redis_clear_session_stm_resets_and_saves_the_session():
    session = _held_session()
    manager = object.__new__(RedisSessionManager)
    manager.get_session = AsyncMock(return_value=session)
    manager.update_session = AsyncMock(return_value=True)

    assert await manager.clear_session_stm(session.session_id) is True
    _assert_cleared(session)
    manager.update_session.assert_awaited_once_with(session)
