"""
Redis Writer for Pattern Metadata Storage

Handles the Redis half of the hybrid store:
- Per-pattern frequency counters
- Node-level symbol statistics and global counters
- Per-symbol emotive affinity sums
- The retired-pattern registry and the purge lifecycle

Pattern emotives and metadata live in ClickHouse patterns_metadata, not here.
All keys are namespaced by kb_id for complete isolation.
"""

import json
import logging
import time
from typing import Any

from redis.exceptions import ResponseError

from kato.config.settings import get_settings
from kato.exceptions import ConcurrencyError, DataConsistencyError

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

# Purge runs as two Lua scripts so that each is atomic against concurrent learns.
# Redis executes a script to completion with nothing interleaved, which is what
# makes the counter arithmetic safe: the guards below read the same values the
# mutations then write, with no window between them.

# Advance a tombstone from 'retired' to 'prepared', attaching the snapshot that
# records exactly what this pattern contributed. Separate from the purge script
# because the snapshot has to be durable *before* anything is deleted -- if the
# process dies mid-purge, the resume path needs to know what was owed.
# Redis keys owned by exactly one pattern, as suffixes between the kb_id and the
# pattern hash. Verified against both the codebase and a live node: frequency is
# the only per-pattern counter, and the affinity ledger is the only per-pattern
# sidecar. Everything else a pattern owns -- emotives, metadata, precomputed
# metrics -- lives in ClickHouse patterns_metadata, not here.
PER_PATTERN_KEY_SUFFIXES = ('frequency', 'pattern_affinity_ledger')

# Marks a ledger hash as present even when a pattern contributed no emotives,
# distinguishing "recorded, contributed nothing" from "never recorded".
_LEDGER_SENTINEL_FIELD = '__kato_version__'

_PREPARE_PATTERN_PURGE_SCRIPT = """
local raw = redis.call('HGET', KEYS[1], ARGV[1])
if not raw then return -1 end
local record = cjson.decode(raw)
if record['state'] ~= 'retired' then return 0 end
redis.call('HSET', KEYS[1], ARGV[1], ARGV[2])
return 1
"""

