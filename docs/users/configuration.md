# Configuration Guide

User guide for configuring KATO behavior and performance.

## Configuration Levels

KATO supports configuration at three levels:

1. **Global (Environment Variables)**: Affects all sessions
2. **Session (Per-Session Config)**: Overrides global for specific session
3. **Runtime (API Parameters)**: Overrides session for specific operations

### Priority Order

```
Runtime Parameters > Session Config > Environment Variables > Defaults
```

## Session Configuration

### Creating Session with Configuration

```bash
curl -X POST http://localhost:8000/sessions \
  -H "Content-Type: application/json" \
  -d '{
    "node_id": "my_app",
    "config": {
      "recall_threshold": 0.3,
      "max_predictions": 50,
      "sort_symbols": true,
      "use_token_matching": true,
      "rank_sort_algo": "potential"
    }
  }'
```

### Updating Session Configuration

```bash
# Update configuration for existing session
curl -X PUT http://localhost:8000/sessions/{session_id}/config \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "recall_threshold": 0.5,
      "max_predictions": 100
    }
  }'
```

### Viewing Current Configuration

```bash
# Get session details including configuration
curl http://localhost:8000/sessions/{session_id}
```

## Core Configuration Options

### Pattern Matching

#### recall_threshold

Minimum similarity score for pattern matching (0.0 - 1.0).

```json
{
  "recall_threshold": 0.3
}
```

**Values**:
- **0.0**: Match everything (not recommended)
- **0.1**: Very permissive (default) - fuzzy matching
- **0.3**: Balanced - partial matches allowed
- **0.5**: Strict - requires majority overlap
- **0.9**: Very strict - near-exact matches only
- **1.0**: Exact matches only

**Use Cases**:
- **Low (0.1-0.3)**: Chatbots, exploratory search, loose associations
- **Medium (0.3-0.6)**: Recommendations, error diagnosis
- **High (0.7-1.0)**: Exact recall, structured workflows

**Example - Strict Matching**:
```bash
# Create session requiring 70% similarity
curl -X POST http://localhost:8000/sessions \
  -d '{
    "node_id": "strict_workflow",
    "config": {"recall_threshold": 0.7}
  }'
```

#### use_token_matching

Token-level (true) vs character-level (false) matching.

```json
{
  "use_token_matching": true
}
```

**Token-Level (Default)**:
- Treats each string as atomic unit
- 9x faster than character-level
- Use for: tokenized text, discrete symbols, structured data

**Character-Level**:
- Fuzzy string matching within strings
- 75x faster than legacy difflib
- Use for: document chunks, raw text (rare cases)

**Example - Character Matching**:
```bash
# For fuzzy text matching
curl -X POST http://localhost:8000/sessions \
  -d '{
    "node_id": "fuzzy_text",
    "config": {"use_token_matching": false}
  }'
```

**Recommendation**: Always use `true` (token-level) unless matching raw document text.

### Prediction Control

#### max_predictions

Maximum number of predictions to return (1-10000).

```json
{
  "max_predictions": 100
}
```

**Values**:
- **10-50**: Fast response, top predictions only
- **100**: Balanced (default)
- **500+**: Comprehensive results, slower response
- **10000**: Maximum allowed

**Performance Impact**:
- Higher values = slower response times
- Minimal impact below 100
- Linear scaling above 100

**Example - Limited Predictions**:
```bash
# Return top 10 predictions only
curl -X POST http://localhost:8000/sessions \
  -d '{
    "node_id": "fast_api",
    "config": {"max_predictions": 10}
  }'
```

#### rank_sort_algo

Metric for ranking predictions.

```json
{
  "rank_sort_algo": "potential"
}
```

**Options**:
- **potential** (default): Information-theoretic value (recommended)
- **similarity**: Pattern match score
- **evidence**: Observation count
- **confidence**: Bayesian confidence
- **snr**: Signal-to-noise ratio

