"""
Comprehensive tests for KATO prediction fields.
Tests the correct usage of past, present, future, missing, and extras fields.
"""

import pytest
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from fixtures.kato_fixtures import kato_fixture as kato_fixture
from fixtures.test_helpers import sort_event_strings


def test_prediction_past_field(kato_fixture):
    """Test that the past field correctly shows events before the present matching portion.
    
    IMPORTANT: The 'present' field includes ALL events containing matching symbols,
    from the first match to the last match, not just explicitly "middle" events.
    """
    kato_fixture.clear_all_memory()
    kato_fixture.set_recall_threshold(0.3)
    
    # Simple test case - observe middle and end from a beginning/middle/end sequence
    # Learn: [['beginning'], ['middle'], ['end']]
    kato_fixture.observe({'strings': ['beginning'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['middle'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['end'], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()
    
    # Observe: [['middle'], ['end']]
    kato_fixture.clear_short_term_memory()
    kato_fixture.observe({'strings': ['middle'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['end'], 'vectors': [], 'emotives': {}})
    
    predictions = kato_fixture.get_predictions()
    assert len(predictions) > 0, "Should have predictions"
    
    pred = predictions[0]
    past = pred.get('past', [])
    present = pred.get('present', [])
    future = pred.get('future', [])
    
    # Validate temporal segmentation
    # Past should contain the beginning event (before first match)
    assert past == [['beginning']], f"Past should be [['beginning']], got {past}"
    
    # Present should contain BOTH middle and end events (all matching events)
    # This is the CORRECT behavior - present includes ALL events with matches
    assert present == [['middle'], ['end']], f"Present should be [['middle'], ['end']], got {present}"
    
    # Future should be empty (no events after last match)
    assert future == [], f"Future should be empty, got {future}"


def test_prediction_missing_symbols(kato_fixture):
    """Test missing field when symbols are expected but not observed in present."""
    kato_fixture.clear_all_memory()
    
    # Learn: [['hello', 'world'], ['foo', 'bar']]
    kato_fixture.observe({'strings': sort_event_strings(['hello', 'world']), 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': sort_event_strings(['foo', 'bar']), 'vectors': [], 'emotives': {}})
    kato_fixture.learn()
    
    # Observe only partial symbols from each event
    kato_fixture.clear_short_term_memory()
    kato_fixture.observe({'strings': ['hello'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['foo'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()

    # Get the prediction (should be only one for this learned sequence)
    assert len(predictions) > 0, "Should have at least one prediction"
    pred = predictions[0]
    
    missing = pred.get('missing', [])
    # Should be missing 'world' from first event and 'bar' from second
    # Event-structured format: one sub-list per event
    assert missing == [['world'], ['bar']], \
        f"Missing field should contain [['world'], ['bar']], got {missing}"


def test_prediction_extra_symbols(kato_fixture):
    """Test extras field when unexpected symbols are observed."""
    kato_fixture.clear_all_memory()
    
    # Learn: [['alpha'], ['beta']]
    sequence = ['alpha', 'beta']
    for item in sequence:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()
    
    # Observe with unexpected additional symbols
    kato_fixture.clear_short_term_memory()
    kato_fixture.observe({'strings': sort_event_strings(['alpha', 'unexpected']), 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': sort_event_strings(['beta', 'extra']), 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()
    
    # Find matching prediction
    for pred in predictions:
        if 'alpha' in pred.get('matches', []) or 'beta' in pred.get('matches', []):
            extras = pred.get('extras', [])
            # Should have 'unexpected' and 'extra' as extras (event-structured)
            # Flatten to check if extras exist
            flat_extras = [item for sublist in extras for item in sublist] if extras and isinstance(extras[0], list) else extras
            assert 'unexpected' in flat_extras or 'extra' in flat_extras, \
                f"Should have extras, got {extras}"
            break


def test_prediction_multi_event_present(kato_fixture):
    """Test present field spanning multiple events with partial matches."""
    kato_fixture.clear_all_memory()
    
    # Learn: [['a', 'b'], ['c', 'd'], ['e', 'f']]
    events = [
        sort_event_strings(['a', 'b']),
        sort_event_strings(['c', 'd']),
        sort_event_strings(['e', 'f'])
    ]
    for event in events:
        kato_fixture.observe({'strings': event, 'vectors': [], 'emotives': {}})
    kato_fixture.learn()
    
    # Observe partial matches across two events
    kato_fixture.clear_short_term_memory()
    kato_fixture.observe({'strings': ['a'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['c'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()
    
    # Get the prediction (should be only one for this learned sequence)
    assert len(predictions) > 0, "Should have at least one prediction"
    pred = predictions[0]
    
    present = pred.get('present', [])
    missing = pred.get('missing', [])
    future = pred.get('future', [])
    
    # Present should span the two matching events
    assert len(present) == 2, f"Present should have 2 events, got {present}"
    # Missing should include 'b' and 'd' in event-structured format
    assert missing == [['b'], ['d']], f"Missing should be [['b'], ['d']], got {missing}"
    # Future should have the third event
    assert len(future) == 1, f"Should have 1 future event, got {future}"


def test_prediction_contiguous_present(kato_fixture):
    """Test that present includes all contiguous matching events."""
    kato_fixture.clear_all_memory()
    
    # Learn: [['one'], ['two'], ['three'], ['four']]
    sequence = ['one', 'two', 'three', 'four']
    for item in sequence:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()
    
    # Observe middle contiguous events
    kato_fixture.clear_short_term_memory()
    kato_fixture.observe({'strings': ['two'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['three'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()
    
    # Find matching prediction
    for pred in predictions:
        if 'two' in pred.get('matches', []) and 'three' in pred.get('matches', []):
            past = pred.get('past', [])
            present = pred.get('present', [])
            future = pred.get('future', [])
            
            # Past should have 'one'
            assert [['one']] == past or ['one'] in past, f"Past should contain 'one', got {past}"
            # Present should have both 'two' and 'three'
            assert len(present) == 2, f"Present should have 2 events, got {present}"
            # Future should have 'four'
            assert [['four']] == future or ['four'] in future, f"Future should contain 'four', got {future}"
            break


def test_prediction_partial_match_at_start(kato_fixture):
    """Test partial match at the beginning of a sequence."""
    kato_fixture.clear_all_memory()
    
    # Learn: [['start', 'begin'], ['middle'], ['end']]
    kato_fixture.observe({'strings': sort_event_strings(['start', 'begin']), 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['middle'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['end'], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()
    
    # Observe only partial match of first event plus one more to meet 2+ requirement
    kato_fixture.clear_short_term_memory()
    kato_fixture.observe({'strings': ['begin'], 'vectors': [], 'emotives': {}})
    # Need to observe at least 2 strings for predictions
    kato_fixture.observe({'strings': ['middle'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()
    
    # Find matching prediction
    for pred in predictions:
        if 'begin' in pred.get('matches', []) and 'middle' in pred.get('matches', []):
            present = pred.get('present', [])
            missing = pred.get('missing', [])
            future = pred.get('future', [])
            
            # Present should be the first two events (both have matches)
            # The first event should have both 'begin' and 'start', but we only observed 'begin'
            assert len(present) == 2, f"Present should have 2 events, got {present}"
            # Missing should include 'start' (in first event but not observed) - event-structured
            flat_missing = [s for event in missing for s in event] if missing and isinstance(missing[0], list) else missing
            assert 'start' in flat_missing, f"Should be missing 'start', got missing={missing}"
            # Future should have the last event
            assert len(future) == 1, f"Should have 1 future event, got {future}"
            assert future == [['end']], f"Future should be [['end']], got {future}"
            break


def test_prediction_partial_match_at_end(kato_fixture):
    """Test partial match at the end of a sequence."""
    kato_fixture.clear_all_memory()
    
    # Learn: [['start'], ['middle'], ['end', 'finish']]
    kato_fixture.observe({'strings': ['start'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['middle'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': sort_event_strings(['end', 'finish']), 'vectors': [], 'emotives': {}})
    kato_fixture.learn()
    
    # Observe partial match including last event
    kato_fixture.clear_short_term_memory()
    kato_fixture.observe({'strings': ['middle'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['end'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()
    
    # Find matching prediction
    for pred in predictions:
        if 'middle' in pred.get('matches', []) and 'end' in pred.get('matches', []):
            past = pred.get('past', [])
            present = pred.get('present', [])
            missing = pred.get('missing', [])
            
            # Past should have 'start'
            assert [['start']] == past or ['start'] in past, f"Past should contain 'start', got {past}"
            # Present should span middle and end events
            assert len(present) == 2, f"Present should have 2 events, got {present}"
            # Missing should include 'finish' - event-structured
            flat_missing = [s for event in missing for s in event] if missing and isinstance(missing[0], list) else missing
            assert 'finish' in flat_missing, f"Should be missing 'finish', got missing={missing}"
            break


def test_prediction_mixed_missing_and_extras(kato_fixture):
    """Test prediction with both missing and extra symbols."""
    kato_fixture.clear_all_memory()
    
    # Learn: [['a', 'b'], ['c', 'd']]
    kato_fixture.observe({'strings': sort_event_strings(['a', 'b']), 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': sort_event_strings(['c', 'd']), 'vectors': [], 'emotives': {}})
    kato_fixture.learn()
    
    # Observe with missing 'b' and 'd', but with extras 'x' and 'y'
    kato_fixture.clear_short_term_memory()
    kato_fixture.observe({'strings': sort_event_strings(['a', 'x']), 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': sort_event_strings(['c', 'y']), 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()
    
    # Get the prediction (should be only one for this learned sequence)
    assert len(predictions) > 0, "Should have at least one prediction"
    pred = predictions[0]
    
    missing = pred.get('missing', [])
    extras = pred.get('extras', [])

    # Should have both missing and extras in event-structured format
    assert missing == [['b'], ['d']], f"Missing should be [['b'], ['d']], got {missing}"
    assert extras == [['x'], ['y']], f"Extras should be [['x'], ['y']], got {extras}"


def test_prediction_multiple_past_events(kato_fixture):
    """Test prediction with multiple events in the past."""
    kato_fixture.clear_all_memory()
    
    # Learn: [['first'], ['second'], ['third'], ['fourth'], ['fifth']]
    sequence = ['first', 'second', 'third', 'fourth', 'fifth']
    for item in sequence:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()
    
    # Observe events in the middle
    kato_fixture.clear_short_term_memory()
    kato_fixture.observe({'strings': ['third'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['fourth'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()
    
    # Find matching prediction
    for pred in predictions:
        if 'third' in pred.get('matches', []) and 'fourth' in pred.get('matches', []):
            past = pred.get('past', [])
            present = pred.get('present', [])
            future = pred.get('future', [])
            
            # Past should have 'first' and 'second'
            assert len(past) == 2, f"Past should have 2 events, got {past}"
            past_items = [item for event in past for item in event if isinstance(event, list)]
            assert 'first' in past_items and 'second' in past_items, \
                f"Past should contain 'first' and 'second', got {past}"
            
            # Present should have 'third' and 'fourth'
            assert len(present) == 2, f"Present should have 2 events, got {present}"
            
            # Future should have 'fifth'
            assert [['fifth']] == future or ['fifth'] in future, \
                f"Future should contain 'fifth', got {future}"
            break


def test_single_event_with_missing(kato_fixture):
    """Test a single event observation with missing symbols."""
    kato_fixture.clear_all_memory()
    # Set lower threshold for missing symbol detection
    kato_fixture.set_recall_threshold(0.2)
    
    # Learn a single event with multiple symbols (will be sorted to ['alpha', 'beta', 'gamma'])
    kato_fixture.observe({'strings': sort_event_strings(['alpha', 'beta', 'gamma']), 'vectors': [], 'emotives': {}})
    kato_fixture.learn()
    
    # Observe partial symbols from the learned event (KATO requires 2+ strings)
    kato_fixture.clear_short_term_memory()
    # Observe as a single event with only some symbols to match the learned structure
    kato_fixture.observe({'strings': sort_event_strings(['alpha', 'gamma']), 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()
    
    # Get the prediction (should be only one for this learned sequence)
    assert len(predictions) > 0, "Should have at least one prediction"
    pred = predictions[0]
    
    missing = pred.get('missing', [])
    # Should be missing 'beta' since we observed 'alpha' and 'gamma' - event-structured
    flat_missing = [s for event in missing for s in event] if missing and isinstance(missing[0], list) else missing
    assert 'beta' in flat_missing, \
        f"Should be missing 'beta', got missing={missing}"