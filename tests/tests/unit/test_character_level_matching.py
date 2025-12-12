"""
Tests for character-level matching (use_token_matching=False).

Verifies that:
1. Character-level matching produces correct predictions
2. Similarity scores differ from token-level by ~0.03 (expected variance)
3. Auto-toggle behavior works (use_token_matching=False → sort_symbols=False)
4. Threshold filtering works correctly
5. Edge cases are handled properly
6. Integration with filter pipeline works
7. Character-level mode is independent of token-level mode

Character-level matching uses fuzz.ratio() on joined strings, which is:
- 75x faster than difflib baseline (vs 9x for token-level)
- ~0.03 score difference from difflib
- Better for text chunks, worse for discrete tokens

TEST COVERAGE SUMMARY:
======================

TestBasicCharacterLevelFunctionality (3 tests):
    - test_character_level_mode_basic_matching: Basic predictions work
    - test_character_level_exact_match: Perfect match = 1.0 similarity
    - test_character_level_vs_token_level_similarity: Score differences are acceptable

TestAutoToggleBehavior (2 tests):
    - test_auto_toggle_sort_symbols_false: Auto-toggle works correctly
    - test_explicit_sort_symbols_with_character_level: Explicit setting works

TestThresholdFiltering (3 tests):
    - test_character_level_respects_recall_threshold: High threshold filters correctly
    - test_character_level_low_threshold_allows_matches: Low threshold allows matches
    - test_high_threshold_filters_garbage_predictions: Unrelated patterns filtered

TestEdgeCases (4 tests):
    - test_character_level_empty_state: Empty STM handled gracefully
    - test_character_level_single_token: Single token (insufficient) handled
    - test_character_level_special_characters: Special chars don't break matching
    - test_character_level_with_vectors: VCTR| tokens handled correctly

TestIntegration (4 tests):
    - test_character_level_with_multiple_patterns: Multiple patterns work
    - test_switching_between_modes: Can switch between token/char modes
    - test_character_level_with_emotives: Emotives don't break matching
    - test_character_level_with_metadata: Metadata doesn't break matching

TestRegressionPrevention (2 tests):
    - test_character_level_does_not_affect_token_level: Modes independent
    - test_modes_are_independent: Same patterns work with both modes

TestPerformanceCharacteristics (2 tests):
    - test_character_level_handles_long_sequences: Long sequences handled
    - test_character_level_handles_many_patterns: Many patterns handled

TOTAL: 20 comprehensive tests covering character-level matching functionality
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from fixtures.kato_fixtures import kato_fixture as kato_fixture


class TestBasicCharacterLevelFunctionality:
    """Test basic character-level matching functionality."""

    def test_character_level_mode_basic_matching(self, kato_fixture):
        """Test that character-level matching produces predictions."""
        kato = kato_fixture
        kato.clear_all_memory()

        # Set character-level matching
        result = kato.update_config({'use_token_matching': False})
        assert result.get('status') == 'okay'

        # Learn a pattern
        kato.observe({'strings': ['apple', 'banana', 'cherry']})
        kato.learn()

        # Query with partial match
        kato.clear_stm()
        kato.observe({'strings': ['apple', 'banana']})

        predictions = kato.get_predictions()

        # Should get predictions with character-level matching
        assert len(predictions) > 0, "Character-level matching should produce predictions"
        assert predictions[0].get('similarity', 0) > 0.5

    def test_character_level_exact_match(self, kato_fixture):
        """Test that character-level matching gives 1.0 similarity for exact matches."""
        kato = kato_fixture
        kato.clear_all_memory()

        # Set character-level matching
        kato.update_config({'use_token_matching': False})

        # Learn a pattern
        pattern = ['dog', 'cat', 'bird']
        kato.observe({'strings': pattern})
        kato.learn()

        # Query with exact same pattern
        kato.clear_stm()
        kato.observe({'strings': pattern})

        predictions = kato.get_predictions()

        # Should have perfect match
        assert len(predictions) > 0
        # Allow small floating point variance
        assert predictions[0].get('similarity', 0) >= 0.99

    def test_character_level_vs_token_level_similarity(self, kato_fixture):
        """Test that character-level and token-level produce similar but not identical scores."""
        kato = kato_fixture
        kato.clear_all_memory()

        # Learn pattern with token-level (default)
        kato.update_config({'use_token_matching': True})
        pattern = ['token1', 'token2', 'token3', 'token4']
        kato.observe({'strings': pattern})
        kato.learn()

        # Query with partial match using token-level
        kato.clear_stm()
        query = ['token1', 'token2', 'token3']
        kato.observe({'strings': query})
        token_level_predictions = kato.get_predictions()

        # Same query with character-level
        kato.clear_stm()
        kato.update_config({'use_token_matching': False})
        kato.observe({'strings': query})
        char_level_predictions = kato.get_predictions()

        # Both should produce predictions
        assert len(token_level_predictions) > 0
        assert len(char_level_predictions) > 0

        # Similarity scores should be close but may differ by ~0.05
        # (documented variance is ~0.03, add margin for safety)
        token_sim = token_level_predictions[0].get('similarity', 0)
        char_sim = char_level_predictions[0].get('similarity', 0)

        # Verify both are reasonable
        assert 0.6 < token_sim < 1.0, f"Token-level similarity out of range: {token_sim}"
        assert 0.6 < char_sim < 1.0, f"Character-level similarity out of range: {char_sim}"

        # Verify they're close (within 0.1 to be safe)
        assert abs(token_sim - char_sim) < 0.1, \
            f"Token-level ({token_sim}) and character-level ({char_sim}) differ by more than 0.1"


class TestAutoToggleBehavior:
    """Test auto-toggle behavior between use_token_matching and sort_symbols."""

    def test_auto_toggle_sort_symbols_false(self, kato_fixture):
        """Test that use_token_matching=False auto-toggles sort_symbols=False."""
        kato = kato_fixture
        kato.clear_all_memory()

        # Set character-level without explicitly setting sort_symbols
        result = kato.update_config({'use_token_matching': False})
        assert result.get('status') == 'okay'

        # Verify it works (auto-toggle should have set sort_symbols=False)
        # We can't directly check internal state, but we can verify it works
        kato.observe({'strings': ['z', 'y', 'x']})
        kato.learn()

        kato.clear_stm()
        kato.observe({'strings': ['z', 'y']})
        predictions = kato.get_predictions()

        # Should work correctly
        assert len(predictions) > 0

    def test_explicit_sort_symbols_with_character_level(self, kato_fixture):
        """Test explicitly setting both use_token_matching and sort_symbols."""
        kato = kato_fixture
        kato.clear_all_memory()

        # Explicitly set both (recommended approach)
        result = kato.update_config({
            'use_token_matching': False,
            'sort_symbols': False
        })
        assert result.get('status') == 'okay'

        # Verify it works
        kato.observe({'strings': ['a', 'b', 'c']})
        kato.learn()

        kato.clear_stm()
        kato.observe({'strings': ['a', 'b']})
        predictions = kato.get_predictions()

        assert len(predictions) > 0


class TestThresholdFiltering:
    """Test threshold filtering with character-level matching."""

    def test_character_level_respects_recall_threshold(self, kato_fixture):
        """Test that character-level matching filters by recall_threshold."""
        kato = kato_fixture
        kato.clear_all_memory()

        # Set character-level with high threshold
        kato.update_config({
            'use_token_matching': False,
            'recall_threshold': 0.9
        })

        # Learn a pattern
        kato.observe({'strings': ['apple', 'banana', 'cherry', 'date', 'elderberry']})
        kato.learn()

        # Query with low similarity (only 2/5 tokens)
        kato.clear_stm()
        kato.observe({'strings': ['apple', 'banana']})

        predictions = kato.get_predictions()

        # With high threshold and low similarity, should get 0 or very few predictions
        # The similarity of 2/5 tokens is ~0.57, below 0.9 threshold
        assert len(predictions) == 0, \
            f"Expected 0 predictions with threshold=0.9 and low similarity, got {len(predictions)}"

    def test_character_level_low_threshold_allows_matches(self, kato_fixture):
        """Test that low threshold allows matches through."""
        kato = kato_fixture
        kato.clear_all_memory()

        # Set character-level with low threshold
        kato.update_config({
            'use_token_matching': False,
            'recall_threshold': 0.3
        })

        # Learn a pattern
        kato.observe({'strings': ['apple', 'banana', 'cherry', 'date', 'elderberry']})
        kato.learn()

        # Query with moderate similarity
        kato.clear_stm()
        kato.observe({'strings': ['apple', 'banana', 'cherry']})

        predictions = kato.get_predictions()

        # With low threshold, should get predictions
        assert len(predictions) > 0
        assert predictions[0].get('similarity', 0) > 0.3

    def test_high_threshold_filters_garbage_predictions(self, kato_fixture):
        """Test that character-level with high threshold filters unrelated patterns."""
        kato = kato_fixture
        kato.clear_all_memory()

        # Set very high recall threshold
        kato.update_config({
            'use_token_matching': False,
            'recall_threshold': 0.8
        })

        # Learn multiple unrelated patterns
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

        # Query with completely different tokens
        kato.clear_stm()
        observation = ['zebra', 'elephant', 'giraffe']
        for token in observation:
            kato.observe({'strings': [token]})

        predictions = kato.get_predictions()

        # With no matching tokens and high threshold, should get NO predictions
        assert len(predictions) == 0, \
            f"Expected 0 predictions with no matching tokens and high threshold, got {len(predictions)}"


class TestEdgeCases:
    """Test edge cases with character-level matching."""

    def test_character_level_empty_state(self, kato_fixture):
        """Test character-level matching with empty state."""
        kato = kato_fixture
        kato.clear_all_memory()

        kato.update_config({'use_token_matching': False})

        # Learn a pattern
        kato.observe({'strings': ['a', 'b']})
        kato.learn()

        # Query with empty state
        kato.clear_stm()
        # Don't observe anything

        predictions = kato.get_predictions()

        # Should handle gracefully (no predictions from empty state)
        assert isinstance(predictions, list)
        assert len(predictions) == 0

    def test_character_level_single_token(self, kato_fixture):
        """Test character-level matching with single token (insufficient for predictions)."""
        kato = kato_fixture
        kato.clear_all_memory()

        kato.update_config({'use_token_matching': False})

        # Learn a pattern
        kato.observe({'strings': ['a', 'b', 'c']})
        kato.learn()

        # Query with single token (need ≥2 for predictions)
        kato.clear_stm()
        kato.observe({'strings': ['a']})

        predictions = kato.get_predictions()

        # Single token is insufficient (KATO requires ≥2 tokens in STM)
        assert len(predictions) == 0

    def test_character_level_special_characters(self, kato_fixture):
        """Test character-level matching with special characters."""
        kato = kato_fixture
        kato.clear_all_memory()

        kato.update_config({'use_token_matching': False})

        # Learn pattern with special characters
        special_tokens = ['hello-world', 'test_123', 'foo.bar']
        kato.observe({'strings': special_tokens})
        kato.learn()

        # Query with same tokens
        kato.clear_stm()
        kato.observe({'strings': special_tokens[:2]})

        predictions = kato.get_predictions()

        # Should match despite special characters
        assert len(predictions) > 0
        assert predictions[0].get('similarity', 0) > 0.5

    def test_character_level_with_vectors(self, kato_fixture):
        """Test character-level matching with vector tokens (VCTR|hash)."""
        kato = kato_fixture
        kato.clear_all_memory()

        kato.update_config({'use_token_matching': False})

        # Learn pattern with vector-like tokens
        tokens = ['VCTR|abc123', 'VCTR|def456', 'regular_token']
        kato.observe({'strings': tokens})
        kato.learn()

        # Query with partial match
        kato.clear_stm()
        kato.observe({'strings': tokens[:2]})

        predictions = kato.get_predictions()

        # Should handle vector tokens correctly
        assert len(predictions) > 0
        assert predictions[0].get('similarity', 0) > 0.5


class TestIntegration:
    """Test character-level matching in integration scenarios."""

    def test_character_level_with_multiple_patterns(self, kato_fixture):
        """Test character-level matching with multiple learned patterns."""
        kato = kato_fixture
        kato.clear_all_memory()

        kato.update_config({
            'use_token_matching': False,
            'recall_threshold': 0.5
        })

        # Learn multiple patterns
        patterns = [
            ['a', 'b', 'c'],
            ['a', 'b', 'd'],
            ['x', 'y', 'z']
        ]

        for pattern in patterns:
            kato.clear_stm()
            kato.observe({'strings': pattern})
            kato.learn()

        # Query that matches first two patterns
        kato.clear_stm()
        kato.observe({'strings': ['a', 'b']})

        predictions = kato.get_predictions()

        # Should get predictions for patterns that match
        assert len(predictions) >= 2, "Should match at least 2 similar patterns"

        # Verify they all meet threshold
        for pred in predictions:
            assert pred.get('similarity', 0) >= 0.5

    def test_switching_between_modes(self, kato_fixture):
        """Test switching between token-level and character-level modes."""
        kato = kato_fixture
        kato.clear_all_memory()

        # Learn with token-level
        kato.update_config({'use_token_matching': True})
        kato.observe({'strings': ['test1', 'test2', 'test3']})
        kato.learn()

        # Query with token-level
        kato.clear_stm()
        kato.observe({'strings': ['test1', 'test2']})
        token_preds = kato.get_predictions()

        # Switch to character-level and query again
        kato.clear_stm()
        kato.update_config({'use_token_matching': False})
        kato.observe({'strings': ['test1', 'test2']})
        char_preds = kato.get_predictions()

        # Both should produce predictions
        assert len(token_preds) > 0
        assert len(char_preds) > 0

        # Should match the same pattern
        if token_preds and char_preds:
            assert token_preds[0]['name'] == char_preds[0]['name']

    def test_character_level_with_emotives(self, kato_fixture):
        """Test character-level matching with emotives."""
        kato = kato_fixture
        kato.clear_all_memory()

        kato.update_config({'use_token_matching': False})

        # Learn pattern with emotives (dict format)
        kato.observe({'strings': ['happy', 'joy'], 'emotives': {'happiness': 0.8}})
        kato.observe({'strings': ['celebration'], 'emotives': {'happiness': 0.9}})
        kato.learn()

        # Query with partial match and emotives
        kato.clear_stm()
        kato.observe({'strings': ['happy', 'joy'], 'emotives': {'happiness': 0.7}})

        predictions = kato.get_predictions()

        # Should get predictions (emotives shouldn't break character-level matching)
        assert len(predictions) > 0
        assert predictions[0].get('similarity', 0) > 0.5

    def test_character_level_with_metadata(self, kato_fixture):
        """Test character-level matching with metadata."""
        kato = kato_fixture
        kato.clear_all_memory()

        kato.update_config({'use_token_matching': False})

        # Learn pattern with metadata
        kato.observe({'strings': ['test', 'data'], 'metadata': {'source': 'test1'}})
        kato.observe({'strings': ['more'], 'metadata': {'source': 'test1'}})
        kato.learn()

        # Query with metadata
        kato.clear_stm()
        kato.observe({'strings': ['test', 'data'], 'metadata': {'source': 'test2'}})

        predictions = kato.get_predictions()

        # Should get predictions (metadata shouldn't break character-level matching)
        assert len(predictions) > 0


class TestRegressionPrevention:
    """Test that character-level mode doesn't affect token-level mode."""

    def test_character_level_does_not_affect_token_level(self, kato_fixture):
        """Test that using character-level doesn't break token-level mode."""
        kato = kato_fixture
        kato.clear_all_memory()

        # Use character-level mode
        kato.update_config({'use_token_matching': False})
        kato.observe({'strings': ['char1', 'char2']})
        kato.learn()

        # Switch back to token-level
        kato.clear_all_memory()
        kato.update_config({'use_token_matching': True})

        # Learn and query with token-level
        kato.observe({'strings': ['token1', 'token2', 'token3']})
        kato.learn()

        kato.clear_stm()
        kato.observe({'strings': ['token1', 'token2']})

        predictions = kato.get_predictions()

        # Token-level should work normally
        assert len(predictions) > 0
        assert predictions[0].get('similarity', 0) > 0.5

    def test_modes_are_independent(self, kato_fixture):
        """Test that learned patterns work with both modes."""
        kato = kato_fixture
        kato.clear_all_memory()

        # Learn pattern (mode doesn't affect storage)
        kato.observe({'strings': ['data1', 'data2', 'data3']})
        kato.learn()

        # Query with token-level
        kato.clear_stm()
        kato.update_config({'use_token_matching': True})
        kato.observe({'strings': ['data1', 'data2']})
        token_preds = kato.get_predictions()

        # Query with character-level
        kato.clear_stm()
        kato.update_config({'use_token_matching': False})
        kato.observe({'strings': ['data1', 'data2']})
        char_preds = kato.get_predictions()

        # Both should find the same pattern
        assert len(token_preds) > 0
        assert len(char_preds) > 0
        assert token_preds[0]['name'] == char_preds[0]['name']


