"""
Unit tests for the rolling window auto-learn feature.

Tests both CLEAR (original) and ROLLING (new) modes of auto-learning.
"""

import pytest
from unittest.mock import patch
from kato.workers.kato_processor import KatoProcessor


def test_clear_mode_behavior(kato_fixture):
    """Test that CLEAR mode maintains original auto-learn behavior."""
    kato_fixture.clear_all_memory()
    
    # Set auto-learn parameters for CLEAR mode
    kato_fixture.update_genes({
        'max_pattern_length': 3,
        'stm_mode': 'CLEAR'
    })
    
    # Add events up to the threshold
    events = ['clear1', 'clear2', 'clear3']
    for event in events:
        kato_fixture.observe({'strings': [event], 'vectors': [], 'emotives': {}})
    
    # STM should be completely cleared after auto-learn
    stm = kato_fixture.get_short_term_memory()
    assert len(stm) == 0, f"CLEAR mode should empty STM, but got: {stm}"
    
    # Add new observation after auto-learn
    kato_fixture.observe({'strings': ['after_clear'], 'vectors': [], 'emotives': {}})
    stm = kato_fixture.get_short_term_memory()
    assert len(stm) == 1, f"Should have 1 event after clear, got: {stm}"
    assert stm[0] == ['after_clear'], f"Wrong event after clear: {stm}"


def test_rolling_mode_behavior(kato_fixture):
    """Test that ROLLING mode maintains a sliding window."""
    kato_fixture.clear_all_memory()
    
    # Set auto-learn parameters for ROLLING mode  
    kato_fixture.update_genes({
        'max_pattern_length': 3,
        'stm_mode': 'ROLLING'
    })
    
    # Add events up to the threshold
    events = ['roll1', 'roll2', 'roll3']
    for event in events:
        kato_fixture.observe({'strings': [event], 'vectors': [], 'emotives': {}})
    
    # STM should be maintained at max_pattern_length - 1 after auto-learn
    stm = kato_fixture.get_short_term_memory()
    assert len(stm) == 2, f"ROLLING mode should maintain window, but got length {len(stm)}: {stm}"
    assert stm == [['roll2'], ['roll3']], f"Wrong rolling window state: {stm}"
    
    # Add another event - should trigger another auto-learn and maintain window
    kato_fixture.observe({'strings': ['roll4'], 'vectors': [], 'emotives': {}})
    stm = kato_fixture.get_short_term_memory()
    assert len(stm) == 2, f"Rolling window should stay at size 2, got: {len(stm)}"
    assert stm == [['roll3'], ['roll4']], f"Wrong rolling window after 4th event: {stm}"


def test_rolling_mode_continuous_learning(kato_fixture):
    """Test that ROLLING mode learns multiple overlapping patterns."""
    kato_fixture.clear_all_memory()
    
    # Set auto-learn for rolling mode
    kato_fixture.update_genes({
        'max_pattern_length': 3,
        'stm_mode': 'ROLLING'
    })
    
    # Track pattern learning
    learned_patterns = []
    
    # Sequence: A -> B -> C -> D -> E
    sequence = ['A', 'B', 'C', 'D', 'E']
    for i, event in enumerate(sequence):
        result = kato_fixture.observe({'strings': [event], 'vectors': [], 'emotives': {}})
        
        # Auto-learn should happen at positions 2, 3, 4 (when STM reaches length 3)
        if i >= 2:  # 0-indexed, so positions 2, 3, 4 correspond to 3rd, 4th, 5th events
            assert 'auto_learned_pattern' in result, f"Should auto-learn at position {i}"
            if result.get('auto_learned_pattern'):
                learned_patterns.append(result['auto_learned_pattern'])
    
    # Should have learned 3 patterns: ABC, BCD, CDE
    assert len(learned_patterns) >= 3, f"Should learn at least 3 patterns, got {len(learned_patterns)}: {learned_patterns}"
    
    # Final STM should contain the last 2 events
    stm = kato_fixture.get_short_term_memory()
    assert len(stm) == 2, f"Final STM should have 2 events, got: {stm}"
    assert stm == [['D'], ['E']], f"Final STM should be [['D'], ['E']], got: {stm}"


