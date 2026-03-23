# Completed Feature: TLS/HTTPS Support for All Database Connections

**Completed**: 2026-03-20
**Type**: Security Feature
**Priority**: P1 — Bug Fix + Security Enhancement
**Time Taken**: Not tracked (single session)
**Related Decisions**: DECISION-010

---

## Summary

Added TLS/HTTPS support for all three KATO database connections (ClickHouse, Redis, Qdrant), triggered by discovering that the `qdrant-client` library automatically enables HTTPS when an `api_key` is provided, causing SSL handshake failures against plain HTTP Qdrant instances.

---

## Root Cause (Qdrant Bug)

The `qdrant-client` Python library silently upgrades the connection to HTTPS when an `api_key` argument is passed to `QdrantClient`, regardless of whether the target server is running with TLS. This caused SSL failures for any deployment that set `QDRANT_API_KEY` (added in DECISION-009 on 2026-03-17) but did not run Qdrant with TLS.

---

## Changes Made

### Bug Fix — Qdrant HTTPS Auto-Enable

- `kato/config/vectordb_config.py`: Added `https: bool = False` field to `QdrantConfig` dataclass; wired from `QDRANT_HTTPS` env var; `get_url()` now uses correct scheme
- `kato/storage/qdrant_store.py`: Passes `https` explicitly to `QdrantClient` to suppress the library's auto-detect behavior
- `kato/storage/connection_manager.py`: Passes `https` from `QDRANT_HTTPS` setting to `QdrantClient`

### New TLS Environment Variables

- `kato/config/settings.py`: Added `QDRANT_HTTPS`, `CLICKHOUSE_SECURE`, `REDIS_TLS` boolean fields (all default `False`)
- `kato/config/settings.py`: `qdrant_url` property updated to use correct scheme based on `QDRANT_HTTPS`; `redis_url` property upgrades `redis://` to `rediss://` when `REDIS_TLS=true`
- `kato/storage/connection_manager.py`: `CLICKHOUSE_SECURE` wired to `secure=True` in `clickhouse_connect.get_client()`; Redis host/port fallback path gets `ssl=True`; Redis URL path uses `redis_url` property (handles TLS upgrade)

### Docker and Deployment Wiring

- `docker-compose.yml`: Added `QDRANT_HTTPS`, `REDIS_TLS`, `CLICKHOUSE_SECURE` env vars (all default false)
- `deployment/docker-compose.yml`: Same for both KATO services
- `deployment/kato-manager.sh`: `setup-auth` command now generates `CLICKHOUSE_SECURE=true`, `REDIS_TLS=true`, `QDRANT_HTTPS=true` in `.env`

### Documentation

- `.env.example` and `deployment/.env.example`: Added new TLS vars
- `docs/reference/configuration-vars.md`: Added `CLICKHOUSE_SECURE`, `QDRANT_API_KEY`, `QDRANT_HTTPS`, `REDIS_TLS`

---

## Files Modified

| File | Change |
|------|--------|
| `kato/config/vectordb_config.py` | Added `https` field to `QdrantConfig` |
| `kato/config/settings.py` | Added `QDRANT_HTTPS`, `CLICKHOUSE_SECURE`, `REDIS_TLS`; updated URL properties |
| `kato/storage/qdrant_store.py` | Explicit `https` param to `QdrantClient` |
| `kato/storage/connection_manager.py` | Wired TLS settings to all three clients |
| `docker-compose.yml` | Added TLS env vars |
| `deployment/docker-compose.yml` | Added TLS env vars |
| `deployment/kato-manager.sh` | `setup-auth` generates TLS vars |
| `.env.example` | Added TLS vars |
| `deployment/.env.example` | Added TLS vars |
| `docs/reference/configuration-vars.md` | Documented new TLS vars |

---

## Backward Compatibility

All three TLS flags default to `False`. Existing deployments without these env vars continue to operate over plain connections without any changes required.

---

## Deployment Behavior by Flag

| Flag | Default | Effect when `true` |
|------|---------|-------------------|
| `QDRANT_HTTPS` | `false` | Passes `https=True` to `QdrantClient`; URL scheme becomes `https://` |
| `CLICKHOUSE_SECURE` | `false` | Passes `secure=True` to `clickhouse_connect.get_client()` |
| `REDIS_TLS` | `false` | `redis_url` property uses `rediss://`; host/port path passes `ssl=True` |

---

## Impact Assessment

- **Security**: Encrypted transport for all three databases when TLS is enabled
- **Regression Risk**: Low — all flags off by default; no behavior change for existing deployments
- **Integration with DECISION-009**: `setup-auth` now generates both credential and TLS vars together, so auth-enabled deployments automatically get encrypted transport
