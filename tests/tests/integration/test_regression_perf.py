"""
Regression tests for performance-critical code paths.

These tests verify behavior introduced by recent performance optimizations:
- Read-your-writes visibility for patterns_data after learn()
- Symbol batch retrieval correctness (get_all_symbols_batch)
- Single-symbol fast path consistency (_predict_single_symbol_fast)

These do NOT test performance (speed), only correctness of the optimized paths.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from fixtures.store_diagnostics import describe_prediction_miss


def test_deferred_flush_visibility(kato_fixture):
    """Test that patterns are immediately queryable after learning.

    patterns_data is inserted with wait_for_async_insert=0, so a row could in
    principle lag the insert before becoming queryable. It does not, because
    learnPattern writes the metadata sidecar with wait=1 straight afterwards and
    ClickHouse's adaptive busy timeout keeps the applied timeout at 0-50ms.

    Nothing on the read path enforces this -- it is a property of the write path
    and of a ClickHouse default. This test previously credited flush_if_pending,
    which only drains the client buffer (empty at batch_size=1) and so did
    nothing. See test_learn_then_predict_is_never_stale for the repeated-trial
    version.
    """
    kato_fixture.clear_all_memory()

    # Learn a pattern
    sequence = ['flush', 'visibility', 'test']
    for item in sequence:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    pattern_name = kato_fixture.learn()
    assert pattern_name.startswith('PTRN|'), "Pattern should be learned"

    # IMMEDIATELY query predictions (no delay) - this is the critical test
    # If the write-path guarantee ever breaks, this is where it surfaces
    kato_fixture.observe({'strings': ['flush'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['visibility'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()

    assert len(predictions) > 0, \
        "Just-learned pattern should be immediately visible in predictions"

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


def test_learn_then_predict_is_never_stale(kato_fixture):
    """Learn then predict immediately, repeatedly, with no finalize-training.

    patterns_data is written with wait_for_async_insert=0, so each new pattern is
    invisible for up to async_insert_busy_timeout_ms (200ms) unless the read path
    drains the server's async buffer. A single learn-then-predict passes whenever
    the drain happens to have occurred, which is why this race survived: the
    existing visibility tests each take one sample.

    Every iteration learns a pattern that did not exist before and immediately
    requires it back, so a missed drain fails here rather than intermittently in
    CI. finalize-training is deliberately not called -- the docs describe it as
    optional, so predictions must work without it.
    """
    kato_fixture.clear_all_memory()

    for i in range(20):
        head, tail = f'stale_head_{i}', f'stale_tail_{i}'

        kato_fixture.observe({'strings': [head], 'vectors': [], 'emotives': {}})
        kato_fixture.observe({'strings': [tail], 'vectors': [], 'emotives': {}})
        pattern_name = kato_fixture.learn()
        assert pattern_name.startswith('PTRN|'), f"iteration {i}: pattern should be learned"

        # No sleep, no finalize-training, no clear_all_memory between iterations.
        kato_fixture.observe({'strings': [head], 'vectors': [], 'emotives': {}})
        predictions = kato_fixture.get_predictions()

        assert len(predictions) > 0, (
            f"iteration {i}: the pattern learned microseconds ago was not visible\n"
            + describe_prediction_miss(kato_fixture, expected_symbols=[head, tail])
        )
        assert any(head in p.get('matches', []) for p in predictions), (
            f"iteration {i}: predictions returned, but not the just-learned pattern"
        )

        kato_fixture.clear_stm()


def test_single_symbol_fast_path_sees_fresh_pattern(kato_fixture):
    """The single-symbol fast path queries patterns_data directly.

    predictPattern dispatches to _predict_single_symbol_fast for a one-symbol
    STM, and that path issues its own SELECT against patterns_data rather than
    going through the filter pipeline. It is therefore the most exposed to the
    visibility window, and it relies on its caller having drained first.
    """
    kato_fixture.clear_all_memory()

    for i in range(15):
        symbol = f'fast_fresh_{i}'
        kato_fixture.observe({'strings': [symbol], 'vectors': [], 'emotives': {}})
        kato_fixture.observe({'strings': [f'fast_next_{i}'], 'vectors': [], 'emotives': {}})
        assert kato_fixture.learn().startswith('PTRN|')

        kato_fixture.clear_stm()
        kato_fixture.observe({'strings': [symbol], 'vectors': [], 'emotives': {}})
        predictions = kato_fixture.get_predictions()

        assert len(predictions) > 0, (
            f"iteration {i}: single-symbol fast path missed a pattern learned moments ago\n"
            + describe_prediction_miss(kato_fixture, expected_symbols=[symbol])
        )
        kato_fixture.clear_stm()
