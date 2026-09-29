import asyncio
from collections import deque
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np

from kato.config.configuration_service import ConfigurationService
from kato.config.session_config import (
    DEFAULT_VECTOR_EVENT_MODE,
    VECTOR_EVENT_MODE_SELF_ONLY,
    SessionConfiguration,
)
from kato.representations.vector_object import VectorObject
from kato.workers.observation_processor import ObservationProcessor
from kato.workers.pattern_operations import PatternOperations
from kato.workers.pattern_processor import PatternProcessor
from kato.workers.vector_processor import VectorProcessor


def make_vector_processor(neighbors=None):
    processor = VectorProcessor.__new__(VectorProcessor)
    processor.indexer_type = 'VI'
    processor.vector_indexer = Mock()
    processor.vector_indexer.findNearestPoints.return_value = list(neighbors or [])
    processor.deferred_vectors_for_learning = []
    return processor


def make_settings():
    return SimpleNamespace(
        learning=SimpleNamespace(
            max_pattern_length=0,
            persistence=5,
            recall_threshold=0.1,
            stm_mode='CLEAR',
        ),
        processing=SimpleNamespace(
            indexer_type='VI',
            max_predictions=100,
            sort_symbols=True,
            process_predictions=True,
            use_token_matching=True,
            rank_sort_algo='potential',
            fuzzy_token_threshold=0.0,
        ),
    )


def make_pattern_processor():
    processor = PatternProcessor.__new__(PatternProcessor)
    processor.name = 'test-PatternProcessor'
    processor.id = 'test-node'
    processor.stm_mode = 'CLEAR'
    processor.trigger_predictions = False
    processor.STM = deque()
    processor.emotives = []
    processor.metadata = []
    processor.patterns_kb = Mock()
    processor.patterns_kb.learnPattern.return_value = True
    processor.patterns_searcher = Mock()
    processor.metrics_cache_manager = None
    processor.query_manager = Mock()
    processor._global_metadata_cache = None
    return processor


def test_self_only_returns_only_own_vctr_and_skips_neighbor_search():
    processor = make_vector_processor(neighbors=['VCTR|neighbor'])

    symbols = processor.process(
        [[1.0, 2.0, 3.0]],
        vector_event_mode=VECTOR_EVENT_MODE_SELF_ONLY,
    )

    processor.vector_indexer.findNearestPoints.assert_not_called()
    assert len(symbols) == 1
    assert symbols[0].startswith('VCTR|')
    assert symbols[0] == processor.deferred_vectors_for_learning[0].name


def test_self_only_vector_is_still_indexed_during_learn():
    processor = make_vector_processor()
    processor.process(
        [[1.0, 2.0, 3.0]],
        vector_event_mode=VECTOR_EVENT_MODE_SELF_ONLY,
    )
    queued_vector = processor.deferred_vectors_for_learning[0]

    processor.learn()

    queued_batch = processor.vector_indexer.assignNewlyLearnedToWorkers.call_args.args[0]
    assert len(queued_batch) == 1
    assert queued_batch[0] is queued_vector
    assert isinstance(queued_batch[0], VectorObject)
    assert np.array_equal(queued_batch[0].vector, np.array([1.0, 2.0, 3.0]))
    assert processor.deferred_vectors_for_learning == []


def test_neighbors_plus_self_remains_the_default_behavior():
    neighbor_id = 'VCTR|neighbor'
    processor = make_vector_processor(neighbors=[neighbor_id])

    symbols = processor.process([[4.0, 5.0, 6.0]])

    queued_vector = processor.deferred_vectors_for_learning[0]
    processor.vector_indexer.findNearestPoints.assert_called_once_with(queued_vector)
    assert set(symbols) == {neighbor_id, queued_vector.name}


def test_own_vctr_to_window_id_is_learnable_through_session_mode():
    vector_processor = make_vector_processor(neighbors=['VCTR|neighbor'])
    pattern_processor = make_pattern_processor()
    pattern_operations = PatternOperations.__new__(PatternOperations)
    pattern_operations.pattern_processor = pattern_processor
    pattern_operations.vector_processor = vector_processor
    pattern_operations.memory_manager = Mock()

    observation_processor = ObservationProcessor(
        vector_processor=vector_processor,
        pattern_processor=pattern_processor,
        memory_manager=Mock(),
        pattern_operations=pattern_operations,
        sort_symbols=True,
        max_pattern_length=0,
        process_predictions=True,
    )
    session_config = SessionConfiguration(
        vector_event_mode=VECTOR_EVENT_MODE_SELF_ONLY,
        max_pattern_length=0,
        process_predictions=False,
    )

    vector_result = asyncio.run(observation_processor.process_observation(
        {
            'unique_id': 'vector-event',
            'vectors': [[7.0, 8.0, 9.0]],
        },
        config=session_config,
        stm=[],
    ))
    window_id = 'WINDOW_ID|example'
    window_result = asyncio.run(observation_processor.process_observation(
        {
            'unique_id': 'window-event',
            'strings': [window_id],
        },
        config=session_config,
        stm=vector_result['stm'],
    ))

    own_vctr = vector_result['symbols'][0]
    assert window_result['stm'] == [[own_vctr], [window_id]]
    assert list(pattern_processor.STM) == []
    pattern_name = pattern_operations.learn_pattern_from(window_result['stm'], [], [])

    learned_pattern = pattern_processor.patterns_kb.learnPattern.call_args.args[0]
    assert pattern_name.startswith('PTRN|')
    assert learned_pattern.pattern_data == [[own_vctr], [window_id]]
    vector_processor.vector_indexer.findNearestPoints.assert_not_called()
    vector_processor.vector_indexer.assignNewlyLearnedToWorkers.assert_called_once()


def test_vector_event_mode_is_a_validated_persistent_session_setting():
    service = ConfigurationService(make_settings())
    defaults = service.get_default_configuration()
    session_config = SessionConfiguration(vector_event_mode=VECTOR_EVENT_MODE_SELF_ONLY)

    assert defaults['vector_event_mode'] == DEFAULT_VECTOR_EVENT_MODE
    assert session_config.validate()
    assert SessionConfiguration.from_dict(
        session_config.to_dict()
    ).vector_event_mode == VECTOR_EVENT_MODE_SELF_ONLY
    assert service.resolve_configuration(session_config).vector_event_mode == VECTOR_EVENT_MODE_SELF_ONLY
    assert service.validate_configuration_update({
        'vector_event_mode': VECTOR_EVENT_MODE_SELF_ONLY,
    }) == {}
    assert 'vector_event_mode' in service.validate_configuration_update({
        'vector_event_mode': 'invalid',
    })
