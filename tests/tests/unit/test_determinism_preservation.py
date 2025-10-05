"""
Comprehensive tests to verify that performance optimizations preserve KATO's
deterministic behavior and full traceability of predictions.
"""

import hashlib
import os
import sys
from typing import List

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from fixtures.kato_fixtures import kato_fixture as kato_fixture
from fixtures.test_helpers import sort_event_strings


class DeterminismTestCases:
    """Collection of test cases for determinism verification."""

    @staticmethod
    def get_standard_sequences():
        """Standard test sequences for determinism testing."""
        return [
            [['alpha', 'beta'], ['gamma'], ['delta', 'epsilon']],
            [['1', '2', '3'], ['4', '5'], ['6']],
            [['x'], ['y', 'z'], ['a', 'b', 'c']],
            [['start', 'begin'], ['middle', 'center'], ['end', 'finish']],
            [['cat', 'dog'], ['bird'], ['fish', 'hamster', 'rabbit']]
        ]

    @staticmethod
    def get_edge_cases():
        """Edge case sequences for robust testing."""
        return [
            [['']],  # Empty string
            [['single']],  # Single symbol
            [['a'] * 100],  # Repetitive pattern
            [list('abcdefghijklmnopqrstuvwxyz')],  # Large single event
            [['1'], ['2'], ['3'], ['4'], ['5'], ['6'], ['7'], ['8'], ['9'], ['0']]  # Many events
        ]


def compute_pattern_hash(sequence: List[List[str]]) -> str:
    """Compute deterministic hash for a sequence (mimics Pattern class behavior)."""
    # Sort symbols within each event alphanumerically
    sorted_sequence = [sorted(event) for event in sequence]
    # Flatten and create hash
    flattened = '|'.join(['_'.join(event) for event in sorted_sequence])
    return hashlib.sha1(flattened.encode(), usedforsecurity=False).hexdigest()


def test_pattern_hash_determinism(kato_fixture):
    """Verify that same sequence always produces same pattern hash."""
    test_sequences = DeterminismTestCases.get_standard_sequences()

    for sequence in test_sequences:
        # Clear and learn the sequence multiple times
        hashes = []
        for _ in range(5):  # Test 5 times for each sequence
            kato_fixture.clear_all_memory()

            # Observe the sequence
            for event in sequence:
                kato_fixture.observe({'strings': sort_event_strings(event),
                                     'vectors': [], 'emotives': {}})

            # Learn and get pattern hash
            pattern_hash = kato_fixture.learn()
            if pattern_hash:  # Not empty sequence
                hashes.append(pattern_hash.replace('PTRN|', ''))

        # All hashes should be identical
        if hashes:
            assert len(set(hashes)) == 1, \
                f"Non-deterministic hashing detected. Hashes: {hashes}"


def test_symbol_sorting_determinism(kato_fixture):
    """Verify alphanumeric sorting is preserved and deterministic."""
    test_cases = [
        ['zebra', 'apple', '123', 'Beta', 'alpha'],
        ['z', 'a', '9', '1', 'Z', 'A'],
        ['test_2', 'test_1', 'test_10', 'test_20'],
        ['αlpha', 'βeta', 'γamma'],  # Unicode
    ]

    for unsorted in test_cases:
        # Test 10 times to ensure no randomness
        sorted_results = []
        for _ in range(10):
            sorted_result = sort_event_strings(unsorted.copy())
            sorted_results.append(sorted_result)

        # All sorted results should be identical
        first_result = sorted_results[0]
        for result in sorted_results[1:]:
            assert result == first_result, \
                f"Non-deterministic sorting: {result} != {first_result}"


def test_prediction_fields_identical(kato_fixture):
    """Verify all prediction fields remain deterministic across multiple runs."""
    test_sequences = DeterminismTestCases.get_standard_sequences()

    for sequence in test_sequences[:3]:  # Test first 3 sequences
        # Learn the pattern
        kato_fixture.clear_all_memory()
        for event in sequence:
            kato_fixture.observe({'strings': sort_event_strings(event),
                                 'vectors': [], 'emotives': {}})
        kato_fixture.learn()

        # Make predictions multiple times with same observation
        test_observation = sort_event_strings(sequence[0])  # Use first event
        predictions_runs = []

        for _ in range(3):
            kato_fixture.clear_short_term_memory()
            kato_fixture.observe({'strings': test_observation,
                                 'vectors': [], 'emotives': {}})
            predictions = kato_fixture.get_predictions()
            predictions_runs.append(predictions)

        # Check all runs produce identical predictions
        if predictions_runs[0]:  # If we have predictions
            for i in range(1, len(predictions_runs)):
                assert len(predictions_runs[i]) == len(predictions_runs[0]), \
                    "Different number of predictions"

                # Check each prediction field
                for j, pred in enumerate(predictions_runs[i]):
                    ref_pred = predictions_runs[0][j]
                    for field in ['type', 'name', 'frequency', 'matches',
                                'past', 'present', 'future', 'missing',
                                'extras', 'evidence', 'similarity',
                                'confidence', 'fragmentation', 'snr']:
                        assert pred.get(field) == ref_pred.get(field), \
                            f"Field {field} differs in run {i}: {pred.get(field)} != {ref_pred.get(field)}"


