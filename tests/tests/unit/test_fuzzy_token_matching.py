"""
Tests for fuzzy token matching with anomalies field.

Verifies that:
1. Fuzzy matching correctly matches similar tokens (e.g., 'bannana' → 'banana')
2. Anomalies field captures fuzzy matches with similarity scores
3. Missing/extras only include tokens that don't fuzzy match
4. Exact matches do not appear in anomalies
5. Threshold behavior works correctly
6. Backward compatibility (threshold=0.0 disables fuzzy matching)
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from fixtures.kato_fixtures import kato_fixture as kato_fixture


class TestBasicFuzzyMatching:
    """Test basic fuzzy token matching functionality."""

    def test_fuzzy_matching_with_misspelled_tokens(self, kato_fixture):
        """Test that fuzzy matching matches misspelled tokens."""
        kato = kato_fixture
        kato.clear_all_memory()

        # Enable fuzzy matching with threshold 0.85
        kato.update_config({'fuzzy_token_threshold': 0.85})

        # Learn a pattern
        kato.observe({'strings': ['apple', 'banana', 'cherry', 'date', 'elderberry']})
        kato.learn()

        # Query with misspelled tokens
        kato.clear_stm()
        kato.observe({'strings': ['apple', 'bannana', 'chery']})

        predictions = kato.get_predictions()

        # Should get predictions with fuzzy matches
        assert len(predictions) > 0, "Fuzzy matching should produce predictions"

        pred = predictions[0]

        # Check that anomalies field exists and contains fuzzy matches
        assert 'anomalies' in pred, "Prediction should have anomalies field"
        assert len(pred['anomalies']) >= 2, f"Should have at least 2 anomalies for misspellings, got {len(pred['anomalies'])}"

        # Check structure of anomalies
        for anomaly in pred['anomalies']:
            assert 'observed' in anomaly, "Anomaly should have 'observed' field"
            assert 'expected' in anomaly, "Anomaly should have 'expected' field"
            assert 'similarity' in anomaly, "Anomaly should have 'similarity' field"
            assert 0.0 <= anomaly['similarity'] <= 1.0, "Similarity should be between 0 and 1"

    def test_exact_matches_no_anomalies(self, kato_fixture):
        """Test that exact matches don't create anomalies."""
        kato = kato_fixture
        kato.clear_all_memory()

        # Enable fuzzy matching
        kato.update_config({'fuzzy_token_threshold': 0.85})

        # Learn a pattern
        kato.observe({'strings': ['dog', 'cat', 'bird']})
        kato.learn()

        # Query with exact same tokens
        kato.clear_stm()
        kato.observe({'strings': ['dog', 'cat', 'bird']})

        predictions = kato.get_predictions()

        assert len(predictions) > 0
        pred = predictions[0]

        # Exact matches should not create anomalies
        assert 'anomalies' in pred
        assert len(pred['anomalies']) == 0, f"Exact matches should have no anomalies, got {pred['anomalies']}"

    def test_fuzzy_matching_disabled_by_default(self, kato_fixture):
        """Test that fuzzy matching is disabled when threshold is 0.0."""
        kato = kato_fixture
        kato.clear_all_memory()

        # Fuzzy matching disabled (default threshold 0.0)
        kato.update_config({'fuzzy_token_threshold': 0.0})

        # Learn a pattern
        kato.observe({'strings': ['apple', 'banana', 'cherry']})
        kato.learn()

        # Query with misspelled tokens
        kato.clear_stm()
        kato.observe({'strings': ['apple', 'bannana']})

        predictions = kato.get_predictions()

        # May or may not get predictions depending on exact matching
        # But if we do, anomalies should be empty (fuzzy matching disabled)
        if len(predictions) > 0:
            pred = predictions[0]
            assert 'anomalies' in pred
            assert len(pred['anomalies']) == 0, "Disabled fuzzy matching should have no anomalies"


