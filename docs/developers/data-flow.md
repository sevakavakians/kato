# Data Flow Through KATO

Detailed walkthrough of how data flows through the KATO system from observation to prediction.

## Overview

KATO processes data through five main stages:

1. **Input Reception** - FastAPI receives and validates requests
2. **Observation Processing** - Input data is normalized and added to STM
3. **Pattern Learning** - STM contents are converted to stored patterns
4. **Pattern Matching** - Current STM is matched against learned patterns
5. **Prediction Generation** - Matching patterns are formatted as predictions

## Complete Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                      HTTP Client                            │
│          POST /sessions/{id}/observe                        │
│          {"strings": ["hello", "world"], ...}               │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│              FastAPI Layer (api/endpoints/)                 │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ 1. Pydantic validates request schema                   │ │
│  │ 2. Extract session_id from URL                         │ │
│  │ 3. Get/create KatoProcessor from session manager       │ │
│  └────────────────────────────────────────────────────────┘ │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│         KatoProcessor (workers/kato_processor.py)           │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ observe(data: dict) -> dict                            │ │
│  │   ├─> ObservationProcessor.process_observation()      │ │
│  │   ├─> MemoryManager.add_to_stm()                      │ │
│  │   ├─> Check auto-learn trigger                        │ │
│  │   └─> Return observation result                       │ │
│  └────────────────────────────────────────────────────────┘ │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│     ObservationProcessor (workers/observation_processor.py) │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ 1. Validate input (strings, vectors, emotives)        │ │
│  │ 2. Sort strings alphabetically (if enabled)           │ │
│  │ 3. Process vectors -> vector names (VectorProcessor)  │ │
│  │ 4. Combine strings + vector names                     │ │
│  │ 5. Store emotives in emotive profile                  │ │
│  └────────────────────────────────────────────────────────┘ │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│         MemoryManager (workers/memory_manager.py)           │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ STM (deque): [                                         │ │
│  │   ["coffee", "morning"],    # Event 1                 │ │
│  │   ["commute", "train"],     # Event 2                 │ │
│  │   ["arrive", "work"]        # Event 3 (just added)    │ │
│  │ ]                                                      │ │
│  │                                                        │ │
│  │ Emotives: {                                            │ │
│  │   "energy": [[-0.2], [0.0], [0.5]]                    │ │
│  │ }                                                      │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

## Stage 1: Observation Input

### HTTP Request Format

```python
POST /sessions/{session_id}/observe

{
  "strings": ["hello", "world"],
  "vectors": [[0.1, 0.2, ..., 0.768]],  # Optional: 768-dim embeddings
  "emotives": {"joy": 0.8, "energy": 0.5},  # Optional: emotional context
  "metadata": {"source": "chat", "user_id": "123"}  # Optional: tags
}
```

### Pydantic Validation

```python
# api/schemas.py
class ObservationData(BaseModel):
    strings: list[str] = Field(default_factory=list)
    vectors: list[list[float]] = Field(default_factory=list)
    emotives: dict[str, float] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
```

**Validation Rules**:
- `strings`: List of any strings (can be empty)
- `vectors`: Each vector must be exactly 768 dimensions
- `emotives`: Keys are emotive names, values in range -1.0 to 1.0
- `metadata`: Arbitrary JSON-serializable tags

### Session Lookup

```python
# api/endpoints/sessions.py
session = await app_state.session_manager.get_session(session_id)
if not session:
    raise HTTPException(404, "Session not found")

processor = session.processor  # KatoProcessor instance
```

## Stage 2: Observation Processing

### Data Normalization

**Location**: `workers/observation_processor.py::process_observation()`

