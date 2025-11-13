# Python Client Guide

Build robust Python clients for interacting with KATO API.

## Basic Client

### Minimal Implementation

```python
import requests
from typing import Optional, Dict, List, Any

class KATOClient:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url.rstrip('/')
        self.session_id: Optional[str] = None

    def create_session(
        self,
        node_id: str,
        config: Optional[Dict] = None,
        ttl: Optional[int] = None
    ) -> str:
        """Create a new KATO session."""
        payload = {"node_id": node_id}
        if config:
            payload["config"] = config
        if ttl:
            payload["ttl"] = ttl

        response = requests.post(
            f"{self.base_url}/sessions",
            json=payload
        )
        response.raise_for_status()

        data = response.json()
        self.session_id = data['session_id']
        return self.session_id

    def observe(
        self,
        strings: List[str],
        vectors: Optional[List[List[float]]] = None,
        emotives: Optional[Dict[str, float]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict:
        """Send an observation to KATO."""
        if not self.session_id:
            raise ValueError("No active session. Call create_session() first.")

        payload = {
            "strings": strings,
            "vectors": vectors or [],
            "emotives": emotives or {},
            "metadata": metadata or {}
        }

        response = requests.post(
            f"{self.base_url}/sessions/{self.session_id}/observe",
            json=payload
        )
        response.raise_for_status()
        return response.json()

    def learn(self) -> Dict:
        """Trigger pattern learning from STM."""
        if not self.session_id:
            raise ValueError("No active session")

        response = requests.post(
            f"{self.base_url}/sessions/{self.session_id}/learn"
        )
        response.raise_for_status()
        return response.json()

    def get_predictions(self) -> Dict:
        """Get predictions based on current STM."""
        if not self.session_id:
            raise ValueError("No active session")

        response = requests.get(
            f"{self.base_url}/sessions/{self.session_id}/predictions"
        )
        response.raise_for_status()
        return response.json()

    def clear_stm(self) -> Dict:
        """Clear short-term memory."""
        if not self.session_id:
            raise ValueError("No active session")

        response = requests.post(
            f"{self.base_url}/sessions/{self.session_id}/clear-stm"
        )
        response.raise_for_status()
        return response.json()

    def get_stm(self) -> Dict:
        """Get current short-term memory."""
        if not self.session_id:
            raise ValueError("No active session")

        response = requests.get(
            f"{self.base_url}/sessions/{self.session_id}/stm"
        )
        response.raise_for_status()
        return response.json()
```

### Usage Example

```python
# Create client
kato = KATOClient()

# Create session
kato.create_session(
    node_id="my_app",
    config={"recall_threshold": 0.3}
)

# Send observations
kato.observe(["morning", "coffee"])
kato.observe(["work", "coding"])
kato.observe(["evening", "relax"])

# Learn pattern
pattern = kato.learn()
print(f"Learned: {pattern['pattern_name']}")

# Test recall
kato.clear_stm()
kato.observe(["morning", "coffee"])
predictions = kato.get_predictions()
print(f"Predicted: {predictions['predictions'][0]['future']}")
```

## Production Client

### Full Implementation with Error Handling

