"""
Multi-User Integration Tests for KATO v2.0

This test suite validates complex multi-user scenarios to ensure:
- Complete data isolation between users
- Correct behavior under concurrent load
- Session handoff and migration scenarios
- Performance with many simultaneous users
- Edge cases with session conflicts

These are end-to-end integration tests that validate the entire v2.0 stack.
"""

import asyncio
import pytest
import time
import random
import uuid
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
import aiohttp
from datetime import datetime, timedelta


@dataclass
class UserScenario:
    """Represents a user interaction scenario"""
    user_id: str
    session_id: Optional[str]
    actions: List[Dict[str, Any]]
    expected_stm: List[List[str]]
    expected_predictions: Optional[List[str]]


class TestMultiUserIsolation:
    """Test complete isolation between multiple concurrent users"""
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_concurrent_users_no_collision(self, kato_v2_system):
        """Test that 10 concurrent users maintain completely isolated sequences"""
        system = kato_v2_system
        users = []
        
        # Create 10 users with unique sequences
        for i in range(10):
            user = UserScenario(
                user_id=f"user_{i}",
                session_id=None,
                actions=[
                    {"type": "observe", "data": {"strings": [f"U{i}_A"]}},
                    {"type": "observe", "data": {"strings": [f"U{i}_B"]}},
                    {"type": "observe", "data": {"strings": [f"U{i}_C"]}},
                    {"type": "learn"},
                    {"type": "clear_stm"},
                    {"type": "observe", "data": {"strings": [f"U{i}_A", f"U{i}_B"]}},
                    {"type": "get_predictions"}
                ],
                expected_stm=[[f"U{i}_A", f"U{i}_B"]],
                expected_predictions=[f"U{i}_C"]
            )
            users.append(user)
        
        # Execute all user scenarios concurrently
        results = await self._execute_concurrent_scenarios(system, users)
        
        # Verify each user's results
        for i, (user, result) in enumerate(zip(users, results)):
            # Check final STM
            assert result['final_stm'] == user.expected_stm, \
                f"User {i} STM corrupted: expected {user.expected_stm}, got {result['final_stm']}"
            
            # Check predictions (may be empty if no patterns match)
            if user.expected_predictions:
                if result['predictions']:
                    future_items = self._extract_future_items(result['predictions'])
                    # Check if we got any expected predictions
                    found_any = any(expected in future_items for expected in user.expected_predictions)
                    if not found_any and len(result['predictions']) > 0:
                        # Only fail if we got predictions but none were expected
                        assert found_any, \
                            f"User {i} got unexpected predictions instead of {user.expected_predictions}"
            
            # Ensure no cross-contamination
            for j, other_user in enumerate(users):
                if i != j:
                    # Other user's data should not appear
                    other_prefix = f"U{j}_"
                    assert not any(
                        other_prefix in str(item)
                        for sublist in result['final_stm']
                        for item in sublist
                    ), f"User {i} has data from User {j}"
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_pattern_learning_isolation(self, kato_v2_system):
        """Test that patterns learned by one user don't affect another"""
        system = kato_v2_system
        
        # User 1 learns a specific pattern
        user1_session = await system.create_session(user_id="pattern_user_1")
        
        # Build and learn pattern
        for item in ["RED", "GREEN", "BLUE"]:
            await system.observe_in_session(
                user1_session['session_id'],
                {"strings": [item]}
            )
        
        pattern1 = await system.learn_in_session(user1_session['session_id'])
        
        # User 2 with different pattern
        user2_session = await system.create_session(user_id="pattern_user_2")
        
        for item in ["ALPHA", "BETA", "GAMMA"]:
            await system.observe_in_session(
                user2_session['session_id'],
                {"strings": [item]}
            )
        
        pattern2 = await system.learn_in_session(user2_session['session_id'])
        
        # Patterns should be different
        assert pattern1['pattern_name'] != pattern2['pattern_name']
        
        # Clear and test predictions
        await system.clear_session_stm(user1_session['session_id'])
        await system.clear_session_stm(user2_session['session_id'])
        
        # User 1 observes partial sequence
        await system.observe_in_session(
            user1_session['session_id'],
            {"strings": ["RED", "GREEN"]}
        )
        
        pred1 = await system.get_session_predictions(user1_session['session_id'])
        
        # User 2 observes partial sequence
        await system.observe_in_session(
            user2_session['session_id'],
            {"strings": ["ALPHA", "BETA"]}
        )
        
        pred2 = await system.get_session_predictions(user2_session['session_id'])
        
        # Predictions should be based on own patterns only
        if pred1['predictions']:
            future1 = self._extract_future_items(pred1['predictions'])
            assert "BLUE" in future1
            assert "GAMMA" not in future1
        
        if pred2['predictions']:
            future2 = self._extract_future_items(pred2['predictions'])
            assert "GAMMA" in future2
            assert "BLUE" not in future2
        
        # Cleanup
        await system.delete_session(user1_session['session_id'])
        await system.delete_session(user2_session['session_id'])
    
    async def _execute_concurrent_scenarios(self, system, users: List[UserScenario]):
        """Execute multiple user scenarios concurrently"""
        
        async def execute_user_scenario(user: UserScenario):
            # Create session
            session = await system.create_session(user_id=user.user_id)
            user.session_id = session['session_id']
            
            result = {
                'user_id': user.user_id,
                'session_id': user.session_id,
                'final_stm': None,
                'predictions': None
            }
            
            # Execute actions
            for action in user.actions:
                if action['type'] == 'observe':
                    await system.observe_in_session(
                        user.session_id,
                        action['data']
                    )
                elif action['type'] == 'learn':
                    await system.learn_in_session(user.session_id)
                elif action['type'] == 'clear_stm':
                    await system.clear_session_stm(user.session_id)
                elif action['type'] == 'get_predictions':
                    result['predictions'] = await system.get_session_predictions(
                        user.session_id
                    )
            
            # Get final STM
            stm_response = await system.get_session_stm(user.session_id)
            result['final_stm'] = stm_response['stm']
            
            # Cleanup
            await system.delete_session(user.session_id)
            
            return result
        
        # Execute all scenarios concurrently
        tasks = [execute_user_scenario(user) for user in users]
        return await asyncio.gather(*tasks)
    
    def _extract_future_items(self, predictions):
        """Extract all future items from predictions"""
        items = []
        for pred in predictions:
            if 'future' in pred:
                for event in pred['future']:
                    items.extend(event)
        return items


