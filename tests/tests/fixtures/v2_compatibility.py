"""
V2 Compatibility Helper for Tests

This module provides compatibility functions to make tests work with both v1 and v2 APIs.
"""

def normalize_response(response_data):
    """
    Normalize response data to work with both v1 and v2 formats.
    
    Args:
        response_data: Dict response from API
        
    Returns:
        Normalized dict with consistent field names
    """
    # Map v2 fields to v1 expectations
    field_mappings = {
        'uptime_seconds': 'uptime',
        'base_processor_id': 'processor_id',
        'timestamp': 'time',
        'ok': 'okay',
        'session_id': 'processor_id',  # Use session_id as processor_id in v2
    }
    
    # Create normalized response
    normalized = response_data.copy()
    
    # Apply field mappings
    for v2_field, v1_field in field_mappings.items():
        if v2_field in response_data and v1_field not in response_data:
            normalized[v1_field] = response_data[v2_field]
    
    # Handle status field
    if 'status' in normalized:
        if normalized['status'] == 'ok':
            normalized['status'] = 'okay'
    
    return normalized


def is_v2_service(base_url):
    """
    Check if the service is v2 based on response format.
    
    Args:
        base_url: Base URL of the service
        
    Returns:
        True if v2 service, False otherwise
    """
    import requests
    try:
        response = requests.get(f"{base_url}/health", timeout=2)
        if response.status_code == 200:
            data = response.json()
            # V2 has 'base_processor_id' or 'active_sessions'
            return 'base_processor_id' in data or 'active_sessions' in data
    except:
        pass
    return False


def adapt_test_expectations(test_func):
    """
    Decorator to adapt test expectations for v1/v2 compatibility.
    
    Usage:
        @adapt_test_expectations
        def test_something(kato_fixture):
            ...
    """
    def wrapper(*args, **kwargs):
        # Check if we're running against v2
        if args and hasattr(args[0], 'base_url'):
            fixture = args[0]
            if is_v2_service(fixture.base_url):
                # Set v2 mode flag
                fixture._is_v2 = True
        return test_func(*args, **kwargs)
    return wrapper