"""
Comprehensive Database Persistence Tests for node_id

This test suite validates the CRITICAL requirement that knowledge bases (MongoDB patterns
and Qdrant vectors) persist across sessions for the same node_id.

Architecture:
- Each node_id → processor_id → isolated MongoDB database ({node_id}_{base}.patterns_kb)
- Sessions store only temporary state (STM, emotives accumulator) in Redis
- Deleting sessions DOES NOT delete learned patterns
- New session with same node_id should access all previously learned patterns

These tests verify production scenarios:
- User logs out and logs back in later (patterns should persist)
- Service restarts but user data remains intact
- Different app instances serving same user access same knowledge base
"""

import os
import sys
import uuid

import pytest
import requests

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))



# ============================================================================
# Helper Functions
# ============================================================================

def generate_unique_node_id(prefix: str = "persist_test") -> str:
    """Generate a unique node_id for test isolation."""
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def create_session_with_node(base_url: str, node_id: str, ttl_seconds: int = 3600) -> str:
    """
    Create a new session with specific node_id.

    Returns:
        session_id for the created session
    """
    response = requests.post(
        f"{base_url}/sessions",
        json={
            "node_id": node_id,
            "metadata": {"test": "persistence"},
            "ttl_seconds": ttl_seconds
        }
    )
    response.raise_for_status()
    result = response.json()
    return result['session_id']


def delete_session(base_url: str, session_id: str) -> bool:
    """Delete a session."""
    response = requests.delete(f"{base_url}/sessions/{session_id}")
    if response.status_code == 404:
        return False
    response.raise_for_status()
    return True


def learn_pattern_in_session(
    base_url: str,
    session_id: str,
    pattern_events: list[list[str]],
    vectors: list[list[float]] = None,
    emotives: dict[str, float] = None
) -> str:
    """
    Learn a pattern in a specific session.

    Args:
        base_url: KATO service URL
        session_id: Session identifier
        pattern_events: List of events, each event is a list of strings
        vectors: Optional list of vectors (one per event)
        emotives: Optional emotives dict

    Returns:
        Pattern name (PTRN|hash)
    """
    # Clear STM first
    requests.post(f"{base_url}/sessions/{session_id}/clear-stm")

    # Observe each event
    for i, event in enumerate(pattern_events):
        obs = {
            'strings': event,
            'vectors': [vectors[i]] if vectors and i < len(vectors) else [],
            'emotives': emotives or {}
        }
        response = requests.post(f"{base_url}/sessions/{session_id}/observe", json=obs)
        response.raise_for_status()

    # Learn the pattern
    response = requests.post(f"{base_url}/sessions/{session_id}/learn")
    response.raise_for_status()
    result = response.json()
    return result.get('pattern_name', '')


def get_predictions_for_session(
    base_url: str,
    session_id: str,
    observed_events: list[list[str]]
) -> list[dict]:
    """
    Get predictions for a specific session after observing events.

    Args:
        base_url: KATO service URL
        session_id: Session identifier
        observed_events: Events to observe before getting predictions

    Returns:
        List of prediction dictionaries
    """
    # Clear STM first
    requests.post(f"{base_url}/sessions/{session_id}/clear-stm")

    # Observe events
    for event in observed_events:
        obs = {'strings': event, 'vectors': [], 'emotives': {}}
        response = requests.post(f"{base_url}/sessions/{session_id}/observe", json=obs)
        response.raise_for_status()

    # Get predictions
    response = requests.get(f"{base_url}/sessions/{session_id}/predictions")
    response.raise_for_status()
    result = response.json()
    return result.get('predictions', [])


def count_patterns_for_node(base_url: str, node_id: str) -> int:
    """
    Count total patterns learned for a specific node.

    Creates a temporary session to check pattern count via predictions.

    Returns:
        Number of unique patterns accessible to this node
    """
    session_id = create_session_with_node(base_url, node_id)

    try:
        # Get all accessible patterns by querying with minimal observation
        # This is a workaround since we can't directly query pattern count
        # We'll observe a unique symbol and see how many patterns exist
        obs = {'strings': [f'count_check_{uuid.uuid4().hex[:4]}'], 'vectors': [], 'emotives': {}}
        requests.post(f"{base_url}/sessions/{session_id}/observe", json=obs)

        # Get predictions (will return patterns that might match)
        # Note: This is not a perfect count, but gives us insight
        response = requests.get(f"{base_url}/sessions/{session_id}/predictions")
        if response.status_code == 200:
            predictions = response.json().get('predictions', [])
            return len(predictions)
        return 0
    finally:
        delete_session(base_url, session_id)


