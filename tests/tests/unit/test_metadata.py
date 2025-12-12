"""
Unit tests for pattern metadata functionality.

Tests metadata accumulation, storage, and retrieval in patterns.
"""
import pytest


def test_observe_with_metadata(kato_fixture):
    """Test observing with metadata values."""
    assert kato_fixture.clear_all_memory() == 'all-cleared'

    # First, learn a sequence with metadata
    sequence_with_metadata = [
        (['hello'], {'book': 'title1', 'author': 'Smith'}),
        (['world'], {'book': 'title2', 'chapter': '1'}),
        (['test'], {'book': 'title1', 'chapter': '2'})
    ]

    for strings, metadata in sequence_with_metadata:
        result = kato_fixture.observe({
            'strings': strings,
            'vectors': [],
            'emotives': {},
            'metadata': metadata
        })
        assert result['status'] == 'observed'

    # Learn the sequence
    pattern_name = kato_fixture.learn()
    assert pattern_name is not None

    # Retrieve the pattern and check metadata
    pattern_result = kato_fixture.get_pattern(pattern_name)
    assert pattern_result['status'] == 'okay'

    pattern = pattern_result['pattern']
    assert 'metadata' in pattern

    # Check that metadata was accumulated correctly
    # Should have: book=['title1', 'title2'], author=['Smith'], chapter=['1', '2']
    metadata = pattern['metadata']
    assert 'book' in metadata
    assert set(metadata['book']) == {'title1', 'title2'}  # Unique values
    assert 'author' in metadata
    assert metadata['author'] == ['Smith']
    assert 'chapter' in metadata
    assert set(metadata['chapter']) == {'1', '2'}

    # CRITICAL: Validate metadata is ACTUALLY stored in Redis
    redis_metadata = kato_fixture.get_redis_metadata(pattern_name)
    assert redis_metadata is not None, "Metadata key should exist in Redis"
    assert 'book' in redis_metadata, "Redis should have 'book' metadata"
    assert set(redis_metadata['book']) == {'title1', 'title2'}, "Redis book metadata should match"
    assert 'author' in redis_metadata, "Redis should have 'author' metadata"
    assert redis_metadata['author'] == ['Smith'], "Redis author metadata should match"
    assert 'chapter' in redis_metadata, "Redis should have 'chapter' metadata"
    assert set(redis_metadata['chapter']) == {'1', '2'}, "Redis chapter metadata should match"


def test_metadata_duplicate_handling(kato_fixture):
    """Test that duplicate metadata values are not added."""
    assert kato_fixture.clear_all_memory() == 'all-cleared'

    # Observe with duplicate metadata values
    kato_fixture.observe({
        'strings': ['A'],
        'vectors': [],
        'emotives': {},
        'metadata': {'tag': 'important'}
    })

    kato_fixture.observe({
        'strings': ['B'],
        'vectors': [],
        'emotives': {},
        'metadata': {'tag': 'important'}  # Duplicate value
    })

    kato_fixture.observe({
        'strings': ['C'],
        'vectors': [],
        'emotives': {},
        'metadata': {'tag': 'urgent'}  # Different value
    })

    # Learn the pattern
    pattern_name = kato_fixture.learn()
    assert pattern_name is not None

    # Check that duplicates were removed
    pattern_result = kato_fixture.get_pattern(pattern_name)
    pattern = pattern_result['pattern']

    assert 'metadata' in pattern
    assert 'tag' in pattern['metadata']
    # Should have both 'important' and 'urgent', but only one 'important'
    assert set(pattern['metadata']['tag']) == {'important', 'urgent'}
    assert len(pattern['metadata']['tag']) == 2


