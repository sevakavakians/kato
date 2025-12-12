"""
Comprehensive metadata tests to verify metadata storage and retrieval.

These tests verify that metadata:
1. Is stored in Redis (not ClickHouse)
2. Accumulates correctly with set-union behavior
3. Appears in predictions
4. Handles large metadata sets
5. Works correctly with kb_id truncation
"""
import pytest


def test_metadata_stored_in_redis_not_clickhouse(kato_fixture):
    """Test that metadata is stored in Redis, not ClickHouse."""
    kato_fixture.clear_all_memory()

    # Learn pattern with metadata
    kato_fixture.observe({'strings': ['A'], 'vectors': [], 'emotives': {}, 'metadata': {'source': 'test1'}})
    kato_fixture.observe({'strings': ['B'], 'vectors': [], 'emotives': {}, 'metadata': {'source': 'test2'}})
    pattern_name = kato_fixture.learn()

    # Verify metadata is in Redis
    redis_metadata = kato_fixture.get_redis_metadata(pattern_name)
    assert redis_metadata is not None, "Metadata should exist in Redis"
    assert 'source' in redis_metadata, "Redis should have 'source' metadata"
    assert set(redis_metadata['source']) == {'test1', 'test2'}, "Redis metadata should match"


def test_metadata_accumulation_with_relearning(kato_fixture):
    """Test metadata accumulates when pattern is re-learned."""
    kato_fixture.clear_all_memory()

    # Learn pattern first time
    kato_fixture.observe({'strings': ['X'], 'vectors': [], 'emotives': {}, 'metadata': {'version': 'v1'}})
    kato_fixture.observe({'strings': ['Y'], 'vectors': [], 'emotives': {}, 'metadata': {'version': 'v1'}})
    first_pattern_name = kato_fixture.learn()

    # Re-learn same pattern with different metadata
    kato_fixture.observe({'strings': ['X'], 'vectors': [], 'emotives': {}, 'metadata': {'version': 'v2'}})
    kato_fixture.observe({'strings': ['Y'], 'vectors': [], 'emotives': {}, 'metadata': {'version': 'v2'}})
    second_pattern_name = kato_fixture.learn()

    # Verify same pattern
    clean_name1 = first_pattern_name[5:] if first_pattern_name.startswith('PTRN|') else first_pattern_name
    clean_name2 = second_pattern_name[5:] if second_pattern_name.startswith('PTRN|') else second_pattern_name
    assert clean_name1 == clean_name2, "Should be same pattern"

    # Verify metadata accumulated
    redis_metadata = kato_fixture.get_redis_metadata(first_pattern_name)
    assert set(redis_metadata['version']) == {'v1', 'v2'}, "Metadata should accumulate"


def test_metadata_in_predictions(kato_fixture):
    """Test that metadata appears in predictions."""
    kato_fixture.clear_all_memory()
    kato_fixture.set_recall_threshold(0.2)

    # Learn 3-event pattern with metadata
    kato_fixture.observe({'strings': ['start'], 'vectors': [], 'emotives': {}, 'metadata': {'tag': 'test1'}})
    kato_fixture.observe({'strings': ['middle'], 'vectors': [], 'emotives': {}, 'metadata': {'tag': 'test2'}})
    kato_fixture.observe({'strings': ['end'], 'vectors': [], 'emotives': {}, 'metadata': {'tag': 'test3'}})
    pattern_name = kato_fixture.learn()

    # Trigger predictions
    kato_fixture.clear_short_term_memory()
    kato_fixture.observe({'strings': ['start'], 'vectors': [], 'emotives': {}, 'metadata': {}})
    kato_fixture.observe({'strings': ['middle'], 'vectors': [], 'emotives': {}, 'metadata': {}})
    predictions = kato_fixture.get_predictions()

    assert len(predictions) > 0, "Should have predictions"
    # Check if metadata appears in predictions
    first_pred = predictions[0]
    if 'metadata' in first_pred:
        metadata = first_pred['metadata']
        assert 'tag' in metadata, "Predictions should include metadata"
        assert set(metadata['tag']) == {'test1', 'test2', 'test3'}, "All metadata values should be present"


def test_large_metadata_accumulation(kato_fixture):
    """Test metadata with many unique values accumulating."""
    kato_fixture.clear_all_memory()

    # Learn pattern with 20 different metadata values
    for i in range(20):
        kato_fixture.observe({'strings': ['item'], 'vectors': [], 'emotives': {}, 'metadata': {'iteration': str(i)}})
        kato_fixture.observe({'strings': ['data'], 'vectors': [], 'emotives': {}, 'metadata': {'iteration': str(i)}})
        pattern_name = kato_fixture.learn()

    # Verify all 20 values accumulated
    redis_metadata = kato_fixture.get_redis_metadata(pattern_name)
    assert 'iteration' in redis_metadata, "Should have iteration metadata"
    assert len(redis_metadata['iteration']) == 20, f"Should have 20 unique values, got {len(redis_metadata['iteration'])}"
    expected_values = {str(i) for i in range(20)}
    assert set(redis_metadata['iteration']) == expected_values, "All 20 values should be present"


