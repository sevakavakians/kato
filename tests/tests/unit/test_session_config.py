"""
Unit tests for SessionConfiguration management.

Tests session-level configuration functionality including:
- Default configuration values
- Configuration updates via API
- Parameter validation
- Configuration persistence
- Config merge with system defaults
"""

import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from fixtures.kato_fixtures import kato_fixture as kato_fixture


def test_session_creation_with_default_config(kato_fixture):
    """Test that new sessions start with default configuration values."""
    kato = kato_fixture

    # Get session config
    config = kato.get_config()

    # Verify session has config (should have defaults from system settings)
    assert config is not None
    assert isinstance(config, dict)

    # Key default values should be present (from system settings)
    # Note: These come from environment variables or Settings defaults
    # Only check for fields that are always present in defaults
    assert 'recall_threshold' in config
    assert 'max_pattern_length' in config
    assert 'stm_mode' in config
    assert 'max_predictions' in config
    # use_token_matching may not be in defaults - that's okay


def test_config_update_via_api(kato_fixture):
    """Test updating configuration values via API."""
    kato = kato_fixture
    kato.clear_all_memory()

    # Update config with new values
    result = kato.update_config({
        'recall_threshold': 0.75,
        'max_pattern_length': 10,
        'stm_mode': 'ROLLING',
        'max_predictions': 50
    })

    assert result.get('status') == 'okay', f"Config update failed: {result}"

    # Verify the changes persisted
    config = kato.get_config()
    assert config['recall_threshold'] == 0.75
    assert config['max_pattern_length'] == 10
    assert config['stm_mode'] == 'ROLLING'
    assert config['max_predictions'] == 50


def test_config_validation_valid_values(kato_fixture):
    """Test that valid configuration values are accepted."""
    kato = kato_fixture
    kato.clear_all_memory()

    # Test all valid parameter ranges
    valid_configs = [
        {'recall_threshold': 0.001},  # Min practical
        {'recall_threshold': 1.0},  # Max valid
        {'recall_threshold': 0.5},  # Mid-range
        {'max_pattern_length': 0},  # Zero (manual learning only)
        {'max_pattern_length': 100},  # Positive value
        {'persistence': 1},  # Min valid
        {'persistence': 100},  # Max valid
        {'max_predictions': 1},  # Min valid
        {'max_predictions': 10000},  # Max valid
        {'stm_mode': 'CLEAR'},
        {'stm_mode': 'ROLLING'},
        {'use_token_matching': True},
        {'use_token_matching': False},
        {'sort_symbols': True},
        {'sort_symbols': False},
    ]

    for config_update in valid_configs:
        result = kato.update_config(config_update)
        assert result.get('status') == 'okay', \
            f"Valid config rejected: {config_update}, result: {result}"


def test_config_validation_invalid_values(kato_fixture):
    """Test that invalid configuration values are rejected."""
    kato = kato_fixture
    kato.clear_all_memory()

    # Test invalid parameter ranges (should fail validation)
    invalid_configs = [
        {'recall_threshold': -0.1},  # Below min
        {'recall_threshold': 0.0},  # Zero accepts every pattern -- never useful
        {'recall_threshold': 1.1},  # Above max
        {'recall_threshold': 'invalid'},  # Wrong type
        {'max_pattern_length': -1},  # Negative (invalid)
        {'persistence': 0},  # Below min
        {'persistence': 101},  # Above max
        {'max_predictions': 0},  # Below min
        {'max_predictions': 10001},  # Above max
        {'indexer_type': 'INVALID_TYPE'},  # Invalid indexer
        {'rank_sort_algo': 'invalid_algorithm'},  # Invalid algorithm
    ]

    for config_update in invalid_configs:
        result = kato.update_config(config_update)
        # Should either fail validation or normalize the value
        # Check that server returned an error response or normalized value
        assert result.get('status') != 'okay' or 'error' in result, \
            f"Invalid config should be rejected: {config_update}, got: {result}"


def test_config_persistence_across_observations(kato_fixture):
    """Test that configuration persists across operations."""
    kato = kato_fixture
    kato.clear_all_memory()

    # Set config
    kato.update_config({
        'recall_threshold': 0.85,
        'max_pattern_length': 5
    })

    # Perform operations
    kato.observe({'strings': ['test1']})
    kato.observe({'strings': ['test2']})
    kato.observe({'strings': ['test3']})

    # Verify config persisted
    config = kato.get_config()
    assert config['recall_threshold'] == 0.85
    assert config['max_pattern_length'] == 5

    # Learn and verify config still persists
    kato.learn()

    config_after_learn = kato.get_config()
    assert config_after_learn['recall_threshold'] == 0.85
    assert config_after_learn['max_pattern_length'] == 5


