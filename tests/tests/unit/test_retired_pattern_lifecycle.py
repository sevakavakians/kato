import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

from kato.api.endpoints.sessions import router
from kato.storage.redis_writer import RedisWriter
from kato.workers.pattern_processor import PatternProcessor

RETIRED = 'a' * 40
ACTIVE = 'b' * 40


class _RegistryPipeline:
    def __init__(self, client):
        self.client = client
        self.commands = []

    def hsetnx(self, *args):
        self.commands.append(('hsetnx', args))
        return self

    def execute(self):
        return [getattr(self.client, command)(*args) for command, args in self.commands]


class RegistryRedis:
    def __init__(self):
        self.hashes = {}

    def pipeline(self, transaction=True):
        return _RegistryPipeline(self)

    def hsetnx(self, key, field, value):
        values = self.hashes.setdefault(key, {})
        if field in values:
            return 0
        values[field] = value
        return 1

    def hmget(self, key, fields):
        values = self.hashes.get(key, {})
        return [values.get(field) for field in fields]

    def hkeys(self, key):
        return list(self.hashes.get(key, {}))

    def exists(self, key):
        return int(bool(self.hashes.get(key)))


def _bare_processor(redis_writer, predictions=None):
    processor = object.__new__(PatternProcessor)
    processor.superkb = SimpleNamespace(redis_writer=redis_writer)
    processor.predictions = list(predictions or [])
    return processor


def test_retired_pattern_disappears_immediately_without_physical_deletion():
    redis = RegistryRedis()
    writer = RedisWriter('level-2-node', redis)
    other_node_writer = RedisWriter('other-node', redis)
    source_rows = {
        RETIRED: [['base-a'], ['base-b']],
        ACTIVE: [['base-a'], ['base-c']],
    }
    original_rows = {
        name: [list(event) for event in data]
        for name, data in source_rows.items()
    }
    processor = _bare_processor(
        writer,
        [{'name': RETIRED, 'potential': 9.0}, {'name': ACTIVE, 'potential': 1.0}],
    )

    first = processor.retire_patterns([f'PTRN|{RETIRED}'])
    second = processor.retire_patterns([RETIRED])

    assert first['retired'] == [RETIRED]
    assert second['already_retired'] == [RETIRED]
    assert processor.predictions == [{'name': ACTIVE, 'potential': 1.0}]
    assert source_rows == original_rows
    assert other_node_writer.get_retired_pattern_ids([RETIRED]) == set()


def test_single_symbol_retirement_happens_before_max_predictions(monkeypatch):
    class FastWriter:
        def get_retired_pattern_ids(self, names):
            return {RETIRED} if RETIRED in names else set()

        def get_metadata_batch(self, names):
            return {name: {'name': name, 'frequency': 1, 'emotives': []} for name in names}

    class QueryResult:
        result_rows = [
            (RETIRED, [['seed'], ['retired-result']], 2),
            (ACTIVE, [['seed'], ['active-result']], 2),
        ]

    clickhouse_client = SimpleNamespace(query=lambda _query, **_kwargs: QueryResult())
    monkeypatch.setattr(
        'kato.storage.connection_manager.get_clickhouse_client',
        lambda: clickhouse_client,
    )

    processor = object.__new__(PatternProcessor)
    processor.name = 'retirement-test'
    processor.use_token_matching = True
    processor.max_predictions = 1
    processor.superkb = SimpleNamespace(
        id='level-2-node',
        redis_writer=FastWriter(),
        metadata_router=FastWriter(),
        clickhouse_writer=SimpleNamespace(flush_if_pending=lambda: 0),
    )
    processor._compute_affinity_weights = lambda *_args, **_kwargs: None

    predictions = asyncio.run(processor._predict_single_symbol_fast('seed'))

    assert [prediction['name'] for prediction in predictions] == [ACTIVE]


class LifecycleRedisWriter:
    def __init__(self, patterns):
        self.records = {}
        self.patterns = set(patterns)
        self.metadata = {
            name: {'name': name, 'frequency': 1, 'emotives': [], 'metadata': {}}
            for name in patterns
        }
        self.purge_calls = []
        self.metrics_deleted = 0

    @staticmethod
    def normalize_pattern_name(name):
        return name[5:] if name.startswith('PTRN|') else name

    def retire_patterns(self, names):
        retired = []
        already = []
        for raw_name in names:
            name = self.normalize_pattern_name(raw_name)
            if name in self.records:
                already.append(name)
            else:
                self.records[name] = {'state': 'retired'}
                retired.append(name)
        return {'retired': retired, 'already_retired': already}

    def get_retired_pattern_ids(self, names=None):
        if names is None:
            return set(self.records)
        return {
            self.normalize_pattern_name(name)
            for name in names
            if self.normalize_pattern_name(name) in self.records
        }

    def get_retirement_records(self, names):
        return {
            self.normalize_pattern_name(name): self.records[self.normalize_pattern_name(name)]
            for name in names
            if self.normalize_pattern_name(name) in self.records
        }

    def get_metadata_batch(self, names):
        return {name: self.metadata[name] for name in names if name in self.metadata}

    def pattern_exists(self, name):
        return name in self.patterns

    def has_pattern_records(self, name):
        return name in self.patterns or name in self.metadata

    def has_pattern_affinity_ledger(self, _name):
        return False

    def get_pattern_affinity_contribution(self, _name):
        return {}

    def prepare_pattern_purge(self, name, snapshot):
        self.records[name] = {'state': 'prepared', 'snapshot': snapshot}
        return self.records[name]

    def purge_pattern_records(self, name):
        if self.records[name]['state'] in {'redis_cleaned', 'purged'}:
            return False
        self.purge_calls.append(name)
        self.patterns.discard(name)
        self.metadata.pop(name, None)
        self.records[name]['state'] = 'redis_cleaned'
        return True

    def purge_patterns_from_prediction_records(self, _names):
        return 0

    def delete_all_precomputed_metrics(self):
        self.metrics_deleted += 1
        return 4

    def verify_pattern_records_absent(self, name):
        return name not in self.patterns and name not in self.metadata

    def mark_pattern_purged(self, name):
        if self.records[name]['state'] == 'purged':
            return False
        self.records[name] = {'state': 'purged'}
        return True


