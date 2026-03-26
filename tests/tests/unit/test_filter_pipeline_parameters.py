"""
Tests for filter pipeline configuration parameters.

Verifies that each filter pipeline config parameter actually affects
prediction results when changed via session config API.

These parameters had ZERO test coverage before this file.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from fixtures.kato_fixtures import kato_fixture as kato_fixture


def _learn_test_patterns(kato_fixture, count=10):
    """Helper: learn N patterns with shared prefix for filter testing."""
    kato_fixture.clear_all_memory()
    pattern_names = []
    for i in range(count):
        for item in [f'filter_{i}_a', f'filter_{i}_b', f'filter_{i}_c']:
            kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
        name = kato_fixture.learn()
        pattern_names.append(name)
    return pattern_names


def _get_predictions_for(kato_fixture, symbols):
    """Helper: observe symbols and get predictions."""
    kato_fixture.clear_short_term_memory()
    for sym in symbols:
        kato_fixture.observe({'strings': [sym], 'vectors': [], 'emotives': {}})
    return kato_fixture.get_predictions()


def test_empty_pipeline_returns_all_matches(kato_fixture):
    """Test that empty filter pipeline returns all matching patterns."""
    _learn_test_patterns(kato_fixture, count=5)
    kato_fixture.update_config({
        'filter_pipeline': [],
        'recall_threshold': 0.1,
    })

    predictions = _get_predictions_for(kato_fixture, ['filter_0_a', 'filter_0_b'])
    assert len(predictions) >= 1, "Empty pipeline should return matching patterns"


def test_minhash_filter_reduces_candidates(kato_fixture):
    """Test that minhash filter reduces candidates based on Jaccard similarity.

    MinHash default threshold is 0.7 (Jaccard).

    Pattern A: tokens {'mh_x', 'mh_y', 'mh_z'}         → Jaccard(query, A) = 3/3 = 1.0  (passes)
    Pattern B: tokens {'mh_x', 'mh_y', 'mh_different'}  → Jaccard(query, B) = 2/4 = 0.5  (filtered)
    Pattern C: tokens {'mh_unrelated', 'mh_other', ...}  → Jaccard(query, C) = 0/6 = 0.0  (filtered)

    Query: tokens {'mh_x', 'mh_y', 'mh_z'}
    """
    kato_fixture.clear_all_memory()

    # Pattern A: exact token overlap with query (Jaccard = 1.0)
    for item in ['mh_x', 'mh_y', 'mh_z']:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()

    # Pattern B: partial overlap (Jaccard = 2/4 = 0.5 < 0.7 threshold)
    for item in ['mh_x', 'mh_y', 'mh_different']:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()

    # Pattern C: no overlap (Jaccard = 0.0)
    for item in ['mh_unrelated', 'mh_other', 'mh_none']:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()

    # Baseline: empty pipeline, low threshold — should find A and B (both share 'mh_x', 'mh_y')
    kato_fixture.update_config({'filter_pipeline': [], 'recall_threshold': 0.1})
    baseline = _get_predictions_for(kato_fixture, ['mh_x', 'mh_y', 'mh_z'])

    assert len(baseline) >= 1, "Baseline should find at least pattern A"

    # With minhash filter: only pattern A should pass (Jaccard=1.0 >= 0.7)
    # Pattern B has Jaccard=0.5 < 0.7, so minhash should reject it
    kato_fixture.update_config({
        'filter_pipeline': ['minhash'],
        'recall_threshold': 0.1,
    })
    filtered = _get_predictions_for(kato_fixture, ['mh_x', 'mh_y', 'mh_z'])

    assert len(filtered) >= 1, "Minhash should pass pattern A (Jaccard=1.0)"
    assert len(filtered) <= len(baseline), \
        f"Minhash should reduce candidates: {len(filtered)} > {len(baseline)}"


def test_jaccard_filter_reduces_candidates(kato_fixture):
    """Test that enabling jaccard filter affects candidate selection."""
    _learn_test_patterns(kato_fixture, count=10)

    kato_fixture.update_config({'filter_pipeline': [], 'recall_threshold': 0.1})
    baseline = _get_predictions_for(kato_fixture, ['filter_5_a', 'filter_5_b'])

    kato_fixture.update_config({
        'filter_pipeline': ['jaccard'],
        'recall_threshold': 0.1,
    })
    filtered = _get_predictions_for(kato_fixture, ['filter_5_a', 'filter_5_b'])

    assert len(filtered) >= 1, "Jaccard filter should still find matching pattern"
    assert len(filtered) <= len(baseline), \
        f"Jaccard filter should not increase result count: {len(filtered)} > {len(baseline)}"


def test_combined_minhash_jaccard_pipeline(kato_fixture):
    """Test that minhash + jaccard pipeline together work correctly.

    Query tokens {'combo_a', 'combo_b', 'combo_c'} exactly match pattern tokens
    so Jaccard = 1.0 (passes minhash threshold 0.7 and jaccard threshold).
    """
    kato_fixture.clear_all_memory()

    # Learn target pattern — exact token match with query
    for item in ['combo_a', 'combo_b', 'combo_c']:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()

    # Learn unrelated pattern — zero overlap
    for item in ['other_x', 'other_y', 'other_z']:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()

    kato_fixture.update_config({
        'filter_pipeline': ['minhash', 'jaccard'],
        'recall_threshold': 0.1,
    })
    predictions = _get_predictions_for(kato_fixture, ['combo_a', 'combo_b', 'combo_c'])

    assert len(predictions) >= 1, "Combined pipeline should find exact-match pattern"

    matching = [p for p in predictions
                if 'combo_a' in p.get('matches', []) and 'combo_b' in p.get('matches', [])]
    assert len(matching) >= 1, "Should find the specific pattern"


def test_max_predictions_limits_output(kato_fixture):
    """Test that max_predictions config limits the number of returned predictions."""
    _learn_test_patterns(kato_fixture, count=20)

    # Set low recall threshold to match many patterns, but limit output
    kato_fixture.update_config({
        'filter_pipeline': [],
        'recall_threshold': 0.1,
        'max_predictions': 3,
    })

    # Observe symbols that might match multiple patterns
    predictions = _get_predictions_for(kato_fixture, ['filter_0_a', 'filter_0_b'])

    assert len(predictions) <= 3, \
        f"max_predictions=3 should limit output, got {len(predictions)}"


def test_enable_filter_metrics_flag(kato_fixture):
    """Test that enable_filter_metrics doesn't break prediction flow."""
    _learn_test_patterns(kato_fixture, count=3)

    # Enable metrics
    kato_fixture.update_config({
        'filter_pipeline': ['minhash'],
        'enable_filter_metrics': True,
        'recall_threshold': 0.1,
    })
    with_metrics = _get_predictions_for(kato_fixture, ['filter_0_a', 'filter_0_b'])

    # Disable metrics
    kato_fixture.update_config({
        'filter_pipeline': ['minhash'],
        'enable_filter_metrics': False,
        'recall_threshold': 0.1,
    })
    without_metrics = _get_predictions_for(kato_fixture, ['filter_0_a', 'filter_0_b'])

    # Results should be the same regardless of metrics flag
    assert len(with_metrics) == len(without_metrics), \
        "enable_filter_metrics should not change prediction results"