```python
def process_observation(self, observation: dict) -> dict:
    """Process and normalize observation data."""

    # Step 1: Extract components
    strings = observation.get('strings', [])
    vectors = observation.get('vectors', [])
    emotives = observation.get('emotives', {})
    metadata = observation.get('metadata', {})

    # Step 2: Process vectors -> vector names
    vector_names = []
    if vectors:
        vector_names = self.vector_processor.process_vectors(
            vectors,
            node_id=self.node_id
        )

    # Step 3: Combine strings and vector names
    combined_event = strings + vector_names

    # Step 4: Sort alphabetically (if configured)
    if self.sort_symbols:
        combined_event = sorted(combined_event)

    # Step 5: Add to STM
    self.memory_manager.add_to_stm(combined_event)

    # Step 6: Store emotives
    if emotives:
        self.memory_manager.update_emotives(emotives)

    # Step 7: Accumulate metadata
    if metadata:
        self.memory_manager.update_metadata(metadata)

    return {
        "observed": True,
        "stm_length": len(self.memory_manager.stm),
        "event": combined_event
    }
```

### Vector Processing Detail

**Location**: `workers/vector_processor.py::process_vectors()`

```python
def process_vectors(self, vectors: list[list[float]], node_id: str) -> list[str]:
    """Convert vector embeddings to symbolic names."""

    vector_names = []
    for vector in vectors:
        # Validate dimensions
        if len(vector) != 768:
            raise ValueError(f"Vector must be 768 dimensions, got {len(vector)}")

        # Generate hash-based name
        vector_hash = self._hash_vector(vector)
        vector_name = f"VCTR|{vector_hash}"

        # Store in Qdrant
        self.qdrant_manager.upsert_vector(
            collection_name=f"vectors_{node_id}",
            vector=vector,
            payload={"vector_name": vector_name}
        )

        vector_names.append(vector_name)

    return vector_names
```

### STM Update

**Location**: `workers/memory_manager.py::add_to_stm()`

```python
def add_to_stm(self, event: list[str]) -> None:
    """Add event to short-term memory."""

    # Append to deque (efficient FIFO)
    self.stm.append(event)

    # Rolling window mode (optional)
    if self.stm_mode == "ROLLING" and len(self.stm) > self.max_stm_length:
        self.stm.popleft()  # Remove oldest event

    logger.debug(f"STM updated: {len(self.stm)} events")
```

## Stage 3: Pattern Learning

### Learning Trigger

**Manual Learning**:
```python
POST /sessions/{session_id}/learn
```

**Auto-Learning** (if `max_pattern_length > 0`):
```python
if len(self.stm) >= self.max_pattern_length:
    pattern = self.learn()
    if self.stm_mode == "CLEAR":
        self.memory_manager.clear_stm()
```

### Learning Process

**Location**: `workers/pattern_processor.py::learn_pattern()`

```python
def learn_pattern(self, stm: list[list[str]], emotives: dict) -> Pattern:
    """Learn pattern from STM contents."""

    # Step 1: Validate minimum length
    if len(stm) < 2:
        raise ValueError("STM must contain at least 2 events")

    # Step 2: Generate pattern hash
    pattern_hash = self._hash_pattern(stm)
    pattern_name = f"PTN|{pattern_hash}"

    # Step 3: Create Pattern object
    pattern = Pattern(
        pattern_name=pattern_name,
        length=len(stm),
        events=stm,
        emotive_profile=emotives,
        metadata={},
        created_at=datetime.now(timezone.utc),
        observation_count=1
    )

    # Step 4: Store in ClickHouse (primary storage)
    self.clickhouse_client.store_pattern(pattern)

    # Step 5: Update Redis metadata
    self.redis_writer.update_pattern_metadata(pattern)

    # Step 6: Update indices
    self._update_indices(pattern)

    logger.info(f"Pattern learned: {pattern_name}, length: {len(stm)}")
    return pattern
```

### Pattern Storage Flow