def test_rolling_vs_clear_pattern_differences(kato_fixture):
    """Test that ROLLING mode learns more patterns than CLEAR mode."""
    # Test CLEAR mode first
    kato_fixture.clear_all_memory()
    kato_fixture.update_genes({
        'max_pattern_length': 3,
        'stm_mode': 'CLEAR'
    })
    
    clear_patterns = []
    sequence = ['X', 'Y', 'Z', 'W', 'V']
    for event in sequence:
        result = kato_fixture.observe({'strings': [event], 'vectors': [], 'emotives': {}})
        if result.get('auto_learned_pattern'):
            clear_patterns.append(result['auto_learned_pattern'])
    
    # Test ROLLING mode
    kato_fixture.clear_all_memory()
    kato_fixture.update_genes({
        'max_pattern_length': 3,
        'stm_mode': 'ROLLING'
    })
    
    rolling_patterns = []
    for event in sequence:
        result = kato_fixture.observe({'strings': [event], 'vectors': [], 'emotives': {}})
        if result.get('auto_learned_pattern'):
            rolling_patterns.append(result['auto_learned_pattern'])
    
    # ROLLING should learn more patterns than CLEAR
    assert len(rolling_patterns) > len(clear_patterns), \
        f"ROLLING should learn more patterns. CLEAR: {len(clear_patterns)}, ROLLING: {len(rolling_patterns)}"


def test_rolling_mode_with_different_window_sizes(kato_fixture):
    """Test ROLLING mode with various window sizes."""
    test_cases = [
        {'window_size': 2, 'sequence': ['A', 'B', 'C'], 'expected_final_stm_size': 1},
        {'window_size': 4, 'sequence': ['A', 'B', 'C', 'D', 'E'], 'expected_final_stm_size': 3},
    ]
    
    for case in test_cases:
        kato_fixture.clear_all_memory()
        kato_fixture.update_genes({
            'max_pattern_length': case['window_size'],
            'stm_mode': 'ROLLING'
        })
        
        for event in case['sequence']:
            kato_fixture.observe({'strings': [event], 'vectors': [], 'emotives': {}})
        
        stm = kato_fixture.get_short_term_memory()
        assert len(stm) == case['expected_final_stm_size'], \
            f"Window size {case['window_size']}: expected STM size {case['expected_final_stm_size']}, got {len(stm)}"


def test_rolling_mode_disabled_when_max_pattern_length_zero(kato_fixture):
    """Test that rolling mode is disabled when max_pattern_length is 0."""
    kato_fixture.clear_all_memory()
    kato_fixture.update_genes({
        'max_pattern_length': 0,  # Disabled
        'stm_mode': 'ROLLING'
    })
    
    # Add many events
    for i in range(10):
        result = kato_fixture.observe({'strings': [f'event_{i}'], 'vectors': [], 'emotives': {}})
        # Should not auto-learn
        assert not result.get('auto_learned_pattern'), f"Should not auto-learn when max_pattern_length=0"
    
    # STM should contain all events (no auto-learning)
    stm = kato_fixture.get_short_term_memory()
    assert len(stm) == 10, f"STM should contain all 10 events when auto-learn disabled, got: {len(stm)}"


def test_mixed_event_sizes_rolling_mode(kato_fixture):
    """Test ROLLING mode with events containing multiple symbols."""
    kato_fixture.clear_all_memory()
    kato_fixture.update_genes({
        'max_pattern_length': 3,
        'stm_mode': 'ROLLING'
    })
    
    # Mixed events: some with 1 symbol, some with multiple
    events = [
        ['single'],
        ['multi', 'symbol'],
        ['another'],
        ['last', 'event']
    ]
    
    for event in events:
        kato_fixture.observe({'strings': event, 'vectors': [], 'emotives': {}})
    
    # Should auto-learn once (at position 2 when STM reaches length 3)
    # Final STM should contain last 2 events
    stm = kato_fixture.get_short_term_memory()
    assert len(stm) == 2, f"STM should have 2 events, got: {stm}"
    # Note: Symbols are sorted alphanumerically within each event
    assert stm[-1] == ['event', 'last'], f"Last event should be preserved: {stm}"


def test_invalid_stm_mode_defaults_to_clear(kato_fixture):
    """Test that invalid STM_MODE values default to CLEAR behavior."""
    kato_fixture.clear_all_memory()
    kato_fixture.update_genes({
        'max_pattern_length': 3,
        'stm_mode': 'INVALID_MODE'  # Should default to CLEAR
    })
    
    # Add events
    for event in ['test1', 'test2', 'test3']:
        kato_fixture.observe({'strings': [event], 'vectors': [], 'emotives': {}})
    
    # Should behave like CLEAR mode (STM emptied)
    stm = kato_fixture.get_short_term_memory()
    assert len(stm) == 0, f"Invalid mode should default to CLEAR behavior, but STM not empty: {stm}"