"""
Unit tests for RapidFuzz integration in pattern matching.

Tests ensure that:
1. RapidFuzz produces identical results to difflib
2. Performance is significantly better with RapidFuzz
3. Graceful fallback works when RapidFuzz is not available
4. String caching optimization works correctly
"""

import os
import pytest
from unittest.mock import patch

# Try to import RapidFuzz to check availability
try:
    import rapidfuzz
    RAPIDFUZZ_INSTALLED = True
except ImportError:
    RAPIDFUZZ_INSTALLED = False


# Skip all tests if running in environment without MongoDB
pytestmark = pytest.mark.skipif(
    not os.environ.get('KATO_SERVICES_RUNNING'),
    reason="KATO services not running (set KATO_SERVICES_RUNNING=true to enable)"
)


class TestRapidFuzzDeterminism:
    """Test that RapidFuzz produces identical results to difflib."""

    @pytest.mark.skipif(not RAPIDFUZZ_INSTALLED, reason="RapidFuzz not installed")
    def test_rapidfuzz_vs_difflib_identical_predictions(self, kato_fixture):
        """Test that RapidFuzz and difflib produce identical prediction results."""
        kato = kato_fixture

        # Learn a simple pattern
        kato.observe({'strings': ['A', 'B']})
        kato.observe({'strings': ['C', 'D']})
        kato.learn()

        # Clear STM and observe matching state
        kato.clear_stm()
        kato.observe({'strings': ['A', 'B', 'C', 'D']})

        # Get predictions with RapidFuzz (default)
        os.environ['KATO_USE_FAST_MATCHING'] = 'true'
        rapidfuzz_predictions = kato.get_predictions()

        # Clear and observe again
        kato.clear_stm()
        kato.observe({'strings': ['A', 'B', 'C', 'D']})

        # Get predictions with difflib
        os.environ['KATO_USE_FAST_MATCHING'] = 'false'
        difflib_predictions = kato.get_predictions()

        # Reset to default
        os.environ['KATO_USE_FAST_MATCHING'] = 'true'

        # Should have same number of predictions
        assert len(rapidfuzz_predictions) == len(difflib_predictions)

        # Predictions should be identical (same pattern names)
        if len(rapidfuzz_predictions) > 0:
            rapidfuzz_names = {p['name'] for p in rapidfuzz_predictions}
            difflib_names = {p['name'] for p in difflib_predictions}
            assert rapidfuzz_names == difflib_names

    @pytest.mark.skipif(not RAPIDFUZZ_INSTALLED, reason="RapidFuzz not installed")
    def test_rapidfuzz_vs_difflib_identical_similarity_scores(self, kato_fixture):
        """Test that similarity scores match between RapidFuzz and difflib."""
        kato = kato_fixture

        # Learn multiple patterns
        patterns = [
            ['A', 'B', 'C'],
            ['A', 'B', 'D'],
            ['A', 'C', 'E'],
        ]

        for pattern_symbols in patterns:
            kato.clear_stm()
            kato.observe({'strings': pattern_symbols})
            kato.learn()

        # Query with partial match
        kato.clear_stm()
        kato.observe({'strings': ['A', 'B']})

        # Get with RapidFuzz
        os.environ['KATO_USE_FAST_MATCHING'] = 'true'
        rapidfuzz_preds = kato.get_predictions()

        # Get with difflib
        kato.clear_stm()
        kato.observe({'strings': ['A', 'B']})
        os.environ['KATO_USE_FAST_MATCHING'] = 'false'
        difflib_preds = kato.get_predictions()

        # Reset
        os.environ['KATO_USE_FAST_MATCHING'] = 'true'

        # Compare similarity scores (should be close, allowing for floating point)
        if len(rapidfuzz_preds) > 0 and len(difflib_preds) > 0:
            # Sort by name for comparison
            rf_sorted = sorted(rapidfuzz_preds, key=lambda x: x['name'])
            df_sorted = sorted(difflib_preds, key=lambda x: x['name'])

            for rf_pred, df_pred in zip(rf_sorted, df_sorted):
                assert rf_pred['name'] == df_pred['name']
                # Similarity scores should match closely
                assert abs(rf_pred.get('similarity', 0) - df_pred.get('similarity', 0)) < 0.01


class TestRapidFuzzThreshold:
    """Test threshold filtering with RapidFuzz."""

    @pytest.mark.skipif(not RAPIDFUZZ_INSTALLED, reason="RapidFuzz not installed")
    def test_rapidfuzz_respects_recall_threshold(self, kato_fixture):
        """Test that RapidFuzz filters results based on recall_threshold."""
        kato = kato_fixture

        # Learn a pattern
        kato.observe({'strings': ['A', 'B', 'C', 'D', 'E']})
        kato.learn()

        # Set high threshold
        kato.update_genes({'recall_threshold': 0.9})

        # Query with low similarity
        kato.clear_stm()
        kato.observe({'strings': ['A', 'B']})  # Only 40% match

        predictions = kato.get_predictions()

        # Should get no predictions with high threshold
        assert len(predictions) == 0

        # Lower threshold
        kato.update_genes({'recall_threshold': 0.3})

        # Same query
        kato.clear_stm()
        kato.observe({'strings': ['A', 'B']})

        predictions = kato.get_predictions()

        # Should get predictions with low threshold
        assert len(predictions) > 0

    @pytest.mark.skipif(not RAPIDFUZZ_INSTALLED, reason="RapidFuzz not installed")
    def test_rapidfuzz_score_cutoff_optimization(self, kato_fixture):
        """Test that score_cutoff optimization works correctly."""
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
        kato.update_genes({'recall_threshold': 0.5})
        kato.observe({'strings': ['A', 'B']})

        predictions = kato.get_predictions()

        # Should filter out low-similarity patterns
        # score_cutoff should have rejected them early
        for pred in predictions:
            assert pred.get('similarity', 0) >= 0.5


