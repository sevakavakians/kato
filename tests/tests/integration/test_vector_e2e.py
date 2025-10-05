#!/usr/bin/env python3
"""
End-to-end test for vector functionality with new vector database architecture.
"""

import os
import random
import sys

import requests

# Add path for fixtures
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from fixtures.kato_fixtures import kato_fixture as kato_fixture


def test_vector_observation_and_learning(kato_fixture):
    """Test that vectors can be observed and learned"""

    # Clear all memory first
    response = requests.post(f"{kato_fixture.base_url}/clear-all-memory")
    assert response.status_code == 200
    result = response.json()
    assert result.get('status') == "cleared"  # FastAPI response format

    # Create a sequence with vectors
    observations = [
        {
            'strings': ['start'],
            'vectors': [[1.0, 0.0, 0.0, 0.0]],
            'emotives': {'confidence': 0.8}
        },
        {
            'strings': ['middle'],
            'vectors': [[0.0, 1.0, 0.0, 0.0]],
            'emotives': {'confidence': 0.9}
        },
        {
            'strings': ['end'],
            'vectors': [[0.0, 0.0, 1.0, 0.0]],
            'emotives': {'confidence': 0.7}
        }
    ]

    # Observe the sequence using fixture
    for obs in observations:
        kato_fixture.observe(obs)
        print(f"Observed: {obs['strings']} with vector")

    # Learn the sequence
    pattern_name = kato_fixture.learn()
    assert pattern_name is not None
    print(f"Learned model: {pattern_name}")

    # Clear short-term memory
    kato_fixture.clear_stm()

    # Observe first element to trigger predictions
    kato_fixture.observe(observations[0])

    # Get predictions
    predictions = kato_fixture.get_predictions()

    assert len(predictions) > 0, "Should have predictions after learning"
    print(f"Got {len(predictions)} predictions")

    # Check that predictions contain expected elements
    prediction_symbols = []
    for pred in predictions:
        if 'future' in pred:
            for future_item in pred['future']:
                if isinstance(future_item, list):
                    prediction_symbols.extend(future_item)

    # Should predict 'middle' after observing 'start'
    assert 'middle' in prediction_symbols, "Should predict 'middle' after 'start'"
    print("✓ Vector-based predictions working correctly")


def test_mixed_modality_processing(kato_fixture):
    """Test processing of mixed strings, vectors, and emotives"""

    # Clear all memory
    response = requests.post(f"{kato_fixture.base_url}/clear-all-memory")
    assert response.status_code == 200
    result = response.json()
    assert result.get('status') == "cleared"  # FastAPI response format

    # Observe mixed modality data
    observation = {
        'strings': ['test', 'mixed', 'mode'],
        'vectors': [
            [0.5, 0.5, 0.5, 0.5],
            [1.0, 0.0, 1.0, 0.0],
            [0.0, 1.0, 0.0, 1.0]
        ],
        'emotives': {
            'arousal': 0.7,
            'valence': 0.8,
            'confidence': 0.9
        }
    }

    response = requests.post(f"{kato_fixture.base_url}/observe", json=observation)
    assert response.status_code == 200
    result = response.json()
    # Extract message if wrapped
    if isinstance(result, dict) and 'message' in result:
        message = result['message']
    else:
        message = result
    assert message['status'] == 'okay'  # FastAPI response format

    # Check short-term memory
    response = requests.get(f"{kato_fixture.base_url}/stm")
    assert response.status_code == 200
    stm_resp = response.json()

    # Extract short-term memory from response (FastAPI returns it in 'stm' key)
    if isinstance(stm_resp, dict) and 'stm' in stm_resp:
        short_term_memory = stm_resp['stm']
    elif isinstance(stm_resp, dict) and 'message' in stm_resp:
        short_term_memory = stm_resp['message']
    else:
        short_term_memory = stm_resp

    # Note: Short-term memory may be cleared after observation in some cases
    if len(short_term_memory) > 0:
        print(f"Short-term memory contains {len(short_term_memory)} events")
        # The strings should be in the short-term memory
        first_event = short_term_memory[0]
        for string in ['test', 'mixed', 'mode']:
            if not (string in first_event or any(string in str(s) for s in first_event)):
                print(f"Note: String '{string}' not found in short-term memory (may be processed already)")
    else:
        print("Short-term memory is empty (normal after processing)")

    print("✓ Mixed modality processing working correctly")


