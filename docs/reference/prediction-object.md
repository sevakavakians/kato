# KATO Prediction Object Reference

## Overview

The Prediction Object is the core output structure of the KATO cognitive processor, derived from the GAIuS (General Autonomous Intelligence using Symbols) architecture developed by Intelligent Artifacts. It represents a comprehensive analysis of how well observed patterns match learned patterns, providing both matching metrics and temporal context.

A Prediction Object is generated when KATO's pattern recognition engine identifies potential matches between current observations and previously learned patterns. Each prediction contains detailed information about the quality of the match, temporal relationships, and various information-theoretic metrics that quantify the prediction's reliability and significance.

## Complete Field Reference

### 1. **name** (string)
**Description**: Unique identifier hash of the learned pattern that generated this prediction.  
**Purpose**: Links the prediction back to a specific learned pattern in the knowledge base.  
**Example**: `"PTRN|abc123def456"`

### 2. **type** (string)
**Description**: Classification of the prediction type.  
**Default Value**: `"prototypical"`  
**Purpose**: Indicates the nature of the prediction mechanism used. Currently, KATO uses prototypical predictions based on learned exemplars.

### 3. **frequency** (int32)
**Description**: Number of times this pattern has been observed during learning.  
**Purpose**: Indicates how common this pattern is in the training data. Higher frequency suggests a more reliable pattern.  
**Range**: 1 to n (where n is the total number of observations)

### 4. **matches** (repeated string)
**Description**: List of symbols from the current observation that match the expected pattern.  
**Purpose**: Shows which elements of the prediction were correctly identified in the current context.  
**Example**: `["hello", "world"]` when these symbols appear in both the pattern and current observation.

### 5. **missing** (repeated string)
**Description**: Symbols that appear in the `present` events but were NOT actually observed.  
**Purpose**: Identifies incomplete or partial observations within the matched events.  
**Critical**: The present field contains complete events; missing lists the symbols from those events that weren't in the observation.  
**Order**: Preserves the pattern order across events.  
**Example 1**: If pattern has `[["a", "b"], ["c", "d"]]` and observing `["a", "c"]`, present would be `[["a", "b"], ["c", "d"]]` (complete events) and missing would be `["b", "d"]`.  
**Example 2**: If pattern has `[["hello", "world"], ["foo", "bar"]]` and observing `["hello", "foo"]`, present would be `[["hello", "world"], ["foo", "bar"]]` and missing would be `["world", "bar"]`.

### 6. **extras** (repeated string)
**Description**: Symbols observed in the current context that are not part of the expected pattern.  
**Purpose**: Identifies unexpected elements that don't fit the predicted pattern.  
**Order**: Preserves the pattern order in which extras were observed across events.  
**Example**: If observing `[["a", "x"], ["b"], ["y"]]` against pattern `[["a"], ["b"]]`, extras would be `["x", "y"]` in that order.

### 7. **past** (repeated ListValue)
**Description**: Pattern of events from the learned pattern that occur BEFORE any observed matches.  
**Structure**: List of lists, where each inner list represents an event.  
**Purpose**: Provides temporal context showing what happened before the first observed event.  
**Important**: Only contains events that were NOT observed in the current context.  
**Example**: If pattern is `[["start"], ["middle"], ["end"]]` and observing `["middle", "end"]`, past would be `[["start"]]`.

### 8. **present** (repeated ListValue)
**Description**: ALL events from the learned pattern that contain ANY observed symbols, including the complete events with all their symbols.  
**Structure**: List of lists representing all matched events with their complete symbol sets.  
**Purpose**: Shows the complete span of the pattern that corresponds to current observations.  
**Critical**: 
- Contains ALL events with matches, from first match to last match
- Includes ALL symbols within those events, even if they weren't observed
- The complete original events are included, not just the observed symbols
**Relationship to missing field**: Symbols that appear in present events but weren't actually observed will be listed in the `missing` field.  
**Example 1**: If observing `["hello", "world"]` from pattern `[["hello"], ["world"], ["end"]]`, present would be `[["hello"], ["world"]]`.  
**Example 2**: If observing `["a", "c"]` from pattern `[["a", "b"], ["c", "d"], ["e"]]`, present would be `[["a", "b"], ["c", "d"]]` (complete events), and missing would be `["b", "d"]`.

