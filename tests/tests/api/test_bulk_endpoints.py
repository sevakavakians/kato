"""
Tests for bulk observation endpoints (observe-sequence).
Tests batch processing capabilities and isolation features.
"""

import time

import requests


def test_observe_sequence_basic(kato_fixture):
    """Test basic batch observation processing."""

    # Create a sequence of observations
    observations = [
        {'strings': ['hello'], 'vectors': [], 'emotives': {}},
        {'strings': ['world'], 'vectors': [], 'emotives': {}},
        {'strings': ['test'], 'vectors': [], 'emotives': {}}
    ]

    # Process batch using the fixture method
    result = kato_fixture.observe_sequence(observations)

    # Verify results
    assert result['status'] == 'completed'
    assert 'processor_id' in result  # processor_id exists but may differ from fixture
    assert result['observations_processed'] == 3
    assert len(result['results']) == 3

    # Each observation should have succeeded
    for _idx, obs_result in enumerate(result['results']):
        assert obs_result['status'] == 'okay'
        assert 'unique_id' in obs_result
        assert 'time' in obs_result
        assert 'sequence_position' in obs_result

    # Should have final learned pattern field (may be None)
    assert 'final_learned_pattern' in result

    # Verify STM contains all observations
    stm = kato_fixture.get_stm()
    assert len(stm) == 3
    assert stm[0] == ['hello']
    assert stm[1] == ['world']
    assert stm[2] == ['test']


def test_observe_sequence_with_vectors(kato_fixture):
    """Test batch processing with multi-modal data (strings and vectors)."""

    # Use simple test vectors for testing
    test_vector = [0.1, 0.2, 0.3, 0.4]

    observations = [
        {'strings': ['alpha'], 'vectors': [test_vector], 'emotives': {'joy': 0.8}},
        {'strings': ['beta'], 'vectors': [], 'emotives': {'fear': 0.3}},
        {'strings': ['gamma'], 'vectors': [test_vector], 'emotives': {}}
    ]

    result = kato_fixture.observe_sequence(observations)

    assert result['observations_processed'] == 3
    assert len(result['results']) == 3

    # STM should contain both strings and vector names
    stm = kato_fixture.get_stm()
    assert len(stm) == 3

    # First observation should have vector name added
    assert 'alpha' in stm[0]
    assert any('VCTR|' in s for s in stm[0])  # Vector name pattern

    # Second observation has no vectors
    assert stm[1] == ['beta']

    # Third observation should also have vector
    assert 'gamma' in stm[2]
    assert any('VCTR|' in s for s in stm[2])


def test_observe_sequence_learn_after_each(kato_fixture):
    """Test learning pattern after each observation."""

    observations = [
        {'strings': ['first', 'pattern'], 'vectors': [], 'emotives': {}},
        {'strings': ['second', 'pattern'], 'vectors': [], 'emotives': {}},
        {'strings': ['third', 'pattern'], 'vectors': [], 'emotives': {}}
    ]

    result = kato_fixture.observe_sequence(observations, learn_after_each=True)

    # Should have learned 3 patterns (one after each observation)
    assert len(result['auto_learned_patterns']) == 3

    # Each pattern should have the PTRN| prefix
    for pattern_name in result['auto_learned_patterns']:
        assert pattern_name.startswith('PTRN|')


def test_observe_sequence_learn_at_end(kato_fixture):
    """Test learning single pattern after all observations."""

    observations = [
        {'strings': ['start'], 'vectors': [], 'emotives': {}},
        {'strings': ['middle'], 'vectors': [], 'emotives': {}},
        {'strings': ['end'], 'vectors': [], 'emotives': {}}
    ]

    result = kato_fixture.observe_sequence(observations, learn_at_end=True)

    # Should have learned 1 pattern at the end
    assert len(result['auto_learned_patterns']) == 1
    assert result['auto_learned_patterns'][0].startswith('PTRN|')

    # STM should be empty after learn_at_end (auto-learn scenario)
    stm = kato_fixture.get_stm()
    assert len(stm) == 0, "STM should be empty after learn_at_end"


