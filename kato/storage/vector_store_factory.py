"""
Vector Store Factory

Factory pattern implementation for creating vector store instances
based on configuration.
"""

import logging
from typing import Optional

from ..config.vectordb_config import VectorDBConfig, get_vector_db_config
from .vector_store_interface import VectorStore

logger = logging.getLogger('kato.storage.factory')


class VectorStoreFactory:
    """Factory for creating vector store instances"""

    _stores: dict[str, type] = {}
    _instances: dict[str, VectorStore] = {}

    @classmethod
    def register_store(cls, backend: str, store_class: type):
        """
        Register a vector store implementation.

        Args:
            backend: Name of the backend (e.g., 'qdrant', 'mongodb')
            store_class: Class implementing VectorStore interface
        """
        cls._stores[backend] = store_class
        logger.info(f"Registered vector store: {backend}")

    @classmethod
    def create_store(
        cls,
        config: Optional[VectorDBConfig] = None,
        backend: Optional[str] = None
    ) -> VectorStore:
        """
        Create a vector store instance.

        Args:
            config: Vector database configuration (uses global if None)
            backend: Override backend selection

        Returns:
            VectorStore instance

        Raises:
            ValueError: If backend is not supported
        """
        if config is None:
            config = get_vector_db_config()

        backend = backend or config.backend

        # Check if store is registered
        if backend not in cls._stores:
            # Try to auto-register known backends
            cls._auto_register_backends()

            if backend not in cls._stores:
                raise ValueError(
                    f"Unsupported vector store backend: {backend}. "
                    f"Available: {list(cls._stores.keys())}"
                )

        # Create store instance
        store_class = cls._stores[backend]
        store = store_class(config.to_dict())

        logger.info(f"Created vector store: {backend}")
        return store

    @classmethod
    def get_store(
        cls,
        name: str = "default",
        config: Optional[VectorDBConfig] = None,
        backend: Optional[str] = None
    ) -> VectorStore:
        """
        Get or create a named vector store instance (singleton pattern).

        Args:
            name: Name for the store instance
            config: Vector database configuration
            backend: Override backend selection

        Returns:
            VectorStore instance
        """
        if name not in cls._instances:
            cls._instances[name] = cls.create_store(config, backend)

        return cls._instances[name]

    @classmethod
    def _auto_register_backends(cls):
        """Auto-register known vector store backends"""

        # Try to import and register Qdrant
        try:
            from .qdrant_store import QdrantStore
            cls.register_store("qdrant", QdrantStore)
        except ImportError:
            logger.debug("Qdrant store not available")

        # MongoDB store removed - use Qdrant for vector storage

        # Try to import and register FAISS (if implemented)
        try:
            from .faiss_store import FAISSStore
            cls.register_store("faiss", FAISSStore)
        except ImportError:
            logger.debug("FAISS store not available")

        # Try to import and register Milvus (if implemented)
        try:
            from .milvus_store import MilvusStore
            cls.register_store("milvus", MilvusStore)
        except ImportError:
            logger.debug("Milvus store not available")

        # Try to import and register Weaviate (if implemented)
        try:
            from .weaviate_store import WeaviateStore
            cls.register_store("weaviate", WeaviateStore)
        except ImportError:
            logger.debug("Weaviate store not available")

    @classmethod
    def list_backends(cls) -> list:
        """List available vector store backends"""
        cls._auto_register_backends()
        return list(cls._stores.keys())

    @classmethod
    def clear_instances(cls):
        """Clear all cached store instances"""
        cls._instances.clear()
        logger.info("Cleared all vector store instances")


def get_vector_store(
    name: str = "default",
    config: Optional[VectorDBConfig] = None,
    backend: Optional[str] = None
) -> VectorStore:
    """
    Convenience function to get a vector store instance.

    Args:
        name: Name for the store instance
        config: Vector database configuration
        backend: Override backend selection

    Returns:
        VectorStore instance
    """
    return VectorStoreFactory.get_store(name, config, backend)


def create_vector_store(
    config: Optional[VectorDBConfig] = None,
    backend: Optional[str] = None
) -> VectorStore:
    """
    Convenience function to create a new vector store instance.

    Args:
        config: Vector database configuration
        backend: Override backend selection

    Returns:
        VectorStore instance
    """
    return VectorStoreFactory.create_store(config, backend)


# Auto-register backends on module import
VectorStoreFactory._auto_register_backends()
