#!/usr/bin/env python3
"""
Delete the per-pattern Redis keys that were migrated to kato.patterns_metadata.

Runs during Phase 6 of the Redis → ClickHouse metadata migration, AFTER:
  1. KATO_METADATA_DUAL_WRITE=true has been live for at least one training cycle,
  2. KATO_METADATA_READ_FROM=clickhouse has been live and validated, and
  3. KATO_METADATA_DUAL_WRITE=false has been set (Redis writes for these keys
     have ceased).

Deletes the following key families per kb_id:
  - {kb_id}:emotives:*
  - {kb_id}:metadata:*
  - {kb_id}:entropy:*
  - {kb_id}:normalized_entropy:*
  - {kb_id}:global_normalized_entropy:*
  - {kb_id}:tf_vector:*

DOES NOT touch (these stay in Redis):
  - {kb_id}:frequency:*          (atomic INCR)
  - {kb_id}:symbols:freq/pmf     (HASH, HINCRBY)
  - {kb_id}:symbol_to_patterns:* (SET)
  - {kb_id}:affinity:*           (HASH, HINCRBYFLOAT)
  - {kb_id}:global:*             (atomic INCR)
  - {kb_id}:prediction:*         (predictions cache)
  - kato:session:*               (session manager)

Uses non-blocking SCAN + UNLINK for safety on large keyspaces.

Usage:
    python scripts/delete_moved_redis_keys.py --kb-ids node0_kato,node1_kato
    python scripts/delete_moved_redis_keys.py --all
    python scripts/delete_moved_redis_keys.py --all --dry-run
"""

import argparse
import sys
import time

import redis


MOVED_KEY_TYPES = (
    'emotives',
    'metadata',
    'entropy',
    'normalized_entropy',
    'global_normalized_entropy',
    'tf_vector',
)


def get_redis_client(redis_url):
    return redis.from_url(redis_url, decode_responses=True, encoding='utf-8')


def discover_kb_ids(redis_client):
    """Discover kb_ids by scanning for any of the moved key families."""
    kb_ids = set()
    for key_type in MOVED_KEY_TYPES:
        for key in redis_client.scan_iter(match=f"*:{key_type}:*", count=1000):
            kb_id = key.split(f":{key_type}:", 1)[0]
            kb_ids.add(kb_id)
    found = sorted(kb_ids)
    for kb_id in found:
        print(f"  Found: {kb_id}")
    return found


def delete_kb_id(redis_client, kb_id, scan_count, dry_run):
    """Delete all moved key families for a single kb_id. Returns counts per key type."""
    counts = {}
    start = time.perf_counter()

    for key_type in MOVED_KEY_TYPES:
        pattern = f"{kb_id}:{key_type}:*"
        deleted = 0
        batch = []
        for key in redis_client.scan_iter(match=pattern, count=scan_count):
            batch.append(key)
            if len(batch) >= scan_count:
                if not dry_run:
                    redis_client.unlink(*batch)
                deleted += len(batch)
                batch.clear()
        if batch:
            if not dry_run:
                redis_client.unlink(*batch)
            deleted += len(batch)
        counts[key_type] = deleted
        print(f"  [{kb_id}] {key_type}: {deleted:,}")

    total = sum(counts.values())
    elapsed = round(time.perf_counter() - start, 2)
    print(f"  [{kb_id}] total deleted: {total:,} in {elapsed}s")
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument('--kb-ids', help='Comma-separated kb_ids to clean up')
    target.add_argument('--all', action='store_true', help='Discover and clean up every kb_id with moved keys')

    parser.add_argument('--scan-count', type=int, default=1000, help='SCAN/UNLINK chunk size (default 1000)')
    parser.add_argument('--dry-run', action='store_true', help='Count keys without deleting them')
    parser.add_argument('--redis-url', default='redis://localhost:6379')

    args = parser.parse_args()

    print(f"Connecting to Redis at {args.redis_url} ...")
    redis_client = get_redis_client(args.redis_url)

    if args.all:
        print("Discovering kb_ids with moved keys ...")
        kb_ids = discover_kb_ids(redis_client)
    else:
        kb_ids = [s.strip() for s in args.kb_ids.split(',') if s.strip()]

    if not kb_ids:
        print("No kb_ids found.", file=sys.stderr)
        sys.exit(1)

    if not args.dry_run:
        print(
            "\nAbout to UNLINK migrated per-pattern keys from Redis.\n"
            "This is irreversible. Ensure dual-write is disabled and\n"
            "read_from=clickhouse has been validated before continuing.\n"
        )
        try:
            confirm = input("Type the number of kb_ids to confirm: ").strip()
        except EOFError:
            confirm = ''
        if confirm != str(len(kb_ids)):
            print("Aborted.", file=sys.stderr)
            sys.exit(1)

    print(f"\nCleaning {len(kb_ids)} kb_id(s){' [DRY RUN]' if args.dry_run else ''} ...\n")

    grand_total = {key: 0 for key in MOVED_KEY_TYPES}
    for kb_id in kb_ids:
        print(f"== {kb_id} ==")
        counts = delete_kb_id(redis_client, kb_id, args.scan_count, args.dry_run)
        for k, v in counts.items():
            grand_total[k] += v
        print()

    print("Grand total:")
    for k, v in grand_total.items():
        print(f"  {k}: {v:,}")
    print(f"  ALL: {sum(grand_total.values()):,}")


if __name__ == '__main__':
    main()