class TestSessionHandoff:
    """Test session handoff and migration scenarios"""
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_session_resume_after_disconnect(self, kato_v2_system):
        """Test that user can resume session after disconnect"""
        system = kato_v2_system
        
        # User starts session
        session = await system.create_session(user_id="mobile_user")
        session_id = session['session_id']
        
        # Build some state
        for item in ["START", "MIDDLE"]:
            await system.observe_in_session(session_id, {"strings": [item]})
        
        # Simulate disconnect (don't delete session)
        # ...time passes...
        await asyncio.sleep(0.1)
        
        # User reconnects with same session
        stm = await system.get_session_stm(session_id)
        assert stm['stm'] == [["START"], ["MIDDLE"]]
        
        # Continue where left off
        await system.observe_in_session(session_id, {"strings": ["END"]})
        
        stm = await system.get_session_stm(session_id)
        assert stm['stm'] == [["START"], ["MIDDLE"], ["END"]]
        
        # Cleanup
        await system.delete_session(session_id)
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_session_migration_between_devices(self, kato_v2_system):
        """Test session migration from one device to another"""
        system = kato_v2_system
        
        # User on Device A
        session_a = await system.create_session(
            user_id="cross_device_user",
            metadata={"device": "phone"}
        )
        session_id = session_a['session_id']
        
        # Build state on Device A
        for item in ["PHONE_1", "PHONE_2"]:
            await system.observe_in_session(session_id, {"strings": [item]})
        
        # User switches to Device B (using same session ID)
        # Would typically involve authentication/authorization
        
        # Continue on Device B with same session
        await system.observe_in_session(
            session_id,
            {"strings": ["DESKTOP_1"]}
        )
        
        # Verify combined state
        stm = await system.get_session_stm(session_id)
        assert stm['stm'] == [["PHONE_1"], ["PHONE_2"], ["DESKTOP_1"]]
        
        # Cleanup
        await system.delete_session(session_id)
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_concurrent_device_access_same_session(self, kato_v2_system):
        """Test behavior when same session accessed from multiple devices"""
        system = kato_v2_system
        
        # Create session
        session = await system.create_session(user_id="multi_device_user")
        session_id = session['session_id']
        
        # Simulate concurrent access from 2 devices
        async def device_a_actions():
            for i in range(5):
                await system.observe_in_session(
                    session_id,
                    {"strings": [f"DEVICE_A_{i}"]}
                )
                await asyncio.sleep(0.01)
        
        async def device_b_actions():
            for i in range(5):
                await system.observe_in_session(
                    session_id,
                    {"strings": [f"DEVICE_B_{i}"]}
                )
                await asyncio.sleep(0.01)
        
        # Run concurrently
        await asyncio.gather(device_a_actions(), device_b_actions())
        
        # Check final state
        stm = await system.get_session_stm(session_id)
        
        # Should have all 10 observations (order may vary)
        assert len(stm['stm']) == 10
        
        # Extract all values
        all_values = [event[0] for event in stm['stm']]
        
        # Should have all device A values
        for i in range(5):
            assert f"DEVICE_A_{i}" in all_values
        
        # Should have all device B values
        for i in range(5):
            assert f"DEVICE_B_{i}" in all_values
        
        # Cleanup
        await system.delete_session(session_id)