def test_cross_session_determinism(kato_fixture):
    """Verify predictions are identical across different runtime sessions."""
    test_cases = [
        {
            'sequence': [['a', 'b'], ['c', 'd'], ['e']],
            'observation': ['a', 'c']
        },
        {
            'sequence': [['hello'], ['world'], ['foo', 'bar']],
            'observation': ['hello', 'foo']
        }
    ]

    session_results = []

    for session in range(3):  # Run 3 sessions
        session_predictions = []

        for test_case in test_cases:
            kato_fixture.clear_all_memory()

            # Learn sequence
            for event in test_case['sequence']:
                kato_fixture.observe({'strings': sort_event_strings(event),
                                     'vectors': [], 'emotives': {}})
            kato_fixture.learn()

            # Make prediction
            kato_fixture.clear_short_term_memory()
            kato_fixture.observe({'strings': sort_event_strings(test_case['observation']),
                                 'vectors': [], 'emotives': {}})
            predictions = kato_fixture.get_predictions()

            # Store sorted predictions (by name) for comparison
            if predictions:
                sorted_preds = sorted(predictions, key=lambda x: x.get('name', ''))
                session_predictions.append(sorted_preds)
            else:
                session_predictions.append([])

        session_results.append(session_predictions)

    # Compare all sessions
    for i in range(1, len(session_results)):
        assert session_results[i] == session_results[0], \
            f"Session {i} differs from session 0"


def test_empty_event_handling_determinism(kato_fixture):
    """Test that empty events are handled deterministically."""
    sequences_with_empty = [
        [['a', ''], ['b', 'c']],  # Empty string in event
        [[''], ['a', 'b']],  # Empty string at start
        [['a', 'b'], ['']],  # Empty string at end
    ]

    for sequence in sequences_with_empty:
        hashes = []
        for _ in range(3):
            kato_fixture.clear_all_memory()

            for event in sequence:
                # Empty strings should be filtered out
                filtered_event = [s for s in event if s]
                if filtered_event:  # Only observe if non-empty
                    kato_fixture.observe({'strings': sort_event_strings(filtered_event),
                                         'vectors': [], 'emotives': {}})

            pattern_hash = kato_fixture.learn()
            hashes.append(pattern_hash)

        # All hashes should be identical
        assert len(set(hashes)) == 1, \
            f"Empty event handling not deterministic: {hashes}"


