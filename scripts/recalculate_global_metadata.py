#!/usr/bin/env python3
"""
Recalculate Global Metadata Totals and Symbol Statistics

This script recalculates:
1. Global metadata totals (total_symbols_in_patterns_frequencies and total_pattern_frequencies)
2. Symbol statistics (frequency and pattern_member_frequency for each symbol)

Usage:
    python scripts/recalculate_global_metadata.py [--dry-run]

Environment Variables:
    REDIS_URL: Redis connection string (default: redis://localhost:6379)
    CLICKHOUSE_HOST: ClickHouse host (default: localhost)
    CLICKHOUSE_PORT: ClickHouse port (default: 8123)
    CLICKHOUSE_DB: ClickHouse database (default: kato)
"""

import argparse
import logging
import sys
from collections import defaultdict
from itertools import chain

import redis
import clickhouse_connect

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


class GlobalMetadataRecalculator:
    """Recalculates global metadata totals from existing patterns."""

    def __init__(self, redis_url: str, clickhouse_host: str, clickhouse_port: int,
                 clickhouse_db: str, dry_run: bool = False):
        """
        Initialize recalculator.

        Args:
            redis_url: Redis connection URL
            clickhouse_host: ClickHouse host
            clickhouse_port: ClickHouse port
            clickhouse_db: ClickHouse database
            dry_run: If True, don't write to Redis
        """
        self.redis_url = redis_url
        self.clickhouse_host = clickhouse_host
        self.clickhouse_port = clickhouse_port
        self.clickhouse_db = clickhouse_db
        self.dry_run = dry_run

        self.redis_client = None
        self.clickhouse_client = None

    def connect(self):
        """Establish database connections."""
        logger.info(f"Connecting to Redis: {self.redis_url}")
        self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
        self.redis_client.ping()
        logger.info("Connected to Redis")

        logger.info(f"Connecting to ClickHouse: {self.clickhouse_host}:{self.clickhouse_port}")
        self.clickhouse_client = clickhouse_connect.get_client(
            host=self.clickhouse_host,
            port=self.clickhouse_port,
            database=self.clickhouse_db
        )
        logger.info("Connected to ClickHouse")

    def disconnect(self):
        """Close database connections."""
        if self.redis_client:
            self.redis_client.close()
            logger.info("Disconnected from Redis")

        if self.clickhouse_client:
            self.clickhouse_client.close()
            logger.info("Disconnected from ClickHouse")

    def get_all_kb_ids(self) -> set[str]:
        """
        Get all unique kb_ids from Redis frequency keys.

        Returns:
            Set of kb_id strings
        """
        logger.info("Scanning Redis for kb_ids...")
        kb_ids = set()

        # Scan for all frequency keys: {kb_id}:frequency:*
        for key in self.redis_client.scan_iter(match="*:frequency:*", count=1000):
            # Extract kb_id from key format: kb_id:frequency:pattern_name
            parts = key.split(':frequency:', 1)
            if len(parts) == 2:
                kb_id = parts[0]
                kb_ids.add(kb_id)

        logger.info(f"Found {len(kb_ids)} unique kb_ids: {sorted(kb_ids)}")
        return kb_ids

    def get_pattern_frequencies(self, kb_id: str) -> dict[str, int]:
        """
        Get all pattern frequencies for a kb_id from Redis.

        Args:
            kb_id: Knowledge base identifier

        Returns:
            Dictionary mapping pattern_name to frequency
        """
        logger.info(f"Getting pattern frequencies for kb_id: {kb_id}")
        pattern_freqs = {}

        pattern_key = f"{kb_id}:frequency:*"
        for key in self.redis_client.scan_iter(match=pattern_key, count=1000):
            # Extract pattern name from key: kb_id:frequency:pattern_name
            pattern_name = key.split(f"{kb_id}:frequency:", 1)[1]
            frequency = int(self.redis_client.get(key))
            pattern_freqs[pattern_name] = frequency

        logger.info(f"Found {len(pattern_freqs)} patterns for kb_id: {kb_id}")
        return pattern_freqs

    def get_pattern_lengths_from_clickhouse(self, kb_id: str, pattern_names: list[str]) -> dict[str, int]:
        """
        Get pattern lengths from ClickHouse.

        Args:
            kb_id: Knowledge base identifier
            pattern_names: List of pattern names to query

        Returns:
            Dictionary mapping pattern_name to length (number of symbols)
        """
        logger.info(f"Querying ClickHouse for {len(pattern_names)} pattern lengths...")

        if not pattern_names:
            return {}

        # Query pattern lengths in batches
        batch_size = 1000
        all_lengths = {}

        for i in range(0, len(pattern_names), batch_size):
            batch = pattern_names[i:i+batch_size]

            # Build IN clause for SQL query
            names_list = "','".join(batch)
            query = f"""
                SELECT name, length
                FROM {self.clickhouse_db}.patterns_data
                WHERE kb_id = '{kb_id}' AND name IN ('{names_list}')
            """

            result = self.clickhouse_client.query(query)
            for row in result.result_rows:
                pattern_name, length = row
                all_lengths[pattern_name] = length

            logger.debug(f"Processed batch {i//batch_size + 1}: {len(batch)} patterns")

        logger.info(f"Retrieved {len(all_lengths)} pattern lengths from ClickHouse")
        return all_lengths

    def calculate_totals(self, kb_id: str) -> tuple[int, int]:
        """
        Calculate global totals for a kb_id.

        Args:
            kb_id: Knowledge base identifier

        Returns:
            Tuple of (total_symbols_in_patterns_frequencies, total_pattern_frequencies)
        """
        logger.info(f"Calculating totals for kb_id: {kb_id}")

        # Get pattern frequencies from Redis
        pattern_freqs = self.get_pattern_frequencies(kb_id)

        if not pattern_freqs:
            logger.warning(f"No patterns found for kb_id: {kb_id}")
            return 0, 0

        # Get pattern lengths from ClickHouse
        pattern_names = list(pattern_freqs.keys())
        pattern_lengths = self.get_pattern_lengths_from_clickhouse(kb_id, pattern_names)

        # Calculate totals
        total_symbols = 0
        total_patterns = 0

        for pattern_name, frequency in pattern_freqs.items():
            length = pattern_lengths.get(pattern_name)
            if length is None:
                logger.warning(f"Pattern {pattern_name} not found in ClickHouse, skipping")
                continue

            # total_symbols_in_patterns_frequencies = sum(frequency * length for all patterns)
            total_symbols += frequency * length
            # total_pattern_frequencies = sum(frequency for all patterns)
            total_patterns += frequency

        logger.info(f"Calculated totals for {kb_id}:")
        logger.info(f"  - Total symbols in patterns frequencies: {total_symbols}")
        logger.info(f"  - Total pattern frequencies: {total_patterns}")

        return total_symbols, total_patterns

    def update_global_metadata(self, kb_id: str, total_symbols: int, total_patterns: int):
        """
        Update global metadata totals in Redis.

        Args:
            kb_id: Knowledge base identifier
            total_symbols: Total symbols in patterns frequencies
            total_patterns: Total pattern frequencies
        """
        if self.dry_run:
            logger.info(f"DRY RUN: Would update Redis for kb_id: {kb_id}")
            logger.info(f"  - Set {kb_id}:global:total_symbols_in_patterns_frequencies = {total_symbols}")
            logger.info(f"  - Set {kb_id}:global:total_pattern_frequencies = {total_patterns}")
            return

        symbols_key = f"{kb_id}:global:total_symbols_in_patterns_frequencies"
        patterns_key = f"{kb_id}:global:total_pattern_frequencies"

        self.redis_client.set(symbols_key, total_symbols)
        self.redis_client.set(patterns_key, total_patterns)

        logger.info(f"Updated global metadata for kb_id: {kb_id}")
        logger.info(f"  - {symbols_key} = {total_symbols}")
        logger.info(f"  - {patterns_key} = {total_patterns}")

    def populate_symbol_statistics(self, kb_id: str):
        """
        Populate symbol statistics (frequency and pattern_member_frequency) in Redis.

        Args:
            kb_id: Knowledge base identifier
        """
        logger.info(f"Populating symbol statistics for kb_id: {kb_id}")

        # Get all patterns with their data from ClickHouse
        query = f"""
            SELECT name, pattern_data, length
            FROM {self.clickhouse_db}.patterns_data
            WHERE kb_id = '{kb_id}'
        """

        patterns = self.clickhouse_client.query(query)

        if not patterns.result_rows:
            logger.warning(f"No patterns found in ClickHouse for kb_id: {kb_id}")
            return

        logger.info(f"Processing {len(patterns.result_rows)} patterns for symbol statistics")

        # Track symbol statistics
        from collections import Counter
        from itertools import chain
        import json

        symbol_frequency = Counter()  # Total occurrences across all patterns
        symbol_pmf = Counter()  # Pattern membership frequency (unique patterns per symbol)

        # Get pattern frequencies from Redis
        pattern_freqs = self.get_pattern_frequencies(kb_id)

        # Process each pattern
        for row in patterns.result_rows:
            pattern_name, pattern_data_raw, length = row

            # Parse pattern_data (may already be a list from ClickHouse array type)
            if isinstance(pattern_data_raw, str):
                pattern_data = json.loads(pattern_data_raw)
            elif isinstance(pattern_data_raw, list):
                pattern_data = pattern_data_raw
            else:
                logger.warning(f"Unexpected pattern_data type for {pattern_name}: {type(pattern_data_raw)}")
                continue

            # Get pattern frequency from Redis
            freq = pattern_freqs.get(pattern_name, 1)

            # Flatten pattern_data to get all symbols
            all_symbols = list(chain(*pattern_data))

            # Count occurrences of each symbol in this pattern
            symbol_counts = Counter(all_symbols)

            # Update statistics
            for symbol, count in symbol_counts.items():
                # Increment frequency by (count * pattern_frequency)
                symbol_frequency[symbol] += count * freq
                # Increment pattern_member_frequency by 1 (this pattern contains this symbol)
                symbol_pmf[symbol] += 1

        logger.info(f"Calculated statistics for {len(symbol_frequency)} unique symbols")

        # Write to Redis
        if self.dry_run:
            logger.info(f"DRY RUN: Would write {len(symbol_frequency)} symbol statistics to Redis")
            # Show sample
            sample_symbols = list(symbol_frequency.keys())[:5]
            for symbol in sample_symbols:
                logger.info(f"  - {symbol}: freq={symbol_frequency[symbol]}, pmf={symbol_pmf[symbol]}")
            return

        # Write symbol statistics to Redis
        for symbol in symbol_frequency:
            freq_key = f"{kb_id}:symbol:freq:{symbol}"
            pmf_key = f"{kb_id}:symbol:pmf:{symbol}"

            self.redis_client.set(freq_key, symbol_frequency[symbol])
            self.redis_client.set(pmf_key, symbol_pmf[symbol])

        logger.info(f"Wrote {len(symbol_frequency)} symbol statistics to Redis for kb_id: {kb_id}")

    def recalculate_all(self):
        """Recalculate global metadata for all kb_ids."""
        logger.info("Starting global metadata recalculation")

        try:
            # Get all kb_ids
            kb_ids = self.get_all_kb_ids()

            if not kb_ids:
                logger.warning("No kb_ids found in Redis")
                return

            # Process each kb_id
            for kb_id in sorted(kb_ids):
                logger.info(f"\n{'='*80}")
                logger.info(f"Processing kb_id: {kb_id}")
                logger.info(f"{'='*80}")

                # Calculate and update global metadata totals
                total_symbols, total_patterns = self.calculate_totals(kb_id)
                self.update_global_metadata(kb_id, total_symbols, total_patterns)

                # Populate symbol statistics
                self.populate_symbol_statistics(kb_id)

            logger.info(f"\n{'='*80}")
            logger.info(f"Recalculation complete for {len(kb_ids)} kb_ids")
            logger.info(f"{'='*80}")

        except Exception as e:
            logger.error(f"Error during recalculation: {e}")
            raise


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Recalculate global metadata totals from existing patterns'
    )
    parser.add_argument(
        '--redis-url',
        default='redis://localhost:6379',
        help='Redis connection URL (default: redis://localhost:6379)'
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
        default='kato',
        help='ClickHouse database (default: kato)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Print what would be done without making changes'
    )

    args = parser.parse_args()

    logger.info("="*80)
    logger.info("GLOBAL METADATA RECALCULATION")
    logger.info("="*80)
    logger.info(f"Redis URL: {args.redis_url}")
    logger.info(f"ClickHouse: {args.clickhouse_host}:{args.clickhouse_port}/{args.clickhouse_db}")
    logger.info(f"Dry run: {args.dry_run}")
    logger.info("="*80)

    recalculator = GlobalMetadataRecalculator(
        redis_url=args.redis_url,
        clickhouse_host=args.clickhouse_host,
        clickhouse_port=args.clickhouse_port,
        clickhouse_db=args.clickhouse_db,
        dry_run=args.dry_run
    )

    try:
        recalculator.connect()
        recalculator.recalculate_all()
    except KeyboardInterrupt:
        logger.warning("\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        recalculator.disconnect()

    logger.info("\nRecalculation completed successfully!")


if __name__ == '__main__':
    main()
