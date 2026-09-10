"""
Metadata facade for per-pattern metadata stored in the ClickHouse
`patterns_metadata` sidecar table.

Centralizes the read/write logic that would otherwise be scattered across
learnPattern, finalize_training, predictPattern, and the prediction-build
batch. Callers go through this single facade instead of touching
ClickHouseWriter directly for emotives/metadata/entropy/tf_vector.

Per-pattern metadata (emotives, metadata, entropy, normalized_entropy,
global_normalized_entropy, tf_vector) lives in ClickHouse. Frequency stays in
Redis — it requires atomic INCR, which ClickHouse doesn't safely expose — and
is merged into read results here.

History: this previously routed between Redis and ClickHouse behind
KATO_METADATA_* feature flags during the Redis → ClickHouse migration. The
migration is complete; the dual-write/dual-read scaffolding has been removed
and ClickHouse is now the sole store for metadata.
"""

import logging
from typing import Any

from kato.storage.clickhouse_writer import ClickHouseWriter
from kato.storage.redis_writer import RedisWriter

logger = logging.getLogger('kato.storage.metadata_router')


class MetadataRouter:
    """Single entry point for per-pattern metadata reads/writes.

    Construct one per kb_id. Holds references to existing RedisWriter (frequency
    only) and ClickHouseWriter (metadata) instances; does not own their
    lifecycles.
    """

    def __init__(
        self,
        kb_id: str,
        redis_writer: RedisWriter,
        clickhouse_writer: ClickHouseWriter,
    ):
        self.kb_id = kb_id
        self.redis = redis_writer
        self.clickhouse = clickhouse_writer

    # ── Reads: emotives / metadata (+ frequency) ────────────────────────

    def get_metadata(self, pattern_name: str) -> dict[str, Any]:
        """Single-pattern convenience around get_metadata_batch.

        Returns {name, frequency, emotives?, metadata?} matching the prior
        RedisWriter.get_metadata contract.
        """
        batch = self.get_metadata_batch([pattern_name])
        return batch.get(pattern_name, {'name': pattern_name, 'frequency': 0})

    def get_metadata_for_merge(self, pattern_name: str) -> dict[str, Any]:
        """Full ClickHouse row, for a read-modify-write of emotives/metadata.

        Differs from get_metadata() in two ways that matter to merge callers:
        it keeps the precomputed metric columns (entropy, tf_vector, ...) so the
        caller can hand them straight back to upsert_pattern_metadata() instead
        of paying for a second identical SELECT, and it skips the Redis
        frequency lookup, which merge callers do not use.

        Returns {} when the pattern has no metadata row yet.
        """
        return self.clickhouse.get_pattern_metadata_batch([pattern_name]).get(pattern_name, {})

    def get_metadata_batch(self, pattern_names: list[str]) -> dict[str, dict]:
        """Returns dict[name → {name, frequency, emotives?, metadata?}].

        Metadata comes from ClickHouse; frequency is merged from Redis.
        emotives/metadata keys are present when the ClickHouse row has them and
        absent otherwise (matches the prior RedisWriter.get_metadata_batch
        contract).
        """
        if not pattern_names:
            return {}

        ch_meta = self.clickhouse.get_pattern_metadata_batch(pattern_names)
        frequencies = self.redis.get_frequency_batch(pattern_names)

        out: dict[str, dict] = {}
        for name in pattern_names:
            ch_entry = ch_meta.get(name)
            entry: dict[str, Any] = {'name': name, 'frequency': frequencies.get(name, 0)}
            if ch_entry is not None:
                entry['emotives'] = ch_entry.get('emotives', [])
                entry['metadata'] = ch_entry.get('metadata', {})
            out[name] = entry
        return out

    # ── Reads: precomputed metrics (entropy / tf_vector) ────────────────

    def get_precomputed_metrics_batch(self, pattern_names: list[str]) -> dict[str, dict]:
        """Returns dict[name → {entropy, normalized_entropy, global_normalized_entropy, tf_vector?}].

        Only patterns that have entropy populated are included (callers treat
        absence as "fallback to runtime computation").
        """
        if not pattern_names:
            return {}

        ch_meta = self.clickhouse.get_pattern_metadata_batch(pattern_names)
        out: dict[str, dict] = {}
        for name, entry in ch_meta.items():
            if 'entropy' not in entry:
                continue
            metric_entry = {
                'entropy': entry['entropy'],
                'normalized_entropy': entry.get('normalized_entropy', 0.0),
                'global_normalized_entropy': entry.get('global_normalized_entropy', 0.0),
            }
            if entry.get('tf_vector'):
                metric_entry['tf_vector'] = entry['tf_vector']
            out[name] = metric_entry
        return out

    # ── Writes: emotives / metadata ─────────────────────────────────────

    def upsert_pattern_metadata(
        self,
        pattern_name: str,
        emotives: list[dict] | None,
        metadata: dict | None,
        prev: dict[str, Any] | None = None,
    ) -> None:
        """Upsert a pattern's emotives + metadata, preserving precomputed metrics.

        patterns_metadata is a ReplacingMergeTree read with argMax(col, version),
        so a row written with a higher version wins for EVERY column - including
        the metric columns this path does not own. We therefore have to write the
        full intended row, which means knowing the current metric values.

        Args:
            prev: the pattern's existing row, when the caller has already read it
                (see get_metadata_for_merge). Omit it and we read the row here.
                Passing it avoids a second identical SELECT on the re-learn path.
        """
        if prev is None:
            prev = self.clickhouse.get_pattern_metadata_batch([pattern_name]).get(pattern_name, {})
        self.clickhouse.write_pattern_metadata(
            name=pattern_name,
            emotives=emotives if emotives is not None else [],
            metadata=metadata if metadata is not None else {},
            entropy=prev.get('entropy'),
            normalized_entropy=prev.get('normalized_entropy'),
            global_normalized_entropy=prev.get('global_normalized_entropy'),
            tf_vector=prev.get('tf_vector'),
        )

    # ── Writes: precomputed metrics (finalize_training) ─────────────────

    def update_precomputed_metrics_batch(self, metrics: list[dict]) -> int:
        """Batch-write precomputed entropy / tf metrics.

        Reads existing emotives/metadata to preserve them, then batch INSERTs
        full rows.
        """
        if not metrics:
            return 0

        names = [m['pattern_name'] for m in metrics]
        existing = self.clickhouse.get_pattern_metadata_batch(names)
        rows = []
        for m in metrics:
            name = m['pattern_name']
            prev = existing.get(name, {})
            rows.append({
                'name': name,
                'emotives': prev.get('emotives', []),
                'metadata': prev.get('metadata', {}),
                'entropy': m.get('entropy'),
                'normalized_entropy': m.get('normalized_entropy'),
                'global_normalized_entropy': m.get('global_normalized_entropy'),
                'tf_vector': m.get('tf_vector'),
            })
        return self.clickhouse.write_pattern_metadata_batch(rows)

    # ── Deletes ─────────────────────────────────────────────────────────

    def delete_pattern_metadata(self, pattern_name: str) -> None:
        """Delete a pattern's emotives/metadata/metric data from ClickHouse.

        The Redis frequency key is NOT touched here; deleting that is the
        caller's responsibility because it lives in Redis only.
        """
        try:
            self.clickhouse.delete_pattern_metadata(pattern_name)
        except Exception as e:
            logger.warning(f"ClickHouse delete_pattern_metadata failed for {pattern_name}: {e}")

    def delete_all_pattern_metadata(self) -> None:
        """Drop all per-pattern metadata for this kb_id from ClickHouse."""
        try:
            self.clickhouse.delete_all_pattern_metadata()
        except Exception as e:
            logger.warning(f"ClickHouse delete_all_pattern_metadata failed: {e}")
