"""
ClickHouse Writer for Pattern Storage

Handles writing pattern data to ClickHouse patterns_data table with:
- Pattern data and metadata
- MinHash signatures for LSH
- LSH bands for fast similarity search
- Token sets for filtering
- Buffered batch inserts for high-throughput learning
"""

import logging
from datetime import datetime
from itertools import chain
from os import environ
from typing import Any

from datasketch import MinHash

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
            # async_insert=1: server-side batches inserts across all clients
            #   (multi-worker safe; batches flush at ~1 MiB or busy_timeout
            #   ~200ms). wait_for_async_insert=0 returns immediately after
            #   enqueueing to the server-side buffer — visibility lags the
            #   call by up to busy_timeout but holds no HTTP connection
            #   hostage. finalize_training calls flush_if_pending (no-op for
            #   the client buffer) and then queries ClickHouse with a small
            #   post-training delay, so missing-at-query-time is not a concern.
            self.client.insert(
                'kato.patterns_data',
                self._write_buffer,
                column_names=self._column_names,
                settings={
                    'async_insert': 1,
                    'wait_for_async_insert': 0,
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
            # Drop partition by kb_id (specify database name)
            self.client.command(f"ALTER TABLE kato.patterns_data DROP PARTITION '{self.kb_id}'")
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
                f"SELECT COUNT(*) FROM kato.patterns_data WHERE kb_id = '{self.kb_id}'"
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
                f"SELECT COUNT(*) FROM kato.patterns_data "
                f"WHERE kb_id = '{self.kb_id}' AND name = '{pattern_name}'"
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
                f"SELECT pattern_data, length FROM kato.patterns_data "
                f"WHERE kb_id = '{self.kb_id}' AND name = '{pattern_name}'"
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
