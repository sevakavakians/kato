"""
MongoDB Vector Store Implementation (Legacy Compatibility)

This module provides a MongoDB-based implementation of the VectorStore interface,
maintaining backward compatibility with the existing KATO vector storage system.
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
try:
    import numpy as np
    HAS_NUMPY = True
except (ImportError, AttributeError):
    HAS_NUMPY = False
    class np:
        ndarray = list
        @staticmethod
        def array(x):
            return x
from pymongo import MongoClient, ASCENDING
from pymongo.errors import DuplicateKeyError, PyMongoError
import asyncio
from hashlib import sha1

from .vector_store_interface import VectorStore, VectorSearchResult, VectorBatch
from ..representations.vector_object import VectorObject

logger = logging.getLogger('kato.storage.mongodb')


class MongoDBVectorStore(VectorStore):
    """
    MongoDB vector store implementation for backward compatibility.
    
    This adapter wraps the existing MongoDB vector storage to conform
    to the new VectorStore interface, allowing gradual migration to
    more efficient vector databases.
    
    Note: MongoDB is not optimized for vector similarity search.
    Consider migrating to Qdrant or another vector database for better performance.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize MongoDB vector store"""
        super().__init__(config)
        
        # Extract MongoDB config
        self.connection_string = config.get('mongodb', {}).get(
            'connection_string', 'mongodb://localhost:27017'
        )
        self.database_name = config.get('mongodb', {}).get('database', 'kato_kb')
        self.collection_prefix = config.get('mongodb', {}).get('collection', 'vectors_kb')
        
        self.client = None
        self.db = None
        self.collections = {}
        
        logger.info(f"Initialized MongoDB vector store: {self.connection_string}")
    
    async def connect(self) -> bool:
        """Connect to MongoDB"""
        try:
            self.client = MongoClient(self.connection_string)
            self.db = self.client[self.database_name]
            
            # Test connection
            self.client.server_info()
            
            self._is_connected = True
            logger.info(f"Connected to MongoDB database: {self.database_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            self._is_connected = False
            return False
    
    async def disconnect(self) -> bool:
        """Disconnect from MongoDB"""
        try:
            if self.client:
                self.client.close()
            self._is_connected = False
            logger.info("Disconnected from MongoDB")
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
        """Create a MongoDB collection for vectors"""
        try:
            # MongoDB doesn't need explicit collection creation
            collection = self.db[self._get_collection_name(collection_name)]
            
            # Create index on vector name/ID
            collection.create_index([("name", ASCENDING)], background=True, unique=True)
            
            # Store collection metadata
            metadata_collection = self.db['_vector_metadata']
            metadata_collection.update_one(
                {"collection": collection_name},
                {
                    "$set": {
                        "collection": collection_name,
                        "vector_dim": vector_dim,
                        "created_at": asyncio.get_event_loop().time()
                    }
                },
                upsert=True
            )
            
            self.collections[collection_name] = collection
            logger.info(f"Created collection '{collection_name}' with dim={vector_dim}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create collection '{collection_name}': {e}")
            return False
    
    async def delete_collection(self, collection_name: str) -> bool:
        """Delete a MongoDB collection"""
        try:
            collection_full_name = self._get_collection_name(collection_name)
            self.db.drop_collection(collection_full_name)
            
            # Remove metadata
            metadata_collection = self.db['_vector_metadata']
            metadata_collection.delete_one({"collection": collection_name})
            
            if collection_name in self.collections:
                del self.collections[collection_name]
            
            logger.info(f"Deleted collection '{collection_name}'")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete collection '{collection_name}': {e}")
            return False
    
    async def collection_exists(self, collection_name: str) -> bool:
        """Check if a collection exists"""
        try:
            collection_full_name = self._get_collection_name(collection_name)
            return collection_full_name in self.db.list_collection_names()
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
        """Add a vector to MongoDB"""
        try:
            collection = self._get_collection(collection_name)
            
            # Create vector hash if not provided
            if not vector_id.startswith("VECTOR|"):
                vector_hash = sha1(str(vector).encode('utf-8')).hexdigest()
                vector_id = f"VECTOR|{vector_hash}"
            
            document = {
                "name": vector_id,
                "vector": vector.tolist(),
                "vector_length": float(np.linalg.norm(vector)),
                "payload": payload or {}
            }
            
            result = collection.update_one(
                {"name": vector_id},
                {"$set": document},
                upsert=True
            )
            
            return result.acknowledged
            
        except Exception as e:
            logger.error(f"Failed to add vector {vector_id}: {e}")
            return False
    
    async def add_vectors(
        self,
        collection_name: str,
        batch: VectorBatch
    ) -> Tuple[int, List[str]]:
        """Add multiple vectors to MongoDB"""
        try:
            collection = self._get_collection(collection_name)
            
            documents = []
            for i in range(batch.size):
                vector_id = batch.ids[i]
                if not vector_id.startswith("VECTOR|"):
                    vector_hash = sha1(str(batch.vectors[i]).encode('utf-8')).hexdigest()
                    vector_id = f"VECTOR|{vector_hash}"
                
                documents.append({
                    "name": vector_id,
                    "vector": batch.vectors[i].tolist(),
                    "vector_length": float(np.linalg.norm(batch.vectors[i])),
                    "payload": batch.payloads[i] if batch.payloads else {}
                })
            
            # Use bulk operations for efficiency
            operations = [
                {
                    "update_one": {
                        "filter": {"name": doc["name"]},
                        "update": {"$set": doc},
                        "upsert": True
                    }
                }
                for doc in documents
            ]
            
            result = collection.bulk_write(operations, ordered=False)
            
            successful = result.modified_count + result.upserted_count
            failed_ids = []  # MongoDB doesn't easily report which specific ones failed
            
            return successful, failed_ids
            
        except Exception as e:
            logger.error(f"Failed to add batch of {batch.size} vectors: {e}")
            return 0, batch.ids
    
    async def get_vector(
        self,
        collection_name: str,
        vector_id: str,
        include_vector: bool = True
    ) -> Optional[VectorSearchResult]:
        """Retrieve a vector from MongoDB"""
        try:
            collection = self._get_collection(collection_name)
            
            projection = {"name": 1, "payload": 1}
            if include_vector:
                projection["vector"] = 1
            
            document = collection.find_one({"name": vector_id}, projection)
            
            if not document:
                return None
            
            return VectorSearchResult(
                id=document["name"],
                score=0.0,
                vector=np.array(document["vector"]) if include_vector and "vector" in document else None,
                payload=document.get("payload", {})
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
        """Retrieve multiple vectors from MongoDB"""
        try:
            collection = self._get_collection(collection_name)
            
            projection = {"name": 1, "payload": 1}
            if include_vectors:
                projection["vector"] = 1
            
            documents = collection.find({"name": {"$in": vector_ids}}, projection)
            
            results = []
            for doc in documents:
                results.append(VectorSearchResult(
                    id=doc["name"],
                    score=0.0,
                    vector=np.array(doc["vector"]) if include_vectors and "vector" in doc else None,
                    payload=doc.get("payload", {})
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
        """Update a vector in MongoDB"""
        try:
            collection = self._get_collection(collection_name)
            
            update_doc = {}
            if vector is not None:
                update_doc["vector"] = vector.tolist()
                update_doc["vector_length"] = float(np.linalg.norm(vector))
            if payload is not None:
                update_doc["payload"] = payload
            
            if not update_doc:
                return True  # Nothing to update
            
            result = collection.update_one(
                {"name": vector_id},
                {"$set": update_doc}
            )
            
            return result.modified_count > 0
            
        except Exception as e:
            logger.error(f"Failed to update vector {vector_id}: {e}")
            return False
    
    async def delete_vector(
        self,
        collection_name: str,
        vector_id: str
    ) -> bool:
        """Delete a vector from MongoDB"""
        try:
            collection = self._get_collection(collection_name)
            result = collection.delete_one({"name": vector_id})
            return result.deleted_count > 0
            
        except Exception as e:
            logger.error(f"Failed to delete vector {vector_id}: {e}")
            return False
    
    async def delete_vectors(
        self,
        collection_name: str,
        vector_ids: List[str]
    ) -> Tuple[int, List[str]]:
        """Delete multiple vectors from MongoDB"""
        try:
            collection = self._get_collection(collection_name)
            result = collection.delete_many({"name": {"$in": vector_ids}})
            
            deleted = result.deleted_count
            # MongoDB doesn't tell us which specific ones weren't deleted
            failed = [] if deleted == len(vector_ids) else []
            
            return deleted, failed
            
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
        """
        Search for similar vectors using brute-force linear search.
        
        Note: This is inefficient for large datasets. Consider migrating to
        a proper vector database for better performance.
        """
        try:
            collection = self._get_collection(collection_name)
            
            # Build query filter
            query = {}
            if filter:
                # Add payload filters
                for key, value in filter.items():
                    query[f"payload.{key}"] = value
            
            # Fetch all matching vectors (inefficient!)
            projection = {"name": 1, "vector": 1, "payload": 1}
            documents = list(collection.find(query, projection))
            
            if not documents:
                return []
            
            # Compute distances
            distances = []
            for doc in documents:
                doc_vector = np.array(doc["vector"])
                distance = np.linalg.norm(query_vector - doc_vector)
                distances.append((distance, doc))
            
            # Sort by distance and take top k
            distances.sort(key=lambda x: x[0])
            top_k = distances[:limit]
            
            # Convert to results
            results = []
            for distance, doc in top_k:
                results.append(VectorSearchResult(
                    id=doc["name"],
                    score=float(distance),  # Lower is better for Euclidean distance
                    vector=np.array(doc["vector"]) if include_vectors else None,
                    payload=doc.get("payload", {})
                ))
            
            return results
            
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
        results = []
        for query_vector in query_vectors:
            query_results = await self.search(
                collection_name, query_vector, limit, filter, include_vectors, **kwargs
            )
            results.append(query_results)
        return results
    
    async def count_vectors(
        self,
        collection_name: str,
        filter: Optional[Dict[str, Any]] = None
    ) -> int:
        """Count vectors in a collection"""
        try:
            collection = self._get_collection(collection_name)
            
            query = {}
            if filter:
                for key, value in filter.items():
                    query[f"payload.{key}"] = value
            
            return collection.count_documents(query)
            
        except Exception as e:
            logger.error(f"Failed to count vectors: {e}")
            return 0
    
    async def get_collection_info(
        self,
        collection_name: str
    ) -> Dict[str, Any]:
        """Get information about a collection"""
        try:
            collection = self._get_collection(collection_name)
            
            # Get metadata
            metadata_collection = self.db['_vector_metadata']
            metadata = metadata_collection.find_one({"collection": collection_name})
            
            # Get stats
            stats = self.db.command("collstats", self._get_collection_name(collection_name))
            
            return {
                'name': collection_name,
                'vector_dim': metadata.get('vector_dim') if metadata else None,
                'vectors_count': stats.get('count', 0),
                'size': stats.get('size', 0),
                'storage_size': stats.get('storageSize', 0),
                'index_count': len(stats.get('indexSizes', {})),
                'indexes': list(stats.get('indexSizes', {}).keys())
            }
            
        except Exception as e:
            logger.error(f"Failed to get collection info: {e}")
            return {}
    
    async def list_collections(self) -> List[str]:
        """List all vector collections"""
        try:
            # Get from metadata collection
            metadata_collection = self.db['_vector_metadata']
            collections = metadata_collection.find({}, {"collection": 1})
            return [doc['collection'] for doc in collections]
        except Exception as e:
            logger.error(f"Failed to list collections: {e}")
            return []
    
    async def optimize_collection(
        self,
        collection_name: str,
        **kwargs
    ) -> bool:
        """Optimize a collection (reindex in MongoDB)"""
        try:
            collection = self._get_collection(collection_name)
            
            # Reindex collection
            collection.reindex()
            
            # Compact collection
            self.db.command("compact", self._get_collection_name(collection_name))
            
            logger.info(f"Optimized collection '{collection_name}'")
            return True
            
        except Exception as e:
            logger.error(f"Failed to optimize collection: {e}")
            return False
    
    async def backup_collection(
        self,
        collection_name: str,
        backup_path: str
    ) -> bool:
        """Backup a collection to a file"""
        try:
            collection = self._get_collection(collection_name)
            
            # Export collection to JSON
            import json
            documents = list(collection.find())
            
            # Convert ObjectId to string for JSON serialization
            for doc in documents:
                if '_id' in doc:
                    doc['_id'] = str(doc['_id'])
            
            with open(backup_path, 'w') as f:
                json.dump({
                    'collection': collection_name,
                    'documents': documents
                }, f)
            
            logger.info(f"Backed up collection '{collection_name}' to {backup_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to backup collection: {e}")
            return False
    
    async def restore_collection(
        self,
        collection_name: str,
        backup_path: str
    ) -> bool:
        """Restore a collection from a backup"""
        try:
            import json
            
            with open(backup_path, 'r') as f:
                data = json.load(f)
            
            if data.get('collection') != collection_name:
                logger.warning(f"Backup is for collection '{data.get('collection')}', not '{collection_name}'")
            
            collection = self._get_collection(collection_name)
            
            # Clear existing data
            collection.delete_many({})
            
            # Insert backup data
            documents = data.get('documents', [])
            if documents:
                # Remove _id field to let MongoDB generate new ones
                for doc in documents:
                    if '_id' in doc:
                        del doc['_id']
                
                collection.insert_many(documents)
            
            logger.info(f"Restored collection '{collection_name}' from {backup_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to restore collection: {e}")
            return False
    
    # Helper methods
    def _get_collection_name(self, collection_name: str) -> str:
        """Get full MongoDB collection name"""
        return f"{self.collection_prefix}_{collection_name}"
    
    def _get_collection(self, collection_name: str):
        """Get MongoDB collection object"""
        if collection_name not in self.collections:
            self.collections[collection_name] = self.db[self._get_collection_name(collection_name)]
        return self.collections[collection_name]