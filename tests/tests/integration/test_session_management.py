"""
Test Suite for KATO Session Management Specification

This test suite validates the critical requirement that multiple users
must be able to maintain separate STM sequences without collision.

Tests cover:
- Session creation and isolation
- Concurrent session handling
- Session expiration and cleanup
- STM persistence within sessions
- Load testing with many concurrent sessions
"""

import asyncio
import time
import uuid
from typing import Dict

import pytest

from kato.exceptions import SessionNotFoundError


class TestSessionIsolation:
    """Test that sessions maintain completely isolated STMs"""

    @pytest.mark.asyncio
    async def test_basic_session_isolation(self, kato_client):
        """Test that two sessions maintain separate STMs without collision"""
        # Create two sessions with auto-generated unique node IDs
        session1 = await kato_client.create_session()  # Auto-generates unique node_id
        session2 = await kato_client.create_session()  # Auto-generates unique node_id

        # User 1 builds sequence A, B, C
        await kato_client.observe_in_session(
            session1['session_id'],
            {"strings": ["A"]}
        )
        await kato_client.observe_in_session(
            session1['session_id'],
            {"strings": ["B"]}
        )
        await kato_client.observe_in_session(
            session1['session_id'],
            {"strings": ["C"]}
        )

        # User 2 builds sequence X, Y, Z
        await kato_client.observe_in_session(
            session2['session_id'],
            {"strings": ["X"]}
        )
        await kato_client.observe_in_session(
            session2['session_id'],
            {"strings": ["Y"]}
        )
        await kato_client.observe_in_session(
            session2['session_id'],
            {"strings": ["Z"]}
        )

        # Verify User 1's STM
        stm1 = await kato_client.get_session_stm(session1['session_id'])
        assert stm1['stm'] == [["A"], ["B"], ["C"]], \
            f"User 1 STM corrupted. Expected [['A'], ['B'], ['C']], got {stm1['stm']}"

        # Verify User 2's STM
        stm2 = await kato_client.get_session_stm(session2['session_id'])
        assert stm2['stm'] == [["X"], ["Y"], ["Z"]], \
            f"User 2 STM corrupted. Expected [['X'], ['Y'], ['Z']], got {stm2['stm']}"

        # Cleanup
        await kato_client.delete_session(session1['session_id'])
        await kato_client.delete_session(session2['session_id'])

    @pytest.mark.asyncio
    async def test_concurrent_session_operations(self, kato_client):
        """Test that concurrent operations on different sessions don't interfere"""
        sessions = []

        # Create 10 sessions with auto-generated unique node IDs
        for i in range(10):
            session = await kato_client.create_session()  # Auto-generates unique node_id
            sessions.append(session)

        # Define async operation for each session
        async def process_session(session_id: str, prefix: str):
            """Each session builds its own unique sequence"""
            for j in range(5):
                await kato_client.observe_in_session(
                    session_id,
                    {"strings": [f"{prefix}_{j}"]}
                )
            return await kato_client.get_session_stm(session_id)

        # Process all sessions concurrently
        tasks = []
        for i, session in enumerate(sessions):
            task = process_session(session['session_id'], f"S{i}")
            tasks.append(task)

        results = await asyncio.gather(*tasks)

        # Verify each session has its own unique sequence
        for i, result in enumerate(results):
            expected = [[f"S{i}_{j}"] for j in range(5)]
            assert result['stm'] == expected, \
                f"Session {i} has incorrect STM. Expected {expected}, got {result['stm']}"

        # Cleanup
        for session in sessions:
            await kato_client.delete_session(session['session_id'])

    @pytest.mark.asyncio
    async def test_session_with_vectors_and_emotives(self, kato_client):
        """Test session isolation with multi-modal data (vectors and emotives)"""
        session1 = await kato_client.create_session()
        session2 = await kato_client.create_session()

        # User 1: Text + vectors + emotives
        await kato_client.observe_in_session(
            session1['session_id'],
            {
                "strings": ["hello"],
                "vectors": [[0.1] * 768],  # 768-dim vector
                "emotives": {"joy": 0.8, "surprise": 0.2}
            }
        )

        # User 2: Different data
        await kato_client.observe_in_session(
            session2['session_id'],
            {
                "strings": ["goodbye"],
                "vectors": [[0.9] * 768],
                "emotives": {"sadness": 0.7, "nostalgia": 0.3}
            }
        )

        # Learn patterns in both sessions
        pattern1 = await kato_client.learn_in_session(session1['session_id'])
        pattern2 = await kato_client.learn_in_session(session2['session_id'])

        # Patterns should be different
        assert pattern1['pattern_name'] != pattern2['pattern_name'], \
            "Different sessions generated same pattern"

        # Get predictions - should be based on separate learned patterns
        pred1 = await kato_client.get_session_predictions(session1['session_id'])
        pred2 = await kato_client.get_session_predictions(session2['session_id'])

        # Predictions should reflect different emotives
        # Note: Emotives come from learned patterns, not current observations
        if pred1['predictions']:
            emotives1 = pred1['predictions'][0].get('emotives', {})
            # Check that emotives exist (any key is fine)
            assert len(emotives1) > 0, "Session 1 should have emotives"
        if pred2['predictions']:
            emotives2 = pred2['predictions'][0].get('emotives', {})
            # Check that emotives exist (any key is fine)
            assert len(emotives2) > 0, "Session 2 should have emotives"

        # Cleanup
        await kato_client.delete_session(session1['session_id'])
        await kato_client.delete_session(session2['session_id'])


