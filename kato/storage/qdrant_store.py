"""
Qdrant Vector Store Implementation

This module provides a Qdrant-based implementation of the VectorStore interface.
Qdrant is a high-performance vector database written in Rust with excellent
support for filtering, GPU acceleration, and various quantization methods.
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
import numpy as np
from uuid import uuid4
import asyncio

try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import (
        Distance, VectorParams, PointStruct, Filter, FieldCondition,
        SearchRequest, ScoredPoint, UpdateStatus, CollectionInfo,
        OptimizersConfig, OptimizersConfigDiff, HnswConfig, HnswConfigDiff,
        QuantizationConfig,
        ScalarQuantization, ProductQuantization, BinaryQuantization,
        ScalarQuantizationConfig, ProductQuantizationConfig,
        BinaryQuantizationConfig, ScalarType, CompressionRatio
    )
    from qdrant_client.http.exceptions import UnexpectedResponse
    QDRANT_AVAILABLE = True
except ImportError:
    QDRANT_AVAILABLE = False
    logging.warning("Qdrant client not installed. Install with: pip install qdrant-client")

from .vector_store_interface import VectorStore, VectorSearchResult, VectorBatch
from ..config.vectordb_config import QdrantConfig, QuantizationConfig as KatoQuantConfig

logger = logging.getLogger('kato.storage.qdrant')


class QdrantStore(VectorStore):
    """
    Qdrant vector store implementation.
    
    Features:
    - High-performance vector similarity search
    - Rich filtering capabilities
    - Multiple quantization options
    - GPU acceleration support (with appropriate Docker image)
    - Automatic index optimization
    """
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize Qdrant store with configuration"""
        super().__init__(config)
        
        if not QDRANT_AVAILABLE:
            raise ImportError("Qdrant client not available. Install with: pip install qdrant-client")
        
        # Extract Qdrant-specific config
        if isinstance(config.get('qdrant'), QdrantConfig):
            self.qdrant_config = config['qdrant']
        else:
            self.qdrant_config = QdrantConfig(**config.get('qdrant', {}))
        
        # Extract quantization config
        if isinstance(config.get('quantization'), KatoQuantConfig):
            self.quant_config = config['quantization']
        else:
            self.quant_config = KatoQuantConfig(**config.get('quantization', {}))
        
        # Initialize client
        self.client = QdrantClient(
            host=self.qdrant_config.host,
            port=self.qdrant_config.port,
            timeout=config.get('search_timeout', 10.0)
        )
        
        # Distance metric mapping
        self.distance_map = {
            'euclidean': Distance.EUCLID,
            'cosine': Distance.COSINE,
            'dot': Distance.DOT,
            'manhattan': Distance.MANHATTAN
        }
        
        logger.info(f"Initialized Qdrant store: {self.qdrant_config.get_url()}")
    
    async def connect(self) -> bool:
        """Establish connection to Qdrant"""
        try:
            # Test connection by getting collections
            collections = await self._async_wrapper(self.client.get_collections)
            self._is_connected = True
            logger.info(f"Connected to Qdrant with {len(collections.collections)} collections")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Qdrant: {e}")
            self._is_connected = False
            return False
    
    async def disconnect(self) -> bool:
        """Close connection to Qdrant"""
        try:
            # Qdrant client doesn't have explicit disconnect
            self._is_connected = False
            logger.info("Disconnected from Qdrant")
            return True
        except Exception as e:
            logger.error(f"Error during disconnect: {e}")
            return False
    
    async def create_collection(
        self,
        collection_name: str,
        vector_dim: int,
        **kwargs
    ) -> bool:
        """Create a new Qdrant collection"""
        try:
            # Get distance metric
            distance = self.distance_map.get(
                kwargs.get('distance', self.qdrant_config.distance),
                Distance.EUCLID
            )
            
            # Configure HNSW index
            hnsw_config = HnswConfigDiff(
                m=kwargs.get('hnsw_m', 16),
                ef_construct=kwargs.get('hnsw_ef_construct', 128),
                full_scan_threshold=kwargs.get('full_scan_threshold', 10000)
            )
            
            # Configure optimizers
            optimizers_config = OptimizersConfigDiff(
                deleted_threshold=self.qdrant_config.optimizers.get('deleted_threshold', 0.2),
                vacuum_min_vector_number=self.qdrant_config.optimizers.get('vacuum_min_vector_number', 1000),
                default_segment_number=self.qdrant_config.optimizers.get('default_segment_number', 4),
                max_segment_size=self.qdrant_config.optimizers.get('max_segment_size', 500000),
                memmap_threshold=self.qdrant_config.optimizers.get('memmap_threshold', 20000),
                indexing_threshold=self.qdrant_config.optimizers.get('indexing_threshold', 10000),
                flush_interval_sec=self.qdrant_config.optimizers.get('flush_interval_sec', 5),
            )
            
            # Configure quantization if enabled
            quantization_config = None
            if self.quant_config.enabled:
                if self.quant_config.type == "scalar":
                    quantization_config = ScalarQuantization(
                        scalar=ScalarQuantizationConfig(
                            type=ScalarType.INT8,
                            quantile=self.quant_config.parameters.get('quantile', 0.99),
                            always_ram=self.quant_config.parameters.get('always_ram', False)
                        )
                    )
                elif self.quant_config.type == "product":
                    compression = self.quant_config.parameters.get('compression', 'x16')
                    compression_ratio = {
                        'x4': CompressionRatio.X4,
                        'x8': CompressionRatio.X8,
                        'x16': CompressionRatio.X16,
                        'x32': CompressionRatio.X32,
                        'x64': CompressionRatio.X64
                    }.get(compression, CompressionRatio.X16)
                    
                    quantization_config = ProductQuantization(
                        product=ProductQuantizationConfig(
                            compression=compression_ratio,
                            always_ram=self.quant_config.parameters.get('always_ram', False)
                        )
                    )
                elif self.quant_config.type == "binary":
                    quantization_config = BinaryQuantization(
                        binary=BinaryQuantizationConfig(
                            always_ram=self.quant_config.parameters.get('always_ram', True)
                        )
                    )
            
            # Create collection
            success = await self._async_wrapper(
                self.client.create_collection,
                collection_name=collection_name,
                vectors_config=VectorParams(
                    size=vector_dim,
                    distance=distance
                ),
                hnsw_config=hnsw_config,
                optimizers_config=optimizers_config,
                quantization_config=quantization_config,
                on_disk_payload=self.qdrant_config.on_disk_payload
            )
            
            if success:
                logger.info(f"Created collection '{collection_name}' with dim={vector_dim}, distance={distance}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to create collection '{collection_name}': {e}")
            return False
    
    async def delete_collection(self, collection_name: str) -> bool:
        """Delete a Qdrant collection"""
        try:
            success = await self._async_wrapper(
                self.client.delete_collection,
                collection_name=collection_name
            )
            logger.info(f"Deleted collection '{collection_name}'")
            return True
        except Exception as e:
            logger.error(f"Failed to delete collection '{collection_name}': {e}")
            return False
    
    async def collection_exists(self, collection_name: str) -> bool:
        """Check if a collection exists"""
        try:
            collections = await self._async_wrapper(self.client.get_collections)
            return any(c.name == collection_name for c in collections.collections)
        except Exception as e:
            logger.error(f"Failed to check collection existence: {e}")
            return False
    
    async def add_vector(
        self,
        collection_name: str,
        vector_id: str,
        vector: np.ndarray,
        payload: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Add a single vector to Qdrant"""
        try:
            point = PointStruct(
                id=vector_id,
                vector=vector.tolist(),
                payload=payload or {}
            )
            
            result = await self._async_wrapper(
                self.client.upsert,
                collection_name=collection_name,
                points=[point]
            )
            
            return result.status == UpdateStatus.COMPLETED
            
        except Exception as e:
            logger.error(f"Failed to add vector {vector_id}: {e}")
            return False
    
    async def add_vectors(
        self,
        collection_name: str,
        batch: VectorBatch
    ) -> Tuple[int, List[str]]:
        """Add multiple vectors in batch"""
        try:
            points = []
            for i in range(batch.size):
                payload = batch.payloads[i] if batch.payloads else {}
                points.append(PointStruct(
                    id=batch.ids[i],
                    vector=batch.vectors[i].tolist(),
                    payload=payload
                ))
            
            # Qdrant handles batching internally
            result = await self._async_wrapper(
                self.client.upsert,
                collection_name=collection_name,
                points=points,
                wait=True
            )
            
            if result.status == UpdateStatus.COMPLETED:
                return batch.size, []
            else:
                # Partial failure - need to check which ones failed
                return 0, batch.ids  # Conservative: assume all failed
                
        except Exception as e:
            logger.error(f"Failed to add batch of {batch.size} vectors: {e}")
            return 0, batch.ids
    
    async def get_vector(
        self,
        collection_name: str,
        vector_id: str,
        include_vector: bool = True
    ) -> Optional[VectorSearchResult]:
        """Retrieve a vector by ID"""
        try:
            points = await self._async_wrapper(
                self.client.retrieve,
                collection_name=collection_name,
                ids=[vector_id],
                with_vectors=include_vector,
                with_payload=True
            )
            
            if not points:
                return None
            
            point = points[0]
            return VectorSearchResult(
                id=str(point.id),
                score=0.0,  # No score for direct retrieval
                vector=np.array(point.vector) if include_vector and point.vector else None,
                payload=point.payload
            )
            
        except Exception as e:
            logger.error(f"Failed to get vector {vector_id}: {e}")
            return None
    
    async def get_vectors(
        self,
        collection_name: str,
        vector_ids: List[str],
        include_vectors: bool = True
    ) -> List[VectorSearchResult]:
        """Retrieve multiple vectors by IDs"""
        try:
            points = await self._async_wrapper(
                self.client.retrieve,
                collection_name=collection_name,
                ids=vector_ids,
                with_vectors=include_vectors,
                with_payload=True
            )
            
            results = []
            for point in points:
                results.append(VectorSearchResult(
                    id=str(point.id),
                    score=0.0,
                    vector=np.array(point.vector) if include_vectors and point.vector else None,
                    payload=point.payload
                ))
            
            return results
            
        except Exception as e:
            logger.error(f"Failed to get vectors: {e}")
            return []
    
    async def update_vector(
        self,
        collection_name: str,
        vector_id: str,
        vector: Optional[np.ndarray] = None,
        payload: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Update a vector and/or its payload"""
        try:
            if vector is not None:
                # Update vector
                point = PointStruct(
                    id=vector_id,
                    vector=vector.tolist(),
                    payload=payload if payload is not None else {}
                )
                result = await self._async_wrapper(
                    self.client.upsert,
                    collection_name=collection_name,
                    points=[point]
                )
                return result.status == UpdateStatus.COMPLETED
                
            elif payload is not None:
                # Update only payload
                result = await self._async_wrapper(
                    self.client.set_payload,
                    collection_name=collection_name,
                    payload=payload,
                    points=[vector_id]
                )
                return result.status == UpdateStatus.COMPLETED
                
            return True  # Nothing to update
            
        except Exception as e:
            logger.error(f"Failed to update vector {vector_id}: {e}")
            return False
    
    async def delete_vector(
        self,
        collection_name: str,
        vector_id: str
    ) -> bool:
        """Delete a vector from Qdrant"""
        try:
            result = await self._async_wrapper(
                self.client.delete,
                collection_name=collection_name,
                points_selector=[vector_id]
            )
            return result.status == UpdateStatus.COMPLETED
            
        except Exception as e:
            logger.error(f"Failed to delete vector {vector_id}: {e}")
            return False
    
    async def delete_vectors(
        self,
        collection_name: str,
        vector_ids: List[str]
    ) -> Tuple[int, List[str]]:
        """Delete multiple vectors"""
        try:
            result = await self._async_wrapper(
                self.client.delete,
                collection_name=collection_name,
                points_selector=vector_ids
            )
            
            if result.status == UpdateStatus.COMPLETED:
                return len(vector_ids), []
            else:
                return 0, vector_ids  # Conservative: assume all failed
                
        except Exception as e:
            logger.error(f"Failed to delete {len(vector_ids)} vectors: {e}")
            return 0, vector_ids
    
    async def search(
        self,
        collection_name: str,
        query_vector: np.ndarray,
        limit: int = 10,
        filter: Optional[Dict[str, Any]] = None,
        include_vectors: bool = False,
        **kwargs
    ) -> List[VectorSearchResult]:
        """Search for similar vectors"""
        try:
            # Build Qdrant filter from dict
            qdrant_filter = None
            if filter:
                # Simple filter conversion - extend as needed
                conditions = []
                for key, value in filter.items():
                    conditions.append(FieldCondition(
                        key=key,
                        match={"value": value}
                    ))
                if conditions:
                    qdrant_filter = Filter(must=conditions)
            
            # Perform search
            results = await self._async_wrapper(
                self.client.search,
                collection_name=collection_name,
                query_vector=query_vector.tolist(),
                limit=limit,
                query_filter=qdrant_filter,
                with_vectors=include_vectors,
                with_payload=True,
                score_threshold=kwargs.get('score_threshold')
            )
            
            # Convert to our format
            search_results = []
            for point in results:
                search_results.append(VectorSearchResult(
                    id=str(point.id),
                    score=point.score,
                    vector=np.array(point.vector) if include_vectors and point.vector else None,
                    payload=point.payload
                ))
            
            return search_results
            
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []
    
    async def batch_search(
        self,
        collection_name: str,
        query_vectors: np.ndarray,
        limit: int = 10,
        filter: Optional[Dict[str, Any]] = None,
        include_vectors: bool = False,
        **kwargs
    ) -> List[List[VectorSearchResult]]:
        """Batch search for multiple query vectors"""
        try:
            # Build search requests
            requests = []
            qdrant_filter = None
            
            if filter:
                conditions = []
                for key, value in filter.items():
                    conditions.append(FieldCondition(
                        key=key,
                        match={"value": value}
                    ))
                if conditions:
                    qdrant_filter = Filter(must=conditions)
            
            for query_vector in query_vectors:
                requests.append(SearchRequest(
                    vector=query_vector.tolist(),
                    limit=limit,
                    filter=qdrant_filter,
                    with_vector=include_vectors,
                    with_payload=True,
                    score_threshold=kwargs.get('score_threshold')
                ))
            
            # Perform batch search
            batch_results = await self._async_wrapper(
                self.client.search_batch,
                collection_name=collection_name,
                requests=requests
            )
            
            # Convert results
            all_results = []
            for results in batch_results:
                query_results = []
                for point in results:
                    query_results.append(VectorSearchResult(
                        id=str(point.id),
                        score=point.score,
                        vector=np.array(point.vector) if include_vectors and point.vector else None,
                        payload=point.payload
                    ))
                all_results.append(query_results)
            
            return all_results
            
        except Exception as e:
            logger.error(f"Batch search failed: {e}")
            return [[] for _ in range(len(query_vectors))]
    
    async def count_vectors(
        self,
        collection_name: str,
        filter: Optional[Dict[str, Any]] = None
    ) -> int:
        """Count vectors in a collection"""
        try:
            if filter:
                # Count with filter using scroll
                conditions = []
                for key, value in filter.items():
                    conditions.append(FieldCondition(
                        key=key,
                        match={"value": value}
                    ))
                qdrant_filter = Filter(must=conditions) if conditions else None
                
                # Use scroll to count filtered results
                count = 0
                offset = None
                while True:
                    records, offset = await self._async_wrapper(
                        self.client.scroll,
                        collection_name=collection_name,
                        scroll_filter=qdrant_filter,
                        limit=1000,
                        offset=offset,
                        with_vectors=False,
                        with_payload=False
                    )
                    count += len(records)
                    if offset is None:
                        break
                
                return count
            else:
                # Get collection info for total count
                info = await self._async_wrapper(
                    self.client.get_collection,
                    collection_name=collection_name
                )
                return info.vectors_count
                
        except Exception as e:
            logger.error(f"Failed to count vectors: {e}")
            return 0
    
    async def get_collection_info(
        self,
        collection_name: str
    ) -> Dict[str, Any]:
        """Get information about a collection"""
        try:
            info = await self._async_wrapper(
                self.client.get_collection,
                collection_name=collection_name
            )
            
            return {
                'name': collection_name,
                'vector_dim': info.config.params.vectors.size,
                'distance': str(info.config.params.vectors.distance),
                'vectors_count': info.vectors_count,
                'indexed_vectors_count': info.indexed_vectors_count,
                'points_count': info.points_count,
                'segments_count': info.segments_count,
                'status': info.status,
                'optimizer_status': info.optimizer_status,
                'config': info.config.dict() if hasattr(info.config, 'dict') else str(info.config)
            }
            
        except Exception as e:
            logger.error(f"Failed to get collection info: {e}")
            return {}
    
    async def list_collections(self) -> List[str]:
        """List all collections"""
        try:
            collections = await self._async_wrapper(self.client.get_collections)
            return [c.name for c in collections.collections]
        except Exception as e:
            logger.error(f"Failed to list collections: {e}")
            return []
    
    async def optimize_collection(
        self,
        collection_name: str,
        **kwargs
    ) -> bool:
        """Optimize a collection for better performance"""
        try:
            # Update collection parameters if provided
            if kwargs:
                await self._async_wrapper(
                    self.client.update_collection,
                    collection_name=collection_name,
                    optimizer_config=OptimizersConfigDiff(**kwargs)
                )
            
            # Trigger optimization
            # Note: Qdrant optimizes automatically, but we can force it
            info = await self._async_wrapper(
                self.client.get_collection,
                collection_name=collection_name
            )
            
            logger.info(f"Collection '{collection_name}' optimization status: {info.optimizer_status}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to optimize collection: {e}")
            return False
    
    async def backup_collection(
        self,
        collection_name: str,
        backup_path: str
    ) -> bool:
        """Backup a collection (create snapshot)"""
        try:
            # Create snapshot
            snapshot_info = await self._async_wrapper(
                self.client.create_snapshot,
                collection_name=collection_name
            )
            
            # Download snapshot to file
            # Note: This is a simplified version. In production, you'd want to
            # actually download the snapshot file from Qdrant's storage
            
            logger.info(f"Created snapshot for '{collection_name}': {snapshot_info}")
            
            # For now, just save the snapshot info
            import json
            with open(backup_path, 'w') as f:
                json.dump({
                    'collection': collection_name,
                    'snapshot': snapshot_info.name if hasattr(snapshot_info, 'name') else str(snapshot_info),
                    'timestamp': str(snapshot_info)
                }, f)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to backup collection: {e}")
            return False
    
    async def restore_collection(
        self,
        collection_name: str,
        backup_path: str
    ) -> bool:
        """Restore a collection from backup"""
        try:
            # This would need to be implemented based on your backup strategy
            # For now, this is a placeholder
            logger.warning("Collection restore not fully implemented for Qdrant")
            return False
            
        except Exception as e:
            logger.error(f"Failed to restore collection: {e}")
            return False
    
    # Helper methods
    async def _async_wrapper(self, func, *args, **kwargs):
        """Wrap synchronous Qdrant client calls for async compatibility"""
        import functools
        loop = asyncio.get_event_loop()
        # run_in_executor doesn't support kwargs, so we use partial
        if kwargs:
            func = functools.partial(func, **kwargs)
        return await loop.run_in_executor(None, func, *args)