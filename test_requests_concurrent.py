#!/usr/bin/env python3
"""
Test script using requests library with ThreadPoolExecutor.
This tests with synchronous HTTP client to see if async is the issue.
"""
import requests
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

def create_sessions():
    """Create 10 test sessions"""
    session_ids = []
    for i in range(10):
        response = requests.post(
            "http://localhost:8000/sessions",
            json={"node_id": f"test_requests_{i}", "ttl_seconds": 3600}
        )
        data = response.json()
        session_ids.append(data["session_id"])
        print(f"Created session {i}: {data['session_id']}")
    return session_ids


def observe_once(session_id, obs_num):
    """Make a single observe request"""
    try:
        response = requests.post(
            f"http://localhost:8000/sessions/{session_id}/observe",
            json={"strings": [f"obs_{obs_num}"], "vectors": [], "emotives": {}},
            timeout=60
        )
        if response.status_code == 200:
            print(f"✓ Success: {session_id[-8:]} obs#{obs_num}")
            return True, None
        else:
            error = f"HTTP {response.status_code}: {session_id[-8:]} obs#{obs_num} - {response.text[:100]}"
            print(f"✗ Failed: {session_id[-8:]} obs#{obs_num} - HTTP {response.status_code}")
            return False, error
    except Exception as e:
        error = f"Exception: {session_id[-8:]} obs#{obs_num} - {type(e).__name__}: {str(e)[:100]}"
        print(f"✗ Exception: {session_id[-8:]} obs#{obs_num} - {type(e).__name__}: {e}")
        return False, error


def test_concurrent_observe(session_ids):
    """Test 50 concurrent observe requests with ThreadPoolExecutor"""
    # Track results
    success_count = 0
    error_count = 0
    errors = []

    # Create tasks list
    tasks = []
    for i, session_id in enumerate(session_ids):
        for j in range(5):
            tasks.append((session_id, j))

    print(f"\n🚀 Starting {len(tasks)} concurrent observe requests with requests library...")

    # Use ThreadPoolExecutor for concurrent requests
    with ThreadPoolExecutor(max_workers=50) as executor:
        # Submit all tasks
        future_to_task = {
            executor.submit(observe_once, session_id, obs_num): (session_id, obs_num)
            for session_id, obs_num in tasks
        }

        # Collect results
        for future in as_completed(future_to_task):
            success, error = future.result()
            if success:
                success_count += 1
            else:
                error_count += 1
                if error:
                    errors.append(error)

    print(f"\n" + "="*60)
    print(f"RESULTS (requests library with ThreadPoolExecutor):")
    print(f"  Total requests: {len(tasks)}")
    print(f"  Successful: {success_count}")
    print(f"  Failed: {error_count}")
    print(f"  Success rate: {success_count/len(tasks)*100:.1f}%")
    print("="*60)

    if errors:
        print(f"\n❌ First 10 errors:")
        for error in errors[:10]:
            print(f"  - {error}")

    return success_count, error_count


def main():
    print("="*60)
    print("Testing concurrent requests library to KATO")
    print("="*60)

    # Create sessions
    print("\n📝 Creating 10 test sessions...")
    session_ids = create_sessions()

    # Test concurrent observe
    print(f"\n🧪 Testing concurrent observe requests...")
    success, errors = test_concurrent_observe(session_ids)

    # Exit with error code if there were failures
    if errors > 0:
        sys.exit(1)
    else:
        print("\n✅ All tests passed!")
        sys.exit(0)


if __name__ == "__main__":
    main()
