"""
Test connection pool functionality for KATO v2.0
Tests MongoDB and Qdrant connection pooling improvements
"""

import pytest
import time
from unittest.mock import Mock, patch
from kato.v2.resilience.connection_pool import (
    PoolConfig, MongoConnectionPool, QdrantConnectionPool,
    get_mongo_pool, get_qdrant_pool, cleanup_connection_pools
)


class TestMongoConnectionPool:
    """Test MongoDB connection pool functionality"""
    
    def test_pool_config_creation(self):
        """Test creating pool configuration"""
        config = PoolConfig(
            mongo_url="mongodb://test:27017",
            mongo_max_pool_size=100,
            qdrant_host="test_host"
        )
        
        assert config.mongo_url == "mongodb://test:27017"
        assert config.mongo_max_pool_size == 100
        assert config.qdrant_host == "test_host"
        # Check defaults
        assert config.mongo_min_pool_size == 10
        assert config.qdrant_port == 6333
    
    @patch('kato.v2.resilience.connection_pool.MongoClient')
    def test_mongo_pool_initialization(self, mock_mongo_client):
        """Test MongoDB pool initialization"""
        # Mock successful connection
        mock_client = Mock()
        mock_mongo_client.return_value = mock_client
        
        config = PoolConfig(mongo_url="mongodb://test:27017")
        pool = MongoConnectionPool(config)
        
        # Verify client was created with correct parameters
        mock_mongo_client.assert_called_once()
        call_kwargs = mock_mongo_client.call_args[1]
        
        # Check critical parameters
        assert call_kwargs['maxPoolSize'] == config.mongo_max_pool_size
        assert call_kwargs['minPoolSize'] == config.mongo_min_pool_size
        assert call_kwargs['w'] == 'majority'  # Critical: write concern
        assert call_kwargs['journal'] is True
        assert call_kwargs['retryWrites'] is True
        assert call_kwargs['appname'] == 'kato-v2'
    
    @patch('kato.v2.resilience.connection_pool.MongoClient')
    def test_mongo_pool_get_database(self, mock_mongo_client):
        """Test getting database from pool"""
        mock_client = Mock()
        mock_db = Mock()
        mock_client.__getitem__ = Mock(return_value=mock_db)
        mock_mongo_client.return_value = mock_client
        
        pool = MongoConnectionPool(PoolConfig())
        
        # Get database
        db = pool.get_database("test_db", ensure_healthy=False)
        
        # Should return database from client
        assert db == mock_db
        mock_client.__getitem__.assert_called_with("test_db")
    
    @patch('kato.v2.resilience.connection_pool.MongoClient')
    def test_mongo_pool_health_check(self, mock_mongo_client):
        """Test MongoDB health check functionality"""
        mock_client = Mock()
        mock_mongo_client.return_value = mock_client
        
        pool = MongoConnectionPool(PoolConfig())
        
        # Mock ping command success
        mock_client.admin.command.return_value = {"ok": 1}
        
        # Health check should succeed
        pool._ensure_healthy()
        
        # Should have called ping
        mock_client.admin.command.assert_called_with('ping')
        assert pool.connection_failures == 0
    
    @patch('kato.v2.resilience.connection_pool.MongoClient')
    def test_mongo_pool_write_concerns(self, mock_mongo_client):
        """Test write concern levels"""
        mock_client = Mock()
        mock_mongo_client.return_value = mock_client
        
        pool = MongoConnectionPool(PoolConfig())
        
        # Test different write concern levels
        majority_wc = pool.get_write_concern("majority")
        assert majority_wc.document["w"] == "majority"
        assert majority_wc.document["j"] is True
        
        acknowledged_wc = pool.get_write_concern("acknowledged")
        assert acknowledged_wc.document["w"] == 1
        assert acknowledged_wc.document["j"] is True
        
        unack_wc = pool.get_write_concern("unacknowledged")
        assert unack_wc.document["w"] == 0
    
    @patch('kato.v2.resilience.connection_pool.MongoClient')
    def test_mongo_pool_stats(self, mock_mongo_client):
        """Test getting pool statistics"""
        mock_client = Mock()
        mock_client.server_info.return_value = {"version": "6.0.0"}
        mock_mongo_client.return_value = mock_client
        
        pool = MongoConnectionPool(PoolConfig())
        
        stats = pool.get_pool_stats()
        
        assert stats["status"] == "connected"
        assert "version" in stats
        assert "connections" in stats
        assert "failures" in stats


