#!/usr/bin/env python3
"""
Improved ZeroMQ client using DEALER socket for better connection handling.
This implementation supports long-lived connections with the ROUTER-based server.
"""

import logging
import time
import uuid
from typing import Optional, Any, Dict
import msgpack
import zmq

logger = logging.getLogger('kato.zmq_client_improved')


class ImprovedZMQClient:
    """
    Improved ZeroMQ client using DEALER socket for persistent connections.
    
    DEALER sockets can maintain persistent connections and handle async messaging,
    making them ideal for long-lived client connections to ROUTER-based servers.
    """
    
    def __init__(self, host='localhost', port=5555, timeout=5000, 
                 heartbeat_interval=10000, max_retries=3):
        """Initialize improved ZMQ client.
        
        Args:
            host: Server hostname
            port: Server port
            timeout: Request timeout in milliseconds
            heartbeat_interval: Milliseconds between heartbeats
            max_retries: Maximum number of retries for failed requests
        """
        self.host = host
        self.port = port
        self.timeout = timeout
        self.heartbeat_interval = heartbeat_interval
        self.max_retries = max_retries
        
        # ZMQ setup
        self.context = zmq.Context()
        self.socket = None
        self.poller = zmq.Poller()
        
        # Connection state
        self._connected = False
        self._identity = str(uuid.uuid4()).encode('utf-8')
        self._last_heartbeat = 0
        self._pending_requests = {}
        self._request_id = 0
        
        # Statistics
        self._request_count = 0
        self._successful_requests = 0
        self._failed_requests = 0
        self._reconnections = 0
        
    def connect(self):
        """Connect to the ZMQ server using DEALER socket."""
        if self._connected:
            logger.debug("Already connected")
            return
            
        # Close existing socket if any
        if self.socket:
            self.disconnect()
            
        # Create DEALER socket
        self.socket = self.context.socket(zmq.DEALER)
        
        # Set socket identity for tracking on server side
        self.socket.setsockopt(zmq.IDENTITY, self._identity)
        
        # Socket options for reliability
        self.socket.setsockopt(zmq.LINGER, 0)
        self.socket.setsockopt(zmq.SNDHWM, 1000)
        self.socket.setsockopt(zmq.RCVHWM, 1000)
        
        # TCP keepalive for long-lived connections
        self.socket.setsockopt(zmq.TCP_KEEPALIVE, 1)
        self.socket.setsockopt(zmq.TCP_KEEPALIVE_IDLE, 120)
        self.socket.setsockopt(zmq.TCP_KEEPALIVE_CNT, 3)
        self.socket.setsockopt(zmq.TCP_KEEPALIVE_INTVL, 30)
        
        # Connect to server
        self.socket.connect(f"tcp://{self.host}:{self.port}")
        
        # Register with poller
        self.poller.register(self.socket, zmq.POLLIN)
        
        self._connected = True
        self._last_heartbeat = time.time() * 1000
        
        logger.info(f"Connected to server at {self.host}:{self.port} with identity {self._identity.decode()}")
        
    def disconnect(self):
        """Disconnect from the ZMQ server."""
        if self.socket:
            try:
                self.poller.unregister(self.socket)
            except:
                pass
                
            self.socket.close()
            self.socket = None
            
        self._connected = False
        self._pending_requests.clear()
        
        logger.info(f"Disconnected from server (identity: {self._identity.decode()})")
        
    def is_connected(self) -> bool:
        """Check if client is connected.
        
        Returns:
            True if connected, False otherwise
        """
        return self._connected and self.socket is not None
        
    def _send_heartbeat(self):
        """Send heartbeat message to keep connection alive."""
        if not self._connected:
            return
            
        current_time = time.time() * 1000
        if current_time - self._last_heartbeat >= self.heartbeat_interval:
            try:
                heartbeat_msg = {
                    'type': 'heartbeat',
                    'timestamp': time.time()
                }
                # DEALER sends just the message
                self.socket.send(msgpack.packb(heartbeat_msg))
                self._last_heartbeat = current_time
                logger.debug("Sent heartbeat")
            except zmq.ZMQError as e:
                logger.error(f"Failed to send heartbeat: {e}")
                self._handle_connection_error()
                
    def _handle_connection_error(self):
        """Handle connection errors by attempting reconnection."""
        logger.warning("Connection error detected, attempting reconnection...")
        self._reconnections += 1
        
        # Disconnect and reconnect
        self.disconnect()
        time.sleep(1)  # Brief pause before reconnecting
        
        try:
            self.connect()
            logger.info("Reconnection successful")
        except Exception as e:
            logger.error(f"Reconnection failed: {e}")
            raise
            
    def call(self, method: str, params: Optional[Dict] = None, 
             timeout: Optional[int] = None) -> Dict[str, Any]:
        """Call a method on the KATO processor.
        
        Args:
            method: Method name to call
            params: Optional parameters dictionary
            timeout: Optional timeout override in milliseconds
            
        Returns:
            Response dictionary from the server
            
        Raises:
            TimeoutError: If request times out
            ConnectionError: If not connected or connection fails
            Exception: On server errors
        """
        if not self._connected:
            self.connect()
            
        # Generate request ID
        self._request_id += 1
        request_id = self._request_id
        
        request = {
            'id': request_id,
            'method': method,
            'params': params or {}
        }
        
        # Use provided timeout or default
        req_timeout = timeout or self.timeout
        
        # Send request with retry logic
        for attempt in range(self.max_retries):
            try:
                # Send heartbeat if needed
                self._send_heartbeat()
                
                # Send request
                # DEALER sends just the message (no empty frame needed)
                self.socket.send(msgpack.packb(request))
                
                self._request_count += 1
                logger.debug(f"Sent request {request_id}: {method}")
                
                # Wait for response
                start_time = time.time() * 1000
                
                while True:
                    # Calculate remaining timeout
                    elapsed = (time.time() * 1000) - start_time
                    remaining = req_timeout - elapsed
                    
                    if remaining <= 0:
                        raise TimeoutError(f"Request {request_id} timed out after {req_timeout}ms")
                        
                    # Poll for response
                    socks = dict(self.poller.poll(min(remaining, 1000)))
                    
                    if self.socket in socks:
                        # DEALER receives just the message from ROUTER
                        message_frame = self.socket.recv()
                        
                        try:
                            response = msgpack.unpackb(message_frame, raw=False)
                            
                            # Check if this is our response (not a heartbeat)
                            if response.get('type') == 'heartbeat':
                                logger.debug("Received heartbeat response")
                                continue
                                
                            # Success!
                            self._successful_requests += 1
                            
                            # Check for errors
                            if response.get('status') == 'error':
                                raise Exception(f"Server error: {response.get('message')}")
                                
                            return response
                            
                        except msgpack.exceptions.UnpackException as e:
                            logger.error(f"Failed to unpack response: {e}")
                            continue
                            
                    # Send periodic heartbeats while waiting
                    self._send_heartbeat()
                    
            except TimeoutError:
                logger.warning(f"Attempt {attempt + 1}/{self.max_retries} timed out for {method}")
                self._failed_requests += 1
                
                if attempt < self.max_retries - 1:
                    # Try to recover the connection
                    self._handle_connection_error()
                else:
                    raise
                    
            except zmq.ZMQError as e:
                logger.error(f"ZMQ error on attempt {attempt + 1}: {e}")
                self._failed_requests += 1
                
                if attempt < self.max_retries - 1:
                    self._handle_connection_error()
                else:
                    raise ConnectionError(f"Failed after {self.max_retries} attempts: {e}")
                    
            except Exception as e:
                logger.error(f"Unexpected error: {e}")
                self._failed_requests += 1
                raise
                
    def close(self):
        """Close the client and clean up resources."""
        self.disconnect()
        
        if self.context:
            self.context.term()
            self.context = None
            
        logger.info(f"Client closed. Stats: {self.get_stats()}")
        
    def get_stats(self) -> Dict[str, Any]:
        """Get client statistics.
        
        Returns:
            Dictionary with client statistics
        """
        return {
            'identity': self._identity.decode(),
            'connected': self._connected,
            'total_requests': self._request_count,
            'successful_requests': self._successful_requests,
            'failed_requests': self._failed_requests,
            'success_rate': self._successful_requests / max(1, self._request_count),
            'reconnections': self._reconnections
        }
        
    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
        
    # Convenience methods matching the original client interface
    
    def ping(self) -> bool:
        """Ping the server to check connection.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            response = self.call('ping', timeout=1000)
            return response.get('status') == 'okay'
        except:
            return False
            
    def get_name(self) -> Dict[str, Any]:
        """Get the processor name and status."""
        return self.call('get_name')
        
    def observe(self, observation_data: Dict) -> Dict[str, Any]:
        """Send an observation to the processor."""
        return self.call('observe', observation_data)
        
    def learn(self, learning_flag=True, manual_flag=False, 
              auto_act_flag=False) -> Dict[str, Any]:
        """Trigger learning in the processor."""
        params = {
            'learning_flag': learning_flag,
            'manual_flag': manual_flag,
            'auto_act_flag': auto_act_flag
        }
        return self.call('learn', params)
        
    def clear_all_memory(self) -> Dict[str, Any]:
        """Clear all processor memory."""
        return self.call('clear_all')
        
    def clear_short_term_memory(self) -> Dict[str, Any]:
        """Clear short-term memory only."""
        return self.call('clear_stm')
        
    def get_short_term_memory(self) -> list:
        """Get the current short-term memory contents."""
        response = self.call('get_stm')
        return response.get('short_term_memory', [])
        
    def get_predictions(self, unique_id: Optional[Dict] = None) -> list:
        """Get current predictions from the processor."""
        params = {'unique_id': unique_id} if unique_id else {}
        response = self.call('get_predictions', params)
        return response.get('predictions', [])
        
    def get_percept_data(self) -> Dict:
        """Get percept data from the processor."""
        response = self.call('get_percept_data')
        return response.get('percept_data', {})
        
    def get_cognition_data(self) -> Dict:
        """Get cognition data from the processor."""
        response = self.call('get_cognition_data')
        return response.get('cognition_data', {})
        
    def get_gene(self, gene_name: str) -> Any:
        """Get a specific gene value."""
        response = self.call('get_gene', {'gene_name': gene_name})
        return response.get('gene_value')
        
    def get_pattern(self, pattern_id: str) -> Dict:
        """Get a specific pattern by ID."""
        response = self.call('get_pattern', {'pattern_id': pattern_id})
        return response
        
    def change_gene(self, gene_name: str, gene_value: Any) -> Dict[str, Any]:
        """Change a gene value."""
        params = {
            'gene_name': gene_name,
            'gene_value': gene_value
        }
        return self.call('gene_change', params)
        
    def get_genome(self) -> Dict:
        """Get the genome information."""
        response = self.call('get_genome')
        return response


if __name__ == "__main__":
    # Test the improved client
    logging.basicConfig(level=logging.DEBUG)
    
    with ImprovedZMQClient() as client:
        # Test basic operations
        print("Testing improved ZMQ client...")
        
        # Ping test
        if client.ping():
            print("✓ Ping successful")
        else:
            print("✗ Ping failed")
            
        # Get name test
        try:
            name_response = client.get_name()
            print(f"✓ Get name: {name_response.get('message')}")
        except Exception as e:
            print(f"✗ Get name failed: {e}")
            
        # Show statistics
        print(f"\nClient statistics: {client.get_stats()}")