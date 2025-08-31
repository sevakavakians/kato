#!/usr/bin/env python3
"""
Improved ZeroMQ server using DEALER/ROUTER pattern for better connection handling.
This implementation supports long-lived connections and better error recovery.
"""

import json
import logging
import time
import traceback
import uuid
from os import environ
from threading import Thread

import msgpack
import zmq

logger = logging.getLogger('kato.zmq_server')
logger.setLevel(getattr(logging, environ.get('LOG_LEVEL', 'INFO')))


class ImprovedZMQServer:
    """
    ZeroMQ server using ROUTER socket for handling multiple persistent connections.
    
    ROUTER sockets can handle multiple clients and maintain connection state,
    making them ideal for production environments with long-lived connections.
    """
    
    def __init__(self, primitive, port=5555):
        """Initialize improved ZMQ server.
        
        Args:
            primitive: The KatoProcessor instance
            port: Port to bind the ZMQ socket (default: 5555)
        """
        self.primitive = primitive
        self.port = port
        self.context = zmq.Context()
        self.socket = None
        self.running = False
        
        # Track connected clients
        self.clients = {}
        self.client_last_seen = {}
        
        # Heartbeat configuration
        self.heartbeat_interval = 5000  # 5 seconds
        self.client_timeout = 30000  # 30 seconds
        
    def start(self):
        """Start the improved ZMQ server."""
        # Use ROUTER socket for better connection handling
        self.socket = self.context.socket(zmq.ROUTER)
        
        # Set socket options for better reliability
        self.socket.setsockopt(zmq.ROUTER_MANDATORY, 1)  # Fail if client not connected
        self.socket.setsockopt(zmq.SNDHWM, 1000)  # High water mark for send queue
        self.socket.setsockopt(zmq.RCVHWM, 1000)  # High water mark for receive queue
        self.socket.setsockopt(zmq.TCP_KEEPALIVE, 1)  # Enable TCP keepalive
        self.socket.setsockopt(zmq.TCP_KEEPALIVE_IDLE, 120)  # 2 minutes idle before keepalive
        self.socket.setsockopt(zmq.TCP_KEEPALIVE_CNT, 3)  # 3 keepalive probes
        self.socket.setsockopt(zmq.TCP_KEEPALIVE_INTVL, 30)  # 30 seconds between probes
        
        self.socket.bind(f"tcp://*:{self.port}")
        self.running = True
        
        logger.info(f"Improved ZMQ server (ROUTER) started on port {self.port}")
        
        # Start heartbeat thread
        heartbeat_thread = Thread(target=self._heartbeat_loop, daemon=True)
        heartbeat_thread.start()
        
        while self.running:
            try:
                # Use poller for non-blocking receive with timeout
                # This allows checking self.running flag periodically for clean shutdown
                poller = zmq.Poller()
                poller.register(self.socket, zmq.POLLIN)
                
                # Poll with timeout to allow shutdown checks
                socks = dict(poller.poll(1000))  # 1 second timeout
                
                if self.socket in socks:
                    # ROUTER receives [client_identity, message_data] from DEALER
                    # Unlike REQ/REP, DEALER doesn't send empty delimiter frame
                    frames = self.socket.recv_multipart()
                    
                    if len(frames) < 2:
                        logger.warning(f"Invalid message format: {frames}")
                        continue
                        
                    # Extract client identity for response routing
                    client_id = frames[0]
                    # DEALER message is directly in second frame (no empty delimiter)
                    message_frame = frames[1]
                    
                    # Track client for heartbeat/timeout management
                    self.client_last_seen[client_id] = time.time()
                    
                    try:
                        request = msgpack.unpackb(message_frame, raw=False)
                        
                        # Handle special messages
                        if request.get('type') == 'heartbeat':
                            response = {'status': 'ok', 'timestamp': time.time()}
                        else:
                            # Process normal request
                            response = self._handle_request(request)
                            
                    except Exception as e:
                        logger.error(f"Error processing request: {e}")
                        response = {
                            'status': 'error',
                            'message': str(e),
                            'traceback': traceback.format_exc()
                        }
                    
                    # Route response back to specific client
                    # ROUTER uses identity to route: [client_id, response_data]
                    try:
                        self.socket.send_multipart([
                            client_id,  # Routing identity
                            msgpack.packb(response)  # Serialized response
                        ])
                    except zmq.error.ZMQError as e:
                        logger.error(f"Failed to send response to client {client_id}: {e}")
                        # Remove disconnected client
                        if client_id in self.client_last_seen:
                            del self.client_last_seen[client_id]
                            
            except zmq.ZMQError as e:
                if e.errno == zmq.EAGAIN:
                    continue  # Timeout, continue loop
                else:
                    logger.error(f"ZMQ error: {e}")
                    if not self.running:
                        break
            except Exception as e:
                logger.error(f"Unexpected error in server loop: {e}")
                traceback.print_exc()
                
    def _heartbeat_loop(self):
        """Send heartbeat messages to track client liveness."""
        while self.running:
            try:
                time.sleep(self.heartbeat_interval / 1000)
                
                # Clean up inactive clients
                current_time = time.time()
                inactive_clients = []
                
                for client_id, last_seen in list(self.client_last_seen.items()):
                    if (current_time - last_seen) * 1000 > self.client_timeout:
                        inactive_clients.append(client_id)
                        
                for client_id in inactive_clients:
                    logger.info(f"Removing inactive client: {client_id}")
                    del self.client_last_seen[client_id]
                    
                # Log connection statistics
                if len(self.client_last_seen) > 0:
                    logger.debug(f"Active clients: {len(self.client_last_seen)}")
                    
            except Exception as e:
                logger.error(f"Error in heartbeat loop: {e}")
                
    def _handle_request(self, request):
        """Handle incoming requests - same as original implementation."""
        try:
            method = request.get('method')
            params = request.get('params', {})
            
            # Map method names to handler functions
            handlers = {
                'ping': self._handle_ping,
                'get_name': self._handle_get_name,
                'observe': self._handle_observe,
                'learn': self._handle_learn,
                'get_predictions': self._handle_get_predictions,
                'clear_stm': self._handle_clear_stm,
                'clear_short_term_memory': self._handle_clear_stm,  # Alias
                'clear_all': self._handle_clear_all,
                'clear_all_memory': self._handle_clear_all,  # Alias for compatibility
                'get_stm': self._handle_get_stm,
                'get_percept_data': self._handle_get_percept_data,
                'get_cognition_data': self._handle_get_cognition_data,
                'get_gene': self._handle_get_gene,
                'gene_change': self._handle_gene_change,
                'get_model': self._handle_get_model,
                'get_genome': self._handle_get_genome,
            }
            
            handler = handlers.get(method)
            if handler:
                return handler(params)
            else:
                return {
                    'status': 'error',
                    'message': f'Unknown method: {method}'
                }
                
        except Exception as e:
            logger.error(f"Error handling request: {e}")
            return {
                'status': 'error',
                'message': str(e),
                'traceback': traceback.format_exc()
            }
            
    # All the handler methods remain the same as in the original zmq_server.py
    def _handle_ping(self, params):
        """Handle ping request."""
        return {
            'status': 'okay',
            'message': 'pong',
            'timestamp': time.time()
        }
        
    def _handle_get_name(self, params):
        """Handle get_name request."""
        return {
            'status': 'okay',
            'message': self.primitive.name,
            'id': self.primitive.id,
            'interval': self.primitive.time
        }
        
    def _handle_observe(self, params):
        """Handle observe request."""
        try:
            # Process the observation data
            result = self.primitive.observe(params)
            
            # Handle both old and new return formats
            if isinstance(result, dict):
                unique_id = result.get('unique_id')
                auto_learned_model = result.get('auto_learned_model')
            else:
                # Backward compatibility
                unique_id = result
                auto_learned_model = None
            
            response = {
                'status': 'okay',
                'id': self.primitive.id,
                'interval': self.primitive.time,
                'time_stamp': time.time(),
                'message': 'observed',
                'unique_id': unique_id
            }
            
            if auto_learned_model:
                response['auto_learned_model'] = auto_learned_model
                
            return response
        except Exception as e:
            logger.error(f"Error in observe: {e}")
            return {
                'status': 'error',
                'message': str(e)
            }
            
    def _handle_learn(self, params):
        """Handle learn request."""
        try:
            model_name = self.primitive.learn()
            return {
                'status': 'okay',
                'model_name': model_name,
                'message': model_name
            }
        except Exception as e:
            logger.error(f"Error in learn: {e}")
            return {
                'status': 'error',
                'message': str(e)
            }
            
    def _handle_get_predictions(self, params):
        """Handle get predictions request."""
        try:
            unique_id = params.get('unique_id', {})
            predictions = self.primitive.get_predictions(unique_id)
            
            # Add MODEL| prefix to prediction names for consistency
            for pred in predictions:
                if isinstance(pred, dict):
                    name = pred.get('name', '')
                    if name and not name.startswith('MODEL|'):
                        pred['name'] = f'MODEL|{name}'
            
            return {
                'status': 'okay',
                'predictions': predictions
            }
        except Exception as e:
            logger.error(f"Error getting predictions: {e}")
            return {
                'status': 'error',
                'message': str(e)
            }
            
    def _handle_clear_stm(self, params):
        """Handle clear short-term memory request."""
        try:
            self.primitive.clear_stm()
            return {
                'status': 'okay',
                'message': 'stm-cleared'
            }
        except Exception as e:
            logger.error(f"Error clearing STM: {e}")
            return {
                'status': 'error',
                'message': str(e)
            }
            
    def _handle_clear_all(self, params):
        """Handle clear all memory request."""
        try:
            self.primitive.clear_all_memory()
            return {
                'status': 'okay',
                'message': 'all-cleared'
            }
        except Exception as e:
            logger.error(f"Error clearing all memory: {e}")
            return {
                'status': 'error',
                'message': str(e)
            }
            
    def _handle_get_stm(self, params):
        """Handle get short-term memory request."""
        try:
            stm = self.primitive.get_stm()
            return {
                'status': 'okay',
                'short_term_memory': stm
            }
        except Exception as e:
            logger.error(f"Error getting STM: {e}")
            return {
                'status': 'error',
                'message': str(e)
            }
            
    def _handle_get_percept_data(self, params):
        """Handle get percept data request."""
        try:
            data = self.primitive.get_percept_data()
            return {
                'status': 'okay',
                'percept_data': data
            }
        except Exception as e:
            logger.error(f"Error getting percept data: {e}")
            return {
                'status': 'error',
                'message': str(e)
            }
            
    def _handle_get_cognition_data(self, params):
        """Handle get cognition data request."""
        try:
            # cognition_data is a property, not a method
            data = self.primitive.cognition_data
            return {
                'status': 'okay',
                'cognition_data': data
            }
        except Exception as e:
            logger.error(f"Error getting cognition data: {e}")
            return {
                'status': 'error',
                'message': str(e)
            }
            
    def _handle_get_gene(self, params):
        """Handle get gene request."""
        try:
            gene_name = params.get('gene_name')
            if not gene_name:
                return {
                    'status': 'error',
                    'message': 'gene_name parameter required'
                }
                
            # Get gene value from the primitive's genome
            if hasattr(self.primitive, 'genome_manifest'):
                gene_value = self.primitive.genome_manifest.get(gene_name)
                return {
                    'status': 'okay',
                    'gene_name': gene_name,
                    'gene_value': gene_value
                }
            else:
                return {
                    'status': 'error',
                    'message': 'Genome not available'
                }
        except Exception as e:
            logger.error(f"Error getting gene: {e}")
            return {
                'status': 'error',
                'message': str(e)
            }
            
    def _handle_get_model(self, params):
        """Handle get model request."""
        try:
            model_id = params.get('model_id')
            if not model_id:
                return {
                    'status': 'error',
                    'message': 'model_id parameter required'
                }
                
            # Get model from knowledge base
            # Strip MODEL| prefix if present
            if model_id.startswith('MODEL|'):
                model_name = model_id[6:]
            else:
                model_name = model_id
                
            model = self.primitive.modeler.models_kb.find_one({"name": model_name})
            if model:
                return {
                    'status': 'okay',
                    'model': {
                        'name': model.get('name'),
                        'sequence': model.get('sequence', []),
                        'frequency': model.get('frequency', 0),
                        'emotives': model.get('emotives', {})
                    }
                }
            else:
                return {
                    'status': 'error',
                    'message': f'Model {model_id} not found'
                }
        except Exception as e:
            logger.error(f"Error getting model: {e}")
            return {
                'status': 'error',
                'message': str(e)
            }
            
    def _handle_gene_change(self, params):
        """Handle gene change request."""
        try:
            gene_name = params.get('gene_name')
            gene_value = params.get('gene_value')
            
            logger.info(f"Gene change request: {gene_name} = {gene_value}")
            
            if not gene_name or gene_value is None:
                return {
                    'status': 'error',
                    'message': 'gene_name and gene_value parameters required'
                }
                
            # Update the gene value in the primitive
            if hasattr(self.primitive, gene_name):
                setattr(self.primitive, gene_name, gene_value)
                
                # Also update in genome_manifest if exists
                if hasattr(self.primitive, 'genome_manifest'):
                    self.primitive.genome_manifest[gene_name] = gene_value
                    
                return {
                    'status': 'okay',
                    'message': f'Gene {gene_name} updated to {gene_value}'
                }
            else:
                # Try updating in modeler
                if hasattr(self.primitive.modeler, gene_name):
                    old_value = getattr(self.primitive.modeler, gene_name, None)
                    setattr(self.primitive.modeler, gene_name, gene_value)
                    logger.info(f"Updated modeler.{gene_name}: {old_value} -> {gene_value}")
                    
                    # Special handling for recall_threshold - also update in models_searcher
                    if gene_name == 'recall_threshold' and hasattr(self.primitive.modeler, 'models_searcher'):
                        self.primitive.modeler.models_searcher.recall_threshold = gene_value
                        logger.info(f"Also updated models_searcher.recall_threshold to {gene_value}")
                    
                    # Also update genome_manifest for consistency
                    if hasattr(self.primitive, 'genome_manifest'):
                        self.primitive.genome_manifest[gene_name] = gene_value
                        logger.info(f"Updated genome_manifest[{gene_name}] = {gene_value}")
                        
                    return {
                        'status': 'okay',
                        'message': f'Gene {gene_name} updated to {gene_value}'
                    }
                else:
                    return {
                        'status': 'error',
                        'message': f'Unknown gene: {gene_name}'
                    }
        except Exception as e:
            logger.error(f"Error changing gene: {e}")
            return {
                'status': 'error',
                'message': str(e)
            }
            
    def _handle_get_genome(self, params):
        """Handle get genome request."""
        try:
            if hasattr(self.primitive, 'genome_manifest'):
                return self.primitive.genome_manifest
            else:
                # Build genome from primitive attributes
                genome = {
                    'id': self.primitive.id,
                    'name': self.primitive.name,
                    'classifier': getattr(self.primitive, 'classifier_type', 'CVC'),
                    'max_sequence_length': getattr(self.primitive.modeler, 'max_sequence_length', 0),
                    'persistence': getattr(self.primitive.modeler, 'persistence', 5),
                    'smoothness': getattr(self.primitive.modeler, 'smoothness', 3),
                    'recall_threshold': getattr(self.primitive.modeler, 'recall_threshold', 0.1),
                }
                return genome
        except Exception as e:
            logger.error(f"Error getting genome: {e}")
            return {
                'status': 'error',
                'message': str(e)
            }
            
    def stop(self):
        """Stop the ZMQ server."""
        self.running = False
        if self.socket:
            self.socket.close()
        if self.context:
            self.context.term()
        logger.info("Improved ZMQ server stopped")