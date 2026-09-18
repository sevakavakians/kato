from types import SimpleNamespace
from unittest.mock import Mock

from kato.storage.clickhouse_writer import ClickHouseWriter


def test_pattern_insert_waits_for_clickhouse_commit():
    client = Mock()
    writer = ClickHouseWriter("durability-test", client)
    pattern = SimpleNamespace(
        name="pattern-id",
        pattern_data=[["VCTR|one"], ["WINDOW_ID|one"]],
        length=2,
    )

    assert writer.write_pattern(pattern) is True

    assert client.insert.call_count == 1
    assert client.insert.call_args.kwargs["settings"] == {
        "async_insert": 1,
        "wait_for_async_insert": 1,
    }


def _purge_writer():
    writer = object.__new__(ClickHouseWriter)
    writer.kb_id = "purge_test"
    writer.client = Mock()
    writer.flush_if_pending = Mock()
    writer.client.query.return_value.result_rows = []
    return writer


def test_purge_removes_sidecar_and_verifies_its_absence():
    writer = _purge_writer()
    name = "a" * 40
    assert writer.purge_patterns([name]) == 1
    commands = [call.args[0] for call in writer.client.command.call_args_list]
    assert any("kato.patterns_metadata DELETE" in command for command in commands)
    assert all("kb_id = 'purge_test'" in command for command in commands)
    assert all(call.kwargs["settings"] == {"mutations_sync": 2}
               for call in writer.client.command.call_args_list)
    queries = [call.args[0] for call in writer.client.query.call_args_list]
    assert any("FROM kato.patterns_metadata" in query for query in queries)


def test_purge_cannot_succeed_with_remaining_sidecar():
    import pytest
    writer = _purge_writer()
    writer.client.query.side_effect = [
        SimpleNamespace(result_rows=[]),
        SimpleNamespace(result_rows=[]),
        SimpleNamespace(result_rows=[("a" * 40,)]),
    ]
    with pytest.raises(RuntimeError, match="metadata="):
        writer.purge_patterns(["a" * 40])


def test_purge_validates_all_identifiers_before_any_mutation():
    import pytest
    writer = _purge_writer()
    with pytest.raises(ValueError):
        writer.purge_patterns(["a" * 40, "bad'pattern"])
    writer.client.command.assert_not_called()
    writer.flush_if_pending.assert_not_called()


def test_metric_invalidation_updates_all_versions_and_preserves_payload():
    writer = _purge_writer()
    writer.client.query.side_effect = [
        SimpleNamespace(result_rows=[(7,)]),
        SimpleNamespace(result_rows=[(0,)]),
    ]
    assert writer.invalidate_precomputed_metrics() == 7
    command = writer.client.command.call_args.args[0]
    assert "entropy = NULL" in command
    assert "tf_vector = '{}'" in command
    assert "emotives =" not in command
    assert "metadata =" not in command
    assert "WHERE kb_id = 'purge_test'" in command
    assert writer.client.command.call_args.kwargs["settings"] == {"mutations_sync": 2}


def test_metric_invalidation_fails_if_metrics_remain():
    import pytest
    writer = _purge_writer()
    writer.client.query.return_value.result_rows = [(1,)]
    with pytest.raises(RuntimeError, match="invalidation failed"):
        writer.invalidate_precomputed_metrics()


def test_sidecar_verification_propagates_query_errors():
    import pytest
    writer = _purge_writer()
    writer.client.query.side_effect = RuntimeError("storage unavailable")
    with pytest.raises(RuntimeError, match="storage unavailable"):
        writer.get_present_metadata_pattern_names(["a" * 40])
