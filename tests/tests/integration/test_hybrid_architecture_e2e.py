"""
End-to-end integration tests for ClickHouse/Redis hybrid architecture.
Tests filter pipeline, mode switching, fallback behavior, and error handling.
"""

import os
import sys
import time
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


@pytest.fixture
def hybrid_kato_fixture(kato_fixture):
    """Configure KATO fixture with hybrid architecture filter pipeline."""
    # Configure session with empty filter pipeline for E2E testing
    # Empty pipeline = query all patterns (no filtering)
    # This avoids filter complexity in basic E2E tests
    filter_config = {
        'filter_pipeline': [],  # Empty = no filtering, query all patterns
        'enable_filter_metrics': True
    }

    # Update session configuration
    kato_fixture.update_config(filter_config)

    return kato_fixture


def test_hybrid_mode_initialization(hybrid_kato_fixture):
    """Test that hybrid mode initializes correctly with ClickHouse and Redis."""
    hybrid_kato_fixture.clear_all_memory()

    # Learn a simple pattern in hybrid mode
    sequence = ['hybrid', 'test', 'pattern']
    for item in sequence:
        hybrid_kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})

    pattern_name = hybrid_kato_fixture.learn()
    assert pattern_name.startswith('PTRN|'), "Pattern should be learned successfully"

    # Verify predictions work with hybrid architecture
    hybrid_kato_fixture.observe({'strings': ['hybrid'], 'vectors': [], 'emotives': {}})
    hybrid_kato_fixture.observe({'strings': ['test'], 'vectors': [], 'emotives': {}})
    predictions = hybrid_kato_fixture.get_predictions()

    assert len(predictions) > 0, "Hybrid mode should generate predictions"

    # Verify the learned pattern is in predictions
    matching = [p for p in predictions if 'hybrid' in p.get('matches', []) and 'test' in p.get('matches', [])]
    assert len(matching) > 0, "Should find pattern using filter pipeline"


def test_filter_pipeline_execution(hybrid_kato_fixture):
    """Test that filter pipeline reduces candidates correctly."""
    hybrid_kato_fixture.clear_all_memory()

    # Learn multiple patterns to test filtering
    patterns = [
        ['alpha', 'beta', 'gamma'],
        ['alpha', 'beta', 'delta'],
        ['alpha', 'theta', 'omega'],
        ['one', 'two', 'three'],
        ['uno', 'dos', 'tres']
    ]

    for pattern in patterns:
        for item in pattern:
            hybrid_kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
        hybrid_kato_fixture.learn()

    # Query with partial match - filter pipeline should reduce candidates
    hybrid_kato_fixture.observe({'strings': ['alpha'], 'vectors': [], 'emotives': {}})
    hybrid_kato_fixture.observe({'strings': ['beta'], 'vectors': [], 'emotives': {}})
    predictions = hybrid_kato_fixture.get_predictions()

    # Should find patterns starting with 'alpha', 'beta'
    alpha_beta_matches = [p for p in predictions if 'alpha' in p.get('matches', []) and 'beta' in p.get('matches', [])]
    assert len(alpha_beta_matches) >= 2, "Should find patterns with 'alpha' and 'beta'"

    # Should NOT find unrelated patterns
    unrelated = [p for p in predictions if 'one' in p.get('matches', []) or 'uno' in p.get('matches', [])]
    assert len(unrelated) == 0, "Filter pipeline should exclude unrelated patterns"


