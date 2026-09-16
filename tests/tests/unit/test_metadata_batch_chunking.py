"""Pattern metadata lookups must be chunked.

The names go into an ``IN`` list that ClickHouse expands into the statement
text, and it rejects any statement over max_query_size (262144 bytes by
default) with "Max query size exceeded". At ~42 bytes per quoted SHA1 name that
ceiling is reached around 6000 patterns.

The failure is silent from the caller's side: ClickHouseWriter logs and returns
{}, so every prediction quietly falls back to frequency=1 and default metrics
instead of erroring. Nothing in the suite noticed, because the corpora tests
build are far below the limit -- hence this unit test, which does not need one.
"""

import pytest

from kato.searches.pattern_search import METADATA_CHUNK_SIZE, PatternSearcher


class _RecordingRouter:
    """Stands in for MetadataRouter, recording the batch sizes it is asked for."""

    def __init__(self):
        self.calls = []

    def get_metadata_batch(self, names):
        self.calls.append(list(names))
        return {name: {'name': name, 'frequency': len(name)} for name in names}


@pytest.fixture
def searcher_with_router():
    searcher = PatternSearcher.__new__(PatternSearcher)
    router = _RecordingRouter()
    searcher._metadata_router = router
    return searcher, router


def test_large_lookups_are_split_into_chunks(searcher_with_router):
    searcher, router = searcher_with_router
    names = [f"{i:040x}" for i in range(6000)]

    result = searcher._load_metadata_batch(names)

    assert router.calls, "the router should have been consulted"
    assert max(len(c) for c in router.calls) <= METADATA_CHUNK_SIZE, (
        f"a chunk exceeded METADATA_CHUNK_SIZE ({METADATA_CHUNK_SIZE}); "
        f"ClickHouse will reject it with 'Max query size exceeded'"
    )
    # Every name looked up exactly once, and every result merged through.
    assert [n for call in router.calls for n in call] == names
    assert len(result) == len(names)
    assert result[names[0]]['frequency'] == len(names[0])


def test_small_lookups_use_a_single_round_trip(searcher_with_router):
    searcher, router = searcher_with_router
    names = [f"{i:040x}" for i in range(10)]

    result = searcher._load_metadata_batch(names)

    assert len(router.calls) == 1, "a small lookup should not be split"
    assert len(result) == 10


def test_exactly_one_chunk_is_not_split(searcher_with_router):
    searcher, router = searcher_with_router
    names = [f"{i:040x}" for i in range(METADATA_CHUNK_SIZE)]

    searcher._load_metadata_batch(names)

    assert len(router.calls) == 1


def test_empty_lookup_does_not_touch_the_router(searcher_with_router):
    searcher, router = searcher_with_router
    assert searcher._load_metadata_batch([]) == {}
    assert router.calls == []


def test_missing_router_returns_empty():
    searcher = PatternSearcher.__new__(PatternSearcher)
    searcher._metadata_router = None
    searcher.redis_client = None
    searcher.clickhouse_client = None
    assert searcher._load_metadata_batch([f"{i:040x}" for i in range(3)]) == {}
