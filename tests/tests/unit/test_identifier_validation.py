"""Guards for identifiers that get inlined into ClickHouse statement text.

Most queries bind their values. A few statements cannot -- ClickHouse accepts
no bound parameters in ``ALTER TABLE ... DROP PARTITION`` or in the predicate
of ``ALTER TABLE ... DELETE`` -- so ``kb_id`` and pattern names are inlined
there. These tests pin the allowlist that makes that safe, and the sanitiser
that guarantees a generated kb_id satisfies it.

The previous sanitiser was a blacklist of 14 characters that did not include
the single quote, so a node_id containing one produced a kb_id that survived
into statement text.
"""

import pytest

from kato.processors.processor_manager import _sanitize_id_component
from kato.storage.identifiers import (
    UnsafeIdentifierError,
    is_valid_kb_id,
    is_valid_pattern_name,
    validate_kb_id,
    validate_pattern_name,
)


@pytest.mark.parametrize("kb_id", [
    "node0_kato",
    "test_abc_123",
    "stress_200_76ebf8b8_kato",
    "a",
    "x" * 60,
])
def test_valid_kb_ids_are_accepted(kb_id):
    assert validate_kb_id(kb_id) == kb_id
    assert is_valid_kb_id(kb_id)


@pytest.mark.parametrize("kb_id,why", [
    ("evil' OR 1=1 --", "single quote closes the literal"),
    ("a\tb", "tab works wherever a space would"),
    ("a\nb", "newline"),
    ("a-b", "hyphen is not in the allowlist"),
    ("a b", "space"),
    ("x" * 61, "too long"),
    ("", "empty"),
    ("kb;DROP", "statement separator"),
])
def test_unsafe_kb_ids_are_rejected(kb_id, why):
    assert not is_valid_kb_id(kb_id), why
    with pytest.raises(UnsafeIdentifierError):
        validate_kb_id(kb_id)


def test_kb_id_must_be_a_string():
    with pytest.raises(UnsafeIdentifierError):
        validate_kb_id(None)


def test_pattern_names_must_be_sha1_hex():
    good = "7729f0ed56a13a9373fc1b1c17e34f61d4512ab4"
    assert validate_pattern_name(good) == good
    assert is_valid_pattern_name(good)

    for bad in ["PTRN|" + good, good.upper(), good[:39], good + "a", "abc' OR 1=1"]:
        assert not is_valid_pattern_name(bad)
        with pytest.raises(UnsafeIdentifierError):
            validate_pattern_name(bad)


@pytest.mark.parametrize("node_id", [
    "node0",
    "my-node.1",
    "a b/c",
    "evil' OR 1=1 --",
    "tab\there",
    "emoji☃node",
    "weird!@#$%^&*()",
])
def test_sanitized_node_ids_always_satisfy_the_allowlist(node_id):
    """Whatever a client sends as node_id, the derived component is safe."""
    assert is_valid_kb_id(_sanitize_id_component(node_id) + "_kato")


def test_sanitizer_preserves_ordinary_identifiers():
    """Normal node ids must be untouched, or existing kb_ids would be orphaned."""
    for unchanged in ["node0", "test_abc_123", "stress_200_76ebf8b8"]:
        assert _sanitize_id_component(unchanged) == unchanged