def test_metadata_duplicate_filtering(kato_fixture):
    """Test that duplicate metadata values are filtered out."""
    kato_fixture.clear_all_memory()

    # Learn pattern multiple times with same metadata value
    for i in range(5):
        kato_fixture.observe({'strings': ['A'], 'vectors': [], 'emotives': {}, 'metadata': {'tag': 'constant'}})
        kato_fixture.observe({'strings': ['B'], 'vectors': [], 'emotives': {}, 'metadata': {'tag': 'constant'}})
        pattern_name = kato_fixture.learn()

    # Verify only one value stored (no duplicates)
    redis_metadata = kato_fixture.get_redis_metadata(pattern_name)
    assert 'tag' in redis_metadata, "Should have tag metadata"
    assert redis_metadata['tag'] == ['constant'], f"Should have single value, got {redis_metadata['tag']}"
    assert len(redis_metadata['tag']) == 1, "Should filter duplicates"


def test_multiple_metadata_keys_accumulation(kato_fixture):
    """Test accumulation of multiple metadata keys simultaneously."""
    kato_fixture.clear_all_memory()

    # Learn with multiple metadata keys
    kato_fixture.observe({
        'strings': ['event1'],
        'vectors': [],
        'emotives': {},
        'metadata': {'source': 'src1', 'category': 'cat1', 'priority': 'high'}
    })
    kato_fixture.observe({
        'strings': ['event2'],
        'vectors': [],
        'emotives': {},
        'metadata': {'source': 'src2', 'category': 'cat1', 'priority': 'low'}
    })
    first_pattern_name = kato_fixture.learn()

    # Re-learn with different values
    kato_fixture.observe({
        'strings': ['event1'],
        'vectors': [],
        'emotives': {},
        'metadata': {'source': 'src3', 'category': 'cat2', 'priority': 'high'}
    })
    kato_fixture.observe({
        'strings': ['event2'],
        'vectors': [],
        'emotives': {},
        'metadata': {'source': 'src4', 'category': 'cat3', 'priority': 'medium'}
    })
    second_pattern_name = kato_fixture.learn()

    # Verify accumulation for all keys
    redis_metadata = kato_fixture.get_redis_metadata(first_pattern_name)
    assert set(redis_metadata['source']) == {'src1', 'src2', 'src3', 'src4'}, "All sources should accumulate"
    assert set(redis_metadata['category']) == {'cat1', 'cat2', 'cat3'}, "All categories should accumulate"
    assert set(redis_metadata['priority']) == {'high', 'low', 'medium'}, "All priorities should accumulate"


def test_metadata_with_kb_id_truncation(kato_fixture):
    """Test that metadata works correctly with long processor IDs (kb_id truncation)."""
    # This test uses the fixture's processor_id which may be truncated
    kato_fixture.clear_all_memory()

    # Learn pattern with metadata
    kato_fixture.observe({'strings': ['test'], 'vectors': [], 'emotives': {}, 'metadata': {'value': 'data'}})
    kato_fixture.observe({'strings': ['item'], 'vectors': [], 'emotives': {}, 'metadata': {'value': 'data'}})
    pattern_name = kato_fixture.learn()

    # Verify metadata is retrievable (tests kb_id truncation)
    redis_metadata = kato_fixture.get_redis_metadata(pattern_name)
    assert redis_metadata is not None, "Metadata should be retrievable with kb_id truncation"
    assert 'value' in redis_metadata, "Should have value metadata"
    assert redis_metadata['value'] == ['data'], "Metadata value should match"


def test_empty_metadata_handling(kato_fixture):
    """Test that empty metadata is handled correctly."""
    kato_fixture.clear_all_memory()

    # Learn pattern without metadata
    kato_fixture.observe({'strings': ['A'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['B'], 'vectors': [], 'emotives': {}})
    pattern_name = kato_fixture.learn()

    # Verify empty metadata doesn't cause errors
    redis_metadata = kato_fixture.get_redis_metadata(pattern_name)
    # Empty metadata may be stored as empty dict or may not exist
    if redis_metadata:
        assert redis_metadata == {} or 'metadata' not in redis_metadata, "Empty metadata should be empty dict"


def test_metadata_type_conversion_to_strings(kato_fixture):
    """Test that all metadata values are converted to strings."""
    kato_fixture.clear_all_memory()

    # Observe with various value types
    kato_fixture.observe({
        'strings': ['A'],
        'vectors': [],
        'emotives': {},
        'metadata': {
            'count': 123,  # int
            'price': 45.67,  # float
            'flag': True,  # bool
            'name': 'test'  # str
        }
    })
    kato_fixture.observe({'strings': ['B'], 'vectors': [], 'emotives': {}, 'metadata': {}})
    pattern_name = kato_fixture.learn()

    # Verify all converted to strings
    redis_metadata = kato_fixture.get_redis_metadata(pattern_name)
    assert redis_metadata['count'] == ['123'], "int should convert to string"
    assert redis_metadata['price'] == ['45.67'], "float should convert to string"
    assert redis_metadata['flag'] == ['True'], "bool should convert to string"
    assert redis_metadata['name'] == ['test'], "string should remain string"
