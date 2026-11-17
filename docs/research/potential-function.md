# Predictive Potential Function in KATO

## Table of Contents
1. [Overview](#overview)
2. [Potential Function Definition](#potential-function-definition)
3. [The Eleven Terms](#the-eleven-terms)
4. [How the Weights Were Fitted](#how-the-weights-were-fitted)
5. [Mathematical Properties](#mathematical-properties)
6. [Worked Example](#worked-example)
7. [From Potential to Probabilities](#from-potential-to-probabilities)
8. [Measured Accuracy](#measured-accuracy)
9. [Alternative Ranking Functions](#alternative-ranking-functions)
10. [Comparison to Other Approaches](#comparison-to-other-approaches)
11. [References](#references)

## Overview

The **potential function** is KATO's default score for ranking predictions. Every candidate pattern gets one number, and the candidates are returned highest first.

`potential` answers one question: of the patterns that match the short-term memory (STM), which is most likely to continue it? It is a weighted sum of eleven terms. Each term is computed from the prediction's own fields and the node's counts, and each weight is a constant.

### Purpose

- Rank the candidates so that the top prediction is the pattern most likely to continue the observation
- Supply the weights behind `future_potentials`, the probability of each next event
- Stay explainable: a score is eleven named numbers that can be printed and checked by hand

## Potential Function Definition

### Formula

```
potential = Σ weight × term        over the eleven terms below
```

### Terms and Weights

| Term | Weight | What it measures |
|------|--------|------------------|
| `cosine_idf_present` | +6.037962738972206 | Cosine between the STM and `present` as bags of symbols, rare symbols counting more |
| `last_event_matched` | +2.7551983021381603 | 1 if the newest STM event has a matched symbol, else 0 |
| `evidence_to_end` | +2.2050945031820732 | Matches over the symbols of `past` and `present` |
| `recency_07` | +1.7897143000355997 | Matched STM symbols, each counted `0.7^n` for an event `n` events back from the newest |
| `tversky` | +0.947709643038957 | `matches / (matches + 2 × missing + 2 × extras)` |
| `fragmentation` | -0.7701727284444962 | Matched blocks minus one |
| `log_frequency` | +0.6797831284041117 | Natural logarithm of the pattern's frequency |
| `snr` | +0.5843639561444975 | `(2 × matches - extras) / (2 × matches + extras)` |
| `inverse_fragmentation` | +0.3874235103814889 | `1 / (fragmentation + 1)` |
| `recency_09` | +0.0632088710855439 | As `recency_07`, with 0.9 |
| `last_event_share` | +0.022364665110185304 | Matched share of the newest STM event's symbols |

The weights are held in `kato/informatics/prediction_metrics.py` as `POTENTIAL_WEIGHTS`. In the same module, `potential_terms()` returns the eleven term values of a prediction and `potential()` adds them up.

### Interpretation

`potential` has no fixed scale. What carries meaning is the difference between two candidates of the same STM: `future_potentials` weights each candidate by `e^potential`, so a difference of 1.0 is a factor of `e` in a candidate's say about the next event, and a difference of 5 is a factor of about 150.

For orientation: an STM of two one-symbol events that exactly matches the first two events of a pattern learned once scores 16.10. Every doubling of the frequency adds 0.47.

## The Eleven Terms

The terms fall into seven groups. Each group answers one question about the match.

### Do the observation and the pattern agree on rare symbols?

**`cosine_idf_present`** treats the STM and the prediction's `present` as bags of symbols and takes the cosine between them. Each symbol is weighted by its inverse document frequency, `log2(patterns / patterns holding the symbol) + 1`, the same IDF that `tfidf_score` uses.

A symbol that half the node's patterns hold says little about which pattern is occurring. A symbol that three patterns hold says a lot. The weighting makes agreement on the second kind count for more.

The cosine is 1.0 when the STM and `present` hold the same symbols in the same numbers. It falls with every symbol on one side that the other lacks, and falls faster when that symbol is rare.

It carries the largest weight. Weight is not importance, though: see the ablation under [How the Weights Were Fitted](#how-the-weights-were-fitted).

### Is the newest event explained?

**`last_event_matched`** is 1 when at least one symbol of the newest STM event is matched, and 0 otherwise. **`last_event_share`** is the share of that event's symbols that are matched.

A pattern that accounts for the older events and not for the one that just arrived describes where the sequence was. The newest event is the best evidence of where it is.

### How recent are the matches?

**`recency_07`** counts the matched symbols of the STM, each multiplied by `0.7^n`, where `n` is how many events back from the newest its event is. **`recency_09`** is the same with 0.9.

Two candidates can match the same number of symbols, one at the start of the STM and one at the end. The one that matches at the end is the better guide to what comes next, and this term says by how much.

### How much of the pattern, up to now, was observed?

**`evidence_to_end`** is the number of matches over the number of symbols in `past` and `present`.

The `evidence` field divides by the whole pattern, so a long pattern with most of its events still ahead scores low on it. That is the wrong direction for prediction: the unobserved future is what the pattern has to offer. `evidence_to_end` leaves the future out of the denominator and asks only how much of the pattern, up to the last matched event, the observation confirms.

It also carries position. The less of a pattern lies before the match, the higher it scores, so for a one-symbol STM a pattern that starts with the symbol ranks above one that holds it later, other things equal.

### How much had to be explained away?

**`tversky`** is `matches / (matches + 2 × missing + 2 × extras)`, a Tversky index with both penalties set to 2 (Tversky 1977). **`snr`** is KATO's signal-to-noise field, `(2 × matches - extras) / (2 × matches + extras)`.

Both fall with every symbol the pattern expected and did not get, or got and did not expect. `tversky` counts missing and extra symbols alike. `snr` counts extras only.

### Is the match in one piece?

**`fragmentation`** is the number of matched blocks minus one, and it carries the only negative weight. **`inverse_fragmentation`** is `1 / (fragmentation + 1)`.

A match in one block is a sequence observed in order. The same symbols scattered over five blocks are more likely to be a coincidence of vocabulary.

The two terms together give a penalty that is steep for the first break and close to linear afterwards.

### How often was the pattern learned?

**`log_frequency`** is the natural logarithm of the pattern's frequency.

A pattern learned 500 times is a better bet than one learned once, when both match equally well. The logarithm keeps frequency from drowning the match: the step from 1 learn to 2 is worth as much as the step from 100 to 200.

## How the Weights Were Fitted

The weights are constants. They were fitted once, offline, and are part of the code. Nothing is fitted when a node learns or predicts, and no random seed is involved anywhere.

1. **Objective.** For one STM, a softmax of the score over the candidates gives each candidate a probability. The weights maximise the probability that falls on the candidates whose next event is the event that actually followed. This is the listwise approach to learning to rank (Cao et al. 2007).
2. **Data.** 3,096 fitting queries drawn from 55 data sets of four kinds, each kind weighing the same: generated sequence libraries, system logs (HDFS), click streams (MSNBC) and text (WikiText-2). A query is the opening of a held-out sequence together with the event that followed it.
3. **Constraint.** The sign of every weight was fixed in advance: more matches, fewer missing symbols, fewer extras, fewer blocks and a higher frequency may never lower the score. The fit was offered 44 candidate terms under that constraint and left 11 of them non-zero.
4. **Method.** L-BFGS-B, started from all-zero weights, on the whole fitting set, with a small ridge penalty. There are no mini-batches and no random initialisation, so the fit gives the same weights every time it is run.
5. **Held-out check.** The fitted sum was then scored on queries the fit never saw; see [Measured Accuracy](#measured-accuracy).

Two results say how far the weights can be trusted on new data:

- **They are not tuned to the real data sets.** A sum fitted on the generated libraries alone is 0.31 points of accuracy behind this one on held-out queries of all four kinds.
- **Four terms carry most of the accuracy.** With the weight of `log_frequency` set to zero and the others left as they are, accuracy falls by 8.1 points on the mean of the four kinds. For `recency_07` the loss is 1.2 points, for `cosine_idf_present` 1.0 and for `last_event_matched` 0.7. Each of the other seven is worth 0.2 points or less. The largest weight belongs to `cosine_idf_present` and the largest effect to `log_frequency`: a weight says how far one unit of a term moves the score, not how much the term differs between the candidates of a request.

**The tradeoff.** A fitted weight has no derivation. `+2.755` for `last_event_matched` is the value that worked best on the fitting data, and that is all that can be said for it. Where every term of a score must follow from stated assumptions, rank by `good_odds` instead: it has one constant, a closed form in bits, and it is 1.4 points behind `potential` on the mean of the four kinds of data.

## Mathematical Properties

### Independence from the other candidates

`potential` reads the prediction's own fields and the node's counts. It reads nothing from the other candidates. The score of a prediction is therefore the same whatever else matched, in whatever order the candidates were found, and whatever `max_predictions` is set to.

### No penalty for the unobserved future

No term has the length of the whole pattern in a denominator. A pattern of 100 events matched on its first 5 is scored on those 5 and on what lies before them, not on the 95 it has yet to predict.

### Direction, for candidates of one STM

Among the candidates of one STM, a candidate with fewer extras, fewer missing symbols, fewer blocks or a higher frequency, and otherwise the same, never scores lower. The signs of the weights guarantee it.

### A limit: scores of different STMs

The property above compares candidates of the same STM. It does not extend to one pattern scored against two STMs. When the STM grows by an event that holds fewer symbols than the older events, the recency terms of a fully matching pattern can fall, and the score with them: the new event adds few matched symbols at full weight, and every older event is multiplied by 0.7 once more. This happens only with events of several symbols.

Compare `potential` values within a request, not across requests. `good_odds` is the score to compare across requests.

### Bounds

There are none. `recency_07` and `log_frequency` grow with the STM and with the frequency, and `fragmentation` can take the score below zero for a match broken into many blocks among many extras.

### Determinism

The eleven products are added in a fixed order, with plain floating-point addition. The same prediction and the same node counts give the same bits.

## Worked Example

A node has learned three patterns, one symbol per event:

| Pattern | Times learned |
|---|---|
| `login`, `browse`, `checkout` | 5 |
| `login`, `browse`, `logout` | 3 |
| `login`, `reset_password`, `logout` | 2 |

A session observes `login`, then `browse`. The first pattern matches both symbols. The third matches `login` and has to treat `browse` as an extra.

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

Reading the third column pair against the first:

- `browse` is held by two of the three patterns, `login` by all three. Missing `browse` on the pattern's side takes the cosine from 1.0 to 0.534.
- The newest event, `browse`, is unexplained: `last_event_matched` contributes nothing.
- The one match is an event back, so `recency_07` counts it at 0.7 and has nothing to count at full weight.
- `evidence_to_end` is 1.0 for both. The third pattern's `present` is `login` alone, and `login` was observed.

The second pattern, `login, browse, logout`, matches exactly as the first does. It differs in one term: `log_frequency` is `ln(3)` in place of `ln(5)`, and its `potential` is 16.850, lower by 0.347.

## From Potential to Probabilities

`potential` ranks. `future_potentials` turns the ranking into probabilities of the next event:

```
P(E | STM) = Σ e^potential over the candidates whose next event is E
             / Σ e^potential over every candidate
```

This is the softmax the weights were fitted under, summed over the candidates that agree on the next event. In the example the three weights, relative to the best, are 1, `e^-0.347` = 0.707 and `e^-9.091` = 0.0001, which gives `checkout` 0.586, `logout` 0.414 and `reset_password` 0.0001.

A candidate whose `future` is empty ends where the observation ends. It proposes no next event, and its share of the weight is returned as `ends_here`, the probability that nothing follows. With the probabilities of `future_potentials` it adds up to 1.

This matches how the weights were fitted. The softmax of the fitting objective ran over every candidate of a query, and a candidate with no future was one of the answers it could put weight on. Two things follow from the data the fit saw:

1. An event followed every fitting query, so a pattern that had ended was always a wrong answer there.
2. None of the eleven terms reads `future`, so the fit had no term with which to mark a pattern down for having ended. It could only do so through what ended patterns tend to have in common.

## Measured Accuracy

Next-event prediction at `recall_threshold` 0.1. A query is the opening of a held-out sequence, and an answer is right when the predicted next event equals the event that followed. The four kinds of data are generated sequence libraries (39 data sets), HDFS system logs (6), MSNBC click streams (2) and WikiText-2 text (10); the mean gives each kind the same weight.

| Share of queries answered right | Mean | Generated | HDFS logs | MSNBC clicks | WikiText-2 text |
|---|---|---|---|---|---|
| Top prediction that has a future, ranked by `potential` | 0.631 | 0.855 | 0.876 | 0.673 | 0.120 |
| The same, ranked by `good_odds` | 0.617 | 0.839 | 0.877 | 0.666 | 0.085 |
| Top entry of `future_potentials` | 0.647 | 0.856 | 0.860 | 0.690 | 0.183 |

These figures are from 117,200 test queries that were read once, after the formulas were fixed.

1. **`future_potentials` is the better read-out.** Pooling the candidates that agree on the next event gains 1.6 points on the mean, and 6 points on text.
2. **Text is hard for a single stored pattern.** On WikiText-2 the top prediction is right 12% of the time and the top entry of `future_potentials` 18%. A plain count of the stored contexts that end as the STM does reaches 17.8% on the same queries.
3. **Short STMs are the weak spot.** With an STM of two events, the top prediction that has a future is right 53% of the time on generated data, where a predictor that knows the generating process reaches 71%.

The accuracy of every metric as a ranking key is tabulated in the [Prediction Object Reference](../reference/prediction-object.md#measured-accuracy).

## Alternative Ranking Functions

`rank_sort_algo` accepts every numeric metric of the prediction object. Predictions are ranked highest value first.

### Good-Odds Ranking

```python
rank_sort_algo = "good_odds"
```

**When to use**: Every term of the score must have a stated derivation, or scores have to be compared across requests. `bayesian_posterior` gives the same order.

### Likelihood Ranking

```python
rank_sort_algo = "bayesian_likelihood"
```

**When to use**: Match strength alone, leaving out how often a pattern was learned.

### Frequency Ranking

```python
rank_sort_algo = "frequency"
```

**When to use**: The most often learned candidates first. `bayesian_prior` gives the same order.

### Similarity Ranking

```python
rank_sort_algo = "similarity"
```

**When to use**: Structural pattern matching, where the observation covers most of each pattern.

### Re-ranking in the Application

`potential` is not configurable: the weights are constants. An application that needs another tradeoff can sort the returned predictions by its own function of their fields.

```python
def utility_first(prediction):
    """Rank by learned utility, then by how well the pattern explains the STM."""
    return (prediction["emotives"].get("utility", 0.0), prediction["good_odds"])

predictions.sort(key=utility_first, reverse=True)
```

Set `max_predictions` high enough that the predictions to be re-ranked are all returned.

## Comparison to Other Approaches

### vs. Simple Similarity

`similarity` divides the common subsequence by the lengths of the pattern and the STM together. It falls as the unobserved part of a pattern grows, so it favours short patterns that the STM nearly completes, and those are the patterns with the least left to predict. `potential` scores the match on the part of the pattern that has been reached.

### vs. Frequency-Only

Frequency alone ignores the observation beyond the recall threshold. It works where a few patterns account for most of what a node has learned, and fails where patterns were learned about equally often. `potential` takes frequency as one term of eleven, on a logarithmic scale.

### vs. Good-Odds

`good_odds` is derived: a prior, plus the bits each matched symbol earns, minus a fixed cost per missing or extra symbol. `potential` is fitted: it reaches a higher accuracy by weighing things `good_odds` has no term for, such as recency and whether the newest event is matched. One has a meaning in bits, the other is the better ranker.

### vs. a Neural Network's Confidence

A network's softmax output is a function of all its weights, and the path from input to score cannot be read off. `potential` is a sum of eleven named terms. For any prediction the terms can be printed, multiplied by the published weights and added by hand, and the same inputs give the same score on every run.

## References

- Z. Cao, T. Qin, T.-Y. Liu, M.-F. Tsai and H. Li, "Learning to Rank: From Pairwise Approach to Listwise Approach", *Proceedings of the 24th International Conference on Machine Learning*, 2007 ([doi:10.1145/1273496.1273513](https://doi.org/10.1145/1273496.1273513)). The objective the weights were fitted under.
- A. Tversky, "Features of Similarity", *Psychological Review* 84(4), 1977 ([doi:10.1037/0033-295X.84.4.327](https://doi.org/10.1037/0033-295X.84.4.327)). The index behind the `tversky` term.
- K. Spärck Jones, "A Statistical Interpretation of Term Specificity and Its Application in Retrieval", *Journal of Documentation* 28(1), 1972 ([doi:10.1108/eb026526](https://doi.org/10.1108/eb026526)). Inverse document frequency.

## Related Documentation

- [Prediction Object Reference](../reference/prediction-object.md) - Every field, its formula and its measured accuracy
- [Bayesian Framework](bayesian-framework-for-kato.md) - `good_odds` and the Bayesian fields
- [Predictive Information](predictive-information.md) - Information the STM carries about the next event
- [Information Theory](information-theory.md) - Theoretical foundations
- [Core Concepts](core-concepts.md) - KATO fundamentals
