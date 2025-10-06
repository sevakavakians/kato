"""
Tests for Auto-Session Middleware

Tests the automatic session creation middleware that provides
backward compatibility for deprecated direct endpoints.

Phase 2 of API Endpoint Deprecation project.
"""

import os
import time
import uuid

import pytest
import requests

# Test configuration
BASE_URL = os.environ.get('KATO_BASE_URL', 'http://localhost:8000')


class TestAutoSessionMiddleware:
    """Test suite for Auto-Session Middleware functionality"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup for each test"""
        self.base_url = BASE_URL
        self.processor_id = f"test_auto_session_{uuid.uuid4().hex[:8]}"

    def test_auto_session_observe_endpoint(self):
        """Test auto-session creation for /observe endpoint"""
        # Call deprecated endpoint with processor_id
        response = requests.post(
            f"{self.base_url}/observe",
            json={"strings": ["test", "auto"], "vectors": [], "emotives": {}},
            params={"processor_id": self.processor_id}
        )

        assert response.status_code == 200
        data = response.json()

        # Verify response contains expected fields
        assert data['status'] == 'okay'
        assert 'stm_length' in data

        # Verify auto-session headers
        assert response.headers.get('X-Auto-Session-Used') == 'true'
        assert 'X-Session-ID' in response.headers

        session_id = response.headers['X-Session-ID']
        assert session_id is not None
        assert session_id.startswith('session-')

    def test_auto_session_stm_endpoint(self):
        """Test auto-session creation for /stm endpoint"""
        # First observe something
        requests.post(
            f"{self.base_url}/observe",
            json={"strings": ["A", "B"], "vectors": [], "emotives": {}},
            params={"processor_id": self.processor_id}
        )

        # Get STM via deprecated endpoint
        response = requests.get(
            f"{self.base_url}/stm",
            params={"processor_id": self.processor_id}
        )

        assert response.status_code == 200
        data = response.json()

        # Verify STM data
        assert 'stm' in data
        assert len(data['stm']) > 0

        # Verify auto-session headers
        assert response.headers.get('X-Auto-Session-Used') == 'true'
        assert 'X-Session-ID' in response.headers

    def test_auto_session_learn_endpoint(self):
        """Test auto-session creation for /learn endpoint"""
        # First observe a sequence
        requests.post(
            f"{self.base_url}/observe",
            json={"strings": ["A"], "vectors": [], "emotives": {}},
            params={"processor_id": self.processor_id}
        )
        requests.post(
            f"{self.base_url}/observe",
            json={"strings": ["B"], "vectors": [], "emotives": {}},
            params={"processor_id": self.processor_id}
        )

        # Learn via deprecated endpoint
        response = requests.post(
            f"{self.base_url}/learn",
            params={"processor_id": self.processor_id}
        )

        assert response.status_code == 200
        data = response.json()

        # Verify learn result
        assert data['status'] == 'learned'
        assert 'pattern_name' in data
        assert data['pattern_name'].startswith('PTRN|')

        # Verify auto-session headers
        assert response.headers.get('X-Auto-Session-Used') == 'true'
        assert 'X-Session-ID' in response.headers

    def test_auto_session_clear_stm_endpoint(self):
        """Test auto-session creation for /clear-stm endpoint"""
        # First observe something
        requests.post(
            f"{self.base_url}/observe",
            json={"strings": ["test"], "vectors": [], "emotives": {}},
            params={"processor_id": self.processor_id}
        )

        # Clear STM via deprecated endpoint
        response = requests.post(
            f"{self.base_url}/clear-stm",
            params={"processor_id": self.processor_id}
        )

        assert response.status_code == 200
        data = response.json()

        # Verify clear result
        assert data['status'] == 'cleared'

        # Verify auto-session headers
        assert response.headers.get('X-Auto-Session-Used') == 'true'
        assert 'X-Session-ID' in response.headers

        # Verify STM is actually cleared
        stm_response = requests.get(
            f"{self.base_url}/stm",
            params={"processor_id": self.processor_id}
        )
        stm_data = stm_response.json()
        assert len(stm_data['stm']) == 0

    def test_auto_session_predictions_endpoint(self):
        """Test auto-session creation for /predictions endpoint"""
        # First learn a pattern
        requests.post(
            f"{self.base_url}/observe",
            json={"strings": ["A"], "vectors": [], "emotives": {}},
            params={"processor_id": self.processor_id}
        )
        requests.post(
            f"{self.base_url}/observe",
            json={"strings": ["B"], "vectors": [], "emotives": {}},
            params={"processor_id": self.processor_id}
        )
        requests.post(
            f"{self.base_url}/learn",
            params={"processor_id": self.processor_id}
        )

        # Clear and observe partial pattern
        requests.post(
            f"{self.base_url}/clear-stm",
            params={"processor_id": self.processor_id}
        )
        requests.post(
            f"{self.base_url}/observe",
            json={"strings": ["A"], "vectors": [], "emotives": {}},
            params={"processor_id": self.processor_id}
        )

        # Get predictions via deprecated endpoint
        response = requests.get(
            f"{self.base_url}/predictions",
            params={"processor_id": self.processor_id}
        )

        assert response.status_code == 200
        data = response.json()

        # Verify predictions data
        assert 'predictions' in data
        assert 'count' in data

        # Verify auto-session headers
        assert response.headers.get('X-Auto-Session-Used') == 'true'
        assert 'X-Session-ID' in response.headers

    def test_auto_session_observe_sequence_endpoint(self):
        """Test auto-session creation for /observe-sequence endpoint"""
        # Call observe-sequence via deprecated endpoint
        response = requests.post(
            f"{self.base_url}/observe-sequence",
            json={
                "observations": [
                    {"strings": ["A"], "vectors": [], "emotives": {}},
                    {"strings": ["B"], "vectors": [], "emotives": {}},
                    {"strings": ["C"], "vectors": [], "emotives": {}}
                ],
                "learn_at_end": False
            },
            params={"processor_id": self.processor_id}
        )

        assert response.status_code == 200
        data = response.json()

        # Verify sequence result
        assert data['status'] == 'completed'
        assert data['observations_processed'] == 3
        assert len(data['results']) == 3

        # Verify auto-session headers
        assert response.headers.get('X-Auto-Session-Used') == 'true'
        assert 'X-Session-ID' in response.headers

    def test_session_reuse_across_requests(self):
        """Test that same processor_id reuses the same session"""
        # First request
        response1 = requests.post(
            f"{self.base_url}/observe",
            json={"strings": ["first"], "vectors": [], "emotives": {}},
            params={"processor_id": self.processor_id}
        )
        session_id_1 = response1.headers['X-Session-ID']

        # Second request with same processor_id
        response2 = requests.post(
            f"{self.base_url}/observe",
            json={"strings": ["second"], "vectors": [], "emotives": {}},
            params={"processor_id": self.processor_id}
        )
        session_id_2 = response2.headers['X-Session-ID']

        # Verify same session is reused
        assert session_id_1 == session_id_2

        # Verify STM accumulation (proves same session)
        stm_response = requests.get(
            f"{self.base_url}/stm",
            params={"processor_id": self.processor_id}
        )
        stm_data = stm_response.json()
        assert len(stm_data['stm']) == 2  # Both observations in STM

    def test_session_based_endpoints_bypass_middleware(self):
        """Test that session-based endpoints are not affected by middleware"""
        # Create session directly
        create_response = requests.post(
            f"{self.base_url}/sessions",
            json={"node_id": f"test_direct_{uuid.uuid4().hex[:8]}"}
        )
        assert create_response.status_code == 200
        session_data = create_response.json()
        session_id = session_data['session_id']

        # Use session-based endpoint
        response = requests.post(
            f"{self.base_url}/sessions/{session_id}/observe",
            json={"strings": ["direct", "session"], "vectors": [], "emotives": {}}
        )

        assert response.status_code == 200

        # Verify middleware headers are NOT present
        assert 'X-Auto-Session-Used' not in response.headers

    def test_processor_id_from_header(self):
        """Test auto-session creation using X-Node-ID header"""
        # Call without query param, using header instead
        response = requests.post(
            f"{self.base_url}/observe",
            json={"strings": ["header", "test"], "vectors": [], "emotives": {}},
            headers={"X-Node-ID": self.processor_id}
        )

        assert response.status_code == 200
        data = response.json()

        assert data['status'] == 'okay'
        assert response.headers.get('X-Auto-Session-Used') == 'true'
        assert 'X-Session-ID' in response.headers

    def test_metrics_tracking(self):
        """Test that deprecation metrics are being tracked"""
        # Make a few deprecated endpoint calls
        for i in range(3):
            requests.post(
                f"{self.base_url}/observe",
                json={"strings": [f"metric_test_{i}"], "vectors": [], "emotives": {}},
                params={"processor_id": f"{self.processor_id}_{i}"}
            )

        # Get metrics
        metrics_response = requests.get(f"{self.base_url}/metrics")
        assert metrics_response.status_code == 200

        metrics_data = metrics_response.json()

        # Verify deprecation metrics exist
        assert 'kato_deprecated_endpoint_calls_total' in metrics_data
        assert 'kato_auto_session_created_total' in metrics_data

        # Verify metrics have non-zero values
        deprecated_calls = metrics_data['kato_deprecated_endpoint_calls_total']
        assert deprecated_calls is not None
        assert deprecated_calls.get('current') is not None

    def test_different_processors_get_different_sessions(self):
        """Test that different processor_ids get different sessions"""
        processor_id_1 = f"test_proc_1_{uuid.uuid4().hex[:8]}"
        processor_id_2 = f"test_proc_2_{uuid.uuid4().hex[:8]}"

        # Observe with first processor
        response1 = requests.post(
            f"{self.base_url}/observe",
            json={"strings": ["processor1"], "vectors": [], "emotives": {}},
            params={"processor_id": processor_id_1}
        )
        session_id_1 = response1.headers['X-Session-ID']

        # Observe with second processor
        response2 = requests.post(
            f"{self.base_url}/observe",
            json={"strings": ["processor2"], "vectors": [], "emotives": {}},
            params={"processor_id": processor_id_2}
        )
        session_id_2 = response2.headers['X-Session-ID']

        # Verify different sessions
        assert session_id_1 != session_id_2

        # Verify isolation - each processor has own STM
        stm1 = requests.get(
            f"{self.base_url}/stm",
            params={"processor_id": processor_id_1}
        ).json()
        stm2 = requests.get(
            f"{self.base_url}/stm",
            params={"processor_id": processor_id_2}
        ).json()

        # Verify different STM contents
        assert stm1['stm'] != stm2['stm']

    def test_error_handling_without_processor_id(self):
        """Test that endpoints handle missing processor_id gracefully"""
        # This should pass through middleware and let endpoint handle it
        # The endpoint will use default_node from headers
        response = requests.post(
            f"{self.base_url}/observe",
            json={"strings": ["no_id"], "vectors": [], "emotives": {}}
        )

        # Should still work (uses default_node)
        assert response.status_code == 200

    def test_auto_session_with_short_term_memory_alias(self):
        """Test auto-session with /short-term-memory endpoint (alias for /stm)"""
        # Observe something first
        requests.post(
            f"{self.base_url}/observe",
            json={"strings": ["alias", "test"], "vectors": [], "emotives": {}},
            params={"processor_id": self.processor_id}
        )

        # Get STM via alias endpoint
        response = requests.get(
            f"{self.base_url}/short-term-memory",
            params={"processor_id": self.processor_id}
        )

        assert response.status_code == 200
        data = response.json()

        assert 'stm' in data
        assert len(data['stm']) > 0

        # Verify auto-session headers
        assert response.headers.get('X-Auto-Session-Used') == 'true'
        assert 'X-Session-ID' in response.headers

    def test_auto_session_database_isolation(self):
        """Test that auto-sessions maintain proper database isolation"""
        proc_id_1 = f"test_isolation_1_{uuid.uuid4().hex[:8]}"
        proc_id_2 = f"test_isolation_2_{uuid.uuid4().hex[:8]}"

        # Processor 1: Learn a pattern
        requests.post(
            f"{self.base_url}/observe",
            json={"strings": ["unique1"], "vectors": [], "emotives": {}},
            params={"processor_id": proc_id_1}
        )
        requests.post(
            f"{self.base_url}/observe",
            json={"strings": ["pattern1"], "vectors": [], "emotives": {}},
            params={"processor_id": proc_id_1}
        )
        learn_response = requests.post(
            f"{self.base_url}/learn",
            params={"processor_id": proc_id_1}
        )
        pattern_1 = learn_response.json()['pattern_name']

        # Processor 2: Learn a different pattern
        requests.post(
            f"{self.base_url}/observe",
            json={"strings": ["unique2"], "vectors": [], "emotives": {}},
            params={"processor_id": proc_id_2}
        )
        requests.post(
            f"{self.base_url}/observe",
            json={"strings": ["pattern2"], "vectors": [], "emotives": {}},
            params={"processor_id": proc_id_2}
        )
        learn_response2 = requests.post(
            f"{self.base_url}/learn",
            params={"processor_id": proc_id_2}
        )
        pattern_2 = learn_response2.json()['pattern_name']

        # Verify different patterns were created (different hashes)
        assert pattern_1 != pattern_2

        # Verify each processor only sees their own patterns in predictions
        # (This tests database isolation at processor_id level)
        requests.post(
            f"{self.base_url}/clear-stm",
            params={"processor_id": proc_id_1}
        )
        requests.post(
            f"{self.base_url}/observe",
            json={"strings": ["unique1"], "vectors": [], "emotives": {}},
            params={"processor_id": proc_id_1}
        )

        preds1 = requests.get(
            f"{self.base_url}/predictions",
            params={"processor_id": proc_id_1}
        ).json()

        # Processor 1 should see predictions from their pattern
        assert preds1['count'] > 0
