# Bayesian Framework for KATO Predictions: A Deep Analysis

## Executive Summary

This document provides a rigorous Bayesian interpretation of KATO's prediction system, going beyond standard Bayesian analysis to account for KATO's unique temporal, event-based architecture. We show how STM represents a **partial, noisy temporal window** into underlying generative patterns, and how that picture turns into four fields of the prediction object: `bayesian_prior`, `bayesian_likelihood`, `good_odds` and `bayesian_posterior`, with `chance_posterior` beside them.

---

## 1. KATO's Generative Process: The Ground Truth

### 1.1 The Hidden Generative Model

In KATO's framework, the world operates according to **temporal patterns** that exist in Long-Term Memory (LTM). These patterns represent **generative processes**—sequences of events that unfold over time.

**Key Insight**: A learned pattern is a hypothesis about how the world generates observable sequences.

```python
# Pattern in LTM (the "true" generative process)
Pattern: [['A','B'], ['C','D'], ['E','F'], ['G','H']]
         ↓
    past events → present events → future events
                  (what we observe)
```

### 1.2 Temporal Evolution

Each pattern has an implicit temporal evolution:

1. **Past Events** (already happened, not observable now)
2. **Present Events** (currently observable, but only partially)
3. **Future Events** (will happen, predictable from present)

**Critical**: The boundaries between past/present/future are **determined by what we actually observe**, not by absolute time.

---

## 2. The Observation Model: STM as Partial Evidence

### 2.1 STM is a Noisy Temporal Window

When we observe the world, we create Short-Term Memory (STM). But STM is **not** a perfect recording:

**Observable Process**:
```
True Pattern:     [['A','B'], ['C','D'], ['E','F'], ['G','H']]
                           ↓
Observation Window:        [observe some events]
                           ↓
STM (Noisy):              [['A'], ['C','D','X']]
                           ↓
Matching produces:
  - matches: ['A', 'C', 'D']  ← Symbols we correctly observed
  - missing: ['B']            ← Symbols in pattern present but not observed
  - extras:  ['X']            ← Noise/unexpected symbols we observed
  - past:    []               ← Events before first match
  - present: [['A','B'], ['C','D']]  ← Pattern events containing matches
  - future:  [['E','F'], ['G','H']]  ← Pattern events after last match
```

### 2.2 The Partial Observability Problem

**Three Sources of Incompleteness**:

1. **Temporal Truncation**: We only observe a window (present), not past or future
2. **Symbol Dropout**: Within present events, we miss some symbols (missing)
3. **Observation Noise**: We observe symbols not in the pattern (extras)

**This is fundamentally different from standard Bayesian classification**, where we assume complete but noisy observations.

### 2.3 How Pattern Matching Works (Sequence Alignment)

KATO uses **Longest Common Subsequence (LCS)** matching via difflib's SequenceMatcher:

```python
Pattern (flattened): ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']
STM (flattened):     ['A', 'C', 'D', 'X']

SequenceMatcher finds matching blocks:
  Block 1: pattern[0:1] ↔ state[0:1]   ('A' matches)
  Block 2: pattern[2:4] ↔ state[1:3]   ('C','D' match)

Similarity = 2 * matches / (len(pattern) + len(state))
           = 2 * 3 / (8 + 4) = 0.5
```

**Key**: Similarity captures **subsequence overlap**, accounting for both symbol presence and temporal order.

---

## 3. The Likelihood: Weight of Evidence in Bits

### 3.1 Two Hypotheses

Section 2 lists what separates an STM from the pattern behind it: truncation in time, dropped symbols and noise symbols. A likelihood has to put numbers on those three, and it has to be measured against something.

KATO measures every pattern against one alternative, **chance**: no learned pattern is occurring, and each observed symbol was drawn independently, with the probability `q(s)` of its share of all the symbol occurrences the node has learned.

So for each candidate there are two hypotheses:

- **H**: this pattern is occurring, and the STM is a noisy view of it
- **C**: chance

### 3.2 The Observation Model

Under **H**, three rules:

