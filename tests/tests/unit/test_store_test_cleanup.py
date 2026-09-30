"""What the test-pattern purge will and will not delete.

This code issues DROP PARTITION against a stack that is routinely shared with
live work, so the matcher deciding which kb_ids are in scope deserves tests of
its own. The interesting cases are the near misses: names that share a prefix
with test data but belong to something real.
"""

import sys

import pytest

sys.path.insert(0, __file__.rsplit('/tests/', 1)[0] + '/tests')

from fixtures.store_test_cleanup import (  # noqa: E402
    LEGACY_TEST_NODE_PREFIXES,
    _is_safe_test_kb_id,
    is_legacy_test_kb_id,
)

PREFIXES = ("test", "topology_", "perf_", "load_test")


@pytest.mark.parametrize("kb_id", [
    "test_something_1790000000000_abcd1234_kato",
    "test_diagprobe_1790778366415_408ef677_kato",
    "topology_4w_kato",
    "perf_1w_kato",
    "load_test_abc_kato",
])
def test_current_convention_is_in_scope(kb_id):
    """Nodes the suite creates today carry one of the documented prefixes."""
    assert _is_safe_test_kb_id(kb_id, PREFIXES) is True


@pytest.mark.parametrize("kb_id", [
    "stress_200_76ebf8b8_kato",
    "large_scale_deadbeef_kato",
    "user_alice_0a1b2c3d_kato",
    "vector_persist_ffffffff_kato",
    "persist_test_00000000_kato",
])
def test_legacy_shape_is_in_scope(kb_id):
    """Data from before the generator carried a test marker is still reclaimable."""
    assert is_legacy_test_kb_id(kb_id) is True
    assert _is_safe_test_kb_id(kb_id, PREFIXES) is True


@pytest.mark.parametrize("kb_id", [
    "node0_kato",
    "node1_kato",
    "node2_kato",
    "node3_kato",
])
def test_production_nodes_are_never_in_scope(kb_id):
    """The documented production names. Deleting these would destroy real data."""
    assert _is_safe_test_kb_id(kb_id, PREFIXES) is False


@pytest.mark.parametrize("kb_id", [
    # Shares a legacy prefix but lacks the 8-hex token the old generator emitted.
    "user_alice_kato",
    "user_alice_prod_kato",
    "stress_200_kato",
    "large_scale_production_kato",
    # Right prefix, wrong token: too short, too long, not hex.
    "user_alice_0a1b2c3_kato",
    "user_alice_0a1b2c3d4_kato",
    "user_alice_zzzzzzzz_kato",
    # Uppercase hex is not what uuid4().hex produces.
    "user_alice_0A1B2C3D_kato",
    # No base-id segment at all.
    "user_alice_0a1b2c3d",
])
def test_legacy_prefix_alone_is_not_enough(kb_id):
    """A shared prefix must not be sufficient.

    "user_alice" is exactly the sort of name a real node could carry, which is
    why the legacy matcher requires the full shape the old generator produced
    rather than trusting the prefix.
    """
    assert is_legacy_test_kb_id(kb_id) is False
    assert _is_safe_test_kb_id(kb_id, PREFIXES) is False


@pytest.mark.parametrize("kb_id", [
    "",
    "   ",
    "'; DROP TABLE kato.patterns_data; --",
    "test_'; DROP TABLE kato.patterns_data; --",
    "test_node with spaces",
    "test_node-with-dashes",
])
def test_unsafe_identifiers_are_refused(kb_id):
    """DROP PARTITION cannot bind parameters, so the value is inlined.

    A test prefix must not on its own license inlining: validate_kb_id has to
    pass as well. The fourth case is the one that matters -- it carries a valid
    test prefix and would otherwise reach statement text.
    """
    assert _is_safe_test_kb_id(kb_id, PREFIXES) is False


def test_legacy_list_is_lowercase_and_sorted():
    """Kept sorted and duplicate-free so additions stay reviewable."""
    assert list(LEGACY_TEST_NODE_PREFIXES) == sorted(LEGACY_TEST_NODE_PREFIXES)
    assert len(set(LEGACY_TEST_NODE_PREFIXES)) == len(LEGACY_TEST_NODE_PREFIXES)
    assert all(p == p.lower() for p in LEGACY_TEST_NODE_PREFIXES)


def test_generator_now_emits_a_reclaimable_node_id():
    """The fix at source: new ids must be recognisable to cleanup.

    Without this, the legacy list above would need a new entry for every
    descriptive prefix anyone adds.
    """
    sys.path.insert(0, __file__.rsplit('/unit/', 1)[0] + '/integration')
    from test_database_persistence import generate_unique_node_id

    node_id = generate_unique_node_id("stress_200")
    assert node_id.startswith("test_"), node_id
    assert _is_safe_test_kb_id(f"{node_id}_kato", PREFIXES) is True


@pytest.mark.parametrize("raw,expected", [
    (None, 15),
    ("0", 0),
    ("30", 30),
    ("  45  ", 45),
    ("-5", 0),          # clamped: a negative window would purge the future
    ("not-a-number", 15),  # unparseable falls back rather than purging eagerly
    ("", 15),
])
def test_quiet_period_override(raw, expected, monkeypatch):
    """The quiet period is what keeps a concurrent suite's corpus intact.

    Every unusable value must fall back to the safe default rather than to zero,
    because zero means "purge partitions currently being written to".
    """
    from fixtures.store_test_cleanup import _quiet_minutes

    if raw is None:
        monkeypatch.delenv("KATO_TEST_PURGE_QUIET_MINUTES", raising=False)
    else:
        monkeypatch.setenv("KATO_TEST_PURGE_QUIET_MINUTES", raw)
    assert _quiet_minutes() == expected
