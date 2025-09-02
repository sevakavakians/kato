"""
Base fixtures for KATO tests.
Provides common setup and teardown functionality.
"""

import os
import sys
import time
import json
import subprocess
import requests
import pytest
from typing import Dict, Any, Optional

# Add parent directories to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))


class KATOTestFixture:
    """Base fixture for KATO tests."""
    
    def __init__(self, processor_name: str = "P1"):
        self.processor_name = processor_name
        
        # Check if we're in container mode and have a processor ID
        if os.environ.get('KATO_TEST_MODE') == 'container' and os.environ.get('KATO_PROCESSOR_ID'):
            self.processor_id = os.environ.get('KATO_PROCESSOR_ID')
        else:
            self.processor_id = self._generate_processor_id()
            
        # Use KATO_API_URL from environment if available, otherwise default to port 8000
        self.base_url = os.environ.get('KATO_API_URL', 'http://localhost:8000')
        self.process = None
        self.is_running = False
        self.services_available = False
        
    def _generate_processor_id(self) -> str:
        """Generate a unique processor ID for complete test isolation.
        
        Each test gets a unique ID to ensure MongoDB, Qdrant, and Redis
        databases are completely isolated, preventing cross-contamination.
        """
        import uuid
        import time
        # Generate unique ID: test_{name}_{timestamp}_{uuid}
        # This ensures complete database isolation per test
        timestamp = int(time.time() * 1000)  # Millisecond precision
        unique = str(uuid.uuid4())[:8]  # Short UUID suffix
        # Clean processor name for use in ID
        clean_name = self.processor_name.replace(' ', '_').replace('-', '_').lower()
        return f"test_{clean_name}_{timestamp}_{unique}"
    
    def _check_services_available(self) -> bool:
        """Check if KATO services are available."""
        try:
            # Try to connect to the API
            response = requests.get(f"{self.base_url}/kato-api/ping", timeout=2)
            return response.status_code == 200
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            return False
        
    def setup(self):
        """Start KATO with the specified genome or use existing instance."""
        # First check if services are available
        self.services_available = self._check_services_available()
        
        if not self.services_available:
            print("\n" + "="*60)
            print("WARNING: KATO services are not running!")
            print("Tests requiring KATO will be skipped.")
            print("To run KATO-dependent tests, start services with:")
            print("  ./test-harness.sh start-services")
            print("Or run tests with automatic service management:")
            print("  ./test-harness.sh test")
            print("="*60 + "\n")
            self.is_running = False
            return
        
        # Check if we're running in a test container
        in_container = os.environ.get('KATO_TEST_MODE') == 'container'
        
        # If we're in a container, KATO should already be running externally
        if in_container:
            print(f"Running in container mode - using processor ID: {self.processor_id}")
            # Don't try to start KATO, just verify it's accessible
            try:
                # Quick check that API is accessible
                response = requests.get(f"{self.base_url}/kato-api/ping", timeout=5)
                if response.status_code == 200:
                    self.is_running = True
                    # Verify processor is accessible
                    proc_response = requests.get(f"{self.base_url}/{self.processor_id}/ping", timeout=5)
                    if proc_response.status_code == 200:
                        return  # Everything is ready
                    else:
                        print(f"Warning: Processor {self.processor_id} not responding")
                        # Try to get actual processor ID from connect endpoint
                        self._update_processor_id()
                        return
            except Exception as e:
                print(f"Warning: Could not connect to KATO API: {e}")
                # Continue anyway, tests will fail if API is truly inaccessible
            self.is_running = True
            return
        
        # Not in container - check if KATO is already running
        try:
            response = requests.get(f"{self.base_url}/kato-api/ping", timeout=2)
            if response.status_code == 200:
                # KATO is already running, just wait for it to be ready
                self._wait_for_ready()
                self.is_running = True
                return
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            pass
        
        # KATO is not running and we're not in a container, try to start it
        env = os.environ.copy()
        env['PROCESSOR_ID'] = self.processor_id
        env['PROCESSOR_NAME'] = self.processor_name
        env['KATO_ZMQ_IMPLEMENTATION'] = 'improved'
        
        # Start KATO using the manager script
        kato_manager = os.path.join(os.path.dirname(__file__), '../../../kato-manager.sh')
        
        # Check if kato-manager.sh exists
        if not os.path.exists(kato_manager):
            raise FileNotFoundError(f"kato-manager.sh not found at {kato_manager}. "
                                    "Make sure KATO is running before running tests.")
        
        # Check if we need to build (only if image doesn't exist)
        check_image = subprocess.run(
            ['docker', 'images', '-q', 'kato:latest'],
            capture_output=True,
            text=True
        )
        
        if not check_image.stdout.strip():
            # Build the Docker image
            build_cmd = [kato_manager, 'build']
            result = subprocess.run(build_cmd, capture_output=True, text=True)
            if result.returncode != 0:
                # Try without building if it fails
                print(f"Warning: Build failed, attempting to use existing setup: {result.stderr}")
        
        # Start KATO
        start_cmd = [kato_manager, 'start', self.processor_id]
            
        self.process = subprocess.Popen(
            start_cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Wait for KATO to be ready
        self._wait_for_ready()
        self.is_running = True
        
    def teardown(self):
        """Stop KATO if we started it."""
        # Check if we're running in a test container
        in_container = os.environ.get('KATO_TEST_MODE') == 'container'
        
        # Don't try to stop KATO if we're in a container (it's managed externally)
        if in_container:
            return
            
        # Only stop if we started the process
        if self.is_running and hasattr(self, 'process') and self.process:
            kato_manager = os.path.join(os.path.dirname(__file__), '../../../kato-manager.sh')
            if os.path.exists(kato_manager):
                stop_cmd = [kato_manager, 'stop']
                subprocess.run(stop_cmd, capture_output=True, text=True)
            self.is_running = False
            
    def _update_processor_id(self):
        """Update processor ID from connect endpoint."""
        try:
            connect_response = requests.get(f"{self.base_url}/connect", timeout=5)
            if connect_response.status_code == 200:
                connect_data = connect_response.json()
                if 'genome' in connect_data and 'id' in connect_data['genome']:
                    self.processor_id = connect_data['genome']['id']
                    print(f"Updated processor ID to: {self.processor_id}")
        except Exception as e:
            print(f"Could not update processor ID: {e}")
    
    def _wait_for_ready(self, timeout: int = 30):
        """Wait for KATO to be ready to accept requests."""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                # Phase 1: Check if API gateway is responding
                response = requests.get(f"{self.base_url}/kato-api/ping")
                if response.status_code == 200:
                    # Get the actual processor ID from the running instance
                    connect_response = requests.get(f"{self.base_url}/connect")
                    if connect_response.status_code == 200:
                        connect_data = connect_response.json()
                        if 'genome' in connect_data and 'id' in connect_data['genome']:
                            actual_processor_id = connect_data['genome']['id']
                            # Update our processor_id to match the running instance
                            self.processor_id = actual_processor_id
                            
                    # Phase 2: Check if processor is responding with actual ID
                    response = requests.get(f"{self.base_url}/{self.processor_id}/ping")
                    if response.status_code == 200:
                        # Phase 3: Try a simple operation
                        response = requests.post(
                            f"{self.base_url}/{self.processor_id}/clear-short-term-memory",
                            json={}
                        )
                        if response.status_code == 200:
                            return  # KATO is ready
            except requests.exceptions.ConnectionError:
                pass
                
            time.sleep(1)
            
        raise TimeoutError(f"KATO did not start within {timeout} seconds")
        
    def connect(self) -> Dict[str, Any]:
        """Connect to KATO and return connection info."""
        if not self.services_available:
            pytest.skip("KATO services not available")
        response = requests.get(f"{self.base_url}/connect")
        response.raise_for_status()
        return response.json()
        
    def observe(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Send an observation to KATO."""
        if not self.services_available:
            pytest.skip("KATO services not available")
        response = requests.post(
            f"{self.base_url}/{self.processor_id}/observe",
            json=data
        )
        response.raise_for_status()
        result = response.json()
        return result.get('message', {})
        
    def get_short_term_memory(self) -> list:
        """Get the current short-term memory."""
        if not self.services_available:
            pytest.skip("KATO services not available")
        response = requests.get(f"{self.base_url}/{self.processor_id}/short-term-memory")
        response.raise_for_status()
        result = response.json()
        return result.get('message', [])
    
    def get_working_memory(self) -> list:
        """Get the current working memory (now called short-term memory)."""
        if not self.services_available:
            pytest.skip("KATO services not available")
        response = requests.get(f"{self.base_url}/{self.processor_id}/short-term-memory")
        response.raise_for_status()
        result = response.json()
        return result.get('message', [])
        
    def get_predictions(self) -> list:
        """Get current predictions."""
        if not self.services_available:
            pytest.skip("KATO services not available")
        response = requests.get(f"{self.base_url}/{self.processor_id}/predictions")
        response.raise_for_status()
        result = response.json()
        return result.get('message', [])
        
    def reset_genes_to_defaults(self) -> str:
        """Reset gene values to their defaults."""
        if not self.services_available:
            return "Services not available"
        default_genes = {
            'max_pattern_length': 0,  # Disable auto-learning by default
        }
        return self.update_genes(default_genes)
    
    def clear_all_memory(self, reset_genes: bool = True) -> str:
        """Clear all memory and optionally reset genes to defaults for test isolation."""
        if not self.services_available:
            pytest.skip("KATO services not available")
        # Reset genes to defaults only if requested (default: True for backward compatibility)
        if reset_genes:
            self.reset_genes_to_defaults()
        
        response = requests.post(
            f"{self.base_url}/{self.processor_id}/clear-all-memory",
            json={}
        )
        response.raise_for_status()
        result = response.json()
        return result.get('message', '')
        
    def clear_short_term_memory(self) -> str:
        """Clear short-term memory."""
        if not self.services_available:
            pytest.skip("KATO services not available")
        response = requests.post(
            f"{self.base_url}/{self.processor_id}/clear-short-term-memory",
            json={}
        )
        response.raise_for_status()
        result = response.json()
        return result.get('message', '')
    
    def clear_working_memory(self) -> str:
        """Clear working memory (now called short-term memory)."""
        if not self.services_available:
            pytest.skip("KATO services not available")
        response = requests.post(
            f"{self.base_url}/{self.processor_id}/clear-short-term-memory",
            json={}
        )
        response.raise_for_status()
        result = response.json()
        return result.get('message', '')
        
    def learn(self) -> str:
        """Force learning of current working memory."""
        if not self.services_available:
            pytest.skip("KATO services not available")
        response = requests.post(
            f"{self.base_url}/{self.processor_id}/learn",
            json={}
        )
        response.raise_for_status()
        result = response.json()
        return result.get('message', '')
        
    def get_status(self) -> Dict[str, Any]:
        """Get processor status."""
        if not self.services_available:
            pytest.skip("KATO services not available")
        response = requests.get(f"{self.base_url}/{self.processor_id}/status")
        response.raise_for_status()
        result = response.json()
        return result.get('message', {})
        
    def get_cognition_data(self) -> Dict[str, Any]:
        """Get cognition data."""
        if not self.services_available:
            pytest.skip("KATO services not available")
        response = requests.get(f"{self.base_url}/{self.processor_id}/cognition-data")
        response.raise_for_status()
        result = response.json()
        return result.get('message', {})
        
    def get_percept_data(self) -> Dict[str, Any]:
        """Get percept data."""
        if not self.services_available:
            pytest.skip("KATO services not available")
        response = requests.get(f"{self.base_url}/{self.processor_id}/percept-data")
        response.raise_for_status()
        result = response.json()
        return result.get('message', {})
        
    def update_genes(self, genes: Dict[str, Any]) -> str:
        """Update gene values."""
        if not self.services_available:
            pytest.skip("KATO services not available")
        response = requests.post(
            f"{self.base_url}/{self.processor_id}/genes/change",
            json={"data": genes}
        )
        response.raise_for_status()
        result = response.json()
        return result.get('message', '')
    
    def set_recall_threshold(self, threshold: float) -> str:
        """Set the recall_threshold parameter.
        
        Args:
            threshold: Value between 0.0 and 1.0
            
        Returns:
            Response message from the API
        """
        if not 0.0 <= threshold <= 1.0:
            raise ValueError(f"recall_threshold must be between 0.0 and 1.0, got {threshold}")
        return self.update_genes({"recall_threshold": threshold})


@pytest.fixture(scope="function")
def kato_fixture(request):
    """Pytest fixture for KATO tests with complete isolation.
    
    Scope is 'function' to ensure each test gets its own KATO instance
    with isolated MongoDB, Qdrant, and Redis databases.
    """
    # Get test name for better debugging
    test_name = request.node.name if hasattr(request, 'node') else 'unknown'
    fixture = KATOTestFixture(processor_name=test_name)
    fixture.setup()
    yield fixture
    fixture.teardown()


@pytest.fixture(scope="function")
def kato_with_genome(request):
    """Factory fixture for creating KATO instances with isolation.
    
    Each created instance gets a unique processor_id for complete
    database isolation (MongoDB, Qdrant, Redis).
    """
    fixtures = []
    
    def _create_fixture(genome_file: str = None, processor_name: str = "P1"):
        # genome_file parameter kept for compatibility but ignored
        fixture = KATOTestFixture(processor_name)
        fixture.setup()
        # Reset genes to defaults for test isolation
        fixture.reset_genes_to_defaults()
        fixtures.append(fixture)
        return fixture
    
    yield _create_fixture
    
    # Cleanup all fixtures
    for fixture in fixtures:
        # Reset genes before teardown for next test module
        try:
            fixture.reset_genes_to_defaults()
        except:
            pass  # Ignore errors if system is already shutting down
        fixture.teardown()