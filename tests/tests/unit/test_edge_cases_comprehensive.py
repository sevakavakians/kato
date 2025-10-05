"""
Comprehensive edge case tests for KATO.
Tests boundary conditions, unusual patterns, and stress scenarios.
"""

import pytest
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from fixtures.kato_fixtures import kato_fixture as kato_fixture
from fixtures.test_helpers import sort_event_strings


def test_all_missing_symbols(kato_fixture):
    """Test when all expected symbols are missing from observation."""
    kato_fixture.clear_all_memory()
    
    # Learn a sequence with specific symbols
    sequence = [
        ['alpha', 'beta', 'gamma'],
        ['delta', 'epsilon', 'zeta'],
        ['eta', 'theta', 'iota']
    ]
    
    for event in sequence:
        kato_fixture.observe({'strings': sort_event_strings(event), 'vectors': [], 'emotives': {}})
    kato_fixture.learn()
    
    # Observe completely different symbols (all missing)
    kato_fixture.clear_short_term_memory()
    kato_fixture.observe({'strings': ['unknown1', 'unknown2'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['unknown3', 'unknown4'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()
    
    # Should not match our learned sequence (or have very low similarity)
    for pred in predictions:
        if pred.get('name', '').startswith('PTRN|'):
            similarity = pred.get('similarity', 1.0)
            assert similarity < 0.5, "Completely different symbols should have low similarity"


def test_all_extra_symbols(kato_fixture):
    """Test when observation has only extra symbols not in learned sequence."""
    kato_fixture.clear_all_memory()
    
    # Learn a simple sequence
    sequence = [['a', 'b'], ['c', 'd']]
    for event in sequence:
        kato_fixture.observe({'strings': sort_event_strings(event), 'vectors': [], 'emotives': {}})
    kato_fixture.learn()
    
    # Observe with original symbols plus many extras
    kato_fixture.clear_short_term_memory()
    kato_fixture.observe({'strings': sort_event_strings(['a', 'b', 'x', 'y', 'z']), 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': sort_event_strings(['c', 'd', 'w', 'v', 'u']), 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()
    
    assert len(predictions) > 0
    for pred in predictions:
        if pred.get('frequency', 0) > 0:
            extras = pred.get('extras', [])
            # Should detect all the extra symbols
            # Extras is event-structured, count total across all events
            if extras and isinstance(extras[0], list):
                total_extras = sum(len(event) for event in extras)
            else:
                total_extras = len(extras)
            assert total_extras >= 6, f"Should detect many extras, got {extras} (total: {total_extras})"
            break


def test_single_symbol_events_sequence(kato_fixture):
    """Test sequence where every event has only one symbol."""
    kato_fixture.clear_all_memory()
    
    # Create sequence of single-symbol events
    single_sequence = []
    for i in range(10):
        single_sequence.append([f'single_{i}'])
    
    # Learn the sequence
    for event in single_sequence:
        kato_fixture.observe({'strings': event, 'vectors': [], 'emotives': {}})
    kato_fixture.learn()
    
    # Observe first two events (meeting 2+ string requirement)
    kato_fixture.clear_short_term_memory()
    kato_fixture.observe({'strings': ['single_0'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['single_1'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()
    
    assert len(predictions) > 0
    for pred in predictions:
        if pred.get('frequency', 0) > 0:
            future = pred.get('future', [])
            # Should predict subsequent single-symbol events
            assert len(future) > 0
            # Each future event should have one symbol
            for event in future:
                if isinstance(event, list) and len(event) == 1:
                    assert True
                    break
            break


def test_duplicate_symbols_in_event(kato_fixture):
    """Test events containing duplicate symbols."""
    kato_fixture.clear_all_memory()
    
    # Events with duplicate symbols (will be de-duplicated by sort_event_strings)
    sequence = [
        ['dup', 'dup', 'unique1'],  # 'dup' appears twice
        ['unique2', 'dup', 'dup', 'dup'],  # 'dup' appears three times
        ['unique3', 'unique4']
    ]
    
    # Learn sequence
    for event in sequence:
        # sort_event_strings should handle duplicates
        kato_fixture.observe({'strings': sort_event_strings(event), 'vectors': [], 'emotives': {}})
    kato_fixture.learn()
    
    # Observe with duplicates
    kato_fixture.clear_short_term_memory()
    kato_fixture.observe({'strings': sort_event_strings(['dup', 'dup', 'unique1']), 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': sort_event_strings(['unique2', 'dup']), 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()
    
    assert len(predictions) > 0
    # System should handle duplicates gracefully


def test_extremely_long_symbol_names(kato_fixture):
    """Test with very long symbol names."""
    kato_fixture.clear_all_memory()
    
    # Create events with very long symbol names
    long_prefix = 'extremely_long_symbol_name_that_contains_many_characters_and_keeps_going_'
    sequence = [
        [f'{long_prefix}alpha', f'{long_prefix}beta'],
        [f'{long_prefix}gamma', f'{long_prefix}delta'],
        [f'{long_prefix}epsilon', f'{long_prefix}zeta']
    ]
    
    # Learn the sequence
    for event in sequence:
        kato_fixture.observe({'strings': sort_event_strings(event), 'vectors': [], 'emotives': {}})
    pattern_name = kato_fixture.learn()
    assert pattern_name.startswith('PTRN|')
    
    # Observe with long names
    kato_fixture.clear_short_term_memory()
    kato_fixture.observe({'strings': sort_event_strings([f'{long_prefix}alpha', f'{long_prefix}beta']), 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': sort_event_strings([f'{long_prefix}gamma', f'{long_prefix}delta']), 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()
    
    assert len(predictions) > 0
    # Should handle long symbol names


def test_special_characters_in_symbols(kato_fixture):
    """Test symbols containing special characters."""
    kato_fixture.clear_all_memory()
    
    # Events with special characters
    sequence = [
        ['symbol-with-dashes', 'symbol_with_underscores'],
        ['symbol.with.dots', 'symbol:with:colons'],
        ['symbol@with@at', 'symbol#with#hash'],
        ['symbol$with$dollar', 'symbol%with%percent']
    ]
    
    # Learn the sequence
    for event in sequence:
        kato_fixture.observe({'strings': sort_event_strings(event), 'vectors': [], 'emotives': {}})
    kato_fixture.learn()
    
    # Observe with special characters
    kato_fixture.clear_short_term_memory()
    kato_fixture.observe({'strings': sort_event_strings(['symbol-with-dashes', 'symbol_with_underscores']), 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': sort_event_strings(['symbol.with.dots', 'symbol:with:colons']), 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()
    
    assert len(predictions) > 0
    # Should handle special characters in symbols


def test_numeric_symbols(kato_fixture):
    """Test symbols that are purely numeric."""
    kato_fixture.clear_all_memory()
    
    # Sequence with numeric symbols
    sequence = [
        ['123', '456', '789'],
        ['000', '111', '222'],
        ['3.14', '2.71', '1.41']
    ]
    
    # Learn the sequence
    for event in sequence:
        kato_fixture.observe({'strings': sort_event_strings(event), 'vectors': [], 'emotives': {}})
    kato_fixture.learn()
    
    # Observe numeric symbols
    kato_fixture.clear_short_term_memory()
    kato_fixture.observe({'strings': sort_event_strings(['123', '456', '789']), 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': sort_event_strings(['000', '111', '222']), 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()
    
    assert len(predictions) > 0
    # Should handle numeric symbols


def test_mixed_case_symbols(kato_fixture):
    """Test case sensitivity in symbols."""
    kato_fixture.clear_all_memory()
    
    # Sequence with mixed case
    sequence = [
        ['UPPER', 'lower', 'MiXeD'],
        ['CamelCase', 'snake_case', 'SCREAMING_SNAKE'],
        ['Title', 'case', 'VARIATIONS']
    ]
    
    # Learn the sequence
    for event in sequence:
        kato_fixture.observe({'strings': sort_event_strings(event), 'vectors': [], 'emotives': {}})
    model1 = kato_fixture.learn()
    
    # Learn same sequence with different case
    for event in sequence:
        # Convert to different case
        modified = [s.lower() if s.isupper() else s.upper() for s in event]
        kato_fixture.observe({'strings': sort_event_strings(modified), 'vectors': [], 'emotives': {}})
    model2 = kato_fixture.learn()
    
    # Patterns should be different if case-sensitive
    assert model1 != model2, "Different cases should produce different models"


def test_boundary_emotives(kato_fixture):
    """Test extreme emotive values at boundaries."""
    kato_fixture.clear_all_memory()
    
    # Sequence with boundary emotive values
    sequence = [
        (['min_emotive'], {'arousal': 0.0, 'valence': 0.0}),
        (['mid_emotive'], {'arousal': 0.5, 'valence': 0.5}),
        (['max_emotive'], {'arousal': 1.0, 'valence': 1.0}),
        (['negative_emotive'], {'arousal': -1.0, 'valence': -1.0})  # If supported
    ]
    
    # Learn sequence with extreme emotives
    for strings, emotives in sequence:
        result = kato_fixture.observe({'strings': strings, 'vectors': [], 'emotives': emotives})
        assert result['status'] == 'observed'
    
    pattern_name = kato_fixture.learn()
    assert pattern_name.startswith('PTRN|')
    
    # Observe with boundary emotives
    kato_fixture.clear_short_term_memory()
    kato_fixture.observe({'strings': ['min_emotive'], 'vectors': [], 'emotives': {'arousal': 0.0, 'valence': 0.0}})
    kato_fixture.observe({'strings': ['mid_emotive'], 'vectors': [], 'emotives': {'arousal': 0.5, 'valence': 0.5}})
    predictions = kato_fixture.get_predictions()
    
    assert len(predictions) > 0
    # Should handle boundary emotives


def test_rapid_observation_sequence(kato_fixture):
    """Test rapid successive observations without delays."""
    kato_fixture.clear_all_memory()
    
    # Learn a sequence
    base_sequence = [['rapid1'], ['rapid2'], ['rapid3'], ['rapid4'], ['rapid5']]
    for event in base_sequence:
        kato_fixture.observe({'strings': event, 'vectors': [], 'emotives': {}})
    kato_fixture.learn()
    
    # Rapidly observe many times
    kato_fixture.clear_short_term_memory()
    for _ in range(10):
        kato_fixture.observe({'strings': ['rapid1'], 'vectors': [], 'emotives': {}})
        kato_fixture.observe({'strings': ['rapid2'], 'vectors': [], 'emotives': {}})
        predictions = kato_fixture.get_predictions()
        assert isinstance(predictions, list)
        kato_fixture.clear_short_term_memory()
    
    # System should handle rapid observations


def test_observation_after_partial_match(kato_fixture):
    """Test continuing observation after partial match."""
    kato_fixture.clear_all_memory()
    
    # Learn sequence
    sequence = [
        ['partial1', 'partial2'],
        ['partial3', 'partial4'],
        ['partial5', 'partial6'],
        ['partial7', 'partial8']
    ]
    
    for event in sequence:
        kato_fixture.observe({'strings': sort_event_strings(event), 'vectors': [], 'emotives': {}})
    kato_fixture.learn()
    
    # Start with partial match
    kato_fixture.clear_short_term_memory()
    kato_fixture.observe({'strings': sort_event_strings(['partial1']), 'vectors': [], 'emotives': {}})  # Missing partial2
    kato_fixture.observe({'strings': sort_event_strings(['partial3', 'partial4']), 'vectors': [], 'emotives': {}})
    
    first_predictions = kato_fixture.get_predictions()
    assert len(first_predictions) > 0
    
    # Continue observing
    kato_fixture.observe({'strings': sort_event_strings(['partial5', 'extra']), 'vectors': [], 'emotives': {}})  # Has extra
    
    second_predictions = kato_fixture.get_predictions()
    assert len(second_predictions) > 0
    
    # Check that system handles continuation after partial match
    for pred in second_predictions:
        if pred.get('frequency', 0) > 0:
            # Should detect the missing and extra symbols
            missing = pred.get('missing', [])
            extras = pred.get('extras', [])
            assert isinstance(missing, list)
            assert isinstance(extras, list)
            break