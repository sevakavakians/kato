"""
Unit tests specifically for KATO's alphanumeric sorting behavior.
KATO sorts strings alphanumerically within each event but preserves event order.
"""

import pytest
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Use FastAPI fixture if available, otherwise fall back to old fixture
if os.environ.get('USE_FASTAPI', 'false').lower() == 'true':
    from fixtures.kato_fastapi_fixtures import kato_fastapi_existing as kato_fixture
else:
    from fixtures.kato_fixtures import kato_fixture
from fixtures.test_helpers import sort_event_strings


def test_alphanumeric_sorting_within_event(kato_fixture):
    """Test that KATO sorts strings alphanumerically within a single event."""
    kato_fixture.clear_all_memory()
    
    # Test various sorting scenarios
    test_cases = [
        # (input, expected_sorted)
        (['z', 'a', 'm'], ['a', 'm', 'z']),
        (['3', '1', '2'], ['1', '2', '3']),
        (['Zoo', 'Apple', 'apple'], ['Apple', 'Zoo', 'apple']),  # Capital letters come first
        (['test_2', 'test_1', 'test_10'], ['test_1', 'test_10', 'test_2']),  # Alphanumeric, not numeric
        (['!special', '@symbol', '#hash'], ['!special', '#hash', '@symbol']),
    ]
    
    for input_strings, expected_sorted in test_cases:
        kato_fixture.clear_short_term_memory()
        
        # Observe the unsorted strings
        kato_fixture.observe({
            'strings': input_strings,
            'vectors': [],
            'emotives': {}
        })
        
        # Get short-term memory
        stm = kato_fixture.get_short_term_memory()
        
        # Verify sorting
        assert len(stm) == 1, f"Expected single event in short-term memory"
        assert stm[0] == expected_sorted, \
            f"Sorting mismatch for {input_strings}: got {stm[0]}, expected {expected_sorted}"


def test_event_order_preserved(kato_fixture):
    """Test that the order of events is preserved even though strings within events are sorted."""
    kato_fixture.clear_all_memory()
    
    # Observe multiple events with unsorted strings
    events = [
        ['z', 'y', 'x'],  # Will be sorted to ['x', 'y', 'z']
        ['c', 'b', 'a'],  # Will be sorted to ['a', 'b', 'c']
        ['3', '2', '1'],  # Will be sorted to ['1', '2', '3']
    ]
    
    for event in events:
        kato_fixture.observe({
            'strings': event,
            'vectors': [],
            'emotives': {}
        })
    
    # Get short-term memory
    stm = kato_fixture.get_short_term_memory()
    
    # Verify event order is preserved
    assert len(stm) == 3, "Should have 3 events"
    assert stm[0] == sort_event_strings(events[0]), "First event strings should be sorted"
    assert stm[1] == sort_event_strings(events[1]), "Second event strings should be sorted"
    assert stm[2] == sort_event_strings(events[2]), "Third event strings should be sorted"
    
    # Verify the order: first event, then second, then third
    assert stm == [
        ['x', 'y', 'z'],
        ['a', 'b', 'c'],
        ['1', '2', '3']
    ]


def test_single_string_unchanged(kato_fixture):
    """Test that single strings in events are unchanged (no sorting needed)."""
    kato_fixture.clear_all_memory()
    
    # Observe single string events
    single_events = ['first', 'second', 'third']
    
    for event in single_events:
        kato_fixture.observe({
            'strings': [event],
            'vectors': [],
            'emotives': {}
        })
    
    # Get short-term memory
    stm = kato_fixture.get_short_term_memory()
    
    # Single strings should be unchanged
    assert stm == [['first'], ['second'], ['third']]


def test_mixed_case_sorting(kato_fixture):
    """Test sorting behavior with mixed case strings."""
    kato_fixture.clear_all_memory()
    
    # Mixed case strings - capitals typically sort before lowercase
    mixed_case = ['zebra', 'Zebra', 'ZEBRA', 'apple', 'Apple', 'APPLE']
    
    kato_fixture.observe({
        'strings': mixed_case,
        'vectors': [],
        'emotives': {}
    })
    
    stm = kato_fixture.get_short_term_memory()
    
    # Verify that capitals come before lowercase in alphanumeric sort
    assert len(stm) == 1
    sorted_result = stm[0]
    
    # The exact order depends on Python's sort, but generally:
    # APPLE, Apple, ZEBRA, Zebra, apple, zebra
    assert sorted_result == sorted(mixed_case)


def test_numeric_string_sorting(kato_fixture):
    """Test that numeric strings are sorted alphanumerically, not numerically."""
    kato_fixture.clear_all_memory()
    
    # These will be sorted as strings, not numbers
    numeric_strings = ['10', '2', '1', '20', '100', '3']
    
    kato_fixture.observe({
        'strings': numeric_strings,
        'vectors': [],
        'emotives': {}
    })
    
    stm = kato_fixture.get_short_term_memory()
    
    # Alphanumeric sort: '1', '10', '100', '2', '20', '3'
    assert stm == [['1', '10', '100', '2', '20', '3']]


def test_special_characters_sorting(kato_fixture):
    """Test sorting with special characters."""
    kato_fixture.clear_all_memory()
    
    # Special characters typically come before alphanumeric
    special_strings = ['_underscore', '-dash', '@at', '#hash', 'normal', '1number']
    
    kato_fixture.observe({
        'strings': special_strings,
        'vectors': [],
        'emotives': {}
    })
    
    stm = kato_fixture.get_short_term_memory()
    
    # Verify they're sorted according to Python's default sort
    assert stm == [sorted(special_strings)]


def test_empty_strings_in_sorting(kato_fixture):
    """Test how empty strings are handled in sorting."""
    kato_fixture.clear_all_memory()
    
    # Include empty string
    with_empty = ['z', '', 'a', 'middle']
    
    kato_fixture.observe({
        'strings': with_empty,
        'vectors': [],
        'emotives': {}
    })
    
    stm = kato_fixture.get_short_term_memory()
    
    # Empty string should come first in alphanumeric sort
    assert stm == [['', 'a', 'middle', 'z']]


def test_unicode_sorting(kato_fixture):
    """Test sorting with unicode characters."""
    kato_fixture.clear_all_memory()
    
    # Unicode characters
    unicode_strings = ['école', 'zebra', 'åpple', 'ñoño', 'normal']
    
    kato_fixture.observe({
        'strings': unicode_strings,
        'vectors': [],
        'emotives': {}
    })
    
    stm = kato_fixture.get_short_term_memory()
    
    # Should be sorted according to Python's default unicode handling
    assert stm == [sorted(unicode_strings)]


def test_sorting_consistency_across_learns(kato_fixture):
    """Test that the same strings always sort the same way across different observations."""
    kato_fixture.clear_all_memory()
    
    # Same strings in different order
    strings_v1 = ['gamma', 'alpha', 'beta']
    strings_v2 = ['beta', 'gamma', 'alpha']
    strings_v3 = ['alpha', 'beta', 'gamma']
    
    # Observe and learn each version
    for strings in [strings_v1, strings_v2, strings_v3]:
        kato_fixture.clear_short_term_memory()
        kato_fixture.observe({
            'strings': strings,
            'vectors': [],
            'emotives': {}
        })
        stm = kato_fixture.get_short_term_memory()
        
        # All should result in the same sorted order
        assert stm == [['alpha', 'beta', 'gamma']], \
            f"Inconsistent sorting for {strings}"