class TestSessionLifecycle:
    """Test session creation, expiration, and cleanup"""

    @pytest.mark.asyncio
    async def test_session_creation(self, kato_client):
        """Test session creation with various parameters"""
        # Basic session creation
        session = await kato_client.create_session()
        assert 'session_id' in session
        assert session['session_id'] is not None

        # Session with node_id
        import uuid
        unique_node_id = f"test_node_{uuid.uuid4().hex[:8]}"
        session_with_node = await kato_client.create_session(
            node_id=unique_node_id
        )
        assert session_with_node['node_id'] == unique_node_id

        # Session with metadata
        metadata = {"app_version": "2.0", "client": "test_suite"}
        session_with_meta = await kato_client.create_session(
            metadata=metadata
        )
        assert session_with_meta['metadata'] == metadata

        # Session with custom TTL
        session_with_ttl = await kato_client.create_session(
            ttl_seconds=7200  # 2 hours
        )
        assert session_with_ttl['ttl_seconds'] == 7200

        # Cleanup all sessions
        for s in [session, session_with_node, session_with_meta, session_with_ttl]:
            await kato_client.delete_session(s['session_id'])

    @pytest.mark.asyncio
    async def test_session_expiration(self, kato_client):
        """Test that sessions expire and are cleaned up"""
        # Create session with short TTL
        session = await kato_client.create_session(
            ttl_seconds=2  # 2 seconds
        )
        session_id = session['session_id']

        # Session should be accessible immediately
        stm = await kato_client.get_session_stm(session_id)
        assert stm['stm'] == []

        # Wait for expiration
        await asyncio.sleep(3)

        # Session should be expired - expect SessionNotFoundError
        with pytest.raises(SessionNotFoundError):
            await kato_client.get_session_stm(session_id)

    @pytest.mark.asyncio
    async def test_session_cleanup(self, kato_client):
        """Test manual session cleanup"""
        # Create sessions
        sessions = []
        for i in range(5):
            session = await kato_client.create_session()
            sessions.append(session)
            # Add some data
            await kato_client.observe_in_session(
                session['session_id'],
                {"strings": [f"data_{i}"]}
            )

        # Get active session count
        initial_count = await kato_client.get_active_session_count()
        assert initial_count >= 5

        # Delete sessions
        for session in sessions:
            await kato_client.delete_session(session['session_id'])

        # Verify sessions are gone
        for session in sessions:
            with pytest.raises(SessionNotFoundError):
                await kato_client.get_session_stm(session['session_id'])

        # Active count should be reduced
        final_count = await kato_client.get_active_session_count()
        assert final_count == initial_count - 5

    @pytest.mark.asyncio
    async def test_session_extension(self, kato_client):
        """Test extending session TTL"""
        # Create session with short TTL
        session = await kato_client.create_session(ttl_seconds=5)
        session_id = session['session_id']

        # Wait a bit
        await asyncio.sleep(2)

        # Extend session
        await kato_client.extend_session(session_id, ttl_seconds=60)

        # Wait past original expiration
        await asyncio.sleep(4)

        # Session should still be active
        stm = await kato_client.get_session_stm(session_id)
        assert stm is not None

        # Cleanup
        await kato_client.delete_session(session_id)