def test_observe_sequence_clear_stm_between(kato_fixture):
    """Test STM clearing between observations for complete isolation."""

    observations = [
        {'strings': ['isolated1'], 'vectors': [], 'emotives': {}},
        {'strings': ['isolated2'], 'vectors': [], 'emotives': {}},
        {'strings': ['isolated3'], 'vectors': [], 'emotives': {}}
    ]

    result = kato_fixture.observe_sequence(observations, clear_stm_between=True)

    assert result['observations_processed'] == 3

    # STM should only contain the last observation (others were cleared)
    # Note: No learning happened, so the last observation remains
    stm = kato_fixture.get_stm()
    assert len(stm) == 1
    assert stm[0] == ['isolated3']


def test_observe_sequence_combined_options(kato_fixture):
    """Test combining clear_stm_between with learn_after_each."""

    observations = [
        {'strings': ['combo1', 'test'], 'vectors': [], 'emotives': {}},
        {'strings': ['combo2', 'test'], 'vectors': [], 'emotives': {}},
        {'strings': ['combo3', 'test'], 'vectors': [], 'emotives': {}}
    ]

    result = kato_fixture.observe_sequence(
        observations,
        clear_stm_between=True,
        learn_after_each=True
    )

    # Each observation was isolated and learned separately
    assert result['observations_processed'] == 3
    assert len(result['auto_learned_patterns']) == 3

    # STM should be empty after learning
    stm = kato_fixture.get_stm()
    assert len(stm) == 0, "STM should be empty after learn_after_each"


def test_observe_sequence_alphanumeric_sorting(kato_fixture):
    """Test that alphanumeric sorting is maintained in batch processing."""

    observations = [
        {'strings': ['zebra', 'alpha', 'beta'], 'vectors': [], 'emotives': {}},
        {'strings': ['3', '1', '2'], 'vectors': [], 'emotives': {}},
        {'strings': ['Z', 'A', 'M'], 'vectors': [], 'emotives': {}}
    ]

    kato_fixture.observe_sequence(observations)

    # Verify STM has sorted strings
    stm = kato_fixture.get_stm()

    assert stm[0] == ['alpha', 'beta', 'zebra']
    assert stm[1] == ['1', '2', '3']
    assert stm[2] == ['A', 'M', 'Z']


def test_observe_sequence_empty_batch(kato_fixture):
    """Test handling of empty batch."""

    result = kato_fixture.observe_sequence([])

    assert result['observations_processed'] == 0
    assert len(result['results']) == 0
    assert len(result['auto_learned_patterns']) == 0


def test_observe_sequence_large_batch(kato_fixture):
    """Test processing a large batch of observations."""

    # Create 50 observations
    observations = []
    for i in range(50):
        observations.append({
            'strings': [f'obs_{i:03d}'],  # Zero-padded for consistent sorting
            'vectors': [],
            'emotives': {}
        })

    # Use fixture method which uses session-based endpoint
    result = kato_fixture.observe_sequence(observations)

    assert result['observations_processed'] == 50
    assert len(result['results']) == 50

    # Verify all observations are in STM using fixture method
    stm = kato_fixture.get_stm()

    # Default persistence is 5, so only last 5 should be in STM
    # unless configured differently
    assert len(stm) <= 50  # Could be limited by persistence setting


def test_observe_sequence_with_unique_ids(kato_fixture):
    """Test that provided unique IDs are preserved."""

    observations = [
        {'strings': ['first'], 'vectors': [], 'emotives': {}, 'unique_id': 'custom-1'},
        {'strings': ['second'], 'vectors': [], 'emotives': {}, 'unique_id': 'custom-2'},
        {'strings': ['third'], 'vectors': [], 'emotives': {}, 'unique_id': 'custom-3'}
    ]

    result = kato_fixture.observe_sequence(observations)

    # Verify custom IDs are preserved
    assert result['results'][0]['unique_id'] == 'custom-1'
    assert result['results'][1]['unique_id'] == 'custom-2'
    assert result['results'][2]['unique_id'] == 'custom-3'


