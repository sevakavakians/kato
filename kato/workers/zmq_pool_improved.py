#!/usr/bin/env python3
"""
Improved connection pool for DEALER/ROUTER pattern.
Provides persistent, thread-safe ZMQ client connections with better long-lived connection support.
"""

import logging
import threading
import time
from typing import Optional, Dict, Any
from collections import deque
import uuid

from kato.workers.zmq_client_improved import ImprovedZMQClient

logger = logging.getLogger('kato.zmq_pool_improved')


class ImprovedConnectionPool:
    """
    Connection pool for improved ZMQ clients using DEALER sockets.
    
    Unlike the legacy pool that uses thread-local storage, this pool maintains
    a shared pool of persistent connections that can be reused across threads.
    This is more efficient for long-lived connections.
    """
    
    def __init__(self, host='localhost', port=5555, timeout=5000,
                 min_connections=1, max_connections=10,
                 connection_lifetime=3600, heartbeat_interval=10000):
        """Initialize the improved connection pool.
        
        Args:
            host: ZMQ server hostname
            port: ZMQ server port
            timeout: Request timeout in milliseconds
            min_connections: Minimum number of connections to maintain
            max_connections: Maximum number of connections allowed
            connection_lifetime: Maximum lifetime of a connection in seconds
            heartbeat_interval: Milliseconds between heartbeats
        """
        self.host = host
        self.port = port
        self.timeout = timeout
        self.min_connections = min_connections
        self.max_connections = max_connections
        self.connection_lifetime = connection_lifetime
        self.heartbeat_interval = heartbeat_interval
        
        # Connection pool
        self._pool = deque()
        self._active_connections = {}
        self._lock = threading.RLock()
        
        # Statistics
        self._stats_lock = threading.Lock()
        self._total_connections_created = 0
        self._total_requests = 0
        self._successful_requests = 0
        self._failed_requests = 0
        self._connection_reuses = 0
        
        # Pool management
        self._running = True
        self._manager_thread = None
        
        # Start pool manager
        self._start_manager()
        
    def _start_manager(self):
        """Start the connection pool manager thread."""
        self._manager_thread = threading.Thread(
            target=self._manage_pool,
            daemon=True,
            name="ZMQPoolManager"
        )
        self._manager_thread.start()
        logger.info("Connection pool manager started")
        
    def _manage_pool(self):
        """Manage the connection pool - maintain minimum connections and clean up old ones."""
        while self._running:
            try:
                with self._lock:
                    current_time = time.time()
                    
                    # Remove expired connections
                    expired = []
                    for conn_info in list(self._pool):
                        if current_time - conn_info['created_at'] > self.connection_lifetime:
                            expired.append(conn_info)
                            
                    for conn_info in expired:
                        try:
                            self._pool.remove(conn_info)
                            conn_info['client'].close()
                            logger.debug(f"Removed expired connection {conn_info['id']}")
                        except Exception as e:
                            logger.error(f"Error removing expired connection: {e}")
                    
                    # Ensure minimum connections
                    pool_size = len(self._pool)
                    active_size = len(self._active_connections)
                    total_size = pool_size + active_size
                    
                    if total_size < self.min_connections:
                        needed = self.min_connections - total_size
                        for _ in range(needed):
                            try:
                                self._create_connection()
                            except Exception as e:
                                logger.error(f"Failed to create minimum connection: {e}")
                                break
                    
                    # Send heartbeats to idle connections
                    for conn_info in list(self._pool):
                        client = conn_info['client']
                        last_used = conn_info.get('last_used', conn_info['created_at'])
                        
                        if current_time - last_used > self.heartbeat_interval / 1000:
                            try:
                                if client.ping():
                                    conn_info['last_heartbeat'] = current_time
                                else:
                                    # Connection is dead, remove it
                                    self._pool.remove(conn_info)
                                    client.close()
                                    logger.warning(f"Removed dead connection {conn_info['id']}")
                            except Exception as e:
                                logger.error(f"Heartbeat failed for {conn_info['id']}: {e}")
                                self._pool.remove(conn_info)
                                client.close()
                
                # Sleep before next management cycle
                time.sleep(5)
                
            except Exception as e:
                logger.error(f"Error in pool manager: {e}")
                time.sleep(5)
                
    def _create_connection(self) -> Dict[str, Any]:
        """Create a new connection and add it to the pool.
        
        Returns:
            Connection info dictionary
        """
        client = ImprovedZMQClient(
            host=self.host,
            port=self.port,
            timeout=self.timeout,
            heartbeat_interval=self.heartbeat_interval
        )
        
        try:
            client.connect()
            
            conn_info = {
                'id': str(uuid.uuid4()),
                'client': client,
                'created_at': time.time(),
                'last_used': time.time(),
                'request_count': 0
            }
            
            self._pool.append(conn_info)
            
            with self._stats_lock:
                self._total_connections_created += 1
                
            logger.debug(f"Created connection {conn_info['id']}")
            return conn_info
            
        except Exception as e:
            logger.error(f"Failed to create connection: {e}")
            client.close()
            raise
            
    def acquire(self) -> tuple:
        """Acquire a connection from the pool.
        
        Returns:
            Tuple of (client, connection_id) for tracking
            
        Raises:
            RuntimeError: If no connections available
        """
        with self._lock:
            # Try to get an existing connection from the pool
            while self._pool:
                conn_info = self._pool.popleft()
                
                # Check if connection is still valid
                if conn_info['client'].is_connected():
                    # Move to active connections
                    conn_id = conn_info['id']
                    self._active_connections[conn_id] = conn_info
                    conn_info['last_used'] = time.time()
                    
                    with self._stats_lock:
                        self._connection_reuses += 1
                        
                    logger.debug(f"Acquired connection {conn_id} from pool")
                    return conn_info['client'], conn_id
                else:
                    # Connection is dead, close it
                    try:
                        conn_info['client'].close()
                    except:
                        pass
                        
            # No connections available, create a new one if under limit
            total_connections = len(self._pool) + len(self._active_connections)
            
            if total_connections < self.max_connections:
                try:
                    conn_info = self._create_connection()
                    # Don't add to pool, move directly to active
                    self._pool.remove(conn_info)
                    conn_id = conn_info['id']
                    self._active_connections[conn_id] = conn_info
                    
                    logger.debug(f"Created and acquired new connection {conn_id}")
                    return conn_info['client'], conn_id
                    
                except Exception as e:
                    logger.error(f"Failed to create new connection: {e}")
                    raise RuntimeError(f"Failed to create connection: {e}")
            else:
                raise RuntimeError(f"Connection pool exhausted (max: {self.max_connections})")
                
    def release(self, conn_id: str):
        """Release a connection back to the pool.
        
        Args:
            conn_id: Connection ID to release
        """
        with self._lock:
            if conn_id in self._active_connections:
                conn_info = self._active_connections.pop(conn_id)
                
                # Check if connection is still valid and pool not full
                if conn_info['client'].is_connected() and len(self._pool) < self.max_connections:
                    # Return to pool
                    conn_info['last_used'] = time.time()
                    self._pool.append(conn_info)
                    logger.debug(f"Released connection {conn_id} back to pool")
                else:
                    # Close the connection
                    try:
                        conn_info['client'].close()
                    except:
                        pass
                    logger.debug(f"Closed connection {conn_id} instead of returning to pool")
            else:
                logger.warning(f"Attempted to release unknown connection {conn_id}")
                
    def execute(self, method: str, params: Optional[Dict] = None, 
                timeout: Optional[int] = None) -> Dict[str, Any]:
        """Execute a method using a pooled connection.
        
        Args:
            method: Method name to call
            params: Optional parameters
            timeout: Optional timeout override
            
        Returns:
            Response from the server
            
        Raises:
            Exception: If execution fails
        """
        conn_id = None
        
        with self._stats_lock:
            self._total_requests += 1
            
        try:
            # Acquire a connection
            client, conn_id = self.acquire()
            
            # Execute the request
            result = client.call(method, params, timeout)
            
            with self._stats_lock:
                self._successful_requests += 1
                
            return result
            
        except Exception as e:
            logger.error(f"Error executing {method}: {e}")
            
            with self._stats_lock:
                self._failed_requests += 1
                
            # Don't return failed connections to pool
            if conn_id and conn_id in self._active_connections:
                with self._lock:
                    conn_info = self._active_connections.pop(conn_id, None)
                    if conn_info:
                        try:
                            conn_info['client'].close()
                        except:
                            pass
                            
            raise
            
        finally:
            # Release the connection back to pool
            if conn_id:
                self.release(conn_id)
                
    def shutdown(self):
        """Shutdown the connection pool and close all connections."""
        logger.info("Shutting down improved connection pool")
        
        self._running = False
        
        with self._lock:
            # Close all pooled connections
            for conn_info in self._pool:
                try:
                    conn_info['client'].close()
                except Exception as e:
                    logger.error(f"Error closing pooled connection: {e}")
                    
            # Close all active connections
            for conn_info in self._active_connections.values():
                try:
                    conn_info['client'].close()
                except Exception as e:
                    logger.error(f"Error closing active connection: {e}")
                    
            self._pool.clear()
            self._active_connections.clear()
            
        logger.info(f"Connection pool shutdown complete. Stats: {self.get_stats()}")
        
    def get_stats(self) -> Dict[str, Any]:
        """Get pool statistics.
        
        Returns:
            Dictionary with pool statistics
        """
        with self._lock:
            pool_size = len(self._pool)
            active_size = len(self._active_connections)
            
        with self._stats_lock:
            return {
                'pool_size': pool_size,
                'active_connections': active_size,
                'total_connections': pool_size + active_size,
                'total_created': self._total_connections_created,
                'total_requests': self._total_requests,
                'successful_requests': self._successful_requests,
                'failed_requests': self._failed_requests,
                'success_rate': self._successful_requests / max(1, self._total_requests),
                'connection_reuses': self._connection_reuses,
                'reuse_rate': self._connection_reuses / max(1, self._total_requests)
            }
            
    def __enter__(self):
        """Context manager entry."""
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.shutdown()


