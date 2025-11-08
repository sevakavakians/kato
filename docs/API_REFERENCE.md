# KATO API Reference

Complete API documentation for the KATO FastAPI service.

## Base URLs

- KATO Service: `http://localhost:8000`

## Interactive Documentation

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Core Endpoints

### Health Check

```http
GET /health
```

Returns service health status.

**Response:**
```json
{
  "status": "healthy",
  "session_id": "default",
  "uptime": 123.45
}
```

### Status

```http
GET /status
```

Returns detailed processor status.

**Response Model: `ProcessorStatus`**
```json
{
  "status": "okay",
  "session_id": "default",
  "processor_name": "PrimaryProcessor",
  "uptime": 123.45,
  "stm_length": 3,
  "time": 42
}
```

### Observe

```http
POST /observe
```

Processes an observation and adds it to short-term memory.

**Request Model: `ObservationData`**
```json
{
  "strings": ["hello", "world"],      // Required: String symbols to observe
  "vectors": [[0.1, 0.2, ...]],      // Optional: 768-dim vectors
  "emotives": {"joy": 0.8},          // Optional: Dict[str, float] - emotional/utility values
  "metadata": {"book": "Alice"},     // Optional: Dict[str, Any] - contextual tags/attributes
  "unique_id": "obs-123"              // Optional: Tracking identifier
}
```

**Response Model: `ObservationResult`**
```json
{
  "status": "okay",
  "session_id": "default",
  "auto_learned_pattern": "PTRN|abc123...",  // If auto-learning triggered
  "time": 43,
  "unique_id": "obs-123"
}
```

**Notes:**
- Vectors are converted to symbolic representations (e.g., `VCTR|<hash>`)
- Symbols within events are sorted alphabetically if SORT=true
- Auto-learning triggers when STM length reaches MAX_PATTERN_LENGTH

### Get Short-Term Memory

```http
GET /stm
GET /short-term-memory  # Alias
```

Returns current short-term memory state.

**Response Model: `STMResponse`**
```json
{
  "stm": [
    ["hello", "world"],
    ["foo", "bar"]
  ],
  "session_id": "primary"
}
```

### Learn

```http
POST /learn
```

Learns a pattern from current short-term memory.

**Response Model: `LearnResult`**
```json
{
  "pattern_name": "PTRN|7f3a2b1c...",
  "session_id": "default",
  "message": "Learned pattern: PTRN|7f3a2b1c..."
}
```

**Notes:**
- Emotives accumulated in STM are averaged and stored with the pattern
- Pattern emotives are maintained as rolling window arrays (size = PERSISTENCE)
- When patterns are re-learned, oldest emotive values drop off
- Metadata accumulated in STM is merged with unique string lists (set-union)
- Pattern metadata persists indefinitely and accumulates across re-learning
- Returns empty pattern_name if STM has < 2 strings
- Pattern name format: `PTRN|<sha1_hash>`
- Clears STM after learning

### Get Predictions

```http
GET /predictions
POST /predictions
GET /predictions?unique_id=<observation_id>
```

Returns predictions based on current STM or specific observation.

**Response Model: `PredictionsResponse`**
```json
{
  "predictions": [
    {
      "name": "PTRN|abc123...",
      "frequency": 5,
      "matches": ["hello", "world"],
      "missing": ["foo"],
      "extras": ["bar"],
      "past": [["previous"]],
      "present": [["hello", "world"]],
      "future": [["next"]],
      "evidence": 0.8,
      "confidence": 0.7,
      "similarity": 0.85,
      "snr": 0.9,
      "fragmentation": 1,
      "emotives": {"joy": 0.5},      // Averaged emotives from learned pattern
      "metadata": {"book": ["Alice", "Wonderland"]},  // Accumulated metadata from pattern
      "predictive_information": 0.75,  // Information-theoretic predictive value
      "potential": 0.6375,             // similarity * predictive_information
      "normalized_entropy": 0.3,
      "global_normalized_entropy": 0.4,
      "confluence": 0.6
    }
  ],
  "future_potentials": [             // Optional: aggregate future predictions
    {
      "future": [["next"]],
      "aggregate_potential": 0.85,
      "supporting_patterns": 3,
      "total_weighted_frequency": 12.5
    }
  ],
  "session_id": "primary"
}
```

### Clear STM

```http
POST /clear-stm
POST /clear-short-term-memory  # Alias
```

Clears short-term memory only.

**Response Model: `StatusResponse`**
```json
{
  "status": "okay",
  "message": "stm-cleared",
  "session_id": "primary"
}
```

### Clear All Memory

```http
POST /clear-all
POST /clear-all-memory  # Alias
```

Clears all memory (STM and long-term patterns).

**Response Model: `StatusResponse`**
```json
{
  "status": "okay",
  "message": "all-cleared",
  "session_id": "primary"
}
```

## Advanced Endpoints

### Get Pattern

```http
GET /pattern/{pattern_id}
```

Retrieves a specific pattern by ID.