```python
import requests
from typing import Optional, Dict, List, Any
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class KATOError(Exception):
    """Base exception for KATO client errors."""
    pass

class KATOAPIError(KATOError):
    """API request failed."""
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(f"HTTP {status_code}: {message}")

class KATOSessionError(KATOError):
    """Session-related error."""
    pass

class KATOClient:
    """Production-ready KATO client with error handling and retry logic."""

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        timeout: int = 30,
        max_retries: int = 3
    ):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.max_retries = max_retries
        self.session_id: Optional[str] = None
        self.node_id: Optional[str] = None
        self.session = requests.Session()

    def _request(
        self,
        method: str,
        endpoint: str,
        **kwargs
    ) -> requests.Response:
        """Make HTTP request with retry logic."""
        url = f"{self.base_url}{endpoint}"
        kwargs.setdefault('timeout', self.timeout)

        for attempt in range(self.max_retries):
            try:
                response = self.session.request(method, url, **kwargs)

                if response.status_code == 404:
                    # Session expired or not found
                    if self.session_id and 'sessions' in endpoint:
                        raise KATOSessionError(
                            f"Session {self.session_id} expired or not found"
                        )

                response.raise_for_status()
                return response

            except requests.HTTPError as e:
                if e.response.status_code >= 500:
                    # Server error - retry
                    logger.warning(
                        f"Attempt {attempt + 1}/{self.max_retries} failed: {e}"
                    )
                    if attempt == self.max_retries - 1:
                        raise KATOAPIError(
                            e.response.status_code,
                            e.response.text
                        )
                else:
                    # Client error - don't retry
                    raise KATOAPIError(
                        e.response.status_code,
                        e.response.text
                    )
            except requests.RequestException as e:
                logger.error(f"Request failed: {e}")
                if attempt == self.max_retries - 1:
                    raise KATOError(f"Request failed after {self.max_retries} attempts")

    def create_session(
        self,
        node_id: str,
        config: Optional[Dict] = None,
        ttl: Optional[int] = None,
        auto_reconnect: bool = True
    ) -> str:
        """Create a new KATO session.

        Args:
            node_id: Permanent identifier for pattern storage
            config: Session configuration overrides
            ttl: Session timeout in seconds
            auto_reconnect: Auto-reconnect on session expiry

        Returns:
            session_id: Session identifier
        """
        payload = {"node_id": node_id}
        if config:
            payload["config"] = config
        if ttl:
            payload["ttl"] = ttl

        response = self._request('POST', '/sessions', json=payload)
        data = response.json()

        self.session_id = data['session_id']
        self.node_id = node_id

        logger.info(
            f"Created session {self.session_id} for node {node_id}"
        )
        return self.session_id

    def reconnect(self) -> str:
        """Reconnect to KATO with same node_id."""
        if not self.node_id:
            raise KATOSessionError("Cannot reconnect - no previous node_id")

        logger.info(f"Reconnecting to node {self.node_id}")
        return self.create_session(self.node_id)

    def observe(
        self,
        strings: List[str],
        vectors: Optional[List[List[float]]] = None,
        emotives: Optional[Dict[str, float]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        auto_reconnect: bool = True
    ) -> Dict:
        """Send an observation to KATO."""
        if not self.session_id:
            raise KATOSessionError("No active session")

        payload = {
            "strings": strings,
            "vectors": vectors or [],
            "emotives": emotives or {},
            "metadata": metadata or {}
        }

        try:
            response = self._request(
                'POST',
                f'/sessions/{self.session_id}/observe',
                json=payload
            )
            return response.json()
        except KATOSessionError:
            if auto_reconnect and self.node_id:
                logger.warning("Session expired - reconnecting")
                self.reconnect()
                return self.observe(
                    strings, vectors, emotives, metadata,
                    auto_reconnect=False  # Prevent infinite loop
                )
            raise

    def learn(self, auto_reconnect: bool = True) -> Dict:
        """Trigger pattern learning."""
        if not self.session_id:
            raise KATOSessionError("No active session")

        try:
            response = self._request(
                'POST',
                f'/sessions/{self.session_id}/learn'
            )
            return response.json()
        except KATOSessionError:
            if auto_reconnect and self.node_id:
                self.reconnect()
                return self.learn(auto_reconnect=False)
            raise

    def get_predictions(
        self,
        auto_reconnect: bool = True
    ) -> Dict:
        """Get predictions from current STM."""
        if not self.session_id:
            raise KATOSessionError("No active session")

        try:
            response = self._request(
                'GET',
                f'/sessions/{self.session_id}/predictions'
            )
            return response.json()
        except KATOSessionError:
            if auto_reconnect and self.node_id:
                self.reconnect()
                return self.get_predictions(auto_reconnect=False)
            raise

    def clear_stm(self) -> Dict:
        """Clear short-term memory."""
        if not self.session_id:
            raise KATOSessionError("No active session")

        response = self._request(
            'POST',
            f'/sessions/{self.session_id}/clear-stm'
        )
        return response.json()

    def get_stm(self) -> Dict:
        """Get current short-term memory."""
        if not self.session_id:
            raise KATOSessionError("No active session")

        response = self._request(
            'GET',
            f'/sessions/{self.session_id}/stm'
        )
        return response.json()

    def get_session_info(self) -> Dict:
        """Get session information."""
        if not self.session_id:
            raise KATOSessionError("No active session")

        response = self._request(
            'GET',
            f'/sessions/{self.session_id}'
        )
        return response.json()

    def delete_session(self) -> Dict:
        """Delete current session."""
        if not self.session_id:
            raise KATOSessionError("No active session")

        response = self._request(
            'DELETE',
            f'/sessions/{self.session_id}'
        )

        logger.info(f"Deleted session {self.session_id}")
        self.session_id = None
        return response.json()

    def close(self):
        """Close HTTP session."""
        self.session.close()

    def __enter__(self):
        """Context manager support."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager cleanup."""
        self.close()
```