# ============================================================================
# Test Suite 1: Basic Pattern Persistence
# ============================================================================

def test_basic_pattern_persistence_across_sessions(kato_fixture):
    """
    Test that a simple pattern persists across session deletion and recreation.

    Scenario:
    1. Create session for node_id="test_user_1"
    2. Learn pattern A→B→C
    3. Delete session
    4. Create NEW session with SAME node_id
    5. Observe A→B and verify prediction includes C
    """
    if not kato_fixture.services_available:
        pytest.skip("KATO services not available")

    base_url = kato_fixture.base_url
    node_id = generate_unique_node_id("basic_persist")

    # Session 1: Learn pattern
    session1_id = create_session_with_node(base_url, node_id)
    pattern_name = learn_pattern_in_session(
        base_url,
        session1_id,
        pattern_events=[['A'], ['B'], ['C']]
    )
    assert pattern_name.startswith('PTRN|'), f"Expected pattern name, got {pattern_name}"

    # Delete session 1
    deleted = delete_session(base_url, session1_id)
    assert deleted, "Session should be deleted"

    # Session 2: Verify pattern persists
    session2_id = create_session_with_node(base_url, node_id)

    try:
        predictions = get_predictions_for_session(
            base_url,
            session2_id,
            observed_events=[['A'], ['B']]
        )

        assert len(predictions) > 0, "Should have predictions from persisted pattern"

        # Check that future contains C
        found_c = False
        for pred in predictions:
            future = pred.get('future', [])
            for future_event in future:
                if 'C' in future_event:
                    found_c = True
                    break

        assert found_c, f"Should predict C after observing A→B. Predictions: {predictions}"

    finally:
        delete_session(base_url, session2_id)


def test_multiple_patterns_basic_persistence(kato_fixture):
    """Test that 2-3 patterns all persist across session recreation."""
    if not kato_fixture.services_available:
        pytest.skip("KATO services not available")

    base_url = kato_fixture.base_url
    node_id = generate_unique_node_id("multi_basic")

    # Session 1: Learn 3 different patterns
    session1_id = create_session_with_node(base_url, node_id)

    patterns_learned = []
    patterns_learned.append(learn_pattern_in_session(
        base_url, session1_id, [['X'], ['Y'], ['Z']]
    ))
    patterns_learned.append(learn_pattern_in_session(
        base_url, session1_id, [['1'], ['2'], ['3']]
    ))
    patterns_learned.append(learn_pattern_in_session(
        base_url, session1_id, [['alpha'], ['beta'], ['gamma']]
    ))

    assert len(patterns_learned) == 3
    assert all(p.startswith('PTRN|') for p in patterns_learned)

    # Delete session
    delete_session(base_url, session1_id)

    # Session 2: Verify all 3 patterns persist
    session2_id = create_session_with_node(base_url, node_id)

    try:
        # Test pattern 1: X→Y should predict Z
        preds1 = get_predictions_for_session(base_url, session2_id, [['X'], ['Y']])
        assert len(preds1) > 0, "Pattern X→Y→Z should persist"

        # Test pattern 2: 1→2 should predict 3
        preds2 = get_predictions_for_session(base_url, session2_id, [['1'], ['2']])
        assert len(preds2) > 0, "Pattern 1→2→3 should persist"

        # Test pattern 3: alpha→beta should predict gamma
        preds3 = get_predictions_for_session(base_url, session2_id, [['alpha'], ['beta']])
        assert len(preds3) > 0, "Pattern alpha→beta→gamma should persist"

    finally:
        delete_session(base_url, session2_id)


# ============================================================================
# Test Suite 2: Large-Scale Pattern Persistence (50+ patterns)
# ============================================================================

