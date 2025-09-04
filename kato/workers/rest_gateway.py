#!/usr/bin/env python3
"""
REST-to-ZMQ Gateway for KATO
Provides HTTP REST endpoints that translate to ZMQ calls for backward compatibility with tests.
"""

import json
import logging
import time
from threading import Thread
from urllib.parse import parse_qs

from kato.workers.zmq_pool_improved import get_improved_pool as get_global_pool, set_improved_pool as set_global_pool, cleanup_improved_pool as cleanup_global_pool, ImprovedConnectionPool as ZMQConnectionPool
from kato.workers.zmq_switcher import get_zmq_client, get_zmq_implementation

# Simple HTTP server implementation
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

logger = logging.getLogger('kato.rest_gateway')

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Handle requests in a separate thread."""

class RestGatewayHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            if self.path == '/kato-api/ping':
                self.handle_ping()
            elif self.path == '/connect':
                self.handle_connect()
            elif self.path.endswith('/ping'):
                self.handle_processor_ping()
            elif self.path.endswith('/status'):
                self.handle_status()
            elif self.path.endswith('/short-term-memory'):
                self.handle_get_short_term_memory()
            elif self.path.endswith('/stm'): # Alias
                self.handle_get_short_term_memory()
            elif self.path.endswith('/predictions'):
                self.handle_get_predictions()
            elif self.path.endswith('/percept-data'):
                self.handle_get_percept_data()
            elif self.path.endswith('/cognition-data'):
                self.handle_get_cognition_data()
            elif '/gene/' in self.path:
                self.handle_get_gene()
            elif '/pattern/' in self.path:
                self.handle_get_pattern()
            else:
                self.send_error(404, "Not Found")
        except Exception as e:
            logger.error(f"GET request error: {e}")
            self.send_error(500, str(e))

    def do_POST(self):
        try:
            if self.path.endswith('/observe'):
                self.handle_observe()
            elif self.path.endswith('/clear-all-memory'):
                self.handle_clear_all_memory()
            elif self.path.endswith('/clear-short-term-memory'):
                self.handle_clear_short_term_memory()
            elif self.path.endswith('/clear-stm'): # Alias
                self.handle_clear_short_term_memory()
            elif self.path.endswith('/learn'):
                self.handle_learn()
            elif self.path.endswith('/predictions'):
                self.handle_get_predictions()  # Support POST /predictions
            elif self.path.endswith('/short-term-memory/clear'):
                self.handle_clear_short_term_memory()  # Support POST /short-term-memory/clear
            elif self.path.endswith('/stm/clear'): # Alias
                self.handle_clear_short_term_memory()  # Support POST /short-term-memory/clear
            elif self.path.endswith('/genes/change'):
                self.handle_gene_change()
            else:
                self.send_error(404, "Not Found")
        except Exception as e:
            logger.error(f"POST request error: {e}")
            self.send_error(500, str(e))

    def handle_ping(self):
        """Health check endpoint"""
        response = {"status": "okay"}
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(response).encode())

    def handle_processor_ping(self):
        """Processor-specific ping endpoint"""
        try:
            # Extract processor ID from path: /{processor_id}/ping
            processor_id = self.path.split('/')[1]
            
            pool = get_global_pool()
            response = pool.execute('get_name')
            
            result = {
                "id": processor_id,
                "interval": response.get('interval', 0),
                "time_stamp": response.get('time_stamp', time.time()),
                "status": "okay",
                "message": response.get('message', 'okay'),
                "processor": response.get('message', 'unknown')
            }
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())
                
        except Exception as e:
            logger.error(f"Processor ping error: {e}")
            self.send_error(500, str(e))

    ## TODO: Deprecated? Get rid of this function?
    def handle_connect(self):
        """Handle connect endpoint for compatibility"""
        # Get genome info if available
        pool = get_global_pool()
        try:
            genome_info = pool.execute('get_genome')
            # Ensure genome has expected structure
            if genome_info and 'elements' not in genome_info:
                # Build elements structure from genome info
                genome_info['elements'] = {
                    'nodes': [{
                        'data': {
                            'id': genome_info.get('id', 'unknown'),
                            'name': genome_info.get('name', 'unknown'),
                        }
                    }]
                }
        except:
            genome_info = {
                'elements': {
                    'nodes': [{
                        'data': {
                            'id': 'unknown',
                            'name': 'unknown',
                        }
                    }]
                }
            }
        
        response = {
            "status": "okay",
            "message": "connected",
            "genome": genome_info  # Add genome for test compatibility
        }
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(response).encode())

    def handle_status(self):
        """Handle status endpoint"""
        try:
            pool = get_global_pool()
            response = pool.execute('get_name')
            
            result = {
                "status": "okay",
                "processor": response.get('message', 'unknown'),
                "id": response.get('id'),
                "time_stamp": response.get('time_stamp', time.time()),
                "interval": response.get('interval', 0),
                "message": response  # Add full response as message for compatibility
            }
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())
                
        except Exception as e:
            logger.error(f"Status error: {e}")
            self.send_error(500, str(e))

    def handle_get_short_term_memory(self):
        """Handle get short-term memory request"""
        try:
            pool = get_global_pool()
            stm_response = pool.execute('get_stm')
            
            # Extract the actual STM data from the response
            stm = stm_response.get('short_term_memory', [])
            
            # Get processor info for timing fields
            response = pool.execute('get_name')
            
            # Add timing fields for test compatibility
            result = {
                "message": stm,
                "time_stamp": response.get('time_stamp', time.time()),
                "interval": response.get('interval', 0)
            }
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())
                
        except Exception as e:
            logger.error(f"Get short-term memory error: {e}")
            self.send_error(500, str(e))

    def handle_get_predictions(self):
        """Handle get predictions request"""
        try:
            pool = get_global_pool()
            response = pool.execute('get_predictions')
            
            # Extract predictions from response
            predictions = response.get('predictions', [])
            
            # Wrap in message for test compatibility
            result = {"message": predictions}
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())
                
        except Exception as e:
            logger.error(f"Get predictions error: {e}")
            self.send_error(500, str(e))

    def handle_get_percept_data(self):
        """Handle get percept data request"""
        try:
            pool = get_global_pool()
            response = pool.execute('get_percept_data')
            
            # Extract percept_data from response
            percept_data = response.get('percept_data', {})
            
            # Wrap in message for test compatibility
            result = {"message": percept_data}
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())
                
        except Exception as e:
            logger.error(f"Get percept data error: {e}")
            self.send_error(500, str(e))

    def handle_get_cognition_data(self):
        """Handle get cognition data request"""
        try:
            pool = get_global_pool()
            response = pool.execute('get_cognition_data')
            
            # Extract cognition_data from response
            cognition_data = response.get('cognition_data', {})
            
            # Wrap in message for test compatibility
            result = {"message": cognition_data}
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())
                
        except Exception as e:
            logger.error(f"Get cognition data error: {e}")
            self.send_error(500, str(e))

    def handle_get_gene(self):
        """Handle get gene request"""
        try:
            # Extract gene name from path: /{processor_id}/gene/{gene_name}
            from urllib.parse import unquote
            parts = self.path.split('/')
            gene_name = unquote(parts[-1])  # URL-decode the gene name
            
            pool = get_global_pool()
            response = pool.execute('get_gene', {'gene_name': gene_name})
            
            # Extract gene_value from response
            gene_value = response.get('gene_value')
            
            # Return just the gene value in message for test compatibility
            result = {
                "gene_name": gene_name,
                "gene_value": gene_value,
                "message": gene_value
            }
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())
                
        except Exception as e:
            logger.error(f"Get gene error: {e}")
            self.send_error(500, str(e))

    def handle_get_pattern(self):
        """Handle get pattern request"""
        try:
            # Extract pattern ID from path: /{processor_id}/pattern/{pattern_id}
            from urllib.parse import unquote
            parts = self.path.split('/')
            pattern_id = unquote(parts[-1])  # URL-decode the pattern ID
            
            pool = get_global_pool()
            response = pool.execute('get_pattern', {'pattern_id': pattern_id})
            
            if response.get('status') == 'okay':
                result = {"message": response.get('pattern')}
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(result).encode())
            else:
                self.send_error(404, f"Pattern {pattern_id} not found")
                    
        except Exception as e:
            logger.error(f"Get pattern error: {e}")
            self.send_error(500, str(e))

    def handle_observe(self):
        """Handle observe requests via ZMQ"""
        try:
            # Extract processor ID from path: /{processor_id}/observe
            processor_id = self.path.split('/')[1]
            
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode())
            
            # The data can come directly or wrapped in a 'data' field
            # Support both formats for backward compatibility
            if 'strings' in data or 'vectors' in data or 'emotives' in data:
                observation_data = data  # Direct format (from tests)
            else:
                observation_data = data.get('data', {})  # Wrapped format
            
            # Add unique_id if not present
            if 'unique_id' not in observation_data:
                observation_data['unique_id'] = f'rest-{int(time.time() * 1000000)}'
            
            pool = get_global_pool()
            response = pool.execute('observe', observation_data)
            
            result = {
                "id": processor_id,
                "interval": response.get('interval', 0),
                "time_stamp": response.get('time_stamp', time.time()),
                "status": response.get('status', 'okay'),
                "message": {
                    "status": "observed",
                    "auto_learned_pattern": response.get('auto_learned_pattern')
                }
            }
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())
                
        except Exception as e:
            logger.error(f"Observe error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self.send_error(500, str(e))

    def handle_clear_all_memory(self):
        """Handle clear all memory request"""
        try:
            # Extract processor ID from path: /{processor_id}/clear-all-memory
            processor_id = self.path.split('/')[1]
            
            pool = get_global_pool()
            response = pool.execute('clear_all_memory')
            
            result = {
                "id": processor_id,
                "interval": response.get('interval', 0),
                "time_stamp": response.get('time_stamp', time.time()),
                "status": response.get('status', 'okay'),
                "message": response.get('message', 'all-cleared')
            }
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())
                
        except Exception as e:
            logger.error(f"Clear all memory error: {e}")
            self.send_error(500, str(e))

    def handle_clear_short_term_memory(self):
        """Handle clear short-term memory request"""
        try:
            # Extract processor ID from path
            processor_id = self.path.split('/')[1]
            
            pool = get_global_pool()
            response = pool.execute('clear_short_term_memory')
            
            result = {
                "id": processor_id,
                "interval": response.get('interval', 0),
                "time_stamp": response.get('time_stamp', time.time()),
                "status": response.get('status', 'okay'),
                "message": response.get('message', 'stm-cleared')
            }
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())
                
        except Exception as e:
            logger.error(f"Clear short-term memory error: {e}")
            self.send_error(500, str(e))

    def handle_learn(self):
        """Handle learn request"""
        try:
            # Extract processor ID from path
            processor_id = self.path.split('/')[1]
            
            # Get optional parameters from POST data
            data = {}
            if self.headers.get('Content-Length'):
                content_length = int(self.headers['Content-Length'])
                if content_length > 0:
                    post_data = self.rfile.read(content_length)
                    if post_data:
                        data = json.loads(post_data.decode())
            
            learning_flag = data.get('learning_flag', True)
            manual_flag = data.get('manual_flag', False)
            auto_act_flag = data.get('auto_act_flag', False)
            
            pool = get_global_pool()
            response = pool.execute('learn')
            
            # Preserve the pattern_name from the response  
            # Pattern name is returned in 'pattern_name' field from ZMQ server
            # Should be either 'PTRN|<hash>' or empty string for insufficient data
            pattern_name = response.get('pattern_name', '')
            
            # Don't use fallback messages - return actual response
            if pattern_name is None:
                pattern_name = ''
            
            result = {
                "id": processor_id,
                "interval": response.get('interval', 0),
                "time_stamp": response.get('time_stamp', time.time()),
                "status": response.get('status', 'okay'),
                "message": pattern_name,
                "pattern_name": pattern_name
            }
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())
                
        except Exception as e:
            logger.error(f"Learn error: {e}")
            self.send_error(500, str(e))

    def handle_gene_change(self):
        """Handle gene change request"""
        try:
            # Extract processor ID from path
            processor_id = self.path.split('/')[1]
            
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode())
            
            # Support both formats:
            # 1. Direct format: {"gene_name": "foo", "gene_value": 1}
            # 2. Data wrapper format: {"data": {"recall_threshold": 0.6, ...}}
            pool = get_global_pool()
            
            if 'data' in data:
                # Handle multiple gene updates in data wrapper format
                genes_to_update = data['data']
                for gene_name, gene_value in genes_to_update.items():
                    logger.info(f"Updating gene {gene_name} to {gene_value}")
                    response = pool.execute('gene_change', gene_name, gene_value)
                    if response.get('status') != 'okay':
                        logger.error(f"Failed to update gene {gene_name}: {response.get('message')}")
            else:
                # Handle single gene update in direct format
                gene_name = data.get('gene_name')
                gene_value = data.get('gene_value')
                
                if not gene_name or gene_value is None:
                    self.send_error(400, "gene_name and gene_value required")
                    return
                
                logger.info(f"Updating single gene {gene_name} to {gene_value}")
                response = pool.execute('gene_change', gene_name, gene_value)
                if response.get('status') != 'okay':
                    logger.error(f"Failed to update gene {gene_name}: {response.get('message')}")
            
            result = {
                "id": processor_id,
                "status": response.get('status', 'okay'),
                "message": "updated-genes"
            }
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())
                
        except Exception as e:
            logger.error(f"Gene change error: {e}")
            self.send_error(500, str(e))

    def log_message(self, format, *args):
        """Override to use our logger instead of stderr"""
        logger.info("%s - %s" % (self.address_string(), format % args))


class RestGateway:
    """REST gateway server that forwards requests to ZMQ backend"""
    
    def __init__(self, port=8000, zmq_host='localhost', zmq_port=5555):
        self.port = port
        self.zmq_host = zmq_host
        self.zmq_port = zmq_port
        self.server = None
        self.server_thread = None
        self.connection_pool = None
        
    def start(self):
        """Start the REST gateway server"""
        logger.info(f"Starting REST gateway on port {self.port}")
        
        # Initialize the connection pool
        self.connection_pool = ZMQConnectionPool(
            host=self.zmq_host,
            port=self.zmq_port,
            timeout=5000,
            heartbeat_interval=10000  # 10 seconds heartbeat
        )
        set_global_pool(self.connection_pool)
        logger.info(f"Initialized ZMQ connection pool to {self.zmq_host}:{self.zmq_port}")
        
        self.server = ThreadedHTTPServer(('0.0.0.0', self.port), RestGatewayHandler)
        self.server_thread = Thread(target=self.server.serve_forever)
        self.server_thread.daemon = True
        self.server_thread.start()
        logger.info(f"REST gateway started on http://0.0.0.0:{self.port}")
        
    def stop(self):
        """Stop the REST gateway server"""
        logger.info("Stopping REST gateway")
        
        # Cleanup connection pool
        if self.connection_pool:
            stats = self.connection_pool.get_stats()
            logger.info(f"Connection pool stats at shutdown: {stats}")
            self.connection_pool.shutdown()
            cleanup_global_pool()
        
        if self.server:
            self.server.shutdown()
            self.server_thread.join()
        logger.info("REST gateway stopped")