### 9. **future** (repeated ListValue)
**Description**: Events from the learned pattern that have NOT been observed yet.  
**Structure**: List of lists representing unobserved future events.  
**Purpose**: Provides predictive capability by showing what should happen next.  
**Important**: Only contains events that come AFTER all observed events.  
**Example**: If pattern is `[["hello"], ["world"], ["end"]]` and observing `["hello", "world"]`, future would be `[["end"]]`.

### 10. **confidence** (float)
**Description**: Ratio of matched symbols to total symbols in the present context.  
**Formula**: `confidence = len(matches) / total_present_length`  
**Range**: 0.0 to 1.0  
**Purpose**: Measures how completely the current observation matches the expected pattern.

### 11. **evidence** (float)
**Description**: Proportion of the pattern that has been observed.  
**Formula**: `evidence = len(matches) / pattern_length`  
**Range**: 0.0 to 1.0  
**Purpose**: Indicates how much of the total pattern has been confirmed by observations.

### 12. **similarity** (float)
**Description**: Base similarity score between observation and pattern.  
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

### 16. **normalized_entropy** (float)
**Description**: Local entropy considering symbol distribution within the present state.
**Formula**: `normalized_entropy = Σ(expectation(count(symbol)/len(state), total_symbols))` for each symbol
**Range**: 0.0 to theoretical maximum based on symbol distribution
**Purpose**: Measures the "energy" or disorder of the local symbol configuration.

### 17. **global_normalized_entropy** (float)
**Description**: Global entropy considering symbol probabilities across the entire knowledge base.
**Formula**: `global_normalized_entropy = Σ(expectation(global_probability(symbol), total_symbols))` for unique symbols
**Range**: 0.0 to theoretical maximum
**Purpose**: Measures information content relative to global symbol distributions.

### 18. **confluence** (float)
**Description**: Probability of the pattern occurring naturally versus randomly.  
**Formula**: `confluence = P(pattern in observations) * (1 - P(pattern occurring randomly))`  
**Range**: 0.0 to 1.0  
**Purpose**: Identifies patterns that are both frequent and non-random, indicating meaningful patterns.

### 19. **itfdf_similarity** (float)
**Description**: Inverse Term Frequency-Document Frequency similarity (adapted from information retrieval).  
**Formula**: `itfdf_similarity = 1 - (distance * frequency / total_ensemble_frequencies)`  
**Range**: 0.0 to 1.0  
**Purpose**: Weights predictions by both local frequency and global rarity, similar to TF-IDF in document retrieval.

### 20. **predictive_information** (float)
**Description**: Measures how much information this specific pattern contributes to predicting its future relative to other patterns in the ensemble.
**Formula**: Based on ensemble-wide statistics and pattern frequencies using information-theoretic mutual information principles.
**Range**: 0.0 to 1.0 (normalized)
**Purpose**: Quantifies the predictive value of this pattern for its anticipated future events. Higher values indicate more reliable predictions.

### 21. **bayesian_posterior** (float)
**Description**: Posterior probability that this pattern generated the observation, calculated using Bayes' theorem.
**Formula**: `P(pattern|obs) = P(obs|pattern) × P(pattern) / P(obs)`
  where:
  - `P(obs|pattern)` = similarity (likelihood)
  - `P(pattern)` = frequency / total_frequencies (prior)
  - `P(obs)` = Σ(similarity × prior) across all patterns (evidence)
**Range**: 0.0 to 1.0
**Purpose**: Provides a rigorous probabilistic interpretation of pattern likelihood. The posterior represents the probability that this specific pattern was the generative source of the current observation, accounting for both how well it matches (likelihood) and how common it is (prior). **Posteriors sum to 1.0 across the ensemble**, making them true probability distributions.
**Use Case**: Ideal for probabilistic decision-making, uncertainty quantification, and when you need predictions that are directly interpretable as probabilities.

