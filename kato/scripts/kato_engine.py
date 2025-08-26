#!/usr/bin/env python3
"""
KATO Engine Entry Point
Main entry point for starting the KATO ZMQ server.
"""

import json
import logging
import os
import signal
import sys
import time
from threading import Thread

from kato.workers.kato_processor import KatoProcessor
from kato.workers.zmq_server import ZMQServer
from kato.workers.rest_gateway import RestGateway
from kato.workers.zmq_switcher import get_zmq_server

# Set up logging
logging.basicConfig(
    level=getattr(logging, os.environ.get('LOG_LEVEL', 'INFO')),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('kato.engine')


class KatoEngine:
    def __init__(self):
        self.zmq_server = None
        self.processor = None
        self.rest_gateway = None
        self.zmq_thread = None
        
    def load_manifest(self):
        """Load processor configuration from environment."""
        manifest_str = os.environ.get('MANIFEST')
        if not manifest_str:
            raise ValueError("MANIFEST environment variable is required")
        
        try:
            manifest = json.loads(manifest_str)
            logger.info(f"Loaded manifest for processor: {manifest.get('name', 'Unknown')}")
            logger.info(f"Processor ID: {manifest.get('id', 'Unknown')}")
            return manifest
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in MANIFEST environment variable: {e}")
    
    def start_server(self):
        """Initialize and start the KATO ZMQ server."""
        logger.info("Starting KATO Engine...")
        
        # Load configuration
        manifest = self.load_manifest()
        
        # Create processor
        logger.info("Initializing KATO Processor...")
        self.processor = KatoProcessor(manifest)
        
        # Create ZMQ server (use switcher to get appropriate implementation)
        port = int(os.environ.get('ZMQ_PORT', '5555'))
        logger.info(f"Starting ZMQ server on port {port}...")
        
        # Use the switcher to get the right implementation
        self.zmq_server = get_zmq_server(self.processor, port=port)
        
        # Start ZMQ server in a thread
        self.zmq_thread = Thread(target=self.zmq_server.start)
        self.zmq_thread.daemon = True
        self.zmq_thread.start()
        
        logger.info(f"ZMQ server started successfully on port {port}")
        logger.info(f"Processor '{self.processor.name}' (ID: {self.processor.id}) is ready")
        
        # Start REST gateway for backward compatibility with tests
        rest_port = os.environ.get('REST_PORT', '8000')
        logger.info(f"Starting REST gateway on port {rest_port}...")
        self.rest_gateway = RestGateway(int(rest_port))
        self.rest_gateway.start()
        logger.info(f"REST gateway started on port {rest_port}")
        
        return self.zmq_server
    
    def stop_server(self):
        """Gracefully stop the server."""
        if self.rest_gateway:
            logger.info("Stopping REST gateway...")
            self.rest_gateway.stop()
        if self.zmq_server:
            logger.info("Stopping ZMQ server...")
            self.zmq_server.stop()
            if self.zmq_thread:
                self.zmq_thread.join(timeout=5)
            logger.info("ZMQ server stopped")
    
    def run(self):
        """Run the server and wait for termination."""
        try:
            self.start_server()
            
            # Set up signal handlers for graceful shutdown
            def signal_handler(signum, frame):
                logger.info(f"Received signal {signum}, shutting down...")
                self.stop_server()
                sys.exit(0)
            
            signal.signal(signal.SIGINT, signal_handler)
            signal.signal(signal.SIGTERM, signal_handler)
            
            # Keep the server running
            logger.info("KATO Engine is running. Press Ctrl+C to stop.")
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                logger.info("Received keyboard interrupt")
            
        except Exception as e:
            logger.error(f"Failed to start KATO Engine: {e}")
            sys.exit(1)
        finally:
            self.stop_server()


def main():
    """Main entry point for kato-engine command."""
    engine = KatoEngine()
    engine.run()


if __name__ == '__main__':
    main()