"""
Modern Vector Search Engine for KATO

This module provides a high-performance vector search engine that leverages
modern vector databases and optimization techniques.
"""

import asyncio
import logging
from typing import Any, Optional, Union

try:
    import numpy as np
    HAS_NUMPY = True
except (ImportError, AttributeError):
    HAS_NUMPY = False
    # Create a mock numpy for testing
    class np:
        ndarray = list
        @staticmethod
        def array(x):
            return x
        @staticmethod
        def linalg_norm(x):
            return sum(i**2 for i in x) ** 0.5
import hashlib
import time
from dataclasses import dataclass

from ..config.vectordb_config import VectorDBConfig, get_vector_db_config
from ..representations.vector_object import VectorObject
from ..storage import VectorBatch, VectorSearchResult, get_vector_store

logger = logging.getLogger('kato.searches.vector_engine')


@dataclass
class SearchMetrics:
    """Metrics for search performance monitoring"""
    search_time_ms: float
    vectors_scanned: int
    cache_hit: bool
    backend: str

    def log_metrics(self):
        """Log search metrics"""
        logger.debug(
            f"Search metrics: time={self.search_time_ms:.2f}ms, "
            f"scanned={self.vectors_scanned}, cache_hit={self.cache_hit}, "
            f"backend={self.backend}"
        )


