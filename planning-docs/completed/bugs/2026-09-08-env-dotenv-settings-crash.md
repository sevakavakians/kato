# Bug Fix: `.env`'s `REDIS_PERSISTENCE` (and Nearly Every Other Key) Crashed KATO Run Outside Docker

*Completed: 2026-09-08*
*Status: FIXED*

## Summary
Originally logged as a narrow P2 — `.env`'s `REDIS_PERSISTENCE=true` crashing a locally-run (non-Docker) KATO server. Investigation found the real root cause was much broader: `Settings.model_config` declared `env_file='.env'` while inheriting pydantic-settings' `extra='forbid'` default, and the dotenv loader forwards **every** key in `.env` it cannot match onto the model. Since `Settings` only declares 8 nested-config fields plus `environment`/`debug`/`config_file`, nearly every real KATO variable in `.env` (`LOG_LEVEL`, `QDRANT_HOST`, `REDIS_URL`, `CLICKHOUSE_HOST`, ...) crashed it — `REDIS_PERSISTENCE` was simply the first one anyone hit. A couple of names (`SERVICE_NAME`, `SESSION_TTL`) were silently swallowed via prefix-matching against the `service`/`session` nested-config fields rather than actually applied. `.env` was effectively unusable outside Docker, not merely fragile. Docker itself was never affected — `.env` is not `COPY`ed into the image, so compose-supplied env vars were the only input `Settings` ever saw there.

## Root Cause
`kato/config/settings.py:434` — `Settings.model_config` set `env_file='.env'`. pydantic-settings' `DotEnvSettingsSource` enumerates the entire `.env` file and attempts to apply every key to the model; any key not recognized as a declared field raises `extra_forbidden` under `Settings`' inherited `extra='forbid'`. `Settings` declares only nested config objects (`database`, `redis`, `qdrant`, `session`, `logging`, `performance`, `service`, plus `environment`/`debug`/`config_file`) — it does not flatten to the individual leaf variable names KATO actually uses in `.env`. Result: any `.env` key that isn't a literal top-level field name (almost all of them) crashed `Settings()` construction; a few collided by accident with nested-field name prefixes and were silently absorbed without doing anything.

## Fix Applied
1. **New `kato/env_loader.py`** — loads `.env` into `os.environ` via python-dotenv's `load_dotenv(path, override=False)` (process env always wins over `.env`). Idempotent via a `_loaded` module guard; never raises. Resolution order: `KATO_ENV_FILE` env var short-circuits to exactly that path; otherwise repo-root `.env`; otherwise CWD `.env` — deterministic rather than CWD-relative. `KATO_SKIP_DOTENV=1` is a hard opt-out. Module docstring explicitly records why `env_file=` must not be reintroduced on `Settings`.
2. **`kato/__init__.py`** — calls `load_env_file()` before the existing import-time `LOG_LEVEL` read. This placement is required: the parent package `__init__` always runs before `kato/config/` is imported, and several hot paths read `os.environ` directly and never go through pydantic at all — `kato/__init__.py` (`LOG_LEVEL`), `kato/workers/pattern_processor.py` (`KATO_ARCHITECTURE_MODE`), `kato/services/kato_fastapi.py` (`SERVICE_NAME`), `kato/storage/*` (`REDIS_URL`). Populating `os.environ` up front is the only mechanism that reaches all of them.
3. **`kato/config/settings.py`** — removed `env_file`/`env_file_encoding` from `Settings.model_config`, keeping `env_prefix` and `case_sensitive`. Deliberately **kept** `extra='forbid'`: with `env_file` gone, the dotenv-forwarding path can no longer fire, and `forbid` is what makes an unknown key in a `KATO_CONFIG_FILE` YAML/JSON fail loudly in the `load_from_file` validator — that protection was worth preserving.
4. **`requirements.txt`** — `python-dotenv` promoted from transitive to explicit; `requirements.lock` regenerated with `pip-compile` under Python 3.10.
5. **`Makefile`** — new `run` target (none existed before) launching `uvicorn kato.services.kato_fastapi:app`, with `HOST`/`PORT`/`RELOAD` overridable via env; added to `.PHONY`.
6. **`.env.example`** — rewritten. Previously documented entirely dead names (`KATO_API_PORT`, `KATO_LOG_LEVEL`, `KATO_MANIFEST`, `MONGO_DB_PORT`, `USER`, `KATO_PROCESSOR_*`) — verified unreferenced anywhere in the repo. Now documents the live flat names, separates "host run" variables from "docker-compose only" ones (`REDIS_PERSISTENCE` belongs to the latter), and warns that changing `SERVICE_NAME` changes ClickHouse `kb_id` partitions and Qdrant collection names.
7. **Docs** — replaced every reference to the nonexistent module `kato.api.main` with the real one, `kato.services.kato_fastapi`, across 12 files (10 runnable commands plus prose paths); fixed `development-setup.md`'s local-run section, which also named nonexistent compose services (`kato-clickhouse`/`qdrant-kb`/`redis-kb` instead of `clickhouse`/`qdrant`/`redis`).

