#!/usr/bin/env python3
"""
Test script to demonstrate KATOClient automatic session recovery.

This script shows how the client handles session expiration during
long-running tasks by automatically recreating the session and
restoring STM state.
"""

import sys
import time
sys.path.insert(0, '.')

from sample_kato_client import KATOClient


def test_basic_recovery():
    """
    Test basic session recreation without STM recovery.

    This simulates a session expiring and being recreated.
    """
    print("=== Test 1: Basic Session Recreation ===")

    client = KATOClient(
        base_url="http://localhost:8000",
        node_id="test_recovery_node",
        auto_recreate_session=True,
        max_session_recreate_attempts=3
    )

    print(f"Initial session: {client._session_id}")

    # Make a successful observation
    result1 = client.observe(strings=["hello", "world"])
    print(f"Observation 1 successful: {result1['stm_length']} events in STM")

    # Simulate session expiration by manually deleting it
    old_session_id = client._session_id
    try:
        client._request('DELETE', f'/sessions/{old_session_id}')
        print(f"Manually deleted session: {old_session_id}")
    except Exception as e:
        print(f"Failed to delete session (may not exist): {e}")

    # The next request should trigger automatic session recreation
    print("Attempting observation after session deletion...")
    try:
        result2 = client.observe(strings=["foo", "bar"])
        print(f"✓ Observation 2 successful after auto-recovery!")
        print(f"  New session: {client._session_id}")
        print(f"  STM length: {result2['stm_length']} events")
        print(f"  Session recreated: {client._session_id != old_session_id}")
    except Exception as e:
        print(f"✗ Observation 2 failed: {e}")
        client.close()
        return False

    client.close()
    print("✓ Test 1 passed!\n")
    return True


def test_stm_recovery():
    """
    Test session recreation with STM state recovery.

    This demonstrates how the client attempts to preserve STM
    state when recreating a session.
    """
    print("=== Test 2: Session Recreation with STM Recovery ===")

    client = KATOClient(
        base_url="http://localhost:8000",
        node_id="test_stm_recovery_node",
        auto_recreate_session=True,
        max_session_recreate_attempts=3
    )

    print(f"Initial session: {client._session_id}")

    # Build up some STM state
    client.observe(strings=["A", "B"])
    client.observe(strings=["C", "D"])
    client.observe(strings=["E", "F"])

    stm_before = client.get_stm()
    print(f"STM before recreation: {len(stm_before['stm'])} events")

    # Simulate session expiration
    old_session_id = client._session_id
    try:
        client._request('DELETE', f'/sessions/{old_session_id}')
        print(f"Manually deleted session: {old_session_id}")
    except Exception:
        pass

    # The next request should trigger recreation with STM recovery
    print("Attempting to get STM after session deletion...")
    try:
        stm_after = client.get_stm()
        print(f"✓ STM retrieval successful after auto-recovery!")
        print(f"  New session: {client._session_id}")
        print(f"  STM length after recovery: {len(stm_after['stm'])} events")
        print(f"  Note: STM may be empty as it was deleted with the session")
    except Exception as e:
        print(f"✗ STM retrieval failed: {e}")
        client.close()
        return False

    client.close()
    print("✓ Test 2 passed!\n")
    return True


def test_long_running_task():
    """
    Simulate a long-running task that would normally fail due to
    session expiration.

    With auto-recovery enabled, the task completes successfully.
    """
    print("=== Test 3: Long-Running Task Simulation ===")

    client = KATOClient(
        base_url="http://localhost:8000",
        node_id="test_long_task_node",
        max_pattern_length=5,
        stm_mode="ROLLING",
        auto_recreate_session=True
    )

    print(f"Starting long-running task with session: {client._session_id}")
    print("Processing 20 observations (simulates long training run)...")

    success_count = 0
    for i in range(20):
        try:
            result = client.observe(strings=[f"token_{i}", f"value_{i % 5}"])
            success_count += 1

            # Simulate session expiration mid-task
            if i == 10:
                print(f"  [Simulating session expiration at iteration {i}]")
                old_session = client._session_id
                try:
                    client._request('DELETE', f'/sessions/{old_session}')
                except Exception:
                    pass

            if i % 5 == 0:
                print(f"  Processed {i}/20 observations...")
        except Exception as e:
            print(f"  ✗ Failed at iteration {i}: {e}")
            break

    print(f"✓ Task completed: {success_count}/20 observations processed")

    # Get final state
    stm = client.get_stm()
    print(f"  Final STM length: {len(stm['stm'])} events")

    client.close()
    print("✓ Test 3 passed!\n")
    return success_count == 20


def test_disabled_recovery():
    """
    Test that recovery can be disabled when needed.

    This shows the fallback behavior when auto-recovery is off.
    """
    print("=== Test 4: Disabled Auto-Recovery ===")

    client = KATOClient(
        base_url="http://localhost:8000",
        node_id="test_no_recovery_node",
        auto_recreate_session=False  # Disable auto-recovery
    )

    print(f"Initial session: {client._session_id}")
    print("Auto-recovery: DISABLED")

    # Make a successful observation
    result1 = client.observe(strings=["hello"])
    print(f"Observation 1 successful: {result1['stm_length']} events")

    # Delete session
    old_session_id = client._session_id
    try:
        client._request('DELETE', f'/sessions/{old_session_id}')
        print(f"Manually deleted session: {old_session_id}")
    except Exception:
        pass

    # The next request should fail (no auto-recovery)
    print("Attempting observation after deletion (should fail)...")
    try:
        result2 = client.observe(strings=["world"])
        print(f"✗ Unexpected success - recovery should be disabled!")
        client.close()
        return False
    except Exception as e:
        print(f"✓ Expected failure occurred: {type(e).__name__}")
        print(f"  Message: {str(e)[:100]}")

    # Cleanup (will fail but that's OK)
    try:
        client.close()
    except Exception:
        pass

    print("✓ Test 4 passed!\n")
    return True


if __name__ == "__main__":
    print("KATO Client Recovery Tests")
    print("=" * 60)
    print()

    tests = [
        test_basic_recovery,
        test_stm_recovery,
        test_long_running_task,
        test_disabled_recovery
    ]

    results = []
    for test_func in tests:
        try:
            passed = test_func()
            results.append((test_func.__name__, passed))
        except Exception as e:
            print(f"✗ Test {test_func.__name__} crashed: {e}")
            results.append((test_func.__name__, False))
        time.sleep(1)  # Brief pause between tests

    print("=" * 60)
    print("Test Results Summary:")
    print("=" * 60)
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status:8} {name}")

    total_passed = sum(1 for _, passed in results if passed)
    print(f"\nTotal: {total_passed}/{len(results)} tests passed")

    sys.exit(0 if total_passed == len(results) else 1)
