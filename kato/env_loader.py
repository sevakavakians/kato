"""
Loads a .env file into os.environ before any KATO configuration is read.

Why this module exists
----------------------
KATO's configuration is read from ``os.environ`` in three separate ways:

1. The nested config classes in ``kato/config/settings.py`` (DatabaseConfig,
   LoggingConfig, ...) are built via ``default_factory`` and each reads
   ``os.environ`` independently.
2. Several hot paths read ``os.environ`` directly and never go through pydantic
   at all -- ``kato/__init__.py`` (LOG_LEVEL), ``kato/workers/pattern_processor.py``
   (KATO_ARCHITECTURE_MODE), ``kato/services/kato_fastapi.py`` (SERVICE_NAME),
   ``kato/storage/*`` (REDIS_URL).
3. Some values are read at module import time, before any Settings object exists.

Populating ``os.environ`` up front is the only mechanism that reaches all three.

Do NOT set ``env_file=`` on the Settings model to do this instead. pydantic-settings'
DotEnvSettingsSource enumerates the *entire* file and forwards every key it cannot
match onto the model; with ``extra='forbid'`` (the BaseSettings default) any key that
is not a declared field raises ``extra_forbidden``. That is what made every non-Docker
start fail on ``REDIS_PERSISTENCE`` -- a variable that only docker-compose consumes.

Precedence: real process environment > .env file > field defaults.

Docker is unaffected: ``.env`` is not COPYed into the image and the kato service has
no bind mounts, so no file is found. Even if one were present, compose's
``environment:`` block populates the real process environment, which wins.
"""

import os
from pathlib import Path
from typing import Optional

# Set once per process so uvicorn --reload / --workers re-imports are free.
_loaded = False

# kato/env_loader.py -> parents[0] == <repo>/kato, parents[1] == <repo>
_REPO_ROOT = Path(__file__).resolve().parents[1]


def _candidate_paths() -> list[Path]:
    """Return the .env paths to try, in priority order.

    An explicit KATO_ENV_FILE short-circuits to exactly that path: if the operator
    named a file, silently falling back to a different one would be worse than
    loading nothing.
    """
    explicit = os.environ.get("KATO_ENV_FILE")
    if explicit:
        return [Path(explicit).expanduser()]
    return [_REPO_ROOT / ".env", Path.cwd() / ".env"]


def load_env_file() -> Optional[Path]:
    """Load the first .env file found into os.environ.

    Idempotent and never raises -- configuration loading must not be able to
    prevent ``import kato``.

    Set KATO_SKIP_DOTENV=1 to disable entirely (useful for tests and CI that want
    a hermetic environment).

    Returns:
        Path of the file that was loaded, or None if nothing was loaded.
    """
    global _loaded
    if _loaded or os.environ.get("KATO_SKIP_DOTENV") == "1":
        return None
    _loaded = True

    try:
        from dotenv import load_dotenv
    except ImportError:
        # python-dotenv is a declared dependency, but importing kato should still
        # work in a stripped-down install that only sets real env vars.
        return None

    for path in _candidate_paths():
        if path.is_file():
            # override=False: an already-exported variable always wins.
            load_dotenv(path, override=False)
            return path
    return None