1. **A symbol of `present` is shown with probability `1 - e`** and dropped with probability `e`.
2. **A symbol the pattern does not account for is an intrusion.** It appears with probability `e × q(s)`: a noise event, then a draw by frequency.
3. **Which stretch of the pattern is in view is taken as given.** The `past` that was not observed and the `future` that has not happened are not evidence against the pattern.

`e` = 0.05 is the only constant. It is the assumed chance that a symbol is dropped from, or intrudes into, an observation of a pattern.

### 3.3 The Likelihood Ratio

Divide the probability of the STM under **H** by its probability under **C**, symbol by symbol:

| What happened | Under H | Under C | Ratio | Bits |
|---|---|---|---|---|
| A symbol of `present` was observed (a match) | `1 - e` | `q(s)` | `(1 - e) / q(s)` | `log2(0.95 / q(s))` |
| A symbol of `present` was not observed (missing) | `e` | 1 | `e` | -4.32 |
| A symbol was observed that the pattern lacks (extra) | `e × q(s)` | `q(s)` | `e` | -4.32 |

The logarithm of the product is a sum:

```
bayesian_likelihood = Σ over matches of log2((1 - e) / q(s))  -  log2(1 / e) × (missing + extras)
```

This is what I. J. Good called the **weight of evidence**: the logarithm of the factor by which an observation multiplies the odds of a hypothesis, which for two simple hypotheses is the likelihood ratio (Good 1985).

Three things follow from the table:

- **A match is worth more for a rarer symbol.** A symbol that makes up one thousandth of the node's symbol occurrences earns 9.9 bits. A symbol that makes up half of them earns 0.9.
- **Missing and extra symbols cost the same,** 4.32 bits each, whatever the symbol.
- **The unobserved future costs nothing.** A pattern of 100 events matched on its first 5 has the same weight of evidence as a pattern of 6 events matched on the same 5.

### 3.4 Why a Ratio, and Why Its Logarithm

A likelihood is only defined up to a factor that every hypothesis shares. The plain probability `P(STM | pattern)` is zero for every pattern as soon as the STM holds one symbol the node has never learned. Measured against chance, that symbol's probability cancels: it is an extra, and it costs 4.32 bits.

The ratio itself is unwieldy. Twenty matched symbols that each make up a thousandth of the node's occurrences give a factor of about 10^59, and a float overflows past 1,024 bits. The field holds the bits.

### 3.5 The Example of Section 2

The pattern `[['A','B'], ['C','D'], ['E','F'], ['G','H']]` was learned once, in a node that has also learned a two-event pattern three times. The node holds 14 symbol occurrences, one of them for each of `A` to `H`. The STM is `[['A'], ['C','D','X']]`.

```
matches   A, C, D     3 × log2(0.95 × 14 / 1)  =  +11.20 bits
missing   B           1 × -4.32                =   -4.32 bits
extras    X           1 × -4.32                =   -4.32 bits
                                                  ----------
bayesian_likelihood                            =   +2.56 bits
```

The observation is 2^2.56, about 6 times, more probable under the pattern than under chance.

### 3.6 Where the Structural Metrics Went

`evidence`, `confidence`, `snr` and `fragmentation` each describe one aspect of the same match:

| Aspect | Metric | In the weight of evidence |
|-----------|-------------|-------------|
| Temporal coverage | `evidence` | Not counted: the stretch in view is taken as given |
| Symbol accuracy | `confidence` | The missing symbols, at 4.32 bits each |
| Noise level | `snr` | The extras, at 4.32 bits each |
| Temporal structure | `fragmentation` | Not counted |

The weight of evidence keeps the two that are evidence about the pattern and drops the two that are not. `potential`, the default ranking score, takes a different route: it is a fitted sum that does use `snr` and `fragmentation`, among other terms. See [Potential Function](potential-function.md).

---

## 4. Prior, Good-Odds and Posterior

### 4.1 The Prior

```
bayesian_prior = frequency / F
```

`F` is the sum of every pattern's frequency in the node: each learn counts once. The prior is the pattern's share of everything the node has learned. It depends on the node alone, not on the observation and not on which other patterns matched.

### 4.2 Good's Identity

Good's identity for weighing evidence says that the initial log-odds plus the weight of evidence equal the final log-odds. In KATO's fields:

