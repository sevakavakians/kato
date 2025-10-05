"""
Session-specific configuration management for KATO.

This module provides per-session configuration capabilities, allowing each session
to have its own set of runtime-modifiable parameters. This replaces the previous
approach of having multiple Docker containers with different configurations.
"""

import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger('kato.config.session_config')


@dataclass
class SessionConfiguration:
    """
    Session-specific configuration that can be dynamically modified.
    
    All parameters default to None, which means "use system default".
    When a value is set, it overrides the system default for that session.
    
    This enables users to create sessions with different processing 
    characteristics.
    """

    # Learning Configuration
    max_pattern_length: Optional[int] = None  # 0+ (0 = manual learning only)
    persistence: Optional[int] = None  # 1-100 (emotive window size)
    recall_threshold: Optional[float] = None  # 0.0-1.0 (pattern matching threshold)
    stm_mode: Optional[str] = None  # STM mode after auto-learning ('CLEAR' or 'ROLLING')

    # Processing Configuration
    indexer_type: Optional[str] = None  # Vector indexer type (e.g., 'VI')
    max_predictions: Optional[int] = None  # 1-10000 (prediction limit)
    sort_symbols: Optional[bool] = None  # Whether to sort symbols alphabetically
    process_predictions: Optional[bool] = None  # Whether to process predictions

    # Metadata
    session_id: str = field(default="")
    node_id: str = field(default="")
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    version: int = field(default=1)

    def validate(self) -> bool:
        """
        Validate all configuration parameters are within acceptable ranges.
        
        Returns:
            True if all parameters are valid, False otherwise
        """
        try:
            # Validate recall_threshold
            if self.recall_threshold is not None:
                if not 0.0 <= self.recall_threshold <= 1.0:
                    logger.error(f"Invalid recall_threshold: {self.recall_threshold}")
                    return False

            # Validate persistence
            if self.persistence is not None:
                if not 1 <= self.persistence <= 100:
                    logger.error(f"Invalid persistence: {self.persistence}")
                    return False

            # Validate max_pattern_length
            if self.max_pattern_length is not None:
                if self.max_pattern_length < 0:
                    logger.error(f"Invalid max_pattern_length: {self.max_pattern_length}")
                    return False

            # Validate max_predictions
            if self.max_predictions is not None:
                if not 1 <= self.max_predictions <= 10000:
                    logger.error(f"Invalid max_predictions: {self.max_predictions}")
                    return False

            # Validate indexer_type
            if self.indexer_type is not None:
                valid_indexers = ['VI', 'LSH', 'ANNOY', 'FAISS']  # Add valid types
                if self.indexer_type not in valid_indexers:
                    logger.error(f"Invalid indexer_type: {self.indexer_type}")
                    return False

            # Normalize and validate stm_mode
            if self.stm_mode is not None:
                valid_modes = ['CLEAR', 'ROLLING']
                if self.stm_mode not in valid_modes:
                    logger.warning(f"Invalid stm_mode '{self.stm_mode}', normalizing to 'CLEAR'")
                    self.stm_mode = 'CLEAR'

            return True

        except Exception as e:
            logger.error(f"Validation error: {e}")
            return False

    def update(self, updates: Dict[str, Any]) -> bool:
        """
        Update configuration with new values.
        
        Args:
            updates: Dictionary of parameter updates
        
        Returns:
            True if update was successful, False if validation failed
        """
        # Store original values in case we need to rollback
        original_values = {}

        try:
            for key, value in updates.items():
                if hasattr(self, key) and key not in ['session_id', 'node_id', 'created_at', 'updated_at', 'version']:
                    original_values[key] = getattr(self, key)
                    setattr(self, key, value)

            # Validate after updates
            if not self.validate():
                # Rollback changes
                for key, value in original_values.items():
                    setattr(self, key, value)
                return False

            # Update metadata
            self.updated_at = datetime.now(timezone.utc)
            self.version += 1

            return True

        except Exception as e:
            logger.error(f"Update failed: {e}")
            # Rollback changes
            for key, value in original_values.items():
                setattr(self, key, value)
            return False

    def merge_with_defaults(self, defaults: Dict[str, Any]) -> Dict[str, Any]:
        """
        Merge session configuration with system defaults.
        
        Session values override defaults where set (not None).
        
        Args:
            defaults: System default configuration
        
        Returns:
            Merged configuration dictionary
        """
        merged = defaults.copy()

        # Override with session values where set
        for key, value in asdict(self).items():
            if key not in ['session_id', 'node_id', 'created_at', 'updated_at', 'version']:
                if value is not None:
                    merged[key] = value

        return merged

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert configuration to dictionary for serialization.
        
        Returns:
            Dictionary representation of configuration
        """
        data = asdict(self)
        # Convert datetime to ISO format for serialization
        data['created_at'] = self.created_at.isoformat()
        data['updated_at'] = self.updated_at.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SessionConfiguration':
        """
        Create SessionConfiguration from dictionary.
        
        Args:
            data: Dictionary with configuration values
        
        Returns:
            SessionConfiguration instance
        """
        # Filter only valid fields
        valid_fields = {
            'max_pattern_length', 'persistence', 'recall_threshold', 'stm_mode',
            'indexer_type', 'max_predictions', 'sort_symbols', 'process_predictions',
            'session_id', 'node_id', 'version'
        }

        filtered_data = {k: v for k, v in data.items() if k in valid_fields}

        # Handle datetime fields
        if 'created_at' in data:
            if isinstance(data['created_at'], str):
                filtered_data['created_at'] = datetime.fromisoformat(data['created_at'])
            else:
                filtered_data['created_at'] = data['created_at']

        if 'updated_at' in data:
            if isinstance(data['updated_at'], str):
                filtered_data['updated_at'] = datetime.fromisoformat(data['updated_at'])
            else:
                filtered_data['updated_at'] = data['updated_at']

        return cls(**filtered_data)

    def get_config_only(self) -> Dict[str, Any]:
        """
        Get only the configuration parameters (exclude metadata and topology).
        
        Returns:
            Dictionary of configuration parameters only
        """
        config = {}

        config_keys = [
            'max_pattern_length', 'persistence', 'recall_threshold',
            'indexer_type', 'max_predictions', 'sort_symbols', 'process_predictions'
        ]

        for key in config_keys:
            value = getattr(self, key)
            if value is not None:
                config[key] = value

        return config

