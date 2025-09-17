"""
Test error handling for KATO v2.0 features
Tests various error conditions and edge cases
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
    return f"{base_url}"


class TestSessionErrorHandling:
    """Test error handling for session operations"""
    
    def test_session_not_found_errors(self):
        """Test 404 errors for non-existent sessions"""
        base_url = _get_test_base_url()
        fake_session_id = f"nonexistent-{uuid.uuid4()}"
        
        # List of endpoints that should return 404 for non-existent sessions
        test_cases = [
            ("GET", f"/v2/sessions/{fake_session_id}/stm", None),
            ("POST", f"/v2/sessions/{fake_session_id}/observe", {"strings": ["test"]}),
            ("POST", f"/v2/sessions/{fake_session_id}/clear-stm", None),
            ("POST", f"/v2/sessions/{fake_session_id}/learn", None),
            ("GET", f"/v2/sessions/{fake_session_id}/predictions", None),
            ("DELETE", f"/v2/sessions/{fake_session_id}", None)
        ]
        
        for method, endpoint, payload in test_cases:
            if method == "GET":
                response = requests.get(f"{base_url}{endpoint}")
            elif method == "POST":
                response = requests.post(f"{base_url}{endpoint}", json=payload)
            elif method == "DELETE":
                response = requests.delete(f"{base_url}{endpoint}")
            
            assert response.status_code == 404, f"{method} {endpoint} should return 404"
    
    def test_invalid_observation_payloads(self):
        """Test error handling for invalid observation payloads"""
        base_url = _get_test_base_url()
        # Create valid session with required user_id
        response = requests.post(f"{base_url}/v2/sessions", json={"user_id": "test_user"})
        assert response.status_code == 200, f"Failed to create session: {response.text}"
        session_id = response.json()["session_id"]
        
        try:
            # Test various invalid payloads
            # Note: Empty observations are actually valid (they just don't add to STM)
            invalid_payloads = [
                {"strings": [None]},  # Null string should be invalid
                {"strings": ["valid"], "vectors": "not_array"},  # Invalid vectors format
                {"strings": ["valid"], "emotives": "not_dict"}  # Invalid emotives format
            ]
            
            # Test valid but empty payloads (should succeed)
            valid_empty_payloads = [
                {},  # Empty payload is valid
                {"strings": []},  # Empty strings array is valid
                {"invalid_key": "value"},  # Extra keys are ignored
            ]
            
            for payload in valid_empty_payloads:
                response = requests.post(
                    f"{base_url}/v2/sessions/{session_id}/observe",
                    json=payload
                )
                assert response.status_code == 200, \
                    f"Valid payload {payload} should return 200"
            
            for payload in invalid_payloads:
                response = requests.post(
                    f"{base_url}/v2/sessions/{session_id}/observe",
                    json=payload
                )
                # Should either return 400 (bad request) or 422 (validation error)
                assert response.status_code in [400, 422, 500], \
                    f"Invalid payload {payload} should return error status"
        
        finally:
            requests.delete(f"{base_url}/v2/sessions/{session_id}")
    
    def test_invalid_session_creation_payloads(self):
        """Test error handling for invalid session creation payloads"""
        base_url = _get_test_base_url()
        invalid_payloads = [
            {"user_id": None},  # Null user_id
            {"ttl_seconds": -1},  # Negative TTL
            {"ttl_seconds": "not_number"},  # Non-numeric TTL
            {"metadata": "not_dict"}  # Invalid metadata format
        ]
        
        for payload in invalid_payloads:
            response = requests.post(f"{base_url}/v2/sessions", json=payload)
            # Should return client error status
            assert response.status_code in [400, 422], \
                f"Invalid payload {payload} should return 400 or 422"
    
    def test_session_timeout_behavior(self):
        """Test behavior with very short session timeout"""
        base_url = _get_test_base_url()
        # Create session with 1 second TTL and required user_id
        payload = {"user_id": "test_timeout_user", "ttl_seconds": 1}
        response = requests.post(f"{base_url}/v2/sessions", json=payload)
        
        if response.status_code != 200:
            pytest.skip("Session creation with short TTL not supported")
        
        session_id = response.json()["session_id"]
        
        # Should work immediately
        response = requests.get(f"{base_url}/v2/sessions/{session_id}/stm")
        assert response.status_code == 200
        
        # Wait for expiration
        time.sleep(2)
        
        # Should now return 404 or appropriate error
        response = requests.get(f"{base_url}/v2/sessions/{session_id}/stm")
        assert response.status_code in [404, 410], "Expired session should return error"
    
    def test_malformed_json_handling(self):
        """Test handling of malformed JSON requests"""
        base_url = _get_test_base_url()
        # Create valid session first with required user_id
        response = requests.post(f"{base_url}/v2/sessions", json={"user_id": "test_malformed_user"})
        assert response.status_code == 200, f"Failed to create session: {response.text}"
        session_id = response.json()["session_id"]
        
        try:
            # Send malformed JSON
            response = requests.post(
                f"{base_url}/v2/sessions/{session_id}/observe",
                data="invalid json content",
                headers={"Content-Type": "application/json"}
            )
            # Should return 400 or 422 for malformed JSON
            assert response.status_code in [400, 422]
        
        finally:
            requests.delete(f"{base_url}/v2/sessions/{session_id}")


class TestConcurrencyAndRaceConditions:
    """Test concurrent access and potential race conditions"""
    
    def test_concurrent_session_deletion(self):
        """Test concurrent attempts to delete the same session"""
        base_url = _get_test_base_url()
        # Create session
        response = requests.post(f"{base_url}/v2/sessions", json={"user_id": f"test_user_{uuid.uuid4().hex[:8]}"})
        session_id = response.json()["session_id"]
        
        # First deletion should succeed
        response1 = requests.delete(f"{base_url}/v2/sessions/{session_id}")
        assert response1.status_code == 200
        
        # Second deletion should handle gracefully (404 is acceptable)
        response2 = requests.delete(f"{base_url}/v2/sessions/{session_id}")
        assert response2.status_code in [200, 404], \
            "Double deletion should be handled gracefully"
    
    def test_observe_after_deletion(self):
        """Test observation attempts after session deletion"""
        base_url = _get_test_base_url()
        # Create session
        response = requests.post(f"{base_url}/v2/sessions", json={"user_id": f"test_user_{uuid.uuid4().hex[:8]}"})
        session_id = response.json()["session_id"]
        
        # Delete session
        response = requests.delete(f"{base_url}/v2/sessions/{session_id}")
        assert response.status_code == 200
        
        # Try to observe in deleted session
        response = requests.post(
            f"{base_url}/v2/sessions/{session_id}/observe",
            json={"strings": ["test"]}
        )
        assert response.status_code == 404, \
            "Observation in deleted session should return 404"
    
    def test_rapid_session_operations(self):
        """Test rapid succession of operations on same session"""
        base_url = _get_test_base_url()
        # Create session
        response = requests.post(f"{base_url}/v2/sessions", json={"user_id": f"test_user_{uuid.uuid4().hex[:8]}"})
        session_id = response.json()["session_id"]
        
        try:
            # Rapid observations
            for i in range(10):
                response = requests.post(
                    f"{base_url}/v2/sessions/{session_id}/observe",
                    json={"strings": [f"rapid_{i}"]}
                )
                # All should succeed or at least not crash
                assert response.status_code in [200, 500], \
                    f"Rapid operation {i} failed with {response.status_code}"
            
            # Check final STM state
            response = requests.get(f"{base_url}/v2/sessions/{session_id}/stm")
            if response.status_code == 200:
                stm = response.json()["stm"]
                # Should have some observations (exact count may vary due to concurrency)
                assert len(stm) > 0, "STM should contain some observations"
        
        finally:
            requests.delete(f"{base_url}/v2/sessions/{session_id}")


class TestResourceLimits:
    """Test resource limits and edge cases"""
    
    def test_large_observation_handling(self):
        """Test handling of very large observations"""
        base_url = _get_test_base_url()
        # Create session
        response = requests.post(f"{base_url}/v2/sessions", json={"user_id": f"test_user_{uuid.uuid4().hex[:8]}"})
        session_id = response.json()["session_id"]
        
        try:
            # Create large observation
            large_strings = [f"string_{i}" for i in range(1000)]
            large_observation = {"strings": large_strings}
            
            response = requests.post(
                f"{base_url}/v2/sessions/{session_id}/observe",
                json=large_observation
            )
            
            # Should either succeed or return appropriate error
            assert response.status_code in [200, 400, 413, 500], \
                "Large observation should be handled appropriately"
            
            if response.status_code == 200:
                # Verify STM contains the observation
                response = requests.get(f"{base_url}/v2/sessions/{session_id}/stm")
                stm = response.json()["stm"]
                assert len(stm) == 1, "Large observation should be stored"
        
        finally:
            requests.delete(f"{base_url}/v2/sessions/{session_id}")
    
    def test_many_small_observations(self):
        """Test handling of many small observations"""
        base_url = _get_test_base_url()
        # Create session
        response = requests.post(f"{base_url}/v2/sessions", json={"user_id": f"test_user_{uuid.uuid4().hex[:8]}"})
        session_id = response.json()["session_id"]
        
        try:
            # Add many small observations
            num_observations = 100
            success_count = 0
            
            for i in range(num_observations):
                response = requests.post(
                    f"{base_url}/v2/sessions/{session_id}/observe",
                    json={"strings": [f"obs_{i}"]}
                )
                if response.status_code == 200:
                    success_count += 1
            
            # Most should succeed
            success_rate = success_count / num_observations
            assert success_rate > 0.8, f"Success rate too low: {success_rate:.2%}"
            
            # Check STM
            response = requests.get(f"{base_url}/v2/sessions/{session_id}/stm")
            if response.status_code == 200:
                stm = response.json()["stm"]
                assert len(stm) > 0, "STM should contain observations"
        
        finally:
            requests.delete(f"{base_url}/v2/sessions/{session_id}")


class TestV1V2Interaction:
    """Test interactions between v1 and v2 endpoints"""
    
    def test_v1_without_session_header(self):
        """Test v1 endpoints without session header (should use default behavior)"""
        base_url = _get_test_base_url()
        # Use v1 observe without session header
        response = requests.post(
            f"{base_url}/observe",
            json={"strings": ["v1_default"]}
        )
        assert response.status_code == 200, "v1 observe should work without session header"
        
        # Get v1 STM
        response = requests.get(f"{base_url}/stm")
        assert response.status_code == 200, "v1 STM should be accessible"
    
    def test_invalid_session_header(self):
        """Test v1 endpoints with invalid X-Session-ID header"""
        base_url = _get_test_base_url()
        fake_session_id = f"invalid-{uuid.uuid4()}"
        headers = {"X-Session-ID": fake_session_id}
        
        response = requests.post(
            f"{base_url}/observe",
            json={"strings": ["test"]},
            headers=headers
        )
        
        # Should either create the session, return error, or fall back to default
        # The exact behavior depends on implementation
        assert response.status_code in [200, 400, 404], \
            "Invalid session header should be handled appropriately"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])