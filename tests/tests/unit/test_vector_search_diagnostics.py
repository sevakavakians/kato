import asyncio
from collections import deque
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import numpy as np

from kato.api.schemas.observation import ObservationResult
from kato.config.configuration_service import ConfigurationService
from kato.config.session_config import (
    DEFAULT_RETURN_VECTOR_SEARCH_RESULTS,
    DEFAULT_VECTOR_SEARCH_LIMIT,
    MAX_VECTOR_SEARCH_LIMIT,
    VECTOR_EVENT_MODE_SELF_ONLY,
    SessionConfiguration,
)
from kato.representations.vector_object import VectorObject
from kato.searches.vector_search_engine import VectorIndexer
from kato.storage.vector_store_interface import VectorSearchResult
from kato.workers.kato_processor import KatoProcessor
from kato.workers.observation_processor import ObservationProcessor
from kato.workers.vector_processor import VectorProcessor


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


def make_vector_processor(search_results=None):
    processor = VectorProcessor.__new__(VectorProcessor)
    processor.indexer_type = 'VI'
    processor.vector_indexer = Mock()
    processor.vector_indexer.engine = SimpleNamespace(
        config=SimpleNamespace(similarity_metric='euclidean')
    )
    processor.vector_indexer.findNearestResults.return_value = list(search_results or [])
    processor.vector_indexer.findNearestPoints.return_value = []
    processor.deferred_vectors_for_learning = []
    return processor


def test_vector_indexer_preserves_ordered_results_and_raw_scores():
    query = VectorObject(np.array([1.0, 0.0, 0.0]))
    expected = [
        VectorSearchResult(id='VCTR|a', score=0.01),
        VectorSearchResult(id='VCTR|b', score=0.25),
    ]
    indexer = VectorIndexer.__new__(VectorIndexer)
    indexer.initialize = Mock()
    indexer.engine = Mock()
    indexer.engine.search_sync.return_value = expected

    results = indexer.findNearestResults(query, k=100)

    assert results is expected
    assert [(item.id, item.score) for item in results] == [
        ('VCTR|a', 0.01),
        ('VCTR|b', 0.25),
    ]
    indexer.engine.search_sync.assert_called_once_with(
        query,
        k=100,
        include_vectors=False,
    )


def test_legacy_vector_id_wrapper_keeps_k20_default():
    query = VectorObject(np.array([1.0, 0.0, 0.0]))
    indexer = VectorIndexer.__new__(VectorIndexer)
    indexer.findNearestResults = Mock(return_value=[
        VectorSearchResult(id='VCTR|a', score=0.01),
        VectorSearchResult(id='VCTR|b', score=0.25),
    ])

    assert indexer.findNearestPoints(query) == ['VCTR|a', 'VCTR|b']
    indexer.findNearestResults.assert_called_once_with(
        query,
        k=DEFAULT_VECTOR_SEARCH_LIMIT,
    )


def test_vector_processor_returns_scores_without_putting_them_in_event():
    vector = [1.0, 2.0, 3.0]
    own_vctr = VectorObject(np.array(vector)).name
    processor = make_vector_processor([
        VectorSearchResult(id=own_vctr, score=0.0),
        VectorSearchResult(id='VCTR|neighbor', score=0.5),
    ])

    symbols, diagnostics = processor.process_with_diagnostics(
        [vector],
        vector_search_limit=100,
    )

    assert set(symbols) == {own_vctr, 'VCTR|neighbor'}
    assert all(isinstance(symbol, str) for symbol in symbols)
    assert diagnostics == {
        'query_vctr_id': own_vctr,
        'requested_limit': 100,
        'search_performed': True,
        'metric': 'euclidean',
        'score_direction': 'lower_is_better',
        'matches': [
            {
                'vctr_id': own_vctr,
                'rank': 1,
                'raw_score': 0.0,
                'source': 'vector_index',
            },
            {
                'vctr_id': 'VCTR|neighbor',
                'rank': 2,
                'raw_score': 0.5,
                'source': 'vector_index',
            },
        ],
    }
    processor.vector_indexer.findNearestResults.assert_called_once()
    assert processor.deferred_vectors_for_learning[0].name == own_vctr


def test_missing_own_vector_is_marked_as_appended_without_a_fake_score():
    vector = [4.0, 5.0, 6.0]
    own_vctr = VectorObject(np.array(vector)).name
    processor = make_vector_processor([
        VectorSearchResult(id='VCTR|neighbor', score=0.75),
    ])

    symbols, diagnostics = processor.process_with_diagnostics([vector])

    assert own_vctr in symbols
    assert diagnostics['matches'][-1] == {
        'vctr_id': own_vctr,
        'rank': 2,
        'raw_score': None,
        'source': 'self_appended',
    }


def test_self_only_diagnostics_do_not_run_neighbor_search():
    processor = make_vector_processor([
        VectorSearchResult(id='VCTR|neighbor', score=0.75),
    ])

    symbols, diagnostics = processor.process_with_diagnostics(
        [[7.0, 8.0, 9.0]],
        vector_event_mode=VECTOR_EVENT_MODE_SELF_ONLY,
        vector_search_limit=100,
    )

    assert len(symbols) == 1
    assert symbols[0].startswith('VCTR|')
    assert diagnostics['search_performed'] is False
    assert diagnostics['matches'] == []
    processor.vector_indexer.findNearestResults.assert_not_called()
    processor.vector_indexer.findNearestPoints.assert_not_called()


