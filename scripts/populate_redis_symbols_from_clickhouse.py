#!/usr/bin/env python3
"""
Populate Redis Symbol Statistics from ClickHouse

This script reads pattern data from ClickHouse and populates Redis with symbol statistics
that are needed for entropy calculations. This is a post-migration utility for systems
that migrated pattern data to ClickHouse but don't have Redis symbol statistics yet.

Usage:
    python scripts/populate_redis_symbols_from_clickhouse.py [--kb-id KB_ID] [--batch-size 1000] [--dry-run]

Environment Variables:
    CLICKHOUSE_HOST: ClickHouse host (default: localhost)
    CLICKHOUSE_PORT: ClickHouse port (default: 8123)
    CLICKHOUSE_DB: ClickHouse database (default: kato)
    REDIS_URL: Redis connection URL (default: redis://localhost:6379)
"""

import argparse
import logging
import sys
from collections import Counter
from datetime import datetime
from itertools import chain
from typing import Optional

import clickhouse_connect
import redis

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


class RedisSymbolPopulator:
    """
    Populates Redis with symbol statistics from ClickHouse pattern data.

    Calculates and stores:
    - Symbol frequency (total occurrences across all patterns)
    - Pattern member frequency (how many patterns contain each symbol)
    - Global totals (total symbols and patterns)
    """

    def __init__(self,
                 clickhouse_host: str = 'localhost',
                 clickhouse_port: int = 8123,
                 clickhouse_db: str = 'kato',
                 redis_url: str = 'redis://localhost:6379',
                 batch_size: int = 1000,
                 dry_run: bool = False):
        """
        Initialize populator.

        Args:
            clickhouse_host: ClickHouse host
            clickhouse_port: ClickHouse port
            clickhouse_db: ClickHouse database
            redis_url: Redis connection URL
            batch_size: Number of patterns to process per batch
            dry_run: If True, don't write to Redis
        """
        self.clickhouse_host = clickhouse_host
        self.clickhouse_port = clickhouse_port
        self.clickhouse_db = clickhouse_db
        self.redis_url = redis_url
        self.batch_size = batch_size
        self.dry_run = dry_run

        # Statistics
        self.stats = {
            'kb_ids_processed': 0,
            'patterns_processed': 0,
            'symbols_tracked': 0,
            'start_time': None,
            'end_time': None
        }

        # Connections
        self.clickhouse_client = None
        self.redis_client = None

    def connect(self):
        """Establish database connections."""
        logger.info(f"Connecting to ClickHouse: {self.clickhouse_host}:{self.clickhouse_port}")
        self.clickhouse_client = clickhouse_connect.get_client(
            host=self.clickhouse_host,
            port=self.clickhouse_port,
            database=self.clickhouse_db,
            compress=True
        )
        logger.info(f"Connected to ClickHouse database: {self.clickhouse_db}")

        if not self.dry_run:
            logger.info(f"Connecting to Redis: {self.redis_url}")
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            # Test connection
            self.redis_client.ping()
            logger.info("Connected to Redis")
        else:
            logger.info("DRY RUN MODE - Redis connection skipped")

    def disconnect(self):
        """Close database connections."""
        if self.clickhouse_client:
            self.clickhouse_client.close()
            logger.info("Disconnected from ClickHouse")

        if self.redis_client:
            self.redis_client.close()
            logger.info("Disconnected from Redis")

    def get_kb_ids(self) -> list[str]:
        """
        Get all kb_ids from ClickHouse.

        Returns:
            List of kb_id values
        """
        query = "SELECT DISTINCT kb_id FROM patterns_data ORDER BY kb_id"
        result = self.clickhouse_client.query(query)
        kb_ids = [row[0] for row in result.result_rows]
        logger.info(f"Found {len(kb_ids)} kb_ids: {kb_ids}")
        return kb_ids

    def populate_kb(self, kb_id: str):
        """
        Populate Redis symbol statistics for one kb_id.

        Args:
            kb_id: Knowledge base identifier
        """
        logger.info("=" * 80)
        logger.info(f"Processing kb_id: {kb_id}")
        logger.info("=" * 80)

        # Get total pattern count for this kb_id
        count_query = f"SELECT COUNT(*) FROM patterns_data WHERE kb_id = '{kb_id}'"
        total_patterns = self.clickhouse_client.query(count_query).result_rows[0][0]
        logger.info(f"Total patterns for {kb_id}: {total_patterns:,}")

        if total_patterns == 0:
            logger.warning(f"No patterns found for {kb_id}, skipping")
            return

        # Track symbol statistics for this kb_id
        symbol_frequency = Counter()  # Total occurrences of each symbol
        symbol_pattern_count = Counter()  # Number of patterns containing each symbol
        total_symbol_count = 0  # Sum of all symbol occurrences

        # Process patterns in batches
        offset = 0
        patterns_processed = 0

        while offset < total_patterns:
            # Query batch of patterns
            query = f"""
                SELECT name, pattern_data
                FROM patterns_data
                WHERE kb_id = '{kb_id}'
                LIMIT {self.batch_size} OFFSET {offset}
            """
            result = self.clickhouse_client.query(query)

            for row in result.result_rows:
                pattern_name = row[0]
                pattern_data = row[1]  # List of events (list of lists)

                # Flatten pattern_data to get all symbols
                try:
                    all_symbols = list(chain(*pattern_data))
                except TypeError:
                    logger.error(f"Invalid pattern_data for {pattern_name}: {pattern_data}")
                    continue

                # Count symbol occurrences in this pattern
                symbol_counts = Counter(all_symbols)

                # Update frequency (total occurrences)
                symbol_frequency.update(symbol_counts)

                # Update pattern member frequency (which symbols appear in this pattern)
                for symbol in symbol_counts.keys():
                    symbol_pattern_count[symbol] += 1

                # Update total symbol count
                total_symbol_count += len(all_symbols)

                patterns_processed += 1

                if patterns_processed % 10000 == 0:
                    logger.info(f"  Processed {patterns_processed:,}/{total_patterns:,} patterns...")

            offset += self.batch_size

        logger.info(f"Completed processing {patterns_processed:,} patterns")
        logger.info(f"Unique symbols found: {len(symbol_frequency):,}")
        logger.info(f"Total symbol occurrences: {total_symbol_count:,}")

        # Write to Redis
        if not self.dry_run:
            logger.info("Writing symbol statistics to Redis...")
            self._write_to_redis(kb_id, symbol_frequency, symbol_pattern_count, total_symbol_count, patterns_processed)
        else:
            logger.info(f"DRY RUN: Would write {len(symbol_frequency)} symbols to Redis for {kb_id}")

        # Update stats
        self.stats['patterns_processed'] += patterns_processed
        self.stats['symbols_tracked'] += len(symbol_frequency)
        self.stats['kb_ids_processed'] += 1

    def _write_to_redis(self, kb_id: str, symbol_frequency: Counter, symbol_pattern_count: Counter,
                        total_symbol_count: int, total_patterns: int):
        """
        Write symbol statistics to Redis.

        Args:
            kb_id: Knowledge base identifier
            symbol_frequency: Counter of symbol occurrences
            symbol_pattern_count: Counter of patterns per symbol
            total_symbol_count: Total symbol occurrences
            total_patterns: Total pattern count
        """
        pipeline = self.redis_client.pipeline()
        write_count = 0

        # Write symbol statistics
        for symbol, freq in symbol_frequency.items():
            freq_key = f"{kb_id}:symbol:freq:{symbol}"
            pmf_key = f"{kb_id}:symbol:pmf:{symbol}"
            pmf = symbol_pattern_count[symbol]

            pipeline.set(freq_key, freq)
            pipeline.set(pmf_key, pmf)
            write_count += 2

            # Execute pipeline in batches to avoid memory issues
            if write_count >= 10000:
                pipeline.execute()
                pipeline = self.redis_client.pipeline()
                logger.debug(f"  Wrote {write_count} keys to Redis...")
                write_count = 0

        # Write global statistics
        symbols_key = f"{kb_id}:global:total_symbols_in_patterns_frequencies"
        patterns_key = f"{kb_id}:global:total_pattern_frequencies"
        pipeline.set(symbols_key, total_symbol_count)
        pipeline.set(patterns_key, total_patterns)
        write_count += 2

        # Execute remaining operations
        if write_count > 0:
            pipeline.execute()

        logger.info(f"✓ Wrote {len(symbol_frequency):,} symbols + global stats to Redis for {kb_id}")

    def populate_all(self, specific_kb_id: Optional[str] = None):
        """
        Populate Redis for all kb_ids or a specific one.

        Args:
            specific_kb_id: If provided, only process this kb_id
        """
        logger.info("=" * 80)
        logger.info("Redis Symbol Statistics Population Started")
        logger.info("=" * 80)

        self.stats['start_time'] = datetime.now()

        try:
            # Connect to databases
            self.connect()

            # Get kb_ids to process
            if specific_kb_id:
                kb_ids = [specific_kb_id]
                logger.info(f"Processing specific kb_id: {specific_kb_id}")
            else:
                kb_ids = self.get_kb_ids()

            # Process each kb_id
            for kb_id in kb_ids:
                try:
                    self.populate_kb(kb_id)
                except Exception as e:
                    logger.error(f"Failed to process {kb_id}: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
                    continue

            self.stats['end_time'] = datetime.now()

            # Print summary
            self._print_summary()

        except Exception as e:
            logger.error(f"Population failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            raise
        finally:
            self.disconnect()

    def _print_summary(self):
        """Print execution summary."""
        logger.info("=" * 80)
        logger.info("POPULATION COMPLETE")
        logger.info("=" * 80)
        logger.info(f"KB IDs processed: {self.stats['kb_ids_processed']}")
        logger.info(f"Patterns processed: {self.stats['patterns_processed']:,}")
        logger.info(f"Unique symbols tracked: {self.stats['symbols_tracked']:,}")

        if self.stats['start_time'] and self.stats['end_time']:
            duration = self.stats['end_time'] - self.stats['start_time']
            logger.info(f"Duration: {duration}")
            if duration.total_seconds() > 0:
                rate = self.stats['patterns_processed'] / duration.total_seconds()
                logger.info(f"Processing rate: {rate:.1f} patterns/sec")

        logger.info("=" * 80)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Populate Redis with symbol statistics from ClickHouse patterns'
    )
    parser.add_argument(
        '--kb-id',
        type=str,
        help='Specific kb_id to process (default: all)'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=1000,
        help='Number of patterns per batch (default: 1000)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Analyze patterns without writing to Redis'
    )
    parser.add_argument(
        '--clickhouse-host',
        type=str,
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
        type=str,
        default='kato',
        help='ClickHouse database (default: kato)'
    )
    parser.add_argument(
        '--redis-url',
        type=str,
        default='redis://localhost:6379',
        help='Redis URL (default: redis://localhost:6379)'
    )

    args = parser.parse_args()

    # Create populator
    populator = RedisSymbolPopulator(
        clickhouse_host=args.clickhouse_host,
        clickhouse_port=args.clickhouse_port,
        clickhouse_db=args.clickhouse_db,
        redis_url=args.redis_url,
        batch_size=args.batch_size,
        dry_run=args.dry_run
    )

    # Run population
    try:
        populator.populate_all(specific_kb_id=args.kb_id)
        sys.exit(0)
    except Exception as e:
        logger.error(f"Population failed: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
