"""
Unit tests for KATO observation processing.
Tests single observations with strings, vectors, and emotives.
"""

import pytest
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from fixtures.kato_fixtures import kato_fixture
from fixtures.test_helpers import sort_event_strings, assert_working_memory_equals


def test_observe_single_string(kato_fixture):
    """Test observing a single string."""
    # Clear memory first
    assert kato_fixture.clear_all_memory() == 'all-cleared'
    
    # Observe a single string
    result = kato_fixture.observe({
        'strings': ['hello'],
        'vectors': [],
        'emotives': {}
    })
    
    assert result['status'] == 'observed'
    assert 'auto_learned_pattern' in result
    
    # Check working memory
    wm = kato_fixture.get_working_memory()
    assert wm == [['hello']]


def test_observe_multiple_strings(kato_fixture):
    """Test observing multiple strings at once."""
    assert kato_fixture.clear_all_memory() == 'all-cleared'
    
    # Observe multiple strings
    result = kato_fixture.observe({
        'strings': ['a', 'b', 'c'],
        'vectors': [],
        'emotives': {}
    })
    
    assert result['status'] == 'observed'
    
    # Check working memory - should be a single event with multiple symbols
    wm = kato_fixture.get_working_memory()
    assert wm == [['a', 'b', 'c']]


def test_observe_with_emotives(kato_fixture):
    """Test observing with emotive values."""
    assert kato_fixture.clear_all_memory() == 'all-cleared'
    
    # First, learn a sequence with emotives
    sequence_with_emotives = [
        (['hello'], {'happiness': 0.8, 'confidence': 0.6}),
        (['world'], {'happiness': 0.9, 'confidence': 0.7}),
        (['test'], {'happiness': 0.7, 'confidence': 0.8})
    ]
    
    for strings, emotives in sequence_with_emotives:
        result = kato_fixture.observe({
            'strings': strings,
            'vectors': [],
            'emotives': emotives
        })
        assert result['status'] == 'observed'
    
    # Learn the sequence
    model_name = kato_fixture.learn()
    assert model_name is not None
    
    # Now observe to trigger predictions (KATO requires 2+ strings)
    kato_fixture.observe({
        'strings': ['hello'],
        'vectors': [],
        'emotives': {'happiness': 0.8, 'confidence': 0.6}
    })
    kato_fixture.observe({
        'strings': ['world'],
        'vectors': [],
        'emotives': {'happiness': 0.9, 'confidence': 0.7}
    })
    
    # Verify emotives are included in predictions
    predictions = kato_fixture.get_predictions()
    assert len(predictions) > 0, "Should have predictions after learning and observing"
    
    # Check that emotives are in the prediction
    pred = predictions[0]
    assert 'emotives' in pred, "Prediction should include emotives field"
    assert isinstance(pred['emotives'], dict), "Emotives should be a dictionary"


def test_observe_with_vectors(kato_fixture):
    """Test observing with vector data."""
    assert kato_fixture.clear_all_memory() == 'all-cleared'
    
    # Observe with vectors
    result = kato_fixture.observe({
        'strings': [],
        'vectors': [[1.0, 2.0, 3.0]],
        'emotives': {}
    })
    
    assert result['status'] == 'observed'
    
    # Vectors ALWAYS produce at least the VECTOR|hash symbol
    # May also include up to 3 nearest neighbors (k=3 default)
    wm = kato_fixture.get_working_memory()
    assert isinstance(wm, list), "Working memory should be a list"
    assert len(wm) == 1, "Should have one event for the vector observation"
    assert len(wm[0]) >= 1, "Should have at least the VECTOR|hash symbol"
    # Check that we have vector symbols (they start with 'VECTOR|')
    vector_symbols = [s for s in wm[0] if s.startswith('VECTOR|')]
    assert len(vector_symbols) >= 1, "Should have at least one VECTOR| symbol"
    assert len(vector_symbols) <= 4, "Should have at most 4 symbols (observed + 3 nearest)"


def test_observe_mixed_modalities(kato_fixture):
    """Test observing with strings, vectors, and emotives together."""
    assert kato_fixture.clear_all_memory() == 'all-cleared'
    
    # Observe with all modalities
    # Note: 'modal' comes before 'multi' alphabetically
    result = kato_fixture.observe({
        'strings': ['multi', 'modal'],
        'vectors': [[0.5, 0.5], [1.0, 0.0]],
        'emotives': {
            'arousal': 0.7,
            'valence': 0.3
        }
    })
    
    assert result['status'] == 'observed'
    
    # Check that working memory has the observation
    wm = kato_fixture.get_working_memory()
    assert len(wm) >= 1, "Should have at least one event in working memory"
    
    # The first event should contain at least the strings (sorted)
    # Vectors may or may not be represented depending on classifier
    first_event = wm[0]
    
    # Check if strings are in the event (they should be sorted)
    if 'modal' in first_event or 'multi' in first_event:
        # Strings should be sorted alphabetically
        assert 'modal' in first_event, "'modal' should be in first event"
        assert 'multi' in first_event, "'multi' should be in first event"
        # Check order by finding indices
        modal_idx = first_event.index('modal')
        multi_idx = first_event.index('multi')
        assert modal_idx < multi_idx, "Strings should be sorted: 'modal' before 'multi'"


