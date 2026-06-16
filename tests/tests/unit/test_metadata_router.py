"""
Unit tests for MetadataRouter — verifies the dual-store routing logic that
gates the Redis → ClickHouse migration.

Uses MagicMock for RedisWriter and ClickHouseWriter so these tests are pure
Python (no live services needed).
"""

from unittest.mock import MagicMock

import pytest

import os

from kato.config.settings import MetadataMigrationConfig
from kato.storage.metadata_router import MetadataRouter


@pytest.fixture
def writers():
    redis = MagicMock(name='RedisWriter')
    clickhouse = MagicMock(name='ClickHouseWriter')
    return redis, clickhouse


def _router(redis, clickhouse, dual_write=True, read_from='redis', read_verify=False):
    config = MetadataMigrationConfig(
        dual_write=dual_write,
        read_from=read_from,
        read_verify=read_verify,
    )
    return MetadataRouter(kb_id='kb_test', redis_writer=redis, clickhouse_writer=clickhouse, config=config)


# ── Reads ─────────────────────────────────────────────────────────────


def test_get_metadata_batch_redis_only(writers):
    redis, clickhouse = writers
    redis.get_metadata_batch.return_value = {'p1': {'name': 'p1', 'frequency': 3, 'emotives': []}}
    r = _router(redis, clickhouse, dual_write=False, read_from='redis')

    out = r.get_metadata_batch(['p1'])

    redis.get_metadata_batch.assert_called_once_with(['p1'])
    clickhouse.get_pattern_metadata_batch.assert_not_called()
    assert out['p1']['frequency'] == 3


def test_get_metadata_batch_clickhouse(writers):
    redis, clickhouse = writers
    clickhouse.get_pattern_metadata_batch.return_value = {
        'p1': {'name': 'p1', 'emotives': [{'happy': 0.5}], 'metadata': {}, 'entropy': 1.2}
    }
    redis.get_frequency_batch.return_value = {'p1': 7}
    r = _router(redis, clickhouse, dual_write=False, read_from='clickhouse')

    out = r.get_metadata_batch(['p1'])

    clickhouse.get_pattern_metadata_batch.assert_called_once_with(['p1'])
    redis.get_frequency_batch.assert_called_once_with(['p1'])
    redis.get_metadata_batch.assert_not_called()
    assert out['p1']['frequency'] == 7
    assert out['p1']['emotives'] == [{'happy': 0.5}]


def test_get_metadata_batch_verify_reads_both(writers, caplog):
    redis, clickhouse = writers
    redis.get_metadata_batch.return_value = {'p1': {'name': 'p1', 'frequency': 5, 'emotives': []}}
    clickhouse.get_pattern_metadata_batch.return_value = {
        'p1': {'name': 'p1', 'emotives': [], 'metadata': {}}
    }
    redis.get_frequency_batch.return_value = {'p1': 9}  # mismatch with Redis batch
    r = _router(redis, clickhouse, dual_write=True, read_from='redis', read_verify=True)

    with caplog.at_level('WARNING'):
        out = r.get_metadata_batch(['p1'])

    redis.get_metadata_batch.assert_called_once()
    clickhouse.get_pattern_metadata_batch.assert_called_once()
    # read_from='redis' means Redis result returned
    assert out['p1']['frequency'] == 5
    # Diff should have been logged
    assert any('freq mismatch' in rec.message for rec in caplog.records)


def test_get_metadata_batch_empty_returns_empty(writers):
    redis, clickhouse = writers
    r = _router(redis, clickhouse, dual_write=True, read_from='redis')
    assert r.get_metadata_batch([]) == {}
    redis.get_metadata_batch.assert_not_called()


def test_get_precomputed_metrics_batch_clickhouse_filters_missing_entropy(writers):
    redis, clickhouse = writers
    clickhouse.get_pattern_metadata_batch.return_value = {
        'p1': {'name': 'p1', 'emotives': [], 'metadata': {}, 'entropy': 1.5,
               'normalized_entropy': 0.5, 'global_normalized_entropy': 0.3,
               'tf_vector': {'a': 0.5}},
        'p2': {'name': 'p2', 'emotives': [], 'metadata': {}},  # no entropy yet
    }
    r = _router(redis, clickhouse, dual_write=False, read_from='clickhouse')

    out = r.get_precomputed_metrics_batch(['p1', 'p2'])

    assert 'p1' in out and out['p1']['entropy'] == 1.5
    assert 'p2' not in out  # entropy missing → filtered, matching prior Redis contract


# ── Writes ────────────────────────────────────────────────────────────


def test_upsert_pattern_metadata_dual_write(writers):
    redis, clickhouse = writers
    clickhouse.get_pattern_metadata_batch.return_value = {}  # no prior row
    r = _router(redis, clickhouse, dual_write=True, read_from='redis')

    r.upsert_pattern_metadata('p1', emotives=[{'h': 1}], metadata={'tag': ['x']})

    redis.write_metadata.assert_called_once_with(
        pattern_name='p1', frequency=None,
        emotives=[{'h': 1}], metadata={'tag': ['x']},
    )
    clickhouse.write_pattern_metadata.assert_called_once()
    ch_kwargs = clickhouse.write_pattern_metadata.call_args.kwargs
    assert ch_kwargs['name'] == 'p1'
    assert ch_kwargs['emotives'] == [{'h': 1}]
    assert ch_kwargs['metadata'] == {'tag': ['x']}
    # No prior row, so metric fields are None
    assert ch_kwargs['entropy'] is None
    assert ch_kwargs['tf_vector'] is None


