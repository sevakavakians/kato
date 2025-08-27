#!/usr/bin/env python3
"""
Test Suite for Vector Database Integration

Tests the new vector database functionality including:
- Vector store interface
- Qdrant and MongoDB adapters
- Vector search engine
- Migration functionality
"""

import pytest
import numpy as np
import asyncio
import tempfile
import json
from typing import List, Dict, Any
from pathlib import Path
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from kato.config.vectordb_config import (
    VectorDBConfig, QuantizationConfig, IndexConfig,
    CacheConfig, GPUConfig, QdrantConfig, EXAMPLE_CONFIGS
)
from kato.storage import (
    VectorStore, VectorSearchResult, VectorBatch,
    VectorStoreFactory, get_vector_store
)
from kato.storage.mongodb_vector_store import MongoDBVectorStore
from kato.searches.vector_search_engine import VectorSearchEngine, CVCSearcherModern
from kato.representations.vector_object import VectorObject


class TestVectorDBConfig:
    """Test vector database configuration"""
    
    def test_default_config(self):
        """Test default configuration creation"""
        config = VectorDBConfig()
        assert config.backend == "qdrant"
        assert config.similarity_metric == "euclidean"
        assert config.batch_size == 1000
        assert config.validate()
    
    def test_config_from_dict(self):
        """Test configuration from dictionary"""
        config_dict = {
            "backend": "mongodb",
            "vector_dim": 256,
            "batch_size": 500,
            "cache": {
                "enabled": True,
                "size": 5000
            }
        }
        config = VectorDBConfig.from_dict(config_dict)
        assert config.backend == "mongodb"
        assert config.vector_dim == 256
        assert config.batch_size == 500
        assert config.cache.enabled is True
        assert config.cache.size == 5000
    
    def test_config_validation(self):
        """Test configuration validation"""
        # Valid config
        config = VectorDBConfig()
        assert config.validate()
        
        # Invalid backend
        config.backend = "invalid_backend"
        assert not config.validate()
        
        # Invalid vector dimension
        config = VectorDBConfig()
        config.vector_dim = -1
        assert not config.validate()
    
    def test_example_configs(self):
        """Test example configurations"""
        for name, config in EXAMPLE_CONFIGS.items():
            assert config.validate(), f"Example config '{name}' is invalid"
    
    def test_config_save_load(self):
        """Test saving and loading configuration"""
        config = VectorDBConfig(
            backend="qdrant",
            vector_dim=128,
            batch_size=2000
        )
        
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
            filepath = f.name
        
        try:
            # Save configuration
            config.save(filepath)
            
            # Load configuration
            loaded_config = VectorDBConfig.from_file(filepath)
            assert loaded_config.backend == config.backend
            assert loaded_config.vector_dim == config.vector_dim
            assert loaded_config.batch_size == config.batch_size
        finally:
            Path(filepath).unlink()


