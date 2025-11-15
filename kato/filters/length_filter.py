"""
Length-based pattern filter for database-side filtering.

Filters patterns by total token count relative to STM length using
ClickHouse's precomputed length field.
"""

from typing import Optional, Set, Dict, Any
import logging

from kato.filters.base import PatternFilter

logger = logging.getLogger(__name__)


class LengthFilter(PatternFilter):
    """
    Filter patterns by length using database-side query.

    Uses precomputed 'length' field in ClickHouse to efficiently filter
    patterns that are too short or too long relative to the STM.

    Configuration:
        - length_min_ratio (default: 0.5): Min pattern length as ratio of STM length
        - length_max_ratio (default: 2.0): Max pattern length as ratio of STM length

    Example:
        STM length = 10 tokens
        min_ratio = 0.5 → min_length = 5
        max_ratio = 2.0 → max_length = 20
        Query: WHERE length BETWEEN 5 AND 20
    """

    def __init__(self, config: Any, state: list[str]):
        """
        Initialize length filter.

        Args:
            config: SessionConfiguration with length_min_ratio, length_max_ratio
            state: Current STM state (flattened token list)
        """
        super().__init__(config, state)

        # Get configuration with defaults
        self.min_ratio = getattr(config, 'length_min_ratio', None) or 0.5
        self.max_ratio = getattr(config, 'length_max_ratio', None) or 2.0

        # Calculate length bounds
        self.min_length = max(1, int(self.stm_length * self.min_ratio))
        self.max_length = int(self.stm_length * self.max_ratio)

        logger.debug(
            f"LengthFilter initialized: STM length={self.stm_length}, "
            f"min_ratio={self.min_ratio}, max_ratio={self.max_ratio}, "
            f"min_length={self.min_length}, max_length={self.max_length}"
        )

    def get_db_query(self) -> Optional[str]:
        """
        Generate ClickHouse SQL query for length-based filtering.

        Returns:
            SQL query string filtering by length bounds
        """
        query = f"""
        SELECT name, pattern_data, length
        FROM patterns_data
        WHERE length BETWEEN {self.min_length} AND {self.max_length}
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
        # Length filtering is done database-side for performance
        # This method should never be called
        logger.warning("LengthFilter.filter_python() called - filter should run database-side")
        return candidates
