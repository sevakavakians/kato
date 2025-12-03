#!/usr/bin/env python3
"""
Test script using httpx instead of aiohttp.
This will help determine if the issue is client-specific.
"""
import asyncio
import httpx
import sys

async def create_sessions():
    """Create 10 test sessions"""
    async with httpx.AsyncClient() as client:
        session_ids = []
        for i in range(10):
            response = await client.post(
                "http://localhost:8000/sessions",
                json={"node_id": f"test_httpx_{i}", "ttl_seconds": 3600}
            )
            data = response.json()
            session_ids.append(data["session_id"])
            print(f"Created session {i}: {data['session_id']}")
        return session_ids


async def test_concurrent_observe(session_ids):
    """Test 50 concurrent observe requests with httpx"""
    # Configure httpx client with high limits
    limits = httpx.Limits(max_keepalive_connections=100, max_connections=200)
    timeout = httpx.Timeout(60.0)

    async with httpx.AsyncClient(limits=limits, timeout=timeout) as client:
        # Track results
        success_count = 0
        error_count = 0
        errors = []

        async def observe_once(session_id, obs_num):
            """Make a single observe request"""
            nonlocal success_count, error_count
            try:
                response = await client.post(
                    f"http://localhost:8000/sessions/{session_id}/observe",
                    json={"strings": [f"obs_{obs_num}"], "vectors": [], "emotives": {}}
                )
                if response.status_code == 200:
                    success_count += 1
                    print(f"✓ Success: {session_id[-8:]} obs#{obs_num}")
                    return True
                else:
                    error_count += 1
                    errors.append(f"HTTP {response.status_code}: {session_id[-8:]} obs#{obs_num} - {response.text[:100]}")
                    print(f"✗ Failed: {session_id[-8:]} obs#{obs_num} - HTTP {response.status_code}")
                    return False
            except Exception as e:
                error_count += 1
                errors.append(f"Exception: {session_id[-8:]} obs#{obs_num} - {type(e).__name__}: {str(e)[:100]}")
                print(f"✗ Exception: {session_id[-8:]} obs#{obs_num} - {type(e).__name__}: {e}")
                return False

        # Create 50 concurrent tasks (10 sessions × 5 observations each)
        tasks = []
        for i, session_id in enumerate(session_ids):
            for j in range(5):
                task = observe_once(session_id, j)
                tasks.append(task)

        print(f"\n🚀 Starting {len(tasks)} concurrent observe requests with httpx...")
        results = await asyncio.gather(*tasks)

        print(f"\n" + "="*60)
        print(f"RESULTS (httpx client):")
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


async def main():
    print("="*60)
    print("Testing concurrent httpx requests to KATO")
    print("="*60)

    # Create sessions
    print("\n📝 Creating 10 test sessions...")
    session_ids = await create_sessions()

    # Test concurrent observe
    print(f"\n🧪 Testing concurrent observe requests...")
    success, errors = await test_concurrent_observe(session_ids)

    # Exit with error code if there were failures
    if errors > 0:
        sys.exit(1)
    else:
        print("\n✅ All tests passed!")
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
