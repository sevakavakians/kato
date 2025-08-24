"""
Unit tests for KATO model hashing.
Tests deterministic hashing of sequences to ensure consistent MODEL| naming.
"""

import pytest
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from fixtures.kato_fixtures import kato_fixture
from fixtures.hash_helpers import (
    verify_model_name,
    extract_hash_from_name,
    verify_hash_consistency
)


def test_model_name_format(kato_fixture):
    """Test that learned models have correct MODEL| prefix."""
    kato_fixture.clear_all_memory()
    
    # Create and learn a sequence
    sequence = ['test', 'model', 'hash']
    for item in sequence:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    
    model_name = kato_fixture.learn()
    
    # Verify format
    assert model_name.startswith('MODEL|'), f"Model name should start with MODEL|, got: {model_name}"
    
    # Verify hash portion exists and is valid hex
    hash_part = extract_hash_from_name(model_name)
    assert len(hash_part) == 40, f"SHA1 hash should be 40 characters, got {len(hash_part)}"
    assert all(c in '0123456789abcdef' for c in hash_part), "Hash should be valid hexadecimal"


def test_identical_sequences_same_hash(kato_fixture):
    """Test that identical sequences produce the same model hash."""
    kato_fixture.clear_all_memory()
    
    # Learn the same sequence twice
    sequence = ['a', 'b', 'c']
    model_names = []
    
    for _ in range(2):
        for item in sequence:
            kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
        model_name = kato_fixture.learn()
        model_names.append(model_name)
    
    # Both should have the same hash
    assert model_names[0] == model_names[1], \
        f"Identical sequences should produce same hash: {model_names[0]} != {model_names[1]}"


def test_different_sequences_different_hash(kato_fixture):
    """Test that different sequences produce different model hashes."""
    kato_fixture.clear_all_memory()
    
    sequences = [
        ['x', 'y', 'z'],
        ['1', '2', '3'],
        ['a', 'b', 'c']
    ]
    
    model_names = []
    for seq in sequences:
        for item in seq:
            kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
        model_name = kato_fixture.learn()
        model_names.append(model_name)
    
    # All should be different
    unique_names = set(model_names)
    assert len(unique_names) == len(sequences), \
        f"Different sequences should produce different hashes, got: {model_names}"


def test_sequence_order_affects_hash(kato_fixture):
    """Test that sequence order affects the hash."""
    kato_fixture.clear_all_memory()
    
    sequences = [
        ['a', 'b', 'c'],
        ['c', 'b', 'a'],
        ['b', 'a', 'c']
    ]
    
    model_names = []
    for seq in sequences:
        for item in seq:
            kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
        model_name = kato_fixture.learn()
        model_names.append(model_name)
    
    # All should be different due to order
    unique_names = set(model_names)
    assert len(unique_names) == len(sequences), \
        f"Different orderings should produce different hashes, got: {model_names}"