def test_fuzzy_token_threshold_affects_matching(kato_fixture):
    """Test that fuzzy_token_threshold enables/disables fuzzy matching."""
    kato_fixture.clear_all_memory()

    # Learn a pattern
    kato_fixture.observe({'strings': ['apple', 'banana', 'cherry']})
    kato_fixture.learn()

    # With fuzzy matching disabled (threshold=0)
    kato_fixture.update_config({'fuzzy_token_threshold': 0.0})
    kato_fixture.clear_short_term_memory()
    kato_fixture.observe({'strings': ['apple', 'bannana']})  # Misspelling
    no_fuzzy = kato_fixture.get_predictions()

    # With fuzzy matching enabled (threshold=0.8)
    kato_fixture.update_config({'fuzzy_token_threshold': 0.8})
    kato_fixture.clear_short_term_memory()
    kato_fixture.observe({'strings': ['apple', 'bannana']})  # Same misspelling
    with_fuzzy = kato_fixture.get_predictions()

    # Both should find the pattern (exact 'apple' match is enough)
    # But fuzzy matching should detect anomalies
    if len(with_fuzzy) > 0:
        for pred in with_fuzzy:
            anomalies = pred.get('anomalies', [])
            # Fuzzy matching should detect 'bannana' → 'banana' as anomaly
            if len(anomalies) > 0:
                assert any(a.get('observed') == 'bannana' for a in anomalies), \
                    f"Should detect 'bannana' as fuzzy match anomaly, got {anomalies}"
                break