**Use Cases**:
- **potential**: General purpose (default)
- **similarity**: Exact match priority
- **evidence**: Popular patterns first
- **confidence**: Risk-averse applications

**Example - Similarity Ranking**:
```bash
# Rank by match quality
curl -X POST http://localhost:8000/sessions \
  -d '{
    "node_id": "exact_match",
    "config": {"rank_sort_algo": "similarity"}
  }'
```

### Symbol Processing

#### sort_symbols

Sort symbols alphabetically within events.

```json
{
  "sort_symbols": true
}
```

**true (Default)**:
- `["zebra", "apple"]` → stored as `["apple", "zebra"]`
- Order-independent matching
- Use for: sets, tags, unordered data

**false**:
- `["zebra", "apple"]` → stored as `["zebra", "apple"]`
- Position matters
- Use for: sequences, ordered lists

**Example - Preserve Order**:
```bash
# Don't sort - order matters
curl -X POST http://localhost:8000/sessions \
  -d '{
    "node_id": "sequence_data",
    "config": {"sort_symbols": false}
  }'
```

**Important**: Changing this mid-session causes inconsistent matching!

### Vector Indexing

#### indexer_type

Algorithm for vector similarity search.

```json
{
  "indexer_type": "VI"
}
```

**Options**:
- **VI** (default): Vector Index - Fast, accurate, general purpose
- **LSH**: Locality-Sensitive Hashing - Approximate, scalable for millions of vectors
- **ANNOY**: Spotify's Approximate Nearest Neighbors - High-dimensional embeddings
- **FAISS**: Facebook's vector search library - GPU-accelerated search

**Use Cases**:
- **VI**: General purpose (recommended for most applications)
- **LSH**: Large-scale vector search with millions of patterns
- **ANNOY**: High-dimensional embeddings (768+ dimensions)
- **FAISS**: GPU-accelerated similarity search

**Example - LSH Indexing**:
```bash
# For large-scale vector search
curl -X POST http://localhost:8000/sessions \
  -d '{
    "node_id": "vector_search",
    "config": {"indexer_type": "LSH"}
  }'
```

**Performance Characteristics**:
| Type | Speed | Accuracy | Scale | GPU |
|------|-------|----------|-------|-----|
| VI | Fast | Exact | 10K-100K | No |
| LSH | Very Fast | ~95% | 1M+ | No |
| ANNOY | Fast | ~99% | 100K-1M | No |
| FAISS | Fastest | Configurable | 10M+ | Yes |

**Recommendation**: Use default `VI` unless handling millions of vector embeddings.

## Session Management

### session_ttl

Session expiration time in seconds.

**Global Configuration** (Environment Variable):
```bash
# .env file
SESSION_TTL=7200  # 2 hours
```

**Per-Session** (API parameter):
```bash
curl -X POST http://localhost:8000/sessions \
  -d '{
    "node_id": "long_session",
    "ttl": 7200
  }'
```

**Values**:
- **60-3600**: Short sessions (1 min - 1 hour)
- **3600**: Default (1 hour)
- **7200-86400**: Long sessions (2-24 hours)

### session_auto_extend

Automatically extend TTL on each access (sliding window).

**Global Configuration**:
```bash
# .env file
SESSION_AUTO_EXTEND=true
```

**Behavior**:
- **true** (default): Each API call resets TTL
- **false**: Absolute timeout from creation

**Example - Absolute Timeout**:
```bash
# Session expires exactly 1 hour after creation
# Environment: SESSION_AUTO_EXTEND=false

curl -X POST http://localhost:8000/sessions \
  -d '{"node_id": "timed_session"}'
```

## Learning Configuration

### max_pattern_length

Auto-learn when STM reaches this length (0 = manual).

**Global Configuration**:
```bash
# .env file
MAX_PATTERN_LENGTH=10
```

**Values**:
- **0**: Manual learning only (default)
- **5-20**: Auto-learn at fixed length
- **100+**: Large patterns

