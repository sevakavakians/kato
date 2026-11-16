# KATO API Reference

Complete API documentation for the KATO FastAPI service.

## Base URLs

- KATO Service: `http://localhost:8000`

## Interactive Documentation

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## ⚠️ IMPORTANT: Session-Based API Required

**As of Phase 3 (2025-10-06), all core KATO operations require session-based endpoints.**

Direct endpoints (`/observe`, `/learn`, `/predictions`, etc.) have been **permanently removed**. This migration ensures:
- ✅ Proper state isolation between users
- ✅ Multi-user support with concurrent access
- ✅ Configuration per session
- ✅ Redis-backed session persistence

See [API Migration Guide](migration-guides/api-migration.md) for migration instructions.

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

### Session Management

#### Create Session

```http
POST /sessions
```

Creates a new isolated session for a user or application.

**Request Model: `CreateSessionRequest`**
```json
{
  "node_id": "user_alice",              // Required: Node identifier
  "config": {                            // Optional: Session-specific configuration
    "recall_threshold": 0.5,
    "max_predictions": 100
  },
  "ttl_seconds": 3600,                   // Optional: Session TTL (default: 3600)
  "metadata": {}                         // Optional: Custom metadata
}
```

**Response Model: `SessionResponse`**
```json
{
  "session_id": "session-abc123...",
  "node_id": "user_alice",
  "created_at": "2025-11-11T12:00:00Z",
  "expires_at": "2025-11-11T13:00:00Z",
  "ttl_seconds": 3600,
  "session_config": {}
}
```

### Observe (Session-Based)

```http
POST /sessions/{session_id}/observe
```

