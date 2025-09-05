# KATO API Reference

Complete API documentation for the KATO FastAPI service.

## Base URLs

- Primary Instance: `http://localhost:8001`
- Testing Instance: `http://localhost:8002`
- Analytics Instance: `http://localhost:8003`

## Interactive Documentation

- Swagger UI: `http://localhost:8001/docs`
- ReDoc: `http://localhost:8001/redoc`

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
  "processor_id": "primary",
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
  "processor_id": "primary",
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
  "emotives": {"joy": 0.8},          // Optional: Emotional/utility values
  "unique_id": "obs-123"              // Optional: Tracking identifier
}
```

**Response Model: `ObservationResult`**
```json
{
  "status": "okay",
  "processor_id": "primary",
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
  "processor_id": "primary"
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
  "processor_id": "primary",
  "message": "Learned pattern: PTRN|7f3a2b1c..."
}
```

**Notes:**
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
      "emotives": {"joy": 0.5},
      "potential": 2.5,
      "hamiltonian": 0.3,
      "grand_hamiltonian": 0.4,
      "confluence": 0.6
    }
  ],
  "processor_id": "primary"
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
  "processor_id": "primary"
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
  "processor_id": "primary"
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
    "emotives": {"confidence": 0.8},
    "length": 3
  },
  "processor_id": "primary"
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
    "persistence": 10
  }
}
```

**Available Genes:**
- `recall_threshold`: Pattern matching threshold (0.0-1.0)
- `max_predictions`: Maximum predictions to return
- `persistence`: STM persistence length
- `smoothness`: Pattern matching smoothness
- `quiescence`: Quiescence period
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
  "processor_id": "primary"
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
  "processor_id": "primary"
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
  "processor_id": "primary"
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
  "processor_id": "primary",
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
    "emotives": {}
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
- `emotives`: Emotional/utility values
- `potential`: Composite ranking metric
- `hamiltonian`: Entropy-like complexity measure
- `grand_hamiltonian`: Extended hamiltonian
- `confluence`: Probability vs random chance

## Notes

1. **Pattern Naming**: All patterns use format `PTRN|<sha1_hash>` where hash is SHA1 of pattern data
2. **Minimum Prediction Requirement**: STM must contain at least 2 strings total to generate predictions
3. **Sorting**: Symbols within events are sorted alphabetically when SORT=true (default)
4. **Auto-Learning**: Triggers when STM reaches MAX_PATTERN_LENGTH (if > 0)
5. **Recall Threshold**: Controls pattern matching sensitivity (0.0 = all patterns, 1.0 = exact matches only)