### 22. **bayesian_prior** (float)
**Description**: Prior probability of this pattern occurring before observing current data.
**Formula**: `P(pattern) = frequency / Σ(all_frequencies)`
**Range**: 0.0 to 1.0
**Purpose**: Represents the base rate of this pattern in the knowledge base. Patterns learned more frequently have higher priors, reflecting their greater prevalence in training data. This captures the "how common is this pattern?" question independent of the current observation.
**Interpretation**: A prior of 0.5 means this pattern accounts for 50% of all learned patterns (by frequency). Priors across all patterns in the ensemble sum to 1.0.

### 23. **bayesian_likelihood** (float)
**Description**: Likelihood of observing the current data given this pattern.
**Formula**: `P(obs|pattern) = similarity`
**Range**: 0.0 to 1.0
**Purpose**: Quantifies how well this pattern explains the observation, equivalent to the similarity score but framed probabilistically. This is the "how well does the pattern fit the data?" component of Bayes' theorem.
**Note**: Identical to the `similarity` field but explicitly labeled as a likelihood for Bayesian interpretation.

### 24. **potential** (float)
**Description**: Primary composite ranking metric combining multiple pattern quality measures.
**Formula**: `potential = (evidence + confidence) * snr + itfdf_similarity + (1/(fragmentation + 1))`
**Range**: Unbounded. Typically 0.0 to ~3.0 for quality matches. Can be negative when SNR < 0 (excessive noise/extras in observation), indicating low-quality or spurious matches.
**Purpose**: Default ranking metric that balances multiple dimensions:
- Match completeness (evidence + confidence)
- Signal quality (snr)
- Frequency-weighted similarity (itfdf_similarity)
- Pattern cohesion (fragmentation term)

**Configuration**: Can be replaced as ranking metric using `rank_sort_algo` parameter. Alternative rankings include similarity, evidence, confidence, predictive_information, bayesian_posterior, and others.

### 25. **emotives** (map<string, float>)
**Description**: Emotional or utility values associated with this pattern.
**Structure**: Dictionary mapping emotive names to float values.
**Purpose**: Allows patterns to carry emotional salience or utility information for decision-making.
**Example**: `{"utility": 50.0, "danger": -10.0}`

### 26. **anomalies** (array of objects)
**Description**: List of fuzzy token matches documenting non-exact matches when fuzzy token matching is enabled.
**Structure**: Array of objects, each containing:
  - `observed` (string): The token that was actually observed
  - `expected` (string): The pattern token that was fuzzy-matched
  - `similarity` (float): Similarity score between observed and expected (0.0-1.0)
