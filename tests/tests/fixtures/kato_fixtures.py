"""
FastAPI-based fixtures for KATO tests.
Supports the new FastAPI architecture with direct container access.
"""

import os
import sys
import time
import json
import subprocess
import requests
import pytest
from typing import Dict, Any, Optional, List
import uuid
from pathlib import Path

# Try to import docker, but don't fail if it's not available
try:
    import docker
    HAS_DOCKER_PACKAGE = True
except ImportError:
    HAS_DOCKER_PACKAGE = False

# Add parent directories to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))


class KATOFastAPIFixture:
    """Test fixture for FastAPI-based KATO architecture."""
    
    def __init__(self, processor_name: str = "test", use_docker: bool = True):
        """Initialize KATO FastAPI test fixture.
        
        Args:
            processor_name: Name for the processor
            use_docker: If True, create a Docker container. If False, expect existing service.
        """
        self.processor_name = processor_name
        self.use_docker = use_docker
        self.docker_client = None
        self.container = None
        self.container_name = None
        self.port = None
        self.base_url = None
        self.processor_id = self._generate_processor_id()
        self.services_available = False
        self.session_id = None  # No longer used after v2 removal
        self.session_created = False  # No longer used after v2 removal
        self.use_v2_session = False  # Disable v2 session usage
        
        if use_docker and HAS_DOCKER_PACKAGE:
            try:
                self.docker_client = docker.from_env()
            except Exception:
                print("Warning: Docker not available, will use existing service")
                self.use_docker = False
        elif use_docker and not HAS_DOCKER_PACKAGE:
            print("Warning: docker Python package not installed, will use existing service")
            self.use_docker = False
                
    def _generate_processor_id(self) -> str:
        """Generate a unique processor ID for complete test isolation."""
        timestamp = int(time.time() * 1000)
        unique = str(uuid.uuid4())[:8]
        clean_name = self.processor_name.replace(' ', '_').replace('-', '_').lower()
        return f"test_{clean_name}_{timestamp}_{unique}"
    
    def _find_available_port(self) -> int:
        """Find an available port for the container."""
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('', 0))
            s.listen(1)
            port = s.getsockname()[1]
        return port
    
    def _discover_dynamic_port(self) -> Optional[int]:
        """Discover dynamically assigned port from saved port mappings or Docker."""
        # First try to read from saved ports file
        ports_file = Path(os.path.dirname(__file__)).parent.parent.parent / '.kato-ports.json'
        if ports_file.exists():
            try:
                with open(ports_file, 'r') as f:
                    port_data = json.load(f)
                # Try to use testing service first, then primary
                for service_name in ['testing', 'primary']:
                    if service_name in port_data.get('services', {}):
                        port = port_data['services'][service_name].get('port')
                        if port:
                            # Verify the service is actually running
                            try:
                                response = requests.get(f"http://localhost:{port}/health", timeout=1)
                                if response.status_code == 200:
                                    return port
                            except:
                                continue
            except (json.JSONDecodeError, KeyError):
                pass
        
        # Try to discover using docker port command
        if HAS_DOCKER_PACKAGE:
            for container_name in ['kato-testing-v2', 'kato-primary-v2']:
                try:
                    result = subprocess.run(
                        ['docker', 'port', container_name, '8000'],
                        capture_output=True,
                        text=True,
                        timeout=2
                    )
                    if result.returncode == 0 and result.stdout:
                        # Parse output like "0.0.0.0:32768"
                        port_str = result.stdout.strip().split(':')[-1]
                        port = int(port_str)
                        # Verify the service is running
                        response = requests.get(f"http://localhost:{port}/health", timeout=1)
                        if response.status_code == 200:
                            return port
                except (subprocess.TimeoutExpired, ValueError, requests.exceptions.RequestException):
                    continue
        
        return None
    
    
    
    def _wait_for_ready(self, timeout: int = 30) -> bool:
        """Wait for the KATO service to be ready."""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                response = requests.get(f"{self.base_url}/health", timeout=2)
                if response.status_code == 200:
                    # Verify processor is responding
                    response = requests.get(f"{self.base_url}/status", timeout=2)
                    if response.status_code == 200:
                        return True
            except requests.exceptions.RequestException:
                pass
            time.sleep(1)
        
        return False
    
    def setup(self):
        """Set up KATO service for testing."""
        if self.use_docker and self.docker_client:
            # Create a new Docker container for this test
            self.port = self._find_available_port()
            self.container_name = f"kato-test-{self.processor_id}"
            self.base_url = f"http://localhost:{self.port}"
            
            try:
                # Check if kato:fastapi image exists
                try:
                    self.docker_client.images.get('kato:fastapi')
                except docker.errors.ImageNotFound:
                    print("Building kato:fastapi image...")
                    # Build the image
                    kato_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..'))
                    self.docker_client.images.build(
                        path=kato_dir,
                        dockerfile='Dockerfile.fastapi',
                        tag='kato:fastapi',
                        rm=True
                    )
                
                # Create and start container
                self.container = self.docker_client.containers.run(
                    'kato:fastapi',
                    name=self.container_name,
                    environment={
                        'PROCESSOR_ID': self.processor_id,
                        'PROCESSOR_NAME': self.processor_name,
                        'MONGO_BASE_URL': os.environ.get('MONGO_BASE_URL', 'mongodb://host.docker.internal:27017'),
                        'MAX_PATTERN_LENGTH': '0',
                        'PERSISTENCE': '5',
                        'RECALL_THRESHOLD': '0.1',
                        'LOG_LEVEL': 'INFO'
                    },
                    ports={'8000/tcp': self.port},
                    detach=True,
                    auto_remove=False,
                    network_mode='bridge'  # Use bridge network for host.docker.internal support
                )
                
                # Wait for service to be ready
                if self._wait_for_ready():
                    self.services_available = True
                    print(f"KATO container {self.container_name} ready at {self.base_url}")
                else:
                    raise TimeoutError(f"KATO container did not start within timeout")
                    
            except Exception as e:
                print(f"Failed to create Docker container: {e}")
                # Fall back to using existing service
                self.use_docker = False
                
        if not self.use_docker:
            # Use existing KATO service (for local development)
            # First try to discover dynamic ports
            discovered_port = self._discover_dynamic_port()
            if discovered_port:
                self.port = discovered_port
                self.base_url = f"http://localhost:{self.port}"
                self.services_available = True
                print(f"Using dynamically discovered KATO v2 service at {self.base_url}")
                self._ensure_session()
            else:
                # Fall back to trying fixed ports - check 8001 first (test default)
                for port in [8001, 8002, 8003, 8000]:
                    self.base_url = f"http://localhost:{port}"
                    try:
                        # Check if service is running (works for both v1 and v2)
                        response = requests.get(f"{self.base_url}/health", timeout=2)
                        if response.status_code == 200:
                            health_data = response.json()
                            # Accept both v1 and v2 services
                            # V2 has "base_processor_id" or "active_sessions"
                            # V1 has just "processor_id" and "uptime"
                            self.services_available = True
                            self.port = port
                            
                            # Check if it's a v2 service
                            if "base_processor_id" in health_data or "active_sessions" in health_data:
                                print(f"Using existing KATO v2 service at {self.base_url}")
                                # Create a persistent session for this test
                                self._ensure_session()
                            else:
                                # V1 service - no session needed
                                print(f"Using existing KATO v1 service at {self.base_url}")
                            break
                    except requests.exceptions.RequestException:
                        continue
            
            if not self.services_available:
                print("\n" + "="*60)
                print("WARNING: No KATO services found!")
                print("Start a KATO FastAPI service with:")
                print("  docker-compose -f docker-compose.fastapi.yml up kato-testing")
                print("Or run locally with:")
                print("  PROCESSOR_ID=testing uvicorn kato.services.kato_fastapi:app")
                print("="*60 + "\n")
        
        # Primary endpoints use automatic session management
        # No need to explicitly create sessions
    
    def _ensure_session(self):
        """V2 sessions no longer used after migration to unified version."""
        # All session management is now handled internally by the service
        # Each processor_id acts as isolation boundary
        self.session_created = False
        self.session_id = None
                
    def teardown(self):
        """Clean up KATO service after testing."""
        # No v2 session cleanup needed after migration
        pass
        
        # With primary endpoints using automatic session management,
        # each test automatically gets isolated per-user databases.
        # No explicit cleanup needed.
        
        if self.use_docker and self.container:
            try:
                self.container.stop()
                self.container.remove()
                print(f"Removed container {self.container_name}")
            except Exception as e:
                print(f"Error removing container: {e}")
                
    def observe(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Send an observation to KATO."""
        if not self.services_available:
            pytest.skip("KATO services not available")
        
        # Use x-test-id header for isolation (processor_id in body is ignored)
        headers = {'x-test-id': self.processor_id}
        response = requests.post(f"{self.base_url}/observe", json=data, headers=headers)
        
        response.raise_for_status()
        result = response.json()
        
        # Transform response to match expected format for tests
        # V2 returns 'ok' but tests expect 'observed'
        status = result.get('status', 'observed')
        if status == 'ok' or status == 'okay':
            status = 'observed'
        
        return {
            'status': status,
            'auto_learned_pattern': result.get('auto_learned_pattern'),
            'processor_id': result.get('processor_id', self.processor_id),
            'time': result.get('time'),
            'unique_id': result.get('unique_id')
        }
    
    def get_stm(self) -> List[List[str]]:
        """Get the current short-term memory."""
        if not self.services_available:
            pytest.skip("KATO services not available")
        
        # Use x-test-id header for isolation
        headers = {'x-test-id': self.processor_id}
        response = requests.get(f"{self.base_url}/stm", headers=headers)
        
        response.raise_for_status()
        result = response.json()
        return result.get('stm', [])
    
    def get_short_term_memory(self) -> List[List[str]]:
        """Alias for get_stm for backward compatibility."""
        return self.get_stm()
    
    def get_predictions(self, unique_id: Optional[str] = None) -> List[Dict]:
        """Get predictions."""
        if not self.services_available:
            pytest.skip("KATO services not available")
        
        params = {}
        if unique_id:
            params['unique_id'] = unique_id
        
        # Use x-test-id header for isolation
        headers = {'x-test-id': self.processor_id}
        response = requests.get(f"{self.base_url}/predictions", params=params, headers=headers)
        
        response.raise_for_status()
        result = response.json()
        return result.get('predictions', [])
    
    def learn(self) -> str:
        """Force learning of current short-term memory."""
        if not self.services_available:
            pytest.skip("KATO services not available")
        
        # Use x-test-id header for isolation
        headers = {'x-test-id': self.processor_id}
        response = requests.post(f"{self.base_url}/learn", json={}, headers=headers)
        
        # Always expect 200 OK now, check the status in response
        response.raise_for_status()
        result = response.json()
        
        # Check if learning was successful or had insufficient data
        if result.get('status') == 'insufficient_data':
            return ''  # Return empty string for insufficient STM
        
        return result.get('pattern_name', '')
    
    def clear_stm(self) -> str:
        """Clear short-term memory."""
        if not self.services_available:
            pytest.skip("KATO services not available")
        
        # Use x-test-id header for isolation
        headers = {'x-test-id': self.processor_id}
        response = requests.post(f"{self.base_url}/clear-stm", json={}, headers=headers)
        
        response.raise_for_status()
        result = response.json()
        # V2 returns {"status": "cleared"}, v1 returns {"message": "stm-cleared"}
        if result.get('status') == 'cleared':
            return 'stm-cleared'
        return result.get('message', '')
    
    def clear_short_term_memory(self) -> str:
        """Alias for clear_stm for backward compatibility."""
        return self.clear_stm()
    
    def clear_all_memory(self, reset_genes: bool = True) -> str:
        """Clear all memory and optionally reset genes.
        
        Note: With user-based isolation, each test has its own database.
        This method deletes and recreates the session to clear all learned patterns.
        """
        if not self.services_available:
            pytest.skip("KATO services not available")
        
        # Use x-test-id header for isolation
        headers = {'x-test-id': self.processor_id}
        response = requests.post(f"{self.base_url}/clear-all", 
                                json={'reset_genes': reset_genes},
                                headers=headers)
        if response.status_code == 200:
            return response.json().get('message', 'all-cleared')
        
        if reset_genes:
            self.reset_genes_to_defaults()
        return 'all-cleared'
    
    def update_genes(self, genes: Dict[str, Any]) -> str:
        """Update gene values.
        
        V2 supports dynamic configuration updates through the session's user_config.
        V1 uses the global genes endpoint with processor_id.
        """
        if not self.services_available:
            pytest.skip("KATO services not available")
        
        # Use x-test-id header for isolation
        headers = {'x-test-id': self.processor_id}
        response = requests.post(
            f"{self.base_url}/genes/update",
            json={"genes": genes},
            headers=headers,
            timeout=5
        )
        if response.status_code == 200:
            result = response.json()
            return result.get('message', 'genes-updated')
        
        # Log the error but don't fail - some tests may expect this
        print(f"Warning: Failed to update genes: {response.status_code} - {response.text if hasattr(response, 'text') else ''}")
        return 'genes-update-failed'
    
    def reset_genes_to_defaults(self) -> str:
        """Reset genes to default values."""
        default_genes = {
            'max_pattern_length': 0,  # Disable auto-learning by default
            'recall_threshold': 0.1,
            'persistence': 5,
            'smoothness': 3,
        }
        return self.update_genes(default_genes)
    
    def set_recall_threshold(self, threshold: float) -> str:
        """Set the recall_threshold parameter.
        
        V2 supports dynamic configuration through the /genes/update endpoint.
        """
        if not 0.0 <= threshold <= 1.0:
            raise ValueError(f"recall_threshold must be between 0.0 and 1.0, got {threshold}")
        
        # V2 supports dynamic threshold changes via the API
        self._attempted_threshold = threshold
        return self.update_genes({"recall_threshold": threshold})
    
    def supports_dynamic_threshold(self) -> bool:
        """Check if the service supports dynamic recall threshold changes."""
        # V2 now supports dynamic threshold changes
        return True
    
    def get_status(self) -> Dict[str, Any]:
        """Get processor status."""
        if not self.services_available:
            pytest.skip("KATO services not available")
            
        # Use x-test-id header for isolation
        headers = {'x-test-id': self.processor_id}
        response = requests.get(f"{self.base_url}/status", headers=headers)
        response.raise_for_status()
        return response.json()
    
    def get_cognition_data(self) -> Dict[str, Any]:
        """Get cognition data."""
        if not self.services_available:
            pytest.skip("KATO services not available")
            
        # Use x-test-id header for isolation
        headers = {'x-test-id': self.processor_id}
        response = requests.get(f"{self.base_url}/cognition-data", headers=headers)
        response.raise_for_status()
        result = response.json()
        return result.get('cognition_data', {})
    
    def get_percept_data(self) -> Dict[str, Any]:
        """Get percept data."""
        if not self.services_available:
            pytest.skip("KATO services not available")
            
        # Use x-test-id header for isolation
        headers = {'x-test-id': self.processor_id}
        response = requests.get(f"{self.base_url}/percept-data", headers=headers)
        response.raise_for_status()
        result = response.json()
        return result.get('percept_data', {})
    
    def get_pattern(self, pattern_id: str) -> Optional[Dict]:
        """Get pattern by ID."""
        if not self.services_available:
            pytest.skip("KATO services not available")
            
        # Use x-test-id header for isolation
        headers = {'x-test-id': self.processor_id}
        response = requests.get(f"{self.base_url}/pattern/{pattern_id}", headers=headers)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        result = response.json()
        return result.get('pattern')
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get processor metrics."""
        if not self.services_available:
            pytest.skip("KATO services not available")
            
        # Use x-test-id header for isolation
        headers = {'x-test-id': self.processor_id}
        response = requests.get(f"{self.base_url}/metrics", headers=headers)
        response.raise_for_status()
        return response.json()


# Pytest fixtures
@pytest.fixture(scope="function")
def kato_fastapi_fixture(request):
    """Pytest fixture for KATO FastAPI tests with complete isolation.
    
    Each test gets its own KATO container with isolated databases.
    """
    test_name = request.node.name if hasattr(request, 'node') else 'unknown'
    fixture = KATOFastAPIFixture(processor_name=test_name, use_docker=True)
    fixture.setup()
    yield fixture
    fixture.teardown()


@pytest.fixture(scope="function")
def kato_fastapi_existing(request):
    """Pytest fixture using existing KATO FastAPI service.
    
    For development/debugging with a pre-running service.
    """
    test_name = request.node.name if hasattr(request, 'node') else 'unknown'
    fixture = KATOFastAPIFixture(processor_name=test_name, use_docker=False)
    fixture.setup()
    
    # Clear memory before test
    if fixture.services_available:
        fixture.clear_all_memory()
    
    yield fixture
    # No teardown needed for existing service


# Main test fixture - uses existing FastAPI service
@pytest.fixture(scope="function")
def kato_fixture(request):
    """Main KATO test fixture - uses existing FastAPI service.
    
    This fixture expects a running KATO service at http://localhost:8000.
    Each test gets its own unique processor_id for isolation.
    """
    test_name = request.node.name if hasattr(request, 'node') else 'unknown'
    fixture = KATOFastAPIFixture(processor_name=test_name, use_docker=False)
    fixture.setup()
    
    # Clear memory before test
    if fixture.services_available:
        fixture.clear_all_memory()
    
    yield fixture
    
    # Teardown - critical for test isolation
    fixture.teardown()