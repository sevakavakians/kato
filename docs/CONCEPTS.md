# KATO Core Concepts and Behavior

This document provides a comprehensive reference for KATO's core concepts, behaviors, and implementation details.

## Table of Contents
1. [Core Concepts](#core-concepts)
   - [Minimum Sequence Requirements](#minimum-sequence-requirements)
   - [Temporal Prediction Fields](#temporal-prediction-fields)
2. [Event Processing](#event-processing)
3. [Memory Architecture](#memory-architecture)
4. [Prediction System](#prediction-system)
5. [Learning Behavior](#learning-behavior)
6. [Multi-Modal Processing](#multi-modal-processing)
7. [Deterministic Properties](#deterministic-properties)
8. [Implementation Details](#implementation-details)

## Core Concepts

### Minimum Sequence Requirements

**CRITICAL**: KATO requires at least 2 strings total in short-term memory (STM) to generate predictions. This is a fundamental architectural requirement.

#### Valid Sequences for Predictions:
- **Single event with 2+ strings**: `[['hello', 'world']]` ✅
- **Multiple events totaling 2+ strings**: `[['hello'], ['world']]` ✅
- **Mixed event sizes**: `[['a', 'b'], ['c']]` ✅

#### Invalid Sequences (No Predictions):
- **Single string only**: `[['hello']]` ❌
- **Single string with emotives**: `[['hello']] + emotives` ❌ (emotives don't contribute strings)
- **Empty events**: `[[], [], []]` ❌

#### Valid with Vectors:
- **Single string with vectors**: `[['hello', 'VECTOR|<hash>']]` ✅
  - Vectors contribute their own string representation (e.g., 'VECTOR|<hash>')
  - Results in 2+ strings total, meeting the minimum requirement
  - The vector string is automatically added when vectors are processed

This requirement ensures sufficient context for meaningful pattern matching and prediction generation.

### Temporal Prediction Fields

KATO organizes predictions into temporal segments that provide sophisticated sequence understanding:

- **`past`**: Events that occurred before the current matching position in a learned sequence
- **`present`**: The current matching events (can span multiple events if partially matching)
- **`future`**: Events expected to occur after the current position
- **`missing`**: Symbols that were expected in the present events but were not observed
  - Order is preserved from the original sequence
  - No sorting is applied
- **`extras`**: Symbols that were observed but not expected in the present events
  - Order is preserved as observed
  - No sorting is applied

### Event Structure

KATO organizes observations into **events**, where each event can contain multiple symbols, strings, vectors, and emotives.

```python
# Example observation with multiple strings in one event
observation = {
    'strings': ['hello', 'world'],  # Single event with two strings
    'vectors': [[1.0, 2.0]],        # Vector data
    'emotives': {'joy': 0.8}        # Emotional context
}
```

## Event Processing

### Alphanumeric Sorting Within Events

**Important**: KATO sorts strings alphanumerically within each event while preserving the order of events in a sequence.

#### Examples:

```python
# Input observation
observe({'strings': ['zebra', 'apple', 'banana']})

# Stored in short-term memory as
[['apple', 'banana', 'zebra']]  # Sorted alphanumerically
```

#### Sequence Preservation:
```python
# Three separate observations
observe({'strings': ['z']})
observe({'strings': ['a']})  
observe({'strings': ['m']})

# Short-term memory maintains event order
[['z'], ['a'], ['m']]  # Order preserved, no sorting between events
```

### String Symbol Processing
- Strings are sorted alphanumerically within each event
- Example: `['multi', 'modal']` becomes `['modal', 'multi']`
- Sorting happens at observation time before storage
- Case-sensitive sorting (capitals before lowercase)
- Numeric strings sorted as strings: `['10', '2', '1']` → `['1', '10', '2']`

### Vector Symbol Processing
- Vectors are processed through the vector indexer (VI) to produce vector names
- **Purpose**: Generate string symbols like `VECTOR|<hash>` for short-term memory
- These vector strings are always added to STM when vectors are processed
- Vector strings count toward the minimum 2-string requirement for predictions
- Vector symbols appear before string symbols in mixed modality events
- A single user string + vectors = valid sequence (2+ strings total)

### Empty Events
KATO ignores empty events - they do not change short-term memory or affect predictions.

```python
# Empty observation
observe({'strings': [], 'vectors': [], 'emotives': {}})
# Result: No change to short-term memory

# Sequence with empty events
observe({'strings': ['first']})
observe({'strings': []})         # Ignored
observe({'strings': ['second']})
# Short-term memory: [['first'], ['second']]
```

## Memory Architecture

### Short-Term Memory
- Accumulates observations as events
- Each observation creates one event (unless empty)
- Maintains temporal order of events
- Has configurable maximum sequence length
- Auto-learns when limit reached
- Cleared when learning is triggered (last event preserved)

### Long-Term Memory
- Stores learned sequences with deterministic hashes
- Sequences identified by `MODEL|<sha1_hash>` format
- Same sequence always produces same hash
- Persists across short-term memory clears
- Used for generating predictions
- Frequency tracking for repeated patterns

## Prediction System

### Prediction Generation

Predictions are generated when:
1. A model has been learned
2. **At least 2 strings are present in short-term memory (STM)**
3. The observed sequence matches a learned sequence with similarity >= `recall_threshold`
   - Default recall_threshold: 0.1 (10% similarity)
   - Higher threshold = stricter matching, fewer predictions
   - Lower threshold = looser matching, more predictions
   - See [Configuration Guide](deployment/CONFIGURATION.md#recall_threshold-tuning-guide) for detailed tuning
4. Either strings or vectors are present (not just emotives)

**Note**: If no sequences match above the recall_threshold, no predictions are returned even if all other conditions are met.

**Important**: The 2+ string requirement is enforced in `modeler.py::processEvents()` at line 154:
```python
if len(state) >= 2 and self.predict and self.trigger_predictions:
```

### Prediction Structure

Each prediction includes:
- `name`: Model identifier (`MODEL|<hash>`)
- `confidence`: Confidence score (0-1)
- `similarity`: How closely the observation matches the model
- `frequency`: How many times this model has been learned
- `hamiltonian`: Energy measure
- `grand_hamiltonian`: Combined energy measure
- `entropy`: Uncertainty measure
- `matches`: Symbols that matched
- `emotives`: Dictionary of emotive values (if learned with the model)

### Temporal Field Examples

**Remember**: All examples below assume observations meet the 2+ string requirement. With fewer than 2 strings, no predictions would be generated.

#### Example 1: Simple Sequential Match
```python
# Learned sequence
[['alpha'], ['beta'], ['gamma']]

# Observation (must have 2+ strings for predictions)
[['alpha'], ['beta']]

# Prediction result
{
    'past': [],
    'present': [['alpha'], ['beta']],
    'future': [['gamma']],
    'missing': [],
    'extras': []
}
```

#### Example 2: Partial Event Match with Missing Symbols
```python
# Learned sequence  
[['hello', 'world'], ['foo', 'bar']]

# Observation (missing 'world' and 'bar', but has 2+ strings)
[['hello'], ['foo']]  # Valid: 2 strings total

# Prediction result
{
    'past': [],
    'present': [['hello', 'world'], ['foo', 'bar']],
    'missing': ['world', 'bar'],  # Expected but not observed
    'extras': [],
    'future': []
}
```

#### Example 3: Observation with Extra Symbols
```python
# Learned sequence
[['cat'], ['dog']]

# Observation (with unexpected 'bird' and 'fish')
[['cat', 'bird'], ['dog', 'fish']]  # Valid: 4 strings total

# Prediction result
{
    'past': [],
    'present': [['cat'], ['dog']],
    'missing': [],
    'extras': ['bird', 'fish'],  # Observed but not expected
    'future': []
}
```

#### Example 4: Invalid - Single String (No Predictions)
```python
# Learned sequence
[['alpha'], ['beta'], ['gamma']]

# Observation (only 1 string - invalid)
[['beta']]

# Result: NO PREDICTIONS GENERATED
# The 2-string minimum requirement is not met
```

#### Example 5: Complex Partial Match
```python
# Learned sequence
[['a', 'b', 'c'], ['d', 'e'], ['f', 'g', 'h']]

# Observation (partial matches with extras)
[['a', 'x'], ['d'], ['f', 'g', 'y']]

# Prediction result
{
    'past': [],
    'present': [['a', 'b', 'c'], ['d', 'e'], ['f', 'g', 'h']],
    'missing': ['b', 'c', 'e', 'h'],  # Expected but not seen
    'extras': ['x', 'y'],              # Seen but not expected
    'future': []
}
```

### Contiguous Matching
The `present` field includes all contiguous events that contain matching symbols:
- Events are included in their entirety when they contain ANY matching symbols
- The present spans from the first event with a match to the last event with a match
- ALL symbols within those events are included, even if they weren't observed
- The `missing` field identifies symbols in present events that weren't actually observed
- Not all symbols need to match for an event to be part of the present

Example: If observing `['a', 'c']` from model `[['a', 'b'], ['c', 'd'], ['e', 'f']]`:
- Present: `[['a', 'b'], ['c', 'd']]` (complete events with matches)
- Missing: `['b', 'd']` (symbols in present but not observed)
- Future: `[['e', 'f']]` (events after last match)

## Learning Behavior

### Learning Process
1. Learning creates a model from the current short-term memory (STM)
2. Models are named with format: `MODEL|<identifier>`
3. Empty short-term memory produces no model
4. Frequency increases when the same sequence is learned multiple times
5. **Regular learning**: Short-term memory is completely cleared after learning

### Auto-Learning
- Triggered when max_sequence_length is reached
- **Auto-learning only**: The last event is preserved in STM after learning
- Configurable through processor parameters
- This preserves continuity for streaming data

## Multi-Modal Processing

KATO processes multiple data types simultaneously within each observation:

### Strings
- Symbolic/textual data
- Sorted alphanumerically within events
- Primary matching mechanism for predictions

### Vectors
- Numeric arrays of any dimension
- Processed by vector indexer (VI)
- Can be used for similarity calculations
- Deterministic hashing: `VECTOR|<sha1_hash>`

### Emotives
- Key-value pairs representing emotional context
- Values are floating-point numbers (0.0 to 1.0)
- Aggregated across observations (averaging)
- Preserved in learned sequences

**Critical Insight**: Emotives only appear in predictions from previously learned models, not from current observations.

### Example Multi-Modal Observation
```python
observation = {
    'strings': ['visual', 'input'],        # Sorted to ['input', 'visual']
    'vectors': [[0.1, 0.2], [0.3, 0.4]],  # Two vectors
    'emotives': {
        'happiness': 0.8,
        'confidence': 0.6,
        'arousal': 0.4
    }
}
```

## Deterministic Properties

### Model Hashing
Every learned sequence receives a deterministic hash-based identifier:
- Format: `MODEL|<sha1_hash>`
- Same sequence always produces same hash
- Hash includes all event data (strings, vectors, emotives)

### Vector Hashing
Vectors are similarly hashed deterministically:
- Format: `VECTOR|<sha1_hash>`
- Consistent across sessions

### Sorting Consistency
- Alphanumeric sorting is consistent across all operations
- Python's default string sorting rules apply
- Case-sensitive (capitals before lowercase)
- Special characters follow ASCII ordering

## Implementation Details

### File Locations
- **Core Processor**: `/kato/workers/kato_processor.py`
- **Vector Handling**: `/kato/representations/vector_object.py`
- **Model Representation**: `/kato/representations/model.py`
- **Prediction Generation**: `/kato/representations/prediction.py`

### API Response Structure
The REST API cognition endpoint returns:
- `short_term_memory`: Current sequence in memory
- `predictions`: List of prediction objects
- `emotives`: Aggregated emotional context
- `symbols`: Current symbols in short-term memory
- `command`: Any command to execute

### Special Behaviors

#### Case Sensitivity
KATO is case-sensitive in string matching:
- 'Hello' ≠ 'hello'
- Capitals sort before lowercase in alphanumeric ordering

#### Unicode Support
KATO supports Unicode characters:
- Sorted according to Python's Unicode handling
- Non-ASCII characters follow Unicode code points

## Common Patterns and Best Practices

### For Sequence Learning
1. Build sequences with consistent event structures
2. Remember that strings will be sorted within events
3. Use empty observations sparingly (they're ignored)
4. Consider max_sequence_length for auto-learning

### For Predictions
1. Check `future` field for upcoming events
2. Use `missing` field to identify incomplete observations
3. Monitor `extras` field for unexpected inputs
4. Leverage `present` field for context understanding

### Testing Emotives
Always follow this pattern:
1. Learn a sequence WITH emotives
2. Clear short-term memory
3. Observe matching events
4. Check predictions for emotives

```python
# Learn with emotives
for strings, emotives in sequence_with_emotives:
    kato.observe({'strings': strings, 'vectors': [], 'emotives': emotives})
kato.learn()

# Clear and observe
kato.clear_short_term_memory()
kato.observe({'strings': ['trigger'], 'vectors': [], 'emotives': {}})

# Check predictions
predictions = kato.get_predictions()
```

### Testing Vector Processing
Vector tests should be flexible:
```python
# Vectors always create STM entries (their name strings)
wm = kato.get_short_term_memory()
assert isinstance(wm, list)  # Check it's a list
assert len(wm[0]) >= 1  # Should contain at least the vector name string
# Don't assert specific content - depends on indexer
```

## Common Pitfalls to Avoid

1. **Don't expect emotives in predictions without learning them first**
2. **Vectors always produce short-term memory entries** - Their purpose is to generate vector names
3. **Don't sort missing/extras fields - order is preserved**
4. **Don't use frequency checks unnecessarily**
5. **Don't assume specific vector symbol formats - depends on indexer**
6. **Assuming String Order Preservation**: Remember strings are sorted within events
7. **Expecting Empty Events to Matter**: They're ignored completely
8. **Confusing `missing` with `future`**: Missing is within present events only
9. **Ignoring Partial Matches**: Present can include partially matching events
10. **Case Insensitive Matching**: KATO is case-sensitive