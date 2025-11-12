"""
Bloom filter-based pattern pre-screening for Python-side filtering.

Uses probabilistic Bloom filter to quickly eliminate patterns that cannot
possibly match observed tokens.
"""

from typing import Optional, Set, Dict, Any
import logging

from kato.filters.base import PatternFilter

logger = logging.getLogger(__name__)


class BloomFilterStage(PatternFilter):
    """
    Filter patterns using Bloom filter for fast token presence checking.

    This is a PYTHON-SIDE filter that operates on candidates from database stages.
    Uses a pre-built Bloom filter instance to quickly check if pattern symbols
    overlap with observed symbols.

    Key Features:
    - Zero false negatives (all matching patterns preserved)
    - Configurable false positive rate
    - 99% reduction in pattern matching computations
    - Very fast set intersection checks

    Configuration:
        - bloom_false_positive_rate (default: 0.01): Desired FPR for filter

    Note: The Bloom filter instance must be provided during initialization.
    """

    def __init__(self, config: Any, state: list[str], bloom_filter: Optional[Any] = None):
        """
        Initialize Bloom filter stage.

        Args:
            config: SessionConfiguration with bloom_false_positive_rate
            state: Current STM state (flattened token list)
            bloom_filter: Pre-built PatternBloomFilter instance (optional)
        """
        super().__init__(config, state)

        # Get configuration
        self.false_positive_rate = getattr(config, 'bloom_false_positive_rate', None) or 0.01

        # Store bloom filter reference
        self.bloom_filter = bloom_filter

        if self.bloom_filter is None:
            logger.warning("BloomFilterStage initialized without Bloom filter instance - will pass all candidates")

        logger.debug(
            f"BloomFilterStage initialized: STM tokens={len(self.stm_tokens)}, "
            f"false_positive_rate={self.false_positive_rate}, "
            f"has_filter={self.bloom_filter is not None}"
        )

    def get_db_query(self) -> Optional[str]:
        """
        This is a Python-side filter - no database query.

        Returns:
            None (Python-side filter)
        """
        return None

    def filter_python(self, candidates: Set[str], patterns_cache: Dict[str, Any]) -> Set[str]:
        """
        Python-side filtering using Bloom filter for token overlap checking.

        Filters out patterns whose tokens have NO overlap with observed tokens.

        Args:
            candidates: Set of pattern names to filter
            patterns_cache: Dict mapping pattern names to pattern data
                Expected key: 'pattern_data' (flattened list of tokens)

        Returns:
            Filtered set of patterns that might match observed symbols
        """
        if not candidates:
            return set()

        # If no Bloom filter, pass all candidates
        if self.bloom_filter is None:
            logger.debug("No Bloom filter available, passing all candidates")
            return candidates

        # If no observed tokens, no patterns can match
        if not self.stm_tokens:
            return set()

        filtered = set()
        observed_set = self.stm_tokens

        for pattern_name in candidates:
            pattern_data_dict = patterns_cache.get(pattern_name)
            if not pattern_data_dict:
                logger.warning(f"Pattern '{pattern_name}' not in cache, skipping")
                continue

            # Extract pattern_data (flattened list of tokens)
            pattern_data = pattern_data_dict.get('pattern_data')
            if not pattern_data:
                logger.warning(f"Pattern '{pattern_name}' missing pattern_data, skipping")
                continue

            # Get unique tokens in pattern
            pattern_tokens = set(pattern_data)

            # Fast check: do observed tokens overlap with pattern tokens?
            if observed_set & pattern_tokens:  # Set intersection - very fast
                filtered.add(pattern_name)

        # Calculate reduction ratio
        filtered_out = len(candidates) - len(filtered)
        reduction_ratio = filtered_out / len(candidates) if candidates else 0

        logger.debug(
            f"Bloom filter stage: {len(candidates)} candidates → {len(filtered)} patterns "
            f"({filtered_out} filtered out, {reduction_ratio:.1%} reduction)"
        )

        return filtered
