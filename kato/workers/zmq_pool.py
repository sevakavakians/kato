#!/usr/bin/env python3
"""
Thread-local ZeroMQ connection pool for the REST gateway.
Provides persistent, thread-safe ZMQ client connections to avoid connection churn.
"""

import logging
import threading
import time
from typing import Optional
import zmq

from kato.workers.zmq_client import ZMQClient

logger = logging.getLogger('kato.zmq_pool')


class ZMQConnectionPool:
    """Thread-local connection pool for ZMQ clients.
    
    Each thread gets its own ZMQ client instance since ZMQ sockets are not thread-safe.
    This avoids the overhead of creating/destroying connections for each request.
    """
    
    def __init__(self, host='localhost', port=5555, timeout=5000, 
                 health_check_interval=30, reconnect_interval=1000):
        """Initialize the connection pool.
        
        Args:
            host: ZMQ server hostname
            port: ZMQ server port
            timeout: Socket timeout in milliseconds
            health_check_interval: Seconds between health checks
            reconnect_interval: Milliseconds between reconnection attempts
        """
        self.host = host
        self.port = port
        self.timeout = timeout
        self.health_check_interval = health_check_interval
        self.reconnect_interval = reconnect_interval
        
        # Thread-local storage for ZMQ clients
        self._local = threading.local()
        
        # Statistics
        self._stats_lock = threading.Lock()
        self._total_connections = 0
        self._active_connections = 0
        self._total_requests = 0
        self._failed_requests = 0
        self._reconnections = 0
        
    def get_client(self) -> ZMQClient:
        """Get or create a thread-local ZMQ client.
        
        Returns:
            ZMQClient instance for the current thread
        """
        # Check if this thread already has a client
        if not hasattr(self._local, 'client') or self._local.client is None:
            self._create_client()
            
        # Check if the client needs health check
        if hasattr(self._local, 'last_health_check'):
            if time.time() - self._local.last_health_check > self.health_check_interval:
                self._health_check()
                
        return self._local.client
    
    def _create_client(self):
        """Create a new ZMQ client for the current thread."""
        logger.debug(f"Creating new ZMQ client for thread {threading.current_thread().name}")
        
        # Create the client
        self._local.client = ZMQClient(
            host=self.host,
            port=self.port,
            timeout=self.timeout
        )
        
        # Initialize health check timestamp
        self._local.last_health_check = time.time()
        self._local.connection_reuses = 0
        
        # Update statistics
        with self._stats_lock:
            self._total_connections += 1
            self._active_connections += 1
            
        logger.info(f"Created ZMQ client #{self._total_connections} for thread {threading.current_thread().name}")
    
    def _health_check(self):
        """Perform a health check on the current thread's client."""
        try:
            # Try a simple ping to check connection health
            client = self._local.client
            if client:
                # First check if the client thinks it's connected
                if not client.is_connected():
                    logger.warning(f"Client not connected for thread {threading.current_thread().name}, reconnecting...")
                    self._reconnect()
                    return
                
                # Try a ping to verify the connection is actually working
                if not client.ping():
                    logger.warning(f"Ping failed for thread {threading.current_thread().name}, reconnecting...")
                    self._reconnect()
                else:
                    # Update health check timestamp on successful ping
                    self._local.last_health_check = time.time()
        except Exception as e:
            logger.error(f"Health check error: {e}")
            self._reconnect()
            
    def _reconnect(self):
        """Reconnect the current thread's client."""
        logger.info(f"Reconnecting ZMQ client for thread {threading.current_thread().name}")
        
        # Close existing client
        if hasattr(self._local, 'client') and self._local.client:
            try:
                self._local.client.close()
            except Exception as e:
                logger.error(f"Error closing client: {e}")
            
            with self._stats_lock:
                self._active_connections -= 1
                self._reconnections += 1
        
        # Wait before reconnecting
        time.sleep(self.reconnect_interval / 1000.0)
        
        # Create new client
        self._create_client()
    
    def execute(self, method: str, *args, **kwargs):
        """Execute a method on the thread-local client with automatic retry.
        
        Args:
            method: Method name to call on the client
            *args: Positional arguments for the method
            **kwargs: Keyword arguments for the method
            
        Returns:
            Result from the method call
            
        Raises:
            Exception: If the method fails after retry
        """
        client = self.get_client()
        
        # Track connection reuse
        self._local.connection_reuses += 1
        
        with self._stats_lock:
            self._total_requests += 1
        
        try:
            # Get the method from the client
            client_method = getattr(client, method)
            result = client_method(*args, **kwargs)
            
            logger.debug(f"Thread {threading.current_thread().name} reused connection "
                        f"(reuse #{self._local.connection_reuses})")
            
            return result
            
        except zmq.ZMQError as e:
            logger.error(f"ZMQ error in {method}: {e}, attempting reconnection...")
            
            with self._stats_lock:
                self._failed_requests += 1
            
            # Try to reconnect and retry once
            self._reconnect()
            
            try:
                client = self.get_client()
                client_method = getattr(client, method)
                return client_method(*args, **kwargs)
            except Exception as retry_error:
                logger.error(f"Retry failed for {method}: {retry_error}")
                raise
                
        except Exception as e:
            logger.error(f"Error executing {method}: {e}")
            
            with self._stats_lock:
                self._failed_requests += 1
                
            raise
    
    def cleanup_thread(self):
        """Clean up the current thread's client."""
        if hasattr(self._local, 'client') and self._local.client:
            try:
                self._local.client.close()
                with self._stats_lock:
                    self._active_connections -= 1
                logger.debug(f"Cleaned up ZMQ client for thread {threading.current_thread().name}")
            except Exception as e:
                logger.error(f"Error cleaning up client: {e}")
            finally:
                self._local.client = None
    
    def shutdown(self):
        """Shutdown the connection pool and clean up all connections."""
        logger.info("Shutting down ZMQ connection pool")
        
        # Note: We can't easily clean up other threads' connections,
        # but we can clean up the current thread's connection
        self.cleanup_thread()
        
        logger.info(f"Connection pool statistics: "
                   f"Total connections: {self._total_connections}, "
                   f"Active: {self._active_connections}, "
                   f"Total requests: {self._total_requests}, "
                   f"Failed: {self._failed_requests}, "
                   f"Reconnections: {self._reconnections}")
    
    def get_stats(self) -> dict:
        """Get connection pool statistics.
        
        Returns:
            Dictionary with pool statistics
        """
        with self._stats_lock:
            return {
                'total_connections': self._total_connections,
                'active_connections': self._active_connections,
                'total_requests': self._total_requests,
                'failed_requests': self._failed_requests,
                'reconnections': self._reconnections,
                'failure_rate': self._failed_requests / max(1, self._total_requests)
            }


# Global connection pool instance
_global_pool: Optional[ZMQConnectionPool] = None


def get_global_pool() -> ZMQConnectionPool:
    """Get or create the global connection pool.
    
    Returns:
        The global ZMQConnectionPool instance
    """
    global _global_pool
    if _global_pool is None:
        _global_pool = ZMQConnectionPool()
    return _global_pool


def set_global_pool(pool: ZMQConnectionPool):
    """Set the global connection pool.
    
    Args:
        pool: The ZMQConnectionPool instance to use globally
    """
    global _global_pool
    _global_pool = pool


def cleanup_global_pool():
    """Clean up the global connection pool."""
    global _global_pool
    if _global_pool:
        _global_pool.shutdown()
        _global_pool = None