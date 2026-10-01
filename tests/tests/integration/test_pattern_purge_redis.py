"""
Purge counter-reversal tests, against real Redis.

Purge is the only operation in KATO that *subtracts* from the node-level
counters, and those counters are shared by every pattern on the node. An error
of one in either direction is not confined to the purged pattern: it silently
skews the entropy and affinity of every surviving pattern that shares a symbol,
and nothing downstream detects it. These are therefore arithmetic tests, not
API tests, and they run against a real Redis because the behaviour under test is
Redis's own -- Lua atomicity, HINCRBYFLOAT's long double, and how Redis parses
the integers written back into counter keys. A fakeredis or a mock would agree
with whatever the implementation did.

Each test seeds the counters exactly as the learn path would, purges, and
asserts the node is left in the state it would have been in had the pattern
never been learned.
"""

import json
import math
import os
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
import redis

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from kato.exceptions import ConcurrencyError
from kato.storage.redis_writer import PER_PATTERN_KEY_SUFFIXES, RedisWriter, escape_glob

REDIS_URL = os.environ.get("KATO_TEST_REDIS_URL", "redis://localhost:6379/0")

PATTERN_A = 'a' * 40
PATTERN_B = 'b' * 40


@pytest.fixture
def writer():
    """A RedisWriter on a throwaway kb_id, with every key removed afterwards.

    The test_ prefix and the uuid matter: without them these tests accumulate
    counters in a shared namespace that later prediction tests then read.
    """
    client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    kb_id = f"test_purge_{uuid.uuid4().hex[:8]}_kato"
    yield RedisWriter(kb_id, client)
    keys = list(client.scan_iter(match=f"{escape_glob(kb_id)}:*", count=1000))
    if keys:
        client.delete(*keys)


def _learn(writer, pattern_name, pattern_data, emotives=None, times=1):
    """Drive the real learn-path writes, so the tests cannot encode a stale
    assumption about how counters accrue."""
    from collections import Counter
    from itertools import chain

    symbols = list(chain(*pattern_data))
    symbol_counts = Counter(symbols)
    for _ in range(times):
        # The SETNX result decides the branch, exactly as learnPattern does, so
        # that calling this again is a faithful re-learn rather than a second
        # new-pattern insert.
        is_new = bool(writer.client.set(
            f"{writer.kb_id}:frequency:{pattern_name}", 1, nx=True))
        if not is_new:
            writer.increment_frequency(pattern_name)
        writer.batch_update_symbol_stats(
            symbol_counts=dict(symbol_counts),
            pattern_name=pattern_name,
            is_new_pattern=is_new,
            total_symbol_count=len(symbols),
        )
        if emotives:
            writer.batch_update_symbol_affinity(
                symbol_names=list(symbol_counts.keys()),
                averaged_emotives=emotives,
                pattern_name=pattern_name,
            )
    return dict(symbol_counts)


def _snapshot_state(writer):
    """Everything purge is supposed to restore, in one comparable dict."""
    client = writer.client
    kb = writer.kb_id
    state = {
        'symbols_freq': client.hgetall(f"{kb}:symbols:freq"),
        'symbols_pmf': client.hgetall(f"{kb}:symbols:pmf"),
        'global_symbols': client.get(f"{kb}:global:total_symbols_in_patterns_frequencies"),
        'global_patterns': client.get(f"{kb}:global:total_pattern_frequencies"),
        'global_unique': client.get(f"{kb}:global:total_unique_patterns"),
        'indices': {},
        'affinity': {},
    }
    for key in client.scan_iter(match=f"{escape_glob(kb)}:symbol_to_patterns:*", count=1000):
        state['indices'][key] = client.smembers(key)
    for key in client.scan_iter(match=f"{escape_glob(kb)}:affinity:*", count=1000):
        state['affinity'][key] = client.hgetall(key)
    return state


def _purge(writer, pattern_name, symbol_counts, affinity=None):
    """Retire, prepare, purge -- the sequence the driver performs."""
    writer.retire_patterns([pattern_name])
    ledger = writer.get_affinity_ledger(pattern_name)
    snapshot = writer.build_purge_snapshot(
        pattern_name, symbol_counts,
        ledger if ledger is not None else (affinity or {}),
    )
    assert writer.prepare_pattern_purge(pattern_name, snapshot) == 'prepared'
    return writer.purge_pattern_records(pattern_name)


