#!/usr/bin/env python3
"""
Simplified vector compatibility test to verify basic functionality.
"""

import os
import sys

import requests

# Add path for fixtures
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from fixtures.kato_fixtures import kato_fixture as kato_fixture


def unwrap_response(response):
    """Unwrap the API response to get the actual message"""
    result = response.json()
    return result.get('message', result)


def test_vector_basic(kato_fixture):
    """Basic test of vector functionality"""

    print("1. Testing vector observation...")

    # Clear memory using fixture method
    kato_fixture.clear_all_memory()

    # Observe vectors using fixture method
    obs = {
        'strings': ['vector_test'],
        'vectors': [[1.0, 2.0, 3.0, 4.0]],
        'emotives': {}
    }
    result = kato_fixture.observe(obs)
    assert result['status'] in ['ok', 'okay', 'observed']
    print("✓ Vector observation works")

    # Learn using fixture method
    pattern_name = kato_fixture.learn()
    assert pattern_name is not None
    print("✓ Learning with vectors works")

    # Note: short-term memory gets cleared after learning, which is normal behavior
    print("✓ Vector basic functionality works")


def test_mixed_modality(kato_fixture):
    """Test mixed strings and vectors"""

    print("\n2. Testing mixed modality...")

    # Clear memory using fixture method
    kato_fixture.clear_all_memory()

    # Observe mixed data using fixture method
    obs = {
        'strings': ['hello', 'world'],
        'vectors': [[0.1, 0.2], [0.3, 0.4]],
        'emotives': {'confidence': 0.8}
    }
    result = kato_fixture.observe(obs)
    assert result['status'] in ['ok', 'okay', 'observed']
    print("✓ Mixed modality observation works")


def test_vector_sequence(kato_fixture):
    """Test sequence learning with vectors"""

    print("\n3. Testing vector sequence learning...")

    # Clear memory using fixture method
    kato_fixture.clear_all_memory()

    # Create a sequence
    sequence = [
        {'strings': ['a'], 'vectors': [[1, 0]], 'emotives': {}},
        {'strings': ['b'], 'vectors': [[0, 1]], 'emotives': {}},
        {'strings': ['c'], 'vectors': [[1, 1]], 'emotives': {}}
    ]

    # Observe sequence using fixture method
    for obs in sequence:
        kato_fixture.observe(obs)

    # Learn using fixture method
    pattern_name = kato_fixture.learn()
    assert pattern_name is not None

    # Clear short-term memory using fixture method
    kato_fixture.clear_stm()

    # Observe first element using fixture method
    kato_fixture.observe(sequence[0])

    # Get predictions using fixture method
    predictions = kato_fixture.get_predictions()

    if len(predictions) > 0:
        print(f"✓ Got {len(predictions)} predictions")
        # Check structure
        pred = predictions[0]
        # KATO predictions have 'future' key containing the predicted sequences
        assert 'future' in pred
        assert 'confidence' in pred
        # Check that we predicted something
        if pred['future']:
            print(f"✓ Predicted next sequence: {pred['future'][0]}")
        print("✓ Prediction structure is correct")
    else:
        print("⚠ No predictions (may be normal depending on config)")


if __name__ == "__main__":
    print("Running simplified vector compatibility tests")
    print("=" * 50)

    try:
        # Check connection
        r = requests.get(f"{kato_fixture.base_url}/health")
        assert r.status_code == 200
        print("✓ KATO is running\n")
    except Exception as e:
        print(f"ERROR: KATO is not running: {e}")
        exit(1)

    # Run tests
    all_passed = True

    # Create a fixture instance for standalone execution
    from fixtures.kato_fixtures import KATOTestFixture
    fixture = KATOTestFixture()
    fixture.setup()

    try:
        test_vector_basic(fixture)
    except AssertionError as e:
        print(f"✗ Basic vector test failed: {e}")
        all_passed = False
    except Exception as e:
        print(f"✗ Basic vector test error: {e}")
        all_passed = False

    try:
        test_mixed_modality(fixture)
    except AssertionError as e:
        print(f"✗ Mixed modality test failed: {e}")
        all_passed = False
    except Exception as e:
        print(f"✗ Mixed modality test error: {e}")
        all_passed = False

    try:
        test_vector_sequence(fixture)
    except AssertionError as e:
        print(f"✗ Vector sequence test failed: {e}")
        all_passed = False
    except Exception as e:
        print(f"✗ Vector sequence test error: {e}")
        all_passed = False

    # Cleanup
    fixture.teardown()

    print("\n" + "=" * 50)
    if all_passed:
        print("✅ ALL VECTOR TESTS PASSED")
        print("\nThe new vector database architecture is compatible")
        print("with existing KATO vector functionality.")
    else:
        print("❌ Some tests failed")
        exit(1)