# Global improved pool instance
_global_improved_pool: Optional[ImprovedConnectionPool] = None


def get_improved_pool() -> ImprovedConnectionPool:
    """Get or create the global improved connection pool.
    
    Returns:
        The global ImprovedConnectionPool instance
    """
    global _global_improved_pool
    if _global_improved_pool is None:
        _global_improved_pool = ImprovedConnectionPool()
    return _global_improved_pool


def set_improved_pool(pool: ImprovedConnectionPool):
    """Set the global improved connection pool.
    
    Args:
        pool: The ImprovedConnectionPool instance to use globally
    """
    global _global_improved_pool
    if _global_improved_pool:
        _global_improved_pool.shutdown()
    _global_improved_pool = pool


def cleanup_improved_pool():
    """Clean up the global improved connection pool."""
    global _global_improved_pool
    if _global_improved_pool:
        _global_improved_pool.shutdown()
        _global_improved_pool = None


if __name__ == "__main__":
    # Test the improved pool
    logging.basicConfig(level=logging.DEBUG)
    
    print("Testing improved connection pool...")
    
    with ImprovedConnectionPool(min_connections=2, max_connections=5) as pool:
        print(f"Initial stats: {pool.get_stats()}")
        
        # Test sequential requests
        for i in range(10):
            try:
                response = pool.execute('ping')
                print(f"Request {i+1}: {response.get('status')}")
            except Exception as e:
                print(f"Request {i+1} failed: {e}")
                
        print(f"After sequential: {pool.get_stats()}")
        
        # Test concurrent requests
        import concurrent.futures
        
        def make_request(n):
            try:
                return pool.execute('ping')
            except Exception as e:
                return {'error': str(e)}
                
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(make_request, i) for i in range(20)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]
            
        success_count = sum(1 for r in results if r.get('status') == 'okay')
        print(f"Concurrent requests: {success_count}/20 successful")
        
        print(f"Final stats: {pool.get_stats()}")