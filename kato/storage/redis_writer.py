"""
Redis Writer for Pattern Metadata Storage

Handles writing pattern metadata to Redis with:
- Frequency counters
- Emotives (emotional context)
- Metadata (tags, categories, etc.)

All keys are namespaced by kb_id for complete isolation.
"""

import json
import logging
import time
from typing import Any, Optional

from kato.config.settings import get_settings

logger = logging.getLogger('kato.storage.redis_writer')


_GLOB_SPECIALS = str.maketrans({c: "\\" + c for c in "*?[]\\"})


def escape_glob(value: str) -> str:
    """Escape Redis SCAN/KEYS glob metacharacters in a literal key component.

    kb_ids are derived from caller-supplied node_ids and can contain ``[``, ``]``,
    ``*``, ``?`` or ``\\`` (pytest parametrize ids, for instance, produce
    ``name[case]``). Unescaped, ``[abc]`` is a character class, so a pattern built
    from such a kb_id matches nothing and any cleanup built on it silently no-ops.
    """
    return value.translate(_GLOB_SPECIALS)
_PREPARE_PATTERN_PURGE_SCRIPT = r"""
local raw = redis.call('HGET', KEYS[1], ARGV[1])
if not raw then return -1 end
local record = cjson.decode(raw)
if record['state'] ~= 'retired' then return 0 end
redis.call('HSET', KEYS[1], ARGV[1], ARGV[2])
return 1
"""


_PURGE_PATTERN_REDIS_SCRIPT = r"""
local registry_key = KEYS[1]
local pattern_name = ARGV[1]
local prefix = ARGV[2]

local raw = redis.call('HGET', registry_key, pattern_name)
if not raw then
    return -1
end

local record = cjson.decode(raw)
if record['state'] == 'redis_cleaned' or record['state'] == 'purged' then
    return 0
end
if record['state'] ~= 'prepared' or not record['snapshot'] then
    return redis.error_reply('retired pattern has no prepared purge snapshot')
end

local snapshot = record['snapshot']
local had_pattern = snapshot['had_pattern_record'] == true
local frequency = tonumber(snapshot['frequency'] or 0)
local symbol_counts = snapshot['symbol_counts'] or {}
local affinity = snapshot['affinity_contribution'] or {}

local function decrement_string(key, amount)
    if amount <= 0 then return end
    local current = tonumber(redis.call('GET', key) or '0')
    local updated = current - amount
    if updated <= 0 then
        redis.call('DEL', key)
    else
        redis.call('SET', key, tostring(updated))
    end
end

local function decrement_hash_int(key, field, amount)
    if amount <= 0 then return end
    local current = tonumber(redis.call('HGET', key, field) or '0')
    local updated = current - amount
    if updated <= 0 then
        redis.call('HDEL', key, field)
    else
        redis.call('HSET', key, field, tostring(updated))
    end
    if redis.call('HLEN', key) == 0 then redis.call('DEL', key) end
end

local function decrement_hash_float(key, field, amount)
    if amount == 0 then return end
    local current = tonumber(redis.call('HGET', key, field) or '0')
    local updated = current - amount
    if math.abs(updated) < 0.000000000001 then
        redis.call('HDEL', key, field)
    else
        redis.call('HSET', key, field, tostring(updated))
    end
    if redis.call('HLEN', key) == 0 then redis.call('DEL', key) end
end

if had_pattern then
    local current_frequency = tonumber(
        redis.call('GET', prefix .. ':frequency:' .. pattern_name) or '0'
    )
    if current_frequency ~= frequency then
        return redis.error_reply('pattern frequency changed after purge preparation')
    end

    local expected_total_symbols = 0
    for symbol, count_value in pairs(symbol_counts) do
        local count = tonumber(count_value)
        expected_total_symbols = expected_total_symbols + count
        local symbol_frequency = tonumber(
            redis.call('HGET', prefix .. ':symbols:freq', symbol) or '0'
        )
        local member_frequency = tonumber(
            redis.call('HGET', prefix .. ':symbols:pmf', symbol) or '0'
        )
        if symbol_frequency < count * frequency or member_frequency < 1 then
            return redis.error_reply('symbol counters changed after purge preparation')
        end
        if redis.call(
            'SISMEMBER', prefix .. ':symbol_to_patterns:' .. symbol, pattern_name
        ) == 0 then
            return redis.error_reply('symbol index changed after purge preparation')
        end
        for emotive, _value in pairs(affinity) do
            if not redis.call('HGET', prefix .. ':affinity:' .. symbol, emotive) then
                return redis.error_reply('affinity data changed after purge preparation')
            end
        end
    end

    local global_symbols = tonumber(redis.call(
        'GET', prefix .. ':global:total_symbols_in_patterns_frequencies'
    ) or '0')
    local global_patterns = tonumber(redis.call(
        'GET', prefix .. ':global:total_pattern_frequencies'
    ) or '0')
    local global_unique = tonumber(redis.call(
        'GET', prefix .. ':global:total_unique_patterns'
    ) or '0')
    if global_symbols < expected_total_symbols * frequency
        or global_patterns < 1 or global_unique < 1 then
        return redis.error_reply('global counters changed after purge preparation')
    end

    local total_symbols = 0
    for symbol, count_value in pairs(symbol_counts) do
        local count = tonumber(count_value)
        total_symbols = total_symbols + count
        decrement_hash_int(prefix .. ':symbols:freq', symbol, count * frequency)
        decrement_hash_int(prefix .. ':symbols:pmf', symbol, 1)

        local mapping_key = prefix .. ':symbol_to_patterns:' .. symbol
        redis.call('SREM', mapping_key, pattern_name)
        if redis.call('SCARD', mapping_key) == 0 then redis.call('DEL', mapping_key) end

        local affinity_key = prefix .. ':affinity:' .. symbol
        for emotive, value in pairs(affinity) do
            decrement_hash_float(affinity_key, emotive, tonumber(value))
        end
    end

    decrement_string(
        prefix .. ':global:total_symbols_in_patterns_frequencies',
        total_symbols * frequency
    )
    -- KATO currently increments both pattern counters once per unique pattern.
    decrement_string(prefix .. ':global:total_pattern_frequencies', 1)
    decrement_string(prefix .. ':global:total_unique_patterns', 1)
end

redis.call('DEL',
    prefix .. ':frequency:' .. pattern_name,
    prefix .. ':emotives:' .. pattern_name,
    prefix .. ':metadata:' .. pattern_name,
    prefix .. ':entropy:' .. pattern_name,
    prefix .. ':normalized_entropy:' .. pattern_name,
    prefix .. ':global_normalized_entropy:' .. pattern_name,
    prefix .. ':tf_vector:' .. pattern_name,
    prefix .. ':pattern_affinity_ledger:' .. pattern_name
)

redis.call('SET', prefix .. ':stats:version', ARGV[3])
record['state'] = 'redis_cleaned'
redis.call('HSET', registry_key, pattern_name, cjson.encode(record))
return 1
"""


