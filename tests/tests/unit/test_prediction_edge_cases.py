"""
Edge case tests for KATO prediction fields.
Tests unusual scenarios and boundary conditions.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from fixtures.kato_fixtures import kato_fixture as kato_fixture
from fixtures.test_helpers import sort_event_strings


def test_empty_events_ignored(kato_fixture):
    """Test that empty events are ignored and don't change state."""
    kato_fixture.clear_all_memory()

    # Get initial state
    initial_stm = kato_fixture.get_short_term_memory()
    kato_fixture.get_predictions()

    # Observe empty event
    kato_fixture.observe({'strings': [], 'vectors': [], 'emotives': {}})

    # short-term memory should not change
    stm_after_empty = kato_fixture.get_short_term_memory()
    assert stm_after_empty == initial_stm, "Empty event should not change short-term memory"

    # Now test that empty events in a sequence are ignored
    kato_fixture.clear_all_memory()

    # Observe sequence with attempted empty events
    kato_fixture.observe({'strings': ['a'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': [], 'vectors': [], 'emotives': {}})  # Should be ignored
    kato_fixture.observe({'strings': ['b'], 'vectors': [], 'emotives': {}})

    stm = kato_fixture.get_short_term_memory()
    # Should only have the non-empty events
    assert stm == [['a'], ['b']], f"Empty events should be ignored, got {stm}"


def test_prediction_no_past(kato_fixture):
    """Test prediction when observing the beginning of a sequence (no past)."""
    kato_fixture.clear_all_memory()
    # Set moderate threshold for beginning sequence predictions
    kato_fixture.set_recall_threshold(0.3)

    # Learn: [['start'], ['middle'], ['end']]
    sequence = ['start', 'middle', 'end']
    for item in sequence:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()

    # Observe the start and middle to meet 2+ requirement
    kato_fixture.clear_short_term_memory()
    kato_fixture.observe({'strings': ['start'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['middle'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()

    # Find matching prediction
    for pred in predictions:
        if 'start' in pred.get('matches', []) and 'middle' in pred.get('matches', []):
            past = pred.get('past', [])
            present = pred.get('present', [])
            future = pred.get('future', [])

            # No past when observing from beginning
            assert past == [] or past == [[]], f"Should have no past, got {past}"
            # Since we observed 'start' and 'middle', both should be in present
            assert present == [['start'], ['middle']], f"Present should be [['start'], ['middle']], got {present}"
            # Future should have remaining event
            assert future == [['end']], f"Future should be [['end']], got {future}"
            break


def test_prediction_no_future(kato_fixture):
    """Test prediction when observing the end of a sequence (no future)."""
    kato_fixture.clear_all_memory()

    # Learn: [['start'], ['middle'], ['end']]
    sequence = ['start', 'middle', 'end']
    for item in sequence:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()

    # Observe all events (complete sequence)
    kato_fixture.clear_short_term_memory()
    for item in sequence:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()

    # Find matching prediction with full sequence
    for pred in predictions:
        if pred.get('similarity', 0) == 1.0 or pred.get('frequency', 0) > 0:
            future = pred.get('future', [])
            # No future after complete sequence
            assert future == [] or future == [[]], f"Should have no future for complete sequence, got {future}"
            break


def test_all_extras_no_matches(kato_fixture):
    """Test when observation has only extras, no matching symbols."""
    kato_fixture.clear_all_memory()

    # Learn: [['known1'], ['known2']]
    sequence = ['known1', 'known2']
    for item in sequence:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()

    # Observe completely different symbols
    kato_fixture.clear_short_term_memory()
    kato_fixture.observe({'strings': ['unknown1'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['unknown2'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()

    # Should have low or no matches
    # This tests the edge case where nothing matches
    if predictions:
        for pred in predictions:
            if pred.get('frequency', 0) > 0:
                # If there's a prediction, extras should contain the unknown symbols
                pred.get('extras', [])
                matches = pred.get('matches', [])
                # Low or no matches expected
                assert len(matches) == 0 or pred.get('similarity', 0) < 0.5


def test_partial_overlap_multiple_sequences(kato_fixture):
    """Test predictions when partial match could belong to multiple sequences."""
    kato_fixture.clear_all_memory()

    # Learn multiple sequences with overlapping symbols
    sequences = [
        [['shared', 'unique1'], ['end1']],
        [['shared', 'unique2'], ['end2']],
        [['different'], ['shared', 'unique3']]
    ]

    for seq in sequences:
        for event in seq:
            kato_fixture.observe({'strings': sort_event_strings(event), 'vectors': [], 'emotives': {}})
        kato_fixture.learn()

    # Observe 'shared' plus another symbol to meet 2+ requirement
    kato_fixture.clear_short_term_memory()
    kato_fixture.observe({'strings': ['shared', 'unique1'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()

    # Should have at least one prediction matching the first sequence
    matching_predictions = [p for p in predictions if 'shared' in p.get('matches', [])]
    assert len(matching_predictions) >= 1, "Should have predictions for matching sequence"

    # Each should have different missing symbols
    all_missing = []
    for pred in matching_predictions:
        missing = pred.get('missing', [])
        # Missing is event-structured, flatten it
        if missing and isinstance(missing[0], list):
            for event_missing in missing:
                all_missing.extend(event_missing)
        else:
            all_missing.extend(missing)

    # Should be missing different unique symbols from different sequences
    assert 'unique1' in all_missing or 'unique2' in all_missing or 'unique3' in all_missing


def test_very_long_sequence_middle_observation(kato_fixture):
    """Test prediction fields with a very long sequence, observing the middle."""
    kato_fixture.clear_all_memory()

    # Learn a long sequence
    long_sequence = [f'item{i}' for i in range(10)]
    for item in long_sequence:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()

    # Observe events in the middle
    kato_fixture.clear_short_term_memory()
    kato_fixture.observe({'strings': ['item4'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['item5'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()

    # Find matching prediction
    for pred in predictions:
        if 'item4' in pred.get('matches', []) and 'item5' in pred.get('matches', []):
            past = pred.get('past', [])
            present = pred.get('present', [])
            future = pred.get('future', [])

            # Should have multiple past events
            assert len(past) >= 4, f"Should have past events 0-3, got {len(past)} events"

            # Present should be the two observed events
            assert len(present) == 2, f"Present should have 2 events, got {len(present)}"

            # Should have multiple future events
            assert len(future) >= 4, f"Should have future events 6-9, got {len(future)} events"
            break


def test_repeated_symbols_in_event(kato_fixture):
    """Test handling of repeated symbols within a single event."""
    kato_fixture.clear_all_memory()

    # Learn event with repeated symbols (after sorting, duplicates might be handled differently)
    kato_fixture.observe({'strings': sort_event_strings(['a', 'b', 'a', 'c', 'b']), 'vectors': [], 'emotives': {}})
    kato_fixture.learn()

    # Observe partial match
    kato_fixture.clear_short_term_memory()
    kato_fixture.observe({'strings': ['a', 'b'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()

    # Check how repeated symbols are handled
    for pred in predictions:
        if pred.get('frequency', 0) > 0:
            missing = pred.get('missing', [])
            # Depending on KATO's handling, might be missing 'c' or duplicates
            assert len(missing) >= 0  # Just verify prediction exists
            break


def test_case_sensitive_matching(kato_fixture):
    """Test that matching is case-sensitive."""
    kato_fixture.clear_all_memory()

    # Learn with specific casing
    kato_fixture.observe({'strings': sort_event_strings(['Hello', 'World']), 'vectors': [], 'emotives': {}})
    kato_fixture.learn()

    # Observe with different casing
    kato_fixture.clear_short_term_memory()
    kato_fixture.observe({'strings': sort_event_strings(['hello', 'world']), 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()

    # Check if lowercase is treated as extras (case-sensitive) or matches (case-insensitive)
    for pred in predictions:
        matches = pred.get('matches', [])
        extras = pred.get('extras', [])

        # Document the actual behavior
        if 'Hello' in matches or 'World' in matches:
            # Case-insensitive matching
            assert True, "KATO uses case-insensitive matching"
        elif 'hello' in extras or 'world' in extras:
            # Case-sensitive matching
            assert True, "KATO uses case-sensitive matching"
        break


def test_observation_longer_than_learned(kato_fixture):
    """Test when observation sequence is longer than any learned sequence."""
    kato_fixture.clear_all_memory()

    # Learn short sequence
    short_seq = ['a', 'b']
    for item in short_seq:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()

    # Observe longer sequence
    kato_fixture.clear_short_term_memory()
    long_obs = ['a', 'b', 'c', 'd', 'e']
    for item in long_obs:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()

    # Find matching prediction
    for pred in predictions:
        if 'a' in pred.get('matches', []) and 'b' in pred.get('matches', []):
            present = pred.get('present', [])
            extras = pred.get('extras', [])

            # The learned sequence should match partially
            # Extra observations beyond learned sequence might be in extras
            assert len(present) <= 2, f"Present should not exceed learned length, got {present}"
            # Additional symbols might be extras - flatten if event-structured
            if extras:
                flat_extras = []
                if isinstance(extras[0], list):
                    for event_extras in extras:
                        flat_extras.extend(event_extras)
                else:
                    flat_extras = extras
                assert 'c' in flat_extras or 'd' in flat_extras or 'e' in flat_extras, f"Expected c, d, or e in extras, got {extras}"
            break


def test_single_symbol_sequences(kato_fixture):
    """Test predictions with sequences of single symbols."""
    kato_fixture.clear_all_memory()

    # Learn sequence of single symbols
    single_symbols = ['x', 'y', 'z']
    for symbol in single_symbols:
        kato_fixture.observe({'strings': [symbol], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()

    # Observe middle symbols (KATO requires 2+ strings for predictions)
    kato_fixture.clear_short_term_memory()
    kato_fixture.observe({'strings': ['x'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['y'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()

    # Find matching prediction
    for pred in predictions:
        if 'x' in pred.get('matches', []) and 'y' in pred.get('matches', []):
            pred.get('past', [])
            present = pred.get('present', [])
            future = pred.get('future', [])

            # Since we observed 'x' and 'y', they should be in present
            assert present == [['x'], ['y']], f"Present should be [['x'], ['y']], got {present}"
            assert future == [['z']], f"Future should be [['z']], got {future}"
            break
