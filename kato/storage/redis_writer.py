"""
Redis Writer for Pattern Metadata Storage

Handles writing pattern metadata to Redis with:
- Frequency counters
- Emotives (emotional context)
- Metadata (tags, categories, etc.)

All keys are namespaced by kb_id for complete isolation.
"""

import json
import logging
from typing import Any, Optional

logger = logging.getLogger('kato.storage.redis_writer')


class RedisWriter:
    """Writes pattern metadata to Redis."""

    def __init__(self, kb_id: str, redis_client):
        """
        Initialize Redis writer.

        Args:
            kb_id: Knowledge base identifier (used for key namespacing)
            redis_client: Redis client from connection manager
        """
        self.kb_id = kb_id
        self.client = redis_client

        if not self.client:
            raise RuntimeError("Redis client is required but was None")

        logger.debug(f"RedisWriter initialized for kb_id: {kb_id}")

    def write_metadata(self, pattern_name: str, frequency: int = 1,
                      emotives: Optional[dict] = None,
                      metadata: Optional[dict] = None) -> bool:
        """
        Store pattern metadata in Redis with kb_id namespacing.

        Args:
            pattern_name: Pattern name (hash)
            frequency: Pattern frequency (default: 1 for new patterns)
            emotives: Emotional context dictionary
            metadata: Additional metadata dictionary

        Returns:
            True if write successful

        Raises:
            Exception: If write fails
        """
        try:
            # Store frequency
            freq_key = f"{self.kb_id}:frequency:{pattern_name}"
            self.client.set(freq_key, frequency)

            # Store emotives as JSON if provided
            if emotives:
                emotives_key = f"{self.kb_id}:emotives:{pattern_name}"
                self.client.set(emotives_key, json.dumps(emotives))

            # Store metadata as JSON if provided
            if metadata:
                metadata_key = f"{self.kb_id}:metadata:{pattern_name}"
                self.client.set(metadata_key, json.dumps(metadata))

            logger.debug(f"Wrote metadata for pattern {pattern_name} to Redis (kb_id={self.kb_id})")
            return True

        except Exception as e:
            logger.error(f"Failed to write metadata for pattern {pattern_name}: {e}")
            raise

    def increment_frequency(self, pattern_name: str) -> int:
        """
        Increment pattern frequency counter.

        Args:
            pattern_name: Pattern name (hash)

        Returns:
            New frequency value after increment

        Raises:
            Exception: If increment fails
        """
        try:
            freq_key = f"{self.kb_id}:frequency:{pattern_name}"
            new_freq = self.client.incr(freq_key)
            logger.debug(f"Incremented frequency for {pattern_name} to {new_freq}")
            return new_freq

        except Exception as e:
            logger.error(f"Failed to increment frequency for {pattern_name}: {e}")
            raise

    def get_frequency(self, pattern_name: str) -> int:
        """
        Get pattern frequency.

        Args:
            pattern_name: Pattern name (hash)

        Returns:
            Pattern frequency (0 if not found)
        """
        try:
            freq_key = f"{self.kb_id}:frequency:{pattern_name}"
            freq = self.client.get(freq_key)
            return int(freq) if freq else 0

        except Exception as e:
            logger.error(f"Failed to get frequency for {pattern_name}: {e}")
            return 0

    def pattern_exists(self, pattern_name: str) -> bool:
        """
        Check if pattern exists in Redis.

        Args:
            pattern_name: Pattern name (hash)

        Returns:
            True if frequency key exists
        """
        try:
            freq_key = f"{self.kb_id}:frequency:{pattern_name}"
            return self.client.exists(freq_key) > 0

        except Exception as e:
            logger.error(f"Failed to check if pattern {pattern_name} exists: {e}")
            return False

    def get_metadata(self, pattern_name: str) -> dict[str, Any]:
        """
        Retrieve all metadata for a pattern.

        Args:
            pattern_name: Pattern name (hash)

        Returns:
            Dictionary with frequency, emotives, and metadata
        """
        try:
            result = {'name': pattern_name}

            # Get frequency
            freq_key = f"{self.kb_id}:frequency:{pattern_name}"
            freq = self.client.get(freq_key)
            result['frequency'] = int(freq) if freq else 0

            # Get emotives
            emotives_key = f"{self.kb_id}:emotives:{pattern_name}"
            emotives = self.client.get(emotives_key)
            if emotives:
                result['emotives'] = json.loads(emotives)

            # Get metadata
            metadata_key = f"{self.kb_id}:metadata:{pattern_name}"
            metadata = self.client.get(metadata_key)
            if metadata:
                result['metadata'] = json.loads(metadata)

            return result

        except Exception as e:
            logger.error(f"Failed to get metadata for {pattern_name}: {e}")
            return {'name': pattern_name, 'frequency': 0}

    def delete_all_metadata(self) -> int:
        """
        Delete all keys for this kb_id.

        Returns:
            Number of keys deleted

        Raises:
            Exception: If deletion fails
        """
        try:
            # Find all keys for this kb_id
            pattern = f"{self.kb_id}:*"
            keys = list(self.client.scan_iter(match=pattern, count=1000))

            if not keys:
                logger.debug(f"No Redis keys found for kb_id: {self.kb_id}")
                return 0

            # Delete all keys
            deleted = self.client.delete(*keys)
            logger.info(f"Deleted {deleted} Redis keys for kb_id: {self.kb_id}")
            return deleted

        except Exception as e:
            logger.error(f"Failed to delete Redis keys for {self.kb_id}: {e}")
            raise

    def count_patterns(self) -> int:
        """
        Count patterns for this kb_id (counts frequency keys).

        Returns:
            Number of patterns (frequency keys) for this kb_id
        """
        try:
            pattern = f"{self.kb_id}:frequency:*"
            count = sum(1 for _ in self.client.scan_iter(match=pattern, count=1000))
            return count

        except Exception as e:
            logger.error(f"Failed to count patterns for {self.kb_id}: {e}")
            return 0

    def get_global_metadata(self) -> dict[str, int]:
        """
        Get global metadata totals for this kb_id.

        Returns:
            Dictionary with total_symbols_in_patterns_frequencies and total_pattern_frequencies
        """
        try:
            # Get total_symbols_in_patterns_frequencies
            symbols_key = f"{self.kb_id}:global:total_symbols_in_patterns_frequencies"
            symbols_total = self.client.get(symbols_key)

            # Get total_pattern_frequencies
            patterns_key = f"{self.kb_id}:global:total_pattern_frequencies"
            patterns_total = self.client.get(patterns_key)

            return {
                'total_symbols_in_patterns_frequencies': int(symbols_total) if symbols_total else 0,
                'total_pattern_frequencies': int(patterns_total) if patterns_total else 0
            }

        except Exception as e:
            logger.error(f"Failed to get global metadata for {self.kb_id}: {e}")
            return {
                'total_symbols_in_patterns_frequencies': 0,
                'total_pattern_frequencies': 0
            }

    def increment_global_symbol_count(self, count: int) -> int:
        """
        Increment global total_symbols_in_patterns_frequencies counter.

        Args:
            count: Number to increment by (number of symbols in pattern)

        Returns:
            New total value after increment
        """
        try:
            symbols_key = f"{self.kb_id}:global:total_symbols_in_patterns_frequencies"
            new_total = self.client.incrby(symbols_key, count)
            logger.debug(f"Incremented global symbol count by {count} to {new_total}")
            return new_total

        except Exception as e:
            logger.error(f"Failed to increment global symbol count: {e}")
            raise

    def increment_global_pattern_count(self, count: int = 1) -> int:
        """
        Increment global total_pattern_frequencies counter.

        Args:
            count: Number to increment by (typically 1 for each pattern learned)

        Returns:
            New total value after increment
        """
        try:
            patterns_key = f"{self.kb_id}:global:total_pattern_frequencies"
            new_total = self.client.incrby(patterns_key, count)
            logger.debug(f"Incremented global pattern count by {count} to {new_total}")
            return new_total

        except Exception as e:
            logger.error(f"Failed to increment global pattern count: {e}")
            raise

    def increment_symbol_frequency(self, symbol: str, count: int = 1) -> int:
        """
        Increment symbol frequency counter.

        Tracks total occurrences of this symbol across all patterns.
        If a symbol appears 3 times in a pattern with frequency=2,
        this increments by 3*2=6.

        Args:
            symbol: Symbol name
            count: Number to increment by

        Returns:
            New frequency value after increment

        Raises:
            Exception: If increment fails
        """
        try:
            freq_key = f"{self.kb_id}:symbol:freq:{symbol}"
            new_freq = self.client.incrby(freq_key, count)
            logger.debug(f"Incremented symbol frequency for {symbol} by {count} to {new_freq}")
            return new_freq

        except Exception as e:
            logger.error(f"Failed to increment symbol frequency for {symbol}: {e}")
            raise

    def increment_pattern_member_frequency(self, symbol: str, count: int = 1) -> int:
        """
        Increment pattern member frequency for a symbol.

        Tracks how many patterns contain this symbol (counted once per pattern).
        Used for calculating symbol probability across pattern space.

        Args:
            symbol: Symbol name
            count: Number to increment by (typically 1 per pattern)

        Returns:
            New pattern_member_frequency value after increment

        Raises:
            Exception: If increment fails
        """
        try:
            pmf_key = f"{self.kb_id}:symbol:pmf:{symbol}"
            new_pmf = self.client.incrby(pmf_key, count)
            logger.debug(f"Incremented pattern_member_frequency for {symbol} by {count} to {new_pmf}")
            return new_pmf

        except Exception as e:
            logger.error(f"Failed to increment pattern_member_frequency for {symbol}: {e}")
            raise

    def get_symbol_stats(self, symbol: str) -> dict[str, Any]:
        """
        Get all statistics for a symbol.

        Args:
            symbol: Symbol name

        Returns:
            Dictionary with 'frequency' and 'pattern_member_frequency'

        Raises:
            Exception: If retrieval fails
        """
        try:
            freq_key = f"{self.kb_id}:symbol:freq:{symbol}"
            pmf_key = f"{self.kb_id}:symbol:pmf:{symbol}"

            freq = self.client.get(freq_key)
            pmf = self.client.get(pmf_key)

            return {
                'name': symbol,
                'frequency': int(freq) if freq else 0,
                'pattern_member_frequency': int(pmf) if pmf else 0
            }

        except Exception as e:
            logger.error(f"Failed to get symbol stats for {symbol}: {e}")
            raise

    def get_all_symbols_batch(self) -> dict[str, dict[str, Any]]:
        """
        Get statistics for all symbols in this kb_id.

        Returns:
            Dictionary mapping symbol names to their statistics

        Raises:
            Exception: If retrieval fails
        """
        try:
            # Scan for all symbol frequency keys
            freq_pattern = f"{self.kb_id}:symbol:freq:*"
            symbols = {}

            for freq_key in self.client.scan_iter(match=freq_pattern, count=1000):
                # Extract symbol name from key: kb_id:symbol:freq:symbol_name
                symbol_name = freq_key.split(f"{self.kb_id}:symbol:freq:", 1)[1]

                # Get both frequency and pattern_member_frequency
                pmf_key = f"{self.kb_id}:symbol:pmf:{symbol_name}"
                freq = self.client.get(freq_key)
                pmf = self.client.get(pmf_key)

                symbols[symbol_name] = {
                    'name': symbol_name,
                    'frequency': int(freq) if freq else 0,
                    'pattern_member_frequency': int(pmf) if pmf else 0
                }

            logger.debug(f"Retrieved {len(symbols)} symbols for kb_id: {self.kb_id}")
            return symbols

        except Exception as e:
            logger.error(f"Failed to get all symbols for {self.kb_id}: {e}")
            raise