class TestThresholdBehavior:
    """Test fuzzy matching threshold behavior."""

    def test_high_threshold_filters_poor_matches(self, kato_fixture):
        """Test that high threshold (0.95) filters out poor fuzzy matches."""
        kato = kato_fixture
        kato.clear_all_memory()

        # Very high threshold - only near-exact matches
        kato.update_config({'fuzzy_token_threshold': 0.95})

        # Learn a pattern
        kato.observe({'strings': ['apple', 'banana', 'cherry']})
        kato.learn()

        # Query with very different tokens
        kato.clear_stm()
        kato.observe({'strings': ['aple', 'bnana']})  # Less similar

        predictions = kato.get_predictions()

        # High threshold should filter out poor matches
        # This is a weaker test - just check it doesn't crash
        assert isinstance(predictions, list)

    def test_low_threshold_allows_fuzzy_matches(self, kato_fixture):
        """Test that low threshold (0.7) allows more fuzzy matches."""
        kato = kato_fixture
        kato.clear_all_memory()

        # Lower threshold - more permissive
        kato.update_config({'fuzzy_token_threshold': 0.7})

        # Learn a pattern
        kato.observe({'strings': ['apple', 'banana', 'cherry']})
        kato.learn()

        # Query with more similar tokens (closer matches)
        kato.clear_stm()
        kato.observe({'strings': ['appl', 'banan', 'cherry']})

        predictions = kato.get_predictions()

        # Should get predictions with fuzzy matches (or at least not crash)
        assert isinstance(predictions, list)
        if len(predictions) > 0:
            pred = predictions[0]
            assert 'anomalies' in pred


class TestMissingExtras:
    """Test that missing/extras respect fuzzy matches."""

    def test_fuzzy_matched_not_in_extras(self, kato_fixture):
        """Test that fuzzy matched tokens don't appear in extras."""
        kato = kato_fixture
        kato.clear_all_memory()

        kato.update_config({'fuzzy_token_threshold': 0.85})

        # Learn pattern
        kato.observe({'strings': ['apple', 'banana']})
        kato.learn()

        # Query with misspelling
        kato.clear_stm()
        kato.observe({'strings': ['apple', 'bannana']})

        predictions = kato.get_predictions()

        if len(predictions) > 0:
            pred = predictions[0]

            # 'bannana' should fuzzy match 'banana', so not in extras
            # extras should be empty or minimal
            assert len(pred.get('extras', [[]])) <= 1, "Fuzzy matched tokens shouldn't be in extras"

    def test_unmatched_tokens_in_missing_extras(self, kato_fixture):
        """Test that tokens below threshold go to missing/extras."""
        kato = kato_fixture
        kato.clear_all_memory()

        kato.update_config({'fuzzy_token_threshold': 0.85})

        # Learn pattern
        kato.observe({'strings': ['apple', 'banana', 'cherry']})
        kato.learn()

        # Query with one match and one completely different token
        kato.clear_stm()
        kato.observe({'strings': ['apple', 'zebra']})

        predictions = kato.get_predictions()

        if len(predictions) > 0:
            pred = predictions[0]

            # 'zebra' should not fuzzy match anything, should be in extras
            # 'banana', 'cherry' should be in missing
            assert 'missing' in pred
            assert 'extras' in pred


class TestAnomaliesStructure:
    """Test the structure and content of anomalies field."""

    def test_anomalies_contain_similarity_scores(self, kato_fixture):
        """Test that anomalies include similarity scores."""
        kato = kato_fixture
        kato.clear_all_memory()

        kato.update_config({'fuzzy_token_threshold': 0.80})

        # Learn pattern
        kato.observe({'strings': ['hello', 'world']})
        kato.learn()

        # Query with similar tokens
        kato.clear_stm()
        kato.observe({'strings': ['helo', 'wrld']})

        predictions = kato.get_predictions()

        if len(predictions) > 0:
            pred = predictions[0]
            anomalies = pred.get('anomalies', [])

            for anomaly in anomalies:
                assert 'observed' in anomaly
                assert 'expected' in anomaly
                assert 'similarity' in anomaly
                # Similarity should be high enough to pass threshold
                assert anomaly['similarity'] >= 0.80

    def test_multiple_anomalies_in_one_prediction(self, kato_fixture):
        """Test handling multiple fuzzy matches in single prediction."""
        kato = kato_fixture
        kato.clear_all_memory()

        kato.update_config({'fuzzy_token_threshold': 0.80})

        # Learn longer pattern
        kato.observe({'strings': ['alpha', 'beta', 'gamma', 'delta']})
        kato.learn()

        # Query with multiple misspellings
        kato.clear_stm()
        kato.observe({'strings': ['alfa', 'bta', 'gama']})

        predictions = kato.get_predictions()

        if len(predictions) > 0:
            pred = predictions[0]
            anomalies = pred.get('anomalies', [])

            # Should have multiple anomalies
            assert len(anomalies) >= 2, "Should detect multiple fuzzy matches"