@pytest.mark.asyncio
class TestQdrantConnectionPool:
    """Test Qdrant connection pool functionality"""
    
    async def test_qdrant_pool_config(self):
        """Test Qdrant pool configuration"""
        config = PoolConfig(
            qdrant_host="test_host",
            qdrant_port=6334,
            qdrant_pool_size=10
        )
        
        pool = QdrantConnectionPool(config)
        
        assert pool.config.qdrant_host == "test_host"
        assert pool.config.qdrant_port == 6334
        assert pool.config.qdrant_pool_size == 10
    
    @patch('qdrant_client.QdrantClient')
    async def test_qdrant_pool_initialization(self, mock_qdrant_client):
        """Test Qdrant pool initialization"""
        # Mock client creation
        mock_clients = [Mock() for _ in range(5)]
        mock_qdrant_client.side_effect = mock_clients
        
        config = PoolConfig(qdrant_pool_size=5)
        pool = QdrantConnectionPool(config)
        
        await pool.initialize()
        
        # Should have created 5 clients
        assert mock_qdrant_client.call_count == 5
        assert len(pool.clients) == 5
        assert pool._initialized is True
    
    @patch('qdrant_client.QdrantClient')
    async def test_qdrant_pool_get_client(self, mock_qdrant_client):
        """Test getting client from Qdrant pool"""
        mock_client = Mock()
        mock_client.get_cluster_info.return_value = {"status": "ok"}
        mock_qdrant_client.return_value = mock_client
        
        config = PoolConfig(qdrant_pool_size=2)
        pool = QdrantConnectionPool(config)
        
        await pool.initialize()
        
        # Get client
        client = await pool.get_client()
        
        # Should return a client and perform health check
        assert client == mock_client
        mock_client.get_cluster_info.assert_called_once()
    
    @patch('qdrant_client.QdrantClient')
    async def test_qdrant_pool_health_check_failure(self, mock_qdrant_client):
        """Test Qdrant health check failure and recovery"""
        # First client fails health check, second succeeds
        failing_client = Mock()
        failing_client.get_cluster_info.side_effect = Exception("Connection failed")
        
        healthy_client = Mock()
        healthy_client.get_cluster_info.return_value = {"status": "ok"}
        
        # Return failing client first, then healthy for recreation
        mock_qdrant_client.side_effect = [failing_client, healthy_client]
        
        config = PoolConfig(qdrant_pool_size=1)
        pool = QdrantConnectionPool(config)
        
        await pool.initialize()
        
        # Try to get client - should recreate the failed one
        client = await pool.get_client()
        
        # Should have called health check on both clients
        failing_client.get_cluster_info.assert_called()
        healthy_client.get_cluster_info.assert_called()
        
        # Should return the healthy client
        assert client == healthy_client
    
    @patch('qdrant_client.QdrantClient')
    async def test_qdrant_pool_stats(self, mock_qdrant_client):
        """Test Qdrant pool statistics"""
        mock_clients = [Mock() for _ in range(3)]
        mock_qdrant_client.side_effect = mock_clients
        
        config = PoolConfig(qdrant_pool_size=3)
        pool = QdrantConnectionPool(config)
        
        # Before initialization
        stats = pool.get_pool_stats()
        assert stats["status"] == "not_initialized"
        
        # After initialization
        await pool.initialize()
        stats = pool.get_pool_stats()
        
        assert stats["status"] == "initialized"
        assert stats["pool_size"] == 3
        assert stats["total_connections"] == 3
        assert stats["available_connections"] == 3
        assert stats["in_use_connections"] == 0
        assert stats["host"] == config.qdrant_host
        assert stats["port"] == config.qdrant_port


class TestGlobalPoolManagement:
    """Test global pool management functions"""
    
    def setup_method(self):
        """Clean up before each test"""
        cleanup_connection_pools()
    
    def teardown_method(self):
        """Clean up after each test"""  
        cleanup_connection_pools()
    
    @patch('kato.v2.resilience.connection_pool.MongoClient')
    def test_get_mongo_pool_singleton(self, mock_mongo_client):
        """Test that get_mongo_pool returns same instance"""
        mock_client = Mock()
        mock_mongo_client.return_value = mock_client
        
        # First call creates pool
        pool1 = get_mongo_pool()
        
        # Second call returns same pool
        pool2 = get_mongo_pool()
        
        assert pool1 is pool2
    
    @pytest.mark.asyncio
    @patch('qdrant_client.QdrantClient')
    async def test_get_qdrant_pool_singleton(self, mock_qdrant_client):
        """Test that get_qdrant_pool returns same instance"""
        mock_client = Mock()
        mock_client.get_cluster_info.return_value = {"status": "ok"}
        mock_qdrant_client.return_value = mock_client
        
        # First call creates pool
        pool1 = await get_qdrant_pool()
        
        # Second call returns same pool
        pool2 = await get_qdrant_pool()
        
        assert pool1 is pool2
    
    @patch('kato.v2.resilience.connection_pool.MongoClient')
    def test_cleanup_pools(self, mock_mongo_client):
        """Test cleaning up connection pools"""
        mock_client = Mock()
        mock_mongo_client.return_value = mock_client
        
        # Create pool
        pool = get_mongo_pool()
        assert pool is not None
        
        # Clean up
        cleanup_connection_pools()
        
        # Should create new pool on next call
        new_pool = get_mongo_pool()
        assert new_pool is not pool


if __name__ == "__main__":
    pytest.main([__file__, "-v"])