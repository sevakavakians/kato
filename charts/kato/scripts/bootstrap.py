"""
KATO Helm chart pre-install/pre-upgrade bootstrap hook.

Verifies connectivity to ClickHouse, Redis, and Qdrant, and applies the
ClickHouse schema (idempotent CREATE/ALTER statements). Exits non-zero
on any failure so the Helm release fails fast with a clear error rather
than letting the runtime pods crash-loop later.

Reads connection settings from the same environment variables KATO uses
at runtime, so the hook Job and the runtime Deployment share secret refs.

Reuses the clickhouse-connect, redis-py, and qdrant-client libraries
already present in the KATO image (per requirements.lock).
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Optional


LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s | %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, stream=sys.stdout)
log = logging.getLogger("kato.bootstrap")


def _env(name: str, default: Optional[str] = None, required: bool = False) -> Optional[str]:
    val = os.environ.get(name, default)
    if required and not val:
        raise SystemExit(f"required env var {name} is not set")
    return val


def _truthy(val: Optional[str]) -> bool:
    return (val or "").lower() in {"1", "true", "yes", "on"}


def split_statements(sql: str) -> list:
    """Split a .sql file into individual statements.

    Kept in lockstep with scripts/apply_clickhouse_schema.py (this file is
    vendored into a ConfigMap, so it cannot import from the repo). Line
    comments are stripped before splitting rather than after: splitting on ';'
    alone leaves each statement glued to the comment block above it, so a later
    `startswith('--')` filter discards the statement along with the comment --
    which silently reduced init.sql to three unrunnable fragments.
    """
    code_lines = []
    for line in sql.splitlines():
        code = line.split("--", 1)[0]
        if code.strip():
            code_lines.append(code)
    return [stmt.strip() for stmt in "\n".join(code_lines).split(";") if stmt.strip()]


def bootstrap_clickhouse() -> None:
    import clickhouse_connect

    host = _env("CLICKHOUSE_HOST", required=True)
    port = int(_env("CLICKHOUSE_PORT", "8123"))
    user = _env("CLICKHOUSE_USER", "default")
    password = _env("CLICKHOUSE_PASSWORD", "")
    secure = _truthy(_env("CLICKHOUSE_SECURE", "false"))
    database = _env("CLICKHOUSE_DB", "kato")

    log.info("Connecting to ClickHouse at %s:%s (secure=%s, db=%s)", host, port, secure, database)
    client = clickhouse_connect.get_client(
        host=host,
        port=port,
        username=user,
        password=password or "",
        secure=secure,
        connect_timeout=10,
        send_receive_timeout=30,
    )

    log.info("Verifying connectivity (SELECT 1)")
    client.query("SELECT 1")

    sql_path = Path(os.environ.get("CLICKHOUSE_INIT_SQL_PATH", "/scripts/init.sql"))
    if not sql_path.is_file():
        raise SystemExit(f"ClickHouse init SQL not found at {sql_path}")
    log.info("Applying schema from %s", sql_path)

    for stmt in split_statements(sql_path.read_text()):
        first_line = stmt.splitlines()[0][:80]
        log.info("  -> %s", first_line)
        client.command(stmt)

    log.info("ClickHouse schema applied successfully.")


def bootstrap_redis() -> None:
    if not _truthy(_env("REDIS_ENABLED", "false")):
        log.info("Redis is disabled (REDIS_ENABLED=false); skipping.")
        return

    import redis  # type: ignore

    url = _env("REDIS_URL")
    if url:
        log.info("Connecting to Redis via REDIS_URL")
        client = redis.from_url(url, socket_connect_timeout=5, socket_timeout=5)
    else:
        host = _env("REDIS_HOST", required=True)
        port = int(_env("REDIS_PORT", "6379"))
        password = _env("REDIS_PASSWORD")
        tls = _truthy(_env("REDIS_TLS", "false"))
        scheme = "rediss" if tls else "redis"
        composed = f"{scheme}://{':' + password + '@' if password else ''}{host}:{port}/{int(_env('REDIS_DB', '0'))}"
        log.info("Connecting to Redis at %s:%s (tls=%s)", host, port, tls)
        client = redis.from_url(composed, socket_connect_timeout=5, socket_timeout=5)

    pong = client.ping()
    if not pong:
        raise SystemExit("Redis PING did not return PONG")

    probe_key = "kato:bootstrap:probe"
    client.set(probe_key, "ok", ex=30)
    if client.get(probe_key) not in (b"ok", "ok"):
        raise SystemExit("Redis probe round-trip failed")
    client.delete(probe_key)
    log.info("Redis connectivity verified.")


def bootstrap_qdrant() -> None:
    from qdrant_client import QdrantClient  # type: ignore

    host = _env("QDRANT_HOST", required=True)
    port = int(_env("QDRANT_PORT", "6333"))
    grpc_port = int(_env("QDRANT_GRPC_PORT", "6334"))
    https = _truthy(_env("QDRANT_HTTPS", "false"))
    api_key = _env("QDRANT_API_KEY")

    log.info("Connecting to Qdrant at %s (https=%s, grpc=%s)", host, https, grpc_port)
    kwargs = {
        "host": host,
        "port": port,
        "grpc_port": grpc_port,
        "prefer_grpc": True,
        "https": https,
        "timeout": 10,
    }
    if api_key:
        kwargs["api_key"] = api_key
    client = QdrantClient(**kwargs)
    collections = client.get_collections()
    log.info("Qdrant connectivity verified (%d collections visible).", len(collections.collections))


def main() -> int:
    failed = []
    for name, fn in (("ClickHouse", bootstrap_clickhouse), ("Redis", bootstrap_redis), ("Qdrant", bootstrap_qdrant)):
        try:
            log.info("=== Bootstrapping %s ===", name)
            fn()
        except SystemExit:
            raise
        except Exception:
            log.exception("%s bootstrap FAILED", name)
            failed.append(name)
    if failed:
        log.error("Bootstrap failed for: %s", ", ".join(failed))
        return 1
    log.info("All backing stores verified. KATO is ready to install.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