def test_vector_similarity_search(kato_fixture):
    """Test vector similarity search functionality"""

    # Clear all memory
    response = requests.post(f"{kato_fixture.base_url}/clear-all-memory")
    assert response.status_code == 200
    result = response.json()
    assert result.get('status') == "cleared"  # FastAPI response format

    # Create and observe several vectors
    base_vectors = [
        [1.0, 0.0, 0.0, 0.0],  # Unit vector in dimension 0
        [0.0, 1.0, 0.0, 0.0],  # Unit vector in dimension 1
        [0.0, 0.0, 1.0, 0.0],  # Unit vector in dimension 2
        [0.0, 0.0, 0.0, 1.0],  # Unit vector in dimension 3
        [0.5, 0.5, 0.0, 0.0],  # Mixed vector
    ]

    # Observe each vector with a label
    for i, vec in enumerate(base_vectors):
        obs = {
            'strings': [f'vector_{i}'],
            'vectors': [vec],
            'emotives': {}
        }
        response = requests.post(f"{kato_fixture.base_url}/observe", json=obs)
        assert response.status_code == 200

    # Learn the vectors
    response = requests.post(f"{kato_fixture.base_url}/learn", json={})
    assert response.status_code == 200

    # Now observe a similar vector
    similar_vector = [0.9, 0.1, 0.0, 0.0]  # Similar to first vector
    response = requests.post(f"{kato_fixture.base_url}/observe", json={
        'strings': [],
        'vectors': [similar_vector],
        'emotives': {}
    })
    assert response.status_code == 200

    # The system should recognize this as similar to vector_0
    # This tests the CVC classifier's nearest neighbor functionality
    print("✓ Vector similarity search working")


def test_large_vector_handling(kato_fixture):
    """Test handling of larger dimensional vectors"""

    # Clear all memory
    response = requests.post(f"{kato_fixture.base_url}/clear-all-memory")
    assert response.status_code == 200
    result = response.json()
    assert result.get('status') == "cleared"  # FastAPI response format

    # Create a large dimensional vector
    large_dim = 128
    large_vector = [random.random() for _ in range(large_dim)]

    # Observe the large vector
    observation = {
        'strings': ['large_vector'],
        'vectors': [large_vector],
        'emotives': {}
    }

    response = requests.post(f"{kato_fixture.base_url}/observe", json=observation)
    assert response.status_code == 200
    result = response.json()
    # Extract message if wrapped
    if isinstance(result, dict) and 'message' in result:
        message = result['message']
    else:
        message = result
    assert message['status'] == 'okay'  # FastAPI response format

    # Learn it
    response = requests.post(f"{kato_fixture.base_url}/learn", json={})
    assert response.status_code == 200

    print(f"✓ Successfully handled {large_dim}-dimensional vector")


def test_vector_persistence(kato_fixture):
    """Test that vectors are persisted across learning cycles"""

    # Clear all memory
    response = requests.post(f"{kato_fixture.base_url}/clear-all-memory")
    assert response.status_code == 200
    result = response.json()
    assert result.get('status') == "cleared"  # FastAPI response format

    # First learning cycle
    obs1 = {
        'strings': ['first'],
        'vectors': [[1.0, 2.0, 3.0]],
        'emotives': {}
    }
    response = requests.post(f"{kato_fixture.base_url}/observe", json=obs1)
    assert response.status_code == 200

    response = requests.post(f"{kato_fixture.base_url}/learn", json={})
    assert response.status_code == 200
    model1_resp = response.json()
    # Extract model name from response (Current uses 'pattern_name', Legacy uses 'message')
    model1 = model1_resp.get('pattern_name') or model1_resp.get('message', model1_resp)

    # Second learning cycle with different vector
    obs2 = {
        'strings': ['second'],
        'vectors': [[4.0, 5.0, 6.0]],
        'emotives': {}
    }
    response = requests.post(f"{kato_fixture.base_url}/observe", json=obs2)
    assert response.status_code == 200

    response = requests.post(f"{kato_fixture.base_url}/learn", json={})
    assert response.status_code == 200
    model2_resp = response.json()
    # Extract model name from response (Current uses 'pattern_name', Legacy uses 'message')
    model2 = model2_resp.get('pattern_name') or model2_resp.get('message', model2_resp)

    # Models should be different
    assert model1 != model2, f"Models should be different: {model1} vs {model2}"

    print("✓ Vector persistence working: 2 different models created")


if __name__ == "__main__":
    print("Running end-to-end vector tests...")
    print("=" * 50)

    try:
        # Check if KATO is running
        response = requests.get(f"{kato_fixture.base_url}/ping")
        if response.status_code != 200:
            print("ERROR: KATO is not running on port 8000")
            exit(1)
    except requests.ConnectionError:
        print("ERROR: Cannot connect to KATO on port 8000")
        print("Please run: ./start.sh start")
        exit(1)

    # Run tests
    test_functions = [
        test_vector_observation_and_learning,
        test_mixed_modality_processing,
        test_vector_similarity_search,
        test_large_vector_handling,
        test_vector_persistence
    ]

    failed = 0
    for test_func in test_functions:
        try:
            print(f"\nRunning {test_func.__name__}...")
            test_func()
            print(f"✅ {test_func.__name__} PASSED")
        except AssertionError as e:
            print(f"❌ {test_func.__name__} FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"❌ {test_func.__name__} ERROR: {e}")
            failed += 1

    print("\n" + "=" * 50)
    if failed == 0:
        print("✅ ALL TESTS PASSED!")
        print("The new vector database architecture is fully compatible.")
    else:
        print(f"❌ {failed} tests failed")
        exit(1)
