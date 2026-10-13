"""
A session's prediction settings reach the predict path, on both entry points.

A processor is shared by every session on a node. Session settings used to reach
prediction by being swapped onto that shared processor around an await
(`get_predictions_async` set `patterns_searcher` and `max_predictions`, then
restored them), which let a concurrent request on the same node run with another
session's settings. `rank_sort_algo` was not swapped at all, so a session's
choice was ignored and every prediction was ranked by the node default. The
observe path passed no configuration, so its predictions used the node defaults
for everything.

Settings stay in the session's stored configuration. The server reads them on
each request into a `PredictionSettings` value and passes that down the predict
path as an argument; nothing on the processor changes. The session's searcher is
cached and reused until its configuration changes.
"""

import os
import sys
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from fixtures.kato_fixtures import kato_fixture as kato_fixture

from kato.config.session_config import SessionConfiguration
from kato.workers import pattern_processor as pattern_processor_module
from kato.workers.pattern_processor import PatternProcessor, PredictionSettings

# ── _prediction_settings ───────────────────────────────────────────────

def _bare_processor():
    """A PatternProcessor with only the attributes _prediction_settings reads."""
    processor = object.__new__(PatternProcessor)
    processor.kb_id = 'settings_test_kato'
    processor.max_predictions = 100
    processor.recall_threshold = 0.1
    processor.use_token_matching = True
    processor.rank_sort_algo = 'potential'
    processor.patterns_searcher = Mock(clickhouse_client=Mock(), redis_client=Mock())
    processor._session_searchers = OrderedDict()
    return processor


def test_without_config_the_node_defaults_and_shared_searcher_are_used():
    processor = _bare_processor()
    settings = processor._prediction_settings(None)
    assert settings == PredictionSettings(processor.patterns_searcher, 100, 'potential', True)


def test_session_values_override_the_node_defaults():
    processor = _bare_processor()
    config = SessionConfiguration(
        rank_sort_algo='similarity', max_predictions=5,
        recall_threshold=0.4, use_token_matching=False,
    )
    settings = processor._prediction_settings(config)

    assert settings.rank_sort_algo == 'similarity'
    assert settings.max_predictions == 5
    assert settings.use_token_matching is False
    # The request gets its own searcher, built from the session's configuration.
    assert settings.searcher is not processor.patterns_searcher
    assert settings.searcher.session_config is config
    assert settings.searcher.recall_threshold == 0.4
    assert settings.searcher.max_predictions == 5
    assert settings.searcher.use_token_matching is False


def test_unset_session_values_fall_back_to_the_node_defaults():
    processor = _bare_processor()
    settings = processor._prediction_settings(SessionConfiguration())
    assert (settings.max_predictions, settings.rank_sort_algo, settings.use_token_matching) == (
        100, 'potential', True)
    assert settings.searcher.recall_threshold == 0.1


def test_resolving_settings_does_not_change_the_processor():
    processor = _bare_processor()
    shared = processor.patterns_searcher
    processor._prediction_settings(SessionConfiguration(rank_sort_algo='frequency', max_predictions=1))
    assert processor.patterns_searcher is shared
    assert (processor.max_predictions, processor.rank_sort_algo) == (100, 'potential')


# ── per-session searcher cache ─────────────────────────────────────────

def _session_config(session_id, **values):
    return SessionConfiguration(session_id=session_id, node_id='n', **values)


def test_a_session_reuses_its_searcher_while_its_configuration_is_unchanged():
    processor = _bare_processor()
    first = processor._prediction_settings(_session_config('s1', recall_threshold=0.3)).searcher
    # Each request loads the session's configuration afresh: an equal one, not the same object.
    again = processor._prediction_settings(_session_config('s1', recall_threshold=0.3)).searcher
    assert again is first


