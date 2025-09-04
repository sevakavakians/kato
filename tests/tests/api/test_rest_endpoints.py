"""
API tests for KATO REST endpoints.
Tests all REST API endpoints for correct behavior and error handling.
"""

import pytest
import requests
import json
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Use FastAPI fixture if available, otherwise fall back to old fixture
if os.environ.get('USE_FASTAPI', 'false').lower() == 'true':
    from fixtures.kato_fastapi_fixtures import kato_fastapi_existing as kato_fixture
else:
    from fixtures.kato_fixtures import kato_fixture
from fixtures.test_helpers import sort_event_strings


def test_ping_endpoint(kato_fixture):
    """Test the health check ping endpoint."""
    response = requests.get(f"{kato_fixture.base_url}/kato-api/ping")
    assert response.status_code == 200
    
    data = response.json()
    assert data['status'] == 'okay'


def test_connect_endpoint(kato_fixture):
    """Test the connect endpoint returns genome structure."""
    response = requests.get(f"{kato_fixture.base_url}/connect")
    assert response.status_code == 200
    
    data = response.json()
    assert 'status' in data
    assert 'genome' in data
    assert 'elements' in data['genome']
    assert 'nodes' in data['genome']['elements']
    
    # Check processor node structure
    nodes = data['genome']['elements']['nodes']
    assert len(nodes) >= 1
    
    node = nodes[0]['data']
    assert 'name' in node
    assert 'id' in node
    assert 'classifier' in node


def test_processor_ping_endpoint(kato_fixture):
    """Test processor-specific ping endpoint."""
    response = requests.get(f"{kato_fixture.base_url}/{kato_fixture.processor_id}/ping")
    assert response.status_code == 200
    
    data = response.json()
    assert 'id' in data
    assert 'status' in data
    assert 'time_stamp' in data
    assert data['status'] == 'okay'


def test_status_endpoint(kato_fixture):
    """Test processor status endpoint."""
    response = requests.get(f"{kato_fixture.base_url}/{kato_fixture.processor_id}/status")
    assert response.status_code == 200
    
    data = response.json()
    assert 'id' in data
    assert 'status' in data
    assert 'message' in data
    assert data['status'] == 'okay'
    
    # Status message should be a dict with processor info
    message = data['message']
    assert isinstance(message, dict)


def test_observe_endpoint(kato_fixture):
    """Test the observe endpoint."""
    observation = {
        'strings': ['test', 'api'],
        'vectors': [[1.0, 2.0]],
        'emotives': {'confidence': 0.8}
    }
    
    response = requests.post(
        f"{kato_fixture.base_url}/{kato_fixture.processor_id}/observe",
        json=observation
    )
    assert response.status_code == 200
    
    data = response.json()
    assert 'status' in data
    assert 'message' in data
    assert data['status'] == 'okay'
    
    message = data['message']
    assert message['status'] == 'observed'
    assert 'auto_learned_pattern' in message


def test_observe_endpoint_empty(kato_fixture):
    """Test observe endpoint with empty data."""
    observation = {
        'strings': [],
        'vectors': [],
        'emotives': {}
    }
    
    response = requests.post(
        f"{kato_fixture.base_url}/{kato_fixture.processor_id}/observe",
        json=observation
    )
    assert response.status_code == 200
    
    data = response.json()
    assert data['message']['status'] == 'observed' #TODO: Let's change this so the message provides something more useful like, "no-data-provided"


def test_short_term_memory_endpoint(kato_fixture):
    """Test getting short-term memory (formerly short-term memory) via REST."""
    # Clear and add some observations
    kato_fixture.clear_all_memory()
    kato_fixture.observe({'strings': ['stm', 'test'], 'vectors': [], 'emotives': {}})
    
    response = requests.get(
        f"{kato_fixture.base_url}/{kato_fixture.processor_id}/short-term-memory"
    )
    assert response.status_code == 200
    
    data = response.json()
    assert 'message' in data
    stm = data['message']
    assert isinstance(stm, list)
    assert len(stm) == 1
    # KATO sorts strings alphanumerically: 'stm' comes before 'test'
    assert stm[0] == sort_event_strings(['stm', 'test'])


