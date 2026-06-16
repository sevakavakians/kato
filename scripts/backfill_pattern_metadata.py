#!/usr/bin/env python3
"""
Backfill kato.patterns_metadata from Redis.

Copies per-pattern metadata (emotives, metadata, entropy, normalized_entropy,
global_normalized_entropy, tf_vector) from the legacy Redis keys into the
new ClickHouse patterns_metadata sidecar table.

Run during Phase 2 of the Redis → ClickHouse migration, after Phase 1
dual-write has been enabled. Patterns learned after Phase 1 are already in
patterns_metadata; this script handles the pre-existing patterns.

Idempotent: ReplacingMergeTree dedupes by (kb_id, name) on background merge
using updated_at as the version column. Re-running with the same input
produces the same final state.

Usage:
    # Backfill specific kb_ids
    python scripts/backfill_pattern_metadata.py --kb-ids node0_kato,node1_kato

    # Backfill ALL kb_ids found in patterns_data
    python scripts/backfill_pattern_metadata.py --all

    # Dry run (report what would be written)
    python scripts/backfill_pattern_metadata.py --all --dry-run

    # Custom batch size / connection overrides
    python scripts/backfill_pattern_metadata.py --all --batch-size 5000 \\
        --clickhouse-host localhost --redis-url redis://localhost:6379
"""

import argparse
import json
import sys
import time
from datetime import datetime

import clickhouse_connect
import redis


COLUMNS = (
    'kb_id', 'name', 'emotives', 'metadata',
    'entropy', 'normalized_entropy', 'global_normalized_entropy',
    'tf_vector', 'updated_at',
)


def get_clickhouse_client(host, port, db, user, password):
    return clickhouse_connect.get_client(
        host=host, port=port, database=db, username=user, password=password,
    )


def get_redis_client(redis_url):
    return redis.from_url(redis_url, decode_responses=True, encoding='utf-8')


def discover_kb_ids(ch_client):
    result = ch_client.query(
        "SELECT kb_id, COUNT(*) AS cnt FROM kato.patterns_data "
        "GROUP BY kb_id ORDER BY cnt DESC"
    )
    found = []
    for row in result.result_rows:
        found.append(row[0])
        print(f"  Found: {row[0]} ({row[1]:,} patterns)")
    return found


def iter_pattern_names(ch_client, kb_id, batch_size):
    """Yield batches of pattern names from patterns_data for one kb_id.

    Uses ORDER BY name + LIMIT/OFFSET for stable pagination. patterns_data is
    write-mostly during migration so the offset cursor doesn't drift.
    """
    offset = 0
    while True:
        result = ch_client.query(
            "SELECT name FROM kato.patterns_data "
            f"WHERE kb_id = %(kb_id)s "
            f"ORDER BY name "
            f"LIMIT {int(batch_size)} OFFSET {int(offset)}",
            parameters={'kb_id': kb_id},
        )
        names = [row[0] for row in result.result_rows]
        if not names:
            return
        yield names
        if len(names) < batch_size:
            return
        offset += len(names)


def read_redis_metadata_batch(redis_client, kb_id, names):
    """Pipelined read of emotives, metadata, and 4 metric keys per pattern.

    Returns a list of row dicts in the column order expected by patterns_metadata.
    """
    if not names:
        return []
    pipe = redis_client.pipeline(transaction=False)
    for name in names:
        pipe.get(f"{kb_id}:emotives:{name}")
        pipe.get(f"{kb_id}:metadata:{name}")
        pipe.get(f"{kb_id}:entropy:{name}")
        pipe.get(f"{kb_id}:normalized_entropy:{name}")
        pipe.get(f"{kb_id}:global_normalized_entropy:{name}")
        pipe.get(f"{kb_id}:tf_vector:{name}")
    raw = pipe.execute()

    rows = []
    now = datetime.now()
    for i, name in enumerate(names):
        emotives_raw = raw[i * 6]
        metadata_raw = raw[i * 6 + 1]
        entropy_raw = raw[i * 6 + 2]
        norm_entropy_raw = raw[i * 6 + 3]
        global_norm_entropy_raw = raw[i * 6 + 4]
        tf_raw = raw[i * 6 + 5]

        rows.append([
            kb_id,
            name,
            emotives_raw if emotives_raw is not None else json.dumps([]),
            metadata_raw if metadata_raw is not None else json.dumps({}),
            float(entropy_raw) if entropy_raw is not None else None,
            float(norm_entropy_raw) if norm_entropy_raw is not None else None,
            float(global_norm_entropy_raw) if global_norm_entropy_raw is not None else None,
            tf_raw if tf_raw is not None else json.dumps({}),
            now,
        ])
    return rows