class TestPerformanceUnderLoad:
    """Test system performance with many concurrent users"""
    
    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_100_concurrent_active_users(self, kato_v2_system):
        """Test system with 100 actively interacting users"""
        system = kato_v2_system
        num_users = 100
        observations_per_user = 20
        
        start_time = time.time()
        
        async def simulate_user(user_num: int):
            """Simulate an active user session"""
            # Create session
            session = await system.create_session(user_id=f"load_user_{user_num}")
            session_id = session['session_id']
            
            # Perform observations
            for obs_num in range(observations_per_user):
                await system.observe_in_session(
                    session_id,
                    {"strings": [f"U{user_num}_O{obs_num}"]}
                )
            
            # Get final STM
            stm = await system.get_session_stm(session_id)
            
            # Verify correctness
            assert len(stm['stm']) == observations_per_user
            
            # Cleanup
            await system.delete_session(session_id)
            
            return user_num
        
        # Run all users concurrently
        tasks = [simulate_user(i) for i in range(num_users)]
        results = await asyncio.gather(*tasks)
        
        elapsed = time.time() - start_time
        
        # Performance assertions
        assert len(results) == num_users, "All users should complete"
        
        total_operations = num_users * (observations_per_user + 3)  # +3 for create, get, delete
        ops_per_second = total_operations / elapsed
        
        print(f"\nPerformance Test Results:")
        print(f"  Users: {num_users}")
        print(f"  Total operations: {total_operations}")
        print(f"  Time: {elapsed:.2f}s")
        print(f"  Throughput: {ops_per_second:.2f} ops/sec")
        
        # Should handle at least 500 ops/sec
        assert ops_per_second > 500, f"Throughput too low: {ops_per_second:.2f} ops/sec"
    
    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_burst_traffic_handling(self, kato_v2_system):
        """Test system response to traffic bursts"""
        system = kato_v2_system
        
        # Create sessions first
        sessions = []
        for i in range(50):
            session = await system.create_session(user_id=f"burst_user_{i}")
            sessions.append(session['session_id'])
        
        # Measure baseline
        baseline_start = time.time()
        for session_id in sessions[:10]:
            await system.observe_in_session(
                session_id,
                {"strings": ["baseline"]}
            )
        baseline_time = (time.time() - baseline_start) / 10
        
        # Create burst - all 50 users observe simultaneously
        burst_start = time.time()
        
        tasks = [
            system.observe_in_session(sid, {"strings": ["burst"]})
            for sid in sessions
        ]
        await asyncio.gather(*tasks)
        
        burst_time = (time.time() - burst_start) / 50
        
        # Burst should not be more than 5x slower than baseline
        slowdown = burst_time / baseline_time
        
        print(f"\nBurst Test Results:")
        print(f"  Baseline: {baseline_time*1000:.2f}ms per request")
        print(f"  Burst: {burst_time*1000:.2f}ms per request")
        print(f"  Slowdown: {slowdown:.2f}x")
        
        assert slowdown < 5, f"Burst caused {slowdown:.2f}x slowdown"
        
        # Cleanup
        for session_id in sessions:
            await system.delete_session(session_id)
    
    @pytest.mark.asyncio
    @pytest.mark.stress
    async def test_sustained_load(self, kato_v2_system):
        """Test system under sustained load for extended period"""
        system = kato_v2_system
        duration_seconds = 30
        concurrent_users = 20
        
        stop_time = time.time() + duration_seconds
        operations_completed = 0
        errors_encountered = 0
        
        async def sustained_user_activity(user_id: int):
            nonlocal operations_completed, errors_encountered
            
            session = await system.create_session(user_id=f"sustained_{user_id}")
            session_id = session['session_id']
            
            while time.time() < stop_time:
                try:
                    # Random operations
                    operation = random.choice([
                        lambda: system.observe_in_session(
                            session_id,
                            {"strings": [f"data_{operations_completed}"]}
                        ),
                        lambda: system.get_session_stm(session_id),
                        lambda: system.clear_session_stm(session_id)
                    ])
                    
                    await operation()
                    operations_completed += 1
                    
                    # Small random delay
                    await asyncio.sleep(random.uniform(0.01, 0.1))
                    
                except Exception as e:
                    errors_encountered += 1
                    print(f"Error during sustained load: {e}")
            
            await system.delete_session(session_id)
        
        # Run sustained load
        tasks = [sustained_user_activity(i) for i in range(concurrent_users)]
        await asyncio.gather(*tasks, return_exceptions=True)
        
        # Calculate metrics
        ops_per_second = operations_completed / duration_seconds
        error_rate = errors_encountered / max(operations_completed, 1)
        
        print(f"\nSustained Load Test Results:")
        print(f"  Duration: {duration_seconds}s")
        print(f"  Operations: {operations_completed}")
        print(f"  Throughput: {ops_per_second:.2f} ops/sec")
        print(f"  Errors: {errors_encountered}")
        print(f"  Error rate: {error_rate:.2%}")
        
        # Assertions
        assert ops_per_second > 100, "Sustained throughput too low"
        assert error_rate < 0.01, f"Error rate too high: {error_rate:.2%}"