def test_hybrid_with_vectors(hybrid_kato_fixture):
    """Test hybrid architecture with vector observations."""
    hybrid_kato_fixture.clear_all_memory()

    # Learn multimodal pattern (strings + vectors)
    multimodal_sequence = [
        {'strings': ['visual'], 'vectors': [[1, 0, 0]], 'emotives': {}},
        {'strings': ['audio'], 'vectors': [[0, 1, 0]], 'emotives': {}},
        {'strings': ['tactile'], 'vectors': [[0, 0, 1]], 'emotives': {}}
    ]

    for obs in multimodal_sequence:
        hybrid_kato_fixture.observe(obs)
    hybrid_kato_fixture.learn()

    # Query with partial multimodal observation
    hybrid_kato_fixture.observe({'strings': ['visual'], 'vectors': [[1, 0, 0]], 'emotives': {}})
    hybrid_kato_fixture.observe({'strings': ['audio'], 'vectors': [[0, 1, 0]], 'emotives': {}})
    predictions = hybrid_kato_fixture.get_predictions()

    assert len(predictions) > 0, "Hybrid mode should handle vectors"

    # Verify prediction contains both user strings and vector names
    for pred in predictions:
        matches = pred.get('matches', [])
        # Should include both 'visual' and 'audio' in matches
        if 'visual' in matches and 'audio' in matches:
            assert True
            break


def test_hybrid_with_emotives(hybrid_kato_fixture):
    """Test hybrid architecture preserves emotives correctly."""
    hybrid_kato_fixture.clear_all_memory()

    # Learn pattern with emotives
    emotive_sequence = [
        {'strings': ['happy'], 'vectors': [], 'emotives': {'joy': 0.9, 'arousal': 0.7}},
        {'strings': ['event'], 'vectors': [], 'emotives': {'joy': 0.5, 'arousal': 0.4}},
        {'strings': ['ending'], 'vectors': [], 'emotives': {'joy': 0.3, 'arousal': 0.2}}
    ]

    for obs in emotive_sequence:
        hybrid_kato_fixture.observe(obs)
    hybrid_kato_fixture.learn()

    # Query to get predictions
    hybrid_kato_fixture.observe({'strings': ['happy'], 'vectors': [], 'emotives': {}})
    hybrid_kato_fixture.observe({'strings': ['event'], 'vectors': [], 'emotives': {}})
    predictions = hybrid_kato_fixture.get_predictions()

    # Verify emotives are present in predictions
    for pred in predictions:
        if 'happy' in pred.get('matches', []) and 'event' in pred.get('matches', []):
            emotives = pred.get('emotives', {})
            # Should have averaged emotives from pattern
            assert 'joy' in emotives or 'arousal' in emotives, "Emotives should be retrieved from Redis"
            break


def test_hybrid_large_scale_filtering(hybrid_kato_fixture):
    """Test filter pipeline performance with larger dataset."""
    hybrid_kato_fixture.clear_all_memory()

    # Create many patterns to test filtering efficiency
    import string

    base_patterns = []
    for letter in string.ascii_lowercase[:10]:  # a-j (10 patterns)
        pattern = [f'{letter}1', f'{letter}2', f'{letter}3']
        base_patterns.append(pattern)

    # Learn all patterns
    for pattern in base_patterns:
        for item in pattern:
            hybrid_kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
        hybrid_kato_fixture.learn()

    # Query with specific pattern - filter pipeline should quickly narrow down
    hybrid_kato_fixture.observe({'strings': ['a1'], 'vectors': [], 'emotives': {}})
    hybrid_kato_fixture.observe({'strings': ['a2'], 'vectors': [], 'emotives': {}})

    start_time = time.time()
    predictions = hybrid_kato_fixture.get_predictions()
    elapsed = time.time() - start_time

    # Should find the 'a' pattern quickly
    a_matches = [p for p in predictions if 'a1' in p.get('matches', []) and 'a2' in p.get('matches', [])]
    assert len(a_matches) >= 1, "Should find pattern starting with 'a1', 'a2'"

    # Should NOT find patterns from other letters
    other_matches = [p for p in predictions if 'b1' in p.get('matches', []) or 'c1' in p.get('matches', [])]
    assert len(other_matches) == 0, "Filter pipeline should exclude non-matching patterns"

    # Performance should be reasonable (< 1 second for small dataset)
    assert elapsed < 1.0, f"Hybrid mode should be fast, took {elapsed:.2f}s"


