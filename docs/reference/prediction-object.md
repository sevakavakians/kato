# KATO Prediction Object Reference

## Overview

The Prediction Object is the core output structure of the KATO cognitive processor, derived from the GAIuS (General Autonomous Intelligence using Symbols) architecture. It represents a comprehensive analysis of how well observed patterns match learned patterns, providing both matching metrics and temporal context.

A Prediction Object is generated when KATO's pattern recognition engine identifies potential matches between current observations and previously learned patterns. Each prediction contains detailed information about the quality of the match, temporal relationships, and various information-theoretic metrics that quantify the prediction's reliability and significance.

A response holds a ranked list of Prediction Objects and three figures computed over the whole set of candidates: `future_potentials`, the probability of each next event; `ends_here`, the probability that no event follows; and `chance_posterior`, the probability that no learned pattern explains the observation better than chance. They are described under [Ensemble Fields](#ensemble-fields). [Metrics at a Glance](#metrics-at-a-glance) says what each metric answers and what data it suits, and [Measured Accuracy](#measured-accuracy) gives each one's accuracy as a ranking key.

## Complete Field Reference

### 1. **name** (string)
**Description**: Unique identifier hash of the learned pattern that generated this prediction.  
**Purpose**: Links the prediction back to a specific learned pattern in the knowledge base.  
**Example**: `"a5b9c3d7e8f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5"`  
**Note**: Pattern names in predictions are plain SHA1 hashes. The `PTRN|` prefix only appears in `Pattern.__repr__()` for human-readable display.

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

### 5. **missing** (array[array[string]], event-aligned)
**Description**: Symbols that appear in the `present` events but were NOT actually observed.  
**Purpose**: Identifies incomplete or partial observations within the matched events.  
**Structure**: List of lists, where each sub-list corresponds to a `present` event and contains the symbols from that event not found in the observation.  
**Critical**: The present field contains complete events; missing lists the symbols from those events that weren't in the observation.  
**Example 1**: If pattern has `[["a", "b"], ["c", "d"]]` and observing `["a", "c"]`, present would be `[["a", "b"], ["c", "d"]]` (complete events) and missing would be `[["b"], ["d"]]`.  
**Example 2**: If pattern has `[["hello", "world"], ["foo", "bar"]]` and observing `["hello", "foo"]`, present would be `[["hello", "world"], ["foo", "bar"]]` and missing would be `[["world"], ["bar"]]`.  
**Repeated symbols**: attribution follows the matcher's alignment of positions, not symbol identity, so a pattern symbol that occurs several times is only "missing" at the occurrence that went unmatched. Matching runs on the flattened sequence, so the alignment is refined with event structure before segmentation: a matched symbol is attributed to the pattern event where the other symbols of its observed event matched (dropping the `y` from event 0 or from event 1 of `[["x","y"],["y","z"],…]` is reported against the right event), and a symbol observed alone prefers the occurrence that leaves the fewest symbols missing (a lone `["x"]` matches an exact pattern event `["x"]` rather than the `x` of `["x","y"]`). The number of matches and `similarity` never change under this refinement.  
**Known limitations**: matching is flat, so an observation that splits one pattern event across two observations, or merges two pattern events into one, still counts as a complete match; the matcher's blocks are not always a maximum common subsequence while `similarity` uses the true one, so `matches` can undercount in rare repeated-symbol cases.

### 6. **extras** (array[array[string]], event-aligned)
**Description**: Symbols observed in the current context that are not part of the expected pattern.  
**Purpose**: Identifies unexpected elements that don't fit the predicted pattern.  
**Structure**: List of lists, where each sub-list corresponds to an STM event and contains observed symbols from that event not expected in the pattern's present events.  
**Example**: If observing `[["a", "x"], ["b"], ["y"]]` against pattern `[["a"], ["b"]]`, extras would be `[["x"], [], ["y"]]`.

**Segmentation**: `past`/`present`/`future` boundaries come from the matched *positions* (the first and last matched symbol's events), so a match that starts or ends inside an event includes that whole event in `present` with its unmatched symbols in `missing`. Single-symbol observations go through the fast path (every pattern containing the symbol, in any event) and are segmented the same way: a lone symbol from a later event puts the events before it in `past`.

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
**Example 2**: If observing `["a", "c"]` from pattern `[["a", "b"], ["c", "d"], ["e"]]`, present would be `[["a", "b"], ["c", "d"]]` (complete events), and missing would be `[["b"], ["d"]]` (event-aligned, one sub-list per present event).

### 9. **future** (repeated ListValue)
**Description**: Events from the learned pattern that have NOT been observed yet.  
**Structure**: List of lists representing unobserved future events.  
**Purpose**: Provides predictive capability by showing what should happen next.  
**Important**: Only contains events that come AFTER all observed events.  
**Example**: If pattern is `[["hello"], ["world"], ["end"]]` and observing `["hello", "world"]`, future would be `[["end"]]`.

**Event grouping matters**: the same symbols learned as one event or as several are different patterns, and they segment differently. Learned as `[["hello", "world"]]`, observing `["hello"]` gives `present=[["hello", "world"]]`, `missing=[["world"]]`, `future=[]` — the unobserved symbol belongs to the event you are already inside. Learned as `[["hello"], ["world"]]`, the same observation gives `present=[["hello"]]`, `missing=[[]]`, `future=[["world"]]`.

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
**Formula**: `similarity = 2 * LCS / (len(pattern) + len(STM))` with token matching (the default). Lengths are counted in symbols. `LCS` is the length of the longest common subsequence of the pattern and the STM, counted by the candidate scorer. It can be larger than `len(matches)`, which comes from the alignment.  
**Range**: 0.0 to 1.0  
**Purpose**: General measure of pattern resemblance before other metrics are applied.  
**Note**: For an STM of two or more symbols, a pattern is returned only when `similarity >= recall_threshold`, so the threshold decides how much of a pattern must be observed before KATO predicts from it. The table under [recall_threshold](../users/configuration.md#recall_threshold) gives that share for each threshold.

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
**Description**: Information entropy of the pattern's symbols using Shannon entropy.  
**Formula**: `entropy = Σ(-p(symbol) * log2(p(symbol)))` for each symbol in the pattern  
**Range**: 0.0 to log2(n) where n is vocabulary size  
**Purpose**: Measures the information content or uncertainty of the pattern. Pattern-intrinsic: the same for every prediction of a given pattern, whatever part of it matched.

### 16. **normalized_entropy** (float)
**Description**: Local entropy considering symbol distribution within the pattern.  
**Formula**: `normalized_entropy = Σ(expectation(count(symbol)/len(pattern), total_symbols))` for each symbol, where `expectation(p, n) = -p × log_n(p)` and `total_symbols` is the number of distinct symbols in the node. This is `entropy / log2(total_symbols)`.  
**Range**: 0.0 to 1.0  
**Purpose**: Measures the "energy" or disorder of the local symbol configuration.

### 17. **global_normalized_entropy** (float)
**Description**: Global entropy considering symbol probabilities across the entire knowledge base.  
**Formula**: `global_normalized_entropy = Σ(expectation(global_probability(symbol), total_symbols))` for unique symbols, where `global_probability(symbol)` is the share of the node's patterns that hold the symbol  
**Range**: 0.0 to theoretical maximum  
**Purpose**: Measures information content relative to global symbol distributions.

### 18. **confluence** (float)
**Description**: How far the pattern is from a chance co-occurrence of its symbols, in bits.  
**Formula**: `confluence = log2(frequency / F) + Σ log2(1 / q(s))`, summed over every symbol of the pattern.
  - `F` = `total_pattern_frequencies`: the sum of every pattern's frequency in the node. Each learn counts once.
  - `q(s)` = the symbol's share of all learned symbol occurrences in the node.

**Range**: Unbounded, in bits. It grows with the length of the pattern and with the rarity of its symbols.  
**Purpose**: The base-2 logarithm of how many times more often the pattern was learned than its symbols would have come together by chance. A high value marks a pattern that is both frequent and non-random. It is a property of the pattern and the node, so it is the same for every prediction of that pattern, whatever was observed.  
**Relation to `good_odds`**: `confluence` is the most `good_odds` a prediction of the pattern can reach. An exact, complete observation of the pattern scores `confluence` less 0.074 bits per symbol.  
**Use**: Describing learned patterns. It does not read the observation, so it is a poor ranking key.

### 19. **itfdf_similarity** (float)
**Description**: One minus the distance between the observation and the matched part of the pattern, with the distance scaled by the pattern's share of the candidates' frequency.  
**Formula**: `itfdf_similarity = 1 - (distance * frequency / candidate_frequency)`
  - `distance = 1 - cosine(STM, present)`, both read as bags of symbols, each symbol weighted by the share of the node's patterns that hold it.
  - `candidate_frequency` = the sum of the frequencies of every candidate above the recall threshold.

**Range**: 0.0 to 1.0. Exactly 1.0 when the STM and `present` hold the same symbols.  
**Purpose**: Measures closeness on the symbols the node's patterns share. The distance counts in proportion to the pattern's share of the candidates' frequency, so at the same distance the pattern with the larger share scores lower.  
**Use**: A symbol-overlap check between the STM and `present`. As a ranking key it sits well below `potential`; see [Measured Accuracy](#measured-accuracy).

### 20. **predictive_information** (float)
**Description**: This prediction's part of the information the STM carries about the next event, in bits.  
**Formula**: `predictive_information = share * log2(P(E | STM) / q(E))`
  - `E` = the prediction's next event: the first event of its `future`.
  - `P(E | STM)` = the probability of that event in [`future_potentials`](#future_potentials).
  - `share` = this prediction's own part of that probability: `e^potential` over the sum of `e^potential` across every candidate.
  - `q(E)` = the chance probability of the event: the product of `q(s)` over its symbols.

**Range**: Unbounded, in bits. 0.0 for a prediction with no `future`. Negative when the ensemble makes the event less probable than chance does.  
**Purpose**: Over the predictions of a request the values add up to `Σ P(E | STM) * log2(P(E | STM) / q(E))` over the events proposed: how many bits the STM tells about which event comes next, measured against chance. Each prediction's value is its part of that total. When no candidate has ended, the probabilities add up to 1 and the total is the Kullback-Leibler divergence of the next-event distribution from chance.  
**Use**: Measuring how informative a context is, and which patterns carry the information. As a ranking key it trades probability for rarity, so it ranks slightly worse than `potential`.

### 21. **bayesian_posterior** (float)
**Description**: Posterior probability that this pattern, and not another candidate or chance, produced the observation.  
**Formula**: `bayesian_posterior = 2^good_odds / (1 + Σ 2^good_odds)`, the sum taken over every candidate above the recall threshold.
  - `2^good_odds` is the posterior odds of the pattern against chance: prior times likelihood ratio.
  - The `1` is chance itself, the hypothesis that no learned pattern is occurring. What the candidates leave over is returned beside the predictions as [`chance_posterior`](#chance_posterior).

**Range**: 0.0 to 1.0. The posteriors of every candidate and `chance_posterior` add up to 1.0. When `max_predictions` returns fewer predictions than there are candidates, the returned posteriors add up to less.  
**Purpose**: Answers "which learned pattern am I looking at, and how sure is that". A lone candidate is weighed against chance and gets `2^good_odds / (1 + 2^good_odds)`, so a weak match is not believed just for being the only one.  
**Use**: Identifying the pattern, and thresholding on a probability. It ranks exactly as `good_odds` does.  
**Caution**: The model adds each matched symbol's bits as if the symbols were independent observations. Where symbols travel together (phrases in text, fixed motifs), the same evidence is counted more than once and the posterior is pushed toward 0 and 1: it still ranks well, and it overstates its certainty. For the probability of what comes next, use `future_potentials`.

### 22. **bayesian_prior** (float)
**Description**: Prior probability of the pattern before the observation: its share of everything the node has learned.  
**Formula**: `bayesian_prior = frequency / F`, with `F` = `total_pattern_frequencies`, the sum of every pattern's frequency in the node.  
**Range**: Above 0.0, up to 1.0.  
**Purpose**: The base rate of the pattern. It depends on the node alone, not on the observation or on which other patterns matched: a pattern learned 50 times in a node of 200 learns has a prior of 0.25 in every prediction. Over all the patterns of a node the priors add up to 1.0; over the predictions of one request they add up to the share of the node's learns that the candidates hold.

### 23. **bayesian_likelihood** (float)
**Description**: How much more probable the observation is under this pattern than under chance, as a base-2 logarithm. This is I. J. Good's weight of evidence.  
**Formula**: `bayesian_likelihood = Σ log2((1 - e) / q(s)) - log2(1 / e) * (missing + extras)`, the sum taken over the matched symbols.
  - `e` = 0.05, the assumed chance that a symbol is dropped from, or intrudes into, an observation of a pattern. It is the only constant.
  - Each match adds `log2(0.95 / q(s))` bits: more for a rarer symbol.
  - Each missing or extra symbol costs `log2(20)` = 4.32 bits.

**Range**: Unbounded, in bits. Positive when the pattern explains the observation better than chance does, negative when worse.  
**Purpose**: The strength of the match on its own, before how often the pattern was learned is counted. An unobserved `past` or `future` is not evidence against a pattern, so the value does not fall as a pattern's unobserved part grows.  
**Why a logarithm of a ratio**: A likelihood is only defined up to a factor shared by every hypothesis. The plain probability of the observation is zero for every pattern as soon as the STM holds one symbol that was never learned; measured against chance, that symbol's probability cancels. The ratio itself overflows a float past 1,024 bits, so the field holds the bits.

### 24. **good_odds** (float)
**Description**: The base-2 logarithm of the posterior odds of this pattern against chance. Named for I. J. Good.  
**Formula**:
```
good_odds = log2(frequency / F)                         how often the pattern was learned
          + Σ over matched symbols of log2((1 - e) / q(s))   each match, worth more for a rarer symbol
          - log2(1 / e) * (missing + extras)            each symbol that had to be explained away
```
Every term is in bits. `F` is the sum of every pattern's frequency in the node, `q(s)` is the symbol's share of all learned symbol occurrences, and `e` = 0.05 is the only constant: the assumed chance that a symbol is dropped, added or replaced between the pattern and the observation.

**What it is**: The logarithm of how much more probable the observation is under "this pattern is occurring" than under "the symbols were drawn by their frequency", plus the pattern's prior. Nothing in it is trained.

**The name**: The three parts are the terms of an identity that Good stated for weighing evidence: the initial log-odds plus the weight of evidence equal the final log-odds.

| Part of the formula | Good's term | Field |
|---|---|---|
| `log2(frequency / F)` | prior (initial) log-odds | `log2(bayesian_prior)` |
| `log2((1 - e) / q(s))` per matched symbol, `-log2(1 / e)` per missing or extra symbol | weight of evidence, in bits | `bayesian_likelihood` |
| the total | posterior (final) log-odds | `good_odds` |

The weight of evidence is the logarithm of the factor by which an observation multiplies the odds, which for two simple hypotheses is the likelihood ratio. `log2(bayesian_prior) + bayesian_likelihood = good_odds` holds exactly for every prediction.

**Range**: Unbounded, in bits. Above 0 the pattern explains the observation better than chance; each further bit doubles the odds.  
**Purpose**: A match score with a meaning that does not depend on the request: it is computed from the prediction's own fields and the node's counts, so it does not change with which other candidates matched, with their order, or with `max_predictions`. An exact match ranks above any looser match of the same pattern frequency.  
**Use**: Ranking where each score has to be explainable term by term; comparing matches across requests; deciding whether a match beats chance at all. `bayesian_posterior` turns it into a probability over the candidates.  
**Reference**: I. J. Good, "Weight of Evidence: A Brief Survey", in *Bayesian Statistics 2* (1985), pp. 249-270 ([scan](https://www.waterboards.ca.gov/water_issues/programs/tmdl/docs/303d_policydocs/207.pdf)).

### 25. **potential** (float)
**Description**: The default ranking score: a weighted sum of eleven terms, each computed from the prediction's own fields and the node's counts.  
**Formula**: `potential = Σ weight * term`

| Term | Weight | What it measures |
|---|---|---|
| `cosine_idf_present` | +6.038 | Cosine between the STM and `present` as bags of symbols, each symbol weighted by `log2(patterns / patterns holding it) + 1` |
| `last_event_matched` | +2.755 | 1 if the newest STM event has a matched symbol, else 0 |
| `evidence_to_end` | +2.205 | `matches / symbols of past and present`: the share of the pattern, up to the end of `present`, that was observed |
| `recency_07` | +1.790 | Matched STM symbols, each counted `0.7^n` for an event `n` events back from the newest |
| `tversky` | +0.948 | `matches / (matches + 2 * missing + 2 * extras)` |
| `fragmentation` | -0.770 | The `fragmentation` field: matched blocks minus one |
| `log_frequency` | +0.680 | Natural logarithm of `frequency` |
| `snr` | +0.584 | The `snr` field |
| `inverse_fragmentation` | +0.387 | `1 / (fragmentation + 1)` |
| `recency_09` | +0.063 | As `recency_07`, with 0.9 |
| `last_event_share` | +0.022 | Matched share of the newest STM event's symbols |

The weights are constants, held in `kato/informatics/prediction_metrics.py` to full precision (`POTENTIAL_WEIGHTS`). They were fitted once, on sequences from four kinds of data (generated sequence libraries, system logs, click streams and text), to make the event that actually followed an STM as probable as possible under [`future_potentials`](#future_potentials). Nothing is fitted at prediction time, and no random seed is involved.

**Range**: Unbounded. An STM of two one-symbol events that exactly matches the first two events of a pattern learned once scores 16.10, and every doubling of the frequency adds 0.47. A match broken into many blocks among many extras can fall below zero.  
**Purpose**: Ranks the candidates so that the top prediction is the pattern most likely to continue the observation. It weighs how alike the observation and the matched part of the pattern are (rare symbols counting more), whether the newest event is explained, how recent the matched symbols are, how much is missing or extra, how broken up the match is, and how often the pattern was learned.  
**Properties**:
- It reads nothing from the other candidates, so a prediction's `potential` does not change with which other patterns matched, with their order, or with `max_predictions`.
- No term falls as the unobserved `future` of a pattern grows: a long pattern is not penalised for what it has yet to predict.
- Among candidates for the same STM, fewer extras, fewer missing symbols, fewer blocks or a higher frequency never lower the score.
- `e^potential` is what `future_potentials` sums, so a difference of 1.0 in `potential` is a factor of `e` in a prediction's weight on the next event.

**Configuration**: `potential` is the default `rank_sort_algo`. Every other numeric metric of the prediction object can be chosen instead; see [Metrics at a Glance](#metrics-at-a-glance).

### 26. **emotives** (map<string, float>)
**Description**: Emotional or utility values associated with this pattern.  
**Structure**: Dictionary mapping emotive names to float values.  
**Purpose**: Allows patterns to carry emotional salience or utility information for decision-making.  
**Example**: `{"utility": 50.0, "danger": -10.0}`

### 27. **anomalies** (array of strings)
**Description**: Flat list of every symbol that deviates from the pattern in this prediction.  
**Structure**: Missing symbols (expected in `present` but not observed) in pattern order, followed by extras (observed but not expected) in STM order, followed by the `observed` token of each entry in `fuzzy_matches`.  
**Purpose**: A single place to see everything that went wrong in the match, without walking the event-aligned `missing`/`extras` structures.  
**Example**: Pattern `hello world` (one character per event) observed as `o wxld`:
```json
"missing": [[], [], [], ["o"], ["r"], [], []],
"extras": [[], [], [], ["x"], [], []],
"anomalies": ["o", "r", "x"]
```
**Behavior**:
- Empty array `[]` when the observation matches the pattern exactly
- Repeated symbols are counted per occurrence, so a pattern symbol that appears twice but is observed once is reported missing once

### 27a. **fuzzy_matches** (array of objects)
**Description**: List of fuzzy token matches documenting non-exact matches when fuzzy token matching is enabled.  
**Structure**: Array of objects, each containing:
  - `observed` (string): The token that was actually observed
  - `expected` (string): The pattern token that was fuzzy-matched
  - `similarity` (float): Similarity score between observed and expected (0.0-1.0)

**Purpose**: Provides transparency about which tokens were fuzzy-matched versus exact-matched, enabling detection of data quality issues like typos and misspellings.  
**Example**:
```json
"fuzzy_matches": [
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
- Contains entries only for non-exact fuzzy matches (exact matches don't generate entries)
- Fuzzy-matched tokens appear in `matches` field, not in `missing` or `extras`; their `observed` token is also listed in `anomalies`
- Tokens below fuzzy threshold appear in `missing`/`extras` as normal mismatches

**Configuration**: Enable via `fuzzy_token_threshold` parameter (see [Session Configuration](session-configuration.md#fuzzy-token-matching))

### 28. **sequence** (repeated ListValue)
**Description**: The learned pattern in full: every event, in order.  
**Structure**: List of lists, where each inner list represents an event.  
**Purpose**: Shows the whole pattern the prediction comes from. `past`, `present` and `future` are this list cut in three; joined in that order they give `sequence` back.

### 29. **tfidf_score** (float)
**Description**: TF-IDF (Term Frequency - Inverse Document Frequency) score measuring pattern distinctiveness.  
**Formula**:
- For each symbol in pattern: `TF(symbol) = count(symbol in pattern) / pattern_length`
- `IDF(symbol) = log2(total_unique_patterns / patterns_containing_symbol) + 1`
- `TFIDF(symbol) = TF(symbol) × IDF(symbol)`
- `tfidf_score = mean(TFIDF for all unique symbols in pattern)`

**Range**: Typically 0.0 to ~2.0 (unbounded positive)  
**Purpose**: Identifies patterns containing distinctive/rare symbols. High scores indicate patterns with uncommon symbols that are frequent within the pattern itself. Useful for finding unique, informative patterns. Pattern-intrinsic: the same for every prediction of a given pattern, whatever was observed.  
**Interpretation**:
- High TF-IDF: Pattern contains rare symbols that appear frequently within it (distinctive)
- Low TF-IDF: Pattern contains mostly common symbols (generic)

### 30. **event_cohesion** (float)
**Description**: How much of each observed event co-occurs in a single pattern event, wherever that event is.  
**Formula**: for each non-empty STM event `s`, `max_j |s ∩ P[j]| / |s|` over the pattern events `P[j]`; `event_cohesion` is the mean over STM events. Events are compared as sets, so sorting within an event does not matter.  
**Range**: 0.0 to 1.0  
**Purpose**: Matching is flat, so observing `[["A","C"]]` against `[["A"],["C"]]` counts as a complete match even though the pattern never holds A and C together. Cohesion tells the two apart: 1.0 against `[["A","B","C"]]`, 0.5 against `[["A"],["C"]]`. Reported only; it is not part of `potential`.

### 31. **onset_alignment** (float)
**Description**: How early in the pattern the observed symbols occur, decaying with position.  
**Formula**: for the first non-empty STM event `s0`, `max_j (|s0 ∩ P[j]| / |s0|) / (1 + j)`. It reads pattern membership directly, so a symbol that occurs in the first event and again later scores as the first occurrence.  
**Range**: 0.0 to 1.0. A lone symbol scores 1.0 in the first event, 0.5 in the second, 1/3 in the third.  
**Purpose**: Reports where in the pattern the observation begins. When the STM is a single event (the first observation after the STM is cleared), that position is most of what separates the candidates. Reported only; it is not a term of `potential`, which accounts for position through `evidence_to_end`: the less of a pattern lies before the match, the higher it scores.

### 32. **weighted_similarity**, **weighted_evidence**, **weighted_confidence**, **weighted_snr** (float or null)
**Deprecated. Do not use.** Affinity-weighted matching (`affinity_emotive` and the metrics `weighted_similarity`, `weighted_evidence`, `weighted_confidence` and `weighted_snr`) is scheduled for removal. For an STM of two or more symbols only the observed symbols are weighted and the rest of the pattern counts as zero, so the values overstate the match: a pattern one third observed can score a `weighted_evidence` of 1.0. The metrics have not been measured on any data set. Leave `affinity_emotive` unset and do not use a weighted metric as `rank_sort_algo`.

**Description**: Four matching metrics with every symbol weighted by its affinity to one emotive.  
**Formula**: with `w(t) = |affinity(t, emotive)| / frequency(t) + epsilon` for a symbol `t`:
- `weighted_similarity = 2 * Σ w(matches) / (Σ w(STM) + Σ w(pattern))`
- `weighted_evidence = Σ w(matches) / Σ w(pattern)`
- `weighted_confidence = Σ w(matches) / Σ w(present)`
- `weighted_snr = Σ w(matches) / (Σ w(matches) + Σ w(extras))`

**Range**: 0.0 to 1.0. `null` unless the session sets `affinity_emotive`.  
**Purpose**: Scores a match by the symbols that matter to an emotive such as utility or risk: a symbol the node has learned alongside strong values of the emotive counts for more than one it has not. `potential` does not read them. To rank by one, set it as `rank_sort_algo`.

## Ensemble Fields

Three figures describe a request's whole set of candidates. They come back beside the `predictions` list, not inside a prediction.

### future_potentials

**Description**: The probability of each next event the candidates propose, most probable first.  
**Structure**: A list of entries:

| Key | Meaning |
|---|---|
| `next_event` | The event, as the patterns store it: a list of symbols. |
| `probability` | The probability that this event comes next, given the STM. The entries and `ends_here` add up to 1.0. |
| `supporting_patterns` | How many candidates have this event as their next event. |

**Formula**: `P(E | STM) = Σ e^potential over the candidates whose next event is E / Σ e^potential over every candidate`  
The next event of a candidate is the first event of its `future`. A candidate with an empty `future` ends where the observation ends. It proposes no event, and its weight goes to [`ends_here`](#ends_here).  
**Order**: By `probability`, highest first. Equal probabilities go to the event that sorts first.  
**Purpose**: The answer to "what comes next". Patterns that agree on the next event pool their support, even when they differ later, so on most data the top entry is right more often than the top prediction's own `future`. The probability is also a usable confidence value: see [Measured Accuracy](#measured-accuracy).  
**Scope**: Computed over every candidate above the recall threshold, including those `max_predictions` leaves out of the response. Empty when the STM is empty, when nothing matches, or when no candidate has a future.  
**What the probability is a share of**: the weight of the candidates. It does not say how well those candidates explain the STM. A lone candidate with a future gets a probability of 1.0, however weak its match. Whether to believe the candidates at all is what `chance_posterior` says.

**Why `e^potential`**: `potential` was fitted as the logarithm of a candidate's weight in exactly this sum, so its shares are probabilities the fit was trained to produce. The other metrics were tried in its place: `future_potentials` and `ends_here` were rebuilt from every candidate of the ranking benchmark's guide-suite queries (`recall_threshold` 0.1, mean of 8 kinds of data) with each candidate weighted by `e^metric`, by `2^good_odds`, by `frequency`, or equally. None names the next event as often, and none states its probability as faithfully:

| Weight of each candidate | Top entry right | Difference (95% interval) | Probability stated | Right when answered | `ends_here` AUROC |
|---|---:|---:|---:|---:|---:|
| `e^potential` | 0.580 | | 0.731 | 0.730 | 0.901 |
| `2^good_odds` (the shares of `bayesian_posterior`) | 0.562 | −1.8 (−3.1 to −0.5) | 0.813 | 0.713 | 0.885 |
| `e^bayesian_likelihood` | 0.548 | −3.2 (−4.5 to −1.9) | 0.799 | 0.691 | 0.877 |
| `e^predictive_information` | 0.437 | −14.3 (−16.3 to −12.4) | 0.371 | 0.557 | 0.810 |
| `frequency` | 0.398 | −18.2 (−20.3 to −16.0) | 0.260 | 0.293 | 0.815 |
| Every candidate equal | 0.379 | −20.1 (−22.2 to −17.9) | 0.207 | 0.284 | 0.785 |
| `e^frequency` | 0.287 | −29.3 (−31.6 to −27.0) | 0.688 | 0.214 | 0.706 |

A metric between 0 and 1 changes little under `e^x`, so it comes out close to every candidate counting equally (0.375 to 0.393). `2^good_odds` comes closest and overstates its certainty. It is ahead on one kind of data, the loan-application log (0.835 against 0.785). The weight does not follow `rank_sort_algo`, so the ranking key orders the list and changes no value in the response. All 23 weightings, the method and how to run it are in [`benchmarks/ranking/README.md`](../../benchmarks/ranking/README.md#the-weight-of-future_potentials).

### ends_here

**Description**: The probability that no event follows the observation.  
**Formula**: `ends_here = Σ e^potential over the candidates with an empty future / Σ e^potential over every candidate`  
**Range**: 0.0 to 1.0. With the probabilities in `future_potentials` it adds up to 1.0. `null` when there is no candidate: an empty STM, or an STM that matches nothing.  
**Purpose**: Keeps a pattern that has ended in the vote. A candidate whose pattern ends where the STM ends is often the best match there is, and it has no next event to propose. Its weight says that the learned sequence is complete. Without it the probability would be shared among the candidates that go on, and a poor match could be given 1.0 for an event that the pattern which fits has never led to.  
**Use**: Compare it with the top entry of `future_potentials`. When `ends_here` is the larger, the most probable reading is that nothing follows. An application that must name a next event anyway can still take the top entry, knowing how little weight it carries.  
**What it is not**: a statement about the session. KATO learned where its patterns end, not when a user stops. `ends_here` is high when the patterns that fit the observation have nothing left, and that is all it reports.

### chance_posterior

**Description**: The probability that no learned pattern explains the observation better than chance.  
**Formula**: `chance_posterior = 1 / (1 + Σ 2^good_odds)`, the sum taken over every candidate above the recall threshold.  
**Range**: 0.0 to 1.0. With the `bayesian_posterior` of every candidate it adds up to 1.0.  
**Purpose**: KATO's "I don't know", graded. An STM that matches nothing returns no predictions, and its `chance_posterior` is 1.0. An STM that matches weakly returns predictions, and a `chance_posterior` near 1.0 says none of them should be trusted. `null` when no prediction was computed, which is the case for an empty STM.

## How the Scores Are Computed

1. **Candidates.** Every pattern whose `similarity` to the STM reaches `recall_threshold`. For a one-symbol STM: every pattern that holds the symbol.
2. **Ensemble scores, for every candidate.** The frequency of each candidate is read. Then `bayesian_prior`, `bayesian_likelihood`, `good_odds`, `potential`, `bayesian_posterior` and `predictive_information` are computed for all of them, along with `future_potentials`, `ends_here` and `chance_posterior`.
3. **Ranking and the cut.** The candidates are ranked by the session's `rank_sort_algo`, highest value first, and the best `max_predictions` are kept. Equal values are ordered by pattern name, so the same request always returns the same predictions in the same order.
4. **Pattern metrics, for what is returned.** `entropy`, `normalized_entropy`, `global_normalized_entropy`, `tfidf_score`, `itfdf_similarity`, `confluence` and the averaged `emotives` are computed for the returned predictions. When the session ranks by one of these six metrics, they are computed for every candidate first, and step 3 follows.

Nothing is cut before it is scored. A returned value therefore does not depend on `max_predictions`, on the order the candidates were found in, or on the ranking key.

Sums over the candidates run in pattern-name order and sums over symbols in a fixed order, with plain floating-point addition. The same candidates give the same bits on every request and on every worker.

## Worked Example

A node has learned three patterns, one symbol per event:

| Pattern | Times learned |
|---|---|
| `login`, `browse`, `checkout` | 5 |
| `login`, `browse`, `logout` | 3 |
| `login`, `reset_password`, `logout` | 2 |

Its counts: 10 learns in all (`F` = 10) and 30 learned symbol occurrences, of which `login` has 10, `browse` 8, `checkout` 5, `logout` 5 and `reset_password` 2.

A session observes `login`, then `browse`. All three patterns reach the default `recall_threshold` of 0.1:

| | `login, browse, checkout` | `login, browse, logout` | `login, reset_password, logout` |
|---|---|---|---|
| `matches` | `login`, `browse` | `login`, `browse` | `login` |
| `extras` | none | none | `browse` |
| next event | `checkout` | `logout` | `reset_password` |
| `similarity` | 0.8 | 0.8 | 0.4 |
| `bayesian_prior` | 0.5 | 0.3 | 0.2 |
| `bayesian_likelihood` | 3.34 bits | 3.34 bits | -2.81 bits |
| `good_odds` | 2.34 bits | 1.61 bits | -5.13 bits |
| `bayesian_posterior` | 0.555 | 0.333 | 0.003 |
| `potential` | 17.20 | 16.85 | 8.11 |
| `predictive_information` | 1.063 bits | 0.544 bits | -0.001 bits |
| `confluence` | 5.08 bits | 4.34 bits | 5.75 bits |

```json
"future_potentials": [
  {"next_event": ["checkout"], "probability": 0.5859, "supporting_patterns": 1},
  {"next_event": ["logout"], "probability": 0.414, "supporting_patterns": 1},
  {"next_event": ["reset_password"], "probability": 0.0001, "supporting_patterns": 1}
],
"ends_here": 0.0,
"chance_posterior": 0.1093
```

**`good_odds`, term by term.** For the first prediction:

1. The pattern holds 5 of the node's 10 learns: `log2(5 / 10)` = -1.00 bit.
2. `login` matched. It is 10 of the 30 symbol occurrences: `log2(0.95 * 30 / 10)` = +1.51 bits.
3. `browse` matched. It is 8 of 30: `log2(0.95 * 30 / 8)` = +1.83 bits.
4. Nothing is missing and nothing is extra, so there is no penalty.

The total is 2.34 bits: odds of about 5 to 1 that this pattern, and not chance, produced the observation. The third prediction starts at `log2(2 / 10)` = -2.32, gains 1.51 for `login` and pays 4.32 for `browse`, which it cannot account for: -5.13 bits, about 35 to 1 against.

**From odds to probabilities.** The three odds are 5.08, 3.05 and 0.03, and chance counts as 1. Each posterior is the pattern's odds over the total of 9.15: 0.555, 0.333 and 0.003. Chance keeps the rest: `chance_posterior` = 1 / 9.15 = 0.109.

**`potential`, term by term.** For the first and the third prediction:

| Term | Weight | `login, browse, checkout`: value | contributes | `login, reset_password, logout`: value | contributes |
|---|---|---|---|---|---|
| `cosine_idf_present` | +6.038 | 1.000 | 6.038 | 0.534 | 3.222 |
| `last_event_matched` | +2.755 | 1 | 2.755 | 0 | 0.000 |
| `evidence_to_end` | +2.205 | 1.000 | 2.205 | 1.000 | 2.205 |
| `recency_07` | +1.790 | 1.700 | 3.043 | 0.700 | 1.253 |
| `tversky` | +0.948 | 1.000 | 0.948 | 0.333 | 0.316 |
| `fragmentation` | -0.770 | 0 | 0.000 | 0 | 0.000 |
| `log_frequency` | +0.680 | 1.609 | 1.094 | 0.693 | 0.471 |
| `snr` | +0.584 | 1.000 | 0.584 | 0.333 | 0.195 |
| `inverse_fragmentation` | +0.387 | 1.000 | 0.387 | 1.000 | 0.387 |
| `recency_09` | +0.063 | 1.900 | 0.120 | 0.900 | 0.057 |
| `last_event_share` | +0.022 | 1.000 | 0.022 | 0.000 | 0.000 |
| **`potential`** | | | **17.197** | | **8.106** |

The second prediction differs from the first in one term: `log_frequency` is `ln(3)` in place of `ln(5)`, which is 0.347 less.

**What comes next.** Each candidate votes for its next event with weight `e^potential`. Relative to the best, the weights are 1, `e^-0.347` = 0.707 and `e^-9.091` = 0.0001. Normalised, they are the probabilities in `future_potentials`: `checkout` 0.586, `logout` 0.414, `reset_password` 0.0001. Every candidate has a future, so `ends_here` is 0.0.

**When a pattern has ended.** The session then observes `checkout`. The first pattern now matches in full and has no event left. The second matches `login` and `browse` and still proposes `logout`; the third matches `login` and proposes `reset_password`.

| | `login, browse, checkout` | `login, browse, logout` | `login, reset_password, logout` |
|---|---|---|---|
| next event | none | `logout` | `reset_password` |
| `similarity` | 1.0 | 0.667 | 0.333 |
| `good_odds` | 4.85 bits | -2.72 bits | -9.45 bits |
| `potential` | 18.13 | 9.95 | 6.07 |

```json
"future_potentials": [
  {"next_event": ["logout"], "probability": 0.0003, "supporting_patterns": 1},
  {"next_event": ["reset_password"], "probability": 0.000006, "supporting_patterns": 1}
],
"ends_here": 0.9997,
"chance_posterior": 0.0332
```

The weights relative to the best are 1, `e^-8.18` = 0.0003 and `e^-12.05` = 0.000006. The pattern that has ended holds 0.9997 of the total, which is `ends_here`. `logout` is the most probable next event and it is still improbable: the only pattern that proposes it explains the observation worse than chance.

## Metrics at a Glance

`f` is the pattern's `frequency`, `F` the node's `total_pattern_frequencies`, `q(s)` a symbol's share of all learned symbol occurrences, and `G` is `good_odds`.

| Metric | Answers | Formula | Unit and range | Reads | Use it for | Suits |
|---|---|---|---|---|---|---|
| `potential` | Which candidate is most likely to continue the observation? | `Σ weight × term`, eleven terms ([field 25](#25-potential-float)) | Score; unbounded | Prediction, node | Default ranking; the weights behind `future_potentials` | Every kind of data measured. Its lead over `good_odds` is largest when the STM runs across two patterns, when the STM is a small part of a pattern, and on text |
| `good_odds` | By how many bits does the pattern explain the observation better than chance, counting how often it was learned? | `log2(f / F) + Σ log2(0.95 / q(s)) - 4.32 × (missing + extras)` | Bits; unbounded; above 0 beats chance | Prediction, node | Ranking where every term has to be derivable; comparing matches across requests; a floor against chance | Logs, click streams and sequence libraries, where it is within 2 points of `potential`. Behind on text (0.097 against 0.127) and when the STM runs across two patterns |
| `bayesian_posterior` | How probable is it that this pattern, and not another candidate or chance, produced the observation? | `2^G / (1 + Σ 2^G)` over every candidate | Probability; 0 to 1 | Candidates | Naming the pattern; a threshold on a probability. Ranks as `good_odds` does | As `good_odds`. It overstates its certainty where symbols occur together by habit, most of all on text |
| `bayesian_likelihood` | How strongly does the observation alone support the pattern over chance? | `Σ log2(0.95 / q(s)) - 4.32 × (missing + extras)` | Bits; unbounded | Prediction, node | Match strength with frequency left out | Nodes whose patterns were learned about equally often: there it matches `good_odds`. Where frequencies differ it is behind (0.496 against 0.671 on click streams) |
| `bayesian_prior` | How common is the pattern in the node? | `f / F` | Probability; above 0, up to 1 | Node | Base rates. Ranks as `frequency` does | As `frequency` |
| `frequency` | How many times was the pattern learned? | Stored count | Count; 1 or more | Pattern | The most often learned candidates first | Nodes where a few patterns account for most of what was learned: 0.785 on the logs. 0.146 on sequence libraries and 0.034 on text |
| `predictive_information` | What part of the STM's information about the next event does this prediction carry? | `share × log2(P(E) / q(E))`, `P(E)` from `future_potentials` | Bits; unbounded; 0 without a future | Candidates, node | Measuring how informative a context is, and which patterns carry it | As a ranking key, within 2 points of `potential` on logs, click streams and sequence libraries, and behind on text (0.089 against 0.127) |
| `confluence` | How far is the pattern from a chance co-occurrence of its symbols? | `log2(f / F) + Σ log2(1 / q(s))` over the pattern | Bits; unbounded | Pattern, node | Describing learned patterns; the ceiling of `good_odds` | Not a ranking key: it does not read the observation |
| `similarity` | How large is the common subsequence, against the pattern and the STM taken together? | `2 × LCS / (len(pattern) + len(STM))` | 0 to 1 | Prediction | The recall gate; ranking whole-sequence matches | Observations that cover most of a pattern: level with `potential` when 75% or more is observed (0.941), far behind when 25% or less is (0.316) |
| `evidence` | How much of the whole pattern was observed? | `matches / pattern length` | 0 to 1 | Prediction | Progress through a pattern | Observations that cover nearly all of a pattern. 0.509 at 75% to 90% observed, 0.071 at 50% |
| `confidence` | How much of the matched events was observed? | `matches / symbols in present` | 0 to 1 | Prediction | Spotting partly observed events | A diagnostic. As a ranking key it is weak everywhere but the logs (0.544) |
| `snr` | How much of the observation does the pattern account for? | `(2 × matches - extras) / (2 × matches + extras)` | -1 to 1 | Prediction | Spotting noisy observations | Long STMs: 0.929 with 10 or 20 events, level with `potential`. 0.316 with 2 or 3 |
| `fragmentation` | Into how many blocks is the match broken? | `blocks - 1` | Count; 0 or more (-1 when no block matched exactly) | Prediction | Diagnosing scattered matches. Lower is better | A diagnostic. Ranked highest first, it puts the most broken matches on top |
| `event_cohesion` | Do the symbols of each observed event sit together in one pattern event? | Mean over STM events of the largest share of the event found in one pattern event | 0 to 1 | Prediction | Telling co-occurrence from sequence | Long STMs and events of several symbols: 0.849 and 0.758. Weak on short STMs |
| `onset_alignment` | How early in the pattern does the observation begin? | Share of the first STM event found in pattern event `j`, over `1 + j`, at its largest | 0 to 1 | Prediction | The position of a match | A diagnostic. Weak as a ranking key outside the logs |
| `entropy` | How varied are the pattern's own symbols? | `-Σ p(s) × log2 p(s)` | Bits; 0 or more | Pattern | Describing patterns | Not a ranking key: it does not read the observation |
| `normalized_entropy` | The same, on a scale set by the node's vocabulary | `entropy / log2(distinct symbols in the node)` | 0 to 1 | Pattern, node | Comparing patterns across nodes | Not a ranking key |
| `global_normalized_entropy` | How evenly are the pattern's symbols spread over the node's patterns? | `-Σ g(s) × log_V g(s)`, `g(s)` the share of patterns holding `s`, `V` the distinct symbols in the node | 0 or more | Pattern, node | Describing patterns | Not a ranking key |
| `tfidf_score` | Does the pattern hold symbols that few other patterns hold? | Mean over the pattern's distinct symbols of `TF(s) × IDF(s)` | 0 or more; typically under 2 | Pattern, node | Finding distinctive patterns | Not a ranking key: it does not read the observation |
| `itfdf_similarity` | How close are the STM and `present` on the symbols patterns share? | `1 - (1 - cosine) × f / candidate frequency` | 0 to 1 | Prediction, node, candidates | A symbol-overlap check | Clean observations: 0.844 without noise, 0.356 at 20% noise. 0.775 on the logs |
| `weighted_similarity`, `weighted_evidence`, `weighted_confidence`, `weighted_snr` | The matching metrics, with each symbol counted by its affinity to an emotive | [Field 32](#32-weighted_similarity-weighted_evidence-weighted_confidence-weighted_snr-float-or-null) | 0 to 1; `null` without `affinity_emotive` | Prediction, node | Nothing: deprecated, do not use | Not measured. Overstates the match for an STM of two or more symbols |

The three ensemble fields, in the same terms:

| Field | Answers | Formula | Unit and range | Reads | Use it for | Suits |
|---|---|---|---|---|---|---|
| `future_potentials` | What comes next, and how probable is it? | `e^potential` summed by next event, over the sum for every candidate | Probability; with `ends_here` the entries add up to 1 | Candidates | The next-event answer and its confidence | Every kind of data measured. On the mean of the four kinds its top entry is right more often than the top prediction of any ranking key; the gain is largest on text (0.193 against 0.127), and on logs it is 1 point behind |
| `ends_here` | Has the sequence come to its end? | `e^potential` of the candidates with no future, over the sum for every candidate | Probability; 0 to 1 | Candidates | Not naming a next event when the patterns that fit have none left | Data in which sequences have learned endings. Not measured on sequences that end. Where an event did follow, it averaged 0.05 and was above 0.5 for 0.6% of the queries |
| `chance_posterior` | Does anything learned explain the observation? | `1 / (1 + Σ 2^G)` over every candidate | Probability; 0 to 1 | Candidates | Declining to answer | Telling a learned situation from an unfamiliar one. Above 0.5 for 4% of the queries on sequence libraries and 50% on text |

**Reads** says what a value depends on. *Prediction*: the pattern, the STM and the match between them. *Node*: counts kept for the whole node (symbol occurrences, how many patterns hold a symbol, pattern totals). *Candidates*: every pattern above the recall threshold for this request.

Every metric in the table is accepted by `rank_sort_algo`. Predictions are always ranked highest value first, so a metric where lower is better (`fragmentation`) puts the weakest matches first when it is chosen as the key.

## Measured Accuracy

How often each metric, used as the ranking key, puts a prediction with the right next event on top, and how well `future_potentials` and `chance_posterior` state their own certainty.

### How It Was Measured

1. **The task.** Next-event prediction. A query is the opening of a sequence the node has not learned, taken as the STM, together with the event that followed it. An answer is right when the predicted next event is exactly that event.
2. **The data.** 57 data sets of four kinds:
   - **Generated sequence libraries** (39 data sets). Patterns of 2 to 100 events are chained from a pool of short motifs over a vocabulary with a Zipf distribution, and learned with Zipf-distributed frequencies. A query passes its STM through a noise channel that drops, inserts and replaces symbols. The base setting has 1,000 symbols, 20,000 patterns, 5% noise and an STM of 5 events; the other data sets change one thing at a time: vocabulary, number of patterns, skew of the frequencies, noise, length of the STM, share of the pattern observed, several symbols per event, and pattern boundaries the node is not told.
   - **System logs** (6): the block traces of the HDFS_v1 log data set, from [Loghub](https://github.com/logpai/loghub) ([doi:10.5281/zenodo.8196385](https://doi.org/10.5281/zenodo.8196385)). The traces repeat heavily: ten of the 16,074 patterns account for 55% of what the node learned.
   - **Click streams** (2): the page-category sequences of the [msnbc.com anonymous web data](https://archive.ics.uci.edu/dataset/133/msnbc+com+anonymous+web+data). The sequences are short, half of them 9 symbols or fewer.
   - **Text** (10): WikiText-2 ([arXiv:1609.07843](https://arxiv.org/abs/1609.07843)), learned as whole sentences and as fixed windows of words. Nearly every pattern was learned once.

   The nodes hold between 908 and 520,955 patterns.
3. **The queries.** 58,600 held-out queries: 47,800 on generated data, 4,800 on logs, 2,000 on click streams and 4,000 on text. None was used to fit the weights of `potential`, which were fitted on separate queries from the same data sets. They were used to choose `potential`'s form among candidate formulas, so its figures on them are slightly favourable; its figures on a further set of test queries, read once after the formulas were fixed, are under [On the Test Queries](#on-the-test-queries).
4. **The settings.** `recall_threshold` 0.1, token-level matching, fuzzy matching off, every candidate above the threshold scored. Depending on the data set, a request has from a few hundred to 127,000 candidates on average.
5. **The averages.** The figure for a kind of data is the mean over its data sets. "Mean" is the mean of the four kinds, so each kind counts the same.

### As a Ranking Key

Every candidate is ranked by the metric, highest value first, as `rank_sort_algo` does. The answer is the next event of the top-ranked prediction that has a `future`. The table gives the share of queries answered right. Some candidate has a future in every query, so this share is at once the accuracy and the precision of the read-out.

| Ranking key | Mean | Generated | Logs | Click streams | Text |
|---|---|---|---|---|---|
| *Top entry of `future_potentials`* | *0.648* | *0.851* | *0.860* | *0.689* | *0.193* |
| `potential` | 0.633 | 0.849 | 0.871 | 0.683 | 0.127 |
| `good_odds`, `bayesian_posterior` | 0.618 | 0.834 | 0.870 | 0.671 | 0.097 |
| `predictive_information` | 0.616 | 0.839 | 0.857 | 0.679 | 0.088 |
| `bayesian_likelihood` | 0.532 | 0.777 | 0.768 | 0.496 | 0.086 |
| `snr` | 0.473 | 0.662 | 0.703 | 0.455 | 0.073 |
| `itfdf_similarity` | 0.437 | 0.527 | 0.775 | 0.384 | 0.064 |
| `event_cohesion` | 0.405 | 0.593 | 0.633 | 0.317 | 0.076 |
| `frequency`, `bayesian_prior` | 0.364 | 0.146 | 0.785 | 0.492 | 0.034 |
| `similarity` | 0.325 | 0.531 | 0.466 | 0.252 | 0.049 |
| `global_normalized_entropy` | 0.235 | 0.175 | 0.595 | 0.117 | 0.055 |
| `evidence` | 0.233 | 0.280 | 0.387 | 0.237 | 0.026 |
| `confidence` | 0.217 | 0.047 | 0.544 | 0.262 | 0.014 |
| `confluence` | 0.214 | 0.179 | 0.281 | 0.364 | 0.031 |
| `onset_alignment` | 0.205 | 0.098 | 0.548 | 0.155 | 0.017 |
| `fragmentation` | 0.173 | 0.069 | 0.502 | 0.072 | 0.047 |
| `entropy` | 0.163 | 0.155 | 0.351 | 0.112 | 0.035 |
| `normalized_entropy` | 0.163 | 0.155 | 0.351 | 0.112 | 0.034 |
| `tfidf_score` | 0.117 | 0.016 | 0.101 | 0.349 | 0.003 |

1. **`potential` leads on the mean and is first or level on every kind of data.** `good_odds` follows 1.4 points behind, level on logs and behind on text.
2. **`future_potentials` is the better read-out on three kinds of data.** Its top entry beats the top prediction of every ranking key on the mean, and by 6.6 points on text, because it pools the patterns that agree. On logs the top prediction by `potential` is 1.1 points ahead of it.
3. **Frequency matters, and it is not enough.** `bayesian_likelihood` is `good_odds` without the prior, and loses 8.6 points. `frequency` alone is right 79% of the time on logs, where a few patterns hold most of the learns, and 15% on generated data.
4. **Metrics that describe the pattern do not rank predictions.** `confluence`, the entropy fields and `tfidf_score` do not read the observation. `fragmentation` is ranked highest first, which puts the most broken matches on top.
5. **Text is hard for every key.** The best-ranked stored pattern names the next word of unseen text about one time in eight. Counting what followed the longest stretch of the STM's ending that occurs in the stored patterns, with no matching at all, is right 17.8% of the time on the test queries, close to the top entry of `future_potentials`.

### The Top Prediction Itself

The top-ranked prediction can be a pattern that ends where the STM ends. Its `future` is empty and it names no next event. Each cell gives accuracy / precision / answered: the share of all queries the top prediction gets right, the share it gets right of those where it names a next event, and the share where it names one.

| Ranking key | Mean | Generated | Logs | Click streams | Text |
|---|---|---|---|---|---|
| `potential` | 0.486 / 0.626 / 0.782 | 0.831 / 0.855 / 0.966 | 0.871 / 0.872 / 0.999 | 0.115 / 0.649 / 0.185 | 0.124 / 0.129 / 0.976 |
| `good_odds`, `bayesian_posterior` | 0.478 / 0.612 / 0.776 | 0.810 / 0.845 / 0.945 | 0.870 / 0.870 / 0.999 | 0.143 / 0.630 / 0.247 | 0.089 / 0.102 / 0.913 |
| `predictive_information` | 0.616 / 0.616 / 1.000 | 0.839 / 0.839 / 1.000 | 0.857 / 0.857 / 1.000 | 0.679 / 0.679 / 1.000 | 0.088 / 0.088 / 1.000 |
| `bayesian_likelihood` | 0.509 / 0.531 / 0.937 | 0.754 / 0.783 / 0.948 | 0.768 / 0.768 / 1.000 | 0.431 / 0.487 / 0.887 | 0.080 / 0.087 / 0.913 |
| `snr` | 0.445 / 0.468 / 0.923 | 0.638 / 0.665 / 0.942 | 0.701 / 0.703 / 0.998 | 0.375 / 0.430 / 0.877 | 0.067 / 0.076 / 0.877 |
| `itfdf_similarity` | 0.421 / 0.443 / 0.922 | 0.512 / 0.540 / 0.921 | 0.775 / 0.775 / 1.000 | 0.339 / 0.391 / 0.867 | 0.059 / 0.066 / 0.900 |
| `event_cohesion` | 0.392 / 0.408 / 0.936 | 0.574 / 0.597 / 0.948 | 0.633 / 0.633 / 1.000 | 0.289 / 0.323 / 0.886 | 0.071 / 0.079 / 0.907 |
| `frequency`, `bayesian_prior` | 0.266 / 0.320 / 0.791 | 0.138 / 0.154 / 0.896 | 0.785 / 0.785 / 0.999 | 0.111 / 0.305 / 0.339 | 0.032 / 0.037 / 0.929 |
| `similarity` | 0.191 / 0.429 / 0.511 | 0.367 / 0.621 / 0.519 | 0.346 / 0.563 / 0.673 | 0.010 / 0.481 / 0.026 | 0.042 / 0.052 / 0.827 |
| `global_normalized_entropy` | 0.231 / 0.236 / 0.960 | 0.172 / 0.176 / 0.965 | 0.586 / 0.590 / 0.992 | 0.111 / 0.121 / 0.916 | 0.054 / 0.055 / 0.967 |
| `evidence` | 0.063 / 0.378 / 0.254 | 0.041 / 0.399 / 0.093 | 0.193 / 0.486 / 0.337 | 0.002 / 0.600 / 0.003 | 0.015 / 0.027 / 0.585 |
| `confidence` | 0.209 / 0.218 / 0.922 | 0.037 / 0.045 / 0.858 | 0.543 / 0.554 / 0.981 | 0.242 / 0.260 / 0.922 | 0.013 / 0.014 / 0.926 |
| `confluence` | 0.210 / 0.213 / 0.976 | 0.174 / 0.179 / 0.953 | 0.281 / 0.281 / 1.000 | 0.355 / 0.361 / 0.983 | 0.030 / 0.030 / 0.967 |
| `onset_alignment` | 0.197 / 0.205 / 0.955 | 0.091 / 0.103 / 0.895 | 0.525 / 0.541 / 0.966 | 0.154 / 0.157 / 0.984 | 0.016 / 0.017 / 0.975 |
| `fragmentation` | 0.163 / 0.171 / 0.890 | 0.061 / 0.070 / 0.893 | 0.495 / 0.497 / 0.992 | 0.058 / 0.070 / 0.832 | 0.041 / 0.048 / 0.842 |
| `entropy` | 0.160 / 0.163 / 0.975 | 0.152 / 0.156 / 0.960 | 0.343 / 0.346 / 0.992 | 0.111 / 0.117 / 0.962 | 0.034 / 0.034 / 0.987 |
| `normalized_entropy` | 0.160 / 0.163 / 0.975 | 0.152 / 0.156 / 0.960 | 0.343 / 0.346 / 0.992 | 0.111 / 0.117 / 0.962 | 0.034 / 0.034 / 0.987 |
| `tfidf_score` | 0.099 / 0.110 / 0.680 | 0.006 / 0.014 / 0.351 | 0.097 / 0.101 / 0.975 | 0.290 / 0.321 / 0.905 | 0.003 / 0.004 / 0.491 |

On click streams the top prediction by `potential` names a next event for 18% of the queries: the sequences are short, and the pattern that matches best is usually one the STM completes. Its precision there is 0.649, and reading the top prediction that has a future instead lifts the accuracy from 0.115 to 0.683. `predictive_information` is 0 for a prediction without a future, so its top prediction always names an event.

### By Situation

The generated data sets isolate one condition each. Share of queries answered right by the top prediction that has a future:

| Situation | `potential` | `good_odds` | `bayesian_likelihood` | `frequency` | `similarity` | `evidence` | `snr` | `event_cohesion` | `itfdf_similarity` |
|---|---|---|---|---|---|---|---|---|---|
| The STM is the first 75% to 90% of a pattern | 0.945 | 0.938 | 0.932 | 0.055 | 0.941 | 0.509 | 0.914 | 0.868 | 0.467 |
| The STM is the first 50% of a pattern | 0.927 | 0.926 | 0.874 | 0.065 | 0.833 | 0.071 | 0.807 | 0.737 | 0.511 |
| The STM is the first 10% to 25% of a pattern | 0.912 | 0.883 | 0.850 | 0.069 | 0.316 | 0.204 | 0.729 | 0.631 | 0.653 |
| STM of 2 or 3 events, from the middle of a pattern | 0.600 | 0.596 | 0.482 | 0.155 | 0.310 | 0.162 | 0.316 | 0.289 | 0.453 |
| STM of 10 or 20 events, from the middle of a pattern | 0.935 | 0.935 | 0.936 | 0.217 | 0.475 | 0.120 | 0.929 | 0.849 | 0.574 |
| No noise | 0.926 | 0.923 | 0.851 | 0.238 | 0.441 | 0.263 | 0.642 | 0.472 | 0.844 |
| 20% noise | 0.673 | 0.694 | 0.620 | 0.202 | 0.307 | 0.157 | 0.407 | 0.335 | 0.356 |
| Events of 1 to 5 symbols | 0.887 | 0.874 | 0.814 | 0.141 | 0.540 | 0.269 | 0.735 | 0.758 | 0.372 |
| Patterns drawn equally often | 0.794 | 0.795 | 0.788 | 0.030 | 0.423 | 0.237 | 0.543 | 0.417 | 0.705 |
| Strongly skewed pattern frequencies | 0.900 | 0.893 | 0.815 | 0.439 | 0.351 | 0.160 | 0.647 | 0.486 | 0.706 |
| A vocabulary of 50 symbols | 0.789 | 0.813 | 0.667 | 0.205 | 0.305 | 0.200 | 0.164 | 0.108 | 0.564 |
| The STM runs across two patterns | 0.613 | 0.437 | 0.392 | 0.111 | 0.208 | 0.113 | 0.272 | 0.210 | 0.175 |
| Pattern boundaries not given to the node | 0.725 | 0.675 | 0.612 | 0.148 | 0.516 | 0.481 | 0.551 | 0.497 | 0.486 |

1. **`similarity` works when the STM covers most of a pattern, and only then.** It is level with `potential` at 75% to 90% observed (0.941 against 0.945) and falls to 0.316 at 10% to 25%: it divides by the length of the whole pattern, so the right pattern scores low when most of it is still ahead.
2. **`snr` and `event_cohesion` work on long STMs.** With 10 or 20 events they reach 0.929 and 0.849; with 2 or 3 events, 0.316 and 0.289. Both depend only on how much of the STM a pattern accounts for. With two or three symbols many patterns account for all of it and tie; with ten or twenty, few do.
3. **`bayesian_likelihood` matches `good_odds` where the prior says little.** With patterns drawn equally often they score 0.788 and 0.795; with strongly skewed frequencies, 0.815 and 0.893.
4. **An STM that runs across two patterns is where `potential` gains most over `good_odds`:** 0.613 against 0.437. The older events of such an STM belong to the previous pattern and are extras for the right one. `good_odds` charges 4.32 bits for each of them; `potential` weighs the newest events most.
5. **Short STMs are hard for every key.** Two or three events leave many patterns equally well matched: 0.600 for `potential`.

### How Sure: `future_potentials`

The `probability` of the top entry, against how often that entry is right:

| | Generated | Logs | Click streams | Text |
|---|---|---|---|---|
| Probability stated, on average | 0.789 | 0.834 | 0.553 | 0.194 |
| Share of the answers that were right | 0.851 | 0.860 | 0.689 | 0.193 |
| Answers with a probability of 0.9 or more | 61% | 55% | none | 1% |
| Right among those | 98% | 98% | | 91% |
| Answers with a probability of 0.5 or more | 80% | 92% | 61% | 7% |
| Right among those | 96% | 90% | 81% | 63% |
| Right among the most confident quarter of the answers | 98% | 97% | 90% | 39% |

1. **The probability tracks the outcome, on the cautious side.** Over all four kinds the top entry states 0.593 on average and is right 0.648 of the time; the mean gap between stated and observed, over ten probability bins, is 0.056. It is cautious on three kinds and level on text. Part of the caution comes from the queries: an event followed every one of them, and the share that went to `ends_here` (0.046 on average) was held back from events that did follow.
2. **A high probability can be acted on.** At 0.9 or more the top entry is right at least 91% of the time. How often it gets there depends on the data: for 61% of the answers on generated data, 1% on text (39 answers, so that figure rests on few cases) and none on click streams, where patterns that have ended hold a tenth of the weight on average.
3. **It separates right answers from wrong ones.** As a score for whether the top entry is right, `probability` has an area under the ROC curve of 0.80.

### How Sure: `ends_here`

Every query of the study is the opening of a sequence that went on, so an event followed each one. The figures below therefore say one thing only: how much probability went to "nothing follows" when something did. How well `ends_here` recognises a sequence that has ended was not measured.

| | Generated | Logs | Click streams | Text |
|---|---|---|---|---|
| `ends_here`, on average | 0.038 | 0.005 | 0.102 | 0.039 |
| Queries with `ends_here` below 0.01 | 59% | 91% | 1% | 57% |
| Queries with `ends_here` above 0.5 | 1.7% | none | none | 0.6% |
| Queries where the top entry is more probable than `ends_here` | 97% | 100% | 100% | 90% |

1. **It rarely speaks out of turn.** When an event did follow, `ends_here` was above 0.5 for 0.6% of the queries (mean of the four kinds).
2. **Where it is high, the answer is weak anyway.** On generated data the top entry is right for 47% of the queries with `ends_here` above 0.5, against 85% of the others.
3. **Text is where it competes with the answer.** For one query in ten there, "nothing follows" outweighs every next event. The top entry is right for 19% of the text queries, so its probability is often small.

### How Sure: `chance_posterior`

| | Generated | Logs | Click streams | Text |
|---|---|---|---|---|
| Queries with `chance_posterior` above 0.5 | 4.4% | 0.1% | 3.5% | 50.3% |
| Top entry of `future_potentials` right, among those | 43% | too few | 54% | 17% |
| Top entry right, among the other queries | 84% | 84% | 69% | 22% |

(Pooled over the queries of each kind.)

A high `chance_posterior` marks the queries where nothing learned explains the STM, and answers there are right about half as often on generated data. On text it is above 0.5 for half of the queries: half the time, no stored pattern explains a new stretch of text better than chance does. It is a statement about the match, not about the next event, so `probability` in `future_potentials` is the sharper signal for whether an answer is right.

### On the Test Queries

117,200 further queries from the same 57 data sets were read once, after the formulas were fixed. A sum of the same kind fitted on the generated data alone is 0.3 points behind `potential` on them, so the weights are not tuned to the three real data sets.

| Share of queries answered right | Mean | Generated | Logs | Click streams | Text |
|---|---|---|---|---|---|
| Top entry of `future_potentials` | 0.647 | 0.856 | 0.860 | 0.690 | 0.183 |
| Top prediction that has a future, ranked by `potential` | 0.631 | 0.855 | 0.876 | 0.673 | 0.120 |
| The same, ranked by `good_odds` | 0.617 | 0.839 | 0.877 | 0.666 | 0.085 |
| The top prediction itself, ranked by `potential` | 0.488 | 0.836 | 0.876 | 0.123 | 0.118 |
| The same, ranked by `good_odds` | 0.480 | 0.813 | 0.877 | 0.151 | 0.078 |

### What Was Not Measured

- **The affinity-weighted metrics.** The data sets carry no emotives. The metrics are deprecated.
- **Fuzzy token matching** and character-level matching.
- **Sequences that end.** An event followed every query, so `ends_here` was measured only as probability given to an ending that did not come.
- **STMs of one symbol.** Every query has at least two.
- **Other recall thresholds, for every metric.** The tables are at 0.1.
- **Other domains.** Four kinds of data are not all kinds. The figures say how the metrics behave on these, and which conditions help or hurt each one; they are not a forecast for a new data set.

The [Ranking Benchmark](ranking-benchmark.md) measures the ranking keys through the REST API of a running instance, at three recall thresholds, on these kinds of data and on four more, with sequences that end and with request times, and it says which key to use when. Run [the benchmark](../../benchmarks/ranking/README.md) to see the figures for your own instance.

## Metric Categories

### Matching Metrics
- **matches, missing, extras**: Direct comparison between expected and observed
- **anomalies**: Flat list of all deviating symbols (missing + extras + fuzzy-observed)
- **fuzzy_matches**: Fuzzy token matches with similarity scores (when fuzzy matching enabled)
- **confidence, evidence**: Proportional matching scores
- **similarity, snr**: Quality of the match

### Temporal Metrics
- **past, present, future**: Temporal context and predictions
- **sequence**: The whole learned pattern
- **fragmentation**: Temporal cohesion
- **onset_alignment**: How early in the pattern the observation lands
- **event_cohesion**: Whether each observed event's symbols sit together in one pattern event

### Information Theory Metrics
- **entropy**: Information content of the pattern's own symbols
- **normalized_entropy, global_normalized_entropy**: Entropy measured against the node's vocabulary
- **confluence**: How far the pattern is from a chance co-occurrence, in bits
- **predictive_information**: The prediction's part of what the STM tells about the next event, in bits

### Probabilistic/Bayesian Metrics
- **bayesian_prior**: The pattern's share of everything the node has learned
- **bayesian_likelihood**: Weight of evidence the observation gives for the pattern over chance, in bits
- **good_odds**: Prior log-odds plus weight of evidence: the posterior log-odds against chance, in bits
- **bayesian_posterior**: Probability that this pattern produced the observation
- **chance_posterior** (ensemble): Probability that no learned pattern did
- **future_potentials** (ensemble): Probability of each next event

### Composite Metrics
- **potential**: Weighted sum of eleven terms (default ranking key)
- **itfdf_similarity**: Closeness on shared symbols, scaled by the pattern's share of the candidates' frequency
- **tfidf_score**: TF-IDF measure of pattern distinctiveness

### Affinity-Weighted Metrics
- **weighted_similarity, weighted_evidence, weighted_confidence, weighted_snr**: Deprecated; do not use. Matching metrics with each symbol weighted by its affinity to an emotive (set when the session configures `affinity_emotive`, `null` otherwise)

### Data Dependencies

The categories above group metrics by meaning. This table groups them by what they are computed from.

| The prediction alone (the pattern, the STM, and the match result) | The prediction and the node's counts | Every candidate of the request |
|---|---|---|
| `matches`, `past`, `present`, `future`, `sequence`, `missing`, `extras`, `anomalies`, `fuzzy_matches` | `bayesian_prior`: the pattern's frequency and the node's total of pattern frequencies | `bayesian_posterior` and `chance_posterior`: the `good_odds` of every candidate |
| `evidence`, `confidence`, `snr`, `similarity`, `fragmentation` | `bayesian_likelihood`, `good_odds`: each matched symbol's learned occurrences and the node's total | `future_potentials` and `ends_here`: the `potential` and next event of every candidate |
| `event_cohesion`, `onset_alignment` | `potential`: the pattern's frequency, and how many patterns hold each symbol of the STM and of `present` | `predictive_information`: the same, plus the learned occurrences of each symbol of the next event |
| `entropy` (Shannon entropy over the pattern's own symbols; precomputed, but computable from the pattern) | `confluence`: the pattern's frequency, the node's totals, and the learned occurrences of each of its symbols | `itfdf_similarity`: the summed frequency of every candidate (and, from the node, how many patterns hold each symbol) |
| | `tfidf_score`: the number of patterns in the node, and how many hold each symbol | |
| | `normalized_entropy`: the number of distinct symbols in the node | |
| | `global_normalized_entropy`: how many patterns hold each symbol, and the number of distinct symbols | |
| | `weighted_similarity`, `weighted_evidence`, `weighted_confidence`, `weighted_snr`: each symbol's node-wide affinity and frequency (set only when the session configures `affinity_emotive`) | |

Notes:

- `frequency` is the pattern's own stored count. It is read for every candidate before anything is scored.
- `emotives` are the pattern's own stored values. They are read for the predictions that are returned.
- A value in the third column is computed over every candidate above the recall threshold, not over the returned predictions, so it does not change with `max_predictions`.
- The node's counts move with every learn. A value in the second or third column describes the node as it was when the request was served.

## Usage Notes

1. **Prediction Selection**: Predictions arrive ranked by `potential`, the default `rank_sort_algo`. It is the most accurate ranking key on the mean of the four kinds of data it was measured on, and first or level on each; on eight kinds of data it is the best key or level with the best in nearly every case ([Ranking Benchmark](ranking-benchmark.md)). Other keys answer other questions:
   - `predictive_information`: a first prediction that almost always names a next event, for code that takes `predictions[0]` as it stands
   - `good_odds` (or `bayesian_posterior`, which ranks the same): a ranking in which every term has a closed-form meaning in bits
   - `bayesian_likelihood`: match strength alone, leaving out how often a pattern was learned
   - `frequency`: the most often learned candidates
   - `similarity`, `evidence`, `confidence`, `snr`: one aspect of the match at a time

2. **What Comes Next**: Read `future_potentials`, not only the top prediction. The top prediction is sometimes a pattern that ends where the observation ends, so its `future` is empty and it predicts nothing: on click-stream data that was the case for four requests in five. `future_potentials` pools the patterns that agree and gives each next event a probability; the weight of the patterns that have ended is reported as `ends_here`, the probability that nothing follows.

3. **How Sure**: Use `probability` in `future_potentials` as the confidence in the next event, `ends_here` as the probability that there is none, and `chance_posterior` as the check on the whole ensemble. A high `chance_posterior` means nothing learned explains the observation well.

4. **Confidence vs Evidence**:
   - `confidence` measures match quality in the current context
   - `evidence` measures how much of the total pattern is confirmed

5. **Temporal Fields**: The past/present/future fields maintain the sequential structure of events, preserving the learned temporal relationships.

6. **Symbol Sets**: The matches/missing/extras fields provide detailed diagnostics about prediction quality and help identify partial matches.

7. **Bits**: `bayesian_likelihood`, `good_odds`, `predictive_information` and `confluence` are in bits and can take either sign. One bit is a factor of two in probability. Values are comparable across requests on the same node.

8. **Bayesian Metrics**:
   - **A share of the node**: `bayesian_prior` is the pattern's share of every learn, whatever was observed
   - **Weighed against chance**: `bayesian_posterior` is a probability over the candidates and chance together, so the posteriors of every candidate and `chance_posterior` add up to 1.0
   - **Combines evidence types**: The posterior balances pattern frequency (prior) with observation fit (likelihood)
   - **Sure of itself on correlated symbols**: where symbols occur together by habit, the posterior states more certainty than the data support; its ranking is unaffected

9. **Node Totals**: `bayesian_prior`, `good_odds` and `confluence` divide by `total_pattern_frequencies`, which holds the sum of every pattern's frequency. If a node's counter holds less than that sum, priors come out too high until it is recounted: see [Recounting the pattern-frequency total](../users/database-persistence.md#recounting-the-pattern-frequency-total).

## Mathematical Foundations

The Prediction Object incorporates several mathematical concepts:

- **Information Theory**: Shannon entropy for the entropy fields; bits as base-2 logarithms of probability ratios; the Kullback-Leibler divergence behind `predictive_information`
- **Weight of Evidence**: I. J. Good's identity, prior log-odds plus weight of evidence equal posterior log-odds, for `bayesian_likelihood`, `good_odds` and `bayesian_posterior`
- **Noisy-Channel Matching**: An observation read as a pattern seen through a channel that drops and inserts symbols, for the likelihood behind `good_odds`
- **Statistical Mechanics**: Normalized entropy as an energy function; a Boltzmann (softmax) weighting of `potential` for `future_potentials`
- **Information Retrieval**: TF-IDF weighting of symbols, in `tfidf_score` and in the cosine term of `potential`
- **Signal Processing**: Signal-to-Noise Ratio for match quality
- **Bayesian Inference**: Posterior probabilities over the candidate patterns and chance

These metrics work together to provide a comprehensive assessment of pattern matching quality, temporal relationships, and predictive confidence in the KATO cognitive processing system.

## References

- I. J. Good, "Weight of Evidence: A Brief Survey", in *Bayesian Statistics 2*, J. M. Bernardo et al. (eds.), North-Holland, 1985, pp. 249-270 ([scan](https://www.waterboards.ca.gov/water_issues/programs/tmdl/docs/303d_policydocs/207.pdf)). The identity behind `good_odds`.
- C. E. Shannon, "A Mathematical Theory of Communication", *Bell System Technical Journal* 27, 1948 ([doi:10.1002/j.1538-7305.1948.tb01338.x](https://doi.org/10.1002/j.1538-7305.1948.tb01338.x)). Entropy, and the bit as a unit.
- S. Kullback and R. A. Leibler, "On Information and Sufficiency", *Annals of Mathematical Statistics* 22, 1951 ([doi:10.1214/aoms/1177729694](https://doi.org/10.1214/aoms/1177729694)). The divergence `predictive_information` adds up to.
- P. Domingos and M. Pazzani, "On the Optimality of the Simple Bayesian Classifier under Zero-One Loss", *Machine Learning* 29, 1997 ([doi:10.1023/A:1007413511361](https://doi.org/10.1023/A:1007413511361)). Why a posterior built on independent symbols can rank well while overstating its certainty.
