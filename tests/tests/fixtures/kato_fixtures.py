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
    
    def __init__(self, genome_file: Optional[str] = None, processor_name: str = "P1"):
        self.genome_file = genome_file or "test-genomes/simple.genome"
        self.processor_name = processor_name
        self.processor_id = self._generate_processor_id()
        self.base_url = "http://localhost:8000"
        self.process = None
        self.is_running = False
        
    def _generate_processor_id(self) -> str:
        """Generate a processor ID based on the processor name."""
        # Use a deterministic ID for testing
        import hashlib
        hash_obj = hashlib.md5(self.processor_name.encode())
        return f"p{hash_obj.hexdigest()[:10]}"
        
    def setup(self):
        """Start KATO with the specified genome or use existing instance."""
        # First check if KATO is already running
        try:
            response = requests.get(f"{self.base_url}/kato-api/ping", timeout=2)
            if response.status_code == 200:
                # KATO is already running, just wait for it to be ready
                self._wait_for_ready()
                self.is_running = True
                return
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            pass
        
        # KATO is not running, try to start it
        env = os.environ.copy()
        env['PROCESSOR_ID'] = self.processor_id
        env['PROCESSOR_NAME'] = self.processor_name
        
        # Start KATO using the manager script
        kato_manager = os.path.join(os.path.dirname(__file__), '../../../kato-manager.sh')
        
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
        
        # Start KATO with the genome
        start_cmd = [kato_manager, 'start', self.processor_id]
        if self.genome_file:
            start_cmd.extend(['-g', self.genome_file])
            
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
        # Only stop if we started the process
        if self.is_running and hasattr(self, 'process') and self.process:
            kato_manager = os.path.join(os.path.dirname(__file__), '../../../kato-manager.sh')
            stop_cmd = [kato_manager, 'stop']
            subprocess.run(stop_cmd, capture_output=True, text=True)
            self.is_running = False
            
    def _wait_for_ready(self, timeout: int = 30):
        """Wait for KATO to be ready to accept requests."""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                # Phase 1: Check if API gateway is responding
                response = requests.get(f"{self.base_url}/kato-api/ping")
                if response.status_code == 200:
                    # Phase 2: Check if processor is responding
                    response = requests.get(f"{self.base_url}/{self.processor_id}/ping")
                    if response.status_code == 200:
                        # Phase 3: Try a simple operation
                        response = requests.post(
                            f"{self.base_url}/{self.processor_id}/clear-working-memory",
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
        response = requests.get(f"{self.base_url}/connect")
        response.raise_for_status()
        return response.json()
        
    def observe(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Send an observation to KATO."""
        response = requests.post(
            f"{self.base_url}/{self.processor_id}/observe",
            json=data
        )
        response.raise_for_status()
        result = response.json()
        return result.get('message', {})
        
    def get_working_memory(self) -> list:
        """Get the current working memory."""
        response = requests.get(f"{self.base_url}/{self.processor_id}/working-memory")
        response.raise_for_status()
        result = response.json()
        return result.get('message', [])
        
    def get_predictions(self) -> list:
        """Get current predictions."""
        response = requests.get(f"{self.base_url}/{self.processor_id}/predictions")
        response.raise_for_status()
        result = response.json()
        return result.get('message', [])
        
    def clear_all_memory(self) -> str:
        """Clear all memory."""
        response = requests.post(
            f"{self.base_url}/{self.processor_id}/clear-all-memory",
            json={}
        )
        response.raise_for_status()
        result = response.json()
        return result.get('message', '')
        
    def clear_working_memory(self) -> str:
        """Clear working memory."""
        response = requests.post(
            f"{self.base_url}/{self.processor_id}/clear-working-memory",
            json={}
        )
        response.raise_for_status()
        result = response.json()
        return result.get('message', '')
        
    def learn(self) -> str:
        """Force learning of current working memory."""
        response = requests.post(
            f"{self.base_url}/{self.processor_id}/learn",
            json={}
        )
        response.raise_for_status()
        result = response.json()
        return result.get('message', '')
        
    def get_status(self) -> Dict[str, Any]:
        """Get processor status."""
        response = requests.get(f"{self.base_url}/{self.processor_id}/status")
        response.raise_for_status()
        result = response.json()
        return result.get('message', {})
        
    def get_cognition_data(self) -> Dict[str, Any]:
        """Get cognition data."""
        response = requests.get(f"{self.base_url}/{self.processor_id}/cognition-data")
        response.raise_for_status()
        result = response.json()
        return result.get('message', {})
        
    def get_percept_data(self) -> Dict[str, Any]:
        """Get percept data."""
        response = requests.get(f"{self.base_url}/{self.processor_id}/percept-data")
        response.raise_for_status()
        result = response.json()
        return result.get('message', {})


@pytest.fixture(scope="module")
def kato_fixture():
    """Pytest fixture for KATO tests."""
    fixture = KATOTestFixture()
    fixture.setup()
    yield fixture
    fixture.teardown()


@pytest.fixture(scope="module")
def kato_with_genome():
    """Factory fixture for creating KATO instances with specific genomes."""
    fixtures = []
    
    def _create_fixture(genome_file: str, processor_name: str = "P1"):
        fixture = KATOTestFixture(genome_file, processor_name)
        fixture.setup()
        fixtures.append(fixture)
        return fixture
    
    yield _create_fixture
    
    # Cleanup all fixtures
    for fixture in fixtures:
        fixture.teardown()