**Example - Auto-Learning**:
```bash
# Auto-learn every 10 observations
# .env: MAX_PATTERN_LENGTH=10

# STM automatically cleared and learned when length reaches 10
```

### stm_mode

Behavior after auto-learning.

**Global Configuration**:
```bash
# .env file
STM_MODE=CLEAR
```

**Options**:
- **CLEAR** (default): Reset STM to empty after auto-learn
- **ROLLING**: Keep most recent observation after learn

**Use Cases**:
- **CLEAR**: Discrete patterns, sessions
- **ROLLING**: Continuous streams, overlapping patterns

## Filter Pipeline Configuration

Control how KATO filters candidate patterns during prediction generation. The filter pipeline executes sequentially, progressively narrowing down candidates for final similarity scoring.

### filter_pipeline

Ordered list of filter stages to execute.

```json
{
  "filter_pipeline": []
}
```

**Available Filters**:
- **length**: Filter by pattern length relative to STM (fast, coarse)
- **jaccard**: Filter by token overlap similarity (fast, mid-precision)
- **minhash**: LSH-based approximate matching (very fast, scalable to millions)
- **bloom**: Bloom filter for fast set membership (fastest, probabilistic)
- **rapidfuzz**: High-precision similarity scoring (slower, most accurate)

**Default Pipeline**: `[]` (no pre-filtering - all patterns pass to matching algorithm)

**Pipeline Strategy**:
1. **Database filters first** (length, jaccard, minhash, bloom) - run in ClickHouse
2. **Python filters last** (rapidfuzz) - run on filtered candidates

**Example - Custom Pipeline**:
```bash
# Skip length filter, add MinHash for scale
curl -X POST http://localhost:8000/sessions \
  -d '{
    "node_id": "large_scale",
    "config": {
      "filter_pipeline": ["minhash", "jaccard", "rapidfuzz"],
      "minhash_threshold": 0.7
    }
  }'
```

### Length Filter Parameters

Control pattern length filtering (first stage - fastest).

```json
{
  "length_min_ratio": 0.5,
  "length_max_ratio": 2.0
}
```

**length_min_ratio**: Minimum pattern length as ratio of STM length
- `0.5` (default): Pattern must be at least 50% of STM length
- **Lower values** (0.3): More candidates, slower matching, better recall
- **Higher values** (0.7): Fewer candidates, faster matching, stricter

**length_max_ratio**: Maximum pattern length as ratio of STM length
- `2.0` (default): Pattern can be up to 200% of STM length
- Controls how much longer patterns can be vs current context
- **Lower values**: Stricter length requirements
- **Higher values**: Allow much longer patterns

**Example**:
```bash
# Strict length requirements
curl -X POST http://localhost:8000/sessions \
  -d '{
    "node_id": "strict_length",
    "config": {
      "length_min_ratio": 0.7,
      "length_max_ratio": 1.5
    }
  }'
```

### Jaccard Filter Parameters

Control token overlap filtering (second stage - fast).

```json
{
  "jaccard_threshold": 0.3,
  "jaccard_min_overlap": 2
}
```

**jaccard_threshold**: Minimum Jaccard similarity (0.0-1.0)
- `0.3` (default): 30% token overlap required
- **Jaccard similarity** = |A ∩ B| / |A ∪ B|
- **Higher values** (0.5-0.8): Stricter filtering, fewer candidates, faster
- **Lower values** (0.1-0.2): More permissive, more candidates, better recall

**jaccard_min_overlap**: Minimum absolute token count
- `2` (default): At least 2 tokens must overlap
- Prevents matching on single-token overlap
- **Higher values**: Require more substantial overlap

**Example**:
```bash
# Require substantial overlap
curl -X POST http://localhost:8000/sessions \
  -d '{
    "node_id": "high_overlap",
    "config": {
      "jaccard_threshold": 0.5,
      "jaccard_min_overlap": 5
    }
  }'
```

**Use Cases**:
- **Low threshold** (0.1-0.3): Exploratory search, loose matching
- **Medium threshold** (0.3-0.5): Balanced filtering (default)
- **High threshold** (0.5-0.8): Strict similarity requirements