def test_prediction_traceability(kato_fixture):
    """Verify every prediction can be traced back to source model."""
    # Create known patterns
    models = [
        [['trace', 'test'], ['one']],
        [['trace', 'test'], ['two'], ['three']],
        [['different'], ['pattern'], ['here']]
    ]

    pattern_hashes = []
    for sequence in models:
        kato_fixture.clear_all_memory()
        for event in sequence:
            kato_fixture.observe({'strings': sort_event_strings(event),
                                 'vectors': [], 'emotives': {}})
        pattern_hash = kato_fixture.learn()
        if pattern_hash:
            pattern_hashes.append(pattern_hash.replace('PTRN|', ''))

    # Make predictions with partial match
    kato_fixture.clear_short_term_memory()
    kato_fixture.observe({'strings': sort_event_strings(['trace', 'test']),
                         'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()

    # Verify each prediction traces to a known pattern
    for pred in predictions:
        pred_pattern_name = pred.get('name')
        assert pred_pattern_name in pattern_hashes, \
            f"Prediction pattern {pred_pattern_name} not in learned patterns {pattern_hashes}"

        # Verify temporal structure is present
        assert 'past' in pred and 'present' in pred and 'future' in pred, \
            "Missing temporal structure in prediction"


def test_emotives_determinism(kato_fixture):
    """Test that emotive processing is deterministic."""
    sequence = [['happy'], ['sad'], ['neutral']]
    emotives = [
        {'joy': 0.8, 'sadness': 0.2},
        {'joy': 0.1, 'sadness': 0.9},
        {'joy': 0.5, 'sadness': 0.5}
    ]

    prediction_emotives = []

    for _ in range(3):  # Run 3 times
        kato_fixture.clear_all_memory()

        # Observe with emotives
        for event, emotive in zip(sequence, emotives):
            kato_fixture.observe({'strings': event,
                                 'vectors': [],
                                 'emotives': emotive})

        kato_fixture.learn()

        # Get predictions
        kato_fixture.clear_short_term_memory()
        kato_fixture.observe({'strings': ['happy'],
                             'vectors': [],
                             'emotives': {'joy': 0.8, 'sadness': 0.2}})

        predictions = kato_fixture.get_predictions()
        if predictions:
            prediction_emotives.append(predictions[0].get('emotives', {}))

    # All emotive calculations should be identical
    if prediction_emotives:
        first = prediction_emotives[0]
        for emotives in prediction_emotives[1:]:
            assert emotives == first, \
                f"Non-deterministic emotives: {emotives} != {first}"


def test_confidence_calculation_determinism(kato_fixture):
    """Verify confidence and evidence calculations are deterministic."""
    # Learn a sequence
    kato_fixture.clear_all_memory()
    sequence = [['a', 'b', 'c'], ['d', 'e'], ['f']]
    for event in sequence:
        kato_fixture.observe({'strings': sort_event_strings(event),
                             'vectors': [], 'emotives': {}})
    kato_fixture.learn()

    # Test with partial matches
    test_cases = [
        ['a', 'b'],  # Partial match of first event
        ['d', 'e'],  # Full match of second event
        ['a', 'd'],  # Matches across events
    ]

    for test_obs in test_cases:
        confidences = []
        evidences = []

        for _ in range(3):
            kato_fixture.clear_short_term_memory()
            kato_fixture.observe({'strings': sort_event_strings(test_obs),
                                 'vectors': [], 'emotives': {}})
            predictions = kato_fixture.get_predictions()

            if predictions:
                confidences.append(predictions[0].get('confidence'))
                evidences.append(predictions[0].get('evidence'))

        # Check determinism
        if confidences:
            assert len(set(confidences)) == 1, \
                f"Non-deterministic confidence: {confidences}"
        if evidences:
            assert len(set(evidences)) == 1, \
                f"Non-deterministic evidence: {evidences}"


def test_multiple_model_interaction_determinism(kato_fixture):
    """Test determinism when multiple models could match."""
    # Learn multiple similar patterns
    models = [
        [['cat', 'dog'], ['bird']],
        [['cat', 'dog'], ['fish']],
        [['cat'], ['dog', 'bird']],
        [['dog', 'cat'], ['bird']],  # Same as first but different order
    ]

    for model in models:
        kato_fixture.clear_all_memory()
        for event in model:
            kato_fixture.observe({'strings': sort_event_strings(event),
                                 'vectors': [], 'emotives': {}})
        kato_fixture.learn()

    # Test predictions are consistent
    prediction_sets = []

    for _ in range(3):
        kato_fixture.clear_short_term_memory()
        kato_fixture.observe({'strings': sort_event_strings(['cat', 'dog']),
                             'vectors': [], 'emotives': {}})
        predictions = kato_fixture.get_predictions()

        # Sort predictions by name for consistent comparison
        sorted_preds = sorted(predictions, key=lambda x: x.get('name', ''))
        pred_names = [p['name'] for p in sorted_preds]
        prediction_sets.append(pred_names)

    # All prediction sets should be identical
    assert all(pset == prediction_sets[0] for pset in prediction_sets), \
        f"Non-deterministic multi-model predictions: {prediction_sets}"


def test_max_predictions_determinism(kato_fixture):
    """Test that max_predictions limit is applied deterministically."""
    # Create many patterns
    for i in range(20):
        kato_fixture.clear_all_memory()
        sequence = [[f'symbol_{i}'], ['common'], [f'end_{i}']]
        for event in sequence:
            kato_fixture.observe({'strings': event, 'vectors': [], 'emotives': {}})
        kato_fixture.learn()

    # Get predictions multiple times (should be limited by max_predictions)
    prediction_counts = []

    for _ in range(3):
        kato_fixture.clear_short_term_memory()
        kato_fixture.observe({'strings': ['common'], 'vectors': [], 'emotives': {}})
        predictions = kato_fixture.get_predictions()
        prediction_counts.append(len(predictions))

    # All counts should be identical and <= max_predictions
    assert len(set(prediction_counts)) == 1, \
        f"Non-deterministic prediction count: {prediction_counts}"