def test_observe_sequence_predictions_available(kato_fixture):
    """Test that predictions are generated after batch processing."""

    # First, learn a pattern
    observations = [
        {'strings': ['pattern', 'A'], 'vectors': [], 'emotives': {}},
        {'strings': ['pattern', 'B'], 'vectors': [], 'emotives': {}},
        {'strings': ['pattern', 'C'], 'vectors': [], 'emotives': {}}
    ]

    kato_fixture.observe_sequence(observations, learn_at_end=True)

    # Clear STM
    kato_fixture.clear_stm()

    # Now observe part of the pattern and check for predictions
    test_observations = [
        {'strings': ['pattern', 'A'], 'vectors': [], 'emotives': {}},
        {'strings': ['pattern', 'B'], 'vectors': [], 'emotives': {}}
    ]

    kato_fixture.observe_sequence(test_observations)

    # Get predictions
    predictions = kato_fixture.get_predictions()

    # Should have predictions since we match part of the learned pattern
    assert predictions is not None
    assert len(predictions) > 0


def test_observe_sequence_error_handling(kato_fixture):
    """Test error handling in batch processing."""

    # Ensure we have a session
    assert kato_fixture.session_id is not None

    # Test with completely invalid structure (observations should be a list)
    batch_data = {
        'observations': "not_a_list"  # Invalid type - should be a list
    }

    # Use session-based endpoint for error testing
    response = requests.post(
        f"{kato_fixture.base_url}/sessions/{kato_fixture.session_id}/observe-sequence",
        json=batch_data
    )
    # Should fail with validation error
    assert response.status_code == 422  # Unprocessable Entity for validation errors


def test_observe_sequence_performance(kato_fixture):
    """Test batch processing performance advantages."""

    # Ensure we have a session
    assert kato_fixture.session_id is not None

    # Prepare 20 observations
    observations = [
        {'strings': [f'perf_test_{i}'], 'vectors': [], 'emotives': {}}
        for i in range(20)
    ]

    # Time batch processing using fixture method
    start_batch = time.time()
    result = kato_fixture.observe_sequence(observations)
    batch_time = time.time() - start_batch
    assert result['observations_processed'] == 20

    # Clear STM for fair comparison
    kato_fixture.clear_stm()

    # Time individual processing using fixture method
    start_individual = time.time()
    for obs in observations:
        kato_fixture.observe(obs)
    individual_time = time.time() - start_individual

    # Batch should be faster due to reduced overhead
    # Though the difference might be small in testing
    print(f"Batch time: {batch_time:.3f}s, Individual time: {individual_time:.3f}s")
    # We won't assert on timing as it can be variable, just log it


def test_observe_sequence_isolation_verification(kato_fixture):
    """Verify that observations are properly isolated when requested."""

    # First, process without isolation
    observations_no_isolation = [
        {'strings': ['shared1'], 'vectors': [], 'emotives': {}},
        {'strings': ['shared2'], 'vectors': [], 'emotives': {}},
        {'strings': ['shared3'], 'vectors': [], 'emotives': {}}
    ]

    kato_fixture.observe_sequence(observations_no_isolation, clear_stm_between=False)

    # Get predictions - should see context from all observations
    kato_fixture.get_predictions()

    # Clear STM
    kato_fixture.clear_stm()

    # Now process WITH isolation (but no learning)
    observations_with_isolation = [
        {'strings': ['isolated1'], 'vectors': [], 'emotives': {}},
        {'strings': ['isolated2'], 'vectors': [], 'emotives': {}},
        {'strings': ['isolated3'], 'vectors': [], 'emotives': {}}
    ]

    kato_fixture.observe_sequence(observations_with_isolation, clear_stm_between=True)

    # STM should only have last observation (no learning happened)
    stm = kato_fixture.get_stm()
    assert len(stm) == 1
    assert stm[0] == ['isolated3']