class LifecycleClickHouseWriter:
    def __init__(self, rows):
        self.rows = dict(rows)
        self.purge_calls = []

    def get_patterns_data_batch(self, names):
        return {name: self.rows[name] for name in names if name in self.rows}

    def purge_patterns(self, names):
        self.purge_calls.append(list(names))
        for name in names:
            self.rows.pop(name, None)
        return len(names)

    def get_present_pattern_names(self, names):
        return set(names) & set(self.rows)

    def get_present_lsh_pattern_names(self, _names):
        return set()

    def get_present_metadata_pattern_names(self, _names):
        return set()

    def invalidate_precomputed_metrics(self):
        return 0


class LifecycleSearcher:
    redis_cache = None

    def __init__(self):
        self.rebuild_calls = []

    def rebuild_after_pattern_purge(self, names):
        self.rebuild_calls.append(list(names))
        return True

    def patterns_absent_from_indices(self, _names):
        return True


def _lifecycle_processor():
    rows = {
        RETIRED: {'name': RETIRED, 'pattern_data': [['base-a'], ['base-b']], 'length': 2},
        ACTIVE: {'name': ACTIVE, 'pattern_data': [['base-a'], ['base-c']], 'length': 2},
    }
    redis_writer = LifecycleRedisWriter(rows)
    clickhouse_writer = LifecycleClickHouseWriter(rows)
    processor = object.__new__(PatternProcessor)
    processor.superkb = SimpleNamespace(
        redis_writer=redis_writer,
        metadata_router=redis_writer,
        clickhouse_writer=clickhouse_writer,
    )
    processor.patterns_searcher = LifecycleSearcher()
    processor.query_manager = Mock()
    processor.metrics_cache_manager = None
    processor._global_metadata_cache = {'stale': True}
    processor.predictions = [
        {'name': RETIRED, 'potential': 2.0},
        {'name': ACTIVE, 'potential': 1.0},
    ]
    return processor, redis_writer, clickhouse_writer


def test_batch_purge_removes_only_tombstoned_patterns():
    processor, redis_writer, clickhouse_writer = _lifecycle_processor()
    processor.retire_patterns([RETIRED])

    result = asyncio.run(processor.purge_retired_patterns([RETIRED, ACTIVE]))

    assert result['purged'] == [RETIRED]
    assert result['skipped_not_retired'] == [ACTIVE]
    assert clickhouse_writer.purge_calls == [[RETIRED]]
    assert ACTIVE in clickhouse_writer.rows
    assert redis_writer.records[RETIRED] == {'state': 'purged'}
    assert RETIRED not in redis_writer.patterns
    assert result['precomputed_metrics_deleted'] == 4


def test_repeated_retire_and_purge_calls_are_safe():
    processor, redis_writer, clickhouse_writer = _lifecycle_processor()

    assert processor.retire_patterns([RETIRED])['retired'] == [RETIRED]
    assert processor.retire_patterns([RETIRED])['already_retired'] == [RETIRED]
    first = asyncio.run(processor.purge_retired_patterns([RETIRED]))
    second = asyncio.run(processor.purge_retired_patterns([RETIRED]))

    assert first['purged'] == [RETIRED]
    assert second['purged'] == []
    assert second['already_purged'] == [RETIRED]
    assert clickhouse_writer.purge_calls == [[RETIRED]]
    assert redis_writer.purge_calls == [RETIRED]
    assert redis_writer.records[RETIRED] == {'state': 'purged'}


def test_tombstone_is_retained_when_index_absence_is_not_proven():
    processor, redis_writer, _clickhouse_writer = _lifecycle_processor()
    processor.retire_patterns([RETIRED])
    processor.patterns_searcher.rebuild_after_pattern_purge = lambda _names: False

    result = asyncio.run(processor.purge_retired_patterns([RETIRED]))

    assert result['status'] == 'partial'
    assert result['purged'] == []
    assert RETIRED in result['failed']
    assert redis_writer.records[RETIRED]['state'] == 'redis_cleaned'
    assert redis_writer.get_retired_pattern_ids([RETIRED]) == {RETIRED}


def test_node_without_tombstones_is_bit_for_bit_unchanged_and_api_is_scoped():
    redis = RegistryRedis()
    writer = RedisWriter('untouched-node', redis)
    processor = _bare_processor(writer)
    predictions = [
        {'name': RETIRED, 'potential': 3.0},
        {'name': ACTIVE, 'potential': 2.0},
    ]

    assert processor.filter_retired_predictions(predictions) is predictions

    routes = {(route.path, tuple(sorted(route.methods))) for route in router.routes}
    assert ('/sessions/{session_id}/patterns/retire', ('POST',)) in routes
    assert ('/sessions/{session_id}/patterns/purge-retired', ('POST',)) in routes