# ---------------------------------------------------------------- T1


def test_purge_restores_counters_to_pre_learn_state(writer):
    """The whole point: purging the only pattern must leave the node as new."""
    before = _snapshot_state(writer)

    counts = _learn(writer, PATTERN_A, [['alpha', 'beta'], ['alpha']],
                    emotives={'joy': 0.5})
    assert _snapshot_state(writer) != before, "fixture did not actually learn"

    assert _purge(writer, PATTERN_A, counts) == 'cleaned'

    after = _snapshot_state(writer)
    assert after['symbols_freq'] == before['symbols_freq']
    assert after['symbols_pmf'] == before['symbols_pmf']
    assert after['global_symbols'] == before['global_symbols']
    assert after['global_patterns'] == before['global_patterns']
    assert after['global_unique'] == before['global_unique']
    assert after['indices'] == before['indices']
    assert after['affinity'] == before['affinity']


# ---------------------------------------------------------------- T2


def test_purge_leaves_shared_symbols_owned_by_survivor(writer):
    """A symbol two patterns share must keep exactly the survivor's share.

    This is the case that makes purge hard: 'beta' belongs to both patterns, so
    its counters must be decremented partially, not deleted, and its index must
    keep pointing at the surviving pattern.
    """
    _learn(writer, PATTERN_B, [['beta'], ['gamma']], emotives={'joy': 0.25})
    survivor_only = _snapshot_state(writer)

    counts = _learn(writer, PATTERN_A, [['alpha', 'beta'], ['alpha']],
                    emotives={'joy': 0.5})
    assert _purge(writer, PATTERN_A, counts) == 'cleaned'

    after = _snapshot_state(writer)
    assert after['symbols_freq'] == survivor_only['symbols_freq']
    assert after['symbols_pmf'] == survivor_only['symbols_pmf']
    assert after['indices'] == survivor_only['indices']
    assert 'alpha' not in after['symbols_freq']
    assert f"{writer.kb_id}:symbol_to_patterns:alpha" not in after['indices']
    assert after['indices'][f"{writer.kb_id}:symbol_to_patterns:beta"] == {PATTERN_B}
    # Affinity is float arithmetic, so compare numerically rather than by string.
    for key, fields in survivor_only['affinity'].items():
        for name, expected in fields.items():
            assert math.isclose(float(after['affinity'][key][name]), float(expected),
                                rel_tol=1e-9, abs_tol=1e-12)


# ---------------------------------------------------------------- T3


def test_purge_reverses_frequency_weighted_share(writer):
    """symbols:freq accrues per learn; pmf accrues once. Purge must match both.

    Conflating the two is the likeliest arithmetic error, and with frequency == 1
    the two are indistinguishable -- so this learns three times.
    """
    before = _snapshot_state(writer)
    counts = _learn(writer, PATTERN_A, [['alpha', 'alpha'], ['beta']], times=3)

    assert writer.client.hget(f"{writer.kb_id}:symbols:freq", 'alpha') == '6'
    assert writer.client.hget(f"{writer.kb_id}:symbols:pmf", 'alpha') == '1'
    assert writer.get_frequency(PATTERN_A) == 3

    assert _purge(writer, PATTERN_A, counts) == 'cleaned'
    assert _snapshot_state(writer) == before


# ---------------------------------------------------------------- T4


def test_purge_writes_counters_redis_can_still_increment(writer):
    """Counters must come back as plain integers, not 1e+15.

    Lua's tostring renders large numbers in scientific notation; Redis then
    rejects the next INCRBY on that key with "value is not an integer", so the
    node's statistics freeze permanently on the first learn after a purge of a
    high-volume node. The value is written with %d to prevent this.
    """
    kb = writer.kb_id
    counts = _learn(writer, PATTERN_A, [['alpha']])
    # Push the shared counters past the 1e14 threshold where %.14g switches
    # to exponent form.
    writer.client.hset(f"{kb}:symbols:freq", 'alpha', 10 ** 15)
    writer.client.set(f"{kb}:global:total_symbols_in_patterns_frequencies", 10 ** 15)

    assert _purge(writer, PATTERN_A, counts) == 'cleaned'

    assert writer.client.hget(f"{kb}:symbols:freq", 'alpha') == '999999999999999'
    assert writer.client.get(f"{kb}:global:total_symbols_in_patterns_frequencies") == '999999999999999'
    # The real assertion: Redis still accepts arithmetic on what we wrote.
    assert writer.client.hincrby(f"{kb}:symbols:freq", 'alpha', 1) == 10 ** 15
    assert writer.client.incrby(f"{kb}:global:total_symbols_in_patterns_frequencies", 1) == 10 ** 15


