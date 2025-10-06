"""
Test KATO current.0 monitoring endpoints
Tests comprehensive metrics and health monitoring
"""

import time

import pytest
import requests


def _get_test_base_url():
    """Get the base URL for testing - use single instance"""
    # Use single KATO instance on port 8000
    return "http://localhost:8000"


class TestMonitoringEndpoints:
    """Test monitoring endpoints"""

    @property
    def BASE_URL(self):
        return _get_test_base_url()

    def test_health_endpoint(self):
        """Test /health endpoint returns comprehensive health information"""
        response = requests.get(f"{self.BASE_URL}/health")

        assert response.status_code == 200
        data = response.json()

        # Check required fields
        assert "status" in data
        assert "processor_status" in data
        # The health endpoint now has service_name and active_sessions instead of processor_id
        assert "service_name" in data or "base_processor_id" in data or "processor_id" in data
        assert "uptime_seconds" in data
        assert "issues" in data
        assert "metrics_collected" in data
        assert "last_collection" in data

        # Health status should be valid
        assert data["status"] in ["healthy", "degraded", "unhealthy"]
        assert data["processor_status"] in ["healthy", "unhealthy", "unknown"]

        # Uptime should be positive
        assert data["uptime_seconds"] > 0

        # Issues should be a list
        assert isinstance(data["issues"], list)

    def test_metrics_endpoint(self):
        """Test /metrics endpoint returns comprehensive metrics"""
        response = requests.get(f"{self.BASE_URL}/metrics")

        assert response.status_code == 200
        data = response.json()

        # Check main sections exist (current uses processor_manager instead of processor)
        required_sections = ["timestamp", "sessions", "performance", "resources", "databases", "rates"]
        for section in required_sections:
            assert section in data, f"Missing section: {section}"

        # Check for processor or processor_manager
        assert "processor" in data or "processor_manager" in data, "Missing processor or processor_manager section"

        # Verify sessions metrics
        sessions = data["sessions"]
        session_fields = ["total_created", "total_deleted", "active", "operations_total"]
        for field in session_fields:
            assert field in sessions, f"Missing session field: {field}"
            assert isinstance(sessions[field], (int, float))

        # Verify performance metrics
        performance = data["performance"]
        perf_fields = ["total_requests", "total_errors", "error_rate", "average_response_time"]
        for field in perf_fields:
            assert field in performance, f"Missing performance field: {field}"
            assert isinstance(performance[field], (int, float))

        # Verify resources metrics
        resources = data["resources"]
        resource_fields = ["cpu_percent", "memory_percent", "disk_percent"]
        for field in resource_fields:
            assert field in resources, f"Missing resource field: {field}"
            assert isinstance(resources[field], (int, float))
            assert 0 <= resources[field] <= 100, f"Invalid percentage for {field}: {resources[field]}"

        # Verify processor metrics (current uses processor_manager)
        if "processor" in data:
            processor = data["processor"]
            processor_fields = ["processor_id", "processor_name", "observations_processed", "stm_size"]
            for field in processor_fields:
                assert field in processor, f"Missing processor field: {field}"
        elif "processor_manager" in data:
            # current service has different structure
            assert "total_processors" in data["processor_manager"]
            assert "processors" in data["processor_manager"]

        # Verify rates
        rates = data["rates"]
        assert isinstance(rates, dict)

    def test_stats_endpoint_default(self):
        """Test /stats endpoint with default parameters"""
        response = requests.get(f"{self.BASE_URL}/stats")

        assert response.status_code == 200
        data = response.json()

        # Check required fields (current may have different fields)
        assert "time_range_minutes" in data
        assert "timestamp" in data
        # current may have processor_manager instead of processor_id
        assert "processor_id" in data or "processor_manager" in data
        assert "current_status" in data or "error" in data  # May have error if no metrics
        assert "time_series" in data or "error" in data
        assert "summary" in data or "error" in data

        # Default range should be 10 minutes
        assert data["time_range_minutes"] == 10

        # Time series should contain expected metrics
        time_series = data["time_series"]
        expected_metrics = ["cpu_percent", "memory_percent", "requests_total", "response_time"]
        for metric in expected_metrics:
            assert metric in time_series, f"Missing time series metric: {metric}"
            assert isinstance(time_series[metric], list)

        # Summary should have main sections
        summary = data["summary"]
        summary_sections = ["sessions", "performance", "resources", "databases"]
        for section in summary_sections:
            assert section in summary, f"Missing summary section: {section}"

    def test_stats_endpoint_custom_range(self):
        """Test /stats endpoint with custom time range"""
        minutes = 5
        response = requests.get(f"{self.BASE_URL}/stats?minutes={minutes}")

        assert response.status_code == 200
        data = response.json()

        assert data["time_range_minutes"] == minutes

    def test_specific_metric_endpoint(self):
        """Test /metrics/{metric_name} endpoint"""
        # First, make a few requests to generate some metrics
        for _ in range(3):
            requests.get(f"{self.BASE_URL}/health")
            time.sleep(0.1)

        # Wait a bit for metrics to be collected
        time.sleep(2)

        # Test getting response_time metrics
        response = requests.get(f"{self.BASE_URL}/metrics/response_time")

        if response.status_code == 200:
            data = response.json()

            # Check required fields
            assert "metric_name" in data
            assert "time_range_minutes" in data
            assert "timestamp" in data
            assert "statistics" in data
            assert "data_points" in data

            assert data["metric_name"] == "response_time"
            assert data["time_range_minutes"] == 10  # Default

            # Statistics should have basic stats
            stats = data["statistics"]
            stat_fields = ["count", "min", "max", "avg"]
            for field in stat_fields:
                assert field in stats, f"Missing statistic: {field}"
                assert isinstance(stats[field], (int, float))

            # Data points should be a list of metric points
            assert isinstance(data["data_points"], list)
        else:
            # If no data available, should be 404
            assert response.status_code == 404
            error_data = response.json()
            assert "detail" in error_data
            assert "No data available" in error_data["detail"]

    def test_specific_metric_invalid(self):
        """Test /metrics/{metric_name} with invalid metric"""
        response = requests.get(f"{self.BASE_URL}/metrics/invalid_metric_name")

        # Should return 404 or empty data
        assert response.status_code in [200, 404]

        if response.status_code == 404:
            data = response.json()
            assert "detail" in data

    def test_session_placeholder_endpoint(self):
        """Test current session creation placeholder"""
        # Sessions endpoint requires a node_id in the request body
        response = requests.post(f"{self.BASE_URL}/sessions", json={"node_id": "test_node_123"})

        assert response.status_code == 200
        data = response.json()

        assert "session_id" in data
        assert "node_id" in data
        assert "created_at" in data
        assert "expires_at" in data
        assert data["node_id"] == "test_node_123"

    def test_metrics_collection_after_requests(self):
        """Test that metrics are properly collected after making requests"""
        # Get initial metrics
        initial_response = requests.get(f"{self.BASE_URL}/metrics")
        assert initial_response.status_code == 200
        initial_data = initial_response.json()
        initial_requests = initial_data["performance"]["total_requests"]

        # Make some requests
        test_requests = 5
        for _i in range(test_requests):
            requests.get(f"{self.BASE_URL}/health")

        # Wait a moment for metrics to update
        time.sleep(1)

        # Get updated metrics
        final_response = requests.get(f"{self.BASE_URL}/metrics")
        assert final_response.status_code == 200
        final_data = final_response.json()
        final_requests = final_data["performance"]["total_requests"]

        # Should have recorded the additional requests
        # Note: This might not be exactly test_requests due to the metrics collection itself
        assert final_requests > initial_requests

        # Performance metrics should be reasonable
        assert final_data["performance"]["error_rate"] >= 0
        assert final_data["performance"]["average_response_time"] > 0

    def test_health_degradation_detection(self):
        """Test that health endpoint can detect system issues"""
        response = requests.get(f"{self.BASE_URL}/health")
        assert response.status_code == 200
        data = response.json()

        # Even if system is healthy, the structure should be correct
        assert "status" in data
        assert "issues" in data

        # Issues should be empty for healthy system, or contain descriptions if not
        if data["issues"]:
            for issue in data["issues"]:
                assert isinstance(issue, str)
                assert len(issue) > 0

    def test_concurrent_metrics_access(self):
        """Test that metrics endpoints can handle concurrent access"""
        import queue
        import threading

        results = queue.Queue()

        def make_request():
            try:
                response = requests.get(f"{self.BASE_URL}/metrics", timeout=10)
                results.put(response.status_code)
            except Exception as e:
                results.put(f"error: {e}")

        # Start multiple concurrent requests
        threads = []
        for _ in range(5):
            thread = threading.Thread(target=make_request)
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join(timeout=15)

        # Check results
        status_codes = []
        while not results.empty():
            result = results.get()
            if isinstance(result, int):
                status_codes.append(result)
            else:
                pytest.fail(f"Request failed: {result}")

        # All requests should succeed
        assert len(status_codes) == 5
        for status_code in status_codes:
            assert status_code == 200



if __name__ == "__main__":
    pytest.main([__file__, "-v"])