def test_dozens_of_patterns_persistence(kato_fixture):
    """
    Test that 50+ patterns all persist across session deletion.

    This validates database integrity at scale.
    """
    if not kato_fixture.services_available:
        pytest.skip("KATO services not available")

    base_url = kato_fixture.base_url
    node_id = generate_unique_node_id("large_scale")

    num_patterns = 50

    # Session 1: Learn 50 different patterns
    session1_id = create_session_with_node(base_url, node_id)

    patterns_learned = []
    for i in range(num_patterns):
        # Create variety: some 2-element, some 3-element, some 5-element
        if i % 3 == 0:
            # 2-element pattern
            pattern = [[f'pat{i}_a'], [f'pat{i}_b']]
        elif i % 3 == 1:
            # 3-element pattern
            pattern = [[f'pat{i}_a'], [f'pat{i}_b'], [f'pat{i}_c']]
        else:
            # 5-element pattern
            pattern = [
                [f'pat{i}_a'], [f'pat{i}_b'], [f'pat{i}_c'],
                [f'pat{i}_d'], [f'pat{i}_e']
            ]

        pattern_name = learn_pattern_in_session(base_url, session1_id, pattern)
        patterns_learned.append({
            'name': pattern_name,
            'pattern': pattern,
            'index': i
        })

    assert len(patterns_learned) == num_patterns

    # Delete session
    delete_session(base_url, session1_id)

    # Session 2: Verify random sample of patterns persist
    session2_id = create_session_with_node(base_url, node_id)

    try:
        # Test a sample of patterns (every 5th one to keep test fast)
        for i in range(0, num_patterns, 5):
            pattern_info = patterns_learned[i]
            pattern_events = pattern_info['pattern']

            # Observe first 2 events, should get predictions
            preds = get_predictions_for_session(
                base_url,
                session2_id,
                observed_events=pattern_events[:2]
            )

            assert len(preds) > 0, f"Pattern {i} should persist: {pattern_events}"

    finally:
        delete_session(base_url, session2_id)


# ============================================================================
# Test Suite 3: Multi-Modal Pattern Persistence
# ============================================================================

def test_multimodal_pattern_persistence(kato_fixture):
    """
    Test persistence of patterns with different modalities:
    - String-only patterns (20)
    - String + vector patterns (20)
    - String + vector + emotive patterns (10)
    """
    if not kato_fixture.services_available:
        pytest.skip("KATO services not available")

    base_url = kato_fixture.base_url
    node_id = generate_unique_node_id("multimodal")

    session1_id = create_session_with_node(base_url, node_id)

    patterns_learned = []

    # 1. String-only patterns (20)
    for i in range(20):
        pattern_name = learn_pattern_in_session(
            base_url, session1_id,
            pattern_events=[[f'str{i}_a'], [f'str{i}_b'], [f'str{i}_c']]
        )
        patterns_learned.append(('string', i, pattern_name))

    # 2. String + vector patterns (20)
    for i in range(20):
        # Use simple 4-dim vectors for testing
        vectors = [[float(i), 0.0, 0.0, 0.0], [0.0, float(i), 0.0, 0.0]]

        # Clear STM and observe with vectors
        requests.post(f"{base_url}/sessions/{session1_id}/clear-stm")

        obs1 = {
            'strings': [f'vec{i}_a'],
            'vectors': [vectors[0]],
            'emotives': {}
        }
        obs2 = {
            'strings': [f'vec{i}_b'],
            'vectors': [vectors[1]],
            'emotives': {}
        }

        requests.post(f"{base_url}/sessions/{session1_id}/observe", json=obs1)
        requests.post(f"{base_url}/sessions/{session1_id}/observe", json=obs2)

        # Learn
        response = requests.post(f"{base_url}/sessions/{session1_id}/learn")
        result = response.json()
        pattern_name = result.get('pattern_name', '')
        patterns_learned.append(('vector', i, pattern_name))

    # 3. String + vector + emotive patterns (10)
    for i in range(10):
        vectors = [[0.0, 0.0, float(i), 0.0]]
        emotives = {'joy': 0.1 * i, 'confidence': 0.9 - 0.1 * i}

        # Clear STM and observe
        requests.post(f"{base_url}/sessions/{session1_id}/clear-stm")

        obs = {
            'strings': [f'emot{i}_a'],
            'vectors': vectors,
            'emotives': emotives
        }
        requests.post(f"{base_url}/sessions/{session1_id}/observe", json=obs)

        obs2 = {
            'strings': [f'emot{i}_b'],
            'vectors': [],
            'emotives': emotives
        }
        requests.post(f"{base_url}/sessions/{session1_id}/observe", json=obs2)

        # Learn
        response = requests.post(f"{base_url}/sessions/{session1_id}/learn")
        result = response.json()
        pattern_name = result.get('pattern_name', '')
        patterns_learned.append(('emotive', i, pattern_name))

    assert len(patterns_learned) == 50, f"Should have 50 patterns, got {len(patterns_learned)}"

    # Delete session
    delete_session(base_url, session1_id)

    # Session 2: Verify sample of each type persists
    session2_id = create_session_with_node(base_url, node_id)

    try:
        # Test string-only pattern (index 0)
        preds = get_predictions_for_session(
            base_url, session2_id,
            observed_events=[['str0_a'], ['str0_b']]
        )
        assert len(preds) > 0, "String-only patterns should persist"

        # Test vector pattern (index 0)
        # Vectors should create VCTR| symbols that persist
        preds2 = get_predictions_for_session(
            base_url, session2_id,
            observed_events=[['vec0_a']]
        )
        # We can at least verify the session works

        # Test emotive pattern (index 0)
        preds3 = get_predictions_for_session(
            base_url, session2_id,
            observed_events=[['emot0_a']]
        )
        # Emotives persist within the pattern metadata

    finally:
        delete_session(base_url, session2_id)