### Production Usage

```python
# Context manager
with KATOClient("http://localhost:8000") as kato:
    kato.create_session("my_app")
    kato.observe(["hello", "world"])
    predictions = kato.get_predictions()

# Error handling
try:
    kato = KATOClient()
    kato.create_session("my_app")
    kato.observe(["test"])
except KATOSessionError as e:
    print(f"Session error: {e}")
    # Reconnect
    kato.reconnect()
except KATOAPIError as e:
    print(f"API error: {e.status_code} - {e.message}")
except KATOError as e:
    print(f"KATO error: {e}")
```

## Advanced Features

### Async Client

```python
import aiohttp
from typing import Optional, Dict, List, Any

class AsyncKATOClient:
    """Async KATO client for high-throughput applications."""

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url.rstrip('/')
        self.session_id: Optional[str] = None
        self._session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        self._session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._session:
            await self._session.close()

    async def create_session(
        self,
        node_id: str,
        config: Optional[Dict] = None
    ) -> str:
        """Create a new session."""
        payload = {"node_id": node_id}
        if config:
            payload["config"] = config

        async with self._session.post(
            f"{self.base_url}/sessions",
            json=payload
        ) as response:
            response.raise_for_status()
            data = await response.json()
            self.session_id = data['session_id']
            return self.session_id

    async def observe(
        self,
        strings: List[str],
        vectors: Optional[List[List[float]]] = None,
        emotives: Optional[Dict[str, float]] = None
    ) -> Dict:
        """Send observation."""
        if not self.session_id:
            raise ValueError("No active session")

        payload = {
            "strings": strings,
            "vectors": vectors or [],
            "emotives": emotives or {}
        }

        async with self._session.post(
            f"{self.base_url}/sessions/{self.session_id}/observe",
            json=payload
        ) as response:
            response.raise_for_status()
            return await response.json()

    async def get_predictions(self) -> Dict:
        """Get predictions."""
        if not self.session_id:
            raise ValueError("No active session")

        async with self._session.get(
            f"{self.base_url}/sessions/{self.session_id}/predictions"
        ) as response:
            response.raise_for_status()
            return await response.json()

# Usage
import asyncio

async def main():
    async with AsyncKATOClient() as kato:
        await kato.create_session("my_app")
        await kato.observe(["hello", "world"])
        predictions = await kato.get_predictions()
        print(predictions)

asyncio.run(main())
```

### Batch Processing

```python
class BatchKATOClient(KATOClient):
    """KATO client with batch operations."""

    def observe_batch(
        self,
        observations: List[Dict[str, Any]]
    ) -> List[Dict]:
        """Send multiple observations in sequence."""
        results = []
        for obs in observations:
            result = self.observe(
                strings=obs.get('strings', []),
                vectors=obs.get('vectors'),
                emotives=obs.get('emotives'),
                metadata=obs.get('metadata')
            )
            results.append(result)
        return results

    def learn_and_test(
        self,
        training_obs: List[Dict],
        test_obs: List[Dict]
    ) -> Dict:
        """Train on observations and test recall."""
        # Train
        self.observe_batch(training_obs)
        pattern = self.learn()

        # Test
        self.clear_stm()
        self.observe_batch(test_obs)
        predictions = self.get_predictions()

        return {
            'pattern': pattern,
            'predictions': predictions
        }

# Usage
kato = BatchKATOClient()
kato.create_session("batch_test")

results = kato.learn_and_test(
    training_obs=[
        {"strings": ["morning", "coffee"]},
        {"strings": ["work", "code"]},
        {"strings": ["evening", "relax"]}
    ],
    test_obs=[
        {"strings": ["morning", "coffee"]}
    ]
)
```

