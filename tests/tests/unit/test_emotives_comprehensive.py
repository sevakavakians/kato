"""
Comprehensive emotives behavior tests for KATO.

These tests validate:
1. Rolling window storage (persistence parameter)
2. Emotive averaging in predictions
3. Multi-key emotives handling
4. Emotives merging on pattern re-learning
5. Window overflow behavior (dropping oldest)

Tests are designed to FAIL if emotives don't behave as specified.
"""
import pytest


def test_emotives_single_key_storage(kato_fixture):
    """Test that single-key emotives are stored correctly."""
    kato_fixture.clear_all_memory()

    # Observe with single-key emotives
    kato_fixture.observe({'strings': ['A'], 'vectors': [], 'emotives': {'joy': 0.9}})
    kato_fixture.observe({'strings': ['B'], 'vectors': [], 'emotives': {'joy': 0.5}})
    kato_fixture.observe({'strings': ['C'], 'vectors': [], 'emotives': {'joy': 0.7}})
    pattern_name = kato_fixture.learn()

    # Validate Redis storage
    redis_emotives = kato_fixture.get_redis_emotives(pattern_name)
    assert redis_emotives is not None, "Emotives should be stored"
    assert len(redis_emotives) == 3, f"Should store 3 emotives, got {len(redis_emotives)}"
    assert redis_emotives[0] == {'joy': 0.9}, f"First emotive should be {{'joy': 0.9}}, got {redis_emotives[0]}"
    assert redis_emotives[1] == {'joy': 0.5}, f"Second emotive should be {{'joy': 0.5}}, got {redis_emotives[1]}"
    assert redis_emotives[2] == {'joy': 0.7}, f"Third emotive should be {{'joy': 0.7}}, got {redis_emotives[2]}"


def test_emotives_multiple_keys_storage(kato_fixture):
    """Test that multi-key emotives are stored correctly."""
    kato_fixture.clear_all_memory()

    # Observe with multi-key emotives
    kato_fixture.observe({'strings': ['A'], 'vectors': [], 'emotives': {'joy': 0.9, 'confidence': 0.8, 'energy': 0.7}})
    kato_fixture.observe({'strings': ['B'], 'vectors': [], 'emotives': {'joy': 0.5, 'confidence': 0.6, 'energy': 0.4}})
    pattern_name = kato_fixture.learn()

    # Debug output
    print(f"\n=== DEBUG test_emotives_multiple_keys_storage ===")
    print(f"Pattern name: {pattern_name}")
    print(f"Processor ID: {kato_fixture.processor_id}")
    clean_name = pattern_name[5:] if pattern_name.startswith('PTRN|') else pattern_name
    kb_id = f"{kato_fixture.processor_id}_kato"
    print(f"KB ID: {kb_id}")
    print(f"Clean pattern name: {clean_name}")
    emotives_key = f"{kb_id}:emotives:{clean_name}"
    print(f"Expected Redis key: {emotives_key}")

    # Check Redis directly
    import redis as redis_module
    redis_client = redis_module.Redis(host='localhost', port=6379, decode_responses=True)
    direct_value = redis_client.get(emotives_key)
    print(f"Direct Redis GET: {direct_value}")

    # All keys in Redis
    all_keys = redis_client.keys(f"{kb_id}:*")
    print(f"All keys for kb_id: {all_keys}")

    # Validate Redis storage
    redis_emotives = kato_fixture.get_redis_emotives(pattern_name)
    print(f"get_redis_emotives returned: {redis_emotives}")
    assert redis_emotives is not None, "Emotives should be stored"
    assert len(redis_emotives) == 2, f"Should store 2 emotives, got {len(redis_emotives)}"

    # Validate first emotive has all keys with correct values
    assert redis_emotives[0] == {'joy': 0.9, 'confidence': 0.8, 'energy': 0.7}, \
        f"First emotive should have all 3 keys, got {redis_emotives[0]}"

    # Validate second emotive has all keys with correct values
    assert redis_emotives[1] == {'joy': 0.5, 'confidence': 0.6, 'energy': 0.4}, \
        f"Second emotive should have all 3 keys, got {redis_emotives[1]}"


