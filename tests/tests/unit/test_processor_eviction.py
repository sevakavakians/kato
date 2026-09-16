"""Guard for LRU processor eviction.

``ProcessorManager._evict_oldest`` used to call ``delete_collection()`` on the
evicted processor's Qdrant indexer unconditionally. ``vectors_{processor_id}``
is persistent per-node storage, not a cache, so pushing a node out of the
in-memory LRU permanently destroyed its embeddings -- reachable by anyone able
to create ``max_processors`` (100) processors with distinct node ids.

The pattern-database cleanup directly below it was always gated on a ``test_``
prefix, and the TTL path (``cleanup_expired_processors``) never deleted Qdrant
at all; these tests pin the eviction path to that same behaviour.
"""

from collections import OrderedDict
from datetime import datetime, timezone

from kato.processors.processor_manager import ProcessorManager


class _FakeIndexer:
    def __init__(self):
        self.delete_called = False

    def delete_collection(self):
        self.delete_called = True


class _FakeSuperKB:
    def __init__(self):
        self.dropped = False

    def drop_database(self):
        self.dropped = True

    def close(self):
        pass


class _FakeVectorProcessor:
    def __init__(self, indexer):
        self.vector_indexer = indexer


class _FakePatternProcessor:
    def __init__(self, superkb):
        self.superkb = superkb


class _FakeProcessor:
    def __init__(self):
        self.vector_indexer = _FakeIndexer()
        self.superkb = _FakeSuperKB()
        self.vector_processor = _FakeVectorProcessor(self.vector_indexer)
        self.pattern_processor = _FakePatternProcessor(self.superkb)


def _manager_with(processor_id: str) -> tuple[ProcessorManager, _FakeProcessor]:
    manager = ProcessorManager.__new__(ProcessorManager)
    processor = _FakeProcessor()
    # Same record shape get_processor() stores, so the eviction log line works.
    manager.processors = OrderedDict({
        processor_id: {
            'processor': processor,
            'node_id': processor_id,
            'created_at': datetime.now(timezone.utc),
            'last_accessed': datetime.now(timezone.utc),
            'access_count': 1,
        }
    })
    return manager, processor


def test_evicting_a_real_node_never_deletes_its_vectors():
    manager, processor = _manager_with('node0_kato')

    manager._evict_oldest()

    assert not processor.vector_indexer.delete_called, (
        "Eviction deleted a live node's Qdrant collection. vectors_* is "
        "persistent tenant storage, not a cache."
    )
    assert not processor.superkb.dropped
    assert 'node0_kato' not in manager.processors, "processor should still be evicted"


def test_evicting_a_test_processor_still_cleans_up():
    manager, processor = _manager_with('test_abc_kato')

    manager._evict_oldest()

    assert processor.vector_indexer.delete_called
    assert processor.superkb.dropped


def test_evicting_an_empty_manager_is_a_noop():
    manager = ProcessorManager.__new__(ProcessorManager)
    manager.processors = OrderedDict()
    manager._evict_oldest()  # must not raise
