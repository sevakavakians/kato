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

### Distributed Deployment

KATO uses a high-performance architecture with ZeroMQ for inter-process communication:

```
REST Client → REST Gateway (Port 8000) → ZMQ Pool → ZMQ Server → KATO Processors
                    ↓                        ↓           ↓
            HTTP to ZMQ Translation    Connection Pool  Internal Queue
                    ↓                        ↓           ↓  
            Processor ID Routing      Load Balancing   Process Isolation
```

**Key Components:**
- **REST Gateway**: HTTP API endpoints, translates REST calls to ZMQ messages
- **ZMQ Pool**: Connection pooling and load balancing for ZMQ clients  
- **ZMQ Server**: High-performance message queue server (Port 5555)
- **KATO Processor**: Core AI processing engine with short-term memory and patterns

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
  - Has configurable maximum length
  - Triggers auto-learning when limit reached
  - Cleared after learning (last event preserved)

#### Long-Term Memory
- **Purpose**: Persistent storage of learned patterns
- **Structure**:
  - Patterns identified by `PTRN|<sha1_hash>` format
  - Deterministic hashing ensures consistency
  - Frequency tracking for repeated patterns
- **Persistence**: Survives short-term memory clears

### 3. Learning Process

Learning occurs when explicitly triggered or when short-term memory reaches capacity:

1. **Pattern Creation**: Current short-term memory pattern becomes a pattern
2. **Hash Generation**: Deterministic SHA1 hash created from pattern
3. **Storage**: Pattern stored with identifier `PTRN|<hash>`
4. **Frequency Update**: Counter increases if identical pattern learned again
5. **Memory Clear**: Short-term memory completely cleared (regular learning) or last event kept (auto-learning)

```python
# Short-Term Memory: [['hello'], ['world']]
kato.learn()
# Creates: PTRN|a5b9c3d7... with pattern [['hello'], ['world']]
# Short-Term Memory after: [['world']]  # Last event preserved
```

### 4. Prediction Generation

KATO generates predictions when observations match learned patterns:

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
- **emotives**: Emotional context if learned with model
- **hamiltonian/entropy**: Energy and uncertainty measures

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
- May generate VECTOR|<hash> symbols
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
- Each KATO processor runs as independent container
- REST gateway provides unified access point
- Sticky routing ensures session consistency
- Processor IDs maintain state isolation

#### Scaling Considerations
- Horizontal scaling via multiple processors
- Each processor maintains independent memory
- Gateway handles routing and load distribution
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