#!/usr/bin/env python3
"""
Stress test for vector operations to verify performance and reliability
of the new vector database architecture.
"""

import requests
import time
import random
import statistics
from typing import List, Dict, Any

BASE_URL = "http://localhost:8000"


def generate_random_vector(dim: int = 4) -> List[float]:
    """Generate a random vector of specified dimensions"""
    return [random.random() for _ in range(dim)]


def measure_time(func):
    """Decorator to measure execution time"""
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        elapsed = time.time() - start
        return result, elapsed
    return wrapper


@measure_time
def observe_vector(vector: List[float], label: str) -> Dict[str, Any]:
    """Observe a vector and return response"""
    observation = {
        'strings': [label],
        'vectors': [vector],
        'emotives': {'confidence': random.random()}
    }
    response = requests.post(f"{BASE_URL}/observe", json=observation)
    assert response.status_code == 200
    return response.json()


@measure_time
def learn_model() -> str:
    """Trigger learning and return model name"""
    response = requests.post(f"{BASE_URL}/learn")
    assert response.status_code == 200
    result = response.json()
    return result.get('message', result)


@measure_time
def get_predictions() -> List[Dict]:
    """Get predictions"""
    response = requests.get(f"{BASE_URL}/predictions")
    assert response.status_code == 200
    result = response.json()
    if isinstance(result, dict) and 'message' in result:
        return result['message']
    return result


def test_vector_performance():
    """Test vector operation performance"""
    print("\n1. PERFORMANCE TEST")
    print("=" * 50)
    
    # Clear memory
    requests.post(f"{BASE_URL}/clear-all-memory")
    
    # Test different vector sizes
    vector_sizes = [4, 16, 64, 128, 256]
    
    for size in vector_sizes:
        print(f"\nTesting {size}-dimensional vectors...")
        
        observe_times = []
        num_vectors = 50
        
        # Observe multiple vectors
        for i in range(num_vectors):
            vector = generate_random_vector(size)
            _, elapsed = observe_vector(vector, f"vec_{size}_{i}")
            observe_times.append(elapsed)
        
        # Learn model
        _, learn_time = learn_model()
        
        # Get predictions
        requests.post(f"{BASE_URL}/clear-working-memory")
        test_vector = generate_random_vector(size)
        observe_vector(test_vector, "test")
        _, predict_time = get_predictions()
        
        # Report results
        avg_observe = statistics.mean(observe_times)
        print(f"  Observe time: {avg_observe*1000:.2f}ms avg")
        print(f"  Learn time:   {learn_time*1000:.2f}ms")
        print(f"  Predict time: {predict_time*1000:.2f}ms")


def test_vector_scalability():
    """Test scalability with large number of vectors"""
    print("\n2. SCALABILITY TEST")
    print("=" * 50)
    
    # Clear memory
    requests.post(f"{BASE_URL}/clear-all-memory")
    
    vector_counts = [10, 50, 100, 200, 500]
    vector_dim = 16
    
    for count in vector_counts:
        print(f"\nTesting with {count} vectors...")
        
        start_batch = time.time()
        
        # Observe batch of vectors
        for i in range(count):
            vector = generate_random_vector(vector_dim)
            observe_vector(vector, f"batch_{count}_{i}")
        
        batch_time = time.time() - start_batch
        
        # Learn and measure
        _, learn_time = learn_model()
        
        # Test search performance
        search_times = []
        for _ in range(10):
            requests.post(f"{BASE_URL}/clear-working-memory")
            test_vector = generate_random_vector(vector_dim)
            observe_vector(test_vector, "search_test")
            _, search_time = get_predictions()
            search_times.append(search_time)
        
        avg_search = statistics.mean(search_times)
        
        print(f"  Total observe time: {batch_time:.2f}s")
        print(f"  Learn time:         {learn_time:.2f}s")
        print(f"  Avg search time:    {avg_search*1000:.2f}ms")
        print(f"  Vectors/second:     {count/batch_time:.1f}")


