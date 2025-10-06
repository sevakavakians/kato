"""
User-specific configuration management for KATO v2.

This module provides per-user configuration capabilities, allowing each user
to have their own set of runtime-modifiable parameters while maintaining
complete isolation between users.
"""

import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

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

    # Processing parameters
    max_predictions: Optional[int] = None  # 1-10000
    sort_symbols: Optional[bool] = None
    process_predictions: Optional[bool] = None

    # Metadata
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
            if self.recall_threshold is not None and not 0.0 <= self.recall_threshold <= 1.0:
                logger.error(f"Invalid recall_threshold: {self.recall_threshold}")
                return False

            # Validate persistence
            if self.persistence is not None and not 1 <= self.persistence <= 100:
                logger.error(f"Invalid persistence: {self.persistence}")
                return False

            # Validate max_pattern_length
            if self.max_pattern_length is not None and self.max_pattern_length < 0:
                logger.error(f"Invalid max_pattern_length: {self.max_pattern_length}")
                return False

            if self.max_predictions is not None and not 1 <= self.max_predictions <= 10000:
                logger.error(f"Invalid max_predictions: {self.max_predictions}")
                return False

            return True

        except Exception as e:
            logger.error(f"Validation error: {e}")
            return False

    def update(self, updates: dict[str, Any]) -> bool:
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
                if hasattr(self, key) and key not in ['node_id', 'created_at', 'updated_at', 'version']:
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

    def merge_with_defaults(self, defaults: dict[str, Any]) -> dict[str, Any]:
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
            if key not in ['node_id', 'created_at', 'updated_at', 'version'] and value is not None:
                merged[key] = value

        return merged

    def to_dict(self) -> dict[str, Any]:
        """
        Convert configuration to dictionary for serialization.

        Returns:
            Dictionary representation of configuration
        """
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'UserConfiguration':
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
            'max_predictions', 'sort_symbols',
            'process_predictions', 'node_id', 'version'
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

    def get_updates_only(self) -> dict[str, Any]:
        """
        Get only the parameters that have been set (not None).

        Returns:
            Dictionary of set parameters only
        """
        updates = {}

        for key, value in asdict(self).items():
            if key not in ['node_id', 'created_at', 'updated_at', 'version'] and value is not None:
                updates[key] = value

        return updates
