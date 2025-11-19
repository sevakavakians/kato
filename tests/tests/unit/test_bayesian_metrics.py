"""
Unit tests for Bayesian probability metrics in KATO predictions.

Tests that Bayesian posterior, prior, and likelihood calculations follow proper
probabilistic rules and Bayes' theorem.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from fixtures.kato_fixtures import kato_fixture as kato_fixture


def test_bayesian_metrics_present(kato_fixture):
    """Test that Bayesian metrics are present in all predictions."""
    kato_fixture.clear_all_memory()
    kato_fixture.set_recall_threshold(0.2)

    # Learn a pattern
    sequence = ['a', 'b', 'c']
    for item in sequence:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()

    # Observe to generate predictions (meet 2+ requirement)
    kato_fixture.observe({'strings': ['a'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['b'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()

    assert len(predictions) > 0, "Should have at least one prediction"

    # Check all predictions have Bayesian metrics
    for pred in predictions:
        assert 'bayesian_posterior' in pred, "Missing bayesian_posterior"
        assert 'bayesian_prior' in pred, "Missing bayesian_prior"
        assert 'bayesian_likelihood' in pred, "Missing bayesian_likelihood"

        # Check they're floats
        assert isinstance(pred['bayesian_posterior'], float), "posterior should be float"
        assert isinstance(pred['bayesian_prior'], float), "prior should be float"
        assert isinstance(pred['bayesian_likelihood'], float), "likelihood should be float"


def test_posteriors_sum_to_one(kato_fixture):
    """Test that posterior probabilities sum to 1.0 across the ensemble."""
    kato_fixture.clear_all_memory()
    kato_fixture.set_recall_threshold(0.2)

    # Learn multiple patterns with different frequencies
    patterns = [
        ['a', 'b', 'c'],
        ['a', 'b', 'd'],
        ['a', 'b', 'e']
    ]

    for pattern in patterns:
        for item in pattern:
            kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
        kato_fixture.learn()

    # Observe partial sequence (meet 2+ requirement)
    kato_fixture.observe({'strings': ['a'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['b'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()

    assert len(predictions) > 0, "Should have multiple predictions"

    # Sum all posteriors
    posterior_sum = sum(p['bayesian_posterior'] for p in predictions)

    # Should sum to 1.0 (within floating point tolerance)
    assert abs(posterior_sum - 1.0) < 1e-6, \
        f"Posteriors should sum to 1.0, got {posterior_sum}"


def test_bayesian_prior_reflects_frequency(kato_fixture):
    """Test that prior probabilities reflect pattern frequencies."""
    kato_fixture.clear_all_memory()
    kato_fixture.set_recall_threshold(0.2)

    # Learn same pattern twice (frequency = 2)
    for _ in range(2):
        for item in ['x', 'y', 'z']:
            kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
        kato_fixture.learn()

    # Learn different pattern once (frequency = 1)
    for item in ['x', 'y', 'w']:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()

    # Observe to generate predictions (meet 2+ requirement)
    kato_fixture.observe({'strings': ['x'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['y'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()

    assert len(predictions) == 2, "Should have exactly 2 predictions"

    # Pattern with frequency=2 should have prior = 2/3
    # Pattern with frequency=1 should have prior = 1/3
    priors = sorted([p['bayesian_prior'] for p in predictions], reverse=True)

    expected_high_prior = 2.0 / 3.0
    expected_low_prior = 1.0 / 3.0

    assert abs(priors[0] - expected_high_prior) < 1e-6, \
        f"High frequency prior should be {expected_high_prior}, got {priors[0]}"
    assert abs(priors[1] - expected_low_prior) < 1e-6, \
        f"Low frequency prior should be {expected_low_prior}, got {priors[1]}"


def test_bayesian_likelihood_equals_similarity(kato_fixture):
    """Test that likelihood equals the similarity score."""
    kato_fixture.clear_all_memory()
    kato_fixture.set_recall_threshold(0.2)

    # Learn a pattern
    for item in ['p', 'q', 'r']:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()

    # Observe to generate predictions (meet 2+ requirement)
    kato_fixture.observe({'strings': ['p'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['q'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()

    assert len(predictions) > 0, "Should have at least one prediction"

    for pred in predictions:
        # Likelihood should equal similarity (P(obs|pattern) = similarity)
        assert abs(pred['bayesian_likelihood'] - pred['similarity']) < 1e-9, \
            f"Likelihood {pred['bayesian_likelihood']} should equal similarity {pred['similarity']}"


def test_bayes_theorem_identity(kato_fixture):
    """Test that Bayes' theorem identity holds: P(pattern|obs) = P(obs|pattern) × P(pattern) / P(obs)."""
    kato_fixture.clear_all_memory()
    kato_fixture.set_recall_threshold(0.2)

    # Learn multiple patterns
    patterns = [
        ['alpha', 'beta', 'gamma'],
        ['alpha', 'beta', 'delta']
    ]

    for pattern in patterns:
        for item in pattern:
            kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
        kato_fixture.learn()

    # Observe to generate predictions (meet 2+ requirement)
    kato_fixture.observe({'strings': ['alpha'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['beta'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()

    assert len(predictions) > 0, "Should have predictions"

    # Calculate P(obs) = Σ P(obs|pattern) × P(pattern)
    evidence = sum(p['bayesian_likelihood'] * p['bayesian_prior'] for p in predictions)

    # Verify Bayes' theorem for each prediction
    for pred in predictions:
        prior = pred['bayesian_prior']
        likelihood = pred['bayesian_likelihood']
        posterior = pred['bayesian_posterior']

        # P(pattern|obs) should equal P(obs|pattern) × P(pattern) / P(obs)
        expected_posterior = (likelihood * prior) / evidence if evidence > 0 else 0.0

        assert abs(posterior - expected_posterior) < 1e-9, \
            f"Bayes' theorem violated: posterior={posterior}, expected={expected_posterior}"


def test_high_frequency_high_similarity_gets_highest_posterior(kato_fixture):
    """Test that patterns with both high frequency and high similarity get highest posterior."""
    kato_fixture.clear_all_memory()
    kato_fixture.set_recall_threshold(0.1)  # Lower threshold to catch partial matches

    # Learn pattern A multiple times (high frequency)
    for _ in range(3):
        for item in ['m', 'n', 'o']:
            kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
        kato_fixture.learn()

    # Learn pattern B once (low frequency)
    for item in ['m', 'n', 'p']:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()

    # Observe exact match to pattern A (high similarity for A, also high for B since ['m','n'] match)
    kato_fixture.observe({'strings': ['m'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['n'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()

    assert len(predictions) > 0, "Should have predictions"

    # Find pattern with highest posterior
    max_posterior_pred = max(predictions, key=lambda p: p['bayesian_posterior'])

    # The high-frequency pattern should have the highest posterior
    # (assuming similar similarity scores)
    assert max_posterior_pred['frequency'] >= 2, \
        f"Highest posterior pattern should have high frequency, got {max_posterior_pred['frequency']}"


def test_zero_similarity_gives_zero_posterior(kato_fixture):
    """Test that zero similarity results in zero posterior (edge case)."""
    kato_fixture.clear_all_memory()
    kato_fixture.set_recall_threshold(0.0)  # Allow all patterns including zero similarity

    # Learn a pattern
    for item in ['u', 'v', 'w']:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()

    # Observe completely different sequence (should get 0 similarity if threshold is 0)
    kato_fixture.observe({'strings': ['completely'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['different'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()

    # Check if any predictions have zero similarity
    zero_sim_preds = [p for p in predictions if p['similarity'] == 0.0]

    for pred in zero_sim_preds:
        # Zero likelihood (similarity) should give zero posterior
        assert pred['bayesian_posterior'] == 0.0, \
            f"Zero similarity should give zero posterior, got {pred['bayesian_posterior']}"


def test_single_pattern_gets_posterior_one(kato_fixture):
    """Test that a single pattern gets posterior probability of 1.0."""
    kato_fixture.clear_all_memory()
    kato_fixture.set_recall_threshold(0.2)

    # Learn only one pattern
    for item in ['one', 'pattern', 'only']:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()

    # Observe to generate predictions (meet 2+ requirement)
    kato_fixture.observe({'strings': ['one'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['pattern'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()

    assert len(predictions) == 1, "Should have exactly one prediction"

    # Single pattern should have posterior = 1.0 (it's the only explanation)
    posterior = predictions[0]['bayesian_posterior']
    assert abs(posterior - 1.0) < 1e-6, \
        f"Single pattern should have posterior=1.0, got {posterior}"


def test_bayesian_posterior_as_ranking_metric(kato_fixture):
    """Test that bayesian_posterior can be used as a ranking metric."""
    kato_fixture.clear_all_memory()
    kato_fixture.set_recall_threshold(0.2)

    # Set bayesian_posterior as ranking algorithm
    kato_fixture.set_rank_sort_algo('bayesian_posterior')

    # Learn multiple patterns
    patterns = [
        ['rank', 'test', 'a'],
        ['rank', 'test', 'b'],
        ['rank', 'test', 'c']
    ]

    for pattern in patterns:
        for item in pattern:
            kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
        kato_fixture.learn()

    # Observe to generate predictions (meet 2+ requirement)
    kato_fixture.observe({'strings': ['rank'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['test'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()

    assert len(predictions) > 0, "Should have predictions"

    # Verify predictions are sorted by bayesian_posterior (descending)
    posteriors = [p['bayesian_posterior'] for p in predictions]
    assert posteriors == sorted(posteriors, reverse=True), \
        "Predictions should be sorted by bayesian_posterior in descending order"
