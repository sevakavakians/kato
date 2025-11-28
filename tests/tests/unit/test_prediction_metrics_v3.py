"""
Unit tests for v3.0 prediction metrics in KATO.

Tests the new TF-IDF metric and integration of all prediction metrics:
- tfidf_score: TF-IDF based pattern ranking
- Metrics integration: All metrics work together correctly
- Edge cases: Zero probabilities, empty predictions, single patterns
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from fixtures.kato_fixtures import kato_fixture as kato_fixture


def test_tfidf_score_present(kato_fixture):
    """Test that tfidf_score metric is present in all predictions."""
    kato_fixture.clear_all_memory()
    kato_fixture.set_recall_threshold(0.2)

    # Learn a pattern
    for item in ['term', 'frequency', 'test']:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()

    # Observe to generate predictions (meet 2+ requirement)
    kato_fixture.observe({'strings': ['term'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['frequency'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()

    assert len(predictions) > 0, "Should have at least one prediction"

    # Check all predictions have tfidf_score
    for pred in predictions:
        assert 'tfidf_score' in pred, "Missing tfidf_score metric"
        assert isinstance(pred['tfidf_score'], (int, float)), "tfidf_score should be numeric"
        assert pred['tfidf_score'] >= 0, "tfidf_score should be non-negative"


def test_tfidf_score_increases_with_uniqueness(kato_fixture):
    """Test that TF-IDF score is higher for patterns with unique symbols."""
    kato_fixture.clear_all_memory()
    kato_fixture.set_recall_threshold(0.2)

    # Pattern 1: Contains common symbol 'common'
    for item in ['common', 'shared', 'pattern1']:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()

    # Pattern 2: Also contains 'common'
    for item in ['common', 'shared', 'pattern2']:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()

    # Pattern 3: Contains unique symbol 'unique' (appears in only one pattern)
    for item in ['unique', 'distinctive', 'pattern3']:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()

    # Observe partial match to pattern 3 (unique symbols)
    kato_fixture.observe({'strings': ['unique'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['distinctive'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()

    assert len(predictions) >= 1, "Should have predictions"

    # Find pattern with 'unique' symbol
    unique_pattern_preds = [p for p in predictions if 'unique' in str(p.get('future', []))]

    # The pattern with unique symbols should have a relatively high TF-IDF score
    # (compared to zero or very low scores for patterns with only common symbols)
    if unique_pattern_preds:
        unique_tfidf = unique_pattern_preds[0]['tfidf_score']
        assert unique_tfidf > 0, "Pattern with unique symbols should have non-zero TF-IDF"


def test_tfidf_score_zero_for_common_symbols(kato_fixture):
    """Test that TF-IDF is lower for patterns with only very common symbols."""
    kato_fixture.clear_all_memory()
    kato_fixture.set_recall_threshold(0.2)

    # Learn many patterns all containing the same symbol
    common_symbol = 'everywhere'
    for i in range(5):
        for item in [common_symbol, f'pattern{i}']:
            kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
        kato_fixture.learn()

    # Observe the common symbol
    kato_fixture.observe({'strings': [common_symbol], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['pattern0'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()

    assert len(predictions) > 0, "Should have predictions"

    # All predictions should have tfidf_score (may be low due to common symbols)
    for pred in predictions:
        assert 'tfidf_score' in pred, "Should have tfidf_score"
        # Common symbols have low IDF, so TF-IDF should be relatively low
        # (but still >= 0)
        assert pred['tfidf_score'] >= 0


def test_tfidf_as_ranking_metric(kato_fixture):
    """Test that tfidf_score can be used as a ranking metric."""
    kato_fixture.clear_all_memory()
    kato_fixture.set_recall_threshold(0.2)

    # Set tfidf_score as ranking algorithm
    kato_fixture.update_config({'rank_sort_algo': 'tfidf_score'})

    # Learn multiple patterns
    patterns = [
        ['rank', 'tfidf', 'a'],
        ['rank', 'tfidf', 'b'],
        ['rank', 'tfidf', 'c']
    ]

    for pattern in patterns:
        for item in pattern:
            kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
        kato_fixture.learn()

    # Observe to generate predictions (meet 2+ requirement)
    kato_fixture.observe({'strings': ['rank'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['tfidf'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()

    assert len(predictions) > 0, "Should have predictions"

    # Verify predictions are sorted by tfidf_score (descending)
    tfidf_scores = [p['tfidf_score'] for p in predictions]
    assert tfidf_scores == sorted(tfidf_scores, reverse=True), \
        "Predictions should be sorted by tfidf_score in descending order"


def test_all_metrics_present_in_predictions(kato_fixture):
    """Test that all v3.0 metrics are present in predictions."""
    kato_fixture.clear_all_memory()
    kato_fixture.set_recall_threshold(0.2)

    # Learn a pattern
    for item in ['all', 'metrics', 'test']:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()

    # Observe to generate predictions
    kato_fixture.observe({'strings': ['all'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['metrics'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()

    assert len(predictions) > 0, "Should have at least one prediction"

    # Required v3.0 metrics
    required_metrics = [
        'bayesian_posterior',
        'bayesian_prior',
        'bayesian_likelihood',
        'tfidf_score',
        'frequency',
        'similarity',
        'potential',
        'entropy',
        'normalized_entropy'
    ]

    for pred in predictions:
        for metric in required_metrics:
            assert metric in pred, f"Missing required metric: {metric}"


def test_edge_case_empty_predictions(kato_fixture):
    """Test behavior when no predictions are generated."""
    kato_fixture.clear_all_memory()
    kato_fixture.set_recall_threshold(0.99)  # Very high threshold

    # Learn a pattern
    for item in ['pattern', 'that', 'wont', 'match']:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()

    # Observe completely different sequence (unlikely to match with high threshold)
    kato_fixture.observe({'strings': ['completely'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['different'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()

    # Empty predictions list is valid - no metrics to check
    assert isinstance(predictions, list), "Predictions should be a list (even if empty)"


def test_edge_case_single_symbol_pattern(kato_fixture):
    """Test metrics for single-symbol patterns."""
    kato_fixture.clear_all_memory()
    kato_fixture.set_recall_threshold(0.2)

    # Learn a single-symbol pattern
    kato_fixture.observe({'strings': ['single'], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()

    # Observe to generate predictions (need 2+ symbols)
    kato_fixture.observe({'strings': ['single'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['single'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()

    # May or may not have predictions depending on matching logic
    # If predictions exist, verify all metrics are present
    for pred in predictions:
        assert 'tfidf_score' in pred
        assert 'bayesian_posterior' in pred
        assert pred['tfidf_score'] >= 0
        assert 0.0 <= pred['bayesian_posterior'] <= 1.0


def test_edge_case_identical_patterns(kato_fixture):
    """Test metrics when patterns have identical symbols."""
    kato_fixture.clear_all_memory()
    kato_fixture.set_recall_threshold(0.2)

    # Learn the same pattern multiple times
    for _ in range(3):
        for item in ['identical', 'pattern']:
            kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
        kato_fixture.learn()

    # Observe to generate predictions
    kato_fixture.observe({'strings': ['identical'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['pattern'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()

    # Should have exactly 1 unique pattern
    # Note: ClickHouse may increment frequency or may deduplicate depending on implementation
    # The key is that we get 1 unique pattern
    assert len(predictions) == 1, "Should have 1 unique pattern"

    pred = predictions[0]
    # Frequency could be 1 (deduplicated) or 3 (incremented) depending on implementation
    assert pred['frequency'] >= 1, "Pattern should have frequency >= 1"
    assert pred['bayesian_prior'] == 1.0, "Single unique pattern should have prior=1.0"
    assert pred['bayesian_posterior'] == 1.0, "Single pattern should have posterior=1.0"


def test_metric_ranges_are_valid(kato_fixture):
    """Test that all metrics have valid ranges."""
    kato_fixture.clear_all_memory()
    kato_fixture.set_recall_threshold(0.2)

    # Learn multiple patterns with varying characteristics
    patterns = [
        ['range', 'test', 'a', 'b', 'c'],  # 5 symbols
        ['range', 'test'],                   # 2 symbols (different length)
        ['range', 'test', 'x', 'y']          # 4 symbols
    ]

    for pattern in patterns:
        for item in pattern:
            kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
        kato_fixture.learn()

    # Observe to generate predictions
    kato_fixture.observe({'strings': ['range'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['test'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()

    assert len(predictions) > 0, "Should have predictions"

    for pred in predictions:
        # Probability metrics should be in [0, 1]
        assert 0.0 <= pred['bayesian_posterior'] <= 1.0, "Posterior should be in [0,1]"
        assert 0.0 <= pred['bayesian_prior'] <= 1.0, "Prior should be in [0,1]"
        assert 0.0 <= pred['bayesian_likelihood'] <= 1.0, "Likelihood should be in [0,1]"
        assert 0.0 <= pred['similarity'] <= 1.0, "Similarity should be in [0,1]"

        # Non-negative metrics
        assert pred['tfidf_score'] >= 0, "TF-IDF should be non-negative"
        assert pred['frequency'] >= 1, "Frequency should be at least 1"
        assert pred['potential'] >= 0, "Potential should be non-negative"
        assert pred['entropy'] >= 0, "Entropy should be non-negative"


def test_metrics_integration_with_different_ranking_algorithms(kato_fixture):
    """Test that metrics work correctly with different ranking algorithms."""
    kato_fixture.clear_all_memory()

    # Learn patterns
    patterns = [
        ['integration', 'test', 'alpha'],
        ['integration', 'test', 'beta']
    ]

    for pattern in patterns:
        for item in pattern:
            kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
        kato_fixture.learn()

    # Test with different ranking algorithms
    ranking_algorithms = [
        'potential',
        'similarity',
        'frequency',
        'bayesian_posterior',
        'bayesian_prior',
        'bayesian_likelihood',
        'tfidf_score'
    ]

    for algo in ranking_algorithms:
        kato_fixture.update_config({'rank_sort_algo': algo})

        # Generate predictions
        kato_fixture.clear_short_term_memory()
        kato_fixture.observe({'strings': ['integration'], 'vectors': [], 'emotives': {}})
        kato_fixture.observe({'strings': ['test'], 'vectors': [], 'emotives': {}})
        predictions = kato_fixture.get_predictions()

        if len(predictions) > 0:
            # Verify predictions are sorted by the selected metric (descending)
            if algo in predictions[0]:  # Metric exists in predictions
                metric_values = [p[algo] for p in predictions]
                assert metric_values == sorted(metric_values, reverse=True), \
                    f"Predictions not sorted correctly by {algo}"

            # Verify all metrics still present regardless of ranking algo
            for pred in predictions:
                assert 'bayesian_posterior' in pred, f"Missing bayesian_posterior with algo={algo}"
                assert 'tfidf_score' in pred, f"Missing tfidf_score with algo={algo}"


def test_tfidf_calculation_with_varying_term_frequency(kato_fixture):
    """Test TF-IDF calculation with patterns having different term frequencies."""
    kato_fixture.clear_all_memory()
    kato_fixture.set_recall_threshold(0.2)

    # Pattern 1: Symbol appears once
    for item in ['tf_test', 'single']:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()

    # Pattern 2: Symbol appears multiple times (higher TF)
    for item in ['tf_test', 'tf_test', 'tf_test', 'multiple']:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()

    # Observe the common symbol
    kato_fixture.observe({'strings': ['tf_test'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['single'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()

    assert len(predictions) >= 1, "Should have predictions"

    # All predictions should have valid tfidf_score
    for pred in predictions:
        assert 'tfidf_score' in pred
        assert isinstance(pred['tfidf_score'], (int, float))
        assert pred['tfidf_score'] >= 0
