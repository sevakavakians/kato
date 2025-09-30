"""
Redis Pattern Caching Layer for KATO Performance Optimization
============================================================

This module implements a Redis-based caching layer for patterns and symbol probabilities
to achieve 80% reduction in pattern loading time as specified in Phase 1 optimizations.

Key Features:
- Cache top patterns per session with automatic TTL
- Cache global symbol probabilities with incremental updates
- Atomic cache operations for thread safety
- Configurable TTL and cache sizes
- Fallback to MongoDB when cache misses
- Cache invalidation strategies for data consistency

Expected Performance Gains:
- 80% reduction in pattern loading time
- 3-5x throughput increase for pattern queries
- Reduced MongoDB load for read operations
"""

import json
import logging
import time
from typing import Dict, List, Any, Optional, Union
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import redis.asyncio as redis
from redis.asyncio import Redis
from pymongo.collection import Collection

logger = logging.getLogger('kato.storage.pattern_cache')


@dataclass
class CacheConfig:
    """Configuration for pattern cache behavior."""
    
    # TTL settings (in seconds)
    pattern_ttl: int = 3600          # 1 hour for patterns
    symbol_prob_ttl: int = 1800      # 30 minutes for symbol probabilities  
    metadata_ttl: int = 300          # 5 minutes for metadata
    
    # Cache size limits
    max_patterns_per_session: int = 1000
    max_symbol_cache_size: int = 10000
    
    # Cache key prefixes
    pattern_prefix: str = "patterns"
    symbol_prefix: str = "symbols"
    metadata_prefix: str = "metadata"
    
    # Performance settings
    pipeline_batch_size: int = 100   # Batch size for Redis pipeline operations
    cache_miss_threshold: float = 0.1  # Cache patterns accessed more than this ratio