def test_session_vector_search_settings_are_opt_in_and_validated():
    service = ConfigurationService(make_settings())
    defaults = service.get_default_configuration()
    config = SessionConfiguration(
        vector_search_limit=100,
        return_vector_search_results=True,
    )

    assert defaults['vector_search_limit'] == DEFAULT_VECTOR_SEARCH_LIMIT
    assert defaults['return_vector_search_results'] is DEFAULT_RETURN_VECTOR_SEARCH_RESULTS
    assert config.validate()
    assert SessionConfiguration.from_dict(config.to_dict()).vector_search_limit == 100
    resolved = service.resolve_configuration(config)
    assert resolved.vector_search_limit == 100
    assert resolved.return_vector_search_results is True
    assert service.validate_configuration_update({
        'vector_search_limit': 100,
        'return_vector_search_results': True,
    }) == {}
    for invalid in (0, MAX_VECTOR_SEARCH_LIMIT + 1, True, 1.5):
        assert 'vector_search_limit' in service.validate_configuration_update({
            'vector_search_limit': invalid,
        })
    assert 'return_vector_search_results' in service.validate_configuration_update({
        'return_vector_search_results': 1,
    })


def test_observation_returns_diagnostics_but_stm_event_contains_only_ids():
    diagnostics = {
        'query_vctr_id': 'VCTR|query',
        'requested_limit': 100,
        'search_performed': True,
        'metric': 'euclidean',
        'score_direction': 'lower_is_better',
        'matches': [
            {
                'vctr_id': 'VCTR|neighbor',
                'rank': 1,
                'raw_score': 0.2,
                'source': 'vector_index',
            }
        ],
    }
    vector_processor = Mock()
    vector_processor.process_with_diagnostics.return_value = (
        ['VCTR|query', 'VCTR|neighbor'],
        diagnostics,
    )
    pattern_processor = Mock()
    pattern_processor.stm_mode = 'CLEAR'
    pattern_processor.predict_from = AsyncMock(return_value=[])
    observation_processor = ObservationProcessor(
        vector_processor=vector_processor,
        pattern_processor=pattern_processor,
        memory_manager=Mock(),
        pattern_operations=Mock(),
        sort_symbols=True,
        max_pattern_length=0,
        process_predictions=True,
    )

    result = asyncio.run(observation_processor.process_observation(
        {
            'unique_id': 'evaluation-query',
            'vectors': [[1.0, 0.0, 0.0]],
        },
        stm=[],
        config=SessionConfiguration(
            vector_search_limit=100,
            return_vector_search_results=True,
            process_predictions=False,
        ),
    ))

    assert result['vector_search'] == diagnostics
    assert result['stm'] == [['VCTR|neighbor', 'VCTR|query']]
    pattern_processor.setCurrentEvent.assert_not_called()
    assert all(isinstance(value, str) for value in result['symbols'])
    assert not any('raw_score' in value for value in result['symbols'])
    vector_processor.process.assert_not_called()


def test_observation_diagnostics_are_absent_by_default():
    vector_processor = Mock()
    vector_processor.process.return_value = ['VCTR|query']
    pattern_processor = Mock()
    pattern_processor.stm_mode = 'CLEAR'
    pattern_processor.predict_from = AsyncMock(return_value=[])
    observation_processor = ObservationProcessor(
        vector_processor=vector_processor,
        pattern_processor=pattern_processor,
        memory_manager=Mock(),
        pattern_operations=Mock(),
        sort_symbols=True,
        max_pattern_length=0,
        process_predictions=True,
    )

    result = asyncio.run(observation_processor.process_observation(
        {
            'unique_id': 'default-query',
            'vectors': [[1.0, 0.0, 0.0]],
        },
        stm=[],
        config=SessionConfiguration(process_predictions=False),
    ))

    assert 'vector_search' not in result
    vector_processor.process.assert_called_once_with(
        [[1.0, 0.0, 0.0]],
        vector_event_mode='neighbors_plus_self',
        vector_search_limit=DEFAULT_VECTOR_SEARCH_LIMIT,
    )
    vector_processor.process_with_diagnostics.assert_not_called()


def test_kato_processor_and_response_schema_pass_diagnostics_without_session_field():
    diagnostics = {
        'query_vctr_id': 'VCTR|query',
        'requested_limit': 100,
        'search_performed': True,
        'metric': 'euclidean',
        'score_direction': 'lower_is_better',
        'matches': [],
    }
    processor = KatoProcessor.__new__(KatoProcessor)
    processor.id = 'test-node'
    processor.pattern_processor = SimpleNamespace(STM=deque([['VCTR|query']]))
    processor.memory_manager = Mock()
    processor.memory_manager.set_stm_in_pattern_processor = Mock()
    processor.observation_processor = SimpleNamespace(
        process_observation=AsyncMock(return_value={
            'unique_id': 'evaluation-query',
            'auto_learned_pattern': None,
            'symbols': ['VCTR|query'],
            'predictions': [],
            'vector_search': diagnostics,
            'path': [],
            'stm': [['VCTR|query']],
        })
    )
    processor.distributed_stm_manager = None
    session = SimpleNamespace(
        stm=[],
        time=0,
        emotives_accumulator=[],
        metadata_accumulator=[],
    )

    result = asyncio.run(processor.observe(
        {
            'unique_id': 'evaluation-query',
            'vectors': [[1.0, 0.0, 0.0]],
        },
        session_state=session,
        config=SessionConfiguration(),
    ))
    response = ObservationResult(
        status='okay',
        time=result['time'],
        vector_search=result['vector_search'],
    )

    assert result['vector_search'] == diagnostics
    assert response.vector_search == diagnostics
    assert not hasattr(session, 'vector_search')
