"""
Unit tests for RapidFuzz integration in pattern matching.

Tests ensure that:
1. Threshold filtering works correctly with the active matcher
2. Edge cases are handled properly (empty state, special chars, large vocabularies)
3. Pattern cache clearing works correctly

Note: Matcher comparison (RapidFuzz vs difflib) requires different server
configurations and cannot be toggled via local environment variables since
tests run against a Docker-hosted KATO service. Performance benchmarking
is done in benchmarks/compare_matchers.py.
"""

import pytest

# Try to import RapidFuzz to check availability
try:
    import rapidfuzz
    RAPIDFUZZ_INSTALLED = True
except ImportError:
    RAPIDFUZZ_INSTALLED = False


class TestMatcherDeterminism:
    """Test that the active matcher produces deterministic results."""

    def test_deterministic_predictions_across_queries(self, kato_fixture):
        """Test that repeated queries produce identical prediction results."""
        kato = kato_fixture

        # Learn a simple pattern
        kato.observe({'strings': ['A', 'B']})
        kato.observe({'strings': ['C', 'D']})
        kato.learn()

        # Query twice and compare
        kato.clear_stm()
        kato.observe({'strings': ['A', 'B', 'C', 'D']})
        predictions_1 = kato.get_predictions()

        kato.clear_stm()
        kato.observe({'strings': ['A', 'B', 'C', 'D']})
        predictions_2 = kato.get_predictions()

        # Should have same number of predictions
        assert len(predictions_1) == len(predictions_2), \
            f"Repeated queries should produce same count: {len(predictions_1)} vs {len(predictions_2)}"

        # Predictions should be identical (same pattern names and scores)
        if len(predictions_1) > 0:
            names_1 = {p['name'] for p in predictions_1}
            names_2 = {p['name'] for p in predictions_2}
            assert names_1 == names_2, "Repeated queries should return same pattern names"

            # Similarity scores should be identical
            sorted_1 = sorted(predictions_1, key=lambda x: x['name'])
            sorted_2 = sorted(predictions_2, key=lambda x: x['name'])
            for p1, p2 in zip(sorted_1, sorted_2):
                assert p1['name'] == p2['name']
                assert abs(p1.get('similarity', 0) - p2.get('similarity', 0)) < 0.001, \
                    f"Similarity scores should match: {p1.get('similarity')} vs {p2.get('similarity')}"


class TestMatcherThreshold:
    """Test threshold filtering with the active matcher."""

    def test_respects_recall_threshold(self, kato_fixture):
        """Test that the matcher filters results based on recall_threshold."""
        kato = kato_fixture

        # Learn a pattern
        kato.observe({'strings': ['A', 'B', 'C', 'D', 'E']})
        kato.learn()

        # Set high threshold
        kato.update_config({'recall_threshold': 0.9})

        # Query with low similarity
        kato.clear_stm()
        kato.observe({'strings': ['A', 'B']})  # Only 40% match

        predictions = kato.get_predictions()

        # Should get no predictions with high threshold
        assert len(predictions) == 0

        # Lower threshold
        kato.update_config({'recall_threshold': 0.3})

        # Same query
        kato.clear_stm()
        kato.observe({'strings': ['A', 'B']})

        predictions = kato.get_predictions()

        # Should get predictions with low threshold
        assert len(predictions) > 0

    def test_score_cutoff_optimization(self, kato_fixture):
        """Test that score_cutoff correctly filters low-similarity patterns."""
        kato = kato_fixture

        # Learn multiple patterns with varying similarity
        patterns = [
            ['A', 'B', 'C', 'D', 'E'],  # Low similarity to query
            ['X', 'Y', 'Z'],            # No similarity
            ['A', 'B', 'X'],             # Medium similarity
        ]

        for pattern_symbols in patterns:
            kato.clear_stm()
            kato.observe({'strings': pattern_symbols})
            kato.learn()

        # Query
        kato.clear_stm()
        kato.update_config({'recall_threshold': 0.5})
        kato.observe({'strings': ['A', 'B']})

        predictions = kato.get_predictions()

        # Should filter out low-similarity patterns
        for pred in predictions:
            assert pred.get('similarity', 0) >= 0.5


class TestMatcherEdgeCases:
    """Test edge cases with the active matcher."""

    def test_empty_state(self, kato_fixture):
        """Test matcher with empty state."""
        kato = kato_fixture

        # Learn a pattern
        kato.observe({'strings': ['A', 'B']})
        kato.learn()

        # Query with empty state (just vectors)
        kato.clear_stm()
        # Don't observe anything

        predictions = kato.get_predictions()

        # Should handle gracefully (likely no predictions)
        assert isinstance(predictions, list)

    def test_special_characters(self, kato_fixture):
        """Test matcher with special characters in symbols."""
        kato = kato_fixture

        # Learn pattern with special characters
        kato.observe({'strings': ['hello|world', 'VCTR|abc123', 'sym_test-123']})
        kato.learn()

        # Query with same symbols
        kato.clear_stm()
        kato.observe({'strings': ['hello|world', 'VCTR|abc123']})

        predictions = kato.get_predictions()

        # Should match despite special characters
        assert len(predictions) > 0
        assert predictions[0].get('similarity', 0) > 0.5

    def test_large_vocabulary(self, kato_fixture):
        """Test matcher with large symbol vocabulary."""
        kato = kato_fixture

        # Learn pattern with many symbols
        symbols = [f"sym{i}" for i in range(50)]
        kato.observe({'strings': symbols[:25]})
        kato.observe({'strings': symbols[25:]})
        kato.learn()

        # Query with subset
        kato.clear_stm()
        kato.observe({'strings': symbols[:10]})

        predictions = kato.get_predictions()

        # Should handle large patterns
        assert isinstance(predictions, list)


class TestStringCaching:
    """Test string caching optimization."""

    def test_string_cache_cleared_on_pattern_delete(self, kato_fixture):
        """Test that string cache is cleared when patterns are deleted."""
        kato = kato_fixture

        # Learn pattern
        kato.observe({'strings': ['A', 'B']})
        pattern_name = kato.learn()

        # Query to populate cache
        kato.clear_stm()
        kato.observe({'strings': ['A']})
        kato.get_predictions()

        # Clear all memory (should clear cache)
        kato.clear_all_memory()

        # Verify cache cleared by re-learning and querying
        kato.observe({'strings': ['C', 'D']})
        kato.learn()
        kato.clear_stm()
        kato.observe({'strings': ['C', 'D']})  # Need 2+ strings for predictions
        predictions = kato.get_predictions()

        # Should work fine with new patterns
        assert len(predictions) > 0