```
good_odds = log2(bayesian_prior) + bayesian_likelihood
```

| Part | Good's term | Field |
|---|---|---|
| `log2(frequency / F)` | prior (initial) log-odds | `log2(bayesian_prior)` |
| `log2((1 - e) / q(s))` per matched symbol, `-log2(1 / e)` per missing or extra symbol | weight of evidence, in bits | `bayesian_likelihood` |
| the total | posterior (final) log-odds | `good_odds` |

The odds are odds **against chance**. Chance is the common reference of every candidate and carries the weight 1, so a pattern's prior odds are its prior share, and `good_odds` of 0 means "as probable as chance". Above 0 the pattern explains the observation better than chance does, and each further bit doubles the odds.

In the example of section 3.5 the pattern holds 1 of the node's 4 learns: `log2(1 / 4)` = -2.00 bits. With 2.56 bits of evidence, `good_odds` is 0.56 bits: odds of about 1.5 to 1.

`good_odds` is a property of one prediction and the node. It does not depend on the other candidates, on their order, or on `max_predictions`, which makes it comparable from one request to the next.

### 4.3 The Posterior

A set of odds against a common reference turns into probabilities by dividing each by the total, and the reference itself counts as 1:

```
bayesian_posterior = 2^good_odds / (1 + Σ 2^good_odds)      summed over every candidate
chance_posterior   = 1           / (1 + Σ 2^good_odds)
```

The posteriors of every candidate and `chance_posterior` add up to 1.

In the example there is one candidate with odds of 2^0.56 = 1.47. Its posterior is 1.47 / 2.47 = 0.595, and `chance_posterior` is 0.405. One pattern matched, with one symbol missing and one symbol extra, and the model is not sure that it beats chance.

### 4.4 Why Chance Is in the Sum

Without the chance hypothesis a posterior is a share among the candidates, and a lone candidate gets 1.0 however weak its match.

A node has learned `a b c d` once and another pattern ten times. The STM is `a z w v`. One candidate clears the recall threshold:

| | Value |
|---|---|
| `bayesian_prior` | 1 / 11 = 0.091 |
| `bayesian_likelihood` | one match, three extras: -7.58 bits |
| `good_odds` | -11.04 bits |
| `bayesian_posterior` | 0.0005 |
| `chance_posterior` | 0.9995 |

The candidate is the best explanation KATO has, and it is two thousand times less probable than chance. `chance_posterior` is how the response says so. It is the graded form of KATO's "I don't know": an STM that matches nothing returns an empty ensemble and a `chance_posterior` of 1.0, and an STM that matches weakly returns predictions and a `chance_posterior` close to 1.0.

Giving chance the weight 1 is a convention, and it has a consequence: before any observation, "none of the learned patterns" is taken to be as probable as all of them together.

---

## 5. From Patterns to Futures

### 5.1 Two Questions

KATO predictions answer two different questions:

**Which pattern?**
```python
P(pattern_i | STM) = bayesian_posterior
```

**What comes next?**
```python
P(next_event | STM) = future_potentials[...]["probability"]
```

Several patterns can predict the same next event, and then their support adds up.

A node has learned `a b c d` five times, `a b c e` four times and `a b x y` six times. The STM is `a b`:

| Pattern | `bayesian_posterior` | Next event |
|---|---|---|
| `a b x y` | 0.374 | `x` |
| `a b c d` | 0.312 | `c` |
| `a b c e` | 0.249 | `c` |

```json
"future_potentials": [
  {"next_event": ["c"], "probability": 0.6216, "supporting_patterns": 2},
  {"next_event": ["x"], "probability": 0.3784, "supporting_patterns": 1}
]
```

The single most probable pattern says `x`. The most probable next event is `c`, because two patterns agree on it.

**Application**: Decision-making should use `P(next_event | STM)`, not `P(pattern | STM)`, when you care about outcomes, not explanations.

### 5.2 Why `future_potentials` Does Not Sum Posteriors

The direct construction would add the posteriors of the patterns that share a next event. KATO does not do that. `future_potentials` adds `e^potential` instead:

