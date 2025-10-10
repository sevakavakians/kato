#!/usr/bin/env python3
"""
Test script with retry logic for concurrent requests.
This implements exponential backoff retry to handle transient 404 errors.
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


async def observe_with_retry(session, session_id, obs_num, max_retries=3):
    """
    Make an observe request with exponential backoff retry.

    Args:
        session: aiohttp ClientSession
        session_id: Session ID to observe in
        obs_num: Observation number
        max_retries: Maximum number of retry attempts (default: 3)

    Returns:
        tuple: (success: bool, attempts: int, error: str or None)
    """
    for attempt in range(max_retries):
        try:
            async with session.post(
                f"http://localhost:8000/sessions/{session_id}/observe",
                json={"strings": [f"obs_{obs_num}"], "vectors": [], "emotives": {}}
            ) as resp:
                if resp.status == 200:
                    return True, attempt + 1, None
                elif resp.status == 404 and attempt < max_retries - 1:
                    # Retry on 404 with exponential backoff
                    backoff_ms = 50 * (2 ** attempt)  # 50ms, 100ms, 200ms
                    await asyncio.sleep(backoff_ms / 1000)
                    continue
                else:
                    # Non-retryable error or max retries reached
                    text = await resp.text()
                    return False, attempt + 1, f"HTTP {resp.status}: {text[:100]}"
        except Exception as e:
            if attempt < max_retries - 1:
                # Retry on exception with exponential backoff
                backoff_ms = 50 * (2 ** attempt)
                await asyncio.sleep(backoff_ms / 1000)
                continue
            else:
                return False, attempt + 1, f"{type(e).__name__}: {str(e)[:100]}"

    return False, max_retries, "Max retries exceeded"


async def test_concurrent_observe_with_retry(session_ids):
    """Test 50 concurrent observe requests with retry logic"""
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
        retry_stats = {1: 0, 2: 0, 3: 0}  # Track attempts needed
        total_retries = 0

        async def observe_with_tracking(session_id, obs_num):
            """Make a single observe request with retry and track stats"""
            nonlocal success_count, error_count, total_retries

            success, attempts, error = await observe_with_retry(session, session_id, obs_num)

            if success:
                success_count += 1
                retry_stats[attempts] = retry_stats.get(attempts, 0) + 1
                if attempts > 1:
                    total_retries += (attempts - 1)
                    print(f"✓ Success: {session_id[-8:]} obs#{obs_num} (attempt {attempts})")
                else:
                    print(f"✓ Success: {session_id[-8:]} obs#{obs_num}")
                return True
            else:
                error_count += 1
                errors.append(f"{session_id[-8:]} obs#{obs_num} - {error}")
                print(f"✗ Failed: {session_id[-8:]} obs#{obs_num} - {error}")
                return False

        # Create 50 concurrent tasks (10 sessions × 5 observations each)
        tasks = []
        for i, session_id in enumerate(session_ids):
            for j in range(5):
                task = observe_with_tracking(session_id, j)
                tasks.append(task)

        print(f"\n🚀 Starting {len(tasks)} concurrent observe requests with retry logic...")
        results = await asyncio.gather(*tasks)

        print(f"\n" + "="*60)
        print(f"RESULTS:")
        print(f"  Total requests: {len(tasks)}")
        print(f"  Successful: {success_count}")
        print(f"  Failed: {error_count}")
        print(f"  Success rate: {success_count/len(tasks)*100:.1f}%")
        print(f"\nRETRY STATISTICS:")
        print(f"  Succeeded on 1st attempt: {retry_stats.get(1, 0)}")
        print(f"  Succeeded on 2nd attempt: {retry_stats.get(2, 0)}")
        print(f"  Succeeded on 3rd attempt: {retry_stats.get(3, 0)}")
        print(f"  Total retries performed: {total_retries}")
        if success_count > 0:
            print(f"  Average retries per success: {total_retries/success_count:.2f}")
        print("="*60)

        if errors:
            print(f"\n❌ First 10 errors:")
            for error in errors[:10]:
                print(f"  - {error}")

        return success_count, error_count


async def main():
    print("="*60)
    print("Testing concurrent requests with RETRY LOGIC")
    print("="*60)

    # Create sessions
    print("\n📝 Creating 10 test sessions...")
    session_ids = await create_sessions()

    # Test concurrent observe with retry
    print(f"\n🧪 Testing concurrent observe requests with retry...")
    success, errors = await test_concurrent_observe_with_retry(session_ids)

    # Exit with error code if there were failures
    if errors > 0:
        print(f"\n⚠️  {errors} requests failed even after retries")
        sys.exit(1)
    else:
        print("\n✅ All requests succeeded (some may have required retries)")
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