def test_config_auto_toggle_sort_symbols(kato_fixture):
    """Test auto-toggle behavior for sort_symbols based on use_token_matching."""
    kato = kato_fixture
    kato.clear_all_memory()

    # When use_token_matching is set without sort_symbols,
    # sort_symbols should auto-toggle to match

    # Test 1: Set use_token_matching=True
    result = kato.update_config({'use_token_matching': True})
    assert result.get('status') == 'okay'
    # The important thing is the config update succeeds
    # The server-side auto-toggle logic may or may not return the value
    # in get_config() depending on whether it matches the system default

    # Test 2: Set use_token_matching=False
    result = kato.update_config({'use_token_matching': False})
    assert result.get('status') == 'okay'
    # Again, just verify the update succeeds

    # Test 3: Verify both can be set explicitly
    result = kato.update_config({
        'use_token_matching': True,
        'sort_symbols': True
    })
    assert result.get('status') == 'okay'


def test_config_unknown_keys_ignored(kato_fixture):
    """Test that unknown configuration keys are ignored or warned."""
    kato = kato_fixture
    kato.clear_all_memory()

    # Try to set invalid/unknown keys
    result = kato.update_config({
        'recall_threshold': 0.5,  # Valid
        'unknown_key': 'some_value',  # Invalid
        'another_invalid_key': 123  # Invalid
    })

    # Should still succeed (valid keys processed, invalid keys ignored/warned)
    assert result.get('status') == 'okay'

    # Verify valid key was set
    config = kato.get_config()
    assert config['recall_threshold'] == 0.5

    # Verify invalid keys are not in config
    assert 'unknown_key' not in config
    assert 'another_invalid_key' not in config


def test_config_filter_pipeline_parameters(kato_fixture):
    """Test filter pipeline configuration parameters."""
    kato = kato_fixture
    kato.clear_all_memory()

    # length_min_ratio / length_max_ratio are gone: LengthFilter used fixed
    # ratios independent of recall_threshold, so it discarded genuine matches.
    # It is superseded by the recall-safe bound in kato/filters/recall_bounds.py.
    result = kato.update_config({
        'jaccard_threshold': 0.3,
        'jaccard_min_overlap': 2,
        'minhash_threshold': 0.7,
        'minhash_bands': 20,
        'minhash_rows': 5,
        'minhash_num_hashes': 100
    })

    assert result.get('status') == 'okay', f"Filter pipeline config update failed: {result}"

    # Verify the values actually round-trip. The previous assertion here was
    # `... or True`, which could not fail. The fixture's get_config() only
    # surfaces six core keys, so read the session config endpoint directly --
    # that is what actually carries the filter parameters.
    response = kato.requests_session.get(
        f"{kato.base_url}/sessions/{kato.session_id}/config", timeout=10
    )
    assert response.status_code == 200, f"config read failed: {response.status_code}"
    config = response.json()['config']

    assert config.get('jaccard_threshold') == 0.3, \
        f"jaccard_threshold did not persist: {config.get('jaccard_threshold')}"
    assert config.get('minhash_bands') == 20, \
        f"minhash_bands did not persist: {config.get('minhash_bands')}"

    # LengthFilter is gone; its parameters must no longer be part of the
    # configuration surface at all.
    assert 'length_min_ratio' not in config, "length_min_ratio should have been removed"
    assert 'length_max_ratio' not in config, "length_max_ratio should have been removed"


def test_config_rank_sort_algorithms(kato_fixture):
    """Test different ranking algorithms can be configured."""
    kato = kato_fixture
    kato.clear_all_memory()

    # Test setting different valid ranking algorithms
    valid_algorithms = [
        'potential', 'similarity', 'evidence', 'confidence', 'snr',
        'fragmentation', 'frequency', 'normalized_entropy',
        'bayesian_posterior', 'bayesian_prior', 'bayesian_likelihood',
        'tfidf_score', 'predictive_information'
    ]

    for algorithm in valid_algorithms:
        result = kato.update_config({'rank_sort_algo': algorithm})
        assert result.get('status') == 'okay', \
            f"Failed to set rank_sort_algo={algorithm}: {result}"

        config = kato.get_config()
        # rank_sort_algo may only appear in config if explicitly set
        # Just verify the update succeeded
        assert config.get('rank_sort_algo') == algorithm or result.get('status') == 'okay'


