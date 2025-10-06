"""
KATO Python Client - Comprehensive API Wrapper

This is a complete Python client for the KATO API that can be copied into any project.
It covers all 40+ KATO API endpoints including session management, observations,
learning, predictions, monitoring, and more.

USAGE:
    from sample_kato_client import KATOClient

    # Create client
    client = KATOClient(base_url="http://localhost:8000")

    # Session-based workflow (recommended for multi-user)
    session = client.create_session(node_id="user123")
    client.observe_in_session(session['session_id'], strings=["hello", "world"])
    predictions = client.get_session_predictions(session['session_id'])

    # Direct workflow (backward compatible, single user)
    client.observe(strings=["hello", "world"], processor_id="default")
    predictions = client.get_predictions(processor_id="default")

Author: KATO Team
Version: 1.0.0
"""

import json
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urljoin

import requests


class KATOClient:
    """
    Comprehensive Python client for KATO API.

    Provides access to all KATO endpoints including:
    - Session Management (multi-user support)
    - Observations and Learning
    - Predictions and Pattern Retrieval
    - Configuration Management
    - Monitoring and Metrics
    - Health Checks

    Configuration Parameters (all optional, use system defaults if not set):
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
    """

    def __init__(self, base_url: str = "http://localhost:8000", timeout: int = 30):
        """
        Initialize KATO client.

        Args:
            base_url: Base URL of KATO service (default: http://localhost:8000)
            timeout: Request timeout in seconds (default: 30)
        """
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.session = requests.Session()

    def _request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None,
        params: Optional[Dict] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Internal method to make HTTP requests.

        Args:
            method: HTTP method (GET, POST, DELETE, etc.)
            endpoint: API endpoint path
            data: Request body data
            params: Query parameters
            **kwargs: Additional arguments for requests

        Returns:
            Response JSON as dictionary

        Raises:
            requests.HTTPError: On HTTP error responses
        """
        url = urljoin(self.base_url, endpoint.lstrip('/'))

        kwargs.setdefault('timeout', self.timeout)
        if data is not None:
            kwargs['json'] = data
        if params is not None:
            kwargs['params'] = params

        response = self.session.request(method, url, **kwargs)
        response.raise_for_status()

        return response.json()

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
    # Session Management Endpoints
    # ========================================================================

    def create_session(
        self,
        node_id: str,
        metadata: Optional[Dict[str, Any]] = None,
        ttl_seconds: Optional[int] = None,
        config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create a new isolated session for multi-user support.

        Args:
            node_id: Node identifier (required for processor isolation)
            metadata: Optional session metadata
            ttl_seconds: Session TTL in seconds (default: 3600)
            config: Optional session configuration (see class docstring for params)

        Returns:
            Session response with session_id, node_id, created_at, expires_at, etc.

        Example:
            >>> client = KATOClient()
            >>> session = client.create_session(
            ...     node_id="user123",
            ...     metadata={"user": "Alice"},
            ...     config={"max_pattern_length": 5, "recall_threshold": 0.5}
            ... )
            >>> session_id = session['session_id']
        """
        data = {
            'node_id': node_id,
            'metadata': metadata or {},
        }
        if ttl_seconds is not None:
            data['ttl_seconds'] = ttl_seconds

        session = self._request('POST', '/sessions', data=data)

        # Update config if provided
        if config:
            self.update_session_config(session['session_id'], config)

        return session

    def get_session(self, session_id: str) -> Dict[str, Any]:
        """
        Get information about a specific session.

        Args:
            session_id: Session identifier

        Returns:
            Session information

        Example:
            >>> info = client.get_session(session_id)
            >>> print(info['node_id'])
        """
        return self._request('GET', f'/sessions/{session_id}')

    def delete_session(self, session_id: str) -> Dict[str, Any]:
        """
        Delete a session and cleanup resources.

        Args:
            session_id: Session identifier

        Returns:
            Status response

        Example:
            >>> result = client.delete_session(session_id)
            >>> print(result['status'])
            'deleted'
        """
        return self._request('DELETE', f'/sessions/{session_id}')

    def get_session_count(self) -> int:
        """
        Get count of active sessions.

        Returns:
            Number of active sessions

        Example:
            >>> count = client.get_session_count()
            >>> print(f"{count} active sessions")
        """
        result = self._request('GET', '/sessions/count')
        return result['active_session_count']

    def update_session_config(
        self,
        session_id: str,
        config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Update session configuration (genes/parameters).

        Args:
            session_id: Session identifier
            config: Configuration parameters to update (see class docstring)

        Returns:
            Status response

        Example:
            >>> result = client.update_session_config(
            ...     session_id,
            ...     {
            ...         "max_pattern_length": 5,
            ...         "recall_threshold": 0.5,
            ...         "stm_mode": "ROLLING"
            ...     }
            ... )
        """
        return self._request('POST', f'/sessions/{session_id}/config', data={'config': config})

    def extend_session(self, session_id: str, ttl_seconds: int = 3600) -> Dict[str, Any]:
        """
        Extend session expiration time.

        Args:
            session_id: Session identifier
            ttl_seconds: New TTL in seconds (default: 3600)

        Returns:
            Status response

        Example:
            >>> result = client.extend_session(session_id, ttl_seconds=7200)
        """
        return self._request('POST', f'/sessions/{session_id}/extend', params={'ttl_seconds': ttl_seconds})

    def test_session_endpoint(self, test_id: str) -> Dict[str, Any]:
        """
        Test endpoint to verify session routing works.

        Args:
            test_id: Test identifier

        Returns:
            Test response
        """
        return self._request('GET', f'/sessions/test/{test_id}')

    # ========================================================================
    # Session-Based KATO Operations
    # ========================================================================

    def observe_in_session(
        self,
        session_id: str,
        strings: Optional[List[str]] = None,
        vectors: Optional[List[List[float]]] = None,
        emotives: Optional[Dict[str, float]] = None
    ) -> Dict[str, Any]:
        """
        Process an observation in a specific session context.

        This is the recommended method for multi-user applications.
        Each session maintains its own isolated STM.

        Args:
            session_id: Session identifier
            strings: List of string symbols to observe
            vectors: List of vector embeddings (768-dim recommended)
            emotives: Emotional values as {emotion_name: value} (values -1.0 to 1.0)

        Returns:
            Observation result with status, stm_length, time, etc.

        Example:
            >>> result = client.observe_in_session(
            ...     session_id,
            ...     strings=["hello", "world"],
            ...     emotives={"happiness": 0.8, "arousal": 0.5}
            ... )
            >>> print(result['stm_length'])
            1
        """
        data = {
            'strings': strings or [],
            'vectors': vectors or [],
            'emotives': emotives or {}
        }
        return self._request('POST', f'/sessions/{session_id}/observe', data=data)

    def get_session_stm(self, session_id: str) -> Dict[str, Any]:
        """
        Get short-term memory for a specific session.

        Args:
            session_id: Session identifier

        Returns:
            STM response with stm list and length

        Example:
            >>> stm_data = client.get_session_stm(session_id)
            >>> print(stm_data['stm'])
            [['hello', 'world'], ['foo', 'bar']]
        """
        return self._request('GET', f'/sessions/{session_id}/stm')

    def learn_in_session(self, session_id: str) -> Dict[str, Any]:
        """
        Learn a pattern from the session's current STM.

        Args:
            session_id: Session identifier

        Returns:
            Learn result with pattern_name and status

        Example:
            >>> result = client.learn_in_session(session_id)
            >>> print(result['pattern_name'])
            'PTRN|a1b2c3...'
        """
        return self._request('POST', f'/sessions/{session_id}/learn')

    def clear_session_stm(self, session_id: str) -> Dict[str, Any]:
        """
        Clear the STM for a specific session.

        Args:
            session_id: Session identifier

        Returns:
            Status response

        Example:
            >>> result = client.clear_session_stm(session_id)
            >>> print(result['status'])
            'cleared'
        """
        return self._request('POST', f'/sessions/{session_id}/clear-stm')

    def observe_sequence_in_session(
        self,
        session_id: str,
        observations: List[Dict[str, Any]],
        learn_after_each: bool = False,
        learn_at_end: bool = False,
        clear_stm_between: bool = False
    ) -> Dict[str, Any]:
        """
        Process multiple observations in sequence within a session.

        Args:
            session_id: Session identifier
            observations: List of observation dicts with strings/vectors/emotives
            learn_after_each: Whether to learn after each observation
            learn_at_end: Whether to learn from final STM state
            clear_stm_between: Whether to clear STM between observations (isolation)

        Returns:
            Sequence result with status, observations_processed, results, etc.

        Example:
            >>> result = client.observe_sequence_in_session(
            ...     session_id,
            ...     observations=[
            ...         {'strings': ['A', 'B']},
            ...         {'strings': ['C', 'D']},
            ...         {'strings': ['E', 'F']}
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
        return self._request('POST', f'/sessions/{session_id}/observe-sequence', data=data)

    def get_session_predictions(self, session_id: str) -> Dict[str, Any]:
        """
        Get predictions based on the session's current STM.

        Args:
            session_id: Session identifier

        Returns:
            Predictions response with predictions list, future_potentials, count

        Example:
            >>> result = client.get_session_predictions(session_id)
            >>> for pred in result['predictions']:
            ...     print(pred['future'])
        """
        return self._request('GET', f'/sessions/{session_id}/predictions')

    # ========================================================================
    # Direct KATO Operations (DEPRECATED - Use Session-Based Instead)
    # ========================================================================
    #
    # ⚠️  WARNING: Direct endpoints are DEPRECATED and will be removed in a future version.
    #
    # These methods use header-based processor isolation which lacks:
    # - Redis-backed session persistence
    # - Explicit session locking for thread safety
    # - Proper TTL and lifecycle management
    # - Strong multi-user isolation guarantees
    #
    # RECOMMENDED: Use session-based methods instead:
    # - create_session() → observe_in_session() → learn_in_session() → get_session_predictions()
    #
    # These direct methods are provided for backward compatibility only.
    # ========================================================================

    def observe(
        self,
        strings: Optional[List[str]] = None,
        vectors: Optional[List[List[float]]] = None,
        emotives: Optional[Dict[str, float]] = None,
        processor_id: Optional[str] = None,
        node_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Process an observation (direct mode, DEPRECATED).

        ⚠️  DEPRECATED: Use session-based methods instead.
        Recommended: create_session() → observe_in_session()

        Uses header-based processor isolation. For multi-user apps,
        prefer session-based methods for better state persistence and isolation.

        Args:
            strings: List of string symbols to observe
            vectors: List of vector embeddings
            emotives: Emotional values
            processor_id: Optional processor identifier (query param)
            node_id: Optional node identifier (X-Node-ID header)

        Returns:
            Observation result

        Example:
            >>> # DEPRECATED approach:
            >>> result = client.observe(
            ...     strings=["hello", "world"],
            ...     processor_id="default"
            ... )
            >>>
            >>> # RECOMMENDED approach:
            >>> session = client.create_session(node_id="user123")
            >>> result = client.observe_in_session(
            ...     session['session_id'],
            ...     strings=["hello", "world"]
            ... )
        """
        data = {
            'strings': strings or [],
            'vectors': vectors or [],
            'emotives': emotives or {}
        }
        params = {'processor_id': processor_id} if processor_id else None
        headers = {'X-Node-ID': node_id} if node_id else None

        return self._request('POST', '/observe', data=data, params=params, headers=headers)

    def get_stm(
        self,
        processor_id: Optional[str] = None,
        node_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get short-term memory (direct mode, DEPRECATED).

        ⚠️  DEPRECATED: Use get_session_stm() instead.

        Args:
            processor_id: Optional processor identifier
            node_id: Optional node identifier (X-Node-ID header)

        Returns:
            STM response

        Example:
            >>> # DEPRECATED:
            >>> stm_data = client.get_stm(processor_id="default")
            >>>
            >>> # RECOMMENDED:
            >>> stm_data = client.get_session_stm(session_id)
        """
        params = {'processor_id': processor_id} if processor_id else None
        headers = {'X-Node-ID': node_id} if node_id else None

        return self._request('GET', '/stm', params=params, headers=headers)

    def get_short_term_memory(
        self,
        processor_id: Optional[str] = None,
        node_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Alias for get_stm(). Get short-term memory (direct mode).

        Args:
            processor_id: Optional processor identifier
            node_id: Optional node identifier

        Returns:
            STM response
        """
        params = {'processor_id': processor_id} if processor_id else None
        headers = {'X-Node-ID': node_id} if node_id else None

        return self._request('GET', '/short-term-memory', params=params, headers=headers)

    def learn(
        self,
        processor_id: Optional[str] = None,
        node_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Learn a pattern from current STM (direct mode, DEPRECATED).

        ⚠️  DEPRECATED: Use learn_in_session() instead.

        Args:
            processor_id: Optional processor identifier
            node_id: Optional node identifier

        Returns:
            Learn result with pattern_name

        Example:
            >>> # DEPRECATED:
            >>> result = client.learn(processor_id="default")
            >>>
            >>> # RECOMMENDED:
            >>> result = client.learn_in_session(session_id)
        """
        params = {'processor_id': processor_id} if processor_id else None
        headers = {'X-Node-ID': node_id} if node_id else None

        return self._request('POST', '/learn', params=params, headers=headers)

    def clear_stm(
        self,
        processor_id: Optional[str] = None,
        node_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Clear short-term memory (direct mode).

        Args:
            processor_id: Optional processor identifier
            node_id: Optional node identifier

        Returns:
            Status response

        Example:
            >>> result = client.clear_stm(processor_id="default")
        """
        params = {'processor_id': processor_id} if processor_id else None
        headers = {'X-Node-ID': node_id} if node_id else None

        return self._request('POST', '/clear-stm', params=params, headers=headers)

    def clear_short_term_memory(
        self,
        processor_id: Optional[str] = None,
        node_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Alias for clear_stm(). Clear short-term memory (direct mode).

        Args:
            processor_id: Optional processor identifier
            node_id: Optional node identifier

        Returns:
            Status response
        """
        params = {'processor_id': processor_id} if processor_id else None
        headers = {'X-Node-ID': node_id} if node_id else None

        return self._request('POST', '/clear-short-term-memory', params=params, headers=headers)

    def clear_all(self, processor_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Clear all processor state (STM, patterns, symbols).

        WARNING: This deletes all learned knowledge for the processor.

        Args:
            processor_id: Optional processor identifier

        Returns:
            Status response

        Example:
            >>> result = client.clear_all(processor_id="default")
        """
        params = {'processor_id': processor_id} if processor_id else None
        return self._request('POST', '/clear-all', params=params)

    def clear_all_memory(self, processor_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Alias for clear_all(). Clear all processor state.

        WARNING: This deletes all learned knowledge for the processor.

        Args:
            processor_id: Optional processor identifier

        Returns:
            Status response
        """
        params = {'processor_id': processor_id} if processor_id else None
        return self._request('POST', '/clear-all-memory', params=params)

    def get_predictions(self, processor_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get predictions based on current STM (direct mode, DEPRECATED).

        ⚠️  DEPRECATED: Use get_session_predictions() instead.

        Args:
            processor_id: Optional processor identifier

        Returns:
            Predictions response

        Example:
            >>> # DEPRECATED:
            >>> result = client.get_predictions(processor_id="default")
            >>>
            >>> # RECOMMENDED:
            >>> result = client.get_session_predictions(session_id)
        """
        params = {'processor_id': processor_id} if processor_id else None
        return self._request('GET', '/predictions', params=params)

    def post_predictions(self, processor_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get predictions based on current STM (direct mode, POST).

        Args:
            processor_id: Optional processor identifier

        Returns:
            Predictions response
        """
        params = {'processor_id': processor_id} if processor_id else None
        return self._request('POST', '/predictions', params=params)

    def observe_sequence(
        self,
        observations: List[Dict[str, Any]],
        learn_after_each: bool = False,
        learn_at_end: bool = False,
        clear_stm_between: bool = False,
        processor_id: Optional[str] = None,
        node_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Process multiple observations in sequence (direct mode).

        Args:
            observations: List of observation dicts
            learn_after_each: Learn after each observation
            learn_at_end: Learn from final STM
            clear_stm_between: Clear STM between observations
            processor_id: Optional processor identifier
            node_id: Optional node identifier

        Returns:
            Sequence result

        Example:
            >>> result = client.observe_sequence(
            ...     observations=[
            ...         {'strings': ['A', 'B']},
            ...         {'strings': ['C', 'D']}
            ...     ],
            ...     learn_at_end=True,
            ...     processor_id="default"
            ... )
        """
        data = {
            'observations': observations,
            'learn_after_each': learn_after_each,
            'learn_at_end': learn_at_end,
            'clear_stm_between': clear_stm_between
        }
        params = {'processor_id': processor_id} if processor_id else None
        headers = {'X-Node-ID': node_id} if node_id else None

        return self._request('POST', '/observe-sequence', data=data, params=params, headers=headers)

    # ========================================================================
    # Gene and Pattern Management
    # ========================================================================

    def update_genes(
        self,
        genes: Dict[str, Any],
        processor_id: Optional[str] = None,
        node_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Update processor genes/configuration (direct mode).

        Args:
            genes: Gene configuration to update (see class docstring for params)
            processor_id: Optional processor identifier
            node_id: Optional node identifier

        Returns:
            Status response

        Example:
            >>> result = client.update_genes(
            ...     {
            ...         "max_pattern_length": 5,
            ...         "recall_threshold": 0.5,
            ...         "stm_mode": "ROLLING"
            ...     },
            ...     processor_id="default"
            ... )
        """
        data = {'genes': genes}
        params = {'processor_id': processor_id} if processor_id else None
        headers = {'X-Node-ID': node_id} if node_id else None

        return self._request('POST', '/genes/update', data=data, params=params, headers=headers)

    def get_gene(
        self,
        gene_name: str,
        processor_id: Optional[str] = None,
        node_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get a specific gene value.

        Args:
            gene_name: Name of gene to retrieve
            processor_id: Optional processor identifier
            node_id: Optional node identifier

        Returns:
            Gene response with gene name and value

        Example:
            >>> result = client.get_gene("max_pattern_length", processor_id="default")
            >>> print(result['value'])
        """
        params = {'processor_id': processor_id} if processor_id else None
        headers = {'X-Node-ID': node_id} if node_id else None

        return self._request('GET', f'/gene/{gene_name}', params=params, headers=headers)

    def get_pattern(
        self,
        pattern_id: str,
        processor_id: Optional[str] = None,
        node_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get a specific pattern by ID.

        Args:
            pattern_id: Pattern identifier (e.g., "PTRN|a1b2c3...")
            processor_id: Optional processor identifier
            node_id: Optional node identifier

        Returns:
            Pattern data

        Example:
            >>> result = client.get_pattern("PTRN|abc123...", processor_id="default")
            >>> print(result['pattern'])
        """
        params = {'processor_id': processor_id} if processor_id else None
        headers = {'X-Node-ID': node_id} if node_id else None

        return self._request('GET', f'/pattern/{pattern_id}', params=params, headers=headers)

    def get_percept_data(self, processor_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get current percept data from processor.

        Args:
            processor_id: Optional processor identifier

        Returns:
            Percept data

        Example:
            >>> result = client.get_percept_data(processor_id="default")
            >>> print(result['percept_data'])
        """
        params = {'processor_id': processor_id} if processor_id else None
        return self._request('GET', '/percept-data', params=params)

    def get_cognition_data(
        self,
        processor_id: Optional[str] = None,
        node_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get current cognition data from processor.

        Args:
            processor_id: Optional processor identifier
            node_id: Optional node identifier

        Returns:
            Cognition data

        Example:
            >>> result = client.get_cognition_data(processor_id="default")
            >>> print(result['cognition_data'])
        """
        params = {'processor_id': processor_id} if processor_id else None
        headers = {'X-Node-ID': node_id} if node_id else None

        return self._request('GET', '/cognition-data', params=params, headers=headers)

    # ========================================================================
    # Monitoring and Metrics Endpoints
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
        Get comprehensive v2 metrics including system resources and performance.

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
    # Health and Status Endpoints
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

    # ========================================================================
    # Helper Methods - Common Workflows
    # ========================================================================

    def create_session_and_observe(
        self,
        node_id: str,
        strings: List[str],
        vectors: Optional[List[List[float]]] = None,
        emotives: Optional[Dict[str, float]] = None,
        config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Helper: Create session and immediately observe.

        Args:
            node_id: Node identifier
            strings: String symbols to observe
            vectors: Optional vector embeddings
            emotives: Optional emotional values
            config: Optional session configuration

        Returns:
            Dict with 'session' and 'observation' results

        Example:
            >>> result = client.create_session_and_observe(
            ...     node_id="user123",
            ...     strings=["hello", "world"],
            ...     config={"max_pattern_length": 5}
            ... )
            >>> session_id = result['session']['session_id']
        """
        session = self.create_session(node_id=node_id, config=config)
        observation = self.observe_in_session(
            session['session_id'],
            strings=strings,
            vectors=vectors,
            emotives=emotives
        )

        return {
            'session': session,
            'observation': observation
        }

    def observe_learn_predict_workflow(
        self,
        session_id: str,
        observations: List[List[str]],
        learn: bool = True
    ) -> Dict[str, Any]:
        """
        Helper: Complete workflow - observe sequence, learn, predict.

        Args:
            session_id: Session identifier
            observations: List of observation string lists
            learn: Whether to learn from observations (default: True)

        Returns:
            Dict with 'observations', 'learn_result', and 'predictions'

        Example:
            >>> result = client.observe_learn_predict_workflow(
            ...     session_id,
            ...     observations=[['A', 'B'], ['C', 'D'], ['E', 'F']],
            ...     learn=True
            ... )
            >>> print(result['predictions']['count'])
        """
        results = {
            'observations': [],
            'learn_result': None,
            'predictions': None
        }

        # Observe each
        for obs_strings in observations:
            obs_result = self.observe_in_session(session_id, strings=obs_strings)
            results['observations'].append(obs_result)

        # Learn if requested
        if learn:
            results['learn_result'] = self.learn_in_session(session_id)

        # Get predictions
        results['predictions'] = self.get_session_predictions(session_id)

        return results

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - close session."""
        self.session.close()


# ============================================================================
# Example Usage
# ============================================================================

if __name__ == "__main__":
    # Example 1: Session-based workflow (RECOMMENDED - best practice)
    print("=== Example 1: Session-Based Workflow (RECOMMENDED) ===")
    client = KATOClient(base_url="http://localhost:8000")

    # Create session with configuration
    session = client.create_session(
        node_id="user123",
        metadata={"user": "Alice", "app": "demo"},
        config={
            "max_pattern_length": 5,
            "recall_threshold": 0.5,
            "stm_mode": "ROLLING"
        }
    )
    session_id = session['session_id']
    print(f"Created session: {session_id}")

    # Observe in session
    obs1 = client.observe_in_session(session_id, strings=["hello", "world"])
    print(f"Observed: {obs1['stm_length']} events in STM")

    obs2 = client.observe_in_session(session_id, strings=["foo", "bar"])
    print(f"Observed: {obs2['stm_length']} events in STM")

    # Learn pattern
    learn_result = client.learn_in_session(session_id)
    print(f"Learned pattern: {learn_result['pattern_name']}")

    # Clear and observe again
    client.clear_session_stm(session_id)
    obs3 = client.observe_in_session(session_id, strings=["hello", "world"])

    # Get predictions
    predictions = client.get_session_predictions(session_id)
    print(f"Got {predictions['count']} predictions")

    # Cleanup
    client.delete_session(session_id)
    print("Session deleted\n")

    # Example 2: Direct workflow (DEPRECATED - backward compatibility only)
    print("=== Example 2: Direct Workflow (DEPRECATED) ===")
    print("⚠️  WARNING: Direct endpoints are deprecated. Use session-based workflow instead.\n")
    processor_id = "demo_processor"

    # Update configuration
    client.update_genes(
        {"max_pattern_length": 3, "recall_threshold": 0.3},
        processor_id=processor_id
    )

    # Observe
    client.observe(strings=["A", "B"], processor_id=processor_id)
    client.observe(strings=["C", "D"], processor_id=processor_id)

    # Learn
    learn_result = client.learn(processor_id=processor_id)
    print(f"Learned pattern: {learn_result['pattern_name']}")

    # Clear and observe again
    client.clear_stm(processor_id=processor_id)
    client.observe(strings=["A", "B"], processor_id=processor_id)

    # Get predictions
    predictions = client.get_predictions(processor_id=processor_id)
    print(f"Got {predictions['count']} predictions")

    # Example 3: Bulk sequence processing
    print("\n=== Example 3: Bulk Sequence Processing ===")
    session2 = client.create_session(node_id="user456")

    result = client.observe_sequence_in_session(
        session2['session_id'],
        observations=[
            {'strings': ['A', 'B']},
            {'strings': ['C', 'D']},
            {'strings': ['E', 'F']}
        ],
        learn_at_end=True
    )
    print(f"Processed {result['observations_processed']} observations")
    print(f"Final STM length: {result['final_stm_length']}")

    # Cleanup
    client.delete_session(session2['session_id'])

    # Example 4: Monitoring
    print("\n=== Example 4: Monitoring ===")
    health = client.health_check()
    print(f"Health: {health['status']}")

    metrics = client.get_metrics()
    print(f"Active sessions: {metrics.get('active_sessions', 0)}")

    print("\nAll examples completed!")
