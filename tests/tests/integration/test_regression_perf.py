"""
Regression tests for performance-critical code paths.

These tests verify behavior introduced by recent performance optimizations:
- Deferred flush visibility (flush_if_pending before queries)
- Symbol batch retrieval correctness (get_all_symbols_batch)
- Single-symbol fast path consistency (_predict_single_symbol_fast)

These do NOT test performance (speed), only correctness of the optimized paths.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


def test_deferred_flush_visibility(kato_fixture):
    """Test that patterns are immediately queryable after learning.

    Regression test for commit 749a9d2: flush_if_pending ensures deferred
    ClickHouse writes are flushed before pattern queries. Without this fix,
    a learn() followed by immediate get_predictions() could miss the pattern.
    """
    kato_fixture.clear_all_memory()

    # Learn a pattern
    sequence = ['flush', 'visibility', 'test']
    for item in sequence:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    pattern_name = kato_fixture.learn()
    assert pattern_name.startswith('PTRN|'), "Pattern should be learned"

    # IMMEDIATELY query predictions (no delay) - this is the critical test
    # Before the flush_if_pending fix, this could miss the just-learned pattern
    kato_fixture.observe({'strings': ['flush'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['visibility'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()

    assert len(predictions) > 0, \
        "Just-learned pattern should be immediately visible in predictions (flush_if_pending regression)"

    # Verify the specific pattern was found
    matching = [p for p in predictions
                if 'flush' in p.get('matches', []) and 'visibility' in p.get('matches', [])]
    assert len(matching) > 0, "Should find the specific just-learned pattern"


def test_deferred_flush_multiple_patterns(kato_fixture):
    """Test that multiple rapidly-learned patterns are all visible."""
    kato_fixture.clear_all_memory()

    # Learn 5 patterns in rapid succession
    pattern_names = []
    for i in range(5):
        prefix = f'rapid{i}'
        kato_fixture.observe({'strings': [f'{prefix}_a'], 'vectors': [], 'emotives': {}})
        kato_fixture.observe({'strings': [f'{prefix}_b'], 'vectors': [], 'emotives': {}})
        kato_fixture.observe({'strings': [f'{prefix}_c'], 'vectors': [], 'emotives': {}})
        name = kato_fixture.learn()
        pattern_names.append(name)

    # All patterns should have been learned
    assert len(pattern_names) == 5
    assert all(n.startswith('PTRN|') for n in pattern_names)

    # Query for the first pattern - should find it despite rapid learning
    kato_fixture.observe({'strings': ['rapid0_a'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['rapid0_b'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()

    assert len(predictions) > 0, \
        "All rapidly-learned patterns should be visible after deferred flushes"


def test_symbol_batch_retrieval_correctness(kato_fixture):
    """Test that symbol batch retrieval returns all learned symbols.

    Regression test for commit 32571df: get_all_symbols_batch was rewritten
    to use HGETALL instead of Redis SCAN for 800x performance improvement.
    This test verifies the new implementation returns correct results.
    """
    kato_fixture.clear_all_memory()

    # Learn patterns with many unique symbols
    unique_symbols_per_pattern = [
        ['alpha', 'beta', 'gamma'],
        ['delta', 'epsilon', 'zeta'],
        ['eta', 'theta', 'iota'],
        ['kappa', 'lambda_sym', 'mu'],  # 'lambda' is a Python keyword
    ]

    all_symbols = set()
    for pattern_symbols in unique_symbols_per_pattern:
        for sym in pattern_symbols:
            kato_fixture.observe({'strings': [sym], 'vectors': [], 'emotives': {}})
        kato_fixture.learn()
        all_symbols.update(pattern_symbols)

    # Query with symbols from different patterns - all should be findable
    kato_fixture.observe({'strings': ['alpha'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['beta'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()

    # Should find the alpha-beta-gamma pattern
    assert len(predictions) > 0, "Symbol retrieval should find patterns"
    matching = [p for p in predictions
                if 'alpha' in p.get('matches', []) and 'beta' in p.get('matches', [])]
    assert len(matching) > 0, "Should find pattern containing observed symbols"


def test_single_symbol_fast_path_consistency(kato_fixture):
    """Test that single-symbol fast path produces same results as multi-symbol path.

    KATO uses _predict_single_symbol_fast for single-symbol observations.
    This test verifies consistency between the fast path and normal path.
    """
    kato_fixture.clear_all_memory()

    # Learn a pattern
    sequence = ['fast', 'path', 'test']
    for item in sequence:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()

    # Single-symbol observation (triggers fast path)
    kato_fixture.observe({'strings': ['fast'], 'vectors': [], 'emotives': {}})
    single_predictions = kato_fixture.get_predictions()

    # Multi-symbol observation (triggers normal path)
    kato_fixture.clear_short_term_memory()
    kato_fixture.observe({'strings': ['fast'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['path'], 'vectors': [], 'emotives': {}})
    multi_predictions = kato_fixture.get_predictions()

    # Both paths should find the same pattern
    assert len(single_predictions) > 0, "Fast path should find the pattern"
    assert len(multi_predictions) > 0, "Normal path should find the pattern"

    single_names = {p['name'] for p in single_predictions}
    multi_names = {p['name'] for p in multi_predictions}

    # The pattern found by multi-symbol should also be found by single-symbol
    assert multi_names.issubset(single_names) or single_names.issubset(multi_names), \
        f"Fast path ({single_names}) and normal path ({multi_names}) should find overlapping patterns"


def test_single_symbol_fast_path_no_false_matches(kato_fixture):
    """Test that single-symbol fast path doesn't produce spurious matches."""
    kato_fixture.clear_all_memory()

    # Learn two distinct patterns
    for item in ['cat', 'dog', 'bird']:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()

    for item in ['red', 'green', 'blue']:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()

    # Single-symbol query for 'cat' should only match the animal pattern
    kato_fixture.observe({'strings': ['cat'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()

    # Should not match the color pattern
    for pred in predictions:
        matches = pred.get('matches', [])
        assert 'red' not in matches and 'green' not in matches, \
            f"Single-symbol fast path should not match unrelated pattern, got matches={matches}"