Processes an observation and adds it to the session's short-term memory.

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
  "auto_learned_pattern": "abc123def456...",  // If auto-learning triggered
  "time": 43,
  "unique_id": "obs-123"
}
```

**Notes:**
- Vectors are converted to symbolic representations (e.g., `VCTR|<hash>`)
- Symbols within events are sorted alphabetically if SORT_SYMBOLS=true
- Auto-learning triggers when STM length reaches MAX_PATTERN_LENGTH

### Get Short-Term Memory (Session-Based)

```http
GET /sessions/{session_id}/stm
```

Returns the session's current short-term memory state.

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

### Learn (Session-Based)

```http
POST /sessions/{session_id}/learn
```

Learns a pattern from the session's current short-term memory.

**Response Model: `LearnResult`**
```json
{
  "pattern_name": "7f3a2b1c4d5e6f7890123456789abcdef0123456",
  "session_id": "default",
  "message": "Learned pattern 7f3a2b1c4d5e6f7890123456789abcdef0123456 from 2 events"
}
```

**Notes:**
- Emotives accumulated in STM are averaged and stored with the pattern
- Pattern emotives are maintained as rolling window arrays (size = PERSISTENCE)
- When patterns are re-learned, oldest emotive values drop off
- Metadata accumulated in STM is merged with unique string lists (set-union)
- Pattern metadata persists indefinitely and accumulates across re-learning
- Returns no predictions if STM has < 1 string
- Pattern name format: plain SHA1 hash (no `PTRN|` prefix)
- Clears STM after learning

### Get Predictions (Session-Based)

```http
GET /sessions/{session_id}/predictions
GET /sessions/{session_id}/predictions?unique_id=<observation_id>
```

Returns predictions based on the session's current STM or specific observation.

**Response Model: `PredictionsResponse`**

The example is a node that has learned `login, browse, checkout` five times, `login, browse, logout` three times and `login, reset_password, logout` twice, with `login` and `browse` observed. The first of the three predictions is shown; values are rounded to four decimals.

```json
{
  "predictions": [
    {
      "name": "a629167ef78bdb4dee0784c40fe2b39a4ffd207d",
      "type": "prototypical",
      "frequency": 5,
      "matches": ["login", "browse"],
      "missing": [[], []],
      "extras": [[], []],
      "anomalies": [],
      "fuzzy_matches": [],
      "past": [],
      "present": [["login"], ["browse"]],
      "future": [["checkout"]],
      "sequence": [["login"], ["browse"], ["checkout"]],
      "evidence": 0.6667,
      "confidence": 1.0,
      "similarity": 0.8,
      "snr": 1.0,
      "fragmentation": 0.0,
      "event_cohesion": 1.0,
      "onset_alignment": 1.0,
      "emotives": {},
      "potential": 17.1968,
      "good_odds": 2.3439,
      "bayesian_prior": 0.5,
      "bayesian_likelihood": 3.3439,
      "bayesian_posterior": 0.5548,
      "predictive_information": 1.0627,
      "confluence": 5.0768,
      "entropy": 1.585,
      "normalized_entropy": 0.6826,
      "global_normalized_entropy": 0.3955,
      "itfdf_similarity": 1.0,
      "tfidf_score": 0.5744,
      "weighted_similarity": null,
      "weighted_evidence": null,
      "weighted_confidence": null,
      "weighted_snr": null
    }
  ],
  "future_potentials": [             // Probability of each next event, over every candidate
    {"next_event": ["checkout"], "probability": 0.5859, "supporting_patterns": 1},
    {"next_event": ["logout"], "probability": 0.414, "supporting_patterns": 1},
    {"next_event": ["reset_password"], "probability": 0.0001, "supporting_patterns": 1}
  ],
  "ends_here": 0.0,                  // Probability that no event follows
  "chance_posterior": 0.1093,        // Probability that no learned pattern explains the STM better than chance
  "session_id": "primary",
  "count": 3
}
```

### Clear STM (Session-Based)

```http
POST /sessions/{session_id}/clear-stm
```

Clears the session's short-term memory only.

**Response Model: `StatusResponse`**
```json
{
  "status": "okay",
  "message": "stm-cleared",
  "session_id": "primary"
}
```

### Clear All Memory (Session-Based)

```http
POST /sessions/{session_id}/clear-all
```

Clears all session memory (STM and long-term patterns for this node).

**Response Model: `StatusResponse`**
```json
{
  "status": "okay",
  "message": "all-cleared",
  "session_id": "primary"
}
```

### Retire Patterns

```http
POST /sessions/{session_id}/patterns/retire
```

Hides learned patterns from every read path without deleting them. Node-scoped,
durable, idempotent and reversible.

**Request Body:**
```json
{"pattern_ids": ["abc123def456789012345678901234567890abcd"]}
```

1–1000 IDs, with or without the `PTRN|` prefix. A malformed ID is a `422`.

**Response Model: `RetirePatternsResponse`**
```json
{
  "status": "okay",
  "session_id": "primary",
  "node_id": "my-node",
  "requested": 1,
  "retired": ["abc123def456789012345678901234567890abcd"],
  "already_retired": []
}
```

Learning a sequence whose pattern is retired returns `409` with code
`RETIRED_PATTERN`.

### Un-Retire Patterns

```http
POST /sessions/{session_id}/patterns/un-retire
```

Removes tombstones, making the patterns visible and learnable again. Same request
body as retire.

**Response Model: `UnRetirePatternsResponse`**
```json
{
  "status": "okay",
  "session_id": "primary",
  "node_id": "my-node",
  "requested": 1,
  "un_retired": ["abc123def456789012345678901234567890abcd"],
  "not_retired": []
}
```

### Purge Patterns

```http
POST /sessions/{session_id}/patterns/purge
```

Permanently deletes retired patterns and subtracts their contribution to the
node's statistics. **Irreversible.** Only a retired pattern can be purged.

**Request Body:**
```json
{"pattern_ids": ["abc123def456789012345678901234567890abcd"], "max_patterns": 1000}
```

Both fields are optional. Omit `pattern_ids` to purge every retired pattern on the
node; `max_patterns` (1–10000, default 1000) bounds one call.

**Response Model: `PurgePatternsResponse`**
```json
{
  "status": "completed",
  "session_id": "primary",
  "node_id": "my-node",
  "purged": ["abc123def456789012345678901234567890abcd"],
  "failed": {},
  "remaining": 0
}
```

`status` is `partial` when some IDs could not be purged, with a reason per ID in
`failed`; purge is resumable, so re-issuing the call retries them. `remaining`
counts retired patterns still awaiting a purge.

The tombstone survives a purge, so learning the same sequence still returns `409`
until it is un-retired. Purging also invalidates the node's precomputed entropy
metrics; predictions stay correct, and `finalize-training` restores the
precomputation. See [pattern retirement and purging](pattern-retirement.md).

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
    "name": "abc123def456789012345678901234567890abcd",
    "pattern_data": [["a"], ["b", "c"]],
    "frequency": 3,
    "emotives": {"confidence": [0.8, 0.7, 0.9]},  // Rolling window arrays per emotive
    "metadata": {"book": ["Alice", "Wonderland"], "chapter": ["1", "2"]},  // Unique string lists
    "length": 3
  },
  "session_id": "primary"
}
```

