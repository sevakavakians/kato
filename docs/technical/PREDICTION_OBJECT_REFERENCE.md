# KATO Prediction Object Reference

## Overview

The Prediction Object is the core output structure of the KATO cognitive processor, derived from the GAIuS (General Autonomous Intelligence using Symbols) architecture developed by Intelligent Artifacts. It represents a comprehensive analysis of how well observed patterns match learned models, providing both matching metrics and temporal context.

A Prediction Object is generated when KATO's pattern recognition engine identifies potential matches between current observations and previously learned sequences. Each prediction contains detailed information about the quality of the match, temporal relationships, and various information-theoretic metrics that quantify the prediction's reliability and significance.

## Complete Field Reference

### 1. **name** (string)
**Description**: Unique identifier hash of the learned model/sequence that generated this prediction.  
**Purpose**: Links the prediction back to a specific learned pattern in the knowledge base.  
**Example**: `"model_abc123def456"`

### 2. **type** (string)
**Description**: Classification of the prediction type.  
**Default Value**: `"prototypical"`  
**Purpose**: Indicates the nature of the prediction mechanism used. Currently, KATO uses prototypical predictions based on learned exemplars.

### 3. **frequency** (int32)
**Description**: Number of times this model/pattern has been observed during learning.  
**Purpose**: Indicates how common this pattern is in the training data. Higher frequency suggests a more reliable pattern.  
**Range**: 1 to n (where n is the total number of observations)

### 4. **matches** (repeated string)
**Description**: List of symbols from the current observation that match the expected pattern.  
**Purpose**: Shows which elements of the prediction were correctly identified in the current context.  
**Example**: `["hello", "world"]` when these symbols appear in both the model and current observation.

### 5. **missing** (repeated string)
**Description**: Symbols expected in the present context based on the model but not observed.  
**Purpose**: Identifies gaps between expected and actual observations.  
**Example**: If model expects `["hello", "world"]` but only `"hello"` is observed, missing would be `["world"]`.

### 6. **extras** (repeated string)
**Description**: Symbols observed in the current context that are not part of the expected model.  
**Purpose**: Identifies unexpected elements that don't fit the predicted pattern.  
**Example**: If observing `["hello", "world", "unexpected"]` against a model of `["hello", "world"]`, extras would be `["unexpected"]`.

### 7. **past** (repeated ListValue)
**Description**: Sequence of events that occurred before the present context in the model.  
**Structure**: List of lists, where each inner list represents an event.  
**Purpose**: Provides temporal context showing what should have happened before the current state.  
**Example**: `[["start"], ["initialize"]]` representing two past events.

### 8. **present** (repeated ListValue)
**Description**: Current events being matched against in the prediction.  
**Structure**: List of lists representing the current temporal window.  
**Purpose**: Defines the active matching context for the prediction.  
**Example**: `[["hello", "world"]]` representing the current event.

### 9. **future** (repeated ListValue)
**Description**: Predicted upcoming events based on the learned model.  
**Structure**: List of lists representing expected future events.  
**Purpose**: Provides predictive capability by showing what should happen next.  
**Example**: `[["goodbye"], ["end"]]` representing two expected future events.

### 10. **confidence** (float)
**Description**: Ratio of matched symbols to total symbols in the present context.  
**Formula**: `confidence = len(matches) / total_present_length`  
**Range**: 0.0 to 1.0  
**Purpose**: Measures how completely the current observation matches the expected pattern.

### 11. **evidence** (float)
**Description**: Proportion of the model that has been observed.  
**Formula**: `evidence = len(matches) / model_length`  
**Range**: 0.0 to 1.0  
**Purpose**: Indicates how much of the total model has been confirmed by observations.

### 12. **similarity** (float)
**Description**: Base similarity score between observation and model.  
**Range**: 0.0 to 1.0  
**Purpose**: General measure of pattern resemblance before other metrics are applied.

### 13. **snr** (float)
**Description**: Signal-to-Noise Ratio measuring the quality of the match.  
**Formula**: `snr = (2 * len(matches) - len(extras)) / (2 * len(matches) + len(extras))`  
**Range**: -1.0 to 1.0  
**Purpose**: Quantifies how much "signal" (matches) exists relative to "noise" (extras).

### 14. **fragmentation** (float)
**Description**: Degree of discontinuity in the matched pattern.  
**Formula**: `fragmentation = number_of_blocks - 1`  
**Range**: 0.0 to n  
**Purpose**: Measures how broken up or scattered the pattern match is. Lower values indicate more cohesive matches.