```
P(E | STM) = Σ e^potential over the candidates whose next event is E
             / Σ e^potential over the candidates that have a future
```

The reason is calibration. The observation model adds each matched symbol's bits as if the symbols were independent observations. In real data symbols travel together: the words of a phrase, the steps of a fixed routine. The same evidence is then counted several times, and the posterior is pushed toward 0 and 1. This is the known behaviour of a posterior built on an independence assumption: it can rank well while overstating its certainty (Domingos and Pazzani 1997; Niculescu-Mizil and Caruana 2005).

Measured on 58,600 held-out queries from four kinds of data, the probability given to the top next event against the share of those answers that were right:

| | Generated sequences | HDFS logs | MSNBC clicks | WikiText-2 text |
|---|---|---|---|---|
| Posteriors summed by next event, as shares of the candidates that have a future: said / right | 0.909 / 0.837 | 0.906 / 0.874 | 0.662 / 0.686 | 0.564 / 0.127 |
| `e^potential` summed by next event (`future_potentials`): said / right | 0.812 / 0.851 | 0.837 / 0.860 | 0.615 / 0.688 | 0.202 / 0.193 |

On text the sum of posteriors claims 56% and delivers 13%. With chance left in the sum the claim falls to 26%, still twice what is delivered. The weights of `potential` were fitted on outcomes, to make the probability of the event that actually followed as large as possible, and the probabilities built on it track what happens.

**What this means for the fields.** `good_odds` and `bayesian_posterior` rank correctly and say which pattern explains the STM best. On data with correlated symbols their bits and probabilities overstate the evidence. The probability of the next event belongs to `future_potentials`.

### 5.3 Expected Utility (Decision-Theoretic Ranking)

When patterns carry `emotives` with utility information, weigh each prediction's utility by its probability:

```python
# Each prediction has utility scores
prediction = {
    'bayesian_posterior': 0.7,
    'emotives': {
        'reward': 10.0,
        'risk': -5.0,
        'effort': -2.0
    }
}

# Expected utility of acting on this prediction
expected_utility = (
    prediction['bayesian_posterior']
    * sum(prediction['emotives'].values())
)

# Total expected utility: 0.7 × (10 - 5 - 2) = 2.1
```

Expected utility is computed by the application from the fields KATO returns. It is not a `rank_sort_algo` value.

**Example Decision Scenario**:
```
Prediction A: P=0.9, utility=+1  → EU = 0.9  ← Safe, small gain
Prediction B: P=0.4, utility=+10 → EU = 4.0  ← Risky, big gain
Prediction C: P=0.6, utility=-3  → EU = -1.8 ← Avoid!

Rational choice: B (highest expected utility despite lower probability)
```

---

## 6. KATO-Specific Bayesian Applications

### 6.1 Disambiguating Competing Patterns (Same Match, Different Priors)

**Scenario**: Two patterns match the observation equally well and differ in frequency:

```
Pattern A: [['hello'], ['world'], ['!!']]     learned 100 times
Pattern B: [['hello'], ['world'], ['??']]     learned 2 times

STM: [['hello'], ['world']]
```

| | Pattern A | Pattern B |
|---|---|---|
| `similarity` | 0.8 | 0.8 |
| `bayesian_likelihood` | 3.02 bits | 3.02 bits |
| `bayesian_prior` | 100 / 102 = 0.980 | 2 / 102 = 0.020 |
| `good_odds` | 2.99 bits | -2.65 bits |
| `bayesian_posterior` | 0.873 | 0.017 |

`chance_posterior` takes the remaining 0.110.

Ranked by `similarity` the two tie. Ranked by `good_odds` or `bayesian_posterior`, A is 50 times more probable than B, which is the ratio of their frequencies.

**Use Case**: When several patterns match equally well, the prior decides, and it favours the patterns the node has seen most.

### 6.2 "Best Match" vs "Most Likely Generator"

**Two Different Questions**:

1. **Best Match**: "Which pattern is most similar to the STM?"
   - Answer: Rank by `similarity`
   - Similarity falls as the unobserved part of a pattern grows

2. **Most Likely Generator**: "Which pattern probably produced the STM?"
   - Answer: Rank by `good_odds` (or `bayesian_posterior`, which gives the same order)
   - Combines the weight of evidence with the prior