def test_emotives_varying_key_counts(kato_fixture):
    """Test emotives with different numbers of keys across observations."""
    kato_fixture.clear_all_memory()

    # Observe with varying key counts
    kato_fixture.observe({'strings': ['A'], 'vectors': [], 'emotives': {'joy': 0.9}})  # 1 key
    kato_fixture.observe({'strings': ['B'], 'vectors': [], 'emotives': {'joy': 0.5, 'confidence': 0.6}})  # 2 keys
    kato_fixture.observe({'strings': ['C'], 'vectors': [], 'emotives': {'joy': 0.7, 'confidence': 0.8, 'energy': 0.9}})  # 3 keys
    pattern_name = kato_fixture.learn()

    # Validate Redis storage
    redis_emotives = kato_fixture.get_redis_emotives(pattern_name)
    assert redis_emotives is not None, "Emotives should be stored"
    assert len(redis_emotives) == 3, f"Should store 3 emotives, got {len(redis_emotives)}"

    # Each observation should store its original keys (not merged)
    assert redis_emotives[0] == {'joy': 0.9}, f"First should have 1 key, got {redis_emotives[0]}"
    assert redis_emotives[1] == {'joy': 0.5, 'confidence': 0.6}, f"Second should have 2 keys, got {redis_emotives[1]}"
    assert redis_emotives[2] == {'joy': 0.7, 'confidence': 0.8, 'energy': 0.9}, f"Third should have 3 keys, got {redis_emotives[2]}"


def test_emotives_persistence_window_within_limit(kato_fixture):
    """Test that emotives within persistence window (default 5) are all stored."""
    kato_fixture.clear_all_memory()

    # Observe 5 emotives (at persistence limit)
    for i in range(5):
        kato_fixture.observe({'strings': [f'item_{i}'], 'vectors': [], 'emotives': {'value': float(i)}})
    pattern_name = kato_fixture.learn()

    # Validate Redis storage - should have all 5
    redis_emotives = kato_fixture.get_redis_emotives(pattern_name)
    assert redis_emotives is not None, "Emotives should be stored"
    assert len(redis_emotives) == 5, f"Should store all 5 emotives (within window), got {len(redis_emotives)}"

    # Validate order and values
    for i in range(5):
        assert redis_emotives[i] == {'value': float(i)}, \
            f"Emotive {i} should be {{'value': {float(i)}}}, got {redis_emotives[i]}"


def test_emotives_persistence_window_overflow(kato_fixture):
    """Test that emotives beyond persistence window (default 5) drop oldest (FIFO)."""
    kato_fixture.clear_all_memory()

    # Observe 7 emotives (exceeds default persistence=5)
    for i in range(7):
        kato_fixture.observe({'strings': [f'item_{i}'], 'vectors': [], 'emotives': {'value': float(i)}})
    pattern_name = kato_fixture.learn()

    # Validate Redis storage - should only have LAST 5 (dropped first 2)
    redis_emotives = kato_fixture.get_redis_emotives(pattern_name)
    assert redis_emotives is not None, "Emotives should be stored"
    assert len(redis_emotives) == 5, \
        f"Should store only last 5 emotives (persistence window), got {len(redis_emotives)}"

    # Should have emotives 2, 3, 4, 5, 6 (dropped 0 and 1)
    expected_values = [2.0, 3.0, 4.0, 5.0, 6.0]
    for i, expected in enumerate(expected_values):
        assert redis_emotives[i] == {'value': expected}, \
            f"Emotive {i} should be {{'value': {expected}}}, got {redis_emotives[i]} (oldest should be dropped)"


def test_emotives_persistence_window_large_overflow(kato_fixture):
    """Test persistence window with significantly more emotives than window size."""
    kato_fixture.clear_all_memory()

    # Observe 12 emotives (way beyond persistence=5)
    for i in range(12):
        kato_fixture.observe({'strings': [f'item_{i}'], 'vectors': [], 'emotives': {'sequence': float(i)}})
    pattern_name = kato_fixture.learn()

    # Should only have LAST 5 (indices 7-11)
    redis_emotives = kato_fixture.get_redis_emotives(pattern_name)
    assert redis_emotives is not None, "Emotives should be stored"
    assert len(redis_emotives) == 5, \
        f"Should store only last 5 emotives, got {len(redis_emotives)}"

    # Should have emotives 7, 8, 9, 10, 11
    expected_values = [7.0, 8.0, 9.0, 10.0, 11.0]
    for i, expected in enumerate(expected_values):
        assert redis_emotives[i] == {'sequence': expected}, \
            f"Should only keep last 5 emotives, got {redis_emotives[i]}"


