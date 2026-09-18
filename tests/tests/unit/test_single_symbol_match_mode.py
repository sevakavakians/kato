import asyncio
from types import SimpleNamespace

from kato.config.session_config import SessionConfiguration
from kato.workers.pattern_processor import PatternProcessor

PATTERN = 'a' * 40


class _Writer:
    def get_retired_pattern_ids(self, _names):
        return set()

    def get_metadata_batch(self, names):
        return {
            name: {'name': name, 'frequency': 1, 'emotives': []}
            for name in names
        }


class _QueryResult:
    result_rows = [
        (PATTERN, [['alpha', 'seed'], ['result']], 3),
    ]


def _processor(monkeypatch, mode):
    captured = []

    def query(statement, parameters):
        captured.append((statement, parameters))
        return _QueryResult()

    monkeypatch.setattr(
        'kato.storage.connection_manager.get_clickhouse_client',
        lambda: SimpleNamespace(query=query),
    )
    processor = object.__new__(PatternProcessor)
    processor.name = 'single-symbol-mode-test'
    processor.use_token_matching = True
    processor.max_predictions = 10
    processor.superkb = SimpleNamespace(
        id='level-2-node',
        redis_writer=_Writer(),
        metadata_router=_Writer(),
        clickhouse_writer=SimpleNamespace(flush_if_pending=lambda: 0),
    )
    processor.patterns_searcher = SimpleNamespace(
        session_config=SessionConfiguration(single_symbol_match_mode=mode)
    )
    processor._compute_affinity_weights = lambda *_args, **_kwargs: None
    return processor, captured


def test_default_mode_remains_first_token(monkeypatch):
    processor, captured = _processor(monkeypatch, None)

    predictions = asyncio.run(processor._predict_single_symbol_fast('seed'))

    assert predictions == []
    assert "first_token = %(first_token)s" in captured[0][0]
    assert captured[0][1]["first_token"] == "seed"
    assert 'has(pattern_data[1]' not in captured[0][0]


def test_first_event_contains_returns_nonleading_member(monkeypatch):
    processor, captured = _processor(monkeypatch, 'first_event_contains')

    predictions = asyncio.run(processor._predict_single_symbol_fast('seed'))

    assert [prediction['name'] for prediction in predictions] == [PATTERN]
    assert "has(pattern_data[1], %(first_token)s)" in captured[0][0]
    assert captured[0][1]["first_token"] == "seed"


def test_session_setting_round_trips_and_validates():
    config = SessionConfiguration(single_symbol_match_mode='first_event_contains')

    assert config.validate() is True
    assert config.get_config_only()['single_symbol_match_mode'] == 'first_event_contains'
    restored = SessionConfiguration.from_dict(config.to_dict())
    assert restored.single_symbol_match_mode == 'first_event_contains'


def test_invalid_session_setting_is_rejected():
    config = SessionConfiguration(single_symbol_match_mode='contains_any_event')

    assert config.validate() is False