**Example**: a node has learned `a b` once and `a b c d e f` twenty times. The STM is `a b`.

| Pattern | `similarity` | `bayesian_likelihood` | `bayesian_prior` | `bayesian_posterior` |
|---|---|---|---|---|
| `a b` | 1.0 | 4.93 bits | 0.048 | 0.046 |
| `a b c d e f` | 0.5 | 4.93 bits | 0.952 | 0.922 |

Both patterns account for both symbols, with nothing missing and nothing extra, so the observation supports them equally. `similarity` prefers the short pattern, because the long one has four events the STM does not hold. The posterior prefers the pattern learned twenty times, and that pattern is also the one with a future to predict.

**When to use each**:
- **Similarity**: When you want the "most similar template" (e.g., nearest neighbor search over whole sequences)
- **Good-odds / posterior**: When you want the "most probable explanation" (e.g., diagnosis)

### 6.3 Uncertainty of a Ratio (Credible Intervals)

The ratio metrics are point estimates. An application can attach an interval to one of them:

```python
# confidence = matches / present_length
# Model as Binomial: matches ~ Binomial(present_length, p_true)

from scipy.stats import beta

α = len(matches) + 1  # successes + 1 (Laplace smoothing)
β = (len(present) - len(matches)) + 1  # failures + 1

# 95% credible interval for true match probability
ci_lower, ci_upper = beta.ppf([0.025, 0.975], α, β)
```

**Interpretation**: "We're 95% confident the true match rate is between `ci_lower` and `ci_upper`"

**Use Case**: `confidence=0.8` from 5 symbols and `confidence=0.8` from 500 symbols are different amounts of knowledge, and the interval shows it.

### 6.4 Active Learning: What to Observe Next?

The posterior over patterns enables **information gain** calculations:

```python
# Current uncertainty (entropy over pattern posterior)
H_current = -Σ P(pattern_i|STM) × log(P(pattern_i|STM))

# If we observe symbol 'X' next, expected posterior entropy
H_after_X = Σ P(X|pattern_i) × H(pattern|STM, X observed)
             patterns

# Information gain from observing X
IG(X) = H_current - H_after_X
```

**Application**: Choose the next observation to **maximize information gain** about which pattern is producing the sequence.

**Example**:
```
Current posteriors:
  Pattern A: [['a'], ['b'], ['c']]  P=0.445
  Pattern B: [['a'], ['b'], ['d']]  P=0.445
  (chance: 0.110)

Observe 'c' next:
  → P(A|STM,'c') = 0.951, P(B|STM,'c') = 0.008   [Low entropy]

IG('c') = HIGH (disambiguates A vs B)
IG('a') = LOW  (both hold 'a', no new information)
```

### 6.5 Predictive Information

`predictive_information` measures, in bits, how much the STM tells about the next event:

```python
predictive_information = share × log2(P(E | STM) / q(E))
```

`E` is the prediction's next event, `P(E | STM)` its probability in `future_potentials`, `share` the prediction's own part of that probability, and `q(E)` the probability of the event by chance. Over the predictions of a request the values add up to the Kullback-Leibler divergence of the next-event distribution from chance.

It is a measure, not a probability: it says how informative a context is, and which patterns carry the information. See [Predictive Information](predictive-information.md).

---

## 7. Practical Recommendations

### 7.1 When to Use Each Metric

| Goal | Use | Why |
|------|---------------|-----|
| Best next-event prediction | `future_potentials` | Pools the patterns that agree; its probability tracks how often it is right |
| Default ranking of patterns | `potential` | The most accurate ranking key |
| Most probable explanation, term by term | `good_odds` / `bayesian_posterior` | Prior plus weight of evidence, in bits |
| Match strength without frequency | `bayesian_likelihood` | Weight of evidence alone |
| Best match template | `similarity` | Direct sequence similarity |
| Declining to answer | `chance_posterior` | Probability that nothing learned explains the STM |
| Decision-making | expected utility, computed by the application | Weighs outcomes by probability |

### 7.2 Configuration Examples