def test_upsert_pattern_metadata_preserves_existing_metrics(writers):
    redis, clickhouse = writers
    clickhouse.get_pattern_metadata_batch.return_value = {
        'p1': {
            'name': 'p1',
            'emotives': [{'old': 1}], 'metadata': {},
            'entropy': 2.5, 'normalized_entropy': 0.6,
            'global_normalized_entropy': 0.4, 'tf_vector': {'a': 0.5},
        }
    }
    r = _router(redis, clickhouse, dual_write=True, read_from='redis')

    r.upsert_pattern_metadata('p1', emotives=[{'new': 1}], metadata={})

    ch_kwargs = clickhouse.write_pattern_metadata.call_args.kwargs
    assert ch_kwargs['emotives'] == [{'new': 1}]
    # Previously-computed metrics carried forward in the new row
    assert ch_kwargs['entropy'] == 2.5
    assert ch_kwargs['normalized_entropy'] == 0.6
    assert ch_kwargs['tf_vector'] == {'a': 0.5}


def test_upsert_pattern_metadata_redis_only_does_not_touch_clickhouse(writers):
    redis, clickhouse = writers
    r = _router(redis, clickhouse, dual_write=False, read_from='redis')

    r.upsert_pattern_metadata('p1', emotives=[], metadata={})

    redis.write_metadata.assert_called_once()
    clickhouse.write_pattern_metadata.assert_not_called()
    clickhouse.get_pattern_metadata_batch.assert_not_called()


def test_upsert_pattern_metadata_clickhouse_only_does_not_touch_redis(writers):
    redis, clickhouse = writers
    clickhouse.get_pattern_metadata_batch.return_value = {}
    r = _router(redis, clickhouse, dual_write=False, read_from='clickhouse')

    r.upsert_pattern_metadata('p1', emotives=[], metadata={})

    redis.write_metadata.assert_not_called()
    clickhouse.write_pattern_metadata.assert_called_once()


def test_update_precomputed_metrics_batch_dual_write(writers):
    redis, clickhouse = writers
    clickhouse.get_pattern_metadata_batch.return_value = {
        'p1': {'name': 'p1', 'emotives': [{'k': 1}], 'metadata': {'t': ['x']}}
    }
    redis.write_precomputed_metrics_batch.return_value = 1
    r = _router(redis, clickhouse, dual_write=True, read_from='redis')

    metrics = [{
        'pattern_name': 'p1',
        'entropy': 1.1, 'normalized_entropy': 0.4,
        'global_normalized_entropy': 0.3, 'tf_vector': {'a': 1.0},
    }]
    written = r.update_precomputed_metrics_batch(metrics)

    redis.write_precomputed_metrics_batch.assert_called_once_with(metrics)
    clickhouse.write_pattern_metadata_batch.assert_called_once()
    rows = clickhouse.write_pattern_metadata_batch.call_args.args[0]
    assert len(rows) == 1
    assert rows[0]['name'] == 'p1'
    # Emotives + metadata preserved from prior read
    assert rows[0]['emotives'] == [{'k': 1}]
    assert rows[0]['metadata'] == {'t': ['x']}
    # New metric fields written
    assert rows[0]['entropy'] == 1.1
    assert rows[0]['tf_vector'] == {'a': 1.0}
    assert written == 1


# ── Deletes ───────────────────────────────────────────────────────────


def test_metadata_migration_config_reads_env_vars(monkeypatch):
    """Regression: Pydantic v2 ignores `json_schema_extra={'env': ...}`. The fields
    must be wired via `validation_alias` or env vars are silently ignored —
    which would cause Phase 4/5 cutovers to no-op even though deployments set
    the env vars correctly."""
    monkeypatch.setenv('KATO_METADATA_DUAL_WRITE', 'false')
    monkeypatch.setenv('KATO_METADATA_READ_FROM', 'clickhouse')
    monkeypatch.setenv('KATO_METADATA_READ_VERIFY', 'true')

    cfg = MetadataMigrationConfig()
    assert cfg.dual_write is False
    assert cfg.read_from == 'clickhouse'
    assert cfg.read_verify is True


def test_metadata_migration_config_defaults_safe(monkeypatch):
    """Defaults must be the safe rollout state: write both, read from Redis."""
    for var in ('KATO_METADATA_DUAL_WRITE', 'KATO_METADATA_READ_FROM', 'KATO_METADATA_READ_VERIFY'):
        monkeypatch.delenv(var, raising=False)

    cfg = MetadataMigrationConfig()
    assert cfg.dual_write is True
    assert cfg.read_from == 'redis'
    assert cfg.read_verify is False


def test_delete_pattern_metadata_deletes_from_both(writers):
    redis, clickhouse = writers
    redis.client = MagicMock()
    r = _router(redis, clickhouse, dual_write=False, read_from='redis')

    r.delete_pattern_metadata('p1')

    # Redis: deletes all 6 moved key families, but NOT frequency
    deleted_keys = [c.args[0] for c in redis.client.delete.call_args_list]
    assert 'kb_test:emotives:p1' in deleted_keys
    assert 'kb_test:metadata:p1' in deleted_keys
    assert 'kb_test:entropy:p1' in deleted_keys
    assert 'kb_test:tf_vector:p1' in deleted_keys
    assert all('frequency' not in k for k in deleted_keys), "Frequency key must not be deleted by router"
    # ClickHouse: always called
    clickhouse.delete_pattern_metadata.assert_called_once_with('p1')