class PatternCache:
    """
    Redis-based caching layer for KATO patterns and symbols.
    
    Provides high-performance caching with automatic fallback to MongoDB
    when cache misses occur. Implements intelligent cache warming and
    invalidation strategies.
    """
    
    def __init__(self, redis_client: Redis, config: Optional[CacheConfig] = None):
        """
        Initialize pattern cache.
        
        Args:
            redis_client: Async Redis client instance
            config: Cache configuration (uses defaults if not provided)
        """
        self.redis = redis_client
        self.config = config or CacheConfig()
        
        # Statistics tracking
        self.stats = {
            'cache_hits': 0,
            'cache_misses': 0,
            'patterns_cached': 0,
            'symbols_cached': 0,
            'last_reset': time.time()
        }
        
        logger.info(f"PatternCache initialized with TTL {self.config.pattern_ttl}s")
    
    async def get_top_patterns(
        self, 
        session_id: str, 
        limit: int = 100,
        mongo_collection: Optional[Collection] = None
    ) -> List[Dict[str, Any]]:
        """
        Get top patterns for a session with caching.
        
        Args:
            session_id: Session identifier for cache isolation
            limit: Maximum number of patterns to return
            mongo_collection: MongoDB collection to fallback to on cache miss
            
        Returns:
            List of pattern documents sorted by frequency
        """
        cache_key = f"{self.config.pattern_prefix}:top:{session_id}:{limit}"
        
        try:
            # Try cache first
            cached_data = await self.redis.get(cache_key)
            if cached_data:
                patterns = json.loads(cached_data)
                self.stats['cache_hits'] += 1
                logger.debug(f"Cache hit for top patterns: {session_id} ({len(patterns)} patterns)")
                return patterns
            
            # Cache miss - load from MongoDB if available
            if mongo_collection is None:
                logger.warning(f"Cache miss for {cache_key} but no MongoDB collection provided")
                return []
            
            patterns = await self._load_top_patterns_from_mongo(mongo_collection, limit)
            
            # Cache the results
            await self.redis.setex(
                cache_key, 
                self.config.pattern_ttl, 
                json.dumps(patterns, default=str)
            )
            
            self.stats['cache_misses'] += 1
            self.stats['patterns_cached'] += len(patterns)
            logger.debug(f"Loaded and cached {len(patterns)} top patterns for {session_id}")
            
            return patterns
            
        except Exception as e:
            logger.error(f"Error in get_top_patterns for {session_id}: {e}")
            # Return empty list on error to prevent cascade failures
            return []
    
    async def get_pattern_by_name(
        self, 
        pattern_name: str,
        mongo_collection: Optional[Collection] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get specific pattern by name with caching.
        
        Args:
            pattern_name: Unique pattern identifier (e.g., 'PTRN|<hash>')
            mongo_collection: MongoDB collection to fallback to
            
        Returns:
            Pattern document or None if not found
        """
        cache_key = f"{self.config.pattern_prefix}:name:{pattern_name}"
        
        try:
            # Try cache first
            cached_data = await self.redis.get(cache_key)
            if cached_data:
                pattern = json.loads(cached_data)
                self.stats['cache_hits'] += 1
                logger.debug(f"Cache hit for pattern: {pattern_name}")
                return pattern
            
            # Cache miss - load from MongoDB
            if mongo_collection is None:
                return None
            
            pattern = mongo_collection.find_one({"name": pattern_name})
            if pattern:
                # Convert ObjectId to string for JSON serialization
                if '_id' in pattern:
                    pattern['_id'] = str(pattern['_id'])
                
                # Cache the pattern
                await self.redis.setex(
                    cache_key,
                    self.config.pattern_ttl,
                    json.dumps(pattern, default=str)
                )
                
                self.stats['cache_misses'] += 1
                self.stats['patterns_cached'] += 1
                logger.debug(f"Loaded and cached pattern: {pattern_name}")
            
            return pattern
            
        except Exception as e:
            logger.error(f"Error in get_pattern_by_name for {pattern_name}: {e}")
            return None
    
    async def get_symbol_probabilities(
        self,
        session_id: Optional[str] = None,
        mongo_metadata_collection: Optional[Collection] = None,
        mongo_symbols_collection: Optional[Collection] = None
    ) -> Dict[str, float]:
        """
        Get cached symbol probabilities with fallback calculation.
        
        Args:
            session_id: Optional session for cache isolation
            mongo_metadata_collection: MongoDB metadata collection for totals
            mongo_symbols_collection: MongoDB symbols collection for frequencies
            
        Returns:
            Dictionary mapping symbol names to probability values
        """
        cache_key = f"{self.config.symbol_prefix}:probabilities"
        if session_id:
            cache_key += f":{session_id}"
        
        try:
            # Try cache first
            cached_data = await self.redis.get(cache_key)
            if cached_data:
                probabilities = json.loads(cached_data)
                self.stats['cache_hits'] += 1
                logger.debug(f"Cache hit for symbol probabilities ({len(probabilities)} symbols)")
                return probabilities
            
            # Cache miss - calculate from MongoDB
            probabilities = await self._calculate_symbol_probabilities(
                mongo_metadata_collection, mongo_symbols_collection
            )
            
            # Cache the results
            await self.redis.setex(
                cache_key,
                self.config.symbol_prob_ttl,
                json.dumps(probabilities)
            )
            
            self.stats['cache_misses'] += 1
            self.stats['symbols_cached'] += len(probabilities)
            logger.debug(f"Calculated and cached {len(probabilities)} symbol probabilities")
            
            return probabilities
            
        except Exception as e:
            logger.error(f"Error in get_symbol_probabilities: {e}")
            return {}
    
    async def cache_pattern_batch(
        self, 
        patterns: List[Dict[str, Any]], 
        session_id: Optional[str] = None
    ) -> int:
        """
        Cache multiple patterns in a batch operation.
        
        Args:
            patterns: List of pattern documents to cache
            session_id: Optional session for cache organization
            
        Returns:
            Number of patterns successfully cached
        """
        if not patterns:
            return 0
        
        try:
            pipe = self.redis.pipeline()
            cached_count = 0
            
            for pattern in patterns:
                if 'name' not in pattern:
                    continue
                
                # Convert ObjectId for JSON serialization
                pattern_copy = pattern.copy()
                if '_id' in pattern_copy:
                    pattern_copy['_id'] = str(pattern_copy['_id'])
                
                cache_key = f"{self.config.pattern_prefix}:name:{pattern['name']}"
                if session_id:
                    cache_key += f":{session_id}"
                
                pipe.setex(
                    cache_key,
                    self.config.pattern_ttl,
                    json.dumps(pattern_copy, default=str)
                )
                cached_count += 1
                
                # Execute pipeline in batches
                if cached_count % self.config.pipeline_batch_size == 0:
                    await pipe.execute()
                    pipe = self.redis.pipeline()
            
            # Execute remaining commands
            if cached_count % self.config.pipeline_batch_size != 0:
                await pipe.execute()
            
            self.stats['patterns_cached'] += cached_count
            logger.info(f"Batch cached {cached_count} patterns")
            
            return cached_count
            
        except Exception as e:
            logger.error(f"Error in cache_pattern_batch: {e}")
            return 0
    
    async def invalidate_pattern_cache(self, session_id: Optional[str] = None) -> int:
        """
        Invalidate pattern cache entries.
        
        Args:
            session_id: If provided, only invalidate cache for this session
            
        Returns:
            Number of cache entries invalidated
        """
        try:
            if session_id:
                # Invalidate session-specific patterns
                pattern = f"{self.config.pattern_prefix}:*:{session_id}*"
            else:
                # Invalidate all pattern cache
                pattern = f"{self.config.pattern_prefix}:*"
            
            keys = []
            async for key in self.redis.scan_iter(match=pattern, count=100):
                keys.append(key)
            
            if keys:
                deleted = await self.redis.delete(*keys)
                logger.info(f"Invalidated {deleted} pattern cache entries")
                return deleted
            
            return 0
            
        except Exception as e:
            logger.error(f"Error in invalidate_pattern_cache: {e}")
            return 0
    
    async def invalidate_symbol_cache(self) -> int:
        """
        Invalidate symbol probability cache.
        
        Returns:
            Number of cache entries invalidated
        """
        try:
            pattern = f"{self.config.symbol_prefix}:*"
            keys = []
            async for key in self.redis.scan_iter(match=pattern, count=100):
                keys.append(key)
            
            if keys:
                deleted = await self.redis.delete(*keys)
                logger.info(f"Invalidated {deleted} symbol cache entries")
                return deleted
            
            return 0
            
        except Exception as e:
            logger.error(f"Error in invalidate_symbol_cache: {e}")
            return 0
    
    async def warm_cache(
        self,
        session_id: str,
        patterns_collection: Collection,
        symbols_collection: Collection,
        metadata_collection: Collection,
        pattern_limit: int = 500
    ) -> Dict[str, int]:
        """
        Pre-populate cache with frequently accessed data.
        
        Args:
            session_id: Session to warm cache for
            patterns_collection: MongoDB patterns collection
            symbols_collection: MongoDB symbols collection
            metadata_collection: MongoDB metadata collection
            pattern_limit: Maximum patterns to pre-cache
            
        Returns:
            Dictionary with counts of cached items
        """
        try:
            logger.info(f"Warming cache for session {session_id}")
            
            # Load top patterns
            patterns = await self._load_top_patterns_from_mongo(patterns_collection, pattern_limit)
            patterns_cached = await self.cache_pattern_batch(patterns, session_id)
            
            # Cache symbol probabilities
            await self.get_symbol_probabilities(session_id, metadata_collection, symbols_collection)
            
            # Cache top patterns list
            cache_key = f"{self.config.pattern_prefix}:top:{session_id}:{pattern_limit}"
            await self.redis.setex(
                cache_key,
                self.config.pattern_ttl,
                json.dumps(patterns, default=str)
            )
            
            result = {
                'patterns_cached': patterns_cached,
                'symbol_probabilities_cached': 1,
                'top_patterns_cached': 1
            }
            
            logger.info(f"Cache warming completed: {result}")
            return result
            
        except Exception as e:
            logger.error(f"Error in warm_cache: {e}")
            return {'patterns_cached': 0, 'symbol_probabilities_cached': 0, 'top_patterns_cached': 0}
    
    async def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get cache performance statistics.
        
        Returns:
            Dictionary with cache hit rates, sizes, and performance metrics
        """
        try:
            total_requests = self.stats['cache_hits'] + self.stats['cache_misses']
            hit_rate = (self.stats['cache_hits'] / total_requests * 100) if total_requests > 0 else 0
            
            # Get Redis memory info
            info = await self.redis.info('memory')
            
            # Count cache keys
            pattern_keys = 0
            symbol_keys = 0
            
            async for key in self.redis.scan_iter(match=f"{self.config.pattern_prefix}:*", count=100):
                pattern_keys += 1
            
            async for key in self.redis.scan_iter(match=f"{self.config.symbol_prefix}:*", count=100):
                symbol_keys += 1
            
            uptime = time.time() - self.stats['last_reset']
            
            return {
                'hit_rate_percent': round(hit_rate, 2),
                'cache_hits': self.stats['cache_hits'],
                'cache_misses': self.stats['cache_misses'],
                'patterns_in_cache': pattern_keys,
                'symbols_in_cache': symbol_keys,
                'patterns_cached_total': self.stats['patterns_cached'],
                'symbols_cached_total': self.stats['symbols_cached'],
                'redis_memory_used_mb': round(info.get('used_memory', 0) / (1024 * 1024), 2),
                'uptime_seconds': round(uptime, 2),
                'requests_per_second': round(total_requests / uptime, 2) if uptime > 0 else 0
            }
            
        except Exception as e:
            logger.error(f"Error getting cache stats: {e}")
            return {'error': str(e)}
    
    async def reset_stats(self):
        """Reset cache statistics."""
        self.stats = {
            'cache_hits': 0,
            'cache_misses': 0,
            'patterns_cached': 0,
            'symbols_cached': 0,
            'last_reset': time.time()
        }
        logger.info("Cache statistics reset")
    
    async def _load_top_patterns_from_mongo(
        self, 
        collection: Collection, 
        limit: int
    ) -> List[Dict[str, Any]]:
        """Load top patterns from MongoDB sorted by frequency."""
        try:
            cursor = collection.find(
                {},
                {"name": 1, "pattern_data": 1, "frequency": 1, "length": 1}
            ).sort([("frequency", -1)]).limit(limit)
            
            patterns = []
            for pattern in cursor:
                # Convert ObjectId to string
                if '_id' in pattern:
                    pattern['_id'] = str(pattern['_id'])
                patterns.append(pattern)
            
            return patterns
            
        except Exception as e:
            logger.error(f"Error loading patterns from MongoDB: {e}")
            return []
    
    async def _calculate_symbol_probabilities(
        self,
        metadata_collection: Optional[Collection],
        symbols_collection: Optional[Collection]
    ) -> Dict[str, float]:
        """Calculate symbol probabilities from MongoDB collections."""
        try:
            if not metadata_collection or not symbols_collection:
                return {}
            
            # Get total symbol frequencies from metadata
            metadata = metadata_collection.find_one({"class": "totals"})
            if not metadata:
                return {}
            
            total_frequencies = metadata.get("total_symbol_frequencies", 0)
            if total_frequencies <= 0:
                return {}
            
            # Get individual symbol frequencies
            probabilities = {}
            cursor = symbols_collection.find({}, {"name": 1, "frequency": 1})
            
            for symbol_doc in cursor:
                symbol_name = symbol_doc.get("name")
                frequency = symbol_doc.get("frequency", 0)
                
                if symbol_name and frequency > 0:
                    probabilities[symbol_name] = frequency / total_frequencies
            
            logger.debug(f"Calculated probabilities for {len(probabilities)} symbols")
            return probabilities
            
        except Exception as e:
            logger.error(f"Error calculating symbol probabilities: {e}")
            return {}


class CacheManager:
    """
    Manager for multiple cache instances and cache lifecycle.
    
    Provides centralized cache management for KATO with automatic
    initialization, cleanup, and monitoring.
    """
    
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        """
        Initialize cache manager.
        
        Args:
            redis_url: Redis connection URL (deprecated - now uses connection manager)
        """
        self.redis_url = redis_url  # Keep for backward compatibility
        self.redis_client: Optional[Redis] = None
        self.pattern_cache: Optional[PatternCache] = None
        self._initialized = False
    
    async def initialize(self, config: Optional[CacheConfig] = None) -> bool:
        """
        Initialize Redis connection and cache instances.
        
        Args:
            config: Cache configuration
            
        Returns:
            True if initialization successful
        """
        try:
            # Use optimized connection manager for Redis
            from kato.storage.connection_manager import get_redis_client
            sync_redis_client = get_redis_client()
            
            if sync_redis_client is None:
                logger.warning("Redis not available - pattern cache disabled")
                return False
            
            # Convert synchronous Redis client to async for aioredis compatibility
            # For now, we'll keep the direct connection but use optimized settings
            self.redis_client = redis.from_url(
                self.redis_url,
                decode_responses=True,
                max_connections=20,  # Optimized connection pool
                retry_on_timeout=True,
                health_check_interval=30
            )
            
            # Test connection
            await self.redis_client.ping()
            
            # Initialize caches
            self.pattern_cache = PatternCache(self.redis_client, config)
            
            self._initialized = True
            logger.info(f"CacheManager initialized with Redis at {self.redis_url}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize CacheManager: {e}")
            return False
    
    async def cleanup(self):
        """Cleanup cache resources."""
        if self.redis_client:
            await self.redis_client.close()
            logger.info("CacheManager cleanup completed")
    
    def is_initialized(self) -> bool:
        """Check if cache manager is initialized."""
        return self._initialized and self.redis_client is not None
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Perform health check on cache system.
        
        Returns:
            Health status and metrics
        """
        if not self.is_initialized():
            return {"status": "unhealthy", "error": "Not initialized"}
        
        try:
            # Test Redis connection
            await self.redis_client.ping()
            
            # Get cache stats if available
            stats = {}
            if self.pattern_cache:
                stats = await self.pattern_cache.get_cache_stats()
            
            return {
                "status": "healthy",
                "redis_connected": True,
                "cache_stats": stats
            }
            
        except Exception as e:
            return {
                "status": "unhealthy", 
                "redis_connected": False,
                "error": str(e)
            }


# Global cache manager instance
_cache_manager: Optional[CacheManager] = None


async def get_cache_manager() -> Optional[CacheManager]:
    """Get or create global cache manager instance."""
    global _cache_manager
    
    if _cache_manager is None:
        import os
        redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379')
        _cache_manager = CacheManager(redis_url=redis_url)
        if not await _cache_manager.initialize():
            _cache_manager = None
            logger.error("Failed to initialize global cache manager")
    
    return _cache_manager


async def cleanup_cache_manager():
    """Cleanup global cache manager."""
    global _cache_manager
    
    if _cache_manager:
        await _cache_manager.cleanup()
        _cache_manager = None