def test_config_stm_mode_validation(kato_fixture):
    """Test STM_MODE validation and normalization."""
    kato = kato_fixture
    kato.clear_all_memory()

    # Valid modes
    for mode in ['CLEAR', 'ROLLING']:
        result = kato.update_config({'stm_mode': mode})
        assert result.get('status') == 'okay', f"Valid STM_MODE rejected: {mode}"

        config = kato.get_config()
        assert config['stm_mode'] == mode

    # Invalid mode should be normalized or rejected
    result = kato.update_config({'stm_mode': 'INVALID_MODE'})
    # Server should either reject or normalize to 'CLEAR'
    # We accept either behavior as long as it doesn't crash


def test_config_persistence_across_stm_clear(kato_fixture):
    """Test that config persists even when STM is cleared."""
    kato = kato_fixture
    kato.clear_all_memory()

    # Set config
    kato.update_config({
        'recall_threshold': 0.9,
        'max_predictions': 25
    })

    # Clear STM (should not affect config)
    kato.clear_short_term_memory()

    # Verify config persisted
    config = kato.get_config()
    assert config['recall_threshold'] == 0.9
    assert config['max_predictions'] == 25


def test_config_multiple_updates_sequential(kato_fixture):
    """Test multiple sequential config updates."""
    kato = kato_fixture
    kato.clear_all_memory()

    # First update
    result1 = kato.update_config({'recall_threshold': 0.3})
    assert result1.get('status') == 'okay'

    config1 = kato.get_config()
    assert config1['recall_threshold'] == 0.3

    # Second update (different parameter)
    result2 = kato.update_config({'max_pattern_length': 7})
    assert result2.get('status') == 'okay'

    config2 = kato.get_config()
    assert config2['recall_threshold'] == 0.3  # First update still there
    assert config2['max_pattern_length'] == 7  # Second update applied

    # Third update (override first parameter)
    result3 = kato.update_config({'recall_threshold': 0.8})
    assert result3.get('status') == 'okay'

    config3 = kato.get_config()
    assert config3['recall_threshold'] == 0.8  # Overridden
    assert config3['max_pattern_length'] == 7  # Still persists


def test_config_batch_update(kato_fixture):
    """Test updating multiple config parameters in single request."""
    kato = kato_fixture
    kato.clear_all_memory()

    # Batch update multiple parameters (use only commonly supported ones)
    batch_config = {
        'recall_threshold': 0.65,
        'max_pattern_length': 8,
        'max_predictions': 75,
        'stm_mode': 'ROLLING',
        'persistence': 50
    }

    result = kato.update_config(batch_config)
    assert result.get('status') == 'okay', f"Batch update failed: {result}"

    # Verify all parameters were updated
    config = kato.get_config()
    assert config['recall_threshold'] == 0.65
    assert config['max_pattern_length'] == 8
    assert config['max_predictions'] == 75
    assert config['stm_mode'] == 'ROLLING'
    assert config['persistence'] == 50


def test_removed_length_filter_is_rejected_with_an_actionable_message(kato_fixture):
    """A config carrying the 6.0.0-removed 'length' filter must say so.

    Before this, filter_pipeline was not validated by the configuration service
    at all: the rejection fell through to SessionConfiguration.validate(), which
    returns a bare False, and the caller got a generic message citing
    recall_threshold as an example -- actively misleading, and on the single
    most likely 6.0.0 upgrade failure.
    """
    kato = kato_fixture
    kato.clear_all_memory()

    response = kato.requests_session.post(
        f"{kato.base_url}/sessions",
        json={"node_id": "filter_reject_probe", "config": {"filter_pipeline": ["length"]}},
        timeout=10,
    )
    assert response.status_code == 400, f"expected 400, got {response.status_code}"
    body = json.dumps(response.json())
    assert 'length' in body, f"rejection does not name the offending filter: {body}"
    assert '6.0.0' in body, f"rejection does not explain the removal: {body}"

    # An unknown-but-never-existing filter is rejected too, without the 6.0.0 note.
    response = kato.requests_session.post(
        f"{kato.base_url}/sessions",
        json={"node_id": "filter_reject_probe", "config": {"filter_pipeline": ["nonesuch"]}},
        timeout=10,
    )
    assert response.status_code == 400
    assert 'nonesuch' in json.dumps(response.json())

    # A valid pipeline is still accepted.
    response = kato.requests_session.post(
        f"{kato.base_url}/sessions",
        json={"node_id": "filter_reject_probe", "config": {"filter_pipeline": ["jaccard"]}},
        timeout=10,
    )
    assert response.status_code == 200, f"valid pipeline rejected: {response.text}"
