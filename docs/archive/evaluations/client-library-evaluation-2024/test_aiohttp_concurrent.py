#!/usr/bin/env python3
"""
Test script to debug aiohttp concurrent request behavior.
This will help identify if the issue is client-side or server-side.
"""
import asyncio
import aiohttp
import sys

async def create_sessions():
    """Create 10 test sessions"""
    async with aiohttp.ClientSession() as session:
        session_ids = []
        for i in range(10):
            async with session.post(
                "http://localhost:8000/sessions",
                json={"node_id": f"test_debug_{i}", "ttl_seconds": 3600}
            ) as resp:
                data = await resp.json()
                session_ids.append(data["session_id"])
                print(f"Created session {i}: {data['session_id']}")
        return session_ids


async def test_concurrent_observe(session_ids):
    """Test 50 concurrent observe requests (10 sessions × 5 observations each)"""
    connector = aiohttp.TCPConnector(
        limit=200,
        limit_per_host=100,
        ttl_dns_cache=300,
        use_dns_cache=True,
        keepalive_timeout=30,
        enable_cleanup_closed=True,
    )
    timeout = aiohttp.ClientTimeout(total=60)

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        # Track results
        success_count = 0
        error_count = 0
        errors = []

        async def observe_once(session_id, obs_num):
            """Make a single observe request"""
            nonlocal success_count, error_count
            try:
                async with session.post(
                    f"http://localhost:8000/sessions/{session_id}/observe",
                    json={"strings": [f"obs_{obs_num}"], "vectors": [], "emotives": {}}
                ) as resp:
                    if resp.status == 200:
                        success_count += 1
                        print(f"✓ Success: {session_id[-8:]} obs#{obs_num}")
                        return True
                    else:
                        error_count += 1
                        text = await resp.text()
                        errors.append(f"HTTP {resp.status}: {session_id[-8:]} obs#{obs_num} - {text[:100]}")
                        print(f"✗ Failed: {session_id[-8:]} obs#{obs_num} - HTTP {resp.status}")
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

        print(f"\n🚀 Starting {len(tasks)} concurrent observe requests...")
        results = await asyncio.gather(*tasks)

        print(f"\n" + "="*60)
        print(f"RESULTS:")
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
    print("Testing concurrent aiohttp requests to KATO")
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
