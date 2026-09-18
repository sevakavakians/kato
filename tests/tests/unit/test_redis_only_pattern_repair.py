from types import SimpleNamespace
from unittest.mock import Mock

from kato.informatics.knowledge_base import SuperKnowledgeBase


def _knowledge_base():
    kb = object.__new__(SuperKnowledgeBase)
    kb.id = "repair-test"
    kb.persistence = 7
    kb.emotives_available = set()
    kb.clickhouse_writer = Mock()
    kb.redis_writer = Mock()
    kb.metadata_router = Mock()
    kb.clickhouse_writer.get_present_pattern_names.return_value = set()
    kb.clickhouse_writer.get_present_metadata_pattern_names.return_value = set()
    kb.redis_writer.client.exists.return_value = 0
    kb._update_symbol_affinity = Mock()
    return kb


def test_opt_in_restores_exact_redis_only_pattern_without_counter_changes(monkeypatch):
    monkeypatch.setenv("KATO_REPAIR_REDIS_ONLY_PATTERNS", "true")
    kb = _knowledge_base()
    kb.redis_writer.client.set.return_value = False
    metadata = {"window_text": ["eight exact tokens live in this test row"]}
    kb.metadata_router.get_metadata.return_value = {
        "frequency": 1,
        "emotives": [],
        "metadata": metadata,
    }
    pattern = SimpleNamespace(
        name="pattern-id",
        pattern_data=[["VCTR|one"], ["WINDOW_ID|one"]],
    )

    assert kb.learnPattern(pattern, emotives=[], metadata=metadata) is True

    kb.clickhouse_writer.write_pattern.assert_called_once_with(pattern)
    kb.redis_writer.increment_frequency.assert_not_called()
    kb.redis_writer.batch_update_symbol_stats.assert_not_called()


def test_opt_in_completes_claim_only_pattern(monkeypatch):
    monkeypatch.setenv("KATO_REPAIR_REDIS_ONLY_PATTERNS", "true")
    kb = _knowledge_base()
    kb.redis_writer.client.set.return_value = False
    kb.metadata_router.get_metadata.return_value = {"frequency": 1}
    metadata = {"window_text": ["eight exact tokens live in this test row"]}
    pattern = SimpleNamespace(
        name="pattern-id",
        pattern_data=[["VCTR|one"], ["WINDOW_ID|one"]],
    )

    assert kb.learnPattern(pattern, emotives=[], metadata=metadata) is True

    kb.clickhouse_writer.write_pattern.assert_called_once_with(pattern)
    kb.metadata_router.upsert_pattern_metadata.assert_called_once_with(
        pattern_name="pattern-id",
        emotives=[],
        metadata=metadata,
    )
    kb.redis_writer.batch_update_symbol_stats.assert_called_once_with(
        symbol_counts={"VCTR|one": 1, "WINDOW_ID|one": 1},
        pattern_name="pattern-id",
        is_new_pattern=True,
        total_symbol_count=2,
    )


def test_repair_mode_refuses_nonexact_redis_state(monkeypatch):
    monkeypatch.setenv("KATO_REPAIR_REDIS_ONLY_PATTERNS", "true")
    kb = _knowledge_base()
    kb.redis_writer.client.set.return_value = False
    kb.metadata_router.get_metadata.return_value = {
        "frequency": 2,
        "emotives": [],
        "metadata": {},
    }
    pattern = SimpleNamespace(
        name="pattern-id",
        pattern_data=[["VCTR|one"], ["WINDOW_ID|one"]],
    )

    try:
        kb.learnPattern(pattern, emotives=[], metadata={})
    except Exception as exc:
        assert "Refusing Redis-only repair" in str(exc)
    else:
        raise AssertionError("nonexact Redis state was repaired")

    kb.clickhouse_writer.write_pattern.assert_not_called()
    kb.redis_writer.increment_frequency.assert_not_called()


def test_default_relearn_behavior_is_unchanged(monkeypatch):
    monkeypatch.delenv("KATO_REPAIR_REDIS_ONLY_PATTERNS", raising=False)
    kb = _knowledge_base()
    kb.redis_writer.client.set.return_value = False
    kb.metadata_router.get_metadata.return_value = {
        "frequency": 1,
        "emotives": [],
        "metadata": {},
    }
    pattern = SimpleNamespace(
        name="pattern-id",
        pattern_data=[["VCTR|one"], ["WINDOW_ID|one"]],
    )

    assert kb.learnPattern(pattern, emotives=[], metadata={}) is False

    kb.clickhouse_writer.get_present_pattern_names.assert_not_called()
    kb.clickhouse_writer.write_pattern.assert_not_called()
    kb.redis_writer.increment_frequency.assert_called_once_with("pattern-id")


def test_repair_refuses_unreadable_sidecar_metadata(monkeypatch):
    monkeypatch.setenv("KATO_REPAIR_REDIS_ONLY_PATTERNS", "true")
    kb = _knowledge_base()
    kb.redis_writer.client.set.return_value = False
    kb.metadata_router.get_metadata.return_value = {"frequency": 1}
    kb.clickhouse_writer.get_present_metadata_pattern_names.return_value = {"pattern-id"}
    pattern = SimpleNamespace(name="pattern-id", pattern_data=[["a"], ["b"]])
    import pytest
    with pytest.raises(Exception, match="metadata absence cannot be proven"):
        kb.learnPattern(pattern)
    kb.clickhouse_writer.write_pattern.assert_not_called()
    kb.redis_writer.batch_update_symbol_stats.assert_not_called()


def test_repair_propagates_presence_query_failure(monkeypatch):
    monkeypatch.setenv("KATO_REPAIR_REDIS_ONLY_PATTERNS", "true")
    kb = _knowledge_base()
    kb.redis_writer.client.set.return_value = False
    kb.clickhouse_writer.get_present_pattern_names.side_effect = RuntimeError("storage unavailable")
    pattern = SimpleNamespace(name="pattern-id", pattern_data=[["a"], ["b"]])
    import pytest
    with pytest.raises(Exception, match="storage unavailable"):
        kb.learnPattern(pattern)
    kb.clickhouse_writer.write_pattern.assert_not_called()
    kb.redis_writer.increment_frequency.assert_not_called()


def test_repair_refuses_unmigrated_legacy_metadata(monkeypatch):
    monkeypatch.setenv("KATO_REPAIR_REDIS_ONLY_PATTERNS", "true")
    kb = _knowledge_base()
    kb.redis_writer.client.set.return_value = False
    kb.metadata_router.get_metadata.return_value = {"frequency": 1}
    kb.redis_writer.client.exists.return_value = 1
    pattern = SimpleNamespace(name="pattern-id", pattern_data=[["a"], ["b"]])
    import pytest
    with pytest.raises(Exception, match="metadata absence cannot be proven"):
        kb.learnPattern(pattern)
    kb.clickhouse_writer.write_pattern.assert_not_called()
