"""Purge learned patterns left behind by earlier test runs.

Session cleanup (fixtures/redis_test_cleanup.py) removes test *sessions*, but
every suite run also *learns* patterns, and those are durable by design -- they
outlive the session that created them, which is exactly the property
test_database_persistence.py exercises. Nothing ever removed them, so a shared
stack accumulated them indefinitely: a stack examined during this work held
16,821 patterns, the bulk from `stress_200_*` runs months old.

That is not merely untidy. Corpus size feeds `total_unique_patterns` and the
symbol statistics behind prediction metrics, and a larger corpus means more
candidates through the filter pipeline, so an ever-growing pile of dead test
patterns makes the suite slower and its timing-sensitive tests less
reproducible over time.

Scope and safety. A kb_id is `<node_id>_<base_id>`, so a kb_id created by the
suite starts with one of the node prefixes in redis_test_cleanup. Only those are
touched; anything else -- production `node0..node3`, a colleague's node, a
training notebook's -- is left alone. Each candidate must additionally pass
`validate_kb_id`, because `DROP PARTITION` cannot bind parameters and the value
is inlined into statement text.

Runs before the suite rather than after, so a crashed run's residue is cleaned
on the next run and the data from the run you just watched fail is still there
to inspect. Set KATO_TEST_KEEP_PATTERNS=1 to skip it.

Only partitions untouched for QUIET_MINUTES are dropped. redis_test_cleanup was
deliberately made safe to run beside another suite or a live notebook, and
purging patterns by name alone would have given that property back up: two
concurrent runs both create test-prefixed nodes, so each would delete the
other's corpus mid-test. A partition still being written to is left alone.
"""

import os
import re
from typing import Optional

import requests
from fixtures.redis_test_cleanup import is_test_node, test_node_prefixes

# All four partition by kb_id (config/clickhouse/init.sql), so each is removable
# with DROP PARTITION rather than a row-by-row mutation. pattern_stats and
# lsh_buckets are empty in current deployments; included so that stops being a
# silent assumption.
PARTITIONED_TABLES = (
    "kato.patterns_data",
    "kato.patterns_metadata",
    "kato.pattern_stats",
    "kato.lsh_buckets",
)

# Historical, pre-convention data. generate_unique_node_id in
# tests/tests/integration/test_database_persistence.py used to emit
# "<descriptive>_<8 hex>" with no test marker, so cleanup could not recognise it
# and every run orphaned another batch -- `stress_200_*` alone reached 10,400
# patterns across 52 nodes. That generator now emits "test_<descriptive>_<8 hex>",
# so this list is closed: it covers only data created before the fix and every
# entry was traced to a call site in that file. It can be deleted once no stack
# carries pre-fix data.
#
# Matched with the exact shape the old generator produced, not by prefix alone.
# "user_alice" is the kind of name a real node could plausibly have; requiring
# the trailing 8-hex-digit token means a genuine node called "user_alice" or
# "user_alice_prod" is never touched.
LEGACY_TEST_NODE_PREFIXES = (
    "basic_persist",
    "emotive_persist",
    "frequency_test",
    "large_scale",
    "multi_basic",
    "multimodal",
    "persist_test",
    "stress_200",
    "user_alice",
    "user_bob",
    "vector_persist",
)

_LEGACY_KB_ID_RE = re.compile(
    r"^(?:" + "|".join(re.escape(p) for p in LEGACY_TEST_NODE_PREFIXES) + r")"
    r"_[0-9a-f]{8}_[A-Za-z0-9_]+$"
)


def is_legacy_test_kb_id(kb_id: str) -> bool:
    """True for a kb_id the old test generator produced.

    Requires "<known prefix>_<8 lowercase hex>_<base id>" exactly, so it cannot
    match a production node that merely shares a prefix.
    """
    return bool(kb_id) and bool(_LEGACY_KB_ID_RE.match(kb_id))


# A partition modified more recently than this may belong to a suite running
# right now, or to the tail of one that just finished. Override with
# KATO_TEST_PURGE_QUIET_MINUTES.
DEFAULT_QUIET_MINUTES = 15


def _quiet_minutes() -> int:
    raw = os.environ.get("KATO_TEST_PURGE_QUIET_MINUTES")
    if raw:
        try:
            return max(0, int(raw))
        except ValueError:
            pass
    return DEFAULT_QUIET_MINUTES


def _clickhouse_url() -> str:
    host = os.environ.get("CLICKHOUSE_HOST", "localhost")
    port = os.environ.get("CLICKHOUSE_PORT", "8123")
    return f"http://{host}:{port}/"


def _query(sql: str, timeout: float = 30.0) -> str:
    resp = requests.post(_clickhouse_url(), data=sql.encode("utf-8"), timeout=timeout)
    resp.raise_for_status()
    return resp.text.strip()