def backfill_kb_id(kb_id, ch_client, redis_client, batch_size, dry_run):
    total_seen = 0
    total_written = 0
    start = time.perf_counter()

    for batch_names in iter_pattern_names(ch_client, kb_id, batch_size):
        total_seen += len(batch_names)
        rows = read_redis_metadata_batch(redis_client, kb_id, batch_names)

        # Skip rows where every Redis source was empty (genuinely no metadata to backfill).
        non_empty = [
            r for r in rows
            if (r[2] not in (None, json.dumps([]))) or (r[3] not in (None, json.dumps({})))
            or any(v is not None for v in r[4:7])
            or (r[7] not in (None, json.dumps({})))
        ]

        if not dry_run and non_empty:
            ch_client.insert(
                'kato.patterns_metadata',
                non_empty,
                column_names=list(COLUMNS),
                settings={'async_insert': 1, 'wait_for_async_insert': 0},
            )

        total_written += len(non_empty)
        elapsed = time.perf_counter() - start
        rate = total_seen / elapsed if elapsed > 0 else 0
        print(
            f"  [{kb_id}] seen={total_seen:,} wrote={total_written:,} "
            f"({rate:,.0f}/s)"
        )

    return {
        'kb_id': kb_id,
        'patterns_seen': total_seen,
        'patterns_written': total_written,
        'time_seconds': round(time.perf_counter() - start, 2),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument('--kb-ids', help='Comma-separated kb_ids to backfill')
    target.add_argument('--all', action='store_true', help='Backfill every kb_id found in patterns_data')

    parser.add_argument('--batch-size', type=int, default=1000, help='Patterns per round-trip (default 1000)')
    parser.add_argument('--dry-run', action='store_true', help='Read everything but skip writes')

    parser.add_argument('--clickhouse-host', default='localhost')
    parser.add_argument('--clickhouse-port', type=int, default=8123)
    parser.add_argument('--clickhouse-db', default='kato')
    parser.add_argument('--clickhouse-user', default='default')
    parser.add_argument('--clickhouse-password', default='')
    parser.add_argument('--redis-url', default='redis://localhost:6379')

    args = parser.parse_args()

    print(f"Connecting to ClickHouse at {args.clickhouse_host}:{args.clickhouse_port} ...")
    ch_client = get_clickhouse_client(
        args.clickhouse_host, args.clickhouse_port, args.clickhouse_db,
        args.clickhouse_user, args.clickhouse_password,
    )
    print(f"Connecting to Redis at {args.redis_url} ...")
    redis_client = get_redis_client(args.redis_url)

    if args.all:
        print("Discovering kb_ids ...")
        kb_ids = discover_kb_ids(ch_client)
    else:
        kb_ids = [s.strip() for s in args.kb_ids.split(',') if s.strip()]

    if not kb_ids:
        print("No kb_ids to backfill.", file=sys.stderr)
        sys.exit(1)

    print(f"\nBackfilling {len(kb_ids)} kb_id(s){' [DRY RUN]' if args.dry_run else ''} ...\n")

    summaries = []
    for kb_id in kb_ids:
        print(f"== {kb_id} ==")
        summary = backfill_kb_id(kb_id, ch_client, redis_client, args.batch_size, args.dry_run)
        summaries.append(summary)
        print(
            f"  done: {summary['patterns_seen']:,} seen, "
            f"{summary['patterns_written']:,} written in {summary['time_seconds']}s\n"
        )

    print("Summary:")
    for s in summaries:
        print(
            f"  {s['kb_id']}: seen={s['patterns_seen']:,} "
            f"written={s['patterns_written']:,} time={s['time_seconds']}s"
        )


if __name__ == '__main__':
    main()