**Parameters:**
- `pattern_id`: Pattern identifier (with or without `PTRN|` prefix)

**Response Model: `PatternResponse`**
```json
{
  "pattern": {
    "name": "PTRN|abc123...",
    "pattern_data": [["a"], ["b", "c"]],
    "frequency": 3,
    "emotives": {"confidence": [0.8, 0.7, 0.9]},  // Rolling window arrays per emotive
    "metadata": {"book": ["Alice", "Wonderland"], "chapter": ["1", "2"]},  // Unique string lists
    "length": 3
  },
  "session_id": "primary"
}
```

### Update Genes

```http
POST /genes/update
```

Updates processor configuration parameters.

**Request Model: `GeneUpdates`**
```json
{
  "genes": {
    "recall_threshold": 0.5,
    "max_predictions": 50,
    "persistence": 10,
    "max_pattern_length": 4,
    "stm_mode": "ROLLING",
    "rank_sort_algo": "similarity"
  }
}
```

**Rolling Window Example:**
```json
{
  "genes": {
    "max_pattern_length": 3,
    "stm_mode": "ROLLING"
  }
}
```
This enables continuous learning where every new observation after reaching 3 events will trigger pattern learning while maintaining a sliding window of the last 2 events.

**Available Genes:**
- `recall_threshold`: Pattern matching threshold (0.0-1.0)
- `max_predictions`: Maximum predictions to return
- `persistence`: Rolling window size for emotive values per pattern
- `max_pattern_length`: Auto-learn threshold (0 = manual only)
- `stm_mode`: Short-term memory mode ('CLEAR' or 'ROLLING')
- `rank_sort_algo`: Prediction ranking metric ('potential', 'similarity', 'evidence', 'confidence', 'snr', 'frequency', 'fragmentation', 'normalized_entropy', 'global_normalized_entropy', 'itfdf_similarity', 'confluence', 'predictive_information')
- `process_predictions`: Enable/disable prediction processing (true/false)
- And others (see Configuration guide)

### Get Gene

```http
GET /gene/{gene_name}
```

Retrieves current value of a specific gene.

**Response:**
```json
{
  "gene_name": "recall_threshold",
  "gene_value": 0.1,
  "session_id": "primary"
}
```

### Get Percept Data

```http
GET /percept-data
```

Returns last received observation data (input perception).

**Response:**
```json
{
  "percept_data": {
    "strings": ["last", "observation"],
    "vectors": [],
    "emotives": {},
    "path": ["source-path"],
    "metadata": {}
  },
  "session_id": "primary"
}
```

### Get Cognition Data

```http
GET /cognition-data
```

Returns current cognitive state.

**Response:**
```json
{
  "cognition_data": {
    "predictions": [...],
    "emotives": {"current": 0.5},
    "symbols": ["active", "symbols"],
    "command": "last-command",
    "metadata": {},
    "path": [],
    "strings": [],
    "vectors": [],
    "short_term_memory": [["stm", "events"]]
  },
  "session_id": "primary"
}
```

### Get Metrics

```http
GET /metrics
```

Returns processor performance metrics.

**Response:**
```json
{
  "session_id": "default",
  "observations_processed": 1234,
  "patterns_learned": 56,
  "stm_size": 3,
  "uptime_seconds": 3600.5
}
```

## WebSocket Endpoint

```http
WS /ws
```

Establishes WebSocket connection for real-time bidirectional communication.

### Message Types

#### Observe
```json
{
  "type": "observe",
  "payload": {
    "strings": ["hello"],
    "vectors": [],
    "emotives": {},
    "metadata": {"source": "chat"}
  }
}
```

#### Get STM
```json
{
  "type": "get_stm",
  "payload": {}
}
```

#### Get Predictions
```json
{
  "type": "get_predictions",
  "payload": {
    "unique_id": "optional-id"
  }
}
```

#### Learn
```json
{
  "type": "learn",
  "payload": {}
}
```

#### Clear STM
```json
{
  "type": "clear_stm",
  "payload": {}
}
```

#### Clear All
```json
{
  "type": "clear_all",
  "payload": {}
}
```

#### Ping
```json
{
  "type": "ping",
  "payload": {}
}
```

### Response Format

All WebSocket responses follow this format:
```json
{
  "type": "response_type",
  "data": {
    // Response data
  }
}
```

## Error Responses

All errors follow a consistent format:

```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable error message",
    "details": {
      // Additional error context
    }
  },
  "status": 400
}
```

Common HTTP status codes:
- `400`: Bad Request - Invalid input
- `404`: Not Found - Resource not found
- `500`: Internal Server Error
- `503`: Service Unavailable - Processor not initialized

## Data Types

### ObservationData
- `strings`: List[str] - String symbols to observe
- `vectors`: List[List[float]] - Optional 768-dim vectors
- `emotives`: Dict[str, float] - Optional emotional values
- `metadata`: Dict[str, Any] - Optional contextual tags/attributes (stored as unique string lists)
- `unique_id`: Optional[str] - Tracking identifier