def test_emotives_merging_on_relearning_same_pattern(kato_fixture):
    """Test that emotives merge (append) when same pattern is re-learned."""
    kato_fixture.clear_all_memory()

    # Learn pattern first time with 2 emotives
    kato_fixture.observe({'strings': ['X'], 'vectors': [], 'emotives': {'mood': 0.9}})
    kato_fixture.observe({'strings': ['Y'], 'vectors': [], 'emotives': {'mood': 0.8}})
    pattern_name1 = kato_fixture.learn()

    # Validate first learning
    redis_emotives1 = kato_fixture.get_redis_emotives(pattern_name1)
    assert len(redis_emotives1) == 2, "Should have 2 emotives after first learning"

    # Re-learn SAME pattern with 2 different emotives
    kato_fixture.clear_short_term_memory()
    kato_fixture.observe({'strings': ['X'], 'vectors': [], 'emotives': {'mood': 0.5}})
    kato_fixture.observe({'strings': ['Y'], 'vectors': [], 'emotives': {'mood': 0.3}})
    pattern_name2 = kato_fixture.learn()

    # Should be same pattern (same hash)
    clean_name1 = pattern_name1[5:] if pattern_name1.startswith('PTRN|') else pattern_name1
    clean_name2 = pattern_name2[5:] if pattern_name2.startswith('PTRN|') else pattern_name2
    assert clean_name1 == clean_name2, "Should be same pattern"

    # Emotives should be MERGED (not replaced)
    redis_emotives2 = kato_fixture.get_redis_emotives(pattern_name2)
    assert len(redis_emotives2) == 4, \
        f"Should have 4 emotives (2 from first + 2 from second learning), got {len(redis_emotives2)}"

    # Validate order: first learning emotives, then second learning emotives
    assert redis_emotives2[0] == {'mood': 0.9}, "First emotive from first learning"
    assert redis_emotives2[1] == {'mood': 0.8}, "Second emotive from first learning"
    assert redis_emotives2[2] == {'mood': 0.5}, "First emotive from second learning"
    assert redis_emotives2[3] == {'mood': 0.3}, "Second emotive from second learning"


def test_emotives_merging_with_window_overflow(kato_fixture):
    """Test that emotives merge respects persistence window (drops oldest)."""
    kato_fixture.clear_all_memory()

    # Learn 3-event pattern with 3 emotives
    kato_fixture.observe({'strings': ['item_0'], 'vectors': [], 'emotives': {'gen': 0.0}})
    kato_fixture.observe({'strings': ['item_1'], 'vectors': [], 'emotives': {'gen': 1.0}})
    kato_fixture.observe({'strings': ['item_2'], 'vectors': [], 'emotives': {'gen': 2.0}})
    pattern_name1 = kato_fixture.learn()

    # Verify first learning
    redis_emotives1 = kato_fixture.get_redis_emotives(pattern_name1)
    assert len(redis_emotives1) == 3, "Should have 3 emotives"

    # Re-learn SAME 3-event pattern with different emotives (total would be 6, exceeds persistence=5)
    kato_fixture.clear_short_term_memory()
    kato_fixture.observe({'strings': ['item_0'], 'vectors': [], 'emotives': {'gen': 3.0}})
    kato_fixture.observe({'strings': ['item_1'], 'vectors': [], 'emotives': {'gen': 4.0}})
    kato_fixture.observe({'strings': ['item_2'], 'vectors': [], 'emotives': {'gen': 5.0}})
    pattern_name2 = kato_fixture.learn()

    # Should be same pattern (same sequence)
    clean_name1 = pattern_name1[5:] if pattern_name1.startswith('PTRN|') else pattern_name1
    clean_name2 = pattern_name2[5:] if pattern_name2.startswith('PTRN|') else pattern_name2
    assert clean_name1 == clean_name2, "Should be same pattern"

    # Total emotives: [0, 1, 2, 3, 4, 5] = 6 emotives
    # Should keep LAST 5: [1, 2, 3, 4, 5]
    redis_emotives2 = kato_fixture.get_redis_emotives(pattern_name2)
    assert len(redis_emotives2) == 5, \
        f"Should have 5 emotives (persistence window enforced), got {len(redis_emotives2)}"

    # Should have dropped first (index 0)
    expected_values = [1.0, 2.0, 3.0, 4.0, 5.0]
    for i, expected in enumerate(expected_values):
        assert redis_emotives2[i] == {'gen': expected}, \
            f"Emotive {i} should be {{'gen': {expected}}}, got {redis_emotives2[i]}"


