"""
KATO Processor Management Implementation

This module provides per-user processor isolation for true multi-user support.
Each user gets their own KatoProcessor instance with isolated MongoDB and Qdrant databases.

Critical requirement: Each user maintains their own persistent knowledge base
that survives across sessions.
"""

import asyncio
import logging
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from kato.config.configuration_service import get_configuration_service
from kato.config.session_config import SessionConfiguration
from kato.config.settings import get_settings
from kato.workers.kato_processor import KatoProcessor
import contextlib

logger = logging.getLogger('kato.processors.manager')


class ProcessorManager:
    """
    Manages KatoProcessor instances per user with complete database isolation.

    This is the core component that enables true multi-user support in KATO.
    Each user gets their own MongoDB database and Qdrant collection.
    """

    def __init__(
        self,
        base_processor_id: str,
        max_processors: int = 100,
        eviction_ttl_seconds: int = 3600
    ):
        """
        Initialize the processor manager.

        Args:
            base_processor_id: Base ID for processors (e.g., "primary-v2")
            max_processors: Maximum number of cached processors (LRU eviction)
            eviction_ttl_seconds: TTL before idle processors are evicted
        """
        self.base_processor_id = base_processor_id
        self.max_processors = max_processors
        self.eviction_ttl = eviction_ttl_seconds

        # OrderedDict for LRU cache behavior
        self.processors: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self.processor_locks: dict[str, asyncio.Lock] = {}
        self.settings = get_settings()
        self.config_service = get_configuration_service(self.settings)

        # Background cleanup task
        self._cleanup_task = None
        self._cleanup_interval = 300  # 5 minutes

        logger.info(
            f"ProcessorManager initialized with base_id={base_processor_id}, "
            f"max={max_processors}, ttl={eviction_ttl_seconds}s"
        )

    def _get_processor_id(self, node_id: str) -> str:
        """
        Generate processor ID for a specific node.

        Args:
            node_id: Node identifier

        Returns:
            Processor ID in format "{node_id}_{base_processor_id}"
        """
        # Clean node_id to be MongoDB-safe
        # MongoDB doesn't allow: / \ . " $ * < > : | ? in database names
        # Also replace hyphens with underscores
        safe_node_id = node_id
        for char in ['/', '\\', '.', '"', '$', '*', '<', '>', ':', '|', '?', '-', ' ']:
            safe_node_id = safe_node_id.replace(char, '_')

        # Clean base_processor_id too
        safe_base_id = self.base_processor_id.replace('-', '_')

        # MongoDB database name limit is 64 characters but we use 60 for absolute safety
        # Calculate the final name and ensure it fits
        full_name = f"{safe_node_id}_{safe_base_id}"

        if len(full_name) > 60:  # Use 60 for extra safety margin
            # Need to truncate node_id to fit
            import hashlib
            node_hash = hashlib.md5(safe_node_id.encode(), usedforsecurity=False).hexdigest()[:8]

            # Calculate exact space available for node_id
            # Format: {truncated_node}_{hash}_{base_id}
            # So we need: len(base_id) + 1 (underscore) + 8 (hash) + 1 (underscore)
            max_node_length = 60 - len(safe_base_id) - 1 - 8 - 1

            truncated_node = safe_node_id[:max_node_length]
            safe_node_id = f"{truncated_node}_{node_hash}"

            # Log for debugging
            final_name = f"{safe_node_id}_{safe_base_id}"
            logger.info(f"Truncated node_id for MongoDB: orig={node_id}, final={final_name}, len={len(final_name)}")

        return f"{safe_node_id}_{safe_base_id}"

    async def get_processor(self, node_id: str, session_config: Optional[SessionConfiguration] = None) -> KatoProcessor:
        """
        Get or create a processor for a specific node.

        Args:
            node_id: Node identifier
            session_config: Optional session configuration to apply

        Returns:
            KatoProcessor instance for this node
        """
        processor_id = self._get_processor_id(node_id)

        # Check if processor exists and is not expired
        if processor_id in self.processors:
            processor_info = self.processors[processor_id]
            processor_info['last_accessed'] = datetime.now(timezone.utc)

            # Move to end for LRU
            self.processors.move_to_end(processor_id)

            # Return processor without mutating its config
            # Config is now passed as parameter to processor methods
            processor = processor_info['processor']

            logger.debug(f"Returning cached processor for node {node_id}")
            return processor

        # Need to create new processor
        if processor_id not in self.processor_locks:
            self.processor_locks[processor_id] = asyncio.Lock()

        async with self.processor_locks[processor_id]:
            # Double-check after acquiring lock
            if processor_id in self.processors:
                processor_info = self.processors[processor_id]
                processor_info['last_accessed'] = datetime.now(timezone.utc)
                self.processors.move_to_end(processor_id)
                return processor_info['processor']

            # Create new processor
            logger.info(f"Creating new processor for node {node_id}")

            # Create processor instance with minimal parameters
            # Configuration is now session-based only - no processor-level config
            processor = KatoProcessor(
                name=f"Node-{node_id}",
                processor_id=processor_id,
                settings=self.settings
            )

            # Initialize async components
            await processor.initialize_async_components()

            # Store in cache
            self.processors[processor_id] = {
                'processor': processor,
                'node_id': node_id,
                'created_at': datetime.now(timezone.utc),
                'last_accessed': datetime.now(timezone.utc),
                'access_count': 1
            }

            # Enforce max processors limit (LRU eviction)
            if len(self.processors) > self.max_processors:
                self._evict_oldest()

            # Start cleanup task if not running
            if not self._cleanup_task:
                self._cleanup_task = asyncio.create_task(self._cleanup_loop())

            return processor

    def _evict_oldest(self):
        """Evict the least recently used processor with resource cleanup."""
        if not self.processors:
            return

        # OrderedDict pops first item (oldest)
        evicted_id, evicted_info = self.processors.popitem(last=False)

        # Clean up processor resources
        try:
            processor = evicted_info['processor']

            # Clean up Qdrant collection
            if hasattr(processor, 'vector_processor') and \
               hasattr(processor.vector_processor, 'vector_indexer'):
                try:
                    processor.vector_processor.vector_indexer.delete_collection()
                    logger.info(f"Cleaned up Qdrant collection for {evicted_id}")
                except Exception as e:
                    logger.error(f"Error cleaning Qdrant for {evicted_id}: {e}")

            # Clean up MongoDB database (ONLY for test processors)
            if evicted_id.startswith('test_') and \
               hasattr(processor, 'pattern_processor') and \
               hasattr(processor.pattern_processor, 'superkb'):
                try:
                    processor.pattern_processor.superkb.drop_database()
                    logger.info(f"Cleaned up MongoDB database for {evicted_id}")
                except Exception as e:
                    logger.error(f"Error cleaning MongoDB for {evicted_id}: {e}")

            # Standard close (no-op but kept for compatibility)
            processor.pattern_processor.superkb.close()

        except Exception as e:
            logger.error(f"Error cleaning up processor {evicted_id}: {e}")

        # Remove lock
        if evicted_id in self.processor_locks:
            del self.processor_locks[evicted_id]

        logger.info(
            f"Evicted processor {evicted_id} for node {evicted_info['node_id']} "
            f"(created: {evicted_info['created_at']}, accesses: {evicted_info['access_count']})"
        )

    async def remove_processor(self, node_id: str) -> bool:
        """
        Remove a specific node's processor from cache.

        Args:
            node_id: Node identifier

        Returns:
            True if removed, False if not found
        """
        processor_id = self._get_processor_id(node_id)

        if processor_id not in self.processors:
            return False

        processor_info = self.processors.pop(processor_id)

        # Clean up the processor
        try:
            processor_info['processor'].pattern_processor.superkb.close()
        except Exception as e:
            logger.error(f"Error closing processor {processor_id}: {e}")

        # Remove lock
        if processor_id in self.processor_locks:
            del self.processor_locks[processor_id]

        logger.info(f"Removed processor {processor_id} for node {node_id}")
        return True

    async def cleanup_expired_processors(self) -> int:
        """
        Remove processors that haven't been accessed within TTL.

        Returns:
            Number of processors cleaned up
        """
        now = datetime.now(timezone.utc)
        expired_threshold = now - timedelta(seconds=self.eviction_ttl)

        expired_ids = [
            pid for pid, info in self.processors.items()
            if info['last_accessed'] < expired_threshold
        ]

        for processor_id in expired_ids:
            processor_info = self.processors.pop(processor_id)

            # Clean up the processor
            try:
                processor_info['processor'].pattern_processor.superkb.close()
            except Exception as e:
                logger.error(f"Error closing processor {processor_id}: {e}")

            # Remove lock
            if processor_id in self.processor_locks:
                del self.processor_locks[processor_id]

            logger.info(
                f"Expired processor {processor_id} for node {processor_info['node_id']} "
                f"(last accessed: {processor_info['last_accessed']})"
            )

        if expired_ids:
            logger.info(f"Cleaned up {len(expired_ids)} expired processors")

        return len(expired_ids)

    async def _cleanup_loop(self):
        """Background task to periodically cleanup expired processors."""
        while True:
            try:
                await asyncio.sleep(self._cleanup_interval)
                await self.cleanup_expired_processors()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")

    def get_stats(self) -> dict[str, Any]:
        """
        Get statistics about cached processors.

        Returns:
            Dictionary with processor cache statistics
        """
        now = datetime.now(timezone.utc)

        stats = {
            "total_processors": len(self.processors),
            "max_processors": self.max_processors,
            "eviction_ttl_seconds": self.eviction_ttl,
            "processors": []
        }

        for processor_id, info in self.processors.items():
            idle_seconds = (now - info['last_accessed']).total_seconds()
            stats["processors"].append({
                "processor_id": processor_id,
                "node_id": info['node_id'],
                "created_at": info['created_at'].isoformat(),
                "last_accessed": info['last_accessed'].isoformat(),
                "access_count": info['access_count'],
                "idle_seconds": idle_seconds
            })

        return stats

    async def shutdown(self):
        """Cleanup all processors on shutdown."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._cleanup_task

        # Close all processors
        for processor_id, processor_info in self.processors.items():
            try:
                processor_info['processor'].pattern_processor.superkb.close()
            except Exception as e:
                logger.error(f"Error closing processor {processor_id}: {e}")

        self.processors.clear()
        self.processor_locks.clear()

        logger.info("ProcessorManager shutdown complete")


# Global processor manager instance (singleton pattern)
_processor_manager: Optional[ProcessorManager] = None


def get_processor_manager(base_processor_id: str) -> ProcessorManager:
    """Get or create the global processor manager instance."""
    global _processor_manager
    if _processor_manager is None:
        _processor_manager = ProcessorManager(base_processor_id)
    return _processor_manager


async def cleanup_processor_manager():
    """Cleanup the global processor manager."""
    global _processor_manager
    if _processor_manager:
        await _processor_manager.shutdown()
        _processor_manager = None
