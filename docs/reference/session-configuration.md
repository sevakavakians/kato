# Session Configuration Reference

Complete reference for session-specific configuration parameters.

## Overview

Session configuration allows per-session customization of KATO's behavior. Each session can have different settings while sharing learned patterns (LTM) via `node_id`.

**Configuration Method**: See [API - Configuration](api/configuration.md)

## Learning Configuration

| Parameter | Type | Range | Default | Description |
|-----------|------|-------|---------|-------------|
| `max_pattern_length` | integer | 0+ | 0 | Auto-learn when STM reaches this length (0=manual only) |
| `persistence` | integer | 1-100 | 5 | Emotive rolling window size |
| `recall_threshold` | float | 0.0-1.0 | 0.1 | Pattern matching sensitivity threshold |
| `stm_mode` | string | CLEAR\|ROLLING | CLEAR | STM behavior after auto-learning |

## Processing Configuration

| Parameter | Type | Range | Default | Description |
|-----------|------|-------|---------|-------------|
| `indexer_type` | string | VI\|LSH\|ANNOY\|FAISS | VI | Vector indexer algorithm |
| `max_predictions` | integer | 1-10000 | 100 | Maximum predictions to return |
| `sort_symbols` | boolean | true\|false | true | Sort symbols alphabetically within events |
| `process_predictions` | boolean | true\|false | true | Enable prediction processing |
| `use_token_matching` | boolean | true\|false | true | Token-level (true) vs character-level (false) matching |
| `rank_sort_algo` | string | See below | potential | Prediction ranking metric |

### Prediction Ranking

The `rank_sort_algo` parameter controls how predictions are sorted and prioritized:

| Value | Description | Use Case |
|-------|-------------|----------|
| `potential` | Information-theoretic value (default) | General purpose, balanced results |
| `similarity` | Pattern match score | Prioritize exact matches |
| `evidence` | Observation count | Popular patterns first |
| `confidence` | Bayesian confidence | Risk-averse applications |
| `snr` | Signal-to-noise ratio | High-quality signals |
| `fragmentation` | Pattern fragmentation score | Cohesive patterns |
| `frequency` | Pattern frequency | Common patterns first |
| `normalized_entropy` | Entropy-normalized score | Information density |
| `global_normalized_entropy` | Global entropy normalization | Cross-pattern comparison |
| `itfdf_similarity` | TF-IDF-inspired similarity | Text-like patterns |
| `confluence` | Pattern confluence score | Convergent patterns |
| `predictive_information` | Predictive information content | Maximum information gain |

**Example:**
```json
{
  "rank_sort_algo": "similarity",
  "max_predictions": 10
}
```

## Filter Pipeline Configuration

### Pipeline Specification

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `filter_pipeline` | array[string] | [] | Ordered list of filter stages (empty = no pre-filtering) |

**Valid Filters**: `length`, `jaccard`, `bloom`, `minhash`, `rapidfuzz`

### Length Filter

| Parameter | Type | Range | Default | Description |
|-----------|------|-------|---------|-------------|
| `length_min_ratio` | float | 0.0-1.0 | 0.5 | Min pattern length as ratio of STM length |
| `length_max_ratio` | float | 1.0+ | 2.0 | Max pattern length as ratio of STM length |

### Jaccard Filter

| Parameter | Type | Range | Default | Description |
|-----------|------|-------|---------|-------------|
| `jaccard_threshold` | float | 0.0-1.0 | 0.3 | Minimum Jaccard similarity |
| `jaccard_min_overlap` | integer | 1+ | 2 | Minimum absolute token overlap count |

### MinHash/LSH Filter

| Parameter | Type | Range | Default | Description |
|-----------|------|-------|---------|-------------|
| `minhash_threshold` | float | 0.0-1.0 | 0.7 | Estimated Jaccard threshold for LSH |
| `minhash_bands` | integer | 1-100 | 20 | Number of LSH bands (higher = faster, less accurate) |
| `minhash_rows` | integer | 1-20 | 5 | Rows per LSH band (bands × rows = num_hashes) |
| `minhash_num_hashes` | integer | 10-256 | 100 | Total MinHash signature size (must equal bands × rows) |

**Tuning Guide:**
- **More bands**: Faster queries, more false negatives
- **More rows**: Higher accuracy, slower queries
- **Total hashes = bands × rows**: Common values: 100 (20×5), 128 (16×8), 200 (20×10)

### Bloom Filter

| Parameter | Type | Range | Default | Description |
|-----------|------|-------|---------|-------------|
| `bloom_false_positive_rate` | float | 0.0001-0.1 | 0.01 | False positive rate (1%) |

### Pipeline Control

| Parameter | Type | Range | Default | Description |
|-----------|------|-------|---------|-------------|
| `max_candidates_per_stage` | integer | 100+ | 100000 | Safety limit per filter stage |
| `enable_filter_metrics` | boolean | true\|false | true | Log filter timing and counts |

## Configuration Presets

### High-Precision Mode

```json
{
  "recall_threshold": 0.9,
  "use_token_matching": true,
  "sort_symbols": true,
  "max_predictions": 10,
  "rank_sort_algo": "similarity",
  "jaccard_threshold": 0.8,
  "filter_pipeline": ["length", "jaccard", "rapidfuzz"]
}
```

**Use Cases**: Security, exact matching, high-confidence predictions

### Exploratory Mode

```json
{
  "recall_threshold": 0.1,
  "max_predictions": 1000,
  "use_token_matching": false,
  "sort_symbols": false,
  "rank_sort_algo": "potential",
  "filter_pipeline": ["length", "rapidfuzz"]
}
```

**Use Cases**: Pattern discovery, research, large-scale analysis

### Auto-Learning Mode

```json
{
  "max_pattern_length": 10,
  "stm_mode": "ROLLING",
  "recall_threshold": 0.3,
  "persistence": 5,
  "rank_sort_algo": "evidence",
  "max_predictions": 100
}
```

**Use Cases**: Real-time learning, streaming data, continuous adaptation

### Document Analysis Mode

```json
{
  "use_token_matching": false,
  "sort_symbols": false,
  "recall_threshold": 0.5,
  "max_predictions": 100,
  "rank_sort_algo": "potential"
}
```

**Use Cases**: Document similarity, NLP, fuzzy text matching

### Large-Scale Mode

```json
{
  "indexer_type": "LSH",
  "filter_pipeline": ["minhash", "bloom", "rapidfuzz"],
  "minhash_threshold": 0.7,
  "minhash_bands": 20,
  "minhash_rows": 5,
  "recall_threshold": 0.3,
  "max_predictions": 100,
  "rank_sort_algo": "potential"
}
```

**Use Cases**: Millions of patterns, scalable similarity search, high-throughput systems

## See Also

- [Configuration API](api/configuration.md) - How to update configuration
- [Environment Variables](configuration-vars.md) - System-level defaults
- [Pattern Matching](../research/pattern-matching.md) - Matching algorithms

---

**Last Updated**: November 2025
**KATO Version**: 3.0+
