"""
Async client for testing KATO session management endpoints.
Provides methods to interact with the session-based API.
"""

from typing import Any, Optional

import aiohttp

from kato.exceptions import SessionNotFoundError


class KatoSessionClient:
    """Async client for KATO session endpoints."""

    def __init__(self, base_url: str = "http://localhost:8000"):
        """Initialize the client with base URL."""
        self.base_url = base_url
        self.session = None

    def _create_session(self) -> aiohttp.ClientSession:
        """Create aiohttp session with optimized settings for stress testing."""
        connector = aiohttp.TCPConnector(
            limit=200,  # Total connection pool size
            limit_per_host=100,  # Connections per host
            ttl_dns_cache=300,  # DNS cache TTL
            use_dns_cache=True,
            keepalive_timeout=30,  # Keep connections alive for 30 seconds
            enable_cleanup_closed=True,  # Clean up closed connections
        )
        timeout = aiohttp.ClientTimeout(total=60)  # Increased to 60 second timeout
        return aiohttp.ClientSession(connector=connector, timeout=timeout)

    async def __aenter__(self):
        """Async context manager entry."""
        self.session = self._create_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.close()

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

        async with self.session.post(f"{self.base_url}/sessions", json=payload) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def get_session_info(self, session_id: str) -> dict[str, Any]:
        """Get information about a session."""
        if not self.session:
            self.session = self._create_session()

        async with self.session.get(f"{self.base_url}/sessions/{session_id}") as resp:
            if resp.status == 404:
                raise SessionNotFoundError(session_id)
            resp.raise_for_status()
            return await resp.json()

    async def delete_session(self, session_id: str) -> None:
        """Delete a session."""
        if not self.session:
            self.session = self._create_session()

        async with self.session.delete(f"{self.base_url}/sessions/{session_id}") as resp:
            # 404 means session already deleted - that's OK for cleanup
            if resp.status != 404:
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

        async with self.session.post(
            f"{self.base_url}/sessions/{session_id}/observe",
            json=data
        ) as resp:
            if resp.status == 404:
                raise SessionNotFoundError(session_id)
            resp.raise_for_status()
            return await resp.json()

    async def get_session_stm(self, session_id: str) -> dict[str, Any]:
        """Get the STM for a session."""
        if not self.session:
            self.session = self._create_session()

        async with self.session.get(f"{self.base_url}/sessions/{session_id}/stm") as resp:
            if resp.status == 404:
                raise SessionNotFoundError(session_id)
            resp.raise_for_status()
            return await resp.json()

    async def learn_in_session(self, session_id: str) -> dict[str, Any]:
        """Learn a pattern in a session."""
        if not self.session:
            self.session = self._create_session()

        async with self.session.post(f"{self.base_url}/sessions/{session_id}/learn") as resp:
            if resp.status == 404:
                raise SessionNotFoundError(session_id)
            resp.raise_for_status()
            return await resp.json()

    async def clear_session_stm(self, session_id: str) -> dict[str, Any]:
        """Clear the STM for a session."""
        if not self.session:
            self.session = self._create_session()

        async with self.session.post(f"{self.base_url}/sessions/{session_id}/clear-stm") as resp:
            if resp.status == 404:
                raise SessionNotFoundError(session_id)
            resp.raise_for_status()
            return await resp.json()

    async def get_session_predictions(self, session_id: str) -> dict[str, Any]:
        """Get predictions for a session."""
        if not self.session:
            self.session = self._create_session()

        async with self.session.get(f"{self.base_url}/sessions/{session_id}/predictions") as resp:
            if resp.status == 404:
                raise SessionNotFoundError(session_id)
            resp.raise_for_status()
            return await resp.json()

    async def extend_session(self, session_id: str, ttl_seconds: int = 3600) -> dict[str, Any]:
        """Extend a session's TTL."""
        if not self.session:
            self.session = self._create_session()

        params = {"ttl_seconds": ttl_seconds}
        async with self.session.post(
            f"{self.base_url}/sessions/{session_id}/extend",
            params=params
        ) as resp:
            if resp.status == 404:
                raise SessionNotFoundError(session_id)
            resp.raise_for_status()
            return await resp.json()

    # Legacy compatibility methods
    async def observe_legacy(self, observation: dict[str, Any], headers: Optional[dict[str, str]] = None) -> dict[str, Any]:
        """Legacy observe method for backward compatibility tests."""
        if not self.session:
            self.session = self._create_session()

        # Use legacy endpoint or session-based endpoint depending on headers
        if headers and "X-Session-ID" in headers:
            # Route to specific session
            session_id = headers["X-Session-ID"]
            async with self.session.post(
                f"{self.base_url}/sessions/{session_id}/observe",
                json=observation
            ) as resp:
                resp.raise_for_status()
                return await resp.json()
        else:
            # Use default/legacy behavior (direct observe endpoint)
            async with self.session.post(
                f"{self.base_url}/observe",
                json=observation,
                headers=headers or {}
            ) as resp:
                resp.raise_for_status()
                return await resp.json()

    async def update_session_config(self, session_id: str, config: dict[str, Any]) -> dict[str, Any]:
        """Update session configuration."""
        if not self.session:
            self.session = self._create_session()

        async with self.session.post(
            f"{self.base_url}/sessions/{session_id}/config",
            json=config
        ) as resp:
            if resp.status == 404:
                raise SessionNotFoundError(session_id)
            resp.raise_for_status()
            return await resp.json()

    async def get_stm_legacy(self, headers: Optional[dict[str, str]] = None) -> dict[str, Any]:
        """Get STM using legacy endpoint for backward compatibility tests."""
        if not self.session:
            self.session = self._create_session()

        async with self.session.get(
            f"{self.base_url}/stm",
            headers=headers or {}
        ) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def clear_stm_legacy(self, headers: Optional[dict[str, str]] = None) -> dict[str, Any]:
        """Clear STM using legacy endpoint for backward compatibility tests."""
        if not self.session:
            self.session = self._create_session()

        async with self.session.post(
            f"{self.base_url}/clear-stm",
            headers=headers or {}
        ) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def get_active_session_count(self) -> int:
        """Get the count of active sessions."""
        if not self.session:
            self.session = self._create_session()

        async with self.session.get(f"{self.base_url}/sessions/count") as resp:
            resp.raise_for_status()
            result = await resp.json()
            return result["active_session_count"]