class VectorSearchEngine:
    """
    Modern vector search engine with caching, batching, and optimization.

    Features:
    - Automatic backend selection based on configuration
    - Result caching for frequently searched vectors
    - Batch processing for efficiency
    - Async operations for better concurrency
    - Automatic fallback to legacy search if needed
    """

    def __init__(
        self,
        config: Optional[VectorDBConfig] = None,
        collection_name: str = "kato_vectors",
        enable_cache: bool = True,
        cache_size: int = 1000
    ):
        """
        Initialize vector search engine.

        Args:
            config: Vector database configuration
            collection_name: Name of the vector collection
            enable_cache: Whether to enable result caching
            cache_size: Maximum number of cached results
        """
        self.config = config or get_vector_db_config()
        self.collection_name = collection_name
        self.enable_cache = enable_cache and self.config.cache.enabled

        # Initialize vector store
        self.store = get_vector_store(config=self.config)

        # Initialize cache if enabled
        self._cache = {} if self.enable_cache else None
        self.cache_size = cache_size

        # Performance tracking
        self.total_searches = 0
        self.cache_hits = 0
        self.total_search_time = 0.0

        # Ensure async event loop exists
        try:
            self._loop = asyncio.get_event_loop()
        except RuntimeError:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)

        logger.info(
            f"Initialized vector search engine: backend={self.config.backend}, "
            f"collection={collection_name}, cache={self.enable_cache}"
        )

    async def initialize(self) -> bool:
        """
        Initialize the search engine and connect to backend.

        Returns:
            True if initialization successful
        """
        try:
            # Connect to vector store
            if not await self.store.connect():
                logger.error("Failed to connect to vector store")
                return False

            # Ensure collection exists
            vector_dim = self.config.vector_dim or 512  # Default dimension

            if not await self.store.ensure_collection(
                self.collection_name,
                vector_dim,
                distance=self.config.similarity_metric
            ):
                logger.error(f"Failed to ensure collection: {self.collection_name}")
                return False

            logger.info("Vector search engine initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize search engine: {e}")
            return False

    def _run_async_in_sync(self, coro):
        """Helper to run async code in sync context, handling event loop issues"""
        import asyncio
        import concurrent.futures

        # Check if we're in an async context
        try:
            asyncio.get_running_loop()
            # We're already in an event loop, need to run in thread
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(asyncio.run, coro)
                return future.result()
        except RuntimeError:
            # No event loop running, can run directly
            return asyncio.run(coro)

    def initialize_sync(self) -> bool:
        """Synchronous wrapper for initialize"""
        return self._run_async_in_sync(self.initialize())

    async def add_vector(
        self,
        vector: Union[np.ndarray, VectorObject],
        vector_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None
    ) -> bool:
        """
        Add a vector to the search index.

        Args:
            vector: Vector to add (numpy array or VectorObject)
            vector_id: Optional ID for the vector
            metadata: Optional metadata to store with vector

        Returns:
            True if addition successful
        """
        try:
            # Convert VectorObject if needed
            if isinstance(vector, VectorObject):
                vector_array = vector.vector
                vector_id = vector_id or vector.name
            else:
                vector_array = vector
                if vector_id is None:
                    # Generate ID from vector hash
                    vector_hash = hashlib.sha1(str(vector_array).encode(), usedforsecurity=False).hexdigest()
                    vector_id = f"VCTR|{vector_hash}"

            # Add to vector store
            success = await self.store.add_vector(
                self.collection_name,
                vector_id,
                vector_array,
                metadata
            )

            # Invalidate cache for this vector
            if self._cache and vector_id in self._cache:
                del self._cache[vector_id]

            return success

        except Exception as e:
            logger.error(f"Failed to add vector: {e}")
            return False

    def add_vector_sync(
        self,
        vector: Union[np.ndarray, VectorObject],
        vector_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None
    ) -> bool:
        """Synchronous wrapper for add_vector"""
        return self._loop.run_until_complete(
            self.add_vector(vector, vector_id, metadata)
        )

    async def add_vectors_batch(
        self,
        vectors: list[Union[np.ndarray, VectorObject]],
        vector_ids: Optional[list[str]] = None,
        metadata: Optional[list[dict[str, Any]]] = None
    ) -> tuple[int, list[str]]:
        """
        Add multiple vectors in batch.

        Args:
            vectors: List of vectors to add
            vector_ids: Optional list of IDs
            metadata: Optional list of metadata dicts

        Returns:
            Tuple of (number added successfully, list of failed IDs)
        """
        try:
            # Prepare batch
            if vector_ids is None:
                vector_ids = []
                for v in vectors:
                    if isinstance(v, VectorObject):
                        vector_ids.append(v.name)
                    else:
                        vector_hash = hashlib.sha1(str(v).encode(), usedforsecurity=False).hexdigest()
                        vector_ids.append(f"VCTR|{vector_hash}")

            # Convert vectors to numpy arrays
            vector_arrays = []
            for v in vectors:
                if isinstance(v, VectorObject):
                    vector_arrays.append(v.vector)
                else:
                    vector_arrays.append(v)

            # Create batch
            batch = VectorBatch(
                ids=vector_ids,
                vectors=np.array(vector_arrays),
                payloads=metadata
            )

            # Add batch to store
            success_count, failed_ids = await self.store.add_vectors(
                self.collection_name,
                batch
            )

            # Invalidate cache for added vectors
            if self._cache:
                for vid in vector_ids:
                    if vid in self._cache:
                        del self._cache[vid]

            logger.info(f"Added {success_count}/{len(vectors)} vectors to index")
            return success_count, failed_ids

        except Exception as e:
            logger.error(f"Failed to add vector batch: {e}")
            return 0, vector_ids if vector_ids else []

    def add_vectors_batch_sync(
        self,
        vectors: list[Union[np.ndarray, VectorObject]],
        vector_ids: Optional[list[str]] = None,
        metadata: Optional[list[dict[str, Any]]] = None
    ) -> tuple[int, list[str]]:
        """Synchronous wrapper for add_vectors_batch"""
        return self._loop.run_until_complete(
            self.add_vectors_batch(vectors, vector_ids, metadata)
        )

    async def search(
        self,
        query_vector: Union[np.ndarray, VectorObject],
        k: int = 3,
        filter: Optional[dict[str, Any]] = None,
        include_vectors: bool = False,
        use_cache: bool = True
    ) -> list[VectorSearchResult]:
        """
        Search for similar vectors.

        Args:
            query_vector: Query vector
            k: Number of results to return
            filter: Optional metadata filter
            include_vectors: Whether to include vector data in results
            use_cache: Whether to use cache for this search

        Returns:
            List of search results
        """
        start_time = time.time()
        cache_hit = False

        try:
            # Convert VectorObject if needed
            if isinstance(query_vector, VectorObject):
                query_array = query_vector.vector
                query_id = query_vector.name
            else:
                query_array = query_vector
                query_hash = hashlib.sha1(str(query_array).encode(), usedforsecurity=False).hexdigest()
                query_id = f"VCTR|{query_hash}"

            # Check cache
            cache_key = None
            if use_cache and self._cache:
                cache_key = self._make_cache_key(query_id, k, filter)
                if cache_key in self._cache:
                    cache_hit = True
                    self.cache_hits += 1
                    results = self._cache[cache_key]
                    logger.debug(f"Cache hit for query: {query_id[:20]}...")
                else:
                    # Perform search
                    results = await self.store.search(
                        self.collection_name,
                        query_array,
                        limit=k,
                        filter=filter,
                        include_vectors=include_vectors
                    )

                    # Update cache
                    self._update_cache(cache_key, results)
            else:
                # Perform search without cache
                results = await self.store.search(
                    self.collection_name,
                    query_array,
                    limit=k,
                    filter=filter,
                    include_vectors=include_vectors
                )

            # Update metrics
            search_time = (time.time() - start_time) * 1000  # Convert to ms
            self.total_searches += 1
            self.total_search_time += search_time

            # Log metrics
            metrics = SearchMetrics(
                search_time_ms=search_time,
                vectors_scanned=len(results),
                cache_hit=cache_hit,
                backend=self.config.backend
            )
            metrics.log_metrics()

            return results

        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []

    def search_sync(
        self,
        query_vector: Union[np.ndarray, VectorObject],
        k: int = 3,
        filter: Optional[dict[str, Any]] = None,
        include_vectors: bool = False,
        use_cache: bool = True
    ) -> list[VectorSearchResult]:
        """Synchronous wrapper for search"""
        import asyncio
        try:
            # Try to get current running loop
            loop = asyncio.get_running_loop()
            if loop == self._loop:
                # We're in the same loop, need to handle differently
                # Create a future and run the coroutine in a thread
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        self.search(query_vector, k, filter, include_vectors, use_cache)
                    )
                    return future.result()
            else:
                # Different loop, can use run_until_complete
                return self._loop.run_until_complete(
                    self.search(query_vector, k, filter, include_vectors, use_cache)
                )
        except RuntimeError:
            # No loop running, safe to use run_until_complete
            return self._loop.run_until_complete(
                self.search(query_vector, k, filter, include_vectors, use_cache)
        )

    async def batch_search(
        self,
        query_vectors: list[Union[np.ndarray, VectorObject]],
        k: int = 3,
        filter: Optional[dict[str, Any]] = None,
        include_vectors: bool = False
    ) -> list[list[VectorSearchResult]]:
        """
        Search for multiple query vectors in batch.

        Args:
            query_vectors: List of query vectors
            k: Number of results per query
            filter: Optional metadata filter
            include_vectors: Whether to include vector data

        Returns:
            List of result lists, one per query
        """
        try:
            # Convert to numpy arrays
            query_arrays = []
            for v in query_vectors:
                if isinstance(v, VectorObject):
                    query_arrays.append(v.vector)
                else:
                    query_arrays.append(v)

            # Perform batch search
            results = await self.store.batch_search(
                self.collection_name,
                np.array(query_arrays),
                limit=k,
                filter=filter,
                include_vectors=include_vectors
            )

            return results

        except Exception as e:
            logger.error(f"Batch search failed: {e}")
            return [[] for _ in query_vectors]

    def batch_search_sync(
        self,
        query_vectors: list[Union[np.ndarray, VectorObject]],
        k: int = 3,
        filter: Optional[dict[str, Any]] = None,
        include_vectors: bool = False
    ) -> list[list[VectorSearchResult]]:
        """Synchronous wrapper for batch_search"""
        return self._run_async_in_sync(
            self.batch_search(query_vectors, k, filter, include_vectors)
        )

    async def find_nearest_neighbors(
        self,
        vector: Union[np.ndarray, VectorObject],
        k: int = 3,
        exclude_self: bool = True
    ) -> list[tuple[str, float]]:
        """
        Find k nearest neighbors for a vector.

        Args:
            vector: Query vector
            k: Number of neighbors
            exclude_self: Whether to exclude the query vector itself

        Returns:
            List of (vector_id, distance) tuples
        """
        # Search for k+1 if excluding self
        search_k = k + 1 if exclude_self else k

        results = await self.search(vector, search_k, include_vectors=False)

        # Convert to simple format
        neighbors = [(r.id, r.score) for r in results]

        # Exclude self if needed
        if exclude_self and isinstance(vector, VectorObject):
            neighbors = [(id, score) for id, score in neighbors if id != vector.name]

        return neighbors[:k]

    def find_nearest_neighbors_sync(
        self,
        vector: Union[np.ndarray, VectorObject],
        k: int = 3,
        exclude_self: bool = True
    ) -> list[tuple[str, float]]:
        """Synchronous wrapper for find_nearest_neighbors"""
        return self._run_async_in_sync(
            self.find_nearest_neighbors(vector, k, exclude_self)
        )

    async def update_vector(
        self,
        vector_id: str,
        vector: Optional[np.ndarray] = None,
        metadata: Optional[dict[str, Any]] = None
    ) -> bool:
        """Update a vector and/or its metadata"""
        success = await self.store.update_vector(
            self.collection_name,
            vector_id,
            vector,
            metadata
        )

        # Invalidate cache
        if self._cache and vector_id in self._cache:
            del self._cache[vector_id]

        return success

    async def delete_vector(self, vector_id: str) -> bool:
        """Delete a vector from the index"""
        success = await self.store.delete_vector(
            self.collection_name,
            vector_id
        )

        # Invalidate cache
        if self._cache and vector_id in self._cache:
            del self._cache[vector_id]

        return success

    async def delete_collection(self) -> bool:
        """
        Delete the entire Qdrant collection for this search engine.

        This permanently removes all vectors and metadata for this collection.
        Used during processor cleanup to prevent resource leaks.

        Returns:
            True if deletion successful, False otherwise
        """
        try:
            success = await self.store.delete_collection(self.collection_name)
            if success:
                logger.info(f"Deleted Qdrant collection: {self.collection_name}")
                # Clear cache
                if self._cache:
                    self._cache.clear()
            return success
        except Exception as e:
            logger.error(f"Error deleting collection {self.collection_name}: {e}")
            return False

    def delete_collection_sync(self) -> bool:
        """Synchronous wrapper for delete_collection"""
        return self._run_async_in_sync(self.delete_collection())

    async def get_stats(self) -> dict[str, Any]:
        """Get search engine statistics"""
        collection_info = await self.store.get_collection_info(self.collection_name)

        stats = {
            'backend': self.config.backend,
            'collection': self.collection_name,
            'total_vectors': collection_info.get('vectors_count', 0),
            'vector_dim': collection_info.get('vector_dim'),
            'total_searches': self.total_searches,
            'cache_hits': self.cache_hits,
            'cache_hit_rate': self.cache_hits / self.total_searches if self.total_searches > 0 else 0,
            'avg_search_time_ms': self.total_search_time / self.total_searches if self.total_searches > 0 else 0,
            'cache_size': len(self._cache) if self._cache else 0,
            'collection_info': collection_info
        }

        return stats

    def get_stats_sync(self) -> dict[str, Any]:
        """Synchronous wrapper for get_stats"""
        return self._run_async_in_sync(self.get_stats())

    async def optimize(self) -> bool:
        """Optimize the vector index for better performance"""
        return await self.store.optimize_collection(self.collection_name)

    async def clear_cache(self):
        """Clear the search cache"""
        if self._cache:
            self._cache.clear()
            logger.info("Cleared search cache")

    async def close(self):
        """Close the search engine and clean up resources"""
        await self.store.disconnect()
        if self._cache:
            self._cache.clear()
        logger.info("Vector search engine closed")

    def close_sync(self):
        """Synchronous wrapper for close"""
        return self._run_async_in_sync(self.close())

    # Helper methods
    def _make_cache_key(
        self,
        query_id: str,
        k: int,
        filter: Optional[dict[str, Any]]
    ) -> str:
        """Create a cache key for a search query"""
        filter_str = str(sorted(filter.items())) if filter else ""
        return f"{query_id}:{k}:{filter_str}"

    def _update_cache(self, key: str, results: list[VectorSearchResult]):
        """Update the cache with new results"""
        if not self._cache:
            return

        # Implement LRU by removing oldest if cache is full
        if len(self._cache) >= self.cache_size:
            # Remove first (oldest) item
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]

        self._cache[key] = results


