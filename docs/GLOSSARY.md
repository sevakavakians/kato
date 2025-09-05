# KATO Glossary

Comprehensive definitions of terms and concepts used in the KATO system.

## Core Concepts

### Pattern
The fundamental learning unit in KATO. A pattern represents a learned structure that can be:
- **Temporal Pattern (Sequence)**: Time-ordered events with temporal dependency
- **Profile Pattern**: Collections without temporal dependency or ordering requirements

All patterns are identified by a unique hash: `PTRN|<sha1_hash>` where the hash is computed from the pattern's data structure.

### STM (Short-Term Memory)
Temporary storage for current observation sequences. STM is a deque (double-ended queue) containing events that haven't been learned yet. When STM reaches `MAX_PATTERN_LENGTH`, auto-learning may be triggered.

### LTM (Long-Term Memory)
Persistent storage of learned patterns in MongoDB. Each pattern is stored with its frequency, emotives, and structural data.

### Event
A single observation unit containing one or more symbols. Events are represented as lists of strings, e.g., `["hello", "world"]`. Events can contain:
- String symbols (direct observations)
- Vector-derived symbols (e.g., `VECTOR|<hash>`)
- Both types mixed

### Symbol
An atomic unit of information within an event. Symbols are strings that represent either:
- Direct string observations
- Vector embeddings converted to symbolic form
- Other data converted to string representation

## Data Types

### Observation
Input data sent to KATO containing:
- **strings**: List of string symbols
- **vectors**: Optional 768-dimensional vector embeddings
- **emotives**: Optional emotional/utility values
- **unique_id**: Optional tracking identifier

### Prediction
Output from pattern matching containing temporal segmentation and match metrics. Key fields include:
- **past/present/future**: Temporal segmentation of the pattern
- **matches**: Symbols that match between observation and pattern
- **missing**: Pattern symbols not observed
- **extras**: Observed symbols not in pattern

### Emotives
Emotional or utility values associated with observations and patterns. These are key-value pairs where keys are emotion names and values are floating-point intensities (typically 0.0 to 1.0).

## Processing Concepts

### Percept Data
The raw input perception - the last observation received by the processor before any processing. This includes the original strings, vectors, and emotives exactly as provided.

### Cognition Data
The current cognitive state after processing, including:
- Current predictions
- Active symbols (after vector processing)
- Short-term memory state
- Averaged emotives
- Processing metadata

### Genes
Configuration parameters that control processor behavior. These can be updated at runtime and include:
- `recall_threshold`: Pattern matching sensitivity
- `max_predictions`: Maximum predictions to return
- `persistence`: STM persistence length
- And many others

### Genome Manifest
The complete configuration profile for a processor instance, containing all genes and their values.

## Pattern Processing

### Pattern Hashing
Deterministic SHA1 hashing of pattern data structures to create unique identifiers. The hash is computed from the string representation of the pattern's event sequence.

### Pattern Frequency
The number of times a specific pattern has been learned. Starts at 1 when first learned and increments each time the same pattern structure is re-learned.

### Temporal Segmentation
The process of dividing patterns into three temporal regions:
- **Past**: Events before the first matching event
- **Present**: ALL events containing matching symbols (complete events, not just matched symbols)
- **Future**: Events after the last matching event

### Recall Threshold
A value between 0.0 and 1.0 controlling pattern matching sensitivity:
- 0.0: Include all patterns (even with no matches)
- 0.1: Default - permissive matching
- 0.5: Moderate filtering
- 1.0: Exact matches only

## Metrics

### Hamiltonian
An entropy-like measure of pattern complexity. Calculates the information content based on symbol distribution within the state. Requires non-empty state to compute.

### Grand Hamiltonian
Extended version of the Hamiltonian using global symbol probability cache. Provides a more comprehensive entropy calculation considering the entire knowledge base.

### Confluence
The probability of a pattern occurring versus random chance. Calculated as: `p(e|h) * (1 - conditionalProbability)`. Returns 0 for empty state.

### Evidence
The strength of pattern match, calculated as the ratio of matched symbols to total pattern length (0.0 to 1.0).