```python
# Use case: Diagnosis (need the most probable explanation, with its derivation)
config = SessionConfiguration(
    rank_sort_algo='good_odds',     # Prior plus weight of evidence, in bits
    recall_threshold=0.1,           # Keep weak candidates: the posterior is over all of them
    max_predictions=20              # Consider many hypotheses
)

# Use case: Next-step prediction (need the most likely continuation)
config = SessionConfiguration(
    rank_sort_algo='potential',     # Default
    recall_threshold=0.1,
    max_predictions=10              # future_potentials still covers every candidate
)

# Use case: Template lookup (need the closest whole sequence)
config = SessionConfiguration(
    rank_sort_algo='similarity',
    recall_threshold=0.6,           # Only close matches
    max_predictions=5
)
```

### 7.3 Ensemble Decision Strategies

**Next event with a confidence floor**:
```python
def decide(response, min_probability=0.7, max_chance=0.5):
    """Return the next event, or None for "I don't know"."""
    if not response['predictions'] or response['chance_posterior'] > max_chance:
        return None
    if not response['future_potentials']:
        return None
    best = response['future_potentials'][0]
    return best['next_event'] if best['probability'] >= min_probability else None
```

**Expected utility over next events**:
```python
# Utility of each next event, weighted by the share of the patterns that predict it
utility = {}
for pred in response['predictions']:
    if pred['future']:
        event = tuple(pred['future'][0])
        value = sum(pred['emotives'].values())
        utility[event] = utility.get(event, 0.0) + pred['bayesian_posterior'] * value

best_event = max(utility, key=utility.get) if utility else None
```

Set `max_predictions` high enough that the predictions the sum should cover are all returned.

---

## 8. Theoretical Connections

### 8.1 Connection to Computational Mechanics

KATO's architecture aligns with **Computational Mechanics** theory (Crutchfield et al.):

- **ε-machines**: KATO patterns are analogous to causal states
- **Excess Entropy**: the mutual information between past and future. `predictive_information` is its per-request counterpart: the divergence of the next-event distribution from chance, given this STM
- **Statistical Complexity**: Pattern count weighted by entropy

### 8.2 Connection to Hidden Markov Models (HMMs)

KATO can be viewed as a **non-parametric HMM**:

- **Hidden states**: Positions in learned patterns
- **Observations**: STM symbols (partial, noisy)
- **Transition probabilities**: Implicit in pattern structure
- **Emission probabilities**: The observation model of section 3.2, with its one constant

**Difference**: HMMs learn continuous transition matrices. KATO learns discrete exemplar patterns (instance-based learning).

### 8.3 Connection to the Noisy-Channel Model

Rules 1 and 2 of section 3.2 describe a channel that deletes and inserts symbols. Scoring a stored sequence against a corrupted observation by a prior times a channel probability is the noisy-channel model of speech recognition and spelling correction (Bahl and Jelinek 1975; Kernighan, Church and Gale 1990). Measuring the result against a chance model, in bits, is how record linkage and sequence alignment score a match (Fellegi and Sunter 1969; Altschul 1991).

### 8.4 Connection to Bayesian Program Learning

**Bayesian Program Learning** (Lake et al.) learns generative programs.

**KATO's analog**:
- **Programs**: Learned patterns (sequences of events)
- **Program prior**: Pattern frequency
- **Likelihood**: Weight of evidence (how well the pattern accounts for the observation, against chance)
- **Inference**: Pattern matching (finding the best explanation)

**KATO's advantage**: Deterministic, traceable inference (no sampling required).

---

## 9. Limitations and Future Work

### 9.1 Current Limitations

1. **Independent Observation Assumption**: The likelihood treats each symbol as an independent observation. Symbols within and across events are correlated in real data, so the bits are overstated and the posterior is surer than it should be (section 5.2). The ranking is not affected.

2. **One Constant for Three Kinds of Noise**: A dropped symbol and an intruding symbol both cost `log2(1 / e)`, with `e` = 0.05 for every node. Across `e` from 0.01 to 0.2 the accuracy of ranking by `good_odds` moves by 0.3 points on the data it was measured on, so the choice is not delicate, but it is not fitted to a node's own noise either.

