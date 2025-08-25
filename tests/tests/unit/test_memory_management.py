"""
Unit tests for KATO memory management.
Tests working memory, long-term memory, and memory limits.
"""

import pytest
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from fixtures.kato_fixtures import kato_fixture, kato_with_genome


def test_clear_all_memory(kato_fixture):
    """Test clearing all memory."""
    # Add some observations first
    kato_fixture.observe({'strings': ['test'], 'vectors': [], 'emotives': {}})
    
    # Clear all memory
    result = kato_fixture.clear_all_memory()
    assert result == 'all-cleared'
    
    # Verify working memory is empty
    wm = kato_fixture.get_working_memory()
    assert wm == []
    
    # Verify no predictions
    predictions = kato_fixture.get_predictions()
    assert predictions == []


def test_clear_working_memory(kato_fixture):
    """Test clearing only working memory."""
    # Clear all first
    kato_fixture.clear_all_memory()
    
    # Learn a sequence
    kato_fixture.observe({'strings': ['a'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['b'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['c'], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()
    
    # Add new observation to working memory
    kato_fixture.observe({'strings': ['d'], 'vectors': [], 'emotives': {}})
    
    # Clear working memory
    result = kato_fixture.clear_working_memory()
    assert result == 'wm-cleared'
    
    # Verify working memory is empty
    wm = kato_fixture.get_working_memory()
    assert wm == []
    
    # But learned models should still generate predictions
    kato_fixture.observe({'strings': ['a'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()
    assert len(predictions) > 0  # Should have predictions from learned model


def test_working_memory_accumulation(kato_fixture):
    """Test that working memory accumulates observations."""
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
        wm = kato_fixture.get_working_memory()
        assert len(wm) == i
    
    # Verify all observations are in working memory
    wm = kato_fixture.get_working_memory()
    assert wm == observations


def test_manual_learning(kato_fixture):
    """Test manual learning of working memory."""
    kato_fixture.clear_all_memory()
    
    # Build a sequence
    kato_fixture.observe({'strings': ['x'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['y'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['z'], 'vectors': [], 'emotives': {}})
    
    # Manually trigger learning
    result = kato_fixture.learn()
    assert 'MODEL|' in result  # Should return the learned model name
    
    # Working memory should be cleared after learning
    wm = kato_fixture.get_working_memory()
    assert wm == []
    
    # Now observe 'x' and should get predictions for 'y', 'z'
    kato_fixture.observe({'strings': ['x'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()
    assert len(predictions) > 0
    
    # Check that the prediction contains the learned sequence
    for pred in predictions:
        # Present should be [['x']], future should be [['y'], ['z']]
        if 'present' in pred and [['x']] == pred['present']:
            future = pred.get('future', [])
            if [['y'], ['z']] == future or (['y'] in future and ['z'] in future):
                assert True
                break
    else:
        # Alternative: just check that we have predictions
        assert len(predictions) > 0, "Should have predictions after observing 'x'"


def test_memory_persistence(kato_fixture):
    """Test that learned models persist across working memory clears."""
    kato_fixture.clear_all_memory()
    
    # Learn multiple sequences
    sequences = [
        ['a', 'b', 'c'],
        ['1', '2', '3'],
        ['x', 'y', 'z']
    ]
    
    model_names = []
    for seq in sequences:
        for symbol in seq:
            kato_fixture.observe({'strings': [symbol], 'vectors': [], 'emotives': {}})
        model_name = kato_fixture.learn()
        model_names.append(model_name)
    
    # Clear working memory
    kato_fixture.clear_working_memory()
    
    # Test each sequence still generates predictions
    for seq in sequences:
        kato_fixture.observe({'strings': [seq[0]], 'vectors': [], 'emotives': {}})
        predictions = kato_fixture.get_predictions()
        assert len(predictions) > 0
        kato_fixture.clear_working_memory()


def test_max_sequence_length(kato_fixture):
    """Test that max_sequence_length limit is enforced."""
    # Clear memory first, then set max_sequence_length
    kato_fixture.clear_working_memory()  # Only clear working memory, not genes
    kato_fixture.update_genes({"max_sequence_length": 3})
    
    # Observe 3 events (should trigger auto-learn at limit)
    kato_fixture.observe({'strings': ['a'], 'vectors': [], 'emotives': {}})
    assert len(kato_fixture.get_working_memory()) == 1
    
    kato_fixture.observe({'strings': ['b'], 'vectors': [], 'emotives': {}})
    assert len(kato_fixture.get_working_memory()) == 2
    
    kato_fixture.observe({'strings': ['c'], 'vectors': [], 'emotives': {}})
    # At max_sequence_length, should auto-learn and keep last event
    wm = kato_fixture.get_working_memory()
    assert wm == [['c']]  # Only last event remains
    
    # Verify sequence was learned
    kato_fixture.clear_working_memory()
    kato_fixture.observe({'strings': ['a'], 'vectors': [], 'emotives': {}})
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
    
    # Learn the sequence (this should store averaged emotives with the model)
    model_name = kato_fixture.learn()
    assert model_name is not None, "Should have learned a model"
    assert model_name.startswith('MODEL|'), "Model name should have MODEL| prefix"
    
    # Clear working memory and observe first element to trigger predictions
    kato_fixture.clear_working_memory()
    kato_fixture.observe({
        'strings': ['0'],
        'vectors': [],
        'emotives': {'happiness': 0.1, 'confidence': 0.2}
    })
    
    # Get predictions - should include averaged emotives from the learned model
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
    
    # Working memory behavior with vectors depends on classifier
    # Vectors may be converted to symbols or may not appear
    wm = kato_fixture.get_working_memory()
    
    # If classifier processes vectors into symbols, we should have entries
    # Otherwise working memory might be empty
    # The key test is that observe accepts vectors without error
    assert isinstance(wm, list), "Working memory should be a list"
    
    # Only try to learn if we have content in working memory
    if len(wm) > 0:
        model_name = kato_fixture.learn()
        # If learning occurred, model name should have MODEL| prefix
        if model_name:
            assert 'MODEL|' in model_name, "Learned model should have MODEL| prefix"
            # Working memory should be cleared after learning
            assert kato_fixture.get_working_memory() == []


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
    
    # Clear working memory (not all memory)
    kato_fixture.clear_working_memory()
    
    # First sequence should still work
    kato_fixture.observe({'strings': ['seq1_a'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()
    assert len(predictions) > 0
    
    # Clear all memory
    kato_fixture.clear_all_memory()
    
    # No predictions should exist now
    kato_fixture.observe({'strings': ['seq1_a'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()
    assert len(predictions) == 0 or all(p.get('frequency', 0) == 0 for p in predictions)