# Vector Embeddings in KATO

## Table of Contents
1. [Overview](#overview)
2. [Embedding Architecture](#embedding-architecture)
3. [Vector-to-Symbol Conversion](#vector-to-symbol-conversion)
4. [Storage and Retrieval](#storage-and-retrieval)
5. [Semantic Similarity Search](#semantic-similarity-search)
6. [Integration with Patterns](#integration-with-patterns)
7. [Best Practices](#best-practices)
8. [Examples](#examples)

## Overview

KATO processes **vector embeddings** as first-class citizens alongside discrete symbols. Vectors enable semantic similarity matching while maintaining KATO's deterministic, symbolic architecture through hash-based naming.

### Key Features

1. **768-Dimensional Standard**: Compatible with popular transformer models
2. **Deterministic Naming**: Hash-based symbol generation
3. **Semantic Search**: Cosine similarity in Qdrant
4. **Hybrid Patterns**: Mix vectors and symbols in same pattern
5. **Unified Processing**: Vectors treated as symbols in pattern formation

## Embedding Architecture

### Vector Pipeline

```
Input Vector (768-dim)
        ↓
   Validation
        ↓
  Normalization (L2)
        ↓
Deterministic Hashing
        ↓
  Symbol Name (VCTR|...)
        ↓
 Store in Qdrant
        ↓
Use in Pattern Formation
```

### Data Structure

```python
vector_object = {
    "vector_name": "VCTR|a1b2c3d4e5f6",  # Symbolic identifier
    "embedding": [0.1, 0.2, ..., 0.768],  # 768 floats
    "norm": 1.0,                           # L2 norm (normalized)
    "created_at": "2025-11-13T10:00:00Z"
}
```

## Vector-to-Symbol Conversion

### Deterministic Hashing

```python
def vector_to_symbol(vector):
    """
    Convert 768-dim vector to deterministic symbol name.

    Process:
    1. Normalize vector (L2)
    2. Round to reduce float precision issues
    3. Generate SHA-1 hash
    4. Format as VCTR|hash
    """
    import numpy as np
    import hashlib

    # Step 1: Normalize
    vector = np.array(vector, dtype=np.float32)
    norm = np.linalg.norm(vector)
    if norm > 0:
        normalized = vector / norm
    else:
        normalized = vector

    # Step 2: Round for consistency
    rounded = np.round(normalized, decimals=6)

    # Step 3: Hash
    vector_bytes = rounded.tobytes()
    hash_value = hashlib.sha1(vector_bytes).hexdigest()

    # Step 4: Format
    return f"VCTR|{hash_value[:12]}"
```

### Properties

**Deterministic**:
```python
# Same vector → same symbol
v1 = [0.1, 0.2, ..., 0.768]
name1 = vector_to_symbol(v1)  # VCTR|a1b2c3d4e5f6

v2 = [0.1, 0.2, ..., 0.768]  # Identical
name2 = vector_to_symbol(v2)  # VCTR|a1b2c3d4e5f6

assert name1 == name2  # ✓ Deterministic
```

**Nearly Unique**:
```python
# Different vectors → different symbols (with high probability)
v3 = [0.1, 0.2, ..., 0.769]  # Slightly different
name3 = vector_to_symbol(v3)  # VCTR|x7y8z9a1b2c3

assert name3 != name1  # ✓ Unique
```

**Collision Probability**:
- SHA-1 produces 160-bit hash
- Using 12 hex chars = 48 bits
- Collision probability ≈ 1 / 2^48 ≈ 3.6 × 10^-15 (negligible)

## Storage and Retrieval

### Qdrant Integration

```python
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, Distance, VectorParams

# Initialize client
qdrant = QdrantClient(host="localhost", port=6333)

# Create collection (once per node_id)
qdrant.create_collection(
    collection_name=f"vectors_{node_id}",
    vectors_config=VectorParams(
        size=768,
        distance=Distance.COSINE
    )
)
```

### Storing Vectors

```python
def store_vector(vector, vector_name, pattern_name, event_index):
    """
    Store vector in Qdrant with metadata.
    """
    import uuid

    point = PointStruct(
        id=str(uuid.uuid4()),
        vector=vector.tolist(),
        payload={
            "vector_name": vector_name,
            "pattern_name": pattern_name,
            "event_index": event_index,
            "created_at": datetime.now().isoformat()
        }
    )

    qdrant.upsert(
        collection_name=f"vectors_{node_id}",
        points=[point]
    )
```

### Retrieving Vectors

```python
def get_vector(vector_name):
    """
    Retrieve vector by symbol name.
    """
    results = qdrant.scroll(
        collection_name=f"vectors_{node_id}",
        scroll_filter={
            "must": [
                {
                    "key": "vector_name",
                    "match": {"value": vector_name}
                }
            ]
        },
        limit=1
    )

    if results[0]:
        return results[0][0].vector
    return None
```

## Semantic Similarity Search

### Cosine Similarity

```python
def search_similar_vectors(query_vector, limit=100, threshold=0.7):
    """
    Find vectors similar to query.

    Args:
        query_vector: 768-dim query vector
        limit: Maximum results
        threshold: Minimum similarity (0-1)

    Returns:
        List of (vector_name, similarity) tuples
    """
    results = qdrant.search(
        collection_name=f"vectors_{node_id}",
        query_vector=query_vector,
        limit=limit,
        score_threshold=threshold
    )

    return [
        (result.payload["vector_name"], result.score)
        for result in results
    ]
```

### Example Search

```python
# Query vector (e.g., sentence embedding)
query = model.encode("machine learning algorithms")

# Search
similar = search_similar_vectors(query, limit=10, threshold=0.8)

# Results
# [
#   ("VCTR|a1b2c3d4e5f6", 0.95),  # "deep learning models"
#   ("VCTR|d4e5f6g7h8i9", 0.87),  # "neural networks"
#   ("VCTR|j1k2l3m4n5o6", 0.82),  # "artificial intelligence"
#   ...
# ]
```

## Integration with Patterns

### Hybrid Patterns

Patterns can contain both symbols and vectors:

```python
pattern = {
    "events": [
        ["user_login", "VCTR|a1b2c3"],      # Symbol + vector
        ["page_view", "VCTR|d4e5f6"],       # Symbol + vector
        ["VCTR|g7h8i9", "VCTR|j1k2l3"],     # Two vectors
        ["user_logout"]                      # Symbol only
    ],
    "frequency": 42
}
```

### Pattern Formation

```python
def form_pattern_with_vectors(observations):
    """
    Create pattern from observations containing vectors.

    Process:
    1. Convert vectors to symbols
    2. Store vectors in Qdrant
    3. Create pattern with vector symbols
    4. Store pattern in persistent storage
    """
    events = []

    for obs in observations:
        event_symbols = []

        # Process discrete symbols
        event_symbols.extend(obs.get("strings", []))

        # Process vectors
        for vector in obs.get("vectors", []):
            # Convert to symbol
            vector_name = vector_to_symbol(vector)
            event_symbols.append(vector_name)

            # Store in Qdrant
            store_vector(vector, vector_name, pattern_name, event_index)

        # Sort for determinism
        events.append(sorted(event_symbols))

    return Pattern(events=events)
```

### Matching with Vectors

Two-stage matching process:

**Stage 1: Symbolic Filter**
```python
# Fast symbolic query in pattern database
candidates = kb.find_patterns({
    "events": {"$elemMatch": {"$in": ["VCTR|a1b2c3"]}}
})
```

**Stage 2: Semantic Refinement**
```python
# Refine with vector similarity
refined = []

for pattern in candidates:
    # Get vector symbols in pattern
    vector_symbols = [s for s in pattern.symbols if s.startswith("VCTR|")]

    # Calculate semantic similarity
    total_sim = 0.0
    for vec_sym in vector_symbols:
        stored_vec = get_vector(vec_sym)
        query_vec = observation_vector

        sim = cosine_similarity(stored_vec, query_vec)
        total_sim += sim

    avg_sim = total_sim / len(vector_symbols) if vector_symbols else 0

    if avg_sim >= semantic_threshold:
        refined.append((pattern, avg_sim))

return sorted(refined, key=lambda x: x[1], reverse=True)
```

## Best Practices

### Vector Preprocessing

```python
def preprocess_vector(vector):
    """
    Standard preprocessing for vectors.

    1. Validate dimensions
    2. Handle NaN/Inf
    3. Normalize
    """
    import numpy as np

    # Validate
    if len(vector) != 768:
        raise ValueError(f"Expected 768 dimensions, got {len(vector)}")

    # Convert to numpy
    vec = np.array(vector, dtype=np.float32)

    # Handle NaN/Inf
    vec = np.nan_to_num(vec, nan=0.0, posinf=1.0, neginf=-1.0)

    # Normalize
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm

    return vec
```

### Embedding Model Selection

**Recommended Models**:
- **all-MiniLM-L6-v2**: Fast, good quality, 768-dim
- **all-mpnet-base-v2**: Higher quality, 768-dim, slower
- **Custom**: Any model producing 768-dim embeddings

```python
from sentence_transformers import SentenceTransformer

# Choose model
model = SentenceTransformer('all-MiniLM-L6-v2')

# Generate embeddings
texts = ["hello world", "machine learning"]
embeddings = model.encode(texts)

# Use in KATO
for text, embedding in zip(texts, embeddings):
    observe(strings=[text], vectors=[embedding])
```

### Performance Optimization

**Batch Processing**:
```python
def batch_store_vectors(vectors, metadata_list):
    """
    Store multiple vectors efficiently.
    """
    points = []

    for i, (vector, metadata) in enumerate(zip(vectors, metadata_list)):
        vector_name = vector_to_symbol(vector)

        point = PointStruct(
            id=str(uuid.uuid4()),
            vector=vector.tolist(),
            payload={
                "vector_name": vector_name,
                **metadata
            }
        )
        points.append(point)

    # Single batch upsert
    qdrant.upsert(
        collection_name=f"vectors_{node_id}",
        points=points
    )
```

**Quantization**:
```python
# Enable quantization for storage efficiency
quantization_config = {
    "scalar": {
        "type": "int8",
        "quantile": 0.99,
        "always_ram": True
    }
}

qdrant.update_collection(
    collection_name=f"vectors_{node_id}",
    quantization_config=quantization_config
)
```

## Examples

### Example 1: Text Similarity

```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer('all-MiniLM-L6-v2')

# Encode texts
texts = [
    "The cat sat on the mat",
    "A feline rested on the rug",  # Similar meaning
    "Python programming language"   # Different meaning
]

embeddings = [model.encode(text) for text in texts]

# Convert to symbols
symbols = [vector_to_symbol(emb) for emb in embeddings]

# Store in KATO
for text, emb, sym in zip(texts, embeddings, symbols):
    observe(strings=[text], vectors=[emb])

# Later: semantic search
query = "cat on mat"
query_emb = model.encode(query)
similar = search_similar_vectors(query_emb, threshold=0.7)

# Results include first two texts (semantically similar)
# but not third (different meaning)
```

### Example 2: Multi-Modal Pattern

```python
# Observation with text and image
observation = {
    "strings": ["product_view", "category_electronics"],
    "vectors": [
        text_embedding,    # Text: "wireless headphones"
        image_embedding    # Image: headphones product photo
    ]
}

# Form pattern
observe(**observation)
learn()

# Prediction: Can match either text or image similarity
# Enables cross-modal retrieval
```

### Example 3: Document Chunking

```python
# Split document into chunks
document = load_document("technical_paper.pdf")
chunks = split_into_chunks(document, chunk_size=512)

# Embed each chunk
chunk_embeddings = [model.encode(chunk) for chunk in chunks]

# Store as sequence pattern
for i, embedding in enumerate(chunk_embeddings):
    observe(
        strings=[f"chunk_{i}", "document_id_123"],
        vectors=[embedding]
    )

learn()

# Later: semantic search within document
query = "neural network architectures"
query_emb = model.encode(query)
relevant_chunks = search_similar_vectors(query_emb)
```

## Related Documentation

- [Vector Processing](vector-processing.md) - Theoretical foundations
- [Similarity Metrics](similarity-metrics.md) - Cosine similarity details
- [Core Concepts](core-concepts.md) - KATO fundamentals
- [Pattern Theory](pattern-theory.md) - Pattern representation

---

**Last Updated**: November 2025
**KATO Version**: 3.0+