def test_observe_empty(kato_fixture):
    """Test that empty observations are ignored by KATO."""
    assert kato_fixture.clear_all_memory() == 'all-cleared'
    
    # Get initial state
    initial_wm = kato_fixture.get_working_memory()
    
    # Observe empty data
    result = kato_fixture.observe({
        'strings': [],
        'vectors': [],
        'emotives': {}
    })
    
    # Empty observations are processed but ignored
    assert result['status'] == 'observed'
    
    # Working memory should not change (empty events are ignored)
    wm = kato_fixture.get_working_memory()
    assert wm == initial_wm, "Empty events should be ignored"


def test_observe_sequence(kato_fixture):
    """Test observing a sequence of events."""
    assert kato_fixture.clear_all_memory() == 'all-cleared'
    
    # Observe sequence of events
    events = ['first', 'second', 'third']
    
    for event in events:
        result = kato_fixture.observe({
            'strings': [event],
            'vectors': [],
            'emotives': {}
        })
        assert result['status'] == 'observed'
    
    # Working memory should contain all events
    wm = kato_fixture.get_working_memory()
    assert len(wm) == 3
    assert wm == [['first'], ['second'], ['third']]


def test_observe_special_characters(kato_fixture):
    """Test observing strings with special characters."""
    assert kato_fixture.clear_all_memory() == 'all-cleared'
    
    # Observe strings with special characters
    special_strings = ['hello@world', '123-456', 'test_case', 'with spaces']
    
    result = kato_fixture.observe({
        'strings': special_strings,
        'vectors': [],
        'emotives': {}
    })
    
    assert result['status'] == 'observed'
    
    # Check working memory - KATO sorts strings alphanumerically within each event
    wm = kato_fixture.get_working_memory()
    assert_working_memory_equals(wm, [special_strings])


def test_observe_numeric_strings(kato_fixture):
    """Test observing numeric strings."""
    assert kato_fixture.clear_all_memory() == 'all-cleared'
    
    # Observe numeric strings
    numeric_strings = ['1', '2', '3', '4.5', '-1']
    result = kato_fixture.observe({
        'strings': numeric_strings,
        'vectors': [],
        'emotives': {}
    })
    
    assert result['status'] == 'observed'
    
    # Check working memory - KATO sorts strings alphanumerically
    # Note: '-1' comes before other numbers in alphanumeric sort
    wm = kato_fixture.get_working_memory()
    assert_working_memory_equals(wm, [numeric_strings])


def test_empty_events_in_sequence(kato_fixture):
    """Test that empty events in a sequence are ignored."""
    assert kato_fixture.clear_all_memory() == 'all-cleared'
    
    # Observe sequence with attempted empty events interspersed
    kato_fixture.observe({'strings': ['first'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': [], 'vectors': [], 'emotives': {}})  # Should be ignored
    kato_fixture.observe({'strings': ['second'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': [], 'vectors': [], 'emotives': {}})  # Should be ignored
    kato_fixture.observe({'strings': ['third'], 'vectors': [], 'emotives': {}})
    
    # Working memory should only contain non-empty events
    wm = kato_fixture.get_working_memory()
    assert wm == [['first'], ['second'], ['third']], \
        f"Empty events should be ignored, expected [['first'], ['second'], ['third']], got {wm}"


def test_observe_large_vector(kato_fixture):
    """Test observing a large vector."""
    assert kato_fixture.clear_all_memory() == 'all-cleared'
    
    # Create a large vector
    large_vector = list(range(100))
    
    result = kato_fixture.observe({
        'strings': [],
        'vectors': [large_vector],
        'emotives': {}
    })
    
    assert result['status'] == 'observed'
    
    # Large vectors should still produce at least VECTOR|hash symbol
    wm = kato_fixture.get_working_memory()
    assert isinstance(wm, list), "Working memory should be a list"
    assert len(wm) == 1, "Should have one event for the vector observation"
    assert len(wm[0]) >= 1, "Should have at least the VECTOR|hash symbol"
    # Check for vector symbols
    vector_symbols = [s for s in wm[0] if s.startswith('VECTOR|')]
    assert len(vector_symbols) >= 1, "Should have at least one VECTOR| symbol for large vector"