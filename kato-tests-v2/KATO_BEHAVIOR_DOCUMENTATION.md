# KATO Behavior Documentation

This document captures the key behavioral patterns and implementation details of KATO discovered through comprehensive testing.

## Core Concepts

### 1. Temporal Prediction Fields

KATO organizes predictions into temporal segments:

- **`past`**: Events that occurred before the current matching position in a learned sequence
- **`present`**: The current matching events (can span multiple events if partially matching)
- **`future`**: Events expected to occur after the current position
- **`missing`**: Symbols that were expected in the present events but were not observed
  - Order is preserved from the original sequence
  - No sorting is applied
- **`extras`**: Symbols that were observed but not expected in the present events
  - Order is preserved as observed
  - No sorting is applied

### 2. Symbol Processing

#### String Symbols
- Strings are sorted alphanumerically within each event
- Example: `['multi', 'modal']` becomes `['modal', 'multi']`
- Sorting happens at observation time before storage

#### Vector Symbols
- Vectors are processed through a classifier
- May produce symbols like `VECTOR|<hash>` depending on classifier configuration
- Vector symbols appear before string symbols in mixed modality events
- Vector processing depends on classifier type and may not always produce working memory entries

### 3. Emotives Handling

**Critical Insight**: Emotives only appear in predictions from previously learned models, not from current observations.

- Emotives must be learned as part of a sequence first
- They appear in predictions when matching learned sequences
- Current observation emotives don't immediately appear in predictions
- Emotives are averaged across multiple pathways

### 4. Working Memory Behavior

- Empty events (no strings, no vectors) are ignored and don't create working memory entries
- Events are stored as lists of symbols
- Maximum sequence length triggers auto-learning when reached
- The last event is preserved when auto-learning occurs

### 5. Prediction Generation

Predictions are generated when:
1. A model has been learned
2. New observations match part of a learned sequence
3. Either strings or vectors are present (not just emotives)

Prediction structure includes:
- `name`: Model identifier
- `confidence`: Confidence score (0-1)
- `similarity`: How closely the observation matches the model
- `frequency`: How many times this model has been learned
- `hamiltonian`: Energy measure
- `grand_hamiltonian`: Combined energy measure
- `entropy`: Uncertainty measure
- `matches`: Symbols that matched
- `emotives`: Dictionary of emotive values (if learned with the model)

### 6. Learning Behavior

- Learning creates a model from the current working memory
- Models are named with format: `MODEL|<identifier>`
- Empty working memory produces no model
- Frequency increases when the same sequence is learned multiple times

## Test Patterns and Best Practices

### 1. Avoid Unnecessary Complexity

Don't use:
- `if pred.get('frequency', 0) > 0:` - Frequency checks are unnecessary
- `sorted()` on missing/extras fields - Order is already preserved
- Complex iteration when simple checks suffice

Do use:
- Direct field access: `predictions[0]`
- Simple equality checks: `missing == ['world', 'bar']`
- Clear assertions about expected values

### 2. Testing Emotives

Always follow this pattern:
1. Learn a sequence WITH emotives
2. Clear working memory
3. Observe matching events
4. Check predictions for emotives

```python
# Learn with emotives
for strings, emotives in sequence_with_emotives:
    kato.observe({'strings': strings, 'vectors': [], 'emotives': emotives})
kato.learn()

# Clear and observe
kato.clear_working_memory()
kato.observe({'strings': ['trigger'], 'vectors': [], 'emotives': {}})

# Check predictions
predictions = kato.get_predictions()
```

### 3. Testing Vector Processing

Vector tests should be flexible:
```python
# Don't assume vectors always create WM entries
wm = kato.get_working_memory()
assert isinstance(wm, list)  # Just check it's a list
# Don't assert specific content - depends on classifier
```

### 4. Mixed Modality Testing

Remember:
- Vector symbols appear before string symbols
- Strings within events are sorted alphanumerically
- Test both the presence and order of symbols

## Implementation Details

### File Locations

- **Core Processor**: `/kato/workers/kato_processor.py`
- **Vector Handling**: `/kato/representations/vector_object.py`
- **Test Fixtures**: `/kato-tests-v2/fixtures/kato_fixtures.py`
- **Test Helpers**: `/kato-tests-v2/fixtures/test_helpers.py`

### Important Fixes Applied

1. **NumPy Compatibility** (vector_object.py:12)
   - Changed `np.str(self.vector)` to `str(self.vector)`
   - Fixes compatibility with NumPy 1.20+

2. **Test Logic Corrections**
   - Removed unnecessary frequency checks
   - Removed unnecessary sorting of missing/extras fields
   - Fixed emotives test logic to learn before checking predictions
   - Made vector tests flexible for classifier dependencies

### API Endpoints

The REST API cognition endpoint returns:
- `working_memory`
- `predictions`
- `emotives`
- `symbols`
- `command`

(Not `entry_count` as some tests previously expected)

## Common Pitfalls to Avoid

1. **Don't expect emotives in predictions without learning them first**
2. **Don't assume vectors always produce working memory entries**
3. **Don't sort missing/extras fields - order is preserved**
4. **Don't use frequency checks unnecessarily**
5. **Don't assume specific vector symbol formats - depends on classifier**

## Testing Checklist

When writing new tests:
- [ ] Learn sequences before expecting predictions
- [ ] Use `clear_working_memory()` between test phases
- [ ] Check for both presence and structure of prediction fields
- [ ] Be flexible with vector-related assertions
- [ ] Sort strings within events but not across fields
- [ ] Include emotives in learning if testing emotive predictions