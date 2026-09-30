"""
Incremental Metrics Calculations Cache for KATO

This module provides Redis-backed caching for expensive metric calculations
like normalized_entropy, global_normalized_entropy, and conditional probabilities.

Performance benefits:
- 70-90% reduction in metric calculation time for repeated queries
- Incremental updates when new patterns are learned
- TTL-based cache invalidation to handle data changes
"""

import hashlib
import json
import logging
import time
from typing import Any, Optional
from uuid import uuid4

try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

logger = logging.getLogger(__name__)

# Global cache manager instance
_metrics_cache_manager = None


class MetricsCacheManager:
    """Manager for caching expensive KATO metric calculations."""

    def __init__(self, redis_url: str = "redis://localhost:6379", ttl: int = 3600):
        """
        Initialize metrics cache manager.

        Args:
            redis_url: Redis connection URL
            ttl: Time-to-live for cached metrics in seconds
        """
        self.redis_url = redis_url
        self.ttl = ttl
        self.redis = None
        self.cache_prefix = "kato:metrics"
        # Outside the legacy cache prefix so an older invalidator cannot delete
        # the generation token while versioned values are still alive.
        self.generation_key = "kato:metrics_generation:v1"

        # Cache hit/miss statistics
        self.stats = {
            "hits": 0,
            "misses": 0,
            "updates": 0,
            "evictions": 0,
            "invalidations": 0
        }

        # Metric calculation counters
        self.calculation_times = {
            "normalized_entropy": [],
            "global_normalized_entropy": [],
            "conditional_probability": [],
            "itfdf_similarity": [],
            "potential": []
        }

    async def initialize(self) -> bool:
        """
        Initialize Redis connection.

        Returns:
            True if initialization successful, False otherwise
        """
        if not REDIS_AVAILABLE:
            logger.warning("redis.asyncio not available, metrics cache disabled")
            return False

        try:
            # Use optimized connection manager for Redis
            from kato.storage.connection_manager import get_redis_client
            sync_redis_client = get_redis_client()

            if sync_redis_client is None:
                logger.warning("Redis not available - metrics cache disabled")
                return False

            # Create async Redis client with optimized settings
            self.redis = await redis.from_url(
                self.redis_url,
                max_connections=20,  # Optimized connection pool
                retry_on_timeout=True,
                health_check_interval=30
            )
            await self.redis.ping()
            logger.info(f"MetricsCacheManager connected to Redis with optimized connection: {self.redis_url}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Redis for metrics cache: {e}")
            self.redis = None
            return False

    def _generate_cache_key(self, metric_type: str, **kwargs) -> str:
        """
        Generate consistent cache key for metric calculations.

        Args:
            metric_type: Type of metric (e.g., 'normalized_entropy', 'global_normalized_entropy')
            **kwargs: Parameters used in metric calculation

        Returns:
            Redis cache key
        """
        # Sort kwargs for consistent key generation
        sorted_params = sorted(kwargs.items())
        params_str = json.dumps(sorted_params, sort_keys=True)

        # Generate hash for consistent key length
        params_hash = hashlib.md5(params_str.encode(), usedforsecurity=False).hexdigest()

        return f"{self.cache_prefix}:{metric_type}:{params_hash}"

    async def get_cache_generation(self) -> Optional[str]:
        """Get a shared cache version without enumerating Redis keys.

        A random token prevents old TTL entries from becoming reachable again
        if the generation key is lost. SET NX handles concurrent initialization.
        Redis failures disable caching for that calculation.
        """
        if not self.redis:
            return None
        try:
            generation = await self.redis.get(self.generation_key)
            if generation is None:
                await self.redis.set(self.generation_key, uuid4().hex, nx=True)
                generation = await self.redis.get(self.generation_key)
            if not generation:
                return None
            return generation.decode("ascii") if isinstance(generation, bytes) else str(generation)
        except Exception as e:
            logger.warning(f"Failed to read metrics cache generation: {e}")
            return None

    def _versioned_cache_key(self, generation: str, metric_type: str, **kwargs) -> str:
        return f"{self._generate_cache_key(metric_type, **kwargs)}:v2:{generation}"

    async def get_cached_metric(
        self, metric_type: str, *, cache_generation: Optional[str] = None, **kwargs
    ) -> Optional[float]:
        """
        Retrieve cached metric value.

        Args:
            metric_type: Type of metric to retrieve
            **kwargs: Parameters that identify the specific calculation

        Returns:
            Cached metric value or None if not found
        """
        if not self.redis:
            return None

        try:
            generation = cache_generation or await self.get_cache_generation()
            if generation is None:
                return None
            cache_key = self._versioned_cache_key(generation, metric_type, **kwargs)
            cached_value = await self.redis.get(cache_key)

            if cached_value is not None:
                self.stats["hits"] += 1
                return float(cached_value)
            else:
                self.stats["misses"] += 1
                return None

        except Exception as e:
            logger.warning(f"Failed to retrieve cached metric {metric_type}: {e}")
            self.stats["misses"] += 1
            return None

    async def cache_metric(
        self, metric_type: str, value: float, *,
        cache_generation: Optional[str] = None, **kwargs
    ) -> bool:
        """
        Cache calculated metric value.

        Args:
            metric_type: Type of metric being cached
            value: Calculated metric value
            **kwargs: Parameters that identify the specific calculation

        Returns:
            True if caching successful, False otherwise
        """
        if not self.redis:
            return False

        try:
            generation = cache_generation or await self.get_cache_generation()
            if generation is None:
                return False
            cache_key = self._versioned_cache_key(generation, metric_type, **kwargs)
            await self.redis.setex(cache_key, self.ttl, str(value))
            self.stats["updates"] += 1
            return True

        except Exception as e:
            logger.warning(f"Failed to cache metric {metric_type}: {e}")
            return False

    async def invalidate_pattern_metrics(self, pattern_name: str) -> int:
        """
        Logically invalidate the metric cache after a pattern changes.

        Preserve the existing global invalidation scope, but rotate one shared
        token instead of scanning the database after every learned pattern.
        Old cache values are left to expire through their existing TTL.

        Args:
            pattern_name: Name of the pattern that was updated

        Returns:
            1 if the cache generation was rotated, otherwise 0. This is not a
            count of deleted keys; no keys are enumerated or deleted.
        """
        return await self.invalidate_all_metrics()

    async def invalidate_all_metrics(self) -> int:
        """
        Rotate the shared cache generation in constant work, with no key scan.

        Returns:
            1 if the generation was rotated, otherwise 0 (not a key count).
        """
        if not self.redis:
            return 0

        try:
            if not await self.redis.set(self.generation_key, uuid4().hex):
                return 0
            self.stats["invalidations"] += 1
            return 1

        except Exception as e:
            logger.warning(f"Failed to invalidate all metrics cache: {e}")
            return 0

    def record_calculation_time(self, metric_type: str, duration: float):
        """
        Record calculation time for performance monitoring.

        Args:
            metric_type: Type of metric calculated
            duration: Time taken for calculation in seconds
        """
        if metric_type in self.calculation_times:
            self.calculation_times[metric_type].append(duration)

            # Keep only last 100 measurements for memory efficiency
            if len(self.calculation_times[metric_type]) > 100:
                self.calculation_times[metric_type] = self.calculation_times[metric_type][-100:]

    async def get_cache_stats(self) -> dict[str, Any]:
        """
        Get cache performance statistics.

        Returns:
            Dictionary with cache statistics
        """
        stats = self.stats.copy()

        # Calculate hit rate
        total_requests = stats["hits"] + stats["misses"]
        stats["hit_rate"] = stats["hits"] / total_requests if total_requests > 0 else 0.0

        # Add calculation time statistics
        for metric_type, times in self.calculation_times.items():
            if times:
                stats[f"{metric_type}_avg_time"] = sum(times) / len(times)
                stats[f"{metric_type}_calculations"] = len(times)
            else:
                stats[f"{metric_type}_avg_time"] = 0.0
                stats[f"{metric_type}_calculations"] = 0

        # Add Redis info if available
        if self.redis:
            try:
                info = await self.redis.info()
                stats["redis_used_memory"] = info.get("used_memory_human", "unknown")
                stats["redis_connected_clients"] = info.get("connected_clients", 0)
            except Exception as e:
                logger.debug(f"Could not get Redis info: {e}")

        return stats

    async def close(self) -> None:
        """Close the async Redis client.

        Safe to call when the manager was never initialized, and safe to call
        twice. aclose(), not close(): redis-py deprecated the async close() in
        5.0.1.
        """
        if self.redis:
            try:
                await self.redis.aclose()
            finally:
                self.redis = None