**Purpose**: Provides transparency about which tokens were fuzzy-matched versus exact-matched, enabling detection of data quality issues like typos and misspellings.
**Example**:
```json
"anomalies": [
  {
    "observed": "bannana",
    "expected": "banana",
    "similarity": 0.93
  },
  {
    "observed": "chery",
    "expected": "cherry",
    "similarity": 0.91
  }
]
```
**Behavior**:
- Empty array `[]` when fuzzy matching is disabled (`fuzzy_token_threshold=0.0`)
- Empty array `[]` when all matches are exact
- Contains entries only for non-exact fuzzy matches (exact matches don't generate anomaly entries)
- Fuzzy-matched tokens appear in `matches` field, not in `missing` or `extras`
- Tokens below fuzzy threshold appear in `missing`/`extras` as normal mismatches

**Configuration**: Enable via `fuzzy_token_threshold` parameter (see [Session Configuration](session-configuration.md#fuzzy-token-matching))

### 27. **pattern** (internal, not in protobuf)
**Description**: Full pattern structure from the pattern (used internally during prediction construction).
**Purpose**: Internal reference to complete pattern for temporal field extraction.

### 28. **tfidf_score** (float)
**Description**: TF-IDF (Term Frequency - Inverse Document Frequency) score measuring pattern distinctiveness.
**Formula**:
- For each symbol in pattern: `TF(symbol) = count(symbol in pattern) / pattern_length`
- `IDF(symbol) = log2(total_unique_patterns / patterns_containing_symbol) + 1`
- `TFIDF(symbol) = TF(symbol) × IDF(symbol)`
- `tfidf_score = mean(TFIDF for all unique symbols in pattern)`
**Range**: Typically 0.0 to ~2.0 (unbounded positive)
**Purpose**: Identifies patterns containing distinctive/rare symbols. High scores indicate patterns with uncommon symbols that are frequent within the pattern itself. Useful for finding unique, informative patterns.
**Interpretation**:
- High TF-IDF: Pattern contains rare symbols that appear frequently within it (distinctive)
- Low TF-IDF: Pattern contains mostly common symbols (generic)

## Metric Categories

### Matching Metrics
- **matches, missing, extras**: Direct comparison between expected and observed
- **anomalies**: Fuzzy token matches with similarity scores (when fuzzy matching enabled)
- **confidence, evidence**: Proportional matching scores
- **similarity, snr**: Quality of the match

### Temporal Metrics
- **past, present, future**: Temporal context and predictions
- **fragmentation**: Temporal cohesion

### Information Theory Metrics
- **entropy**: Local information content
- **normalized_entropy, global_normalized_entropy**: Energy/disorder measures
- **confluence**: Meaningfulness of patterns
- **predictive_information**: Pattern's contribution to future prediction

### Probabilistic/Bayesian Metrics
- **bayesian_posterior**: P(pattern|observation) - probability this pattern generated the observation
- **bayesian_prior**: P(pattern) - base rate frequency of this pattern
- **bayesian_likelihood**: P(observation|pattern) - how well pattern explains observation

### Composite Metrics
- **potential**: Multi-dimensional ranking metric (default sorting key)
- **itfdf_similarity**: Frequency-weighted importance
- **tfidf_score**: TF-IDF measure of pattern distinctiveness

## Usage Notes

1. **Prediction Selection**: When multiple predictions are generated, use `potential` as the default ranking metric. The formula `potential = (evidence + confidence) * snr + itfdf_similarity + (1/(fragmentation + 1))` provides balanced ranking across multiple quality dimensions. Alternative ranking metrics can be selected via `rank_sort_algo` configuration to optimize for specific use cases:
   - `similarity`: Best pattern matches by similarity score
   - `frequency`: Most common patterns
   - `predictive_information`: Information-theoretic ranking
   - `bayesian_posterior`: Probabilistic ranking (recommended for uncertainty quantification)

2. **Confidence vs Evidence**: 
   - `confidence` measures match quality in the current context
   - `evidence` measures how much of the total pattern is confirmed

3. **Temporal Fields**: The past/present/future fields maintain the sequential structure of events, preserving the learned temporal relationships.

4. **Symbol Sets**: The matches/missing/extras fields provide detailed diagnostics about prediction quality and help identify partial matches.

5. **Information Metrics**: Entropy, normalized entropy, and confluence provide theoretical grounding in information theory, useful for advanced analysis of prediction quality.

6. **Bayesian Metrics**: The posterior, prior, and likelihood metrics provide rigorous probabilistic interpretation:
   - **Posteriors sum to 1.0**: Unlike other metrics, Bayesian posteriors form a proper probability distribution across the prediction ensemble
   - **Interpretable as probabilities**: A posterior of 0.75 means "75% confidence this pattern generated the observation"
   - **Combines evidence types**: Automatically balances pattern frequency (prior) with observation fit (likelihood)
   - **Ideal for decision-making**: When you need to weight predictions by their probability or calculate expected utilities

## Mathematical Foundations

The Prediction Object incorporates several mathematical concepts:

- **Information Theory**: Entropy calculations based on Shannon's information theory
- **Statistical Mechanics**: Normalized entropy as an energy function
- **Information Retrieval**: TF-IDF adapted for pattern prediction
- **Signal Processing**: Signal-to-Noise Ratio for match quality
- **Probability Theory**: Confluence as conditional probability
- **Bayesian Inference**: Bayes' theorem for posterior probability calculation, combining prior beliefs (pattern frequency) with likelihood (similarity) to compute rigorous posterior probabilities

These metrics work together to provide a comprehensive assessment of pattern matching quality, temporal relationships, and predictive confidence in the KATO cognitive processing system.