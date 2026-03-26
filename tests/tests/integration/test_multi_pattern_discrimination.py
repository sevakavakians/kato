"""
Tests for multi-pattern discrimination.

Verifies that KATO correctly disambiguates between multiple learned patterns
including overlapping prefixes, subset patterns, reordered patterns, and
large numbers of similar patterns.

Previous test coverage for multi-pattern scenarios was limited to 6 tests.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from fixtures.kato_fixtures import kato_fixture as kato_fixture


def test_overlapping_prefix_discrimination(kato_fixture):
    """Test disambiguation when multiple patterns share a common prefix."""
    kato_fixture.clear_all_memory()

    patterns = [
        ['common', 'prefix', 'ending_a'],
        ['common', 'prefix', 'ending_b'],
        ['common', 'prefix', 'ending_c'],
        ['common', 'diverge', 'ending_d'],
    ]

    for pattern in patterns:
        for item in pattern:
            kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
        kato_fixture.learn()

    # Observe the shared prefix — should match all 4 patterns
    kato_fixture.observe({'strings': ['common'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['prefix'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()

    # Should find at least the 3 patterns that share 'common', 'prefix'
    prefix_matches = [p for p in predictions
                      if 'common' in p.get('matches', []) and 'prefix' in p.get('matches', [])]
    assert len(prefix_matches) >= 3, \
        f"Should find at least 3 patterns with shared prefix, got {len(prefix_matches)}"

    # Each should predict a different future
    futures = set()
    for pred in prefix_matches:
        future = pred.get('future', [])
        if future and isinstance(future[0], list):
            futures.add(tuple(future[0]))
    assert len(futures) >= 3, \
        f"Different patterns should predict different futures, got {futures}"


def test_subset_pattern_discrimination(kato_fixture):
    """Test that a shorter pattern (subset) and longer pattern are both found."""
    kato_fixture.clear_all_memory()

    # Learn a short pattern and a longer pattern that contains it
    for item in ['A', 'B']:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    short_name = kato_fixture.learn()

    for item in ['A', 'B', 'C', 'D']:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    long_name = kato_fixture.learn()

    assert short_name != long_name, "Short and long patterns should have different hashes"

    # Observe 'A', 'B' — should match both patterns
    kato_fixture.observe({'strings': ['A'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['B'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()

    names = {p.get('name') for p in predictions}
    assert short_name in names, "Should find the short pattern"
    assert long_name in names, "Should find the long pattern"

    # Short pattern should have higher similarity (2/2 = 1.0 vs 2/4 = 0.667)
    short_pred = [p for p in predictions if p.get('name') == short_name][0]
    long_pred = [p for p in predictions if p.get('name') == long_name][0]
    assert short_pred.get('similarity', 0) > long_pred.get('similarity', 0), \
        "Short pattern (exact match) should have higher similarity than long pattern (partial match)"


def test_reordered_symbols_different_patterns(kato_fixture):
    """Test that same symbols in different event ORDER produce different patterns."""
    kato_fixture.clear_all_memory()

    # Learn [X, Y, Z] and [Z, Y, X] — different temporal order
    for item in ['order_x', 'order_y', 'order_z']:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    name_forward = kato_fixture.learn()

    for item in ['order_z', 'order_y', 'order_x']:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    name_reverse = kato_fixture.learn()

    assert name_forward != name_reverse, \
        "Same symbols in different order should produce different pattern hashes"


def test_many_overlapping_patterns(kato_fixture):
    """Test discrimination with 15+ patterns sharing a common symbol."""
    kato_fixture.clear_all_memory()
    kato_fixture.set_recall_threshold(0.1)

    # Learn 15 patterns that all start with 'root'
    pattern_names = []
    for i in range(15):
        for item in ['root', f'branch_{i}', f'leaf_{i}']:
            kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
        name = kato_fixture.learn()
        pattern_names.append(name)

    # All should be unique patterns
    assert len(set(pattern_names)) == 15, "All 15 patterns should have unique hashes"

    # Observe 'root' + 'branch_5' — should match pattern 5 with highest similarity
    kato_fixture.observe({'strings': ['root'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['branch_5'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()

    # Should find the specific pattern
    exact = [p for p in predictions
             if 'root' in p.get('matches', []) and 'branch_5' in p.get('matches', [])]
    assert len(exact) >= 1, "Should find the pattern with 'root' and 'branch_5'"

    # The exact match should have higher similarity than other patterns
    if len(predictions) > 1:
        exact_sim = exact[0].get('similarity', 0)
        other_sims = [p.get('similarity', 0) for p in predictions if p not in exact]
        if other_sims:
            assert exact_sim >= max(other_sims), \
                f"Exact match (sim={exact_sim}) should have highest similarity"


def test_identical_events_different_lengths(kato_fixture):
    """Test patterns with same events but different repetition counts."""
    kato_fixture.clear_all_memory()

    # Pattern 1: [A, B] (2 events)
    for item in ['rep', 'seq']:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    name_short = kato_fixture.learn()

    # Pattern 2: [A, B, A, B] (4 events, repeated)
    for item in ['rep', 'seq', 'rep', 'seq']:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    name_long = kato_fixture.learn()

    assert name_short != name_long, \
        "Different-length patterns with same symbols should have different hashes"

    # Both should be findable
    kato_fixture.observe({'strings': ['rep'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['seq'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()

    names = {p.get('name') for p in predictions}
    assert name_short in names, "Should find the short pattern"
    assert name_long in names, "Should find the long repeated pattern"


def test_disjoint_patterns_no_cross_match(kato_fixture):
    """Test that completely disjoint patterns don't match each other."""
    kato_fixture.clear_all_memory()

    # Learn completely disjoint patterns
    for item in ['cat', 'dog', 'bird']:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()

    for item in ['red', 'green', 'blue']:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()

    # Observe from pattern 1 — should NOT match pattern 2
    kato_fixture.observe({'strings': ['cat'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['dog'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()

    for pred in predictions:
        matches = pred.get('matches', [])
        assert 'red' not in matches and 'green' not in matches and 'blue' not in matches, \
            f"Disjoint pattern should not match, got matches={matches}"


def test_multi_symbol_event_discrimination(kato_fixture):
    """Test discrimination with multi-symbol events."""
    kato_fixture.clear_all_memory()

    from fixtures.test_helpers import sort_event_strings

    # Learn patterns with multi-symbol events
    kato_fixture.observe({'strings': sort_event_strings(['a', 'b']), 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': sort_event_strings(['c', 'd']), 'vectors': [], 'emotives': {}})
    name1 = kato_fixture.learn()

    kato_fixture.observe({'strings': sort_event_strings(['a', 'b']), 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': sort_event_strings(['e', 'f']), 'vectors': [], 'emotives': {}})
    name2 = kato_fixture.learn()

    assert name1 != name2, "Patterns with different second events should differ"

    # Observe shared first event + unique second event from pattern 1
    kato_fixture.observe({'strings': sort_event_strings(['a', 'b']), 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': sort_event_strings(['c', 'd']), 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()

    # Pattern 1 should have higher similarity (exact match) than pattern 2 (partial match)
    pred1 = [p for p in predictions if p.get('name') == name1]
    pred2 = [p for p in predictions if p.get('name') == name2]

    assert len(pred1) >= 1, "Should find pattern 1"
    if len(pred2) >= 1:
        assert pred1[0].get('similarity', 0) >= pred2[0].get('similarity', 0), \
            "Exact match should have >= similarity than partial match"
