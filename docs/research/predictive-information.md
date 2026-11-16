# Excess Entropy / Predictive Information in KATO

## Executive Summary

**Predictive Information** (also called **Excess Entropy**) measures how much information the past of a sequence contains about its future. In KATO the `predictive_information` field is that quantity for one request: the bits the short-term memory (STM) carries about the next event, split among the predictions that propose one.

```
predictive_information = share × log2(P(E | STM) / q(E))
```

Where:
- `E`: the prediction's next event, the first event of its `future`
- `P(E | STM)`: the probability of that event in `future_potentials`
- `share`: the prediction's own part of that probability
- `q(E)`: the probability of the event by chance

The values of a request add up to the Kullback-Leibler divergence of the next-event distribution from chance. That sum is the answer to "how much does this observation tell me about what comes next?", in bits.

`predictive_information` is a measure. It is available as a `rank_sort_algo` value, and it ranks slightly below `potential`, the default.

## 1. Theoretical Foundation

### 1.1 Information-Theoretic Definition

Excess Entropy (EE) is formally defined as the mutual information between the semi-infinite past and semi-infinite future of a stochastic process:

```
E = I(Past; Future) = Σ P(past, future) log₂[P(past, future)/(P(past)·P(future))]
```

This captures the **complexity of structure** in sequences—not just randomness (entropy rate) but the predictive relationships between different parts of the sequence.

### 1.2 Intuitive Understanding

- **Entropy rate** (h_μ): How unpredictable each next symbol is
- **Excess entropy**: How much "hidden structure" exists—the reduction in uncertainty about the future by knowing the past
- **High EE**: Strong correlations between past and future (reliable predictions)
- **Low EE**: Either nearly random (white noise) or trivially repetitive

### 1.3 From an Average to One Observation

Mutual information is an average over every past the process can produce. It can be written as the average of a quantity that belongs to one past:

```
I(Past; Future) = Σ P(past) × D( P(future | past) ‖ P(future) )
                  past
```

`D` is the Kullback-Leibler divergence (Kullback and Leibler 1951): how far the distribution of the future, given this past, is from the distribution of the future with nothing known.

A prediction request has one past in hand, the STM. The inner term is therefore the quantity a request can report: the information this STM carries about the future. KATO computes that term, and its average over the STMs a node sees is the mutual information of section 1.1.

## 2. KATO's Temporal Segmentation Mapping

### 2.1 Conceptual Alignment

The critical insight is that KATO's temporal segmentation differs from traditional excess entropy formulations:

**Traditional EE:**
- Past: Everything before current observation
- Future: Everything after current observation

**KATO's Implementation:**
- **Past**: Events BEFORE the first matching event
- **Present**: ALL events containing matching symbols (the observed overlap)
- **Future**: Events AFTER the last matching event

### 2.2 Mapping to Predictive Information

