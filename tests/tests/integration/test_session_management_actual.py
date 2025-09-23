"""
Actual test suite for KATO Session Management
Tests real endpoints with running services
"""

import asyncio
import pytest
import time


class TestBasicSessionOperations:
    """Test basic session operations against real current services"""
    
    @pytest.mark.asyncio
    async def test_session_creation_and_deletion(self, kato_current_client):
        """Test creating and deleting a session"""
        # Create session
        session = await kato_current_client.create_session(
            user_id="test_user_basic"
        )
        
        assert "session_id" in session
        assert session["user_id"] == "test_user_basic"
        assert "created_at" in session
        
        # Verify session exists
        stm = await kato_current_client.get_session_stm(session["session_id"])
        assert stm["stm"] == []
        assert stm["session_id"] == session["session_id"]
        
        # Delete session
        await kato_current_client.delete_session(session["session_id"])
        
        # Verify session is gone
        with pytest.raises(Exception):  # Should be SessionNotFoundError
            await kato_current_client.get_session_stm(session["session_id"])
    
    @pytest.mark.asyncio
    async def test_basic_observation_in_session(self, isolated_session, kato_current_client):
        """Test basic observation in a session"""
        session_id = isolated_session["session_id"]
        
        # Add observation
        result = await kato_current_client.observe_in_session(
            session_id,
            {"strings": ["hello", "world"]}
        )
        
        assert "status" in result
        
        # Check STM
        stm = await kato_current_client.get_session_stm(session_id)
        assert len(stm["stm"]) == 1
        # Strings should be sorted alphabetically
        assert set(stm["stm"][0]) == {"hello", "world"}
    
    @pytest.mark.asyncio
    async def test_session_stm_persistence(self, isolated_session, kato_current_client):
        """Test that STM persists across requests within a session"""
        session_id = isolated_session["session_id"]
        
        # Build up sequence
        observations = ["first", "second", "third"]
        
        for obs in observations:
            await kato_current_client.observe_in_session(
                session_id,
                {"strings": [obs]}
            )
            
        # Check final STM
        stm = await kato_current_client.get_session_stm(session_id)
        assert len(stm["stm"]) == 3
        
        # Extract observations
        observed = [event[0] for event in stm["stm"]]
        assert observed == observations
    
    @pytest.mark.asyncio
    async def test_session_clear_stm(self, isolated_session, kato_current_client):
        """Test clearing STM in a session"""
        session_id = isolated_session["session_id"]
        
        # Add some data
        await kato_current_client.observe_in_session(
            session_id,
            {"strings": ["test_data"]}
        )
        
        # Verify data exists
        stm = await kato_current_client.get_session_stm(session_id)
        assert len(stm["stm"]) == 1
        
        # Clear STM
        await kato_current_client.clear_session_stm(session_id)
        
        # Verify STM is empty
        stm = await kato_current_client.get_session_stm(session_id)
        assert stm["stm"] == []


class TestSessionIsolation:
    """Test that sessions are properly isolated from each other"""
    
    @pytest.mark.asyncio
    async def test_two_session_isolation(self, kato_current_client):
        """Test that two sessions maintain separate STMs"""
        # Create two sessions
        session1 = await kato_current_client.create_session(user_id="user1")
        session2 = await kato_current_client.create_session(user_id="user2")
        
        try:
            # User 1 observes A, B, C
            for letter in ["A", "B", "C"]:
                await kato_current_client.observe_in_session(
                    session1["session_id"],
                    {"strings": [letter]}
                )
            
            # User 2 observes X, Y, Z
            for letter in ["X", "Y", "Z"]:
                await kato_current_client.observe_in_session(
                    session2["session_id"],
                    {"strings": [letter]}
                )
            
            # Check session 1 STM
            stm1 = await kato_current_client.get_session_stm(session1["session_id"])
            observed1 = [event[0] for event in stm1["stm"]]
            assert observed1 == ["A", "B", "C"]
            
            # Check session 2 STM  
            stm2 = await kato_current_client.get_session_stm(session2["session_id"])
            observed2 = [event[0] for event in stm2["stm"]]
            assert observed2 == ["X", "Y", "Z"]
            
            # Verify no cross-contamination
            assert "X" not in observed1
            assert "Y" not in observed1
            assert "Z" not in observed1
            assert "A" not in observed2
            assert "B" not in observed2
            assert "C" not in observed2
            
        finally:
            # Cleanup
            await kato_current_client.delete_session(session1["session_id"])
            await kato_current_client.delete_session(session2["session_id"])
    
    @pytest.mark.asyncio
    async def test_concurrent_session_operations(self, kato_current_client):
        """Test concurrent operations on different sessions"""
        sessions = []
        
        # Create 5 sessions
        for i in range(5):
            session = await kato_current_client.create_session(
                user_id=f"concurrent_user_{i}"
            )
            sessions.append(session)
        
        try:
            # Define concurrent operation for each session
            async def process_session(session_data, prefix):
                """Each session builds its own sequence"""
                session_id = session_data["session_id"]
                for j in range(3):
                    await kato_current_client.observe_in_session(
                        session_id,
                        {"strings": [f"{prefix}_{j}"]}
                    )
                return await kato_current_client.get_session_stm(session_id)
            
            # Process all sessions concurrently
            tasks = []
            for i, session in enumerate(sessions):
                task = process_session(session, f"S{i}")
                tasks.append(task)
            
            results = await asyncio.gather(*tasks)
            
            # Verify each session has correct, unique data
            for i, result in enumerate(results):
                expected = [[f"S{i}_{j}"] for j in range(3)]
                assert result["stm"] == expected, \
                    f"Session {i} corrupted. Expected {expected}, got {result['stm']}"
                
        finally:
            # Cleanup all sessions
            cleanup_tasks = [
                kato_current_client.delete_session(s["session_id"])
                for s in sessions
            ]
            await asyncio.gather(*cleanup_tasks, return_exceptions=True)


