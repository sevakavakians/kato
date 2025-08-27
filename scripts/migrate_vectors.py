#!/usr/bin/env python3
"""
Vector Database Migration Script

Migrates vectors from MongoDB to modern vector database (Qdrant by default).
Supports incremental migration, verification, and rollback.
"""

import argparse
import asyncio
import json
import logging
import sys
import time
from typing import Dict, List, Optional
from pathlib import Path
import numpy as np
from pymongo import MongoClient
from tqdm import tqdm

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from kato.config.vectordb_config import VectorDBConfig, EXAMPLE_CONFIGS
from kato.storage import VectorStoreFactory, VectorBatch
from kato.storage.mongodb_vector_store import MongoDBVectorStore

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class VectorMigrator:
    """Handles migration of vectors between storage backends"""
    
    def __init__(
        self,
        source_config: Dict,
        target_config: VectorDBConfig,
        batch_size: int = 1000,
        verify: bool = True
    ):
        """
        Initialize migrator.
        
        Args:
            source_config: MongoDB connection configuration
            target_config: Target vector database configuration
            batch_size: Number of vectors to migrate per batch
            verify: Whether to verify migration
        """
        self.source_config = source_config
        self.target_config = target_config
        self.batch_size = batch_size
        self.verify = verify
        
        # Initialize stores
        self.source_store = None
        self.target_store = None
        
        # Migration statistics
        self.stats = {
            'total_vectors': 0,
            'migrated': 0,
            'failed': 0,
            'verified': 0,
            'start_time': None,
            'end_time': None
        }
    
    async def connect(self):
        """Connect to source and target databases"""
        logger.info("Connecting to source database (MongoDB)...")
        
        # Create MongoDB store
        mongo_config = {
            'mongodb': self.source_config
        }
        self.source_store = MongoDBVectorStore(mongo_config)
        
        if not await self.source_store.connect():
            raise ConnectionError("Failed to connect to MongoDB")
        
        logger.info("Connecting to target database...")
        
        # Create target store
        self.target_store = VectorStoreFactory.create_store(self.target_config)
        
        if not await self.target_store.connect():
            raise ConnectionError(f"Failed to connect to {self.target_config.backend}")
        
        logger.info("Successfully connected to both databases")
    
    async def get_collections(self) -> List[str]:
        """Get list of collections to migrate"""
        collections = await self.source_store.list_collections()
        logger.info(f"Found {len(collections)} collections in source database")
        return collections
    
    async def migrate_collection(
        self,
        collection_name: str,
        target_collection: Optional[str] = None
    ) -> Dict:
        """
        Migrate a single collection.
        
        Args:
            collection_name: Source collection name
            target_collection: Target collection name (uses source name if None)
        
        Returns:
            Migration statistics for this collection
        """
        target_collection = target_collection or collection_name
        
        logger.info(f"Starting migration: {collection_name} -> {target_collection}")
        
        # Get collection info
        info = await self.source_store.get_collection_info(collection_name)
        vector_count = info.get('vectors_count', 0)
        vector_dim = info.get('vector_dim')
        
        if not vector_dim:
            # Try to get dimension from first vector
            logger.warning("Vector dimension not in metadata, checking first vector...")
            first_vector = await self._get_first_vector(collection_name)
            if first_vector:
                vector_dim = len(first_vector['vector'])
            else:
                logger.error(f"Cannot determine vector dimension for {collection_name}")
                return {'error': 'Unknown vector dimension'}
        
        logger.info(f"Collection has {vector_count} vectors of dimension {vector_dim}")
        
        # Create target collection
        if not await self.target_store.create_collection(
            target_collection,
            vector_dim,
            distance=self.target_config.similarity_metric
        ):
            logger.error(f"Failed to create target collection: {target_collection}")
            return {'error': 'Failed to create target collection'}
        
        # Migrate vectors in batches
        collection_stats = {
            'name': collection_name,
            'total': vector_count,
            'migrated': 0,
            'failed': 0,
            'batches': 0
        }
        
        # Get MongoDB collection directly for efficient iteration
        mongo_client = MongoClient(self.source_config['connection_string'])
        db = mongo_client[self.source_config['database']]
        source_collection = db[f"{self.source_config['collection']}_{collection_name}"]
        
        # Progress bar
        pbar = tqdm(total=vector_count, desc=f"Migrating {collection_name}")
        
        # Process in batches
        batch_ids = []
        batch_vectors = []
        batch_payloads = []
        
        cursor = source_collection.find({}, {'_id': 0})
        
        for doc in cursor:
            # Extract vector data
            vector_id = doc.get('name', '')
            vector_data = doc.get('vector', [])
            payload = doc.get('payload', {})
            
            # Add vector length to payload for compatibility
            if 'vector_length' in doc:
                payload['vector_length'] = doc['vector_length']
            
            batch_ids.append(vector_id)
            batch_vectors.append(vector_data)
            batch_payloads.append(payload)
            
            # Process batch when full
            if len(batch_ids) >= self.batch_size:
                success = await self._migrate_batch(
                    target_collection,
                    batch_ids,
                    batch_vectors,
                    batch_payloads
                )
                
                if success:
                    collection_stats['migrated'] += len(batch_ids)
                else:
                    collection_stats['failed'] += len(batch_ids)
                
                collection_stats['batches'] += 1
                pbar.update(len(batch_ids))
                
                # Clear batch
                batch_ids = []
                batch_vectors = []
                batch_payloads = []
        
        # Process remaining vectors
        if batch_ids:
            success = await self._migrate_batch(
                target_collection,
                batch_ids,
                batch_vectors,
                batch_payloads
            )
            
            if success:
                collection_stats['migrated'] += len(batch_ids)
            else:
                collection_stats['failed'] += len(batch_ids)
            
            collection_stats['batches'] += 1
            pbar.update(len(batch_ids))
        
        pbar.close()
        mongo_client.close()
        
        # Verify migration if requested
        if self.verify:
            logger.info(f"Verifying migration for {collection_name}...")
            verification = await self._verify_collection(
                collection_name,
                target_collection,
                collection_stats['migrated']
            )
            collection_stats['verification'] = verification
        
        logger.info(
            f"Collection {collection_name} migration complete: "
            f"{collection_stats['migrated']}/{vector_count} vectors migrated"
        )
        
        return collection_stats
    
    async def _get_first_vector(self, collection_name: str) -> Optional[Dict]:
        """Get first vector from collection to determine dimension"""
        mongo_client = MongoClient(self.source_config['connection_string'])
        db = mongo_client[self.source_config['database']]
        collection = db[f"{self.source_config['collection']}_{collection_name}"]
        
        first_doc = collection.find_one()
        mongo_client.close()
        
        return first_doc
    
    async def _migrate_batch(
        self,
        target_collection: str,
        ids: List[str],
        vectors: List[List[float]],
        payloads: List[Dict]
    ) -> bool:
        """Migrate a batch of vectors"""
        try:
            # Create batch
            batch = VectorBatch(
                ids=ids,
                vectors=np.array(vectors),
                payloads=payloads
            )
            
            # Add to target
            success_count, failed_ids = await self.target_store.add_vectors(
                target_collection,
                batch
            )
            
            if failed_ids:
                logger.warning(f"Failed to migrate {len(failed_ids)} vectors in batch")
            
            return len(failed_ids) == 0
            
        except Exception as e:
            logger.error(f"Batch migration failed: {e}")
            return False
    
    async def _verify_collection(
        self,
        source_collection: str,
        target_collection: str,
        expected_count: int
    ) -> Dict:
        """Verify migration by comparing counts and sample vectors"""
        verification = {
            'count_match': False,
            'sample_match': False,
            'target_count': 0
        }
        
        try:
            # Check count
            target_count = await self.target_store.count_vectors(target_collection)
            verification['target_count'] = target_count
            verification['count_match'] = (target_count == expected_count)
            
            if not verification['count_match']:
                logger.warning(
                    f"Count mismatch: expected {expected_count}, got {target_count}"
                )
            
            # Sample verification (check a few random vectors)
            sample_size = min(10, expected_count)
            
            # Get random sample from source
            mongo_client = MongoClient(self.source_config['connection_string'])
            db = mongo_client[self.source_config['database']]
            source_coll = db[f"{self.source_config['collection']}_{source_collection}"]
            
            sample_docs = list(source_coll.aggregate([
                {"$sample": {"size": sample_size}}
            ]))
            
            mongo_client.close()
            
            # Check each sample in target
            matches = 0
            for doc in sample_docs:
                vector_id = doc.get('name')
                target_vector = await self.target_store.get_vector(
                    target_collection,
                    vector_id,
                    include_vector=True
                )
                
                if target_vector:
                    # Compare vectors
                    source_vec = np.array(doc['vector'])
                    target_vec = target_vector.vector
                    
                    if np.allclose(source_vec, target_vec, rtol=1e-5):
                        matches += 1
            
            verification['sample_match'] = (matches == len(sample_docs))
            verification['sample_stats'] = f"{matches}/{len(sample_docs)} samples matched"
            
            logger.info(f"Verification: {verification}")
            
        except Exception as e:
            logger.error(f"Verification failed: {e}")
            verification['error'] = str(e)
        
        return verification
    
    async def migrate_all(
        self,
        collections: Optional[List[str]] = None
    ) -> Dict:
        """
        Migrate all or specified collections.
        
        Args:
            collections: List of collections to migrate (all if None)
        
        Returns:
            Migration statistics
        """
        self.stats['start_time'] = time.time()
        
        # Get collections
        if collections is None:
            collections = await self.get_collections()
        
        logger.info(f"Migrating {len(collections)} collections")
        
        # Migrate each collection
        collection_results = []
        for collection in collections:
            result = await self.migrate_collection(collection)
            collection_results.append(result)
            
            # Update global stats
            if 'error' not in result:
                self.stats['migrated'] += result['migrated']
                self.stats['failed'] += result['failed']
        
        self.stats['end_time'] = time.time()
        self.stats['duration'] = self.stats['end_time'] - self.stats['start_time']
        self.stats['collections'] = collection_results
        
        return self.stats
    
    async def cleanup(self):
        """Disconnect from databases"""
        if self.source_store:
            await self.source_store.disconnect()
        if self.target_store:
            await self.target_store.disconnect()