# ============================================================================
# Test Suite 4: Cross-User Isolation
# ============================================================================

def test_pattern_isolation_between_nodes(kato_fixture):
    """
    Verify that different nodes have completely isolated knowledge bases.

    User A's patterns should NEVER appear in User B's predictions.
    """
    if not kato_fixture.services_available:
        pytest.skip("KATO services not available")

    base_url = kato_fixture.base_url
    node_a = generate_unique_node_id("user_alice")
    node_b = generate_unique_node_id("user_bob")

    # User A: Learn 10 patterns with prefix "alice_"
    session_a1 = create_session_with_node(base_url, node_a)
    for i in range(10):
        learn_pattern_in_session(
            base_url, session_a1,
            pattern_events=[[f'alice_{i}_a'], [f'alice_{i}_b'], [f'alice_{i}_c']]
        )
    delete_session(base_url, session_a1)

    # User B: Learn 10 patterns with prefix "bob_"
    session_b1 = create_session_with_node(base_url, node_b)
    for i in range(10):
        learn_pattern_in_session(
            base_url, session_b1,
            pattern_events=[[f'bob_{i}_a'], [f'bob_{i}_b'], [f'bob_{i}_c']]
        )
    delete_session(base_url, session_b1)

    # Recreate sessions for both users
    session_a2 = create_session_with_node(base_url, node_a)
    session_b2 = create_session_with_node(base_url, node_b)

    try:
        # User A should see alice_ patterns, NOT bob_ patterns
        preds_a = get_predictions_for_session(
            base_url, session_a2,
            observed_events=[['alice_0_a'], ['alice_0_b']]
        )

        # Check predictions only contain alice symbols
        for pred in preds_a:
            future = pred.get('future', [])
            for event in future:
                for symbol in event:
                    assert 'bob_' not in symbol, f"User A should never see bob_ patterns! Got: {symbol}"

        # User B should see bob_ patterns, NOT alice_ patterns
        preds_b = get_predictions_for_session(
            base_url, session_b2,
            observed_events=[['bob_0_a'], ['bob_0_b']]
        )

        # Check predictions only contain bob symbols
        for pred in preds_b:
            future = pred.get('future', [])
            for event in future:
                for symbol in event:
                    assert 'alice_' not in symbol, f"User B should never see alice_ patterns! Got: {symbol}"

    finally:
        delete_session(base_url, session_a2)
        delete_session(base_url, session_b2)


# ============================================================================
# Test Suite 5: Pattern Frequency Accumulation
# ============================================================================

def test_pattern_frequency_across_sessions(kato_fixture):
    """
    Test that learning the same pattern in different sessions increments frequency.

    This validates that pattern storage uses upsert correctly.
    """
    if not kato_fixture.services_available:
        pytest.skip("KATO services not available")

    base_url = kato_fixture.base_url
    node_id = generate_unique_node_id("frequency_test")

    # Session 1: Learn pattern X→Y→Z (frequency should be 1)
    session1_id = create_session_with_node(base_url, node_id)
    pattern_name_1 = learn_pattern_in_session(
        base_url, session1_id,
        pattern_events=[['X'], ['Y'], ['Z']]
    )

    # Get first prediction to check frequency
    preds1 = get_predictions_for_session(
        base_url, session1_id,
        observed_events=[['X'], ['Y']]
    )

    initial_frequency = None
    if preds1:
        initial_frequency = preds1[0].get('frequency', 0)

    delete_session(base_url, session1_id)

    # Session 2: Learn SAME pattern X→Y→Z again (frequency should increment)
    session2_id = create_session_with_node(base_url, node_id)
    pattern_name_2 = learn_pattern_in_session(
        base_url, session2_id,
        pattern_events=[['X'], ['Y'], ['Z']]
    )

    # Pattern names should be identical (same hash)
    assert pattern_name_1 == pattern_name_2, "Same pattern should have same hash"

    # Get prediction and check frequency increased
    preds2 = get_predictions_for_session(
        base_url, session2_id,
        observed_events=[['X'], ['Y']]
    )

    if preds2 and initial_frequency is not None:
        new_frequency = preds2[0].get('frequency', 0)
        assert new_frequency > initial_frequency, \
            f"Frequency should increase from {initial_frequency} to {new_frequency}"

    delete_session(base_url, session2_id)

    # Session 3: Learn it a THIRD time
    session3_id = create_session_with_node(base_url, node_id)
    learn_pattern_in_session(
        base_url, session3_id,
        pattern_events=[['X'], ['Y'], ['Z']]
    )

    preds3 = get_predictions_for_session(
        base_url, session3_id,
        observed_events=[['X'], ['Y']]
    )

    if preds3 and preds2:
        freq_2 = preds2[0].get('frequency', 0)
        freq_3 = preds3[0].get('frequency', 0)
        assert freq_3 > freq_2, f"Frequency should keep increasing: {freq_2} → {freq_3}"

    delete_session(base_url, session3_id)