## Verification
- Crash reproduced before the fix, confirmed gone after.
- `.env` values now genuinely apply to nested configs — `QDRANT_PORT`, `LOG_LEVEL`, `REDIS_ENABLED`, `SESSION_TTL` all confirmed taking effect where they previously either crashed or were silently dropped.
- Process env correctly beats `.env` (`override=False`); `KATO_SKIP_DOTENV=1` correctly opts out; behavior confirmed CWD-independent.
- `make run` produced a fully working non-Docker server: `observe`/`learn`/`patterns/count`/`predictions`/`clear-all` all returned 200; learn → count went 0 → 1 → 0 on clear-all.
- Docker unaffected: no `.env` in the image, compose-supplied values still win (`qdrant`/`clickhouse` hostnames, `REDIS_PERSISTENCE=True` from compose, not `.env`).
- Full suite: 447 passed / 2 skipped / 5 failed — an improvement on the 446/2/6 baseline (one previously-6 failure no longer reproduces); all 5 remaining failures are the already-characterized multi-worker websocket/session backlog bug (see `planning-docs/SPRINT_BACKLOG.md`), unrelated to this fix.

## Files Modified
- `kato/env_loader.py` (new)
- `kato/__init__.py`
- `kato/config/settings.py`
- `requirements.txt`, `requirements.lock`
- `Makefile`
- `.env.example`
- 12 documentation files (module path corrections `kato.api.main` → `kato.services.kato_fastapi`; `development-setup.md` local-run section)

## Impact
- **Severity**: Was High for anyone running KATO outside Docker with the repo's own `.env` sourced — nearly all of `.env` was either a hard crash or a silent no-op; the working surface was effectively empty. Zero impact on Docker deployments, which never read `.env` in the first place.
- **Scope**: `kato/` runtime code (new module + two files touched), dependency lock, dev tooling (`Makefile`), and documentation. No API behavior change, no schema change.

## Incidental Findings (Discovered While Regenerating `requirements.lock`)
`requirements.lock` was already stale before this fix touched it — regenerating it surfaced two unrelated drift issues, now corrected as a side effect:
1. **`xxhash` was declared in `requirements.txt` but missing from `requirements.lock`**, so it was never installed in the running container — confirmed `import xxhash` fails inside the live `kato` container. This means the `MINHASH_HASH_FUNC=xxhash` optimization has been silently falling back to SHA-1 and was never actually available, despite being documented as an active performance feature (see `planning-docs/README.md` Performance line). The regenerated lock adds it; the next `docker compose build --no-cache kato` will make it genuinely available for the first time.
2. **`pymongo`/`dnspython` were still pinned in `requirements.lock`** despite MongoDB being fully removed in v3.0 and `pymongo` no longer appearing in `requirements.txt` at all — confirmed `pymongo==4.15.1` is currently installed in the running container. The regenerated lock drops both, shrinking the next-built image.

**Not yet realized**: both corrections are in the lock file only as of this fix. The running container still lacks `xxhash` and still has `pymongo`/`dnspython` until the next `docker compose build --no-cache kato` is actually run.

## Still Open (Not Fixed By This Work)
The dead `KATO_*` env names referenced via `json_schema_extra={'env': ...}` in `kato/config/settings.py` remain broken — that's a pydantic-v1 idiom that pydantic-settings v2 silently ignores, so `docker-compose.yml`'s `KATO_BATCH_SIZE=10000` still has no effect and the container runs with `batch_size=1000`. Added to `planning-docs/SPRINT_BACKLOG.md` as a new P2 item; not addressed here.

## Completion Date
2026-09-08
