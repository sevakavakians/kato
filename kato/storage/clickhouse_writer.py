"""
ClickHouse Writer for Pattern Storage

Handles writing pattern data to ClickHouse patterns_data table with:
- Pattern data and metadata
- MinHash signatures for LSH
- LSH bands for fast similarity search
- Token sets for filtering
- Buffered batch inserts for high-throughput learning
"""

import json
import logging
import time
from datetime import datetime
from itertools import chain
from os import environ
from typing import Any

from datasketch import MinHash

from kato.storage.identifiers import validate_kb_id, validate_pattern_name

# Pattern names per metadata query. They are expanded into the statement text as
# an IN list (~42 bytes each quoted) and ClickHouse rejects a statement over
# max_query_size, so every read chunks at this size regardless of what a caller
# asks for.
METADATA_QUERY_CHUNK = 500

# Optional xxhash for faster MinHash computation (~3-5x speedup)
try:
    import xxhash
    XXHASH_AVAILABLE = True
except ImportError:
    XXHASH_AVAILABLE = False

logger = logging.getLogger('kato.storage.clickhouse_writer')

# MinHash hash function selection
# Set MINHASH_HASH_FUNC=xxhash to use xxhash (faster, requires reindexing existing patterns)
_MINHASH_HASH_FUNC_SETTING = environ.get('MINHASH_HASH_FUNC', 'sha1').lower()

def _get_minhash_hashfunc():
    """Get the configured MinHash hash function."""
    if _MINHASH_HASH_FUNC_SETTING == 'xxhash' and XXHASH_AVAILABLE:
        def _xxhash_func(b):
            return xxhash.xxh64(b).intdigest()
        return _xxhash_func
    return None  # Use datasketch default (SHA-1)

_MINHASH_HASHFUNC = _get_minhash_hashfunc()


