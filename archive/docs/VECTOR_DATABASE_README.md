# KATO Vector Database Modernization

## Overview

The KATO system has been enhanced with a modern vector database infrastructure that replaces the legacy MongoDB-based vector storage with high-performance alternatives. The new system supports multiple vector database backends, GPU acceleration, quantization, and advanced search capabilities.

## Key Features

- **Multiple Backend Support**: Qdrant (recommended), MongoDB (legacy), with extensibility for Milvus, Weaviate, and FAISS
- **High Performance**: Sub-millisecond search times with proper indexing
- **GPU Acceleration**: Optional GPU support for 10-100x speedup
- **Quantization**: Scalar, product, and binary quantization for memory efficiency
- **Caching Layer**: Redis-based caching for frequently accessed vectors
- **Migration Tools**: Automated migration from MongoDB to modern vector databases
- **Docker Integration**: Fully containerized with Docker Compose support

## Architecture

```
┌─────────────────────────────┐
│      KATO Application       │
└──────────┬──────────────────┘
           │
┌──────────▼──────────────────┐
│   Vector Search Engine      │
├─────────────────────────────┤
│  - Caching Layer           │
│  - Batch Operations        │
│  - Async Support           │
└──────────┬──────────────────┘
           │
┌──────────▼──────────────────┐
│  Vector Store Interface     │
├─────────────────────────────┤
│  Abstract base class for    │
│  all vector backends        │
└──────────┬──────────────────┘
           │
     ┌─────┴─────┬──────┬──────┐
     │           │      │      │
┌────▼────┐ ┌───▼───┐ ┌▼──┐ ┌─▼────┐
│ Qdrant  │ │MongoDB│ │... │ │Future│
└─────────┘ └───────┘ └───┘ └──────┘
```

## Quick Start

### 1. Automatic Vector Database Startup

By default, the vector database starts automatically when you start KATO:

```bash
# Start KATO with vector database (default behavior)
./kato-manager.sh start

# Start KATO WITHOUT vector database
./kato-manager.sh start --no-vectordb

# Start with specific vector database backend
./kato-manager.sh start --vectordb-backend qdrant
```

### 2. Manual Vector Database Management

You can also manage the vector database separately:

```bash
# Start vector database services manually
./kato-manager.sh vectordb start

# Check status
./kato-manager.sh vectordb status

# Stop vector database
./kato-manager.sh vectordb stop
```

### 3. Migrate Existing Vectors

```bash
# Migrate all vectors from MongoDB to Qdrant
./kato-manager.sh vectordb migrate

# Migrate with custom options
./kato-manager.sh vectordb migrate --batch-size 5000 --preset production
```

### 4. Use in KATO

The system automatically uses the configured vector database. No code changes required for existing KATO functionality.

**Default Behavior:**
- Vector database (Qdrant) starts automatically with KATO
- Redis cache also starts for improved performance
- If vector DB fails to start, KATO falls back to MongoDB vector storage
- Use `--no-vectordb` flag to disable vector database entirely

## Configuration

### Environment Variables

```bash
# Vector database backend selection
export KATO_VECTOR_DB_BACKEND=qdrant  # or mongodb, milvus, weaviate

# Qdrant configuration
export QDRANT_HOST=localhost
export QDRANT_PORT=6333
export QDRANT_COLLECTION=kato_vectors

# GPU acceleration (requires GPU-enabled Docker image)
export KATO_GPU_ENABLED=true
export KATO_GPU_DEVICES=0,1

# Quantization
export KATO_QUANTIZATION_ENABLED=true
export KATO_QUANTIZATION_TYPE=scalar  # or product, binary

# Cache configuration
export KATO_CACHE_ENABLED=true
export REDIS_HOST=localhost
export REDIS_PORT=6379
```

### Configuration Files

Example configurations are provided in `config/vectordb_examples/`:

- `development.json` - Optimized for development (no cache, no quantization)
- `production.json` - Production settings with caching and scalar quantization
- `gpu_optimized.json` - GPU acceleration with advanced indexing
- `memory_optimized.json` - Binary quantization for minimal memory usage
- `legacy_mongodb.json` - MongoDB compatibility mode

### Using a Configuration File

```python
from kato.config.vectordb_config import VectorDBConfig

# Load from file
config = VectorDBConfig.from_file("config/vectordb_examples/production.json")

# Or use preset
from kato.config.vectordb_config import EXAMPLE_CONFIGS
config = EXAMPLE_CONFIGS["production"]
```

## Vector Database Management

### Command Line Interface

```bash
# Start services
./kato-manager.sh vectordb start

# Stop services
./kato-manager.sh vectordb stop

# Check status
./kato-manager.sh vectordb status

# Migrate vectors
./kato-manager.sh vectordb migrate [options]

# Backup vectors
./kato-manager.sh vectordb backup [directory]

# View logs
./kato-manager.sh vectordb logs [qdrant|redis|all]

# Show configuration
./kato-manager.sh vectordb config

# Test connections
./kato-manager.sh vectordb test
```

### Python API

```python
from kato.searches.vector_search_engine import VectorSearchEngine
import numpy as np

# Initialize search engine
engine = VectorSearchEngine(
    collection_name="my_vectors",
    enable_cache=True
)

# Initialize (connect to backend)
engine.initialize_sync()

# Add vectors
vector = np.random.rand(512)  # 512-dimensional vector
engine.add_vector_sync(vector, vector_id="vec_001", metadata={"type": "test"})

# Search for similar vectors
query = np.random.rand(512)
results = engine.search_sync(query, k=5)

for result in results:
    print(f"ID: {result.id}, Score: {result.score}")

# Get statistics
stats = engine.get_stats_sync()
print(f"Total vectors: {stats['total_vectors']}")
print(f"Cache hit rate: {stats['cache_hit_rate']:.2%}")
```

