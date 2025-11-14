"""
Base class for pattern filtering stages.

Provides abstract interface that all filters must implement.
"""

from abc import ABC, abstractmethod
from typing import Optional, Set, List, Dict, Any
import logging

logger = logging.getLogger(__name__)


class PatternFilter(ABC):
    """
    Base class for pattern filtering stages.

    Filters can be database-side (generate SQL queries) or Python-side
    (operate on loaded data). The pipeline executor determines which type
    and applies them appropriately.
    """

    def __init__(self, config: Any, state: List[str]):
        """
        Initialize filter with session config and current state.

        Args:
            config: SessionConfig with filter parameters
            state: Current STM state (flattened list of tokens)
        """
        self.config = config
        self.state = state
        self.stm_length = len(state)
        self.stm_tokens = set(state)
        self.stm_token_list = list(self.stm_tokens)

    @abstractmethod
    def get_db_query(self) -> Optional[str]:
        """
        Return ClickHouse SQL query for database-side filtering.

        Returns None if this is a Python-side filter.

        Returns:
            SQL query string or None
        """
        pass

    @abstractmethod
    def filter_python(self, candidates: Set[str], patterns_cache: Dict[str, Any]) -> Set[str]:
        """
        Python-side filtering logic (for non-database filters).

        Args:
            candidates: Set of pattern names to filter
            patterns_cache: Dict mapping pattern names to pattern data

        Returns:
            Filtered set of pattern names
        """
        pass

    def is_database_filter(self) -> bool:
        """Check if this filter runs on database side."""
        return self.get_db_query() is not None

    def is_hybrid_filter(self) -> bool:
        """
        Check if this filter is hybrid (both database and Python stages).

        Hybrid filters run a database query first, then Python-side verification.
        By default, only MinHash is hybrid. Override this for other hybrid filters.

        Returns:
            True if filter should run both database and Python stages
        """
        # Check if this is MinHashFilter by class name
        return 'MinHash' in self.__class__.__name__

    def get_filter_name(self) -> str:
        """Get human-readable filter name."""
        return self.__class__.__name__.replace('Filter', '').replace('Stage', '').lower()
