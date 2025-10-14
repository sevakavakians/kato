"""
Async client for testing KATO session management endpoints.
Provides methods to interact with the session-based API.

Migrated from aiohttp to httpx for improved reliability under concurrent load.
"""

import asyncio
from typing import Any, Optional

import httpx

from kato.exceptions import SessionNotFoundError


class KatoSessionClient:
    """Async client for KATO session endpoints."""

    def __init__(self, base_url: str = "http://localhost:8000"):
        """Initialize the client with base URL."""
        self.base_url = base_url
        self.session = None

    def _create_session(self) -> httpx.AsyncClient:
        """Create httpx async client with optimized settings for stress testing."""
        limits = httpx.Limits(
            max_keepalive_connections=100,  # Connections per host
            max_connections=200,  # Total connection pool size
            keepalive_expiry=30.0,  # Keep connections alive for 30 seconds
        )
        timeout = httpx.Timeout(60.0)  # 60 second timeout
        return httpx.AsyncClient(limits=limits, timeout=timeout)

    async def __aenter__(self):
        """Async context manager entry."""
        self.session = self._create_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.aclose()

    async def _request_with_retry(self, method: str, url: str, **kwargs) -> httpx.Response:
        """
        Make HTTP request with retry logic for transient failures.

        Args:
            method: HTTP method (GET, POST, DELETE, etc.)
            url: Full URL to request
            **kwargs: Additional arguments for httpx request

        Returns:
            httpx.Response object

        Raises:
            httpx.HTTPError: After all retries exhausted
        """
        max_retries = 3
        backoff_factor = 0.5  # 0.5s, 1s, 2s
        retry_status_codes = {502, 503, 504}

        last_exception = None

        for attempt in range(max_retries + 1):
            try:
                response = await self.session.request(method, url, **kwargs)

                # Retry on specific server errors
                if response.status_code in retry_status_codes and attempt < max_retries:
                    await asyncio.sleep(backoff_factor * (2 ** attempt))
                    continue

                return response

            except (httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError) as e:
                last_exception = e
                if attempt < max_retries:
                    await asyncio.sleep(backoff_factor * (2 ** attempt))
                    continue
                else:
                    raise

        # Should not reach here, but just in case
        if last_exception:
            raise last_exception

    async def create_session(self, node_id: Optional[str] = None, ttl_seconds: int = 3600,
                           metadata: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        """Create a new session."""
        if not self.session:
            self.session = self._create_session()

        # Generate a default node_id if none provided (required by API)
        if node_id is None:
            import uuid
            node_id = f"test_node_{uuid.uuid4().hex[:8]}"

        payload = {
            "node_id": node_id,
            "ttl_seconds": ttl_seconds,
            "metadata": metadata or {}
        }

        resp = await self._request_with_retry("POST", f"{self.base_url}/sessions", json=payload)
        resp.raise_for_status()
        return resp.json()

    async def get_session_info(self, session_id: str) -> dict[str, Any]:
        """Get information about a session."""
        if not self.session:
            self.session = self._create_session()

        resp = await self._request_with_retry("GET", f"{self.base_url}/sessions/{session_id}")
        if resp.status_code == 404:
            raise SessionNotFoundError(session_id)
        resp.raise_for_status()
        return resp.json()

    async def delete_session(self, session_id: str) -> None:
        """Delete a session."""
        if not self.session:
            self.session = self._create_session()

        resp = await self._request_with_retry("DELETE", f"{self.base_url}/sessions/{session_id}")
        # 404 means session already deleted - that's OK for cleanup
        if resp.status_code != 404:
            resp.raise_for_status()

    async def observe_in_session(self, session_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Make an observation in a session."""
        if not self.session:
            self.session = self._create_session()

        # Ensure required fields are present
        if "strings" not in data:
            data["strings"] = []
        if "vectors" not in data:
            data["vectors"] = []
        if "emotives" not in data:
            data["emotives"] = {}

        resp = await self._request_with_retry(
            "POST",
            f"{self.base_url}/sessions/{session_id}/observe",
            json=data
        )
        if resp.status_code == 404:
            raise SessionNotFoundError(session_id)
        resp.raise_for_status()
        return resp.json()

    async def get_session_stm(self, session_id: str) -> dict[str, Any]:
        """Get the STM for a session."""
        if not self.session:
            self.session = self._create_session()

        resp = await self._request_with_retry("GET", f"{self.base_url}/sessions/{session_id}/stm")
        if resp.status_code == 404:
            raise SessionNotFoundError(session_id)
        resp.raise_for_status()
        return resp.json()

    async def learn_in_session(self, session_id: str) -> dict[str, Any]:
        """Learn a pattern in a session."""
        if not self.session:
            self.session = self._create_session()

        resp = await self._request_with_retry("POST", f"{self.base_url}/sessions/{session_id}/learn")
        if resp.status_code == 404:
            raise SessionNotFoundError(session_id)
        resp.raise_for_status()
        return resp.json()

    async def clear_session_stm(self, session_id: str) -> dict[str, Any]:
        """Clear the STM for a session."""
        if not self.session:
            self.session = self._create_session()

        resp = await self._request_with_retry("POST", f"{self.base_url}/sessions/{session_id}/clear-stm")
        if resp.status_code == 404:
            raise SessionNotFoundError(session_id)
        resp.raise_for_status()
        return resp.json()

    async def get_session_predictions(self, session_id: str) -> dict[str, Any]:
        """Get predictions for a session."""
        if not self.session:
            self.session = self._create_session()

        resp = await self._request_with_retry("GET", f"{self.base_url}/sessions/{session_id}/predictions")
        if resp.status_code == 404:
            raise SessionNotFoundError(session_id)
        resp.raise_for_status()
        return resp.json()

    async def extend_session(self, session_id: str, ttl_seconds: int = 3600) -> dict[str, Any]:
        """Extend a session's TTL."""
        if not self.session:
            self.session = self._create_session()

        params = {"ttl_seconds": ttl_seconds}
        resp = await self._request_with_retry(
            "POST",
            f"{self.base_url}/sessions/{session_id}/extend",
            params=params
        )
        if resp.status_code == 404:
            raise SessionNotFoundError(session_id)
        resp.raise_for_status()
        return resp.json()

    async def check_session_exists(self, session_id: str) -> dict[str, Any]:
        """
        Check if session exists without extending its TTL.

        Returns:
            dict with 'exists' and 'expired' boolean fields
        """
        if not self.session:
            self.session = self._create_session()

        resp = await self._request_with_retry(
            "GET",
            f"{self.base_url}/sessions/{session_id}/exists"
        )
        resp.raise_for_status()
        return resp.json()

    # Legacy compatibility methods
    async def observe_legacy(self, observation: dict[str, Any], headers: Optional[dict[str, str]] = None) -> dict[str, Any]:
        """Legacy observe method for backward compatibility tests."""
        if not self.session:
            self.session = self._create_session()

        # Use legacy endpoint or session-based endpoint depending on headers
        if headers and "X-Session-ID" in headers:
            # Route to specific session
            session_id = headers["X-Session-ID"]
            resp = await self._request_with_retry(
                "POST",
                f"{self.base_url}/sessions/{session_id}/observe",
                json=observation
            )
            resp.raise_for_status()
            return resp.json()
        else:
            # Use default/legacy behavior (direct observe endpoint)
            resp = await self._request_with_retry(
                "POST",
                f"{self.base_url}/observe",
                json=observation,
                headers=headers or {}
            )
            resp.raise_for_status()
            return resp.json()

    async def update_session_config(self, session_id: str, config: dict[str, Any]) -> dict[str, Any]:
        """Update session configuration."""
        if not self.session:
            self.session = self._create_session()

        resp = await self._request_with_retry(
            "POST",
            f"{self.base_url}/sessions/{session_id}/config",
            json=config
        )
        if resp.status_code == 404:
            raise SessionNotFoundError(session_id)
        resp.raise_for_status()
        return resp.json()

    async def get_stm_legacy(self, headers: Optional[dict[str, str]] = None) -> dict[str, Any]:
        """Get STM using legacy endpoint for backward compatibility tests."""
        if not self.session:
            self.session = self._create_session()

        resp = await self._request_with_retry(
            "GET",
            f"{self.base_url}/stm",
            headers=headers or {}
        )
        resp.raise_for_status()
        return resp.json()

    async def clear_stm_legacy(self, headers: Optional[dict[str, str]] = None) -> dict[str, Any]:
        """Clear STM using legacy endpoint for backward compatibility tests."""
        if not self.session:
            self.session = self._create_session()

        resp = await self._request_with_retry(
            "POST",
            f"{self.base_url}/clear-stm",
            headers=headers or {}
        )
        resp.raise_for_status()
        return resp.json()

    async def get_active_session_count(self) -> int:
        """Get the count of active sessions."""
        if not self.session:
            self.session = self._create_session()

        resp = await self._request_with_retry("GET", f"{self.base_url}/sessions/count")
        resp.raise_for_status()
        result = resp.json()
        return result["active_session_count"]
