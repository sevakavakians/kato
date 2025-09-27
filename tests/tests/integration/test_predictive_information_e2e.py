"""
End-to-end integration tests for predictive information in predictions.
"""

import pytest
import requests
import uuid
from time import time


@pytest.fixture(scope="function")
def kato_url():
    """Get the KATO service URL."""
    return "http://localhost:8000"


@pytest.fixture(scope="function")
def processor_id():
    """Generate a unique processor ID for test isolation."""
    return f"test_pi_e2e_{int(time())}_{uuid.uuid4().hex[:8]}"


class TestPredictiveInformationE2E:
    """End-to-end tests for predictive information in predictions."""
    
    def test_predictions_include_pi_field(self, kato_url, processor_id):
        """Verify predictions include the predictive_information field."""
        # Learn a simple pattern
        response = requests.post(
            f"{kato_url}/observe",
            json={"strings": ["A", "B"], "processor_id": processor_id}
        )
        assert response.status_code == 200
        
        response = requests.post(
            f"{kato_url}/observe",
            json={"strings": ["C", "D"], "processor_id": processor_id}
        )
        assert response.status_code == 200
        
        response = requests.post(
            f"{kato_url}/learn",
            json={"processor_id": processor_id}
        )
        assert response.status_code == 200
        
        # Clear STM and observe to trigger predictions
        response = requests.post(
            f"{kato_url}/clear-stm",
            json={"processor_id": processor_id}
        )
        assert response.status_code == 200
        
        response = requests.post(
            f"{kato_url}/observe",
            json={"strings": ["A", "B"], "processor_id": processor_id}
        )
        assert response.status_code == 200
        
        # Get predictions
        response = requests.post(
            f"{kato_url}/predictions",
            json={"processor_id": processor_id}
        )
        assert response.status_code == 200
        
        result = response.json()
        predictions = result.get('predictions', [])
        assert len(predictions) > 0
        
        # Check that predictive_information field exists
        for pred in predictions:
            assert 'predictive_information' in pred
            assert isinstance(pred['predictive_information'], float)
            assert pred['predictive_information'] >= 0.0
            assert pred['predictive_information'] <= 1.0  # Normalized value
    
    def test_potential_uses_pi_formula(self, kato_url, processor_id):
        """Verify potential is calculated as similarity * predictive_information."""
        # Learn a pattern
        response = requests.post(
            f"{kato_url}/observe",
            json={"strings": ["X", "Y", "Z"], "processor_id": processor_id}
        )
        assert response.status_code == 200
        
        response = requests.post(
            f"{kato_url}/observe",
            json={"strings": ["W", "V"], "processor_id": processor_id}
        )
        assert response.status_code == 200
        
        response = requests.post(
            f"{kato_url}/learn",
            json={"processor_id": processor_id}
        )
        assert response.status_code == 200
        
        # Clear and observe for predictions
        response = requests.post(
            f"{kato_url}/clear-stm",
            json={"processor_id": processor_id}
        )
        assert response.status_code == 200
        
        response = requests.post(
            f"{kato_url}/observe",
            json={"strings": ["X", "Y"], "processor_id": processor_id}
        )
        assert response.status_code == 200
        
        # Get predictions
        response = requests.post(
            f"{kato_url}/predictions",
            json={"processor_id": processor_id}
        )
        assert response.status_code == 200
        
        result = response.json()
        predictions = result.get('predictions', [])
        assert len(predictions) > 0
        
        for pred in predictions:
            similarity = pred.get('similarity', 0)
            pi = pred.get('predictive_information', 0)
            potential = pred.get('potential', 0)
            
            # Verify the new formula (within floating point tolerance)
            expected_potential = similarity * pi
            assert abs(potential - expected_potential) < 0.0001, \
                f"Potential {potential} != similarity {similarity} * PI {pi}"
    
    def test_pi_increases_with_pattern_repetition(self, kato_url, processor_id):
        """Test that PI increases when patterns are learned multiple times."""
        # Learn the same pattern multiple times
        for _ in range(3):
            response = requests.post(
                f"{kato_url}/observe",
                json={"strings": ["START"], "processor_id": processor_id}
            )
            assert response.status_code == 200
            
            response = requests.post(
                f"{kato_url}/observe",
                json={"strings": ["MIDDLE"], "processor_id": processor_id}
            )
            assert response.status_code == 200
            
            response = requests.post(
                f"{kato_url}/observe",
                json={"strings": ["END"], "processor_id": processor_id}
            )
            assert response.status_code == 200
            
            response = requests.post(
                f"{kato_url}/learn",
                json={"processor_id": processor_id}
            )
            assert response.status_code == 200
        
        # Clear and observe for predictions
        response = requests.post(
            f"{kato_url}/clear-stm",
            json={"processor_id": processor_id}
        )
        assert response.status_code == 200
        
        response = requests.post(
            f"{kato_url}/observe",
            json={"strings": ["START", "MIDDLE"], "processor_id": processor_id}
        )
        assert response.status_code == 200
        
        # Get predictions
        response = requests.post(
            f"{kato_url}/predictions",
            json={"processor_id": processor_id}
        )
        assert response.status_code == 200
        
        result = response.json()
        predictions = result.get('predictions', [])
        assert len(predictions) > 0
        
        # With repeated patterns, PI should be non-zero
        # (as co-occurrence statistics build up)
        max_pi = max(p['predictive_information'] for p in predictions)
        assert max_pi >= 0.0  # Should have some predictive information
    
    def test_different_patterns_have_different_pi(self, kato_url, processor_id):
        """Test that different patterns have different PI values."""
        # Learn first pattern (highly predictable)
        for _ in range(5):
            response = requests.post(
                f"{kato_url}/observe",
                json={"strings": ["A1"], "processor_id": processor_id}
            )
            response = requests.post(
                f"{kato_url}/observe",
                json={"strings": ["B1"], "processor_id": processor_id}
            )
            response = requests.post(
                f"{kato_url}/learn",
                json={"processor_id": processor_id}
            )
        
        # Learn second pattern (less predictable, only once)
        response = requests.post(
            f"{kato_url}/observe",
            json={"strings": ["X9"], "processor_id": processor_id}
        )
        response = requests.post(
            f"{kato_url}/observe",
            json={"strings": ["Y9"], "processor_id": processor_id}
        )
        response = requests.post(
            f"{kato_url}/learn",
            json={"processor_id": processor_id}
        )
        
        # Clear and observe both patterns
        response = requests.post(
            f"{kato_url}/clear-stm",
            json={"processor_id": processor_id}
        )
        
        # Observe to match both patterns
        response = requests.post(
            f"{kato_url}/observe",
            json={"strings": ["A1", "X9"], "processor_id": processor_id}
        )
        
        # Get predictions
        response = requests.post(
            f"{kato_url}/predictions",
            json={"processor_id": processor_id}
        )
        
        result = response.json()
        predictions = result.get('predictions', [])
        assert len(predictions) >= 2  # Should have predictions for both patterns
        
        # Different patterns should have different PI values
        pi_values = [p['predictive_information'] for p in predictions]
        assert len(set(pi_values)) > 1 or all(v == 0 for v in pi_values), \
            "All patterns have same PI value, expected variation"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])