### Update Session Config

```http
POST /sessions/{session_id}/config
```

Updates session configuration parameters.

**Request Body:**
```json
{
  "config": {
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
  "config": {
    "max_pattern_length": 3,
    "stm_mode": "ROLLING"
  }
}
```
This enables continuous learning where every new observation after reaching 3 events will trigger pattern learning while maintaining a sliding window of the last 2 events.

**Available Configuration Parameters:**
- `recall_threshold`: Pattern matching threshold (>0.0-1.0)
- `max_predictions`: Maximum predictions to return
- `persistence`: Rolling window size for emotive values per pattern
- `max_pattern_length`: Auto-learn threshold (0 = manual only)
- `stm_mode`: Short-term memory mode ('CLEAR' or 'ROLLING')
- `rank_sort_algo`: Prediction ranking metric. Any numeric metric of a prediction: 'potential' (default), 'good_odds', 'similarity', 'evidence', 'confidence', 'snr', 'fragmentation', 'frequency', 'bayesian_posterior', 'bayesian_prior', 'bayesian_likelihood', 'predictive_information', 'confluence', 'entropy', 'normalized_entropy', 'global_normalized_entropy', 'tfidf_score', 'itfdf_similarity', 'event_cohesion', 'onset_alignment', 'weighted_similarity', 'weighted_evidence', 'weighted_confidence', 'weighted_snr'
- `process_predictions`: Enable/disable prediction processing (true/false)
- And others (see Configuration guide)

### Get Session Config

```http
GET /sessions/{session_id}/config
```

Retrieves effective configuration for a session (session overrides merged with system defaults).

**Response:**
```json
{
  "session_id": "abc123",
  "config": {
    "recall_threshold": 0.1,
    "max_predictions": 100,
    "rank_sort_algo": "potential"
  }
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
  "timestamp": 1790859484.95,
  "databases": {"clickhouse": {}, "qdrant": {}, "redis": {}},
  "performance": {
    "total_requests": 0,
    "total_errors": 0,
    "error_rate": 0.0,
    "average_response_time": 0.0
  },
  "rates": {"requests_per_second": 0.0, "requests_per_minute": 0.0, "errors_per_minute": 0.0},
  "resources": {"cpu_percent": 0.0, "memory_percent": 0.0, "disk_percent": 0.0},
  "sessions": {"active": 0, "total_created": 0, "total_deleted": 0, "operations_total": 0},
  "processor_manager": {
    "total_processors": 0,
    "max_processors": 0,
    "eviction_ttl_seconds": 0,
    "processors": []
  },
  "active_sessions": null,
  "uptime_seconds": null,
  "error": null
}
```

