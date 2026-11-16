#!/usr/bin/env python3
"""
Recount total_pattern_frequencies from the per-pattern frequency counters.

`{kb_id}:global:total_pattern_frequencies` is the sum of every pattern's
frequency: each learn adds 1, whether the pattern is new or already known. It is
the F in `bayesian_prior` (f / F), `good_odds` and `confluence`.

A node needs a recount when its counter does not hold that sum. That is the case
for a node that was written to by a KATO release in which the counter went up
only for a new pattern, and so held the number of patterns. On such a node every
pattern learned more than once is missing from the total, priors come out too
high, and purging a pattern learned more often than the counter holds is
refused. This script sets the counter to the sum.

Usage:
    # Report what would change, write nothing
    python scripts/recount_pattern_frequencies.py --all --dry-run

    # Recount every node found in Redis
    python scripts/recount_pattern_frequencies.py --all

    # Recount specific kb_ids
    python scripts/recount_pattern_frequencies.py --kb-ids node0_kato,node1_kato

    # Another Redis
    python scripts/recount_pattern_frequencies.py --all --redis-url redis://redis:6379

Run it while the node is not learning or purging. The count is a scan over the
node's frequency keys, and it is written only if the node's statistics did not
change while it was taken (an optimistic check on `{kb_id}:stats:version`; no
lock is held). A node that changes during the count is counted again, up to
--attempts times, and then reported as busy with nothing written. A second
count after the write confirms the stored value.

Exit status: 0 when every requested node was verified (or, with --dry-run,
counted); 1 when at least one node was busy or failed.
"""

import argparse
import sys

import redis

FREQUENCY_BATCH = 5000

_GLOB_SPECIALS = str.maketrans({c: "\\" + c for c in "*?[]\\"})


def escape_glob(value: str) -> str:
    """Escape Redis SCAN glob metacharacters in a literal key component."""
    return value.translate(_GLOB_SPECIALS)


def get_redis_client(redis_url: str) -> redis.Redis:
    return redis.from_url(redis_url, decode_responses=True, encoding='utf-8')


def discover_kb_ids(client: redis.Redis) -> list[str]:
    """Every kb_id that has learned a pattern, from its total_unique_patterns key."""
    suffix = ':global:total_unique_patterns'
    return sorted(
        key[:-len(suffix)]
        for key in client.scan_iter(match=f"*{suffix}", count=1000)
        if key.endswith(suffix)
    )


def count_pattern_frequencies(client: redis.Redis, kb_id: str) -> tuple[int, int]:
    """(sum of every pattern's frequency, number of patterns) for one kb_id."""
    total = 0
    patterns = 0
    batch: list[str] = []

    def drain() -> None:
        nonlocal total, patterns
        for value in client.mget(batch):
            if value is not None:
                total += int(value)
                patterns += 1
        batch.clear()

    for key in client.scan_iter(match=f"{escape_glob(kb_id)}:frequency:*", count=1000):
        batch.append(key)
        if len(batch) >= FREQUENCY_BATCH:
            drain()
    if batch:
        drain()
    return total, patterns


def recount(client: redis.Redis, kb_id: str, dry_run: bool = False, attempts: int = 3) -> dict:
    """Set one node's total_pattern_frequencies to the sum of its pattern frequencies.

    Returns a report: kb_id, patterns, before, counted, written, and status, one of
    'unchanged' (the counter already held the sum), 'recounted' (written and
    confirmed by a second count), 'dry_run', or 'busy' (the node changed during
    every attempt; nothing was written, or the written value could not be
    confirmed).
    """
    total_key = f"{kb_id}:global:total_pattern_frequencies"
    version_key = f"{kb_id}:stats:version"
    report = {'kb_id': kb_id, 'patterns': 0, 'before': None, 'counted': None, 'written': False, 'status': 'busy'}

    for _ in range(max(1, attempts)):
        version = client.get(version_key)
        before = int(client.get(total_key) or 0)
        counted, patterns = count_pattern_frequencies(client, kb_id)
        report.update(patterns=patterns, before=before, counted=counted)

        if dry_run:
            report['status'] = 'dry_run'
            return report

        # Write only if nothing learned or purged while the count was taken.
        # WATCH makes the transaction fail, rather than wait, if the stamp
        # moves between here and EXEC.
        with client.pipeline(transaction=True) as pipe:
            try:
                pipe.watch(version_key)
                if pipe.get(version_key) != version:
                    pipe.unwatch()
                    continue
                pipe.multi()
                if counted > 0:
                    pipe.set(total_key, counted)
                else:
                    pipe.delete(total_key)
                pipe.execute()
            except redis.WatchError:
                continue
        report['written'] = counted != before

        # Confirm: a second count, with the stamp still where it was.
        confirmed, _ = count_pattern_frequencies(client, kb_id)
        stored = int(client.get(total_key) or 0)
        if confirmed == stored and client.get(version_key) == version:
            report['status'] = 'recounted' if report['written'] else 'unchanged'
            return report

    report['status'] = 'busy'
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0].strip())
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument('--kb-ids', help='Comma-separated kb_ids to recount')
    target.add_argument('--all', action='store_true', help='Recount every kb_id found in Redis')
    parser.add_argument('--redis-url', default='redis://localhost:6379', help='Redis URL')
    parser.add_argument('--dry-run', action='store_true', help='Count and report; write nothing')
    parser.add_argument('--attempts', type=int, default=3,
                        help='Counts to try per node when it changes underneath (default 3)')
    args = parser.parse_args(argv)

    client = get_redis_client(args.redis_url)
    kb_ids = discover_kb_ids(client) if args.all else [k.strip() for k in args.kb_ids.split(',') if k.strip()]
    if not kb_ids:
        print("No kb_ids to recount.")
        return 0

    failed = 0
    for kb_id in kb_ids:
        try:
            report = recount(client, kb_id, dry_run=args.dry_run, attempts=args.attempts)
        except Exception as error:      # one node must not stop the rest
            failed += 1
            print(f"{kb_id}: FAILED ({error})")
            continue
        line = (f"{kb_id}: {report['patterns']:,} patterns, total_pattern_frequencies "
                f"{report['before']:,} -> {report['counted']:,}")
        if report['status'] == 'busy':
            failed += 1
            print(f"{line}  BUSY: the node changed during the count. Stop learning and purging on it, then run again.")
        elif report['status'] == 'dry_run':
            print(f"{line}  (dry run, nothing written)")
        elif report['status'] == 'unchanged':
            print(f"{line}  already correct")
        else:
            print(f"{line}  recounted")
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