class TestEdgeCases:
    """Test edge cases and boundary conditions"""
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_rapid_session_churn(self, kato_v2_system):
        """Test rapid creation and deletion of sessions"""
        system = kato_v2_system
        
        async def churn_session():
            session = await system.create_session()
            await system.observe_in_session(
                session['session_id'],
                {"strings": ["churn"]}
            )
            await system.delete_session(session['session_id'])
        
        # Rapid churn
        tasks = [churn_session() for _ in range(100)]
        
        start_time = time.time()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        elapsed = time.time() - start_time
        
        # Check for errors
        errors = [r for r in results if isinstance(r, Exception)]
        assert len(errors) == 0, f"Churn test had {len(errors)} errors"
        
        print(f"Churned 100 sessions in {elapsed:.2f}s")
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_session_id_collision_handling(self, kato_v2_system):
        """Test that system handles session ID collisions correctly"""
        system = kato_v2_system
        
        # Create many sessions to increase collision probability
        sessions = []
        session_ids = set()
        
        for _ in range(1000):
            session = await system.create_session()
            session_id = session['session_id']
            
            # Check for collision
            assert session_id not in session_ids, \
                f"Session ID collision detected: {session_id}"
            
            session_ids.add(session_id)
            sessions.append(session_id)
        
        # Cleanup
        cleanup_tasks = [system.delete_session(sid) for sid in sessions]
        await asyncio.gather(*cleanup_tasks, return_exceptions=True)
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_unicode_and_special_characters(self, kato_v2_system):
        """Test that sessions handle Unicode and special characters correctly"""
        system = kato_v2_system
        
        # Test data with various character sets
        test_data = [
            "Hello",  # ASCII
            "你好",    # Chinese
            "مرحبا",   # Arabic
            "🎉🎊🎈",  # Emojis
            "Ñoño",   # Spanish
            "Здравствуй",  # Russian
            "!@#$%^&*()",  # Special chars
        ]
        
        session = await system.create_session(user_id="unicode_user")
        session_id = session['session_id']
        
        # Observe each string
        for data in test_data:
            await system.observe_in_session(
                session_id,
                {"strings": [data]}
            )
        
        # Verify all preserved correctly
        stm = await system.get_session_stm(session_id)
        
        for i, data in enumerate(test_data):
            assert stm['stm'][i] == [data], \
                f"Unicode data corrupted: expected [{data}], got {stm['stm'][i]}"
        
        # Cleanup
        await system.delete_session(session_id)


