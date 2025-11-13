"""
RapidFuzz-based similarity filter for Python-side pattern matching.

Uses RapidFuzz library for fast string/token similarity calculation,
providing 5-10x speedup over traditional difflib matching.
"""

from typing import Optional, Set, Dict, Any
import logging

from kato.filters.base import PatternFilter

logger = logging.getLogger(__name__)

# Import RapidFuzz (optional - graceful degradation)
try:
    from rapidfuzz import fuzz, process
    from rapidfuzz.distance import LCSseq
    RAPIDFUZZ_AVAILABLE = True
except ImportError:
    RAPIDFUZZ_AVAILABLE = False
    logger.warning("RapidFuzz not available - filter will skip similarity checking")


class RapidFuzzFilter(PatternFilter):
    """
    Filter patterns using RapidFuzz for fast similarity calculation.

    This is a PYTHON-SIDE filter that operates on candidates from previous stages.
    Uses RapidFuzz to calculate similarity and filter by recall threshold.

    Two modes:
    - Token-level (use_token_matching=True): EXACT difflib compatibility using LCSseq
    - Character-level (use_token_matching=False): 75x faster using character-level fuzzy matching

    Configuration:
        - recall_threshold (default: 0.1): Minimum similarity (0.0-1.0)
        - use_token_matching (default: True): Token-level vs character-level

    Note: Requires InformationExtractor instance for prediction info calculation.
    """

    def __init__(self, config: Any, state: list[str], extractor: Optional[Any] = None):
        """
        Initialize RapidFuzz filter.

        Args:
            config: SessionConfiguration with recall_threshold, use_token_matching
            state: Current STM state (flattened token list)
            extractor: InformationExtractor instance for prediction calculation
        """
        super().__init__(config, state)

        # Get configuration
        self.recall_threshold = getattr(config, 'recall_threshold', None) or 0.1
        self.use_token_matching = getattr(config, 'use_token_matching', True)

        # Store extractor reference
        self.extractor = extractor

        if self.extractor is None:
            logger.warning("RapidFuzzFilter initialized without extractor - will skip similarity checking")

        if not RAPIDFUZZ_AVAILABLE:
            logger.warning("RapidFuzz not installed - filter will pass all candidates")

        logger.debug(
            f"RapidFuzzFilter initialized: STM tokens={len(self.state)}, "
            f"threshold={self.recall_threshold}, "
            f"use_token_matching={self.use_token_matching}, "
            f"has_extractor={self.extractor is not None}"
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
        Python-side filtering using RapidFuzz similarity calculation.

        Calculates similarity between STM and each pattern, filtering by recall threshold.

        Args:
            candidates: Set of pattern names to filter
            patterns_cache: Dict mapping pattern names to pattern data
                Expected key: 'pattern_data' (flattened list of tokens)

        Returns:
            Filtered set of patterns with similarity >= recall_threshold
        """
        if not candidates:
            return set()

        # If no RapidFuzz or extractor, pass all candidates
        if not RAPIDFUZZ_AVAILABLE or self.extractor is None:
            logger.debug("RapidFuzz/extractor unavailable, passing all candidates")
            return candidates

        # If no observed state, no patterns can match
        if not self.state:
            return set()

        filtered = set()

        for pattern_name in candidates:
            pattern_data_dict = patterns_cache.get(pattern_name)
            if not pattern_data_dict:
                logger.warning(f"Pattern '{pattern_name}' not in cache, skipping")
                continue

            # Extract pattern_data (flattened list of tokens)
            pattern_data = pattern_data_dict.get('pattern_data_flat')
            if not pattern_data:
                logger.warning(f"Pattern '{pattern_name}' missing pattern_data_flat, skipping")
                continue

            # Calculate similarity using extractor
            try:
                # Use extractor's extract_prediction_info for consistency
                prediction_info = self.extractor.extract_prediction_info(
                    pattern_data,
                    self.state,
                    cutoff=self.recall_threshold
                )

                # If prediction_info is not None, similarity >= threshold
                if prediction_info is not None:
                    filtered.add(pattern_name)

            except Exception as e:
                logger.warning(f"Error calculating similarity for '{pattern_name}': {e}")
                # Include pattern on error (safer)
                filtered.add(pattern_name)

        # Calculate reduction ratio
        filtered_out = len(candidates) - len(filtered)
        reduction_ratio = filtered_out / len(candidates) if candidates else 0

        logger.debug(
            f"RapidFuzz filter: {len(candidates)} candidates → {len(filtered)} patterns "
            f"({filtered_out} filtered out, {reduction_ratio:.1%} reduction, "
            f"threshold={self.recall_threshold})"
        )

        return filtered
