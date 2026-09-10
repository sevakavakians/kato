#!/usr/bin/env python3
"""
Compare per-kb_id pattern counts between Redis and ClickHouse.

Redis holds one ``{kb_id}:frequency:{name}`` key per learned pattern; ClickHouse
holds the pattern rows in ``kato.patterns_data``. In a healthy store the two
agree for every kb_id. Disagreement means one side lost or leaked data — most
often cleanup residue from tests, occasionally a real write failure.

Usage:
    python scripts/check_store_parity.py                 # report mismatches
    python scripts/check_store_parity.py --all           # report every kb_id
    python scripts/check_store_parity.py --purge-prefix test_            # dry run
    python scripts/check_store_parity.py --purge-prefix test_ --execute  # delete

Purging removes, for each MISMATCHED kb_id with the given prefix, all of its
Redis keys and its ClickHouse patterns_data / patterns_metadata partitions.
kb_ids that already agree are never touched, whatever their prefix.

Exit status: 0 when every kb_id agrees (after any purge), 1 otherwise.
"""

import argparse
import collections
import os
import sys

import redis
import requests

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from kato.storage.redis_writer import escape_glob  # noqa: E402

CLICKHOUSE_URL = os.environ.get("CLICKHOUSE_URL", "http://localhost:8123")
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")


def ch_query(query: str, **params) -> str:
    # POST: ClickHouse's HTTP interface treats GET as read-only, which rejects the DDL used by --execute.
    resp = requests.post(CLICKHOUSE_URL, params={"query": query, **{f"param_{k}": v for k, v in params.items()}}, timeout=60)
    resp.raise_for_status()
    return resp.text


def clickhouse_counts() -> dict[str, int]:
    out = ch_query("SELECT kb_id, uniqExact(name) FROM kato.patterns_data GROUP BY kb_id FORMAT TSV")
    return {kb: int(n) for kb, n in (line.split("\t") for line in out.splitlines() if line)}


def redis_counts(client: redis.Redis) -> dict[str, int]:
    counts: collections.Counter = collections.Counter()
    for key in client.scan_iter(match="*:frequency:*", count=5000):
        counts[key.rsplit(":frequency:", 1)[0]] += 1
    return dict(counts)


def purge(kb_id: str, client: redis.Redis, execute: bool) -> None:
    keys = list(client.scan_iter(match=f"{escape_glob(kb_id)}:*", count=5000))
    action = "would delete" if not execute else "deleted"
    if execute:
        if keys:
            client.delete(*keys)
        # DDL does not accept query parameters, so the partition id is inlined
        # as an escaped string literal.
        literal = kb_id.replace("\\", "\\\\").replace("'", "\\'")
        for table in ("patterns_data", "patterns_metadata"):
            try:
                ch_query(f"ALTER TABLE kato.{table} DROP PARTITION '{literal}'")
            except requests.HTTPError as e:
                body = getattr(e.response, "text", "").lower()
                if "doesn't exist" not in body and "not found" not in body:
                    raise
    print(f"    {action} {len(keys)} Redis keys + ClickHouse partitions for {kb_id}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--all", action="store_true", help="list every kb_id, not only mismatches")
    ap.add_argument("--purge-prefix", metavar="PREFIX", help="purge mismatched kb_ids starting with PREFIX")
    ap.add_argument("--execute", action="store_true", help="actually delete (default is a dry run)")
    args = ap.parse_args()

    client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    ch, rd = clickhouse_counts(), redis_counts(client)
    kbs = sorted(set(ch) | set(rd))
    mismatched = [kb for kb in kbs if ch.get(kb, 0) != rd.get(kb, 0)]

    print(f"kb_ids: {len(kbs)}  (clickhouse {len(ch)}, redis {len(rd)})   "
          f"patterns: clickhouse {sum(ch.values())}, redis {sum(rd.values())}")
    for kb in (kbs if args.all else mismatched):
        flag = "  " if ch.get(kb, 0) == rd.get(kb, 0) else "!!"
        print(f"{flag} {kb:60s} clickhouse={ch.get(kb, 0):6d} redis={rd.get(kb, 0):6d}")
    print(f"mismatched kb_ids: {len(mismatched)}")

    if args.purge_prefix:
        targets = [kb for kb in mismatched if kb.startswith(args.purge_prefix)]
        print(f"\n{'Purging' if args.execute else 'Dry run — would purge'} {len(targets)} mismatched kb_id(s) "
              f"with prefix {args.purge_prefix!r}:")
        for kb in targets:
            purge(kb, client, args.execute)
        if args.execute:
            ch, rd = clickhouse_counts(), redis_counts(client)
            mismatched = [kb for kb in sorted(set(ch) | set(rd)) if ch.get(kb, 0) != rd.get(kb, 0)]
            print(f"after purge: mismatched kb_ids: {len(mismatched)}")

    return 0 if not mismatched else 1


if __name__ == "__main__":
    sys.exit(main())
