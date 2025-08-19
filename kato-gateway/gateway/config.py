"""
Configuration management for KATO REST Gateway
"""

import os
import json
import yaml
from typing import Dict, List, Optional
from pydantic import BaseModel


class ProcessorConfig(BaseModel):
    """Configuration for a single KATO processor"""
    id: str
    name: str
    grpc_endpoint: str
    description: Optional[str] = None


class GatewayConfig(BaseModel):
    """Main gateway configuration"""
    port: int = 8000
    log_level: str = "INFO"
    processors: List[ProcessorConfig] = []
    timeout: int = 30
    max_connections: int = 10


def load_config() -> GatewayConfig:
    """Load configuration from environment or config file"""
    config = GatewayConfig()
    
    # Try to load from config file first
    config_file = os.environ.get('GATEWAY_CONFIG', 'config.yaml')
    if os.path.exists(config_file):
        with open(config_file, 'r') as f:
            data = yaml.safe_load(f)
            config = GatewayConfig(**data)
    
    # Override with environment variables
    config.port = int(os.environ.get('GATEWAY_PORT', config.port))
    config.log_level = os.environ.get('LOG_LEVEL', config.log_level)
    
    # Load processors from environment if not in config file
    if not config.processors:
        processors = []
        
        # Check for individual processor environment variables
        # Format: KATO_P1=processor_id:grpc_endpoint
        for key, value in os.environ.items():
            if key.startswith('KATO_'):
                parts = value.split(':')
                if len(parts) >= 2:
                    processor_id = parts[0]
                    grpc_endpoint = ':'.join(parts[1:])  # Handle IPv6 addresses
                    name = key.replace('KATO_', '')
                    processors.append(ProcessorConfig(
                        id=processor_id,
                        name=name,
                        grpc_endpoint=grpc_endpoint
                    ))
        
        # Also check for JSON-formatted processor list
        if proc_json := os.environ.get('KATO_PROCESSORS'):
            try:
                proc_data = json.loads(proc_json)
                for p in proc_data:
                    processors.append(ProcessorConfig(**p))
            except json.JSONDecodeError:
                pass
        
        config.processors = processors
    
    return config