These are service-wide counters, not per-session. `active_sessions` and
`uptime_seconds` may be `null`; use `GET /sessions/count` and `GET /health`
respectively for those. Fetch the endpoint on a running service for the current
shape rather than relying on this sample.

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
- `name`: Pattern identifier (plain SHA1 hash)
- `type`: Prediction type (always "prototypical")
- `frequency`: Number of times pattern learned
- `matches`: Symbols matching observation (flat list)
- `missing`: Symbols in pattern but not observed (event-aligned with present)
- `extras`: Observed symbols not in pattern (event-aligned with STM)
- `anomalies`: Flat list of every deviating symbol — missing, then extras, then fuzzy-observed tokens
- `fuzzy_matches`: Fuzzy token matches with similarity scores (when fuzzy matching enabled)
- `past`: Events before first match
- `present`: All events from first to last match (complete events)
- `future`: Events after last match
- `evidence`: Proportion of pattern observed: `len(matches) / pattern_length` (0-1)
- `confidence`: Ratio of matches to present length: `len(matches) / total_present_length` (0-1)
- `similarity`: Overall pattern similarity (0-1)
- `snr`: Signal-to-noise ratio (-1 to 1)
- `fragmentation`: Pattern cohesion measure (0-n)
- `event_cohesion`: How much of each observed event sits together in one pattern event (0-1)
- `onset_alignment`: How early in the pattern the observed symbols occur (0-1)
- `entropy`: Shannon entropy of the pattern's symbols
- `normalized_entropy`: The pattern's entropy over the largest entropy the node's vocabulary allows (0-1)
- `global_normalized_entropy`: Entropy using global symbol probabilities
- `confluence`: How far the pattern is from a chance co-occurrence of its symbols, in bits (unbounded)
- `itfdf_similarity`: One minus the distance between the STM and `present`, the distance scaled by the pattern's share of the candidates' frequency (0-1)
- `tfidf_score`: TF-IDF pattern distinctiveness (0-~2.0)
- `potential`: Default ranking score: a weighted sum of eleven match terms (unbounded; higher is better)
- `good_odds`: Posterior log-odds of the pattern against chance, in bits: `log2(bayesian_prior) + bayesian_likelihood` (unbounded; above 0 beats chance)
- `bayesian_prior`: The pattern's share of every learn in the node: `frequency / total_pattern_frequencies` (0-1)
- `bayesian_likelihood`: Weight of evidence the observation gives for the pattern over chance, in bits (unbounded)
- `bayesian_posterior`: P(pattern|observation); with `chance_posterior`, sums to 1.0 over every candidate (0-1)
- `predictive_information`: The prediction's part of what the STM tells about the next event, in bits (unbounded; 0 with no future)
- `emotives`: Emotional/utility values (averaged from pattern)
- `weighted_similarity`: Affinity-weighted similarity (null when disabled)
- `weighted_evidence`: Affinity-weighted evidence (null when disabled)
- `weighted_confidence`: Affinity-weighted confidence (null when disabled)
- `weighted_snr`: Affinity-weighted SNR (null when disabled)

Formulas, ranges and what each metric is for: [Prediction Object Reference](../reference/prediction-object.md).

### Ensemble Fields (beside the predictions)
- `future_potentials`: The probability of each next event the candidates propose, most probable first. Each entry:
  - `next_event`: The event, a list of symbols
  - `probability`: The probability that this event comes next (the entries and `ends_here` sum to 1.0)
  - `supporting_patterns`: Number of candidates whose next event this is
- `ends_here`: The probability that no event follows (0-1): the share of the candidates' weight held by patterns that end where the observation ends. `null` when there is no candidate
- `chance_posterior`: The probability that no learned pattern explains the STM better than chance (0-1). `1.0` when nothing matched, `null` when no prediction was computed

All three are computed over every candidate above the recall threshold, not only the returned predictions.

## Reading the Scores

The numbers below are from the example response above: `login` and `browse` observed, against three learned patterns.

| Pattern (times learned) | Match | `potential` | `good_odds` | `bayesian_posterior` | Next event |
|---|---|---|---|---|---|
| `login, browse, checkout` (5) | both symbols | 17.20 | 2.34 bits | 0.555 | `checkout` |
| `login, browse, logout` (3) | both symbols | 16.85 | 1.61 bits | 0.333 | `logout` |
| `login, reset_password, logout` (2) | `login` only; `browse` is an extra | 8.11 | -5.13 bits | 0.003 | `reset_password` |

### Which prediction first: `potential`

