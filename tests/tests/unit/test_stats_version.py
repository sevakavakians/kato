"""The stats version is what keeps uvicorn workers agreeing on symbol statistics.

KATO runs several worker processes against one Redis. Each memoises the node's
symbol table (two HGETALLs over the whole vocabulary) and previously dropped it
only when *that* process served a learn. A worker that missed the learn kept
answering from stale figures, so every metric derived from them -- confluence,
normalized_entropy, global_normalized_entropy -- came back different depending on
which worker took the request. Reproduced end to end before the fix: warm all
four workers, teach 18 more patterns through one of them, and the others keep
returning the pre-learn values.

Every writer now bumps a per-node counter and readers compare it before reusing
the cache. These tests pin that contract at the unit level; the end-to-end
behaviour needs a multi-worker deployment and is not reproducible in-process.
"""

import pytest

from kato.storage.aggregation_pipelines import OptimizedQueryManager


class _RecordingPipelines:
    """Counts how many times the expensive symbol load actually runs."""

    def __init__(self, table):
        self.table = table
        self.loads = 0

    def get_all_symbols_optimized(self, collection):
        self.loads += 1
        return dict(self.table)


@pytest.fixture
def manager():
    mgr = OptimizedQueryManager.__new__(OptimizedQueryManager)
    mgr.superkb = None
    mgr.pipelines = _RecordingPipelines({"a": {"frequency": 1}})
    mgr._symbol_cache = {}
    mgr._cache_valid = False
    mgr._cached_stats_version = None
    return mgr


def test_same_version_reuses_the_cache(manager):
    manager.get_all_symbols_optimized(None, stats_version=7)
    manager.get_all_symbols_optimized(None, stats_version=7)
    manager.get_all_symbols_optimized(None, stats_version=7)
    assert manager.pipelines.loads == 1, "an unchanged version must not reload"


def test_changed_version_reloads(manager):
    manager.get_all_symbols_optimized(None, stats_version=7)
    manager.get_all_symbols_optimized(None, stats_version=8)
    assert manager.pipelines.loads == 2, (
        "a version bumped by another process must invalidate this process's cache")
    assert manager._cached_stats_version == 8


def test_version_going_backwards_also_reloads(manager):
    """Not just '>'. Any difference means the data is not what we cached."""
    manager.get_all_symbols_optimized(None, stats_version=9)
    manager.get_all_symbols_optimized(None, stats_version=4)
    assert manager.pipelines.loads == 2


def test_no_version_keeps_local_only_behaviour(manager):
    """Callers with no version to hand still get the old memoisation."""
    manager.get_all_symbols_optimized(None)
    manager.get_all_symbols_optimized(None)
    assert manager.pipelines.loads == 1


def test_unversioned_load_marks_the_stamp_unknown(manager):
    """An unversioned load must not leave a stamp a later reader would trust."""
    manager.get_all_symbols_optimized(None, stats_version=5)
    manager.invalidate_caches()
    manager.get_symbol_frequencies_batch = None  # not under test
    # Simulate the unversioned population path.
    manager._symbol_cache = {"a": {"frequency": 1}}
    manager._cache_valid = True
    manager._cached_stats_version = None
    before = manager.pipelines.loads
    manager.get_all_symbols_optimized(None, stats_version=5)
    assert manager.pipelines.loads == before + 1, (
        "a cache loaded without a version must be revalidated, not trusted")


def test_local_invalidation_still_works(manager):
    manager.get_all_symbols_optimized(None, stats_version=3)
    manager.invalidate_caches()
    manager.get_all_symbols_optimized(None, stats_version=3)
    assert manager.pipelines.loads == 2
    assert manager._cached_stats_version == 3
