"""
Database cleanup utilities for test isolation.
Provides functions to completely clear all databases for a specific processor_id.
"""

import os
import pymongo
import redis
from qdrant_client import QdrantClient
from typing import Optional


def clear_mongodb_for_processor(processor_id: str, mongo_url: Optional[str] = None):
    """
    Clear all MongoDB collections for a specific processor.
    
    Args:
        processor_id: The processor ID whose data to clear
        mongo_url: MongoDB connection URL (defaults to environment variable)
    """
    if not mongo_url:
        mongo_url = os.environ.get('MONGO_BASE_URL', 'mongodb://localhost:27017')
    
    try:
        client = pymongo.MongoClient(mongo_url)
        
        # The database name is the processor_id
        db = client[processor_id]
        
        # Drop all collections in the database
        for collection_name in db.list_collection_names():
            db[collection_name].drop()
            print(f"  Dropped MongoDB collection: {processor_id}.{collection_name}")
        
        # Optionally drop the entire database
        client.drop_database(processor_id)
        print(f"  Dropped MongoDB database: {processor_id}")
        
        client.close()
    except Exception as e:
        print(f"  Warning: Failed to clear MongoDB for {processor_id}: {e}")


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
    Clear all databases (MongoDB, Qdrant, Redis) for a specific processor.
    
    Args:
        processor_id: The processor ID to clear
    """
    print(f"\nClearing all databases for processor: {processor_id}")
    
    # Clear MongoDB
    clear_mongodb_for_processor(processor_id)
    
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
    
    # Check MongoDB
    try:
        mongo_url = os.environ.get('MONGO_BASE_URL', 'mongodb://localhost:27017')
        client = pymongo.MongoClient(mongo_url)
        db = client[processor_id]
        
        collections = db.list_collection_names()
        if collections:
            print(f"  WARNING: MongoDB has {len(collections)} collections for {processor_id}")
            is_isolated = False
        
        client.close()
    except Exception as e:
        print(f"  Could not verify MongoDB isolation: {e}")
    
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
    
    # Clean MongoDB
    try:
        mongo_url = os.environ.get('MONGO_BASE_URL', 'mongodb://localhost:27017')
        client = pymongo.MongoClient(mongo_url)
        
        # Find all test databases (start with test_ or cluster_)
        for db_name in client.list_database_names():
            if db_name.startswith(('test_', 'cluster_')):
                client.drop_database(db_name)
                print(f"  Dropped orphaned MongoDB database: {db_name}")
        
        client.close()
    except Exception as e:
        print(f"  Could not clean MongoDB: {e}")
    
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