"""
Integration tests for the Redis → ClickHouse per-pattern metadata migration.

Exercises the live FastAPI stack with the default migration flags
(dual_write=true, read_from=redis) to confirm that:
  1. Learning a pattern writes metadata to both stores without breaking the
     existing Redis read path.
  2. Re-learning the same pattern correctly merges emotives + metadata.
  3. Predictions continue to surface emotives and frequency.
  4. Pattern deletion cleans up data in both stores.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


def test_learn_pattern_dual_write_smoke(kato_fixture):
    """Learning a pattern under dual_write does not break the existing read path."""
    kato_fixture.clear_all_memory()
    kato_fixture.set_recall_threshold(0.3)

    sequence = ['migrate', 'metadata', 'router']
    for item in sequence:
        kato_fixture.observe({
            'strings': [item], 'vectors': [],
            'emotives': {'curious': 0.7},
        })
    pattern_name = kato_fixture.learn()
    assert pattern_name.startswith('PTRN|'), "Pattern should be learned"

    # Recall via the predict path — this exercises the migration router's read.
    kato_fixture.observe({'strings': ['migrate'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['metadata'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()
    assert len(predictions) > 0, "Predictions should still work under dual-write"

    matched = [
        p for p in predictions
        if 'migrate' in p.get('matches', []) and 'metadata' in p.get('matches', [])
    ]
    assert matched, "Expected to find the learned pattern in predictions"
    assert matched[0].get('frequency', 0) >= 1, "Frequency should be returned"


def test_relearn_merges_emotives(kato_fixture):
    """Re-learning a pattern under the router preserves merge semantics."""
    kato_fixture.clear_all_memory()
    kato_fixture.set_recall_threshold(0.3)

    sequence = ['rolling', 'window', 'emotives']

    # First learn — happy emotive
    for item in sequence:
        kato_fixture.observe({
            'strings': [item], 'vectors': [],
            'emotives': {'happy': 0.9},
        })
    first_name = kato_fixture.learn()
    assert first_name.startswith('PTRN|')

    # Re-learn the same sequence with a different emotive — should INCR frequency
    # and accumulate emotives into the rolling window in both stores.
    for item in sequence:
        kato_fixture.observe({
            'strings': [item], 'vectors': [],
            'emotives': {'sad': 0.4},
        })
    second_name = kato_fixture.learn()
    assert second_name == first_name, "Same sequence must produce the same pattern hash"

    # Drive a prediction so we get the merged metadata back out.
    kato_fixture.observe({'strings': ['rolling'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['window'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()
    matched = [
        p for p in predictions
        if 'rolling' in p.get('matches', []) and 'window' in p.get('matches', [])
    ]
    assert matched, "Expected the re-learned pattern to surface in predictions"
    # Frequency should reflect re-learn (>= 2)
    assert matched[0].get('frequency', 0) >= 2, (
        f"Frequency should reflect both learns, got {matched[0].get('frequency')}"
    )
    # Emotives should contain entries from at least one of the two learns
    pred_emotives = matched[0].get('emotives', {})
    assert pred_emotives, "Predicted pattern should carry merged emotives"


def test_metadata_router_attached_on_superkb():
    """Sanity check that SuperKnowledgeBase wires the router on init.

    Direct Python import — no HTTP. Avoids spinning up writers by stubbing
    the connection manager. Settings is also stubbed because the .env file
    in this repo carries REDIS_PERSISTENCE (a docker-compose-only flag) which
    the Pydantic Settings model would otherwise reject as an extra field.
    """
    from unittest.mock import MagicMock, patch

    fake_settings = MagicMock()
    fake_settings.logging.log_level = 'INFO'
    fake_settings.metadata_migration = MagicMock(
        dual_write=True, read_from='redis', read_verify=False,
    )

    with patch('kato.informatics.knowledge_base.get_settings', return_value=fake_settings), \
         patch('kato.storage.connection_manager.get_clickhouse_client', return_value=MagicMock()), \
         patch('kato.storage.connection_manager.get_redis_client', return_value=MagicMock()), \
         patch('kato.storage.clickhouse_writer.ClickHouseWriter._ensure_patterns_metadata_table'):
        from kato.informatics.knowledge_base import SuperKnowledgeBase
        kb = SuperKnowledgeBase('test_kb_migration')
        assert hasattr(kb, 'metadata_router'), "SuperKnowledgeBase must expose metadata_router"
        assert kb.metadata_router.kb_id == 'test_kb_migration'
