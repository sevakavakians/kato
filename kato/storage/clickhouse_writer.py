"""
ClickHouse Writer for Pattern Storage

Handles writing pattern data to ClickHouse patterns_data table with:
- Pattern data and metadata
- MinHash signatures for LSH
- LSH bands for fast similarity search
- Token sets for filtering
"""

import logging
from itertools import chain
from typing import Any

logger = logging.getLogger('kato.storage.clickhouse_writer')


class ClickHouseWriter:
    """Writes pattern data to ClickHouse."""

    def __init__(self, kb_id: str, clickhouse_client):
        """
        Initialize ClickHouse writer.

        Args:
            kb_id: Knowledge base identifier (used for partitioning)
            clickhouse_client: ClickHouse client from connection manager
        """
        self.kb_id = kb_id
        self.client = clickhouse_client

        if not self.client:
            raise RuntimeError("ClickHouse client is required but was None")

        logger.debug(f"ClickHouseWriter initialized for kb_id: {kb_id}")

    def write_pattern(self, pattern_object) -> bool:
        """
        Insert pattern into ClickHouse patterns_data table.

        Computes MinHash signature and LSH bands for the pattern,
        then inserts all data into ClickHouse with kb_id partitioning.

        Args:
            pattern_object: Pattern object with name, pattern_data, length

        Returns:
            True if write successful

        Raises:
            Exception: If write fails
        """
        try:
            from datasketch import MinHash

            # Compute MinHash signature for LSH (100 permutations)
            minhash = MinHash(num_perm=100)
            for token in chain(*pattern_object.pattern_data):
                minhash.update(token.encode('utf8'))
            minhash_sig = list(minhash.hashvalues)

            # Compute LSH bands (20 bands, 5 rows each)
            # This allows fast approximate similarity search
            lsh_bands = []
            for i in range(20):
                band = minhash_sig[i*5:(i+1)*5]
                # Hash the band to create band signature (use abs for UInt64)
                band_hash = abs(hash(tuple(band)))
                lsh_bands.append(band_hash)

            # Flatten pattern_data to create token_set for filtering
            token_set = list(set(chain(*pattern_object.pattern_data)))

            # Calculate additional fields
            token_count = len(token_set)
            first_token = pattern_object.pattern_data[0][0] if pattern_object.pattern_data and pattern_object.pattern_data[0] else ''
            last_token = pattern_object.pattern_data[-1][-1] if pattern_object.pattern_data and pattern_object.pattern_data[-1] else ''

            # Prepare row for insertion (column order matches schema)
            from datetime import datetime
            now = datetime.now()

            row = {
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

            logger.debug(f"Inserting row with {len(row)} columns: {list(row.keys())}")

            # Insert into ClickHouse with column names and values as list
            # clickhouse_connect expects data as list of lists, not list of dicts
            column_names = list(row.keys())
            values = [list(row.values())]

            self.client.insert('kato.patterns_data', values, column_names=column_names)

            logger.debug(f"Wrote pattern {pattern_object.name} to ClickHouse (kb_id={self.kb_id})")
            return True

        except Exception as e:
            import traceback
            logger.error(f"Failed to write pattern {pattern_object.name}: {type(e).__name__}: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
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