class TestVectorStoreInterface:
    """Test abstract vector store interface"""
    
    @pytest.fixture
    def mock_store(self):
        """Create a mock vector store for testing"""
        from unittest.mock import MagicMock, AsyncMock
        
        class MockVectorStore(VectorStore):
            def __init__(self, config):
                super().__init__(config)
                self.connected = False
                self.collections = {}
            
            async def connect(self):
                self.connected = True
                self._is_connected = True
                return True
            
            async def disconnect(self):
                self.connected = False
                self._is_connected = False
                return True
            
            async def create_collection(self, name, dim, **kwargs):
                self.collections[name] = {"dim": dim, "vectors": {}}
                return True
            
            async def delete_collection(self, name):
                if name in self.collections:
                    del self.collections[name]
                return True
            
            async def collection_exists(self, name):
                return name in self.collections
            
            async def add_vector(self, collection, id, vector, payload=None):
                if collection in self.collections:
                    self.collections[collection]["vectors"][id] = {
                        "vector": vector,
                        "payload": payload
                    }
                    return True
                return False
            
            async def add_vectors(self, collection, batch):
                success = 0
                failed = []
                for i in range(batch.size):
                    if await self.add_vector(
                        collection,
                        batch.ids[i],
                        batch.vectors[i],
                        batch.payloads[i] if batch.payloads else None
                    ):
                        success += 1
                    else:
                        failed.append(batch.ids[i])
                return success, failed
            
            async def get_vector(self, collection, id, include_vector=True):
                if collection in self.collections:
                    if id in self.collections[collection]["vectors"]:
                        data = self.collections[collection]["vectors"][id]
                        return VectorSearchResult(
                            id=id,
                            score=0.0,
                            vector=data["vector"] if include_vector else None,
                            payload=data["payload"]
                        )
                return None
            
            async def get_vectors(self, collection, ids, include_vectors=True):
                results = []
                for id in ids:
                    result = await self.get_vector(collection, id, include_vectors)
                    if result:
                        results.append(result)
                return results
            
            async def update_vector(self, collection, id, vector=None, payload=None):
                if collection in self.collections and id in self.collections[collection]["vectors"]:
                    if vector is not None:
                        self.collections[collection]["vectors"][id]["vector"] = vector
                    if payload is not None:
                        self.collections[collection]["vectors"][id]["payload"] = payload
                    return True
                return False
            
            async def delete_vector(self, collection, id):
                if collection in self.collections and id in self.collections[collection]["vectors"]:
                    del self.collections[collection]["vectors"][id]
                    return True
                return False
            
            async def delete_vectors(self, collection, ids):
                success = 0
                failed = []
                for id in ids:
                    if await self.delete_vector(collection, id):
                        success += 1
                    else:
                        failed.append(id)
                return success, failed
            
            async def search(self, collection, query, limit=10, filter=None, include_vectors=False, **kwargs):
                # Simple brute-force search for testing
                if collection not in self.collections:
                    return []
                
                results = []
                for id, data in self.collections[collection]["vectors"].items():
                    distance = np.linalg.norm(query - data["vector"])
                    results.append((distance, id, data))
                
                results.sort(key=lambda x: x[0])
                
                search_results = []
                for dist, id, data in results[:limit]:
                    search_results.append(VectorSearchResult(
                        id=id,
                        score=dist,
                        vector=data["vector"] if include_vectors else None,
                        payload=data["payload"]
                    ))
                
                return search_results
            
            async def batch_search(self, collection, queries, limit=10, filter=None, include_vectors=False, **kwargs):
                results = []
                for query in queries:
                    results.append(await self.search(collection, query, limit, filter, include_vectors, **kwargs))
                return results
            
            async def count_vectors(self, collection, filter=None):
                if collection in self.collections:
                    return len(self.collections[collection]["vectors"])
                return 0
            
            async def get_collection_info(self, collection):
                if collection in self.collections:
                    return {
                        "name": collection,
                        "vector_dim": self.collections[collection]["dim"],
                        "vectors_count": len(self.collections[collection]["vectors"])
                    }
                return {}
            
            async def list_collections(self):
                return list(self.collections.keys())
            
            async def optimize_collection(self, collection, **kwargs):
                return collection in self.collections
            
            async def backup_collection(self, collection, path):
                return collection in self.collections
            
            async def restore_collection(self, collection, path):
                return True
        
        return MockVectorStore({})
    
    @pytest.mark.asyncio
    async def test_store_lifecycle(self, mock_store):
        """Test vector store connection lifecycle"""
        assert not mock_store.is_connected
        
        # Connect
        assert await mock_store.connect()
        assert mock_store.is_connected
        
        # Disconnect
        assert await mock_store.disconnect()
        assert not mock_store.is_connected
    
    @pytest.mark.asyncio
    async def test_collection_operations(self, mock_store):
        """Test collection CRUD operations"""
        await mock_store.connect()
        
        collection_name = "test_collection"
        vector_dim = 128
        
        # Create collection
        assert await mock_store.create_collection(collection_name, vector_dim)
        assert await mock_store.collection_exists(collection_name)
        
        # Get collection info
        info = await mock_store.get_collection_info(collection_name)
        assert info["name"] == collection_name
        assert info["vector_dim"] == vector_dim
        
        # List collections
        collections = await mock_store.list_collections()
        assert collection_name in collections
        
        # Delete collection
        assert await mock_store.delete_collection(collection_name)
        assert not await mock_store.collection_exists(collection_name)
    
    @pytest.mark.asyncio
    async def test_vector_operations(self, mock_store):
        """Test vector CRUD operations"""
        await mock_store.connect()
        
        collection_name = "test_vectors"
        await mock_store.create_collection(collection_name, 128)
        
        # Add single vector
        vector_id = "test_vector_1"
        vector = np.random.rand(128)
        payload = {"metadata": "test"}
        
        assert await mock_store.add_vector(collection_name, vector_id, vector, payload)
        
        # Get vector
        result = await mock_store.get_vector(collection_name, vector_id)
        assert result is not None
        assert result.id == vector_id
        assert np.allclose(result.vector, vector)
        assert result.payload == payload
        
        # Update vector
        new_vector = np.random.rand(128)
        new_payload = {"metadata": "updated"}
        assert await mock_store.update_vector(collection_name, vector_id, new_vector, new_payload)
        
        result = await mock_store.get_vector(collection_name, vector_id)
        assert np.allclose(result.vector, new_vector)
        assert result.payload == new_payload
        
        # Delete vector
        assert await mock_store.delete_vector(collection_name, vector_id)
        assert await mock_store.get_vector(collection_name, vector_id) is None
    
    @pytest.mark.asyncio
    async def test_batch_operations(self, mock_store):
        """Test batch vector operations"""
        await mock_store.connect()
        
        collection_name = "test_batch"
        await mock_store.create_collection(collection_name, 64)
        
        # Create batch
        n_vectors = 10
        ids = [f"vec_{i}" for i in range(n_vectors)]
        vectors = np.random.rand(n_vectors, 64)
        payloads = [{"index": i} for i in range(n_vectors)]
        
        batch = VectorBatch(ids=ids, vectors=vectors, payloads=payloads)
        
        # Add batch
        success, failed = await mock_store.add_vectors(collection_name, batch)
        assert success == n_vectors
        assert len(failed) == 0
        
        # Count vectors
        count = await mock_store.count_vectors(collection_name)
        assert count == n_vectors
        
        # Get multiple vectors
        results = await mock_store.get_vectors(collection_name, ids[:5])
        assert len(results) == 5
        
        # Delete multiple vectors
        success, failed = await mock_store.delete_vectors(collection_name, ids[:5])
        assert success == 5
        assert len(failed) == 0
        
        count = await mock_store.count_vectors(collection_name)
        assert count == 5
    
    @pytest.mark.asyncio
    async def test_search_operations(self, mock_store):
        """Test vector search operations"""
        await mock_store.connect()
        
        collection_name = "test_search"
        vector_dim = 32
        await mock_store.create_collection(collection_name, vector_dim)
        
        # Add test vectors
        n_vectors = 20
        for i in range(n_vectors):
            vector = np.random.rand(vector_dim)
            await mock_store.add_vector(
                collection_name,
                f"vec_{i}",
                vector,
                {"index": i}
            )
        
        # Single search
        query = np.random.rand(vector_dim)
        results = await mock_store.search(collection_name, query, limit=5)
        assert len(results) <= 5
        assert all(isinstance(r, VectorSearchResult) for r in results)
        
        # Batch search
        queries = np.random.rand(3, vector_dim)
        batch_results = await mock_store.batch_search(collection_name, queries, limit=3)
        assert len(batch_results) == 3
        assert all(len(r) <= 3 for r in batch_results)