### Confidence
The ratio of matched symbols to the length of the "present" segment (0.0 to 1.0). Indicates how completely the current observation matches the relevant portion of the pattern.

### SNR (Signal-to-Noise Ratio)
A measure of match quality considering both matches and extras:
```
SNR = (2 * matches - extras) / (2 * matches + extras)
```

### Similarity
Overall pattern similarity score (0.0 to 1.0) computed using sequence matching algorithms.

### Fragmentation
A measure of pattern cohesion, calculated as the number of matching blocks minus 1. Can be -1 in edge cases, indicating no matches.

### Potential
Composite metric for ranking predictions, combining multiple factors:
```
potential = (evidence + confidence) * snr + similarity + (1/(fragmentation + 1))
```

### ITFDF Similarity
Inverse Term Frequency-Document Frequency similarity. Measures pattern relevance based on frequency and distance. Used in information retrieval-style matching.

## Processing Modes

### Auto-Learning
Automatic pattern learning triggered when STM reaches `MAX_PATTERN_LENGTH`. When triggered:
1. Creates a pattern from current STM
2. Clears STM (keeping last event for continuity)
3. Stores pattern in long-term memory

### Manual Learning
Explicit pattern learning triggered by API call. Learns current STM contents regardless of length (minimum 2 strings required).

### Vector Processing
Conversion of numerical vectors to symbolic representations:
1. Vector is hashed to create unique identifier
2. Stored in Qdrant vector database
3. Represented symbolically as `VECTOR|<hash>`

### Sorting Mode
When `SORT=true` (default), symbols within events are sorted alphabetically for deterministic pattern matching.

## Architecture Components

### KatoProcessor
The core processing engine that:
- Manages observations and predictions
- Maintains STM and coordinates with LTM
- Handles vector and pattern processing

### PatternProcessor
Specialized component for pattern operations:
- Creates new patterns from STM
- Recognizes known patterns
- Generates predictions

### VectorProcessor
Handles vector embeddings:
- Converts vectors to symbols
- Manages vector database operations
- Performs similarity searches

### PatternSearcher
Optimized pattern matching engine:
- Parallel pattern searching
- Fast sequence matching algorithms
- Index-based optimization

## Database Terms

### MongoDB Collections
- **patterns_kb**: Stores pattern structures and metadata
- **symbols_kb**: Stores symbol frequency and probability data
- **predictions_kb**: Stores prediction results
- **metadata**: Stores processor metadata

### Qdrant Collections
Vector database collections named `vectors_{processor_id}` storing:
- Vector embeddings
- Associated metadata
- HNSW index for fast similarity search

### Processor Isolation
Each processor instance uses a unique `processor_id` for complete database isolation:
- MongoDB: Database name = processor_id
- Qdrant: Collection name = `vectors_{processor_id}`
- Prevents cross-contamination between instances

## Configuration Terms

### Persistence
The length of emotional/utility value history maintained. Controls how many historical emotives are averaged.

### Smoothness
Smoothing factor for pattern matching algorithms. Higher values provide more lenient matching.

### Quiescence
Period of inactivity before certain operations trigger. Used for pattern stabilization.

### Search Depth
Maximum depth for pattern search operations. Controls how extensively the system searches for matches.

### Indexer Type
Type of vector indexing used (default: 'VI' for vector indexing).

### Auto-Act Method
Method for automatic actions (default: 'none'). Can trigger automated responses based on patterns.

### Auto-Act Threshold
Threshold value for triggering automatic actions (0.0 to 1.0).

## Special Symbols

### PTRN| Prefix
Identifier prefix for patterns. Format: `PTRN|<sha1_hash>`

### VECTOR| Prefix
Identifier prefix for vector-derived symbols. Format: `VECTOR|<hash>`

## Edge Cases and Boundaries

### Empty Events
Empty events `[]` are NOT supported and should be filtered before observation.

### Minimum Pattern Length
Patterns require at least 2 strings total across all events to be valid for prediction generation.

### Division by Zero Protection
Various metrics include protection against division by zero:
- Hamiltonian calculations check for empty state
- SNR calculations handle zero denominators
- Confidence calculations check for zero present length

### Fragmentation = -1
Special case indicating no matching blocks found. Handled specially in potential calculations.