class RedisWriter:
    """Writes pattern metadata to Redis."""

    def __init__(self, kb_id: str, redis_client):
        """
        Initialize Redis writer.

        Args:
            kb_id: Knowledge base identifier (used for key namespacing)
            redis_client: Redis client from connection manager
        """
        self.kb_id = kb_id
        self.client = redis_client

        if not self.client:
            raise RuntimeError("Redis client is required but was None")

        # TTL for per-observation prediction keys (see write_prediction).
        self.prediction_ttl_seconds = get_settings().session.session_ttl

        # Stamp rewritten whenever this node's symbol statistics or global
        # counters change. Readers cache those figures per process and compare
        # this value before reusing the cache; see get_global_metadata.
        #
        # It holds a nanosecond timestamp rather than an incrementing counter so
        # that clear-all can delete it like every other key for this kb_id (the
        # store must leave nothing behind -- see
        # test_redis_writer_cleanup_handles_glob_metacharacters). A counter
        # would restart at 1 after a wipe, and a process still holding a cache
        # stamped with a low number could then see a matching value and reuse a
        # cache describing data that no longer exists. A timestamp never repeats,
        # so a stale stamp can never match. Only inequality matters here, so
        # clock skew between workers costs at most one extra reload.
        self.stats_version_key = f"{kb_id}:stats:version"
        logger.debug(f"RedisWriter initialized for kb_id: {kb_id}")

    @property
    def retired_patterns_key(self) -> str:
        """Durable, node-scoped retired-pattern registry key."""
        return f"{self.kb_id}:retired_patterns"

    @staticmethod
    def normalize_pattern_name(pattern_name: str) -> str:
        """Return the storage hash without changing the learned pattern itself."""
        if not isinstance(pattern_name, str):
            raise TypeError("pattern ID must be a string")
        clean_name = pattern_name[5:] if pattern_name.startswith('PTRN|') else pattern_name
        if not clean_name:
            raise ValueError("pattern ID cannot be empty")
        return clean_name

    def retire_patterns(self, pattern_names: list[str]) -> dict[str, list[str]]:
        """Idempotently tombstone pattern IDs in this node's Redis namespace."""
        normalized = list(dict.fromkeys(
            self.normalize_pattern_name(name) for name in pattern_names
        ))
        if not normalized:
            return {'retired': [], 'already_retired': []}

        pipe = self.client.pipeline(transaction=True)
        value = json.dumps({'state': 'retired'}, separators=(',', ':'))
        for name in normalized:
            pipe.hsetnx(self.retired_patterns_key, name, value)
        results = pipe.execute()

        retired = [name for name, added in zip(normalized, results) if bool(added)]
        already = [name for name, added in zip(normalized, results) if not bool(added)]
        return {'retired': retired, 'already_retired': already}

    def get_retirement_records(self, pattern_names: list[str]) -> dict[str, dict[str, Any]]:
        """Read tombstone state for a bounded set of pattern IDs."""
        normalized = list(dict.fromkeys(
            self.normalize_pattern_name(name) for name in pattern_names
        ))
        if not normalized:
            return {}

        raw_records = self.client.hmget(self.retired_patterns_key, normalized)
        records: dict[str, dict[str, Any]] = {}
        for name, raw in zip(normalized, raw_records):
            if raw is None:
                continue
            if isinstance(raw, bytes):
                raw = raw.decode('utf-8')
            try:
                records[name] = json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                # Fail closed for any legacy/corrupt non-JSON tombstone.
                records[name] = {'state': 'retired'}
        return records

    def get_retired_pattern_ids(self, pattern_names: Optional[list[str]] = None) -> set[str]:
        """Return tombstoned hashes, optionally restricted to candidate IDs."""
        if not self.client.exists(self.retired_patterns_key):
            return set()
        if pattern_names is None:
            raw_names = self.client.hkeys(self.retired_patterns_key)
            return {
                name.decode('utf-8') if isinstance(name, bytes) else name
                for name in raw_names
            }
        return set(self.get_retirement_records(pattern_names))

    def prepare_pattern_purge(self, pattern_name: str, snapshot: dict[str, Any]) -> dict[str, Any]:
        """Durably attach the exact cleanup snapshot before physical deletion."""
        name = self.normalize_pattern_name(pattern_name)
        records = self.get_retirement_records([name])
        if name not in records:
            raise ValueError(f"pattern {name} is not retired")
        current = records[name]
        if current.get('state') in {'prepared', 'redis_cleaned', 'purged'}:
            return current

        prepared = {'state': 'prepared', 'snapshot': snapshot}
        prepared_json = json.dumps(prepared, separators=(',', ':'))
        transitioned = self.client.eval(
            _PREPARE_PATTERN_PURGE_SCRIPT,
            1,
            self.retired_patterns_key,
            name,
            prepared_json,
        )
        if transitioned == -1:
            raise ValueError(f"pattern {name} is not retired")
        if transitioned == 1:
            return prepared
        # Another caller advanced the state; never overwrite its snapshot or
        # cleanup marker with stale preparation data.
        return self.get_retirement_records([name])[name]

    def purge_pattern_records(self, pattern_name: str) -> bool:
        """Atomically remove one prepared pattern's Redis records and counters."""
        name = self.normalize_pattern_name(pattern_name)
        result = self.client.eval(
            _PURGE_PATTERN_REDIS_SCRIPT,
            1,
            self.retired_patterns_key,
            name,
            self.kb_id,
            str(time.time_ns()),
        )
        if result == -1:
            raise ValueError(f"pattern {name} is not retired")
        return result == 1

    def verify_pattern_records_absent(self, pattern_name: str) -> bool:
        """Verify all per-pattern Redis records and symbol memberships are gone."""
        name = self.normalize_pattern_name(pattern_name)
        record = self.get_retirement_records([name]).get(name, {})
        snapshot = record.get('snapshot', {})
        symbols = list(snapshot.get('symbol_counts', {}))

        per_pattern_keys = [
            f"{self.kb_id}:{kind}:{name}"
            for kind in (
                'frequency', 'emotives', 'metadata', 'entropy',
                'normalized_entropy', 'global_normalized_entropy', 'tf_vector',
                'pattern_affinity_ledger',
            )
        ]
        if any(self.client.exists(key) for key in per_pattern_keys):
            return False
        return all(
            not self.client.sismember(f"{self.kb_id}:symbol_to_patterns:{symbol}", name)
            for symbol in symbols
        )

    def has_pattern_records(self, pattern_name: str) -> bool:
        """Detect orphaned per-pattern records when ClickHouse data is absent."""
        name = self.normalize_pattern_name(pattern_name)
        per_pattern_keys = [
            f"{self.kb_id}:{kind}:{name}"
            for kind in (
                'frequency', 'emotives', 'metadata', 'entropy',
                'normalized_entropy', 'global_normalized_entropy', 'tf_vector',
                'pattern_affinity_ledger',
            )
        ]
        if any(self.client.exists(key) for key in per_pattern_keys):
            return True
        for key in self.client.scan_iter(
            match=f"{escape_glob(self.kb_id)}:symbol_to_patterns:*", count=1000
        ):
            if self.client.sismember(key, name):
                return True
        return False

    def mark_pattern_purged(self, pattern_name: str) -> bool:
        """Compact a verified tombstone while retaining it permanently."""
        name = self.normalize_pattern_name(pattern_name)
        record = self.get_retirement_records([name]).get(name)
        if not record:
            return False
        if record.get('state') == 'purged':
            return False
        if record.get('state') != 'redis_cleaned':
            raise RuntimeError(f"pattern {name} has not completed Redis cleanup")
        self.client.hset(
            self.retired_patterns_key,
            name,
            json.dumps({'state': 'purged'}, separators=(',', ':')),
        )
        return True

    def initialize_pattern_affinity_ledger(self, pattern_name: str) -> None:
        """Mark affinity accounting complete for a newly learned pattern."""
        name = self.normalize_pattern_name(pattern_name)
        self.client.hset(
            f"{self.kb_id}:pattern_affinity_ledger:{name}",
            '__kato_version__',
            1,
        )

    def has_pattern_affinity_ledger(self, pattern_name: str) -> bool:
        name = self.normalize_pattern_name(pattern_name)
        return bool(self.client.hexists(
            f"{self.kb_id}:pattern_affinity_ledger:{name}",
            '__kato_version__',
        ))

    def get_pattern_affinity_contribution(self, pattern_name: str) -> dict[str, float]:
        """Return the exact per-symbol affinity delta contributed by a pattern."""
        name = self.normalize_pattern_name(pattern_name)
        raw = self.client.hgetall(f"{self.kb_id}:pattern_affinity_ledger:{name}")
        contribution = {}
        for key, value in raw.items():
            key = key.decode('utf-8') if isinstance(key, bytes) else key
            if key == '__kato_version__':
                continue
            contribution[key] = float(value)
        return contribution

    def purge_patterns_from_prediction_records(self, pattern_names: list[str]) -> int:
        """Remove retired IDs from durable prediction snapshots for this node."""
        retired = {
            self.normalize_pattern_name(name) for name in pattern_names
        }
        if not retired:
            return 0

        changed = 0
        for key in self.client.scan_iter(
            match=f"{escape_glob(self.kb_id)}:prediction:*", count=1000
        ):
            raw = self.client.get(key)
            if not raw:
                continue
            if isinstance(raw, bytes):
                raw = raw.decode('utf-8')
            try:
                predictions = json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                # Corrupt snapshots are not rewritten by a lifecycle operation.
                continue
            if not isinstance(predictions, list):
                continue

            active = []
            for prediction in predictions:
                if not isinstance(prediction, dict):
                    active.append(prediction)
                    continue
                name = prediction.get('name')
                clean_name = (
                    self.normalize_pattern_name(name)
                    if isinstance(name, str) and name
                    else None
                )
                if clean_name not in retired:
                    active.append(prediction)

            if len(active) == len(predictions):
                continue
            changed += 1
            if active:
                self.client.set(key, json.dumps(active), keepttl=True)
            else:
                self.client.delete(key)
        return changed

    def delete_all_precomputed_metrics(self) -> int:
        """Invalidate node-wide finalized metrics after corpus membership changes."""
        keys = []
        for metric_type in (
            'entropy', 'normalized_entropy', 'global_normalized_entropy', 'tf_vector'
        ):
            keys.extend(self.client.scan_iter(
                match=f"{escape_glob(self.kb_id)}:{metric_type}:*", count=1000
            ))
        return self.client.delete(*keys) if keys else 0

    def increment_frequency(self, pattern_name: str) -> int:
        """
        Increment pattern frequency counter.

        Args:
            pattern_name: Pattern name (hash)

        Returns:
            New frequency value after increment

        Raises:
            Exception: If increment fails
        """
        try:
            freq_key = f"{self.kb_id}:frequency:{pattern_name}"
            new_freq = self.client.incr(freq_key)
            logger.debug(f"Incremented frequency for {pattern_name} to {new_freq}")
            return new_freq

        except Exception as e:
            logger.error(f"Failed to increment frequency for {pattern_name}: {e}")
            raise

    def get_frequency(self, pattern_name: str) -> int:
        """
        Get pattern frequency.

        Args:
            pattern_name: Pattern name (hash)

        Returns:
            Pattern frequency (0 if not found)
        """
        try:
            freq_key = f"{self.kb_id}:frequency:{pattern_name}"
            freq = self.client.get(freq_key)
            return int(freq) if freq else 0

        except Exception as e:
            logger.error(f"Failed to get frequency for {pattern_name}: {e}")
            return 0

    def pattern_exists(self, pattern_name: str) -> bool:
        """
        Check if pattern exists in Redis.

        Args:
            pattern_name: Pattern name (hash)

        Returns:
            True if frequency key exists
        """
        try:
            freq_key = f"{self.kb_id}:frequency:{pattern_name}"
            return self.client.exists(freq_key) > 0

        except Exception as e:
            logger.error(f"Failed to check if pattern {pattern_name} exists: {e}")
            return False

    def get_frequency_batch(self, pattern_names: list[str]) -> dict[str, int]:
        """
        Batch fetch pattern frequencies via a single MGET.

        Used by predict-path callers that previously pulled frequency through
        get_metadata_batch but no longer need the full metadata (emotives,
        metadata) bundle from Redis — those fields now live in ClickHouse
        patterns_metadata. Frequency stays in Redis to preserve atomic INCR.

        Args:
            pattern_names: List of pattern name hashes

        Returns:
            Dict mapping pattern_name → frequency (0 if not found)
        """
        if not pattern_names:
            return {}
        try:
            keys = [f"{self.kb_id}:frequency:{name}" for name in pattern_names]
            values = self.client.mget(keys)
            return {
                name: int(val) if val else 0
                for name, val in zip(pattern_names, values)
            }
        except Exception as e:
            logger.error(f"Failed to batch get frequencies for {len(pattern_names)} patterns: {e}")
            return dict.fromkeys(pattern_names, 0)

    def batch_update_symbol_stats(self, symbol_counts: dict[str, int],
                                   pattern_name: str,
                                   is_new_pattern: bool,
                                   total_symbol_count: int) -> None:
        """
        Batch all per-symbol Redis updates into a single pipeline call.

        Replaces per-symbol loops of increment_symbol_frequency,
        increment_pattern_member_frequency, and add_symbol_to_pattern_mapping
        plus global counter updates.

        Args:
            symbol_counts: Dict mapping symbol -> count in pattern
            pattern_name: Pattern name hash
            is_new_pattern: True if this is a new pattern (updates pmf and global unique count)
            total_symbol_count: Total number of symbols (sum of counts)
        """
        try:
            pipe = self.client.pipeline(transaction=False)

            for symbol, count in symbol_counts.items():
                # Increment symbol frequency by count (HASH field per symbol)
                pipe.hincrby(f"{self.kb_id}:symbols:freq", symbol, count)
                # Add symbol-to-pattern mapping (idempotent SET add)
                pipe.sadd(f"{self.kb_id}:symbol_to_patterns:{symbol}", pattern_name)

                if is_new_pattern:
                    # Increment pattern_member_frequency by 1 (new pattern contains this symbol)
                    pipe.hincrby(f"{self.kb_id}:symbols:pmf", symbol, 1)

            # Global counters
            pipe.incrby(f"{self.kb_id}:global:total_symbols_in_patterns_frequencies", total_symbol_count)

            if is_new_pattern:
                pipe.incrby(f"{self.kb_id}:global:total_pattern_frequencies", 1)
                pipe.incrby(f"{self.kb_id}:global:total_unique_patterns", 1)
            else:
                # Re-learned pattern: only increment pattern frequency total
                # (not unique count, since pattern already exists)
                pass

            # Announce the change to every other process. Rides along in this
            # pipeline, so it costs no extra round trip.
            pipe.set(self.stats_version_key, time.time_ns())

            pipe.execute()
            logger.debug(f"Batch updated symbol stats: {len(symbol_counts)} symbols, "
                        f"is_new={is_new_pattern}, total_symbols={total_symbol_count}")

        except Exception as e:
            logger.error(f"Failed to batch update symbol stats for pattern {pattern_name}: {e}")
            raise

    def delete_all_metadata(self) -> int:
        """
        Delete all keys for this kb_id.

        Returns:
            Number of keys deleted

        Raises:
            Exception: If deletion fails
        """
        try:
            # Find all keys for this kb_id
            pattern = f"{escape_glob(self.kb_id)}:*"
            keys = list(self.client.scan_iter(match=pattern, count=1000))

            if not keys:
                logger.debug(f"No Redis keys found for kb_id: {self.kb_id}")
                return 0

            # Everything goes, the stats stamp included -- the store must leave
            # nothing behind. A reader holding a cache stamped from before the
            # wipe reads a missing key as 0, which cannot equal the nanosecond
            # timestamp it cached, so it reloads.
            deleted = self.client.delete(*keys)
            logger.info(f"Deleted {deleted} Redis keys for kb_id: {self.kb_id}")
            return deleted

        except Exception as e:
            logger.error(f"Failed to delete Redis keys for {self.kb_id}: {e}")
            raise

    def count_patterns(self) -> int:
        """
        Count patterns for this kb_id (counts frequency keys).

        Returns:
            Number of patterns (frequency keys) for this kb_id
        """
        try:
            pattern = f"{escape_glob(self.kb_id)}:frequency:*"
            count = sum(1 for _ in self.client.scan_iter(match=pattern, count=1000))
            return count

        except Exception as e:
            logger.error(f"Failed to count patterns for {self.kb_id}: {e}")
            return 0

    def get_global_metadata(self) -> dict[str, int]:
        """
        Get global metadata totals for this kb_id.

        Also returns `stats_version`, the counter bumped by every write that
        changes these figures or the symbol table. Callers pass it to
        OptimizedQueryManager.get_all_symbols_optimized so a process can tell
        that another process changed the data underneath it. It is fetched in
        the same MGET, so it costs nothing extra.

        Returns:
            Dictionary with total_symbols_in_patterns_frequencies,
            total_pattern_frequencies, total_unique_patterns and stats_version
        """
        try:
            # Batch all GETs into a single mget call
            symbols_key = f"{self.kb_id}:global:total_symbols_in_patterns_frequencies"
            patterns_key = f"{self.kb_id}:global:total_pattern_frequencies"
            unique_patterns_key = f"{self.kb_id}:global:total_unique_patterns"

            symbols_total, patterns_total, unique_patterns_total, stats_version = self.client.mget(
                symbols_key, patterns_key, unique_patterns_key, self.stats_version_key
            )

            return {
                'total_symbols_in_patterns_frequencies': int(symbols_total) if symbols_total else 0,
                'total_pattern_frequencies': int(patterns_total) if patterns_total else 0,
                'total_unique_patterns': int(unique_patterns_total) if unique_patterns_total else 0,
                'stats_version': int(stats_version) if stats_version else 0,
            }

        except Exception as e:
            logger.error(f"Failed to get global metadata for {self.kb_id}: {e}")
            return {
                'total_symbols_in_patterns_frequencies': 0,
                'total_pattern_frequencies': 0,
                'total_unique_patterns': 0,
                'stats_version': 0,
            }

    def increment_global_symbol_count(self, count: int) -> int:
        """
        Increment global total_symbols_in_patterns_frequencies counter.

        Args:
            count: Number to increment by (number of symbols in pattern)

        Returns:
            New total value after increment
        """
        try:
            symbols_key = f"{self.kb_id}:global:total_symbols_in_patterns_frequencies"
            new_total = self.client.incrby(symbols_key, count)
            logger.debug(f"Incremented global symbol count by {count} to {new_total}")
            return new_total

        except Exception as e:
            logger.error(f"Failed to increment global symbol count: {e}")
            raise

    def increment_global_pattern_count(self, count: int = 1) -> int:
        """
        Increment global total_pattern_frequencies counter.

        Args:
            count: Number to increment by (typically 1 for each pattern learned)

        Returns:
            New total value after increment
        """
        try:
            patterns_key = f"{self.kb_id}:global:total_pattern_frequencies"
            new_total = self.client.incrby(patterns_key, count)
            logger.debug(f"Incremented global pattern count by {count} to {new_total}")
            return new_total

        except Exception as e:
            logger.error(f"Failed to increment global pattern count: {e}")
            raise

    def increment_unique_pattern_count(self, count: int = 1) -> int:
        """
        Increment total unique patterns counter (NOT frequency-weighted).

        This is different from total_pattern_frequencies which is frequency-weighted.
        Used for TF-IDF IDF calculation and proper probability calculations.

        Args:
            count: Number to increment by (typically 1 for each NEW pattern)

        Returns:
            New total value after increment

        Raises:
            Exception: If increment fails
        """
        try:
            key = f"{self.kb_id}:global:total_unique_patterns"
            new_total = self.client.incrby(key, count)
            logger.debug(f"Incremented unique pattern count by {count} to {new_total}")
            return new_total

        except Exception as e:
            logger.error(f"Failed to increment unique pattern count: {e}")
            raise

    def increment_symbol_frequency(self, symbol: str, count: int = 1) -> int:
        """
        Increment symbol frequency counter.

        Tracks total occurrences of this symbol across all patterns.
        If a symbol appears 3 times in a pattern with frequency=2,
        this increments by 3*2=6.

        Args:
            symbol: Symbol name
            count: Number to increment by

        Returns:
            New frequency value after increment

        Raises:
            Exception: If increment fails
        """
        try:
            new_freq = self.client.hincrby(f"{self.kb_id}:symbols:freq", symbol, count)
            logger.debug(f"Incremented symbol frequency for {symbol} by {count} to {new_freq}")
            return new_freq

        except Exception as e:
            logger.error(f"Failed to increment symbol frequency for {symbol}: {e}")
            raise

    def increment_pattern_member_frequency(self, symbol: str, count: int = 1) -> int:
        """
        Increment pattern member frequency for a symbol.

        Tracks how many patterns contain this symbol (counted once per pattern).
        Used for calculating symbol probability across pattern space.

        Args:
            symbol: Symbol name
            count: Number to increment by (typically 1 per pattern)

        Returns:
            New pattern_member_frequency value after increment

        Raises:
            Exception: If increment fails
        """
        try:
            new_pmf = self.client.hincrby(f"{self.kb_id}:symbols:pmf", symbol, count)
            logger.debug(f"Incremented pattern_member_frequency for {symbol} by {count} to {new_pmf}")
            return new_pmf

        except Exception as e:
            logger.error(f"Failed to increment pattern_member_frequency for {symbol}: {e}")
            raise

    def get_symbol_stats(self, symbol: str) -> dict[str, Any]:
        """
        Get all statistics for a symbol.

        Args:
            symbol: Symbol name

        Returns:
            Dictionary with 'frequency' and 'pattern_member_frequency'

        Raises:
            Exception: If retrieval fails
        """
        try:
            freq = self.client.hget(f"{self.kb_id}:symbols:freq", symbol)
            pmf = self.client.hget(f"{self.kb_id}:symbols:pmf", symbol)

            return {
                'name': symbol,
                'frequency': int(freq) if freq else 0,
                'pattern_member_frequency': int(pmf) if pmf else 0
            }

        except Exception as e:
            logger.error(f"Failed to get symbol stats for {symbol}: {e}")
            raise

    def get_all_symbols_batch(self) -> dict[str, dict[str, Any]]:
        """
        Get statistics for all symbols in this kb_id using Redis HASH structures.

        Uses HGETALL on two HASH keys (symbols:freq and symbols:pmf) instead of
        SCAN + pipelined GETs. This is O(1) for the hash lookup plus O(k) for
        k symbols, vs O(N) SCAN over all Redis keys.

        Returns:
            Dictionary mapping symbol names to their statistics

        Raises:
            Exception: If retrieval fails
        """
        try:
            # Two HGETALL calls instead of O(N) SCAN + O(N) pipelined GETs
            freq_data = self.client.hgetall(f"{self.kb_id}:symbols:freq")
            pmf_data = self.client.hgetall(f"{self.kb_id}:symbols:pmf")

            if not freq_data:
                logger.debug(f"No symbols found for kb_id: {self.kb_id}")
                return {}

            symbols = {}
            for symbol_name, freq_val in freq_data.items():
                # Handle bytes vs string keys
                name = symbol_name.decode('utf-8') if isinstance(symbol_name, bytes) else symbol_name
                pmf_val = pmf_data.get(symbol_name, 0)

                symbols[name] = {
                    'name': name,
                    'frequency': int(freq_val) if freq_val else 0,
                    'pattern_member_frequency': int(pmf_val) if pmf_val else 0
                }

            logger.debug(f"Retrieved {len(symbols)} symbols for kb_id: {self.kb_id} (HASH)")
            return symbols

        except Exception as e:
            logger.error(f"Failed to get all symbols for {self.kb_id}: {e}")
            raise

    def write_prediction(self, unique_id: str, predictions: list) -> bool:
        """
        Store predictions in Redis for later retrieval.

        Written with a TTL: one key is produced per observation and nothing
        reaps them, so an un-expiring write leaks a key per observe forever.
        The TTL matches the session lifetime, which bounds how long a caller
        could plausibly come back for the result.

        Args:
            unique_id: Unique identifier for this prediction state
            predictions: List of prediction dictionaries

        Returns:
            True if write successful

        Raises:
            Exception: If write fails
        """
        try:
            prediction_key = f"{self.kb_id}:prediction:{unique_id}"
            self.client.setex(
                prediction_key, self.prediction_ttl_seconds, json.dumps(predictions)
            )
            logger.debug(f"Wrote predictions for unique_id {unique_id} to Redis (kb_id={self.kb_id})")
            return True

        except Exception as e:
            logger.error(f"Failed to write predictions for unique_id {unique_id}: {e}")
            raise

    def get_predictions(self, unique_id: str) -> list:
        """
        Retrieve predictions by unique_id.

        Args:
            unique_id: Unique identifier for prediction state

        Returns:
            List of prediction dictionaries (empty list if not found)

        Raises:
            Exception: If retrieval fails
        """
        try:
            prediction_key = f"{self.kb_id}:prediction:{unique_id}"
            predictions = self.client.get(prediction_key)

            if predictions:
                return json.loads(predictions)
            return []

        except Exception as e:
            logger.error(f"Failed to get predictions for unique_id {unique_id}: {e}")
            return []

    def delete_all_predictions(self) -> int:
        """
        Delete all prediction keys for this kb_id.

        Returns:
            Number of prediction keys deleted

        Raises:
            Exception: If deletion fails
        """
        try:
            # Find all prediction keys for this kb_id
            pattern = f"{escape_glob(self.kb_id)}:prediction:*"
            keys = list(self.client.scan_iter(match=pattern, count=1000))

            if not keys:
                logger.debug(f"No prediction keys found for kb_id: {self.kb_id}")
                return 0

            # Delete all prediction keys
            deleted = self.client.delete(*keys)
            logger.debug(f"Deleted {deleted} prediction keys for kb_id: {self.kb_id}")
            return deleted

        except Exception as e:
            logger.error(f"Failed to delete predictions for {self.kb_id}: {e}")
            raise

    def add_symbol_to_pattern_mapping(self, symbol: str, pattern_name: str) -> int:
        """
        Add a symbol-to-pattern mapping in Redis.

        Creates a SET containing all pattern names that contain this symbol.
        Used for fast single-symbol prediction lookups.

        Args:
            symbol: Symbol name
            pattern_name: Pattern name (hash)

        Returns:
            Number of elements added to the set (1 if new, 0 if already exists)

        Raises:
            Exception: If add fails
        """
        try:
            key = f"{self.kb_id}:symbol_to_patterns:{symbol}"
            result = self.client.sadd(key, pattern_name)
            logger.debug(f"Added pattern {pattern_name} to symbol index for '{symbol}'")
            return result

        except Exception as e:
            logger.error(f"Failed to add symbol-to-pattern mapping for {symbol}: {e}")
            raise

    def get_patterns_for_symbol(self, symbol: str) -> set[str]:
        """
        Get all pattern names that contain a specific symbol.

        Args:
            symbol: Symbol name

        Returns:
            Set of pattern names (hashes) that contain this symbol

        Raises:
            Exception: If retrieval fails
        """
        try:
            key = f"{self.kb_id}:symbol_to_patterns:{symbol}"
            pattern_names = self.client.smembers(key)
            # Redis returns bytes, decode to strings
            return {name.decode('utf-8') if isinstance(name, bytes) else name for name in pattern_names}

        except Exception as e:
            logger.error(f"Failed to get patterns for symbol {symbol}: {e}")
            return set()

    def remove_symbol_to_pattern_mapping(self, symbol: str, pattern_name: str) -> int:
        """
        Remove a symbol-to-pattern mapping.

        Used when a pattern is deleted.

        Args:
            symbol: Symbol name
            pattern_name: Pattern name (hash)

        Returns:
            Number of elements removed (1 if existed, 0 if didn't exist)

        Raises:
            Exception: If removal fails
        """
        try:
            key = f"{self.kb_id}:symbol_to_patterns:{symbol}"
            result = self.client.srem(key, pattern_name)
            logger.debug(f"Removed pattern {pattern_name} from symbol index for '{symbol}'")
            return result

        except Exception as e:
            logger.error(f"Failed to remove symbol-to-pattern mapping for {symbol}: {e}")
            raise

    def get_patterns_starting_with_symbol(self, symbol: str, max_patterns: int = 1000) -> set[str]:
        """
        Get pattern names that START with a specific symbol (first event, first symbol).

        This is optimized for single-symbol predictions where we only want patterns
        that could be matched by the symbol at the beginning.

        Args:
            symbol: Symbol name
            max_patterns: Maximum number of patterns to return (default: 1000)

        Returns:
            Set of pattern names (hashes) that start with this symbol

        Note:
            For now, returns all patterns containing the symbol. Filtering by first symbol
            requires loading pattern_data from ClickHouse. This is still faster than
            the full filter pipeline for single-symbol queries.
        """
        # For initial implementation, return all patterns containing symbol
        # The pattern_processor will filter to first-symbol matches after loading from ClickHouse
        return self.get_patterns_for_symbol(symbol)

    # ── Symbol affinity ────────────────────────────────────────────────

    def batch_update_symbol_affinity(self, symbol_names: list[str],
                                      averaged_emotives: dict[str, float],
                                      pattern_name: Optional[str] = None) -> None:
        """
        Accumulate averaged emotives into per-symbol affinity sums.

        For each symbol, increments its affinity HASH fields by the corresponding
        emotive values using HINCRBYFLOAT (atomic, lock-free).

        Args:
            symbol_names: List of unique symbol names to update
            averaged_emotives: Dict mapping emotive name -> value to add
            pattern_name: Optional pattern hash. When its ledger has been
                initialized, the exact contribution is recorded for purge.
        """
        if not symbol_names or not averaged_emotives:
            return

        try:
            # Update symbol affinity and its reversible per-pattern
            # contribution in one Redis transaction.
            pipe = self.client.pipeline(transaction=bool(pattern_name))

            for symbol in symbol_names:
                affinity_key = f"{self.kb_id}:affinity:{symbol}"
                for emotive_name, value in averaged_emotives.items():
                    pipe.hincrbyfloat(affinity_key, emotive_name, value)

            if pattern_name:
                clean_name = self.normalize_pattern_name(pattern_name)
                ledger_key = f"{self.kb_id}:pattern_affinity_ledger:{clean_name}"
                if self.client.hexists(ledger_key, '__kato_version__'):
                    for emotive_name, value in averaged_emotives.items():
                        pipe.hincrbyfloat(ledger_key, emotive_name, value)

            pipe.execute()
            logger.debug(f"Batch updated affinity for {len(symbol_names)} symbols, "
                        f"{len(averaged_emotives)} emotive keys")

        except Exception as e:
            logger.error(f"Failed to batch update symbol affinity: {e}")
            raise

    def get_symbol_affinity(self, symbol: str) -> dict[str, float]:
        """
        Get affinity (cumulative emotive sums) for a symbol.

        Args:
            symbol: Symbol name

        Returns:
            Dictionary mapping emotive name -> cumulative sum value.
            Empty dict if no affinity data exists.
        """
        try:
            affinity_key = f"{self.kb_id}:affinity:{symbol}"
            raw = self.client.hgetall(affinity_key)

            if not raw:
                return {}

            return {
                (k.decode('utf-8') if isinstance(k, bytes) else k):
                float(v)
                for k, v in raw.items()
            }

        except Exception as e:
            logger.error(f"Failed to get affinity for symbol {symbol}: {e}")
            return {}

    def get_all_symbol_affinities(self) -> dict[str, dict[str, float]]:
        """
        Get affinity data for all symbols in this kb_id.

        Uses scan_iter to find all affinity keys, then pipelines HGETALL
        for each.

        Returns:
            Dictionary mapping symbol name -> {emotive_name: cumulative_sum}.
        """
        try:
            pattern = f"{escape_glob(self.kb_id)}:affinity:*"
            keys = list(self.client.scan_iter(match=pattern, count=1000))

            if not keys:
                return {}

            pipe = self.client.pipeline(transaction=False)
            for key in keys:
                pipe.hgetall(key)

            results = pipe.execute()

            prefix = f"{self.kb_id}:affinity:"
            affinities = {}
            for key, raw_hash in zip(keys, results):
                key_str = key.decode('utf-8') if isinstance(key, bytes) else key
                symbol = key_str[len(prefix):]
                if raw_hash:
                    affinities[symbol] = {
                        (k.decode('utf-8') if isinstance(k, bytes) else k):
                        float(v)
                        for k, v in raw_hash.items()
                    }
                else:
                    affinities[symbol] = {}

            logger.debug(f"Retrieved affinity for {len(affinities)} symbols")
            return affinities

        except Exception as e:
            logger.error(f"Failed to get all symbol affinities for {self.kb_id}: {e}")
            return {}

    def get_symbol_affinity_batch(self, symbols: list[str]) -> dict[str, dict[str, float]]:
        """
        Batch fetch affinity data for multiple symbols using a single pipeline.

        Args:
            symbols: List of symbol names to look up

        Returns:
            Dictionary mapping symbol name -> {emotive_name: cumulative_sum}.
            Symbols with no affinity data map to empty dict.
        """
        if not symbols:
            return {}

        try:
            pipe = self.client.pipeline(transaction=False)
            for symbol in symbols:
                pipe.hgetall(f"{self.kb_id}:affinity:{symbol}")
            results = pipe.execute()

            affinities = {}
            for symbol, raw in zip(symbols, results):
                if raw:
                    affinities[symbol] = {
                        (k.decode('utf-8') if isinstance(k, bytes) else k): float(v)
                        for k, v in raw.items()
                    }
                else:
                    affinities[symbol] = {}
            return affinities

        except Exception as e:
            logger.error(f"Failed to batch get symbol affinities: {e}")
            return {}

    def get_symbol_frequencies_batch(self, symbols: list[str]) -> dict[str, int]:
        """
        Batch fetch learn-frequencies for multiple symbols from the symbols:freq HASH.

        Args:
            symbols: List of symbol names to look up

        Returns:
            Dictionary mapping symbol name -> learn frequency (int).
            Symbols with no frequency data map to 0.
        """
        if not symbols:
            return {}

        try:
            pipe = self.client.pipeline(transaction=False)
            for symbol in symbols:
                pipe.hget(f"{self.kb_id}:symbols:freq", symbol)
            results = pipe.execute()

            return {
                symbol: int(val) if val else 0
                for symbol, val in zip(symbols, results)
            }

        except Exception as e:
            logger.error(f"Failed to batch get symbol frequencies: {e}")
            return {}

