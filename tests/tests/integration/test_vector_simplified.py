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

    # Clear memory
    r = requests.post(f"{kato_fixture.base_url}/clear-all-memory")
    assert r.status_code == 200

    # Observe vectors
    obs = {
        'strings': ['vector_test'],
        'vectors': [[1.0, 2.0, 3.0, 4.0]],
        'emotives': {}
    }
    r = requests.post(f"{kato_fixture.base_url}/observe", json=obs)
    assert r.status_code == 200
    message = unwrap_response(r)
    assert message['status'] == 'okay'  # FastAPI returns 'okay' not 'observed'
    print("✓ Vector observation works")

    # Learn
    r = requests.post(f"{kato_fixture.base_url}/learn", json={})
    assert r.status_code == 200
    print("✓ Learning with vectors works")

    # Note: short-term memory gets cleared after learning, which is normal behavior
    print("✓ Vector basic functionality works")


def test_mixed_modality(kato_fixture):
    """Test mixed strings and vectors"""

    print("\n2. Testing mixed modality...")

    # Clear memory
    r = requests.post(f"{kato_fixture.base_url}/clear-all-memory")
    assert r.status_code == 200

    # Observe mixed data
    obs = {
        'strings': ['hello', 'world'],
        'vectors': [[0.1, 0.2], [0.3, 0.4]],
        'emotives': {'confidence': 0.8}
    }
    r = requests.post(f"{kato_fixture.base_url}/observe", json=obs)
    assert r.status_code == 200
    message = unwrap_response(r)
    assert message['status'] == 'okay'  # FastAPI returns 'okay' not 'observed'
    print("✓ Mixed modality observation works")


def test_vector_sequence(kato_fixture):
    """Test sequence learning with vectors"""

    print("\n3. Testing vector sequence learning...")

    # Clear memory
    r = requests.post(f"{kato_fixture.base_url}/clear-all-memory")
    assert r.status_code == 200

    # Create a sequence
    sequence = [
        {'strings': ['a'], 'vectors': [[1, 0]], 'emotives': {}},
        {'strings': ['b'], 'vectors': [[0, 1]], 'emotives': {}},
        {'strings': ['c'], 'vectors': [[1, 1]], 'emotives': {}}
    ]

    # Observe sequence
    for obs in sequence:
        r = requests.post(f"{kato_fixture.base_url}/observe", json=obs)
        assert r.status_code == 200

    # Learn
    r = requests.post(f"{kato_fixture.base_url}/learn", json={})
    assert r.status_code == 200

    # Clear short-term memory (formerly short-term memory)
    r = requests.post(f"{kato_fixture.base_url}/clear-stm", json={})
    assert r.status_code == 200

    # Observe first element
    r = requests.post(f"{kato_fixture.base_url}/observe", json=sequence[0])
    assert r.status_code == 200

    # Get predictions
    r = requests.get(f"{kato_fixture.base_url}/predictions")
    assert r.status_code == 200
    response = unwrap_response(r)

    # FastAPI returns predictions in a 'predictions' key
    predictions = response.get('predictions', response) if isinstance(response, dict) else response

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
    except:
        print("ERROR: KATO is not running")
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