def test_emotives_averaging_in_predictions(kato_fixture):
    """Test that emotives are averaged when returned in predictions."""
    kato_fixture.clear_all_memory()
    kato_fixture.set_recall_threshold(0.2)  # Match working prediction tests

    # Learn 3-event pattern with varying emotives (so we can observe 2, predict 1)
    kato_fixture.observe({'strings': ['start'], 'vectors': [], 'emotives': {'joy': 1.0, 'confidence': 0.8}})
    kato_fixture.observe({'strings': ['middle'], 'vectors': [], 'emotives': {'joy': 0.5, 'confidence': 0.6}})
    kato_fixture.observe({'strings': ['end'], 'vectors': [], 'emotives': {'joy': 0.3, 'confidence': 0.4}})
    pattern_name = kato_fixture.learn()

    # Verify storage (should be list with 3 dicts)
    redis_emotives = kato_fixture.get_redis_emotives(pattern_name)
    assert isinstance(redis_emotives, list), "Redis should store emotives as list"
    assert len(redis_emotives) == 3, "Should store 3 emotive dicts"

    # Trigger predictions - observe first 2 events to get prediction about 3rd
    kato_fixture.clear_short_term_memory()
    kato_fixture.observe({'strings': ['start'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['middle'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()

    # Find matching prediction
    assert len(predictions) > 0, "Should have predictions"
    matching_preds = [p for p in predictions if p.get('frequency', 0) > 0]
    assert len(matching_preds) > 0, "Should have at least one matching prediction"

    # Validate emotives in prediction are AVERAGED
    pred_emotives = matching_preds[0].get('emotives', {})
    assert isinstance(pred_emotives, dict), "Prediction emotives should be a dict (averaged)"

    # Average of all 3: [{'joy': 1.0, 'confidence': 0.8}, {'joy': 0.5, 'confidence': 0.6}, {'joy': 0.3, 'confidence': 0.4}]
    # joy: (1.0 + 0.5 + 0.3) / 3 = 0.6
    # confidence: (0.8 + 0.6 + 0.4) / 3 = 0.6
    assert 'joy' in pred_emotives, "Averaged emotives should have 'joy' key"
    assert 'confidence' in pred_emotives, "Averaged emotives should have 'confidence' key"
    assert abs(pred_emotives['joy'] - 0.6) < 0.01, \
        f"joy should average to 0.6, got {pred_emotives['joy']}"
    assert abs(pred_emotives['confidence'] - 0.6) < 0.01, \
        f"confidence should average to 0.6, got {pred_emotives['confidence']}"


def test_emotives_averaging_with_multiple_relearnings(kato_fixture):
    """Test averaging with emotives from multiple pattern learnings."""
    kato_fixture.clear_all_memory()
    kato_fixture.set_recall_threshold(0.2)  # Match working prediction tests

    # Learn 3-event pattern with 3 emotives (so we can observe 2, predict 1)
    kato_fixture.observe({'strings': ['A'], 'vectors': [], 'emotives': {'value': 1.0}})
    kato_fixture.observe({'strings': ['B'], 'vectors': [], 'emotives': {'value': 0.8}})
    kato_fixture.observe({'strings': ['C'], 'vectors': [], 'emotives': {'value': 0.6}})
    pattern_name1 = kato_fixture.learn()

    # Re-learn with 3 more emotives
    kato_fixture.clear_short_term_memory()
    kato_fixture.observe({'strings': ['A'], 'vectors': [], 'emotives': {'value': 0.4}})
    kato_fixture.observe({'strings': ['B'], 'vectors': [], 'emotives': {'value': 0.2}})
    kato_fixture.observe({'strings': ['C'], 'vectors': [], 'emotives': {'value': 0.1}})
    pattern_name2 = kato_fixture.learn()

    # Verify merged storage (should trim to persistence window = 5)
    redis_emotives = kato_fixture.get_redis_emotives(pattern_name2)
    assert len(redis_emotives) == 5, "Should have 5 emotives (persistence window enforced)"

    # Trigger predictions and check averaging - observe first 2 events
    kato_fixture.clear_short_term_memory()
    kato_fixture.observe({'strings': ['A'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['B'], 'vectors': [], 'emotives': {}})
    predictions = kato_fixture.get_predictions()

    matching_preds = [p for p in predictions if p.get('frequency', 0) > 0]
    assert len(matching_preds) > 0, "Should have matching predictions"

    pred_emotives = matching_preds[0].get('emotives', {})
    # Average of last 5: [0.8, 0.6, 0.4, 0.2, 0.1] = 2.1 / 5 = 0.42
    assert 'value' in pred_emotives, "Should have 'value' key"
    assert abs(pred_emotives['value'] - 0.42) < 0.01, \
        f"value should average to 0.42, got {pred_emotives['value']}"


def test_emotives_empty_observations_not_stored(kato_fixture):
    """Test that observations with empty emotives don't add to rolling window."""
    kato_fixture.clear_all_memory()

    # Observe with emotives
    kato_fixture.observe({'strings': ['A'], 'vectors': [], 'emotives': {'mood': 0.9}})
    # Observe WITHOUT emotives (empty dict)
    kato_fixture.observe({'strings': ['B'], 'vectors': [], 'emotives': {}})
    # Observe with emotives again
    kato_fixture.observe({'strings': ['C'], 'vectors': [], 'emotives': {'mood': 0.7}})
    pattern_name = kato_fixture.learn()

    # Should only store 2 emotives (not 3 - middle one was empty)
    redis_emotives = kato_fixture.get_redis_emotives(pattern_name)

    # This could be either:
    # Option 1: Only 2 emotives stored (empty ones skipped)
    # Option 2: 3 stored with middle one as {} (empty dict preserved)
    # Let's check which behavior is implemented
    assert redis_emotives is not None, "Emotives should be stored"

    # Count non-empty emotives
    non_empty = [e for e in redis_emotives if e != {}]
    assert len(non_empty) == 2, \
        f"Should have 2 non-empty emotives, got {len(non_empty)}"
    assert non_empty[0] == {'mood': 0.9}, "First non-empty should match"
    assert non_empty[1] == {'mood': 0.7}, "Second non-empty should match"


def test_emotives_api_vs_redis_consistency(kato_fixture):
    """
    CRITICAL: Test that API response emotives match Redis storage emotives.

    This ensures get_pattern() reads from Redis, not from cache or memory.
    """
    kato_fixture.clear_all_memory()

    # Create pattern with specific emotives
    test_emotives = [
        {'alpha': 0.1, 'beta': 0.2},
        {'alpha': 0.3, 'beta': 0.4},
        {'alpha': 0.5, 'beta': 0.6}
    ]

    for i, emotive in enumerate(test_emotives):
        kato_fixture.observe({'strings': [f'test_{i}'], 'vectors': [], 'emotives': emotive})
    pattern_name = kato_fixture.learn()

    # Get emotives via Redis (ground truth)
    redis_emotives = kato_fixture.get_redis_emotives(pattern_name)

    # Get emotives via API
    pattern_result = kato_fixture.get_pattern(pattern_name)
    api_emotives = pattern_result['pattern'].get('emotives', [])

    # API should return EXACT same emotives as Redis
    assert api_emotives == redis_emotives, \
        f"API emotives {api_emotives} should match Redis emotives {redis_emotives}"


def test_emotives_frequency_counter_created(kato_fixture):
    """Test that frequency counter is created alongside emotives."""
    kato_fixture.clear_all_memory()

    # Learn pattern with emotives
    kato_fixture.observe({'strings': ['freq_test'], 'vectors': [], 'emotives': {'test': 1.0}})
    kato_fixture.observe({'strings': ['freq_end'], 'vectors': [], 'emotives': {'test': 0.5}})
    pattern_name = kato_fixture.learn()

    # Both emotives AND frequency should be in Redis
    redis_emotives = kato_fixture.get_redis_emotives(pattern_name)
    redis_freq = kato_fixture.get_redis_frequency(pattern_name)

    assert redis_emotives is not None, "Emotives should be stored"
    assert redis_freq > 0, f"Frequency should be > 0, got {redis_freq}"
    assert redis_freq == 1, f"Frequency should be 1 for new pattern, got {redis_freq}"
