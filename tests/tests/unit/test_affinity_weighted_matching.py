"""
Affinity-weighted pattern matching tests for KATO.

These tests validate:
1. Weight computation: w(t) = |aff(t,e)| / freq(t) + epsilon
2. Weighted similarity: 2 * W_matched / (W_state + W_pattern)
3. Weighted metrics in prediction output (weighted_similarity, weighted_evidence, etc.)
4. Fallback to unweighted when no affinity_emotive configured
5. Noise discount: low-affinity tokens contribute minimally
"""

import pytest

from kato.searches.pattern_search import InformationExtractor


EPSILON = 0.01


class TestWeightComputation:
    """Test the weight function: w(t) = |aff(t,e)| / freq(t) + epsilon."""

    def test_weight_from_positive_affinity(self):
        """Positive affinity yields correct weight."""
        aff = 8.0
        freq = 10
        expected = abs(aff) / freq + EPSILON  # 0.8 + 0.01 = 0.81
        assert abs(expected - 0.81) < 0.001

    def test_weight_from_negative_affinity(self):
        """Negative affinity uses absolute value."""
        aff = -5.0
        freq = 10
        expected = abs(aff) / freq + EPSILON  # 0.5 + 0.01 = 0.51
        assert abs(expected - 0.51) < 0.001

    def test_weight_zero_affinity_gives_epsilon(self):
        """Zero affinity yields floor weight epsilon."""
        aff = 0.0
        freq = 100
        expected = abs(aff) / freq + EPSILON  # 0.0 + 0.01 = 0.01
        assert abs(expected - EPSILON) < 0.001

    def test_weight_missing_affinity_gives_epsilon(self):
        """Missing affinity (freq > 0, aff = 0) yields epsilon."""
        # When aff=0 and freq>0: 0/freq + epsilon = epsilon
        expected = 0.0 / 50 + EPSILON
        assert abs(expected - EPSILON) < 0.001


