"""
User-specific configuration management for KATO v2.

This module provides per-user configuration capabilities, allowing each user
to have their own set of runtime-modifiable parameters while maintaining
complete isolation between users.
"""

from typing import Optional, Dict, Any, Literal
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
import logging

logger = logging.getLogger('kato.v2.config.user_config')


@dataclass
class UserConfiguration:
    """
    User-specific configuration that can be dynamically modified.
    
    All parameters default to None, which means "use system default".
    When a value is set, it overrides the system default for that user.
    """
    
    # Learning parameters
    recall_threshold: Optional[float] = None  # 0.0-1.0
    persistence: Optional[int] = None  # 1-100
    max_pattern_length: Optional[int] = None  # 0+ (0 = unlimited)
    smoothness: Optional[int] = None  # 1-10
    quiescence: Optional[int] = None  # 0-100
    
    # Processing parameters
    auto_act_method: Optional[Literal['none', 'threshold', 'adaptive']] = None
    auto_act_threshold: Optional[float] = None  # 0.0-1.0
    always_update_frequencies: Optional[bool] = None
    max_predictions: Optional[int] = None  # 1-10000
    search_depth: Optional[int] = None  # 1-100
    sort_symbols: Optional[bool] = None
    process_predictions: Optional[bool] = None
    
    # Metadata
    user_id: str = field(default="")
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
            
            # Validate smoothness
            if self.smoothness is not None:
                if not 1 <= self.smoothness <= 10:
                    logger.error(f"Invalid smoothness: {self.smoothness}")
                    return False
            
            # Validate quiescence
            if self.quiescence is not None:
                if not 0 <= self.quiescence <= 100:
                    logger.error(f"Invalid quiescence: {self.quiescence}")
                    return False
            
            # Validate auto_act_method
            if self.auto_act_method is not None:
                if self.auto_act_method not in ['none', 'threshold', 'adaptive']:
                    logger.error(f"Invalid auto_act_method: {self.auto_act_method}")
                    return False
            
            # Validate auto_act_threshold
            if self.auto_act_threshold is not None:
                if not 0.0 <= self.auto_act_threshold <= 1.0:
                    logger.error(f"Invalid auto_act_threshold: {self.auto_act_threshold}")
                    return False
            
            # Validate max_predictions
            if self.max_predictions is not None:
                if not 1 <= self.max_predictions <= 10000:
                    logger.error(f"Invalid max_predictions: {self.max_predictions}")
                    return False
            
            # Validate search_depth
            if self.search_depth is not None:
                if not 1 <= self.search_depth <= 100:
                    logger.error(f"Invalid search_depth: {self.search_depth}")
                    return False
            
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
                if hasattr(self, key) and key not in ['user_id', 'created_at', 'updated_at', 'version']:
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
        Merge user configuration with system defaults.
        
        User values override defaults where set (not None).
        
        Args:
            defaults: System default configuration
        
        Returns:
            Merged configuration dictionary
        """
        merged = defaults.copy()
        
        # Override with user values where set
        for key, value in asdict(self).items():
            if key not in ['user_id', 'created_at', 'updated_at', 'version']:
                if value is not None:
                    merged[key] = value
        
        return merged
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert configuration to dictionary for serialization.
        
        Returns:
            Dictionary representation of configuration
        """
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'UserConfiguration':
        """
        Create UserConfiguration from dictionary.
        
        Args:
            data: Dictionary with configuration values
        
        Returns:
            UserConfiguration instance
        """
        # Filter only valid fields
        valid_fields = {
            'recall_threshold', 'persistence', 'max_pattern_length', 
            'smoothness', 'quiescence', 'auto_act_method', 
            'auto_act_threshold', 'always_update_frequencies',
            'max_predictions', 'search_depth', 'sort_symbols',
            'process_predictions', 'user_id', 'version'
        }
        
        filtered_data = {k: v for k, v in data.items() if k in valid_fields}
        
        # Handle datetime fields
        if 'created_at' in data:
            if isinstance(data['created_at'], str):
                from datetime import datetime
                filtered_data['created_at'] = datetime.fromisoformat(data['created_at'])
            else:
                filtered_data['created_at'] = data['created_at']
        
        if 'updated_at' in data:
            if isinstance(data['updated_at'], str):
                from datetime import datetime
                filtered_data['updated_at'] = datetime.fromisoformat(data['updated_at'])
            else:
                filtered_data['updated_at'] = data['updated_at']
        
        return cls(**filtered_data)
    
    def get_updates_only(self) -> Dict[str, Any]:
        """
        Get only the parameters that have been set (not None).
        
        Returns:
            Dictionary of set parameters only
        """
        updates = {}
        
        for key, value in asdict(self).items():
            if key not in ['user_id', 'created_at', 'updated_at', 'version']:
                if value is not None:
                    updates[key] = value
        
        return updates