For predictive information calculation in KATO:
- **EE "Past"** → the **STM** (what has been observed, which the matching aligns with each pattern's "present")
- **EE "Future"** → the **next event**: the first event of a prediction's `future`

This mapping makes sense because:
1. The STM represents what we know
2. The next event is what a prediction is asked for first
3. The divergence between the two distributions of that event, with and without the STM, measures predictive power

## 3. Mathematical Formulation for KATO

### 3.1 The Distribution Given the STM

`P(E | STM)` is the next-event distribution KATO already returns as `future_potentials`:

```
P(E | STM) = Σ e^potential over the candidates whose next event is E
             / Σ e^potential over every candidate
```

A candidate whose pattern ends where the STM ends proposes no event. Its weight is `ends_here`, the probability that nothing follows, so the events hold `1 - ends_here` between them.

The candidates above the recall threshold are KATO's estimate of what can follow this STM, so no separate store of present and future co-occurrences is needed.

### 3.2 The Distribution With Nothing Known

With nothing known, an event is as probable as its symbols are common:

```
q(E) = Π q(s)    over the symbols of E
```

`q(s)` is the symbol's share of all the symbol occurrences the node has learned. This is the chance model that `good_odds` and `confluence` use.

### 3.3 The Divergence

```
D = Σ P(E | STM) × log2( P(E | STM) / q(E) )
    E
```

Each term says how many bits the ensemble's probability for an event is above its chance probability, weighted by that probability. The sum runs over the events the candidates propose. When no candidate has ended, their probabilities add up to 1 and `D` is the Kullback-Leibler divergence of the next-event distribution from chance. When some have ended, `D` counts the events alone: "nothing follows" is not an event with symbols, so it has no chance probability to be measured against.

### 3.4 One Prediction's Part

Several predictions can propose the same next event. Each gets its part of that event's term:

```python
share = e^potential / Σ e^potential over every candidate

predictive_information = share × log2(P(E | STM) / q(E))
```

The shares of the predictions that propose `E` add up to `P(E | STM)`, so the values of all the predictions add up to `D`.

A prediction with no `future` proposes nothing and has `predictive_information` 0.0.

## 4. Implementation in KATO

### 4.1 Where It Is Computed

`kato/informatics/prediction_metrics.py`:

- `score_ensemble()` sets `predictive_information` on every candidate, together with `potential`, `good_odds`, the Bayesian fields and `future_potentials`.
- `predictive_information()` returns the values of a list of predictions by pattern name.

### 4.2 Order of Operations

1. Every candidate above the recall threshold gets its `potential`.
2. The shares are computed over every candidate, and the next-event probabilities add up the shares of the candidates that have a future.
3. Each such candidate gets `share × (log2 P(E | STM) + Σ log2(1 / q(s)))`, the sum taken over the symbols of its next event.
4. The candidates are ranked and cut to `max_predictions`.

Step 4 comes last, so a prediction's value does not depend on `max_predictions`.

### 4.3 Determinism

Sums over the candidates run in pattern-name order, and every exponential is taken relative to the largest `potential`. The same candidates give the same bits on every request.

## 5. Example Calculation

### 5.1 Scenario Setup

A node has learned three patterns, one symbol per event:

| Pattern | Times learned |
|---|---|
| `login`, `browse`, `checkout` | 5 |
| `login`, `browse`, `logout` | 3 |
| `login`, `reset_password`, `logout` | 2 |

The node holds 30 symbol occurrences: `login` 10, `browse` 8, `checkout` 5, `logout` 5, `reset_password` 2.

**STM Observation**: `login`, then `browse`.

### 5.2 Next-Event Distribution

| Pattern | `potential` | Weight relative to the best | Next event |
|---|---|---|---|
| `login, browse, checkout` | 17.197 | 1.0000 | `checkout` |
| `login, browse, logout` | 16.850 | 0.7066 | `logout` |
| `login, reset_password, logout` | 8.106 | 0.0001 | `reset_password` |

Normalised: `P(checkout | STM)` = 0.5859, `P(logout | STM)` = 0.4140, `P(reset_password | STM)` = 0.0001.

### 5.3 Predictive Information Calculation

```python
# checkout: 5 of 30 symbol occurrences
q = 5 / 30 = 0.1667
PI = 0.5859 * log2(0.5859 / 0.1667)
   = 0.5859 * 1.814
   = 1.063 bits

# logout: 5 of 30
PI = 0.4140 * log2(0.4140 / 0.1667)
   = 0.4140 * 1.313
   = 0.544 bits

# reset_password: 2 of 30
q = 2 / 30 = 0.0667
PI = 0.000066 * log2(0.000066 / 0.0667)
   = 0.000066 * -9.98
   = -0.001 bits
```

### 5.4 Reading the Result

The three values add up to 1.606 bits. Before the observation, `checkout` and `logout` each had a chance probability of one in six. After it, they hold 0.59 and 0.41 between them. The STM has narrowed the next event from about six equally likely options to roughly two, and 1.6 bits is the size of that narrowing.

The third value is negative. The ensemble gives `reset_password` a probability a thousand times below its chance probability, so that prediction's part of the total is a small subtraction.

## 6. Benefits and Implications

### 6.1 Theoretical Advantages

1. **Information-Theoretic Foundation**: Grounded in established theory from computational mechanics
2. **A Unit**: Bits, comparable between requests on the same node
3. **Additive**: The values of a request add up to one interpretable quantity

### 6.2 Practical Benefits

1. **How informative is this context?** The sum over a request says how much the observation pins down the next event. A long, specific STM that leaves one rare event carries many bits. A common opening that leaves several common events carries few.
2. **Which patterns carry the information?** Each prediction's value is its part of the total.
3. **Spotting empty contexts.** A total near zero means the STM leaves the next event about as open as it was.

### 6.3 What It Is Not

`predictive_information` is not a probability and not a confidence. It grows with the rarity of the predicted event as well as with its probability, so a likely common event can score below a less likely rare one. For the most probable next event use `future_potentials`.

## 7. Measured Behaviour

Measured on 58,600 held-out queries from four kinds of data, at `recall_threshold` 0.1.

### 7.1 Does the Claim Hold?

The sum of `predictive_information` over a request is a claim: this many bits about the next event. The claim can be checked against what was delivered, the logarithm of the probability the ensemble gave to the event that did follow, over that event's chance probability.

| Mean bits per query | Generated sequences | HDFS logs | MSNBC clicks | WikiText-2 text |
|---|---|---|---|---|
| Claimed (sum of `predictive_information`) | 8.64 | 2.47 | 1.78 | 3.67 |
| Delivered | 8.42 | 2.42 | 2.09 | 0.73 |
| Available (chance bits of the event that followed) | 9.85 | 3.06 | 3.75 | 9.87 |

The claim holds on three kinds of data. On text it overclaims: for 14% of the queries there, no candidate proposes the event that actually followed, and the ensemble is confident about the events it does propose.

"Delivered" is computed with a floor: the ensemble's probability is mixed 99 to 1 with the chance probability, so that an event no candidate proposed counts as slightly below chance instead of minus infinity.

### 7.2 As a Ranking Key

Ranked by `predictive_information`, the top prediction that has a future names the right next event for 0.617 of the queries (mean of the four kinds), against 0.633 when ranked by `potential`: 1.6 points lower.

The reason is in the formula. It multiplies a probability by a rarity, and the most probable next event is the best single guess whatever its rarity.

### 7.3 As a Confidence Value

Used to separate right answers from wrong ones, the `predictive_information` of the top prediction has an AUROC of 0.70. The `probability` of the top entry of `future_potentials` has 0.80.

## 8. Edge Cases and Considerations

### 8.1 Empty Segments

- Empty future → PI = 0.0 (the prediction proposes no next event)
- No candidate with a future → every PI is 0.0 and `future_potentials` is empty
- Empty STM → no prediction is computed

### 8.2 Negative Values

A value is negative when the ensemble gives an event less probability than chance does. Negative values are small in practice, because they are weighted by a small share.

### 8.3 Events of Several Symbols

`q(E)` multiplies the shares of an event's symbols. An event whose symbols always occur together therefore looks rarer than it is, and its bits are overstated.

### 8.4 Never-Learned Symbols

The next event comes from a learned pattern, so every symbol in it has been learned and has a count of at least 1.

## 9. Testing

### 9.1 Unit Tests

- `tests/tests/unit/test_prediction_metrics_formulas.py`: hand-computed values, the sum over a request against the divergence, a prediction without a future
- `tests/tests/unit/test_prediction_scoring_order.py`: the value does not change with `max_predictions`, with the order the candidates arrive in, or with the ranking key

### 9.2 Integration Tests

- `tests/tests/integration/test_predictive_information_e2e.py`: the field through the API, with learning and prediction against the running services

## 10. Future Extensions

### 10.1 Longer Horizons

The field measures information about the next event. The same construction over the whole `future`, or over the event `k` steps ahead, would measure information at longer range.

### 10.2 Conditional Predictive Information

Extend to conditional PI given context:
```
I(Past; Future | Context)
```

### 10.3 A Node-Wide Figure

Averaging the per-request total over the STMs a node serves estimates the mutual information of section 1.1 for that node's data.

## Conclusion

`predictive_information` puts a unit on what a prediction request learns from its observation: bits about the next event, measured against chance, and attributed to the patterns that supply them. It is computed from the same candidates and the same scores as the rest of the response, so it is deterministic and traceable to the patterns behind it.

## References

- S. Kullback and R. A. Leibler, "On Information and Sufficiency", *Annals of Mathematical Statistics* 22, 1951 ([doi:10.1214/aoms/1177729694](https://doi.org/10.1214/aoms/1177729694)).
- C. E. Shannon, "A Mathematical Theory of Communication", *Bell System Technical Journal* 27, 1948 ([doi:10.1002/j.1538-7305.1948.tb01338.x](https://doi.org/10.1002/j.1538-7305.1948.tb01338.x)).

## Related Documentation

- [Prediction Object Reference](../reference/prediction-object.md) - Every field and its formula
- [Potential Function](potential-function.md) - The score behind `P(E | STM)`
- [Bayesian Framework](bayesian-framework-for-kato.md) - The chance model, `good_odds` and the posterior
- [Information Theory](information-theory.md) - Theoretical foundations
