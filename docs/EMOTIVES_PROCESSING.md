# KATO Emotives Processing System

## Table of Contents
1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Processing Pipeline](#processing-pipeline)
4. [Storage Mechanism](#storage-mechanism)
5. [Averaging Algorithm](#averaging-algorithm)
6. [PERSISTENCE Parameter](#persistence-parameter)
7. [Configuration](#configuration)
8. [Examples](#examples)
9. [Best Practices](#best-practices)
10. [Troubleshooting](#troubleshooting)

## Overview

Emotives in KATO are **emotional or utility values** that provide contextual metadata for patterns. They represent subjective dimensions like emotions, preferences, utilities, or any continuous valued attributes that accompany observations.

### Key Concepts
- **Format**: Dictionary mapping string keys to float values
- **Purpose**: Capture contextual state during observations
- **Association**: Stored with learned patterns, not individual observations
- **Temporal**: Maintain rolling history limited by PERSISTENCE parameter
- **Averaging**: Multiple values averaged rather than summed

### Design Philosophy
Emotives are designed to capture **persistent states** rather than cumulative values. This is why KATO uses averaging instead of summation - an emotional state like "happiness" shouldn't double just because two observations occur.

## Architecture

The emotives processing system flows through multiple components:

```
┌─────────────────────────────────────────────┐
│          Input Observation                  │
│     {"joy": 0.8, "arousal": -0.3}          │
└─────────────────┬───────────────────────────┘
                  │
┌─────────────────▼───────────────────────────┐
│       ObservationProcessor                  │
│   • Validates emotive format                │
│   • Ensures float values                    │
└─────────────────┬───────────────────────────┘
                  │
┌─────────────────▼───────────────────────────┐
│          MemoryManager                      │
│   • Adds to emotives accumulator list       │
│   • Maintains current_emotives (averaged)   │
└─────────────────┬───────────────────────────┘
                  │
┌─────────────────▼───────────────────────────┐
│        PatternProcessor                     │
│   • Accumulates in self.emotives list       │
│   • Averages when learning pattern          │
│   • Clears after learning                   │
└─────────────────┬───────────────────────────┘
                  │
┌─────────────────▼───────────────────────────┐
│      SuperKnowledgeBase                     │
│   • Stores with MongoDB $slice operation    │
│   • Maintains rolling window per pattern    │
│   • Filters zero values                     │
└─────────────────┬───────────────────────────┘
                  │
┌─────────────────▼───────────────────────────┐
│           MongoDB Storage                   │
│   • patterns_kb collection                  │
│   • emotives field as array of dicts        │
│   • Limited by PERSISTENCE parameter        │
└─────────────────┬───────────────────────────┘
                  │
┌─────────────────▼───────────────────────────┐
│         Prediction Output                   │
│   • Emotives from learned patterns          │
│   • Averaged across rolling window          │
└─────────────────────────────────────────────┘
```

## Processing Pipeline

### 1. Input Validation

```python
# Input format
observation = {
    'strings': ['hello', 'world'],
    'emotives': {
        'happiness': 0.8,
        'confidence': 0.6,
        'arousal': -0.2
    }
}

# Validation checks:
# - Keys must be strings
# - Values must be int or float
# - Empty emotives {} is valid
```

### 2. Accumulation During Observation

```python
# Each observation's emotives are accumulated
# PatternProcessor.emotives list grows:
[
    {'happiness': 0.8, 'confidence': 0.6},  # From observation 1
    {'happiness': 0.7, 'arousal': 0.3},     # From observation 2
    {'confidence': 0.9}                      # From observation 3
]
```

### 3. Averaging When Learning

```python
# When pattern is learned, emotives are averaged:
averaged = average_emotives(self.emotives)
# Result:
{
    'happiness': 0.75,  # (0.8 + 0.7) / 2
    'confidence': 0.75,  # (0.6 + 0.9) / 2
    'arousal': 0.3       # 0.3 / 1
}
```

### 4. Storage with Rolling Window

```javascript
// MongoDB update with $slice
{
    "$push": {
        "emotives": {
            "$each": [averaged_emotives],
            "$slice": -5  // Keep last 5 (PERSISTENCE=5)
        }
    }
}
```

### 5. Pattern Storage Evolution

```python
# Initial state
pattern.emotives = []

# After first learning
pattern.emotives = [{'happiness': 0.8}]

# After multiple learnings (PERSISTENCE=5)
pattern.emotives = [
    {'happiness': 0.8},
    {'happiness': 0.7, 'calm': 0.5},
    {'happiness': 0.9},
    {'happiness': 0.6, 'calm': 0.8},
    {'happiness': 0.85}
]

# Next learning pushes out oldest
pattern.emotives = [
    {'happiness': 0.7, 'calm': 0.5},  # 0.8 dropped
    {'happiness': 0.9},
    {'happiness': 0.6, 'calm': 0.8},
    {'happiness': 0.85},
    {'happiness': 0.75, 'calm': 0.6}  # New entry
]
```

### 6. Retrieval in Predictions

When patterns are recalled for predictions, emotives are:
1. Retrieved from the pattern's rolling window
2. Averaged across all entries in the window
3. Included in the prediction output

```python
# Prediction includes averaged emotives from pattern
prediction = {
    'name': 'PTRN|abc123...',
    'emotives': {
        'happiness': 0.76,  # Average of window values
        'calm': 0.63        # Average where present
    },
    'confidence': 0.85,
    # ... other prediction fields
}
```

## Storage Mechanism

### MongoDB Schema

```javascript
// Pattern document structure
{
    "_id": ObjectId("..."),
    "name": "PTRN|sha1_hash",
    "pattern_data": [["A"], ["B", "C"]],
    "frequency": 5,
    "emotives": [
        {"joy": 0.8, "confidence": 0.6},
        {"joy": 0.7},
        {"confidence": 0.9, "arousal": 0.3}
    ]
    // emotives array limited by PERSISTENCE
}
```

### Update Operation

```python
# MongoDB update with upsert
self.patterns_kb.update_one(
    {"name": pattern.name},
    {
        "$setOnInsert": {
            "pattern_data": pattern.pattern_data,
            "length": pattern.length
        },
        "$inc": {"frequency": 1},
        "$push": {
            "emotives": {
                "$each": [emotives_dict],
                "$slice": -1 * self.persistence  # Rolling window
            }
        }
    },
    upsert=True
)
```

### Zero Value Filtering

Before storage, zero values are filtered out:

```python
# Remove zeros to save space
emotives = {k: v for k, v in emotives.items() if v != 0}
```

## Averaging Algorithm

The `average_emotives` function implements arithmetic mean calculation:

```python
def average_emotives(record: List[Dict[str, float]]) -> Dict[str, float]:
    """
    Average emotives across multiple observations.
    
    Args:
        record: List of emotive dictionaries
        
    Returns:
        Dictionary with averaged values per key
    """
    # Collect all values per key
    new_dict = {}
    for bunch in record:
        for key, value in bunch.items():
            if key not in new_dict:
                new_dict[key] = [value]
            else:
                new_dict[key].append(value)
    
    # Calculate arithmetic mean
    avg_dict = {}
    for key, values in new_dict.items():
        if len(values) > 0:
            avg_dict[key] = sum(values) / len(values)
        else:
            avg_dict[key] = 0.0
    
    return avg_dict
```

### Example Calculation

```python
# Input
emotives_list = [
    {'happy': 0.8, 'sad': 0.2},
    {'happy': 0.6},
    {'sad': 0.4, 'angry': 0.3}
]

# Processing
# happy: [0.8, 0.6] → 1.4 / 2 = 0.7
# sad: [0.2, 0.4] → 0.6 / 2 = 0.3
# angry: [0.3] → 0.3 / 1 = 0.3

# Output
result = {
    'happy': 0.7,
    'sad': 0.3,
    'angry': 0.3
}
```

## PERSISTENCE Parameter

The PERSISTENCE parameter controls the rolling window size for emotive storage.

### Configuration

| Parameter | Default | Range | Description |
|-----------|---------|-------|-------------|
| `PERSISTENCE` | `5` | 1-∞ | Number of historical emotive entries to maintain per pattern |

### Effects of Different Values

#### PERSISTENCE = 1
- **Behavior**: Only keeps latest emotive values
- **Adaptation**: Instant - patterns immediately reflect new emotives
- **Memory**: No historical context
- **Use Case**: Rapidly changing environments

#### PERSISTENCE = 5 (Default)
- **Behavior**: Keeps last 5 emotive entries
- **Adaptation**: Balanced - smooths over recent history
- **Memory**: Recent context maintained
- **Use Case**: Most applications

#### PERSISTENCE = 10+
- **Behavior**: Long rolling window
- **Adaptation**: Slow - changes are gradual
- **Memory**: Extended historical context
- **Use Case**: Stable environments, long-term patterns

### Setting PERSISTENCE

```bash
# Environment variable
export PERSISTENCE=5

# In docker-compose.yml
environment:
  - PERSISTENCE=5

# In configuration file
{
    "persistence": 5
}
```

## Configuration

### Environment Variables

| Variable | Default | Description | Impact |
|----------|---------|-------------|--------|
| `PERSISTENCE` | `5` | Rolling window size | Controls emotive memory depth |

### Emotive Dimensions

There are no predefined emotive dimensions - you can use any string keys:

```python
# Valid emotive dictionaries
{'happiness': 0.8, 'sadness': 0.2}
{'arousal': 0.5, 'valence': 0.7}
{'utility': 0.9, 'cost': -0.3}
{'custom_dimension_1': 0.4}
```

### Value Ranges

- **Typical Range**: -1.0 to 1.0 or 0.0 to 1.0
- **No Hard Limits**: Any float value is accepted
- **Zero Filtering**: Zero values are removed before storage

## Examples

### Example 1: Emotional Context in Conversation

```python
# Observation 1: Greeting
observe({
    'strings': ['hello', 'how', 'are', 'you'],
    'emotives': {'friendliness': 0.9, 'formality': 0.3}
})

# Observation 2: Question
observe({
    'strings': ['what', 'is', 'weather', 'today'],
    'emotives': {'curiosity': 0.7, 'friendliness': 0.8}
})

# Learn pattern
learn()

# Pattern stored with averaged emotives:
# friendliness: (0.9 + 0.8) / 2 = 0.85
# formality: 0.3 / 1 = 0.3
# curiosity: 0.7 / 1 = 0.7
```

### Example 2: Sensor Data with Utility Values

```python
# Temperature readings with comfort utility
observations = [
    {
        'strings': ['temp_sensor_1', 'reading_normal'],
        'emotives': {'comfort': 0.8, 'energy_cost': -0.2}
    },
    {
        'strings': ['temp_sensor_2', 'reading_high'],
        'emotives': {'comfort': 0.3, 'energy_cost': -0.7}
    }
]

# Averaged emotives when learned:
# comfort: (0.8 + 0.3) / 2 = 0.55
# energy_cost: (-0.2 + -0.7) / 2 = -0.45
```

### Example 3: Rolling Window Evolution

```python
# PERSISTENCE = 3

# Initial learning
pattern.emotives = [{'joy': 0.8}]

# Second learning
pattern.emotives = [{'joy': 0.8}, {'joy': 0.6, 'calm': 0.7}]

# Third learning
pattern.emotives = [
    {'joy': 0.8},
    {'joy': 0.6, 'calm': 0.7},
    {'joy': 0.9}
]

# Fourth learning (window full, oldest dropped)
pattern.emotives = [
    {'joy': 0.6, 'calm': 0.7},  # First entry dropped
    {'joy': 0.9},
    {'joy': 0.7, 'calm': 0.8}   # New entry
]

# Prediction will average current window:
# joy: (0.6 + 0.9 + 0.7) / 3 = 0.73
# calm: (0.7 + 0.8) / 2 = 0.75
```

### Example 4: Multi-Modal Pattern with Emotives

```python
# Combining text, vectors, and emotives
observation = {
    'strings': ['user_input', 'question'],
    'vectors': [[0.1, 0.2, 0.3]],  # Embedding
    'emotives': {
        'confidence': 0.7,
        'urgency': 0.3,
        'sentiment': 0.5
    }
}

# Process observation
processor.observe(observation)

# Emotives flow through:
# 1. Validated by ObservationProcessor
# 2. Accumulated by MemoryManager
# 3. Averaged by PatternProcessor
# 4. Stored by SuperKnowledgeBase
# 5. Retrieved in predictions
```

## Best Practices

### 1. Choose Meaningful Dimensions

Use emotive keys that represent meaningful states in your domain:
- **Conversational AI**: sentiment, engagement, formality
- **IoT/Sensors**: comfort, efficiency, reliability
- **Games**: excitement, difficulty, satisfaction
- **Healthcare**: pain_level, stress, alertness

### 2. Normalize Value Ranges

Keep values in consistent ranges for easier interpretation:
```python
# Good: Normalized to [0, 1]
{'happiness': 0.8, 'energy': 0.6}

# Good: Normalized to [-1, 1]
{'valence': 0.5, 'arousal': -0.3}

# Avoid: Mixed scales
{'happiness': 0.8, 'energy': 75}  # Different scales
```

### 3. Set Appropriate PERSISTENCE

Match PERSISTENCE to your use case:
- **Real-time systems**: PERSISTENCE=1-3 for quick adaptation
- **Stable patterns**: PERSISTENCE=5-10 for smoothing
- **Long-term learning**: PERSISTENCE=10+ for historical context

### 4. Handle Missing Dimensions

Not all observations need all dimensions:
```python
# Valid - different dimensions per observation
obs1 = {'emotives': {'happy': 0.8}}
obs2 = {'emotives': {'sad': 0.3}}
obs3 = {'emotives': {'happy': 0.7, 'sad': 0.2}}
```

### 5. Use Emotives for Context, Not Control

Emotives provide context but don't directly control behavior:
- They're stored with patterns
- They appear in predictions
- Your application decides how to use them

## Troubleshooting

### Issue: Emotives Not Appearing in Predictions

**Symptom**: Predictions have empty or missing emotives field

**Causes & Solutions**:

1. **No emotives during learning**:
   ```python
   # Check that emotives were provided during observations
   observe({'strings': [...], 'emotives': {'key': value}})
   ```

2. **Pattern learned without emotives**:
   - Patterns must be re-learned with emotives
   - Existing patterns won't retroactively gain emotives

3. **Zero values filtered out**:
   ```python
   # This will be filtered
   {'emotives': {'joy': 0.0}}  # Removed during storage
   ```

### Issue: Emotives Not Averaging Correctly

**Symptom**: Unexpected emotive values in predictions

**Solutions**:

1. Check accumulation:
   ```python
   # Emotives accumulate across ALL observations before learning
   observe(obs1)  # Emotives added
   observe(obs2)  # Emotives added
   learn()        # All emotives averaged together
   ```

2. Verify PERSISTENCE setting:
   ```bash
   echo $PERSISTENCE  # Check current value
   ```

3. Inspect stored pattern:
   ```python
   # Check MongoDB directly
   pattern = patterns_kb.find_one({'name': 'PTRN|...'})
   print(pattern['emotives'])  # See rolling window
   ```

### Issue: Emotives Growing Unbounded

**Symptom**: Memory usage increasing due to emotives

**Solution**: Check PERSISTENCE configuration
```bash
# Ensure PERSISTENCE is set (not unlimited)
export PERSISTENCE=5  # Reasonable limit
```

### Issue: Rapid Emotive Changes Not Reflected

**Symptom**: Patterns seem "stuck" on old emotive values

**Solution**: Reduce PERSISTENCE for faster adaptation
```bash
export PERSISTENCE=1  # Immediate adaptation
# or
export PERSISTENCE=2  # Very responsive
```

### Issue: Emotive Values Too Volatile

**Symptom**: Predictions show rapidly fluctuating emotives

**Solution**: Increase PERSISTENCE for smoothing
```bash
export PERSISTENCE=10  # More stable averaging
```

## Implementation Details

### Data Flow

1. **Input**: `Dict[str, float]` with observation
2. **Validation**: `ObservationProcessor.validate_observation()`
3. **Processing**: `MemoryManager.process_emotives()`
4. **Accumulation**: `PatternProcessor.emotives.append()`
5. **Averaging**: `average_emotives()` from `metrics.py`
6. **Storage**: `SuperKnowledgeBase.learnPattern()`
7. **Retrieval**: Included in `Prediction` objects

### Key Files

- `kato/workers/observation_processor.py`: Validation
- `kato/workers/memory_manager.py`: Processing
- `kato/workers/pattern_processor.py`: Accumulation
- `kato/informatics/metrics.py`: Averaging function
- `kato/informatics/knowledge_base.py`: Storage with $slice
- `kato/representations/prediction.py`: Output format

### MongoDB Operations

```javascript
// Storage with rolling window
db.patterns_kb.update(
    { "name": "PTRN|hash" },
    {
        "$push": {
            "emotives": {
                "$each": [{"joy": 0.8}],
                "$slice": -5  // Keep last 5
            }
        }
    }
)

// Retrieval
db.patterns_kb.findOne(
    { "name": "PTRN|hash" },
    { "emotives": 1 }
)
```

## See Also

- [Pattern Matching](PATTERN_MATCHING.md) - How patterns are matched
- [Vector Processing](VECTOR_PROCESSING.md) - How vectors are processed
- [System Overview](SYSTEM_OVERVIEW.md) - Overall KATO architecture
- [Configuration Management](CONFIGURATION_MANAGEMENT.md) - All configuration options
- [API Reference](API_REFERENCE.md) - API endpoints for observations with emotives