def test_a_configuration_change_rebuilds_the_searcher():
    processor = _bare_processor()
    first = processor._prediction_settings(_session_config('s1', recall_threshold=0.3)).searcher
    changed = processor._prediction_settings(_session_config('s1', recall_threshold=0.6)).searcher
    assert changed is not first
    assert changed.recall_threshold == 0.6
    assert processor._prediction_settings(_session_config('s1', recall_threshold=0.6)).searcher is changed


def test_sessions_never_share_a_searcher_even_with_equal_configurations():
    processor = _bare_processor()
    a = processor._prediction_settings(_session_config('s1', recall_threshold=0.3)).searcher
    b = processor._prediction_settings(_session_config('s2', recall_threshold=0.3)).searcher
    assert a is not b


def test_settings_not_held_by_the_searcher_are_read_on_every_request():
    processor = _bare_processor()
    processor._prediction_settings(_session_config('s1'))
    settings = processor._prediction_settings(_session_config('s1', rank_sort_algo='frequency'))
    assert settings.rank_sort_algo == 'frequency'


def test_a_configuration_without_a_session_id_is_not_cached():
    processor = _bare_processor()
    a = processor._prediction_settings(SessionConfiguration()).searcher
    b = processor._prediction_settings(SessionConfiguration()).searcher
    assert a is not b
    assert not processor._session_searchers


def test_the_cache_drops_the_least_recently_used_session(monkeypatch):
    monkeypatch.setattr(pattern_processor_module, 'SESSION_SEARCHER_CACHE_SIZE', 2)
    processor = _bare_processor()
    processor._prediction_settings(_session_config('s1'))
    processor._prediction_settings(_session_config('s2'))
    processor._prediction_settings(_session_config('s1'))  # s2 is now the oldest
    processor._prediction_settings(_session_config('s3'))
    assert list(processor._session_searchers) == ['s1', 's3']


def test_releasing_request_data_leaves_only_the_configuration():
    processor = _bare_processor()
    searcher = processor._prediction_settings(_session_config('s1')).searcher
    searcher.patterns_cache = {'p': ['a']}
    searcher.patterns_count = 1
    searcher._pattern_strings_cache = {'p': 'a'}
    searcher.affinity_weights = {'a': 1.0}
    searcher.filter_executor = Mock(patterns_cache={'p': {'pattern_data': [['a']]}})

    searcher.release_request_data()

    assert (searcher.patterns_cache, searcher.patterns_count, searcher._pattern_strings_cache) == ({}, 0, {})
    assert searcher.affinity_weights is None
    assert searcher.filter_executor.patterns_cache == {}


# ── end to end ─────────────────────────────────────────────────────────
#
# Two patterns that `potential` and `frequency` rank in opposite orders against
# the STM [['a'], ['b']]: EXACT matches it contiguously, so its potential is
# higher; COMMON matches it with a gap, but is learned three times.

EXACT = [['a'], ['b'], ['c']]
COMMON = [['a'], ['m'], ['n'], ['b'], ['d']]
STM = [['a'], ['b']]


def _clean(name):
    return name[5:] if name.startswith('PTRN|') else name


def _learn(fixture, events, times=1):
    name = None
    for _ in range(times):
        fixture.clear_short_term_memory()
        for event in events:
            fixture.observe({'strings': event, 'vectors': [], 'emotives': {}})
        name = fixture.learn()
    return _clean(name)


def _observe_stm(fixture):
    fixture.clear_short_term_memory()
    for event in STM:
        fixture.observe({'strings': event, 'vectors': [], 'emotives': {}})


def _names(predictions):
    return [_clean(p['name']) for p in predictions]


@pytest.fixture
def two_patterns(kato_fixture):
    kato_fixture.clear_all_memory()
    exact = _learn(kato_fixture, EXACT)
    common = _learn(kato_fixture, COMMON, times=3)
    return kato_fixture, exact, common


