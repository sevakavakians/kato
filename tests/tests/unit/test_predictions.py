"""
Unit tests for KATO predictions.
Tests prediction generation, Hamiltonian calculations, and confidence scores.
"""

import pytest
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from fixtures.kato_fixtures import kato_fixture


def test_no_predictions_initially(kato_fixture):
    """Test that there are no predictions initially."""
    kato_fixture.clear_all_memory()
    
    predictions = kato_fixture.get_predictions()
    assert predictions == []


def test_predictions_after_observation(kato_fixture):
    """Test predictions after a single observation."""
    kato_fixture.clear_all_memory()
    
    # Learn a sequence first
    sequence = ['a', 'b', 'c']
    for item in sequence:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()
    
    # Now observe 'a' and 'b' to meet 2+ requirement and get predictions
    kato_fixture.observe({'strings': ['a'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['b'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()
    
    assert len(predictions) > 0, "Should have predictions after observation"
    
    # Check prediction structure
    for pred in predictions:
        assert 'name' in pred
        assert 'confidence' in pred
        assert 'hamiltonian' in pred
        assert 'grand_hamiltonian' in pred
        assert 'entropy' in pred
        assert 'similarity' in pred
        assert 'frequency' in pred


def test_prediction_matches(kato_fixture):
    """Test that predictions correctly identify matches."""
    kato_fixture.clear_all_memory()
    # Set lower threshold to ensure predictions for partial matches
    kato_fixture.set_recall_threshold(0.2)
    
    # Learn a sequence
    sequence = ['x', 'y', 'z']
    for item in sequence:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()
    
    # Observe 'x' and 'y' to meet 2+ requirement and check matches
    kato_fixture.observe({'strings': ['x'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['y'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()
    
    # Find prediction for our sequence
    for pred in predictions:
        if 'x' in pred.get('matches', []) and 'y' in pred.get('matches', []):
            # Since we observed 'x' and 'y', they should be in present
            present = pred.get('present', [])
            future = pred.get('future', [])
            
            # Both 'x' and 'y' should be in present
            assert [['x'], ['y']] == present, f"Present should be [['x'], ['y']], got {present}"
            # Only 'z' should be in future
            assert [['z']] == future, f"Future should be [['z']], got {future}"
            break


def test_prediction_present_past_future(kato_fixture):
    """Test prediction temporal components (past, present, future)."""
    kato_fixture.clear_all_memory()
    
    # Learn a longer sequence
    sequence = ['1', '2', '3', '4', '5']
    for item in sequence:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()
    
    # Observe middle of sequence
    kato_fixture.observe({'strings': ['2'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['3'], 'vectors': [], 'emotives': {}})
    
    predictions = kato_fixture.get_predictions()
    
    for pred in predictions:
        assert 'past' in pred
        assert 'present' in pred
        assert 'future' in pred


def test_prediction_similarity_perfect_match(kato_fixture):
    """Test similarity score for perfect match."""
    kato_fixture.clear_all_memory()
    
    # Learn a sequence
    sequence = ['perfect', 'match', 'test']
    for item in sequence:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()
    
    # Observe the entire sequence
    for item in sequence:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    
    predictions = kato_fixture.get_predictions()
    
    # Should have high similarity for perfect match
    assert len(predictions) > 0, "Should have at least one prediction"
    pred = predictions[0]
    similarity = pred.get('similarity', 0)
    assert similarity >= 0.9, f"Perfect match should have high similarity, got {similarity}"


def test_prediction_partial_match(kato_fixture):
    """Test predictions for partial sequence matches."""
    kato_fixture.clear_all_memory()
    
    # Learn a sequence
    full_sequence = ['start', 'middle', 'end']
    for item in full_sequence:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()
    
    # Observe partial sequence (KATO requires 2+ strings for predictions)
    kato_fixture.observe({'strings': ['start'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['middle'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()
    
    # Should have predictions with partial similarity
    assert len(predictions) > 0
    for pred in predictions:
        if 'start' in pred.get('matches', []):
            similarity = pred.get('similarity', 0)
            assert 0 < similarity < 1, "Partial match should have intermediate similarity"
            break


def test_prediction_frequency(kato_fixture):
    """Test that frequency increases with repeated observations."""
    kato_fixture.clear_all_memory()
    
    # Learn the same sequence multiple times
    sequence = ['freq', 'test']
    
    for _ in range(3):
        for item in sequence:
            kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
        kato_fixture.learn()
    
    # Observe to get predictions (KATO requires 2+ strings)
    kato_fixture.observe({'strings': ['freq'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['test'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()
    
    # Should have frequency > 1 for repeated sequence
    for pred in predictions:
        if pred.get('frequency', 0) >= 3:
            assert True
            break
    else:
        assert False, "Should have prediction with frequency >= 3"


def test_prediction_entropy(kato_fixture):
    """Test entropy calculation in predictions."""
    kato_fixture.clear_all_memory()
    
    # Learn sequences with different complexities
    simple_sequence = ['a', 'a', 'a']
    complex_sequence = ['x', 'y', 'z']
    
    # Learn simple sequence
    for item in simple_sequence:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()
    
    # Learn complex sequence
    for item in complex_sequence:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()
    
    # Get predictions (need 2+ strings)
    kato_fixture.observe({'strings': ['a'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['a'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()
    
    # All predictions should have entropy values
    for pred in predictions:
        assert 'entropy' in pred
        assert isinstance(pred['entropy'], (int, float))
        assert pred['entropy'] >= 0


def test_prediction_hamiltonian(kato_fixture):
    """Test Hamiltonian and grand Hamiltonian calculations."""
    kato_fixture.clear_all_memory()
    
    # Learn a sequence
    sequence = ['ham', 'test', 'seq']
    for item in sequence:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()
    
    # Observe to get predictions (need 2+ strings)
    kato_fixture.observe({'strings': ['ham'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['test'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()
    
    for pred in predictions:
        assert 'hamiltonian' in pred
        assert 'grand_hamiltonian' in pred
        assert isinstance(pred['hamiltonian'], (int, float))
        assert isinstance(pred['grand_hamiltonian'], (int, float))


def test_prediction_with_emotives(kato_fixture):
    """Test predictions include emotive values."""
    kato_fixture.clear_all_memory()
    
    # Learn sequence with emotives
    sequence = [
        ('happy', {'joy': 0.9, 'energy': 0.8}),
        ('sad', {'joy': 0.1, 'energy': 0.2}),
        ('neutral', {'joy': 0.5, 'energy': 0.5})
    ]
    
    for string, emotives in sequence:
        kato_fixture.observe({'strings': [string], 'vectors': [], 'emotives': emotives})
    model_name = kato_fixture.learn()
    assert model_name is not None, "Should have learned a model"
    
    # Clear working memory and observe to trigger predictions (KATO requires 2+ strings)
    kato_fixture.clear_working_memory()
    kato_fixture.observe({'strings': ['happy'], 'vectors': [], 'emotives': {'joy': 0.9, 'energy': 0.8}})
    kato_fixture.observe({'strings': ['sad'], 'vectors': [], 'emotives': {'joy': 0.1, 'energy': 0.2}})
    predictions = kato_fixture.get_predictions()
    
    # Should have at least one prediction
    assert len(predictions) > 0, "Should have predictions after learning and observing"
    
    # Find predictions with non-zero frequency (actual matches)
    matching_predictions = [p for p in predictions if p.get('frequency', 0) > 0]
    assert len(matching_predictions) > 0, "Should have at least one matching prediction"
    
    # Check that matching predictions have emotives
    for pred in matching_predictions:
        assert 'emotives' in pred, "Matching prediction should have emotives field"
        assert isinstance(pred['emotives'], dict), "Emotives should be a dictionary"
        # The averaged emotives should be present
        assert 'joy' in pred['emotives'], "Should have 'joy' emotive"
        assert 'energy' in pred['emotives'], "Should have 'energy' emotive"


def test_multiple_model_predictions(kato_fixture):
    """Test predictions when multiple models are learned."""
    kato_fixture.clear_all_memory()
    
    # Learn multiple different sequences
    sequences = [
        ['a', 'b', 'c'],
        ['a', 'x', 'y'],
        ['a', 'p', 'q']
    ]
    
    for seq in sequences:
        for item in seq:
            kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
        kato_fixture.learn()
    
    # Observe 'a' and 'b' which starts multiple sequences (KATO requires 2+ strings)
    kato_fixture.observe({'strings': ['a'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['b'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()
    
    # Should have multiple predictions
    assert len(predictions) >= 3, f"Should have at least 3 predictions, got {len(predictions)}"
    
    # Each should have different model name
    model_names = [pred.get('name', '') for pred in predictions]
    unique_names = set(model_names)
    assert len(unique_names) >= 3, "Should have different model names"


def test_prediction_confidence_scores(kato_fixture):
    """Test confidence score calculation."""
    kato_fixture.clear_all_memory()
    
    # Learn sequences with different patterns
    strong_pattern = ['strong'] * 5  # Repetitive, high confidence
    weak_pattern = ['w1', 'w2', 'w3', 'w4', 'w5']  # Varied, lower confidence
    
    # Learn strong pattern
    for item in strong_pattern:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()
    
    # Learn weak pattern
    for item in weak_pattern:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()
    
    # Get predictions (KATO requires 2+ strings)
    kato_fixture.observe({'strings': ['strong'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['strong'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()
    
    # All should have confidence scores
    for pred in predictions:
        assert 'confidence' in pred
        assert 0 <= pred['confidence'] <= 1


def test_prediction_type_field(kato_fixture):
    """Test that predictions have a type field."""
    kato_fixture.clear_all_memory()
    
    # Learn a sequence
    sequence = ['type', 'test']
    for item in sequence:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()
    
    # Get predictions (KATO requires 2+ strings)
    kato_fixture.observe({'strings': ['type'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['test'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()
    
    # Check for type field
    for pred in predictions:
        if 'type' in pred:
            assert pred['type'] in ['prototypical', 'episodic', 'abstract']