### MinHash/LSH Filter Parameters

Control locality-sensitive hashing for large-scale pattern matching (alternative to Jaccard, scales to millions).

```json
{
  "minhash_threshold": 0.7,
  "minhash_bands": 20,
  "minhash_rows": 5,
  "minhash_num_hashes": 100
}
```

**minhash_threshold**: Estimated Jaccard threshold (0.0-1.0)
- `0.7` (default): 70% estimated similarity
- Controls LSH bucket membership
- **Higher values**: Fewer false positives, may miss some candidates
- **Lower values**: More candidates, more false positives

**minhash_bands**: Number of LSH bands (1-100)
- `20` (default): Balanced speed/accuracy
- **More bands**: Faster queries, more false negatives
- **Fewer bands**: Slower queries, better recall

**minhash_rows**: Rows per band (1-20)
- `5` (default): Standard configuration
- **More rows**: More accurate, slower
- **Fewer rows**: Faster, less accurate
- **Important**: `bands × rows = num_hashes`

**minhash_num_hashes**: Total signature size (10-256)
- `100` (default): Full MinHash signature size
- Must equal `bands × rows`
- **Common configurations**:
  - 100 = 20 bands × 5 rows (default)
  - 128 = 16 bands × 8 rows (more accurate)
  - 200 = 20 bands × 10 rows (high accuracy)

**Example - Large Scale**:
```bash
# Configure for millions of patterns
curl -X POST http://localhost:8000/sessions \
  -d '{
    "node_id": "large_scale",
    "config": {
      "filter_pipeline": ["minhash", "bloom", "rapidfuzz"],
      "minhash_threshold": 0.6,
      "minhash_bands": 25,
      "minhash_rows": 4,
      "minhash_num_hashes": 100
    }
  }'
```

**When to Use MinHash**:
- ✅ **Use when**: Millions of patterns, scalability critical
- ❌ **Skip when**: < 100K patterns (Jaccard is faster)

### Bloom Filter Parameters

Control Bloom filter false positive rate (fastest set membership test).

```json
{
  "bloom_false_positive_rate": 0.01
}
```

**bloom_false_positive_rate**: False positive probability (0.0001-0.1)
- `0.01` (default): 1% false positive rate
- **Lower values** (0.001): More memory, fewer false positives, higher precision
- **Higher values** (0.05): Less memory, more false positives, faster

**Trade-offs**:
- **Lower FPR**: More accurate filtering, uses more memory
- **Higher FPR**: Faster filtering, some irrelevant candidates pass through

**Example**:
```bash
# Very accurate Bloom filter
curl -X POST http://localhost:8000/sessions \
  -d '{
    "node_id": "accurate_bloom",
    "config": {
      "filter_pipeline": ["bloom", "jaccard", "rapidfuzz"],
      "bloom_false_positive_rate": 0.001
    }
  }'
```

### Pipeline Control Parameters

Global pipeline behavior controls.

```json
{
  "max_candidates_per_stage": 100000,
  "enable_filter_metrics": true
}
```

**max_candidates_per_stage**: Safety limit per filter stage
- `100000` (default): Maximum candidates between stages
- Prevents memory exhaustion on large datasets
- **Lower values**: More conservative, may truncate results
- **Higher values**: Allow more candidates, use more memory

**enable_filter_metrics**: Log filter performance
- `true` (default): Log timing and candidate counts for each stage
- `false`: Disable metrics logging (slight performance gain)

**Example Metrics**:
```
Filter 'length': 5432 candidates (2.3ms)
Filter 'jaccard': 1234 candidates (5.7ms)
Filter 'rapidfuzz': 234 candidates (45.2ms)
```

### Filter Pipeline Examples

**High-Precision Pipeline** (quality over speed):
```json
{
  "filter_pipeline": [],
  "recall_threshold": 0.8,
  "max_predictions": 10
}
```
**Use for**: Security, exact matching, high-confidence predictions

