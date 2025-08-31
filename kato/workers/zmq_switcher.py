#!/usr/bin/env python3
"""
ZeroMQ implementation switcher for transitioning between REQ/REP and DEALER/ROUTER patterns.
This allows gradual migration and testing of the improved implementation.
"""

import logging
import os
from typing import Optional

logger = logging.getLogger('kato.zmq_switcher')


def get_zmq_implementation() -> str:
    """Get the configured ZMQ implementation type.
    
    Returns:
        Always returns 'improved' for DEALER/ROUTER pattern
    """
    # Always use improved implementation - legacy code removed
    return 'improved'


def get_zmq_server(primitive, port=5555):
    """Get the ZMQ server implementation.
    
    Args:
        primitive: The KatoProcessor instance
        port: Port to bind the server
        
    Returns:
        ImprovedZMQServer instance
    """
    logger.info("Using improved ZMQ server (DEALER/ROUTER pattern)")
    from kato.workers.zmq_server import ImprovedZMQServer
    return ImprovedZMQServer(primitive, port)


def get_zmq_client(host='localhost', port=5555, timeout=5000):
    """Get the ZMQ client implementation.
    
    Args:
        host: Server hostname
        port: Server port  
        timeout: Request timeout in milliseconds
        
    Returns:
        ImprovedZMQClient instance
    """
    logger.info("Using improved ZMQ client (DEALER socket)")
    from kato.workers.zmq_client_improved import ImprovedZMQClient
    return ImprovedZMQClient(host, port, timeout)


def migrate_to_improved():
    """Helper to migrate to the improved implementation."""
    os.environ['KATO_ZMQ_IMPLEMENTATION'] = 'improved'
    logger.info("Migrated to improved ZMQ implementation (DEALER/ROUTER)")
    

def rollback_to_legacy():
    """Helper to rollback to the legacy implementation."""
    os.environ['KATO_ZMQ_IMPLEMENTATION'] = 'legacy'
    logger.info("Rolled back to legacy ZMQ implementation (REQ/REP)")


class ZMQClientFactory:
    """Factory for creating ZMQ clients."""
    
    @staticmethod
    def create_client(host='localhost', port=5555, timeout=5000, 
                     force_implementation: Optional[str] = None):
        """Create a ZMQ client.
        
        Args:
            host: Server hostname
            port: Server port
            timeout: Request timeout
            force_implementation: Deprecated parameter, kept for compatibility
            
        Returns:
            ImprovedZMQClient instance
        """
        return get_zmq_client(host, port, timeout)
    
    @staticmethod
    def create_pooled_client(host='localhost', port=5555, timeout=5000):
        """Create a connection-pooled client.
        
        Args:
            host: Server hostname
            port: Server port
            timeout: Request timeout
            
        Returns:
            ImprovedZMQConnectionPool instance
        """
        from kato.workers.zmq_pool_improved import ImprovedZMQConnectionPool
        return ImprovedZMQConnectionPool(host, port, timeout)


def test_implementation(implementation: str):
    """Test a specific ZMQ implementation.
    
    Args:
        implementation: 'legacy' or 'improved'
    """
    import time
    
    logger.info(f"Testing {implementation} implementation...")
    
    # Set implementation
    os.environ['KATO_ZMQ_IMPLEMENTATION'] = implementation
    
    # Create client
    client = get_zmq_client()
    
    try:
        # Test ping
        start = time.time()
        for i in range(10):
            try:
                if hasattr(client, 'ping'):
                    result = client.ping()
                else:
                    # Legacy client doesn't have ping, use get_name
                    result = client.get_name()
                    result = result.get('status') == 'okay'
                    
                if not result:
                    logger.error(f"Ping {i+1} failed")
            except Exception as e:
                logger.error(f"Ping {i+1} error: {e}")
                
        elapsed = time.time() - start
        logger.info(f"{implementation} completed 10 pings in {elapsed:.2f}s")
        
        # Show stats if available
        if hasattr(client, 'get_stats'):
            logger.info(f"Stats: {client.get_stats()}")
            
    finally:
        client.close()


if __name__ == "__main__":
    # Test both implementations
    logging.basicConfig(level=logging.INFO)
    
    print("Testing ZMQ implementation switcher...")
    print(f"Current implementation: {get_zmq_implementation()}")
    print()
    
    # Test legacy
    test_implementation('legacy')
    print()
    
    # Test improved
    test_implementation('improved')
    print()
    
    print("Testing complete!")