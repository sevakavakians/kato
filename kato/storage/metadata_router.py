"""
Metadata Router: dual-store routing for per-pattern metadata during the
Redis → ClickHouse migration.

Centralizes the read/write logic that would otherwise be scattered across
learnPattern, finalize_training, predictPattern, and the prediction-build
batch. Callers go through this single facade instead of directly touching
RedisWriter or ClickHouseWriter for emotives/metadata/entropy/tf_vector.

Routes are controlled by MetadataMigrationConfig:
  - dual_write=true   → writes go to both stores (default during rollout)
  - read_from         → 'redis' (default) or 'clickhouse'
  - read_verify=true  → reads BOTH stores, logs field-level diffs, returns
                        the read_from store's result. Staging-only.

Frequency stays in Redis regardless of these flags — it requires atomic
INCR, which ClickHouse doesn't safely expose.
"""

import logging
import math
from typing import Any

from kato.config.settings import MetadataMigrationConfig
from kato.storage.clickhouse_writer import ClickHouseWriter
from kato.storage.redis_writer import RedisWriter

logger = logging.getLogger('kato.storage.metadata_router')


class MetadataRouter:
    """Single entry point for per-pattern metadata reads/writes.

    Construct one per kb_id. Holds references to existing RedisWriter and
    ClickHouseWriter instances; does not own their lifecycles.
    """

    def __init__(
        self,
        kb_id: str,
        redis_writer: RedisWriter,
        clickhouse_writer: ClickHouseWriter,
        config: MetadataMigrationConfig,
    ):
        self.kb_id = kb_id
        self.redis = redis_writer
        self.clickhouse = clickhouse_writer
        self.config = config

    # ── Helpers ─────────────────────────────────────────────────────────

    @property
    def _writes_redis(self) -> bool:
        return self.config.dual_write or self.config.read_from == 'redis'

    @property
    def _writes_clickhouse(self) -> bool:
        return self.config.dual_write or self.config.read_from == 'clickhouse'

    # ── Reads: emotives / metadata (+ frequency) ────────────────────────

    def get_metadata(self, pattern_name: str) -> dict[str, Any]:
        """Single-pattern convenience around get_metadata_batch.

        Returns {name, frequency, emotives?, metadata?} matching the prior
        RedisWriter.get_metadata contract.
        """
        batch = self.get_metadata_batch([pattern_name])
        return batch.get(pattern_name, {'name': pattern_name, 'frequency': 0})

    def get_metadata_batch(self, pattern_names: list[str]) -> dict[str, dict]:
        """Returns dict[name → {name, frequency, emotives?, metadata?}].

        Matches the prior RedisWriter.get_metadata_batch contract: emotives
        and metadata keys are present when the underlying store has them, and
        absent when it doesn't.
        """
        if not pattern_names:
            return {}

        verify = self.config.read_verify
        source = self.config.read_from

        if source == 'redis' and not verify:
            return self.redis.get_metadata_batch(pattern_names)

        if source == 'clickhouse' and not verify:
            return self._get_metadata_batch_from_clickhouse(pattern_names)

        # Verify mode: read both, diff, return the configured source
        redis_result = self.redis.get_metadata_batch(pattern_names)
        ch_result = self._get_metadata_batch_from_clickhouse(pattern_names)
        self._diff_metadata_batches(pattern_names, redis_result, ch_result)
        return ch_result if source == 'clickhouse' else redis_result

    def _get_metadata_batch_from_clickhouse(self, pattern_names: list[str]) -> dict[str, dict]:
        """ClickHouse read path: merge patterns_metadata + Redis frequency."""
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

        Only patterns that have entropy populated are included (matches the
        prior RedisWriter.get_precomputed_metrics_batch contract — callers
        treat absence as "fallback to runtime computation").
        """
        if not pattern_names:
            return {}

        verify = self.config.read_verify
        source = self.config.read_from

        if source == 'redis' and not verify:
            return self.redis.get_precomputed_metrics_batch(pattern_names)

        if source == 'clickhouse' and not verify:
            return self._get_metrics_batch_from_clickhouse(pattern_names)

        redis_result = self.redis.get_precomputed_metrics_batch(pattern_names)
        ch_result = self._get_metrics_batch_from_clickhouse(pattern_names)
        self._diff_metric_batches(pattern_names, redis_result, ch_result)
        return ch_result if source == 'clickhouse' else redis_result

    def _get_metrics_batch_from_clickhouse(self, pattern_names: list[str]) -> dict[str, dict]:
        """Project metric-only fields out of patterns_metadata."""
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
    ) -> None:
        """Upsert a pattern's emotives + metadata, preserving precomputed metrics.

        Redis path is a direct write (emotives_key, metadata_key — metric
        keys are unaffected). ClickHouse path needs to write a full row,
        so we first read any existing metric columns to avoid overwriting
        them with NULL on background merge.
        """
        if self._writes_redis:
            try:
                self.redis.write_metadata(
                    pattern_name=pattern_name,
                    frequency=None,  # owned by SETNX / INCR — never touch from here
                    emotives=emotives if emotives is not None else [],
                    metadata=metadata if metadata is not None else {},
                )
            except Exception as e:
                logger.error(f"Redis upsert_pattern_metadata failed for {pattern_name}: {e}")
                if not self._writes_clickhouse:
                    raise

        if self._writes_clickhouse:
            try:
                existing = self.clickhouse.get_pattern_metadata_batch([pattern_name])
                prev = existing.get(pattern_name, {})
                self.clickhouse.write_pattern_metadata(
                    name=pattern_name,
                    emotives=emotives if emotives is not None else [],
                    metadata=metadata if metadata is not None else {},
                    entropy=prev.get('entropy'),
                    normalized_entropy=prev.get('normalized_entropy'),
                    global_normalized_entropy=prev.get('global_normalized_entropy'),
                    tf_vector=prev.get('tf_vector'),
                )
            except Exception as e:
                logger.error(f"ClickHouse upsert_pattern_metadata failed for {pattern_name}: {e}")
                if not self._writes_redis:
                    raise

    # ── Writes: precomputed metrics (finalize_training) ─────────────────

    def update_precomputed_metrics_batch(self, metrics: list[dict]) -> int:
        """Batch-write precomputed entropy / tf metrics.

        Redis path is a direct 4N-key pipeline. ClickHouse path needs to
        read existing emotives/metadata to preserve them, then batch INSERT
        full rows.
        """
        if not metrics:
            return 0

        written = 0
        if self._writes_redis:
            try:
                written = self.redis.write_precomputed_metrics_batch(metrics)
            except Exception as e:
                logger.error(f"Redis update_precomputed_metrics_batch failed: {e}")
                if not self._writes_clickhouse:
                    raise

        if self._writes_clickhouse:
            try:
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
                ch_written = self.clickhouse.write_pattern_metadata_batch(rows)
                if not self._writes_redis:
                    written = ch_written
            except Exception as e:
                logger.error(f"ClickHouse update_precomputed_metrics_batch failed: {e}")
                if not self._writes_redis:
                    raise

        return written

    # ── Deletes ─────────────────────────────────────────────────────────

    def delete_pattern_metadata(self, pattern_name: str) -> None:
        """Delete a pattern's emotives/metadata/metric data from both stores.

        Always deletes from both regardless of dual_write — orphaned rows
        are worse than the redundancy of an extra delete call. The Redis
        frequency key is NOT touched here; deleting that is the caller's
        responsibility because it lives in Redis only.
        """
        try:
            for key_type in ('emotives', 'metadata', 'entropy',
                              'normalized_entropy', 'global_normalized_entropy',
                              'tf_vector'):
                self.redis.client.delete(f"{self.kb_id}:{key_type}:{pattern_name}")
        except Exception as e:
            logger.warning(f"Redis delete_pattern_metadata failed for {pattern_name}: {e}")

        try:
            self.clickhouse.delete_pattern_metadata(pattern_name)
        except Exception as e:
            logger.warning(f"ClickHouse delete_pattern_metadata failed for {pattern_name}: {e}")

    def delete_all_pattern_metadata(self) -> None:
        """Drop all per-pattern metadata for this kb_id from both stores."""
        try:
            self.clickhouse.delete_all_pattern_metadata()
        except Exception as e:
            logger.warning(f"ClickHouse delete_all_pattern_metadata failed: {e}")

    # ── Verify-mode diffing ─────────────────────────────────────────────

    def _diff_metadata_batches(
        self,
        names: list[str],
        redis_result: dict[str, dict],
        ch_result: dict[str, dict],
    ) -> None:
        """Log field-level mismatches between the two stores. Best-effort only."""
        for name in names:
            r = redis_result.get(name) or {}
            c = ch_result.get(name) or {}
            if not r and not c:
                continue
            if r.get('frequency', 0) != c.get('frequency', 0):
                logger.warning(
                    f"[metadata-verify] freq mismatch name={name} "
                    f"redis={r.get('frequency')} clickhouse={c.get('frequency')}"
                )
            if 'emotives' in r and 'emotives' in c and r['emotives'] != c['emotives']:
                logger.warning(f"[metadata-verify] emotives mismatch name={name}")
            if 'metadata' in r and 'metadata' in c and r['metadata'] != c['metadata']:
                logger.warning(f"[metadata-verify] metadata mismatch name={name}")

    def _diff_metric_batches(
        self,
        names: list[str],
        redis_result: dict[str, dict],
        ch_result: dict[str, dict],
    ) -> None:
        """Log float-tolerant mismatches between the two stores."""
        for name in names:
            r = redis_result.get(name)
            c = ch_result.get(name)
            if r is None and c is None:
                continue
            if (r is None) != (c is None):
                logger.warning(
                    f"[metric-verify] presence mismatch name={name} "
                    f"redis={'hit' if r else 'miss'} clickhouse={'hit' if c else 'miss'}"
                )
                continue
            for field in ('entropy', 'normalized_entropy', 'global_normalized_entropy'):
                rv, cv = r.get(field), c.get(field)
                if rv is None and cv is None:
                    continue
                if rv is None or cv is None or not math.isclose(rv, cv, rel_tol=1e-6, abs_tol=1e-9):
                    logger.warning(
                        f"[metric-verify] {field} mismatch name={name} "
                        f"redis={rv} clickhouse={cv}"
                    )
            if r.get('tf_vector') != c.get('tf_vector'):
                logger.warning(f"[metric-verify] tf_vector mismatch name={name}")
