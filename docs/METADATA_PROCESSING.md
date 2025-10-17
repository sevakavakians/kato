# KATO Pattern Metadata System

## Table of Contents
1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Processing Pipeline](#processing-pipeline)
4. [Storage Mechanism](#storage-mechanism)
5. [Accumulation Algorithm](#accumulation-algorithm)
6. [Configuration](#configuration)
7. [Examples](#examples)
8. [Best Practices](#best-practices)
9. [Troubleshooting](#troubleshooting)

## Overview

Pattern metadata in KATO provides **contextual tags and attributes** for learned patterns. Unlike emotives (which store emotional/utility values), metadata is designed for categorical information like sources, tags, versions, or any discrete attributes that should accumulate across pattern observations.

### Key Concepts
- **Format**: Dictionary mapping string keys to any value type
- **Storage**: All values converted to strings and stored as unique lists
- **Purpose**: Track pattern provenance, categories, and contextual information
- **Association**: Stored with learned patterns in MongoDB
- **Accumulation**: Set-union behavior - values accumulate, duplicates filtered
- **Persistence**: Metadata persists indefinitely (no rolling window)

### Design Philosophy
Metadata uses **set-union accumulation** rather than averaging. When the same pattern is re-learned with new metadata, the values are added to existing lists without duplication. This allows tracking all unique sources, versions, or attributes that have contributed to a pattern over time.

## Architecture

The metadata processing system flows through multiple components:

```
┌─────────────────────────────────────────────┐
│          Input Observation                  │
│  {"book": "Alice", "chapter": "1"}         │
└─────────────────┬───────────────────────────┘
                  │
┌─────────────────▼───────────────────────────┐
│       ObservationProcessor                  │
│   • Validates metadata format               │
│   • Ensures dict with string keys           │
└─────────────────┬───────────────────────────┘
                  │
┌─────────────────▼───────────────────────────┐
│          MemoryManager                      │
│   • Adds to metadata accumulator list       │
└─────────────────┬───────────────────────────┘
                  │
┌─────────────────▼───────────────────────────┐
│        PatternProcessor                     │
│   • Accumulates in self.metadata list       │
│   • Merges when learning pattern            │
│   • Clears after learning                   │
└─────────────────┬───────────────────────────┘
                  │
┌─────────────────▼───────────────────────────┐
│      SuperKnowledgeBase                     │
│   • Converts values to strings              │
│   • Uses MongoDB $addToSet operation        │
│   • Ensures unique values per key           │
└─────────────────┬───────────────────────────┘
                  │
┌─────────────────▼───────────────────────────┐
│           MongoDB Storage                   │
│   • patterns_kb collection                  │
│   • metadata field as dict of string arrays │
│   • No expiration (permanent storage)       │
└─────────────────┬───────────────────────────┘
                  │
┌─────────────────▼───────────────────────────┐
│         Pattern Retrieval                   │
│   • Metadata from stored patterns           │
│   • All accumulated values per key          │
└─────────────────────────────────────────────┘
```

## Processing Pipeline

### 1. Input Validation

```python
# Input format
observation = {
    'strings': ['hello', 'world'],
    'metadata': {
        'book': 'Alice in Wonderland',
        'chapter': '1',
        'author': 'Lewis Carroll'
    }
}

# Validation checks:
# - Must be a dictionary
# - Keys must be strings
# - Values can be any type (converted to strings)
# - Empty metadata {} is valid
```

### 2. Accumulation During Observation

```python
# Each observation's metadata is accumulated
# PatternProcessor.metadata list grows:
[
    {'book': 'Alice', 'chapter': '1'},          # From observation 1
    {'book': 'Alice', 'chapter': '2'},          # From observation 2
    {'author': 'Lewis Carroll'}                  # From observation 3
]
```

### 3. Merging When Learning

```python
# When pattern is learned, metadata is merged using accumulate_metadata():
merged = accumulate_metadata(self.metadata)
# Result:
{
    'book': ['Alice'],           # Unique values
    'chapter': ['1', '2'],       # Both chapters
    'author': ['Lewis Carroll']  # Single author
}
```

### 4. Storage with Set-Union

```javascript
// MongoDB update with $addToSet
{
    "$addToSet": {
        "metadata.book": {"$each": ["Alice"]},
        "metadata.chapter": {"$each": ["1", "2"]},
        "metadata.author": {"$each": ["Lewis Carroll"]}
    }
}
```

### 5. Pattern Storage Evolution

```python
# Initial state
pattern.metadata = {}

# After first learning
pattern.metadata = {
    'book': ['Alice'],
    'chapter': ['1', '2']
}

# After re-learning same pattern with new metadata
pattern.metadata = {
    'book': ['Alice', 'Through the Looking Glass'],  # New book added
    'chapter': ['1', '2'],                            # No change (duplicates filtered)
    'source': ['dataset_v2']                          # New key added
}

# After another re-learning
pattern.metadata = {
    'book': ['Alice', 'Through the Looking Glass'],
    'chapter': ['1', '2', '3'],                       # New chapter added
    'source': ['dataset_v2', 'dataset_v3'],          # New source added
    'version': ['2.0']                                # New key added
}
```

### 6. Retrieval with Patterns

```python
# Pattern retrieval includes all accumulated metadata
pattern = {
    'name': 'PTRN|abc123...',
    'pattern_data': [['A'], ['B']],
    'frequency': 5,
    'metadata': {
        'book': ['Alice', 'Through the Looking Glass'],
        'chapter': ['1', '2', '3'],
        'source': ['dataset_v2', 'dataset_v3']
    }
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
    "emotives": [...],
    "metadata": {
        "book": ["Alice in Wonderland", "Through the Looking Glass"],
        "chapter": ["1", "2", "3"],
        "author": ["Lewis Carroll"],
        "version": ["1.0", "2.0"]
    }
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
            "length": pattern.length,
            "metadata": {}  # Initialize if new pattern
        },
        "$inc": {"frequency": 1},
        "$addToSet": {
            # Add each metadata key's values uniquely
            "metadata.book": {"$each": ["Alice", "Through the Looking Glass"]},
            "metadata.chapter": {"$each": ["1", "2"]},
            "metadata.author": {"$each": ["Lewis Carroll"]}
        }
    },
    upsert=True
)
```

### Type Conversion

All values are converted to strings before storage:

```python
# Input
metadata = {
    'count': 123,
    'price': 45.67,
    'is_valid': True,
    'title': 'Alice'
}

# Stored as
{
    'count': ['123'],
    'price': ['45.67'],
    'is_valid': ['True'],
    'title': ['Alice']
}
```

## Accumulation Algorithm

The `accumulate_metadata` function merges multiple metadata dictionaries:

```python
def accumulate_metadata(metadata_list: list[dict]) -> dict[str, list[str]]:
    """
    Accumulate metadata dicts into a single dict with unique string list values.

    Args:
        metadata_list: List of metadata dictionaries

    Returns:
        Dictionary mapping each key to a list of unique string values.
    """
    accumulated: dict[str, set[str]] = {}

    for metadata_dict in metadata_list:
        for key, value in metadata_dict.items():
            # Convert value to string
            str_value = str(value)

            if key not in accumulated:
                accumulated[key] = {str_value}
            else:
                accumulated[key].add(str_value)

    # Convert sets to sorted lists for consistent ordering
    result: dict[str, list[str]] = {}
    for key, value_set in accumulated.items():
        result[key] = sorted(list(value_set))

    return result
```

### Example Calculation

```python
# Input
metadata_list = [
    {'book': 'Alice', 'chapter': 1},
    {'book': 'Alice', 'chapter': 2},
    {'book': 'Looking Glass', 'author': 'Carroll'}
]

# Processing
# book: {'Alice', 'Looking Glass'} → sorted → ['Alice', 'Looking Glass']
# chapter: {'1', '2'} → sorted → ['1', '2']
# author: {'Carroll'} → sorted → ['Carroll']

# Output
result = {
    'book': ['Alice', 'Looking Glass'],
    'chapter': ['1', '2'],
    'author': ['Carroll']
}
```

## Configuration

### No Configuration Required

Unlike emotives (which have PERSISTENCE), metadata requires no special configuration:
- All values are stored permanently
- No rolling window or limits
- No parameters to tune

### Session Support

Metadata is fully supported in session-based workflows:

```python
# Create session
session = kato_client.create_session()

# Observe with metadata
kato_client.observe(
    strings=['hello'],
    metadata={'source': 'user_input', 'session': 'abc123'}
)

# Metadata is isolated per session
# Each session accumulates its own metadata
```

## Examples

### Example 1: Document Tracking

```python
# Track patterns from different document sources

# Observation from Chapter 1
observe({
    'strings': ['alice', 'rabbit', 'hole'],
    'metadata': {
        'book': 'Alice in Wonderland',
        'chapter': '1',
        'page': '5'
    }
})

# Observation from Chapter 2
observe({
    'strings': ['pool', 'tears'],
    'metadata': {
        'book': 'Alice in Wonderland',
        'chapter': '2',
        'page': '15'
    }
})

# Learn pattern
learn()

# Pattern metadata:
{
    'book': ['Alice in Wonderland'],
    'chapter': ['1', '2'],
    'page': ['15', '5']  # Sorted alphabetically
}
```

### Example 2: Dataset Attribution

```python
# Track which datasets contributed to patterns

# From dataset v1
observe({'strings': ['A', 'B'], 'metadata': {'dataset': 'v1', 'date': '2025-01-01'}})
observe({'strings': ['C'], 'metadata': {'dataset': 'v1'}})
learn()

# Later, re-learn same pattern from dataset v2
observe({'strings': ['A', 'B'], 'metadata': {'dataset': 'v2', 'date': '2025-02-01'}})
observe({'strings': ['C'], 'metadata': {'dataset': 'v2'}})
learn()

# Pattern metadata now shows both sources:
{
    'dataset': ['v1', 'v2'],
    'date': ['2025-01-01', '2025-02-01']
}
```

### Example 3: Semantic Tagging

```python
# Add semantic categories to patterns

observe({'strings': ['hello', 'world'], 'metadata': {'category': 'greeting', 'language': 'english'}})
observe({'strings': ['how', 'are', 'you'], 'metadata': {'category': 'question'}})
learn()

# Pattern metadata:
{
    'category': ['greeting', 'question'],
    'language': ['english']
}

# Later, observe in different language
observe({'strings': ['hello', 'world'], 'metadata': {'language': 'informal'}})
observe({'strings': ['how', 'are', 'you'], 'metadata': {}})
learn()

# Pattern metadata updated:
{
    'category': ['greeting', 'question'],
    'language': ['english', 'informal']  # Accumulated
}
```

### Example 4: Version Tracking

```python
# Track pattern evolution across system versions

# System v1.0
observe({'strings': ['command', 'execute'], 'metadata': {'version': '1.0', 'status': 'stable'}})
observe({'strings': ['task', 'complete'], 'metadata': {'version': '1.0'}})
learn()

# System v2.0 (same pattern learned again)
observe({'strings': ['command', 'execute'], 'metadata': {'version': '2.0', 'status': 'experimental'}})
observe({'strings': ['task', 'complete'], 'metadata': {'version': '2.0'}})
learn()

# Pattern metadata shows version history:
{
    'version': ['1.0', '2.0'],
    'status': ['experimental', 'stable']  # Both states tracked
}
```

## Metadata in Batch Operations (observe_sequence)

### Overview

The `observe_sequence` endpoint supports metadata on individual observations within the batch. **Importantly, the placement of metadata within the sequence does not affect the final learned pattern** - all metadata from all observations in the sequence are accumulated and merged together using set-union semantics.

### Placement Independence

Whether metadata is provided in the first observation, last observation, or distributed across multiple observations, the final merged metadata will be identical:

```python
# Example 1: All metadata in first observation
observations_first = [
    {'strings': ['A'], 'metadata': {'book': 'Alice', 'chapter': '1', 'author': 'Carroll'}},
    {'strings': ['B'], 'metadata': {}}
]

# Example 2: All metadata in last observation
observations_last = [
    {'strings': ['A'], 'metadata': {}},
    {'strings': ['B'], 'metadata': {'book': 'Alice', 'chapter': '1', 'author': 'Carroll'}}
]

# Example 3: Metadata distributed
observations_distributed = [
    {'strings': ['A'], 'metadata': {'book': 'Alice', 'author': 'Carroll'}},
    {'strings': ['B'], 'metadata': {'chapter': '1'}}
]

# All three will produce the SAME merged metadata when learned:
# {'book': ['Alice'], 'chapter': ['1'], 'author': ['Carroll']}
```

### Accumulation Process

1. **During Sequence Processing**: Each observation's metadata is added to the accumulator
2. **When Learning**: All accumulated metadata is merged using `accumulate_metadata()`
3. **Result**: Final pattern contains unique values from ALL observations

### Use Cases

This placement independence is useful for:

**1. Flexible Data Formats**
```python
# Some observations may have metadata, others may not
observations = [
    {'strings': ['event1'], 'metadata': {'source': 'db1'}},
    {'strings': ['event2'], 'metadata': {}},  # No metadata
    {'strings': ['event3'], 'metadata': {'version': '2.0'}}
]
# Pattern will have: {'source': ['db1'], 'version': ['2.0']}
```

**2. Different Metadata Keys Per Observation**
```python
# Each observation can contribute different metadata keys
observations = [
    {'strings': ['chapter1'], 'metadata': {'book': 'Alice', 'chapter': '1'}},
    {'strings': ['chapter2'], 'metadata': {'chapter': '2', 'page': '15'}},
    {'strings': ['chapter3'], 'metadata': {'chapter': '3', 'author': 'Carroll'}}
]
# Pattern will have:
# - book: ['Alice']
# - chapter: ['1', '2', '3']
# - page: ['15']
# - author: ['Carroll']
```

**3. Consolidated Metadata**
```python
# Provide all metadata in one observation for convenience
observations = [
    {'strings': ['A'], 'metadata': {'book': 'Alice', 'chapter': '1', 'author': 'Carroll'}},
    {'strings': ['B'], 'metadata': {}},
    {'strings': ['C'], 'metadata': {}}
]
# Pattern will have all three metadata keys
```

**4. Duplicate Value Filtering**
```python
# Duplicate values are automatically filtered
observations = [
    {'strings': ['event1'], 'metadata': {'source': 'dataset_v1', 'type': 'training'}},
    {'strings': ['event2'], 'metadata': {'source': 'dataset_v1', 'type': 'validation'}},
    {'strings': ['event3'], 'metadata': {'source': 'dataset_v1'}}
]
# Pattern will have:
# - source: ['dataset_v1']  # Only one entry despite being in all 3 observations
# - type: ['training', 'validation']
```

### Best Practice for observe_sequence

While metadata can be placed anywhere in the sequence, for clarity and maintainability:

**Option 1: Consolidate in First Observation**
```python
observations = [
    {'strings': ['event1'], 'metadata': {'book': 'Alice', 'chapter': '1'}},  # All metadata here
    {'strings': ['event2'], 'metadata': {}},
    {'strings': ['event3'], 'metadata': {}}
]
```

**Option 2: Distribute Based on Semantic Meaning**
```python
observations = [
    {'strings': ['intro'], 'metadata': {'section': 'introduction', 'page': '1'}},
    {'strings': ['body'], 'metadata': {'section': 'body', 'page': '5'}},
    {'strings': ['conclusion'], 'metadata': {'section': 'conclusion', 'page': '20'}}
]
# Pattern will have:
# - section: ['body', 'conclusion', 'introduction']  # Sorted alphabetically
# - page: ['1', '20', '5']  # All unique pages
```

**Option 3: Track Different Attributes Per Event**
```python
# Each observation contributes different provenance information
observations = [
    {'strings': ['A'], 'metadata': {'source': 'db1', 'timestamp': '2025-01-01'}},
    {'strings': ['B'], 'metadata': {'source': 'db2', 'timestamp': '2025-01-02'}},
    {'strings': ['C'], 'metadata': {'source': 'db1', 'user': 'alice'}}
]
# Pattern will have:
# - source: ['db1', 'db2']
# - timestamp: ['2025-01-01', '2025-01-02']
# - user: ['alice']
```

All approaches produce equivalent results when the same metadata values are used - choose based on your application's semantics and clarity needs.

## Best Practices

### 1. Use Metadata for Discrete Values

Metadata works best for categorical/discrete information:

```python
# Good: Discrete categories
metadata = {
    'source': 'database',
    'category': 'question',
    'priority': 'high'
}

# Avoid: Continuous values (use emotives instead)
metadata = {
    'confidence': '0.85',  # Better as emotive
    'temperature': '72.5'  # Better as emotive
}
```

### 2. Use Consistent Key Names

Maintain consistent metadata keys across observations:

```python
# Good: Consistent keys
obs1 = {'metadata': {'source': 'db1', 'type': 'user'}}
obs2 = {'metadata': {'source': 'db2', 'type': 'system'}}

# Avoid: Inconsistent keys
obs1 = {'metadata': {'source': 'db1', 'type': 'user'}}
obs2 = {'metadata': {'src': 'db2', 'kind': 'system'}}  # Different keys
```

### 3. Leverage Accumulation for Provenance

Use metadata to track all sources that contributed to a pattern:

```python
# Each re-learning adds to the provenance trail
{
    'sources': ['dataset_2023', 'dataset_2024', 'user_feedback'],
    'versions': ['1.0', '1.5', '2.0'],
    'environments': ['dev', 'staging', 'prod']
}
```

### 4. Use Meaningful String Values

Since all values become strings, use values that are meaningful as strings:

```python
# Good: Values meaningful as strings
metadata = {
    'priority': 'high',      # Clear meaning
    'status': 'active',      # Clear meaning
    'version': '2.1.0'       # Clear meaning
}

# Acceptable but less ideal: Numbers
metadata = {
    'count': 42,      # Becomes '42'
    'index': 5        # Becomes '5'
}
```

### 5. Don't Use Metadata for Temporary State

Metadata persists across re-learning, so avoid temporary values:

```python
# Avoid: Temporary state (will accumulate forever)
metadata = {'timestamp': '2025-01-15T10:30:00'}  # Every timestamp accumulates

# Better: Use stable identifiers
metadata = {'session_id': 'abc123', 'user_id': 'user456'}
```

## Troubleshooting

### Issue: Metadata Not Appearing in Patterns

**Symptom**: Retrieved patterns have empty or missing metadata field

**Causes & Solutions**:

1. **No metadata during learning**:
   ```python
   # Ensure metadata was provided during observations
   observe({'strings': [...], 'metadata': {'key': 'value'}})
   ```

2. **Pattern learned without metadata**:
   - Patterns must be re-learned with metadata
   - Existing patterns won't retroactively gain metadata

3. **Check MongoDB directly**:
   ```bash
   db.patterns_kb.findOne({'name': 'PTRN|...'}, {'metadata': 1})
   ```

### Issue: Duplicate Values in Metadata

**Symptom**: Same value appears multiple times in metadata lists

**Solution**: This should not happen - check MongoDB operations

```bash
# Check pattern metadata
db.patterns_kb.findOne({'name': 'PTRN|...'}, {'metadata': 1})

# Expected: Unique values per key
# If duplicates found, this is a bug
```

### Issue: Metadata Keys Changing

**Symptom**: Metadata keys vary across observations

**Solution**: Standardize metadata keys in your application

```python
# Define standard metadata schema
METADATA_SCHEMA = {
    'source': str,
    'category': str,
    'version': str
}

# Validate before observation
def validate_metadata(metadata):
    return {k: metadata.get(k) for k in METADATA_SCHEMA.keys() if k in metadata}
```

### Issue: Too Much Metadata Accumulation

**Symptom**: Metadata lists growing indefinitely

**Solution**: This is by design - metadata persists forever

If you need to limit metadata:
1. Periodically clear and re-learn patterns
2. Use application-level filtering
3. Consider if emotives (rolling window) would be better

### Issue: Type Conversion Problems

**Symptom**: Metadata values don't match expected types

**Solution**: Remember all values are strings

```python
# Input
metadata = {'count': 42, 'flag': True}

# Retrieved as
{'count': ['42'], 'flag': ['True']}

# Convert back in application
count = int(pattern['metadata']['count'][0])
flag = pattern['metadata']['flag'][0] == 'True'
```

## Implementation Details

### Data Flow

1. **Input**: `Dict[str, Any]` with observation
2. **Validation**: `ObservationProcessor.validate_observation()`
3. **Processing**: `MemoryManager.process_metadata()`
4. **Accumulation**: `PatternProcessor.metadata.append()`
5. **Merging**: `accumulate_metadata()` from `metrics.py`
6. **Storage**: `SuperKnowledgeBase.learnPattern()`
7. **Retrieval**: Included in pattern documents

### Key Files

- `kato/workers/observation_processor.py`: Validation
- `kato/workers/memory_manager.py`: Processing
- `kato/workers/pattern_processor.py`: Accumulation
- `kato/informatics/metrics.py`: Merging function
- `kato/informatics/knowledge_base.py`: Storage with $addToSet
- `kato/api/schemas/observation.py`: API schema

### MongoDB Operations

```javascript
// Storage with $addToSet
db.patterns_kb.update(
    { "name": "PTRN|hash" },
    {
        "$addToSet": {
            "metadata.book": {"$each": ["Alice", "Wonderland"]},
            "metadata.chapter": {"$each": ["1", "2"]}
        }
    }
)

// Retrieval
db.patterns_kb.findOne(
    { "name": "PTRN|hash" },
    { "metadata": 1 }
)
```

## See Also

- [Emotives Processing](EMOTIVES_PROCESSING.md) - Emotional/utility value processing
- [Pattern Matching](PATTERN_MATCHING.md) - How patterns are matched
- [API Reference](API_REFERENCE.md) - API endpoints for observations with metadata
- [Configuration Management](CONFIGURATION_MANAGEMENT.md) - All configuration options