# ---------------------------------------------------------------- T5


def test_purge_without_pattern_records_skips_counter_arithmetic(writer):
    """A tombstone with no learned record must not decrement anything.

    Reached when Redis was lost and rehydrated, or a pattern was retired before
    it ever landed. Subtracting a snapshot's worth of counters here would corrupt
    every other pattern on the node.
    """
    _learn(writer, PATTERN_B, [['beta']])
    before = _snapshot_state(writer)

    snapshot = writer.build_purge_snapshot(PATTERN_A, {'alpha': 1}, {})
    assert snapshot['had_pattern_record'] is False
    assert snapshot['frequency'] == 0

    writer.retire_patterns([PATTERN_A])
    assert writer.prepare_pattern_purge(PATTERN_A, snapshot) == 'prepared'
    assert writer.purge_pattern_records(PATTERN_A) == 'cleaned'

    assert _snapshot_state(writer) == before


# ---------------------------------------------------------------- T6


@pytest.mark.parametrize("value", [0.1, 1.0, 1e-9, 123.456, 98765.4321, -0.75, 1e6])
def test_affinity_reversal_leaves_no_residue(writer, value):
    """Affinity must end deleted, not at 1e-13.

    Float error scales with magnitude, so an absolute epsilon leaves a residue
    field above ~100 that no later purge can clear -- a symbol owning no patterns
    keeps a phantom emotive, which then skews affinity-weighted predictions. The
    arithmetic runs through HINCRBYFLOAT (Redis long double) and the delete
    threshold is relative.
    """
    counts = _learn(writer, PATTERN_A, [['alpha']], emotives={'joy': value}, times=4)
    key = f"{writer.kb_id}:affinity:alpha"
    assert writer.client.hexists(key, 'joy')

    assert _purge(writer, PATTERN_A, counts) == 'cleaned'
    assert writer.client.exists(key) == 0, (
        f"affinity residue for value={value}: {writer.client.hgetall(key)}"
    )


def test_affinity_reversal_preserves_unrelated_emotives(writer):
    """Purging one pattern must not disturb an emotive it never contributed."""
    _learn(writer, PATTERN_B, [['alpha']], emotives={'fear': 0.3})
    counts = _learn(writer, PATTERN_A, [['alpha']], emotives={'joy': 0.6})

    assert _purge(writer, PATTERN_A, counts) == 'cleaned'

    affinity = writer.get_symbol_affinity('alpha')
    assert 'joy' not in affinity
    assert math.isclose(affinity['fear'], 0.3, rel_tol=1e-9)


def test_affinity_reversal_tolerates_already_settled_field(writer):
    """A missing affinity field is settled, not an error.

    Two patterns contributing +x and -x drive the field to zero and the first
    purge deletes it. Erroring on the absent field would wedge the second pattern
    at 'prepared' forever, with no way to re-prepare and no way to un-retire.
    """
    counts = _learn(writer, PATTERN_A, [['alpha']], emotives={'joy': 0.5})
    writer.client.delete(f"{writer.kb_id}:affinity:alpha")

    assert _purge(writer, PATTERN_A, counts) == 'cleaned'
    assert writer.get_retirement_records([PATTERN_A])[PATTERN_A]['state'] == 'redis_cleaned'


# ---------------------------------------------------------------- T7