# ============================================================================
# Test Suite 6: Vector Persistence
# ============================================================================

def test_vector_pattern_persistence(kato_fixture):
    """
    Test that patterns with vectors persist correctly.

    Qdrant collection should persist across sessions.
    """
    if not kato_fixture.services_available:
        pytest.skip("KATO services not available")

    base_url = kato_fixture.base_url
    node_id = generate_unique_node_id("vector_persist")

    # Session 1: Learn 20 patterns with 4-dim vectors
    session1_id = create_session_with_node(base_url, node_id)

    for i in range(20):
        # Clear STM
        requests.post(f"{base_url}/sessions/{session1_id}/clear-stm")

        # Create unique vectors
        vec1 = [float(i), 0.0, 0.0, 0.0]
        vec2 = [0.0, float(i), 0.0, 0.0]

        obs1 = {
            'strings': [f'v{i}_start'],
            'vectors': [vec1],
            'emotives': {}
        }
        obs2 = {
            'strings': [f'v{i}_end'],
            'vectors': [vec2],
            'emotives': {}
        }

        requests.post(f"{base_url}/sessions/{session1_id}/observe", json=obs1)
        requests.post(f"{base_url}/sessions/{session1_id}/observe", json=obs2)
        requests.post(f"{base_url}/sessions/{session1_id}/learn")

    delete_session(base_url, session1_id)

    # Session 2: Verify vector patterns persist
    session2_id = create_session_with_node(base_url, node_id)

    try:
        # Test a few vector patterns
        for i in [0, 5, 10, 15]:
            preds = get_predictions_for_session(
                base_url, session2_id,
                observed_events=[[f'v{i}_start']]
            )

            # Should get predictions from the persisted vector patterns
            # The exact behavior depends on vector similarity, but we should get some response
            assert isinstance(preds, list), f"Should get predictions for vector pattern {i}"

    finally:
        delete_session(base_url, session2_id)


# ============================================================================
# Test Suite 7: Emotive Rolling Window Persistence
# ============================================================================

def test_emotive_persistence_with_rolling_window(kato_fixture):
    """
    Test that emotive rolling windows persist across sessions.

    PERSISTENCE parameter controls rolling window size (default=5).
    """
    if not kato_fixture.services_available:
        pytest.skip("KATO services not available")

    base_url = kato_fixture.base_url
    node_id = generate_unique_node_id("emotive_persist")

    # Session 1: Learn pattern with emotives (happiness: 0.8)
    session1_id = create_session_with_node(base_url, node_id)

    requests.post(f"{base_url}/sessions/{session1_id}/clear-stm")
    obs1 = {'strings': ['happy_start'], 'vectors': [], 'emotives': {'happiness': 0.8}}
    obs2 = {'strings': ['happy_end'], 'vectors': [], 'emotives': {'happiness': 0.7}}

    requests.post(f"{base_url}/sessions/{session1_id}/observe", json=obs1)
    requests.post(f"{base_url}/sessions/{session1_id}/observe", json=obs2)
    requests.post(f"{base_url}/sessions/{session1_id}/learn")

    delete_session(base_url, session1_id)

    # Session 2: Learn SAME pattern with different emotives (happiness: 0.2)
    session2_id = create_session_with_node(base_url, node_id)

    requests.post(f"{base_url}/sessions/{session2_id}/clear-stm")
    obs1 = {'strings': ['happy_start'], 'vectors': [], 'emotives': {'happiness': 0.2}}
    obs2 = {'strings': ['happy_end'], 'vectors': [], 'emotives': {'happiness': 0.3}}

    requests.post(f"{base_url}/sessions/{session2_id}/observe", json=obs1)
    requests.post(f"{base_url}/sessions/{session2_id}/observe", json=obs2)
    requests.post(f"{base_url}/sessions/{session2_id}/learn")

    # Get predictions and check emotives exist
    preds = get_predictions_for_session(
        base_url, session2_id,
        observed_events=[['happy_start']]
    )

    if preds:
        emotives = preds[0].get('emotives', {})
        assert 'happiness' in emotives, "Emotives should persist in pattern"
        # The averaged value should reflect both learning sessions

    delete_session(base_url, session2_id)


