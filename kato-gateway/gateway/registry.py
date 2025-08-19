"""
Processor registry for maintaining processor-to-instance mappings
"""

import logging
import grpc
from typing import Dict, Optional, Set
from threading import Lock
import time

logger = logging.getLogger(__name__)


class ProcessorRegistry:
    """
    Maintains registry of KATO processors and their gRPC connections.
    Implements sticky routing to ensure stateful processing.
    """
    
    def __init__(self, max_connections: int = 10):
        self.processors: Dict[str, str] = {}  # processor_id -> grpc_endpoint
        self.connections: Dict[str, grpc.Channel] = {}  # processor_id -> grpc channel
        self.connection_health: Dict[str, bool] = {}  # processor_id -> is_healthy
        self.last_health_check: Dict[str, float] = {}  # processor_id -> timestamp
        self.max_connections = max_connections
        self._lock = Lock()
        
    def register_processor(self, processor_id: str, grpc_endpoint: str, name: str = None) -> None:
        """Register a processor with its gRPC endpoint"""
        with self._lock:
            self.processors[processor_id] = grpc_endpoint
            self.connection_health[processor_id] = False
            self.last_health_check[processor_id] = 0
            logger.info(f"Registered processor {processor_id} ({name}) at {grpc_endpoint}")
    
    def unregister_processor(self, processor_id: str) -> None:
        """Unregister a processor and close its connection"""
        with self._lock:
            if processor_id in self.connections:
                try:
                    self.connections[processor_id].close()
                except Exception as e:
                    logger.error(f"Error closing connection for {processor_id}: {e}")
                del self.connections[processor_id]
            
            if processor_id in self.processors:
                del self.processors[processor_id]
                del self.connection_health[processor_id]
                del self.last_health_check[processor_id]
                logger.info(f"Unregistered processor {processor_id}")
    
    def get_channel(self, processor_id: str) -> Optional[grpc.Channel]:
        """
        Get or create gRPC channel for processor (sticky routing).
        Returns None if processor not found or connection failed.
        """
        with self._lock:
            # Check if processor is registered
            if processor_id not in self.processors:
                logger.error(f"Processor {processor_id} not registered")
                return None
            
            # Return existing connection if healthy
            if processor_id in self.connections:
                if self._is_connection_healthy(processor_id):
                    return self.connections[processor_id]
                else:
                    # Close unhealthy connection
                    try:
                        self.connections[processor_id].close()
                    except:
                        pass
                    del self.connections[processor_id]
            
            # Create new connection
            endpoint = self.processors[processor_id]
            try:
                channel = grpc.insecure_channel(
                    endpoint,
                    options=[
                        ('grpc.keepalive_time_ms', 10000),
                        ('grpc.keepalive_timeout_ms', 5000),
                        ('grpc.keepalive_permit_without_calls', True),
                        ('grpc.http2.max_pings_without_data', 0),
                    ]
                )
                
                # Test the connection with a simple call
                # We'll implement a proper health check later
                self.connections[processor_id] = channel
                self.connection_health[processor_id] = True
                self.last_health_check[processor_id] = time.time()
                
                logger.info(f"Created new gRPC connection to {processor_id} at {endpoint}")
                return channel
                
            except Exception as e:
                logger.error(f"Failed to create connection to {processor_id} at {endpoint}: {e}")
                self.connection_health[processor_id] = False
                return None
    
    def _is_connection_healthy(self, processor_id: str) -> bool:
        """
        Check if a connection is healthy.
        Performs periodic health checks to ensure connection is alive.
        """
        # Check if we need a new health check (every 30 seconds)
        now = time.time()
        if now - self.last_health_check.get(processor_id, 0) > 30:
            # Perform health check (will be implemented with actual gRPC ping)
            # For now, assume connection is healthy if it exists
            self.connection_health[processor_id] = processor_id in self.connections
            self.last_health_check[processor_id] = now
        
        return self.connection_health.get(processor_id, False)
    
    def has_processor(self, processor_id: str) -> bool:
        """Check if a processor is registered"""
        return processor_id in self.processors
    
    def get_all_processors(self) -> Dict[str, str]:
        """Get all registered processors"""
        with self._lock:
            return self.processors.copy()
    
    def get_healthy_processors(self) -> Set[str]:
        """Get IDs of all healthy processors"""
        with self._lock:
            return {pid for pid, healthy in self.connection_health.items() if healthy}
    
    def close_all_connections(self) -> None:
        """Close all gRPC connections"""
        with self._lock:
            for processor_id, channel in self.connections.items():
                try:
                    channel.close()
                except Exception as e:
                    logger.error(f"Error closing connection for {processor_id}: {e}")
            self.connections.clear()
            logger.info("Closed all gRPC connections")