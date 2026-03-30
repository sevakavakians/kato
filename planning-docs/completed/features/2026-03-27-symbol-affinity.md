# Completed Feature: Symbol Affinity
*Archived: 2026-03-27*

## Summary
Implemented Symbol Affinity — a per-symbol running cumulative sum of averaged emotive values, accumulated across every pattern that contains the symbol when it is learned with emotives. Unlike pattern emotives (rolling window), affinity is a monotonic cumulative sum that builds over the lifetime of the knowledge base.

## Motivation
Pattern emotives use a rolling window and can shift over time. Symbol Affinity provides a stable, long-horizon signal of how emotively charged each symbol is across all learned patterns — useful for downstream reasoning, ranking, and hybrid agent architectures.

## Implementation Details

### Storage
- Redis HASH per symbol at key `{kb_id}:affinity:{symbol}`
- Atomic updates via `HINCRBYFLOAT` — thread-safe, no locks required
- Namespaced by `kb_id` to maintain full node isolation

### Write Path
- In `learnPattern()` (`kato/informatics/knowledge_base.py`):
  - After symbol stats are updated, the averaged emotive values are summed into each symbol's affinity entry
  - Implemented via `_update_symbol_affinity()` helper method
  - Integrated into both branches of `learnPattern()` (new pattern and existing pattern frequency increment)

### Read Path
- `get_symbol_affinity(kb_id, symbol)` — single-symbol lookup
- `get_all_symbol_affinities(kb_id)` — returns all symbol affinities for a node
- Both methods in `kato/storage/redis_writer.py`

### API
- `GET /symbols/affinity` — all symbol affinities for the current kb_id
- `GET /symbols/{symbol}/affinity` — single symbol affinity
- Both endpoints added to `kato/api/endpoints/kato_ops.py`

## Files Modified
- `kato/storage/redis_writer.py` — Added `batch_update_symbol_affinity()`, `get_symbol_affinity()`, `get_all_symbol_affinities()`
- `kato/informatics/knowledge_base.py` — Added `_update_symbol_affinity()` helper; integrated into both branches of `learnPattern()`
- `kato/api/endpoints/kato_ops.py` — Added 2 API endpoints
- `tests/tests/unit/test_symbol_affinity.py` — 6 unit tests (all passing)
- `tests/tests/integration/test_symbol_affinity_e2e.py` — 4 integration tests (all passing)

## Test Results
- 10/10 new affinity tests passing
- 433/442 total tests passing
- 9 pre-existing failures in session/websocket tests (unrelated to this feature)
- Zero regressions introduced

## Key Design Properties
- **Monotonic**: Affinity only grows; never decrements (cumulative sum, not average)
- **Per-symbol**: Each symbol has its own affinity value, independent of patterns
- **Atomic**: `HINCRBYFLOAT` ensures concurrent learn calls are safe
- **Isolated**: Fully namespaced by `kb_id` — no cross-node leakage
- **Complementary**: Works alongside pattern emotives (rolling window) to provide two different emotive signals

## Distinction from Pattern Emotives
| Property | Pattern Emotives | Symbol Affinity |
|---|---|---|
| Granularity | Per pattern | Per symbol |
| Accumulation | Rolling window | Monotonic cumulative sum |
| Scope | Single pattern's emotional context | Aggregated across all patterns containing the symbol |
| Storage | Redis key per pattern | Redis HASH per symbol |

## Completion Date
2026-03-27