**High-Scale Pipeline** (millions of patterns):
```json
{
  "filter_pipeline": ["minhash", "bloom", "rapidfuzz"],
  "minhash_threshold": 0.6,
  "minhash_bands": 20,
  "minhash_rows": 5,
  "bloom_false_positive_rate": 0.02,
  "max_candidates_per_stage": 50000,
  "max_predictions": 100
}
```
**Use for**: Large databases, high-throughput systems

**Fast Pipeline** (fewer stages):
```json
{
  "filter_pipeline": ["length", "rapidfuzz"],
  "length_min_ratio": 0.6,
  "recall_threshold": 0.5,
  "max_predictions": 50
}
```
**Use for**: Low-latency requirements, small pattern sets

**Exploratory Pipeline** (maximum recall):
```json
{
  "filter_pipeline": ["length"],
  "length_min_ratio": 0.3,
  "length_max_ratio": 3.0,
  "recall_threshold": 0.1,
  "max_predictions": 1000
}
```
**Use for**: Pattern discovery, research, exploratory analysis

## Performance Configuration

### Batch Sizes

**Global Configuration** (Environment Variables):
```bash
# .env file
KATO_BATCH_SIZE=1000
KATO_VECTOR_BATCH_SIZE=1000
KATO_VECTOR_SEARCH_LIMIT=100
```

**KATO_BATCH_SIZE**:
- Pattern retrieval batch size
- Higher = fewer DB queries, more memory
- Default: 1000

**KATO_VECTOR_BATCH_SIZE**:
- Vector operation batch size
- Higher = better throughput, more memory
- Default: 1000

**KATO_VECTOR_SEARCH_LIMIT**:
- Maximum vector search results
- Higher = more candidates, slower search
- Default: 100

### Optimization Flags

**Global Configuration**:
```bash
# .env file
KATO_USE_FAST_MATCHING=true
KATO_USE_INDEXING=true
KATO_USE_OPTIMIZED=true
```

**KATO_USE_FAST_MATCHING**:
- Use RapidFuzz for pattern matching
- 9x-75x faster than legacy difflib
- Default: true

**KATO_USE_INDEXING**:
- Use pattern indexing for faster lookups
- Default: true

**KATO_USE_OPTIMIZED**:
- Enable all optimizations
- Default: true

**Recommendation**: Keep all optimizations enabled unless debugging.

## Configuration Recipes

### Chatbot (Fuzzy, Fast)

```json
{
  "recall_threshold": 0.1,
  "max_predictions": 50,
  "sort_symbols": true,
  "use_token_matching": true,
  "rank_sort_algo": "potential",
  "filter_pipeline": []
}
```

### Workflow Engine (Strict, Ordered)

```json
{
  "recall_threshold": 0.8,
  "max_predictions": 10,
  "sort_symbols": false,
  "use_token_matching": true,
  "rank_sort_algo": "similarity",
  "filter_pipeline": []
}
```

### Recommendation System (Balanced)

```json
{
  "recall_threshold": 0.3,
  "max_predictions": 100,
  "sort_symbols": true,
  "use_token_matching": true,
  "rank_sort_algo": "evidence",
  "filter_pipeline": []
}
```

### Real-Time Analytics (Auto-Learning)

```bash
# .env file
MAX_PATTERN_LENGTH=50
STM_MODE=ROLLING
SESSION_TTL=86400
```

```json
{
  "recall_threshold": 0.3,
  "max_predictions": 100,
  "use_token_matching": true,
  "rank_sort_algo": "potential",
  "filter_pipeline": ["length", "rapidfuzz"]
}
```

### Large-Scale System (Millions of Patterns)

```json
{
  "indexer_type": "LSH",
  "recall_threshold": 0.3,
  "max_predictions": 100,
  "use_token_matching": true,
  "rank_sort_algo": "potential",
  "filter_pipeline": ["minhash", "bloom", "rapidfuzz"],
  "minhash_threshold": 0.7,
  "minhash_bands": 20,
  "minhash_rows": 5,
  "bloom_false_positive_rate": 0.02,
  "max_candidates_per_stage": 50000
}
```