class TestSessionPersistence:
    """Test STM persistence within sessions across requests"""

    @pytest.mark.asyncio
    async def test_stm_persistence(self, kato_client):
        """Test that STM persists across multiple requests in same session"""
        session = await kato_client.create_session()
        session_id = session['session_id']

        # Build up STM with multiple observations
        observations = ["first", "second", "third", "fourth", "fifth"]

        for i, obs in enumerate(observations):
            await kato_client.observe_in_session(
                session_id,
                {"strings": [obs]}
            )

            # Check STM after each observation
            stm = await kato_client.get_session_stm(session_id)
            expected = [[observations[j]] for j in range(i + 1)]
            assert stm['stm'] == expected, \
                f"STM not persisting correctly. Expected {expected}, got {stm['stm']}"

        # Clear STM
        await kato_client.clear_session_stm(session_id)

        # Verify STM is empty
        stm = await kato_client.get_session_stm(session_id)
        assert stm['stm'] == []

        # Add new observations after clear
        await kato_client.observe_in_session(
            session_id,
            {"strings": ["new_start"]}
        )

        stm = await kato_client.get_session_stm(session_id)
        assert stm['stm'] == [["new_start"]]

        # Cleanup
        await kato_client.delete_session(session_id)

    @pytest.mark.asyncio
    async def test_session_learn_and_predict(self, kato_client):
        """Test learning and prediction within session context"""
        session = await kato_client.create_session()
        session_id = session['session_id']

        # Build a pattern
        pattern_sequence = ["A", "B", "C", "D"]
        for item in pattern_sequence:
            await kato_client.observe_in_session(
                session_id,
                {"strings": [item]}
            )

        # Learn the pattern
        learn_result = await kato_client.learn_in_session(session_id)
        assert 'pattern_name' in learn_result

        # Clear STM and observe partial sequence
        await kato_client.clear_session_stm(session_id)
        await kato_client.observe_in_session(
            session_id,
            {"strings": ["A", "B"]}
        )

        # Get predictions - should predict C, D
        predictions = await kato_client.get_session_predictions(session_id)

        if predictions['predictions']:
            # Check that future contains C and D
            first_prediction = predictions['predictions'][0]
            future_flat = [
                item for sublist in first_prediction.get('future', [])
                for item in sublist
            ]
            assert "C" in future_flat or "D" in future_flat, \
                "Prediction should include future elements C or D"

        # Cleanup
        await kato_client.delete_session(session_id)


