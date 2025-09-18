# KATO Vector Processing System

## Table of Contents
1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Processing Pipeline](#processing-pipeline)
4. [Storage Backends](#storage-backends)
5. [Similarity Algorithms](#similarity-algorithms)
6. [Index Types](#index-types)
7. [Configuration](#configuration)
8. [Performance Optimization](#performance-optimization)
9. [Examples](#examples)
10. [Troubleshooting](#troubleshooting)

## Overview

KATO's vector processing system handles continuous numerical data (embeddings) and converts them into symbolic representations that can be integrated with the pattern matching system. This allows KATO to process multi-modal data combining discrete symbols with continuous vectors.

### Key Features
- **Modern Vector Database**: Qdrant backend with HNSW indexing
- **Multiple Distance Metrics**: Euclidean, Cosine, Dot Product, Manhattan
- **Performance Optimizations**: Caching, batching, quantization, GPU support
- **Isolation**: Each processor has its own vector collection
- **Symbolic Integration**: Vectors converted to `VCTR|<hash>` symbols for STM

### Use Cases
- Processing neural network embeddings (e.g., from transformers)
- Handling sensor data as continuous vectors
- Similarity search in high-dimensional spaces
- Multi-modal pattern recognition combining text and embeddings

## Architecture

KATO's vector processing uses a **layered architecture** optimized for performance and flexibility:

```
┌─────────────────────────────────────────────┐
│          Application Layer                  │
│        (KATO Processor API)                 │
└─────────────────┬───────────────────────────┘
                  │
┌─────────────────▼───────────────────────────┐
│         VectorProcessor                     │
│   • Orchestrates vector operations          │
│   • Converts arrays to VectorObjects        │
│   • Manages learning queue                  │
└─────────────────┬───────────────────────────┘
                  │
┌─────────────────▼───────────────────────────┐
│         VectorIndexer                       │
│   • Modern search interface                 │
│   • Collection isolation by processor_id    │
│   • K-nearest neighbor search               │
└─────────────────┬───────────────────────────┘
                  │
┌─────────────────▼───────────────────────────┐
│      VectorSearchEngine                     │
│   • Caching layer (Redis/Memory)            │
│   • Batch operations                        │
│   • Async I/O                               │
│   • Metrics and monitoring                  │
└─────────────────┬───────────────────────────┘
                  │
┌─────────────────▼───────────────────────────┐
│         VectorStore Interface               │
│   • Abstract storage interface              │
│   • Backend-agnostic operations             │
└─────────────────┬───────────────────────────┘
                  │
┌─────────────────▼───────────────────────────┐
│        QdrantStore (Default)                │
│   • Qdrant client implementation            │
│   • HNSW indexing                          │
│   • Quantization support                    │
│   • GPU acceleration (optional)             │
└─────────────────┬───────────────────────────┘
                  │
┌─────────────────▼───────────────────────────┐
│         Qdrant Database                     │
│   • Vector storage and indexing             │
│   • Port 6333 (HTTP), 6334 (gRPC)          │
│   • Collection: vectors_{processor_id}      │
└─────────────────────────────────────────────┘
```

## Processing Pipeline

### 1. Input Processing

Vectors are received as lists of floating-point numbers:

```python
# Input format
observation = {
    'vectors': [
        [0.1, 0.2, 0.3, ...],  # First vector
        [0.4, 0.5, 0.6, ...]   # Second vector
    ]
}
```

### 2. Vector Object Creation

Each vector is processed through these steps:

```python
# 1. Convert to numpy array
vector_array = np.array([0.1, 0.2, 0.3, ...])

# 2. Reduce/concatenate multiple vectors
combined = reduce(lambda x,y: x+y, vectors)

# 3. Create VectorObject
vector_obj = VectorObject(combined)
# Generates:
# - vector_hash: SHA1 hash of vector
# - name: "VCTR|<hash>"
# - vector_length: Euclidean norm
```

### 3. Storage and Indexing

Vectors are stored in Qdrant with:
- **Collection**: `vectors_{processor_id}` for isolation
- **Index**: HNSW (Hierarchical Navigable Small World) by default
- **Metadata**: Optional payload with additional information

### 4. Similarity Search

When processing new vectors:
1. Find k-nearest neighbors (default k=3)
2. Return vector IDs as symbolic names
3. Add both nearest neighbors and new vector to symbol list

### 5. Symbolic Integration

Vector names are added to STM as regular symbols:
```python
# Vector symbols in STM
['VCTR|abc123...', 'VCTR|def456...', 'string1', 'string2']
```

## Storage Backends

### Qdrant (Default)

**Features:**
- Written in Rust for high performance
- HNSW indexing with tunable parameters
- Rich filtering capabilities
- Quantization support
- GPU acceleration (with appropriate Docker image)

**Configuration:**
```yaml
backend: qdrant
host: localhost
port: 6333
grpc_port: 6334
collection_name: vectors_{processor_id}
```

### Alternative Backends (Planned)

| Backend | Status | Best For |
|---------|--------|----------|
| **FAISS** | Planned | CPU-optimized, large-scale |
| **Milvus** | Planned | Distributed, billion-scale |
| **Weaviate** | Planned | GraphQL API, semantic search |

## Similarity Algorithms

### Distance Metrics

#### 1. Euclidean Distance (Default)
- **Formula**: `sqrt(sum((a[i] - b[i])^2))`
- **Range**: [0, ∞)
- **Use Case**: Dense vectors, general similarity
- **Properties**: Triangle inequality holds

#### 2. Cosine Similarity
- **Formula**: `dot(a, b) / (norm(a) * norm(b))`
- **Range**: [-1, 1]
- **Use Case**: Text embeddings, normalized vectors
- **Properties**: Magnitude-independent

#### 3. Dot Product
- **Formula**: `sum(a[i] * b[i])`
- **Range**: (-∞, ∞)
- **Use Case**: When magnitude matters
- **Properties**: Fast computation

#### 4. Manhattan Distance
- **Formula**: `sum(abs(a[i] - b[i]))`
- **Range**: [0, ∞)
- **Use Case**: Grid-based, sparse vectors
- **Properties**: L1 norm, city-block distance

### Choosing a Distance Metric

| Use Case | Recommended Metric | Why |
|----------|-------------------|-----|
| Text embeddings | Cosine | Direction matters more than magnitude |
| Image features | Euclidean | Absolute distances meaningful |
| Recommendation systems | Dot Product | Magnitude indicates strength |
| Sparse data | Manhattan | Robust to outliers |

## Index Types

### HNSW (Default)

**Hierarchical Navigable Small World**

```yaml
type: hnsw
parameters:
  m: 16                 # Number of connections per node
  ef_construct: 128     # Size of dynamic list during construction
  ef_search: 100       # Size of dynamic list during search
  max_elements: 1000000 # Maximum number of vectors
```

**Characteristics:**
- Build time: O(N log N)
- Search time: O(log N)
- Memory: O(N * m)
- Accuracy: 95-99% (tunable)

### Alternative Index Types

#### Flat Index
```yaml
type: flat
parameters: {}  # No parameters - exact search
```
- **Pros**: 100% accuracy
- **Cons**: O(N) search time
- **Use Case**: Small datasets (<10k vectors)

#### IVF (Inverted File)
```yaml
type: ivf
parameters:
  nlist: 1024  # Number of clusters
  nprobe: 8    # Number of clusters to search
```
- **Pros**: Good for large datasets
- **Cons**: Requires training
- **Use Case**: 100k+ vectors

#### LSH (Locality-Sensitive Hashing)
```yaml
type: lsh
parameters:
  hash_functions: 12
  tables: 4
```
- **Pros**: Sublinear search time
- **Cons**: Lower accuracy
- **Use Case**: Very high dimensions

## Configuration

### Environment Variables

#### Core Settings

| Variable | Default | Description | Range/Options |
|----------|---------|-------------|---------------|
| `INDEXER_TYPE` | `"VI"` | Vector indexer type | "VI" only currently |
| `KATO_VECTOR_DB_BACKEND` | `"qdrant"` | Storage backend | qdrant, faiss, milvus, weaviate |
| `KATO_VECTOR_DIM` | Auto | Vector dimensions | Any positive integer |
| `KATO_SIMILARITY_METRIC` | `"euclidean"` | Distance metric | euclidean, cosine, dot, manhattan |

#### Qdrant Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `QDRANT_HOST` | `"localhost"` | Qdrant server host |
| `QDRANT_PORT` | `6333` | HTTP API port |
| `QDRANT_GRPC_PORT` | `6334` | gRPC API port |
| `QDRANT_COLLECTION` | `"vectors_{processor_id}"` | Collection name pattern |

#### Performance Tuning

| Variable | Default | Description |
|----------|---------|-------------|
| `KATO_VECTOR_BATCH_SIZE` | `1000` | Vectors per batch operation |
| `KATO_VECTOR_SEARCH_LIMIT` | `100` | Maximum search results |
| `CONNECTION_POOL_SIZE` | `10` | Database connections |
| `REQUEST_TIMEOUT` | `30.0` | Timeout in seconds |

#### Optimization Features

| Variable | Default | Description |
|----------|---------|-------------|
| `KATO_CACHE_ENABLED` | `true` | Enable result caching |
| `REDIS_HOST` | `"localhost"` | Redis cache host |
| `REDIS_PORT` | `6379` | Redis cache port |
| `KATO_GPU_ENABLED` | `false` | Use GPU acceleration |
| `KATO_GPU_DEVICES` | `"0"` | GPU device IDs (comma-separated) |
| `KATO_QUANTIZATION_ENABLED` | `false` | Enable vector quantization |
| `KATO_QUANTIZATION_TYPE` | `"scalar"` | Quantization method |

### Configuration Examples

#### Development Configuration
```bash
export KATO_VECTOR_DB_BACKEND=qdrant
export KATO_SIMILARITY_METRIC=euclidean
export KATO_CACHE_ENABLED=false
export KATO_QUANTIZATION_ENABLED=false
export KATO_VECTOR_BATCH_SIZE=100
```

#### Production Configuration
```bash
export KATO_VECTOR_DB_BACKEND=qdrant
export KATO_SIMILARITY_METRIC=cosine
export KATO_CACHE_ENABLED=true
export KATO_QUANTIZATION_ENABLED=true
export KATO_QUANTIZATION_TYPE=scalar
export KATO_VECTOR_BATCH_SIZE=5000
export CONNECTION_POOL_SIZE=20
```

#### GPU-Accelerated Configuration
```bash
export KATO_GPU_ENABLED=true
export KATO_GPU_DEVICES=0,1
export KATO_QUANTIZATION_TYPE=product
export KATO_VECTOR_BATCH_SIZE=10000
```

## Performance Optimization

### 1. Quantization

Reduce memory usage and improve speed by quantizing vectors:

#### Scalar Quantization (Recommended)
```python
quantization = {
    "enabled": True,
    "type": "scalar",
    "parameters": {
        "type": "int8",      # 4x memory reduction
        "quantile": 0.99,    # Outlier handling
        "always_ram": False  # Keep on disk if needed
    }
}
```

#### Product Quantization
```python
quantization = {
    "enabled": True,
    "type": "product",
    "parameters": {
        "compression": "x16",  # 16x compression
        "always_ram": False
    }
}
```

#### Binary Quantization (Maximum Compression)
```python
quantization = {
    "enabled": True,
    "type": "binary",
    "parameters": {
        "always_ram": True  # Fast but uses more RAM
    }
}
```

### 2. Caching

Result caching provides dramatic speedups for repeated queries:

```python
cache_config = {
    "enabled": True,
    "backend": "redis",     # or "memory"
    "size": 10000,         # Number of cached results
    "ttl": 3600           # Time to live in seconds
}
```

**Performance Impact:**
- First query: ~10ms
- Cached query: ~0.1ms (100x faster)

### 3. Batch Processing

Process multiple vectors together for efficiency:

```python
# Instead of individual operations
for vector in vectors:
    engine.add_vector(vector)  # Slow

# Use batch operations
engine.add_vectors_batch(vectors)  # Much faster
```

**Benchmarks:**
- Individual: 1000 vectors in ~1000ms
- Batch: 1000 vectors in ~50ms (20x faster)

### 4. Index Optimization

Tune HNSW parameters for your use case:

#### For Speed (Lower Accuracy)
```yaml
m: 8
ef_construct: 64
ef_search: 50
```

#### For Accuracy (Slower)
```yaml
m: 32
ef_construct: 256
ef_search: 200
```

#### Balanced (Default)
```yaml
m: 16
ef_construct: 128
ef_search: 100
```

### Performance Benchmarks

| Configuration | Vectors | Build Time | Search Time | Accuracy | Memory |
|--------------|---------|------------|-------------|----------|--------|
| Flat (Exact) | 10K | 0ms | 100ms | 100% | Low |
| HNSW Default | 10K | 500ms | 1ms | 98% | Medium |
| HNSW + Scalar Quant | 10K | 600ms | 0.8ms | 97% | Low |
| HNSW + Cache | 10K | 500ms | 0.1ms* | 98% | High |
| HNSW + GPU | 10K | 200ms | 0.5ms | 98% | Medium |

*Cached queries only

## Examples

### Example 1: Basic Vector Processing

```python
# Input observation with vectors
observation = {
    'vectors': [
        [0.1, 0.2, 0.3, 0.4, 0.5],  # 5-dimensional vector
        [0.6, 0.7, 0.8, 0.9, 1.0]   # Another 5-dim vector
    ]
}

# Processing flow:
# 1. Vectors concatenated: [0.1, 0.2, ..., 0.9, 1.0]
# 2. VectorObject created with hash: VCTR|a1b2c3...
# 3. Stored in Qdrant collection: vectors_processor123
# 4. Search finds 3 nearest: [VCTR|xyz..., VCTR|abc..., VCTR|def...]
# 5. Returns symbols: [VCTR|a1b2c3..., VCTR|xyz..., VCTR|abc..., VCTR|def...]
```

### Example 2: Text Embedding Integration

```python
# Using text embeddings (e.g., from BERT)
text = "The weather is sunny today"
embedding = bert_model.encode(text)  # Returns 768-dim vector

observation = {
    'strings': ['weather', 'sunny'],
    'vectors': [embedding.tolist()]
}

# Result in STM:
# ['sunny', 'weather', 'VCTR|embedding_hash']
# All three symbols can be used for pattern matching
```

### Example 3: Sensor Data Processing

```python
# Multiple sensor readings as vectors
sensor_readings = {
    'vectors': [
        temperature_sensor.get_vector(),  # [temp, humidity, pressure]
        motion_sensor.get_vector(),       # [x, y, z, acceleration]
        audio_sensor.get_vector()         # [frequency_bins...]
    ]
}

# Each sensor vector gets unique ID
# Result: [VCTR|temp_hash, VCTR|motion_hash, VCTR|audio_hash]
```

### Example 4: Configuration for Different Vector Types

#### For Text Embeddings (768-dim from transformers)
```bash
export KATO_VECTOR_DIM=768
export KATO_SIMILARITY_METRIC=cosine
export KATO_QUANTIZATION_TYPE=scalar
```

#### For Image Features (2048-dim from ResNet)
```bash
export KATO_VECTOR_DIM=2048
export KATO_SIMILARITY_METRIC=euclidean
export KATO_GPU_ENABLED=true
```

#### For Low-Dimensional Sensor Data (3-50 dims)
```bash
export KATO_VECTOR_DIM=50
export KATO_SIMILARITY_METRIC=manhattan
export KATO_QUANTIZATION_ENABLED=false  # Not needed for small vectors
```

## Troubleshooting

### Issue: Qdrant Connection Failed

**Symptom**: `Failed to connect to Qdrant` error

**Solutions:**
1. Check Qdrant is running:
   ```bash
   docker ps | grep qdrant
   curl http://localhost:6333/health
   ```

2. Verify environment variables:
   ```bash
   echo $QDRANT_HOST
   echo $QDRANT_PORT
   ```

3. Check Docker network:
   ```bash
   docker network inspect kato_network
   ```

### Issue: Vector Dimension Mismatch

**Symptom**: `Vector dimension 768 doesn't match collection dimension 512`

**Solutions:**
1. Set explicit dimension:
   ```bash
   export KATO_VECTOR_DIM=768
   ```

2. Or recreate collection:
   ```bash
   # Delete old collection via Qdrant API
   curl -X DELETE http://localhost:6333/collections/vectors_processor_id
   ```

### Issue: Slow Vector Search

**Symptom**: Search takes >100ms

**Solutions:**
1. Enable caching:
   ```bash
   export KATO_CACHE_ENABLED=true
   ```

2. Reduce search accuracy for speed:
   ```bash
   # In configuration
   ef_search: 50  # Lower value = faster
   ```

3. Enable quantization:
   ```bash
   export KATO_QUANTIZATION_ENABLED=true
   export KATO_QUANTIZATION_TYPE=scalar
   ```

### Issue: Out of Memory

**Symptom**: Container crashes with OOM error

**Solutions:**
1. Enable quantization to reduce memory:
   ```bash
   export KATO_QUANTIZATION_TYPE=binary  # Maximum compression
   ```

2. Reduce batch size:
   ```bash
   export KATO_VECTOR_BATCH_SIZE=100
   ```

3. Use disk-based payload storage:
   ```python
   # Qdrant configuration
   on_disk_payload: true
   ```

### Issue: Duplicate Vectors

**Symptom**: Same vector appears multiple times

**Cause**: Vectors are identified by SHA1 hash - identical vectors get same ID

**Solution**: This is expected behavior. If uniqueness is needed, add timestamp or ID to vector:
```python
# Add small unique component
vector_with_id = vector + [unique_id * 0.0001]
```

### Issue: GPU Not Being Used

**Symptom**: No GPU acceleration despite configuration

**Solutions:**
1. Verify GPU-enabled Qdrant image:
   ```bash
   # Use GPU-enabled image
   docker pull qdrant/qdrant:latest-gpu
   ```

2. Check CUDA availability:
   ```bash
   nvidia-smi
   ```

3. Set GPU environment:
   ```bash
   export KATO_GPU_ENABLED=true
   export KATO_GPU_DEVICES=0
   ```

## Performance Best Practices

1. **Choose the right distance metric** for your data type
2. **Enable caching** for production deployments
3. **Use batch operations** for bulk inserts
4. **Tune index parameters** based on accuracy/speed needs
5. **Enable quantization** for large-scale deployments
6. **Monitor metrics** using the search engine stats
7. **Isolate collections** per processor for clean separation
8. **Set appropriate dimensions** to avoid mismatches

## See Also

- [Pattern Matching](PATTERN_MATCHING.md) - How patterns are matched
- [System Overview](SYSTEM_OVERVIEW.md) - Overall KATO architecture
- [Configuration Management](CONFIGURATION_MANAGEMENT.md) - All configuration options
- [API Reference](API_REFERENCE.md) - API endpoints for vector operations