Predictions arrive ranked by `potential`, a weighted sum of eleven terms: how alike the observation and the matched part of the pattern are, whether the newest event is explained, how recent the matches are, how much is missing or extra, how broken up the match is, and how often the pattern was learned.

- The first two patterns match identically. They differ only in frequency, which enters as `0.680 * ln(frequency)`: 5 learns against 3 is worth 0.35.
- The third matches one symbol of two and leaves the newest event unexplained. That costs 9 points.

### What comes next: `future_potentials`

```json
"future_potentials": [
  {"next_event": ["checkout"], "probability": 0.5859, "supporting_patterns": 1},
  {"next_event": ["logout"], "probability": 0.414, "supporting_patterns": 1},
  {"next_event": ["reset_password"], "probability": 0.0001, "supporting_patterns": 1}
]
```

Each candidate votes with weight `e^potential`: for its next event, or for `ends_here` when its pattern has ended. Each sum is divided by the total. Patterns that agree on the next event add up, so the list answers "what comes next" better than the top prediction alone, and `probability` is a usable confidence: a difference of 1.0 in `potential` is a factor of `e` in weight.

**Best Practice**: Read the next event from `future_potentials[0]`, and use its `probability` to decide whether to act on it.

### Nothing follows: `ends_here`

`ends_here` (0.0 here, since all three patterns go on) is the probability that no event follows: the share of the weight held by patterns that end where the observation ends. With the probabilities above it adds up to 1. When it is larger than the top `probability`, the patterns that fit the observation have nothing left to propose.

### How sure, in bits: `good_odds`

`good_odds` says how many times more probable the observation is under the pattern than under chance, as a base-2 logarithm, counting how often the pattern was learned. Above 0 the pattern beats chance. Here the first pattern is at 2.34 bits (about 5 to 1 in its favour) and the third at -5.13 bits (35 to 1 against).

`bayesian_posterior` turns those odds into probabilities over the candidates and chance together: 0.555, 0.333 and 0.003, with 0.109 left for chance.

### "I don't know": `chance_posterior`

`chance_posterior` (0.109 here) is the probability that none of the learned patterns explains the observation better than chance. When nothing matches, `predictions` is empty and `chance_posterior` is 1.0. When something matches weakly, predictions come back with a `chance_posterior` near 1.0: treat that the same way.

### How much the observation tells: `predictive_information`

In bits. The values of a request add up to the information the STM carries about the next event, measured against chance: 1.063 + 0.544 - 0.001 = 1.606 bits here. A context that pins the next event down to one rare event carries many bits; one that leaves several common events open carries few. A prediction with no `future` has 0.

### Decision-Making Guidelines

1. **Primary Ranking**: Predictions are sorted by `potential` (descending) by default
2. **Next Event**: Take it from `future_potentials`, with `probability` as the confidence
3. **Abstaining**: Decline to answer when `chance_posterior` is high or the top `probability` is low. When `ends_here` exceeds the top `probability`, the answer is that nothing follows
4. **Explaining a Score**: `good_odds`, `bayesian_prior` and `bayesian_likelihood` break a match into how often the pattern was learned and how strongly the observation supports it, in bits

For the formulas and what each metric is for, see the [Prediction Object Reference](../reference/prediction-object.md).

## Notes

1. **Pattern Naming**: Pattern names are plain SHA1 hashes of pattern data (the `PTRN|` prefix only appears in display/repr output)
2. **Minimum Prediction Requirement**: STM must contain at least 1 string to generate predictions (single-symbol uses optimized fast path)
3. **Sorting**: Symbols within events are sorted alphabetically when SORT_SYMBOLS=true (default)
4. **Auto-Learning**: Triggers when STM reaches MAX_PATTERN_LENGTH (if > 0)
5. **Recall Threshold**: Controls pattern matching sensitivity. Must be greater than 0.0 (a threshold of 0 accepts every pattern regardless of similarity and is rejected); values near 0 are very permissive, 1.0 means exact matches only
6. **Dynamic Calculation**: Predictive information is calculated at prediction time using ensemble statistics