class VectorIndexer:
    """
    Modern implementation of Vector Indexer.

    Indexes vectors and performs similarity search using the modern
    vector search engine for better performance.
    """

    def __init__(self, procs: int = 1, vectors_kb=None, processor_id: str = None):
        """Initialize Vector Indexer with isolated collection

        Args:
            procs: Number of processors (kept for compatibility but not used)
            vectors_kb: Vector knowledge base (kept for compatibility)
            processor_id: Unique processor ID for Qdrant collection isolation
        """
        self.procs = procs  # Kept for compatibility but not used
        self.vectors_kb = vectors_kb  # Kept for compatibility
        self.processor_id = processor_id or "default"
        # Use processor_id in collection name for complete isolation
        collection_name = f"vectors_{self.processor_id}"
        self.engine = VectorSearchEngine(collection_name=collection_name)
        self.initialized = False

        # Compatibility attributes
        self.datasubset = []

    def initialize(self):
        """Initialize the search engine"""
        if not self.initialized:
            self.initialized = self.engine.initialize_sync()
            if not self.initialized:
                logger.error("Failed to initialize Vector Indexer")

    def loadMemoryIntoRAM(self, vectors_dict: dict[str, VectorObject]):
        """Load vectors into the search index"""
        self.initialize()

        # Convert to lists for batch addition
        vector_ids = []
        vector_arrays = []

        for vector_id, vector_obj in vectors_dict.items():
            vector_ids.append(vector_id)
            vector_arrays.append(vector_obj.vector)

        # Add vectors in batch
        if vector_arrays:
            success, failed = self.engine.add_vectors_batch_sync(
                vector_arrays,
                vector_ids
            )
            logger.info(f"Loaded {success}/{len(vector_arrays)} vectors into vector index")

        # Update compatibility attribute
        self.datasubset = list(vectors_dict.values())

    def clearPatternsFromRAM(self):
        """Clear the search index"""
        self.engine.clear_cache()
        self.datasubset = []

    def assignNewlyLearnedToWorkers(self, new_vectors):
        """
        Compatibility method - in the modern architecture, vectors are automatically
        indexed when stored in the vector database, so this is a no-op.
        """
        # In the new architecture, vectors are automatically indexed when stored
        # No need to manually assign to workers
        logger.debug(f"Received {len(new_vectors)} new vectors (auto-indexed)")
        pass

    def findNearestPoints(self, query_vector: VectorObject) -> list[str]:
        """Find the 3 nearest vectors to the query"""
        self.initialize()

        # Perform search
        results = self.engine.search_sync(
            query_vector,
            k=3,
            include_vectors=False
        )

        # Return vector IDs
        return [r.id for r in results]

    def delete_collection(self):
        """
        Delete the Qdrant collection for this processor.

        This permanently removes all vectors and metadata for this processor.
        Used during processor cleanup to prevent resource leaks.
        """
        try:
            success = self.engine.delete_collection_sync()
            if success:
                logger.info(f"Deleted Qdrant collection for processor {self.processor_id}")
            return success
        except Exception as e:
            logger.error(f"Error deleting Qdrant collection for processor {self.processor_id}: {e}")
            return False

    def __del__(self):
        """Cleanup on deletion"""
        # Don't try to close in destructor - causes issues with async event loops
        # The engine should be explicitly closed when needed
        pass
