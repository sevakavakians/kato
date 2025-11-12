#!/usr/bin/env python3
"""
MongoDB to Redis Migration Script

Migrates pattern metadata from MongoDB to Redis:
- Emotives data (rolling window arrays per emotive key)
- Metadata (unique string lists per metadata key)
- Frequency counts

Usage:
    python scripts/migrate_mongodb_to_redis.py [--batch-size 1000] [--dry-run]

Environment Variables:
    MONGO_BASE_URL: MongoDB connection string (default: mongodb://localhost:27017)
    REDIS_HOST: Redis host (default: localhost)
    REDIS_PORT: Redis port (default: 6379)
    REDIS_DB: Redis database number (default: 0)
"""

import argparse
import json
import logging
import sys
import time
from datetime import datetime
from typing import List, Dict, Any

# Third-party imports
from pymongo import MongoClient
import redis

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


class MongoToRedisMigration:
    """
    Handles migration of pattern metadata from MongoDB to Redis.

    Features:
    - Batch processing with Redis pipelines
    - Emotives, metadata, and frequency migration
    - Progress tracking and reporting
    - Dry-run mode for testing
    - Comprehensive error handling
    """

    def __init__(self,
                 mongo_url: str,
                 redis_host: str,
                 redis_port: int,
                 redis_db: int,
                 batch_size: int = 1000,
                 dry_run: bool = False):
        """
        Initialize migration manager.

        Args:
            mongo_url: MongoDB connection string
            redis_host: Redis host
            redis_port: Redis port
            redis_db: Redis database number
            batch_size: Number of patterns per batch
            dry_run: If True, don't write to Redis
        """
        self.mongo_url = mongo_url
        self.redis_host = redis_host
        self.redis_port = redis_port
        self.redis_db = redis_db
        self.batch_size = batch_size
        self.dry_run = dry_run

        # Statistics
        self.stats = {
            'total_patterns': 0,
            'migrated_patterns': 0,
            'failed_patterns': 0,
            'emotives_migrated': 0,
            'metadata_migrated': 0,
            'frequency_migrated': 0,
            'start_time': None,
            'end_time': None
        }

        # Connections
        self.mongo_client = None
        self.mongo_db = None
        self.redis_client = None

    def connect(self):
        """Establish database connections."""
        logger.info(f"Connecting to MongoDB: {self.mongo_url}")
        self.mongo_client = MongoClient(self.mongo_url)

        # Extract database name from connection string or use default
        # This database name is the kb_id (node identifier) for Redis key namespacing
        if '/' in self.mongo_url.split('://')[-1]:
            db_name = self.mongo_url.split('/')[-1].split('?')[0]
        else:
            db_name = 'kato'  # Default database name

        self.kb_id = db_name  # Store kb_id for Redis key namespacing
        self.mongo_db = self.mongo_client[db_name]
        logger.info(f"Connected to MongoDB database: {db_name} (kb_id: {self.kb_id})")

        if not self.dry_run:
            logger.info(f"Connecting to Redis: {self.redis_host}:{self.redis_port}/{self.redis_db}")
            self.redis_client = redis.Redis(
                host=self.redis_host,
                port=self.redis_port,
                db=self.redis_db,
                decode_responses=True  # Return strings instead of bytes
            )
            # Test connection
            self.redis_client.ping()
            logger.info(f"Connected to Redis database: {self.redis_db}")
        else:
            logger.info("DRY RUN MODE - Redis connection skipped")

    def disconnect(self):
        """Close database connections."""
        if self.mongo_client:
            self.mongo_client.close()
            logger.info("Disconnected from MongoDB")

        if self.redis_client:
            self.redis_client.close()
            logger.info("Disconnected from Redis")

    def migrate_pattern_to_redis(self, pattern: Dict[str, Any], pipeline: redis.client.Pipeline = None):
        """
        Migrate single pattern's metadata to Redis.

        Args:
            pattern: MongoDB pattern document
            pipeline: Redis pipeline for batch operations (optional)

        Returns:
            True if successful, False otherwise
        """
        try:
            name = pattern.get('name', '')
            if not name:
                logger.warning("Pattern missing name, skipping")
                return False

            # Use pipeline if provided, otherwise use direct client
            redis_conn = pipeline if pipeline else self.redis_client

            # Migrate frequency (simple integer) with kb_id namespace for isolation
            frequency = pattern.get('frequency', 1)
            redis_conn.set(f'{self.kb_id}:frequency:{name}', frequency)
            self.stats['frequency_migrated'] += 1

            # Migrate emotives (hash of arrays) with kb_id namespace for isolation
            emotives = pattern.get('emotives', {})
            if emotives:
                # Convert arrays to JSON strings for Redis storage
                emotives_data = {k: json.dumps(v) for k, v in emotives.items()}
                redis_conn.hset(f'{self.kb_id}:emotives:{name}', mapping=emotives_data)
                self.stats['emotives_migrated'] += 1

            # Migrate metadata from pattern document (embedded field)
            metadata = pattern.get('metadata', {})
            if metadata:
                # Convert lists to JSON strings for Redis storage with kb_id namespace for isolation
                metadata_data = {k: json.dumps(v) for k, v in metadata.items()}
                redis_conn.hset(f'{self.kb_id}:metadata:{name}', mapping=metadata_data)
                self.stats['metadata_migrated'] += 1

            return True

        except Exception as e:
            logger.error(f"Failed to migrate pattern '{pattern.get('name', 'UNKNOWN')}': {e}")
            return False

    def migrate_metadata_to_redis(self, metadata_doc: Dict[str, Any], pipeline: redis.client.Pipeline = None):
        """
        Migrate metadata document to Redis.

        Args:
            metadata_doc: MongoDB metadata document
            pipeline: Redis pipeline for batch operations (optional)

        Returns:
            True if successful, False otherwise
        """
        try:
            pattern_name = metadata_doc.get('pattern_name', '')
            if not pattern_name:
                logger.warning("Metadata document missing pattern_name, skipping")
                return False

            # Use pipeline if provided, otherwise use direct client
            redis_conn = pipeline if pipeline else self.redis_client

            # Extract metadata fields (excluding _id and pattern_name)
            metadata = {k: v for k, v in metadata_doc.items() if k not in ['_id', 'pattern_name']}

            if metadata:
                # Convert lists to JSON strings for Redis storage with kb_id namespace for isolation
                metadata_data = {k: json.dumps(v) for k, v in metadata.items()}
                redis_conn.hset(f'{self.kb_id}:metadata:{pattern_name}', mapping=metadata_data)
                self.stats['metadata_migrated'] += 1

            return True

        except Exception as e:
            logger.error(f"Failed to migrate metadata for '{metadata_doc.get('pattern_name', 'UNKNOWN')}': {e}")
            return False

    def migrate(self, processor_id: str = None):
        """
        Execute migration from MongoDB to Redis.

        Args:
            processor_id: Optional processor ID to migrate specific collections
        """
        logger.info("=" * 80)
        logger.info("MongoDB → Redis Migration Started")
        logger.info("=" * 80)

        self.stats['start_time'] = datetime.now()

        try:
            # Connect to databases
            self.connect()

            # Determine collection names
            if processor_id:
                patterns_collection_name = f'{processor_id}.patterns_kb'
                metadata_collection_name = f'{processor_id}.metadata'
            else:
                patterns_collection_name = 'patterns_kb'
                metadata_collection_name = 'metadata'

            # Migrate patterns (emotives + frequency)
            logger.info(f"Migrating patterns from '{patterns_collection_name}'...")
            patterns_collection = self.mongo_db[patterns_collection_name]
            total_patterns = patterns_collection.count_documents({})
            self.stats['total_patterns'] = total_patterns

            logger.info(f"Found {total_patterns:,} patterns to migrate")

            if total_patterns == 0:
                logger.warning("No patterns to migrate!")
            else:
                # Process patterns in batches
                processed_count = 0
                cursor = patterns_collection.find({})

                if not self.dry_run:
                    pipeline = self.redis_client.pipeline()
                    batch_count = 0

                    for pattern in cursor:
                        if self.migrate_pattern_to_redis(pattern, pipeline):
                            batch_count += 1

                        # Execute pipeline when batch is full
                        if batch_count >= self.batch_size:
                            pipeline.execute()
                            self.stats['migrated_patterns'] += batch_count
                            processed_count += batch_count

                            # Progress report
                            progress_pct = (processed_count / total_patterns) * 100
                            logger.info(f"Patterns: {processed_count:,}/{total_patterns:,} ({progress_pct:.1f}%)")

                            pipeline = self.redis_client.pipeline()
                            batch_count = 0

                    # Execute remaining patterns
                    if batch_count > 0:
                        pipeline.execute()
                        self.stats['migrated_patterns'] += batch_count
                        processed_count += batch_count

                    logger.info(f"Patterns: {processed_count:,}/{total_patterns:,} (100.0%)")
                else:
                    # Dry run - just count
                    for pattern in cursor:
                        self.migrate_pattern_to_redis(pattern, None)
                        processed_count += 1
                    self.stats['migrated_patterns'] = processed_count

            # Migrate metadata
            logger.info(f"Migrating metadata from '{metadata_collection_name}'...")
            metadata_collection = self.mongo_db[metadata_collection_name]
            total_metadata = metadata_collection.count_documents({})

            logger.info(f"Found {total_metadata:,} metadata documents to migrate")

            if total_metadata > 0:
                processed_count = 0
                cursor = metadata_collection.find({})

                if not self.dry_run:
                    pipeline = self.redis_client.pipeline()
                    batch_count = 0

                    for metadata_doc in cursor:
                        if self.migrate_metadata_to_redis(metadata_doc, pipeline):
                            batch_count += 1

                        # Execute pipeline when batch is full
                        if batch_count >= self.batch_size:
                            pipeline.execute()
                            processed_count += batch_count

                            # Progress report
                            progress_pct = (processed_count / total_metadata) * 100
                            logger.info(f"Metadata: {processed_count:,}/{total_metadata:,} ({progress_pct:.1f}%)")

                            pipeline = self.redis_client.pipeline()
                            batch_count = 0

                    # Execute remaining metadata
                    if batch_count > 0:
                        pipeline.execute()
                        processed_count += batch_count

                    logger.info(f"Metadata: {processed_count:,}/{total_metadata:,} (100.0%)")
                else:
                    # Dry run - just count
                    for metadata_doc in cursor:
                        self.migrate_metadata_to_redis(metadata_doc, None)
                        processed_count += 1

        except Exception as e:
            logger.error(f"Migration failed: {e}")
            raise

        finally:
            self.disconnect()
            self.stats['end_time'] = datetime.now()
            self.print_summary()

    def print_summary(self):
        """Print migration summary statistics."""
        logger.info("=" * 80)
        logger.info("Migration Summary")
        logger.info("=" * 80)
        logger.info(f"Total patterns:       {self.stats['total_patterns']:,}")
        logger.info(f"Migrated patterns:    {self.stats['migrated_patterns']:,}")
        logger.info(f"Failed patterns:      {self.stats['failed_patterns']:,}")
        logger.info(f"Emotives migrated:    {self.stats['emotives_migrated']:,}")
        logger.info(f"Metadata migrated:    {self.stats['metadata_migrated']:,}")
        logger.info(f"Frequency migrated:   {self.stats['frequency_migrated']:,}")

        if self.stats['start_time'] and self.stats['end_time']:
            duration = (self.stats['end_time'] - self.stats['start_time']).total_seconds()
            rate = self.stats['migrated_patterns'] / duration if duration > 0 else 0
            logger.info(f"Duration:             {duration:.1f} seconds")
            logger.info(f"Rate:                 {rate:.0f} patterns/second")

        logger.info("=" * 80)


