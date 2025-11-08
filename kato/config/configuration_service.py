"""
Configuration Service for KATO

This service provides centralized configuration management, handling:
- Default configuration extraction from settings
- Session-level configuration overrides
- Validation and consistency across components
- Configuration merging and resolution

This eliminates duplication of default settings extraction across
ProcessorManager, FastAPI service, and other components.
"""

import logging
from dataclasses import dataclass
from typing import Any, Optional

from kato.config.session_config import SessionConfiguration
from kato.config.settings import Settings

logger = logging.getLogger('kato.config.configuration_service')


@dataclass
class ResolvedConfiguration:
    """
    Resolved configuration combining defaults with session overrides.

    This represents the final configuration that should be applied
    to a processor or operation.
    """
    # Learning Configuration
    max_pattern_length: int
    persistence: int
    recall_threshold: float
    stm_mode: str

    # Processing Configuration
    indexer_type: str
    max_predictions: int
    sort_symbols: bool
    process_predictions: bool
    use_token_matching: bool
    rank_sort_algo: str

    # Source tracking
    source_session_id: Optional[str] = None
    source_node_id: Optional[str] = None
    overrides_applied: dict[str, Any] = None

    def to_genes_dict(self) -> dict[str, Any]:
        """
        Convert to genes dictionary format for API responses.

        Returns:
            Dictionary in the format expected by gene APIs
        """
        return {
            'recall_threshold': self.recall_threshold,
            'persistence': self.persistence,
            'max_pattern_length': self.max_pattern_length,
            'stm_mode': self.stm_mode,
            'max_predictions': self.max_predictions,
            'sort': self.sort_symbols,
            'process_predictions': self.process_predictions,
            'use_token_matching': self.use_token_matching,
            'rank_sort_algo': self.rank_sort_algo
        }


