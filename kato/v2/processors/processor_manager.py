"""
KATO v2.0 Processor Management Implementation

This module provides per-user processor isolation for true multi-user support.
Each user gets their own KatoProcessor instance with isolated MongoDB and Qdrant databases.

Critical requirement: Each user maintains their own persistent knowledge base
that survives across sessions.
"""

import asyncio
import logging
import time
from collections import OrderedDict
from typing import Dict, Optional, Any
from datetime import datetime, timedelta

from kato.workers.kato_processor import KatoProcessor
from kato.config.settings import get_settings
from kato.v2.config.user_config import UserConfiguration

logger = logging.getLogger('kato.v2.processors.manager')


class ProcessorManager:
    """
    Manages KatoProcessor instances per user with complete database isolation.
    
    This is the core component that enables true multi-user support in KATO v2.
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
        self.processors: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self.processor_locks: Dict[str, asyncio.Lock] = {}
        self.settings = get_settings()
        
        # Background cleanup task
        self._cleanup_task = None
        self._cleanup_interval = 300  # 5 minutes
        
        logger.info(
            f"ProcessorManager initialized with base_id={base_processor_id}, "
            f"max={max_processors}, ttl={eviction_ttl_seconds}s"
        )
    
    def _get_processor_id(self, user_id: str) -> str:
        """
        Generate processor ID for a specific user.
        
        Args:
            user_id: User identifier
        
        Returns:
            Processor ID in format "{user_id}_{base_processor_id}"
        """
        # Clean user_id to be MongoDB-safe
        # MongoDB doesn't allow: / \ . " $ * < > : | ? in database names
        # Also replace hyphens with underscores
        safe_user_id = user_id
        for char in ['/', '\\', '.', '"', '$', '*', '<', '>', ':', '|', '?', '-', ' ']:
            safe_user_id = safe_user_id.replace(char, '_')
        
        # Clean base_processor_id too
        safe_base_id = self.base_processor_id.replace('-', '_')
        
        # MongoDB database name limit is 64 characters but we use 60 for absolute safety
        # Calculate the final name and ensure it fits
        full_name = f"{safe_user_id}_{safe_base_id}"
        
        if len(full_name) > 60:  # Use 60 for extra safety margin
            # Need to truncate user_id to fit
            import hashlib
            user_hash = hashlib.md5(safe_user_id.encode()).hexdigest()[:8]
            
            # Calculate exact space available for user_id
            # Format: {truncated_user}_{hash}_{base_id}
            # So we need: len(base_id) + 1 (underscore) + 8 (hash) + 1 (underscore)
            max_user_length = 60 - len(safe_base_id) - 1 - 8 - 1
            
            truncated_user = safe_user_id[:max_user_length]
            safe_user_id = f"{truncated_user}_{user_hash}"
            
            # Log for debugging
            final_name = f"{safe_user_id}_{safe_base_id}"
            logger.info(f"Truncated user_id for MongoDB: orig={user_id}, final={final_name}, len={len(final_name)}")
        
        return f"{safe_user_id}_{safe_base_id}"
    
    async def get_processor(self, user_id: str, user_config: Optional[UserConfiguration] = None) -> KatoProcessor:
        """
        Get or create a processor for a specific user.
        
        Args:
            user_id: User identifier
            user_config: Optional user configuration to apply
        
        Returns:
            KatoProcessor instance for this user
        """
        processor_id = self._get_processor_id(user_id)
        
        # Check if processor exists and is not expired
        if processor_id in self.processors:
            processor_info = self.processors[processor_id]
            processor_info['last_accessed'] = datetime.utcnow()
            
            # Move to end for LRU
            self.processors.move_to_end(processor_id)
            
            # Apply dynamic configuration updates to cached processor
            processor = processor_info['processor']
            if user_config:
                self._apply_config_to_processor(processor, user_config)
            
            logger.debug(f"Returning cached processor for user {user_id}")
            return processor
        
        # Need to create new processor
        if processor_id not in self.processor_locks:
            self.processor_locks[processor_id] = asyncio.Lock()
        
        async with self.processor_locks[processor_id]:
            # Double-check after acquiring lock
            if processor_id in self.processors:
                processor_info = self.processors[processor_id]
                processor_info['last_accessed'] = datetime.utcnow()
                self.processors.move_to_end(processor_id)
                return processor_info['processor']
            
            # Create new processor
            logger.info(f"Creating new processor for user {user_id} with id {processor_id}")
            
            # Get default settings
            defaults = {
                'indexer_type': self.settings.processing.indexer_type,
                'max_pattern_length': self.settings.learning.max_pattern_length,
                'persistence': self.settings.learning.persistence,
                'recall_threshold': self.settings.learning.recall_threshold,
                'smoothness': self.settings.learning.smoothness,
                'auto_act_method': self.settings.processing.auto_act_method,
                'auto_act_threshold': self.settings.processing.auto_act_threshold,
                'always_update_frequencies': self.settings.processing.always_update_frequencies,
                'max_predictions': self.settings.processing.max_predictions,
                'quiescence': self.settings.learning.quiescence,
                'search_depth': self.settings.processing.search_depth,
                'sort': self.settings.processing.sort_symbols,
                'process_predictions': self.settings.processing.process_predictions
            }
            
            # Merge with user configuration if provided
            if user_config:
                genome_values = user_config.merge_with_defaults(defaults)
            else:
                genome_values = defaults
            
            # Build genome manifest with user-specific processor_id
            genome_manifest = {
                'id': processor_id,  # This becomes the MongoDB database name
                'name': f"User-{user_id}",
                **genome_values
            }
            
            # Create processor instance
            processor = KatoProcessor(genome_manifest, settings=self.settings)
            
            # Store in cache
            self.processors[processor_id] = {
                'processor': processor,
                'user_id': user_id,
                'created_at': datetime.utcnow(),
                'last_accessed': datetime.utcnow(),
                'access_count': 1
            }
            
            # Enforce max processors limit (LRU eviction)
            if len(self.processors) > self.max_processors:
                self._evict_oldest()
            
            # Start cleanup task if not running
            if not self._cleanup_task:
                self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            
            return processor
    
    def _apply_config_to_processor(self, processor: 'KatoProcessor', user_config: UserConfiguration):
        """
        Apply dynamic configuration updates to an existing processor.
        
        Args:
            processor: The KatoProcessor instance to update
            user_config: User configuration with updates
        """
        # Update critical parameters that can be changed dynamically
        if user_config.recall_threshold is not None:
            # Update the pattern processor's recall threshold
            if hasattr(processor, 'pattern_processor'):
                processor.pattern_processor.recall_threshold = user_config.recall_threshold
                # Also update the pattern searcher's threshold
                if hasattr(processor.pattern_processor, 'patterns_searcher'):
                    processor.pattern_processor.patterns_searcher.recall_threshold = user_config.recall_threshold
                    logger.debug(f"Updated recall_threshold to {user_config.recall_threshold}")
        
        if user_config.max_pattern_length is not None:
            if hasattr(processor, 'max_pattern_length'):
                processor.max_pattern_length = user_config.max_pattern_length
            if hasattr(processor, 'pattern_processor'):
                processor.pattern_processor.max_pattern_length = user_config.max_pattern_length
                logger.debug(f"Updated max_pattern_length to {user_config.max_pattern_length}")
        
        if user_config.persistence is not None:
            if hasattr(processor, 'pattern_processor'):
                processor.pattern_processor.persistence = user_config.persistence
                logger.debug(f"Updated persistence to {user_config.persistence}")
        
        # Update other configurable parameters
        if user_config.max_predictions is not None:
            if hasattr(processor, 'pattern_processor'):
                processor.pattern_processor.max_predictions = user_config.max_predictions
                if hasattr(processor.pattern_processor, 'patterns_searcher'):
                    processor.pattern_processor.patterns_searcher.max_predictions = user_config.max_predictions
                logger.debug(f"Updated max_predictions to {user_config.max_predictions}")
    
    def _evict_oldest(self):
        """Evict the least recently used processor."""
        if not self.processors:
            return
        
        # OrderedDict pops first item (oldest)
        evicted_id, evicted_info = self.processors.popitem(last=False)
        
        # Clean up the processor
        try:
            evicted_info['processor'].pattern_processor.superkb.close()
        except Exception as e:
            logger.error(f"Error closing processor {evicted_id}: {e}")
        
        # Remove lock
        if evicted_id in self.processor_locks:
            del self.processor_locks[evicted_id]
        
        logger.info(
            f"Evicted processor {evicted_id} for user {evicted_info['user_id']} "
            f"(created: {evicted_info['created_at']}, accesses: {evicted_info['access_count']})"
        )
    
    async def update_processor_config(self, user_id: str, user_config: UserConfiguration) -> bool:
        """
        Update a processor's configuration dynamically.
        
        Args:
            user_id: User identifier
            user_config: New user configuration
        
        Returns:
            True if successful, False otherwise
        """
        processor_id = self._get_processor_id(user_id)
        
        if processor_id not in self.processors:
            # Processor doesn't exist, will be created with new config on next access
            return True
        
        processor_info = self.processors[processor_id]
        processor = processor_info['processor']
        
        try:
            # Get default settings
            defaults = {
                'indexer_type': self.settings.processing.indexer_type,
                'max_pattern_length': self.settings.learning.max_pattern_length,
                'persistence': self.settings.learning.persistence,
                'recall_threshold': self.settings.learning.recall_threshold,
                'smoothness': self.settings.learning.smoothness,
                'auto_act_method': self.settings.processing.auto_act_method,
                'auto_act_threshold': self.settings.processing.auto_act_threshold,
                'always_update_frequencies': self.settings.processing.always_update_frequencies,
                'max_predictions': self.settings.processing.max_predictions,
                'quiescence': self.settings.learning.quiescence,
                'search_depth': self.settings.processing.search_depth,
                'sort': self.settings.processing.sort_symbols,
                'process_predictions': self.settings.processing.process_predictions
            }
            
            # Merge with user configuration
            new_config = user_config.merge_with_defaults(defaults)
            
            # Update processor attributes directly
            # These are the safe runtime-updateable parameters
            if 'recall_threshold' in new_config:
                processor.recall_threshold = new_config['recall_threshold']
                if hasattr(processor, 'pattern_processor'):
                    processor.pattern_processor.recall_threshold = new_config['recall_threshold']
            
            if 'persistence' in new_config:
                processor.persistence = new_config['persistence']
            
            if 'max_pattern_length' in new_config:
                processor.max_pattern_length = new_config['max_pattern_length']
            
            if 'smoothness' in new_config:
                processor.smoothness = new_config['smoothness']
            
            if 'quiescence' in new_config:
                processor.quiescence = new_config['quiescence']
            
            if 'auto_act_threshold' in new_config:
                processor.auto_act_threshold = new_config['auto_act_threshold']
            
            if 'always_update_frequencies' in new_config:
                processor.always_update_frequencies = new_config['always_update_frequencies']
            
            if 'max_predictions' in new_config:
                processor.max_predictions = new_config['max_predictions']
            
            if 'search_depth' in new_config:
                processor.search_depth = new_config['search_depth']
            
            if 'sort' in new_config:
                processor.sort = new_config['sort']
            
            if 'process_predictions' in new_config:
                processor.process_predictions = new_config['process_predictions']
            
            logger.info(f"Updated processor {processor_id} configuration for user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update processor config for {user_id}: {e}")
            return False
    
    async def remove_processor(self, user_id: str) -> bool:
        """
        Remove a specific user's processor from cache.
        
        Args:
            user_id: User identifier
        
        Returns:
            True if removed, False if not found
        """
        processor_id = self._get_processor_id(user_id)
        
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
        
        logger.info(f"Removed processor {processor_id} for user {user_id}")
        return True
    
    async def cleanup_expired_processors(self) -> int:
        """
        Remove processors that haven't been accessed within TTL.
        
        Returns:
            Number of processors cleaned up
        """
        now = datetime.utcnow()
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
                f"Expired processor {processor_id} for user {processor_info['user_id']} "
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
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get statistics about cached processors.
        
        Returns:
            Dictionary with processor cache statistics
        """
        now = datetime.utcnow()
        
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
                "user_id": info['user_id'],
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
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
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