### Prediction Helper

```python
class PredictionHelper:
    """Helper for working with KATO predictions."""

    @staticmethod
    def get_top_prediction(predictions: Dict) -> Optional[Dict]:
        """Get highest-ranked prediction."""
        preds = predictions.get('predictions', [])
        return preds[0] if preds else None

    @staticmethod
    def get_future_strings(prediction: Dict) -> List[str]:
        """Extract all future strings from prediction."""
        future = prediction.get('future', [])
        return [s for event in future for s in event]

    @staticmethod
    def get_next_event(prediction: Dict) -> Optional[List[str]]:
        """Get immediate next event."""
        future = prediction.get('future', [])
        return future[0] if future else None

    @staticmethod
    def has_missing_symbols(prediction: Dict) -> bool:
        """Check if prediction has missing symbols."""
        missing = prediction.get('missing', [])
        return any(event for event in missing)

    @staticmethod
    def get_confidence(prediction: Dict) -> float:
        """Get prediction confidence."""
        return prediction.get('metrics', {}).get('confidence', 0.0)

# Usage
predictions = kato.get_predictions()
helper = PredictionHelper()

top = helper.get_top_prediction(predictions)
if top:
    next_event = helper.get_next_event(top)
    confidence = helper.get_confidence(top)
    print(f"Next: {next_event} (confidence: {confidence:.2f})")
```

## Testing

### Unit Tests

```python
import unittest
from unittest.mock import Mock, patch

class TestKATOClient(unittest.TestCase):
    def setUp(self):
        self.kato = KATOClient("http://test:8000")

    @patch('requests.post')
    def test_create_session(self, mock_post):
        # Mock response
        mock_post.return_value.json.return_value = {
            'session_id': 'test-123',
            'node_id': 'test_node'
        }
        mock_post.return_value.raise_for_status = Mock()

        # Test
        session_id = self.kato.create_session("test_node")

        # Verify
        self.assertEqual(session_id, 'test-123')
        self.assertEqual(self.kato.session_id, 'test-123')
        mock_post.assert_called_once()

    @patch('requests.post')
    def test_observe(self, mock_post):
        self.kato.session_id = 'test-123'
        mock_post.return_value.json.return_value = {
            'strings': ['hello'],
            'stm_length': 1
        }
        mock_post.return_value.raise_for_status = Mock()

        result = self.kato.observe(['hello'])

        self.assertEqual(result['stm_length'], 1)
        mock_post.assert_called_once()

if __name__ == '__main__':
    unittest.main()
```

### Integration Tests

```python
import pytest

@pytest.fixture
def kato_client():
    """Create KATO client for testing."""
    client = KATOClient("http://localhost:8000")
    yield client
    # Cleanup
    if client.session_id:
        try:
            client.delete_session()
        except:
            pass

def test_full_workflow(kato_client):
    """Test complete KATO workflow."""
    # Create session
    session_id = kato_client.create_session("pytest_test")
    assert session_id is not None

    # Send observations
    kato_client.observe(["hello", "world"])
    kato_client.observe(["foo", "bar"])

    # Check STM
    stm = kato_client.get_stm()
    assert stm['length'] == 2

    # Learn
    pattern = kato_client.learn()
    assert 'pattern_name' in pattern

    # Test recall
    kato_client.clear_stm()
    kato_client.observe(["hello", "world"])
    predictions = kato_client.get_predictions()
    assert len(predictions['predictions']) > 0
```

## Best Practices

1. **Use context managers** for automatic cleanup
2. **Enable auto-reconnect** for long-running applications
3. **Handle session expiry** gracefully
4. **Implement retry logic** for network errors
5. **Use batch operations** when processing multiple items
6. **Log all KATO interactions** for debugging
7. **Test with mock KATO** before production
8. **Monitor prediction confidence** and adjust thresholds

## Related Documentation

- [First Session Tutorial](first-session.md)
- [Session Management](session-management.md)
- [API Reference](../reference/api/)
- [Examples](examples/)

---

**Last Updated**: November 2025
**KATO Version**: 3.0+
