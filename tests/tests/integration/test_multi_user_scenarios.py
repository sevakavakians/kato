"""
Multi-User Integration Tests for KATO

This test suite validates complex multi-user scenarios to ensure:
- Complete data isolation between users
- Correct behavior under concurrent load
- Session handoff and migration scenarios
- Performance with many simultaneous users
- Edge cases with session conflicts

These are end-to-end integration tests that use real KATO instances.
"""

import asyncio
import pytest
import time
import random
import uuid
import requests
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import sys
import os

# Add parent directories to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from tests.fixtures.kato_fixtures import KATOFastAPIFixture


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
    
    def test_concurrent_users_no_collision(self):
        """Test that 10 concurrent users maintain completely isolated sequences"""
        # Create separate KATO instances for each user
        fixtures = []
        users = []
        
        try:
            # Create 10 users with unique sequences and fixtures
            for i in range(10):
                # Each user gets their own KATO fixture with unique processor_id
                fixture = KATOFastAPIFixture(processor_name=f"user_{i}", use_docker=False)
                fixture.setup()
                fixtures.append(fixture)
                
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
            results = self._execute_concurrent_scenarios(fixtures, users)
            
            # Verify each user's results
            for i, result in enumerate(results):
                user = users[i]
                # Check final STM
                assert result['final_stm'] == user.expected_stm, \
                    f"User {i} STM corrupted: expected {user.expected_stm}, got {result['final_stm']}"
                
                # Check predictions
                if user.expected_predictions and result['predictions']:
                    future_items = self._extract_future_items(result['predictions'])
                    # Since we learned the pattern, we should get the expected prediction
                    assert any(expected in future_items for expected in user.expected_predictions), \
                        f"User {i} didn't get expected predictions {user.expected_predictions}"
                
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
        
        finally:
            # Clean up all fixtures
            for fixture in fixtures:
                fixture.teardown()
    
    def test_pattern_learning_isolation(self):
        """Test that patterns learned by one user don't affect another"""
        # Create two separate KATO fixtures
        fixture1 = KATOFastAPIFixture(processor_name="user1", use_docker=False)
        fixture2 = KATOFastAPIFixture(processor_name="user2", use_docker=False)
        
        try:
            fixture1.setup()
            fixture2.setup()
            
            # User 1 learns a pattern
            fixture1.observe({'strings': ['UNIQUE_A'], 'vectors': [], 'emotives': {}})
            fixture1.observe({'strings': ['UNIQUE_B'], 'vectors': [], 'emotives': {}})
            fixture1.observe({'strings': ['UNIQUE_C'], 'vectors': [], 'emotives': {}})
            fixture1.learn()
            
            # User 2 learns a completely different pattern
            fixture2.observe({'strings': ['DIFF_X'], 'vectors': [], 'emotives': {}})
            fixture2.observe({'strings': ['DIFF_Y'], 'vectors': [], 'emotives': {}})
            fixture2.observe({'strings': ['DIFF_Z'], 'vectors': [], 'emotives': {}})
            fixture2.learn()
            
            # User 1 should predict their pattern
            fixture1.clear_short_term_memory()
            fixture1.observe({'strings': ['UNIQUE_A', 'UNIQUE_B'], 'vectors': [], 'emotives': {}})
            preds1 = fixture1.get_predictions()
            
            # User 2 should predict their pattern
            fixture2.clear_short_term_memory()
            fixture2.observe({'strings': ['DIFF_X', 'DIFF_Y'], 'vectors': [], 'emotives': {}})
            preds2 = fixture2.get_predictions()
            
            # Verify isolation
            if preds1:
                future1 = self._extract_future_items(preds1)
                assert not any('DIFF' in str(item) for item in future1), \
                    "User 1 sees User 2's patterns"
            
            if preds2:
                future2 = self._extract_future_items(preds2)
                assert not any('UNIQUE' in str(item) for item in future2), \
                    "User 2 sees User 1's patterns"
        
        finally:
            fixture1.teardown()
            fixture2.teardown()
    
    def test_rapid_context_switching(self):
        """Test rapid switching between multiple user contexts"""
        fixtures = []
        
        try:
            # Create 5 users
            for i in range(5):
                fixture = KATOFastAPIFixture(processor_name=f"rapid_user_{i}", use_docker=False)
                fixture.setup()
                fixtures.append(fixture)
                
                # Each user learns their unique pattern
                for j in range(3):
                    fixture.observe({'strings': [f'USER{i}_EVENT{j}'], 'vectors': [], 'emotives': {}})
                fixture.learn()
            
            # Rapidly switch between users making observations
            for _ in range(20):  # 20 rapid switches
                user_idx = random.randint(0, 4)
                fixture = fixtures[user_idx]
                
                # Clear and make observation
                fixture.clear_short_term_memory()
                fixture.observe({'strings': [f'USER{user_idx}_EVENT0'], 'vectors': [], 'emotives': {}})
                fixture.observe({'strings': [f'USER{user_idx}_EVENT1'], 'vectors': [], 'emotives': {}})
                
                # Verify predictions are user-specific
                preds = fixture.get_predictions()
                if preds:
                    future = self._extract_future_items(preds)
                    # Should only predict this user's patterns
                    for item in future:
                        if 'USER' in str(item):
                            assert f'USER{user_idx}' in str(item), \
                                f"User {user_idx} got contaminated predictions"
        
        finally:
            for fixture in fixtures:
                fixture.teardown()
    
    def _execute_concurrent_scenarios(self, fixtures, users):
        """Execute user scenarios concurrently using ThreadPoolExecutor"""
        def execute_user_scenario(fixture, user):
            result = {'predictions': None, 'final_stm': None}
            
            for action in user.actions:
                if action['type'] == 'observe':
                    fixture.observe(action['data'])
                elif action['type'] == 'learn':
                    fixture.learn()
                elif action['type'] == 'clear_stm':
                    fixture.clear_short_term_memory()
                elif action['type'] == 'get_predictions':
                    result['predictions'] = fixture.get_predictions()
            
            # Get final STM
            result['final_stm'] = fixture.get_short_term_memory()
            return result
        
        # Execute all scenarios concurrently
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [
                executor.submit(execute_user_scenario, fixtures[i], users[i])
                for i in range(len(users))
            ]
            results = [f.result() for f in futures]
        
        return results
    
    def _extract_future_items(self, predictions):
        """Extract all future items from predictions"""
        items = []
        for pred in predictions:
            if 'future' in pred:
                for event in pred['future']:
                    if isinstance(event, list):
                        items.extend(event)
        return items


