"""
A manual learn resets the session's emotives and metadata accumulators.

The learn endpoint used to replace the session's STM and nothing else, so the
emotives and metadata accumulated for one pattern carried into the next pattern
learned in the same session. Only clear-stm reset them. The legacy stateful
learn() reset both after every learn; the stateless rewrite dropped that.

Learning consumes everything accumulated for the pattern, so every session-level
learn (POST /learn, and observe-sequence's learn_after_each / learn_at_end) now
goes through SessionState.apply_learn_result.

Auto-learning (max_pattern_length reached inside observe) is the same event: the
pattern is stored with the session's emotives and metadata, including those of
the observation that triggered it, and the accumulators are reset afterwards.
"""

import os
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from kato.config.session_config import SessionConfiguration
from kato.sessions.session_manager import SessionState
from kato.workers.kato_processor import KatoProcessor
from kato.workers.observation_processor import ObservationProcessor


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
        async def learn(self, *, session_state):
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


# ── auto-learn ─────────────────────────────────────────────────────────

def _observation_processor(learned_name='PTRN|x'):
    pattern_operations = Mock()
    pattern_operations.learn_pattern_from.return_value = learned_name
    pattern_processor = Mock()
    pattern_processor.stm_mode = 'CLEAR'
    pattern_processor.predict_from = AsyncMock(return_value=[])
    processor = ObservationProcessor(
        vector_processor=Mock(),
        pattern_processor=pattern_processor,
        memory_manager=Mock(),
        pattern_operations=pattern_operations,
        sort_symbols=True,
        max_pattern_length=0,
        process_predictions=False,
    )
    return processor, pattern_operations


def test_auto_learning_reports_whether_it_fired():
    processor, _ = _observation_processor()
    stm = [['a'], ['b']]

    assert processor.check_auto_learning(stm, [], [], 0, 'CLEAR') == (None, stm, False)
    assert processor.check_auto_learning(stm, [], [], 3, 'CLEAR') == (None, stm, False)
    assert processor.check_auto_learning(stm, [], [], 2, 'CLEAR') == ('PTRN|x', [], True)

    name, kept, fired = processor.check_auto_learning(stm, [], [], 2, 'ROLLING')
    assert (name, kept, fired) == ('PTRN|x', [['b']], True)


def test_auto_learning_a_single_event_still_counts_as_fired():
    """Nothing is stored for one event, but the STM is consumed, so the
    caller must still reset the accumulators."""
    processor, _ = _observation_processor(learned_name='')
    assert processor.check_auto_learning([['a']], [], [], 1, 'CLEAR') == (None, [], True)


@pytest.mark.asyncio
async def test_auto_learned_pattern_is_stored_with_the_passed_accumulators():
    processor, pattern_operations = _observation_processor()
    emotives = [{'joy': 0.5}, {'joy': 0.9}]
    metadata = [{'source': 'x'}]

    result = await processor.process_observation(
        {'unique_id': 'u', 'strings': ['b']},
        config=SessionConfiguration(max_pattern_length=2, process_predictions=False),
        stm=[['a']],
        emotives=emotives,
        metadata=metadata,
    )

    assert result['auto_learn_triggered'] is True
    assert result['auto_learned_pattern'] == 'PTRN|x'
    assert result['stm'] == []
    stored = pattern_operations.learn_pattern_from.call_args.args
    assert stored == ([['a'], ['b']], emotives, metadata)


@pytest.mark.asyncio
async def test_no_auto_learn_means_no_flag():
    processor, pattern_operations = _observation_processor()
    result = await processor.process_observation(
        {'unique_id': 'u', 'strings': ['b']},
        config=SessionConfiguration(max_pattern_length=5, process_predictions=False),
        stm=[['a']],
    )
    assert result['auto_learn_triggered'] is False
    pattern_operations.learn_pattern_from.assert_not_called()


def _kato_processor(observation_result):
    processor = object.__new__(KatoProcessor)
    processor.id = 'p'
    processor.distributed_stm_manager = None
    processor.observation_processor = Mock()
    processor.observation_processor.process_observation = AsyncMock(
        return_value=observation_result)
    return processor


@pytest.mark.asyncio
async def test_observe_hands_the_updated_accumulators_to_the_observation():
    """The learn sees the triggering observation's emotives and metadata."""
    processor = _kato_processor({'stm': [['a'], ['b']], 'auto_learn_triggered': False})
    session = _session()

    new_state = await processor.observe(
        {'strings': ['b'], 'emotives': {'joy': 0.1}, 'metadata': {'k': 'v'}},
        session_state=session,
        config=SessionConfiguration(),
    )

    kwargs = processor.observation_processor.process_observation.call_args.kwargs
    assert kwargs['emotives'] == [{'joy': 0.5}, {'joy': 0.7}, {'joy': 0.1}]
    assert kwargs['metadata'] == [{'source': 'x'}, {'k': 'v'}]
    # No auto-learn: the accumulators carry on.
    assert new_state['emotives_accumulator'] == kwargs['emotives']
    assert new_state['metadata_accumulator'] == kwargs['metadata']


@pytest.mark.asyncio
async def test_observe_resets_the_accumulators_after_an_auto_learn():
    processor = _kato_processor(
        {'stm': [], 'auto_learned_pattern': 'PTRN|x', 'auto_learn_triggered': True})
    session = _session()

    new_state = await processor.observe(
        {'strings': ['b'], 'emotives': {'joy': 0.1}, 'metadata': {'k': 'v'}},
        session_state=session,
        config=SessionConfiguration(),
    )

    kwargs = processor.observation_processor.process_observation.call_args.kwargs
    assert kwargs['emotives'][-1] == {'joy': 0.1}      # learned with this event's
    assert kwargs['metadata'][-1] == {'k': 'v'}
    assert new_state['emotives_accumulator'] == []
    assert new_state['metadata_accumulator'] == []
    assert new_state['auto_learned_pattern'] == 'PTRN|x'
    # The percept still reports the emotives of the event just observed.
    assert new_state['percept_data']['emotives']
    # The input state is untouched (stateless contract).
    assert session.emotives_accumulator == [{'joy': 0.5}, {'joy': 0.7}]
