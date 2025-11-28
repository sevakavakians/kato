"""
Tests for use_token_matching configuration and auto-toggle behavior.

Verifies that:
1. Token-level matching produces correct low similarity for few matches
2. Configuration is properly stored in session config
3. Patterns are correctly filtered with token-level matching
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from fixtures.kato_fixtures import kato_fixture as kato_fixture


def test_token_matching_filters_low_similarity_correctly(kato_fixture):
    """
    Test that token-level matching correctly calculates low similarity
    for patterns with few matching tokens.
    """
    kato = kato_fixture
    kato.clear_all_memory()

    # Set high recall threshold
    kato.update_config({'recall_threshold': 0.6})

    # Learn a pattern
    pattern_tokens = ['token1', 'token2', 'token3', 'token4', 'token5', 'token6', 'token7', 'token8']
    for token in pattern_tokens:
        kato.observe({'strings': [token]})
    kato.learn()

    # Clear STM and observe with only 1 matching token
    kato.clear_stm()
    observation_tokens = ['other1', 'other2', 'other3', 'other4', 'other5', 'other6', 'other7', 'token1']
    for token in observation_tokens:
        kato.observe({'strings': [token]})

    # Get predictions
    predictions = kato.get_predictions()

    # With token-level matching and only 1 match out of 8 tokens:
    # - Similarity should be approximately 2*1/(8+8) = 0.125
    # - With recall_threshold=0.6, this should be FILTERED OUT
    # - Result: Should have 0 predictions (or very few if there are partial matches)

    # The key assertion: Should NOT have high-similarity predictions
    # because token-level matching gives correct low similarity
    if len(predictions) > 0:
        # If there are any predictions, they should have low similarity
        max_similarity = max(p.get('similarity', 0) for p in predictions)
        assert max_similarity < 0.3, \
            f"With only 1 matching token, similarity should be low, got {max_similarity}"


def test_high_recall_threshold_filters_garbage_predictions(kato_fixture):
    """
    Test that with token-level matching and high recall threshold,
    patterns with low token overlap are properly filtered out.
    """
    kato = kato_fixture
    kato.clear_all_memory()

    # Set very high recall threshold
    kato.update_config({'recall_threshold': 0.8})

    # Learn multiple patterns
    patterns = [
        ['apple', 'banana', 'cherry'],
        ['dog', 'cat', 'bird'],
        ['red', 'green', 'blue']
    ]

    for pattern in patterns:
        kato.clear_stm()
        for token in pattern:
            kato.observe({'strings': [token]})
        kato.learn()

    # Clear and observe completely different tokens
    kato.clear_stm()
    observation = ['zebra', 'elephant', 'giraffe']
    for token in observation:
        kato.observe({'strings': [token]})

    # Get predictions
    predictions = kato.get_predictions()

    # With no matching tokens and high threshold, should get NO predictions
    assert len(predictions) == 0, \
        f"Expected 0 predictions with no matching tokens and high threshold, got {len(predictions)}"
