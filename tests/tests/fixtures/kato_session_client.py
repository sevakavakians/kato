"""
Async client for testing KATO session management endpoints.
Provides methods to interact with the session-based API.
"""

import aiohttp
import asyncio
from typing import Dict, Any, Optional, List


class KatoSessionClient:
    """Async client for KATO session endpoints."""
    
    def __init__(self, base_url: str = "http://localhost:8001"):
        """Initialize the client with base URL."""
        self.base_url = base_url
        self.session = None
        
    async def __aenter__(self):
        """Async context manager entry."""
        self.session = aiohttp.ClientSession()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.close()
            
    async def create_session(self, user_id: str, ttl_seconds: int = 3600, 
                           metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Create a new session."""
        if not self.session:
            self.session = aiohttp.ClientSession()
            
        payload = {
            "user_id": user_id,
            "ttl_seconds": ttl_seconds,
            "metadata": metadata or {}
        }
        
        async with self.session.post(f"{self.base_url}/sessions", json=payload) as resp:
            resp.raise_for_status()
            return await resp.json()
    
    async def get_session_info(self, session_id: str) -> Dict[str, Any]:
        """Get information about a session."""
        if not self.session:
            self.session = aiohttp.ClientSession()
            
        async with self.session.get(f"{self.base_url}/sessions/{session_id}") as resp:
            resp.raise_for_status()
            return await resp.json()
    
    async def delete_session(self, session_id: str) -> None:
        """Delete a session."""
        if not self.session:
            self.session = aiohttp.ClientSession()
            
        async with self.session.delete(f"{self.base_url}/sessions/{session_id}") as resp:
            resp.raise_for_status()
    
    async def observe_in_session(self, session_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Make an observation in a session."""
        if not self.session:
            self.session = aiohttp.ClientSession()
            
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
            resp.raise_for_status()
            return await resp.json()
    
    async def get_session_stm(self, session_id: str) -> Dict[str, Any]:
        """Get the STM for a session."""
        if not self.session:
            self.session = aiohttp.ClientSession()
            
        async with self.session.get(f"{self.base_url}/sessions/{session_id}/stm") as resp:
            resp.raise_for_status()
            return await resp.json()
    
    async def learn_in_session(self, session_id: str) -> Dict[str, Any]:
        """Learn a pattern in a session."""
        if not self.session:
            self.session = aiohttp.ClientSession()
            
        async with self.session.post(f"{self.base_url}/sessions/{session_id}/learn") as resp:
            resp.raise_for_status()
            return await resp.json()
    
    async def clear_session_stm(self, session_id: str) -> Dict[str, Any]:
        """Clear the STM for a session."""
        if not self.session:
            self.session = aiohttp.ClientSession()
            
        async with self.session.post(f"{self.base_url}/sessions/{session_id}/clear-stm") as resp:
            resp.raise_for_status()
            return await resp.json()
    
    async def get_session_predictions(self, session_id: str) -> Dict[str, Any]:
        """Get predictions for a session."""
        if not self.session:
            self.session = aiohttp.ClientSession()
            
        async with self.session.get(f"{self.base_url}/sessions/{session_id}/predictions") as resp:
            resp.raise_for_status()
            return await resp.json()
    
    async def extend_session(self, session_id: str, ttl_seconds: int = 3600) -> Dict[str, Any]:
        """Extend a session's TTL."""
        if not self.session:
            self.session = aiohttp.ClientSession()
            
        params = {"ttl_seconds": ttl_seconds}
        async with self.session.post(
            f"{self.base_url}/sessions/{session_id}/extend",
            params=params
        ) as resp:
            resp.raise_for_status()
            return await resp.json()
    
    async def update_session_config(self, session_id: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """Update session configuration."""
        if not self.session:
            self.session = aiohttp.ClientSession()
            
        async with self.session.post(
            f"{self.base_url}/sessions/{session_id}/config",
            json=config
        ) as resp:
            resp.raise_for_status()
            return await resp.json()