```
Pattern Object
      ↓
ClickHouse (primary pattern storage)
      └─> patterns table (columnar storage for fast queries)
          {
            name: "abc123",  # Stored WITHOUT 'PTRN|' prefix
            kb_id: "my_app",
            length: 3,
            event_0_string_0: "hello",
            event_1_string_0: "world",
            event_2_string_0: "!",
            created_at: DateTime(...),
            observation_count: 1
          }
      ↓
Redis (pattern metadata & caching)
      └─> pattern:{kb_id}:{pattern_name} (hash)
          {
            frequency: 1,
            last_observed: timestamp,
            emotives: JSON
          }
```

## Stage 4: Pattern Matching

### Prediction Request

```python
GET /sessions/{session_id}/predictions
```

### Matching Process

**Location**: `searches/pattern_search.py::search_patterns()`

```python
def search_patterns(
    self,
    query_stm: list[list[str]],
    threshold: float,
    max_predictions: int
) -> list[Prediction]:
    """Find patterns matching current STM."""

    # Step 1: Candidate retrieval
    candidates = self._get_candidates(query_stm)

    # Step 2: Similarity calculation
    scored_patterns = []
    for pattern in candidates:
        similarity = self._calculate_similarity(
            pattern.events,
            query_stm,
            use_token_matching=self.use_token_matching
        )

        if similarity >= threshold:
            scored_patterns.append((pattern, similarity))

    # Step 3: Ranking
    ranked = self._rank_patterns(scored_patterns)

    # Step 4: Format predictions
    predictions = []
    for pattern, similarity in ranked[:max_predictions]:
        prediction = self._format_prediction(pattern, query_stm, similarity)
        predictions.append(prediction)

    return predictions
```

### Candidate Retrieval

```python
def _get_candidates(self, query_stm: list[list[str]]) -> list[Pattern]:
    """Retrieve candidate patterns from storage."""

    # ClickHouse query with multi-stage filter pipeline
    # Stage 1: MinHash/LSH bloom filter for fast rejection
    # Stage 2: Length-based filtering
    # Stage 3: Token overlap filtering
    candidates = self.clickhouse_client.search_patterns(
        query_stm=query_stm,
        kb_id=self.kb_id,
        min_length=len(query_stm)
    )

    return candidates
```

### Similarity Calculation

**Token-Level Matching** (Default):
```python
def _token_similarity(pattern_event: list[str], query_event: list[str]) -> float:
    """Calculate token overlap similarity."""
    pattern_set = set(pattern_event)
    query_set = set(query_event)

    intersection = pattern_set & query_set
    union = pattern_set | query_set

    return len(intersection) / len(union) if union else 0.0
```

**Character-Level Matching** (Fuzzy):
```python
def _character_similarity(pattern_str: str, query_str: str) -> float:
    """Calculate string similarity using RapidFuzz."""
    from rapidfuzz import fuzz

    return fuzz.ratio(pattern_str, query_str) / 100.0
```

## Stage 5: Prediction Generation

### Prediction Structure

**Location**: `representations/prediction.py::Prediction`

```python
class Prediction:
    """Structured prediction output."""

    # Temporal alignment with pattern
    past: list[list[str]]      # Events before first match
    present: list[list[str]]   # Events containing matches (complete events)
    future: list[list[str]]    # Events after last match

    # Comparison with STM
    missing: list[list[str]]   # Unobserved symbols (aligned with present)
    extras: list[list[str]]    # Unexpected symbols (aligned with STM)

    # Metrics
    similarity: float          # Overall similarity score
    potential: float          # Predictive information
    confidence: float         # Evidence-based confidence
    evidence: float           # Observation count / max
```

### Prediction Formatting

