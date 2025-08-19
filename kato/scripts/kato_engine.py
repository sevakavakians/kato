#!/usr/bin/env python3
"""
KATO Engine Entry Point
Main entry point for starting the KATO gRPC server.
"""

import json
import logging
import os
import signal
import sys
import time
from concurrent import futures

import grpc
from kato.workers.kato_processor import KatoProcessor
from kato.workers.server import KatoEngineServicer
from kato.workers.rest_gateway import RestGateway
from kato import kato_proc_pb2_grpc

# Set up logging
logging.basicConfig(
    level=getattr(logging, os.environ.get('LOG_LEVEL', 'INFO')),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('kato.engine')


class KatoEngine:
    def __init__(self):
        self.server = None
        self.processor = None
        self.rest_gateway = None
        
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
        """Initialize and start the KATO gRPC server."""
        logger.info("Starting KATO Engine...")
        
        # Load configuration
        manifest = self.load_manifest()
        
        # Create processor
        logger.info("Initializing KATO Processor...")
        self.processor = KatoProcessor(manifest)
        
        # Create gRPC server
        port = os.environ.get('PORT', '1441')
        logger.info(f"Starting gRPC server on port {port}...")
        
        self.server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
        servicer = KatoEngineServicer(self.processor)
        kato_proc_pb2_grpc.add_KatoEngineServicer_to_server(servicer, self.server)
        
        listen_addr = f'[::]:{port}'
        self.server.add_insecure_port(listen_addr)
        
        # Start gRPC server
        self.server.start()
        logger.info(f"KATO Engine started successfully on {listen_addr}")
        logger.info(f"Processor '{self.processor.name}' (ID: {self.processor.id}) is ready")
        
        # Start REST gateway for backward compatibility with tests
        rest_port = os.environ.get('REST_PORT', '8000')
        logger.info(f"Starting REST gateway on port {rest_port}...")
        self.rest_gateway = RestGateway(int(rest_port))
        self.rest_gateway.start()
        logger.info(f"REST gateway started on port {rest_port}")
        
        return self.server
    
    def stop_server(self):
        """Gracefully stop the server."""
        if self.rest_gateway:
            logger.info("Stopping REST gateway...")
            self.rest_gateway.stop()
        if self.server:
            logger.info("Stopping KATO Engine...")
            self.server.stop(grace=5)
            logger.info("KATO Engine stopped")
    
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