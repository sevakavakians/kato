# KATO System Overview

## Introduction

KATO (Knowledge Abstraction for Traceable Outcomes) is a deterministic memory and prediction system designed for transparent, explainable AI. This document provides a comprehensive overview of KATO's end-to-end behavior, from input processing through prediction generation.

## Core Purpose

KATO serves as an intelligent memory module that:
- Learns patterns of multi-modal events
- Makes temporal predictions based on learned patterns
- Maintains complete transparency and traceability
- Operates deterministically without randomness

## System Architecture

### High-Level Flow

```
Input (Observation) → Processing → Short-Term Memory → Learning → Long-Term Memory
                           ↓
                      Predictions ← Pattern Matching ← Query
```

### FastAPI Architecture

KATO uses a modern FastAPI architecture with direct embedding:

```
Client Request → FastAPI Service (Ports 8001-8003) → Embedded KATO Processor
                           ↓                                    ↓
                    Async Processing              Pattern Storage & Vector DB
                           ↓                            (Isolated by node_id)
                    JSON Response
```

**Key Components:**
- **FastAPI Service**: Modern async web framework with automatic API documentation
- **Embedded Processor**: Each container runs one KATO processor instance
- **Database Isolation**: Each node has isolated data via `node_id`
- **Async Processing**: Non-blocking I/O for high performance

## End-to-End Behavior

### 1. Input Processing

#### Observation Structure
KATO accepts multi-modal observations containing:
- **Strings**: Symbolic/textual data
- **Vectors**: Numeric arrays for continuous data
- **Emotives**: Key-value pairs for emotional context

```python
observation = {
    'strings': ['hello', 'world'],
    'vectors': [[1.0, 2.0]],
    'emotives': {'joy': 0.8, 'confidence': 0.6}
}
```

#### Processing Rules
1. **Alphanumeric Sorting**: Strings within each event are automatically sorted
2. **Event Preservation**: The order of events in a pattern is maintained
3. **Empty Filtering**: Empty observations are completely ignored
4. **Vector Processing**: Vectors are processed through the vector indexer (VI)

#### Example Processing
```python
# Input
observe({'strings': ['zebra', 'apple', 'banana']})

# Stored in Short-Term Memory as
[['apple', 'banana', 'zebra']]  # Sorted alphanumerically

# Sequential observations
observe({'strings': ['z']})
observe({'strings': ['a']})
observe({'strings': ['m']})

# Short-Term Memory maintains event order
[['z'], ['a'], ['m']]  # Order preserved between events
```

### 2. Memory Architecture

#### Short-Term Memory
- **Purpose**: Temporary storage for current observation pattern
- **Behavior**: 
  - Accumulates observations as events
  - Has configurable maximum length (max_pattern_length)
  - Triggers auto-learning when limit reached
  - Cleared after learning:
    - Regular learn(): Completely cleared
    - Auto-learn: Completely cleared (same as regular learn)

#### Long-Term Memory
- **Purpose**: Persistent storage of learned patterns
- **Structure**:
  - Patterns identified by `PTRN|<sha1_hash>` format
  - Deterministic hashing ensures consistency
  - Frequency tracking for repeated patterns
- **Storage**: Persistent database per `node_id` (e.g., "alice_kato")
- **Persistence**: Survives short-term memory clears and service restarts

**Node Isolation:**
Each `node_id` maps to its own isolated storage:
```
node_id = "alice"
→ Database namespace = "alice_kato" (default SERVICE_NAME)
→ All patterns for this node stored permanently
```

**Important**: Using the same `node_id` in future sessions accesses the same trained patterns. See [Database Persistence Guide](database-persistence.md) for details.

### 3. Learning Process

Learning occurs when explicitly triggered or when short-term memory reaches capacity:

1. **Pattern Creation**: Current short-term memory pattern becomes a pattern
2. **Hash Generation**: Deterministic SHA1 hash created from pattern data
3. **Storage**: Pattern stored with identifier `PTRN|<sha1_hash>`
4. **Frequency Update**: Frequency starts at 1 for new patterns, increments if identical pattern learned again
5. **Memory Clear**: 
   - **Regular learning (explicit learn() call)**: Short-term memory COMPLETELY cleared
   - **Auto-learning (max_pattern_length reached)**: Short-term memory COMPLETELY cleared

```python
# Regular Learning Example
# Short-Term Memory: [['hello'], ['world']]
kato.learn()
# Creates: PTRN|a5b9c3d7... with pattern [['hello'], ['world']] (frequency=1)
# Short-Term Memory after: []  # Completely cleared

# Auto-Learning Example (max_pattern_length=3)
# Short-Term Memory: [['a'], ['b'], ['c']]  # Reaches max
# Auto-learn triggers
# Creates: PTRN|xyz123... with pattern [['a'], ['b'], ['c']]
# Short-Term Memory after: []  # Completely cleared
```

### 4. Prediction Generation

KATO generates predictions when observations match learned patterns.

**CRITICAL REQUIREMENT**: KATO requires at least 2 strings total in short-term memory (STM) to generate predictions. This ensures sufficient context for meaningful pattern matching.

Valid for predictions:
- Single event with 2+ strings: `[['hello', 'world']]` ✅
- Multiple events totaling 2+ strings: `[['hello'], ['world']]` ✅
- Single string with vectors: `[['hello', 'VCTR|<hash>']]` ✅ (vectors generate string representations)