def test_metadata_accumulation_across_relearning(kato_fixture):
    """Test that metadata accumulates when the same pattern is learned multiple times."""
    assert kato_fixture.clear_all_memory() == 'all-cleared'

    # Learn pattern first time with one metadata value
    kato_fixture.observe({
        'strings': ['X'],
        'vectors': [],
        'emotives': {},
        'metadata': {'version': 'v1'}
    })

    kato_fixture.observe({
        'strings': ['Y'],
        'vectors': [],
        'emotives': {},
        'metadata': {}
    })

    pattern_name1 = kato_fixture.learn()
    assert pattern_name1 is not None

    # Learn same pattern again with different metadata value
    kato_fixture.observe({
        'strings': ['X'],
        'vectors': [],
        'emotives': {},
        'metadata': {'version': 'v2'}
    })

    kato_fixture.observe({
        'strings': ['Y'],
        'vectors': [],
        'emotives': {},
        'metadata': {}
    })

    pattern_name2 = kato_fixture.learn()

    # Should be same pattern
    # Get clean names for comparison
    clean_name1 = pattern_name1[5:] if pattern_name1.startswith('PTRN|') else pattern_name1
    clean_name2 = pattern_name2[5:] if pattern_name2.startswith('PTRN|') else pattern_name2
    assert clean_name1 == clean_name2

    # Check that both versions are in metadata
    pattern_result = kato_fixture.get_pattern(pattern_name1)
    pattern = pattern_result['pattern']

    assert 'metadata' in pattern
    assert 'version' in pattern['metadata']
    assert set(pattern['metadata']['version']) == {'v1', 'v2'}


def test_metadata_type_conversion(kato_fixture):
    """Test that metadata values are converted to strings."""
    assert kato_fixture.clear_all_memory() == 'all-cleared'

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

    kato_fixture.observe({
        'strings': ['B'],
        'vectors': [],
        'emotives': {},
        'metadata': {}
    })

    pattern_name = kato_fixture.learn()
    assert pattern_name is not None

    # Check that all values were converted to strings
    pattern_result = kato_fixture.get_pattern(pattern_name)
    pattern = pattern_result['pattern']

    assert 'metadata' in pattern
    metadata = pattern['metadata']

    # All values should be string lists
    assert metadata['count'] == ['123']
    assert metadata['price'] == ['45.67']
    assert metadata['flag'] == ['True']
    assert metadata['name'] == ['test']


def test_metadata_with_empty_values(kato_fixture):
    """Test metadata handling when no metadata is provided."""
    assert kato_fixture.clear_all_memory() == 'all-cleared'

    # Observe without metadata
    kato_fixture.observe({
        'strings': ['A'],
        'vectors': [],
        'emotives': {}
    })

    kato_fixture.observe({
        'strings': ['B'],
        'vectors': [],
        'emotives': {}
    })

    pattern_name = kato_fixture.learn()
    assert pattern_name is not None

    # Check that metadata field exists but is empty
    pattern_result = kato_fixture.get_pattern(pattern_name)
    pattern = pattern_result['pattern']

    assert 'metadata' in pattern
    assert pattern['metadata'] == {}


def test_metadata_cleared_with_stm(kato_fixture):
    """Test that metadata accumulator is cleared when STM is cleared."""
    assert kato_fixture.clear_all_memory() == 'all-cleared'

    # Observe with metadata
    kato_fixture.observe({
        'strings': ['A'],
        'vectors': [],
        'emotives': {},
        'metadata': {'tag': 'test'}
    })

    # Clear STM
    kato_fixture.clear_stm()

    # Observe new sequence without metadata
    kato_fixture.observe({
        'strings': ['X'],
        'vectors': [],
        'emotives': {}
    })

    kato_fixture.observe({
        'strings': ['Y'],
        'vectors': [],
        'emotives': {}
    })

    pattern_name = kato_fixture.learn()
    assert pattern_name is not None

    # Check that metadata from first observation is not in pattern
    pattern_result = kato_fixture.get_pattern(pattern_name)
    pattern = pattern_result['pattern']

    assert 'metadata' in pattern
    assert pattern['metadata'] == {}
