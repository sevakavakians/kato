#!/usr/bin/env python3
"""
MongoDB to ClickHouse Migration Script

Migrates pattern data from MongoDB to ClickHouse with pre-computation of:
- Length, token sets, and token counts
- MinHash signatures for LSH-based similarity
- LSH band hashes for approximate matching
- First/last tokens for prefix/suffix filtering

Usage:
    python scripts/migrate_mongodb_to_clickhouse.py [--batch-size 1000] [--dry-run]

Environment Variables:
    MONGO_BASE_URL: MongoDB connection string (default: mongodb://localhost:27017)
    CLICKHOUSE_HOST: ClickHouse host (default: localhost)
    CLICKHOUSE_PORT: ClickHouse port (default: 8123)
    CLICKHOUSE_DB: ClickHouse database (default: default)
"""

import argparse
import logging
import sys
import time
from datetime import datetime
from typing import List, Dict, Any, Tuple

# Third-party imports
from pymongo import MongoClient
import clickhouse_connect
from datasketch import MinHash

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


class MongoToClickHouseMigration:
    """
    Handles migration of pattern data from MongoDB to ClickHouse.

    Features:
    - Batch processing for memory efficiency
    - MinHash signature pre-computation
    - LSH band hash pre-computation
    - Progress tracking and reporting
    - Dry-run mode for testing
    - Comprehensive error handling
    """

    def __init__(self,
                 mongo_url: str,
                 clickhouse_host: str,
                 clickhouse_port: int,
                 clickhouse_db: str,
                 batch_size: int = 1000,
                 dry_run: bool = False):
        """
        Initialize migration manager.

        Args:
            mongo_url: MongoDB connection string
            clickhouse_host: ClickHouse host
            clickhouse_port: ClickHouse port
            clickhouse_db: ClickHouse database
            batch_size: Number of patterns per batch
            dry_run: If True, don't write to ClickHouse
        """
        self.mongo_url = mongo_url
        self.clickhouse_host = clickhouse_host
        self.clickhouse_port = clickhouse_port
        self.clickhouse_db = clickhouse_db
        self.batch_size = batch_size
        self.dry_run = dry_run

        # MinHash/LSH configuration (must match filter defaults)
        self.num_hashes = 100
        self.bands = 20
        self.rows = 5

        # Statistics
        self.stats = {
            'total_patterns': 0,
            'migrated_patterns': 0,
            'failed_patterns': 0,
            'start_time': None,
            'end_time': None
        }

        # Connections
        self.mongo_client = None
        self.mongo_db = None
        self.clickhouse_client = None

    def connect(self):
        """Establish database connections."""
        logger.info(f"Connecting to MongoDB: {self.mongo_url}")
        self.mongo_client = MongoClient(self.mongo_url)

        # Extract database name from connection string or use default
        # Assuming format: mongodb://host:port/database
        # This database name is the kb_id (node identifier) for ClickHouse partitioning
        if '/' in self.mongo_url.split('://')[-1]:
            db_name = self.mongo_url.split('/')[-1].split('?')[0]
        else:
            db_name = 'kato'  # Default database name

        self.kb_id = db_name  # Store kb_id for ClickHouse partitioning
        self.mongo_db = self.mongo_client[db_name]
        logger.info(f"Connected to MongoDB database: {db_name} (kb_id: {self.kb_id})")

        if not self.dry_run:
            logger.info(f"Connecting to ClickHouse: {self.clickhouse_host}:{self.clickhouse_port}")
            self.clickhouse_client = clickhouse_connect.get_client(
                host=self.clickhouse_host,
                port=self.clickhouse_port,
                database=self.clickhouse_db,
                compress=True
            )
            logger.info(f"Connected to ClickHouse database: {self.clickhouse_db}")
        else:
            logger.info("DRY RUN MODE - ClickHouse connection skipped")

    def disconnect(self):
        """Close database connections."""
        if self.mongo_client:
            self.mongo_client.close()
            logger.info("Disconnected from MongoDB")

        if self.clickhouse_client:
            self.clickhouse_client.close()
            logger.info("Disconnected from ClickHouse")

    def compute_minhash(self, tokens: List[str]) -> Tuple[List[int], List[int]]:
        """
        Compute MinHash signature and LSH band hashes.

        Args:
            tokens: List of unique tokens from pattern

        Returns:
            Tuple of (minhash_signature, lsh_bands)
        """
        # Create MinHash
        minhash = MinHash(num_perm=self.num_hashes)
        for token in tokens:
            minhash.update(token.encode('utf-8'))

        # Get signature
        signature = list(minhash.hashvalues)

        # Compute LSH band hashes
        lsh_bands = []
        for i in range(self.bands):
            start_idx = i * self.rows
            end_idx = start_idx + self.rows
            band_values = tuple(signature[start_idx:end_idx])
            band_hash = abs(hash(band_values))  # Use abs for UInt64 compatibility
            lsh_bands.append(band_hash)

        return signature, lsh_bands

    def transform_pattern(self, pattern: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform MongoDB pattern document to ClickHouse format.

        Args:
            pattern: MongoDB pattern document

        Returns:
            Dictionary with ClickHouse column values
        """
        try:
            name = pattern.get('name', '')
            pattern_data = pattern.get('pattern_data', [])

            if not name or not pattern_data:
                raise ValueError(f"Invalid pattern: name='{name}', data length={len(pattern_data)}")

            # Flatten pattern data to get all tokens
            all_tokens = []
            for event in pattern_data:
                all_tokens.extend(event)

            # Compute precomputed fields
            length = len(all_tokens)
            token_set = sorted(set(all_tokens))  # Unique tokens, sorted
            token_count = len(token_set)

            # First and last tokens
            first_token = all_tokens[0] if all_tokens else ''
            last_token = all_tokens[-1] if all_tokens else ''

            # Compute MinHash signature and LSH bands
            minhash_sig, lsh_bands = self.compute_minhash(token_set)

            return {
                'name': name,
                'pattern_data': pattern_data,
                'length': length,
                'token_set': token_set,
                'token_count': token_count,
                'minhash_sig': minhash_sig,
                'lsh_bands': lsh_bands,
                'first_token': first_token,
                'last_token': last_token
            }

        except Exception as e:
            logger.error(f"Failed to transform pattern '{pattern.get('name', 'UNKNOWN')}': {e}")
            raise

    def batch_insert_clickhouse(self, batch: List[Dict[str, Any]]):
        """
        Insert batch of patterns into ClickHouse.

        Args:
            batch: List of transformed pattern dictionaries
        """
        if self.dry_run:
            logger.debug(f"DRY RUN: Would insert {len(batch)} patterns")
            return

        try:
            # Prepare row data for batch insert
            rows = []
            for p in batch:
                rows.append([
                    self.kb_id,         # kb_id
                    p['name'],          # name
                    p['pattern_data'],  # pattern_data
                    p['length'],        # length
                    p['token_set'],     # token_set
                    p['token_count'],   # token_count
                    p['minhash_sig'],   # minhash_sig
                    p['lsh_bands'],     # lsh_bands
                    p['first_token'],   # first_token
                    p['last_token']     # last_token
                ])

            # Insert batch (row-oriented format)
            self.clickhouse_client.insert(
                'patterns_data',
                rows,
                column_names=['kb_id', 'name', 'pattern_data', 'length', 'token_set',
                             'token_count', 'minhash_sig', 'lsh_bands', 'first_token', 'last_token']
            )

        except Exception as e:
            logger.error(f"Failed to insert batch: {e}")
            raise

    def migrate(self, processor_id: str = None):
        """
        Execute migration from MongoDB to ClickHouse.

        Args:
            processor_id: Optional processor ID to migrate specific collection
        """
        logger.info("=" * 80)
        logger.info("MongoDB → ClickHouse Migration Started")
        logger.info("=" * 80)

        self.stats['start_time'] = datetime.now()

        try:
            # Connect to databases
            self.connect()

            # Get MongoDB collection
            if processor_id:
                collection_name = f'{processor_id}.patterns_kb'
            else:
                collection_name = 'patterns_kb'

            patterns_collection = self.mongo_db[collection_name]
            total_patterns = patterns_collection.count_documents({})
            self.stats['total_patterns'] = total_patterns

            logger.info(f"Found {total_patterns:,} patterns in MongoDB collection '{collection_name}'")

            if total_patterns == 0:
                logger.warning("No patterns to migrate!")
                return

            # Process patterns in batches
            batch = []
            processed_count = 0

            cursor = patterns_collection.find({})

            for pattern in cursor:
                try:
                    # Transform pattern
                    transformed = self.transform_pattern(pattern)
                    batch.append(transformed)

                    # Insert batch when full
                    if len(batch) >= self.batch_size:
                        self.batch_insert_clickhouse(batch)
                        self.stats['migrated_patterns'] += len(batch)
                        processed_count += len(batch)

                        # Progress report
                        progress_pct = (processed_count / total_patterns) * 100
                        logger.info(f"Progress: {processed_count:,}/{total_patterns:,} ({progress_pct:.1f}%)")

                        batch = []

                except Exception as e:
                    logger.error(f"Failed to process pattern: {e}")
                    self.stats['failed_patterns'] += 1
                    continue

            # Insert remaining patterns
            if batch:
                self.batch_insert_clickhouse(batch)
                self.stats['migrated_patterns'] += len(batch)
                processed_count += len(batch)

            logger.info(f"Progress: {processed_count:,}/{total_patterns:,} (100.0%)")

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
        logger.info(f"Total patterns:    {self.stats['total_patterns']:,}")
        logger.info(f"Migrated:          {self.stats['migrated_patterns']:,}")
        logger.info(f"Failed:            {self.stats['failed_patterns']:,}")

        if self.stats['start_time'] and self.stats['end_time']:
            duration = (self.stats['end_time'] - self.stats['start_time']).total_seconds()
            rate = self.stats['migrated_patterns'] / duration if duration > 0 else 0
            logger.info(f"Duration:          {duration:.1f} seconds")
            logger.info(f"Rate:              {rate:.0f} patterns/second")

        logger.info("=" * 80)


def main():
    """Main entry point for migration script."""
    parser = argparse.ArgumentParser(
        description='Migrate pattern data from MongoDB to ClickHouse'
    )
    parser.add_argument(
        '--mongo-url',
        default='mongodb://localhost:27017',
        help='MongoDB connection string (default: mongodb://localhost:27017)'
    )
    parser.add_argument(
        '--clickhouse-host',
        default='localhost',
        help='ClickHouse host (default: localhost)'
    )
    parser.add_argument(
        '--clickhouse-port',
        type=int,
        default=8123,
        help='ClickHouse port (default: 8123)'
    )
    parser.add_argument(
        '--clickhouse-db',
        default='default',
        help='ClickHouse database (default: default)'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=1000,
        help='Number of patterns per batch (default: 1000)'
    )
    parser.add_argument(
        '--processor-id',
        help='Optional processor ID to migrate specific collection'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Run migration without writing to ClickHouse'
    )

    args = parser.parse_args()

    # Create migration manager
    migration = MongoToClickHouseMigration(
        mongo_url=args.mongo_url,
        clickhouse_host=args.clickhouse_host,
        clickhouse_port=args.clickhouse_port,
        clickhouse_db=args.clickhouse_db,
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