def test_clear_short_term_memory_endpoint(kato_fixture):
    """Test clearing short-term memory (formerly short-term memory) via REST."""
    # Add observation first
    kato_fixture.observe({'strings': ['clear', 'me'], 'vectors': [], 'emotives': {}})
    
    response = requests.post(
        f"{kato_fixture.base_url}/{kato_fixture.processor_id}/clear-short-term-memory",
        json={}
    )
    assert response.status_code == 200
    
    data = response.json()
    assert data['message'] == 'stm-cleared'
    
    # Verify it's cleared
    stm = kato_fixture.get_short_term_memory()
    assert stm == []


def test_clear_all_memory_endpoint(kato_fixture):
    """Test clearing all memory via REST."""
    # Add and learn something first
    kato_fixture.observe({'strings': ['mem'], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()
    
    response = requests.post(
        f"{kato_fixture.base_url}/{kato_fixture.processor_id}/clear-all-memory",
        json={}
    )
    assert response.status_code == 200
    
    data = response.json()
    assert data['message'] == 'all-cleared'
    
    # Verify no predictions
    predictions = kato_fixture.get_predictions()
    assert predictions == []


def test_learn_endpoint(kato_fixture):
    """Test the learn endpoint."""
    # Build sequence to learn
    kato_fixture.clear_all_memory()
    for item in ['learn', 'this', 'sequence']:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    
    response = requests.post(
        f"{kato_fixture.base_url}/{kato_fixture.processor_id}/learn",
        json={}
    )
    assert response.status_code == 200
    
    data = response.json()
    assert 'message' in data
    pattern_name = data['message']
    assert pattern_name.startswith('PTRN|')
    
    # Short-term memory should be cleared
    stm = kato_fixture.get_short_term_memory()
    assert stm == []


def test_predictions_endpoint(kato_fixture):
    """Test getting predictions via REST."""
    # Setup: learn a sequence
    kato_fixture.clear_all_memory()
    for item in ['pred', 'test', 'api']:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    kato_fixture.learn()
    
    # Observe to generate predictions (KATO requires 2+ strings)
    kato_fixture.observe({'strings': ['pred'], 'vectors': [], 'emotives': {}})
    kato_fixture.observe({'strings': ['test'], 'vectors': [], 'emotives': {}})
    
    response = requests.get(
        f"{kato_fixture.base_url}/{kato_fixture.processor_id}/predictions"
    )
    assert response.status_code == 200
    
    data = response.json()
    assert 'message' in data
    predictions = data['message']
    assert isinstance(predictions, list)
    assert len(predictions) > 0
    
    # Check prediction structure
    pred = predictions[0]
    assert 'name' in pred
    assert 'confidence' in pred
    assert 'similarity' in pred


def test_percept_data_endpoint(kato_fixture):
    """Test getting percept data via REST."""
    response = requests.get(
        f"{kato_fixture.base_url}/{kato_fixture.processor_id}/percept-data"
    )
    assert response.status_code == 200
    
    data = response.json()
    assert 'message' in data
    percept_data = data['message']
    assert isinstance(percept_data, dict)


def test_cognition_data_endpoint(kato_fixture):
    """Test getting cognition data via REST."""
    # Add some data first
    kato_fixture.clear_all_memory()
    kato_fixture.observe({'strings': ['cog', 'data'], 'vectors': [], 'emotives': {}})
    
    response = requests.get(
        f"{kato_fixture.base_url}/{kato_fixture.processor_id}/cognition-data"
    )
    assert response.status_code == 200
    
    data = response.json()
    assert 'message' in data
    cog_data = data['message']
    assert isinstance(cog_data, dict)
    
    # Should have cognition data fields based on KATO's actual implementation
    expected_fields = ['short_term_memory', 'predictions', 'emotives', 'symbols', 'command']
    for field in expected_fields:
        assert field in cog_data, f"Missing field: {field}"


def test_gene_endpoint(kato_fixture):
    """Test getting gene values via REST."""
    # Test getting a known gene
    response = requests.get(
        f"{kato_fixture.base_url}/{kato_fixture.processor_id}/gene/recall_threshold"
    )
    assert response.status_code == 200
    
    data = response.json()
    assert 'message' in data
    # Gene value could be None or a number
    assert data['message'] is None or isinstance(data['message'], (int, float))


def test_gene_change_endpoint(kato_fixture):
    """Test changing gene values via REST."""
    gene_update = {
        'data': {
            'recall_threshold': 0.6
        }
    }
    
    response = requests.post(
        f"{kato_fixture.base_url}/{kato_fixture.processor_id}/genes/change",
        json=gene_update
    )
    assert response.status_code == 200
    
    data = response.json()
    assert 'message' in data
    assert data['message'] == 'updated-genes'


def test_pattern_endpoint(kato_fixture):
    """Test getting pattern information via REST."""
    # Learn a pattern first
    kato_fixture.clear_all_memory()
    for item in ['pattern', 'info', 'test']:
        kato_fixture.observe({'strings': [item], 'vectors': [], 'emotives': {}})
    pattern_name = kato_fixture.learn()
    
    # Get pattern info
    response = requests.get(
        f"{kato_fixture.base_url}/{kato_fixture.processor_id}/pattern/{pattern_name}"
    )
    assert response.status_code == 200
    
    data = response.json()
    assert 'message' in data
    pattern_info = data['message']
    assert isinstance(pattern_info, dict)
    assert 'name' in pattern_info


def test_error_handling_404(kato_fixture):
    """Test 404 error for non-existent endpoints."""
    response = requests.get(
        f"{kato_fixture.base_url}/non-existent-endpoint"
    )
    assert response.status_code == 404


def test_error_handling_invalid_json(kato_fixture):
    """Test error handling for invalid JSON."""
    response = requests.post(
        f"{kato_fixture.base_url}/{kato_fixture.processor_id}/observe",
        data="invalid json",
        headers={'Content-Type': 'application/json'}
    )
    assert response.status_code == 500


def test_observe_data_wrapper_format(kato_fixture):
    """Test observe endpoint with wrapped data format."""
    observation = {
        'data': {
            'strings': ['wrapped', 'format'],  # Will be sorted to ['format', 'wrapped'] by KATO
            'vectors': [],
            'emotives': {}
        }
    }
    
    response = requests.post(
        f"{kato_fixture.base_url}/{kato_fixture.processor_id}/observe",
        json=observation
    )
    assert response.status_code == 200
    
    data = response.json()
    assert data['message']['status'] == 'observed'


def test_predictions_post_endpoint(kato_fixture):
    """Test POST method for predictions endpoint."""
    # Some implementations support POST for predictions
    response = requests.post(
        f"{kato_fixture.base_url}/{kato_fixture.processor_id}/predictions",
        json={}
    )
    assert response.status_code == 200
    
    data = response.json()
    assert 'message' in data
    assert isinstance(data['message'], list)


def test_endpoint_response_timing(kato_fixture):
    """Test that endpoints include timing information."""
    endpoints = [
        f"/{kato_fixture.processor_id}/ping",
        f"/{kato_fixture.processor_id}/status",
        f"/{kato_fixture.processor_id}/short-term-memory"
    ]
    
    for endpoint in endpoints:
        response = requests.get(f"{kato_fixture.base_url}{endpoint}")
        assert response.status_code == 200
        
        data = response.json()
        assert 'time_stamp' in data or 'timestamp' in data
        assert 'interval' in data