## Environment Variables

For complete list of environment variables, see [Environment Variables Reference](../reference/configuration-vars.md).

### Quick Reference

**Service**:
- `LOG_LEVEL`: DEBUG, INFO, WARNING, ERROR
- `LOG_FORMAT`: json, human

**Database**:
- `QDRANT_HOST`: qdrant host
- `REDIS_URL`: redis://host:port/db
- `CLICKHOUSE_HOST`: clickhouse host

**Learning**:
- `MAX_PATTERN_LENGTH`: Auto-learn length (0 = manual)
- `RECALL_THRESHOLD`: Pattern match threshold (0.0-1.0)
- `STM_MODE`: CLEAR or ROLLING

**Session**:
- `SESSION_TTL`: Session timeout (seconds)
- `SESSION_AUTO_EXTEND`: Auto-extend on access (true/false)

## Configuration File

KATO supports loading configuration from YAML or JSON files.

### YAML Configuration

```yaml
# config.yaml
environment: production
log_level: INFO

database:
  clickhouse_host: clickhouse-cluster
  qdrant_host: qdrant-cluster
  redis_url: redis://redis-cluster:6379/0

learning:
  max_pattern_length: 10
  recall_threshold: 0.3
  stm_mode: CLEAR

session:
  session_ttl: 7200
  session_auto_extend: true

processing:
  max_predictions: 100
  use_token_matching: true
  rank_sort_algo: potential
```

### Load Configuration File

```bash
# Via environment variable
export KATO_CONFIG_FILE=/path/to/config.yaml
./start.sh

# Or in docker compose.yml
environment:
  - KATO_CONFIG_FILE=/etc/kato/config.yaml
```

## Validation and Troubleshooting

### View Effective Configuration

```bash
# Get current session configuration
curl http://localhost:8000/sessions/{session_id} | jq '.config'
```

### Configuration Warnings

KATO validates configuration on startup:

```bash
docker compose logs kato | grep "Configuration warning"
```

**Common Warnings**:
- Using localhost databases in production
- CORS allows all origins in production
- Auto-learning with unlimited pattern length
- Large batch size may cause memory issues

### Testing Configuration

```bash
# Create test session
TEST_SESSION=$(curl -s -X POST http://localhost:8000/sessions \
  -d '{"node_id": "config_test", "config": {...}}' | jq -r '.session_id')

# Verify configuration applied
curl http://localhost:8000/sessions/$TEST_SESSION | jq '.config'

# Test behavior
curl -X POST http://localhost:8000/sessions/$TEST_SESSION/observe \
  -d '{"strings": ["test"], "vectors": [], "emotives": {}}'

# Check predictions use configuration
curl http://localhost:8000/sessions/$TEST_SESSION/predictions
```

## Best Practices

### Production Configuration

1. **Use configuration files** instead of environment variables for complex setups
2. **Set appropriate session TTLs** based on usage patterns
3. **Tune recall_threshold** based on precision/recall requirements
4. **Monitor performance** and adjust batch sizes
5. **Enable auto-extend** for interactive applications
6. **Use token matching** unless specifically need character-level fuzzy matching

### Development vs Production

**Development**:
```bash
LOG_LEVEL=DEBUG
LOG_FORMAT=human
RECALL_THRESHOLD=0.1
SESSION_TTL=3600
```

**Production**:
```bash
LOG_LEVEL=INFO
LOG_FORMAT=json
RECALL_THRESHOLD=0.3
SESSION_TTL=7200
```

## Related Documentation

- [Environment Variables Reference](../reference/configuration-vars.md)
- [Session Management](session-management.md)
- [Pattern Learning](pattern-learning.md)
- [Performance Tuning](../operations/performance-tuning.md)

---

**Last Updated**: November 2025
**KATO Version**: 3.0+