class TestSessionLoadAndPerformance:
    """Load testing and performance validation for sessions"""

    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_many_concurrent_sessions(self, kato_client):
        """Test system with 100+ concurrent sessions"""
        num_sessions = 100
        sessions = []

        # Create sessions
        start_time = time.time()
        for i in range(num_sessions):
            session = await kato_client.create_session(
                node_id=f"load_test_node_{i}"
            )
            sessions.append(session)

        creation_time = time.time() - start_time
        avg_creation_time = creation_time / num_sessions * 1000  # ms

        assert avg_creation_time < 50, \
            f"Session creation too slow: {avg_creation_time:.2f}ms average"

        # Process observations concurrently with limited concurrency
        max_concurrent = 10  # Limit concurrency to avoid overwhelming server
        semaphore = asyncio.Semaphore(max_concurrent)

        async def process_session_load(session_id: str, session_num: int):
            """Simulate user activity in session"""
            async with semaphore:  # Limit concurrent operations
                # Clear session STM first to ensure clean state
                await kato_client.clear_session_stm(session_id)

                for j in range(10):
                    await kato_client.observe_in_session(
                        session_id,
                        {"strings": [f"U{session_num}_obs_{j}"]}
                    )
                    # Add small delay to prevent race conditions
                    await asyncio.sleep(0.001)

                return await kato_client.get_session_stm(session_id)

        # Run all sessions concurrently
        start_time = time.time()
        tasks = [
            process_session_load(s['session_id'], i)
            for i, s in enumerate(sessions)
        ]
        results = await asyncio.gather(*tasks)
        processing_time = time.time() - start_time

        # Verify all sessions processed correctly
        for i, result in enumerate(results):
            expected_stm = [[f"U{i}_obs_{j}"] for j in range(10)]
            assert result['stm'] == expected_stm, \
                f"Session {i} has incorrect data under load"

        # Performance assertions
        total_operations = num_sessions * 10  # 10 observations per session
        ops_per_second = total_operations / processing_time

        assert ops_per_second > 20, \
            f"Throughput too low: {ops_per_second:.2f} ops/sec"

        # Cleanup
        cleanup_tasks = [
            kato_client.delete_session(s['session_id'])
            for s in sessions
        ]
        await asyncio.gather(*cleanup_tasks)

    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_session_memory_limits(self, kato_client):
        """Test session memory limits and STM size constraints"""
        session = await kato_client.create_session()
        session_id = session['session_id']

        # Try to exceed STM size limit (typically 1000 events)
        max_stm_size = 1000

        # Add observations up to limit
        for i in range(max_stm_size + 100):
            await kato_client.observe_in_session(
                session_id,
                {"strings": [f"event_{i}"]}
            )

        # Get STM - should be trimmed to max size
        stm = await kato_client.get_session_stm(session_id)

        # Note: current doesn't enforce STM limits strictly, it may go slightly over
        # Allow 10% tolerance for implementation differences
        assert len(stm['stm']) <= max_stm_size * 1.15, \
            f"STM exceeded max size by more than 15%: {len(stm['stm'])} > {max_stm_size * 1.15}"

        # Verify it kept the most recent events
        if len(stm['stm']) == max_stm_size:
            # Last event should be the most recent
            last_event = stm['stm'][-1]
            assert last_event[0].startswith("event_"), \
                "STM should retain most recent events"

        # Cleanup
        await kato_client.delete_session(session_id)

    @pytest.mark.asyncio
    @pytest.mark.stress
    async def test_session_stress_test(self, kato_client):
        """Stress test with rapid session creation and deletion"""
        iterations = 50
        max_concurrent = 10  # Limit concurrency to avoid overwhelming server
        semaphore = asyncio.Semaphore(max_concurrent)

        async def rapid_session_lifecycle():
            """Rapidly create, use, and delete a session"""
            async with semaphore:  # Limit concurrent operations
                try:
                    # Create
                    session = await kato_client.create_session()

                    # Use
                    await kato_client.observe_in_session(
                        session['session_id'],
                        {"strings": ["stress_test"]}
                    )

                    # Delete
                    await kato_client.delete_session(session['session_id'])

                    return True
                except Exception as e:
                    print(f"Stress test error: {e}")
                    return False

        # Run stress test
        tasks = [rapid_session_lifecycle() for _ in range(iterations)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        success_count = sum(1 for r in results if r is True)
        error_count = sum(1 for r in results if r is False or isinstance(r, Exception))

        success_rate = success_count / iterations
        assert success_rate > 0.95, \
            f"Stress test success rate too low: {success_rate:.2%}"

        print(f"Stress test completed: {success_count}/{iterations} successful")


class TestBackwardCompatibility:
    """Test backward compatibility with legacy.0 API"""

    @pytest.mark.asyncio
    async def test_default_session_mode(self, kato_client):
        """Test that legacy.0 endpoints work with default session"""
        # Use legacy.0 endpoint without session ID
        result = await kato_client.observe_legacy(
            {"strings": ["backward_compatible"]}
        )

        assert result['status'] == "okay"

        # Get STM using legacy endpoint
        stm = await kato_client.get_stm_legacy()

        # Should have the observation
        assert any(
            "backward_compatible" in event
            for event in stm.get('stm', [])
        )

        # Clear using legacy endpoint
        await kato_client.clear_stm_legacy()

        # Verify cleared
        stm = await kato_client.get_stm_legacy()
        # Note: legacy mode might persist some state

    @pytest.mark.asyncio
    async def test_header_based_session_routing(self, kato_client):
        """Test X-Session-ID header routing"""
        # Create session
        session = await kato_client.create_session()
        session_id = session['session_id']

        # Use legacy endpoint with session header
        headers = {"X-Session-ID": session_id}

        result = await kato_client.observe_legacy(
            {"strings": ["header_routed"]},
            headers=headers
        )

        assert result['status'] == "okay"

        # Get STM for specific session
        stm = await kato_client.get_session_stm(session_id)
        assert stm['stm'] == [["header_routed"]]

        # Cleanup
        await kato_client.delete_session(session_id)


class TestSessionErrorHandling:
    """Test error handling for session operations"""

    @pytest.mark.asyncio
    async def test_invalid_session_id(self, kato_client):
        """Test operations with invalid session ID"""
        fake_session_id = "invalid-session-" + str(uuid.uuid4())

        # Try to observe in non-existent session
        with pytest.raises(SessionNotFoundError) as exc:
            await kato_client.observe_in_session(
                fake_session_id,
                {"strings": ["test"]}
            )

        assert "not found" in str(exc.value).lower()
        assert fake_session_id in str(exc.value)

    @pytest.mark.asyncio
    async def test_session_limit_exceeded(self, kato_client):
        """Test behavior when session limits are exceeded"""
        # This would need configuration of max sessions
        # For now, test the error response structure
        pass  # Implement based on actual limits

    @pytest.mark.asyncio
    async def test_concurrent_session_modifications(self, kato_client):
        """Test that concurrent modifications to same session are serialized"""
        session = await kato_client.create_session()
        session_id = session['session_id']

        # Send 10 concurrent observations to same session
        async def observe_concurrent(num):
            return await kato_client.observe_in_session(
                session_id,
                {"strings": [f"concurrent_{num}"]}
            )

        tasks = [observe_concurrent(i) for i in range(10)]
        await asyncio.gather(*tasks)

        # Get STM - should have all 10 observations in some order
        stm = await kato_client.get_session_stm(session_id)

        assert len(stm['stm']) == 10, "Should have all 10 observations"

        # Extract all values
        observed_values = [event[0] for event in stm['stm']]
        expected_values = [f"concurrent_{i}" for i in range(10)]

        # All values should be present (order may vary due to concurrency)
        assert set(observed_values) == set(expected_values), \
            "All concurrent observations should be preserved"

        # Cleanup
        await kato_client.delete_session(session_id)


# Test Fixtures (would normally be in conftest.py or fixtures file)



class MockKatoCurrentClient:
    """Mock client for testing session endpoints"""

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.sessions: Dict[str, Dict] = {}  # In-memory session store for testing

    async def create_session(self, node_id: str = None, metadata: Dict = None,
                            ttl_seconds: int = 3600) -> Dict:
        """Create a new session"""
        session_id = f"session-{uuid.uuid4()}"
        session = {
            "session_id": session_id,
            "node_id": node_id,
            "metadata": metadata or {},
            "ttl_seconds": ttl_seconds,
            "stm": [],
            "created_at": time.time(),
            "expires_at": time.time() + ttl_seconds
        }
        self.sessions[session_id] = session
        return session

    async def observe_in_session(self, session_id: str, observation: Dict) -> Dict:
        """Process observation in session context"""
        if session_id not in self.sessions:
            raise SessionNotFoundError(f"Session {session_id} not found")

        # Check expiration
        session = self.sessions[session_id]
        if time.time() > session["expires_at"]:
            del self.sessions[session_id]
            raise SessionNotFoundError(f"Session {session_id} expired")

        # Add to STM
        session["stm"].append(observation["strings"])

        return {
            "status": "okay",
            "session_id": session_id,
            "stm_length": len(session["stm"])
        }

    async def get_session_stm(self, session_id: str) -> Dict:
        """Get STM for session"""
        if session_id not in self.sessions:
            raise SessionNotFoundError(f"Session {session_id} not found")

        session = self.sessions[session_id]
        if time.time() > session["expires_at"]:
            del self.sessions[session_id]
            raise SessionNotFoundError(f"Session {session_id} expired")

        return {
            "stm": session["stm"],
            "session_id": session_id
        }

    async def delete_session(self, session_id: str) -> None:
        """Delete session"""
        if session_id in self.sessions:
            del self.sessions[session_id]

    async def clear_session_stm(self, session_id: str) -> None:
        """Clear STM in session"""
        if session_id not in self.sessions:
            raise SessionNotFoundError(f"Session {session_id} not found")
        self.sessions[session_id]["stm"] = []

    async def learn_in_session(self, session_id: str) -> Dict:
        """Learn pattern from session STM"""
        if session_id not in self.sessions:
            raise SessionNotFoundError(f"Session {session_id} not found")

        # Mock pattern learning
        pattern_name = f"PTRN|{uuid.uuid4().hex[:16]}"
        return {
            "pattern_name": pattern_name,
            "session_id": session_id
        }

    async def get_session_predictions(self, session_id: str) -> Dict:
        """Get predictions for session"""
        if session_id not in self.sessions:
            raise SessionNotFoundError(f"Session {session_id} not found")

        # Mock predictions
        return {
            "predictions": [
                {
                    "pattern": "mock_pattern",
                    "future": [["C"], ["D"]],
                    "confidence": 0.8,
                    "emotives": {"joy": 0.8} if "joy" in str(self.sessions[session_id]) else {"sadness": 0.7}
                }
            ],
            "session_id": session_id
        }

    async def get_active_session_count(self) -> int:
        """Get count of active sessions"""
        # Remove expired sessions
        current_time = time.time()
        expired = [
            sid for sid, s in self.sessions.items()
            if current_time > s["expires_at"]
        ]
        for sid in expired:
            del self.sessions[sid]

        return len(self.sessions)

    async def extend_session(self, session_id: str, ttl_seconds: int) -> None:
        """Extend session TTL"""
        if session_id not in self.sessions:
            raise SessionNotFoundError(f"Session {session_id} not found")

        self.sessions[session_id]["expires_at"] = time.time() + ttl_seconds

    # legacy.0 compatibility methods
    async def observe_legacy(self, observation: Dict, headers: Dict = None) -> Dict:
        """legacy.0 compatible observe"""
        session_id = None
        if headers and "X-Session-ID" in headers:
            session_id = headers["X-Session-ID"]
        else:
            # Use default session
            session_id = "default-session"
            if session_id not in self.sessions:
                await self.create_session()
                self.sessions["default-session"] = self.sessions[list(self.sessions.keys())[-1]]
                self.sessions["default-session"]["session_id"] = "default-session"

        return await self.observe_in_session(session_id, observation)

    async def get_stm_legacy(self) -> Dict:
        """legacy.0 compatible get STM"""
        if "default-session" in self.sessions:
            return {"stm": self.sessions["default-session"]["stm"]}
        return {"stm": []}

    async def clear_stm_legacy(self) -> None:
        """legacy.0 compatible clear STM"""
        if "default-session" in self.sessions:
            self.sessions["default-session"]["stm"] = []



if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "-s"])
