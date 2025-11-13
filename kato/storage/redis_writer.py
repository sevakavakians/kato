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