```python
def _format_prediction(
    self,
    pattern: Pattern,
    query_stm: list[list[str]],
    similarity: float
) -> Prediction:
    """Format pattern as prediction."""

    # Find matching region
    match_start, match_end = self._find_match_region(pattern.events, query_stm)

    # Extract temporal components
    past = pattern.events[:match_start]
    present = pattern.events[match_start:match_end+1]
    future = pattern.events[match_end+1:]

    # Calculate missing/extras
    missing = self._calculate_missing(present, query_stm)
    extras = self._calculate_extras(query_stm, present)

    # Calculate metrics
    potential = self._calculate_potential(pattern)
    confidence = self._calculate_confidence(pattern)
    evidence = pattern.observation_count / self.max_observations

    return Prediction(
        past=past,
        present=present,
        future=future,
        missing=missing,
        extras=extras,
        similarity=similarity,
        potential=potential,
        confidence=confidence,
        evidence=evidence,
        pattern_name=pattern.pattern_name
    )
```

### Response Format

```json
{
  "predictions": [
    {
      "past": [["coffee"], ["morning"]],
      "present": [["commute", "train"]],
      "future": [["arrive", "work"]],
      "missing": [["bus"]],
      "extras": [[]],
      "similarity": 0.85,
      "potential": 0.72,
      "confidence": 0.91,
      "evidence": 0.15,
      "pattern_name": "PTN|abc123"
    }
  ],
  "stm": [["commute", "train"]],
  "stm_length": 1
}
```

## Data Flow Optimization Points

### 1. Vector Processing

**Optimization**: Hash-based deduplication
```python
# Store only unique vectors
vector_cache = {}
for vector in vectors:
    vector_hash = self._hash_vector(vector)
    if vector_hash not in vector_cache:
        self.qdrant_manager.upsert_vector(...)
        vector_cache[vector_hash] = vector_name
```

### 2. Pattern Matching

**Optimization**: Bloom filters for fast rejection
```python
# Quick check before expensive similarity calculation
if not self.bloom_filter.might_contain(query_tokens):
    continue  # Skip this pattern
```

### 3. Database Queries

**Optimization**: Index-based candidate retrieval
```python
# MongoDB indices for fast queries
db.patterns.createIndex({"length": 1})
db.patterns.createIndex({"events.0": 1})
db.patterns.createIndex({"observation_count": -1})
```

### 4. Caching

**Optimization**: Redis cache for frequent predictions
```python
# Cache prediction results
cache_key = f"predictions:{session_id}:{stm_hash}"
cached = redis.get(cache_key)
if cached:
    return json.loads(cached)
```

## Error Handling Flow

### Observation Errors

```python
try:
    result = processor.observe(observation)
except ValueError as e:
    # Invalid input (e.g., wrong vector dimensions)
    raise HTTPException(400, f"Invalid observation: {e}")
except StorageError as e:
    # Database unavailable
    raise HTTPException(503, f"Storage error: {e}")
```

### Learning Errors

```python
try:
    pattern = processor.learn()
except ValueError as e:
    # STM too short (<2 events)
    raise HTTPException(400, f"Cannot learn: {e}")
except DuplicatePatternError:
    # Pattern already exists (not an error, return existing)
    pattern = self.get_existing_pattern(pattern_hash)
```

## Performance Metrics

### Typical Flow Timings

```
Observation Processing:  5-15ms
  ├─ Validation:         1ms
  ├─ Vector processing:  2-5ms
  ├─ STM update:         1ms
  └─ Response:           1ms

Pattern Learning:        50-200ms
  ├─ Hash generation:    5ms
  ├─ MongoDB write:      30-100ms
  ├─ ClickHouse write:   10-50ms
  └─ Index update:       5-50ms

Pattern Matching:        100-500ms
  ├─ Candidate retrieval: 50-200ms
  ├─ Similarity calc:     30-200ms
  ├─ Ranking:            10-50ms
  └─ Formatting:         10-50ms
```

## Related Documentation

- [Architecture Overview](architecture.md)
- [Design Patterns](design-patterns.md)
- [Performance Profiling](performance-profiling.md)
- [Database Management](database-management.md)

---

**Last Updated**: November 2025
**KATO Version**: 3.0+
