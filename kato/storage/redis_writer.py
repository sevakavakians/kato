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
from typing import Any

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
                                      averaged_emotives: dict[str, float]) -> None:
        """
        Accumulate averaged emotives into per-symbol affinity sums.

        For each symbol, increments its affinity HASH fields by the corresponding
        emotive values using HINCRBYFLOAT (atomic, lock-free).

        Args:
            symbol_names: List of unique symbol names to update
            averaged_emotives: Dict mapping emotive name -> value to add
        """
        if not symbol_names or not averaged_emotives:
            return

        try:
            pipe = self.client.pipeline(transaction=False)

            for symbol in symbol_names:
                affinity_key = f"{self.kb_id}:affinity:{symbol}"
                for emotive_name, value in averaged_emotives.items():
                    pipe.hincrbyfloat(affinity_key, emotive_name, value)

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

