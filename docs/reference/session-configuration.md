# Session Configuration Reference

Complete reference for session-specific configuration parameters.

## Overview

Session configuration allows per-session customization of KATO's behavior. Each session can have different settings while sharing learned patterns (LTM) via `node_id`.

**Configuration Method**: See [API - Configuration](api/configuration.md)

## Learning Configuration

| Parameter | Type | Range | Default | Description |
|-----------|------|-------|---------|-------------|
| `max_pattern_length` | integer | 0+ | 0 | Auto-learn when STM reaches this length (0=manual only) |
| `persistence` | integer | 1-100 | 20 | Emotive rolling window size |
| `recall_threshold` | float | 0.0-1.0 | 0.1 | Pattern matching sensitivity threshold |
| `stm_mode` | string | CLEAR\|ROLLING | CLEAR | STM behavior after auto-learning |

## Processing Configuration

| Parameter | Type | Range | Default | Description |
|-----------|------|-------|---------|-------------|
| `indexer_type` | string | VI\|LSH\|ANNOY\|FAISS | VI | Vector indexer type |
| `max_predictions` | integer | 1-10000 | 10000 | Maximum predictions to return |
| `sort_symbols` | boolean | true\|false | true | Sort symbols alphabetically within events |
| `process_predictions` | boolean | true\|false | true | Enable prediction processing |
| `use_token_matching` | boolean | true\|false | true | Token-level (true) vs character-level (false) matching |

## Filter Pipeline Configuration

### Pipeline Specification

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `filter_pipeline` | array[string] | ["length", "jaccard", "bloom", "minhash", "rapidfuzz"] | Ordered list of filter stages |

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
| `minhash_bands` | integer | 1-100 | 20 | Number of LSH bands |
| `minhash_rows` | integer | 1-20 | 5 | Rows per LSH band |
| `minhash_num_hashes` | integer | 10-256 | 100 | Total MinHash signature size |

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
  "jaccard_threshold": 0.8
}
```

**Use Cases**: Security, exact matching, high-confidence predictions

### Exploratory Mode

```json
{
  "recall_threshold": 0.1,
  "max_predictions": 1000,
  "use_token_matching": false,
  "sort_symbols": false
}
```

**Use Cases**: Pattern discovery, research, large-scale analysis

### Auto-Learning Mode

```json
{
  "max_pattern_length": 10,
  "stm_mode": "ROLLING",
  "recall_threshold": 0.3,
  "persistence": 20
}
```

**Use Cases**: Real-time learning, streaming data, continuous adaptation

### Document Analysis Mode

```json
{
  "use_token_matching": false,
  "sort_symbols": false,
  "recall_threshold": 0.5,
  "max_predictions": 100
}
```

**Use Cases**: Document similarity, NLP, fuzzy text matching

## See Also

- [Configuration API](api/configuration.md) - How to update configuration
- [Environment Variables](configuration-vars.md) - System-level defaults
- [Pattern Matching](../research/pattern-matching.md) - Matching algorithms

---

**Last Updated**: November 2025
**KATO Version**: 3.0+