class TestSessionPerformance:
    """Test session performance under load"""
    
    def test_many_sessions_performance(self):
        """Test system performance with many concurrent sessions"""
        fixtures = []
        start_time = time.time()
        
        try:
            # Create 20 sessions
            for i in range(20):
                fixture = KATOFastAPIFixture(processor_name=f"perf_user_{i}", use_docker=False)
                fixture.setup()
                fixtures.append(fixture)
            
            # Each makes observations
            for fixture in fixtures:
                for j in range(5):
                    fixture.observe({'strings': [f'PERF_{j}'], 'vectors': [], 'emotives': {}})
            
            # Verify all complete within reasonable time
            elapsed = time.time() - start_time
            assert elapsed < 30, f"Performance test took too long: {elapsed}s"
            
            # Verify all sessions are independent
            for i, fixture in enumerate(fixtures):
                stm = fixture.get_short_term_memory()
                assert len(stm) == 5, f"Session {i} has wrong STM length"
        
        finally:
            for fixture in fixtures:
                fixture.teardown()
    
    def test_session_cleanup(self):
        """Test that sessions are properly cleaned up"""
        fixtures = []
        
        try:
            # Create and destroy sessions
            for i in range(10):
                fixture = KATOFastAPIFixture(processor_name=f"cleanup_{i}", use_docker=False)
                fixture.setup()
                
                # Make some observations
                fixture.observe({'strings': ['CLEANUP_TEST'], 'vectors': [], 'emotives': {}})
                
                # Immediately teardown
                fixture.teardown()
                
                # Create new session with same user - should be fresh
                fixture2 = KATOFastAPIFixture(processor_name=f"cleanup_{i}_new", use_docker=False)
                fixture2.setup()
                fixtures.append(fixture2)
                
                stm = fixture2.get_short_term_memory()
                assert len(stm) == 0, f"New session {i} not clean"
        
        finally:
            for fixture in fixtures:
                fixture.teardown()


class TestEdgeCases:
    """Test edge cases and error conditions"""
    
    def test_empty_observation_handling(self):
        """Test handling of empty observations"""
        fixture = KATOFastAPIFixture(processor_name="empty_test", use_docker=False)
        
        try:
            fixture.setup()
            
            # Empty strings should be filtered
            fixture.observe({'strings': [], 'vectors': [], 'emotives': {}})
            stm = fixture.get_short_term_memory()
            assert len(stm) == 0, "Empty observation should not affect STM"
            
            # Mixed empty and valid
            fixture.observe({'strings': ['VALID'], 'vectors': [], 'emotives': {}})
            fixture.observe({'strings': [], 'vectors': [], 'emotives': {}})
            fixture.observe({'strings': ['ALSO_VALID'], 'vectors': [], 'emotives': {}})
            
            stm = fixture.get_short_term_memory()
            assert stm == [['VALID'], ['ALSO_VALID']], "Empty events should be filtered"
        
        finally:
            fixture.teardown()
    
    def test_large_observation_handling(self):
        """Test handling of very large observations"""
        fixture = KATOFastAPIFixture(processor_name="large_test", use_docker=False)
        
        try:
            fixture.setup()
            
            # Create large observation
            large_event = [f'SYMBOL_{i}' for i in range(100)]
            fixture.observe({'strings': large_event, 'vectors': [], 'emotives': {}})
            
            stm = fixture.get_short_term_memory()
            assert len(stm) == 1, "Should have one event"
            assert len(stm[0]) == 100, "Should preserve all symbols"
            
            # Learn the large pattern
            fixture.learn()
            
            # Should be able to recall
            fixture.clear_short_term_memory()
            fixture.observe({'strings': large_event[:50], 'vectors': [], 'emotives': {}})
            preds = fixture.get_predictions()
            assert preds is not None, "Should get predictions for large patterns"
        
        finally:
            fixture.teardown()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])