Invalid (no predictions):
- Single string only: `[['hello']]` ❌
- Empty events: `[[], []]` ❌

When predictions are generated:

#### Temporal Segmentation

Predictions are organized into temporal fields:

- **Past**: Events that occurred before the current match
- **Present**: All contiguous events with matching symbols
- **Future**: Events expected after the current position
- **Missing**: Expected symbols not observed in present
- **Extras**: Observed symbols not expected in present

#### Example Predictions

##### Simple Sequential Match
```python
# Learned pattern: [['A'], ['B'], ['C']]
# Observation: [['B']]

# Prediction:
{
    'past': [['A']],
    'present': [['B']],
    'future': [['C']],
    'missing': [],
    'extras': []
}
```

##### Partial Match with Missing Symbols
```python
# Learned: [['hello', 'world'], ['foo', 'bar']]
# Observed: [['hello'], ['foo']]  # Missing 'world' and 'bar'

# Prediction:
{
    'past': [],
    'present': [['hello', 'world'], ['foo', 'bar']],
    'missing': ['world', 'bar'],
    'extras': [],
    'future': []
}
```

##### Match with Extra Symbols
```python
# Learned: [['cat'], ['dog']]
# Observed: [['cat', 'bird'], ['dog', 'fish']]

# Prediction:
{
    'past': [],
    'present': [['cat'], ['dog']],
    'missing': [],
    'extras': ['bird', 'fish'],
    'future': []
}
```

#### Prediction Metadata

Each prediction includes:
- **name**: Pattern identifier (PTRN|hash)
- **confidence**: Confidence score (0-1)
- **similarity**: Match quality measure
- **frequency**: Times this pattern was learned
- **emotives**: Emotional context if learned with pattern
- **normalized_entropy/entropy**: Energy and uncertainty measures

### 5. Special Behaviors

#### Emotives Processing
- Must be learned as part of a pattern
- Only appear in predictions from previously learned patterns
- Values are averaged across multiple pathways
- Don't immediately appear from current observations

```python
# Learn with emotives
observe({'strings': ['happy'], 'emotives': {'joy': 0.9}})
observe({'strings': ['day'], 'emotives': {'joy': 0.8}})
kato.learn()

# Later observation triggers emotive prediction
observe({'strings': ['happy']})
# Prediction includes averaged emotives from learned pattern
```

#### Vector Processing
- Processed through configurable classifiers
- May generate VCTR|<hash> symbols
- Appear before string symbols in mixed events
- Classifier-dependent short-term memory behavior

#### Deterministic Properties
- Same inputs always produce same outputs
- No randomness in any processing step
- Consistent hashing across sessions
- Reproducible predictions

### 6. API Interface

#### Primary Endpoints

**`/cognition`** - Main processing endpoint
- Accepts observations
- Returns short-term memory, predictions, emotives, symbols
- Supports observe, learn, and query operations

#### Response Structure
```json
{
    "short_term_memory": [["current"], ["events"]],
    "predictions": [{
        "name": "PTRN|abc123...",
        "past": [],
        "present": [["matching", "events"]],
        "future": [["expected", "next"]],
        "missing": [],
        "extras": [],
        "confidence": 0.85
    }],
    "emotives": {"joy": 0.7},
    "symbols": ["current", "events"]
}
```

### 7. Deployment Configuration

#### Container Architecture
- Each KATO processor runs as independent FastAPI container
- Direct HTTP access to each container (ports 8001-8003)
- Processor IDs maintain complete database isolation
- Async processing ensures high throughput

#### Scaling Considerations
- Horizontal scaling via multiple FastAPI containers
- Each processor maintains independent memory
- Optional load balancer for traffic distribution
- State persistence through processor lifecycle

## Key Properties

### Deterministic Operation
- Identical inputs produce identical outputs
- No random elements in processing
- Consistent pattern and vector hashing
- Reproducible across sessions

### Full Transparency
- All internal states inspectable
- Every prediction traceable to source
- Complete decision explainability
- No "black box" operations

### Stateful Processing
- Maintains pattern context
- Preserves temporal relationships
- Accumulates learning over time
- Persistent pattern recognition

## Use Cases

KATO excels in scenarios requiring:
- **Pattern Learning**: Learning and recognizing temporal patterns
- **Predictive Analytics**: Anticipating future events from partial observations
- **Explainable AI**: Full traceability of decisions
- **Multi-Modal Processing**: Combining text, numeric, and emotional data
- **Deterministic Processing**: Reproducible results for testing/validation

## Integration Guidelines

When integrating KATO:
1. **Sort Expected Strings**: Account for alphanumeric sorting in tests
2. **Handle Empty Responses**: Empty observations produce no changes
3. **Parse Temporal Fields**: Correctly interpret past/present/future
4. **Track Pattern Hashes**: Use PTRN| prefixes for identification
5. **Preserve State**: Maintain processor affinity for patterns

## Summary

KATO provides a transparent, deterministic memory and prediction system that learns from patterns of multi-modal observations. Its temporal segmentation pattern, combined with full explainability, makes it ideal for applications requiring traceable AI decision-making. The system's stateful nature, distributed architecture, and consistent processing ensure reliable pattern recognition and prediction across diverse use cases.