class ClickHouseWriter:
    """Writes pattern data to ClickHouse.

    Client-side buffering is disabled by default (batch_size=1); batching is
    delegated to ClickHouse's server-side `async_insert` feature, which batches
    across all uvicorn workers rather than per-worker. This eliminates the
    cross-worker visibility gap that per-worker client buffers created during
    multi-worker deployments.
    """

    # Default batch size for client-side buffering. 1 means "no buffering —
    # flush on every write_pattern call". Server-side async_insert handles the
    # actual batching across all callers.
    DEFAULT_BATCH_SIZE = 1

    # Class-level flag: ensure-DDL runs once per process, not once per kb_id.
    _metadata_table_ensured: bool = False

    def __init__(self, kb_id: str, clickhouse_client, batch_size: int = None):
        """
        Initialize ClickHouse writer.

        Args:
            kb_id: Knowledge base identifier (used for partitioning)
            clickhouse_client: ClickHouse client from connection manager
            batch_size: Number of patterns to buffer before auto-flush (default: 50)
        """
        self.kb_id = kb_id
        self.client = clickhouse_client
        self.batch_size = batch_size or self.DEFAULT_BATCH_SIZE
        self.max_buffer_size = self.batch_size * 10  # Cap buffer to prevent OOM on persistent flush failures

        # Write buffer for batch inserts
        self._write_buffer: list[list] = []
        self._column_names: list[str] | None = None

        if not self.client:
            raise RuntimeError("ClickHouse client is required but was None")

        if _MINHASH_HASH_FUNC_SETTING == 'xxhash':
            if XXHASH_AVAILABLE:
                logger.info("MinHash using xxhash (faster). Existing patterns may need reindexing.")
            else:
                logger.warning("MINHASH_HASH_FUNC=xxhash but xxhash not installed. Using default SHA-1.")

        logger.debug(f"ClickHouseWriter initialized for kb_id: {kb_id}, batch_size: {self.batch_size}")

        # One-time DDL for the patterns_metadata sidecar (idempotent CREATE IF NOT EXISTS).
        # Lets the dual-write rollout succeed on clusters whose init.sql predates this column set.
        if not ClickHouseWriter._metadata_table_ensured:
            self._ensure_patterns_metadata_table()
            ClickHouseWriter._metadata_table_ensured = True

    def _ensure_patterns_metadata_table(self) -> None:
        """Create the patterns_metadata sidecar table if it doesn't exist.

        Safe to run on every process startup. Existing tables are untouched
        because of CREATE TABLE IF NOT EXISTS. Logs a warning on failure rather
        than raising — if the DDL fails the metadata-write paths will surface
        the real error later.
        """
        ddl = """
            CREATE TABLE IF NOT EXISTS kato.patterns_metadata (
                kb_id                     String,
                name                      String,
                emotives                  String  DEFAULT '[]',
                metadata                  String  DEFAULT '{}',
                entropy                   Nullable(Float64),
                normalized_entropy        Nullable(Float64),
                global_normalized_entropy Nullable(Float64),
                tf_vector                 String  DEFAULT '{}',
                version                   UInt64,
                updated_at                DateTime64(3) DEFAULT now64(3)
            )
            ENGINE = ReplacingMergeTree(version)
            PARTITION BY kb_id
            ORDER BY (kb_id, name)
        """
        try:
            self.client.command(ddl)
            logger.debug("Ensured kato.patterns_metadata table exists")
        except Exception as e:
            logger.warning(f"Could not ensure kato.patterns_metadata table: {e}")

    @property
    def has_pending(self) -> bool:
        """Check if there are unflushed patterns in the write buffer."""
        return len(self._write_buffer) > 0

    def flush_if_pending(self) -> int:
        """Flush the write buffer only if there are pending patterns.

        Returns:
            Number of patterns flushed (0 if buffer was empty)
        """
        if self._write_buffer:
            return self.flush()
        return 0

    def flush_async_insert_queue(self) -> None:
        """Drain the ClickHouse server-side async_insert queue to the target table.

        With async_insert=1 and wait_for_async_insert=0, inserted rows sit in the
        server's async buffer for up to async_insert_busy_timeout_ms (~200ms by
        default) before they become queryable. Callers that need read-your-writes
        at a checkpoint (finalize_training) call this to force an immediate drain.
        """
        try:
            self.client.command('SYSTEM FLUSH ASYNC INSERT QUEUE')
            logger.debug(f"Flushed server async_insert queue (kb_id={self.kb_id})")
        except Exception as e:
            # FLUSH ASYNC INSERT QUEUE requires specific privileges on older versions.
            # Fall back to a brief sleep (the server will auto-flush in ~200ms).
            import time as _time
            logger.warning(f"SYSTEM FLUSH ASYNC INSERT QUEUE failed ({e}); sleeping briefly to let server auto-flush")
            _time.sleep(0.5)

    def _prepare_row(self, pattern_object) -> dict:
        """
        Prepare a row for ClickHouse insertion from a pattern object.

        Computes MinHash signature, LSH bands, and token set.

        Args:
            pattern_object: Pattern object with name, pattern_data, length

        Returns:
            Dictionary with all column values
        """
        # Pre-encode all tokens to bytes at once (avoids per-iteration overhead)
        all_tokens = list(chain(*pattern_object.pattern_data))
        encoded_tokens = [token.encode('utf8') for token in all_tokens]

        # Compute MinHash signature for LSH (100 permutations)
        if _MINHASH_HASHFUNC:
            minhash = MinHash(num_perm=100, hashfunc=_MINHASH_HASHFUNC)
        else:
            minhash = MinHash(num_perm=100)
        for encoded_token in encoded_tokens:
            minhash.update(encoded_token)
        minhash_sig = list(minhash.hashvalues)

        # Compute LSH bands (20 bands, 5 rows each)
        lsh_bands = []
        for i in range(20):
            band = minhash_sig[i*5:(i+1)*5]
            band_hash = abs(hash(tuple(band)))
            lsh_bands.append(band_hash)

        # Create token_set for filtering (use pre-computed all_tokens)
        token_set = list(set(all_tokens))

        token_count = len(token_set)
        first_token = pattern_object.pattern_data[0][0] if pattern_object.pattern_data and pattern_object.pattern_data[0] else ''
        last_token = pattern_object.pattern_data[-1][-1] if pattern_object.pattern_data and pattern_object.pattern_data[-1] else ''

        now = datetime.now()

        return {
            'kb_id': self.kb_id,
            'name': pattern_object.name,
            'pattern_data': pattern_object.pattern_data,
            'length': pattern_object.length,
            'token_set': token_set,
            'token_count': token_count,
            'minhash_sig': minhash_sig,
            'lsh_bands': lsh_bands,
            'first_token': first_token,
            'last_token': last_token,
            'created_at': now,
            'updated_at': now
        }

    def write_pattern(self, pattern_object) -> bool:
        """
        Buffer pattern for batch insertion into ClickHouse.

        Patterns are accumulated in an internal buffer and flushed to ClickHouse
        when the buffer reaches batch_size. Call flush() to write remaining
        buffered patterns.

        Args:
            pattern_object: Pattern object with name, pattern_data, length

        Returns:
            True if pattern was buffered (and possibly flushed) successfully

        Raises:
            Exception: If row preparation or flush fails
        """
        try:
            row = self._prepare_row(pattern_object)

            # Set column names on first write
            if self._column_names is None:
                self._column_names = list(row.keys())

            self._write_buffer.append(list(row.values()))

            # Auto-flush when buffer is full
            if len(self._write_buffer) >= self.batch_size:
                self.flush()

            logger.debug(f"Buffered pattern {pattern_object.name} (buffer: {len(self._write_buffer)}/{self.batch_size})")
            return True

        except Exception as e:
            import traceback
            logger.error(f"Failed to prepare pattern {pattern_object.name}: {type(e).__name__}: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise

    def flush(self) -> int:
        """
        Flush buffered patterns to ClickHouse in a single batch insert.

        Returns:
            Number of patterns flushed

        Raises:
            Exception: If batch insert fails
        """
        if not self._write_buffer:
            return 0

        count = len(self._write_buffer)
        try:
            # async_insert=1 keeps server-side batching across clients.
            # wait_for_async_insert=1 is required because Redis is updated after
            # this call; acknowledging before ClickHouse commits can otherwise
            # leave a Redis-only pattern if the async insert is lost.
            self.client.insert(
                'kato.patterns_data',
                self._write_buffer,
                column_names=self._column_names,
                settings={
                    'async_insert': 1,
                    'wait_for_async_insert': 1,
                },
            )
            logger.debug(f"Flushed {count} patterns to ClickHouse (kb_id={self.kb_id})")
            self._write_buffer.clear()
            return count
        except Exception as e:
            import traceback
            logger.error(f"Failed to flush {count} patterns to ClickHouse: {type(e).__name__}: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            # Prevent unbounded buffer growth on persistent failures
            if len(self._write_buffer) > self.max_buffer_size:
                dropped = len(self._write_buffer) - self.max_buffer_size
                self._write_buffer = self._write_buffer[dropped:]
                logger.error(f"Write buffer exceeded max size, dropped {dropped} oldest entries (kept {self.max_buffer_size})")
            raise

    def delete_all_patterns(self) -> bool:
        """
        Drop entire partition for this kb_id.

        This is much faster than deleting individual rows,
        as ClickHouse can drop the entire partition atomically.

        Returns:
            True if deletion successful

        Raises:
            Exception: If partition drop fails
        """
        try:
            # Drop partition by kb_id (specify database name).
            # DROP PARTITION does not accept bound parameters, so the kb_id is
            # allowlist-validated before it is inlined into statement text.
            safe_kb_id = validate_kb_id(self.kb_id)
            self.client.command(f"ALTER TABLE kato.patterns_data DROP PARTITION '{safe_kb_id}'")
            logger.info(f"Dropped ClickHouse partition for kb_id: {self.kb_id}")
            return True

        except Exception as e:
            # Partition might not exist if no patterns were ever written
            if "doesn't exist" in str(e).lower() or "not found" in str(e).lower():
                logger.debug(f"Partition {self.kb_id} doesn't exist, nothing to drop")
                return True
            logger.error(f"Failed to drop partition {self.kb_id}: {e}")
            raise

    def count_patterns(self) -> int:
        """
        Count patterns for this kb_id.

        Returns:
            Number of patterns in ClickHouse for this kb_id
        """
        try:
            result = self.client.query(
                "SELECT COUNT(*) FROM kato.patterns_data WHERE kb_id = %(kb_id)s",
                parameters={'kb_id': self.kb_id},
            )
            count = result.result_rows[0][0] if result.result_rows else 0
            return count

        except Exception as e:
            logger.error(f"Failed to count patterns for {self.kb_id}: {e}")
            return 0

    def pattern_exists(self, pattern_name: str) -> bool:
        """
        Check if pattern exists in ClickHouse.

        Args:
            pattern_name: Pattern name (hash)

        Returns:
            True if pattern exists
        """
        try:
            result = self.client.query(
                "SELECT COUNT(*) FROM kato.patterns_data "
                "WHERE kb_id = %(kb_id)s AND name = %(name)s",
                parameters={'kb_id': self.kb_id, 'name': pattern_name},
            )
            count = result.result_rows[0][0] if result.result_rows else 0
            return count > 0

        except Exception as e:
            logger.error(f"Failed to check if pattern {pattern_name} exists: {e}")
            return False

    def get_pattern_data(self, pattern_name: str) -> dict[str, Any] | None:
        """
        Retrieve pattern data from ClickHouse.

        Args:
            pattern_name: Pattern name (hash)

        Returns:
            Dictionary with pattern_data and length, or None if not found
        """
        try:
            result = self.client.query(
                "SELECT pattern_data, length FROM kato.patterns_data "
                "WHERE kb_id = %(kb_id)s AND name = %(name)s",
                parameters={'kb_id': self.kb_id, 'name': pattern_name},
            )

            if not result.result_rows:
                return None

            pattern_data, length = result.result_rows[0]
            return {
                'pattern_data': pattern_data,
                'length': length,
                'name': pattern_name
            }

        except Exception as e:
            logger.error(f"Failed to get pattern data for {pattern_name}: {e}")
            return None

    # ── Pattern metadata sidecar (offloaded from Redis) ─────────────────

    _METADATA_COLUMNS = (
        'kb_id', 'name', 'emotives', 'metadata',
        'entropy', 'normalized_entropy', 'global_normalized_entropy',
        'tf_vector', 'version', 'updated_at'
    )

    def _build_metadata_row(
        self,
        name: str,
        emotives: list[dict] | None,
        metadata: dict | None,
        entropy: float | None,
        normalized_entropy: float | None,
        global_normalized_entropy: float | None,
        tf_vector: dict | None,
        version: int,
        now: datetime,
    ) -> list:
        return [
            self.kb_id,
            name,
            json.dumps(emotives if emotives is not None else []),
            json.dumps(metadata if metadata is not None else {}),
            entropy,
            normalized_entropy,
            global_normalized_entropy,
            json.dumps(tf_vector if tf_vector is not None else {}),
            version,
            now,
        ]

    def write_pattern_metadata(
        self,
        name: str,
        emotives: list[dict] | None = None,
        metadata: dict | None = None,
        entropy: float | None = None,
        normalized_entropy: float | None = None,
        global_normalized_entropy: float | None = None,
        tf_vector: dict | None = None,
    ) -> bool:
        """
        INSERT a row into patterns_metadata (ReplacingMergeTree dedupes by (kb_id, name)).

        Callers must provide the full intended state of the row. To preserve
        existing fields, read via get_pattern_metadata_batch first and merge
        in Python — there is no partial-update semantics, omitted columns are
        written as their DEFAULTs.

        The row carries a strictly-monotonic `version` (time.time_ns()) that
        serves as the ReplacingMergeTree version and the argMax read tiebreaker,
        so a later write to the same (kb_id, name) always wins — even when two
        writes land in the same wall-clock second. Metadata is low-volume, so
        this uses wait_for_async_insert=1 for immediate read-after-write
        visibility (unlike the high-throughput patterns_data path).
        """
        try:
            row = self._build_metadata_row(
                name, emotives, metadata,
                entropy, normalized_entropy, global_normalized_entropy,
                tf_vector, time.time_ns(), datetime.now(),
            )
            self.client.insert(
                'kato.patterns_metadata',
                [row],
                column_names=list(self._METADATA_COLUMNS),
                settings={'async_insert': 1, 'wait_for_async_insert': 1},
            )
            return True
        except Exception as e:
            logger.error(f"Failed to write metadata for pattern {name}: {e}")
            raise

    def write_pattern_metadata_batch(self, rows: list[dict]) -> int:
        """
        Bulk INSERT multiple metadata rows in one ClickHouse call.

        Each dict accepts the same keys as write_pattern_metadata's kwargs
        (name, emotives, metadata, entropy, normalized_entropy,
        global_normalized_entropy, tf_vector). Missing keys → DEFAULT.
        """
        if not rows:
            return 0
        now = datetime.now()
        # Strictly-increasing version per row (base ns + index) so even repeated
        # names within one batch get distinct, monotonic versions.
        base_version = time.time_ns()
        values = [
            self._build_metadata_row(
                r['name'],
                r.get('emotives'),
                r.get('metadata'),
                r.get('entropy'),
                r.get('normalized_entropy'),
                r.get('global_normalized_entropy'),
                r.get('tf_vector'),
                base_version + i,
                now,
            )
            for i, r in enumerate(rows)
        ]
        try:
            self.client.insert(
                'kato.patterns_metadata',
                values,
                column_names=list(self._METADATA_COLUMNS),
                settings={'async_insert': 1, 'wait_for_async_insert': 1},
            )
            logger.debug(f"Batch wrote {len(rows)} metadata rows (kb_id={self.kb_id})")
            return len(rows)
        except Exception as e:
            logger.error(f"Failed to batch write {len(rows)} metadata rows: {e}")
            raise

    def get_pattern_metadata_batch(self, names: list[str]) -> dict[str, dict]:
        """
        Batch fetch metadata for multiple patterns.

        Uses argMax(field, version) GROUP BY name to retrieve the latest
        values across unmerged ReplacingMergeTree parts, without depending on
        the FINAL modifier's merge timing. `version` is a strictly-monotonic
        time.time_ns() stamp, so same-second re-writes are ordered correctly
        (the prior DateTime `updated_at` version tied at 1-second resolution
        and could return a stale row).

        Returns:
            Dict mapping pattern_name → {emotives, metadata, entropy,
            normalized_entropy, global_normalized_entropy, tf_vector}.
            Patterns absent from the table are omitted from the result —
            callers must default appropriately.
        """
        if not names:
            return {}

        # Chunk here, at the point the IN list is built, rather than leaving it
        # to callers. The names are expanded into the statement text, and
        # ClickHouse rejects anything over max_query_size (262144 bytes) -- at
        # ~42 bytes per quoted SHA1 that is roughly 6000 names. The failure is
        # silent from a caller's point of view: the except below logs and returns
        # {}, so predictions quietly fall back to frequency=1 and runtime
        # entropy. Two call sites were passing unbounded lists.
        if len(names) > METADATA_QUERY_CHUNK:
            merged: dict[str, dict] = {}
            for start in range(0, len(names), METADATA_QUERY_CHUNK):
                merged.update(
                    self.get_pattern_metadata_batch(names[start:start + METADATA_QUERY_CHUNK])
                )
            return merged

        try:
            result = self.client.query(
                """
                SELECT
                  name,
                  argMax(emotives, version)                  AS emotives,
                  argMax(metadata, version)                  AS metadata,
                  argMax(entropy, version)                   AS entropy,
                  argMax(normalized_entropy, version)        AS normalized_entropy,
                  argMax(global_normalized_entropy, version) AS global_normalized_entropy,
                  argMax(tf_vector, version)                 AS tf_vector
                FROM kato.patterns_metadata
                WHERE kb_id = %(kb_id)s AND name IN %(names)s
                GROUP BY name
                """,
                parameters={'kb_id': self.kb_id, 'names': tuple(names)},
            )
            out: dict[str, dict] = {}
            for row in result.result_rows:
                (
                    name,
                    emotives_str,
                    metadata_str,
                    entropy,
                    norm_entropy,
                    global_norm_entropy,
                    tf_str,
                ) = row
                entry: dict[str, Any] = {'name': name}
                try:
                    entry['emotives'] = json.loads(emotives_str) if emotives_str else []
                except (json.JSONDecodeError, TypeError):
                    entry['emotives'] = []
                try:
                    entry['metadata'] = json.loads(metadata_str) if metadata_str else {}
                except (json.JSONDecodeError, TypeError):
                    entry['metadata'] = {}
                if entropy is not None:
                    entry['entropy'] = float(entropy)
                if norm_entropy is not None:
                    entry['normalized_entropy'] = float(norm_entropy)
                if global_norm_entropy is not None:
                    entry['global_normalized_entropy'] = float(global_norm_entropy)
                try:
                    entry['tf_vector'] = json.loads(tf_str) if tf_str else {}
                except (json.JSONDecodeError, TypeError):
                    entry['tf_vector'] = {}
                out[name] = entry
            return out
        except Exception as e:
            logger.error(f"Failed to batch get pattern metadata for {len(names)} patterns: {e}")
            return {}

    def delete_pattern_metadata(self, name: str) -> bool:
        """Delete a single pattern's metadata row (async ALTER ... DELETE)."""
        try:
            # ALTER ... DELETE does not accept bound parameters; validate the
            # identifiers against a strict allowlist before inlining them.
            safe_kb_id = validate_kb_id(self.kb_id)
            safe_name = validate_pattern_name(name)
            self.client.command(
                f"ALTER TABLE kato.patterns_metadata "
                f"DELETE WHERE kb_id = '{safe_kb_id}' AND name = '{safe_name}'"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to delete metadata for pattern {name}: {e}")
            return False

    def delete_all_pattern_metadata(self) -> bool:
        """Drop the metadata partition for this kb_id (matches delete_all_patterns)."""
        try:
            # DROP PARTITION does not accept bound parameters.
            safe_kb_id = validate_kb_id(self.kb_id)
            self.client.command(
                f"ALTER TABLE kato.patterns_metadata DROP PARTITION '{safe_kb_id}'"
            )
            logger.info(f"Dropped patterns_metadata partition for kb_id: {self.kb_id}")
            return True
        except Exception as e:
            if "doesn't exist" in str(e).lower() or "not found" in str(e).lower():
                return True
            logger.error(f"Failed to drop metadata partition for {self.kb_id}: {e}")
            raise
    def get_patterns_data_batch(self, pattern_names: list[str]) -> dict[str, dict[str, Any]]:
        """Retrieve a bounded set of patterns for durable purge snapshots."""
        names = list(dict.fromkeys(pattern_names))
        if not names:
            return {}
        self.flush_if_pending()
        result = self.client.query(
            "SELECT name, pattern_data, length FROM kato.patterns_data "
            "WHERE kb_id = {kb_id:String} "
            "AND has({pattern_names:Array(String)}, name)",
            parameters={'kb_id': self.kb_id, 'pattern_names': names},
        )
        return {
            name: {'name': name, 'pattern_data': pattern_data, 'length': length}
            for name, pattern_data, length in result.result_rows
        }

    def get_present_pattern_names(self, pattern_names: list[str]) -> set[str]:
        """Return which requested pattern rows still exist in ClickHouse."""
        names = list(dict.fromkeys(pattern_names))
        if not names:
            return set()
        result = self.client.query(
            "SELECT DISTINCT name FROM kato.patterns_data "
            "WHERE kb_id = {kb_id:String} "
            "AND has({pattern_names:Array(String)}, name)",
            parameters={'kb_id': self.kb_id, 'pattern_names': names},
        )
        return {row[0] for row in result.result_rows}

    def get_present_lsh_pattern_names(self, pattern_names: list[str]) -> set[str]:
        """Return requested IDs still present in the optional LSH table."""
        names = list(dict.fromkeys(pattern_names))
        if not names:
            return set()
        result = self.client.query(
            "SELECT DISTINCT pattern_name FROM kato.lsh_buckets "
            "WHERE kb_id = {kb_id:String} "
            "AND has({pattern_names:Array(String)}, pattern_name)",
            parameters={'kb_id': self.kb_id, 'pattern_names': names},
        )
        return {row[0] for row in result.result_rows}

    def get_present_metadata_pattern_names(self, pattern_names: list[str]) -> set[str]:
        """Strict sidecar presence check; query failures must prevent purge success."""
        names = list(dict.fromkeys(pattern_names))
        if not names:
            return set()
        result = self.client.query(
            "SELECT DISTINCT name FROM kato.patterns_metadata "
            "WHERE kb_id = {kb_id:String} "
            "AND has({pattern_names:Array(String)}, name)",
            parameters={'kb_id': self.kb_id, 'pattern_names': names},
        )
        return {row[0] for row in result.result_rows}

    def invalidate_precomputed_metrics(self) -> int:
        """Clear finalized metrics on all physical rows, preserving user metadata.

        Updating every version avoids argMax skipping a new NULL and exposing
        an older finalized value in this ReplacingMergeTree sidecar.
        """
        safe_kb_id = validate_kb_id(self.kb_id)
        query = (
            "SELECT count() FROM kato.patterns_metadata "
            "WHERE kb_id = {kb_id:String} AND "
            "(entropy IS NOT NULL OR normalized_entropy IS NOT NULL OR "
            "global_normalized_entropy IS NOT NULL OR tf_vector != '{}')"
        )
        parameters = {'kb_id': self.kb_id}
        count = int(self.client.query(query, parameters=parameters).result_rows[0][0])
        self.client.command(
            "ALTER TABLE kato.patterns_metadata UPDATE "
            "entropy = NULL, normalized_entropy = NULL, "
            "global_normalized_entropy = NULL, tf_vector = '{}' "
            f"WHERE kb_id = '{safe_kb_id}'",
            settings={'mutations_sync': 2},
        )
        remaining = int(self.client.query(query, parameters=parameters).result_rows[0][0])
        if remaining:
            raise RuntimeError("ClickHouse precomputed metric invalidation failed")
        return count

    def purge_patterns(self, pattern_names: list[str]) -> int:
        """Synchronously purge node-scoped rows, sidecar metadata and indices.

        Validate identifiers before any mutation because ClickHouse ALTER
        predicates cannot use the query parameter binding path.
        """
        names = list(dict.fromkeys(pattern_names))
        if not names:
            return 0
        safe_kb_id = validate_kb_id(self.kb_id)
        safe_names = [validate_pattern_name(name) for name in names]
        names_sql = ', '.join(f"'{name}'" for name in safe_names)
        self.flush_if_pending()
        for table, column in (
            ('patterns_data', 'name'),
            ('patterns_metadata', 'name'),
            ('lsh_buckets', 'pattern_name'),
        ):
            self.client.command(
                f"ALTER TABLE kato.{table} DELETE WHERE kb_id = '{safe_kb_id}' "
                f"AND {column} IN ({names_sql})",
                settings={'mutations_sync': 2},
            )
        self.client.command(
            f"ALTER TABLE kato.pattern_stats DELETE WHERE kb_id = '{safe_kb_id}'",
            settings={'mutations_sync': 2},
        )
        remaining = self.get_present_pattern_names(names)
        remaining_lsh = self.get_present_lsh_pattern_names(names)
        remaining_metadata = self.get_present_metadata_pattern_names(names)
        if remaining or remaining_lsh or remaining_metadata:
            raise RuntimeError(
                "ClickHouse purge verification failed: "
                f"patterns={sorted(remaining)}, lsh={sorted(remaining_lsh)}, "
                f"metadata={sorted(remaining_metadata)}"
            )
        return len(names)