def test_stale_snapshot_is_rejected_without_writing(writer):
    """A pattern re-learned after preparation must abort the purge, untouched.

    The snapshot says what to subtract; if the node moved on, subtracting it
    corrupts the counters. The guard phase runs entirely before the mutation
    phase, so a rejection must leave both the counters and the tombstone state
    exactly as they were -- which is what makes re-preparing safe.
    """
    counts = _learn(writer, PATTERN_A, [['alpha', 'beta']])
    writer.retire_patterns([PATTERN_A])
    snapshot = writer.build_purge_snapshot(PATTERN_A, counts, {})
    assert writer.prepare_pattern_purge(PATTERN_A, snapshot) == 'prepared'

    # Concurrent re-learn between prepare and purge.
    _learn(writer, PATTERN_A, [['alpha', 'beta']])
    before = _snapshot_state(writer)

    with pytest.raises(ConcurrencyError):
        writer.purge_pattern_records(PATTERN_A)

    assert _snapshot_state(writer) == before
    assert writer.get_retirement_records([PATTERN_A])[PATTERN_A]['state'] == 'prepared'

    # And the documented recovery actually recovers: re-snapshot the node as it
    # now stands, return the tombstone to 'retired', prepare again.
    fresh = writer.build_purge_snapshot(PATTERN_A, counts, {})
    assert fresh['frequency'] == 2
    writer.client.hset(writer.retired_patterns_key, PATTERN_A,
                       json.dumps({'state': 'retired'}, separators=(',', ':')))
    assert writer.prepare_pattern_purge(PATTERN_A, fresh) == 'prepared'
    assert writer.purge_pattern_records(PATTERN_A) == 'cleaned'


def test_purge_requires_a_prepared_snapshot(writer):
    """Purging a merely-retired pattern must refuse rather than guess."""
    counts = _learn(writer, PATTERN_A, [['alpha']])
    writer.retire_patterns([PATTERN_A])
    before = _snapshot_state(writer)

    with pytest.raises(ConcurrencyError):
        writer.purge_pattern_records(PATTERN_A)

    assert _snapshot_state(writer) == before
    assert counts  # pattern was really learned


def test_purge_of_unretired_pattern_is_refused(writer):
    """Purge is reachable only through retirement."""
    _learn(writer, PATTERN_A, [['alpha']])
    before = _snapshot_state(writer)

    assert writer.prepare_pattern_purge(PATTERN_A, {'frequency': 1}) == 'not_retired'
    assert writer.purge_pattern_records(PATTERN_A) == 'not_retired'
    assert _snapshot_state(writer) == before


# ---------------------------------------------------------------- T8


def test_repeated_purge_does_not_subtract_twice(writer):
    """Resume safety. A retried purge must be a no-op, not a second subtraction.

    The counters are decremented and the state advanced inside one script, so
    there is no interleaving in which the first happened and the second did not.
    """
    _learn(writer, PATTERN_B, [['alpha']])
    counts = _learn(writer, PATTERN_A, [['alpha', 'beta']], emotives={'joy': 0.5})
    assert _purge(writer, PATTERN_A, counts) == 'cleaned'
    after_first = _snapshot_state(writer)

    for _ in range(3):
        assert writer.purge_pattern_records(PATTERN_A) == 'already_cleaned'
    assert _snapshot_state(writer) == after_first


def test_concurrent_purges_subtract_exactly_once(writer):
    """Eight threads racing the same purge must net one subtraction.

    Redis runs a script to completion with nothing interleaved, which is the only
    reason this holds without a lock -- and KATO does not take locks.
    """
    _learn(writer, PATTERN_B, [['alpha']])
    counts = _learn(writer, PATTERN_A, [['alpha', 'beta']], times=2,
                    emotives={'joy': 0.5})
    # alpha now carries 1 learn of PATTERN_B plus 2 of PATTERN_A.
    assert writer.client.hget(f"{writer.kb_id}:symbols:freq", 'alpha') == '3'

    writer.retire_patterns([PATTERN_A])
    snapshot = writer.build_purge_snapshot(
        PATTERN_A, counts, writer.get_affinity_ledger(PATTERN_A) or {})
    assert writer.prepare_pattern_purge(PATTERN_A, snapshot) == 'prepared'

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(
            lambda _: writer.purge_pattern_records(PATTERN_A), range(8)))

    assert results.count('cleaned') == 1, results
    assert results.count('already_cleaned') == 7, results
    # Exactly PATTERN_B's share survives -- one subtraction, not eight.
    assert writer.client.hget(f"{writer.kb_id}:symbols:freq", 'alpha') == '1'
    assert writer.client.hget(f"{writer.kb_id}:symbols:pmf", 'alpha') == '1'
    assert writer.client.get(f"{writer.kb_id}:global:total_unique_patterns") == '1'