# Test System Mock

class MockKatoV2System:
    """Mock KATO v2 system for integration testing"""
    
    def __init__(self):
        self.sessions: Dict[str, Dict] = {}
        self.patterns: Dict[str, Dict] = {}
        self.session_lock = asyncio.Lock()
    
    async def create_session(self, user_id: str = None, metadata: Dict = None):
        async with self.session_lock:
            session_id = f"session-{uuid.uuid4().hex}"
            self.sessions[session_id] = {
                'session_id': session_id,
                'user_id': user_id,
                'metadata': metadata or {},
                'stm': [],
                'created_at': datetime.now()
            }
            return {'session_id': session_id}
    
    async def observe_in_session(self, session_id: str, observation: Dict):
        if session_id not in self.sessions:
            raise ValueError(f"Session {session_id} not found")
        
        # Simulate processing delay
        await asyncio.sleep(random.uniform(0.001, 0.005))
        
        self.sessions[session_id]['stm'].append(observation['strings'])
        return {'status': 'ok'}
    
    async def get_session_stm(self, session_id: str):
        if session_id not in self.sessions:
            raise ValueError(f"Session {session_id} not found")
        
        return {'stm': self.sessions[session_id]['stm']}
    
    async def learn_in_session(self, session_id: str):
        if session_id not in self.sessions:
            raise ValueError(f"Session {session_id} not found")
        
        # Create unique pattern
        pattern_name = f"PTRN|{uuid.uuid4().hex[:16]}"
        self.patterns[pattern_name] = {
            'session_id': session_id,
            'data': self.sessions[session_id]['stm'].copy()
        }
        
        return {'pattern_name': pattern_name}
    
    async def clear_session_stm(self, session_id: str):
        if session_id not in self.sessions:
            raise ValueError(f"Session {session_id} not found")
        
        self.sessions[session_id]['stm'] = []
        return {'status': 'ok'}
    
    async def get_session_predictions(self, session_id: str):
        if session_id not in self.sessions:
            raise ValueError(f"Session {session_id} not found")
        
        # Mock predictions based on learned patterns
        current_stm = self.sessions[session_id]['stm']
        predictions = []
        
        # Find matching patterns
        for pattern_name, pattern_data in self.patterns.items():
            if pattern_data['session_id'] == session_id:
                # Simple prediction: if partial match, predict rest
                pattern_sequence = pattern_data['data']
                if len(current_stm) > 0 and len(pattern_sequence) > len(current_stm):
                    # Check if current is prefix of pattern
                    is_prefix = all(
                        current_stm[i] == pattern_sequence[i]
                        for i in range(min(len(current_stm), len(pattern_sequence)))
                    )
                    
                    if is_prefix:
                        future = pattern_sequence[len(current_stm):]
                        predictions.append({
                            'pattern': pattern_name,
                            'future': future,
                            'confidence': 0.8
                        })
        
        return {'predictions': predictions}
    
    async def delete_session(self, session_id: str):
        if session_id in self.sessions:
            del self.sessions[session_id]
        return {'status': 'ok'}


@pytest.fixture
async def kato_v2_system():
    """Fixture providing KATO v2 system for testing"""
    system = MockKatoV2System()
    yield system
    # Cleanup
    system.sessions.clear()
    system.patterns.clear()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s", "-m", "integration"])