def _is_safe_test_kb_id(kb_id: str, prefixes: tuple[str, ...]) -> bool:
    """Two independent gates, both of which must pass.

    The prefix check establishes that the suite created it. validate_kb_id
    establishes that it is safe to inline into a DROP PARTITION statement, which
    cannot bind parameters. Neither alone is sufficient: a prefix match says
    nothing about the characters in the rest of the string, and a well-formed
    kb_id may well belong to production.
    """
    if not (is_test_node(kb_id, prefixes) or is_legacy_test_kb_id(kb_id)):
        return False
    try:
        from kato.storage.identifiers import UnsafeIdentifierError, validate_kb_id
    except ImportError:
        # Without the validator, refuse rather than inline an unvalidated value.
        return False
    try:
        validate_kb_id(kb_id)
    except UnsafeIdentifierError:
        return False
    return True


def existing_partitions(prefixes: Optional[tuple[str, ...]] = None) -> dict[str, list[str]]:
    """Map table -> kb_ids that have an active partition and are in scope.

    Read from system.parts rather than by SELECT DISTINCT per table, so the whole
    picture costs one query, and so DROP PARTITION is only issued for partitions
    that exist. The first run on a long-lived stack faces thousands of candidate
    partitions; asking for the ones that are really there is what keeps this from
    dominating suite startup.
    """
    prefixes = prefixes or test_node_prefixes()
    quiet = _quiet_minutes()
    try:
        # max(modification_time) per partition, so a partition with any recent
        # part is excluded -- that is the one a concurrent run may be writing.
        rows = _query(
            "SELECT table, partition FROM system.parts "
            "WHERE database = 'kato' AND active "
            "GROUP BY table, partition "
            f"HAVING max(modification_time) < now() - INTERVAL {quiet} MINUTE "
            "FORMAT TabSeparated"
        )
    except Exception:
        # Unreachable or restricted server: cleanup is optional, carry on.
        return {}

    by_table: dict[str, list[str]] = {}
    for line in rows.splitlines():
        if "\t" not in line:
            continue
        table, partition = line.split("\t", 1)
        qualified = f"kato.{table.strip()}"
        if qualified not in PARTITIONED_TABLES:
            continue
        kb_id = partition.strip()
        if _is_safe_test_kb_id(kb_id, prefixes):
            by_table.setdefault(qualified, []).append(kb_id)
    return by_table


def find_test_kb_ids(prefixes: Optional[tuple[str, ...]] = None) -> list[str]:
    """Return kb_ids holding learned patterns that the suite created."""
    by_table = existing_partitions(prefixes)
    return sorted({kb_id for kb_ids in by_table.values() for kb_id in kb_ids})


def _purge_redis(redis_client, doomed: set[str]) -> int:
    """Delete every Redis key belonging to a doomed kb_id, in one keyspace pass.

    Scanning per kb_id would mean one full pass each, and there can be hundreds;
    keys are "<kb_id>:<rest>", so a single pass can bucket them instead.
    """
    deleted = 0
    batch: list[str] = []
    for key in redis_client.scan_iter(match="*", count=1000):
        head_, sep, _ = key.partition(":")
        if sep and head_ in doomed:
            batch.append(key)
            if len(batch) >= 1000:
                deleted += redis_client.delete(*batch)
                batch = []
    if batch:
        deleted += redis_client.delete(*batch)
    return deleted


def purge_test_patterns(
    redis_client=None,
    prefixes: Optional[tuple[str, ...]] = None,
    dry_run: bool = False,
) -> dict:
    """Drop ClickHouse partitions and Redis keys for test-created kb_ids.

    Never raises: cleanup is a convenience and must not fail a suite that would
    otherwise run. Failures are counted and reported.

    Returns counts: kb_ids, partitions_dropped, redis_keys_deleted, failures.
    """
    prefixes = prefixes or test_node_prefixes()
    by_table = existing_partitions(prefixes)
    doomed = {kb_id for kb_ids in by_table.values() for kb_id in kb_ids}

    result = {
        "kb_ids": len(doomed),
        "partitions_dropped": 0,
        "redis_keys_deleted": 0,
        "failures": 0,
    }
    if not doomed or dry_run:
        return result

    # Several DROP PARTITION actions are legal in one ALTER, which turns
    # thousands of round trips into a handful. Chunked so no single statement
    # grows unreasonably long.
    for table, kb_ids in by_table.items():
        for i in range(0, len(kb_ids), 100):
            chunk = kb_ids[i:i + 100]
            # Re-validate at the point of use: this is the line that becomes SQL.
            if not all(_is_safe_test_kb_id(kb, prefixes) for kb in chunk):
                result["failures"] += len(chunk)
                continue
            actions = ", ".join(f"DROP PARTITION '{kb}'" for kb in chunk)
            try:
                _query(f"ALTER TABLE {table} {actions}", timeout=120.0)
                result["partitions_dropped"] += len(chunk)
            except Exception:
                result["failures"] += len(chunk)

    if redis_client is not None:
        try:
            result["redis_keys_deleted"] = _purge_redis(redis_client, doomed)
        except Exception:
            result["failures"] += 1

    return result