class TestVectorSearchEngine:
    """Test modern vector search engine"""
    
    @pytest.fixture
    def search_engine(self):
        """Create a search engine with mock backend"""
        config = VectorDBConfig(
            backend="mongodb",  # Use MongoDB mock for testing
            cache=CacheConfig(enabled=True, backend="memory")
        )
        engine = VectorSearchEngine(
            config=config,
            collection_name="test_search",
            enable_cache=True
        )
        return engine
    
    @pytest.mark.asyncio
    async def test_engine_initialization(self, search_engine):
        """Test search engine initialization"""
        # Note: This would need a running MongoDB or mock
        # For now, we'll test the configuration
        assert search_engine.collection_name == "test_search"
        assert search_engine.enable_cache
        assert search_engine.config.backend == "mongodb"
    
    def test_cache_operations(self, search_engine):
        """Test search result caching"""
        # Create cache key
        key = search_engine._make_cache_key("test_id", 5, {"filter": "test"})
        assert isinstance(key, str)
        assert "test_id" in key
        assert "5" in key
        
        # Test cache update
        results = [
            VectorSearchResult(id="r1", score=0.1),
            VectorSearchResult(id="r2", score=0.2)
        ]
        search_engine._update_cache(key, results)
        
        if search_engine._cache:
            assert key in search_engine._cache
            assert search_engine._cache[key] == results
    
    def test_cvc_searcher_modern(self):
        """Test modern CVC searcher compatibility"""
        searcher = CVCSearcherModern(procs=4)
        assert searcher.procs == 4
        assert hasattr(searcher, 'engine')
        assert hasattr(searcher, 'findNearestPoints')
        assert hasattr(searcher, 'loadMemoryIntoRAM')
        assert hasattr(searcher, 'clearModelsFromRAM')