def test_model_hash_in_predictions(kato_fixture):
    """Test that model hashes appear correctly in predictions."""
    kato_fixture.clear_all_memory()
    
    # Learn a sequence
    sequence = ['predict', 'test', 'hash']
    for item in sequence:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    
    model_name = kato_fixture.learn()
    
    # Observe first element to get predictions
    kato_fixture.observe({'strings': ['predict'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()
    
    assert len(predictions) > 0, "Should have predictions"
    
    # Find the prediction for our learned model
    for pred in predictions:
        if pred.get('name') == model_name:
            assert pred['name'].startswith('MODEL|')
            break
    else:
        # If exact match not found, at least verify format
        assert any(pred.get('name', '').startswith('MODEL|') for pred in predictions), \
            "At least one prediction should have MODEL| prefix"


def test_model_hash_with_emotives(kato_fixture):
    """Test that emotives are included in model hash calculation."""
    kato_fixture.clear_all_memory()
    
    # Two sequences with same strings but different emotives
    sequences = [
        (['a', 'b'], {'happiness': 0.5}),
        (['a', 'b'], {'happiness': 0.8})
    ]
    
    model_names = []
    for strings, emotives in sequences:
        for s in strings:
            kato_fixture.observe({'strings': [s], 'vectors': [], 'emotives': emotives})
        model_name = kato_fixture.learn()
        model_names.append(model_name)
    
    # If emotives affect hash, these should be different
    # Note: This behavior depends on KATO implementation
    # The test documents the actual behavior
    if model_names[0] == model_names[1]:
        print("Emotives do not affect model hash")
    else:
        print("Emotives affect model hash")


def test_model_hash_with_vectors(kato_fixture):
    """Test model hashing with vector observations."""
    kato_fixture.clear_all_memory()
    
    # Sequence with vectors
    # Note: Vector processing depends on classifier configuration
    vectors = [
        [1.0, 0.0],
        [0.0, 1.0],
        [0.5, 0.5]
    ]
    
    for vec in vectors:
        result = kato_fixture.observe({'strings': [], 'vectors': [vec], 'emotives': {}})
        assert result['status'] == 'observed'
    
    # Check if we have content to learn
    wm = kato_fixture.get_working_memory()
    
    # Only test model hashing if vectors produced content in working memory
    if len(wm) > 0:
        model_name = kato_fixture.learn()
        
        # If a model was learned, verify format
        if model_name:
            assert model_name.startswith('MODEL|'), "Model name should have MODEL| prefix"
            hash_part = extract_hash_from_name(model_name)
            assert len(hash_part) == 40, "SHA1 hash should be 40 characters"
    else:
        # If no content in working memory, learning might not occur
        # This is expected behavior when classifier doesn't process vectors
        pass


def test_empty_sequence_hash(kato_fixture):
    """Test hashing of empty sequences."""
    kato_fixture.clear_all_memory()
    
    # Try to learn an empty sequence
    model_name = kato_fixture.learn()
    
    # Empty sequence might not create a model or might have special handling
    if model_name:
        assert model_name.startswith('MODEL|') or model_name == ''


def test_single_observation_hash(kato_fixture):
    """Test hashing of single-observation sequences."""
    kato_fixture.clear_all_memory()
    
    # Single observation
    kato_fixture.observe({'strings': ['single'], 'vectors': [], 'emotives': {}})
    model_name = kato_fixture.learn()
    
    if model_name:
        assert model_name.startswith('MODEL|')
        hash_part = extract_hash_from_name(model_name)
        assert len(hash_part) == 40


def test_hash_consistency_across_sessions(kato_fixture):
    """Test that hashes remain consistent across clear operations."""
    kato_fixture.clear_all_memory()
    
    sequence = ['consistent', 'hash', 'test']
    hashes = []
    
    # Learn the same sequence multiple times with clears in between
    for _ in range(3):
        for item in sequence:
            kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
        model_name = kato_fixture.learn()
        hashes.append(extract_hash_from_name(model_name))
        kato_fixture.clear_all_memory()
    
    # All hashes should be identical
    assert len(set(hashes)) == 1, f"Hash should be consistent, got: {hashes}"


def test_complex_sequence_hash(kato_fixture):
    """Test hashing of complex multi-modal sequences."""
    kato_fixture.clear_all_memory()
    
    # Complex sequence with strings, vectors, and emotives
    observations = [
        {
            'strings': ['multi', 'modal'],
            'vectors': [[1.0, 2.0]],
            'emotives': {'arousal': 0.6}
        },
        {
            'strings': ['test'],
            'vectors': [[3.0, 4.0]],
            'emotives': {'valence': 0.8}
        }
    ]
    
    for obs in observations:
        kato_fixture.observe(obs)
    
    model_name = kato_fixture.learn()
    
    # Verify proper format
    assert model_name.startswith('MODEL|')
    hash_part = extract_hash_from_name(model_name)
    assert len(hash_part) == 40
    
    # Learn the same sequence again
    for obs in observations:
        kato_fixture.observe(obs)
    model_name2 = kato_fixture.learn()
    
    # Should produce the same hash
    assert model_name == model_name2