### Prediction Fields
- `name`: Pattern identifier (PTRN|hash)
- `frequency`: Number of times pattern learned
- `matches`: Symbols matching observation
- `missing`: Symbols in pattern but not observed
- `extras`: Observed symbols not in pattern
- `past`: Events before first match
- `present`: Events containing matches
- `future`: Events after last match
- `evidence`: Strength of pattern match (0-1)
- `confidence`: Ratio of matches to present length (0-1)
- `similarity`: Overall pattern similarity (0-1)
- `snr`: Signal-to-noise ratio
- `fragmentation`: Pattern cohesion measure
- `emotives`: Emotional/utility values (averaged from pattern)
- `metadata`: Contextual tags/attributes (unique string lists from pattern)
- `predictive_information`: Information-theoretic predictive value (0-1)
- `potential`: Information-theoretic ranking metric (similarity × predictive_information)
- `normalized_entropy`: Entropy-like complexity measure
- `global_normalized_entropy`: Extended normalized entropy
- `confluence`: Probability vs random chance

### Future Potentials Fields (Optional Response)
- `future`: The predicted future event sequence
- `aggregate_potential`: Combined potential of all patterns predicting this future (0-1)
- `supporting_patterns`: Number of patterns that predict this future
- `total_weighted_frequency`: Sum of frequency × similarity for supporting patterns

## Predictive Information User Guide

### Understanding Predictive Information Values

**Predictive Information (PI)** measures how much information a pattern provides about its future outcomes. This information-theoretic metric helps rank predictions based on their reliability and usefulness.

### Key Concepts

#### 1. **Predictive Information Range: 0.0 to 1.0**
- **0.0**: Pattern provides no predictive information about the future
- **0.5**: Pattern provides moderate predictive information  
- **1.0**: Pattern provides maximum predictive information (rare, indicates strong predictive relationship)

#### 2. **New Potential Formula**
```
potential = similarity × predictive_information
```
- **similarity**: How well the pattern matches your current observation (0.0-1.0)
- **predictive_information**: How reliably this pattern predicts its future (0.0-1.0)
- **potential**: Combined ranking metric (0.0-1.0)

### Practical Usage Examples

#### Example 1: High PI Pattern
```json
{
  "name": "PTRN|abc123",
  "similarity": 0.9,
  "predictive_information": 0.8,
  "potential": 0.72,
  "frequency": 15,
  "future": [["expected_next_event"]]
}
```
**Interpretation**: This pattern matches well (90%) and has strong predictive power (80%). The high frequency (15) suggests it's been learned many times, making it very reliable.

#### Example 2: Low PI Pattern  
```json
{
  "name": "PTRN|def456",
  "similarity": 0.85,
  "predictive_information": 0.2,
  "potential": 0.17,
  "frequency": 2,
  "future": [["uncertain_outcome"]]
}
```
**Interpretation**: Although this pattern matches reasonably well (85%), it has low predictive power (20%) and low frequency (2), making it less reliable for prediction.

### Using Future Potentials

The `future_potentials` field aggregates predictions across multiple patterns:

```json
"future_potentials": [
  {
    "future": [["high_confidence_outcome"]],
    "aggregate_potential": 0.85,
    "supporting_patterns": 5,
    "total_weighted_frequency": 47.3
  },
  {
    "future": [["lower_confidence_outcome"]],
    "aggregate_potential": 0.3,
    "supporting_patterns": 2,
    "total_weighted_frequency": 8.1
  }
]
```

**Best Practice**: Use futures with high `aggregate_potential` and multiple `supporting_patterns` for most reliable predictions.

### Decision-Making Guidelines

1. **Primary Ranking**: Sort predictions by `potential` (descending) for best overall predictions
2. **Reliability Check**: Consider both `predictive_information` and `frequency` for confidence assessment
3. **Future Planning**: Use `future_potentials` to identify most likely outcomes across all patterns
4. **Threshold Setting**: Patterns with PI < 0.3 may be unreliable for critical decisions

### Information-Theoretic Foundation

Predictive Information is based on **Excess Entropy** from information theory, measuring mutual information between past and future sequence segments. Higher values indicate stronger statistical dependencies and more reliable predictions.

For theoretical details, see: `docs/PREDICTIVE_INFORMATION.md`

## Notes

1. **Pattern Naming**: All patterns use format `PTRN|<sha1_hash>` where hash is SHA1 of pattern data
2. **Minimum Prediction Requirement**: STM must contain at least 2 strings total to generate predictions
3. **Sorting**: Symbols within events are sorted alphabetically when SORT=true (default)
4. **Auto-Learning**: Triggers when STM reaches MAX_PATTERN_LENGTH (if > 0)
5. **Recall Threshold**: Controls pattern matching sensitivity (0.0 = all patterns, 1.0 = exact matches only)
6. **Dynamic Calculation**: Predictive information is calculated at prediction time using ensemble statistics