class TestPerformanceCharacteristics:
    """Test performance-related characteristics (not actual benchmarks)."""

    def test_character_level_handles_long_sequences(self, kato_fixture):
        """Test that character-level handles longer sequences efficiently."""
        kato = kato_fixture
        kato.clear_all_memory()

        kato.update_config({'use_token_matching': False})

        # Learn pattern with many tokens
        long_pattern = [f"token{i}" for i in range(30)]
        kato.observe({'strings': long_pattern})
        kato.learn()

        # Query with subset
        kato.clear_stm()
        kato.observe({'strings': long_pattern[:10]})

        predictions = kato.get_predictions()

        # Should handle long sequences
        assert isinstance(predictions, list)
        # May or may not have predictions depending on similarity

    def test_character_level_handles_many_patterns(self, kato_fixture):
        """Test that character-level handles many patterns."""
        kato = kato_fixture
        kato.clear_all_memory()

        kato.update_config({
            'use_token_matching': False,
            'recall_threshold': 0.7
        })

        # Learn many patterns
        for i in range(20):
            kato.clear_stm()
            kato.observe({'strings': [f"pattern{i}_a", f"pattern{i}_b"]})
            kato.learn()

        # Query
        kato.clear_stm()
        kato.observe({'strings': ['pattern0_a', 'pattern0_b']})

        predictions = kato.get_predictions()

        # Should handle many patterns and filter correctly
        assert isinstance(predictions, list)
        # Should get at least the exact match
        assert len(predictions) >= 1