def test_vector_accuracy():
    """Test accuracy of vector similarity search"""
    print("\n3. ACCURACY TEST")
    print("=" * 50)
    
    # Clear memory
    requests.post(f"{BASE_URL}/clear-all-memory")
    
    # Create known vectors with specific patterns
    base_vectors = [
        ([1, 0, 0, 0], "x_axis"),
        ([0, 1, 0, 0], "y_axis"),
        ([0, 0, 1, 0], "z_axis"),
        ([0, 0, 0, 1], "w_axis"),
        ([1, 1, 0, 0], "xy_plane"),
        ([0, 1, 1, 0], "yz_plane"),
        ([1, 0, 0, 1], "xw_plane"),
    ]
    
    print("\nObserving base vectors...")
    for vector, label in base_vectors:
        observe_vector(vector, label)
    
    learn_model()
    
    # Test similar vectors
    test_cases = [
        ([0.9, 0.1, 0, 0], "x_axis"),      # Should match x_axis
        ([0.1, 0.9, 0.1, 0], "y_axis"),    # Should match y_axis
        ([0.7, 0.7, 0, 0], "xy_plane"),    # Should match xy_plane
    ]
    
    print("\nTesting similarity matching...")
    correct = 0
    for test_vector, expected in test_cases:
        requests.post(f"{BASE_URL}/clear-working-memory")
        observe_vector(test_vector, "test")
        predictions, _ = get_predictions()
        
        if predictions:
            # Check if expected label is in predictions
            pred_symbols = []
            for pred in predictions:
                if 'future' in pred:
                    for future_item in pred['future']:
                        if isinstance(future_item, list):
                            pred_symbols.extend(future_item)
            
            found = any(expected in str(s) for s in pred_symbols)
            if found:
                correct += 1
                print(f"  ✓ {test_vector[:2]}... correctly matched to {expected}")
            else:
                print(f"  ✗ {test_vector[:2]}... failed to match {expected}")
    
    accuracy = (correct / len(test_cases)) * 100
    print(f"\nAccuracy: {accuracy:.1f}%")


def test_vector_persistence():
    """Test vector persistence across multiple learning cycles"""
    print("\n4. PERSISTENCE TEST")
    print("=" * 50)
    
    # Clear memory
    requests.post(f"{BASE_URL}/clear-all-memory")
    
    models_created = []
    vectors_per_cycle = 10
    num_cycles = 5
    
    print(f"\nRunning {num_cycles} learning cycles...")
    
    for cycle in range(num_cycles):
        print(f"\nCycle {cycle + 1}:")
        
        # Add new vectors
        for i in range(vectors_per_cycle):
            vector = generate_random_vector(8)
            observe_vector(vector, f"cycle_{cycle}_vec_{i}")
        
        # Learn model
        model_name, learn_time = learn_model()
        models_created.append(model_name)
        print(f"  Created model: {model_name[:30]}...")
        print(f"  Learn time: {learn_time*1000:.2f}ms")
        
        # Clear working memory for next cycle
        requests.post(f"{BASE_URL}/clear-working-memory")
    
    # Check that all models are different
    unique_models = set(models_created)
    print(f"\nTotal models created: {len(models_created)}")
    print(f"Unique models: {len(unique_models)}")
    
    if len(unique_models) == len(models_created):
        print("✓ All models are unique (good persistence)")
    else:
        print("✗ Some models are duplicated (persistence issue)")


def test_vector_edge_cases():
    """Test edge cases and error handling"""
    print("\n5. EDGE CASES TEST")
    print("=" * 50)
    
    # Clear memory
    requests.post(f"{BASE_URL}/clear-all-memory")
    
    print("\nTesting edge cases...")
    
    # Test 1: Empty vector
    try:
        observe_vector([], "empty_vector")
        print("  ✓ Empty vector handled")
    except:
        print("  ✗ Empty vector failed")
    
    # Test 2: Very large vector
    try:
        large_vector = generate_random_vector(1000)
        observe_vector(large_vector, "large_vector")
        print("  ✓ 1000-dim vector handled")
    except:
        print("  ✗ Large vector failed")
    
    # Test 3: Zero vector
    try:
        zero_vector = [0.0] * 10
        observe_vector(zero_vector, "zero_vector")
        print("  ✓ Zero vector handled")
    except:
        print("  ✗ Zero vector failed")
    
    # Test 4: Negative values
    try:
        neg_vector = [-1.0, 0.5, -0.5, 1.0]
        observe_vector(neg_vector, "negative_vector")
        print("  ✓ Negative values handled")
    except:
        print("  ✗ Negative values failed")
    
    # Test 5: Multiple vectors in one observation
    try:
        obs = {
            'strings': ['multi_1', 'multi_2', 'multi_3'],
            'vectors': [
                [1, 0, 0],
                [0, 1, 0],
                [0, 0, 1]
            ],
            'emotives': {}
        }
        response = requests.post(f"{BASE_URL}/observe", json=obs)
        assert response.status_code == 200
        print("  ✓ Multiple vectors handled")
    except:
        print("  ✗ Multiple vectors failed")


if __name__ == "__main__":
    print("=" * 60)
    print("VECTOR STRESS TEST SUITE")
    print("Testing new vector database architecture")
    print("=" * 60)
    
    try:
        # Check connection
        r = requests.get(f"{BASE_URL}/ping")
        assert r.status_code == 200
        print("✓ KATO is running\n")
    except:
        print("ERROR: KATO is not running on port 8000")
        exit(1)
    
    # Run all tests
    start_time = time.time()
    
    test_vector_performance()
    test_vector_scalability()
    test_vector_accuracy()
    test_vector_persistence()
    test_vector_edge_cases()
    
    total_time = time.time() - start_time
    
    print("\n" + "=" * 60)
    print(f"✅ ALL STRESS TESTS COMPLETED in {total_time:.1f} seconds")
    print("=" * 60)