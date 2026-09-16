"""Validation for identifiers that end up inside ClickHouse statement text.

Most KATO queries can and should bind their values with
``client.query(sql, parameters={...})``. A few statements cannot: ClickHouse
does not accept bound parameters in ``ALTER TABLE ... DROP PARTITION`` or in
the predicate of ``ALTER TABLE ... DELETE``. For those, the only safe option is
to prove the identifier cannot contain anything but the characters an
identifier is allowed to contain.

That is what this module is for. It is an allowlist, deliberately: the previous
approach replaced a fixed list of 14 "unsafe" characters and did not include
the single quote, so a quote in a ``node_id`` survived into statement text.
"""

import re

# kb_id is built by ProcessorManager._get_processor_id and is capped at 60
# characters there; pattern names are SHA1 hex digests (stored without the
# 'PTRN|' prefix).
KB_ID_RE = re.compile(r'^[A-Za-z0-9_]{1,60}$')
PATTERN_NAME_RE = re.compile(r'^[0-9a-f]{40}$')


class UnsafeIdentifierError(ValueError):
    """Raised when an identifier would be unsafe to inline into SQL text."""


def validate_kb_id(kb_id: str) -> str:
    """Return ``kb_id`` unchanged, or raise if it is not allowlist-clean.

    Raises:
        UnsafeIdentifierError: if ``kb_id`` is not ``^[A-Za-z0-9_]{1,60}$``.
    """
    if not isinstance(kb_id, str) or not KB_ID_RE.match(kb_id):
        raise UnsafeIdentifierError(
            f"kb_id must match {KB_ID_RE.pattern!r}, got {kb_id!r}"
        )
    return kb_id


def validate_pattern_name(name: str) -> str:
    """Return ``name`` unchanged, or raise if it is not a SHA1 hex digest.

    Raises:
        UnsafeIdentifierError: if ``name`` is not 40 lowercase hex characters.
    """
    if not isinstance(name, str) or not PATTERN_NAME_RE.match(name):
        raise UnsafeIdentifierError(
            f"pattern name must be a 40-character SHA1 hex digest, got {name!r}"
        )
    return name


def is_valid_kb_id(kb_id: str) -> bool:
    """Non-raising form of :func:`validate_kb_id`."""
    return isinstance(kb_id, str) and bool(KB_ID_RE.match(kb_id))


def is_valid_pattern_name(name: str) -> bool:
    """Non-raising form of :func:`validate_pattern_name`."""
    return isinstance(name, str) and bool(PATTERN_NAME_RE.match(name))
