# Vector Processing Theory in KATO

## Table of Contents
1. [Overview](#overview)
2. [Vector Embeddings](#vector-embeddings)
3. [Vector Space Model](#vector-space-model)
4. [Similarity in Vector Spaces](#similarity-in-vector-spaces)
5. [Dimensionality and Representation](#dimensionality-and-representation)
6. [Vector Quantization](#vector-quantization)
7. [Integration with Symbolic Processing](#integration-with-symbolic-processing)
8. [Theoretical Foundations](#theoretical-foundations)

## Overview

KATO processes **vector embeddings** as a third modality alongside discrete symbols and continuous emotives. This document explores the theoretical foundations of vector processing, embedding spaces, and integration with KATO's symbolic architecture.

### Why Vectors?

**Problem**: Real-world data (text, images, audio) doesn't fit cleanly into discrete symbols.

**Solution**: Vector embeddings provide:
1. **Continuous representation**: Capture semantic nuances
2. **Similarity structure**: Geometrically encode relationships
3. **Dimensionality reduction**: Compress high-dimensional data
4. **Transfer learning**: Leverage pre-trained models

### KATO's Approach

Convert vectors to **symbolic names** via deterministic hashing:

```python
# Vector embedding (768 dimensions)
vector = [0.123, -0.456, 0.789, ..., 0.234]

# Hash to symbolic name
vector_name = "VCTR|a1b2c3d4e5f6"

# Store vector in Qdrant, use name in patterns
```

**Benefits**:
- Unified symbolic processing
- Deterministic pattern formation
- Semantic similarity search
- Pattern-vector correspondence

## Vector Embeddings

### Definition

A **vector embedding** is a mapping from high-dimensional or discrete spaces to continuous vector spaces:

```
φ: 𝒳 → ℝᵈ

Where:
  𝒳 = Original space (text, images, etc.)
  ℝᵈ = d-dimensional real vector space
  φ = Embedding function
```

### Properties of Good Embeddings

1. **Semantic Preservation**:
   ```
   similar(x₁, x₂) in 𝒳 ⟹ distance(φ(x₁), φ(x₂)) small in ℝᵈ
   ```

2. **Geometric Structure**:
   ```
   φ(king) - φ(man) + φ(woman) ≈ φ(queen)
   ```

3. **Dimensionality Reduction**:
   ```
   dim(ℝᵈ) << dim(𝒳)
   # Example: 768 dimensions vs. 50,000 word vocabulary
   ```

### Embedding Models

KATO supports embeddings from various models:

**Text Embeddings**:
```python
# Sentence transformers (768-dim)
from sentence_transformers import SentenceTransformer

model = SentenceTransformer('all-MiniLM-L6-v2')
embedding = model.encode("Hello world")  # Shape: (768,)
```

**Custom Embeddings**:
```python
# Any 768-dimensional vector
custom_embedding = np.random.randn(768)
```

### KATO's 768-Dimensional Standard

**Why 768 dimensions?**
1. Common output from transformer models (BERT, etc.)
2. Rich enough for semantic representation
3. Manageable storage and computation
4. Good balance of expressiveness vs. efficiency

**Normalization**:
```python
def normalize_vector(v):
    """L2 normalization for cosine similarity."""
    norm = np.linalg.norm(v)
    if norm > 0:
        return v / norm
    return v
```

## Vector Space Model

### Euclidean Space

Vectors live in d-dimensional Euclidean space:

```
ℝᵈ = {(x₁, x₂, ..., xᵈ) | xᵢ ∈ ℝ}
```

**Properties**:
- Inner product: ⟨u, v⟩ = Σᵢ uᵢvᵢ
- Norm: ‖v‖ = √⟨v, v⟩
- Distance: d(u, v) = ‖u - v‖

### Metric Structure

Vector space equipped with **cosine similarity** metric:

```python
def cosine_similarity(u, v):
    """
    Cosine similarity in [-1, 1].

    cos(θ) = ⟨u, v⟩ / (‖u‖ · ‖v‖)
    """
    dot_product = np.dot(u, v)
    norm_u = np.linalg.norm(u)
    norm_v = np.linalg.norm(v)

    if norm_u > 0 and norm_v > 0:
        return dot_product / (norm_u * norm_v)
    return 0.0
```

**Range**:
- cos = 1.0: Identical direction
- cos = 0.0: Orthogonal
- cos = -1.0: Opposite direction

### Topological Properties

**Open Balls**: Neighborhoods in vector space

```python
def in_ball(v, center, radius):
    """Check if vector v is within radius of center."""
    distance = np.linalg.norm(v - center)
    return distance <= radius
```

**Compact Subspaces**: Bounded regions

```python
# L2-normalized vectors lie on unit sphere
unit_sphere = {v ∈ ℝᵈ | ‖v‖ = 1}
```

**Continuity**: Small changes in vectors → small changes in similarity

```python
# Lipschitz continuity of cosine similarity
|cos_sim(u₁, v) - cos_sim(u₂, v)| ≤ L · ‖u₁ - u₂‖
```

## Similarity in Vector Spaces

### Distance Metrics

Multiple ways to measure vector similarity:

**Euclidean Distance** (L2):
```python
def euclidean_distance(u, v):
    """L2 distance."""
    return np.linalg.norm(u - v)
```

**Manhattan Distance** (L1):
```python
def manhattan_distance(u, v):
    """L1 distance."""
    return np.sum(np.abs(u - v))
```

**Cosine Distance**:
```python
def cosine_distance(u, v):
    """Angular distance in [0, 2]."""
    return 1 - cosine_similarity(u, v)
```

### KATO's Choice: Cosine Similarity

**Rationale**:
1. **Magnitude-invariant**: Only direction matters
2. **Interpretable**: Direct angle relationship
3. **Normalized**: Range [-1, 1]
4. **Fast computation**: Single dot product + norms

**Implementation**:
```python
# Qdrant configuration
from qdrant_client.models import Distance

collection_config = {
    "vectors": {
        "size": 768,
        "distance": Distance.COSINE  # Use cosine metric
    }
}
```

### Approximate Nearest Neighbor (ANN)

Finding similar vectors efficiently:

**Exact Search**: O(N × d) - expensive for large N

**HNSW (Hierarchical Navigable Small World)**:
- Builds graph structure over vectors
- Complexity: O(log N × d)
- Configurable accuracy/speed tradeoff

```python
# Qdrant HNSW configuration
hnsw_config = {
    "m": 16,           # Number of connections per layer
    "ef_construct": 100 # Construction parameter
}
```

## Dimensionality and Representation

### Curse of Dimensionality

**Problem**: High-dimensional spaces are sparse

```python
# Volume of d-dimensional unit sphere
# decreases relative to bounding cube as d increases

def sphere_vs_cube_ratio(d):
    """Volume ratio: sphere / cube."""
    return (np.pi ** (d/2)) / (2**d * gamma(d/2 + 1))

# d=2: ratio ≈ 0.785
# d=10: ratio ≈ 0.0025
# d=100: ratio ≈ 10^-30 (essentially zero!)
```

**Implications**:
- Most volume in "corners" of space
- Nearest neighbors far apart
- Similarity search challenging

### Dimensionality Reduction

**Why Reduce?**
1. Storage efficiency
2. Faster similarity search
3. Noise reduction
4. Visualization

**Principal Component Analysis (PCA)**:
```python
from sklearn.decomposition import PCA

# Reduce 768 → 128 dimensions
pca = PCA(n_components=128)
reduced_vectors = pca.fit_transform(vectors_768d)

# Explained variance
print(f"Variance retained: {sum(pca.explained_variance_ratio_):.2%}")
```

**UMAP (Uniform Manifold Approximation and Projection)**:
```python
import umap

# Non-linear dimensionality reduction
reducer = umap.UMAP(n_components=2)
embedding_2d = reducer.fit_transform(vectors_768d)
```

**KATO's Approach**: Keep full 768-dimensional vectors for accuracy

### Intrinsic Dimensionality

**Definition**: True degrees of freedom in data

```python
def estimate_intrinsic_dimension(vectors, k=10):
    """
    Estimate intrinsic dimensionality using k-NN distances.

    Based on maximum likelihood estimation.
    """
    from sklearn.neighbors import NearestNeighbors

    nbrs = NearestNeighbors(n_neighbors=k+1).fit(vectors)
    distances, _ = nbrs.kneighbors(vectors)

    # Ratio of successive distances
    ratios = distances[:, 1:] / distances[:, :-1]

    # MLE estimate
    intrinsic_dim = -k / np.mean(np.log(ratios + 1e-10))

    return intrinsic_dim
```

**Typical Finding**: While embeddings are 768-dim, intrinsic dimension often 10-50

## Vector Quantization

### Product Quantization

Compressing vectors for storage:

```python
def product_quantize(vector, n_subspaces=8):
    """
    Divide vector into subspaces and quantize each.

    768 dimensions → 8 subspaces of 96 dimensions
    Each subspace quantized to single byte (256 codebook entries)
    Compression: 768 floats (3KB) → 8 bytes
    """
    subspace_size = len(vector) // n_subspaces
    quantized = []

    for i in range(n_subspaces):
        subvector = vector[i*subspace_size:(i+1)*subspace_size]
        # Quantize to nearest codebook entry
        code = quantize_subvector(subvector, codebook[i])
        quantized.append(code)

    return quantized  # 8 bytes total
```

**Qdrant Support**:
```python
# Enable scalar quantization
quantization_config = {
    "scalar": {
        "type": "int8",  # 8-bit quantization
        "quantile": 0.99,
        "always_ram": True
    }
}
```

### Binary Quantization

Extreme compression:

```python
def binary_quantize(vector):
    """
    Convert to binary: positive → 1, negative → 0.

    768 floats (3KB) → 96 bytes (768 bits)
    """
    return np.packbits(vector > 0)
```

**Tradeoff**: Massive compression but reduced accuracy

## Integration with Symbolic Processing

### Vector-to-Symbol Mapping

KATO's core innovation: treating vectors as symbols

```python
def vector_to_symbol(vector):
    """
    Deterministic hash-based symbol generation.
    """
    # Normalize for consistency
    normalized = vector / np.linalg.norm(vector)

    # Round to reduce float precision issues
    rounded = np.round(normalized, decimals=6)

    # Generate hash
    vector_bytes = rounded.tobytes()
    hash_value = hashlib.sha1(vector_bytes).hexdigest()

    return f"VCTR|{hash_value[:12]}"
```

**Properties**:
- **Deterministic**: Same vector → same symbol
- **Unique**: Different vectors → different symbols (high probability)
- **Symbolic**: Compatible with pattern representation

### Hybrid Pattern Formation

Patterns with both symbols and vectors:

```python
pattern = {
    "events": [
        ["login", "VCTR|a1b2c3"],     # Event 1: symbol + vector
        ["browse", "VCTR|d4e5f6"],    # Event 2: symbol + vector
        ["logout"]                     # Event 3: symbol only
    ],
    "frequency": 42
}
```

### Semantic Pattern Matching

Two-stage matching:

**Stage 1: Symbolic Matching**
```python
# Fast symbolic filter
matching_patterns = kb.query({"events": {"$in": ["login", "VCTR|a1b2c3"]}})
```

**Stage 2: Vector Similarity**
```python
# Refine with vector similarity
for pattern in matching_patterns:
    for event in pattern.events:
        for symbol in event:
            if symbol.startswith("VCTR|"):
                # Get stored vector
                stored_vector = qdrant.get_vector(symbol)

                # Compare with observation vector
                similarity = cosine_similarity(observation_vector, stored_vector)

                if similarity >= threshold:
                    # Pattern is semantic match
                    matches.append(pattern)
```

### Advantages of Hybrid Approach

1. **Best of Both Worlds**:
   - Symbolic: Exact matching, explainability
   - Vector: Semantic similarity, continuous representation

2. **Scalable**:
   - Initial symbolic filter reduces search space
   - Vector comparison only on candidates

3. **Interpretable**:
   - Pattern structure visible (symbols)
   - Semantic relationships preserved (vectors)

## Theoretical Foundations

### Reproducing Kernel Hilbert Space (RKHS)

Vector embeddings implicitly define kernel:

```
k(x, y) = ⟨φ(x), φ(y)⟩

Where:
  φ: 𝒳 → ℋ (Hilbert space)
  k: Kernel function
```

**Properties**:
- Symmetric: k(x, y) = k(y, x)
- Positive definite: Σᵢⱼ cᵢcⱼk(xᵢ, xⱼ) ≥ 0

### Manifold Hypothesis

**Assumption**: High-dimensional data lies on low-dimensional manifold

```
Data ⊂ ℳ ⊂ ℝᵈ

Where:
  ℳ = Manifold (intrinsic dimension k << d)
  ℝᵈ = Ambient space (768 dimensions)
```

**Implications**:
- Smooth interpolation possible
- Local structure meaningful
- Similarity search effective

### Information Geometry

Vector space as information manifold:

```python
# Fisher information metric
def fisher_metric(θ₁, θ₂):
    """
    Measure distance in parameter space.

    Based on KL divergence.
    """
    kl_divergence = kl_div(P(·|θ₁), P(·|θ₂))
    return kl_divergence
```

**Connection to Vectors**: Embeddings approximate information geometry of data distribution

## Practical Considerations

### Vector Preprocessing

```python
def preprocess_vector(v):
    """
    Standard preprocessing pipeline.
    """
    # 1. Check dimension
    assert len(v) == 768, "Expected 768 dimensions"

    # 2. Convert to numpy
    v = np.array(v, dtype=np.float32)

    # 3. Handle NaN/Inf
    v = np.nan_to_num(v, nan=0.0, posinf=1.0, neginf=-1.0)

    # 4. Normalize (L2)
    norm = np.linalg.norm(v)
    if norm > 0:
        v = v / norm

    return v
```

### Storage Optimization

```python
# Vector storage calculation
vectors_count = 1_000_000
vector_dim = 768
bytes_per_float = 4  # float32

# Uncompressed
uncompressed_size = vectors_count * vector_dim * bytes_per_float
# = 3.07 GB

# With quantization (int8)
quantized_size = vectors_count * vector_dim * 1  # 1 byte per value
# = 768 MB (4x reduction)
```

### Query Performance

```python
# Benchmark: Search 1M vectors
import time

start = time.time()
results = qdrant.search(
    collection_name="vectors",
    query_vector=query,
    limit=100
)
elapsed = time.time() - start

print(f"Search time: {elapsed*1000:.1f}ms")
# Typical: 5-20ms with HNSW
```

## Related Documentation

- [Vector Embeddings](vector-embeddings.md) - Practical vector usage
- [Similarity Metrics](similarity-metrics.md) - Similarity calculations
- [Core Concepts](core-concepts.md) - KATO fundamentals
- [Pattern Theory](pattern-theory.md) - Pattern representation

---

**Last Updated**: November 2025
**KATO Version**: 3.0+