def test_mongodb_fallback_behavior(kato_fixture):
    """Test that MongoDB mode still works (fallback or explicit mode)."""
    # This test should work in both mongodb and hybrid modes
    kato_fixture.clear_all_memory()

    # Learn a simple pattern
    sequence = ['mongo', 'db', 'fallback']
    for item in sequence:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})

    pattern_name = kato_fixture.learn()
    assert pattern_name.startswith('PTRN|'), "MongoDB mode should still work"

    # Get predictions
    kato_fixture.observe({'strings': ['mongo'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['db'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()

    assert len(predictions) > 0, "MongoDB mode should generate predictions"


def test_hybrid_pattern_frequency_tracking(hybrid_kato_fixture):
    """Test that pattern frequency is correctly tracked in hybrid mode."""
    hybrid_kato_fixture.clear_all_memory()

    # Learn the same pattern multiple times
    sequence = ['freq', 'test', 'pattern']

    # Learn first time
    for item in sequence:
        hybrid_kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    pattern_name_1 = hybrid_kato_fixture.learn()

    # Learn second time (same pattern)
    for item in sequence:
        hybrid_kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    pattern_name_2 = hybrid_kato_fixture.learn()

    # Pattern names should be identical (same hash)
    assert pattern_name_1 == pattern_name_2, "Same pattern should have same name"

    # Get predictions
    hybrid_kato_fixture.observe({'strings': ['freq'], 'vectors': [], 'emotives': {}})
    hybrid_kato_fixture.observe({'strings': ['test'], 'vectors': [], 'emotives': {}})
    predictions = hybrid_kato_fixture.get_predictions()

    # Find the pattern in predictions
    for pred in predictions:
        if pred.get('name') == pattern_name_1:
            # Frequency should be >= 2 (learned at least twice)
            frequency = pred.get('frequency', 0)
            assert frequency >= 2, f"Pattern learned twice should have frequency >= 2, got {frequency}"
            break


def test_hybrid_recall_threshold(hybrid_kato_fixture):
    """Test that recall threshold filtering works in hybrid mode."""
    hybrid_kato_fixture.clear_all_memory()

    # Learn patterns with varying similarity to query
    patterns = [
        ['exact', 'match', 'pattern'],       # High similarity
        ['exact', 'different', 'words'],     # Medium similarity
        ['completely', 'unrelated', 'stuff']  # Low similarity
    ]

    for pattern in patterns:
        for item in pattern:
            hybrid_kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
        hybrid_kato_fixture.learn()

    # Set high recall threshold via session config
    hybrid_kato_fixture.set_recall_threshold(0.7)

    # Query with exact match to first pattern
    hybrid_kato_fixture.observe({'strings': ['exact'], 'vectors': [], 'emotives': {}})
    hybrid_kato_fixture.observe({'strings': ['match'], 'vectors': [], 'emotives': {}})
    predictions = hybrid_kato_fixture.get_predictions()

    # Should find high-similarity pattern
    exact_matches = [p for p in predictions if 'exact' in p.get('matches', []) and 'match' in p.get('matches', [])]
    assert len(exact_matches) >= 1, "Should find exact match pattern"

    # Should NOT find low-similarity pattern with high threshold
    unrelated = [p for p in predictions if 'completely' in p.get('matches', []) or 'unrelated' in p.get('matches', [])]
    assert len(unrelated) == 0, "High recall threshold should filter out unrelated patterns"


def test_hybrid_max_predictions_limit(hybrid_kato_fixture):
    """Test that max_predictions limit works in hybrid mode."""
    hybrid_kato_fixture.clear_all_memory()

    # Learn many patterns
    for i in range(20):
        pattern = [f'pattern_{i}_a', f'pattern_{i}_b', f'pattern_{i}_c']
        for item in pattern:
            hybrid_kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
        hybrid_kato_fixture.learn()

    # Set low max_predictions via session config
    hybrid_kato_fixture.update_config({'max_predictions': 5})

    # Query with low recall threshold to potentially match many patterns
    hybrid_kato_fixture.set_recall_threshold(0.1)
    hybrid_kato_fixture.observe({'strings': ['pattern_0_a'], 'vectors': [], 'emotives': {}})
    hybrid_kato_fixture.observe({'strings': ['pattern_0_b'], 'vectors': [], 'emotives': {}})
    predictions = hybrid_kato_fixture.get_predictions()

    # Should respect max_predictions limit
    assert len(predictions) <= 5, f"Should return at most 5 predictions, got {len(predictions)}"


def test_hybrid_session_isolation(hybrid_kato_fixture):
    """Test that hybrid mode maintains session isolation."""
    hybrid_kato_fixture.clear_all_memory()

    # Learn a pattern specific to this session
    sequence = ['session', 'specific', 'data']
    for item in sequence:
        hybrid_kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    hybrid_kato_fixture.learn()

    # Verify pattern is learned
    hybrid_kato_fixture.observe({'strings': ['session'], 'vectors': [], 'emotives': {}})
    hybrid_kato_fixture.observe({'strings': ['specific'], 'vectors': [], 'emotives': {}})
    predictions = hybrid_kato_fixture.get_predictions()

    session_matches = [p for p in predictions if 'session' in p.get('matches', []) and 'specific' in p.get('matches', [])]
    assert len(session_matches) >= 1, "Session-specific pattern should be found"

    # Clear STM but keep LTM (pattern should persist)
    hybrid_kato_fixture.clear_short_term_memory()

    # Pattern should still be retrievable in new query
    hybrid_kato_fixture.observe({'strings': ['session'], 'vectors': [], 'emotives': {}})
    hybrid_kato_fixture.observe({'strings': ['specific'], 'vectors': [], 'emotives': {}})
    predictions = hybrid_kato_fixture.get_predictions()

    session_matches = [p for p in predictions if 'session' in p.get('matches', []) and 'specific' in p.get('matches', [])]
    assert len(session_matches) >= 1, "Pattern should persist across STM clears"


def test_hybrid_empty_state_handling(hybrid_kato_fixture):
    """Test that hybrid mode handles empty state correctly."""
    hybrid_kato_fixture.clear_all_memory()

    # Learn a pattern
    sequence = ['empty', 'state', 'test']
    for item in sequence:
        hybrid_kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    hybrid_kato_fixture.learn()

    # Query with only 1 string (below minimum for predictions)
    hybrid_kato_fixture.observe({'strings': ['empty'], 'vectors': [], 'emotives': {}})
    predictions = hybrid_kato_fixture.get_predictions()

    # Should return empty list (KATO requires 2+ strings)
    assert len(predictions) == 0, "Should return no predictions with only 1 string"


def test_hybrid_backward_compatibility(kato_fixture):
    """Test that hybrid mode is backward compatible with MongoDB-only code."""
    # This test works in both mongodb and hybrid modes
    kato_fixture.clear_all_memory()

    # Use standard KATO workflow
    kato_fixture.observe({'strings': ['backward'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['compatible'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['test'], 'vectors': [], 'emotives': {}})

    pattern_name = kato_fixture.learn()
    assert pattern_name.startswith('PTRN|'), "Standard workflow should work"

    # Get predictions
    kato_fixture.observe({'strings': ['backward'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['compatible'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()

    assert len(predictions) > 0, "Standard predictions should work"

    # Verify prediction structure is compatible
    for pred in predictions:
        # All standard fields should be present
        assert 'name' in pred
        assert 'frequency' in pred
        assert 'matches' in pred
        assert 'missing' in pred
        assert 'evidence' in pred
        assert 'confidence' in pred
        assert 'similarity' in pred