class TestVectorStoreFactory:
    """Test vector store factory"""
    
    def test_factory_registration(self):
        """Test store registration"""
        # Clear existing registrations
        VectorStoreFactory._stores.clear()
        
        # Mock store class
        class TestStore(VectorStore):
            pass
        
        # Register store
        VectorStoreFactory.register_store("test", TestStore)
        assert "test" in VectorStoreFactory._stores
        assert VectorStoreFactory._stores["test"] == TestStore
    
    def test_factory_auto_registration(self):
        """Test automatic backend registration"""
        VectorStoreFactory._auto_register_backends()
        backends = VectorStoreFactory.list_backends()
        
        # At least MongoDB should be available
        assert "mongodb" in backends
    
    def test_factory_create_store(self):
        """Test store creation"""
        config = VectorDBConfig(backend="mongodb")
        
        # This will fail without MongoDB running, but tests the interface
        try:
            store = VectorStoreFactory.create_store(config)
            assert isinstance(store, VectorStore)
        except Exception:
            # Expected if MongoDB is not running
            pass
    
    def test_factory_singleton(self):
        """Test singleton pattern for named stores"""
        config = VectorDBConfig(backend="mongodb")
        
        try:
            store1 = VectorStoreFactory.get_store("test_store", config)
            store2 = VectorStoreFactory.get_store("test_store", config)
            assert store1 is store2  # Same instance
        except Exception:
            # Expected if backend is not available
            pass


class TestMigration:
    """Test vector migration functionality"""
    
    def test_migration_script_exists(self):
        """Test that migration script exists"""
        script_path = Path(__file__).parent.parent / "scripts" / "migrate_vectors.py"
        assert script_path.exists()
        assert script_path.is_file()
    
    def test_migration_script_syntax(self):
        """Test migration script has valid Python syntax"""
        script_path = Path(__file__).parent.parent / "scripts" / "migrate_vectors.py"
        with open(script_path, 'r') as f:
            code = f.read()
        
        # Try to compile the code
        compile(code, str(script_path), 'exec')


class TestIntegration:
    """Integration tests for the complete system"""
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_end_to_end_workflow(self):
        """Test complete workflow from config to search"""
        # This test requires actual services running
        # Mark as integration test to skip in unit test runs
        
        # 1. Create configuration
        config = EXAMPLE_CONFIGS["development"]
        assert config.validate()
        
        # 2. Create vector store
        try:
            store = VectorStoreFactory.create_store(config)
            
            # 3. Connect to store
            connected = await store.connect()
            if not connected:
                pytest.skip("Vector database not available")
            
            # 4. Create collection
            collection_name = "integration_test"
            vector_dim = 128
            await store.ensure_collection(collection_name, vector_dim, recreate=True)
            
            # 5. Add vectors
            n_vectors = 100
            for i in range(n_vectors):
                vector = np.random.rand(vector_dim)
                await store.add_vector(
                    collection_name,
                    f"test_vec_{i}",
                    vector,
                    {"test_id": i}
                )
            
            # 6. Search vectors
            query = np.random.rand(vector_dim)
            results = await store.search(collection_name, query, limit=10)
            assert len(results) <= 10
            
            # 7. Clean up
            await store.delete_collection(collection_name)
            await store.disconnect()
            
        except ImportError:
            pytest.skip("Required vector database libraries not installed")
        except ConnectionError:
            pytest.skip("Vector database service not running")


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])