class CachedMetricsCalculator:
    """
    Wrapper for metric calculations with automatic caching.

    This class provides the same interface as the original metrics functions
    but with transparent caching for performance optimization.
    """

    def __init__(self, cache_manager: MetricsCacheManager):
        self.cache_manager = cache_manager

    async def normalized_entropy_cached(self, state: list[str],
                                total_symbols: int) -> float:
        """
        Calculate normalized entropy with caching.

        Args:
            state: Current state symbols
            total_symbols: Total number of symbols in dataset

        Returns:
            Normalized entropy value
        """
        # Generate cache key parameters
        cache_params = {
            "state_hash": hashlib.md5(str(sorted(state)).encode(), usedforsecurity=False).hexdigest(),
            "total_symbols": total_symbols
        }

        # Pin the generation across lookup, calculation, and publication. An
        # invalidation during calculation must not populate the new generation.
        generation = await self.cache_manager.get_cache_generation()
        cached_value = await self.cache_manager.get_cached_metric(
            "normalized_entropy", cache_generation=generation, **cache_params
        ) if generation is not None else None
        if cached_value is not None:
            return cached_value

        # Calculate if not cached
        start_time = time.time()

        # Import here to avoid circular dependencies
        from kato.informatics.metrics import normalized_entropy

        try:
            result = normalized_entropy(state, total_symbols)
            calculation_time = time.time() - start_time

            # Cache the result
            if generation is not None:
                await self.cache_manager.cache_metric(
                    "normalized_entropy", result, cache_generation=generation, **cache_params
                )
            self.cache_manager.record_calculation_time("normalized_entropy", calculation_time)

            return result

        except Exception as e:
            logger.warning(f"Normalized entropy calculation failed: {e}")
            return 0.0

    async def global_normalized_entropy_cached(self, state: list[str],
                                     symbol_probability_cache: dict[str, float],
                                     total_symbols: int) -> float:
        """
        Calculate global normalized entropy with caching.

        Args:
            state: Current state symbols
            symbol_probability_cache: Cached symbol probabilities
            total_symbols: Total number of unique symbols in the system

        Returns:
            Global normalized entropy value
        """
        cache_params = {
            "state_hash": hashlib.md5(str(sorted(state)).encode(), usedforsecurity=False).hexdigest(),
            "cache_hash": hashlib.md5(
                str(sorted(symbol_probability_cache.items())).encode(), usedforsecurity=False
            ).hexdigest(),
            "total_symbols": total_symbols
        }

        generation = await self.cache_manager.get_cache_generation()
        cached_value = await self.cache_manager.get_cached_metric(
            "global_normalized_entropy", cache_generation=generation, **cache_params
        ) if generation is not None else None
        if cached_value is not None:
            return cached_value

        start_time = time.time()

        from kato.informatics.metrics import global_normalized_entropy

        try:
            result = global_normalized_entropy(state, symbol_probability_cache, total_symbols)
            calculation_time = time.time() - start_time

            if generation is not None:
                await self.cache_manager.cache_metric(
                    "global_normalized_entropy", result, cache_generation=generation, **cache_params
                )
            self.cache_manager.record_calculation_time("global_normalized_entropy", calculation_time)

            return result

        except Exception as e:
            logger.warning(f"Global normalized entropy calculation failed: {e}")
            return 0.0

    async def conditional_probability_cached(self, state: list[str],
                                           symbol_probabilities: dict[str, float]) -> float:
        """
        Calculate conditional probability with caching.

        Args:
            state: State symbols (flat list)
            symbol_probabilities: Symbol probability mapping

        Returns:
            Conditional probability value
        """
        cache_params = {
            "state_hash": hashlib.md5(str(sorted(state)).encode(), usedforsecurity=False).hexdigest(),
            "probabilities_hash": hashlib.md5(
                str(sorted(symbol_probabilities.items())).encode(), usedforsecurity=False
            ).hexdigest()
        }

        generation = await self.cache_manager.get_cache_generation()
        cached_value = await self.cache_manager.get_cached_metric(
            "conditional_probability", cache_generation=generation, **cache_params
        ) if generation is not None else None
        if cached_value is not None:
            return cached_value

        start_time = time.time()

        from kato.informatics.metrics import conditionalProbability

        try:
            result = conditionalProbability(state, symbol_probabilities)
            calculation_time = time.time() - start_time

            if generation is not None:
                await self.cache_manager.cache_metric(
                    "conditional_probability", result, cache_generation=generation, **cache_params
                )
            self.cache_manager.record_calculation_time("conditional_probability", calculation_time)

            return result

        except Exception as e:
            logger.warning(f"Conditional probability calculation failed: {e}")
            return 0.0


async def get_metrics_cache_manager() -> Optional[MetricsCacheManager]:
    """Get or create global metrics cache manager instance."""
    global _metrics_cache_manager

    if _metrics_cache_manager is None:
        import os
        redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379')
        _metrics_cache_manager = MetricsCacheManager(redis_url=redis_url)
        if not await _metrics_cache_manager.initialize():
            _metrics_cache_manager = None
            logger.error("Failed to initialize global metrics cache manager")

    return _metrics_cache_manager


async def close_metrics_cache_manager() -> None:
    """Close and drop the global metrics cache manager, if one was created.

    The manager opens a redis.asyncio client in initialize() and previously had
    no teardown path at all, so its connection pool leaked for the life of the
    process. Resetting the singleton to None lets a later
    get_metrics_cache_manager() re-initialize cleanly.
    """
    global _metrics_cache_manager

    manager, _metrics_cache_manager = _metrics_cache_manager, None
    if manager is not None:
        await manager.close()
        logger.info("Metrics cache manager closed")


def create_cached_calculator() -> Optional[CachedMetricsCalculator]:
    """Create cached metrics calculator instance."""
    # This would need to be called from an async context
    # For now, return None to maintain compatibility
    return None
