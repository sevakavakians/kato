"""
Integration tests for rolling window auto-learn feature.

Tests end-to-end scenarios with API endpoints and real streaming data patterns.
"""

import time


def test_api_gene_update_stm_mode(kato_fixture):
    """Test updating STM_MODE through the genes API."""
    kato_fixture.clear_all_memory()

    # Test updating to ROLLING mode
    result = kato_fixture.update_genes({'stm_mode': 'ROLLING'})
    assert result.get('status') == 'okay', f"Failed to update STM_MODE: {result}"

    # Verify the change took effect
    genes = kato_fixture.get_genes()
    assert genes.get('stm_mode') == 'ROLLING', f"STM_MODE not updated in genes: {genes}"

    # Test updating back to CLEAR mode
    result = kato_fixture.update_genes({'stm_mode': 'CLEAR'})
    assert result.get('status') == 'okay', f"Failed to update STM_MODE back to CLEAR: {result}"

    genes = kato_fixture.get_genes()
    assert genes.get('stm_mode') == 'CLEAR', f"STM_MODE not updated back to CLEAR: {genes}"


def test_streaming_data_scenario(kato_fixture):
    """Test rolling window with streaming data pattern."""
    kato_fixture.clear_all_memory()
    kato_fixture.update_genes({
        'max_pattern_length': 4,
        'stm_mode': 'ROLLING'
    })

    # Simulate streaming sensor data
    streaming_data = [
        ['sensor_start'],
        ['temperature', '20'],
        ['humidity', '60'],
        ['pressure', '1013'],  # First auto-learn: [sensor_start, temp_20, humid_60, press_1013]
        ['temperature', '21'],  # Second auto-learn: [temp_20, humid_60, press_1013, temp_21]
        ['humidity', '61'],     # Third auto-learn: [humid_60, press_1013, temp_21, humid_61]
        ['pressure', '1014'],   # Fourth auto-learn: [press_1013, temp_21, humid_61, press_1014]
    ]

    learned_patterns = []
    for i, data in enumerate(streaming_data):
        result = kato_fixture.observe({'strings': data, 'vectors': [], 'emotives': {}})

        if result.get('auto_learned_pattern'):
            learned_patterns.append(result['auto_learned_pattern'])
            print(f"Step {i}: Learned pattern {result['auto_learned_pattern']}")

    # Should have learned overlapping patterns
    assert len(learned_patterns) >= 4, f"Expected at least 4 patterns, got {len(learned_patterns)}"

    # Final STM should contain last 3 events (window_size - 1)
    stm = kato_fixture.get_short_term_memory()
    assert len(stm) == 3, f"Final STM should have 3 events, got: {stm}"
    # Note: Symbols are sorted alphanumerically within each event
    expected_last_events = [['21', 'temperature'], ['61', 'humidity'], ['1014', 'pressure']]
    assert stm == expected_last_events, f"Expected {expected_last_events}, got {stm}"


