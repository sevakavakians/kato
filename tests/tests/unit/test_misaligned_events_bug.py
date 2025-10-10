"""
Test to reproduce and verify fix for misaligned event bug.

Bug: The missing/extras fields were incorrectly aligned with STM events
instead of following the documented behavior:
- missing should align with present events (pattern events)
- extras should align with STM events (observed events)

This led to situations where a symbol could appear in both present and missing,
which is logically impossible.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from fixtures.kato_fixtures import kato_fixture as kato_fixture
from fixtures.test_helpers import sort_event_strings


def test_misaligned_events_different_lengths(kato_fixture):
    """
    Test case where STM has different number of events than pattern present.

    This is the core bug scenario: when pattern matching finds a pattern
    where the present portion has a different number of events than the STM.
    """
    kato_fixture.clear_all_memory()
    kato_fixture.set_recall_threshold(0.1)  # Low threshold to allow fuzzy matches

    # Learn pattern 1: Single event with one symbol
    kato_fixture.observe({'strings': ['shared'], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()

    # Learn pattern 2: Multi-event sequence with the shared symbol
    kato_fixture.observe({'strings': ['before1'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['before2'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['shared'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['after1'], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()

    # Now observe a multi-event sequence that includes 'shared'
    kato_fixture.clear_short_term_memory()
    kato_fixture.observe({'strings': ['event1'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['event2'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['shared'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['event4'], 'vectors': [], 'emotives': {}})

    predictions = kato_fixture.get_predictions()
    assert len(predictions) > 0, "Should have predictions"

    # Find the prediction for the single-event pattern
    for pred in predictions:
        if pred.get('name') and len(pred.get('sequence', [])) == 1:
            present = pred.get('present', [])
            missing = pred.get('missing', [])
            extras = pred.get('extras', [])

            # CRITICAL CHECKS:
            # 1. Length of missing should match length of present (not STM!)
            assert len(missing) == len(present), \
                f"Missing length ({len(missing)}) should match present length ({len(present)}), " \
                f"not STM length (4). missing={missing}, present={present}"

            # 2. No symbol should appear in both present and missing for same event
            for i, present_event in enumerate(present):
                if i < len(missing):
                    missing_event = missing[i]
                    overlap = set(present_event) & set(missing_event)
                    assert len(overlap) == 0, \
                        f"Event {i}: Symbol(s) {overlap} appear in both present and missing! " \
                        f"present[{i}]={present_event}, missing[{i}]={missing_event}"

            # 3. Length of extras should match length of STM (observed events)
            assert len(extras) == 4, \
                f"Extras length ({len(extras)}) should match STM length (4). extras={extras}"

            break


def test_missing_aligned_with_present_not_stm(kato_fixture):
    """
    Test that missing is aligned with present events, not STM events.

    This verifies the fix where missing[i] corresponds to present[i].
    """
    kato_fixture.clear_all_memory()
    kato_fixture.set_recall_threshold(0.3)

    # Learn a 2-event pattern with multiple symbols per event
    kato_fixture.observe({'strings': sort_event_strings(['a', 'b', 'c']), 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': sort_event_strings(['d', 'e', 'f']), 'vectors': [], 'emotives': {}})
    kato_fixture.learn()

    # Observe partial symbols from each event
    kato_fixture.clear_short_term_memory()
    kato_fixture.observe({'strings': ['a'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['d'], 'vectors': [], 'emotives': {}})

    predictions = kato_fixture.get_predictions()
    assert len(predictions) > 0, "Should have predictions"

    pred = predictions[0]
    present = pred.get('present', [])
    missing = pred.get('missing', [])
    matches = pred.get('matches', [])

    # Verify structure
    assert len(present) == 2, f"Should have 2 present events, got {len(present)}"
    assert len(missing) == 2, f"Missing should have 2 sub-lists (one per present event), got {len(missing)}"

    # Verify missing is calculated correctly per present event
    # present[0] should be ['a', 'b', 'c'], we observed 'a', so missing should be ['b', 'c']
    # present[1] should be ['d', 'e', 'f'], we observed 'd', so missing should be ['e', 'f']
    assert set(missing[0]) == {'b', 'c'}, f"First event should be missing 'b' and 'c', got {missing[0]}"
    assert set(missing[1]) == {'e', 'f'}, f"Second event should be missing 'e' and 'f', got {missing[1]}"

    # Verify no overlap between matched symbols and missing symbols
    all_missing = [s for event in missing for s in event]
    overlap = set(matches) & set(all_missing)
    assert len(overlap) == 0, f"Matches and missing should not overlap, got {overlap}"


def test_extras_aligned_with_stm_not_present(kato_fixture):
    """
    Test that extras is aligned with STM events, not present events.

    This verifies that extras[i] corresponds to stm_events[i].
    """
    kato_fixture.clear_all_memory()
    kato_fixture.set_recall_threshold(0.3)

    # Learn a simple 2-event pattern
    kato_fixture.observe({'strings': ['expected1'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['expected2'], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()

    # Observe with extra unexpected symbols in each event
    kato_fixture.clear_short_term_memory()
    kato_fixture.observe({'strings': sort_event_strings(['expected1', 'extra1']), 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': sort_event_strings(['expected2', 'extra2']), 'vectors': [], 'emotives': {}})

    predictions = kato_fixture.get_predictions()
    assert len(predictions) > 0, "Should have predictions"

    pred = predictions[0]
    extras = pred.get('extras', [])

    # Verify structure - should have 2 sub-lists (one per STM event)
    assert len(extras) == 2, f"Extras should have 2 sub-lists (one per STM event), got {len(extras)}"

    # Verify extras content - each STM event has one extra symbol
    assert 'extra1' in extras[0], f"First STM event should have 'extra1' in extras, got {extras[0]}"
    assert 'extra2' in extras[1], f"Second STM event should have 'extra2' in extras, got {extras[1]}"


def test_complex_misalignment_scenario(kato_fixture):
    """
    Test complex scenario with significant mismatch between STM and pattern structures.

    Simulates the real bug scenario from the issue report where:
    - STM has many events
    - Pattern present has fewer events
    - Symbol appears incorrectly in both present and missing
    """
    kato_fixture.clear_all_memory()
    kato_fixture.set_recall_threshold(0.1)  # Very low to allow fuzzy matches

    # Learn a long pattern with a shared symbol in the middle
    kato_fixture.observe({'strings': ['p1'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['p2'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['p3'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['shared_symbol'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['p5'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['p6'], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()

    # Observe a completely different sequence that happens to have the shared symbol
    kato_fixture.clear_short_term_memory()
    kato_fixture.observe({'strings': ['s1'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['s2'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['shared_symbol'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['s4'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['s5'], 'vectors': [], 'emotives': {}})

    predictions = kato_fixture.get_predictions()

    # For each prediction, verify the invariants
    for pred in predictions:
        present = pred.get('present', [])
        missing = pred.get('missing', [])
        extras = pred.get('extras', [])
        matches = pred.get('matches', [])

        # INVARIANT 1: missing length equals present length
        assert len(missing) == len(present), \
            f"Prediction {pred.get('name')}: missing length {len(missing)} != present length {len(present)}"

        # INVARIANT 2: extras length equals STM length (5 in this case)
        assert len(extras) == 5, \
            f"Prediction {pred.get('name')}: extras length {len(extras)} != STM length (5)"

        # INVARIANT 3: No symbol in both present and missing for same event
        for i in range(len(present)):
            present_symbols = set(present[i]) if i < len(present) else set()
            missing_symbols = set(missing[i]) if i < len(missing) else set()
            overlap = present_symbols & missing_symbols
            assert len(overlap) == 0, \
                f"Prediction {pred.get('name')}, event {i}: symbols {overlap} in both present and missing"

        # INVARIANT 4: All missing symbols should be in flattened present
        all_missing = [s for event in missing for s in event]
        flattened_present = [s for event in present for s in event]
        for sym in all_missing:
            assert sym in flattened_present, \
                f"Prediction {pred.get('name')}: missing symbol '{sym}' not in present"


def test_single_present_event_multi_stm_events(kato_fixture):
    """
    Test specific scenario: pattern has 1 present event, STM has multiple events.

    This is the exact scenario from the bug report.
    Note: This test verifies the invariants hold for any predictions returned,
    without relying on specific pattern matching behavior.
    """
    kato_fixture.clear_all_memory()
    kato_fixture.set_recall_threshold(0.1)

    # Learn a single-event pattern
    kato_fixture.observe({'strings': ['the_symbol'], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()

    # Learn a multi-event pattern to ensure we have something to match
    kato_fixture.observe({'strings': ['other1'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['the_symbol'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['other3'], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()

    # Observe multiple events with the symbol appearing in one
    kato_fixture.clear_short_term_memory()
    kato_fixture.observe({'strings': ['other1'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['other2'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['the_symbol'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['other4'], 'vectors': [], 'emotives': {}})

    predictions = kato_fixture.get_predictions()
    assert len(predictions) > 0, "Should have at least one prediction"

    # Verify all predictions meet the invariants (regardless of which pattern matched)
    for pred in predictions:
        present = pred.get('present', [])
        missing = pred.get('missing', [])
        extras = pred.get('extras', [])

        # Key assertions for this bug scenario:
        # 1. Missing length equals present length (not STM length)
        assert len(missing) == len(present), \
            f"Missing length ({len(missing)}) should equal present length ({len(present)})"

        # 2. Extras length equals STM length (4 events)
        assert len(extras) == 4, \
            f"Extras length ({len(extras)}) should equal STM length (4)"

        # 3. No symbol appears in both present and missing for the same event
        for i in range(len(present)):
            present_symbols = set(present[i])
            missing_symbols = set(missing[i]) if i < len(missing) else set()
            overlap = present_symbols & missing_symbols
            assert len(overlap) == 0, \
                f"Event {i}: symbols {overlap} appear in both present and missing!"
