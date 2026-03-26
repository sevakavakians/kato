"""
Consolidated recall threshold tests.

Tests recall_threshold behavior across the full range (0.0-1.0) with:
- Parametrized threshold filtering
- Missing/extra symbols affecting similarity
- Multimodal data (strings + vectors + emotives)
- Boundary similarity conditions
- Runtime threshold updates
- Scaling with many patterns
- Invalid value rejection

Similarity formula: 2*M / (len(pattern) + len(state))
where M = number of matching elements found by difflib SequenceMatcher.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from fixtures.kato_fixtures import kato_fixture as kato_fixture
from fixtures.test_helpers import sort_event_strings


# --- Parametrized threshold filtering ---

@pytest.mark.parametrize("threshold,expect_match", [
    (0.0, True),    # No filtering — all matches returned
    (0.1, True),    # Default — very permissive
    (0.3, True),    # Moderate — 2/3 match (sim=0.8) passes
    (0.5, True),    # Balanced — 2/3 match (sim=0.8) passes
    (0.7, True),    # Restrictive — 2/3 match (sim=0.8) passes
    (0.9, False),   # Very restrictive — 2/3 match (sim=0.8) < 0.9
])
def test_threshold_filters_by_similarity(kato_fixture, threshold, expect_match):
    """Test that recall_threshold correctly filters predictions by similarity.

    Pattern: 3 events × 1 symbol each ['alpha', 'beta', 'gamma']
    STM: 2 events ['alpha', 'beta'] → similarity = 2*2/(2+3) = 0.8
    """
    kato_fixture.clear_all_memory()
    kato_fixture.set_recall_threshold(threshold)

    # Learn a 3-event pattern
    for item in ['alpha', 'beta', 'gamma']:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()

    # Observe 2 of 3 events (similarity = 0.8)
    kato_fixture.observe({'strings': ['alpha'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['beta'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()

    if expect_match:
        assert len(predictions) > 0, \
            f"threshold={threshold} should include pattern with similarity ~0.8"
        for pred in predictions:
            assert pred.get('similarity', 0) >= threshold, \
                f"Returned prediction should meet threshold {threshold}"
    else:
        assert len(predictions) == 0, \
            f"threshold={threshold} should exclude pattern with similarity ~0.8"


def test_threshold_exact_match_passes_any_threshold(kato_fixture):
    """Test that exact match (similarity=1.0) passes even threshold=1.0."""
    kato_fixture.clear_all_memory()
    kato_fixture.set_recall_threshold(1.0)

    # Learn and observe the exact same pattern
    pattern = ['perfect', 'match', 'test']
    for item in pattern:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()

    for item in pattern:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()

    assert len(predictions) >= 1, "Exact match should pass threshold=1.0"
    perfect = [p for p in predictions if p.get('similarity', 0) == 1.0]
    assert len(perfect) >= 1, "Should have at least one prediction with similarity=1.0"


def test_threshold_unrelated_observation_zero_similarity(kato_fixture):
    """Test that completely unrelated observations produce zero-similarity predictions at threshold=0.0.

    KATO has a special case: threshold=0.0 includes patterns with similarity=0.0
    (all symbols missing, all observed symbols are extras). This is correct behavior —
    threshold=0.0 means "return everything."
    """
    kato_fixture.clear_all_memory()
    kato_fixture.set_recall_threshold(0.0)  # Most permissive — includes zero-similarity

    for item in ['known', 'pattern', 'here']:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()

    # Observe symbols that don't appear in any pattern
    kato_fixture.observe({'strings': ['unknown1'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['unknown2'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()

    # With threshold=0.0, KATO returns patterns with similarity=0.0 (all missing, all extras)
    if len(predictions) > 0:
        for pred in predictions:
            assert pred.get('similarity', 0) == 0.0, \
                f"Unrelated observation should have similarity=0.0, got {pred.get('similarity')}"
            assert pred.get('matches', ['non-empty']) == [], \
                f"Unrelated observation should have no matches, got {pred.get('matches')}"

    # With threshold > 0, unrelated observations should produce NO predictions
    kato_fixture.set_recall_threshold(0.1)
    kato_fixture.clear_short_term_memory()
    kato_fixture.observe({'strings': ['unknown3'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['unknown4'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()

    assert len(predictions) == 0, \
        "Unrelated observation with threshold > 0 should produce no predictions"


# --- Missing and extra symbols ---

def test_threshold_with_missing_symbols(kato_fixture):
    """Test how missing symbols affect similarity with different thresholds.

    Pattern: 2 events with 3 symbols each (9 total symbols)
    Observations vary in how many symbols are omitted.
    """
    kato_fixture.clear_all_memory()

    # Learn multi-symbol event pattern
    kato_fixture.observe({'strings': sort_event_strings(['alpha', 'beta', 'gamma']), 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': sort_event_strings(['delta', 'epsilon', 'zeta']), 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': sort_event_strings(['eta', 'theta', 'iota']), 'vectors': [], 'emotives': {}})
    kato_fixture.learn()

    test_cases = [
        # (observation, threshold, should_match)
        ([['alpha', 'beta', 'gamma'], ['delta', 'epsilon']], 0.7, True),   # Missing 1 symbol
        ([['alpha', 'beta', 'gamma'], ['delta', 'epsilon']], 0.8, False),  # Threshold too high
        ([['alpha'], ['delta']], 0.3, True),                                # Missing many symbols
        ([['alpha'], ['delta']], 0.7, False),                               # Too many missing
    ]

    for observation, threshold, should_match in test_cases:
        kato_fixture.set_recall_threshold(threshold)
        kato_fixture.clear_short_term_memory()

        for event in observation:
            kato_fixture.observe({'strings': sort_event_strings(event), 'vectors': [], 'emotives': {}})

        predictions = kato_fixture.get_predictions()

        if should_match:
            assert len(predictions) > 0, \
                f"Should match with threshold {threshold}, observation has {sum(len(e) for e in observation)} symbols"
            for pred in predictions:
                missing = pred.get('missing', [])
                assert len(missing) > 0, "Should detect missing symbols"
        else:
            assert len(predictions) == 0, \
                f"Should NOT match with threshold {threshold}"


def test_threshold_with_extra_symbols(kato_fixture):
    """Test how extra symbols affect similarity with different thresholds."""
    kato_fixture.clear_all_memory()

    kato_fixture.observe({'strings': sort_event_strings(['simple1', 'simple2']), 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': sort_event_strings(['simple3', 'simple4']), 'vectors': [], 'emotives': {}})
    kato_fixture.learn()

    test_cases = [
        ([['simple1', 'simple2', 'extra1'], ['simple3', 'simple4']], 0.7, True),
        ([['simple1', 'simple2', 'extra1', 'extra2'], ['simple3', 'simple4', 'extra3']], 0.5, True),
        ([['simple1', 'extra1'], ['simple3', 'extra2']], 0.3, True),
    ]

    for observation, threshold, should_match in test_cases:
        kato_fixture.set_recall_threshold(threshold)
        kato_fixture.clear_short_term_memory()

        for event in observation:
            kato_fixture.observe({'strings': sort_event_strings(event), 'vectors': [], 'emotives': {}})

        predictions = kato_fixture.get_predictions()

        if should_match:
            assert len(predictions) > 0, f"Should match with threshold {threshold} despite extras"
            for pred in predictions:
                extras = pred.get('extras', [])
                assert len(extras) > 0, "Should detect extra symbols"


# --- Boundary conditions ---

def test_threshold_boundary_at_actual_similarity(kato_fixture):
    """Test threshold behavior at the actual computed similarity boundary.

    Pattern: 4 events × 1 symbol ['a', 'b', 'c', 'd']
    STM: 2 events ['a', 'b'] → similarity = 2*2/(2+4) = 0.667
    """
    kato_fixture.clear_all_memory()

    for item in ['bound_a', 'bound_b', 'bound_c', 'bound_d']:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()

    boundary_tests = [
        (0.6, True),    # Below similarity 0.667
        (0.65, True),   # Still below 0.667
        (0.7, False),   # Above similarity 0.667
    ]

    for threshold, expect_match in boundary_tests:
        kato_fixture.set_recall_threshold(threshold)
        kato_fixture.clear_short_term_memory()

        kato_fixture.observe({'strings': ['bound_a'], 'vectors': [], 'emotives': {}})
        kato_fixture.observe({'strings': ['bound_b'], 'vectors': [], 'emotives': {}})
        predictions = kato_fixture.get_predictions()

        if expect_match:
            assert len(predictions) > 0, \
                f"threshold={threshold} should include pattern (similarity ~0.667)"
        else:
            assert len(predictions) == 0, \
                f"threshold={threshold} should exclude pattern (similarity ~0.667)"


def test_invalid_threshold_values(kato_fixture):
    """Test that invalid threshold values are rejected."""
    with pytest.raises(ValueError):
        kato_fixture.set_recall_threshold(-0.1)

    with pytest.raises(ValueError):
        kato_fixture.set_recall_threshold(1.5)

    with pytest.raises((ValueError, TypeError)):
        kato_fixture.set_recall_threshold(float('nan'))

    # Valid boundary values should not raise
    kato_fixture.set_recall_threshold(0.0)
    kato_fixture.set_recall_threshold(1.0)


# --- Runtime updates ---

def test_threshold_runtime_update(kato_fixture):
    """Test that changing threshold at runtime immediately affects predictions."""
    kato_fixture.clear_all_memory()

    # Learn 3 patterns with varying overlap to query
    patterns = [
        ['runtime', 'update', 'exact'],     # Will match 3/3 (sim=1.0)
        ['runtime', 'update', 'different'],  # Will match 2/3 (sim=0.8)
        ['totally', 'unrelated', 'stuff'],   # Will match 0/3 (sim=0.0)
    ]
    for pat in patterns:
        for item in pat:
            kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
        kato_fixture.learn()

    # Low threshold — should find 2 matching patterns
    kato_fixture.set_recall_threshold(0.1)
    for item in ['runtime', 'update', 'exact']:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    low_predictions = kato_fixture.get_predictions()

    # High threshold — should find only the exact match
    kato_fixture.set_recall_threshold(0.9)
    kato_fixture.clear_short_term_memory()
    for item in ['runtime', 'update', 'exact']:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    high_predictions = kato_fixture.get_predictions()

    assert len(low_predictions) >= len(high_predictions), \
        f"Low threshold ({len(low_predictions)}) should return >= high threshold ({len(high_predictions)})"
    assert len(low_predictions) > 0, "Low threshold should find matches"
    assert len(high_predictions) > 0, "Exact match should pass even high threshold"


# --- Multimodal ---

def test_threshold_multimodal(kato_fixture):
    """Test threshold with multimodal data (strings + vectors + emotives)."""
    kato_fixture.clear_all_memory()

    kato_fixture.observe({
        'strings': sort_event_strings(['multi1', 'modal1']),
        'vectors': [[1.0, 0.0, 0.0]],
        'emotives': {'arousal': 0.8, 'valence': 0.6}
    })
    kato_fixture.observe({
        'strings': sort_event_strings(['multi2', 'modal2']),
        'vectors': [[0.0, 1.0, 0.0]],
        'emotives': {'arousal': 0.3, 'valence': 0.7}
    })
    kato_fixture.learn()

    # Partial match — observe with missing strings from each event
    # Similarity = 2*4/(4+6) = 0.8 (difflib ratio with 4 matched tokens)
    test_cases = [
        (0.2, True),
        (0.5, True),
        (0.8, True),   # Boundary: similarity=0.8 passes threshold=0.8 (>= comparison)
        (0.85, False), # Above similarity: should filter out
    ]

    for threshold, expect_predictions in test_cases:
        kato_fixture.set_recall_threshold(threshold)
        kato_fixture.clear_short_term_memory()

        kato_fixture.observe({
            'strings': sort_event_strings(['multi1']),
            'vectors': [[1.0, 0.0, 0.0]],
            'emotives': {'arousal': 0.8}
        })
        kato_fixture.observe({
            'strings': sort_event_strings(['multi2']),
            'vectors': [[0.0, 1.0, 0.0]],
            'emotives': {'arousal': 0.3}
        })
        predictions = kato_fixture.get_predictions()

        if expect_predictions:
            assert len(predictions) > 0, f"Should have predictions with threshold {threshold}"
        else:
            assert len(predictions) == 0, f"Should have no predictions with threshold {threshold}"


# --- Scaling ---

def test_threshold_scaling_with_many_patterns(kato_fixture):
    """Test that higher thresholds reduce prediction count with many patterns."""
    kato_fixture.clear_all_memory()

    # Learn 20 distinct patterns
    for i in range(20):
        for item in [f'model_{i}_a', f'model_{i}_b', f'model_{i}_c']:
            kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
        kato_fixture.learn()

    # Observe 2/3 of one specific pattern (sim=0.8 for that pattern, 0 for others)
    observation = ['model_5_a', 'model_5_b']

    prediction_counts = []
    for threshold in [0.1, 0.3, 0.5, 0.7]:
        kato_fixture.set_recall_threshold(threshold)
        kato_fixture.clear_short_term_memory()

        for item in observation:
            kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
        predictions = kato_fixture.get_predictions()
        prediction_counts.append(len(predictions))

    # Higher thresholds should not increase prediction count
    for i in range(1, len(prediction_counts)):
        assert prediction_counts[i] <= prediction_counts[i-1], \
            f"Higher threshold should not increase predictions: {prediction_counts}"


# --- Long sequences ---

def test_threshold_long_sequence_similarity_decay(kato_fixture):
    """Test that observing fewer events of a long pattern reduces similarity."""
    kato_fixture.clear_all_memory()

    # Learn a 10-event pattern
    long_pattern = [f'long_{i}' for i in range(10)]
    for item in long_pattern:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()

    kato_fixture.set_recall_threshold(0.1)

    # Observe 2/10 events → sim = 2*2/(2+10) = 0.333
    kato_fixture.observe({'strings': ['long_0'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['long_1'], 'vectors': [], 'emotives': {}})
    predictions_2 = kato_fixture.get_predictions()
    assert len(predictions_2) > 0, "2/10 match should produce predictions at threshold 0.1"

    # Observe 5/10 events → sim = 2*5/(5+10) = 0.667
    kato_fixture.clear_short_term_memory()
    for i in range(5):
        kato_fixture.observe({'strings': [long_pattern[i]], 'vectors': [], 'emotives': {}})
    predictions_5 = kato_fixture.get_predictions()
    assert len(predictions_5) > 0, "5/10 match should produce predictions"

    # The 5/10 observation should have higher similarity than 2/10
    sim_2 = predictions_2[0].get('similarity', 0)
    sim_5 = predictions_5[0].get('similarity', 0)
    assert sim_5 > sim_2, \
        f"5/10 match (sim={sim_5}) should have higher similarity than 2/10 (sim={sim_2})"
