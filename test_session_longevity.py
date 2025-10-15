#!/usr/bin/env python3
"""
Test script to verify session longevity fix for long-running training.

This simulates the hierarchical training workflow:
- Creates a session with short TTL (60 seconds)
- Makes many observe_sequence() calls over 120+ seconds
- Verifies session stays alive throughout despite TTL expiration

Expected behavior with fix:
- Session auto-extends on every call
- Session never expires during active use
- No "Session not found" errors

Without fix:
- Session would expire after 60 seconds
- Subsequent calls would fail with "Session not found"
"""

import requests
import time
import sys

BASE_URL = "http://localhost:8000"
SESSION_TTL = 60  # 60 second TTL (much shorter than 3600 default)
TEST_DURATION = 150  # Run for 150 seconds (2.5x TTL)
CALL_INTERVAL = 5  # Make a call every 5 seconds

def create_session():
    """Create a session with short TTL for testing."""
    response = requests.post(
        f"{BASE_URL}/sessions",
        json={
            "node_id": "test_longevity",
            "ttl_seconds": SESSION_TTL,
            "session_config": {
                "max_pattern_length": 0,
                "recall_threshold": 0.1,
                "stm_mode": "CLEAR"
            }
        }
    )
    response.raise_for_status()
    data = response.json()
    return data["session_id"]

def check_session_exists(session_id):
    """Check if session still exists."""
    response = requests.get(f"{BASE_URL}/sessions/{session_id}/exists")
    if response.status_code == 200:
        data = response.json()
        return data.get("exists", False)
    return False

def observe_sequence(session_id, sentence_num):
    """Simulate observing a sentence (like hierarchical training)."""
    # Simulate tokenizing a sentence: 10-50 tokens
    tokens = [f"token_{sentence_num}_{i}" for i in range(30)]
    observations = [{"strings": [token]} for token in tokens]

    response = requests.post(
        f"{BASE_URL}/sessions/{session_id}/observe-sequence",
        json={
            "observations": observations,
            "learn_at_end": True,
            "learn_after_each": False,
            "clear_stm_between": False
        },
        timeout=30
    )
    response.raise_for_status()
    return response.json()

def main():
    print("=" * 80)
    print("Session Longevity Test")
    print("=" * 80)
    print(f"Session TTL: {SESSION_TTL} seconds")
    print(f"Test Duration: {TEST_DURATION} seconds ({TEST_DURATION / SESSION_TTL:.1f}x TTL)")
    print(f"Call Interval: {CALL_INTERVAL} seconds")
    print("=" * 80)
    print()

    # Create session
    print(f"[T+0s] Creating session with {SESSION_TTL}s TTL...")
    try:
        session_id = create_session()
        print(f"✓ Session created: {session_id}")
    except Exception as e:
        print(f"✗ Failed to create session: {e}")
        return 1

    print()
    start_time = time.time()
    sentence_num = 0
    errors = []

    # Run test for specified duration
    while True:
        elapsed = int(time.time() - start_time)
        if elapsed > TEST_DURATION:
            break

        # Make a call every CALL_INTERVAL seconds
        if elapsed % CALL_INTERVAL == 0:
            sentence_num += 1

            try:
                # Simulate training: observe a sentence
                print(f"[T+{elapsed}s] Processing sentence {sentence_num}...", end=" ", flush=True)
                result = observe_sequence(session_id, sentence_num)
                print(f"✓ OK (STM: {result['final_stm_length']})")

                # Verify session still exists
                if not check_session_exists(session_id):
                    error_msg = f"Session expired at T+{elapsed}s (after {elapsed / SESSION_TTL:.1f}x TTL)"
                    errors.append(error_msg)
                    print(f"✗ {error_msg}")
                    break

            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 404:
                    error_msg = f"Session not found at T+{elapsed}s (after {elapsed / SESSION_TTL:.1f}x TTL)"
                    errors.append(error_msg)
                    print(f"✗ {error_msg}")
                    break
                else:
                    error_msg = f"HTTP error at T+{elapsed}s: {e}"
                    errors.append(error_msg)
                    print(f"✗ {error_msg}")
            except Exception as e:
                error_msg = f"Error at T+{elapsed}s: {e}"
                errors.append(error_msg)
                print(f"✗ {error_msg}")

        time.sleep(1)

    final_elapsed = int(time.time() - start_time)
    print()
    print("=" * 80)
    print("Test Results")
    print("=" * 80)
    print(f"Total Duration: {final_elapsed} seconds")
    print(f"TTL Multiples: {final_elapsed / SESSION_TTL:.1f}x")
    print(f"Sentences Processed: {sentence_num}")
    print(f"Errors: {len(errors)}")

    if errors:
        print()
        print("FAILED - Errors encountered:")
        for error in errors:
            print(f"  - {error}")
        return 1
    else:
        print()
        print("SUCCESS - Session remained active throughout test!")
        print(f"✓ Session survived {final_elapsed / SESSION_TTL:.1f}x its TTL")
        print(f"✓ Auto-extension working correctly")
        return 0

if __name__ == "__main__":
    sys.exit(main())
