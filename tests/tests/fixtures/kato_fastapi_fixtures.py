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
import docker
from typing import Dict, Any, Optional, List
import uuid

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
        
        if use_docker:
            try:
                self.docker_client = docker.from_env()
            except docker.errors.DockerException:
                print("Warning: Docker not available, will use existing service")
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
            # Try FastAPI ports first
            for port in [8001, 8002, 8003, 8000]:
                self.base_url = f"http://localhost:{port}"
                try:
                    response = requests.get(f"{self.base_url}/health", timeout=2)
                    if response.status_code == 200:
                        self.services_available = True
                        self.port = port
                        print(f"Using existing KATO service at {self.base_url}")
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
                
    def teardown(self):
        """Clean up KATO service after testing."""
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
            
        response = requests.post(
            f"{self.base_url}/observe",
            json=data
        )
        response.raise_for_status()
        return response.json()
    
    def get_stm(self) -> List[List[str]]:
        """Get the current short-term memory."""
        if not self.services_available:
            pytest.skip("KATO services not available")
            
        response = requests.get(f"{self.base_url}/stm")
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
            
        params = {'unique_id': unique_id} if unique_id else {}
        response = requests.get(f"{self.base_url}/predictions", params=params)
        response.raise_for_status()
        result = response.json()
        return result.get('predictions', [])
    
    def learn(self) -> str:
        """Force learning of current short-term memory."""
        if not self.services_available:
            pytest.skip("KATO services not available")
            
        response = requests.post(f"{self.base_url}/learn")
        response.raise_for_status()
        result = response.json()
        return result.get('pattern_name', '')
    
    def clear_stm(self) -> str:
        """Clear short-term memory."""
        if not self.services_available:
            pytest.skip("KATO services not available")
            
        response = requests.post(f"{self.base_url}/clear-stm")
        response.raise_for_status()
        result = response.json()
        return result.get('message', '')
    
    def clear_short_term_memory(self) -> str:
        """Alias for clear_stm for backward compatibility."""
        return self.clear_stm()
    
    def clear_all_memory(self, reset_genes: bool = True) -> str:
        """Clear all memory and optionally reset genes."""
        if not self.services_available:
            pytest.skip("KATO services not available")
            
        # Reset genes if requested
        if reset_genes:
            self.reset_genes_to_defaults()
            
        response = requests.post(f"{self.base_url}/clear-all")
        response.raise_for_status()
        result = response.json()
        return result.get('message', '')
    
    def update_genes(self, genes: Dict[str, Any]) -> str:
        """Update gene values."""
        if not self.services_available:
            pytest.skip("KATO services not available")
            
        response = requests.post(
            f"{self.base_url}/genes/update",
            json={"genes": genes}
        )
        response.raise_for_status()
        result = response.json()
        return result.get('message', '')
    
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
        """Set the recall_threshold parameter."""
        if not 0.0 <= threshold <= 1.0:
            raise ValueError(f"recall_threshold must be between 0.0 and 1.0, got {threshold}")
        return self.update_genes({"recall_threshold": threshold})
    
    def get_status(self) -> Dict[str, Any]:
        """Get processor status."""
        if not self.services_available:
            pytest.skip("KATO services not available")
            
        response = requests.get(f"{self.base_url}/status")
        response.raise_for_status()
        return response.json()
    
    def get_cognition_data(self) -> Dict[str, Any]:
        """Get cognition data."""
        if not self.services_available:
            pytest.skip("KATO services not available")
            
        response = requests.get(f"{self.base_url}/cognition-data")
        response.raise_for_status()
        result = response.json()
        return result.get('cognition_data', {})
    
    def get_percept_data(self) -> Dict[str, Any]:
        """Get percept data."""
        if not self.services_available:
            pytest.skip("KATO services not available")
            
        response = requests.get(f"{self.base_url}/percept-data")
        response.raise_for_status()
        result = response.json()
        return result.get('percept_data', {})
    
    def get_pattern(self, pattern_id: str) -> Optional[Dict]:
        """Get pattern by ID."""
        if not self.services_available:
            pytest.skip("KATO services not available")
            
        response = requests.get(f"{self.base_url}/pattern/{pattern_id}")
        if response.status_code == 404:
            return None
        response.raise_for_status()
        result = response.json()
        return result.get('pattern')
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get processor metrics."""
        if not self.services_available:
            pytest.skip("KATO services not available")
            
        response = requests.get(f"{self.base_url}/metrics")
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


# Backward compatibility wrapper
@pytest.fixture(scope="function")
def kato_fixture(request):
    """Backward compatible fixture that uses FastAPI backend.
    
    This allows existing tests to work with the new architecture.
    """
    # Check if we should use FastAPI (new) or REST/ZMQ (old)
    use_fastapi = os.environ.get('USE_FASTAPI', 'true').lower() == 'true'
    
    if use_fastapi:
        # Use new FastAPI fixture
        test_name = request.node.name if hasattr(request, 'node') else 'unknown'
        fixture = KATOFastAPIFixture(processor_name=test_name, use_docker=False)
        fixture.setup()
        
        # Clear memory before test
        if fixture.services_available:
            fixture.clear_all_memory()
        
        yield fixture
    else:
        # Fall back to old fixture (import it)
        from kato_fixtures import KATOTestFixture
        fixture = KATOTestFixture(processor_name=request.node.name)
        fixture.setup()
        yield fixture
        fixture.teardown()