# ---------------------------------------------------------------- T9


def test_purge_is_confined_to_its_own_node(writer):
    """A purge on one node must not touch an identically-named pattern on another.

    kb_id namespacing is the only isolation between nodes, and the purge builds
    keys by concatenation -- so this is the test that catches a missing prefix.
    """
    other_kb = f"{writer.kb_id}_neighbour"
    other = RedisWriter(other_kb, writer.client)
    try:
        other_counts = _learn(other, PATTERN_A, [['alpha', 'beta']],
                              emotives={'joy': 0.5})
        other_before = _snapshot_state(other)

        counts = _learn(writer, PATTERN_A, [['alpha', 'beta']], emotives={'joy': 0.5})
        assert _purge(writer, PATTERN_A, counts) == 'cleaned'

        assert _snapshot_state(other) == other_before
        assert other.get_frequency(PATTERN_A) == 1
        assert other.get_retired_pattern_ids([PATTERN_A]) == set()
        assert other_counts == counts
    finally:
        keys = list(writer.client.scan_iter(match=f"{escape_glob(other_kb)}:*", count=1000))
        if keys:
            writer.client.delete(*keys)


# ---------------------------------------------------------------- lifecycle


def test_per_pattern_keys_are_all_removed(writer):
    """Every key the pattern owns must be gone, and verification must agree.

    If PER_PATTERN_KEY_SUFFIXES ever drifts from what the purge script deletes,
    verification would stop looking for the key the purge stopped deleting, and
    a pattern would be marked 'purged' with a live record behind it. Both read
    the same tuple, and this asserts the tuple is complete.
    """
    kb = writer.kb_id
    counts = _learn(writer, PATTERN_A, [['alpha']], emotives={'joy': 0.5})
    assert writer.has_pattern_records(PATTERN_A)
    for suffix in PER_PATTERN_KEY_SUFFIXES:
        assert writer.client.exists(f"{kb}:{suffix}:{PATTERN_A}"), suffix

    assert _purge(writer, PATTERN_A, counts) == 'cleaned'

    assert writer.verify_pattern_records_absent(PATTERN_A) == []
    assert writer.has_pattern_records(PATTERN_A) is False
    # Nothing matching the hash may survive anywhere in the namespace.
    leftover = [k for k in writer.client.scan_iter(
        match=f"{escape_glob(kb)}:*", count=1000) if PATTERN_A in k]
    assert leftover == [writer.retired_patterns_key] or leftover == [], leftover


def test_mark_purged_drops_the_snapshot(writer):
    """The final state keeps the tombstone but not its bulky snapshot.

    The tombstone must survive -- it is what stops a later observation of the
    same sequence re-learning the hash. The snapshot must not: a heavily purged
    node would otherwise carry every purged pattern's symbol counts forever in
    one hash.
    """
    counts = _learn(writer, PATTERN_A, [['alpha', 'beta']])
    assert _purge(writer, PATTERN_A, counts) == 'cleaned'
    assert 'snapshot' in writer.get_retirement_records([PATTERN_A])[PATTERN_A]

    assert writer.mark_pattern_purged(PATTERN_A) is True

    record = writer.get_retirement_records([PATTERN_A])[PATTERN_A]
    assert record['state'] == 'purged'
    assert 'snapshot' not in record
    assert 'purged_at' in record
    assert writer.get_retired_pattern_ids([PATTERN_A]) == {PATTERN_A}
    assert writer.mark_pattern_purged(PATTERN_B) is False