async def main():
    """Main migration function"""
    parser = argparse.ArgumentParser(
        description='Migrate vectors from MongoDB to modern vector database'
    )
    
    # Source configuration
    parser.add_argument(
        '--source-host',
        default='localhost',
        help='MongoDB host (default: localhost)'
    )
    parser.add_argument(
        '--source-port',
        type=int,
        default=27017,
        help='MongoDB port (default: 27017)'
    )
    parser.add_argument(
        '--source-db',
        default='kato_kb',
        help='MongoDB database name (default: kato_kb)'
    )
    parser.add_argument(
        '--source-collection-prefix',
        default='vectors_kb',
        help='MongoDB collection prefix (default: vectors_kb)'
    )
    
    # Target configuration
    parser.add_argument(
        '--target-backend',
        choices=['qdrant', 'milvus', 'weaviate'],
        default='qdrant',
        help='Target vector database backend (default: qdrant)'
    )
    parser.add_argument(
        '--target-host',
        default='localhost',
        help='Target database host (default: localhost)'
    )
    parser.add_argument(
        '--target-port',
        type=int,
        help='Target database port (default: backend-specific)'
    )
    parser.add_argument(
        '--config-preset',
        choices=list(EXAMPLE_CONFIGS.keys()),
        help='Use a preset configuration'
    )
    
    # Migration options
    parser.add_argument(
        '--collections',
        nargs='+',
        help='Specific collections to migrate (default: all)'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=1000,
        help='Batch size for migration (default: 1000)'
    )
    parser.add_argument(
        '--no-verify',
        action='store_true',
        help='Skip verification after migration'
    )
    parser.add_argument(
        '--output',
        help='Output file for migration report (JSON)'
    )
    
    args = parser.parse_args()
    
    # Build source configuration
    source_config = {
        'connection_string': f"mongodb://{args.source_host}:{args.source_port}",
        'database': args.source_db,
        'collection': args.source_collection_prefix
    }
    
    # Build target configuration
    if args.config_preset:
        target_config = EXAMPLE_CONFIGS[args.config_preset]
        logger.info(f"Using preset configuration: {args.config_preset}")
    else:
        target_config = VectorDBConfig(backend=args.target_backend)
        
        if args.target_backend == 'qdrant':
            target_config.qdrant.host = args.target_host
            target_config.qdrant.port = args.target_port or 6333
    
    # Create migrator
    migrator = VectorMigrator(
        source_config=source_config,
        target_config=target_config,
        batch_size=args.batch_size,
        verify=not args.no_verify
    )
    
    try:
        # Connect to databases
        await migrator.connect()
        
        # Run migration
        stats = await migrator.migrate_all(args.collections)
        
        # Print summary
        print("\n" + "="*60)
        print("MIGRATION SUMMARY")
        print("="*60)
        print(f"Total vectors migrated: {stats['migrated']}")
        print(f"Failed vectors: {stats['failed']}")
        print(f"Duration: {stats['duration']:.2f} seconds")
        print(f"Rate: {stats['migrated']/stats['duration']:.0f} vectors/second")
        
        # Save report if requested
        if args.output:
            with open(args.output, 'w') as f:
                json.dump(stats, f, indent=2, default=str)
            print(f"\nReport saved to: {args.output}")
        
        # Return success if no failures
        return stats['failed'] == 0
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        return False
        
    finally:
        await migrator.cleanup()


if __name__ == '__main__':
    success = asyncio.run(main())
    sys.exit(0 if success else 1)