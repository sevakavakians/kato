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
        'improved' for DEALER/ROUTER pattern, 'legacy' for REQ/REP pattern
    """
    impl = os.environ.get('KATO_ZMQ_IMPLEMENTATION', 'legacy').lower()
    if impl not in ['legacy', 'improved']:
        logger.warning(f"Invalid ZMQ implementation '{impl}', using 'legacy'")
        return 'legacy'
    return impl


def get_zmq_server(primitive, port=5555):
    """Get the appropriate ZMQ server implementation.
    
    Args:
        primitive: The KatoProcessor instance
        port: Port to bind the server
        
    Returns:
        ZMQServer or ImprovedZMQServer instance
    """
    impl = get_zmq_implementation()
    
    if impl == 'improved':
        logger.info("Using improved ZMQ server (DEALER/ROUTER pattern)")
        from kato.workers.zmq_server_improved import ImprovedZMQServer
        return ImprovedZMQServer(primitive, port)
    else:
        logger.info("Using legacy ZMQ server (REQ/REP pattern)")
        from kato.workers.zmq_server import ZMQServer
        return ZMQServer(primitive, port)


def get_zmq_client(host='localhost', port=5555, timeout=5000):
    """Get the appropriate ZMQ client implementation.
    
    Args:
        host: Server hostname
        port: Server port  
        timeout: Request timeout in milliseconds
        
    Returns:
        ZMQClient or ImprovedZMQClient instance
    """
    impl = get_zmq_implementation()
    
    if impl == 'improved':
        logger.info("Using improved ZMQ client (DEALER socket)")
        from kato.workers.zmq_client_improved import ImprovedZMQClient
        return ImprovedZMQClient(host, port, timeout)
    else:
        logger.info("Using legacy ZMQ client (REQ socket)")
        from kato.workers.zmq_client import ZMQClient
        return ZMQClient(host, port, timeout)


def migrate_to_improved():
    """Helper to migrate to the improved implementation."""
    os.environ['KATO_ZMQ_IMPLEMENTATION'] = 'improved'
    logger.info("Migrated to improved ZMQ implementation (DEALER/ROUTER)")
    

def rollback_to_legacy():
    """Helper to rollback to the legacy implementation."""
    os.environ['KATO_ZMQ_IMPLEMENTATION'] = 'legacy'
    logger.info("Rolled back to legacy ZMQ implementation (REQ/REP)")


class ZMQClientFactory:
    """Factory for creating ZMQ clients with automatic implementation selection."""
    
    @staticmethod
    def create_client(host='localhost', port=5555, timeout=5000, 
                     force_implementation: Optional[str] = None):
        """Create a ZMQ client with the appropriate implementation.
        
        Args:
            host: Server hostname
            port: Server port
            timeout: Request timeout
            force_implementation: Force 'legacy' or 'improved' implementation
            
        Returns:
            ZMQClient or ImprovedZMQClient instance
        """
        if force_implementation:
            if force_implementation == 'improved':
                from kato.workers.zmq_client_improved import ImprovedZMQClient
                return ImprovedZMQClient(host, port, timeout)
            elif force_implementation == 'legacy':
                from kato.workers.zmq_client import ZMQClient
                return ZMQClient(host, port, timeout)
            else:
                raise ValueError(f"Invalid implementation: {force_implementation}")
        else:
            return get_zmq_client(host, port, timeout)
    
    @staticmethod
    def create_pooled_client(host='localhost', port=5555, timeout=5000):
        """Create a connection-pooled client (always uses legacy for compatibility).
        
        Args:
            host: Server hostname
            port: Server port
            timeout: Request timeout
            
        Returns:
            ZMQConnectionPool instance
        """
        # Connection pool currently only works with legacy implementation
        from kato.workers.zmq_pool import ZMQConnectionPool
        return ZMQConnectionPool(host, port, timeout)


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