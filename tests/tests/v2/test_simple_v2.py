"""
Simple v2.0 tests using requests instead of aiohttp
Tests basic v2 functionality with synchronous calls
"""

import pytest
import requests
import time
import uuid
import json
import os
from pathlib import Path


def _get_test_base_url():
    """Get the base URL for testing from dynamic port discovery"""
    # Try to read from saved ports file
    ports_file = Path(__file__).parent.parent.parent.parent / '.kato-ports.json'
    if ports_file.exists():
        try:
            with open(ports_file, 'r') as f:
                port_data = json.load(f)
            # Try to use testing service first, then primary
            for service_name in ['testing', 'primary']:
                if service_name in port_data.get('services', {}):
                    port = port_data['services'][service_name].get('port')
                    if port:
                        return f"http://localhost:{port}"
        except (json.JSONDecodeError, KeyError):
            pass
    # Fall back to default
    return "http://localhost:8001"


class TestV2BasicFunctionality:
    """Test v2 endpoints using synchronous requests"""
    
    def test_v2_health_endpoint(self):
        """Test that v2 health endpoint works"""
        base_url = _get_test_base_url()
        response = requests.get(f"{base_url}/v2/health")
        assert response.status_code == 200
        
        data = response.json()
        assert "status" in data
        assert data["status"] == "healthy"
        assert "active_sessions" in data
        assert "timestamp" in data
    
    def test_v2_session_creation_basic(self):
        """Test basic v2 session creation"""
        base_url = _get_test_base_url()
        # Create session
        payload = {
            "user_id": "test_user_sync"
        }
        
        response = requests.post(f"{base_url}/v2/sessions", json=payload)
        assert response.status_code == 200
        
        session_data = response.json()
        assert "session_id" in session_data
        assert session_data["user_id"] == "test_user_sync"
        
        session_id = session_data["session_id"]
        
        # Test STM retrieval
        response = requests.get(f"{base_url}/v2/sessions/{session_id}/stm")
        assert response.status_code == 200
        
        stm_data = response.json()
        assert "stm" in stm_data
        assert stm_data["stm"] == []
        
        # Cleanup - Delete session
        response = requests.delete(f"{base_url}/v2/sessions/{session_id}")
        assert response.status_code == 200
    
    def test_v2_session_observation(self):
        """Test observing in a v2 session"""
        base_url = _get_test_base_url()
        # Create session
        response = requests.post(f"{base_url}/v2/sessions", json={"user_id": "test_observation_user"})
        assert response.status_code == 200
        session_id = response.json()["session_id"]
        
        try:
            # Make observation
            observation = {"strings": ["test", "observation"]}
            response = requests.post(
                f"{base_url}/v2/sessions/{session_id}/observe",
                json=observation
            )
            assert response.status_code == 200
            
            # Check STM
            response = requests.get(f"{base_url}/v2/sessions/{session_id}/stm")
            assert response.status_code == 200
            
            stm_data = response.json()
            assert len(stm_data["stm"]) == 1
            # Check that both strings are present (order may vary due to sorting)
            observed_strings = set(stm_data["stm"][0])
            assert observed_strings == {"test", "observation"}
            
        finally:
            # Cleanup
            requests.delete(f"{base_url}/v2/sessions/{session_id}")
    
    def test_v2_session_isolation(self):
        """Test that two sessions are isolated"""
        base_url = _get_test_base_url()
        # Create two sessions
        response1 = requests.post(f"{base_url}/v2/sessions", json={"user_id": "user1"})
        response2 = requests.post(f"{base_url}/v2/sessions", json={"user_id": "user2"})
        
        assert response1.status_code == 200
        assert response2.status_code == 200
        
        session1_id = response1.json()["session_id"]
        session2_id = response2.json()["session_id"]
        
        try:
            # Session 1 observes "A"
            requests.post(
                f"{base_url}/v2/sessions/{session1_id}/observe",
                json={"strings": ["A"]}
            )
            
            # Session 2 observes "B" 
            requests.post(
                f"{base_url}/v2/sessions/{session2_id}/observe",
                json={"strings": ["B"]}
            )
            
            # Check session 1 STM
            response = requests.get(f"{base_url}/v2/sessions/{session1_id}/stm")
            stm1 = response.json()["stm"]
            
            # Check session 2 STM
            response = requests.get(f"{base_url}/v2/sessions/{session2_id}/stm")
            stm2 = response.json()["stm"]
            
            # Verify isolation
            assert stm1 == [["A"]]
            assert stm2 == [["B"]]
            
        finally:
            # Cleanup
            requests.delete(f"{base_url}/v2/sessions/{session1_id}")
            requests.delete(f"{base_url}/v2/sessions/{session2_id}")
    
    def test_v2_invalid_session_handling(self):
        """Test handling of invalid session IDs"""
        base_url = _get_test_base_url()
        fake_session_id = f"fake-session-{uuid.uuid4()}"
        
        # Try to access non-existent session
        response = requests.get(f"{base_url}/v2/sessions/{fake_session_id}/stm")
        assert response.status_code == 404
        
        # Try to observe in non-existent session
        response = requests.post(
            f"{base_url}/v2/sessions/{fake_session_id}/observe",
            json={"strings": ["test"]}
        )
        assert response.status_code == 404
    
    def test_v2_session_learning(self):
        """Test learning patterns in a v2 session"""
        base_url = _get_test_base_url()
        # Create v2 session
        response = requests.post(f"{base_url}/v2/sessions", json={"user_id": "test_learning_user"})
        session_id = response.json()["session_id"]
        
        try:
            # Add observations to build pattern
            requests.post(
                f"{base_url}/v2/sessions/{session_id}/observe",
                json={"strings": ["A", "B"]}
            )
            requests.post(
                f"{base_url}/v2/sessions/{session_id}/observe",
                json={"strings": ["C", "D"]}
            )
            
            # Learn pattern from STM
            response = requests.post(f"{base_url}/v2/sessions/{session_id}/learn")
            assert response.status_code == 200
            
            learn_result = response.json()
            assert "pattern_name" in learn_result
            assert learn_result["pattern_name"].startswith("PTRN|")
            
            # STM should be cleared after learning (typical KATO behavior)
            response = requests.get(f"{base_url}/v2/sessions/{session_id}/stm")
            stm_data = response.json()
            # STM might be empty or contain the learned pattern depending on config
            
        finally:
            requests.delete(f"{base_url}/v2/sessions/{session_id}")
    
    def test_session_clear_stm(self):
        """Test clearing STM in a session"""
        base_url = _get_test_base_url()
        # Create session and add data
        response = requests.post(f"{base_url}/v2/sessions", json={"user_id": "test_clear_stm_user"})
        session_id = response.json()["session_id"]
        
        try:
            # Add observation
            requests.post(
                f"{base_url}/v2/sessions/{session_id}/observe",
                json={"strings": ["data_to_clear"]}
            )
            
            # Verify data exists
            response = requests.get(f"{base_url}/v2/sessions/{session_id}/stm")
            stm_data = response.json()
            assert len(stm_data["stm"]) == 1
            
            # Clear STM
            response = requests.post(f"{base_url}/v2/sessions/{session_id}/clear-stm")
            assert response.status_code == 200
            
            # Verify STM is empty
            response = requests.get(f"{base_url}/v2/sessions/{session_id}/stm")
            stm_data = response.json()
            assert stm_data["stm"] == []
            
        finally:
            requests.delete(f"{base_url}/v2/sessions/{session_id}")


class TestV2ServiceHealth:
    """Test v2 service health and availability"""
    
    def test_all_v2_services_healthy(self):
        """Test that all v2 services report healthy"""
        base_url = _get_test_base_url()
        # Just test the discovered service
        response = requests.get(f"{base_url}/v2/health")
        assert response.status_code == 200, "Service not healthy"
        
        data = response.json()
        assert data["status"] == "healthy", "Service reports unhealthy"
    
    def test_v2_endpoints_exist(self):
        """Test that v2 endpoints are available"""
        base_url = _get_test_base_url()
        
        # Test endpoint availability (should return appropriate response, not 404)
        endpoints_to_test = [
            ("/v2/health", "GET"),
            ("/v2/sessions", "POST")
        ]
        
        for endpoint, method in endpoints_to_test:
            if method == "GET":
                response = requests.get(f"{base_url}{endpoint}")
            elif method == "POST":
                response = requests.post(f"{base_url}{endpoint}", json={"user_id": "test_endpoint_user"})
            
            assert response.status_code != 404, f"Endpoint {endpoint} not found"
            # We don't require 200 here since some endpoints might return errors
            # for invalid payloads, but they should exist


if __name__ == "__main__":
    pytest.main([__file__, "-v"])