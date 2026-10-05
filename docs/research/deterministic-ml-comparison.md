# Deterministic Machine Learning: KATO Compared

"Deterministic" means different things in machine learning. This document separates
those meanings and shows how KATO meets each one. It then compares KATO with the major
ML families, including the classical methods that are just as deterministic. It also
says plainly where KATO's end-to-end determinism has limits.

## Three Kinds of Determinism

| Kind | Question | KATO |
|------|----------|------|
| **Algorithmic** | Does the method use randomness: initialization, sampling, dropout, shuffling? | None. Learning is hashing and counting. Prediction is exact sequence alignment followed by closed-form metrics. |
| **Order** | Does the order of the training data change the final model? | Mostly no. The knowledge base is built from operations whose result does not depend on order (see below). |
| **Implementation** | Do the same inputs produce the same bytes across runs and workers? | Engineered for it on the same build and hardware. Ranked predictions are byte-identical across runs and workers, with the limits listed [below](#known-limits-on-end-to-end-determinism). |

Determinism in all three senses is **not rare**, and it is not unique to KATO.

- **Methods that typically meet none or one by default:** deep learning trained with
  SGD, LLM inference, and randomized ensembles. They can be made reproducible only by
  pinning seeds, kernels, batch shapes, and thread counts, usually at a speed cost.
- **Methods that can meet all three:** many classical, interpretable methods.
  Examples are linear and logistic regression with deterministic solvers, scorecards,
  rules engines, single decision trees, Naive Bayes, exact k-NN, and n-gram models.

What distinguishes KATO is what it combines with determinism (see
[Where KATO Is Actually Different](#where-kato-is-actually-different)), not
determinism itself.

### How Implementation Determinism Is Enforced

- **Total-order ranking.** Predictions are ranked on `(metric, name)`, so ties never
  depend on the order results arrive in (`kato/representations/prediction.py`,
  `rank_predictions`). The same ordering drives the top-K pre-prune when candidates
  exceed `max_predictions × 3`.
- **Fixed summation order.** Floating-point addition is not associative, so entropy
  sums iterate in sorted symbol order (`kato/informatics/metrics.py`).
- **Exact alignment.** Matching uses a vendored difflib
  (`kato/informatics/extractor.py`) without autojunk / "popular element" pruning. The
  same pair of sequences always produces the same alignment.
- **Recall-safe pruning.** Candidates are pruned in ClickHouse using integer upper
  bounds on LCS similarity (`kato/filters/recall_bounds.py`). The bounds are
  deliberately weakened so they can never be stricter than the floating-point scorer.
  Pruning makes queries faster but cannot change which patterns are ranked.
- **Read-your-writes.** `ensure_visible` (`kato/storage/clickhouse_writer.py`) drains
  ClickHouse async inserts before a prediction, so a just-learned pattern is never
  missed.
- **Content addressing.** A pattern's name is the SHA1 of its event data, so identity
  never depends on insertion order, row IDs, or timestamps.

## Why Training Order Mostly Does Not Matter

When a pattern is learned:

- **Its name is a content hash.** The same sequence always lands on the same row, so
  there are never duplicates.
- **Frequency is an atomic increment.** Counting is commutative.
- **Symbol statistics and affinity are sums.** Also commutative.
- **Metadata merges by set union.** Commutative and idempotent.

Once a set of patterns has been learned, the resulting knowledge base is the same
whatever order those learns happened in. This is close to the merge property of a
CRDT. It also makes **exact unlearning** possible: purging a pattern subtracts exactly
what learning it added. The reversal is atomic and guarded by invariant checks, and it
leaves the statistics as if the pattern had never been seen.

Other count-based models share this property: Naive Bayes, n-gram models, supervised
HMMs, and linear regression through its sufficient statistics.

**Order-dependent exceptions:**

- **Emotives** are kept in a rolling window of the most recent `persistence` entries.
  Which values survive depends on learning order.
- **Retirement** is a deliberate state change. A retired pattern rejects re-learning.
- **What gets learned** depends on the order of observations in short-term memory, by
  design. Sequence is the signal.

## Comparison With Other ML Families

**Legend:**

| Mark | Meaning |
|------|---------|
| ✅ | Holds by default |
| ⚙️ | Holds once configured (pinned seed, solver, thread count, or tie-break rule) |
| ⚠️ | Holds partially, or only in some variants |
| ❌ | Does not hold |
| n/a | Does not apply |

**Column definitions:**

- **Order-independent** means "in exact arithmetic". Batch methods that sum over rows
  can still differ in the last bits when row order changes. That is captured in the
  **Byte-reproducible** column.
- **Exact unlearning** means removing one training example's influence without
  retraining.

| Family | No randomness | Order-independent | Byte-reproducible | Exact unlearning | Explanation |
|--------|---------------|-------------------|-------------------|------------------|-------------|
| **KATO** | ✅ | ✅ Mostly (emotives window excepted) | ✅ Same build and hardware ([limits](#known-limits-on-end-to-end-determinism)) | ✅ Subtract counts, drop row | Per prediction: past / present / future / missing / extras plus the source pattern |
| **Deep nets (SGD)** | ❌ Random init, dropout, shuffling (⚙️ seedable) | ❌ Path-dependent | ⚙️ Deterministic kernels, fixed batch shape, at a speed cost | ❌ Approximate; an open research area | Post-hoc (SHAP, saliency) |
| **LLM inference** | ❌ Sampling (⚙️ greedy decoding) | n/a | ❌ Batch-dependent kernels; ⚙️ only with batch-invariant kernels | ❌ | Generated rationales, not traces |
| **Random forests** | ⚙️ Bootstrap and feature subsampling are seedable | ❌ Bootstrap draws are tied to row order | ⚙️ | ❌ Retrain | Partial (importances) |
| **Gradient boosting** | ✅ Without subsampling; ⚙️ with it | ✅ Without subsampling (ties aside) | ⚙️ Fixed thread count; multithreaded histogram sums can drift | ❌ Retrain | Partial |
| **Logistic regression / linear-chain CRF** | ✅ L-BFGS, Newton, IRLS; ⚙️ liblinear, SAG/SAGA and SGD shuffle | ✅ Batch fit (unique optimum with L2); ❌ online SGD | ⚙️ Fixed row order, pinned BLAS threads | ❌ Refit (warm start is cheap) | ✅ Coefficients |
| **OLS / ridge regression** | ✅ | ✅ Sufficient statistics XᵀX, Xᵀy are sums | ⚙️ Pinned BLAS threads | ✅ Downdate the sufficient statistics (up to rounding) | ✅ Coefficients |
| **GAM / EBM** | ✅ Spline GAMs; ⚙️ EBM bagging is seedable | ✅ / ⚙️ | ⚙️ | ❌ Refit | ✅ Shape functions |
| **Scorecards** | ✅ | n/a Points are fixed once built | ✅ | n/a Edited by hand | ✅ Points and reason codes |
| **Rules engines** | ✅ | ⚠️ Recency-based conflict resolution depends on fact order | ✅ | n/a Delete or edit the rule | ✅ Fired rules |
| **Single decision tree (CART)** | ✅ The algorithm; ⚙️ scikit-learn permutes features at each split, so `random_state` decides ties | ✅ Ties aside | ✅ | ❌ Retrain | ✅ Decision path |
| **Naive Bayes / fixed-structure Bayes net** | ✅ | ✅ Counts | ✅ | ✅ Decrement counts | ⚠️ Per-feature likelihoods |
| **Exact k-NN / exemplar models** | ✅ | ✅ Store the points | ⚙️ Needs an explicit tie-break rule | ✅ Delete the point | ✅ The neighbours |
| **Approximate k-NN (HNSW, IVF)** | ⚠️ Index construction may use randomness | ❌ Index structure depends on insertion order | ❌ | ⚠️ Deletes are often tombstones | ✅ The neighbours |
| **n-gram / VOMM (PPM, PST, CTW)** | ✅ | ✅ Counts | ✅ | ✅ Decrement counts | ⚠️ Context → next-symbol distribution |
| **HMM, supervised (counting)** | ✅ | ✅ Counts | ✅ | ✅ Decrement counts | ⚠️ State posteriors |
| **HMM, unsupervised (Baum-Welch)** | ⚙️ Seeded initialization; local optima depend on it | ✅ Batch EM | ⚙️ | ❌ Retrain | ⚠️ State posteriors |
| **Sequence alignment (Smith-Waterman / BLAST)** | ✅ Smith-Waterman; ⚠️ BLAST seeding is heuristic | n/a | ✅ | n/a | ✅ The alignment |
| **Rule learners (RIPPER) / ILP** | ⚙️ RIPPER's grow/prune split is seeded; ILP search is usually deterministic | ❌ Covering order matters | ✅ | ❌ Relearn | ✅ Rules |
| **HTM (hierarchical temporal memory)** | ⚙️ Random synapse initialization is seedable | ❌ Online, path-dependent | ⚙️ | ❌ | ⚠️ |
| **Case-based reasoning** | ✅ | ✅ | ⚙️ Implementation-dependent | ✅ Delete the case | ✅ The retrieved case |

## Where KATO Is Actually Different

Because many methods are deterministic, the useful comparison is among deterministic
methods, on the properties KATO combines with determinism:

- **Incremental:** learns from a single observation, with no batch refit.
- **Subtractive unlearning:** forgets one example by subtraction, with no retraining.
- **Sequence-native:** matches ordered sequences, tolerating gaps and extra symbols.
- **Instance explanation:** justifies a prediction by pointing to specific stored
  observations.
- **Missing / unexpected:** the output names what was expected but not observed, and
  what was observed but not expected.

| Method | Incremental | Subtractive unlearning | Sequence-native | Instance explanation | Missing / unexpected |
|--------|-------------|------------------------|-----------------|----------------------|----------------------|
| **KATO** | ✅ | ✅ | ✅ | ✅ | ✅ |
| Logistic regression | ❌ Batch (online SGD gives up order-independence) | ❌ | ❌ | ❌ Coefficients | ❌ |
| OLS / ridge | ✅ Rank-one update | ✅ Downdate | ❌ | ❌ Coefficients | ❌ |
| Scorecard | ❌ Built offline | n/a | ❌ | ⚠️ Reason codes | ❌ |
| Rules engine | n/a Authored | ✅ Delete the rule | ⚠️ Complex-event-processing engines | ✅ Fired rules | ❌ |
| Single decision tree | ❌ Batch (incremental Hoeffding trees depend on order) | ❌ | ❌ | ⚠️ Path, not instances | ❌ |
| Naive Bayes | ✅ | ✅ | ❌ Bag of features | ⚠️ Likelihoods | ❌ |
| Exact k-NN with alignment / DTW distance | ✅ | ✅ | ✅ | ✅ | ⚠️ Derivable from the alignment, not standard output |
| n-gram / VOMM | ✅ | ✅ | ⚠️ Contiguous suffix context, next symbol only | ⚠️ Context counts | ❌ |

**Closest relatives.** Alignment-based k-NN and variable-order Markov models come
closest. A researcher could approximate KATO's core as nearest-neighbour retrieval
under an LCS distance, weighted by occurrence counts. KATO's contribution is not a new
class of learner. It brings together:

- **Event structure:** unordered symbols within an event, ordered events.
- **Partial matching anywhere in short-term memory.** It returns the complete stored
  future, not just the next symbol.
- **Structured output:** past / present / future / missing / extras for every
  prediction.
- **Ensemble metrics:** frequency-weighted, information-theoretic metrics across all
  candidates.
- **Emotive and metadata accumulation.**
- **A serving layer** (ClickHouse, Redis, Qdrant, stateless processors) engineered so
  that scale and concurrency do not break reproducibility.

## Trade-offs

Determinism and traceability have costs.

- **Narrow generalization.** KATO matches only symbols it has observed. Unseen tokens
  match only through fuzzy token matching or vector-neighbour symbols. Neural networks
  and linear models generalize across features; KATO does not. That is also why it
  cannot hallucinate.
- **Symbol brittleness.** `cat` and `cats` are unrelated unless fuzzy token matching is
  enabled. Near-identical embeddings get different `VCTR|` names unless their
  neighbour symbols overlap.
- **Memory grows with the data.** Like k-NN, storage grows with the number of distinct
  patterns, not a fixed parameter budget. With the default (empty) filter pipeline,
  prediction cost grows with corpus size.
- **Deterministic is not the same as stable.** Learning one new pattern changes the
  ensemble normalizations (pattern probabilities, global entropy, predictive
  information), so rankings can reorder. The result is reproducible but not monotone.
- **Some settings change pattern identity.** Changing `vector_search_limit` or the
  symbol sort mode changes pattern hashes. They cannot be changed in place on an
  existing knowledge base without breaking comparability with what is already stored.

## Known Limits on End-to-End Determinism

The precise claim is this:

- Learning and matching use no randomness.
- Given the same knowledge base, the same short-term memory and the same
  configuration, on the same build and hardware, KATO returns the same ranked
  predictions.

The items below are where guarantees beyond that do not hold, or have not been shown.

### Determinism limits

- **Ensemble fields follow candidate arrival order.**
  - **Cause:** candidate queries have no `ORDER BY` (`kato/filters/recall_bounds.py`,
    and the single-symbol query in `kato/workers/pattern_processor.py`). The total-order
    pre-prune runs only when candidates exceed `max_predictions × 3`. Below that, the
    ensemble pass in `kato/informatics/predictive_information.py` sees candidates in
    ClickHouse arrival order.
  - **Effect 1:** ties in `future_potentials` appear in arrival order.
  - **Effect 2:** when three or more patterns share a future, `aggregate_potential`,
    and the `predictive_information` derived from it, are floating-point sums whose
    last bits can vary with that order.
  - **Not affected:** the ranked predictions and their `potential`. Neither depends on
    these values.
  - **Status:** identified by reading the code; not yet reproduced.
- **Cross-hardware reproducibility is not shown.** `itfdf_similarity` uses BLAS
  matrix-vector products and norms, and the Bayesian posterior uses `np.dot`. Their
  reduction order can differ between CPU architectures. Values can then differ in the
  last bits on different hardware, and a near-tie in `potential` could swap order.
  Byte-identical output has been shown across runs and workers on the same build and
  hardware.
- **Approximate vector search: unverified.** Vector observations become symbols partly
  through nearest-neighbour lookups in Qdrant, which uses an approximate HNSW index.
  HNSW graph construction can depend on insertion order. Background segment
  optimization can also change the index over time. If neighbour results differ, the
  `VCTR|` symbols differ, and so do the pattern hashes. This affects what is
  *learned*, not only what is predicted. It has not been confirmed for KATO's
  configuration. Two ways to check:
  - compare against Qdrant's exact search;
  - run a determinism test that learns the same vector stream in two orders.

### Not determinism, but worth knowing

- **Emotives window.** The rolling emotives window depends on learning order.
  Frequencies, symbol statistics, and metadata do not. Replaying the same sequence
  still gives the same result.
- **Lossy vector names.** A vector's name is the SHA1 of `str(np.array)`
  (`kato/representations/vector_object.py`). NumPy's string form rounds values and
  truncates long arrays. The name is deterministic, but two different high-dimensional
  vectors can collide on the same name. This is a correctness concern, not a
  determinism one.

## Bottom Line

Determinism in all three senses is common among classical, interpretable methods.
Logistic regression with a deterministic solver, a single decision tree, Naive Bayes,
a scorecard, or a rules engine can all be fully reproducible. It is rare in deep
learning, LLM inference, and randomized ensembles.

KATO's distinction is the combination it pairs with determinism:

- incremental, one-shot learning;
- exact unlearning by subtraction;
- native sequence matching that tolerates gaps;
- explanations that point to stored observations;
- predictions that state what is missing and what is unexpected.

It also has a serving layer engineered to keep those results reproducible at scale.
Its closest relatives are alignment-based k-NN and variable-order Markov models. The
price, shared with them, is generalization: KATO predicts from what it has observed,
and does not interpolate beyond it.

## Related Documentation

- [Core Concepts](core-concepts.md) - Theoretical foundations
- [Pattern Matching](pattern-matching.md) - Similarity and alignment algorithms
- [Potential Function](potential-function.md) - Prediction ranking
- [Predictive Information](predictive-information.md) - Ensemble metrics and future potentials