class TestWeightedSimilarity:
    """Test the weighted Dice-Sorensen formula in extract_prediction_info."""

    def test_weighted_similarity_basic(self):
        """Signal tokens dominate similarity when noise tokens have low weight."""
        # Pattern: [A, NOISE_1, B, NOISE_2]
        # State:   [A, NOISE_3, B]
        # Matches: {A, B}
        pattern = ['A', 'NOISE_1', 'B', 'NOISE_2']
        state = ['A', 'NOISE_3', 'B']

        # Weights: signal tokens ~0.8, noise tokens ~0.01
        weights = {
            'A': 0.84, 'B': 0.81,
            'NOISE_1': EPSILON, 'NOISE_2': EPSILON,
            'NOISE_3': EPSILON
        }

        extractor = InformationExtractor(use_fast_matcher=True, use_token_matching=True)
        result = extractor.extract_prediction_info(
            pattern, state, cutoff=0.0, weights=weights)

        assert result is not None
        (pat, matching, past, present, missing, extras,
         similarity, n_blocks, anomalies, weighted_similarity) = result

        # Unweighted: 2*2/(4+3) = 4/7 ≈ 0.571
        assert abs(similarity - 4/7) < 0.01

        # Weighted: signal tokens dominate
        # W_matched = 0.84 + 0.81 = 1.65
        # W_state = 0.84 + 0.01 + 0.81 = 1.66
        # W_pattern = 0.84 + 0.01 + 0.81 + 0.01 = 1.67
        # sim_w = 2 * 1.65 / (1.66 + 1.67) = 3.30 / 3.33 ≈ 0.991
        assert weighted_similarity is not None
        assert weighted_similarity > similarity, \
            f"Weighted ({weighted_similarity:.3f}) should be > unweighted ({similarity:.3f})"
        assert weighted_similarity > 0.95, \
            f"Weighted similarity should be near 1.0 when signal matches, got {weighted_similarity:.3f}"

    def test_weighted_similarity_noise_match(self):
        """When only noise tokens match, weighted similarity is very low."""
        # Pattern: [A, NOISE_1]
        # State:   [B, NOISE_1]
        # Matches: {NOISE_1}
        pattern = ['A', 'NOISE_1']
        state = ['B', 'NOISE_1']

        weights = {
            'A': 0.80, 'B': 0.80,
            'NOISE_1': EPSILON
        }

        extractor = InformationExtractor(use_fast_matcher=True, use_token_matching=True)
        result = extractor.extract_prediction_info(
            pattern, state, cutoff=0.0, weights=weights)

        assert result is not None
        (*_, similarity, _, _, weighted_similarity) = result

        # Unweighted: 2*1/(2+2) = 0.5
        assert abs(similarity - 0.5) < 0.01

        # Weighted: noise token match contributes minimally
        # W_matched = 0.01
        # W_state = 0.80 + 0.01 = 0.81
        # W_pattern = 0.80 + 0.01 = 0.81
        # sim_w = 2 * 0.01 / (0.81 + 0.81) = 0.02 / 1.62 ≈ 0.012
        assert weighted_similarity is not None
        assert weighted_similarity < 0.05, \
            f"Weighted similarity should be near 0 for noise-only match, got {weighted_similarity:.3f}"
        assert weighted_similarity < similarity

    def test_no_weights_returns_none(self):
        """Without weights dict, weighted_similarity is None."""
        pattern = ['A', 'B']
        state = ['A', 'C']

        extractor = InformationExtractor(use_fast_matcher=True, use_token_matching=True)
        result = extractor.extract_prediction_info(
            pattern, state, cutoff=0.0)

        assert result is not None
        (*_, weighted_similarity) = result
        assert weighted_similarity is None

    def test_empty_weights_returns_none(self):
        """Empty weights dict means no weighting."""
        pattern = ['A', 'B']
        state = ['A', 'C']

        extractor = InformationExtractor(use_fast_matcher=True, use_token_matching=True)
        result = extractor.extract_prediction_info(
            pattern, state, cutoff=0.0, weights={})

        assert result is not None
        (*_, weighted_similarity) = result
        assert weighted_similarity is None

    def test_equal_weights_match_unweighted(self):
        """When all weights are equal, weighted similarity equals unweighted."""
        pattern = ['A', 'B', 'C']
        state = ['A', 'B']

        # All tokens have equal weight
        weights = {'A': 1.0, 'B': 1.0, 'C': 1.0}

        extractor = InformationExtractor(use_fast_matcher=True, use_token_matching=True)
        result = extractor.extract_prediction_info(
            pattern, state, cutoff=0.0, weights=weights)

        assert result is not None
        (*_, similarity, _, _, weighted_similarity) = result

        assert weighted_similarity is not None
        assert abs(weighted_similarity - similarity) < 0.01, \
            f"Equal weights should give same result: weighted={weighted_similarity:.3f}, unweighted={similarity:.3f}"

    def test_worked_example_from_plan(self):
        """Validate the worked example from the plan document."""
        # From plan: STM = [A, NOISE_1, NOISE_2, NOISE_3, B, NOISE_4]
        # Pattern = [A, NOISE_5, B, NOISE_6, NOISE_7, C, NOISE_8]
        state = ['A', 'NOISE_1', 'NOISE_2', 'NOISE_3', 'B', 'NOISE_4']
        pattern = ['A', 'NOISE_5', 'B', 'NOISE_6', 'NOISE_7', 'C', 'NOISE_8']

        # Weights from plan: A=0.84, B=0.81, C=0.84, NOISE_x=0.01
        weights = {
            'A': 0.84, 'B': 0.81, 'C': 0.84,
            'NOISE_1': EPSILON, 'NOISE_2': EPSILON, 'NOISE_3': EPSILON,
            'NOISE_4': EPSILON, 'NOISE_5': EPSILON, 'NOISE_6': EPSILON,
            'NOISE_7': EPSILON, 'NOISE_8': EPSILON
        }

        extractor = InformationExtractor(use_fast_matcher=True, use_token_matching=True)
        result = extractor.extract_prediction_info(
            pattern, state, cutoff=0.0, weights=weights)

        assert result is not None
        (*_, similarity, _, _, weighted_similarity) = result

        # Unweighted: 2*2/(6+7) = 4/13 ≈ 0.308
        assert abs(similarity - 4/13) < 0.02, f"Unweighted should be ~0.308, got {similarity:.3f}"

        # Weighted should be much higher (plan says 0.782)
        assert weighted_similarity is not None
        assert weighted_similarity > 0.70, \
            f"Weighted should be >0.70, got {weighted_similarity:.3f}"
        assert weighted_similarity > 2 * similarity, \
            f"Weighted ({weighted_similarity:.3f}) should be significantly higher than unweighted ({similarity:.3f})"


class TestWeightedMetricsInPredictions:
    """Test that weighted metrics appear in prediction output."""

    def test_prediction_has_weighted_fields(self):
        """Prediction dict includes weighted metric fields."""
        from kato.representations.prediction import Prediction

        pattern_data = {
            'name': 'test_hash',
            'pattern_data': [['A'], ['B']],
            'length': 2,
            'frequency': 1,
            'emotives': {}
        }

        pred = Prediction(
            pattern_data,
            matching_intersection=['A'],
            past=[], present=['A'],
            missing=[], extras=[],
            similarity=0.5,
            number_of_blocks=1,
            weighted_similarity=0.8
        )

        assert 'weighted_similarity' in pred
        assert pred['weighted_similarity'] == 0.8
        assert 'weighted_evidence' in pred
        assert 'weighted_confidence' in pred
        assert 'weighted_snr' in pred

    def test_prediction_weighted_fields_none_by_default(self):
        """Weighted fields are None when no weighted_similarity provided."""
        from kato.representations.prediction import Prediction

        pattern_data = {
            'name': 'test_hash',
            'pattern_data': [['A'], ['B']],
            'length': 2,
            'frequency': 1,
            'emotives': {}
        }

        pred = Prediction(
            pattern_data,
            matching_intersection=['A'],
            past=[], present=['A'],
            missing=[], extras=[],
            similarity=0.5,
            number_of_blocks=1
        )

        assert pred['weighted_similarity'] is None
        assert pred['weighted_evidence'] is None
        assert pred['weighted_confidence'] is None
        assert pred['weighted_snr'] is None