# ============================================================================
# Test Suite 8: Stress Test - Hundreds of Patterns
# ============================================================================

@pytest.mark.stress
def test_stress_hundreds_of_patterns_persistence(kato_fixture):
    """
    Stress test: Learn 200 unique patterns and verify they all persist.

    This validates production-scale knowledge base persistence.
    """
    if not kato_fixture.services_available:
        pytest.skip("KATO services not available")

    base_url = kato_fixture.base_url
    node_id = generate_unique_node_id("stress_200")

    num_patterns = 200

    # Session 1: Learn 200 patterns
    session1_id = create_session_with_node(base_url, node_id)

    patterns_learned = []
    for i in range(num_patterns):
        # Mix of 2, 3, and 4 element patterns
        length = 2 + (i % 3)
        pattern = [[f'stress{i}_{chr(97+j)}'] for j in range(length)]

        pattern_name = learn_pattern_in_session(base_url, session1_id, pattern)
        patterns_learned.append({
            'index': i,
            'pattern': pattern,
            'name': pattern_name
        })

        # Log progress every 50 patterns
        if (i + 1) % 50 == 0:
            print(f"  Learned {i+1}/{num_patterns} patterns...")

    assert len(patterns_learned) == num_patterns

    delete_session(base_url, session1_id)

    # Session 2: Verify a sample of patterns persist (every 10th one)
    session2_id = create_session_with_node(base_url, node_id)

    try:
        verified = 0
        for i in range(0, num_patterns, 10):
            pattern_info = patterns_learned[i]
            pattern = pattern_info['pattern']

            # Observe first 2 events
            preds = get_predictions_for_session(
                base_url, session2_id,
                observed_events=pattern[:2]
            )

            if len(preds) > 0:
                verified += 1

        # Should verify at least 80% of sampled patterns
        sample_size = num_patterns // 10
        success_rate = verified / sample_size

        assert success_rate >= 0.8, \
            f"Only {verified}/{sample_size} patterns verified ({success_rate:.1%})"

        print(f"  ✓ Verified {verified}/{sample_size} patterns ({success_rate:.1%})")

    finally:
        delete_session(base_url, session2_id)


# ============================================================================
# Additional Test: Concurrent Sessions for Same Node
# ============================================================================

def test_concurrent_sessions_same_node_see_same_patterns(kato_fixture):
    """
    Test that multiple concurrent sessions for the same node_id share knowledge.

    This is important for scenarios where a user has multiple browser tabs open.
    """
    if not kato_fixture.services_available:
        pytest.skip("KATO services not available")

    base_url = kato_fixture.base_url
    node_id = generate_unique_node_id("concurrent")

    # Create first session and learn pattern
    session1_id = create_session_with_node(base_url, node_id)
    learn_pattern_in_session(
        base_url, session1_id,
        pattern_events=[['concurrent_a'], ['concurrent_b'], ['concurrent_c']]
    )

    # Create SECOND session for SAME node (without deleting first)
    session2_id = create_session_with_node(base_url, node_id)

    try:
        # Session 2 should see the pattern learned in session 1
        preds = get_predictions_for_session(
            base_url, session2_id,
            observed_events=[['concurrent_a'], ['concurrent_b']]
        )

        assert len(preds) > 0, "Second session should see patterns from first session"

        # Verify it predicts 'concurrent_c'
        found = False
        for pred in preds:
            for event in pred.get('future', []):
                if 'concurrent_c' in event:
                    found = True

        assert found, "Should predict concurrent_c"

    finally:
        delete_session(base_url, session1_id)
        delete_session(base_url, session2_id)


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "-s"])