### 15. **entropy** (float)
**Description**: Information entropy of the present symbols using Shannon entropy.  
**Formula**: `entropy = Σ(-p(symbol) * log2(p(symbol)))` for each symbol in present  
**Range**: 0.0 to log2(n) where n is vocabulary size  
**Purpose**: Measures the information content or uncertainty in the present context.

### 16. **hamiltonian** (float)
**Description**: Local entropy considering symbol distribution within the present state.  
**Formula**: `hamiltonian = Σ(expectation(count(symbol)/len(state), total_symbols))` for each symbol  
**Range**: 0.0 to theoretical maximum based on symbol distribution  
**Purpose**: Measures the "energy" or disorder of the local symbol configuration.

### 17. **grand_hamiltonian** (float)
**Description**: Global entropy considering symbol probabilities across the entire knowledge base.  
**Formula**: `grand_hamiltonian = Σ(expectation(global_probability(symbol), total_symbols))` for unique symbols  
**Range**: 0.0 to theoretical maximum  
**Purpose**: Measures information content relative to global symbol distributions.

### 18. **confluence** (float)
**Description**: Probability of the sequence occurring naturally versus randomly.  
**Formula**: `confluence = P(sequence in observations) * (1 - P(sequence occurring randomly))`  
**Range**: 0.0 to 1.0  
**Purpose**: Identifies patterns that are both frequent and non-random, indicating meaningful sequences.

### 19. **itfdf_similarity** (float)
**Description**: Inverse Term Frequency-Document Frequency similarity (adapted from information retrieval).  
**Formula**: `itfdf_similarity = 1 - (distance * frequency / total_ensemble_frequencies)`  
**Range**: 0.0 to 1.0  
**Purpose**: Weights predictions by both local frequency and global rarity, similar to TF-IDF in document retrieval.

### 20. **potential** (float)
**Description**: Composite score combining multiple metrics to rank prediction strength.  
**Formula**: `potential = (evidence + confidence) * snr + itfdf_similarity + (1 / (fragmentation + 1))`  
**Range**: Variable, typically 0.0 to ~5.0  
**Purpose**: Primary ranking metric for selecting the best prediction among alternatives.

### 21. **emotives** (map<string, float>)
**Description**: Emotional or utility values associated with this pattern.  
**Structure**: Dictionary mapping emotive names to float values.  
**Purpose**: Allows patterns to carry emotional salience or utility information for decision-making.  
**Example**: `{"utility": 50.0, "danger": -10.0}`

### 22. **sequence** (internal, not in protobuf)
**Description**: Full sequence structure from the model (used internally during prediction construction).  
**Purpose**: Internal reference to complete model sequence for temporal field extraction.

## Metric Categories

### Matching Metrics
- **matches, missing, extras**: Direct comparison between expected and observed
- **confidence, evidence**: Proportional matching scores
- **similarity, snr**: Quality of the match

### Temporal Metrics
- **past, present, future**: Temporal context and predictions
- **fragmentation**: Temporal cohesion

### Information Theory Metrics
- **entropy**: Local information content
- **hamiltonian, grand_hamiltonian**: Energy/disorder measures
- **confluence**: Meaningfulness of patterns

### Composite Metrics
- **potential**: Overall prediction quality
- **itfdf_similarity**: Frequency-weighted importance

## Usage Notes

1. **Prediction Selection**: When multiple predictions are generated, use `potential` as the primary ranking metric.

2. **Confidence vs Evidence**: 
   - `confidence` measures match quality in the current context
   - `evidence` measures how much of the total model is confirmed

3. **Temporal Fields**: The past/present/future fields maintain the sequential structure of events, preserving the learned temporal relationships.

4. **Symbol Sets**: The matches/missing/extras fields provide detailed diagnostics about prediction quality and help identify partial matches.

5. **Information Metrics**: Entropy, hamiltonian, and confluence provide theoretical grounding in information theory, useful for advanced analysis of prediction quality.

## Mathematical Foundations

The Prediction Object incorporates several mathematical concepts:

- **Information Theory**: Entropy calculations based on Shannon's information theory
- **Statistical Mechanics**: Hamiltonian as an energy function
- **Information Retrieval**: TF-IDF adapted for sequence prediction
- **Signal Processing**: Signal-to-Noise Ratio for match quality
- **Probability Theory**: Confluence as conditional probability

These metrics work together to provide a comprehensive assessment of pattern matching quality, temporal relationships, and predictive confidence in the KATO cognitive processing system.