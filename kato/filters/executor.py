"""
Filter pipeline executor for pattern matching optimization.

Manages sequential execution of filters with metrics collection and
optimization of database queries.
"""

import time
import logging
from typing import Set, Dict, List, Any, Optional

from kato.filters.base import PatternFilter

logger = logging.getLogger(__name__)


class FilterPipelineExecutor:
    """
    Executes configurable filter pipeline sequentially.

    Handles both database-side and Python-side filters, optimizing
    database queries and collecting performance metrics.
    """

    # Registry mapping filter names to filter classes
    FILTER_REGISTRY: Dict[str, type] = {}

    def __init__(self,
                 config: Any,
                 state: List[str],
                 clickhouse_client: Any,
                 redis_client: Any,
                 kb_id: str,
                 bloom_filter: Optional[Any] = None,
                 extractor: Optional[Any] = None):
        """
        Initialize filter pipeline executor.

        Args:
            config: SessionConfiguration with filter parameters
            state: Current STM state (flattened token list)
            clickhouse_client: ClickHouse database client
            redis_client: Redis client for metadata
            kb_id: Knowledge base / node / processor identifier (for isolation)
            bloom_filter: Optional Bloom filter instance
            extractor: Optional prediction info extractor (for RapidFuzz)
        """
        self.config = config
        self.state = state
        self.clickhouse = clickhouse_client
        self.redis = redis_client
        self.kb_id = kb_id  # For ClickHouse partition pruning
        self.bloom_filter = bloom_filter
        self.extractor = extractor

        # Cache for loaded patterns
        self.patterns_cache: Dict[str, Any] = {}

        # Metrics tracking
        self.stage_metrics: List[Dict[str, Any]] = []

        # Get filter pipeline from config or use default
        self.filter_pipeline = self._get_filter_pipeline()

    def _get_filter_pipeline(self) -> List[str]:
        """Get filter pipeline from config or return default."""
        if self.config.filter_pipeline is not None:
            return self.config.filter_pipeline

        # Default pipeline if not configured
        return ["length", "jaccard", "rapidfuzz"]

    @classmethod
    def register_filter(cls, name: str, filter_class: type):
        """
        Register a filter in the global registry.

        Args:
            name: Filter name (e.g., "length", "minhash")
            filter_class: Filter class implementing PatternFilter
        """
        cls.FILTER_REGISTRY[name] = filter_class
        logger.debug(f"Registered filter: {name}")

    def execute_pipeline(self) -> Set[str]:
        """
        Execute filter pipeline sequentially.

        Returns:
            Set of pattern names that passed all filters
        """
        if not self.filter_pipeline:
            logger.info("Empty filter pipeline, returning empty set")
            return set()

        candidates: Optional[Set[str]] = None
        pipeline_start = time.time()

        for filter_name in self.filter_pipeline:
            stage_start = time.time()

            # Get filter class from registry
            filter_class = self.FILTER_REGISTRY.get(filter_name)
            if not filter_class:
                logger.warning(f"Unknown filter '{filter_name}', skipping")
                continue

            # Initialize filter with appropriate dependencies
            filter_instance = self._create_filter_instance(filter_class, filter_name)
            if not filter_instance:
                logger.warning(f"Failed to create filter instance for '{filter_name}', skipping")
                continue

            # Execute filter
            try:
                if filter_instance.is_database_filter():
                    # Database-side filter
                    candidates = self._execute_database_filter(filter_instance, candidates)
                else:
                    # Python-side filter
                    if candidates is None:
                        logger.error(
                            f"Python-side filter '{filter_name}' called before database filters. "
                            f"Pipeline must start with database filter!"
                        )
                        raise ValueError(
                            f"Pipeline must start with database filter, not '{filter_name}'"
                        )

                    candidates = filter_instance.filter_python(candidates, self.patterns_cache)

            except Exception as e:
                logger.error(f"Filter '{filter_name}' failed with error: {e}")
                # Continue with next filter rather than failing entire pipeline
                continue

            # Record metrics
            stage_time = (time.time() - stage_start) * 1000
            candidate_count = len(candidates) if candidates else 0

            self.stage_metrics.append({
                "filter": filter_name,
                "candidates_after": candidate_count,
                "time_ms": round(stage_time, 2)
            })

            # Log metrics if enabled
            if self.config.enable_filter_metrics:
                logger.info(
                    f"Filter '{filter_name}': {candidate_count} candidates ({stage_time:.1f}ms)"
                )

            # Safety check: max candidates per stage
            max_candidates = getattr(self.config, 'max_candidates_per_stage', 100000)
            if max_candidates and candidate_count > max_candidates:
                logger.warning(
                    f"Filter '{filter_name}' exceeded max_candidates_per_stage "
                    f"({candidate_count} > {max_candidates})"
                )

            # Early exit if no candidates
            if candidate_count == 0:
                logger.info("No candidates remaining, stopping pipeline early")
                break

        # Log total pipeline time
        pipeline_time = (time.time() - pipeline_start) * 1000
        final_count = len(candidates) if candidates else 0
        logger.info(
            f"Filter pipeline complete: {final_count} final candidates "
            f"({pipeline_time:.1f}ms total)"
        )

        return candidates if candidates else set()

    def _create_filter_instance(self, filter_class: type, filter_name: str) -> Optional[PatternFilter]:
        """
        Create filter instance with appropriate dependencies.

        Args:
            filter_class: Filter class to instantiate
            filter_name: Name of the filter (for dependency injection)

        Returns:
            Filter instance or None if creation failed
        """
        try:
            # Base filters just need config and state
            if filter_name in ['length', 'jaccard', 'minhash']:
                return filter_class(self.config, self.state)

            # Bloom filter needs bloom_filter instance
            elif filter_name == 'bloom':
                return filter_class(self.config, self.state, self.bloom_filter)

            # RapidFuzz filter needs extractor
            elif filter_name == 'rapidfuzz':
                return filter_class(self.config, self.state, self.extractor)

            # Unknown filter - try basic initialization
            else:
                return filter_class(self.config, self.state)

        except Exception as e:
            logger.error(f"Failed to create filter instance '{filter_name}': {e}")
            return None

    def _execute_database_filter(
        self,
        filter_instance: PatternFilter,
        existing_candidates: Optional[Set[str]]
    ) -> Set[str]:
        """
        Execute database-side filter.

        If existing_candidates is None (first filter), query all patterns.
        If existing_candidates exists, refine query to only those candidates.

        Args:
            filter_instance: Filter to execute
            existing_candidates: Existing candidate set (or None)

        Returns:
            New filtered candidate set
        """
        query = filter_instance.get_db_query()

        if not query:
            logger.warning(
                f"Filter {filter_instance.get_filter_name()} returned empty query"
            )
            return existing_candidates if existing_candidates else set()

        # CRITICAL: Add kb_id filter FIRST for partition pruning
        kb_id_where = f"kb_id = '{self.kb_id}'"

        if "WHERE" not in query:
            # No WHERE clause yet, add kb_id filter
            query = query.replace(
                "FROM patterns_data",
                f"FROM patterns_data WHERE {kb_id_where}"
            )
        else:
            # Already has WHERE, inject kb_id as first condition
            query = query.replace("WHERE", f"WHERE {kb_id_where} AND", 1)

        # Refine query if we have existing candidates
        if existing_candidates is not None and len(existing_candidates) > 0:
            # Add WHERE clause to filter by existing candidates
            # Limit to first 10,000 to avoid query size issues
            candidate_list = list(existing_candidates)[:10000]
            candidate_str = ", ".join(f"'{c}'" for c in candidate_list)

            # Inject WHERE clause into query (kb_id already added above)
            if "WHERE" in query:
                # Already has WHERE (kb_id), add AND condition for candidates
                query = query.replace("WHERE", f"WHERE name IN ({candidate_str}) AND", 1)
                # This creates: WHERE name IN (...) AND kb_id = '...' AND <filter conditions>
                # Move kb_id to beginning for partition pruning efficiency
                query = query.replace(f"WHERE name IN ({candidate_str}) AND {kb_id_where}",
                                     f"WHERE {kb_id_where} AND name IN ({candidate_str})")
            else:
                # This shouldn't happen since we added kb_id above, but handle it
                query = query.replace(
                    "FROM patterns_data",
                    f"FROM patterns_data WHERE {kb_id_where} AND name IN ({candidate_str})"
                )

        # Execute query
        try:
            result = self.clickhouse.query(query)

            # Extract candidate names and cache ALL columns for Python-side filters
            new_candidates = set()
            column_names = result.column_names if hasattr(result, 'column_names') else []

            for row in result.result_rows:
                # First column is always 'name'
                name = row[0]
                new_candidates.add(name)

                # Cache ALL columns as dict for Python-side filters
                if name not in self.patterns_cache:
                    self.patterns_cache[name] = {}

                # Map column names to values
                for i, col_name in enumerate(column_names):
                    if i == 0:
                        continue  # Skip 'name' column (already used as key)

                    value = row[i] if i < len(row) else None

                    # Special handling for pattern_data: store both event-structured and flattened versions
                    if col_name == 'pattern_data' and value:
                        from itertools import chain
                        # Store original event-structured for Prediction class
                        self.patterns_cache[name]['pattern_data'] = value
                        # Store flattened version for similarity matching
                        self.patterns_cache[name]['pattern_data_flat'] = list(chain(*value))
                    else:
                        self.patterns_cache[name][col_name] = value

            return new_candidates

        except Exception as e:
            logger.error(f"Database query failed: {e}")
            logger.error(f"Query was: {query}")
            # Return existing candidates on error to allow pipeline to continue
            return existing_candidates if existing_candidates else set()

    def get_metrics(self) -> Dict[str, Any]:
        """
        Return pipeline execution metrics.

        Returns:
            Dictionary with metrics for all executed stages
        """
        return {
            "stages": self.stage_metrics,
            "total_stages": len(self.stage_metrics),
            "final_candidates": (
                self.stage_metrics[-1]["candidates_after"]
                if self.stage_metrics
                else 0
            )
        }
