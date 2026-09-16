"""
Filter pipeline executor for pattern matching optimization.

Manages sequential execution of filters with metrics collection and
optimization of database queries.
"""

import logging
import time
from itertools import chain
from typing import Any, Dict, List, Optional, Set

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
        return []

    def _get_all_patterns(self) -> Set[str]:
        """
        Query all patterns from database (with kb_id filtering).
        Used when filter_pipeline is empty to bypass filtering.

        Returns:
            Set of all pattern names in the knowledge base
        """
        query = """
            SELECT name, pattern_data, length
            FROM patterns_data
            WHERE kb_id = %(kb_id)s
        """

        try:
            result = self.clickhouse.query(query, parameters={'kb_id': self.kb_id})
            all_patterns = self._cache_result_rows(result)
            logger.info(f"Retrieved {len(all_patterns)} patterns from database (no filtering)")
            return all_patterns

        except Exception as e:
            logger.error(f"Failed to query all patterns: {e}")
            return set()

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
            logger.info("Empty filter pipeline, querying all patterns from database")
            return self._get_all_patterns()

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
                is_db_filter = filter_instance.is_database_filter()
                is_hybrid = filter_instance.is_hybrid_filter()

                logger.info(
                    f"Filter '{filter_name}': is_database={is_db_filter}, "
                    f"is_hybrid={is_hybrid}, initial_candidates={len(candidates) if candidates else 0}"
                )

                # Stage 1: Database-side filtering (if applicable)
                if is_db_filter:
                    candidates_before = len(candidates) if candidates else 0
                    candidates = self._execute_database_filter(filter_instance, candidates)
                    logger.info(
                        f"Filter '{filter_name}' DB stage: {candidates_before} → {len(candidates)} candidates"
                    )

                # Stage 2: Python-side filtering (if applicable)
                # This handles:
                # - Pure Python filters (bloom, rapidfuzz without DB stage)
                # - Hybrid filters (minhash - DB stage + Python verification)
                if not is_db_filter or is_hybrid:
                    # Ensure we have candidates from database stage
                    if candidates is None:
                        logger.error(
                            f"Python-side filter '{filter_name}' called before database filters. "
                            f"Pipeline must start with database filter!"
                        )
                        raise ValueError(
                            f"Pipeline must start with database filter, not '{filter_name}'"
                        )

                    # Run Python-side filtering
                    candidates_before_python = len(candidates)
                    logger.info(
                        f"Filter '{filter_name}' running Python stage on {candidates_before_python} candidates"
                    )
                    candidates = filter_instance.filter_python(candidates, self.patterns_cache)
                    logger.info(
                        f"Filter '{filter_name}' Python stage: {candidates_before_python} → {len(candidates)} candidates"
                    )

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

        # CRITICAL: Add kb_id filter FIRST for partition pruning.
        # Everything is bound server-side -- nothing derived from user input
        # (STM tokens, session thresholds, kb_id, candidate names) is ever
        # interpolated into statement text.
        parameters: Dict[str, Any] = {'kb_id': self.kb_id}
        filter_params = filter_instance.get_query_parameters()
        for reserved in ('kb_id', 'candidate_names'):
            if reserved in filter_params:
                raise ValueError(
                    f"Filter {filter_instance.get_filter_name()} may not bind "
                    f"reserved parameter {reserved!r}"
                )
        parameters.update(filter_params)

        kb_id_where = "kb_id = %(kb_id)s"

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
            candidate_list = list(existing_candidates)

            # Chunk large candidate sets to avoid ClickHouse max_query_size overflow
            # Each SHA1 hash is ~42 chars quoted; 500 * 42 = ~21KB per chunk (safe under 262KB limit)
            CHUNK_SIZE = 500
            if len(candidate_list) > CHUNK_SIZE:
                return self._execute_chunked_query(
                    query, kb_id_where, candidate_list, CHUNK_SIZE, parameters
                )

            candidates_where = "name IN %(candidate_names)s"
            parameters['candidate_names'] = tuple(candidate_list)

            # Inject WHERE clause into query (kb_id already added above)
            if "WHERE" in query:
                # Already has WHERE (kb_id), add AND condition for candidates
                query = query.replace("WHERE", f"WHERE {candidates_where} AND", 1)
                # This creates: WHERE name IN (...) AND kb_id = ... AND <filter conditions>
                # Move kb_id to beginning for partition pruning efficiency
                query = query.replace(f"WHERE {candidates_where} AND {kb_id_where}",
                                     f"WHERE {kb_id_where} AND {candidates_where}")
            else:
                # This shouldn't happen since we added kb_id above, but handle it
                query = query.replace(
                    "FROM patterns_data",
                    f"FROM patterns_data WHERE {kb_id_where} AND {candidates_where}"
                )

        # Execute query
        try:
            result = self.clickhouse.query(query, parameters=parameters)
            return self._cache_result_rows(result)

        except Exception as e:
            logger.error(f"Database query failed: {e}")
            # Safe to log: the query is now a parameterised template, so it
            # carries placeholders rather than user-supplied values.
            logger.error(f"Query was: {query}")
            # Return existing candidates on error to allow pipeline to continue
            return existing_candidates if existing_candidates else set()

    def _cache_result_rows(self, result) -> Set[str]:
        """Populate ``patterns_cache`` from a query result and return the names.

        The first column is always ``name``; every other column is cached under
        its own name, with ``pattern_data`` additionally stored flattened for
        similarity matching. Shared by the unfiltered, filtered and chunked
        query paths, which previously carried three copies of this loop.
        """
        names: Set[str] = set()
        column_names = result.column_names if hasattr(result, 'column_names') else []

        for row in result.result_rows:
            name = row[0]
            names.add(name)

            entry = self.patterns_cache.setdefault(name, {})

            for i, col_name in enumerate(column_names):
                if i == 0:
                    continue  # Skip 'name' column (already used as key)

                value = row[i] if i < len(row) else None

                # pattern_data is kept both event-structured (for Prediction)
                # and flattened (for similarity matching)
                if col_name == 'pattern_data' and value:
                    entry['pattern_data'] = value
                    entry['pattern_data_flat'] = list(chain(*value))
                else:
                    entry[col_name] = value

        return names

    def _execute_chunked_query(self, base_query: str, kb_id_where: str,
                               candidate_list: List[str], chunk_size: int,
                               parameters: Dict[str, Any]) -> Set[str]:
        """Execute a query with large candidate sets by chunking the IN clause.

        Avoids ClickHouse max_query_size overflow when candidate count exceeds
        ~500 (each SHA1 hash is ~42 chars quoted).

        Args:
            base_query: The filter query with WHERE clause already containing kb_id
            kb_id_where: The kb_id WHERE clause fragment (a bind placeholder)
            candidate_list: Full list of candidate pattern names
            chunk_size: Maximum candidates per IN clause
            parameters: Bind parameters for the query (kb_id plus any the
                filter contributed); each chunk adds its own candidate names.

        Returns:
            Set of candidate names passing the filter across all chunks
        """
        all_candidates = set()

        candidates_where = "name IN %(candidate_names)s"
        if "WHERE" in base_query:
            chunk_query = base_query.replace("WHERE", f"WHERE {candidates_where} AND", 1)
            chunk_query = chunk_query.replace(
                f"WHERE {candidates_where} AND {kb_id_where}",
                f"WHERE {kb_id_where} AND {candidates_where}"
            )
        else:
            chunk_query = base_query.replace(
                "FROM patterns_data",
                f"FROM patterns_data WHERE {kb_id_where} AND {candidates_where}"
            )

        for i in range(0, len(candidate_list), chunk_size):
            chunk = candidate_list[i:i + chunk_size]
            chunk_params = dict(parameters, candidate_names=tuple(chunk))

            try:
                result = self.clickhouse.query(chunk_query, parameters=chunk_params)
                all_candidates |= self._cache_result_rows(result)
            except Exception as e:
                logger.error(f"Chunked query failed (chunk {i//chunk_size + 1}): {e}")

        logger.debug(f"Chunked query: {len(candidate_list)} candidates in "
                     f"{(len(candidate_list) + chunk_size - 1) // chunk_size} chunks, "
                     f"{len(all_candidates)} results")
        return all_candidates

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