class ConfigurationService:
    """
    Centralized configuration management for KATO.

    This service provides a single source of truth for:
    - Default configuration values from settings
    - Session-specific configuration overrides
    - Configuration validation and consistency
    - Configuration merging and resolution
    """

    def __init__(self, settings: Settings):
        """
        Initialize the configuration service.

        Args:
            settings: KATO settings instance
        """
        self.settings = settings
        logger.info("ConfigurationService initialized")

    def get_default_configuration(self) -> dict[str, Any]:
        """
        Extract default configuration from settings.

        This is the single source of truth for default values,
        eliminating duplication across components.

        Returns:
            Dictionary with default configuration values
        """
        return {
            'indexer_type': self.settings.processing.indexer_type,
            'max_pattern_length': self.settings.learning.max_pattern_length,
            'persistence': self.settings.learning.persistence,
            'recall_threshold': self.settings.learning.recall_threshold,
            'stm_mode': self.settings.learning.stm_mode,
            'max_predictions': self.settings.processing.max_predictions,
            'sort': self.settings.processing.sort_symbols,
            'process_predictions': self.settings.processing.process_predictions,
            'use_token_matching': self.settings.processing.use_token_matching,
            'rank_sort_algo': self.settings.processing.rank_sort_algo
        }

    def resolve_configuration(
        self,
        session_config: Optional[SessionConfiguration] = None,
        session_id: Optional[str] = None,
        node_id: Optional[str] = None
    ) -> ResolvedConfiguration:
        """
        Resolve final configuration by merging defaults with session overrides.

        Args:
            session_config: Optional session-specific configuration
            session_id: Session ID for tracking
            node_id: Node ID for tracking

        Returns:
            ResolvedConfiguration with final values and source tracking
        """
        # Start with defaults
        defaults = self.get_default_configuration()

        # Track which values were overridden
        overrides_applied = {}

        # Apply session overrides if provided
        if session_config:
            merged = session_config.merge_with_defaults(defaults)

            # Track which values were overridden
            for key, value in merged.items():
                if key in defaults and defaults[key] != value:
                    overrides_applied[key] = {
                        'default': defaults[key],
                        'override': value,
                        'source': 'session_config'
                    }
        else:
            merged = defaults

        # Create resolved configuration
        resolved = ResolvedConfiguration(
            max_pattern_length=merged['max_pattern_length'],
            persistence=merged['persistence'],
            recall_threshold=merged['recall_threshold'],
            stm_mode=merged['stm_mode'],
            indexer_type=merged['indexer_type'],
            max_predictions=merged['max_predictions'],
            sort_symbols=merged['sort'],
            process_predictions=merged['process_predictions'],
            use_token_matching=merged['use_token_matching'],
            rank_sort_algo=merged['rank_sort_algo'],
            source_session_id=session_id,
            source_node_id=node_id,
            overrides_applied=overrides_applied
        )

        if overrides_applied:
            logger.debug(
                f"Configuration resolved for session {session_id}, node {node_id} "
                f"with {len(overrides_applied)} overrides: {list(overrides_applied.keys())}"
            )

        return resolved

    def validate_configuration_update(self, updates: dict[str, Any]) -> dict[str, str]:
        """
        Validate configuration updates before applying them.

        Args:
            updates: Dictionary of configuration updates

        Returns:
            Dictionary of validation errors (empty if all valid)
        """
        errors = {}

        # Validate recall_threshold
        if 'recall_threshold' in updates:
            value = updates['recall_threshold']
            if not isinstance(value, (int, float)) or not 0.0 <= value <= 1.0:
                errors['recall_threshold'] = 'Must be a number between 0.0 and 1.0'

        # Validate persistence
        if 'persistence' in updates:
            value = updates['persistence']
            if not isinstance(value, int) or not 1 <= value <= 100:
                errors['persistence'] = 'Must be an integer between 1 and 100'

        # Validate max_pattern_length
        if 'max_pattern_length' in updates:
            value = updates['max_pattern_length']
            if not isinstance(value, int) or value < 0:
                errors['max_pattern_length'] = 'Must be a non-negative integer'

        # Validate max_predictions
        if 'max_predictions' in updates:
            value = updates['max_predictions']
            if not isinstance(value, int) or not 1 <= value <= 10000:
                errors['max_predictions'] = 'Must be an integer between 1 and 10000'

        # Validate indexer_type
        if 'indexer_type' in updates:
            value = updates['indexer_type']
            valid_indexers = ['VI', 'LSH', 'ANNOY', 'FAISS']
            if not isinstance(value, str) or value not in valid_indexers:
                errors['indexer_type'] = f'Must be one of: {", ".join(valid_indexers)}'

        # Normalize and validate stm_mode
        if 'stm_mode' in updates:
            value = updates['stm_mode']
            valid_modes = ['CLEAR', 'ROLLING']
            if not isinstance(value, str):
                errors['stm_mode'] = 'Must be a string'
            elif value not in valid_modes:
                logger.warning(f"Invalid stm_mode '{value}', normalizing to 'CLEAR'")
                updates['stm_mode'] = 'CLEAR'

        # Validate boolean fields
        for bool_field in ['sort', 'process_predictions', 'use_token_matching']:
            if bool_field in updates:
                value = updates[bool_field]
                if not isinstance(value, bool):
                    errors[bool_field] = 'Must be a boolean (true/false)'

        # Validate rank_sort_algo
        if 'rank_sort_algo' in updates:
            value = updates['rank_sort_algo']
            valid_algorithms = [
                'potential', 'similarity', 'evidence', 'confidence', 'snr',
                'fragmentation', 'frequency', 'normalized_entropy',
                'global_normalized_entropy', 'itfdf_similarity', 'confluence',
                'predictive_information'
            ]
            if not isinstance(value, str) or value not in valid_algorithms:
                errors['rank_sort_algo'] = f'Must be one of: {", ".join(valid_algorithms)}'

        return errors

    def get_configuration_info(self, session_config: Optional[SessionConfiguration] = None) -> dict[str, Any]:
        """
        Get comprehensive configuration information including defaults and overrides.

        Args:
            session_config: Optional session configuration

        Returns:
            Dictionary with configuration details, defaults, and overrides
        """
        defaults = self.get_default_configuration()
        resolved = self.resolve_configuration(session_config)

        return {
            'defaults': defaults,
            'resolved': resolved.to_genes_dict(),
            'overrides_applied': resolved.overrides_applied or {},
            'has_overrides': bool(resolved.overrides_applied),
            'source_session': resolved.source_session_id,
            'source_node': resolved.source_node_id
        }


# Global configuration service instance (singleton pattern)
_configuration_service: Optional[ConfigurationService] = None


def get_configuration_service(settings: Optional[Settings] = None) -> ConfigurationService:
    """
    Get or create the global configuration service instance.

    Args:
        settings: Optional settings instance (required for first call)

    Returns:
        ConfigurationService instance
    """
    global _configuration_service
    if _configuration_service is None:
        if settings is None:
            from kato.config.settings import get_settings
            settings = get_settings()
        _configuration_service = ConfigurationService(settings)
    return _configuration_service


def reset_configuration_service():
    """Reset the global configuration service (for testing)."""
    global _configuration_service
    _configuration_service = None
