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
        self.session_id = None  # V2 session ID for isolation
        self.session_created = False  # Track if session has been created
        
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
                    # Check if v2 service is running (v2 uses /health not /v2/health)
                    response = requests.get(f"{self.base_url}/health", timeout=2)
                    if response.status_code == 200:
                        # Verify it's a v2 service by checking for v2-specific fields
                        health_data = response.json()
                        if "base_processor_id" in health_data or "active_sessions" in health_data:
                            self.services_available = True
                            self.port = port
                            print(f"Using existing KATO v2 service at {self.base_url}")
                            # Create a persistent session for this test
                            self._ensure_session()
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
        """Ensure a v2 session exists for this test."""
        if not self.session_created and self.services_available:
            user_id = self.processor_id
            session_data = {
                "user_id": user_id,
                "metadata": {"test_name": self.processor_name, "type": "test"}
            }
            try:
                session_resp = requests.post(f"{self.base_url}/v2/sessions", json=session_data)
                session_resp.raise_for_status()
                self.session_id = session_resp.json()["session_id"]
                self.session_created = True
            except Exception as e:
                print(f"Warning: Could not create v2 session: {e}")
                self.session_created = False
                
    def teardown(self):
        """Clean up KATO service after testing."""
        # Clean up v2 session if created
        if self.session_created and self.session_id and self.services_available:
            try:
                requests.delete(f"{self.base_url}/v2/sessions/{self.session_id}")
            except:
                pass  # Ignore cleanup errors
        
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
        
        # Ensure we have a persistent session
        self._ensure_session()
        
        if not self.session_id:
            pytest.skip("Could not create v2 session")
        
        # Use session-based endpoint with persistent session
        response = requests.post(f"{self.base_url}/v2/sessions/{self.session_id}/observe", json=data)
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
            'processor_id': result.get('processor_id'),
            'time': result.get('time'),
            'unique_id': result.get('unique_id')
        }
    
    def get_stm(self) -> List[List[str]]:
        """Get the current short-term memory."""
        if not self.services_available:
            pytest.skip("KATO services not available")
        
        # Ensure we have the same persistent session
        self._ensure_session()
        
        if not self.session_id:
            pytest.skip("Could not create v2 session")
        
        response = requests.get(f"{self.base_url}/v2/sessions/{self.session_id}/stm")
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
        
        # Use direct endpoint
        params = {'unique_id': unique_id} if unique_id else {}
        # Ensure we have the same persistent session
        self._ensure_session()
        
        if not self.session_id:
            pytest.skip("Could not create v2 session")
        
        response = requests.get(f"{self.base_url}/v2/sessions/{self.session_id}/predictions", params=params)
        response.raise_for_status()
        result = response.json()
        return result.get('predictions', [])
    
    def learn(self) -> str:
        """Force learning of current short-term memory."""
        if not self.services_available:
            pytest.skip("KATO services not available")
        
        # Ensure we have the same persistent session
        self._ensure_session()
        
        if not self.session_id:
            pytest.skip("Could not create v2 session")
        
        response = requests.post(f"{self.base_url}/v2/sessions/{self.session_id}/learn")
        
        # In v2, learning empty STM returns 400 error
        # For compatibility, return empty string when learning fails
        if response.status_code == 400:
            # Check if it's due to insufficient data
            try:
                error_data = response.json()
                if 'insufficient' in str(error_data).lower() or 'empty' in str(error_data).lower():
                    return ''  # Return empty string for empty/insufficient STM
            except:
                pass
        
        response.raise_for_status()
        result = response.json()
        return result.get('pattern_name', '')
    
    def clear_stm(self) -> str:
        """Clear short-term memory."""
        if not self.services_available:
            pytest.skip("KATO services not available")
        
        # Ensure we have the same persistent session
        self._ensure_session()
        
        if not self.session_id:
            pytest.skip("Could not create v2 session")
        
        response = requests.post(f"{self.base_url}/v2/sessions/{self.session_id}/clear-stm")
        response.raise_for_status()
        result = response.json()
        # V2 returns {"status": "cleared"}, v1 tests expect 'stm-cleared'
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
        
        # v2 doesn't have a global clear-all endpoint - each user has isolated databases
        # Delete the current session and create a new one to clear all memory including patterns
        if self.session_created and self.session_id:
            try:
                # Delete the session (this clears all data for this user)
                requests.delete(f"{self.base_url}/v2/sessions/{self.session_id}")
            except:
                pass  # Ignore errors
            
            # Reset session tracking
            self.session_id = None
            self.session_created = False
        
        # Create a fresh session with a new user_id to ensure complete isolation
        # This gives us a completely clean slate with no learned patterns
        self.processor_id = self._generate_processor_id()  # Generate new ID for complete reset
        self._ensure_session()
        
        if reset_genes:
            self.reset_genes_to_defaults()
        return 'all-cleared'
    
    def update_genes(self, genes: Dict[str, Any]) -> str:
        """Update gene values.
        
        Note: In v2, genes are set when processor is created.
        This method is kept for compatibility but does nothing.
        """
        if not self.services_available:
            pytest.skip("KATO services not available")
        
        # In v2, genes are configured when the processor is created
        # per user. No dynamic gene updates.
        return 'genes-not-updateable-in-v2'
    
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
        
        Note: In v2, this is not dynamically configurable and will be ignored.
        Tests that rely on dynamic threshold changes should be skipped.
        """
        if not 0.0 <= threshold <= 1.0:
            raise ValueError(f"recall_threshold must be between 0.0 and 1.0, got {threshold}")
        
        # In v2, this doesn't actually change the threshold
        # Store the attempted value for tests to check
        self._attempted_threshold = threshold
        return self.update_genes({"recall_threshold": threshold})
    
    def supports_dynamic_threshold(self) -> bool:
        """Check if the service supports dynamic recall threshold changes."""
        # V2 does not support dynamic threshold changes
        return False
    
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