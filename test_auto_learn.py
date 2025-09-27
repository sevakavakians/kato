import requests
import json
import uuid

# Create a new session with unique user ID
unique_user = f"test-auto-learn-{uuid.uuid4().hex[:8]}"
session_resp = requests.post("http://localhost:8000/sessions", json={"user_id": unique_user})
session = session_resp.json()
session_id = session['session_id']
print(f"Created session: {session_id}")

# Clear STM 
clear_resp = requests.post(f"http://localhost:8000/sessions/{session_id}/clear-stm")
print(f"Cleared STM: {clear_resp.json()}")

# Set max_pattern_length to 3
config_resp = requests.post(
    f"http://localhost:8000/sessions/{session_id}/config",
    json={"config": {"max_pattern_length": 3}}
)
print(f"Config response status: {config_resp.status_code}")
print(f"Config response text: {config_resp.text}")
if config_resp.text:
    print(f"Set max_pattern_length: {config_resp.json()}")

# Get session config to verify
status_resp = requests.get(f"http://localhost:8000/sessions/{session_id}")
session_data = status_resp.json()
print(f"Session config after update: {session_data.get('session_config', {})}")

# Observe 3 events
for i in range(1, 4):
    obs_resp = requests.post(
        f"http://localhost:8000/sessions/{session_id}/observe",
        json={"strings": [f"auto{i}"], "vectors": [], "emotives": {}}
    )
    data = obs_resp.json()
    print(f"Observed auto{i}: STM length = {data.get('stm_length')}, auto_learned = {data.get('auto_learned_pattern')}")
    
    # After first observation, check processor's config
    if i == 1:
        import time
        time.sleep(0.5)  # Give processor time to initialize
        # Try to get the processor's actual config via a debug endpoint or logs

# Check STM after
stm_resp = requests.get(f"http://localhost:8000/sessions/{session_id}/stm")
stm = stm_resp.json()
print(f"\nFinal STM: {stm['stm']}")
print(f"STM length: {len(stm['stm'])}")