# Reverse one pattern's contribution to the node's Redis counters, then advance
# the tombstone to 'redis_cleaned' -- in the same script, so a crash can never
# leave the counters decremented with the tombstone still 'prepared'. That
# property is what makes a retry safe rather than double-subtracting.
#
# ARGV[4] carries the already-encoded 'redis_cleaned' record. Encoding it in
# Python rather than calling cjson.encode here matters: cjson.encode is the one
# operation after the mutations that can fail, and a failure there would leave
# the counters decremented with the state unadvanced -- the single path by which
# a retry could subtract twice.
_PURGE_PATTERN_REDIS_SCRIPT = """
local registry_key = KEYS[1]
local pattern_name = ARGV[1]
local prefix = ARGV[2]
local stats_version = ARGV[3]
local cleaned_record = ARGV[4]

local raw = redis.call('HGET', registry_key, pattern_name)
if not raw then return -1 end

local record = cjson.decode(raw)
if record['state'] == 'redis_cleaned' or record['state'] == 'purged' then
    -- Already done. Return before touching anything, including stats:version,
    -- so a repeated call is observably a no-op.
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

-- Integers are written with %d, not tostring(). Lua's tostring uses %.14g, which
-- renders anything above ~1e14 in scientific notation ('1e+15'); Redis then
-- rejects the next INCRBY on that key with "value is not an integer".
local function decrement_string(key, amount)
    if amount <= 0 then return end
    local current = tonumber(redis.call('GET', key) or '0')
    local updated = current - amount
    if updated <= 0 then
        redis.call('DEL', key)
    else
        redis.call('SET', key, string.format('%d', updated))
    end
end

local function decrement_hash_int(key, field, amount)
    if amount <= 0 then return end
    local current = tonumber(redis.call('HGET', key, field) or '0')
    local updated = current - amount
    if updated <= 0 then
        redis.call('HDEL', key, field)
    else
        redis.call('HSET', key, field, string.format('%d', updated))
    end
    if redis.call('HLEN', key) == 0 then redis.call('DEL', key) end
end

-- Affinity is subtracted with HINCRBYFLOAT so Redis's own long double does the
-- arithmetic. Doing it in Lua would round-trip the value through a double and
-- write it back via %.14g, silently re-rounding every surviving pattern's
-- contribution on each purge.
--
-- The delete threshold is relative, not absolute. A fixed 1e-12 works for
-- emotives near 1.0 and fails above ~100, where float representation error
-- exceeds it -- leaving a residue field that no later purge can clear, so the
-- affinity hash survives with a phantom emotive for a symbol owning no patterns.
local function decrement_affinity(key, field, amount)
    if amount == 0 then return end
    if not redis.call('HEXISTS', key, field) then
        -- Nothing to reverse. Treated as already settled rather than an error:
        -- two patterns sharing a symbol with opposing contributions drive the
        -- field to zero, and the first purge deletes it. Erroring here would
        -- wedge the second pattern permanently, with no way to re-prepare.
        return
    end
    local updated = tonumber(redis.call('HINCRBYFLOAT', key, field, -amount))
    local magnitude = math.abs(updated)
    local scale = math.max(1.0, math.abs(amount))
    if magnitude < 1e-12 * scale then
        redis.call('HDEL', key, field)
    end
    if redis.call('HLEN', key) == 0 then redis.call('DEL', key) end
end

-- Guard phase. Every check runs before any write, so a tripped guard leaves the
-- node exactly as it was and the tombstone still 'prepared'.
if had_pattern then
    local current_frequency = tonumber(redis.call('GET', prefix .. ':frequency:' .. pattern_name) or '0')
    if current_frequency ~= frequency then
        return redis.error_reply('pattern frequency changed after purge preparation')
    end

    local expected_total_symbols = 0
    for symbol, count_value in pairs(symbol_counts) do
        local count = tonumber(count_value)
        expected_total_symbols = expected_total_symbols + count

        local symbol_frequency = tonumber(redis.call('HGET', prefix .. ':symbols:freq', symbol) or '0')
        local member_frequency = tonumber(redis.call('HGET', prefix .. ':symbols:pmf', symbol) or '0')
        if symbol_frequency < count * frequency or member_frequency < 1 then
            return redis.error_reply('symbol counters changed after purge preparation')
        end

        if redis.call('SISMEMBER', prefix .. ':symbol_to_patterns:' .. symbol, pattern_name) == 0 then
            return redis.error_reply('symbol index changed after purge preparation')
        end
    end

    local global_symbols = tonumber(redis.call('GET', prefix .. ':global:total_symbols_in_patterns_frequencies') or '0')
    local global_patterns = tonumber(redis.call('GET', prefix .. ':global:total_pattern_frequencies') or '0')
    local global_unique = tonumber(redis.call('GET', prefix .. ':global:total_unique_patterns') or '0')
    if global_symbols < expected_total_symbols * frequency or global_patterns < 1 or global_unique < 1 then
        return redis.error_reply('global counters changed after purge preparation')
    end

    -- Mutation phase.
    local total_symbols = 0
    for symbol, count_value in pairs(symbol_counts) do
        local count = tonumber(count_value)
        total_symbols = total_symbols + count

        -- symbols:freq accrues count on every learn, so the pattern's share is
        -- count * frequency. pmf accrues 1 only on first learn, so it is 1.
        decrement_hash_int(prefix .. ':symbols:freq', symbol, count * frequency)
        decrement_hash_int(prefix .. ':symbols:pmf', symbol, 1)

        local index_key = prefix .. ':symbol_to_patterns:' .. symbol
        redis.call('SREM', index_key, pattern_name)
        if redis.call('SCARD', index_key) == 0 then redis.call('DEL', index_key) end

        for emotive_name, value in pairs(affinity) do
            decrement_affinity(prefix .. ':affinity:' .. symbol, emotive_name, tonumber(value))
        end
    end

    decrement_string(prefix .. ':global:total_symbols_in_patterns_frequencies', total_symbols * frequency)
    -- Both pattern counters move by 1, not by frequency: the learn path
    -- increments each once per unique pattern, not once per learn (see
    -- batch_update_symbol_stats, where both sit behind is_new_pattern).
    -- test_purge_reverses_frequency_weighted_share learns three times and
    -- compares the whole node before and after, so it fails loudly if the learn
    -- path ever starts accruing these per learn.
    decrement_string(prefix .. ':global:total_pattern_frequencies', 1)
    decrement_string(prefix .. ':global:total_unique_patterns', 1)
end

-- Per-pattern keys go regardless of had_pattern: a pattern with no Redis
-- records still needs any stragglers removed.
--
-- The list arrives fully built from Python (ARGV[5] onward) instead of being
-- reassembled here. PER_PATTERN_KEY_SUFFIXES is then the single definition of
-- what a pattern owns, shared by this purge, the post-purge verification and
-- has_pattern_records -- three readings that must agree, because a key this
-- script does not delete is one verification would not look for either, and the
-- pattern would be marked 'purged' with a live record behind it.
for i = 5, #ARGV do
    redis.call('DEL', ARGV[i])
end

-- Tell other workers their cached symbol statistics are stale.
redis.call('SET', prefix .. ':stats:version', stats_version)

redis.call('HSET', registry_key, pattern_name, cleaned_record)
return 1
"""

