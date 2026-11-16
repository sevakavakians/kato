"""
total_pattern_frequencies is the sum of every pattern's frequency.

`{kb_id}:global:total_pattern_frequencies` is the F in `bayesian_prior` (f / F),
`good_odds` and `confluence`, so it has to count every learn: one for a new
pattern and one for each time a known pattern is learned again. Every path that
writes a pattern's frequency keeps it so -- the learn path, purge, and the two
direct writes -- and scripts/recount_pattern_frequencies.py restores it on a node
whose counter does not hold the sum.

These run against a real Redis, like the purge tests, because the behaviour under
test is Redis's own: pipelines, Lua atomicity and optimistic transactions.
"""

import importlib.util
import os
import sys
import uuid
from collections import Counter
from itertools import chain
from pathlib import Path

import pytest
import redis

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from kato.storage.redis_writer import RedisWriter, escape_glob

REDIS_URL = os.environ.get("KATO_TEST_REDIS_URL", "redis://localhost:6379/0")
REPO_ROOT = Path(__file__).resolve().parents[3]

PATTERN_A = 'a' * 40
PATTERN_B = 'b' * 40
PATTERN_C = 'c' * 40


def _load_recount_script():
    path = REPO_ROOT / "scripts" / "recount_pattern_frequencies.py"
    spec = importlib.util.spec_from_file_location("recount_pattern_frequencies", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


recount_script = _load_recount_script()


@pytest.fixture
def writer():
    """A RedisWriter on a throwaway kb_id, with every key removed afterwards."""
    try:
        client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
        client.ping()
    except redis.exceptions.ConnectionError:
        pytest.skip("Redis not available")
    kb_id = f"test_total_{uuid.uuid4().hex[:8]}_kato"
    yield RedisWriter(kb_id, client)
    keys = list(client.scan_iter(match=f"{escape_glob(kb_id)}:*", count=1000))
    if keys:
        client.delete(*keys)


def _learn(writer, pattern_name, pattern_data, times=1):
    """The learn path's Redis writes, branch chosen by SETNX as learnPattern does."""
    symbols = list(chain(*pattern_data))
    symbol_counts = Counter(symbols)
    for _ in range(times):
        is_new = bool(writer.client.set(f"{writer.kb_id}:frequency:{pattern_name}", 1, nx=True))
        if not is_new:
            writer.increment_frequency(pattern_name)
        writer.batch_update_symbol_stats(
            symbol_counts=dict(symbol_counts),
            pattern_name=pattern_name,
            is_new_pattern=is_new,
            total_symbol_count=len(symbols),
        )
    return dict(symbol_counts)


def _totals(writer):
    metadata = writer.get_global_metadata()
    return metadata['total_pattern_frequencies'], metadata['total_unique_patterns']


def _sum_of_frequencies(writer):
    keys = list(writer.client.scan_iter(match=f"{escape_glob(writer.kb_id)}:frequency:*", count=1000))
    return sum(int(value) for value in writer.client.mget(keys)) if keys else 0


def _purge(writer, pattern_name, symbol_counts):
    writer.retire_patterns([pattern_name])
    snapshot = writer.build_purge_snapshot(pattern_name, symbol_counts, {})
    assert writer.prepare_pattern_purge(pattern_name, snapshot) == 'prepared'
    return writer.purge_pattern_records(pattern_name)


# ── the learn path ─────────────────────────────────────────────────────

def test_every_learn_adds_one_whether_the_pattern_is_new_or_known(writer):
    _learn(writer, PATTERN_A, [['alpha'], ['beta']])
    assert _totals(writer) == (1, 1)

    _learn(writer, PATTERN_A, [['alpha'], ['beta']], times=4)      # the same pattern, four more times
    assert _totals(writer) == (5, 1), "a re-learn adds to the frequency total, not to the pattern count"

    _learn(writer, PATTERN_B, [['gamma']], times=2)
    assert _totals(writer) == (7, 2)
    assert _sum_of_frequencies(writer) == 7


def test_the_total_is_what_a_prior_divides_by(writer):
    """f / F is a share: the priors of every pattern in the node add up to 1."""
    _learn(writer, PATTERN_A, [['alpha']], times=50)
    _learn(writer, PATTERN_B, [['beta']], times=3)
    _learn(writer, PATTERN_C, [['gamma']])
    total, _ = _totals(writer)
    frequencies = writer.get_frequency_batch([PATTERN_A, PATTERN_B, PATTERN_C])
    assert total == 54
    assert sum(frequency / total for frequency in frequencies.values()) == pytest.approx(1.0)
    assert frequencies[PATTERN_A] / total == pytest.approx(50 / 54)


# ── purge ──────────────────────────────────────────────────────────────

def test_purge_takes_out_every_learn_of_the_pattern(writer):
    _learn(writer, PATTERN_B, [['beta']], times=2)
    counts = _learn(writer, PATTERN_A, [['alpha', 'alpha'], ['beta']], times=3)
    assert _totals(writer) == (5, 2)

    assert _purge(writer, PATTERN_A, counts) == 'cleaned'

    assert _totals(writer) == (2, 1)
    assert _sum_of_frequencies(writer) == 2


def test_purging_the_only_pattern_leaves_no_counter_behind(writer):
    counts = _learn(writer, PATTERN_A, [['alpha']], times=6)
    assert _purge(writer, PATTERN_A, counts) == 'cleaned'
    assert writer.client.get(f"{writer.kb_id}:global:total_pattern_frequencies") is None
    assert writer.client.get(f"{writer.kb_id}:global:total_unique_patterns") is None


def test_purge_refuses_a_counter_that_never_counted_the_re_learns(writer):
    """A counter below the pattern's frequency cannot be subtracted from correctly.

    That is the state of a node whose counter went up only for new patterns:
    three learns of one pattern, counter 1. The purge says what to do and
    writes nothing; after a recount it goes through.
    """
    counts = _learn(writer, PATTERN_A, [['alpha'], ['beta']], times=3)
    total_key = f"{writer.kb_id}:global:total_pattern_frequencies"
    writer.client.set(total_key, 1)
    frequencies_before = dict(writer.client.hgetall(f"{writer.kb_id}:symbols:freq"))

    writer.retire_patterns([PATTERN_A])
    snapshot = writer.build_purge_snapshot(PATTERN_A, counts, {})
    assert writer.prepare_pattern_purge(PATTERN_A, snapshot) == 'prepared'
    with pytest.raises(redis.exceptions.ResponseError, match='recount_pattern_frequencies'):
        writer.purge_pattern_records(PATTERN_A)

    assert writer.client.get(total_key) == '1'
    assert writer.get_frequency(PATTERN_A) == 3
    assert writer.client.hgetall(f"{writer.kb_id}:symbols:freq") == frequencies_before

    report = recount_script.recount(writer.client, writer.kb_id)
    assert report['status'] == 'recounted' and report['counted'] == 3
    assert writer.purge_pattern_records(PATTERN_A) == 'cleaned'
    assert writer.client.get(total_key) is None


# ── direct frequency writes ────────────────────────────────────────────

def test_setting_a_frequency_moves_the_total_by_the_difference(writer):
    _learn(writer, PATTERN_A, [['alpha']], times=3)
    _learn(writer, PATTERN_B, [['beta']])
    assert _totals(writer) == (4, 2)

    assert writer.set_frequency(PATTERN_A, 10) == 3, "returns the frequency it replaced"
    assert writer.get_frequency(PATTERN_A) == 10
    assert _totals(writer) == (11, 2)

    assert writer.set_frequency(PATTERN_A, 2) == 10
    assert _totals(writer) == (3, 2)
    assert _sum_of_frequencies(writer) == 3


def test_setting_a_frequency_to_zero_drops_the_key_and_its_share(writer):
    _learn(writer, PATTERN_A, [['alpha']], times=3)
    _learn(writer, PATTERN_B, [['beta']])

    assert writer.set_frequency(PATTERN_A, 0) == 3
    assert not writer.pattern_exists(PATTERN_A)
    assert _totals(writer)[0] == 1

    assert writer.set_frequency(PATTERN_A, 0) == 0, "dropping an absent counter changes nothing"
    assert _totals(writer)[0] == 1


def test_setting_a_frequency_accepts_the_display_name_and_rejects_a_negative(writer):
    _learn(writer, PATTERN_A, [['alpha']])
    writer.set_frequency(f"PTRN|{PATTERN_A}", 4)
    assert writer.get_frequency(PATTERN_A) == 4
    with pytest.raises(ValueError):
        writer.set_frequency(PATTERN_A, -1)
    assert writer.get_frequency(PATTERN_A) == 4


def test_setting_a_frequency_announces_the_change(writer):
    _learn(writer, PATTERN_A, [['alpha']])
    before = writer.get_global_metadata()['stats_version']
    writer.set_frequency(PATTERN_A, 7)
    assert writer.get_global_metadata()['stats_version'] != before


def test_large_totals_stay_integers_redis_can_increment(writer):
    _learn(writer, PATTERN_A, [['alpha']])
    writer.set_frequency(PATTERN_A, 10 ** 15)
    total_key = f"{writer.kb_id}:global:total_pattern_frequencies"
    assert writer.client.get(total_key) == str(10 ** 15)
    assert writer.client.incrby(total_key, 1) == 10 ** 15 + 1


# ── the recount script ─────────────────────────────────────────────────

def test_recount_sets_the_counter_to_the_sum_of_the_frequencies(writer):
    _learn(writer, PATTERN_A, [['alpha']], times=50)
    _learn(writer, PATTERN_B, [['beta']], times=3)
    _learn(writer, PATTERN_C, [['gamma']])
    total_key = f"{writer.kb_id}:global:total_pattern_frequencies"
    writer.client.set(total_key, 3)          # the number of patterns, as the old counter held

    report = recount_script.recount(writer.client, writer.kb_id)

    assert report == {'kb_id': writer.kb_id, 'patterns': 3, 'before': 3, 'counted': 54,
                      'written': True, 'status': 'recounted'}
    assert writer.client.get(total_key) == '54'


def test_recount_leaves_a_correct_counter_alone(writer):
    _learn(writer, PATTERN_A, [['alpha']], times=5)
    report = recount_script.recount(writer.client, writer.kb_id)
    assert report['status'] == 'unchanged' and report['written'] is False
    assert report['before'] == report['counted'] == 5


def test_recount_dry_run_writes_nothing(writer):
    _learn(writer, PATTERN_A, [['alpha']], times=5)
    total_key = f"{writer.kb_id}:global:total_pattern_frequencies"
    writer.client.set(total_key, 1)

    report = recount_script.recount(writer.client, writer.kb_id, dry_run=True)

    assert report['status'] == 'dry_run' and report['counted'] == 5 and report['written'] is False
    assert writer.client.get(total_key) == '1'


def test_recount_does_not_write_a_count_taken_while_the_node_changed(writer, monkeypatch):
    """The count is only good if nothing learned while it was taken."""
    _learn(writer, PATTERN_A, [['alpha']], times=5)
    total_key = f"{writer.kb_id}:global:total_pattern_frequencies"
    writer.client.set(total_key, 1)
    real_count = recount_script.count_pattern_frequencies

    def count_during_a_learn(client, kb_id):
        result = real_count(client, kb_id)
        _learn(writer, PATTERN_B, [['beta']])      # lands after the scan, before the write
        return result

    monkeypatch.setattr(recount_script, 'count_pattern_frequencies', count_during_a_learn)
    report = recount_script.recount(writer.client, writer.kb_id, attempts=2)

    assert report['status'] == 'busy' and report['written'] is False
    # Untouched by the script: 1 as set above, plus the two learns that raced it.
    assert writer.client.get(total_key) == '3'


def test_recount_finds_the_nodes_that_have_learned(writer):
    _learn(writer, PATTERN_A, [['alpha']])
    assert writer.kb_id in recount_script.discover_kb_ids(writer.client)


def test_recount_of_an_empty_node_writes_no_counter(writer):
    report = recount_script.recount(writer.client, writer.kb_id)
    assert report['status'] == 'unchanged' and report['counted'] == 0
    assert writer.client.get(f"{writer.kb_id}:global:total_pattern_frequencies") is None