def main():
    """Main entry point for migration script."""
    parser = argparse.ArgumentParser(
        description='Migrate pattern metadata from MongoDB to Redis'
    )
    parser.add_argument(
        '--mongo-url',
        default='mongodb://localhost:27017',
        help='MongoDB connection string (default: mongodb://localhost:27017)'
    )
    parser.add_argument(
        '--redis-host',
        default='localhost',
        help='Redis host (default: localhost)'
    )
    parser.add_argument(
        '--redis-port',
        type=int,
        default=6379,
        help='Redis port (default: 6379)'
    )
    parser.add_argument(
        '--redis-db',
        type=int,
        default=0,
        help='Redis database number (default: 0)'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=1000,
        help='Number of patterns per batch (default: 1000)'
    )
    parser.add_argument(
        '--processor-id',
        help='Optional processor ID to migrate specific collections'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Run migration without writing to Redis'
    )

    args = parser.parse_args()

    # Create migration manager
    migration = MongoToRedisMigration(
        mongo_url=args.mongo_url,
        redis_host=args.redis_host,
        redis_port=args.redis_port,
        redis_db=args.redis_db,
        batch_size=args.batch_size,
        dry_run=args.dry_run
    )

    try:
        # Execute migration
        migration.migrate(processor_id=args.processor_id)

        # Exit with appropriate code
        if migration.stats['failed_patterns'] > 0:
            logger.warning(f"Migration completed with {migration.stats['failed_patterns']} failures")
            sys.exit(1)
        else:
            logger.info("Migration completed successfully!")
            sys.exit(0)

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
