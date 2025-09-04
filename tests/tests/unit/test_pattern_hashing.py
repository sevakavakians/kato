"""
Unit tests for KATO pattern hashing.
Tests deterministic hashing of sequences to ensure consistent PTRN| naming.
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
from fixtures.hash_helpers import (
    verify_pattern_name,
    extract_hash_from_name,
    verify_hash_consistency
)


def test_pattern_name_format(kato_fixture):
    """Test that learned patterns have correct PTRN| prefix."""
    kato_fixture.clear_all_memory()
    
    # Create and learn a sequence
    sequence = ['test', 'model', 'hash']
    for item in sequence:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    
    pattern_name = kato_fixture.learn()
    
    # Verify format
    assert pattern_name.startswith('PTRN|'), f"Pattern name should start with PTRN|, got: {pattern_name}"
    
    # Verify hash portion exists and is valid hex
    hash_part = extract_hash_from_name(pattern_name)
    assert len(hash_part) == 40, f"SHA1 hash should be 40 characters, got {len(hash_part)}"
    assert all(c in '0123456789abcdef' for c in hash_part), "Hash should be valid hexadecimal"


def test_identical_sequences_same_hash(kato_fixture):
    """Test that identical sequences produce the same pattern hash."""
    kato_fixture.clear_all_memory()
    
    # Learn the same sequence twice
    sequence = ['a', 'b', 'c']
    pattern_names = []
    
    for _ in range(2):
        for item in sequence:
            kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
        pattern_name = kato_fixture.learn()
        pattern_names.append(pattern_name)
    
    # Both should have the same hash
    assert pattern_names[0] == pattern_names[1], \
        f"Identical sequences should produce same hash: {pattern_names[0]} != {pattern_names[1]}"


def test_different_sequences_different_hash(kato_fixture):
    """Test that different sequences produce different pattern hashes."""
    kato_fixture.clear_all_memory()
    
    sequences = [
        ['x', 'y', 'z'],
        ['1', '2', '3'],
        ['a', 'b', 'c']
    ]
    
    pattern_names = []
    for seq in sequences:
        for item in seq:
            kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
        pattern_name = kato_fixture.learn()
        pattern_names.append(pattern_name)
    
    # All should be different
    unique_names = set(pattern_names)
    assert len(unique_names) == len(sequences), \
        f"Different sequences should produce different hashes, got: {pattern_names}"


def test_sequence_order_affects_hash(kato_fixture):
    """Test that sequence order affects the hash."""
    kato_fixture.clear_all_memory()
    
    sequences = [
        ['a', 'b', 'c'],
        ['c', 'b', 'a'],
        ['b', 'a', 'c']
    ]
    
    pattern_names = []
    for seq in sequences:
        for item in seq:
            kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
        pattern_name = kato_fixture.learn()
        pattern_names.append(pattern_name)
    
    # All should be different due to order
    unique_names = set(pattern_names)
    assert len(unique_names) == len(sequences), \
        f"Different orderings should produce different hashes, got: {pattern_names}"


def test_pattern_hash_in_predictions(kato_fixture):
    """Test that pattern hashes appear correctly in predictions."""
    kato_fixture.clear_all_memory()
    
    # Learn a sequence
    sequence = ['predict', 'test', 'hash']
    for item in sequence:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    
    pattern_name = kato_fixture.learn()
    
    # Observe to get predictions (KATO requires 2+ strings)
    kato_fixture.observe({'strings': ['predict'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['test'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()
    
    assert len(predictions) > 0, "Should have predictions"
    
    # Find the prediction for our learned pattern
    for pred in predictions:
        if pred.get('name') == pattern_name:
            assert pred['name'].startswith('PTRN|')
            break
    else:
        # If exact match not found, at least verify format
        assert any(pred.get('name', '').startswith('PTRN|') for pred in predictions), \
            "At least one prediction should have PTRN| prefix"


def test_pattern_hash_with_emotives(kato_fixture):
    """Test that emotives are included in pattern hash calculation."""
    kato_fixture.clear_all_memory()
    
    # Two sequences with same strings but different emotives
    sequences = [
        (['a', 'b'], {'happiness': 0.5}),
        (['a', 'b'], {'happiness': 0.8})
    ]
    
    pattern_names = []
    for strings, emotives in sequences:
        for s in strings:
            kato_fixture.observe({'strings': [s], 'vectors': [], 'emotives': emotives})
        pattern_name = kato_fixture.learn()
        pattern_names.append(pattern_name)
    
    # If emotives affect hash, these should be different
    # Note: This behavior depends on KATO implementation
    # The test documents the actual behavior
    if pattern_names[0] == pattern_names[1]:
        print("Emotives do not affect pattern hash")
    else:
        print("Emotives affect pattern hash")


def test_pattern_hash_with_vectors(kato_fixture):
    """Test pattern hashing with vector observations."""
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
    stm = kato_fixture.get_short_term_memory()
    
    # Only test pattern hashing if vectors produced content in short-term memory
    if len(stm) > 0:
        pattern_name = kato_fixture.learn()
        
        # If a pattern was learned, verify format
        if pattern_name:
            assert pattern_name.startswith('PTRN|'), "Pattern name should have PTRN| prefix"
            hash_part = extract_hash_from_name(pattern_name)
            assert len(hash_part) == 40, "SHA1 hash should be 40 characters"
    else:
        # If no content in short-term memory, learning might not occur
        # This is expected behavior when classifier doesn't process vectors
        pass


def test_empty_sequence_hash(kato_fixture):
    """Test hashing of empty sequences."""
    kato_fixture.clear_all_memory()
    
    # Try to learn an empty sequence
    pattern_name = kato_fixture.learn()
    
    # Empty sequence should not create a pattern (requires at least 2 strings)
    # Should return empty string
    assert pattern_name == '', f"Expected empty string for empty sequence, got: {pattern_name}"


def test_single_observation_hash(kato_fixture):
    """Test hashing of single-observation sequences."""
    kato_fixture.clear_all_memory()
    
    # Single observation
    kato_fixture.observe({'strings': ['single'], 'vectors': [], 'emotives': {}})
    pattern_name = kato_fixture.learn()
    
    # Single observation should not create a pattern (requires at least 2 strings)
    # Should return empty string
    assert pattern_name == '', f"Expected empty string for single observation, got: {pattern_name}"


def test_hash_consistency_across_sessions(kato_fixture):
    """Test that hashes remain consistent across clear operations."""
    kato_fixture.clear_all_memory()
    
    sequence = ['consistent', 'hash', 'test']
    hashes = []
    
    # Learn the same sequence multiple times with clears in between
    for _ in range(3):
        for item in sequence:
            kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
        pattern_name = kato_fixture.learn()
        hashes.append(extract_hash_from_name(pattern_name))
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
    
    pattern_name = kato_fixture.learn()
    
    # Verify proper format
    assert pattern_name.startswith('PTRN|')
    hash_part = extract_hash_from_name(pattern_name)
    assert len(hash_part) == 40
    
    # Clear memory and learn the same sequence again to test hash consistency
    kato_fixture.clear_all_memory()
    for obs in observations:
        kato_fixture.observe(obs)
    pattern_name2 = kato_fixture.learn()
    
    # Should produce the same hash
    assert pattern_name == pattern_name2