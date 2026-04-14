# Redis Rehydration & Persistence Fix
**Completed**: 2026-04-13  
**Type**: Bug Fix + Resilience Improvement  
**Impact**: High — restored all prediction metrics for 250,850 trained patterns across 4 hierarchical nodes

## Problem

After training 250,850 patterns across 4 hierarchical nodes (`node0_kato` through `node3_kato`), all prediction metrics returned zeros in the generation notebook. ClickHouse retained the actual pattern data but Redis had lost all metadata (frequency, symbol stats, global counters, pre-computed entropy/TF metrics) because Redis persistence was not enabled.

**Root Cause**: Redis running without persistence (`REDIS_PERSISTENCE=false` default) lost all metadata on restart. ClickHouse retained pattern data. The frequency floor in the prediction pipeline was missing — patterns with frequency=0 in Redis caused silent metric cascading to zero rather than a recoverable warning.

## What Was Done

### 1. Created `scripts/rehydrate_redis.py`
Standalone script that rebuilds all Redis metadata from ClickHouse patterns:
- Frequency keys set to 1 for all patterns
- Symbol stats rebuilt from pattern data
- Global metadata reconstructed
- Pre-computed entropy/TF metrics regenerated

**Performance**: Rehydrated 250,850 patterns across 4 nodes in 51 seconds.

### 2. Enabled Redis Persistence in Deployment Config
- `deployment/.env.example`: Changed `REDIS_PERSISTENCE` default to `true`
- `config/redis.conf`: Added warning comments about data loss risk when persistence is disabled

### 3. Added Defensive Frequency Floor
- `kato/searches/pattern_search.py`: Floors frequency at 1 (with warning log) when a pattern exists in ClickHouse but has frequency=0 in Redis
- `kato/workers/pattern_processor.py`: Same defensive floor applied

## Verification

- Redis metadata verified post-rehydration: 193,900 frequency keys, 31,029 symbols, pre-computed metrics all present for `node0_kato`
- Redis memory usage: 361MB of 8GB (well within limits)
- Prediction metrics returning correct non-zero values after rehydration

## Files Changed

| File | Change |
|------|--------|
| `scripts/rehydrate_redis.py` | New — standalone Redis rehydration script |
| `deployment/.env.example` | Set `REDIS_PERSISTENCE=true` as default |
| `config/redis.conf` | Added data loss warning comments |
| `kato/searches/pattern_search.py` | Added frequency floor (floor at 1 with warning) |
| `kato/workers/pattern_processor.py` | Added frequency floor (floor at 1 with warning) |

## Operational Notes

Users running existing deployments need to:
1. Set `REDIS_PERSISTENCE=true` in their deployment `.env`
2. Restart Redis
3. If metadata was already lost, run `python scripts/rehydrate_redis.py` to recover

## Related

- Root architecture: ClickHouse + Redis hybrid (v3.0+)
- Redis session management: `kato/sessions/redis_session_manager.py`
- Pattern search: `kato/searches/pattern_search.py`
