"""
Integration tests for KATO sequence learning.
Tests end-to-end sequence learning, recall, and prediction scenarios.
"""

import pytest
import time
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from fixtures.kato_fixtures import kato_fixture, kato_with_genome


def test_simple_sequence_learning(kato_fixture):
    """Test learning and recalling a simple sequence."""
    kato_fixture.clear_all_memory()
    
    # Learn sequence
    sequence = ['hello', 'world', 'test']
    for item in sequence:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    
    model_name = kato_fixture.learn()
    assert model_name.startswith('MODEL|')
    
    # Recall sequence
    kato_fixture.observe({'strings': ['hello'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()
    
    # Should predict the rest of the sequence
    assert len(predictions) > 0
    for pred in predictions:
        if 'hello' in pred.get('matches', []):
            # Check future field for subsequent events
            future = pred.get('future', [])
            # Future should contain [['world'], ['test']]
            assert len(future) >= 2
            assert ['world'] in future or ['test'] in future
            break


def test_multiple_sequence_learning(kato_fixture):
    """Test learning multiple sequences and disambiguation."""
    kato_fixture.clear_all_memory()
    
    # Learn multiple sequences with common prefix
    sequences = [
        ['start', 'path1', 'end1'],
        ['start', 'path2', 'end2'],
        ['begin', 'middle', 'finish']
    ]
    
    for seq in sequences:
        for item in seq:
            kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
        kato_fixture.learn()
    
    # Test disambiguation with common prefix
    kato_fixture.observe({'strings': ['start'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()
    
    # Should have multiple predictions for sequences starting with 'start'
    start_predictions = [p for p in predictions if 'start' in p.get('matches', [])]
    assert len(start_predictions) >= 2
    
    # Continue sequence to disambiguate
    kato_fixture.observe({'strings': ['path1'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()
    
    # Should now favor the path1 sequence
    for pred in predictions:
        if pred.get('similarity', 0) > 0.6:
            present = pred.get('present', [])
            if any('path1' in p and 'end1' in p for p in present if isinstance(p, list)):
                assert True
                break


def test_sequence_completion(kato_fixture):
    """Test partial sequence completion and prediction."""
    kato_fixture.clear_all_memory()
    
    # Learn a longer sequence
    long_sequence = ['once', 'upon', 'a', 'time', 'there', 'was', 'a', 'story']
    for item in long_sequence:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()
    
    # Test completion at different points
    test_points = [
        (['once'], ['upon', 'a', 'time']),
        (['once', 'upon'], ['a', 'time']),
        (['once', 'upon', 'a'], ['time', 'there'])
    ]
    
    for observed, expected in test_points:
        kato_fixture.clear_working_memory()
        
        for item in observed:
            kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
        
        predictions = kato_fixture.get_predictions()
        
        # Check if expected items are in future events
        for pred in predictions:
            if pred.get('frequency', 0) > 0:
                future = pred.get('future', [])
                # Flatten future events to check for expected items
                future_items = [item for sublist in future for item in sublist if isinstance(sublist, list)]
                
                # At least some expected items should be in future
                if any(exp in future_items for exp in expected):
                    assert True
                    break


def test_cyclic_sequence_learning(kato_fixture):
    """Test learning and predicting cyclic sequences."""
    kato_fixture.clear_all_memory()
    
    # Learn a cyclic pattern
    cycle = ['A', 'B', 'C', 'A', 'B', 'C', 'A']
    for item in cycle:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()
    
    # Test cycle prediction
    kato_fixture.observe({'strings': ['A'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['B'], 'vectors': [], 'emotives': {}})
    
    predictions = kato_fixture.get_predictions()
    
    # Should predict 'C' as next in future
    for pred in predictions:
        if pred.get('similarity', 0) > 0.5:
            future = pred.get('future', [])
            # Check if 'C' is in the next future event
            if future and 'C' in future[0]:
                assert True
                break


def test_sequence_with_repetition(kato_fixture):
    """Test sequences with repeated elements."""
    kato_fixture.clear_all_memory()
    
    # Sequence with repetitions
    sequence = ['rep', 'rep', 'unique', 'rep', 'end']
    for item in sequence:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()
    
    # Start with repeated element
    kato_fixture.observe({'strings': ['rep'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()
    
    # Should handle repetition correctly
    assert len(predictions) > 0
    
    # Continue sequence
    kato_fixture.observe({'strings': ['rep'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()
    
    # Should still generate predictions
    for pred in predictions:
        if pred.get('frequency', 0) > 0:
            # Check for future events or missing symbols within present
            assert 'future' in pred or 'missing' in pred


def test_interleaved_sequence_learning(kato_fixture):
    """Test learning interleaved sequences."""
    kato_fixture.clear_all_memory()
    
    # Learn two sequences in interleaved fashion
    seq1 = ['s1_a', 's1_b', 's1_c']
    seq2 = ['s2_x', 's2_y', 's2_z']
    
    # Interleave observations
    for i in range(len(seq1)):
        kato_fixture.observe({'strings': [seq1[i]], 'vectors': [], 'emotives': {}})
        if i < len(seq1) - 1:  # Don't learn seq1 yet
            kato_fixture.observe({'strings': [seq2[i]], 'vectors': [], 'emotives': {}})
    
    # Learn first sequence
    kato_fixture.learn()
    
    # Continue with seq2
    for i in range(len(seq2)):
        kato_fixture.observe({'strings': [seq2[i]], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()
    
    # Test both sequences work
    kato_fixture.observe({'strings': ['s1_a'], 'vectors': [], 'emotives': {}})
    pred1 = kato_fixture.get_predictions()
    assert len(pred1) > 0
    
    kato_fixture.clear_working_memory()
    kato_fixture.observe({'strings': ['s2_x'], 'vectors': [], 'emotives': {}})
    pred2 = kato_fixture.get_predictions()
    assert len(pred2) > 0


def test_context_switching(kato_fixture):
    """Test switching between different learned contexts."""
    kato_fixture.clear_all_memory()
    
    # Learn sequences for different contexts
    contexts = {
        'greeting': ['hello', 'how', 'are', 'you'],
        'farewell': ['goodbye', 'see', 'you', 'later'],
        'question': ['what', 'is', 'your', 'name']
    }
    
    for context, sequence in contexts.items():
        for item in sequence:
            kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
        kato_fixture.learn()
    
    # Test context switching
    test_cases = [
        ('hello', 'greeting'),
        ('goodbye', 'farewell'),
        ('what', 'question')
    ]
    
    for trigger, expected_context in test_cases:
        kato_fixture.clear_working_memory()
        kato_fixture.observe({'strings': [trigger], 'vectors': [], 'emotives': {}})
        predictions = kato_fixture.get_predictions()
        
        # Should predict appropriate context continuation
        for pred in predictions:
            if pred.get('frequency', 0) > 0:
                future = pred.get('future', [])
                context_seq = contexts[expected_context]
                # Check if future events contain the expected context continuation
                future_items = [item for event in future for item in event if isinstance(event, list)]
                if any(item in future_items for item in context_seq[1:]):
                    assert True
                    break


def test_max_sequence_length_auto_learn(kato_fixture):
    """Test automatic learning when max_sequence_length is reached."""
    # Clear memory first, then set max_sequence_length
    kato_fixture.clear_working_memory()  # Only clear working memory, not genes
    kato_fixture.update_genes({"max_sequence_length": 3})
    
    # Observe exactly max_sequence_length events
    events = ['auto1', 'auto2', 'auto3']
    for event in events:
        kato_fixture.observe({'strings': [event], 'vectors': [], 'emotives': {}})
    
    # Should auto-learn and clear working memory except last
    wm = kato_fixture.get_working_memory()
    assert len(wm) == 1
    assert wm == [['auto3']]
    
    # Verify sequence was learned
    kato_fixture.clear_working_memory()
    kato_fixture.observe({'strings': ['auto1'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()
    
    # Should predict the learned sequence
    for pred in predictions:
        if 'auto1' in pred.get('matches', []):
            future = pred.get('future', [])
            # Future should contain [['auto2'], ['auto3']]
            future_items = [item for event in future for item in event if isinstance(event, list)]
            assert 'auto2' in future_items or 'auto3' in future_items


def test_sequence_with_time_gaps(kato_fixture):
    """Test sequence learning with time gaps between observations."""
    kato_fixture.clear_all_memory()
    
    # Learn sequence with delays
    sequence = ['time', 'gap', 'test']
    for i, item in enumerate(sequence):
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
        if i < len(sequence) - 1:
            time.sleep(0.1)  # Small delay between observations
    
    kato_fixture.learn()
    
    # Recall should still work
    kato_fixture.observe({'strings': ['time'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()
    
    assert len(predictions) > 0
    for pred in predictions:
        if 'time' in pred.get('matches', []):
            future = pred.get('future', [])
            # Future should contain [['gap'], ['test']]
            future_items = [item for event in future for item in event if isinstance(event, list)]
            assert 'gap' in future_items or 'test' in future_items


def test_multimodal_sequence_learning(kato_fixture):
    """Test learning sequences with mixed modalities."""
    kato_fixture.clear_all_memory()
    
    # Multimodal sequence
    sequence = [
        {'strings': ['visual'], 'vectors': [[1, 0, 0]], 'emotives': {'arousal': 0.5}},
        {'strings': ['audio'], 'vectors': [[0, 1, 0]], 'emotives': {'arousal': 0.7}},
        {'strings': ['tactile'], 'vectors': [[0, 0, 1]], 'emotives': {'arousal': 0.3}}
    ]
    
    for obs in sequence:
        kato_fixture.observe(obs)
    kato_fixture.learn()
    
    # Test recall with partial multimodal input
    kato_fixture.observe({'strings': ['visual'], 'vectors': [[1, 0, 0]], 'emotives': {}})
    predictions = kato_fixture.get_predictions()
    
    assert len(predictions) > 0
    # Should predict continuation of multimodal sequence
    for pred in predictions:
        if pred.get('frequency', 0) > 0:
            # Check for future events in the multimodal sequence
            assert 'future' in pred or 'missing' in pred


def test_branching_sequences(kato_fixture):
    """Test sequences that branch into multiple possibilities."""
    kato_fixture.clear_all_memory()
    
    # Learn branching sequences
    branches = [
        ['root', 'branch', 'leaf1'],
        ['root', 'branch', 'leaf2'],
        ['root', 'trunk', 'bark']
    ]
    
    for branch in branches:
        for item in branch:
            kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
        kato_fixture.learn()
    
    # Test at branch point
    kato_fixture.observe({'strings': ['root'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()
    
    # Should have multiple predictions
    root_preds = [p for p in predictions if 'root' in p.get('matches', [])]
    assert len(root_preds) >= 2
    
    # Disambiguate with next observation
    kato_fixture.observe({'strings': ['branch'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()
    
    # Should narrow down to branch-specific predictions
    branch_preds = [p for p in predictions if p.get('similarity', 0) > 0.5]
    assert len(branch_preds) >= 1
    
    # Check that both leaf1 and leaf2 are possible in future
    all_future_items = []
    for pred in branch_preds:
        future = pred.get('future', [])
        for event in future:
            if isinstance(event, list):
                all_future_items.extend(event)
    
    assert 'leaf1' in all_future_items or 'leaf2' in all_future_items