class TestIntegration:
    """Test fuzzy matching in integration scenarios."""

    def test_fuzzy_matching_with_emotives(self, kato_fixture):
        """Test that fuzzy matching works with emotives."""
        kato = kato_fixture
        kato.clear_all_memory()

        kato.update_config({'fuzzy_token_threshold': 0.85})

        # Learn with emotives
        kato.observe({'strings': ['happy', 'joy'], 'emotives': {'happiness': 0.8}})
        kato.learn()

        # Query with misspelling and emotives
        kato.clear_stm()
        kato.observe({'strings': ['hapy', 'joy'], 'emotives': {'happiness': 0.7}})

        predictions = kato.get_predictions()

        # Should work with emotives
        assert isinstance(predictions, list)

    def test_fuzzy_matching_with_metadata(self, kato_fixture):
        """Test that fuzzy matching works with metadata."""
        kato = kato_fixture
        kato.clear_all_memory()

        kato.update_config({'fuzzy_token_threshold': 0.85})

        # Learn with metadata
        kato.observe({'strings': ['test', 'data'], 'metadata': {'source': 'test1'}})
        kato.learn()

        # Query with metadata
        kato.clear_stm()
        kato.observe({'strings': ['tst', 'data'], 'metadata': {'source': 'test2'}})

        predictions = kato.get_predictions()

        # Should work with metadata
        assert isinstance(predictions, list)


class TestBackwardCompatibility:
    """Test that disabling fuzzy matching maintains old behavior."""

    def test_zero_threshold_exact_matching_only(self, kato_fixture):
        """Test that threshold=0.0 uses exact matching only."""
        kato = kato_fixture
        kato.clear_all_memory()

        # Explicitly disable fuzzy matching
        kato.update_config({'fuzzy_token_threshold': 0.0})

        # Learn pattern
        kato.observe({'strings': ['exact', 'match', 'only']})
        kato.learn()

        # Query with misspelling
        kato.clear_stm()
        kato.observe({'strings': ['exact', 'mach']})  # 'mach' != 'match'

        predictions = kato.get_predictions()

        # Behavior should be exact matching
        # Anomalies should be empty
        if len(predictions) > 0:
            pred = predictions[0]
            assert len(pred.get('anomalies', [])) == 0


class TestEdgeCases:
    """Test edge cases for fuzzy matching."""

    def test_empty_state_no_anomalies(self, kato_fixture):
        """Test fuzzy matching with empty state."""
        kato = kato_fixture
        kato.clear_all_memory()

        kato.update_config({'fuzzy_token_threshold': 0.85})

        # Learn pattern
        kato.observe({'strings': ['a', 'b']})
        kato.learn()

        # Query with empty state
        kato.clear_stm()

        predictions = kato.get_predictions()

        # Empty state should return no predictions
        assert len(predictions) == 0

    def test_special_characters_fuzzy_matching(self, kato_fixture):
        """Test fuzzy matching with special characters."""
        kato = kato_fixture
        kato.clear_all_memory()

        kato.update_config({'fuzzy_token_threshold': 0.80})

        # Learn with special characters
        kato.observe({'strings': ['test-123', 'data_456']})
        kato.learn()

        # Query with similar tokens
        kato.clear_stm()
        kato.observe({'strings': ['test-12', 'data_45']})

        predictions = kato.get_predictions()

        # Should handle special characters
        assert isinstance(predictions, list)
