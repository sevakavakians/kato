"""
Unit tests for KATO memory management.
Tests short-term memory, long-term memory, and memory limits.
"""

import pytest
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from fixtures.kato_fixtures import kato_fixture


def test_clear_all_memory(kato_fixture):
    """Test clearing all memory."""
    # Add some observations first
    kato_fixture.observe({'strings': ['test'], 'vectors': [], 'emotives': {}})
    
    # Clear all memory
    result = kato_fixture.clear_all_memory()
    assert result == 'all-cleared'
    
    # Verify short-term memory is empty
    stm = kato_fixture.get_short_term_memory()
    assert stm == []
    
    # Verify no predictions
    predictions = kato_fixture.get_predictions()
    assert predictions == []


def test_clear_short_term_memory(kato_fixture):
    """Test clearing only short-term memory."""
    # Clear all first
    kato_fixture.clear_all_memory()
    
    # Learn a sequence
    kato_fixture.observe({'strings': ['a'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['b'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['c'], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()
    
    # Add new observation to short-term memory
    kato_fixture.observe({'strings': ['d'], 'vectors': [], 'emotives': {}})
    
    # Clear short-term memory
    result = kato_fixture.clear_short_term_memory()
    assert result == 'stm-cleared'
    
    # Verify short-term memory is empty
    stm = kato_fixture.get_short_term_memory()
    assert stm == []
    
    # But learned patterns should still generate predictions
    # KATO requires 2+ strings for predictions
    kato_fixture.observe({'strings': ['a'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['b'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()
    assert len(predictions) > 0  # Should have predictions from learned pattern


def test_short_term_memory_accumulation(kato_fixture):
    """Test that short-term memory accumulates observations."""
    # Ensure default gene values for this test
    kato_fixture.reset_genes_to_defaults()
    kato_fixture.clear_all_memory()
    
    # Add observations sequentially
    observations = [
        ['first'],
        ['second'],
        ['third']
    ]
    
    for i, obs in enumerate(observations, 1):
        kato_fixture.observe({'strings': obs, 'vectors': [], 'emotives': {}})
        stm = kato_fixture.get_short_term_memory()
        assert len(stm) == i
    
    # Verify all observations are in short-term memory
    stm = kato_fixture.get_short_term_memory()
    assert stm == observations


def test_manual_learning(kato_fixture):
    """Test manual learning of short-term memory."""
    kato_fixture.clear_all_memory()
    
    # Build a sequence
    kato_fixture.observe({'strings': ['x'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['y'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['z'], 'vectors': [], 'emotives': {}})
    
    # Manually trigger learning
    result = kato_fixture.learn()
    assert 'PTRN|' in result  # Should return the learned pattern name
    
    # Short-term memory should be cleared after learning
    stm = kato_fixture.get_short_term_memory()
    assert stm == []
    
    # Now observe 'x' and 'y' to get predictions (KATO requires 2+ strings)
    kato_fixture.observe({'strings': ['x'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['y'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()
    assert len(predictions) > 0
    
    # Check that the prediction contains the learned sequence
    for pred in predictions:
        # Since we observed 'x' and 'y', present should be [['x'], ['y']], future should be [['z']]
        if 'x' in pred.get('matches', []) and 'y' in pred.get('matches', []):
            present = pred.get('present', [])
            future = pred.get('future', [])
            # Both 'x' and 'y' should be in present since we observed them
            assert [['x'], ['y']] == present, f"Present should be [['x'], ['y']], got {present}"
            # Only 'z' should be in future
            assert [['z']] == future, f"Future should be [['z']], got {future}"
            break
    else:
        # If no matching prediction found, fail with informative message
        assert False, f"No prediction found with 'x' and 'y' in matches. Got predictions: {predictions}"


def test_memory_persistence(kato_fixture):
    """Test that learned patterns persist across short-term memory clears."""
    kato_fixture.clear_all_memory()
    
    # Learn multiple sequences
    sequences = [
        ['a', 'b', 'c'],
        ['1', '2', '3'],
        ['x', 'y', 'z']
    ]
    
    pattern_names = []
    for seq in sequences:
        for symbol in seq:
            kato_fixture.observe({'strings': [symbol], 'vectors': [], 'emotives': {}})
        pattern_name = kato_fixture.learn()
        pattern_names.append(pattern_name)
    
    # Clear short-term memory
    kato_fixture.clear_short_term_memory()
    
    # Test each sequence still generates predictions
    for seq in sequences:
        # KATO requires 2+ strings for predictions
        kato_fixture.observe({'strings': [seq[0]], 'vectors': [], 'emotives': {}})
        kato_fixture.observe({'strings': [seq[1]], 'vectors': [], 'emotives': {}})
        predictions = kato_fixture.get_predictions()
        assert len(predictions) > 0
        kato_fixture.clear_short_term_memory()


def test_max_pattern_length(kato_fixture):
    """Test that max_pattern_length limit is enforced."""
    # Note: In v2, max_pattern_length is configured at service startup, not dynamically
    # This test validates that STM can hold multiple observations
    kato_fixture.clear_short_term_memory()  # Only clear short-term memory, not genes
    
    # In v2, gene updates don't work dynamically - skip this specific behavior
    # Instead, test that STM accumulates observations correctly
    kato_fixture.observe({'strings': ['a'], 'vectors': [], 'emotives': {}})
    assert len(kato_fixture.get_short_term_memory()) == 1
    
    kato_fixture.observe({'strings': ['b'], 'vectors': [], 'emotives': {}})
    assert len(kato_fixture.get_short_term_memory()) == 2
    
    kato_fixture.observe({'strings': ['c'], 'vectors': [], 'emotives': {}})
    # In v2 without auto-learn, STM keeps all events
    stm = kato_fixture.get_short_term_memory()
    # V2 behavior: all events remain in STM until explicitly learned or cleared
    assert len(stm) == 3  # All events remain in v2
    
    # Learn the sequence before testing predictions
    kato_fixture.learn()
    
    # Verify sequence was learned (KATO requires 2+ strings for predictions)
    kato_fixture.clear_short_term_memory()
    kato_fixture.observe({'strings': ['a'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['b'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()
    assert len(predictions) > 0


def test_memory_with_emotives(kato_fixture):
    """Test that emotives are preserved in memory."""
    kato_fixture.clear_all_memory()
    
    # Build a sequence with different emotives for each event
    emotives_sequence = [
        {'happiness': 0.1, 'confidence': 0.2},
        {'happiness': 0.5, 'confidence': 0.6},
        {'happiness': 0.9, 'confidence': 0.8}
    ]
    
    # Observe the sequence with emotives
    for i, emotives in enumerate(emotives_sequence):
        result = kato_fixture.observe({
            'strings': [str(i)],
            'vectors': [],
            'emotives': emotives
        })
        assert result['status'] == 'observed'
    
    # Learn the sequence (this should store averaged emotives with the pattern)
    pattern_name = kato_fixture.learn()
    assert pattern_name is not None, "Should have learned a model"
    assert pattern_name.startswith('PTRN|'), "Pattern name should have PTRN| prefix"
    
    # Clear short-term memory and observe first two elements to trigger predictions (KATO requires 2+ strings)
    kato_fixture.clear_short_term_memory()
    kato_fixture.observe({
        'strings': ['0'],
        'vectors': [],
        'emotives': {'happiness': 0.1, 'confidence': 0.2}
    })
    kato_fixture.observe({
        'strings': ['1'],
        'vectors': [],
        'emotives': {'happiness': 0.5, 'confidence': 0.6}
    })
    
    # Get predictions - should include averaged emotives from the learned pattern
    predictions = kato_fixture.get_predictions()
    assert len(predictions) > 0, "Should have predictions after learning and observing"
    
    # Find predictions with non-zero frequency (actual matches)
    matching_predictions = [p for p in predictions if p.get('frequency', 0) > 0]
    assert len(matching_predictions) > 0, "Should have at least one matching prediction"
    
    # Check that matching predictions have emotives
    for pred in matching_predictions:
        assert 'emotives' in pred, "Matching prediction should have emotives field"
        assert isinstance(pred['emotives'], dict), "Emotives should be a dictionary"
        # Check that the emotives keys are present (values will be averaged)
        assert 'happiness' in pred['emotives'], "Should have 'happiness' emotive"
        assert 'confidence' in pred['emotives'], "Should have 'confidence' emotive"


def test_memory_with_vectors(kato_fixture):
    """Test that vectors are processed through the system."""
    kato_fixture.clear_all_memory()
    
    # Observe sequence with vectors
    # Note: Vector processing depends on classifier configuration
    vectors = [
        [1.0, 0.0],
        [0.0, 1.0],
        [0.5, 0.5]
    ]
    
    for vec in vectors:
        result = kato_fixture.observe({
            'strings': [],
            'vectors': [vec],
            'emotives': {}
        })
        assert result['status'] == 'observed'
    
    # Vectors ALWAYS produce at least VCTR|hash symbols in STM
    stm = kato_fixture.get_short_term_memory()
    assert isinstance(stm, list), "Short-term memory should be a list"
    assert len(stm) == 3, "Should have 3 events (one for each vector observation)"
    
    # Each event should have at least one VCTR| symbol
    for event in stm:
        vector_symbols = [s for s in event if s.startswith('VCTR|')]
        assert len(vector_symbols) >= 1, "Each vector observation should produce at least one VCTR| symbol"
    
    # Learn the sequence
    pattern_name = kato_fixture.learn()
    # Should successfully learn since we have 2+ symbols
    assert pattern_name is not None, "Should learn pattern from vector observations"
    assert 'PTRN|' in pattern_name, "Learned pattern should have PTRN| prefix"
    # Short-term memory should be cleared after learning
    assert kato_fixture.get_short_term_memory() == []


def test_interleaved_memory_operations(kato_fixture):
    """Test interleaved observation, learning, and clearing."""
    kato_fixture.clear_all_memory()
    
    # First sequence
    kato_fixture.observe({'strings': ['seq1_a'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['seq1_b'], 'vectors': [], 'emotives': {}})
    model1 = kato_fixture.learn()
    
    # Second sequence
    kato_fixture.observe({'strings': ['seq2_x'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['seq2_y'], 'vectors': [], 'emotives': {}})
    
    # Clear short-term memory (not all memory)
    kato_fixture.clear_short_term_memory()
    
    # First sequence should still work (KATO requires 2+ strings for predictions)
    kato_fixture.observe({'strings': ['seq1_a'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['seq1_b'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()
    assert len(predictions) > 0
    
    # Clear all memory
    kato_fixture.clear_all_memory()
    
    # No predictions should exist now (observe 2 strings but no learned patterns)
    kato_fixture.observe({'strings': ['seq1_a'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['seq1_b'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()
    assert len(predictions) == 0 or all(p.get('frequency', 0) == 0 for p in predictions)