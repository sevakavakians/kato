"""
Store-cleanup regression tests.

clear-all must leave nothing behind in either store for the cleared kb_id.
Two ways it silently failed to:

1. kb_ids are built from node_ids and can contain glob metacharacters
   (parametrized test ids produce ``name[case]``). RedisWriter's cleanup used
   ``SCAN MATCH {kb_id}:*`` unescaped, so ``[case]`` became a character class,
   matched nothing, and every key for that kb survived.
2. Pattern inserts go through ClickHouse's server-side async_insert queue
   (~200 ms). A learn immediately followed by clear-all could have its row
   land in the partition *after* the DROP PARTITION. patterns_metadata rows
   were never dropped at all.

Each case below is parametrized so one id contains brackets, which the fixture
carries into the real kb_id.
"""

import os
import sys

import pytest
import redis
import requests

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from fixtures.kato_fixtures import kato_fixture as kato_fixture  # noqa: F401

from kato.storage.redis_writer import RedisWriter, escape_glob

CLICKHOUSE_URL = os.environ.get("KATO_TEST_CLICKHOUSE_URL", "http://localhost:8123")
REDIS_URL = os.environ.get("KATO_TEST_REDIS_URL", "redis://localhost:6379/0")

# Short ids: kb_id = "<test name>[<id>]_<13-digit ts>_<8-char uuid>_kato" is truncated
# past 60 chars, which would cut the brackets off and defeat the point.
KB_ID_CASES = pytest.mark.parametrize("case", ["plain", "[x]"], ids=["plain", "[x]"])


def _clickhouse_count(table: str, kb_id: str) -> int:
    resp = requests.get(CLICKHOUSE_URL, params={
        "query": f"SELECT count() FROM kato.{table} WHERE kb_id = {{kb:String}}",
        "param_kb": kb_id,
    }, timeout=10)
    resp.raise_for_status()
    return int(resp.text.strip() or 0)


def _redis_keys(kb_id: str) -> list[str]:
    client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    return list(client.scan_iter(match=f"{escape_glob(kb_id)}:*", count=1000))


@KB_ID_CASES
def test_redis_writer_cleanup_handles_glob_metacharacters(case):
    """RedisWriter.delete_all_metadata removes every key even when kb_id has [ ] * ?."""
    kb_id = f"test_cleanup_{case}_{os.getpid()}"
    client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    writer = RedisWriter(kb_id, client)
    try:
        client.set(f"{kb_id}:frequency:abc", 1)
        client.set(f"{kb_id}:symbols:pmf", 1)
        client.set(f"{kb_id}:prediction:obs-1", 1)
        assert len(_redis_keys(kb_id)) == 3

        assert writer.count_patterns() == 1
        deleted = writer.delete_all_metadata()

        assert deleted == 3
        assert _redis_keys(kb_id) == []
    finally:
        keys = _redis_keys(kb_id)
        if keys:
            client.delete(*keys)


@KB_ID_CASES
def test_clear_all_purges(kato_fixture, case):
    """Learn, then clear-all immediately: no Redis keys, no ClickHouse rows remain."""
    kb_id = kato_fixture._get_actual_kb_id(kato_fixture.processor_id)
    if case == "[x]":
        assert "[" in kb_id, f"fixture should carry the bracketed id into kb_id, got {kb_id}"

    kato_fixture.clear_all_memory()
    for symbol in ("alpha", "beta", "gamma"):
        kato_fixture.observe({'strings': [symbol], 'vectors': [], 'emotives': {'joy': 0.5}})
    pattern_name = kato_fixture.learn()
    assert pattern_name

    # Immediately: the learn's insert may still be in the async_insert queue.
    kato_fixture.clear_all_memory()

    # Anything still queued would surface after the server flushes; wait past
    # async_insert_busy_timeout_ms so a late-landing row can't hide from us.
    requests.get(CLICKHOUSE_URL, params={"query": "SYSTEM FLUSH ASYNC INSERT QUEUE"}, timeout=10)

    assert _redis_keys(kb_id) == [], f"Redis keys survived clear-all for {kb_id}"
    assert _clickhouse_count("patterns_data", kb_id) == 0, "patterns_data rows survived clear-all"
    assert _clickhouse_count("patterns_metadata", kb_id) == 0, "patterns_metadata rows survived clear-all"
