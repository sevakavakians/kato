#!/usr/bin/env python3
"""
Debug script to test concurrent HTTP connections to KATO.
This will help us understand if it's a client-side or server-side issue.
"""
import asyncio
import aiohttp


async def test_concurrent_requests():
    """Test making 10 concurrent HTTP requests to the same endpoint."""
    async with aiohttp.ClientSession() as session:
        tasks = []

        # Create 10 concurrent GET requests to the health endpoint
        for i in range(10):
            async def make_request(idx):
                try:
                    async with session.get("http://localhost:8000/health") as resp:
                        status = resp.status
                        data = await resp.json()
                        print(f"Request {idx}: Status {status} - {data.get('status', 'unknown')}")
                        return (idx, status, None)
                except Exception as e:
                    print(f"Request {idx}: FAILED - {type(e).__name__}: {e}")
                    return (idx, None, str(e))

            tasks.append(make_request(i))

        results = await asyncio.gather(*tasks)

        # Summary
        successes = sum(1 for _, status, _ in results if status == 200)
        failures = sum(1 for _, status, _ in results if status != 200)

        print(f"\n=== SUMMARY ===")
        print(f"Total requests: 10")
        print(f"Successful: {successes}")
        print(f"Failed: {failures}")
        print(f"Success rate: {successes/10*100:.1f}%")


if __name__ == "__main__":
    print("Testing concurrent HTTP connections to KATO...")
    print("=" * 60)
    asyncio.run(test_concurrent_requests())
