"""
Jaccard similarity-based pattern filter for database-side filtering.

Filters patterns by token set overlap using ClickHouse's array functions
for efficient Jaccard similarity calculation.
"""

from typing import Optional, Set, Dict, Any
import logging

from kato.filters.base import PatternFilter

logger = logging.getLogger(__name__)


class JaccardFilter(PatternFilter):
    """
    Filter patterns by Jaccard similarity using database-side query.

    Uses precomputed 'token_set' field in ClickHouse to efficiently calculate
    Jaccard similarity = |intersection| / |union| using array functions.

    Configuration:
        - jaccard_threshold (default: 0.3): Minimum Jaccard similarity (0.0-1.0)
        - jaccard_min_overlap (default: 2): Minimum absolute token overlap count

    Example:
        STM tokens: {A, B, C, D}
        Pattern tokens: {B, C, E, F}
        Intersection: {B, C} → size = 2
        Union: {A, B, C, D, E, F} → size = 6
        Jaccard = 2/6 = 0.333

        Query filters:
        - Overlap >= 2 (passes)
        - Jaccard >= 0.3 (passes)
    """

    def __init__(self, config: Any, state: list[str]):
        """
        Initialize Jaccard filter.

        Args:
            config: SessionConfiguration with jaccard_threshold, jaccard_min_overlap
            state: Current STM state (flattened token list)
        """
        super().__init__(config, state)

        # Get configuration with defaults
        self.threshold = getattr(config, 'jaccard_threshold', None) or 0.3
        self.min_overlap = getattr(config, 'jaccard_min_overlap', None) or 2

        logger.debug(
            f"JaccardFilter initialized: STM tokens={len(self.stm_tokens)}, "
            f"threshold={self.threshold}, min_overlap={self.min_overlap}"
        )

    def get_db_query(self) -> Optional[str]:
        """
        Generate ClickHouse SQL query for Jaccard similarity filtering.

        Uses array functions for set operations:
        - arrayIntersect: Find common tokens
        - arrayConcat + arrayDistinct: Calculate union

        Returns:
            SQL query string filtering by Jaccard similarity
        """
        # Convert STM tokens to ClickHouse array literal
        stm_tokens_str = ", ".join(f"'{token}'" for token in self.stm_token_list)
        stm_array = f"[{stm_tokens_str}]"

        query = f"""
        SELECT name, pattern_data, length
        FROM patterns_data
        WHERE (
            -- Calculate intersection size
            length(arrayIntersect(token_set, {stm_array})) >= {self.min_overlap}
            AND
            -- Calculate Jaccard similarity
            length(arrayIntersect(token_set, {stm_array})) * 1.0 /
            length(arrayDistinct(arrayConcat(token_set, {stm_array}))) >= {self.threshold}
        )
        """

        return query

    def filter_python(self, candidates: Set[str], patterns_cache: Dict[str, Any]) -> Set[str]:
        """
        Python-side filtering (not used - this is a database filter).

        Args:
            candidates: Set of pattern names to filter
            patterns_cache: Dict mapping pattern names to pattern data

        Returns:
            Unchanged candidate set (filter runs database-side)
        """
        # Jaccard filtering is done database-side for performance
        # This method should never be called
        logger.warning("JaccardFilter.filter_python() called - filter should run database-side")
        return candidates