# Create the ledger sentinel and add this learn's contribution in one atomic
# step. Splitting them left a window in which a concurrent re-learner added to
# affinity while its ledger increment was skipped, so purge later treated an
# under-counted ledger as exact and silently under-subtracted.
_ACCRUE_AFFINITY_LEDGER_SCRIPT = """
redis.call('HSETNX', KEYS[1], '__kato_version__', '1')
for i = 1, #ARGV, 2 do
    redis.call('HINCRBYFLOAT', KEYS[1], ARGV[i], ARGV[i + 1])
end
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
        """Return the storage hash without changing the learned pattern itself.

        Patterns are stored under the bare SHA1; the 'PTRN|' prefix exists only in
        human-readable output. Callers may pass either form.
        """
        if not isinstance(pattern_name, str):
            raise TypeError("pattern ID must be a string")
        clean_name = pattern_name[5:] if pattern_name.startswith('PTRN|') else pattern_name
        if not clean_name:
            raise ValueError("pattern ID cannot be empty")
        return clean_name

    def retire_patterns(self, pattern_names: list[str]) -> dict[str, list[str]]:
        """Idempotently tombstone pattern IDs in this node's Redis namespace.

        HSETNX rather than HSET, so a repeated retire reports the ID as already
        retired instead of silently resetting its state. Learned rows are not
        touched: retirement only hides a pattern from the read paths.
        """
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

    def un_retire_patterns(self, pattern_names: list[str]) -> dict[str, list[str]]:
        """Remove tombstones, making the patterns visible and learnable again.

        Retirement would otherwise be irreversible, and learnPattern refuses a
        tombstoned hash -- so without this, one mistaken retire permanently
        prevents that sequence from ever being learned on this node.
        """
        normalized = list(dict.fromkeys(
            self.normalize_pattern_name(name) for name in pattern_names
        ))
        if not normalized:
            return {'un_retired': [], 'not_retired': []}

        pipe = self.client.pipeline(transaction=True)
        for name in normalized:
            pipe.hdel(self.retired_patterns_key, name)
        results = pipe.execute()

        un_retired = [name for name, removed in zip(normalized, results) if bool(removed)]
        absent = [name for name, removed in zip(normalized, results) if not bool(removed)]
        return {'un_retired': un_retired, 'not_retired': absent}

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
                # Fail closed for any legacy or corrupt non-JSON tombstone: an
                # unreadable record still means "retired".
                records[name] = {'state': 'retired'}
        return records

    def has_any_retired_patterns(self) -> bool:
        """Whether this node has any tombstone at all.

        The read-path barriers consult this first. On a node that has never
        retired anything -- which is every node by default -- it is one EXISTS
        against a key that does not exist, and the barrier then does no further
        work. Without it, every prediction paid an HMGET sized to its candidate
        set for a feature almost nobody has switched on.
        """
        return bool(self.client.exists(self.retired_patterns_key))

    def get_retired_pattern_ids(self, pattern_names: list[str] | None = None) -> set[str]:
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

    # ------------------------------------------------------------------
    # Purge lifecycle
    #
    # A tombstone walks 'retired' -> 'prepared' -> 'redis_cleaned' -> 'purged',
    # and each transition is durable before the work it authorises begins. That
    # ordering is what makes an interrupted purge resumable rather than
    # corrupting: the snapshot recording what a pattern owed is written before
    # anything is subtracted, and the counters are subtracted in the same atomic
    # step that records them as subtracted.
    # ------------------------------------------------------------------

    def _per_pattern_keys(self, clean_name: str) -> list[str]:
        """Every Redis key owned solely by one pattern, for this kb_id."""
        return [
            f"{self.kb_id}:{suffix}:{clean_name}"
            for suffix in PER_PATTERN_KEY_SUFFIXES
        ]

    def affinity_ledger_key(self, pattern_name: str) -> str:
        """Key holding what one pattern has contributed to symbol affinity."""
        return f"{self.kb_id}:pattern_affinity_ledger:{self.normalize_pattern_name(pattern_name)}"

    def accrue_affinity_ledger(self, pattern_name: str,
                               contribution: dict[str, float]) -> None:
        """Record a learn's affinity contribution so purge can reverse it exactly.

        Affinity is a running sum of *averaged* emotives, and the average shifts
        with every learn as the rolling persistence window slides. Nothing in the
        stored pattern therefore recovers what a given pattern actually added --
        so a purge that recomputed it would subtract a different number than was
        added, permanently skewing every symbol it shares. This ledger is the
        only exact record.

        The sentinel and the increments go in one script rather than a pipeline:
        separately, a concurrent re-learn could add to affinity in the window
        between them and have its own increment skipped, leaving an under-counted
        ledger that purge would trust as exact.
        """
        if not contribution:
            return

        args: list[Any] = []
        for emotive_name, value in contribution.items():
            args.extend([emotive_name, repr(float(value))])

        self.client.eval(
            _ACCRUE_AFFINITY_LEDGER_SCRIPT, 1,
            self.affinity_ledger_key(pattern_name), *args
        )

    def get_affinity_ledger(self, pattern_name: str) -> dict[str, float] | None:
        """Exact affinity contribution for a pattern, or None if unrecorded.

        None and {} mean different things. None is a pattern learned before the
        ledger existed, whose contribution can only be estimated; {} is a pattern
        that genuinely contributed no affinity. Callers must not collapse them --
        see the backfill note in PatternProcessor.purge_retired_patterns.
        """
        raw = self.client.hgetall(self.affinity_ledger_key(pattern_name))
        if not raw:
            return None

        ledger: dict[str, float] = {}
        for key, value in raw.items():
            name = key.decode('utf-8') if isinstance(key, bytes) else key
            if name == _LEDGER_SENTINEL_FIELD:
                continue
            try:
                ledger[name] = float(value)
            except (TypeError, ValueError):
                logger.warning(
                    f"Ignoring unparseable affinity ledger entry {name!r} "
                    f"for pattern {pattern_name}"
                )
        return ledger

    def has_pattern_records(self, pattern_name: str) -> bool:
        """Whether any Redis key for this pattern still exists."""
        clean_name = self.normalize_pattern_name(pattern_name)
        pipe = self.client.pipeline(transaction=False)
        for key in self._per_pattern_keys(clean_name):
            pipe.exists(key)
        return any(bool(found) for found in pipe.execute())

    def verify_pattern_records_absent(self, pattern_name: str) -> list[str]:
        """Return any per-pattern keys that survived a purge.

        A non-empty result blocks the final 'purged' transition: the pattern is
        left at 'redis_cleaned' so a resume retries, rather than being recorded
        as gone while a record of it is still readable.
        """
        clean_name = self.normalize_pattern_name(pattern_name)
        keys = self._per_pattern_keys(clean_name)
        pipe = self.client.pipeline(transaction=False)
        for key in keys:
            pipe.exists(key)
        return [key for key, found in zip(keys, pipe.execute()) if bool(found)]

    def build_purge_snapshot(self, pattern_name: str,
                             symbol_counts: dict[str, int],
                             affinity_contribution: dict[str, float]) -> dict[str, Any]:
        """Capture exactly what this pattern owes the node's counters.

        `symbol_counts` and `affinity_contribution` come from the caller because
        they are derived from the stored pattern and its emotives; frequency and
        record existence are read here, together, from Redis.
        """
        clean_name = self.normalize_pattern_name(pattern_name)
        frequency_key = f"{self.kb_id}:frequency:{clean_name}"

        pipe = self.client.pipeline(transaction=False)
        pipe.get(frequency_key)
        pipe.exists(frequency_key)
        raw_frequency, frequency_exists = pipe.execute()

        try:
            frequency = int(raw_frequency) if raw_frequency is not None else 0
        except (TypeError, ValueError):
            frequency = 0

        return {
            'had_pattern_record': bool(frequency_exists) and frequency > 0,
            'frequency': frequency,
            'symbol_counts': {
                symbol: int(count) for symbol, count in symbol_counts.items()
            },
            'affinity_contribution': {
                name: float(value)
                for name, value in (affinity_contribution or {}).items()
            },
        }

    def prepare_pattern_purge(self, pattern_name: str,
                              snapshot: dict[str, Any]) -> str:
        """Attach a purge snapshot to a tombstone: 'retired' -> 'prepared'.

        Returns 'prepared', 'already_advanced' (the tombstone is at or past
        'prepared' -- resume, do not re-snapshot), or 'not_retired'.
        """
        clean_name = self.normalize_pattern_name(pattern_name)
        record = json.dumps(
            {
                'state': 'prepared',
                'snapshot': snapshot,
                'prepared_at': time.time_ns(),
            },
            separators=(',', ':'),
        )
        result = int(self.client.eval(
            _PREPARE_PATTERN_PURGE_SCRIPT, 1,
            self.retired_patterns_key, clean_name, record
        ))
        if result == 1:
            return 'prepared'
        return 'already_advanced' if result == 0 else 'not_retired'

    def purge_pattern_records(self, pattern_name: str) -> str:
        """Reverse this pattern's Redis contribution and delete its records.

        Returns 'cleaned', 'already_cleaned' or 'not_retired'. Raises
        ConcurrencyError if the node moved under the snapshot -- the pattern was
        re-learned between preparation and here -- in which case nothing was
        written and the caller re-prepares.
        """
        clean_name = self.normalize_pattern_name(pattern_name)

        raw = self.client.hget(self.retired_patterns_key, clean_name)
        if raw is None:
            return 'not_retired'
        if isinstance(raw, bytes):
            raw = raw.decode('utf-8')
        try:
            record = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            raise DataConsistencyError(
                resource_id=clean_name,
                consistency_type='unparseable tombstone',
                expected_value='a JSON retirement record',
                actual_value='a value that is not JSON',
                context={'kb_id': self.kb_id},
            ) from None

        state = record.get('state')
        if state in ('redis_cleaned', 'purged'):
            return 'already_cleaned'

        # The 'redis_cleaned' record is encoded here, not in Lua. cjson.encode is
        # the one call in the script that can fail *after* the counters have been
        # decremented, and a failure there would leave them decremented with the
        # state unadvanced -- the single path by which a retry double-subtracts.
        cleaned_record = json.dumps(
            {**record, 'state': 'redis_cleaned', 'redis_cleaned_at': time.time_ns()},
            separators=(',', ':'),
        )

        try:
            result = int(self.client.eval(
                _PURGE_PATTERN_REDIS_SCRIPT, 1,
                self.retired_patterns_key,
                clean_name,
                self.kb_id,
                str(time.time_ns()),
                cleaned_record,
                *self._per_pattern_keys(clean_name),
            ))
        except ResponseError as exc:
            message = str(exc)
            if 'after purge preparation' in message or 'prepared purge snapshot' in message:
                raise ConcurrencyError(
                    resource_id=clean_name,
                    operation='purge_pattern_records',
                    message=f"Purge snapshot for {clean_name} is stale: {message}",
                    context={'kb_id': self.kb_id},
                ) from exc
            raise

        if result == 1:
            return 'cleaned'
        return 'already_cleaned' if result == 0 else 'not_retired'

    def mark_pattern_purged(self, pattern_name: str) -> bool:
        """Final transition, once every store has confirmed the pattern is gone.

        The tombstone is kept rather than deleted: it is what stops a later
        observation of the same sequence silently re-learning the hash, and it
        remains the audit record of the purge.
        """
        clean_name = self.normalize_pattern_name(pattern_name)
        raw = self.client.hget(self.retired_patterns_key, clean_name)
        if raw is None:
            return False
        if isinstance(raw, bytes):
            raw = raw.decode('utf-8')
        try:
            record = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            record = {}

        # The snapshot has served its purpose and is the bulky part of the
        # record; a node that purges heavily would otherwise carry every purged
        # pattern's symbol counts in one hash forever.
        record.pop('snapshot', None)
        record['state'] = 'purged'
        record['purged_at'] = time.time_ns()
        self.client.hset(
            self.retired_patterns_key, clean_name,
            json.dumps(record, separators=(',', ':'))
        )
        return True


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
                                      pattern_name: str | None = None) -> None:
        """
        Accumulate averaged emotives into per-symbol affinity sums.

        For each symbol, increments its affinity HASH fields by the corresponding
        emotive values using HINCRBYFLOAT (atomic, lock-free).

        Args:
            symbol_names: List of unique symbol names to update
            averaged_emotives: Dict mapping emotive name -> value to add
            pattern_name: Pattern this contribution belongs to. When given, the
                same amounts are journalled so a later purge can subtract exactly
                what was added; without it the contribution is unattributable and
                purge can only estimate. Optional so that callers outside the
                learn path stay unaffected.
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

            # After the affinity writes, never before. The ledger is purge's
            # claim about what affinity holds, so a ledger entry without the
            # matching affinity increment would have purge subtract a
            # contribution that was never added -- driving a shared symbol's
            # affinity negative. The reverse ordering only under-records, which
            # the backfill path already tolerates.
            if pattern_name:
                self.accrue_affinity_ledger(pattern_name, averaged_emotives)

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

