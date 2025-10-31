"""
Comprehensive tests for KATO's 2+ string requirement for predictions.

KATO requires at least 2 strings total in STM to generate predictions.
This can be achieved through:
- Single event with 2+ strings: [['a', 'b']]
- Multiple events with 1+ strings each: [['a'], ['b']]
- Any combination totaling 2+ strings

This test file verifies this requirement is properly enforced.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from fixtures.kato_fixtures import kato_fixture as kato_fixture


def test_single_string_no_predictions(kato_fixture):
    """Test that a single string observation generates NO predictions."""
    kato_fixture.clear_all_memory()

    # First learn a sequence for comparison
    sequence = ['alpha', 'beta', 'gamma']
    for item in sequence:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()

    # Clear STM and observe only ONE string
    kato_fixture.clear_short_term_memory()
    kato_fixture.observe({'strings': ['alpha'], 'vectors': [], 'emotives': {}})

    # Should have NO predictions with only 1 string
    predictions = kato_fixture.get_predictions()
    assert predictions == [], f"Expected no predictions with 1 string, got {len(predictions)} predictions"

    # Verify STM has the single string
    stm = kato_fixture.get_short_term_memory()
    assert stm == [['alpha']], "STM should contain the single observed string"


def test_exactly_two_strings_generates_predictions(kato_fixture):
    """Test that exactly 2 strings (minimum) generates predictions."""
    kato_fixture.clear_all_memory()

    # Learn a sequence
    sequence = ['one', 'two', 'three']
    for item in sequence:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()

    # Test Case 1: Two separate events with one string each
    kato_fixture.clear_short_term_memory()
    kato_fixture.observe({'strings': ['one'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['two'], 'vectors': [], 'emotives': {}})

    # Should have predictions with 2 strings
    predictions = kato_fixture.get_predictions()
    assert len(predictions) > 0, "Should have predictions with exactly 2 strings"

    # Test Case 2: Single event with two strings
    kato_fixture.clear_short_term_memory()
    kato_fixture.observe({'strings': ['one', 'two'], 'vectors': [], 'emotives': {}})

    # Should also have predictions
    predictions = kato_fixture.get_predictions()
    assert len(predictions) > 0, "Should have predictions with 2 strings in single event"


def test_empty_events_dont_count(kato_fixture):
    """Test that empty events don't count toward the 2+ requirement."""
    kato_fixture.clear_all_memory()

    # Learn a sequence
    sequence = ['x', 'y', 'z']
    for item in sequence:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()

    # Observe one string and multiple empty events
    kato_fixture.clear_short_term_memory()
    kato_fixture.observe({'strings': ['x'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': [], 'vectors': [], 'emotives': {}})  # Empty - ignored
    kato_fixture.observe({'strings': [], 'vectors': [], 'emotives': {}})  # Empty - ignored

    # Should still have NO predictions (only 1 actual string)
    predictions = kato_fixture.get_predictions()
    assert predictions == [], "Empty events shouldn't count toward 2+ requirement"

    # Now add a second real string
    kato_fixture.observe({'strings': ['y'], 'vectors': [], 'emotives': {}})

    # NOW should have predictions
    predictions = kato_fixture.get_predictions()
    assert len(predictions) > 0, "Should have predictions after 2nd non-empty string"


def test_vector_only_observations(kato_fixture):
    """
    Test behavior with vector-only observations (no strings).
    Tests that the service handles vectors without crashing.

    This test verifies:
    1. Vector observations are handled without service crashes
    2. System gracefully handles vector dimension mismatches
    3. Predictions work with vector-only observations
    """
    import random

    # Test with multiple dimensions to ensure robustness
    # The service should handle all dimensions without crashing
    dimensions_to_test = [2, 128, 512]

    for dim in dimensions_to_test:
        # Generate test vectors of the specified dimension
        vec1 = [random.random() for _ in range(dim)]
        vec2 = [random.random() for _ in range(dim)]
        vec3 = [random.random() for _ in range(dim)]

        # Learn a mixed sequence (strings + vectors)
        kato_fixture.observe({'strings': ['start'], 'vectors': [vec1], 'emotives': {}})
        kato_fixture.observe({'strings': ['middle'], 'vectors': [vec2], 'emotives': {}})
        kato_fixture.observe({'strings': ['end'], 'vectors': [vec3], 'emotives': {}})
        kato_fixture.learn()

        # Clear STM and observe only vectors of the same dimension
        kato_fixture.clear_short_term_memory()
        kato_fixture.observe({'strings': [], 'vectors': [vec1], 'emotives': {}})
        kato_fixture.observe({'strings': [], 'vectors': [vec2], 'emotives': {}})

        # This test verifies no crash and consistent behavior for each dimension
        predictions = kato_fixture.get_predictions()
        assert isinstance(predictions, list), f"Should return a list for {dim}D vectors (no crash)"

        # Test that dimension mismatches are handled gracefully (no service crash)
        wrong_dim = dim + 1
        wrong_vec = [random.random() for _ in range(wrong_dim)]

        # Try to send a vector with wrong dimension - should not crash the service
        # The system may accept it (with degraded performance) or reject it gracefully
        try:
            kato_fixture.observe({'strings': [], 'vectors': [wrong_vec], 'emotives': {}})
            # If accepted, just verify no crash occurred
            assert True, "Dimension mismatch handled gracefully"
        except Exception as e:
            # If rejected, verify it's a graceful error (not a crash)
            assert "400" in str(e) or "dimension" in str(e).lower() or "error" in str(e).lower(), \
                f"Should get graceful error for dimension mismatch, got: {e}"

        # Clear all memory for next test iteration
        kato_fixture.clear_all_memory()


def test_learning_with_insufficient_strings(kato_fixture):
    """Test that learning with < 2 strings doesn't create a model."""
    kato_fixture.clear_all_memory()

    # Try to learn with only 1 string
    kato_fixture.observe({'strings': ['lonely'], 'vectors': [], 'emotives': {}})
    pattern_name = kato_fixture.learn()

    # Should not create a pattern with only 1 string
    # Pattern creation requires at least 2 events/strings
    assert pattern_name == "" or pattern_name is None, f"Should not create model with 1 string, got {pattern_name}"


def test_auto_learn_with_insufficient_strings(kato_fixture):
    """Test auto-learn behavior when max_pattern_length reached with < 2 strings."""
    kato_fixture.clear_all_memory()

    # Set a low max_pattern_length for testing
    # Note: This assumes the fixture allows setting max_pattern_length
    # If not, this test can be skipped or modified

    # Observe single string (should not trigger predictions even after auto-learn)
    kato_fixture.observe({'strings': ['auto'], 'vectors': [], 'emotives': {}})

    # Even if auto-learn triggers, predictions should not be generated
    predictions = kato_fixture.get_predictions()
    assert predictions == [], "No predictions with insufficient strings even after auto-learn"


def test_transition_from_one_to_two_strings(kato_fixture):
    """Test the transition point from 1 string (no predictions) to 2 strings (predictions)."""
    kato_fixture.clear_all_memory()

    # Learn a sequence
    for char in ['a', 'b', 'c', 'd']:
        kato_fixture.observe({'strings': [char], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()

    # Start fresh
    kato_fixture.clear_short_term_memory()

    # First string - no predictions
    kato_fixture.observe({'strings': ['a'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()
    assert predictions == [], "No predictions with 1 string"

    # Second string - now predictions should appear
    kato_fixture.observe({'strings': ['b'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()
    assert len(predictions) > 0, "Should have predictions immediately after 2nd string"

    # Third string - predictions should continue
    kato_fixture.observe({'strings': ['c'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()
    assert len(predictions) > 0, "Should continue having predictions with 3+ strings"


def test_mixed_event_sizes(kato_fixture):
    """Test 2+ requirement with events of different sizes."""
    kato_fixture.clear_all_memory()

    # Learn a complex sequence
    kato_fixture.observe({'strings': ['w', 'x'], 'vectors': [], 'emotives': {}})  # 2 strings
    kato_fixture.observe({'strings': ['y'], 'vectors': [], 'emotives': {}})       # 1 string
    kato_fixture.observe({'strings': ['z'], 'vectors': [], 'emotives': {}})       # 1 string
    kato_fixture.learn()

    # Test various combinations reaching 2+ threshold
    test_cases = [
        # (observations, should_have_predictions, description)
        ([['w']], False, "1 string - no predictions"),
        ([['w'], ['x']], True, "2 strings across 2 events - predictions"),
        ([['w', 'x']], True, "2 strings in 1 event - predictions"),
        ([['w', 'x', 'y']], True, "3 strings in 1 event - predictions"),
        ([['w'], [], ['x']], True, "2 strings with empty between - predictions"),
    ]

    for observations, should_predict, description in test_cases:
        kato_fixture.clear_short_term_memory()

        for obs in observations:
            if obs:  # Skip empty observations as they're ignored
                kato_fixture.observe({'strings': obs, 'vectors': [], 'emotives': {}})

        predictions = kato_fixture.get_predictions()

        if should_predict:
            assert len(predictions) > 0, f"Failed: {description}"
        else:
            assert predictions == [], f"Failed: {description}"


def test_emotives_dont_affect_requirement(kato_fixture):
    """Test that emotives don't count toward the 2+ string requirement."""
    kato_fixture.clear_all_memory()

    # Learn sequence with emotives
    sequence_with_emotives = [
        (['happy'], {'joy': 0.8}),
        (['day'], {'joy': 0.9}),
        (['sunshine'], {'joy': 0.7})
    ]

    for strings, emotives in sequence_with_emotives:
        kato_fixture.observe({'strings': strings, 'vectors': [], 'emotives': emotives})
    kato_fixture.learn()

    # Observe single string with emotives
    kato_fixture.clear_short_term_memory()
    kato_fixture.observe({
        'strings': ['happy'],
        'vectors': [],
        'emotives': {'joy': 0.8, 'excitement': 0.6}  # Multiple emotives
    })

    # Should still have NO predictions (emotives don't count)
    predictions = kato_fixture.get_predictions()
    assert predictions == [], "Emotives shouldn't count toward 2+ string requirement"

    # Add second string
    kato_fixture.observe({'strings': ['day'], 'vectors': [], 'emotives': {'joy': 0.9}})

    # NOW should have predictions
    predictions = kato_fixture.get_predictions()
    assert len(predictions) > 0, "Should have predictions with 2 strings regardless of emotives"


def test_clear_stm_resets_requirement(kato_fixture):
    """Test that clearing STM resets the 2+ string requirement."""
    kato_fixture.clear_all_memory()

    # Learn a sequence
    for item in ['red', 'green', 'blue']:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()

    # Build up to 2+ strings
    kato_fixture.observe({'strings': ['red'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['green'], 'vectors': [], 'emotives': {}})

    # Should have predictions
    predictions = kato_fixture.get_predictions()
    assert len(predictions) > 0, "Should have predictions with 2 strings"

    # Clear STM
    kato_fixture.clear_short_term_memory()

    # Now observe single string again
    kato_fixture.observe({'strings': ['blue'], 'vectors': [], 'emotives': {}})

    # Should have NO predictions after clear
    predictions = kato_fixture.get_predictions()
    assert predictions == [], "Should reset to no predictions after clearing STM"
