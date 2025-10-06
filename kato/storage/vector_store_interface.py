"""
Abstract Vector Store Interface

This module defines the abstract interface for vector storage backends.
All vector database implementations must conform to this interface.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional

try:
    import numpy as np
    HAS_NUMPY = True
except (ImportError, AttributeError):
    HAS_NUMPY = False
    # Create a mock numpy for type hints
    class np:
        ndarray = list  # Use list as fallback type
import logging

logger = logging.getLogger('kato.storage.interface')


@dataclass
class VectorSearchResult:
    """Result from a vector similarity search"""
    id: str  # Vector ID
    score: float  # Similarity score (distance or similarity depending on metric)
    vector: Optional[np.ndarray] = None  # The vector itself (optional)
    payload: Optional[dict[str, Any]] = None  # Additional metadata

    def __lt__(self, other):
        """For sorting by score"""
        return self.score < other.score


@dataclass
class VectorBatch:
    """Batch of vectors for bulk operations"""
    ids: list[str]
    vectors: np.ndarray  # Shape: (n_vectors, vector_dim)
    payloads: Optional[list[dict[str, Any]]] = None

    def __post_init__(self):
        """Validate batch consistency"""
        n_vectors = len(self.ids)
        if self.vectors.shape[0] != n_vectors:
            raise ValueError(f"Mismatch: {n_vectors} IDs but {self.vectors.shape[0]} vectors")
        if self.payloads and len(self.payloads) != n_vectors:
            raise ValueError(f"Mismatch: {n_vectors} IDs but {len(self.payloads)} payloads")

    @property
    def size(self) -> int:
        """Number of vectors in batch"""
        return len(self.ids)

    @property
    def vector_dim(self) -> int:
        """Dimension of vectors"""
        return self.vectors.shape[1] if self.vectors.ndim > 1 else 0


class VectorStore(ABC):
    """
    Abstract base class for vector storage backends.

    This interface provides a unified API for different vector database
    implementations, allowing seamless switching between backends.
    """

    def __init__(self, config: dict[str, Any]):
        """
        Initialize vector store with configuration.

        Args:
            config: Backend-specific configuration dictionary
        """
        self.config = config
        self._is_connected = False

    @abstractmethod
    async def connect(self) -> bool:
        """
        Establish connection to the vector store.

        Returns:
            True if connection successful, False otherwise
        """
        pass

    @abstractmethod
    async def disconnect(self) -> bool:
        """
        Close connection to the vector store.

        Returns:
            True if disconnection successful, False otherwise
        """
        pass

    @abstractmethod
    async def create_collection(
        self,
        collection_name: str,
        vector_dim: int,
        **kwargs
    ) -> bool:
        """
        Create a new vector collection/index.

        Args:
            collection_name: Name of the collection
            vector_dim: Dimension of vectors to be stored
            **kwargs: Additional backend-specific parameters

        Returns:
            True if creation successful, False otherwise
        """
        pass

    @abstractmethod
    async def delete_collection(self, collection_name: str) -> bool:
        """
        Delete a vector collection/index.

        Args:
            collection_name: Name of the collection to delete

        Returns:
            True if deletion successful, False otherwise
        """
        pass

    @abstractmethod
    async def collection_exists(self, collection_name: str) -> bool:
        """
        Check if a collection exists.

        Args:
            collection_name: Name of the collection

        Returns:
            True if collection exists, False otherwise
        """
        pass

    @abstractmethod
    async def add_vector(
        self,
        collection_name: str,
        vector_id: str,
        vector: np.ndarray,
        payload: Optional[dict[str, Any]] = None
    ) -> bool:
        """
        Add a single vector to the store.

        Args:
            collection_name: Name of the collection
            vector_id: Unique identifier for the vector
            vector: The vector to store
            payload: Optional metadata to store with the vector

        Returns:
            True if addition successful, False otherwise
        """
        pass

    @abstractmethod
    async def add_vectors(
        self,
        collection_name: str,
        batch: VectorBatch
    ) -> tuple[int, list[str]]:
        """
        Add multiple vectors in batch.

        Args:
            collection_name: Name of the collection
            batch: Batch of vectors to add

        Returns:
            Tuple of (number of successful additions, list of failed IDs)
        """
        pass

    @abstractmethod
    async def get_vector(
        self,
        collection_name: str,
        vector_id: str,
        include_vector: bool = True
    ) -> Optional[VectorSearchResult]:
        """
        Retrieve a vector by ID.

        Args:
            collection_name: Name of the collection
            vector_id: ID of the vector to retrieve
            include_vector: Whether to include the vector data

        Returns:
            VectorSearchResult if found, None otherwise
        """
        pass

    @abstractmethod
    async def get_vectors(
        self,
        collection_name: str,
        vector_ids: list[str],
        include_vectors: bool = True
    ) -> list[VectorSearchResult]:
        """
        Retrieve multiple vectors by IDs.

        Args:
            collection_name: Name of the collection
            vector_ids: List of vector IDs to retrieve
            include_vectors: Whether to include vector data

        Returns:
            List of VectorSearchResults (may be shorter than input if some not found)
        """
        pass

    @abstractmethod
    async def update_vector(
        self,
        collection_name: str,
        vector_id: str,
        vector: Optional[np.ndarray] = None,
        payload: Optional[dict[str, Any]] = None
    ) -> bool:
        """
        Update a vector and/or its payload.

        Args:
            collection_name: Name of the collection
            vector_id: ID of the vector to update
            vector: New vector data (if None, vector is not updated)
            payload: New payload (if None, payload is not updated)

        Returns:
            True if update successful, False otherwise
        """
        pass

    @abstractmethod
    async def delete_vector(
        self,
        collection_name: str,
        vector_id: str
    ) -> bool:
        """
        Delete a vector from the store.

        Args:
            collection_name: Name of the collection
            vector_id: ID of the vector to delete

        Returns:
            True if deletion successful, False otherwise
        """
        pass

    @abstractmethod
    async def delete_vectors(
        self,
        collection_name: str,
        vector_ids: list[str]
    ) -> tuple[int, list[str]]:
        """
        Delete multiple vectors.

        Args:
            collection_name: Name of the collection
            vector_ids: List of vector IDs to delete

        Returns:
            Tuple of (number of successful deletions, list of failed IDs)
        """
        pass

    @abstractmethod
    async def search(
        self,
        collection_name: str,
        query_vector: np.ndarray,
        limit: int = 10,
        filter: Optional[dict[str, Any]] = None,
        include_vectors: bool = False,
        **kwargs
    ) -> list[VectorSearchResult]:
        """
        Search for similar vectors.

        Args:
            collection_name: Name of the collection
            query_vector: Query vector for similarity search
            limit: Maximum number of results to return
            filter: Optional filter conditions for metadata
            include_vectors: Whether to include vector data in results
            **kwargs: Additional backend-specific search parameters

        Returns:
            List of search results ordered by similarity
        """
        pass

    @abstractmethod
    async def batch_search(
        self,
        collection_name: str,
        query_vectors: np.ndarray,
        limit: int = 10,
        filter: Optional[dict[str, Any]] = None,
        include_vectors: bool = False,
        **kwargs
    ) -> list[list[VectorSearchResult]]:
        """
        Search for multiple query vectors in batch.

        Args:
            collection_name: Name of the collection
            query_vectors: Array of query vectors
            limit: Maximum number of results per query
            filter: Optional filter conditions
            include_vectors: Whether to include vector data
            **kwargs: Additional search parameters

        Returns:
            List of result lists, one per query vector
        """
        pass

    @abstractmethod
    async def count_vectors(
        self,
        collection_name: str,
        filter: Optional[dict[str, Any]] = None
    ) -> int:
        """
        Count vectors in a collection.

        Args:
            collection_name: Name of the collection
            filter: Optional filter conditions

        Returns:
            Number of vectors matching the filter
        """
        pass

    @abstractmethod
    async def get_collection_info(
        self,
        collection_name: str
    ) -> dict[str, Any]:
        """
        Get information about a collection.

        Args:
            collection_name: Name of the collection

        Returns:
            Dictionary with collection information (backend-specific)
        """
        pass

    @abstractmethod
    async def list_collections(self) -> list[str]:
        """
        List all available collections.

        Returns:
            List of collection names
        """
        pass

    @abstractmethod
    async def optimize_collection(
        self,
        collection_name: str,
        **kwargs
    ) -> bool:
        """
        Optimize a collection for better performance.

        This might include operations like:
        - Rebuilding indexes
        - Compacting storage
        - Rebalancing shards

        Args:
            collection_name: Name of the collection
            **kwargs: Backend-specific optimization parameters

        Returns:
            True if optimization successful, False otherwise
        """
        pass

    @abstractmethod
    async def backup_collection(
        self,
        collection_name: str,
        backup_path: str
    ) -> bool:
        """
        Backup a collection to a file.

        Args:
            collection_name: Name of the collection
            backup_path: Path to save the backup

        Returns:
            True if backup successful, False otherwise
        """
        pass

    @abstractmethod
    async def restore_collection(
        self,
        collection_name: str,
        backup_path: str
    ) -> bool:
        """
        Restore a collection from a backup.

        Args:
            collection_name: Name of the collection
            backup_path: Path to the backup file

        Returns:
            True if restore successful, False otherwise
        """
        pass

    # Synchronous convenience methods
    def add_vector_sync(
        self,
        collection_name: str,
        vector_id: str,
        vector: np.ndarray,
        payload: Optional[dict[str, Any]] = None
    ) -> bool:
        """Synchronous wrapper for add_vector"""
        import asyncio
        return asyncio.run(self.add_vector(collection_name, vector_id, vector, payload))

    def search_sync(
        self,
        collection_name: str,
        query_vector: np.ndarray,
        limit: int = 10,
        filter: Optional[dict[str, Any]] = None,
        include_vectors: bool = False,
        **kwargs
    ) -> list[VectorSearchResult]:
        """Synchronous wrapper for search"""
        import asyncio
        return asyncio.run(self.search(
            collection_name, query_vector, limit, filter, include_vectors, **kwargs
        ))

    def get_vector_sync(
        self,
        collection_name: str,
        vector_id: str,
        include_vector: bool = True
    ) -> Optional[VectorSearchResult]:
        """Synchronous wrapper for get_vector"""
        import asyncio
        return asyncio.run(self.get_vector(collection_name, vector_id, include_vector))

    # Utility methods
    async def clear_collection(self, collection_name: str) -> bool:
        """
        Clear all vectors from a collection without deleting it.

        Args:
            collection_name: Name of the collection

        Returns:
            True if clearing successful, False otherwise
        """
        # Default implementation: recreate the collection
        info = await self.get_collection_info(collection_name)
        if not info:
            return False

        vector_dim = info.get('vector_dim', info.get('dimension', 512))

        if not await self.delete_collection(collection_name):
            return False

        return await self.create_collection(collection_name, vector_dim)

    async def ensure_collection(
        self,
        collection_name: str,
        vector_dim: int,
        recreate: bool = False,
        **kwargs
    ) -> bool:
        """
        Ensure a collection exists, creating it if necessary.

        Args:
            collection_name: Name of the collection
            vector_dim: Dimension of vectors
            recreate: If True, delete existing collection first
            **kwargs: Additional creation parameters

        Returns:
            True if collection exists or was created successfully
        """
        if recreate and await self.collection_exists(collection_name):
            if not await self.delete_collection(collection_name):
                logger.error(f"Failed to delete existing collection: {collection_name}")
                return False

        if not await self.collection_exists(collection_name):
            if not await self.create_collection(collection_name, vector_dim, **kwargs):
                logger.error(f"Failed to create collection: {collection_name}")
                return False

        return True

    @property
    def is_connected(self) -> bool:
        """Check if store is connected"""
        return self._is_connected

    async def __aenter__(self):
        """Async context manager entry"""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, _exc_tb):
        """Async context manager exit"""
        await self.disconnect()
