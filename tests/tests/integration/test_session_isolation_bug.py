"""
Test Suite for Session Isolation Bug Investigation

This test suite is designed to reproduce and diagnose the bug where
STM from one session appears when calling get_stm from another session.

The bug manifests when:
- Multiple sessions are active simultaneously
- Sessions may share the same node_id (for shared LTM)
- STM data "leaks" between sessions despite different session_ids
"""

import asyncio
import uuid

import pytest

from kato.exceptions import SessionNotFoundError


class TestSessionSTMIsolation:
    """Test that STM is strictly isolated per session_id"""

    @pytest.mark.asyncio
    async def test_stm_isolation_different_node_ids(self, kato_client):
        """
        Test STM isolation with different node_ids.

        This is the baseline case - sessions with different node_ids
        should have completely isolated STM and LTM.
        """
        # Create two sessions with different node_ids
        node_id_1 = f"test_node_{uuid.uuid4().hex[:8]}"
        node_id_2 = f"test_node_{uuid.uuid4().hex[:8]}"

        session1 = await kato_client.create_session(node_id=node_id_1)
        session2 = await kato_client.create_session(node_id=node_id_2)

        session1_id = session1['session_id']
        session2_id = session2['session_id']

        # Session 1: Build STM with A, B, C
        await kato_client.observe_in_session(session1_id, {"strings": ["A"]})
        await kato_client.observe_in_session(session1_id, {"strings": ["B"]})
        await kato_client.observe_in_session(session1_id, {"strings": ["C"]})

        # Session 2: Build STM with X, Y, Z
        await kato_client.observe_in_session(session2_id, {"strings": ["X"]})
        await kato_client.observe_in_session(session2_id, {"strings": ["Y"]})
        await kato_client.observe_in_session(session2_id, {"strings": ["Z"]})

        # Get STM from both sessions
        stm1 = await kato_client.get_session_stm(session1_id)
        stm2 = await kato_client.get_session_stm(session2_id)

        # Verify Session 1's STM
        assert stm1['stm'] == [["A"], ["B"], ["C"]], \
            f"Session 1 STM corrupted. Expected [['A'], ['B'], ['C']], got {stm1['stm']}"

        # Verify Session 2's STM
        assert stm2['stm'] == [["X"], ["Y"], ["Z"]], \
            f"Session 2 STM corrupted. Expected [['X'], ['Y'], ['Z']], got {stm2['stm']}"

        # Verify no cross-contamination
        stm1_flat = str(stm1['stm'])
        stm2_flat = str(stm2['stm'])

        assert "X" not in stm1_flat and "Y" not in stm1_flat and "Z" not in stm1_flat, \
            f"Session 1 should not contain Session 2's data. STM1: {stm1['stm']}"

        assert "A" not in stm2_flat and "B" not in stm2_flat and "C" not in stm2_flat, \
            f"Session 2 should not contain Session 1's data. STM2: {stm2['stm']}"

        # Cleanup
        await kato_client.delete_session(session1_id)
        await kato_client.delete_session(session2_id)

    @pytest.mark.asyncio
    async def test_stm_isolation_same_node_id(self, kato_client):
        """
        Test STM isolation with SAME node_id.

        This is the critical case that reproduces the bug:
        - Two sessions share the same node_id (for shared LTM)
        - But they should have ISOLATED STM
        - Bug: STM from session1 appears in session2's get_stm
        """
        # Create two sessions with THE SAME node_id
        shared_node_id = f"test_node_{uuid.uuid4().hex[:8]}"

        session1 = await kato_client.create_session(node_id=shared_node_id)
        session2 = await kato_client.create_session(node_id=shared_node_id)

        session1_id = session1['session_id']
        session2_id = session2['session_id']

        print(f"\nDEBUG: Created sessions:")
        print(f"  Session 1: {session1_id} (node_id: {shared_node_id})")
        print(f"  Session 2: {session2_id} (node_id: {shared_node_id})")

        # Session 1: Build STM with A, B, C
        await kato_client.observe_in_session(session1_id, {"strings": ["A"]})
        await kato_client.observe_in_session(session1_id, {"strings": ["B"]})
        await kato_client.observe_in_session(session1_id, {"strings": ["C"]})

        # Get Session 1's STM to verify it's correct
        stm1_after_observe = await kato_client.get_session_stm(session1_id)
        print(f"DEBUG: Session 1 STM after observe: {stm1_after_observe['stm']}")

        # Session 2: Build STM with X, Y, Z
        await kato_client.observe_in_session(session2_id, {"strings": ["X"]})
        await kato_client.observe_in_session(session2_id, {"strings": ["Y"]})
        await kato_client.observe_in_session(session2_id, {"strings": ["Z"]})

        # Get Session 2's STM
        stm2_after_observe = await kato_client.get_session_stm(session2_id)
        print(f"DEBUG: Session 2 STM after observe: {stm2_after_observe['stm']}")

        # NOW GET SESSION 1's STM AGAIN - this is where the bug manifests
        stm1_final = await kato_client.get_session_stm(session1_id)
        print(f"DEBUG: Session 1 STM final (after session2 observes): {stm1_final['stm']}")

        # BUG CHECK: Session 1's STM should still be [['A'], ['B'], ['C']]
        # If bug exists, it might show [['X'], ['Y'], ['Z']] or a mix
        assert stm1_final['stm'] == [["A"], ["B"], ["C"]], \
            f"BUG DETECTED: Session 1 STM changed after Session 2 activity! " \
            f"Expected [['A'], ['B'], ['C']], got {stm1_final['stm']}"

        # Session 2's STM should be [['X'], ['Y'], ['Z']]
        assert stm2_after_observe['stm'] == [["X"], ["Y"], ["Z"]], \
            f"Session 2 STM incorrect. Expected [['X'], ['Y'], ['Z']], got {stm2_after_observe['stm']}"

        # Verify no cross-contamination in either direction
        stm1_str = str(stm1_final['stm'])
        stm2_str = str(stm2_after_observe['stm'])

        assert "X" not in stm1_str and "Y" not in stm1_str and "Z" not in stm1_str, \
            f"Session 1 should not contain Session 2's data. STM1: {stm1_final['stm']}"

        assert "A" not in stm2_str and "B" not in stm2_str and "C" not in stm2_str, \
            f"Session 2 should not contain Session 1's data. STM2: {stm2_after_observe['stm']}"

        # Cleanup
        await kato_client.delete_session(session1_id)
        await kato_client.delete_session(session2_id)

    @pytest.mark.asyncio
    async def test_stm_isolation_concurrent_same_node(self, kato_client):
        """
        Test STM isolation with concurrent operations on same node_id.

        This tests if there's a race condition when multiple sessions
        with the same node_id are being used simultaneously.
        """
        shared_node_id = f"test_node_{uuid.uuid4().hex[:8]}"

        # Create 5 sessions with the same node_id
        sessions = []
        for i in range(5):
            session = await kato_client.create_session(node_id=shared_node_id)
            sessions.append(session)

        async def build_session_stm(session_id: str, prefix: str):
            """Build STM for a session with unique prefix"""
            for j in range(3):
                await kato_client.observe_in_session(
                    session_id,
                    {"strings": [f"{prefix}_{j}"]}
                )
            return await kato_client.get_session_stm(session_id)

        # Process all sessions concurrently
        tasks = []
        for i, session in enumerate(sessions):
            task = build_session_stm(session['session_id'], f"S{i}")
            tasks.append(task)

        results = await asyncio.gather(*tasks)

        # Verify each session has its own unique STM
        for i, result in enumerate(results):
            expected = [[f"S{i}_{j}"] for j in range(3)]
            assert result['stm'] == expected, \
                f"Session {i} has incorrect STM under concurrent load. " \
                f"Expected {expected}, got {result['stm']}"

        # Verify no session has data from another session
        for i, result in enumerate(results):
            stm_str = str(result['stm'])
            for other_i in range(5):
                if other_i != i:
                    # Should not contain data from other sessions
                    assert f"S{other_i}_0" not in stm_str, \
                        f"Session {i} contains data from Session {other_i}: {result['stm']}"

        # Cleanup
        for session in sessions:
            await kato_client.delete_session(session['session_id'])

    @pytest.mark.asyncio
    async def test_get_or_create_session_isolation(self, kato_client):
        """
        Test that get_or_create_session properly isolates sessions.

        Tests the specific code path that might be causing the bug:
        - get_or_create_session uses node_id to track active session
        - But each call should still get its own session with isolated STM
        """
        node_id = f"test_node_{uuid.uuid4().hex[:8]}"

        # First call to get_or_create (should create new session)
        session1 = await kato_client.create_session(node_id=node_id)
        session1_id = session1['session_id']

        # Build STM in session1
        await kato_client.observe_in_session(session1_id, {"strings": ["first"]})
        await kato_client.observe_in_session(session1_id, {"strings": ["second"]})

        # Second call with SAME node_id (should create DIFFERENT session)
        session2 = await kato_client.create_session(node_id=node_id)
        session2_id = session2['session_id']

        # Verify they are different sessions
        assert session1_id != session2_id, \
            "create_session with same node_id should create different sessions"

        # Build different STM in session2
        await kato_client.observe_in_session(session2_id, {"strings": ["alpha"]})
        await kato_client.observe_in_session(session2_id, {"strings": ["beta"]})

        # Get STM from both sessions
        stm1 = await kato_client.get_session_stm(session1_id)
        stm2 = await kato_client.get_session_stm(session2_id)

        # Verify isolation
        assert stm1['stm'] == [["first"], ["second"]], \
            f"Session 1 STM incorrect: {stm1['stm']}"

        assert stm2['stm'] == [["alpha"], ["beta"]], \
            f"Session 2 STM incorrect: {stm2['stm']}"

        # Cleanup
        await kato_client.delete_session(session1_id)
        await kato_client.delete_session(session2_id)

    @pytest.mark.asyncio
    async def test_stm_isolation_after_learn(self, kato_client):
        """
        Test STM isolation when sessions share LTM (learned patterns).

        This tests the intended use case:
        - Multiple sessions with same node_id share learned patterns (LTM)
        - But their STM should remain isolated
        """
        shared_node_id = f"test_node_{uuid.uuid4().hex[:8]}"

        # Session 1: Learn a pattern
        session1 = await kato_client.create_session(node_id=shared_node_id)
        session1_id = session1['session_id']

        await kato_client.observe_in_session(session1_id, {"strings": ["hello"]})
        await kato_client.observe_in_session(session1_id, {"strings": ["world"]})
        await kato_client.learn_in_session(session1_id)

        # Get Session 1's STM before creating session 2
        stm1_before = await kato_client.get_session_stm(session1_id)
        print(f"DEBUG: Session 1 STM before session 2: {stm1_before['stm']}")

        # Session 2: Should have access to learned pattern but empty STM
        session2 = await kato_client.create_session(node_id=shared_node_id)
        session2_id = session2['session_id']

        # Get Session 2's initial STM (should be empty)
        stm2_initial = await kato_client.get_session_stm(session2_id)
        assert stm2_initial['stm'] == [], \
            f"Session 2 should start with empty STM, got: {stm2_initial['stm']}"

        # Session 2: Observe different data
        await kato_client.observe_in_session(session2_id, {"strings": ["foo"]})
        await kato_client.observe_in_session(session2_id, {"strings": ["bar"]})

        # Get STM from both sessions
        stm1_after = await kato_client.get_session_stm(session1_id)
        stm2_after = await kato_client.get_session_stm(session2_id)

        print(f"DEBUG: Session 1 STM after session 2: {stm1_after['stm']}")
        print(f"DEBUG: Session 2 STM after observe: {stm2_after['stm']}")

        # Session 1's STM should still be [["hello"], ["world"]]
        assert stm1_after['stm'] == [["hello"], ["world"]], \
            f"Session 1 STM changed! Expected [['hello'], ['world']], got {stm1_after['stm']}"

        # Session 2's STM should be [["foo"], ["bar"]]
        assert stm2_after['stm'] == [["foo"], ["bar"]], \
            f"Session 2 STM incorrect. Expected [['foo'], ['bar']], got {stm2_after['stm']}"

        # Cleanup
        await kato_client.delete_session(session1_id)
        await kato_client.delete_session(session2_id)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
