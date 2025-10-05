"""
Database Query Batching Utilities

Provides batching capabilities for common database operations to reduce
round-trip latency and improve throughput in high-traffic scenarios.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Generic, List, Optional, TypeVar

logger = logging.getLogger('kato.storage.query_batcher')

T = TypeVar('T')


@dataclass
class BatchRequest:
    """Represents a single request in a batch."""
    key: str
    future: asyncio.Future
    timestamp: float


class QueryBatcher(Generic[T]):
    """
    Generic query batcher that accumulates requests and executes them in batches.
    
    Useful for operations like:
    - Multiple session lookups
    - Batch pattern retrievals
    - Multiple database writes
    """

    def __init__(
        self,
        batch_executor: Callable[[List[str]], Dict[str, T]],
        max_batch_size: int = 50,
        max_wait_time: float = 0.01,  # 10ms
        enable_batching: bool = True
    ):
        """
        Initialize the query batcher.
        
        Args:
            batch_executor: Function that takes a list of keys and returns a dict of results
            max_batch_size: Maximum number of requests to batch together
            max_wait_time: Maximum time to wait before executing a partial batch (seconds)
            enable_batching: Whether to enable batching (can be disabled for debugging)
        """
        self.batch_executor = batch_executor
        self.max_batch_size = max_batch_size
        self.max_wait_time = max_wait_time
        self.enable_batching = enable_batching

        # Pending requests
        self._pending_requests: List[BatchRequest] = []
        self._batch_lock = asyncio.Lock()
        self._batch_task: Optional[asyncio.Task] = None

        # Statistics
        self.stats = {
            'total_requests': 0,
            'batches_executed': 0,
            'average_batch_size': 0.0,
            'total_time_saved_ms': 0.0
        }

    async def get(self, key: str) -> Optional[T]:
        """
        Get a single item, potentially batched with other concurrent requests.
        
        Args:
            key: The key to retrieve
            
        Returns:
            The retrieved item or None if not found
        """
        if not self.enable_batching:
            # Bypass batching for debugging or single-threaded scenarios
            result = self.batch_executor([key])
            return result.get(key)

        # Create a future for this request
        future = asyncio.Future()
        request = BatchRequest(
            key=key,
            future=future,
            timestamp=time.time()
        )

        async with self._batch_lock:
            self._pending_requests.append(request)
            self.stats['total_requests'] += 1

            # Start batch timer if this is the first request
            if len(self._pending_requests) == 1:
                self._batch_task = asyncio.create_task(self._batch_timer())

            # Execute immediately if batch is full
            if len(self._pending_requests) >= self.max_batch_size:
                await self._execute_batch()

        # Wait for the result
        return await future

    async def get_many(self, keys: List[str]) -> Dict[str, T]:
        """
        Get multiple items efficiently.
        
        Args:
            keys: List of keys to retrieve
            
        Returns:
            Dictionary mapping keys to their values
        """
        if not keys:
            return {}

        if not self.enable_batching or len(keys) >= self.max_batch_size:
            # Execute directly for large requests or when batching is disabled
            return self.batch_executor(keys)

        # Use individual gets which will be automatically batched
        tasks = [self.get(key) for key in keys]
        results = await asyncio.gather(*tasks)

        return {key: result for key, result in zip(keys, results) if result is not None}

    async def _batch_timer(self):
        """Timer that triggers batch execution after max_wait_time."""
        try:
            await asyncio.sleep(self.max_wait_time)
            async with self._batch_lock:
                if self._pending_requests:  # Check if there are still pending requests
                    await self._execute_batch()
        except asyncio.CancelledError:
            # Timer was cancelled because batch was executed early
            pass

    async def _execute_batch(self):
        """Execute the current batch of pending requests."""
        if not self._pending_requests:
            return

        # Take all pending requests
        requests = self._pending_requests[:]
        self._pending_requests.clear()

        # Cancel the timer if it's running
        if self._batch_task and not self._batch_task.done():
            self._batch_task.cancel()
            self._batch_task = None

        # Extract keys and execute batch
        keys = [req.key for req in requests]
        batch_start = time.time()

        try:
            logger.debug(f"Executing batch with {len(keys)} items")
            results = self.batch_executor(keys)
            batch_duration = (time.time() - batch_start) * 1000  # Convert to ms

            # Update statistics
            self.stats['batches_executed'] += 1
            batch_count = self.stats['batches_executed']
            self.stats['average_batch_size'] = (
                (self.stats['average_batch_size'] * (batch_count - 1) + len(keys)) / batch_count
            )

            # Estimate time saved (rough calculation)
            estimated_individual_time = len(keys) * 2.0  # Assume 2ms per individual query
            time_saved = max(0, estimated_individual_time - batch_duration)
            self.stats['total_time_saved_ms'] += time_saved

            # Set results for all futures
            for request in requests:
                result = results.get(request.key)
                if not request.future.done():
                    request.future.set_result(result)

        except Exception as e:
            logger.error(f"Batch execution failed: {e}")
            # Set exception for all futures
            for request in requests:
                if not request.future.done():
                    request.future.set_exception(e)

    def get_stats(self) -> Dict[str, Any]:
        """Get batching statistics."""
        return {
            **self.stats,
            'pending_requests': len(self._pending_requests),
            'batching_enabled': self.enable_batching
        }


class SessionBatcher:
    """Specialized batcher for session operations."""

    def __init__(self, session_manager, max_batch_size: int = 20):
        """
        Initialize session batcher.
        
        Args:
            session_manager: The session manager instance
            max_batch_size: Maximum sessions to fetch in one batch
        """
        self.session_manager = session_manager

        # Create the actual batch executor function
        async def batch_get_sessions(session_ids: List[str]) -> Dict[str, Any]:
            """Batch fetch multiple sessions."""
            results = {}

            # Use Redis pipeline for efficient batch operations if using Redis
            if hasattr(session_manager, 'redis_client'):
                try:
                    pipe = session_manager.redis_client.pipeline()
                    for session_id in session_ids:
                        key = f"session:{session_id}"
                        pipe.get(key)

                    redis_results = pipe.execute()

                    for session_id, redis_result in zip(session_ids, redis_results):
                        if redis_result:
                            try:
                                import json
                                session_data = json.loads(redis_result)
                                results[session_id] = session_data
                            except (json.JSONDecodeError, AttributeError):
                                logger.warning(f"Failed to decode session {session_id}")

                except Exception as e:
                    logger.error(f"Redis batch operation failed: {e}")
                    # Fall back to individual operations
                    for session_id in session_ids:
                        try:
                            session = await session_manager.get_session(session_id)
                            if session:
                                results[session_id] = session
                        except Exception as individual_error:
                            logger.warning(f"Failed to get session {session_id}: {individual_error}")
            else:
                # Fall back to individual operations for non-Redis session managers
                for session_id in session_ids:
                    try:
                        session = await session_manager.get_session(session_id)
                        if session:
                            results[session_id] = session
                    except Exception as e:
                        logger.warning(f"Failed to get session {session_id}: {e}")

            return results

        # Wrap the async function for the batcher
        def sync_batch_executor(session_ids: List[str]) -> Dict[str, Any]:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # We're in an async context, need to handle this carefully
                return asyncio.create_task(batch_get_sessions(session_ids))
            else:
                return loop.run_until_complete(batch_get_sessions(session_ids))

        self.batcher = QueryBatcher(
            batch_executor=sync_batch_executor,
            max_batch_size=max_batch_size,
            max_wait_time=0.005,  # 5ms for sessions (faster response needed)
        )

    async def get_session(self, session_id: str):
        """Get a session with potential batching."""
        return await self.batcher.get(session_id)

    async def get_sessions(self, session_ids: List[str]) -> Dict[str, Any]:
        """Get multiple sessions efficiently."""
        return await self.batcher.get_many(session_ids)

    def get_stats(self) -> Dict[str, Any]:
        """Get batching statistics."""
        return self.batcher.get_stats()


# Global session batcher instance (initialized when first session manager is available)
_session_batcher: Optional[SessionBatcher] = None


def get_session_batcher(session_manager) -> SessionBatcher:
    """Get or create a session batcher instance."""
    global _session_batcher

    if _session_batcher is None:
        _session_batcher = SessionBatcher(session_manager)
        logger.info("Session batcher initialized")

    return _session_batcher