class _OtherSession:
    """A second session on the fixture's node, with its own configuration."""

    def __init__(self, fixture, config):
        self.fixture = fixture
        response = fixture.requests_session.post(
            f"{fixture.base_url}/sessions",
            json={'node_id': fixture.processor_id, 'config': config},
        )
        response.raise_for_status()
        self.url = f"{fixture.base_url}/sessions/{response.json()['session_id']}"

    def observe_stm(self):
        self.fixture.requests_session.post(f"{self.url}/clear-stm").raise_for_status()
        for event in STM:
            self.fixture.requests_session.post(
                f"{self.url}/observe",
                json={'strings': event, 'vectors': [], 'emotives': {}},
            ).raise_for_status()

    def predictions(self):
        response = self.fixture.requests_session.get(f"{self.url}/predictions")
        response.raise_for_status()
        return response.json()['predictions']

    def close(self):
        self.fixture.requests_session.delete(self.url)


def test_the_patterns_rank_differently_by_potential_and_frequency(two_patterns):
    fixture, exact, common = two_patterns
    _observe_stm(fixture)
    by_name = {_clean(p['name']): p for p in fixture.get_predictions()}
    assert by_name[exact]['potential'] > by_name[common]['potential']
    assert by_name[common]['frequency'] > by_name[exact]['frequency']


def test_session_rank_sort_algo_orders_the_predictions(two_patterns):
    fixture, exact, common = two_patterns
    _observe_stm(fixture)
    assert _names(fixture.get_predictions())[:2] == [exact, common]

    fixture.update_config({'rank_sort_algo': 'frequency'})
    _observe_stm(fixture)
    assert _names(fixture.get_predictions())[:2] == [common, exact]


def test_observe_path_predictions_use_the_session_settings(two_patterns):
    fixture, exact, common = two_patterns
    fixture.update_config({'rank_sort_algo': 'frequency', 'max_predictions': 1})
    _observe_stm(fixture)
    # Observe-time predictions are kept on the session and served here.
    response = fixture.requests_session.get(
        f"{fixture.base_url}/sessions/{fixture.session_id}/cognition-data")
    response.raise_for_status()
    observed = response.json()['cognition_data']['predictions']
    assert _names(observed) == [common]


def test_sessions_on_one_node_rank_by_their_own_settings(two_patterns):
    fixture, exact, common = two_patterns
    other = _OtherSession(fixture, {'rank_sort_algo': 'frequency'})
    try:
        _observe_stm(fixture)
        other.observe_stm()
        assert _names(fixture.get_predictions())[:2] == [exact, common]
        assert _names(other.predictions())[:2] == [common, exact]
    finally:
        other.close()


def test_concurrent_sessions_keep_their_own_max_predictions(two_patterns):
    fixture, exact, common = two_patterns
    narrow = _OtherSession(fixture, {'max_predictions': 1})
    wide = _OtherSession(fixture, {'max_predictions': 10})
    try:
        narrow.observe_stm()
        wide.observe_stm()
        with ThreadPoolExecutor(max_workers=8) as pool:
            jobs = [(session, pool.submit(session.predictions))
                    for _ in range(20) for session in (narrow, wide)]
            counts = [(session is narrow, len(job.result())) for session, job in jobs]
        assert all(count == 1 for is_narrow, count in counts if is_narrow)
        assert all(count == 2 for is_narrow, count in counts if not is_narrow)
    finally:
        narrow.close()
        wide.close()


def test_a_searcher_setting_changed_mid_session_takes_effect(two_patterns):
    fixture, exact, common = two_patterns
    _observe_stm(fixture)
    assert set(_names(fixture.get_predictions())) >= {exact, common}

    # COMMON's similarity against [a, b] is 4/7, EXACT's 4/5: a threshold between
    # them leaves only EXACT, so the cached searcher must have been rebuilt.
    fixture.update_config({'recall_threshold': 0.7})
    _observe_stm(fixture)
    assert _names(fixture.get_predictions()) == [exact]
