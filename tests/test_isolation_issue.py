"""Test to identify isolation issues."""

import requests
import time
import random

BASE_URL = "http://localhost:8000"

def test_instance(processor_id):
    """Test a specific processor instance."""
    print(f"\n=== Testing processor {processor_id} ===")
    
    # Clear all memory for this processor
    r = requests.post(f"{BASE_URL}/{processor_id}/clear-all-memory", json={})
    print(f"Clear result: {r.status_code}")
    
    # Learn a simple pattern
    for item in ['x', 'y', 'z']:
        r = requests.post(f"{BASE_URL}/{processor_id}/observe", 
                         json={'strings': [item], 'vectors': [], 'emotives': {}})
        print(f"Observe {item}: {r.status_code}")
    
    r = requests.post(f"{BASE_URL}/{processor_id}/learn", json={})
    result = r.json()
    pattern = result.get('pattern_name', result.get('message', ''))
    print(f"Learned pattern: {pattern}")
    
    # Clear STM and test predictions
    r = requests.post(f"{BASE_URL}/{processor_id}/clear-short-term-memory", json={})
    
    r = requests.post(f"{BASE_URL}/{processor_id}/observe", 
                     json={'strings': ['x'], 'vectors': [], 'emotives': {}})
    r = requests.post(f"{BASE_URL}/{processor_id}/observe", 
                     json={'strings': ['y'], 'vectors': [], 'emotives': {}})
    
    r = requests.get(f"{BASE_URL}/{processor_id}/predictions")
    predictions = r.json().get('message', [])
    print(f"Predictions: {len(predictions)}")
    
    return pattern, len(predictions)

# Test with different processor IDs
processor1 = f"test_proc_{random.randint(1000, 9999)}"
processor2 = f"test_proc_{random.randint(1000, 9999)}"

# First test - use kato-api (default)
pattern1, pred_count1 = test_instance("kato-api")

# Second test - use kato-api again
pattern2, pred_count2 = test_instance("kato-api")

print("\n=== Results ===")
print(f"Test 1: pattern={pattern1}, predictions={pred_count1}")
print(f"Test 2: pattern={pattern2}, predictions={pred_count2}")

# Test with unique processor IDs
print("\n=== Testing with unique processor IDs ===")
pattern3, pred_count3 = test_instance(processor1)
pattern4, pred_count4 = test_instance(processor2)
print(f"Unique ID 1: pattern={pattern3}, predictions={pred_count3}")
print(f"Unique ID 2: pattern={pattern4}, predictions={pred_count4}")