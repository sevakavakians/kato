import requests

BASE_URL = "http://localhost:8000/kato-api"

# Learn a pattern
print("Learning pattern...")
for item in ['a', 'b', 'c']:
    r = requests.post(f"{BASE_URL}/observe", json={'strings': [item], 'vectors': [], 'emotives': {}})
r = requests.post(f"{BASE_URL}/learn", json={})
print("Learned a pattern")

# Get patterns before clear
r = requests.get(f"{BASE_URL}/patterns")
if r.status_code == 200:
    patterns_before = r.json().get('message', [])
    print(f"Patterns before clear: {len(patterns_before) if isinstance(patterns_before, list) else 'N/A'}")

# Clear all memory
print("\nClearing all memory...")
r = requests.post(f"{BASE_URL}/clear-all-memory", json={})
print(f"Clear response: {r.json()}")

# Check STM after clear
r = requests.get(f"{BASE_URL}/short-term-memory")
stm = r.json()['message']
print(f"STM after clear: {stm}")

# Try to get predictions with empty STM
r = requests.get(f"{BASE_URL}/predictions")
predictions = r.json()['message']
print(f"Predictions after clear: {len(predictions)}")

# Check if patterns still exist
r = requests.get(f"{BASE_URL}/patterns")
if r.status_code == 200:
    patterns_after = r.json().get('message', [])
    print(f"Patterns after clear: {len(patterns_after) if isinstance(patterns_after, list) else 'N/A'}")
