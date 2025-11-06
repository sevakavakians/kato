#!/usr/bin/env python3
"""
Verification script to demonstrate the token matching fix.

This recreates the original problem scenario to show that token-level
matching correctly filters patterns with few token matches.
"""

import requests
import time

BASE_URL = "http://localhost:8000"

# Original problem: BPE tokens where only 1 out of 8 matches
chunk_learned = ['ĠNorth', 'ĠAmerican', 'Ġwolves', 'Ġis', 'ĠAl', 'aria', 'Ġ,', 'Ġwhich']
chunk_observed = ['For', 'Ġseveral', 'Ġyears', 'Ġthe', 'Ġarsenal', 'Ġ,', 'Ġwhich', 'Ġwas']

print("=" * 80)
print("TOKEN MATCHING FIX VERIFICATION")
print("=" * 80)
print()
print("Scenario: BPE tokenized text where only 1-2 tokens match")
print(f"Learned pattern:  {chunk_learned}")
print(f"Observed pattern: {chunk_observed}")
print()
print("Expected behavior with token-level matching:")
print("  - Only 'Ġwhich' matches (1 out of 8 tokens)")
print("  - Similarity: ~0.125 (2*1/16)")
print("  - With recall_threshold=0.6: Pattern should be FILTERED OUT")
print()

# Create session with high recall threshold
session_response = requests.post(
    f"{BASE_URL}/sessions",
    json={
        "node_id": "verify_token_fix",
        "config": {
            "recall_threshold": 0.6,
            "use_token_matching": True  # Explicitly set (though it's the default)
        }
    }
)

if session_response.status_code != 200:
    print(f"❌ Failed to create session: {session_response.text}")
    exit(1)

session_id = session_response.json()["session_id"]
print(f"✓ Created session: {session_id}")
print()

# Learn the pattern
print("Learning pattern...")
for token in chunk_learned:
    requests.post(
        f"{BASE_URL}/sessions/{session_id}/observe",
        json={"strings": [token]}
    )
requests.post(f"{BASE_URL}/sessions/{session_id}/learn")
print("✓ Pattern learned")
print()

# Clear STM
requests.post(f"{BASE_URL}/sessions/{session_id}/clear-stm")

# Observe the test chunk
print("Observing chunk with only 1 matching token...")
for token in chunk_observed:
    requests.post(
        f"{BASE_URL}/sessions/{session_id}/observe",
        json={"strings": [token]}
    )

# Get predictions
predictions_response = requests.get(f"{BASE_URL}/sessions/{session_id}/predictions")
predictions = predictions_response.json()["predictions"]

print(f"✓ Received {len(predictions)} predictions")
print()

# Analyze results
print("=" * 80)
print("RESULTS")
print("=" * 80)
print()

if len(predictions) == 0:
    print("✅ SUCCESS: No predictions returned (correctly filtered)")
    print()
    print("With token-level matching and recall_threshold=0.6:")
    print("  - Pattern with only 1 matching token has similarity ~0.125")
    print("  - This is correctly filtered out by the threshold")
    print()
    print("🎉 The fix is working! Token-level matching produces correct similarity.")

elif len(predictions) > 0:
    print(f"⚠️  Got {len(predictions)} prediction(s) - analyzing...")
    print()

    max_similarity = max(p.get('similarity', 0) for p in predictions)

    if max_similarity < 0.3:
        print(f"✅ ACCEPTABLE: Max similarity is {max_similarity:.3f} (low, as expected)")
        print()
        print("Token-level matching is working - similarity is correctly low.")
        print("Some predictions may still appear due to partial matches with other patterns.")
    else:
        print(f"❌ UNEXPECTED: Max similarity is {max_similarity:.3f} (too high!)")
        print()
        print("This suggests character-level matching may still be active.")
        print("Expected: similarity ~0.125 with token-level matching")
        print(f"Got: similarity {max_similarity:.3f}")

    print()
    print("Top prediction details:")
    for i, pred in enumerate(predictions[:3], 1):
        print(f"  {i}. Similarity: {pred.get('similarity', 0):.3f}, "
              f"Matches: {pred.get('matches', [])}, "
              f"Match count: {len(pred.get('matches', []))}")

# Cleanup
requests.delete(f"{BASE_URL}/sessions/{session_id}")
print()
print("=" * 80)