## Performance Comparison

| Operation | MongoDB (Legacy) | Qdrant | Qdrant + GPU |
|-----------|-----------------|--------|--------------|
| Add 1K vectors | 5-10s | 0.5-1s | 0.1-0.3s |
| Search (100K vectors) | 100-500ms | 1-5ms | <1ms |
| Search (1M vectors) | 1-5s | 5-20ms | 1-5ms |
| Memory per 1M vectors | 4GB | 1GB (with quantization) | 1GB |

## Migration Guide

### Migrating from MongoDB to Qdrant

1. **Ensure both services are running:**
```bash
./kato-manager.sh start  # Start KATO with MongoDB
./kato-manager.sh vectordb start  # Start Qdrant
```

2. **Run migration:**
```bash
./scripts/migrate_vectors.py \
    --source-host localhost \
    --source-port 27017 \
    --target-backend qdrant \
    --target-host localhost \
    --target-port 6333 \
    --batch-size 1000
```

3. **Verify migration:**
```bash
./kato-manager.sh vectordb status
```

4. **Update KATO configuration** to use Qdrant:
```bash
export KATO_VECTOR_DB_BACKEND=qdrant
```

### Gradual Migration

The system supports running both MongoDB and Qdrant simultaneously:

```python
from kato.storage import get_vector_store

# Use MongoDB for legacy operations
legacy_store = get_vector_store(backend="mongodb")

# Use Qdrant for new operations
modern_store = get_vector_store(backend="qdrant")
```

## GPU Acceleration

### Requirements

- NVIDIA GPU with CUDA support
- Docker with GPU support (nvidia-docker)
- Qdrant GPU Docker image

### Setup

1. **Use GPU-enabled Docker Compose:**
```yaml
# Uncomment the qdrant-gpu service in docker-compose.vectordb.yml
qdrant-gpu:
  image: qdrant/qdrant:gpu-nvidia-latest
  runtime: nvidia
  environment:
    - NVIDIA_VISIBLE_DEVICES=all
    - QDRANT__GPU__INDEXING=true
```

2. **Enable GPU in configuration:**
```json
{
  "gpu": {
    "enabled": true,
    "device_ids": [0, 1],
    "force_half_precision": true
  }
}
```

## Quantization Options

### Scalar Quantization (Recommended)
- **Compression**: 4x (int8)
- **Performance**: Minimal impact
- **Use case**: General purpose

### Product Quantization
- **Compression**: 8-64x configurable
- **Performance**: Slight search quality reduction
- **Use case**: Very large datasets

### Binary Quantization
- **Compression**: 32x
- **Performance**: Noticeable quality reduction
- **Use case**: Memory-constrained environments

## Troubleshooting

### Common Issues

1. **Qdrant not starting:**
```bash
# Check Docker logs
docker logs qdrant-${USER}-1

# Verify port availability
lsof -i :6333
```

2. **Migration fails:**
```bash
# Check MongoDB is running
docker ps | grep mongo

# Verify source data
mongo kato_kb --eval "db.vectors_kb.count()"
```

3. **Search performance issues:**
```bash
# Check index status
curl http://localhost:6333/collections/kato_vectors

# Optimize collection
curl -X POST http://localhost:6333/collections/kato_vectors/optimize
```

### Performance Tuning

1. **Adjust HNSW parameters** for better recall:
```json
{
  "index": {
    "type": "hnsw",
    "parameters": {
      "m": 32,  // Increase for better recall
      "ef_construct": 200  // Increase for better index quality
    }
  }
}
```

2. **Enable caching** for repeated queries:
```json
{
  "cache": {
    "enabled": true,
    "size": 50000,  // Adjust based on RAM
    "ttl": 7200
  }
}
```

3. **Use batch operations** for bulk inserts:
```python
# Instead of individual inserts
for vector in vectors:
    engine.add_vector_sync(vector)

# Use batch operation
engine.add_vectors_batch_sync(vectors)
```

## Testing

Run the test suite:

```bash
# Run vector database tests
pytest tests/test_vector_database.py -v

# Run integration tests (requires services running)
pytest tests/test_vector_database.py -v -m integration
```

## API Reference

### VectorStore Interface

All vector stores implement this interface:

- `connect()` - Establish connection
- `disconnect()` - Close connection
- `create_collection()` - Create vector collection
- `add_vector()` - Add single vector
- `add_vectors()` - Batch add vectors
- `search()` - Similarity search
- `update_vector()` - Update vector/metadata
- `delete_vector()` - Remove vector
- `optimize_collection()` - Optimize for performance

### VectorSearchEngine

High-level search interface:

- `initialize()` - Connect and setup
- `add_vector()` - Add with caching
- `search()` - Search with caching
- `find_nearest_neighbors()` - KNN search
- `get_stats()` - Performance metrics

## Future Enhancements

- [ ] Support for additional backends (Pinecone, ChromaDB)
- [ ] Distributed vector search across multiple nodes
- [ ] Advanced filtering with SQL-like syntax
- [ ] Vector versioning and rollback
- [ ] Real-time vector updates with CDC
- [ ] Multi-modal vector support (text + image)
- [ ] Automatic vector dimension detection
- [ ] Vector compression with learned indices

## Contributing

To add a new vector database backend:

1. Create adapter in `kato/storage/your_backend_store.py`
2. Implement `VectorStore` interface
3. Register in `VectorStoreFactory`
4. Add configuration in `vectordb_config.py`
5. Create tests in `test_vector_database.py`

## License

Part of the KATO project. See main LICENSE file.