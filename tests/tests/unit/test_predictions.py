"""
Unit tests for KATO prediction behaviors.

Tests prediction-specific behaviors NOT covered by other test files:
- No predictions initially (empty state)
- Frequency tracking across re-learning
- Entropy and normalized entropy calculations
- Emotives in predictions (storage + retrieval)
- Multi-pattern disambiguation
- Confidence score ranges
- Prediction type field

Temporal field structure (past/present/future/missing/extras) is tested
in test_prediction_fields.py. Metrics (TF-IDF, Bayesian, potential) are
tested in test_prediction_metrics_v3.py. Recall threshold filtering is
tested in test_recall_threshold.py.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from fixtures.kato_fixtures import kato_fixture as kato_fixture


def test_no_predictions_initially(kato_fixture):
    """Test that there are no predictions with empty state."""
    kato_fixture.clear_all_memory()
    predictions = kato_fixture.get_predictions()
    assert predictions == []


def test_prediction_frequency(kato_fixture):
    """Test that frequency increases with repeated learning of the same pattern."""
    kato_fixture.clear_all_memory()

    sequence = ['freq', 'test']
    for _ in range(3):
        for item in sequence:
            kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
        kato_fixture.learn()

    kato_fixture.observe({'strings': ['freq'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['test'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()

    found_high_freq = False
    for pred in predictions:
        if pred.get('frequency', 0) >= 3:
            found_high_freq = True
            break
    assert found_high_freq, \
        f"Should have prediction with frequency >= 3, got frequencies: {[p.get('frequency') for p in predictions]}"


def test_prediction_entropy(kato_fixture):
    """Test entropy values are present and valid in predictions."""
    kato_fixture.clear_all_memory()

    for item in ['ent_a', 'ent_b', 'ent_c']:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()

    kato_fixture.observe({'strings': ['ent_a'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['ent_b'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()

    assert len(predictions) > 0
    for pred in predictions:
        assert 'entropy' in pred
        assert isinstance(pred['entropy'], (int, float))
        assert pred['entropy'] >= 0


def test_prediction_normalized_entropy(kato_fixture):
    """Test normalized entropy and global normalized entropy fields."""
    kato_fixture.clear_all_memory()

    for item in ['norm_a', 'norm_b', 'norm_c']:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()

    kato_fixture.observe({'strings': ['norm_a'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['norm_b'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()

    for pred in predictions:
        assert 'normalized_entropy' in pred
        assert 'global_normalized_entropy' in pred
        assert isinstance(pred['normalized_entropy'], (int, float))
        assert isinstance(pred['global_normalized_entropy'], (int, float))


def test_prediction_with_emotives(kato_fixture):
    """Test that emotives are stored in Redis and averaged in predictions."""
    kato_fixture.clear_all_memory()

    sequence = [
        ('happy', {'joy': 0.9, 'energy': 0.8}),
        ('sad', {'joy': 0.1, 'energy': 0.2}),
        ('neutral', {'joy': 0.5, 'energy': 0.5})
    ]

    for string, emotives in sequence:
        kato_fixture.observe({'strings': [string], 'vectors': [], 'emotives': emotives})
    pattern_name = kato_fixture.learn()
    assert pattern_name is not None

    # Verify Redis storage
    redis_emotives = kato_fixture.get_redis_emotives(pattern_name)
    assert redis_emotives is not None, "Emotives should be stored in Redis"
    assert len(redis_emotives) == 3
    assert redis_emotives[0] == {'joy': 0.9, 'energy': 0.8}
    assert redis_emotives[1] == {'joy': 0.1, 'energy': 0.2}
    assert redis_emotives[2] == {'joy': 0.5, 'energy': 0.5}

    # Verify emotives appear in predictions
    kato_fixture.clear_short_term_memory()
    kato_fixture.observe({'strings': ['happy'], 'vectors': [], 'emotives': {'joy': 0.9, 'energy': 0.8}})
    kato_fixture.observe({'strings': ['sad'], 'vectors': [], 'emotives': {'joy': 0.1, 'energy': 0.2}})
    predictions = kato_fixture.get_predictions()

    assert len(predictions) > 0
    matching = [p for p in predictions if p.get('frequency', 0) > 0]
    assert len(matching) > 0

    for pred in matching:
        assert 'emotives' in pred
        assert isinstance(pred['emotives'], dict)
        assert 'joy' in pred['emotives']
        assert 'energy' in pred['emotives']


def test_multiple_pattern_predictions(kato_fixture):
    """Test predictions when multiple patterns are learned with shared prefix."""
    kato_fixture.clear_all_memory()

    sequences = [
        ['shared', 'branch_a', 'end_a'],
        ['shared', 'branch_b', 'end_b'],
        ['shared', 'branch_c', 'end_c']
    ]

    for seq in sequences:
        for item in seq:
            kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
        kato_fixture.learn()

    # Observe 'shared' + 'branch_a' — should match all 3 patterns (they all start with 'shared')
    kato_fixture.observe({'strings': ['shared'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['branch_a'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()

    assert len(predictions) >= 3, f"Should have predictions for all 3 patterns, got {len(predictions)}"

    # Pattern names should be unique
    names = {p.get('name', '') for p in predictions}
    assert len(names) >= 3, "Each pattern should have a unique name"


def test_prediction_confidence_scores(kato_fixture):
    """Test that confidence scores are valid (0-1 range)."""
    kato_fixture.clear_all_memory()

    for item in ['conf_a', 'conf_b', 'conf_c']:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()

    kato_fixture.observe({'strings': ['conf_a'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['conf_b'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()

    for pred in predictions:
        assert 'confidence' in pred
        assert 0 <= pred['confidence'] <= 1, \
            f"Confidence should be in [0,1], got {pred['confidence']}"


def test_prediction_type_field(kato_fixture):
    """Test that predictions have a valid type field."""
    kato_fixture.clear_all_memory()

    for item in ['type_a', 'type_b']:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()

    kato_fixture.observe({'strings': ['type_a'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['type_b'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()

    for pred in predictions:
        if 'type' in pred:
            assert pred['type'] in ['prototypical', 'episodic', 'abstract']
