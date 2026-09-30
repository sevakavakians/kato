"""Read-your-writes for patterns_data.

`ClickHouseWriter.flush()` inserts with `wait_for_async_insert=0`, so a row is
enqueued in ClickHouse's server-side async buffer and is not queryable until that
buffer flushes. ClickHouse adapts the delay between
`async_insert_busy_timeout_min_ms` and `_max_ms` (50ms and 200ms by default) and
*increases* it under load, so the window is widest exactly when traffic is
heaviest.

That was observed directly: under concurrent learn load, the single-symbol fast
path logged "No patterns found starting with symbol 'stale_head_6'" and then, 182
milliseconds later, "Found 1 patterns starting with symbol 'stale_head_6'" -- the
same query, nothing changed but time.

`ensure_visible` gates a drain on the Redis stats version so it costs nothing on a
read-only workload. These tests pin the gating, and pin that a server which
refuses the flush statement degrades quietly rather than sleeping on every read.
"""

from unittest.mock import Mock

import pytest

from kato.storage.clickhouse_writer import ClickHouseWriter


def _make_writer(kb_id='visibility-test'):
    w = ClickHouseWriter.__new__(ClickHouseWriter)
    w.kb_id = kb_id
    w.client = Mock()
    w.batch_size = 1
    w._write_buffer = []
    w._column_names = None
    w._last_drained_stats_version = ClickHouseWriter._UNDRAINED
    return w


@pytest.fixture
def writer():
    """A writer with no real ClickHouse behind it.

    `_async_flush_unavailable` is deliberately class-level -- the privilege
    belongs to the server, not to a kb_id -- so it leaks between tests unless
    restored. Saving and restoring it keeps these tests order-independent.
    """
    original = ClickHouseWriter._async_flush_unavailable
    ClickHouseWriter._async_flush_unavailable = False
    yield _make_writer()
    ClickHouseWriter._async_flush_unavailable = original


def _flush_calls(w):
    return [c for c in w.client.command.call_args_list if 'FLUSH ASYNC INSERT QUEUE' in str(c)]


def test_first_call_always_drains(writer):
    """A fresh writer has drained at no version, so it cannot assume visibility.

    This is the state on worker startup and after a processor is evicted from the
    manager's LRU: the new writer has no memory of earlier drains, and the safe
    assumption is that a write it never saw may still be buffered.
    """
    assert writer.ensure_visible(0) is True
    assert len(_flush_calls(writer)) == 1


def test_unchanged_version_does_not_drain(writer):
    """No learn since the last drain means nothing new can be buffered.

    This is what keeps a read-only workload from paying for the statement, which
    is server-global and drains every table on the node.
    """
    assert writer.ensure_visible(111) is True
    writer.client.command.reset_mock()

    for _ in range(5):
        assert writer.ensure_visible(111) is False
    assert _flush_calls(writer) == []


def test_changed_version_drains_again(writer):
    """A bumped stats version means a learn landed, so drain once more."""
    writer.ensure_visible(111)
    writer.client.command.reset_mock()

    assert writer.ensure_visible(222) is True
    assert len(_flush_calls(writer)) == 1

    assert writer.ensure_visible(222) is False, "should settle at the new version"
    assert len(_flush_calls(writer)) == 1


def test_version_reset_to_zero_still_drains(writer):
    """delete_all_metadata removes the version key; get_global_metadata reports 0.

    0 is a real value, not "unknown", so it must compare unequal to the
    nanosecond stamp we last drained at and force a drain. That is why the
    sentinel is a dedicated object rather than None or 0.
    """
    writer.ensure_visible(1790000000000000000)
    writer.client.command.reset_mock()

    assert writer.ensure_visible(0) is True
    assert len(_flush_calls(writer)) == 1


def test_refused_flush_is_latched_and_never_sleeps(writer, monkeypatch):
    """A server that refuses the statement must not cost 0.5s on every read.

    flush_async_insert_queue used to sleep 0.5s as a fallback, which is tolerable
    at a training checkpoint and ruinous once this runs per prediction.
    """
    slept = []
    monkeypatch.setattr('time.sleep', lambda s: slept.append(s))
    writer.client.command.side_effect = Exception("Not enough privileges")

    assert writer.ensure_visible(111) is True
    assert slept == [], "must not sleep on the read path"
    assert ClickHouseWriter._async_flush_unavailable is True

    writer.client.command.reset_mock()
    writer.ensure_visible(222)
    assert _flush_calls(writer) == [], "must not retry a refused statement"
    assert slept == []


def test_latch_is_shared_across_writers(writer):
    """The privilege is the server's, so one refusal applies to every kb_id."""
    writer.client.command.side_effect = Exception("Not enough privileges")
    writer.ensure_visible(111)

    other = _make_writer(kb_id='another-node')
    other.ensure_visible(999)
    assert _flush_calls(other) == []


def test_pending_client_buffer_is_also_flushed(writer):
    """batch_size is a constructor knob, so the client buffer must not be skipped.

    It is empty at the default batch_size=1, which is exactly why the old
    flush_if_pending call on this path did nothing. If anyone raises batch_size, a
    buffered row still has to reach the server before we drain it.
    """
    writer.batch_size = 50
    writer._column_names = ['kb_id', 'name']
    writer._write_buffer = [['visibility-test', 'a' * 40]]

    writer.ensure_visible(111)

    assert writer._write_buffer == [], "client buffer should have been flushed"
    assert writer.client.insert.call_count == 1
    assert len(_flush_calls(writer)) == 1