def test_pattern_prediction_with_rolling_mode(kato_fixture):
    """Test that rolling mode improves pattern predictions."""
    kato_fixture.clear_all_memory()
    kato_fixture.update_genes({
        'max_pattern_length': 3,
        'stm_mode': 'ROLLING'
    })

    # Learn a sequence pattern multiple times with overlap
    base_sequence = ['morning', 'coffee', 'work', 'lunch', 'meeting', 'home']

    # Feed the sequence to create overlapping patterns
    for event in base_sequence:
        kato_fixture.observe({'strings': [event], 'vectors': [], 'emotives': {}})

    # Clear STM and test predictions
    kato_fixture.clear_short_term_memory()

    # Start a similar sequence
    kato_fixture.observe({'strings': ['morning'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['coffee'], 'vectors': [], 'emotives': {}})

    # Should predict 'work' based on learned patterns
    predictions = kato_fixture.get_predictions()
    assert len(predictions) > 0, "Should have predictions after learning"

    # Look for 'work' in future predictions
    found_work_prediction = False
    for pred in predictions:
        future_events = pred.get('future', [])
        for event_list in future_events:
            if 'work' in event_list:
                found_work_prediction = True
                break

    assert found_work_prediction, f"Should predict 'work' after 'morning' -> 'coffee'. Predictions: {predictions}"


def test_time_series_pattern_learning(kato_fixture):
    """Test rolling window with time-series like patterns."""
    kato_fixture.clear_all_memory()
    kato_fixture.update_genes({
        'max_pattern_length': 5,
        'stm_mode': 'ROLLING'
    })

    # Simulate time series: up, up, down, down, stable pattern
    pattern = ['up', 'up', 'down', 'down', 'stable']
    cycles = 3  # Repeat pattern 3 times

    learned_patterns = []
    for cycle in range(cycles):
        for event in pattern:
            result = kato_fixture.observe({'strings': [event], 'vectors': [], 'emotives': {}})
            if result.get('auto_learned_pattern'):
                learned_patterns.append(result['auto_learned_pattern'])

    # Should learn many overlapping patterns
    assert len(learned_patterns) >= 10, f"Expected many patterns from repeating cycles, got {len(learned_patterns)}"

    # Test prediction after partial pattern
    kato_fixture.clear_short_term_memory()
    kato_fixture.observe({'strings': ['up'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['up'], 'vectors': [], 'emotives': {}})

    predictions = kato_fixture.get_predictions()
    assert len(predictions) > 0, "Should predict after learning time series patterns"


def test_multi_modal_rolling_window(kato_fixture):
    """Test rolling window with multi-modal data (strings + vectors + emotives)."""
    kato_fixture.clear_all_memory()
    kato_fixture.update_genes({
        'max_pattern_length': 3,
        'stm_mode': 'ROLLING'
    })

    # Multi-modal observations
    observations = [
        {
            'strings': ['action', 'start'],
            'vectors': [[0.1, 0.2, 0.3]],
            'emotives': {'confidence': 0.8}
        },
        {
            'strings': ['process'],
            'vectors': [[0.4, 0.5, 0.6]],
            'emotives': {'confidence': 0.9}
        },
        {
            'strings': ['action', 'end'],
            'vectors': [[0.7, 0.8, 0.9]],
            'emotives': {'confidence': 0.7}
        },
        {
            'strings': ['cleanup'],
            'vectors': [[0.2, 0.3, 0.4]],
            'emotives': {'confidence': 0.6}
        }
    ]

    learned_patterns = []
    for obs in observations:
        result = kato_fixture.observe(obs)
        if result.get('auto_learned_pattern'):
            learned_patterns.append(result['auto_learned_pattern'])

    # Should learn patterns including vector and emotive data
    assert len(learned_patterns) >= 2, f"Expected at least 2 patterns, got {len(learned_patterns)}"

    # Final STM should maintain window
    stm = kato_fixture.get_short_term_memory()
    assert len(stm) == 2, f"Expected STM window of 2, got {len(stm)}: {stm}"


def test_bulk_observation_with_rolling_mode(kato_fixture):
    """Test rolling window with bulk observation API."""
    kato_fixture.clear_all_memory()
    kato_fixture.update_genes({
        'max_pattern_length': 3,
        'stm_mode': 'ROLLING'
    })

    # Bulk observations
    bulk_data = [
        {'strings': ['bulk1'], 'vectors': [], 'emotives': {}},
        {'strings': ['bulk2'], 'vectors': [], 'emotives': {}},
        {'strings': ['bulk3'], 'vectors': [], 'emotives': {}},
        {'strings': ['bulk4'], 'vectors': [], 'emotives': {}},
        {'strings': ['bulk5'], 'vectors': [], 'emotives': {}},
    ]

    # Process bulk observations
    result = kato_fixture.observe_sequence(bulk_data)
    assert result.get('status') == 'completed', f"Bulk observation failed: {result}"

    # Should have auto-learned multiple patterns
    auto_learned_patterns = result.get('auto_learned_patterns', [])
    assert len(auto_learned_patterns) >= 3, f"Expected at least 3 patterns from bulk, got {len(auto_learned_patterns)}"

    # STM should maintain rolling window
    stm = kato_fixture.get_short_term_memory()
    assert len(stm) == 2, f"Expected rolling window of 2 after bulk, got {len(stm)}: {stm}"


def test_rolling_mode_memory_efficiency(kato_fixture):
    """Test that rolling mode doesn't cause memory bloat with continuous learning."""
    kato_fixture.clear_all_memory()
    kato_fixture.update_genes({
        'max_pattern_length': 4,
        'stm_mode': 'ROLLING'
    })

    # Generate a long sequence to test memory efficiency
    num_events = 100
    learned_patterns = []

    start_time = time.time()
    for i in range(num_events):
        result = kato_fixture.observe({'strings': [f'event_{i}'], 'vectors': [], 'emotives': {}})
        if result.get('auto_learned_pattern'):
            learned_patterns.append(result['auto_learned_pattern'])

    end_time = time.time()
    processing_time = end_time - start_time

    # Should learn many patterns efficiently
    expected_patterns = num_events - 3  # First 3 events don't trigger auto-learn
    assert len(learned_patterns) >= expected_patterns * 0.9, \
        f"Expected ~{expected_patterns} patterns, got {len(learned_patterns)}"

    # STM should remain bounded
    stm = kato_fixture.get_short_term_memory()
    assert len(stm) <= 4, f"STM should be bounded to window size, got {len(stm)}: {stm}"

    # Processing should be reasonably fast (less than 1 second per 10 events)
    assert processing_time < (num_events / 10), \
        f"Processing too slow: {processing_time:.2f}s for {num_events} events"

    print(f"Processed {num_events} events in {processing_time:.2f}s, learned {len(learned_patterns)} patterns")


def test_mode_switching_during_operation(kato_fixture):
    """Test switching between CLEAR and ROLLING modes during operation."""
    kato_fixture.clear_all_memory()

    # Start with CLEAR mode
    kato_fixture.update_genes({
        'max_pattern_length': 3,
        'stm_mode': 'CLEAR'
    })

    # Add some events
    for event in ['switch1', 'switch2', 'switch3']:
        kato_fixture.observe({'strings': [event], 'vectors': [], 'emotives': {}})

    # STM should be cleared in CLEAR mode
    stm = kato_fixture.get_short_term_memory()
    assert len(stm) == 0, f"CLEAR mode should empty STM, got: {stm}"

    # Switch to ROLLING mode
    kato_fixture.update_genes({'stm_mode': 'ROLLING'})

    # Add more events
    for event in ['switch4', 'switch5', 'switch6']:
        kato_fixture.observe({'strings': [event], 'vectors': [], 'emotives': {}})

    # STM should maintain window in ROLLING mode
    stm = kato_fixture.get_short_term_memory()
    assert len(stm) == 2, f"ROLLING mode should maintain window, got {len(stm)}: {stm}"
    assert stm == [['switch5'], ['switch6']], f"Wrong window content: {stm}"
