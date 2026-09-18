"""Metadata reads must chunk at the point the IN list is built.

Pattern names are expanded into the statement text, and ClickHouse rejects a
statement over max_query_size (262144 bytes) -- roughly 6000 quoted SHA1 names.
The failure is silent from the caller's side: ClickHouseWriter logs and returns
{}, so predictions quietly fall back to frequency=1 and runtime entropy instead
of erroring.

Chunking used to live in one caller (PatternSearcher._load_metadata_batch) while
two others passed unbounded lists, so it now lives in
ClickHouseWriter.get_pattern_metadata_batch where the constraint actually
applies and every caller is covered.

Verified against the real server: 8000 names (328 KB of IN list) return rows
with chunking on, and return {} with it disabled, logging
"Max query size exceeded".
"""

import pytest

from kato.storage.clickhouse_writer import METADATA_QUERY_CHUNK, ClickHouseWriter

# ClickHouse's default max_query_size, and the cost of one quoted SHA1 name plus
# its separator in the IN list. These are properties of the server and the data,
# NOT of our chunk size -- the bound has to be independent of the constant under
# test, or raising that constant would raise the bar with it and the assertion
# could never fail.
CLICKHOUSE_MAX_QUERY_SIZE = 262144
BYTES_PER_NAME = 44
QUERY_OVERHEAD = 1024


class _RecordingClient:
    """Captures the size of every IN list the writer asks for."""

    def __init__(self):
        self.batch_sizes = []

    def query(self, sql, parameters=None):
        names = parameters["names"]
        self.batch_sizes.append(len(names))

        class _Result:
            result_rows = [
                (name, "[]", "{}", None, None, None, "{}") for name in names
            ]
        return _Result()

    def command(self, *args, **kwargs):
        return None


@pytest.fixture
def writer():
    w = ClickHouseWriter.__new__(ClickHouseWriter)
    w.kb_id = "test_kb"
    w.client = _RecordingClient()
    return w


def test_large_read_stays_within_the_server_limit(writer):
    """The bound is ClickHouse's, not ours."""
    names = [f"{i:040x}" for i in range(8000)]

    result = writer.get_pattern_metadata_batch(names)

    biggest = max(writer.client.batch_sizes)
    statement_bytes = biggest * BYTES_PER_NAME + QUERY_OVERHEAD
    assert statement_bytes < CLICKHOUSE_MAX_QUERY_SIZE, (
        f"largest batch was {biggest} names ~= {statement_bytes} bytes of "
        f"statement, over ClickHouse's max_query_size of "
        f"{CLICKHOUSE_MAX_QUERY_SIZE}. The server rejects it and "
        f"get_pattern_metadata_batch swallows the error and returns {{}}, so "
        f"predictions silently fall back to frequency=1 and runtime entropy."
    )
    assert len(result) == len(names), "every name must still come back"


def test_configured_chunk_is_within_the_server_limit():
    """The constant itself must be a safe value, whatever it is set to."""
    statement_bytes = METADATA_QUERY_CHUNK * BYTES_PER_NAME + QUERY_OVERHEAD
    assert statement_bytes < CLICKHOUSE_MAX_QUERY_SIZE, (
        f"METADATA_QUERY_CHUNK={METADATA_QUERY_CHUNK} implies ~{statement_bytes} "
        f"bytes of statement, over max_query_size {CLICKHOUSE_MAX_QUERY_SIZE}"
    )


def test_small_read_is_one_query(writer):
    writer.get_pattern_metadata_batch([f"{i:040x}" for i in range(10)])
    assert writer.client.batch_sizes == [10]


def test_exactly_one_chunk_is_not_split(writer):
    writer.get_pattern_metadata_batch([f"{i:040x}" for i in range(METADATA_QUERY_CHUNK)])
    assert writer.client.batch_sizes == [METADATA_QUERY_CHUNK]


def test_one_over_the_chunk_splits(writer):
    writer.get_pattern_metadata_batch([f"{i:040x}" for i in range(METADATA_QUERY_CHUNK + 1)])
    assert len(writer.client.batch_sizes) == 2
    assert max(writer.client.batch_sizes) <= METADATA_QUERY_CHUNK


def test_empty_read_issues_no_query(writer):
    assert writer.get_pattern_metadata_batch([]) == {}
    assert writer.client.batch_sizes == []