def test_purge_bumps_stats_version_for_other_workers(writer):
    """Other processes cache symbol statistics; purge must invalidate that.

    Without the bump, a worker keeps serving predictions computed from counters
    that included the purged pattern until something else happens to learn.
    """
    counts = _learn(writer, PATTERN_A, [['alpha']])
    writer.retire_patterns([PATTERN_A])
    snapshot = writer.build_purge_snapshot(PATTERN_A, counts, {})
    writer.prepare_pattern_purge(PATTERN_A, snapshot)

    before = writer.client.get(writer.stats_version_key)
    time.sleep(0.001)
    assert writer.purge_pattern_records(PATTERN_A) == 'cleaned'
    assert writer.client.get(writer.stats_version_key) != before

    # An already-cleaned repeat must not bump it: workers would reload caches
    # on every retry of a no-op.
    settled = writer.client.get(writer.stats_version_key)
    assert writer.purge_pattern_records(PATTERN_A) == 'already_cleaned'
    assert writer.client.get(writer.stats_version_key) == settled


# ---------------------------------------------------------------- ledger


def test_affinity_ledger_records_the_exact_sum_contributed(writer):
    """The ledger must total what was added, across a shifting rolling average.

    Affinity sums *averaged* emotives, and the average changes each learn as the
    persistence window slides, so no recomputation from the stored pattern can
    recover it. This is why the ledger exists rather than being derived.
    """
    per_learn = [{'joy': 0.5}, {'joy': 0.25}, {'joy': 0.125, 'fear': 1.0}]
    for averaged in per_learn:
        writer.batch_update_symbol_affinity(['alpha', 'beta'], averaged,
                                            pattern_name=PATTERN_A)

    ledger = writer.get_affinity_ledger(PATTERN_A)
    assert math.isclose(ledger['joy'], 0.875, rel_tol=1e-12)
    assert math.isclose(ledger['fear'], 1.0, rel_tol=1e-12)
    # The ledger equals what each symbol actually holds -- the property purge relies on.
    for symbol in ('alpha', 'beta'):
        affinity = writer.get_symbol_affinity(symbol)
        for name, total in ledger.items():
            assert math.isclose(affinity[name], total, rel_tol=1e-12)


def test_unrecorded_ledger_is_distinguishable_from_empty(writer):
    """None means "learned before the ledger existed"; {} means "contributed nothing".

    Collapsing them makes the backfill path silently treat a pre-ledger pattern
    as having owed no affinity, so purging it leaves its contribution behind
    permanently.
    """
    assert writer.get_affinity_ledger(PATTERN_A) is None

    writer.batch_update_symbol_affinity(['alpha'], {}, pattern_name=PATTERN_A)
    assert writer.get_affinity_ledger(PATTERN_A) is None, "empty emotives wrote a ledger"

    writer.batch_update_symbol_affinity(['alpha'], {'joy': 0.0},
                                        pattern_name=PATTERN_A)
    assert writer.get_affinity_ledger(PATTERN_A) == {'joy': 0.0}


def test_affinity_ledger_is_omitted_without_a_pattern_name(writer):
    """Callers outside the learn path must stay unaffected by the ledger."""
    writer.batch_update_symbol_affinity(['alpha'], {'joy': 0.5})
    assert writer.get_affinity_ledger(PATTERN_A) is None
    assert math.isclose(writer.get_symbol_affinity('alpha')['joy'], 0.5, rel_tol=1e-12)


def test_concurrent_accrual_loses_no_contribution(writer):
    """The ledger must equal affinity even under concurrent learns.

    HSETNX and the increments run in one script. Split across a pipeline, a
    concurrent re-learner could add to affinity in the window between them and
    skip its own ledger increment -- leaving an under-counted ledger that purge
    trusts as exact, so affinity keeps a residue forever.
    """
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(
            lambda _: writer.batch_update_symbol_affinity(
                ['alpha'], {'joy': 0.1}, pattern_name=PATTERN_A),
            range(40)))

    ledger = writer.get_affinity_ledger(PATTERN_A)
    affinity = writer.get_symbol_affinity('alpha')
    assert math.isclose(ledger['joy'], 4.0, rel_tol=1e-9), ledger
    assert math.isclose(affinity['joy'], ledger['joy'], rel_tol=1e-12)


