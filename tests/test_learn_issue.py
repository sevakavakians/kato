import requests
import time

BASE_URL = "http://localhost:8000/kato-api"

for test_num in range(3):
    print(f"\n=== Test {test_num + 1} ===")
    
    # Clear all
    r = requests.post(f"{BASE_URL}/clear-all-memory", json={})
    print(f"Clear: {r.status_code}")
    
    # Observe some strings
    for item in ['x', 'y', 'z']:
        r = requests.post(f"{BASE_URL}/observe", json={'strings': [item], 'vectors': [], 'emotives': {}})
        print(f"Observe {item}: {r.status_code}")
    
    # Learn
    r = requests.post(f"{BASE_URL}/learn", json={})
    result = r.json()
    pattern = result.get('pattern_name', result.get('message', ''))
    print(f"Learn result: {result}")
    print(f"Pattern: {pattern}")
    
    # Small delay
    time.sleep(0.1)
