#!/usr/bin/env python3
"""Apply config/clickhouse/init.sql over the ClickHouse HTTP interface.

The HTTP interface executes exactly one statement per request: POSTing a whole
.sql file comes back as `Code: 62 ... Multi-statements are not allowed`, and
there is no server-side setting to relax that (`multiquery` is a
clickhouse-client flag, not a setting -- asking for `?multiquery=1` fails with
`Code: 115 ... UNKNOWN_SETTING`). The docker-compose stack gets away with
feeding the file in whole only because /docker-entrypoint-initdb.d is applied by
clickhouse-client inside the container. Anything speaking HTTP -- CI, an
operator running this by hand -- has to send the statements one at a time.

Stdlib only, so it can run before the project's dependencies are installed.

    python scripts/apply_clickhouse_schema.py --wait 60
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_SQL = Path(__file__).resolve().parent.parent / "config" / "clickhouse" / "init.sql"


def split_statements(sql: str) -> list[str]:
    """Split a .sql file into individual statements.

    Line comments are stripped before splitting rather than after: splitting on
    ';' alone leaves each statement glued to the comment block above it, so a
    later `startswith('--')` filter discards the statement along with the
    comment. Assumes no string literal in the schema contains '--' or ';'.
    """
    code_lines = []
    for line in sql.splitlines():
        code = line.split("--", 1)[0]
        if code.strip():
            code_lines.append(code)
    return [stmt.strip() for stmt in "\n".join(code_lines).split(";") if stmt.strip()]


def wait_for_ready(base_url: str, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    last_error = "no attempt made"
    while True:
        try:
            with urllib.request.urlopen(f"{base_url}/ping", timeout=5) as resp:  # noqa: S310
                if resp.status == 200:
                    return
                last_error = f"HTTP {resp.status}"
        except (urllib.error.URLError, OSError) as exc:
            last_error = str(exc)
        if time.monotonic() >= deadline:
            sys.exit(f"ClickHouse at {base_url} did not become ready within {timeout:.0f}s: {last_error}")
        time.sleep(2)


def execute(base_url: str, statement: str, user: str, password: str) -> None:
    request = urllib.request.Request(  # noqa: S310
        base_url + "/",
        data=statement.encode(),
        headers={"X-ClickHouse-User": user, "X-ClickHouse-Key": password},
    )
    try:
        urllib.request.urlopen(request, timeout=60).read()  # noqa: S310
    except urllib.error.HTTPError as exc:
        # ClickHouse puts the real diagnosis in the response body; `curl -f`
        # threw it away, which is why the original CI failure said only "22".
        body = exc.read().decode(errors="replace").strip()
        sys.exit(f"statement failed (HTTP {exc.code}):\n  {statement.splitlines()[0][:100]}\n{body}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, default=DEFAULT_SQL, help="schema file to apply")
    parser.add_argument("--host", default=os.environ.get("CLICKHOUSE_HOST", "localhost"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("CLICKHOUSE_PORT", "8123")))
    parser.add_argument("--user", default=os.environ.get("CLICKHOUSE_USER", "default"))
    parser.add_argument("--password", default=os.environ.get("CLICKHOUSE_PASSWORD", ""))
    parser.add_argument("--wait", type=float, default=0.0, help="seconds to wait for /ping before applying")
    args = parser.parse_args()

    if not args.file.is_file():
        sys.exit(f"schema file not found: {args.file}")

    base_url = f"http://{args.host}:{args.port}"
    if args.wait:
        wait_for_ready(base_url, args.wait)

    statements = split_statements(args.file.read_text())
    if not statements:
        sys.exit(f"no statements found in {args.file}")

    for statement in statements:
        print(f"  -> {statement.splitlines()[0][:80]}")
        execute(base_url, statement, args.user, args.password)

    print(f"Applied {len(statements)} statements from {args.file} to {base_url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
