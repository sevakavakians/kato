"""
KATO Python Client - Simple API Wrapper with Transparent Session Management

This is a complete Python client for the KATO API that can be copied into any project.
Sessions are handled automatically - one client instance equals one isolated KATO session.

Features:
- Automatic session creation and cleanup
- Session-based configuration updates (v3.3.0+)
- Automatic session recreation on 404 errors (expired/lost sessions)
- STM state recovery after session recreation
- Exponential backoff retry for transient failures

USAGE:
    from sample_kato_client import KATOClient

    # Create client with auto-session creation
    client = KATOClient(
        base_url="http://localhost:8000",
        node_id="user123",
        max_pattern_length=10,
        stm_mode="ROLLING"
    )

    # Observe, learn, and predict (no session_id needed)
    client.observe(strings=["hello", "world"])
    client.learn()
    predictions = client.get_predictions()

    # Update configuration dynamically (v3.3.0+)
    client.update_session_config({
        'recall_threshold': 0.1,
        'max_predictions': 100
    })

    # Cleanup
    client.close()

    # Or use as context manager for auto-cleanup
    with KATOClient(base_url="http://localhost:8000", node_id="user123") as client:
        client.observe(strings=["hello", "world"])
        predictions = client.get_predictions()

Author: KATO Team
Version: 3.5.0 - Removed processor genes (update_genes/get_gene) - session config only (breaking change)
"""

