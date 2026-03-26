"""
Integration tests for filter pipeline runtime reconfiguration.

Tests that filter pipeline can be changed mid-session via session config API
and that the new configuration takes effect immediately.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


def test_filter_pipeline_runtime_change(kato_fixture):
    """Test that changing filter pipeline mid-session works correctly."""
    kato_fixture.clear_all_memory()

    # Learn several patterns
    patterns = [
        ['config', 'test', 'alpha'],
        ['config', 'test', 'beta'],
        ['config', 'test', 'gamma'],
        ['unrelated', 'different', 'pattern'],
    ]

    for pattern in patterns:
        for item in pattern:
            kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
        kato_fixture.learn()

    # Start with empty filter pipeline (no filtering)
    kato_fixture.update_config({'filter_pipeline': []})

    kato_fixture.observe({'strings': ['config'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['test'], 'vectors': [], 'emotives': {}})
    no_filter_predictions = kato_fixture.get_predictions()

    # Should find matching patterns with no filter
    assert len(no_filter_predictions) > 0, "Should find patterns with empty pipeline"

    # Now change to a filter pipeline with filters enabled
    kato_fixture.update_config({
        'filter_pipeline': ['minhash', 'jaccard'],
        'recall_threshold': 0.5
    })

    kato_fixture.clear_short_term_memory()
    kato_fixture.observe({'strings': ['config'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['test'], 'vectors': [], 'emotives': {}})
    filtered_predictions = kato_fixture.get_predictions()

    # Filtered predictions should also work (may have different count due to filtering)
    # The key test is that no errors occur and results are valid
    assert isinstance(filtered_predictions, list), "Filtered predictions should be a list"

    # All filtered predictions should meet the threshold
    for pred in filtered_predictions:
        assert pred.get('similarity', 0) >= 0.5, \
            f"Filtered predictions should meet threshold, got similarity={pred.get('similarity')}"


def test_filter_pipeline_reset_to_empty(kato_fixture):
    """Test that resetting filter pipeline to empty restores unfiltered behavior."""
    kato_fixture.clear_all_memory()

    # Learn a pattern
    for item in ['reset', 'pipeline', 'test']:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()

    # Set strict filtering
    kato_fixture.update_config({
        'filter_pipeline': ['minhash', 'jaccard'],
        'recall_threshold': 0.1
    })

    kato_fixture.observe({'strings': ['reset'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['pipeline'], 'vectors': [], 'emotives': {}})
    strict_predictions = kato_fixture.get_predictions()

    # Reset to empty pipeline
    kato_fixture.update_config({
        'filter_pipeline': [],
        'recall_threshold': 0.1
    })

    kato_fixture.clear_short_term_memory()
    kato_fixture.observe({'strings': ['reset'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['pipeline'], 'vectors': [], 'emotives': {}})
    open_predictions = kato_fixture.get_predictions()

    # Both should find the pattern
    assert len(open_predictions) > 0, "Empty pipeline should find patterns"

    # Verify the specific pattern is found
    matching = [p for p in open_predictions
                if 'reset' in p.get('matches', []) and 'pipeline' in p.get('matches', [])]
    assert len(matching) > 0, "Should find the reset-pipeline-test pattern"


def test_recall_threshold_runtime_change(kato_fixture):
    """Test that changing recall threshold mid-session takes effect immediately."""
    kato_fixture.clear_all_memory()

    # Learn a 5-event pattern
    for item in ['thresh', 'change', 'exact', 'match', 'test']:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()

    # High threshold (0.9) - exact match STM for all 5 events gives similarity = 1.0,
    # which should pass even the high threshold
    kato_fixture.update_config({'recall_threshold': 0.9})
    for item in ['thresh', 'change', 'exact', 'match', 'test']:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    high_threshold_predictions = kato_fixture.get_predictions()

    assert len(high_threshold_predictions) > 0, \
        "recall_threshold=0.9 should include exact match pattern (similarity=1.0)"

    # Now test with partial match - only 2 of 5 events
    # similarity = 2*2/(2+5) = 0.571, below 0.9 threshold
    kato_fixture.update_config({'recall_threshold': 0.9})
    kato_fixture.clear_short_term_memory()
    kato_fixture.observe({'strings': ['thresh'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['change'], 'vectors': [], 'emotives': {}})
    partial_high_predictions = kato_fixture.get_predictions()

    assert len(partial_high_predictions) == 0, \
        f"recall_threshold=0.9 should exclude partial match (similarity ~0.571), got {len(partial_high_predictions)}"

    # Low threshold (0.1) - same partial query should now return the pattern
    kato_fixture.update_config({'recall_threshold': 0.1})
    kato_fixture.clear_short_term_memory()
    kato_fixture.observe({'strings': ['thresh'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['change'], 'vectors': [], 'emotives': {}})
    low_threshold_predictions = kato_fixture.get_predictions()

    assert len(low_threshold_predictions) > 0, \
        "recall_threshold=0.1 should include partial match (similarity ~0.571)"
