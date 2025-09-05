# observe-sequence Endpoint Documentation

## Overview
The `/observe-sequence` endpoint enables efficient batch processing of multiple observations in a single API call. This endpoint is designed for high-throughput scenarios where multiple events need to be processed sequentially or in isolation.

## Important Conceptual Clarification

**The `/observe-sequence` endpoint processes an array of single-event observations, NOT full sequences.**

Each "observation" in the array represents:
- **One temporal event** (a single moment in time)
- A collection of strings that occur together at that moment
- Optional vectors and emotional values for that event

## API Specification

### Endpoint
`POST /observe-sequence`

### Request Body
```json
{
  "observations": [
    {
      "strings": ["string1", "string2"],
      "vectors": [[0.1, 0.2, ...]],  // 768-dimensional vectors
      "emotives": {"joy": 0.8},
      "unique_id": "optional-custom-id"
    }
  ],
  "learn_after_each": false,    // Learn pattern after each single event
  "learn_at_end": false,         // Learn pattern from accumulated sequence  
  "clear_stm_between": false    // Clear STM between events for isolation
}
```

### Response
```json
{
  "status": "okay",
  "processor_id": "primary",
  "observations_processed": 3,
  "patterns_learned": ["PTRN|abc123..."],
  "individual_results": [
    {
      "status": "okay",
      "processor_id": "primary",
      "auto_learned_pattern": null,
      "time": 1,
      "unique_id": "obs-1-..."
    }
  ],
  "final_predictions": [...]
}
```

## Behavioral Modes

### 1. Sequence Building Mode (Default)
**Settings**: `clear_stm_between=false`

This mode accumulates events into a temporal sequence:

```python
# Input
observations = [
  {"strings": ["user", "login"]},     # Event at T=0
  {"strings": ["user", "browse"]},    # Event at T=1
  {"strings": ["user", "purchase"]}   # Event at T=2
]

# STM Evolution (without learning)
After Event 1: [["login", "user"]]
After Event 2: [["login", "user"], ["browse", "user"]]
After Event 3: [["login", "user"], ["browse", "user"], ["purchase", "user"]]

# Result: A 3-event sequence representing user behavior over time
# Note: If learning is triggered, STM will be empty after learning
```

### 2. Isolated Processing Mode
**Settings**: `clear_stm_between=true`

Each event is processed independently without context from previous events:

```python
# Input
observations = [
  {"strings": ["sensor1", "alert"]},
  {"strings": ["sensor2", "normal"]},
  {"strings": ["sensor3", "warning"]}
]

# STM Evolution (without learning)
Process Event 1: [["alert", "sensor1"]] → Clear
Process Event 2: [["normal", "sensor2"]] → Clear
Process Event 3: [["sensor3", "warning"]]

# Result: Each sensor reading processed independently
# Note: Final STM contains only the last event (unless learning is triggered)
```

## Learning Options

### learn_after_each
When `true`, a pattern is learned after processing each individual event:
- 3 events → 3 separate patterns
- Each pattern represents a single event
- STM is cleared after each learning operation
- Useful for: Learning individual behaviors or states

### learn_at_end
When `true`, a single pattern is learned from all accumulated events:
- 3 events → 1 combined pattern
- Pattern represents the entire sequence
- STM is cleared after learning (empty at the end)
- Useful for: Learning temporal sequences or workflows

### Combined Options
You can combine options for complex scenarios:
```json
{
  "clear_stm_between": true,
  "learn_after_each": true
}
```
Result: Each event is isolated AND learned as its own pattern. STM will be empty after processing.

## Use Cases

### 1. User Behavior Tracking
Track a sequence of user actions:
```python
observations = [
  {"strings": ["page_view", "homepage"]},
  {"strings": ["click", "product_A"]},
  {"strings": ["add_to_cart", "product_A"]},
  {"strings": ["checkout", "complete"]}
]
# Process with learn_at_end=true to learn the purchase journey
```

### 2. Sensor Data Processing
Process independent sensor readings:
```python
observations = [
  {"strings": ["temp_sensor", "25C"], "emotives": {"alert": 0.0}},
  {"strings": ["pressure_sensor", "1013hPa"], "emotives": {"alert": 0.0}},
  {"strings": ["humidity_sensor", "45%"], "emotives": {"alert": 0.2}}
]
# Process with clear_stm_between=true for independent analysis
```

### 3. Time Series Analysis
Build temporal patterns from time series data:
```python
observations = [
  {"strings": ["stock_AAPL", "up"], "vectors": [market_embedding]},
  {"strings": ["stock_AAPL", "up"], "vectors": [market_embedding]},
  {"strings": ["stock_AAPL", "down"], "vectors": [market_embedding]}
]
# Process without isolation to capture temporal dependencies
```

### 4. Batch Document Processing
Process multiple documents efficiently:
```python
observations = [
  {"strings": doc1_keywords, "vectors": [doc1_embedding]},
  {"strings": doc2_keywords, "vectors": [doc2_embedding]},
  {"strings": doc3_keywords, "vectors": [doc3_embedding]}
]
# Process with clear_stm_between=true and learn_after_each=true
# to learn each document independently
```

## Performance Considerations

1. **Batch Size**: Optimal batch size is 10-100 observations
2. **Memory**: Large batches without STM clearing may exceed persistence limits
3. **Latency**: Single batch call is more efficient than multiple individual calls
4. **Isolation**: Using `clear_stm_between` prevents memory accumulation

## Important Notes

1. **Alphanumeric Sorting**: Strings within each event are automatically sorted alphanumerically
2. **Vector Processing**: Vectors are converted to symbolic names (VCTR|hash) in STM
3. **Persistence Limits**: Default STM persistence is 5 events (configurable)
4. **Pattern Naming**: Learned patterns follow the format PTRN|<sha1_hash>
5. **Deterministic**: Same inputs always produce same outputs
6. **Learning Clears STM**: Any learning operation (learn_after_each or learn_at_end) always clears STM

## Error Handling

The endpoint returns HTTP 500 for:
- Invalid vector dimensions (must be 768D)
- Missing required fields
- Processing errors

## Example Implementation

```python
import requests

# Build a user session sequence
user_session = {
    "observations": [
        {"strings": ["login", "user123"]},
        {"strings": ["search", "laptops"]},
        {"strings": ["filter", "price_low"]},
        {"strings": ["click", "product_xyz"]},
        {"strings": ["purchase", "product_xyz"]}
    ],
    "learn_at_end": True  # Learn the complete purchase pattern
}

response = requests.post(
    "http://localhost:8001/observe-sequence",
    json=user_session
)

if response.status_code == 200:
    result = response.json()
    print(f"Processed {result['observations_processed']} events")
    if result['patterns_learned']:
        print(f"Learned pattern: {result['patterns_learned'][0]}")
    if result['final_predictions']:
        print(f"Generated {len(result['final_predictions'])} predictions")
```

## See Also
- `/observe` - Single event observation
- `/learn` - Manual pattern learning
- `/predictions` - Get predictions from current STM
- `/stm` - View current short-term memory state