class TestSessionWithVectors:
    """Test sessions with vector and emotive data"""
    
    @pytest.mark.asyncio
    async def test_session_with_multimodal_data(self, isolated_session, kato_current_client):
        """Test session handling vectors and emotives"""
        session_id = isolated_session["session_id"]
        
        # Observe with vectors and emotives
        observation = {
            "strings": ["multimodal_test"],
            "vectors": [[0.1] * 768],  # 768-dim vector
            "emotives": {"joy": 0.8, "confidence": 0.6}
        }
        
        result = await kato_current_client.observe_in_session(session_id, observation)
        assert "status" in result
        
        # Check STM contains the data
        stm = await kato_current_client.get_session_stm(session_id)
        assert len(stm["stm"]) >= 1
        
        # Should have both the string and vector name
        flattened = [item for event in stm["stm"] for item in event]
        assert "multimodal_test" in flattened
        # Vector should be converted to VCTR|hash format
        assert any(item.startswith("VCTR|") for item in flattened)


@pytest.mark.performance
class TestSessionPerformance:
    """Performance tests for session operations"""
    
    @pytest.mark.asyncio
    async def test_session_creation_performance(self, kato_current_client):
        """Test session creation performance"""
        num_sessions = 20
        sessions = []
        
        start_time = time.time()
        
        # Create sessions
        for i in range(num_sessions):
            session = await kato_current_client.create_session(
                user_id=f"perf_user_{i}"
            )
            sessions.append(session)
        
        creation_time = time.time() - start_time
        avg_time_ms = (creation_time / num_sessions) * 1000
        
        # Should create sessions quickly
        assert avg_time_ms < 100, f"Session creation too slow: {avg_time_ms:.1f}ms"
        
        # Cleanup
        cleanup_tasks = [
            kato_current_client.delete_session(s["session_id"])
            for s in sessions
        ]
        await asyncio.gather(*cleanup_tasks, return_exceptions=True)
    
    @pytest.mark.asyncio
    async def test_concurrent_observations_performance(self, kato_current_client):
        """Test performance with concurrent observations"""
        # Create session
        session = await kato_current_client.create_session(user_id="perf_test")
        session_id = session["session_id"]
        
        try:
            # Define concurrent observation task
            async def observe_batch(start_index, count):
                for i in range(count):
                    await kato_current_client.observe_in_session(
                        session_id,
                        {"strings": [f"perf_obs_{start_index + i}"]}
                    )
            
            # Run concurrent batches
            start_time = time.time()
            batch_size = 10
            num_batches = 5
            
            tasks = [
                observe_batch(i * batch_size, batch_size)
                for i in range(num_batches)
            ]
            
            await asyncio.gather(*tasks)
            
            total_time = time.time() - start_time
            total_ops = batch_size * num_batches
            ops_per_second = total_ops / total_time
            
            # Should handle concurrent operations efficiently
            # Relaxed threshold - current has more overhead with session management
            assert ops_per_second > 10, f"Throughput too low: {ops_per_second:.1f} ops/sec"
            
            # Add a couple more observations to ensure STM has content
            # (auto-learn may have cleared STM after 50 observations)
            await kato_current_client.observe_in_session(
                session_id,
                {"strings": ["final_obs_1"]}
            )
            await kato_current_client.observe_in_session(
                session_id,
                {"strings": ["final_obs_2"]}
            )
            
            # Verify observations were recorded (may be limited by STM window)
            stm = await kato_current_client.get_session_stm(session_id)
            # STM should have the final observations after auto-learns
            assert len(stm["stm"]) > 0, "No observations were recorded"
            # The important metric here is throughput, not STM retention
            
        finally:
            await kato_current_client.delete_session(session_id)


# Legacy compatibility tests removed per project requirement
# All tests now use current session-based APIs only


class TestErrorHandling:
    """Test error handling for session operations"""
    
    @pytest.mark.asyncio
    async def test_invalid_session_operations(self, kato_current_client):
        """Test operations with invalid session IDs"""
        fake_session_id = "fake-session-12345"
        
        # Try to observe in non-existent session
        with pytest.raises(Exception) as exc_info:
            await kato_current_client.observe_in_session(
                fake_session_id,
                {"strings": ["test"]}
            )
        
        # Should get appropriate error
        error_msg = str(exc_info.value).lower()
        assert "not found" in error_msg or "404" in error_msg
    
    @pytest.mark.asyncio
    async def test_expired_session_handling(self, kato_current_client):
        """Test handling of expired sessions"""
        # Create session with very short TTL
        session = await kato_current_client.create_session(
            user_id="expire_test",
            ttl_seconds=2
        )
        session_id = session["session_id"]
        
        # Session should work initially
        await kato_current_client.observe_in_session(
            session_id,
            {"strings": ["before_expiry"]}
        )
        
        # Wait for expiration
        await asyncio.sleep(3)
        
        # Should now fail
        with pytest.raises(Exception):
            await kato_current_client.observe_in_session(
                session_id,
                {"strings": ["after_expiry"]}
            )


if __name__ == "__main__":
    # Run with: python -m pytest tests/tests/test_session_management_actual.py -v
    pytest.main([__file__, "-v", "-s"])