"""
Modified fixtures for running tests in a container.
Detects container environment and adjusts behavior accordingly.
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
    """Base fixture for KATO tests that works in container environment."""
    
    def __init__(self, processor_name: str = "P1"):
        self.processor_name = processor_name
        self.processor_id = self._generate_processor_id()
        
        # Check if we're running in a container
        self.in_container = os.environ.get('KATO_TEST_MODE') == 'container'
        
        # Use the appropriate URL based on environment
        if self.in_container:
            # When in container with --network host, localhost works
            self.base_url = os.environ.get('KATO_API_URL', 'http://localhost:8000')
        else:
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
        """Start KATO or connect to existing instance."""
        # First check if KATO is already running
        try:
            response = requests.get(f"{self.base_url}/kato-api/ping", timeout=5)
            if response.status_code == 200:
                # KATO is already running, just wait for it to be ready
                self._wait_for_ready()
                self.is_running = True
                return
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            if self.in_container:
                # In container mode, KATO should already be running on the host
                raise RuntimeError(
                    f"Cannot connect to KATO at {self.base_url}. "
                    f"Make sure KATO is running on the host before running tests. "
                    f"Error: {e}"
                )
            pass
        
        # If we're in a container, we can't start KATO
        if self.in_container:
            raise RuntimeError(
                "KATO is not running and cannot be started from within the test container. "
                "Please start KATO on the host using: ./kato-manager.sh start"
            )
        
        # Not in container, try to start KATO normally
        env = os.environ.copy()
        env['PROCESSOR_ID'] = self.processor_id
        env['PROCESSOR_NAME'] = self.processor_name
        env['KATO_ZMQ_IMPLEMENTATION'] = 'improved'
        
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
        # In container mode, never stop KATO (it's running on the host)
        if self.in_container:
            return
            
        # Only stop if we started the process
        if self.is_running and hasattr(self, 'process') and self.process:
            kato_manager = os.path.join(os.path.dirname(__file__), '../../../kato-manager.sh')
            stop_cmd = [kato_manager, 'stop']
            subprocess.run(stop_cmd, capture_output=True, text=True)
            self.is_running = False
            
    def _wait_for_ready(self, timeout: int = 30):
        """Wait for KATO to be ready to accept requests."""
        start_time = time.time()
        last_error = None
        
        while time.time() - start_time < timeout:
            try:
                response = requests.get(f"{self.base_url}/kato-api/ping", timeout=2)
                if response.status_code == 200:
                    # Also try a processor ping to ensure it's fully ready
                    processor_response = requests.post(
                        f"{self.base_url}/kato-api/ping",
                        json={"processor_name": self.processor_name},
                        timeout=2
                    )
                    if processor_response.status_code == 200:
                        return
            except Exception as e:
                last_error = e
                
            time.sleep(1)
            
        raise TimeoutError(f"KATO failed to become ready within {timeout} seconds. Last error: {last_error}")
        
    def observe(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Send observation to KATO."""
        response = requests.post(
            f"{self.base_url}/kato-api/observe",
            json=data
        )
        response.raise_for_status()
        return response.json()
        
    def predict(self, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Get predictions from KATO."""
        if data is None:
            response = requests.get(f"{self.base_url}/kato-api/predictions")
        else:
            response = requests.post(f"{self.base_url}/kato-api/predictions", json=data)
        response.raise_for_status()
        return response.json()
        
    def learn(self) -> Dict[str, Any]:
        """Trigger learning in KATO."""
        response = requests.post(f"{self.base_url}/kato-api/learn", json={})
        response.raise_for_status()
        return response.json()
        
    def clear_working_memory(self) -> Dict[str, Any]:
        """Clear working memory."""
        response = requests.post(f"{self.base_url}/kato-api/clear-working-memory", json={})
        response.raise_for_status()
        return response.json()
        
    def clear_all_memory(self) -> Dict[str, Any]:
        """Clear all memory."""
        response = requests.post(f"{self.base_url}/kato-api/clear-all-memory", json={})
        response.raise_for_status()
        return response.json()


@pytest.fixture
def kato_fixture():
    """Pytest fixture for KATO tests."""
    kato = KATOTestFixture()
    kato.setup()
    yield kato
    kato.teardown()


@pytest.fixture
def kato_p1():
    """Pytest fixture for KATO with P1 processor."""
    kato = KATOTestFixture(processor_name="P1")
    kato.setup()
    yield kato
    kato.teardown()


@pytest.fixture
def kato_p2():
    """Pytest fixture for KATO with P2 processor."""
    kato = KATOTestFixture(processor_name="P2")
    kato.setup()
    yield kato
    kato.teardown()