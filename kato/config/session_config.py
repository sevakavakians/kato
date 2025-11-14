"""
Session-specific configuration management for KATO.

This module provides per-session configuration capabilities, allowing each session
to have its own set of runtime-modifiable parameters. This replaces the previous
approach of having multiple Docker containers with different configurations.
"""

import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

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
    use_token_matching: Optional[bool] = None  # Token-level vs character-level matching
    rank_sort_algo: Optional[str] = None  # Ranking algorithm for predictions (e.g., 'potential', 'similarity')

    # Filter Pipeline Configuration
    filter_pipeline: Optional[list[str]] = None  # Ordered list of filter names

    # Length Filter Parameters
    length_min_ratio: Optional[float] = None  # Min pattern length as ratio of STM length (default: 0.5)
    length_max_ratio: Optional[float] = None  # Max pattern length as ratio of STM length (default: 2.0)

    # Jaccard Filter Parameters
    jaccard_threshold: Optional[float] = None  # Minimum Jaccard similarity (default: 0.3)
    jaccard_min_overlap: Optional[int] = None  # Minimum absolute token overlap count (default: 2)

    # MinHash/LSH Filter Parameters
    minhash_threshold: Optional[float] = None  # Estimated Jaccard threshold for LSH (default: 0.7)
    minhash_bands: Optional[int] = None  # Number of LSH bands (default: 20)
    minhash_rows: Optional[int] = None  # Rows per LSH band (default: 5)
    minhash_num_hashes: Optional[int] = None  # Total MinHash signature size (default: 100)

    # Bloom Filter Parameters
    bloom_false_positive_rate: Optional[float] = None  # Bloom filter FPR (default: 0.01)

    # Pipeline Control Parameters
    max_candidates_per_stage: Optional[int] = None  # Safety limit per stage (default: 100000)
    enable_filter_metrics: Optional[bool] = None  # Log timing and counts (default: True)

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

            # Validate max_predictions
            if self.max_predictions is not None and not 1 <= self.max_predictions <= 10000:
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

            # Validate rank_sort_algo
            if self.rank_sort_algo is not None:
                valid_algorithms = [
                    'potential', 'similarity', 'evidence', 'confidence', 'snr',
                    'fragmentation', 'frequency', 'normalized_entropy',
                    'global_normalized_entropy', 'itfdf_similarity', 'confluence',
                    'predictive_information'
                ]
                if self.rank_sort_algo not in valid_algorithms:
                    logger.error(f"Invalid rank_sort_algo: {self.rank_sort_algo}")
                    return False

            # Validate filter pipeline
            if self.filter_pipeline is not None:
                valid_filters = ['minhash', 'length', 'jaccard', 'bloom', 'rapidfuzz']
                for filter_name in self.filter_pipeline:
                    if filter_name not in valid_filters:
                        logger.error(f"Invalid filter in pipeline: {filter_name}")
                        return False

            # Validate filter parameters
            if self.length_min_ratio is not None and not 0.0 <= self.length_min_ratio <= 1.0:
                logger.error(f"Invalid length_min_ratio: {self.length_min_ratio}")
                return False

            if self.length_max_ratio is not None and self.length_max_ratio < 1.0:
                logger.error(f"Invalid length_max_ratio: {self.length_max_ratio}")
                return False

            if self.jaccard_threshold is not None and not 0.0 <= self.jaccard_threshold <= 1.0:
                logger.error(f"Invalid jaccard_threshold: {self.jaccard_threshold}")
                return False

            if self.jaccard_min_overlap is not None and self.jaccard_min_overlap < 1:
                logger.error(f"Invalid jaccard_min_overlap: {self.jaccard_min_overlap}")
                return False

            if self.minhash_threshold is not None and not 0.0 <= self.minhash_threshold <= 1.0:
                logger.error(f"Invalid minhash_threshold: {self.minhash_threshold}")
                return False

            if self.minhash_bands is not None and not 1 <= self.minhash_bands <= 100:
                logger.error(f"Invalid minhash_bands: {self.minhash_bands}")
                return False

            if self.minhash_rows is not None and not 1 <= self.minhash_rows <= 20:
                logger.error(f"Invalid minhash_rows: {self.minhash_rows}")
                return False

            if self.minhash_num_hashes is not None and not 10 <= self.minhash_num_hashes <= 256:
                logger.error(f"Invalid minhash_num_hashes: {self.minhash_num_hashes}")
                return False

            if self.bloom_false_positive_rate is not None and not 0.0001 <= self.bloom_false_positive_rate <= 0.1:
                logger.error(f"Invalid bloom_false_positive_rate: {self.bloom_false_positive_rate}")
                return False

            if self.max_candidates_per_stage is not None and self.max_candidates_per_stage < 100:
                logger.error(f"Invalid max_candidates_per_stage: {self.max_candidates_per_stage}")
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

    def merge_with_defaults(self, defaults: dict[str, Any]) -> dict[str, Any]:
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
            if key not in ['session_id', 'node_id', 'created_at', 'updated_at', 'version'] and value is not None:
                merged[key] = value

        return merged

    def to_dict(self) -> dict[str, Any]:
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
    def from_dict(cls, data: dict[str, Any]) -> 'SessionConfiguration':
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
            'use_token_matching', 'rank_sort_algo', 'session_id', 'node_id', 'version',
            # Filter pipeline fields
            'filter_pipeline', 'length_min_ratio', 'length_max_ratio',
            'jaccard_threshold', 'jaccard_min_overlap',
            'minhash_threshold', 'minhash_bands', 'minhash_rows', 'minhash_num_hashes',
            'bloom_false_positive_rate', 'max_candidates_per_stage', 'enable_filter_metrics'
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

    def get_config_only(self) -> dict[str, Any]:
        """
        Get only the configuration parameters (exclude metadata and topology).

        Returns:
            Dictionary of configuration parameters only (only non-None values)
        """
        config = {}

        config_keys = [
            'max_pattern_length', 'persistence', 'recall_threshold',
            'indexer_type', 'max_predictions', 'sort_symbols', 'process_predictions',
            'use_token_matching', 'stm_mode', 'rank_sort_algo',
            # Filter pipeline configuration
            'filter_pipeline', 'length_min_ratio', 'length_max_ratio',
            'jaccard_threshold', 'jaccard_min_overlap',
            'minhash_threshold', 'minhash_bands', 'minhash_rows', 'minhash_num_hashes',
            'bloom_false_positive_rate', 'max_candidates_per_stage', 'enable_filter_metrics'
        ]

        for key in config_keys:
            value = getattr(self, key)
            if value is not None:
                config[key] = value

        return config

    def get_effective_config(self, defaults: dict[str, Any]) -> dict[str, Any]:
        """
        Get effective configuration with all configurable items.

        Merges session configuration with system defaults, returning ALL
        configurable items with their effective values (session override or default).

        Args:
            defaults: System default configuration dictionary

        Returns:
            Dictionary of all configuration parameters with effective values
        """
        config = {}

        config_keys = [
            'max_pattern_length', 'persistence', 'recall_threshold',
            'indexer_type', 'max_predictions', 'sort_symbols', 'process_predictions',
            'use_token_matching', 'stm_mode', 'rank_sort_algo',
            # Filter pipeline configuration
            'filter_pipeline', 'length_min_ratio', 'length_max_ratio',
            'jaccard_threshold', 'jaccard_min_overlap',
            'minhash_threshold', 'minhash_bands', 'minhash_rows', 'minhash_num_hashes',
            'bloom_false_positive_rate', 'max_candidates_per_stage', 'enable_filter_metrics'
        ]

        # For each config key, use session value if set, otherwise use default
        for key in config_keys:
            session_value = getattr(self, key)
            if session_value is not None:
                # Session has override for this key
                config[key] = session_value
            elif key in defaults:
                # Use default value
                config[key] = defaults[key]
            # else: neither session nor default has this key (skip it)

        return config

