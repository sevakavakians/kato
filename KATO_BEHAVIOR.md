# KATO Behavior Documentation

This document provides detailed information about KATO's core behaviors, particularly focusing on sequence processing, prediction structure, and memory management.

## Table of Contents
1. [Sequence Processing](#sequence-processing)
2. [Prediction Structure](#prediction-structure)
3. [Memory Management](#memory-management)
4. [Deterministic Behaviors](#deterministic-behaviors)
5. [Multi-Modal Processing](#multi-modal-processing)

## Sequence Processing

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

### Alphanumeric Sorting Within Events
**Important**: KATO sorts strings alphanumerically within each event while preserving the order of events in a sequence.

#### Example:
```python
# Input observation
observe({'strings': ['zebra', 'apple', 'banana']})

# Stored in working memory as
[['apple', 'banana', 'zebra']]  # Sorted alphanumerically
```

#### Sequence Example:
```python
# Three separate observations
observe({'strings': ['z']})
observe({'strings': ['a']})  
observe({'strings': ['m']})

# Working memory maintains event order
[['z'], ['a'], ['m']]  # Order preserved, no sorting between events
```

### Empty Events
KATO ignores empty events - they do not change working memory or affect predictions.

```python
# Empty observation
observe({'strings': [], 'vectors': [], 'emotives': {}})
# Result: No change to working memory

# Sequence with empty events
observe({'strings': ['first']})
observe({'strings': []})         # Ignored
observe({'strings': ['second']})
# Working memory: [['first'], ['second']]
```

## Prediction Structure

KATO's predictions use sophisticated temporal segmentation to understand sequences. Each prediction contains fields that segment the sequence temporally and identify discrepancies.

### Temporal Fields

#### Past
Events that occurred before the current matching state in the learned sequence.

#### Present
All contiguous events identified by matching symbols. Not all symbols need to match - just enough to delimit the start and end of the present state.

#### Future
Events that come after the present state in the learned sequence.

### Discrepancy Fields

#### Missing
Symbols that are expected in the `present` state based on the learned sequence but were not observed in the working memory.

#### Extras
Symbols that were observed but are not expected in the `present` state based on the learned sequence.

### Examples

#### Example 1: Simple Sequential Match
```python
# Learned sequence
[['alpha'], ['beta'], ['gamma']]

# Observation
[['beta']]

# Prediction result
{
    'past': [['alpha']],
    'present': [['beta']],
    'future': [['gamma']],
    'missing': [],
    'extras': []
}
```

#### Example 2: Partial Event Match with Missing Symbols
```python
# Learned sequence  
[['hello', 'world'], ['foo', 'bar']]

# Observation (missing 'world' and 'bar')
[['hello'], ['foo']]

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
[['cat', 'bird'], ['dog', 'fish']]

# Prediction result
{
    'past': [],
    'present': [['cat'], ['dog']],
    'missing': [],
    'extras': ['bird', 'fish'],  # Observed but not expected
    'future': []
}
```

#### Example 4: Middle Sequence Match
```python
# Learned sequence
[['start'], ['middle1'], ['middle2'], ['end']]

# Observation
[['middle1'], ['middle2']]

# Prediction result
{
    'past': [['start']],
    'present': [['middle1'], ['middle2']],
    'future': [['end']],
    'missing': [],
    'extras': []
}
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
The `present` field includes all contiguous events that are identified by matching symbols. This means:
- Partial matches can trigger inclusion in the present state
- The present can span multiple events if they have matching symbols
- Not all symbols need to match for an event to be part of the present

## Memory Management

### Working Memory
- Accumulates observations as events
- Each observation creates one event (unless empty)
- Maintains temporal order of events
- Cleared when learning is triggered

### Long-Term Memory
- Stores learned sequences with deterministic hashes
- Sequences identified by MODEL|<sha1_hash> format
- Persists across working memory clears
- Used for generating predictions

### Max Sequence Length
- Configurable limit on working memory size
- Auto-learns when limit reached
- Keeps last event in working memory after auto-learn

## Deterministic Behaviors

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

## Multi-Modal Processing

KATO processes multiple data types simultaneously within each observation:

### Strings
- Symbolic/textual data
- Sorted alphanumerically within events
- Primary matching mechanism for predictions

### Vectors
- Numeric arrays of any dimension
- Processed by classifiers (CVC/DVC)
- Can be used for similarity calculations

### Emotives
- Key-value pairs representing emotional context
- Values are floating-point numbers (0.0 to 1.0)
- Aggregated across observations (averaging)
- Preserved in learned sequences

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

## Special Behaviors

### Case Sensitivity
KATO is case-sensitive in string matching:
- 'Hello' ≠ 'hello'
- Capitals sort before lowercase in alphanumeric ordering

### Numeric String Sorting
Numeric strings are sorted as strings, not numbers:
- Sorting ['10', '2', '1'] results in ['1', '10', '2']
- Not ['1', '2', '10'] as would happen with numeric sorting

### Symbol Repetition
Repeated symbols within an event may be handled specially:
- Depends on KATO's internal deduplication logic
- Sorting happens after any deduplication

### Unicode Support
KATO supports Unicode characters:
- Sorted according to Python's Unicode handling
- Non-ASCII characters follow Unicode code points

## Usage Recommendations

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

### For Testing
1. Use helper functions for sorting validation
2. Account for alphanumeric sorting in assertions
3. Test with multi-modal data for comprehensive coverage
4. Verify deterministic hashing consistency

## Common Pitfalls

1. **Assuming String Order Preservation**: Remember strings are sorted within events
2. **Expecting Empty Events to Matter**: They're ignored completely
3. **Confusing `missing` with `future`**: Missing is within present events only
4. **Ignoring Partial Matches**: Present can include partially matching events
5. **Case Insensitive Matching**: KATO is case-sensitive

## API Integration

When integrating with KATO's API:
- Always sort expected strings for comparison
- Handle empty responses for empty observations
- Parse prediction fields correctly
- Account for deterministic MODEL| prefixes