def test_purge_reverses_a_shifting_rolling_average_exactly(writer):
    """End to end: the case a recomputing purge gets wrong.

    PATTERN_A's contribution differs on each learn. A purge that recomputed the
    average from the final emotives would subtract 3 x the last value instead of
    the true sum, leaving 'alpha' -- shared with PATTERN_B -- permanently skewed.
    """
    writer.batch_update_symbol_affinity(['alpha'], {'joy': 2.0}, pattern_name=PATTERN_B)
    baseline = writer.get_symbol_affinity('alpha')['joy']

    counts = _learn(writer, PATTERN_A, [['alpha']])
    for averaged in ({'joy': 0.5}, {'joy': 0.25}, {'joy': 0.125}):
        writer.batch_update_symbol_affinity(['alpha'], averaged, pattern_name=PATTERN_A)

    assert _purge(writer, PATTERN_A, counts) == 'cleaned'

    assert math.isclose(writer.get_symbol_affinity('alpha')['joy'], baseline,
                        rel_tol=1e-9, abs_tol=1e-12)


def test_ledger_does_not_change_affinity_values(writer):
    """The ledger must be purely additive to the store.

    Affinity is a published prediction input, so introducing the ledger must not
    move a single affinity figure. This compares two nodes given identical learns,
    one journalling and one not: the affinity hashes must be byte-identical, and
    only the ledger key may differ.
    """
    other_kb = f"{writer.kb_id}_noledger"
    other = RedisWriter(other_kb, writer.client)
    try:
        learns = [{'joy': 0.5, 'fear': -0.25}, {'joy': 0.125}, {'fear': 0.75}]
        for averaged in learns:
            writer.batch_update_symbol_affinity(
                ['alpha', 'beta'], averaged, pattern_name=PATTERN_A)
            # The pre-ledger call shape: no pattern_name.
            other.batch_update_symbol_affinity(['alpha', 'beta'], averaged)

        for symbol in ('alpha', 'beta'):
            with_ledger = writer.client.hgetall(f"{writer.kb_id}:affinity:{symbol}")
            without = other.client.hgetall(f"{other_kb}:affinity:{symbol}")
            assert with_ledger == without, (symbol, with_ledger, without)

        # And the only extra key is the ledger itself.
        def suffixes(kb):
            return {k[len(kb) + 1:] for k in writer.client.scan_iter(
                match=f"{escape_glob(kb)}:*", count=1000)}

        assert suffixes(writer.kb_id) - suffixes(other_kb) == {
            f"pattern_affinity_ledger:{PATTERN_A}"
        }
        assert suffixes(other_kb) - suffixes(writer.kb_id) == set()
    finally:
        keys = list(writer.client.scan_iter(match=f"{escape_glob(other_kb)}:*", count=1000))
        if keys:
            writer.client.delete(*keys)


def test_snapshot_without_symbol_counts_would_corrupt_globals(writer):
    """Pins why the driver refuses a pattern whose ClickHouse row is missing.

    The symbol counts come from the stored pattern. If the row is gone while Redis
    still holds the frequency key, an empty symbol_counts passes every guard --
    the loops it feeds are empty -- and the script decrements the two global
    pattern counters while leaving symbols:freq, symbols:pmf, the symbol indices
    and affinity untouched. The tombstone is then marked purged and its snapshot
    discarded, so nothing can reconstruct the difference.

    This asserts that damage is real, which is what makes
    PatternProcessor._purge_one_from_redis's DataConsistencyError load-bearing
    rather than defensive. If a future change makes the empty case harmless, this
    test fails and the guard can go.
    """
    _learn(writer, PATTERN_A, [['alpha', 'alpha'], ['beta']])
    writer.retire_patterns([PATTERN_A])

    # The snapshot a missing ClickHouse row produces.
    blind = writer.build_purge_snapshot(PATTERN_A, {}, {})
    assert blind['had_pattern_record'] is True
    assert blind['symbol_counts'] == {}

    assert writer.prepare_pattern_purge(PATTERN_A, blind) == 'prepared'
    assert writer.purge_pattern_records(PATTERN_A) == 'cleaned'

    # Globals moved; per-symbol state did not. Exactly the corruption described.
    assert writer.client.get(f"{writer.kb_id}:global:total_unique_patterns") is None
    assert writer.client.hget(f"{writer.kb_id}:symbols:freq", 'alpha') == '2'
    assert writer.client.hget(f"{writer.kb_id}:symbols:pmf", 'alpha') == '1'
    assert writer.client.sismember(
        f"{writer.kb_id}:symbol_to_patterns:alpha", PATTERN_A) == 1
