#!/usr/bin/env python3
"""ZeroMQ client utilities for communicating with KATO ZMQ server."""

import logging
import msgpack
import zmq

logger = logging.getLogger('kato.zmq_client')


class ZMQClient:
    """ZeroMQ client for communicating with KATO processor."""
    
    def __init__(self, host='localhost', port=5555, timeout=5000):
        """Initialize ZMQ client.
        
        Args:
            host: Server hostname (default: localhost)
            port: Server port (default: 5555)
            timeout: Request timeout in milliseconds (default: 5000)
        """
        self.host = host
        self.port = port
        self.timeout = timeout
        self.context = zmq.Context()
        self.socket = None
        self._connected = False
        self._request_count = 0
        
    def _connect(self):
        """Connect to the ZMQ server."""
        # Close existing socket if any
        if self.socket:
            self.socket.close()
            self._connected = False
            
        self.socket = self.context.socket(zmq.REQ)
        self.socket.setsockopt(zmq.RCVTIMEO, self.timeout)
        self.socket.setsockopt(zmq.SNDTIMEO, self.timeout)
        self.socket.setsockopt(zmq.LINGER, 0)
        self.socket.connect(f"tcp://{self.host}:{self.port}")
        self._connected = True
        logger.debug(f"Connected to ZMQ server at {self.host}:{self.port}")
        
    def close(self):
        """Close the ZMQ connection."""
        if self.socket:
            self.socket.close()
            self.socket = None
            self._connected = False
        if self.context:
            self.context.term()
            self.context = None
        
    def __enter__(self):
        """Context manager entry."""
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
    
    def is_connected(self):
        """Check if the client is connected.
        
        Returns:
            True if connected, False otherwise
        """
        return self._connected and self.socket is not None
    
    def reset_connection(self):
        """Reset the connection by closing and reconnecting."""
        logger.info("Resetting ZMQ connection")
        if self.socket:
            try:
                self.socket.close()
            except Exception as e:
                logger.error(f"Error closing socket during reset: {e}")
            finally:
                self.socket = None
                self._connected = False
        
        # Reconnect
        self._connect()
    
    def ping(self):
        """Perform a lightweight ping to check connection health.
        
        Returns:
            True if ping successful, False otherwise
        """
        try:
            # Use get_name as a lightweight ping operation
            response = self.call('get_name')
            return response.get('status') == 'okay'
        except Exception as e:
            logger.debug(f"Ping failed: {e}")
            return False
        
    def call(self, method, params=None):
        """Call a method on the KATO processor.
        
        Args:
            method: Method name to call
            params: Optional parameters dictionary
            
        Returns:
            Response dictionary from the server
            
        Raises:
            zmq.ZMQError: On communication errors
            Exception: On server errors
        """
        request = {
            'method': method,
            'params': params or {}
        }
        
        # Create a fresh socket for each request to avoid state issues
        if not self.socket:
            self._connect()
        
        try:
            # Send request
            self.socket.send(msgpack.packb(request))
            
            # Receive response
            message = self.socket.recv()
            response = msgpack.unpackb(message, raw=False)
            
            # Track successful requests
            self._request_count += 1
            
            # Check for errors
            if response.get('status') == 'error':
                raise Exception(f"Server error: {response.get('message')}")
                
            return response
            
        except zmq.ZMQError as e:
            logger.error(f"ZMQ communication error: {e}")
            # Close the socket so a fresh one is created next time
            if self.socket:
                self.socket.close()
                self.socket = None
                self._connected = False
            raise
            
    def get_name(self):
        """Get the processor name and status."""
        return self.call('get_name')
        
    def observe(self, observation_data):
        """Send an observation to the processor.
        
        Args:
            observation_data: Dictionary containing observation data
                - strings: List of string symbols
                - vectors: List of vector arrays
                - emotives: Dictionary of emotive values
                
        Returns:
            Response dictionary from the server
        """
        return self.call('observe', observation_data)
        
    def learn(self, learning_flag=True, manual_flag=False, auto_act_flag=False):
        """Trigger learning in the processor.
        
        Args:
            learning_flag: Enable learning (default: True)
            manual_flag: Manual learning mode (default: False)
            auto_act_flag: Auto action flag (default: False)
            
        Returns:
            Response dictionary from the server
        """
        params = {
            'learning_flag': learning_flag,
            'manual_flag': manual_flag,
            'auto_act_flag': auto_act_flag
        }
        return self.call('learn', params)
        
    def clear_all_memory(self):
        """Clear all processor memory."""
        return self.call('clear_all_memory')
        
    def clear_short_term_memory(self):
        """Clear short-term memory only."""
        return self.call('clear_short_term_memory')
        
    def get_short_term_memory(self):
        """Get the current short-term memory contents."""
        response = self.call('get_stm')
        return response.get('data', [])
        
    def get_predictions(self):
        """Get current predictions from the processor."""
        response = self.call('get_predictions')
        return response.get('data', [])
        
    def get_percept_data(self):
        """Get percept data from the processor."""
        response = self.call('get_percept_data')
        return response.get('data', {})
        
    def get_cognition_data(self):
        """Get cognition data from the processor."""
        response = self.call('get_cognition_data')
        return response.get('data', {})
        
    def get_gene(self, gene_name):
        """Get a specific gene value.
        
        Args:
            gene_name: Name of the gene to retrieve
            
        Returns:
            Gene value
        """
        response = self.call('get_gene', {'gene_name': gene_name})
        return response.get('gene_value')
        
    def get_model(self, model_id):
        """Get a specific model by ID.
        
        Args:
            model_id: Model ID to retrieve
            
        Returns:
            Full response with status and model information
        """
        response = self.call('get_model', {'model_id': model_id})
        return response
        
    def change_gene(self, gene_name, gene_value):
        """Change a gene value.
        
        Args:
            gene_name: Name of the gene to change
            gene_value: New value for the gene
            
        Returns:
            Response dictionary from the server
        """
        params = {
            'gene_name': gene_name,
            'gene_value': gene_value
        }
        return self.call('gene_change', params)
        
    def get_genome(self):
        """Get the genome information.
        
        Returns:
            Genome dictionary
        """
        response = self.call('get_genome')
        return response.get('genome', {})