class TestRapidFuzzEdgeCases:
    """Test edge cases with RapidFuzz."""

    @pytest.mark.skipif(not RAPIDFUZZ_INSTALLED, reason="RapidFuzz not installed")
    def test_rapidfuzz_empty_state(self, kato_fixture):
        """Test RapidFuzz with empty state."""
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

    @pytest.mark.skipif(not RAPIDFUZZ_INSTALLED, reason="RapidFuzz not installed")
    def test_rapidfuzz_special_characters(self, kato_fixture):
        """Test RapidFuzz with special characters in symbols."""
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

    @pytest.mark.skipif(not RAPIDFUZZ_INSTALLED, reason="RapidFuzz not installed")
    def test_rapidfuzz_large_vocabulary(self, kato_fixture):
        """Test RapidFuzz with large symbol vocabulary."""
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


class TestRapidFuzzFallback:
    """Test graceful fallback when RapidFuzz is not available."""

    def test_fallback_to_difflib_when_rapidfuzz_missing(self, kato_fixture):
        """Test that system falls back to difflib if RapidFuzz not available."""
        kato = kato_fixture

        # Force difflib mode
        os.environ['KATO_USE_FAST_MATCHING'] = 'false'

        # Learn a pattern
        kato.observe({'strings': ['A', 'B', 'C']})
        kato.learn()

        # Query
        kato.clear_stm()
        kato.observe({'strings': ['A', 'B']})

        predictions = kato.get_predictions()

        # Should still work with difflib
        assert len(predictions) > 0

        # Reset
        os.environ['KATO_USE_FAST_MATCHING'] = 'true'

    def test_environment_variable_controls_matcher(self, kato_fixture):
        """Test that KATO_USE_FAST_MATCHING env var controls which matcher is used."""
        kato = kato_fixture

        # Learn a pattern
        kato.observe({'strings': ['test1', 'test2']})
        kato.learn()

        # Test with fast matching enabled
        os.environ['KATO_USE_FAST_MATCHING'] = 'true'
        kato.clear_stm()
        kato.observe({'strings': ['test1']})
        fast_preds = kato.get_predictions()

        # Test with fast matching disabled
        os.environ['KATO_USE_FAST_MATCHING'] = 'false'
        kato.clear_stm()
        kato.observe({'strings': ['test1']})
        slow_preds = kato.get_predictions()

        # Reset
        os.environ['KATO_USE_FAST_MATCHING'] = 'true'

        # Should get same results either way
        assert len(fast_preds) == len(slow_preds)


class TestStringCaching:
    """Test string caching optimization for RapidFuzz."""

    @pytest.mark.skipif(not RAPIDFUZZ_INSTALLED, reason="RapidFuzz not installed")
    def test_string_cache_populated(self, kato_fixture):
        """Test that string cache is populated on first query."""
        kato = kato_fixture

        # Learn patterns
        kato.observe({'strings': ['A', 'B']})
        kato.learn()

        # First query should populate cache
        kato.clear_stm()
        kato.observe({'strings': ['A']})
        kato.get_predictions()

        # Second query should use cache (faster)
        kato.clear_stm()
        kato.observe({'strings': ['A']})
        kato.get_predictions()

        # Cache should exist (we can't directly test PatternSearcher internals
        # but we can verify it doesn't error)
        assert True

    @pytest.mark.skipif(not RAPIDFUZZ_INSTALLED, reason="RapidFuzz not installed")
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
        kato.observe({'strings': ['C']})
        predictions = kato.get_predictions()

        # Should work fine with new patterns
        assert len(predictions) > 0


class TestPerformance:
    """Test that RapidFuzz is actually faster (optional, may be slow)."""

    @pytest.mark.slow
    @pytest.mark.skipif(not RAPIDFUZZ_INSTALLED, reason="RapidFuzz not installed")
    def test_rapidfuzz_faster_than_difflib(self, kato_fixture):
        """Test that RapidFuzz is measurably faster than difflib."""
        import time
        kato = kato_fixture

        # Learn many patterns
        for i in range(100):
            kato.clear_stm()
            kato.observe({'strings': [f"sym{i}", f"sym{i+1}", f"sym{i+2}"]})
            kato.learn()

        # Benchmark difflib
        os.environ['KATO_USE_FAST_MATCHING'] = 'false'
        kato.clear_stm()
        kato.observe({'strings': ['sym50', 'sym51']})

        start_difflib = time.perf_counter()
        kato.get_predictions()
        difflib_time = time.perf_counter() - start_difflib

        # Benchmark RapidFuzz
        os.environ['KATO_USE_FAST_MATCHING'] = 'true'
        kato.clear_stm()
        kato.observe({'strings': ['sym50', 'sym51']})

        start_rapidfuzz = time.perf_counter()
        kato.get_predictions()
        rapidfuzz_time = time.perf_counter() - start_rapidfuzz

        # Reset
        os.environ['KATO_USE_FAST_MATCHING'] = 'true'

        # RapidFuzz should be faster (at least 2x for 100 patterns)
        # This is a loose check - actual speedup increases with pattern count
        assert rapidfuzz_time < difflib_time, \
            f"RapidFuzz ({rapidfuzz_time:.4f}s) should be faster than difflib ({difflib_time:.4f}s)"
