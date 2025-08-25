#!/usr/bin/env python3
"""ZeroMQ server implementation for KATO processor communication."""

import json
import logging
import time
import traceback
from os import environ
from threading import Thread

import msgpack
import zmq

logger = logging.getLogger('kato.zmq_server')
logger.setLevel(getattr(logging, environ.get('LOG_LEVEL', 'INFO')))


class ZMQServer:
    """ZeroMQ server that handles KATO processor requests."""
    
    def __init__(self, primitive, port=5555):
        """Initialize ZMQ server with a KATO processor primitive.
        
        Args:
            primitive: The KatoProcessor instance
            port: Port to bind the ZMQ socket (default: 5555)
        """
        self.primitive = primitive
        self.port = port
        self.context = zmq.Context()
        self.socket = None
        self.running = False
        
    def start(self):
        """Start the ZMQ server."""
        self.socket = self.context.socket(zmq.REP)
        self.socket.bind(f"tcp://*:{self.port}")
        self.running = True
        
        logger.info(f"ZMQ server started on port {self.port}")
        
        while self.running:
            try:
                # Wait for a request with timeout
                if self.socket.poll(1000):  # 1 second timeout
                    message = self.socket.recv()
                    request = msgpack.unpackb(message, raw=False)
                    
                    # Process the request
                    response = self._handle_request(request)
                    
                    # Send response
                    self.socket.send(msgpack.packb(response))
            except zmq.ZMQError as e:
                if e.errno == zmq.EAGAIN:
                    continue  # Timeout, continue loop
                else:
                    logger.error(f"ZMQ error: {e}")
                    break
            except Exception as e:
                logger.error(f"Error handling request: {e}")
                logger.error(traceback.format_exc())
                # Send error response
                error_response = {
                    'status': 'error',
                    'message': str(e)
                }
                try:
                    self.socket.send(msgpack.packb(error_response))
                except:
                    pass  # Can't send error, move on
                    
    def stop(self):
        """Stop the ZMQ server."""
        logger.info("Stopping ZMQ server...")
        self.running = False
        if self.socket:
            self.socket.close()
        self.context.term()
        logger.info("ZMQ server stopped")
        
    def _handle_request(self, request):
        """Handle a request and return a response.
        
        Args:
            request: Dictionary containing the request data
            
        Returns:
            Dictionary containing the response data
        """
        method = request.get('method')
        params = request.get('params', {})
        
        logger.debug(f"Handling request: method={method}")
        
        if method == 'get_name':
            return self._handle_get_name()
        elif method == 'observe':
            return self._handle_observe(params)
        elif method == 'learn':
            return self._handle_learn(params)
        elif method == 'clear_all_memory':
            return self._handle_clear_all_memory()
        elif method == 'clear_working_memory':
            return self._handle_clear_working_memory()
        elif method == 'get_wm':
            return self._handle_get_working_memory()
        elif method == 'get_predictions':
            return self._handle_get_predictions()
        elif method == 'get_percept_data':
            return self._handle_get_percept_data()
        elif method == 'get_cognition_data':
            return self._handle_get_cognition_data()
        elif method == 'get_gene':
            return self._handle_get_gene(params)
        elif method == 'get_model':
            return self._handle_get_model(params)
        elif method == 'gene_change':
            return self._handle_gene_change(params)
        elif method == 'get_genome':
            return self._handle_get_genome(params)
        else:
            return {
                'status': 'error',
                'message': f'Unknown method: {method}'
            }
            
    def _handle_get_name(self):
        """Handle get_name request."""
        return {
            'status': 'okay',
            'id': self.primitive.id,
            'interval': self.primitive.time,
            'time_stamp': time.time(),
            'message': self.primitive.name
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
            logger.error(traceback.format_exc())
            return {
                'status': 'error',
                'message': str(e)
            }
            
    def _handle_learn(self, params):
        """Handle learn request."""
        try:
            # Get parameters with defaults (for future use)
            learning_flag = params.get('learning_flag', True)
            manual_flag = params.get('manual_flag', False)
            auto_act_flag = params.get('auto_act_flag', False)
            
            # Call the learn method (KatoProcessor.learn() takes no arguments)
            result = self.primitive.learn()
            
            return {
                'status': 'okay',
                'id': self.primitive.id,
                'interval': self.primitive.time,
                'time_stamp': time.time(),
                'message': result if result else 'learning-called'
            }
        except Exception as e:
            logger.error(f"Error in learn: {e}")
            return {
                'status': 'error',
                'message': str(e)
            }
            
    def _handle_clear_all_memory(self):
        """Handle clear all memory request."""
        try:
            self.primitive.clear_all_memory()
            return {
                'status': 'okay',
                'id': self.primitive.id,
                'interval': self.primitive.time,
                'time_stamp': time.time(),
                'message': 'all-cleared'
            }
        except Exception as e:
            logger.error(f"Error clearing all memory: {e}")
            return {
                'status': 'error',
                'message': str(e)
            }
            
    def _handle_clear_working_memory(self):
        """Handle clear working memory request."""
        try:
            self.primitive.clear_wm()
            return {
                'status': 'okay',
                'id': self.primitive.id,
                'interval': self.primitive.time,
                'time_stamp': time.time(),
                'message': 'wm-cleared'
            }
        except Exception as e:
            logger.error(f"Error clearing working memory: {e}")
            return {
                'status': 'error',
                'message': str(e)
            }
            
    def _handle_get_working_memory(self):
        """Handle get working memory request."""
        try:
            # Get working memory from modeler's WM
            wm = list(self.primitive.modeler.WM)
            return {
                'status': 'okay',
                'data': wm
            }
        except Exception as e:
            logger.error(f"Error getting working memory: {e}")
            return {
                'status': 'error',
                'message': str(e)
            }
            
    def _handle_get_predictions(self):
        """Handle get predictions request."""
        try:
            predictions = self.primitive.get_predictions()
            # Convert predictions to serializable format
            # Prediction is a dict subclass, so we can directly access keys
            pred_list = []
            for pred in predictions:
                # Extract the fields that exist in Prediction dict
                pred_dict = {
                    'name': pred.get('name'),
                    'confidence': pred.get('confidence'),
                    'similarity': pred.get('similarity'),
                    'past': pred.get('past', []),
                    'present': pred.get('present', []),
                    'future': pred.get('future', []),
                    'missing': pred.get('missing', []),
                    'extras': pred.get('extras', []),
                    'emotives': pred.get('emotives', {}),
                    'frequency': pred.get('frequency'),
                    'evidence': pred.get('evidence'),
                    'fragmentation': pred.get('fragmentation'),
                    'snr': pred.get('snr'),
                    'entropy': pred.get('entropy'),
                    'hamiltonian': pred.get('hamiltonian'),
                    'grand_hamiltonian': pred.get('grand_hamiltonian'),
                    'confluence': pred.get('confluence')
                }
                pred_list.append(pred_dict)
            
            return {
                'status': 'okay',
                'data': pred_list
            }
        except Exception as e:
            logger.error(f"Error getting predictions: {e}")
            return {
                'status': 'error',
                'message': str(e)
            }
            
    def _handle_get_percept_data(self):
        """Handle get percept data request."""
        try:
            percept_data = self.primitive.get_percept_data()
            return {
                'status': 'okay',
                'data': percept_data
            }
        except Exception as e:
            logger.error(f"Error getting percept data: {e}")
            return {
                'status': 'error',
                'message': str(e)
            }
            
    def _handle_get_cognition_data(self):
        """Handle get cognition data request."""
        try:
            cognition_data = self.primitive.cognition_data
            return {
                'status': 'okay',
                'data': cognition_data
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
                
            gene_value = self.primitive.genome_manifest.get(gene_name)
            return {
                'status': 'okay',
                'gene_name': gene_name,
                'gene_value': gene_value
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
            
            if not gene_name or gene_value is None:
                return {
                    'status': 'error',
                    'message': 'gene_name and gene_value parameters required'
                }
                
            # Update the gene
            self.primitive.genome_manifest[gene_name] = gene_value
            
            # Apply changes if it's a critical gene
            if gene_name == 'max_predictions':
                self.primitive.modeler.max_predictions = gene_value
            elif gene_name == 'recall_threshold':
                self.primitive.modeler.recall_threshold = gene_value
            elif gene_name == 'classifier':
                # Classifier changes require reinitialization
                pass  # TODO: Handle classifier changes
                
            return {
                'status': 'okay',
                'id': self.primitive.id,
                'message': f'Gene {gene_name} updated to {gene_value}'
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
            # Return the genome manifest
            return {
                'status': 'okay',
                'genome': self.primitive.genome_manifest
            }
        except Exception as e:
            logger.error(f"Error getting genome: {e}")
            return {
                'status': 'error',
                'message': str(e)
            }