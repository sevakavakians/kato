"""
Database cleanup utilities for test isolation.
Provides functions to completely clear all databases for a specific processor_id.
"""

import os
from typing import Optional

import redis
from qdrant_client import QdrantClient


def clear_clickhouse_for_processor(processor_id: str, clickhouse_host: str = "localhost", clickhouse_port: int = 8123):
    """
    Clear ClickHouse patterns for a specific processor.

    Args:
        processor_id: The processor ID whose data to clear
        clickhouse_host: ClickHouse host
        clickhouse_port: ClickHouse HTTP port
    """
    try:
        import clickhouse_connect
        client = clickhouse_connect.get_client(host=clickhouse_host, port=clickhouse_port)
        client.command(f"ALTER TABLE kato.patterns_data DROP PARTITION '{processor_id}'")
        print(f"  Dropped ClickHouse partition for: {processor_id}")
        client.close()
    except Exception as e:
        if "doesn't exist" in str(e).lower() or "not found" in str(e).lower():
            print(f"  ClickHouse partition {processor_id} doesn't exist (nothing to drop)")
        elif "Connection refused" in str(e):
            print(f"  Info: ClickHouse not available for {processor_id}")
        else:
            print(f"  Warning: Failed to clear ClickHouse for {processor_id}: {e}")


def clear_qdrant_for_processor(processor_id: str, qdrant_host: str = "localhost", qdrant_port: int = 6333):
    """
    Clear Qdrant collections for a specific processor.

    Args:
        processor_id: The processor ID whose vectors to clear
        qdrant_host: Qdrant host
        qdrant_port: Qdrant port
    """
    try:
        client = QdrantClient(host=qdrant_host, port=qdrant_port)

        # Collection name format: vectors_{processor_id}
        collection_name = f"vectors_{processor_id}"

        # Check if collection exists
        collections = client.get_collections()
        if any(c.name == collection_name for c in collections.collections):
            # Delete the collection
            client.delete_collection(collection_name)
            print(f"  Deleted Qdrant collection: {collection_name}")
        else:
            print(f"  Qdrant collection {collection_name} does not exist")

    except Exception as e:
        # Qdrant might not be running for some tests, which is okay
        if "Connection refused" in str(e):
            print(f"  Info: Qdrant not available for {processor_id} (not required for all tests)")
        else:
            print(f"  Warning: Failed to clear Qdrant for {processor_id}: {e}")


def clear_redis_for_processor(processor_id: str, redis_host: str = "localhost", redis_port: int = 6379):
    """
    Clear Redis keys for a specific processor.

    Args:
        processor_id: The processor ID whose cache to clear
        redis_host: Redis host
        redis_port: Redis port
    """
    try:
        r = redis.Redis(host=redis_host, port=redis_port, decode_responses=True)

        # Key pattern: {processor_id}:*
        pattern = f"{processor_id}:*"

        # Find all keys matching the pattern
        keys = r.keys(pattern)

        if keys:
            # Delete all matching keys
            r.delete(*keys)
            print(f"  Deleted {len(keys)} Redis keys with pattern: {pattern}")
        else:
            print(f"  No Redis keys found with pattern: {pattern}")

    except Exception as e:
        # Redis might not be running for some tests, which is okay
        if "Connection refused" in str(e):
            print(f"  Info: Redis not available for {processor_id} (not required for all tests)")
        else:
            print(f"  Warning: Failed to clear Redis for {processor_id}: {e}")


def clear_all_databases_for_processor(processor_id: str):
    """
    Clear all databases (ClickHouse, Qdrant, Redis) for a specific processor.

    Args:
        processor_id: The processor ID to clear
    """
    print(f"\nClearing all databases for processor: {processor_id}")

    # Clear ClickHouse
    clear_clickhouse_for_processor(processor_id)

    # Clear Qdrant
    clear_qdrant_for_processor(processor_id)

    # Clear Redis
    clear_redis_for_processor(processor_id)

    print(f"Completed database cleanup for: {processor_id}")


def verify_isolation(processor_id: str) -> bool:
    """
    Verify that databases are properly isolated for a processor.

    Args:
        processor_id: The processor ID to check

    Returns:
        True if properly isolated (no data found), False otherwise
    """
    is_isolated = True

    # Check ClickHouse
    try:
        import clickhouse_connect
        client = clickhouse_connect.get_client(host="localhost", port=8123)
        result = client.query(f"SELECT COUNT(*) FROM kato.patterns_data WHERE kb_id = '{processor_id}'")
        count = result.result_rows[0][0]
        if count > 0:
            print(f"  WARNING: ClickHouse has {count} patterns for {processor_id}")
            is_isolated = False
        client.close()
    except Exception as e:
        print(f"  Could not verify ClickHouse isolation: {e}")

    # Check Qdrant
    try:
        client = QdrantClient(host="localhost", port=6333)
        collection_name = f"vectors_{processor_id}"

        collections = client.get_collections()
        if any(c.name == collection_name for c in collections.collections):
            collection_info = client.get_collection(collection_name)
            if collection_info.vectors_count > 0:
                print(f"  WARNING: Qdrant has {collection_info.vectors_count} vectors for {processor_id}")
                is_isolated = False

    except Exception as e:
        print(f"  Could not verify Qdrant isolation: {e}")

    # Check Redis
    try:
        r = redis.Redis(host="localhost", port=6379, decode_responses=True)
        pattern = f"{processor_id}:*"
        keys = r.keys(pattern)

        if keys:
            print(f"  WARNING: Redis has {len(keys)} keys for {processor_id}")
            is_isolated = False

    except Exception as e:
        print(f"  Could not verify Redis isolation: {e}")

    return is_isolated


def cleanup_orphaned_data():
    """
    Clean up any orphaned test data from previous test runs.
    This should be run periodically to prevent database bloat.
    """
    print("\nCleaning up orphaned test data...")

    # Clean ClickHouse
    try:
        import clickhouse_connect
        client = clickhouse_connect.get_client(host="localhost", port=8123)
        result = client.query("SELECT DISTINCT kb_id FROM kato.patterns_data WHERE kb_id LIKE 'test_%'")
        for row in result.result_rows:
            kb_id = row[0]
            client.command(f"ALTER TABLE kato.patterns_data DROP PARTITION '{kb_id}'")
            print(f"  Dropped orphaned ClickHouse partition: {kb_id}")
        client.close()
    except Exception as e:
        print(f"  Could not clean ClickHouse: {e}")

    # Clean Qdrant
    try:
        client = QdrantClient(host="localhost", port=6333)
        collections = client.get_collections()

        for collection in collections.collections:
            if collection.name.startswith(('vectors_test_', 'vectors_cluster_')):
                client.delete_collection(collection.name)
                print(f"  Dropped orphaned Qdrant collection: {collection.name}")

    except Exception as e:
        print(f"  Could not clean Qdrant: {e}")

    # Clean Redis
    try:
        r = redis.Redis(host="localhost", port=6379, decode_responses=True)

        # Find test keys
        for pattern in ['test_*', 'cluster_*']:
            keys = r.keys(pattern)
            if keys:
                r.delete(*keys)
                print(f"  Deleted {len(keys)} orphaned Redis keys with pattern: {pattern}")

    except Exception as e:
        print(f"  Could not clean Redis: {e}")

    print("Orphaned data cleanup complete")