import json
import time
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class KATOClient:
    """
    Python client for KATO API with transparent session management and automatic recovery.

    This client provides a simple interface to KATO where sessions are handled
    automatically. One client instance = one isolated KATO session.

    Features:
        - Automatic session creation and cleanup
        - Session-based configuration updates (v3.3.0+)
        - Automatic session recreation on 404 errors (expired/lost sessions)
        - STM state recovery after session recreation
        - Exponential backoff retry for transient failures

    Configuration Parameters:
        max_pattern_length: int (0+, default=0)
            - 0 = manual learning only
            - N > 0 = auto-learn after N observations

        persistence: int (1-100, default=5)
            - Rolling window size for emotive values per pattern

        recall_threshold: float (0.0-1.0, default=0.1)
            - Pattern matching threshold (0.1=permissive, 0.9=strict)

        stm_mode: str ('CLEAR' or 'ROLLING', default='CLEAR')
            - 'CLEAR': STM cleared after auto-learn
            - 'ROLLING': STM maintained as sliding window

        indexer_type: str ('VI'/'LSH'/'ANNOY'/'FAISS', default='VI')
            - Vector indexer type for similarity search

        max_predictions: int (1-10000, default=100)
            - Maximum number of predictions to return

        sort_symbols: bool (default=True)
            - Whether to sort symbols alphabetically within events

        process_predictions: bool (default=True)
            - Whether to process predictions

        auto_recreate_session: bool (default=True)
            - Automatically recreate session on 404 errors
            - Attempts to restore STM state when recreating

        max_session_recreate_attempts: int (default=3)
            - Maximum attempts to recreate session before failing
            - Uses exponential backoff: 0.5s, 1s, 2s

    Node Isolation (v3.4.0+):
        **BREAKING CHANGE**: Optional node_id parameters removed from all methods.
        One client instance = one node, always. To access multiple nodes, create
        multiple client instances.

        ✅ CORRECT:
            node0 = KATOClient(node_id="node0")
            node1 = KATOClient(node_id="node1")
            node0.get_gene("recall_threshold")  # Always uses node0
            node1.get_gene("recall_threshold")  # Always uses node1

        ❌ REMOVED (no longer supported):
            client.get_gene("recall_threshold", node_id="other_node")

    Configuration Updates (v3.3.0+):
        **IMPORTANT**: Use update_session_config() for runtime configuration changes.

        ✅ CORRECT:
            client.update_session_config({'recall_threshold': 0.1})

        ❌ DEPRECATED:
            client.update_genes({'recall_threshold': 0.1})  # Won't affect your session!

        The update_genes() method only updates processor defaults and does NOT
        affect active sessions. It's deprecated in KATO v2.1.0+.

    Resilience:
        The client is designed for long-running tasks and handles:
        - Session expiration: Auto-recreates and restores STM
        - Network failures: Retries with exponential backoff
        - Transient errors: HTTP 502/503/504 automatic retry

    Timeout Configuration:
        The timeout parameter controls how long to wait for server responses.

        Recommended values:
        - 30-60s: Standard workloads with small batches (<100 observations)
        - 120s: Training workloads with large batches (100-1000 observations)
        - 300s: Very large batches or slow database conditions

        Note: The server has SESSION_AUTO_EXTEND enabled, which means sessions
        automatically extend their TTL on every request. Long timeouts are safe
        and won't cause session expiration issues.

    Example:
        >>> # Long-running training with appropriate timeout
        >>> client = KATOClient(
        ...     base_url="http://localhost:8000",
        ...     node_id="level0_token_node",
        ...     timeout=120,  # 2 minutes for training workloads
        ...     max_pattern_length=10,
        ...     stm_mode="ROLLING",
        ...     auto_recreate_session=True  # Enabled by default
        ... )
        >>> # Even if session expires mid-training, client auto-recovers
        >>> for i in range(10000):
        ...     client.observe(strings=[f"token_{i}"])
        >>> client.learn()
        >>> predictions = client.get_predictions()
        >>> client.close()
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        node_id: str = None,
        timeout: int = 120,
        metadata: Optional[Dict[str, Any]] = None,
        ttl_seconds: Optional[int] = None,
        # Configuration parameters with defaults from KATO settings
        max_pattern_length: int = 0,
        persistence: int = 5,
        recall_threshold: float = 0.1,
        stm_mode: str = 'CLEAR',
        indexer_type: str = 'VI',
        max_predictions: int = 100,
        sort_symbols: bool = True,
        process_predictions: bool = True,
        # Retry configuration
        auto_recreate_session: bool = True,
        max_session_recreate_attempts: int = 3
    ):
        """
        Initialize KATO client with automatic session creation.

        Args:
            base_url: Base URL of KATO service
            node_id: Node identifier (required for processor isolation)
            timeout: Request timeout in seconds (default: 120)
                    Recommended: 30-60s for standard workloads, 120s for training,
                    300s for very large batches or slow DB conditions
            metadata: Optional session metadata
            ttl_seconds: Session TTL in seconds (default: 3600)
            max_pattern_length: Auto-learn after N observations (0=manual, default: 0)
            persistence: Rolling window size for emotives (1-100, default: 5)
            recall_threshold: Pattern matching threshold (0.0-1.0, default: 0.1)
            stm_mode: STM mode 'CLEAR' or 'ROLLING' (default: 'CLEAR')
            indexer_type: Vector indexer type (default: 'VI')
            max_predictions: Max predictions to return (1-10000, default: 100)
            sort_symbols: Sort symbols alphabetically (default: True)
            process_predictions: Enable prediction processing (default: True)
            auto_recreate_session: Auto-recreate session on 404 errors (default: True)
            max_session_recreate_attempts: Max attempts to recreate session (default: 3)

        Raises:
            ValueError: If node_id is not provided
        """
        if node_id is None:
            raise ValueError("node_id is required for KATO client initialization")

        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.node_id = node_id
        self._http_session = requests.Session()

        # Retry configuration
        self.auto_recreate_session = auto_recreate_session
        self.max_session_recreate_attempts = max_session_recreate_attempts

        # Store session creation parameters for recreation
        self._session_metadata = metadata or {}
        self._session_ttl_seconds = ttl_seconds
        self._session_config = {}

        # Configure retry strategy for resilience against transient failures
        retry_strategy = Retry(
            total=3,  # Total number of retries
            backoff_factor=0.5,  # Exponential backoff: 0.5s, 1s, 2s
            status_forcelist=[502, 503, 504],  # Retry on server errors
            allowed_methods=["GET", "POST", "DELETE", "PUT"]  # Retry safe methods
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self._http_session.mount("http://", adapter)
        self._http_session.mount("https://", adapter)

        # Build configuration
        config = {}
        if max_pattern_length != 0:
            config['max_pattern_length'] = max_pattern_length
        if persistence != 5:
            config['persistence'] = persistence
        if recall_threshold != 0.1:
            config['recall_threshold'] = recall_threshold
        if stm_mode != 'CLEAR':
            config['stm_mode'] = stm_mode
        if indexer_type != 'VI':
            config['indexer_type'] = indexer_type
        if max_predictions != 100:
            config['max_predictions'] = max_predictions
        if sort_symbols is not True:
            config['sort_symbols'] = sort_symbols
        if process_predictions is not True:
            config['process_predictions'] = process_predictions

        # Store config for session recreation
        self._session_config = config

        # Auto-create session (bypass retry logic for initial creation)
        self._session_id = None
        self._create_session()

    def _create_session(self) -> None:
        """Create a new session with stored parameters."""
        session_data = {
            'node_id': self.node_id,
            'metadata': self._session_metadata,
        }
        if self._session_ttl_seconds is not None:
            session_data['ttl_seconds'] = self._session_ttl_seconds

        # Direct request without retry wrapper for session creation
        url = urljoin(self.base_url, '/sessions')
        response = self._http_session.post(url, json=session_data, timeout=self.timeout)
        response.raise_for_status()
        session_response = response.json()
        self._session_id = session_response['session_id']

        # Update config if any non-default values provided
        if self._session_config:
            url = urljoin(self.base_url, f'/sessions/{self._session_id}/config')
            response = self._http_session.post(
                url,
                json={'config': self._session_config},
                timeout=self.timeout
            )
            response.raise_for_status()

    def _recreate_session_with_state_recovery(self) -> None:
        """
        Recreate session and attempt to restore STM state.

        This is called automatically when a 404 error occurs, indicating
        the session has expired or been lost.
        """
        # Try to get current STM state before recreation (may fail)
        cached_stm = None
        try:
            # Attempt direct GET without retry wrapper
            url = urljoin(self.base_url, f'/sessions/{self._session_id}/stm')
            response = self._http_session.get(url, timeout=self.timeout)
            if response.status_code == 200:
                stm_data = response.json()
                cached_stm = stm_data.get('stm', [])
        except Exception:
            # STM retrieval failed, will create fresh session
            pass

        # Create new session
        old_session_id = self._session_id
        self._create_session()

        # Restore STM if we retrieved it
        if cached_stm:
            try:
                # Replay observations to restore STM state
                for event in cached_stm:
                    self.observe(strings=event)
            except Exception:
                # STM restoration failed, continue with empty STM
                pass

    def _request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None,
        params: Optional[Dict] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Internal method to make HTTP requests with automatic session recreation.

        This method implements retry logic with session recreation on 404 errors.
        If a session expires or is lost, it will:
        1. Attempt to cache current STM state
        2. Recreate the session
        3. Restore STM state if possible
        4. Retry the original request

        Args:
            method: HTTP method (GET, POST, DELETE, etc.)
            endpoint: API endpoint path
            data: Request body data
            params: Query parameters
            **kwargs: Additional arguments for requests

        Returns:
            Response JSON as dictionary

        Raises:
            requests.HTTPError: On HTTP error responses after all retry attempts
        """
        url = urljoin(self.base_url, endpoint.lstrip('/'))

        kwargs.setdefault('timeout', self.timeout)
        if data is not None:
            kwargs['json'] = data
        if params is not None:
            kwargs['params'] = params

        # Retry loop with session recreation
        for attempt in range(self.max_session_recreate_attempts):
            try:
                response = self._http_session.request(method, url, **kwargs)
                response.raise_for_status()
                return response.json()

            except requests.HTTPError as e:
                # Check if this is a 404 error (session not found)
                if e.response.status_code == 404 and self.auto_recreate_session:
                    # Don't retry session creation/deletion endpoints
                    if '/sessions' in endpoint and method in ['POST', 'DELETE']:
                        raise

                    # Don't retry on last attempt
                    if attempt >= self.max_session_recreate_attempts - 1:
                        raise

                    # Recreate session and retry
                    try:
                        self._recreate_session_with_state_recovery()
                        # Update URL with new session_id if endpoint contains session reference
                        if self._session_id and '{session_id}' not in endpoint:
                            # Replace old session_id in URL
                            url = urljoin(self.base_url, endpoint.lstrip('/'))
                        # Exponential backoff before retry
                        time.sleep(0.5 * (2 ** attempt))
                        continue  # Retry the request
                    except Exception:
                        # Session recreation failed, re-raise original error
                        raise e
                else:
                    # Not a 404 or auto-recreate disabled, re-raise
                    raise

    # ========================================================================
    # Root Endpoint
    # ========================================================================

    def get_root_info(self) -> Dict[str, Any]:
        """
        Get root service information.

        Returns:
            Service information including version, uptime, architecture

        Example:
            >>> client = KATOClient()
            >>> info = client.get_root_info()
            >>> print(info['version'])
            '1.0.0'
        """
        return self._request('GET', '/')

    # ========================================================================
    # Session Management (Internal)
    # ========================================================================

    def get_session_info(self) -> Dict[str, Any]:
        """
        Get complete session information including configuration.

        This returns the ACTUAL session configuration that's being used,
        not the processor's default genes.

        Returns:
            Dictionary with:
            - session_id: Session identifier
            - node_id: Node this session is connected to
            - created_at: Session creation timestamp
            - expires_at: Session expiration timestamp
            - ttl_seconds: Remaining time to live
            - metadata: Session metadata
            - session_config: Current session configuration (THIS is what matters!)

        Example:
            >>> info = client.get_session_info()
            >>> print(info['session_config']['recall_threshold'])
            0.6  # This is the ACTUAL value being used
        """
        return self._request('GET', f'/sessions/{self._session_id}')

    def get_session_config(self) -> Dict[str, Any]:
        """
        Get the current session configuration.

        This is the ACTUAL configuration being used for this session's operations.
        Use this instead of get_gene() to check your session's config.

        Returns:
            Dictionary of session configuration parameters

        Example:
            >>> config = client.get_session_config()
            >>> print(config['recall_threshold'])
            0.6  # The value you set when creating the client

            >>> # Compare to get_gene (WRONG - returns processor default):
            >>> gene = client.get_gene('recall_threshold')
            >>> print(gene['value'])
            0.1  # This is NOT what your session is using!
        """
        info = self.get_session_info()
        return info.get('session_config', {})

    def extend_session(self, ttl_seconds: int = 3600) -> Dict[str, Any]:
        """
        Extend session expiration time.

        Args:
            ttl_seconds: New TTL in seconds (default: 3600)

        Returns:
            Status response

        Example:
            >>> result = client.extend_session(ttl_seconds=7200)
        """
        return self._request('POST', f'/sessions/{self._session_id}/extend', params={'ttl_seconds': ttl_seconds})

    def check_session_exists(self) -> Dict[str, Any]:
        """
        Check if session exists without extending its TTL.

        This is useful for checking session status without triggering auto-extension.
        When SESSION_AUTO_EXTEND is enabled on the server, normal operations like
        get_stm() will extend the session TTL. Use this method to check expiration
        status without side effects.

        Returns:
            Dictionary with:
            - exists: Whether session exists in Redis
            - expired: Whether session has expired
            - session_id: The session identifier

        Example:
            >>> status = client.check_session_exists()
            >>> if status['expired']:
            ...     print("Session has expired!")
            >>> elif status['exists']:
            ...     print("Session is still active")
        """
        return self._request('GET', f'/sessions/{self._session_id}/exists')

    def close(self) -> None:
        """
        Close the client and delete the session.

        This is called automatically when using the client as a context manager.

        Example:
            >>> client = KATOClient(node_id="user123")
            >>> # ... use client ...
            >>> client.close()
        """
        try:
            self._request('DELETE', f'/sessions/{self._session_id}')
        except Exception:
            pass  # Ignore errors during cleanup
        finally:
            self._http_session.close()

    # ========================================================================
    # Core KATO Operations
    # ========================================================================

    def observe(
        self,
        strings: Optional[List[str]] = None,
        vectors: Optional[List[List[float]]] = None,
        emotives: Optional[Dict[str, float]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Process an observation.

        Args:
            strings: List of string symbols to observe
            vectors: List of vector embeddings (768-dim recommended)
            emotives: Emotional values as {emotion_name: value} (values -1.0 to 1.0)
            metadata: Pattern metadata as {key: value} (stored as unique string lists)

        Returns:
            Observation result with status, stm_length, time, etc.

        Example:
            >>> result = client.observe(
            ...     strings=["hello", "world"],
            ...     emotives={"happiness": 0.8, "arousal": 0.5},
            ...     metadata={"book": "title1", "chapter": "1"}
            ... )
            >>> print(result['stm_length'])
            1
        """
        data = {
            'strings': strings or [],
            'vectors': vectors or [],
            'emotives': emotives or {},
            'metadata': metadata or {}
        }
        return self._request('POST', f'/sessions/{self._session_id}/observe', data=data)

    def get_stm(self) -> Dict[str, Any]:
        """
        Get short-term memory.

        Returns:
            STM response with stm list and length

        Example:
            >>> stm_data = client.get_stm()
            >>> print(stm_data['stm'])
            [['hello', 'world'], ['foo', 'bar']]
        """
        return self._request('GET', f'/sessions/{self._session_id}/stm')

    def learn(self) -> Dict[str, Any]:
        """
        Learn a pattern from the current STM.

        Returns:
            Learn result with pattern_name and status

        Example:
            >>> result = client.learn()
            >>> print(result['pattern_name'])
            'PTRN|a1b2c3...'
        """
        return self._request('POST', f'/sessions/{self._session_id}/learn')

    def clear_stm(self) -> Dict[str, Any]:
        """
        Clear the short-term memory.

        Returns:
            Status response

        Example:
            >>> result = client.clear_stm()
            >>> print(result['status'])
            'cleared'
        """
        return self._request('POST', f'/sessions/{self._session_id}/clear-stm')

    def observe_sequence(
        self,
        observations: List[Dict[str, Any]],
        learn_after_each: bool = False,
        learn_at_end: bool = False,
        clear_stm_between: bool = False
    ) -> Dict[str, Any]:
        """
        Process multiple observations in sequence.

        Args:
            observations: List of observation dicts with strings/vectors/emotives/metadata
            learn_after_each: Whether to learn after each observation
            learn_at_end: Whether to learn from final STM state
            clear_stm_between: Whether to clear STM between observations (isolation)

        Returns:
            Sequence result with status, observations_processed, results, etc.

        Example:
            >>> result = client.observe_sequence(
            ...     observations=[
            ...         {'strings': ['A', 'B'], 'metadata': {'book': 'title1'}},
            ...         {'strings': ['C', 'D'], 'metadata': {'book': 'title2'}},
            ...         {'strings': ['E', 'F'], 'metadata': {'chapter': '1'}}
            ...     ],
            ...     learn_at_end=True
            ... )
            >>> print(result['observations_processed'])
            3
        """
        data = {
            'observations': observations,
            'learn_after_each': learn_after_each,
            'learn_at_end': learn_at_end,
            'clear_stm_between': clear_stm_between
        }
        return self._request('POST', f'/sessions/{self._session_id}/observe-sequence', data=data)

    def get_predictions(self) -> Dict[str, Any]:
        """
        Get predictions based on the current STM.

        Returns:
            Predictions response with predictions list, future_potentials, count

        Example:
            >>> result = client.get_predictions()
            >>> for pred in result['predictions']:
            ...     print(pred['future'])
        """
        return self._request('GET', f'/sessions/{self._session_id}/predictions')

    # ========================================================================
    # Configuration Management
    # ========================================================================
    # NOTE: All methods operate on this client's node (self.node_id).
    # To access multiple nodes, create multiple KATOClient instances.

    def update_session_config(
        self,
        config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Update session configuration (RECOMMENDED method).

        This is the proper way to update configuration in KATO v2.1.0+.
        Configuration changes affect this session immediately and persist
        across requests.

        Available configuration parameters:
            - max_pattern_length: int (0+) - Auto-learn after N observations
            - persistence: int (1-100) - Rolling window size for emotives
            - recall_threshold: float (0.0-1.0) - Pattern matching threshold
            - stm_mode: str - STM mode 'CLEAR' or 'ROLLING'
            - indexer_type: str - Vector indexer type
            - max_predictions: int (1-10000) - Max predictions to return
            - sort_symbols: bool - Sort symbols alphabetically
            - process_predictions: bool - Enable prediction processing
            - use_token_matching: bool - Token-level vs character-level matching

        Args:
            config: Configuration parameters to update

        Returns:
            Status response with updated configuration

        Example:
            >>> # Update recall threshold for this session
            >>> result = client.update_session_config({
            ...     'recall_threshold': 0.1,
            ...     'max_predictions': 100,
            ...     'process_predictions': True
            ... })
            >>> print(result['status'])
            'okay'

            >>> # Changes take effect immediately on next operation
            >>> predictions = client.get_predictions()  # Uses recall_threshold=0.1
        """
        data = {'config': config}
        return self._request('POST', f'/sessions/{self._session_id}/config', data=data)

    def get_pattern(
        self,
        pattern_id: str
    ) -> Dict[str, Any]:
        """
        Get a specific pattern by ID from this client's node.

        Args:
            pattern_id: Pattern identifier (e.g., "PTRN|a1b2c3...")

        Returns:
            Pattern data

        Example:
            >>> result = client.get_pattern("PTRN|abc123...")
            >>> print(result['pattern'])
        """
        params = {'node_id': self.node_id}
        return self._request('GET', f'/pattern/{pattern_id}', params=params)

    def get_percept_data(self) -> Dict[str, Any]:
        """
        Get current percept data from this client's node.

        Returns:
            Percept data

        Example:
            >>> result = client.get_percept_data()
            >>> print(result['percept_data'])
        """
        params = {'node_id': self.node_id}
        return self._request('GET', '/percept-data', params=params)

    def get_cognition_data(self) -> Dict[str, Any]:
        """
        Get current cognition data from this client's node.

        Returns:
            Cognition data

        Example:
            >>> result = client.get_cognition_data()
            >>> print(result['cognition_data'])
        """
        params = {'node_id': self.node_id}
        return self._request('GET', '/cognition-data', params=params)

    # ========================================================================
    # Monitoring and Metrics
    # ========================================================================

    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get Redis pattern cache performance statistics.

        Returns:
            Cache performance stats and health

        Example:
            >>> stats = client.get_cache_stats()
            >>> print(stats['cache_performance'])
        """
        return self._request('GET', '/cache/stats')

    def invalidate_cache(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Invalidate pattern cache (optionally for specific session).

        Args:
            session_id: Optional session identifier to invalidate

        Returns:
            Invalidation result with counts

        Example:
            >>> result = client.invalidate_cache()
            >>> print(result['patterns_invalidated'])
        """
        params = {'session_id': session_id} if session_id else None
        return self._request('POST', '/cache/invalidate', params=params)

    def get_distributed_stm_stats(self) -> Dict[str, Any]:
        """
        Get distributed STM performance statistics and health.

        Returns:
            Distributed STM stats

        Example:
            >>> stats = client.get_distributed_stm_stats()
            >>> print(stats['status'])
        """
        return self._request('GET', '/distributed-stm/stats')

    def get_metrics(self) -> Dict[str, Any]:
        """
        Get comprehensive metrics including system resources and performance.

        Returns:
            Comprehensive metrics including sessions, performance, resources, databases

        Example:
            >>> metrics = client.get_metrics()
            >>> print(metrics['performance']['total_requests'])
        """
        return self._request('GET', '/metrics')

    def get_stats(self, minutes: int = 10) -> Dict[str, Any]:
        """
        Get time-series statistics for the last N minutes.

        Args:
            minutes: Number of minutes of history (default: 10)

        Returns:
            Time-series statistics

        Example:
            >>> stats = client.get_stats(minutes=30)
            >>> print(stats['time_series'])
        """
        return self._request('GET', '/stats', params={'minutes': minutes})

    def get_metric_history(self, metric_name: str, minutes: int = 10) -> Dict[str, Any]:
        """
        Get time series data for a specific metric.

        Args:
            metric_name: Name of metric (e.g., 'cpu_percent', 'memory_percent')
            minutes: Number of minutes of history (default: 10)

        Returns:
            Metric history with statistics and data points

        Example:
            >>> history = client.get_metric_history('cpu_percent', minutes=30)
            >>> print(history['statistics']['avg'])
        """
        return self._request('GET', f'/metrics/{metric_name}', params={'minutes': minutes})

    def get_connection_pools_status(self) -> Dict[str, Any]:
        """
        Get connection pool health and statistics.

        Returns:
            Connection pool status for MongoDB, Redis, Qdrant

        Example:
            >>> status = client.get_connection_pools_status()
            >>> print(status['health'])
        """
        return self._request('GET', '/connection-pools')

    # ========================================================================
    # Health and Status
    # ========================================================================

    def health_check(self) -> Dict[str, Any]:
        """
        Check service health.

        Returns:
            Health status with processor status, uptime, active sessions

        Example:
            >>> health = client.health_check()
            >>> print(health['status'])
            'healthy'
        """
        return self._request('GET', '/health')

    def get_status(self) -> Dict[str, Any]:
        """
        Get overall system status including session statistics.

        Returns:
            System status with sessions, processors, uptime

        Example:
            >>> status = client.get_status()
            >>> print(status['sessions'])
        """
        return self._request('GET', '/status')

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - close session and cleanup."""
        self.close()


# ============================================================================
# Example Usage
# ============================================================================

if __name__ == "__main__":
    # Example 1: Basic workflow with context manager
    print("=== Example 1: Basic Workflow (Context Manager) ===")
    with KATOClient(
        base_url="http://localhost:8000",
        node_id="user123",
        max_pattern_length=5,
        recall_threshold=0.5,
        stm_mode="ROLLING",
        metadata={"user": "Alice", "app": "demo"}
    ) as client:
        print(f"Created session: {client._session_id}")

        # Observe with metadata
        obs1 = client.observe(
            strings=["hello", "world"],
            metadata={"book": "Alice in Wonderland", "chapter": "1"}
        )
        print(f"Observed: {obs1['stm_length']} events in STM")

        obs2 = client.observe(
            strings=["foo", "bar"],
            metadata={"book": "Alice in Wonderland", "chapter": "2"}
        )
        print(f"Observed: {obs2['stm_length']} events in STM")

        # Learn pattern
        learn_result = client.learn()
        print(f"Learned pattern: {learn_result['pattern_name']}")

        # Clear and observe again
        client.clear_stm()
        obs3 = client.observe(strings=["hello", "world"])

        # Get predictions
        predictions = client.get_predictions()
        print(f"Got {predictions['count']} predictions")

    print("Session auto-deleted on exit\n")

    # Example 2: Manual cleanup
    print("=== Example 2: Manual Cleanup ===")
    client = KATOClient(
        base_url="http://localhost:8000",
        node_id="user456"
    )

    client.observe(strings=["A", "B"])
    client.observe(strings=["C", "D"])
    client.learn()

    # Manual cleanup
    client.close()
    print("Session manually deleted\n")

    # Example 3: Bulk sequence processing
    print("=== Example 3: Bulk Sequence Processing ===")
    client = KATOClient(
        base_url="http://localhost:8000",
        node_id="user789"
    )

    result = client.observe_sequence(
        observations=[
            {'strings': ['A', 'B'], 'metadata': {'source': 'dataset1'}},
            {'strings': ['C', 'D'], 'metadata': {'source': 'dataset2'}},
            {'strings': ['E', 'F'], 'metadata': {'source': 'dataset1', 'tag': 'important'}}
        ],
        learn_at_end=True
    )
    print(f"Processed {result['observations_processed']} observations")
    print(f"Final STM length: {result['final_stm_length']}")

    client.close()

    # Example 4: Monitoring
    print("\n=== Example 4: Monitoring ===")
    client = KATOClient(
        base_url="http://localhost:8000",
        node_id="monitor_node"
    )

    health = client.health_check()
    print(f"Health: {health['status']}")

    metrics = client.get_metrics()
    print(f"Total requests: {metrics.get('performance', {}).get('total_requests', 0)}")

    client.close()

    # Example 5: Configuration updates
    print("\n=== Example 5: Dynamic Configuration Updates ===")
    client = KATOClient(
        base_url="http://localhost:8000",
        node_id="config_demo",
        recall_threshold=0.5,  # Initial config
        max_predictions=50
    )

    # Observe and learn some patterns
    client.observe(strings=["hello", "world"])
    client.observe(strings=["foo", "bar"])
    client.learn()

    # Update configuration dynamically
    print("Updating session configuration...")
    config_result = client.update_session_config({
        'recall_threshold': 0.1,  # More permissive matching
        'max_predictions': 100,   # More predictions
        'process_predictions': True
    })
    print(f"Config updated: {config_result['status']}")

    # New config takes effect immediately
    client.clear_stm()
    client.observe(strings=["hello", "world"])
    predictions = client.get_predictions()  # Uses new recall_threshold=0.1
    print(f"Got {predictions['count']} predictions with new config")

    client.close()

    print("\nAll examples completed!")