3. **Events of Several Symbols**: The chance probability of an event multiplies the shares of its symbols. An event whose symbols always occur together looks rarer than it is.

4. **The Weight of Chance**: Chance carries the weight 1 against all the patterns together (section 4.4). A node that should expect unfamiliar input more, or less, often than that has no setting for it.

5. **Stationary Priors**: Pattern frequencies do not decay over time.

### 9.2 Potential Extensions

**Time-Aware Bayesian Priors**:
```python
# Decay old patterns, upweight recent patterns
P(pattern) = frequency × exp(-λ × age_since_last_seen)
```

**Bayesian Pattern Merging**:
```python
# Merge similar patterns with Bayesian model selection
BIC(merge) = log P(data|merged) - (params/2) × log(N)
```

**Conditional Bayesian Posteriors**:
```python
# Posterior given context (metadata, emotives)
P(pattern|STM, context) = P(STM|pattern) × P(context|pattern) × P(pattern) / Z
```

---

## 10. Conclusion

### Key Takeaways

1. **STM is a partial, noisy temporal window** into underlying generative patterns, not a complete observation.

2. **The likelihood is a weight of evidence.** Each matched symbol adds bits, more for a rarer symbol. Each missing or extra symbol costs 4.32 bits. The unobserved past and future cost nothing.

3. **`good_odds` is Good's identity in KATO's fields**: `log2(bayesian_prior) + bayesian_likelihood`, the posterior log-odds of the pattern against chance.

4. **The posterior includes chance.** `bayesian_posterior` and `chance_posterior` add up to 1, so a weak lone match is not believed for being the only one.

5. **Patterns and futures are different questions.** `bayesian_posterior` says which pattern, `future_potentials` says what comes next, and the second is the one to act on.

### The Deep Insight

**KATO's deterministic pattern matching** can be understood as **Bayesian inference with a structured likelihood function** that respects partial observability and symbolic structure.

This isn't just mathematical formalism. It provides **operational guidance**:
- Use `future_potentials` when you need **the next event and a probability for it**
- Use `good_odds` or `bayesian_posterior` when you need **probable explanations**
- Use `chance_posterior` when you need to know **whether anything learned applies**
- Use `similarity` when you need **good matches of whole sequences**

---

## References

- I. J. Good, "Weight of Evidence: A Brief Survey", in *Bayesian Statistics 2*, J. M. Bernardo et al. (eds.), North-Holland, 1985, pp. 249-270 ([scan](https://www.waterboards.ca.gov/water_issues/programs/tmdl/docs/303d_policydocs/207.pdf)).
- L. R. Bahl and F. Jelinek, "Decoding for Channels with Insertions, Deletions, and Substitutions with Applications to Speech Recognition", *IEEE Transactions on Information Theory* 21(4), 1975 ([doi:10.1109/TIT.1975.1055419](https://doi.org/10.1109/TIT.1975.1055419)).
- M. D. Kernighan, K. W. Church and W. A. Gale, "A Spelling Correction Program Based on a Noisy Channel Model", *COLING 1990* ([ACL Anthology C90-2036](https://aclanthology.org/C90-2036/)).
- I. P. Fellegi and A. B. Sunter, "A Theory for Record Linkage", *Journal of the American Statistical Association* 64(328), 1969 ([doi:10.2307/2286061](https://doi.org/10.2307/2286061)).
- S. F. Altschul, "Amino Acid Substitution Matrices from an Information Theoretic Perspective", *Journal of Molecular Biology* 219(3), 1991 ([doi:10.1016/0022-2836(91)90193-A](https://doi.org/10.1016/0022-2836(91)90193-A)).
- P. Domingos and M. Pazzani, "On the Optimality of the Simple Bayesian Classifier under Zero-One Loss", *Machine Learning* 29, 1997 ([doi:10.1023/A:1007413511361](https://doi.org/10.1023/A:1007413511361)).
- A. Niculescu-Mizil and R. Caruana, "Predicting Good Probabilities with Supervised Learning", *Proceedings of the 22nd International Conference on Machine Learning*, 2005 ([doi:10.1145/1102351.1102430](https://doi.org/10.1145/1102351.1102430)).
